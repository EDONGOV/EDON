/**
 * Unit tests for EdonClient.
 *
 * Mocks global.fetch — no real network traffic.
 * Run with: npm test
 */
import {
  EdonClient,
  APIError,
  AuthenticationError,
  RateLimitError,
  GatewayError,
  APIConnectionError,
  APITimeoutError,
} from '../src/index'

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockOk(body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function mockErr(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

const TOKEN = 'edon-test-token-abc123'

// ── Constructor ───────────────────────────────────────────────────────────────

describe('EdonClient constructor', () => {
  it('throws when token is empty string', () => {
    expect(() => new EdonClient({ token: '' })).toThrow('EDON API key is required')
  })

  it('accepts a valid token without throwing', () => {
    expect(() => new EdonClient({ token: TOKEN })).not.toThrow()
  })
})

// ── evaluate() ────────────────────────────────────────────────────────────────

describe('EdonClient.evaluate()', () => {
  afterEach(() => jest.restoreAllMocks())

  it('returns ALLOW verdict on 200', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ verdict: 'ALLOW', reason_code: 'APPROVED', explanation: 'ok', action_id: 'act-1' }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.evaluate({ actionType: 'email.send', payload: {} })

    expect(result.verdict).toBe('ALLOW')
    expect(result.reasonCode).toBe('APPROVED')
    expect(result.actionId).toBe('act-1')
    expect(result.fallback).toBe(false)
  })

  it('returns fail-open on network error', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    const client = new EdonClient({ token: TOKEN, maxRetries: 0 })
    const result = await client.evaluate({ actionType: 'email.send', payload: {} })

    expect(result.verdict).toBe('ALLOW')
    expect(result.fallback).toBe(true)
    expect(result.reasonCode).toBe('GATEWAY_UNREACHABLE')
  })

  it('returns fail-open on 401 — governance does not crash agents', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockErr(401, { detail: 'Invalid API key' }),
    )
    const client = new EdonClient({ token: 'bad-key', maxRetries: 0 })
    const result = await client.evaluate({ actionType: 'email.send', payload: {} })

    expect(result.verdict).toBe('ALLOW')
    expect(result.fallback).toBe(true)
  })

  it('maps DEGRADE verdict with safeAlternative', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ verdict: 'DEGRADE', reason_code: 'RISK_TOO_HIGH', safe_alternative: { limit: 10 } }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.evaluate({ actionType: 'database.query', payload: { limit: 1000 } })

    expect(result.verdict).toBe('DEGRADE')
    expect(result.safeAlternative).toEqual({ limit: 10 })
  })

  it('maps ESCALATE verdict with escalationQuestion', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ verdict: 'ESCALATE', escalation_question: 'Should this bulk export proceed?' }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.evaluate({ actionType: 'bulk.export', payload: {} })

    expect(result.verdict).toBe('ESCALATE')
    expect(result.escalationQuestion).toBe('Should this bulk export proceed?')
  })

  it('retries on 500 and succeeds on second call', async () => {
    const spy = jest
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(mockErr(500, { detail: 'Server error' }))
      .mockResolvedValueOnce(mockOk({ verdict: 'ALLOW', action_id: 'act-retry' }))

    const client = new EdonClient({ token: TOKEN, maxRetries: 1 })
    const result = await client.evaluate({ actionType: 'email.send', payload: {} })

    expect(result.verdict).toBe('ALLOW')
    expect(spy).toHaveBeenCalledTimes(2)
  }, 3_000)

  it('sends X-EDON-TOKEN and SDK version headers', async () => {
    const spy = jest
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(mockOk({ verdict: 'ALLOW' }))

    const client = new EdonClient({ token: TOKEN })
    await client.evaluate({ actionType: 'tool.call', payload: {} })

    const [, init] = spy.mock.calls[0]
    const headers = (init as RequestInit).headers as Record<string, string>
    expect(headers['X-EDON-TOKEN']).toBe(TOKEN)
    expect(headers['X-EDON-SDK-Version']).toBeDefined()
    expect(headers['User-Agent']).toMatch(/^edon-js\//)
  })
})

// ── scanOutput() ──────────────────────────────────────────────────────────────

describe('EdonClient.scanOutput()', () => {
  afterEach(() => jest.restoreAllMocks())

  it('returns PASS result on clean response', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ verdict: 'PASS', payload: { rows: [] }, findings: [], redacted: false }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.scanOutput({ response: { rows: [] }, actionType: 'database.query' })

    expect(result.verdict).toBe('PASS')
    expect(result.findings).toHaveLength(0)
    expect(result.fallback).toBe(false)
  })

  it('returns REDACT with findings when PHI detected', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({
        verdict: 'REDACT',
        payload: { name: '[NAME_REDACTED]', ssn: '[SSN_REDACTED]' },
        findings: [{ category: 'phi', pattern: 'ssn', count: 1 }],
        redacted: true,
      }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.scanOutput({
      response: { name: 'Jane', ssn: '123-45-6789' },
      actionType: 'ehr.read',
    })

    expect(result.verdict).toBe('REDACT')
    expect(result.redacted).toBe(true)
    expect(result.findings).toHaveLength(1)
    expect(result.findings[0].pattern).toBe('ssn')
  })

  it('links actionId from evaluate() result', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ verdict: 'PASS', payload: {}, findings: [], redacted: false }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.scanOutput({
      response: {},
      actionType: 'ehr.read',
      actionId: 'act-xyz',
    })

    expect(result.actionId).toBe('act-xyz')
  })

  it('returns fail-open on connection error', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    const raw = { data: 'original' }
    const client = new EdonClient({ token: TOKEN })
    const result = await client.scanOutput({ response: raw, actionType: 'tool.call' })

    expect(result.verdict).toBe('PASS')
    expect(result.payload).toBe(raw)
    expect(result.fallback).toBe(true)
  })
})

// ── health() ─────────────────────────────────────────────────────────────────

describe('EdonClient.health()', () => {
  afterEach(() => jest.restoreAllMocks())

  it('returns status on 200', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockOk({ status: 'healthy', version: '1.0.0' }),
    )
    const client = new EdonClient({ token: TOKEN })
    const result = await client.health()

    expect(result['status']).toBe('healthy')
  })

  it('returns unreachable when gateway is down', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    const client = new EdonClient({ token: TOKEN })
    const result = await client.health()

    expect(result['status']).toBe('unreachable')
  })
})

// ── beginIntent() ─────────────────────────────────────────────────────────────

describe('EdonClient.beginIntent()', () => {
  afterEach(() => jest.restoreAllMocks())

  it('returns an intent_id string starting with intent_', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(mockOk({ ok: true }))
    const client = new EdonClient({ token: TOKEN })
    const id = await client.beginIntent({
      objective: 'Summarise patient roster for care team',
      allowedTools: ['database.query', 'email.send'],
    })

    expect(typeof id).toBe('string')
    expect(id.startsWith('intent_')).toBe(true)
  })

  it('still returns an ID even if gateway call fails', async () => {
    jest.spyOn(global, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    const client = new EdonClient({ token: TOKEN })
    const id = await client.beginIntent({ objective: 'Test', allowedTools: [] })

    expect(typeof id).toBe('string')
    expect(id.startsWith('intent_')).toBe(true)
  })

  it('respects a caller-supplied intentId', async () => {
    jest.spyOn(global, 'fetch').mockResolvedValueOnce(mockOk({ ok: true }))
    const client = new EdonClient({ token: TOKEN })
    const id = await client.beginIntent({
      objective: 'Test',
      allowedTools: [],
      intentId: 'my-custom-id',
    })

    expect(id).toBe('my-custom-id')
  })
})

// ── APIError.fromResponse() factory ──────────────────────────────────────────

describe('APIError.fromResponse()', () => {
  it('creates AuthenticationError for 401', () => {
    const err = APIError.fromResponse(401, { detail: 'Invalid API key' }, null)

    expect(err).toBeInstanceOf(AuthenticationError)
    expect(err.statusCode).toBe(401)
    expect(err.message).toBe('Invalid API key')
  })

  it('creates RateLimitError with retryAfter for 429', () => {
    const err = APIError.fromResponse(429, { detail: 'Slow down', retry_after: 60 }, 'req-abc')

    expect(err).toBeInstanceOf(RateLimitError)
    expect((err as RateLimitError).retryAfter).toBe(60)
    expect(err.requestId).toBe('req-abc')
  })

  it('creates GatewayError for 500', () => {
    const err = APIError.fromResponse(500, { error: 'Internal server error' }, null)

    expect(err).toBeInstanceOf(GatewayError)
    expect(err.statusCode).toBe(500)
  })

  it('falls back to HTTP status text when body has no message', () => {
    const err = APIError.fromResponse(503, {}, null)

    expect(err.message).toBe('HTTP 503')
  })

  it('instanceof checks work through transpiled class hierarchy', () => {
    const err = APIError.fromResponse(401, { detail: 'bad key' }, null)

    expect(err).toBeInstanceOf(AuthenticationError)
    expect(err).toBeInstanceOf(APIError)
    expect(err).toBeInstanceOf(Error)
  })
})

// ── APIConnectionError / APITimeoutError ──────────────────────────────────────

describe('connection error types', () => {
  it('APIConnectionError carries the original cause', () => {
    const cause = new TypeError('ECONNREFUSED')
    const err = new APIConnectionError('Cannot reach gateway', cause)

    expect(err).toBeInstanceOf(APIConnectionError)
    expect(err.cause).toBe(cause)
  })

  it('APITimeoutError is a subclass of APIConnectionError', () => {
    const err = new APITimeoutError('Timed out')

    expect(err).toBeInstanceOf(APIConnectionError)
    expect(err).toBeInstanceOf(APITimeoutError)
  })
})
