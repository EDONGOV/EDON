/**
 * EDON JavaScript/TypeScript SDK — EdonClient
 *
 * Three calls cover the full governed agent loop:
 *   beginIntent()  — register a session intent contract upfront
 *   evaluate()     — govern an action before executing it
 *   scanOutput()   — scan a tool response before the agent uses it
 *
 * @example
 * ```ts
 * import { EdonClient } from '@edon/sdk'
 *
 * const client = new EdonClient({ token: process.env.EDON_API_KEY! })
 *
 * const intentId = await client.beginIntent({
 *   objective: 'Summarise patient records',
 *   allowedTools: ['database.query', 'llm.complete'],
 * })
 *
 * const result = await client.evaluate({
 *   actionType: 'database.query',
 *   payload: { query: 'SELECT * FROM patients WHERE id = 42' },
 * })
 *
 * if (result.verdict === 'ALLOW') {
 *   const raw = await runQuery()
 *   const scan = await client.scanOutput({ response: raw, actionType: 'database.query', actionId: result.actionId })
 *   if (scan.verdict !== 'BLOCK') use(scan.payload)
 * }
 * ```
 */

import { VERSION } from './version'
import {
  APIConnectionError,
  APIError,
  APITimeoutError,
} from './errors'

export { VERSION } from './version'

const DEFAULT_BASE_URL = 'https://edon-gateway-prod.fly.dev'
const DEFAULT_TIMEOUT_MS = 10_000
const DEFAULT_MAX_RETRIES = 2
const RETRY_STATUSES = new Set([429, 500, 502, 503, 504])
const BASE_DELAY_MS = 500
const MAX_DELAY_MS = 8_000

// ── Public types ─────────────────────────────────────────────────────────────

export interface EdonClientOptions {
  /** Your EDON API key (starts with `edon-`). */
  token: string
  /** Gateway base URL. Defaults to production. */
  baseUrl?: string
  /** HTTP timeout in milliseconds. Default 10 000. */
  timeoutMs?: number
  /** Default agent ID used when not passed per-call. */
  agentId?: string
  /** Automatic retries on 429 / 5xx. Default 2. */
  maxRetries?: number
}

export interface BeginIntentOptions {
  /** Plain-English description of what the agent will do. */
  objective: string
  /** `"tool.op"` strings the agent needs, e.g. `["database.query", "email.send"]`. */
  allowedTools: string[]
  /** Max acceptable risk. Default `"MEDIUM"`. */
  riskCeiling?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  /** Optional extra constraints forwarded to the policy engine. */
  constraints?: Record<string, unknown>
  /** Supply your own intent ID, or let EDON generate one. */
  intentId?: string
  /** Intent expiry in seconds. Default 3600. */
  ttlSeconds?: number
}

export interface EvaluateOptions {
  /** `tool.operation` string, e.g. `"database.query"`. */
  actionType: string
  /** Action parameters (tool-specific). */
  payload: Record<string, unknown>
  /** Agent identifier. Overrides client-level `agentId`. */
  agentId?: string
  /** Intent ID to scope this action under. Defaults to active intent. */
  intentId?: string
  /** Why the agent is taking this action — improves alignment scoring. */
  statedIntent?: string
  /** Max retries on PAUSE verdict. Default 3. */
  maxRetries?: number
}

export interface EvaluateResult {
  verdict: 'ALLOW' | 'BLOCK' | 'ESCALATE' | 'DEGRADE' | 'PAUSE' | 'ERROR'
  reasonCode: string
  explanation: string
  actionId: string | null
  /** (DEGRADE only) Modified params to use instead of original. */
  safeAlternative: Record<string, unknown> | null
  /** (ESCALATE only) Question to show the human reviewer. */
  escalationQuestion: string | null
  escalationOptions: string[]
  /** `true` if EDON was unreachable and fail-open was applied. */
  fallback: boolean
}

export interface ScanOutputOptions {
  /** Raw tool response — any JSON-serialisable value. */
  response: unknown
  /** Same `actionType` used in `evaluate()` — for audit linking. */
  actionType: string
  /** Agent identifier. Overrides client-level `agentId`. */
  agentId?: string
  /** `actionId` from the `evaluate()` result — links audit records. */
  actionId?: string | null
}

export interface ScanOutputResult {
  verdict: 'PASS' | 'REDACT' | 'BLOCK'
  /** Safe payload to use — redacted if `REDACT`, `null` if `BLOCK`. */
  payload: unknown
  findings: Array<{ category: string; pattern: string; count: number }>
  redacted: boolean
  actionId: string | null
  /** `true` if EDON was unreachable and the original response was returned. */
  fallback: boolean
}

// ── Client ────────────────────────────────────────────────────────────────────

export class EdonClient {
  private readonly token: string
  private readonly baseUrl: string
  private readonly timeoutMs: number
  private readonly maxRetries: number
  readonly agentId: string
  private activeIntentId: string | null = null

  constructor(options: EdonClientOptions) {
    if (!options.token) {
      throw new Error('EDON API key is required. Pass token: or set EDON_API_KEY.')
    }
    this.token = options.token
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, '')
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES
    this.agentId = options.agentId ?? 'edon-agent'
  }

  // ── Intent contract ─────────────────────────────────────────────────────────

  async beginIntent(options: BeginIntentOptions): Promise<string> {
    const intentId = options.intentId ?? `intent_${randomHex(16)}`
    const riskCeiling = (options.riskCeiling ?? 'MEDIUM').toUpperCase()
    const scope: Record<string, string[]> = {}
    for (const entry of options.allowedTools) {
      const dotIdx = entry.indexOf('.')
      const tool = dotIdx === -1 ? entry : entry.slice(0, dotIdx)
      const op = dotIdx === -1 ? '*' : entry.slice(dotIdx + 1)
      ;(scope[tool] ??= []).push(op)
    }
    const body = {
      intent_id: intentId,
      objective: options.objective,
      scope,
      constraints: {
        max_risk_level: riskCeiling,
        ttl_seconds: options.ttlSeconds ?? 3600,
        ...(options.constraints ?? {}),
      },
      risk_level: riskCeiling.toLowerCase(),
      approved_by_user: false,
    }
    try {
      await this._post('/intent/set', body)
    } catch {
      // Non-fatal — governance falls back gracefully without the intent record
    }
    this.activeIntentId = intentId
    return intentId
  }

  // ── Input governance ────────────────────────────────────────────────────────

  async evaluate(options: EvaluateOptions): Promise<EvaluateResult> {
    const agentId = options.agentId ?? this.agentId
    const intentId = options.intentId ?? this.activeIntentId
    const pauseRetries = options.maxRetries ?? 3

    const body: Record<string, unknown> = {
      agent_id: agentId,
      action_type: options.actionType,
      action_payload: options.payload,
      timestamp: new Date().toISOString(),
      context: {
        stated_intent: options.statedIntent ?? '',
        ...(intentId ? { intent_id: intentId } : {}),
      },
    }

    for (let attempt = 0; attempt < pauseRetries; attempt++) {
      let resp: Record<string, unknown>
      try {
        resp = await this._post('/v1/action', body)
      } catch (err) {
        return failOpen(err)
      }

      const verdict = ((resp['decision'] ?? resp['verdict'] ?? 'ALLOW') as string) as EvaluateResult['verdict']

      if (verdict === 'PAUSE') {
        await sleep(5_000 * (attempt + 1))
        continue
      }

      return buildEvaluateResult(resp, verdict, false)
    }

    return {
      verdict: 'BLOCK',
      reasonCode: 'PAUSE_TIMEOUT',
      explanation: `Exhausted ${pauseRetries} PAUSE retries.`,
      actionId: null,
      safeAlternative: null,
      escalationQuestion: null,
      escalationOptions: [],
      fallback: false,
    }
  }

  // ── Output governance ───────────────────────────────────────────────────────

  async scanOutput(options: ScanOutputOptions): Promise<ScanOutputResult> {
    const body = {
      agent_id: options.agentId ?? this.agentId,
      action_type: options.actionType,
      action_id: options.actionId ?? null,
      response: options.response,
    }
    try {
      const resp = await this._post('/v1/output', body)
      return {
        verdict: ((resp['verdict'] ?? 'PASS') as string) as ScanOutputResult['verdict'],
        payload: resp['payload'] ?? options.response,
        findings: (resp['findings'] ?? []) as ScanOutputResult['findings'],
        redacted: Boolean(resp['redacted']),
        actionId: (options.actionId ?? null) as string | null,
        fallback: false,
      }
    } catch {
      return {
        verdict: 'PASS',
        payload: options.response,
        findings: [],
        redacted: false,
        actionId: (options.actionId ?? null) as string | null,
        fallback: true,
      }
    }
  }

  // ── Utility ─────────────────────────────────────────────────────────────────

  async health(): Promise<Record<string, unknown>> {
    try {
      return await this._get('/health')
    } catch (err) {
      return { status: 'unreachable', error: String(err) }
    }
  }

  endIntent(): void {
    this.activeIntentId = null
  }

  // ── Internal HTTP ────────────────────────────────────────────────────────────

  private _sdkHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      'X-EDON-TOKEN': this.token,
      'User-Agent': `edon-js/${VERSION}`,
      'X-EDON-SDK-Version': VERSION,
      'X-EDON-SDK-Language': 'javascript',
    }
  }

  private async _post(path: string, body: unknown): Promise<Record<string, unknown>> {
    return this._fetch('POST', path, JSON.stringify(body))
  }

  private async _get(path: string): Promise<Record<string, unknown>> {
    return this._fetch('GET', path)
  }

  private async _fetch(
    method: string,
    path: string,
    bodyStr?: string,
  ): Promise<Record<string, unknown>> {
    const url = `${this.baseUrl}${path}`

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0) {
        await sleep(retryDelay(attempt - 1))
      }

      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), this.timeoutMs)

      let res: Response
      try {
        res = await fetch(url, {
          method,
          headers: this._sdkHeaders(),
          body: bodyStr,
          signal: controller.signal,
        })
      } catch (err: unknown) {
        clearTimeout(timer)
        if (err instanceof Error && err.name === 'AbortError') {
          throw new APITimeoutError(`Request to ${url} timed out`)
        }
        throw new APIConnectionError(`Could not reach EDON gateway at ${this.baseUrl}`, err)
      } finally {
        clearTimeout(timer)
      }

      if (res.ok) {
        return (await res.json()) as Record<string, unknown>
      }

      // Parse error body before deciding to retry
      let errBody: Record<string, unknown> = {}
      try {
        errBody = (await res.json()) as Record<string, unknown>
      } catch {
        errBody = { error: await res.text().catch(() => res.statusText) }
      }
      const requestId = res.headers.get('X-Request-ID') ?? res.headers.get('X-Request-Id')
      const apiErr = APIError.fromResponse(res.status, errBody, requestId)

      if (attempt < this.maxRetries && RETRY_STATUSES.has(res.status)) {
        const retryAfterHeader = res.headers.get('Retry-After')
        if (retryAfterHeader) {
          const ra = parseFloat(retryAfterHeader)
          if (!isNaN(ra)) await sleep(Math.min(ra * 1000, 60_000))
        }
        continue
      }

      throw apiErr
    }

    // Unreachable but satisfies TS
    throw new APIConnectionError('Unexpected retry loop exit')
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildEvaluateResult(
  resp: Record<string, unknown>,
  verdict: EvaluateResult['verdict'],
  fallback: boolean,
): EvaluateResult {
  return {
    verdict,
    reasonCode: ((resp['reason_code'] ?? resp['decision_reason'] ?? '') as string),
    explanation: ((resp['explanation'] ?? '') as string),
    actionId: (resp['action_id'] ?? null) as string | null,
    safeAlternative: (resp['safe_alternative'] ?? null) as Record<string, unknown> | null,
    escalationQuestion: (resp['escalation_question'] ?? null) as string | null,
    escalationOptions: (resp['escalation_options'] ?? []) as string[],
    fallback,
  }
}

function failOpen(err: unknown): EvaluateResult {
  return {
    verdict: 'ALLOW',
    reasonCode: 'GATEWAY_UNREACHABLE',
    explanation: `EDON gateway unreachable — fail-open applied: ${err}`,
    actionId: null,
    safeAlternative: null,
    escalationQuestion: null,
    escalationOptions: [],
    fallback: true,
  }
}

function retryDelay(attempt: number): number {
  const base = BASE_DELAY_MS * Math.pow(2, attempt)
  const jitter = Math.random() * base * 0.25
  return Math.min(base + jitter, MAX_DELAY_MS)
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function randomHex(len: number): string {
  const bytes = new Uint8Array(len / 2)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes)
  } else {
    // Node.js < 19 (no globalThis.crypto)
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const nodeCrypto = require('crypto') as typeof import('crypto')
    const buf = nodeCrypto.randomBytes(len / 2)
    bytes.set(buf)
  }
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}
