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

export interface ReviewItem {
  decision_id: string
  action_type: string
  agent_id: string
  escalation_question?: string
  explanation?: string
  action_payload?: Record<string, unknown>
  created_at: string
  resolved_at?: string
  resolution?: 'approved' | 'rejected'
  resolved_by?: string
  resolution_note?: string
  meta?: {
    urgency?: 'critical' | 'urgent' | 'routine'
    department?: string
    patient_id?: string
    clinical_context?: string
    vendor_name?: string
    device_id?: string
    device_name?: string
    policy_version?: string
  }
}

export interface ReviewQueueResponse {
  queue: ReviewItem[]
  count: number
}

export interface ApiKey {
  id: string
  name?: string | null
  role: string
  status: string
  created_at?: string
  last_used_at?: string
  expires_at?: string
}

export interface ApiKeyListResponse {
  keys: ApiKey[]
  count: number
}

export interface CreateKeyResponse {
  key_id: string
  key: string
  name?: string
  role: string
  message: string
}

export interface RotateKeyResponse {
  new_key_id: string
  new_key: string
  new_key_name: string
  old_key_id: string
  old_key_expires_at: string
  overlap_hours: number
  message: string
}

export interface TenantSummary {
  tenant_id: string
  plan: string
  status: string
  created_at?: string
  updated_at?: string
  active_key_count: number
  total_key_count: number
}

export interface BootstrapKeyResponse {
  tenant_id: string
  key_id: string
  key: string
  role: string
  message: string
}

export interface MeResponse {
  tenant_id: string
  key_id: string | null
  key_name: string | null
  role: string
  plan: string
  is_admin: boolean
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  me: () => request<MeResponse>('/api-keys/me'),

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

  reviewQueue: (status = 'pending') =>
    request<ReviewQueueResponse>(`/compliance/review/queue?status=${status}`),

  approveReview: (decisionId: string, reviewer: string, note?: string) =>
    request(`/compliance/review/${decisionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reviewer, note }),
    }),

  rejectReview: (decisionId: string, reviewer: string, note?: string) =>
    request(`/compliance/review/${decisionId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reviewer, note }),
    }),

  // ── API Key management ────────────────────────────────────────────────────
  listApiKeys: () =>
    request<ApiKeyListResponse>('/api-keys'),

  createApiKey: (name: string, role: string) =>
    request<CreateKeyResponse>('/api-keys', {
      method: 'POST',
      body: JSON.stringify({ name, role }),
    }),

  revokeApiKey: (keyId: string) =>
    request<{ key_id: string; status: string }>(`/api-keys/${keyId}`, { method: 'DELETE' }),

  rotateApiKey: (keyId: string, overlapHours = 24, name?: string) =>
    request<RotateKeyResponse>(`/api-keys/${keyId}/rotate`, {
      method: 'POST',
      body: JSON.stringify({ overlap_hours: overlapHours, name }),
    }),

  // ── New tenant provisioning (requires bootstrap secret) ───────────────────
  bootstrapTenant: (bootstrapSecret: string, tenantId: string, token: string, name: string, email: string, role = 'admin', plan = 'enterprise') =>
    request<BootstrapKeyResponse>('/admin/bootstrap-api-key', {
      method: 'POST',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify({ tenant_id: tenantId, token, name, email, role, plan }),
    }),

  // ── Support tickets ───────────────────────────────────────────────────────
  submitSupportTicket: (payload: {
    summary: string
    tab: string
    reviewer_name?: string
    department?: string
    chat_history: { role: string; content: string }[]
    urgency: string
  }) => request<{ ticket_id: string; status: string; message: string }>('/support/ticket', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),

  // ── IP allowlist ──────────────────────────────────────────────────────────
  getIpAllowlist: () =>
    request<{ cidrs: string[]; enabled: boolean }>('/settings/ip-allowlist'),

  addIpAllowlist: (cidr: string) =>
    request<{ ok: boolean; cidr: string }>('/settings/ip-allowlist', {
      method: 'POST',
      body: JSON.stringify({ cidr }),
    }),

  removeIpAllowlist: (cidr: string) =>
    request<{ ok: boolean; cidr: string }>('/settings/ip-allowlist', {
      method: 'DELETE',
      body: JSON.stringify({ cidr }),
    }),

  // ── Admin tenant management ────────────────────────────────────────────────
  listTenants: (bootstrapSecret: string) =>
    request<{ tenants: TenantSummary[]; count: number }>('/admin/tenants', {
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
    }),

  updateTenant: (bootstrapSecret: string, tenantId: string, updates: { plan?: string; status?: string }) =>
    request<{ tenant_id: string; plan: string; status: string }>(`/admin/tenants/${tenantId}`, {
      method: 'PATCH',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify(updates),
    }),

  createSupportKey: (bootstrapSecret: string, tenantId: string, label?: string) =>
    request<{ key_id: string; key: string; tenant_id: string; label: string }>(`/admin/tenants/${tenantId}/support-key`, {
      method: 'POST',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify({ label }),
    }),
}
