// EDON Gateway API client

export interface AuthConfig {
  gatewayUrl: string
  token: string
}

function getAuth(): AuthConfig | null {
  const raw = localStorage.getItem('edon_auth')
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const auth = getAuth()
  if (!auth) throw new Error('Not authenticated')
  const res = await fetch(`${auth.gatewayUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-EDON-TOKEN': auth.token,
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `${res.status}`)
  }
  return res.json()
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface HealthResponse {
  ok: boolean
  status: string
  version: string
  uptime_seconds: number
  components: Record<string, { status: string; latency_ms?: number }>
}

export interface TimeseriesPoint {
  timestamp: string
  label: string
  allowed: number
  blocked: number
  confirm: number
}

export interface BlockReason {
  reason: string
  count: number
}

export interface AuditEvent {
  id?: string
  action_id?: string
  agent_id: string
  decision_verdict: string
  decision_reason_code?: string
  tool_name?: string
  timestamp: string
  risk_score?: number
  policy_version?: string
  explanation?: string
  customer_id?: string
}

export interface AuditQueryResponse {
  events: AuditEvent[]
  count: number
}

export interface Agent {
  agent_id: string
  name?: string
  agent_type?: string
  status?: string
  description?: string
  capabilities?: string[]
  policy_pack?: string
  last_seen?: string
  decisions_total?: number
  decisions_blocked?: number
}

export interface PolicyRule {
  rule_id: string
  name: string
  description?: string
  enabled: boolean
  regulation?: string
  action?: string
  condition?: Record<string, unknown>
  created_at?: string
}

export interface ComplianceHealth {
  overall: string
  clinical_safety_mode_active: boolean
  regulations: Record<string, {
    status: string
    label: string
    rules_required: number
    rules_active: number
    missing_rules: string[]
  }>
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  health: () => request<HealthResponse>('/health'),

  timeseries: (days = 7) =>
    request<TimeseriesPoint[]>(`/timeseries?days=${days}`),

  blockReasons: (days = 7) =>
    request<BlockReason[]>(`/block-reasons?days=${days}`),

  auditQuery: (params: {
    verdict?: string
    agent_id?: string
    limit?: number
    from_ts?: string
  } = {}) => {
    const qs = new URLSearchParams()
    if (params.verdict) qs.set('verdict', params.verdict)
    if (params.agent_id) qs.set('agent_id', params.agent_id)
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.from_ts) qs.set('from_ts', params.from_ts)
    return request<AuditQueryResponse>(`/audit/query?${qs}`)
  },

  agents: () => request<{ agents?: Agent[]; items?: Agent[] } | Agent[]>('/agents'),

  policyRules: () =>
    request<{ rules: PolicyRule[] } | PolicyRule[]>('/policy/rules'),

  complianceHealth: () => request<ComplianceHealth>('/compliance/health'),

  enableRule: (ruleId: string) =>
    request(`/policy/rules/${ruleId}/enable`, { method: 'POST' }),

  disableRule: (ruleId: string) =>
    request(`/policy/rules/${ruleId}/disable`, { method: 'POST' }),
}
