// Gateway API client — reads token + base URL from localStorage

export const getBase = () =>
  localStorage.getItem('edon_api_base') ||
  (import.meta.env.VITE_GATEWAY_URL as string | undefined) ||
  'https://api.edoncore.com'

export const getToken = () =>
  localStorage.getItem('edon_token') ||
  localStorage.getItem('edon_api_key') ||
  ''

async function gw<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${getBase()}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-EDON-TOKEN': getToken(),
      ...(opts.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface GatewayStats {
  total_decisions: number
  allowed: number
  blocked: number
  escalated: number
  avg_latency_ms: number
  decisions_today: number
}

export interface GatewayHealth {
  status: string
  version?: string
  uptime_seconds?: number
  components?: Record<string, string>
}

export interface Agent {
  id: string
  name: string
  status: 'idle' | 'working' | 'blocked' | 'error' | 'offline'
  model?: string
  last_seen?: string
  decisions_today?: number
}

export interface Decision {
  action_id: string
  agent_id?: string
  verdict: 'ALLOW' | 'BLOCK' | 'ESCALATE' | 'DEGRADE' | 'PAUSE' | 'ERROR'
  reason_code: string
  explanation?: string
  timestamp: string
  tool?: string
  risk_score?: number
}

export interface AuditQueryParams {
  agent_id?: string
  verdict?: string
  from?: string
  to?: string
  limit?: number
  offset?: number
}

export interface PolicyPack {
  name: string
  label: string
  description: string
  active?: boolean
  risk_level?: string
}

export interface BillingStatus {
  plan: string
  status: string
  decisions_used: number
  decisions_limit: number
  billing_period_end?: string
  stripe_portal_url?: string
}

export interface ReviewItem {
  review_id: string
  action_id: string
  agent_id: string
  tool?: string
  explanation: string
  escalation_question?: string
  escalation_options?: Array<{ id: string; label: string }>
  created_at: string
  risk_score?: number
}

// ── API calls ────────────────────────────────────────────────────────────────

export const gwHealth = () => gw<GatewayHealth>('/health')

export const gwStats = () => gw<GatewayStats>('/stats')

export const gwAgents = () => gw<{ agents: Agent[] }>('/agents')

export const gwAuditQuery = (params: AuditQueryParams = {}) => {
  const qs = new URLSearchParams()
  if (params.agent_id) qs.set('agent_id', params.agent_id)
  if (params.verdict) qs.set('verdict', params.verdict)
  if (params.from) qs.set('from', params.from)
  if (params.to) qs.set('to', params.to)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  return gw<{ decisions: Decision[]; total: number }>(`/audit/query?${qs}`)
}

export const gwAuditExportUrl = (params: AuditQueryParams = {}) => {
  const qs = new URLSearchParams()
  if (params.agent_id) qs.set('agent_id', params.agent_id)
  if (params.verdict) qs.set('verdict', params.verdict)
  if (params.from) qs.set('from', params.from)
  if (params.to) qs.set('to', params.to)
  qs.set('format', 'csv')
  return `${getBase()}/audit/export?${qs}`
}

export const gwPolicyPacks = () => gw<{ packs: PolicyPack[] }>('/policy-packs')

export const gwApplyPack = (name: string) =>
  gw<{ intent_id: string; policy_pack: string }>(`/policy-packs/${name}/apply`, { method: 'POST', body: '{}' })

export const gwBillingStatus = () => gw<BillingStatus>('/billing/status')

export const gwReviewQueue = () =>
  gw<{ items: ReviewItem[]; total: number }>('/review/queue')

export const gwReviewDecide = (reviewId: string, decision: 'approve' | 'block', note?: string) =>
  gw<{ ok: boolean }>(`/review/queue/${reviewId}/decide`, {
    method: 'POST',
    body: JSON.stringify({ decision, note }),
  })

// ── API key management ───────────────────────────────────────────────────────

export interface ApiKey {
  id: string
  name: string | null
  role: string
  status: string
  created_at: string
  expires_at: string | null
}

export const gwListApiKeys = () =>
  gw<{ keys: ApiKey[]; count: number }>('/api-keys')

export const gwRotateApiKey = (keyId: string, overlapHours = 24) =>
  gw<{ new_key: string; new_key_id: string; old_key_expires_at: string; overlap_hours: number }>(
    `/api-keys/${keyId}/rotate`,
    { method: 'POST', body: JSON.stringify({ overlap_hours: overlapHours }) }
  )

// ── IP allowlist ──────────────────────────────────────────────────────────────

export const gwGetIpAllowlist = () =>
  gw<{ cidrs: string[] }>('/settings/ip-allowlist')

export const gwAddIpAllowlist = (cidr: string) =>
  gw<{ ok: boolean }>('/settings/ip-allowlist', {
    method: 'POST',
    body: JSON.stringify({ cidr }),
  })

export const gwRemoveIpAllowlist = (cidr: string) =>
  gw<{ ok: boolean }>('/settings/ip-allowlist', {
    method: 'DELETE',
    body: JSON.stringify({ cidr }),
  })
