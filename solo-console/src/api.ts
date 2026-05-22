export interface AuthConfig {
  gatewayUrl: string
  token: string
}

let lastRequestId: string | null = null

function readAuth(): AuthConfig | null {
  const raw = sessionStorage.getItem('edon_auth') || localStorage.getItem('edon_auth')
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export function getLastRequestId() {
  return lastRequestId
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
  lastRequestId = res.headers.get('X-Request-ID') || res.headers.get('x-request-id') || lastRequestId
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `${res.status}`)
  }
  return res.json()
}

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
  meta?: Record<string, unknown>
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
  department?: string
  last_seen?: string
  decisions_total?: number
  decisions_blocked?: number
  block_rate?: number
  metadata?: Record<string, unknown>
}

export interface PolicyRule {
  rule_id: string
  name: string
  description?: string
  enabled: boolean
  regulation?: string
  action?: string
  tool?: string
  op?: string
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

export interface MeResponse {
  tenant_id: string
  key_id: string | null
  key_name: string | null
  role: string
  plan: string
  is_admin: boolean
  is_sandbox: boolean
  vertical: 'healthcare' | 'banking' | 'general' | null
}

export interface AssistantProposal {
  proposal_id?: string
  tenant_id?: string
  type: 'add_policy_rule' | 'enable_rule' | 'disable_rule' | 'set_shadow_mode'
  description: string
  impact: string
  regulation?: string
  payload: Record<string, unknown>
}

export interface Citation {
  type: 'decision' | 'agent' | 'rule'
  id: string
}

export interface AssistantExplainSuggestion {
  title: string
  body: string
}

export interface AssistantChatResponse {
  answer: string
  suggestion: AssistantProposal | null
  citations: Citation[]
}

export const api = {
  me: () => request<MeResponse>('/api-keys/me'),
  health: () => request<HealthResponse>('/health'),
  timeseries: (days = 7) => request<TimeseriesPoint[]>(`/timeseries?days=${days}`),
  blockReasons: (days = 7) => request<BlockReason[]>(`/block-reasons?days=${days}`),
  auditQuery: (params: { verdict?: string; agent_id?: string; limit?: number; from_ts?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.verdict) qs.set('verdict', params.verdict)
    if (params.agent_id) qs.set('agent_id', params.agent_id)
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.from_ts) qs.set('from_ts', params.from_ts)
    return request<AuditQueryResponse>(`/audit/query?${qs}`)
  },
  agents: () => request<{ agents?: Agent[]; items?: Agent[] } | Agent[]>('/agents'),
  policyRules: () => request<{ rules: PolicyRule[] } | PolicyRule[]>('/policy/rules'),
  complianceHealth: () => request<ComplianceHealth>('/compliance/health'),
  enableRule: (ruleId: string) => request(`/policy/rules/${ruleId}/enable`, { method: 'POST' }),
  disableRule: (ruleId: string) => request(`/policy/rules/${ruleId}/disable`, { method: 'POST' }),
  assistantChat: (message: string, conversation: Array<{ role: string; content: string }>, page_context?: Record<string, unknown>) =>
    request<AssistantChatResponse>('/v1/assistant/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation, page_context }),
    }),
  assistantExplain: (type: string, id: string) =>
    request<{ type: string; id: string; explanation: string; suggestion?: AssistantExplainSuggestion; citations?: Citation[] }>('/v1/assistant/explain', {
      method: 'POST',
      body: JSON.stringify({ type, id }),
    }),
}

export function saveAuth(gatewayUrl: string, token: string) {
  sessionStorage.setItem('edon_auth', JSON.stringify({ gatewayUrl, token }))
  localStorage.setItem('edon_auth', JSON.stringify({ gatewayUrl, token }))
}

export function clearAuth() {
  sessionStorage.removeItem('edon_auth')
  localStorage.removeItem('edon_auth')
}

export function getAuth() {
  return readAuth()
}
