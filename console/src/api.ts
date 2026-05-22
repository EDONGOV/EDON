// EDON Gateway API client

export interface AuthConfig {
  gatewayUrl: string
  token: string
}

const CONSOLE_DEV_MODE = import.meta.env.VITE_CONSOLE_DEV_MODE === 'true'
const CONSOLE_DEV_GATEWAY = import.meta.env.VITE_GATEWAY ?? 'http://localhost:8000'
const CONSOLE_DEV_TOKEN = import.meta.env.VITE_CONSOLE_DEV_TOKEN ?? 'edon_sandbox_key_dev_only'

let lastRequestId: string | null = null

function getAuth(): AuthConfig | null {
  const raw = sessionStorage.getItem('edon_auth') || localStorage.getItem('edon_auth')
  if (!raw && CONSOLE_DEV_MODE) return { gatewayUrl: CONSOLE_DEV_GATEWAY, token: CONSOLE_DEV_TOKEN }
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return CONSOLE_DEV_MODE ? { gatewayUrl: CONSOLE_DEV_GATEWAY, token: CONSOLE_DEV_TOKEN } : null }
}

export function getLastRequestId(): string | null {
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
  vendor_id?: string | null
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
  key_preview?: string
  is_active?: boolean
  department?: string | null
  scope_group?: string | null
  purpose?: string | null
  scope?: string | null
  environment?: string | null
  created_at?: string
  last_used_at?: string
  last_used?: string | null
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
  department?: string | null
  scope_group?: string | null
  purpose?: string | null
  scope?: string | null
  environment?: string | null
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

export interface AuditorGrant {
  key_id: string
  label?: string
  name?: string
  role?: string
  status?: string
  expires_at?: string
  created_at?: string
  last_used_at?: string | null
  expired?: boolean
  auditor_email?: string
  scope_note?: string
}

export interface AuditorGrantListResponse {
  grants: AuditorGrant[]
  count: number
}

export interface AuditorInviteResponse {
  key_id: string
  api_key: string
  auditor_email: string
  scope_note?: string
  role: 'auditor'
  expires_at: string
  expires_in_hours: number
  warning?: string
  permissions?: string[]
}

export interface ConsoleUserInvite {
  invite_id: string
  tenant_id?: string
  email: string
  role: string
  department?: string | null
  scope?: string | null
  status: string
  invited_by?: string | null
  invite_url?: string | null
  expires_at?: string
  accepted_at?: string | null
  revoked_at?: string | null
  created_at?: string
  updated_at?: string
  expired?: boolean
}

export interface ConsoleUserInviteResponse {
  invite: ConsoleUserInvite
  invite_token: string
  delivery: {
    status: string
    channel: string
    message: string
  }
}

export interface DepartmentOwner {
  id?: string
  tenant_id?: string
  department: string
  owner_email: string
  updated_by?: string | null
  created_at?: string
  updated_at?: string
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
  is_sandbox: boolean
  vertical: 'healthcare' | 'banking' | 'general' | null
}

export interface ShadowSummary {
  stable: number
  advisory: number
  critical: number
  non_determinism_count: number
  confirmed_bypasses: number
}

export interface ShadowFinding {
  id?: number
  trace_id: string
  perturbation_name: string
  perturbation_type: string
  perturbed_field?: string
  shadow_verdict: string
  shadow_reason: string
  shadow_latency_ms: number
  verdict_changed: number
  severity: 'stable' | 'advisory' | 'critical'
  findings: string[]
  created_at: string
  agent_id?: string
  action_type?: string
  trace_original_verdict?: string
  policy_recommendation?: string
}

export interface ConfirmedBypass {
  id: number
  action_id: string
  trace_id: string
  agent_id: string
  tenant_id?: string
  action_type: string
  perturbation_name: string
  perturbation_type: string
  original_verdict: string
  shadow_verdict: string
  real_outcome: string
  confirmed_at: string
}

export interface ActionResult {
  result_id: string
  action_id: string
  agent_id: string
  tenant_id?: string
  action_type: string
  outcome: 'success' | 'failure' | 'partial' | 'timeout'
  latency_ms: number
  error?: string | null
  result_summary?: string | null
  executed_at: string
  reported_at: string
}

export interface ActionResultStats {
  outcomes: Record<'success' | 'failure' | 'partial' | 'timeout', number>
  total: number
  failure_rate: number
  success_rate: number
}

export interface ChainStressResult {
  injection_step: number
  injection_trace_id: string
  perturbation_name: string
  perturbation_type: string
  steps_after: number
  cascade_count: number
  severity: 'stable' | 'advisory' | 'critical'
  cascade_verdicts: { step: number; trace_id: string; action_type: string; original: string; shadow: string }[]
}

export interface ChainStressResponse {
  session_id: string
  message?: string
  summary?: { total_tests: number; critical: number; advisory: number; stable: number; max_cascade: number }
  results: ChainStressResult[]
}

export interface AssistantMessage {
  role: 'user' | 'assistant'
  content: string | unknown[]
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

export interface AssistantChatResponse {
  answer: string
  suggestion: AssistantProposal | null
  citations: Citation[]
}

export interface AssistantExplainSuggestion {
  title: string
  body: string
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  me: () => request<MeResponse>('/api-keys/me'),

  setVertical: (vertical: 'healthcare' | 'banking' | 'general' | null) =>
    request<{ vertical: string | null }>('/api-keys/me/vertical', {
      method: 'PATCH',
      body: JSON.stringify({ vertical }),
    }),

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

  createRule: (rule: {
    name: string
    description?: string
    condition_tool?: string
    condition_op?: string
    condition_risk_level?: string
    condition_tags?: string[]
    action: string
    priority?: number
    enabled?: boolean
  }) =>
    request<PolicyRule>('/policy/rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),

  enableRule: (ruleId: string) =>
    request(`/policy/rules/${ruleId}/enable`, { method: 'POST' }),

  disableRule: (ruleId: string) =>
    request(`/policy/rules/${ruleId}/disable`, { method: 'POST' }),

  policySandboxTest: (rule: Record<string, unknown>, sampleSize = 200) =>
    request<{ sample_size: number; changed: number; unchanged: number; false_positive_rate: number; changed_decisions: Array<{ action_id: string; original_verdict: string; new_verdict: string }> }>('/policy/sandbox/test', {
      method: 'POST',
      body: JSON.stringify({ rule, sample_size: sampleSize }),
    }),

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

  createApiKey: (payload: {
    name: string
    role: string
    department?: string
    scope_group?: string
    purpose?: string
    scope?: string
    environment?: string
  }) =>
    request<CreateKeyResponse>('/api-keys', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  revokeApiKey: (keyId: string) =>
    request<{ key_id: string; status: string }>(`/api-keys/${keyId}`, { method: 'DELETE' }),

  rotateApiKey: (keyId: string, overlapHours = 24, name?: string) =>
    request<RotateKeyResponse>(`/api-keys/${keyId}/rotate`, {
      method: 'POST',
      body: JSON.stringify({ overlap_hours: overlapHours, name }),
    }),

  // ── New tenant provisioning (requires bootstrap secret) ───────────────────
  listAuditorGrants: () =>
    request<AuditorGrantListResponse>('/auditors'),

  inviteAuditor: (payload: { auditor_email: string; expires_in_hours?: number; scope_note?: string }) =>
    request<AuditorInviteResponse>('/auditors/invite', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  revokeAuditorGrant: (keyId: string) =>
    request<{ key_id?: string; status?: string }>(`/auditors/${keyId}`, { method: 'DELETE' }),

  listConsoleUserInvites: () =>
    request<{ invites: ConsoleUserInvite[]; count: number }>('/access/user-invites'),

  createConsoleUserInvite: (payload: {
    email: string
    role: string
    department?: string
    scope?: string
    expires_in_hours?: number
  }) =>
    request<ConsoleUserInviteResponse>('/access/user-invites', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  revokeConsoleUserInvite: (inviteId: string) =>
    request<{ invite: ConsoleUserInvite; status: string }>(`/access/user-invites/${inviteId}`, { method: 'DELETE' }),

  listDepartmentOwners: () =>
    request<{ owners: DepartmentOwner[]; count: number }>('/access/department-owners'),

  setDepartmentOwner: (department: string, owner_email: string) =>
    request<{ owner: DepartmentOwner; status: string }>(`/access/department-owners/${encodeURIComponent(department)}`, {
      method: 'PUT',
      body: JSON.stringify({ owner_email }),
    }),

  deleteDepartmentOwner: (department: string) =>
    request<{ department: string; status: string }>(`/access/department-owners/${encodeURIComponent(department)}`, { method: 'DELETE' }),

  bootstrapTenant: (bootstrapSecret: string, tenantId: string, token: string, name: string, email: string, role = 'admin', plan = 'enterprise') =>
    request<BootstrapKeyResponse>('/admin/bootstrap-api-key', {
      method: 'POST',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify({ tenant_id: tenantId, token, name, email, role, plan }),
    }),

  // ── Support tickets ───────────────────────────────────────────────────────
  submitSupportTicket: (payload: {
    summary: string
    severity: 'sev1' | 'sev2' | 'sev3' | 'sev4'
    tab: string
    reviewer_name?: string
    department?: string
    issue_type?: string
    chat_history: { role: string; content: string }[]
    notes?: string
    diagnostics: Record<string, unknown>
  }) => request<{ case_id: string; support_code?: string; status: string; severity: string; tenant_id: string; support_url: string; message: string }>('/support/ticket', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),

  // ── Shadow mode ───────────────────────────────────────────────────────────
  getShadowMode: () =>
    request<{ enabled: boolean }>('/settings/shadow-mode'),

  setShadowMode: (enabled: boolean) =>
    request<{ enabled: boolean }>('/settings/shadow-mode', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
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

  getTenantSandbox: (bootstrapSecret: string, tenantId: string) =>
    request<{ tenant_id: string; sandbox: boolean; enabled: boolean }>(`/admin/tenants/${tenantId}/shadow-mode`, {
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
    }),

  setTenantSandbox: (bootstrapSecret: string, tenantId: string, enabled: boolean) =>
    request<{ tenant_id: string; sandbox: boolean; ok: boolean }>(`/admin/tenants/${tenantId}/shadow-mode`, {
      method: 'POST',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify({ enabled }),
    }),

  createSupportKey: (bootstrapSecret: string, tenantId: string, label?: string) =>
    request<{ key_id: string; key: string; tenant_id: string; label: string }>(`/admin/tenants/${tenantId}/support-key`, {
      method: 'POST',
      headers: { 'X-Bootstrap-Secret': bootstrapSecret },
      body: JSON.stringify({ label }),
    }),

  // ── Shadow execution ─────────────────────────────────────────────────────
  shadowSummary: () =>
    request<ShadowSummary>('/v1/shadow/summary'),

  shadowFindings: (severity?: string, limit = 100) => {
    const qs = new URLSearchParams({ limit: String(limit) })
    if (severity) qs.set('severity', severity)
    return request<{ findings: ShadowFinding[]; count: number }>(`/v1/shadow/findings?${qs}`)
  },

  confirmedBypasses: (limit = 50) =>
    request<{ confirmed_bypasses: ConfirmedBypass[]; count: number }>(`/v1/shadow/confirmed-bypasses?limit=${limit}`),

  actionResultStats: () =>
    request<ActionResultStats>('/v1/action/result-stats'),

  actionResult: (actionId: string) =>
    request<ActionResult>(`/v1/action/result/${encodeURIComponent(actionId)}`),

  shadowExport: async () => {
    const auth = getAuth()
    if (!auth) throw new Error('Not authenticated')
    const res = await fetch(`${auth.gatewayUrl}/v1/shadow/export?format=csv`, {
      headers: { 'X-EDON-TOKEN': auth.token },
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    return res.blob()
  },

  chainStress: (sessionId: string, maxPerturbations = 3) =>
    request<ChainStressResponse>(`/v1/shadow/chain-stress?session_id=${encodeURIComponent(sessionId)}&max_perturbations=${maxPerturbations}`, {
      method: 'POST',
    }),

  // ── Governance Assistant ──────────────────────────────────────────────────
  assistantChat: (message: string, conversation: AssistantMessage[], page_context?: Record<string, unknown>) =>
    request<AssistantChatResponse>('/v1/assistant/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation, page_context }),
    }),

  assistantChatStream: async (
    message: string,
    conversation: AssistantMessage[],
    page_context: Record<string, unknown> | undefined,
    onDelta: (chunk: string) => void,
    onDone: (suggestion: AssistantProposal | null, citations: Citation[], conversationId?: string) => void,
    onError: (msg: string) => void,
    onThinking?: (label: string) => void,
    conversationId?: string,
  ): Promise<void> => {
    const auth = getAuth()
    if (!auth) { onError('Not authenticated'); return }
    let res: Response
    try {
      res = await fetch(`${auth.gatewayUrl}/v1/assistant/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-EDON-TOKEN': auth.token },
        body: JSON.stringify({ message, conversation, page_context, conversation_id: conversationId }),
      })
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Network error'); return
    }
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      onError(err.detail || `${res.status}`); return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const ev = JSON.parse(line.slice(6))
          if (ev.error) { onError(ev.error); return }
          if (ev.thinking && onThinking) onThinking(ev.thinking)
          if (ev.delta) onDelta(ev.delta)
          if (ev.done) { onDone(ev.suggestion ?? null, ev.citations ?? [], ev.conversation_id); return }
        } catch { /* ignore malformed */ }
      }
    }
  },

  assistantExplain: (type: string, id: string) =>
    request<{ type: string; id: string; explanation: string; suggestion?: AssistantExplainSuggestion; citations?: Citation[] }>('/v1/assistant/explain', {
      method: 'POST',
      body: JSON.stringify({ type, id }),
    }),

  assistantApply: (proposal: AssistantProposal) =>
    request<{ applied: boolean; rule_id?: string; name?: string; shadow_mode?: boolean }>(
      '/v1/assistant/apply',
      { method: 'POST', body: JSON.stringify({ proposal }) },
    ),

  assistantConversations: () =>
    request<{ conversations: { id: string; title: string; created_at: string; updated_at: string; turn_count: number }[] }>('/v1/assistant/conversations'),

  assistantConversation: (id: string) =>
    request<{ id: string; title: string; messages: { role: string; content: string }[]; created_at: string }>(`/v1/assistant/conversations/${id}`),

  assistantMemories: () =>
    request<{ memories: { id: string; category: string; fact: string; confidence: number; updated_at: string }[]; count: number }>('/v1/assistant/memories'),

  // ── Compliance report export ──────────────────────────────────────────────
  auditReportExport: async (params: {
    format: 'json' | 'pdf'
    from_ts?: string
    to_ts?: string
    agent_id?: string
    verdict?: string
    limit?: number
  }) => {
    const auth = getAuth()
    if (!auth) throw new Error('Not authenticated')
    const qs = new URLSearchParams({ format: params.format })
    if (params.from_ts)  qs.set('from_ts',   params.from_ts)
    if (params.to_ts)    qs.set('to_ts',      params.to_ts)
    if (params.agent_id) qs.set('agent_id',   params.agent_id)
    if (params.verdict)  qs.set('verdict',    params.verdict)
    if (params.limit)    qs.set('limit',      String(params.limit))
    const res = await fetch(`${auth.gatewayUrl}/audit/report/export?${qs}`, {
      headers: { 'X-EDON-TOKEN': auth.token },
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    return res.blob()
  },

  // ── Live key claim ────────────────────────────────────────────────────────
  checkPendingLiveKey: () =>
    request<{ pending: boolean; created_at?: string }>('/live-key/pending'),

  claimLiveKey: () =>
    request<{ key: string; key_id: string; message: string }>('/live-key/claim', { method: 'POST' }),

  // ── Policy templates ──────────────────────────────────────────────────────
  getPolicyTemplates: () =>
    request<{ templates: Array<{ id: string; name: string; description?: string; regulation?: string; rule_count?: number }> }>('/policy/templates'),

  applyPolicyTemplate: (templateId: string) =>
    request<{ applied: number; template_id: string }>(`/policy/templates/${templateId}/apply`, { method: 'POST' }),

  // ── Webhooks ──────────────────────────────────────────────────────────────
  listWebhooks: () =>
    request<{ webhooks: Array<{ id: string; url: string; events: string[]; enabled: boolean; created_at?: string }> }>('/webhooks'),

  createWebhook: (url: string, events: string[]) =>
    request<{ id: string; url: string; events: string[]; enabled: boolean }>('/webhooks', {
      method: 'POST',
      body: JSON.stringify({ url, events }),
    }),

  deleteWebhook: (id: string) =>
    request<{ ok: boolean }>(`/webhooks/${id}`, { method: 'DELETE' }),

  testWebhook: (id: string) =>
    request<{ ok: boolean; status_code?: number }>(`/webhooks/${id}/test`, { method: 'POST' }),

  // ── Onboarding Copilot ────────────────────────────────────────────────────
  onboardingSubmitIntake: (body: {
    org_name: string
    agent_systems: Array<{
      name: string; agent_type: string; actions: string[]
      data_classes: string[]; external_sinks: string[]; description: string
      vendor_name?: string; department?: string
    }>
    identity_provider: string
    environments: string[]
    compliance_requirements: string[]
  }) => request<{ profile: OnboardingProfile; next_step: { action: string; description: string } }>(
    '/v1/onboarding/intake', { method: 'POST', body: JSON.stringify(body) }
  ),

  onboardingRegisterRuntime: (body: {
    runtime_name: string
    vendor_name?: string
    vendor_id?: string
    source_type?: string
    agent_count?: number
    department?: string
    purpose?: string
    runtime_type?: string
    requested_access?: string[]
    connectors?: string[]
  }) => request<{ runtime: RuntimeRegistration; message: string; next_step: { action: string; description: string } }>(
    '/v1/onboarding/runtimes', { method: 'POST', body: JSON.stringify(body) }
  ),

  onboardingListRuntimes: () =>
    request<{ runtimes: RuntimeRegistration[]; count: number }>('/v1/onboarding/runtimes'),

  onboardingGetRuntime: (runtimeId: string) =>
    request<{ runtime: RuntimeRegistration }>(`/v1/onboarding/runtimes/${runtimeId}`),

  onboardingReviewRuntime: (runtimeId: string, reviewedBy: string, approved = true, notes?: string) =>
    request<{ runtime: RuntimeRegistration; message: string }>(`/v1/onboarding/runtimes/${runtimeId}/review`, {
      method: 'POST',
      body: JSON.stringify({ reviewed_by: reviewedBy, approved, notes }),
    }),

  onboardingPromoteRuntime: (runtimeId: string, promotedBy: string, agentId?: string) =>
    request<{ runtime: RuntimeRegistration; agent?: Record<string, unknown>; message: string }>(
      `/v1/onboarding/runtimes/${runtimeId}/promote`,
      { method: 'POST', body: JSON.stringify({ promoted_by: promotedBy, agent_id: agentId }) }
    ),

  onboardingListProfiles: () =>
    request<{ profiles: OnboardingProfile[]; count: number }>('/v1/onboarding/profiles'),

  onboardingGetProfile: (id: string) =>
    request<{ profile: OnboardingProfile }>(`/v1/onboarding/profiles/${id}`),

  onboardingGetStatus: (id: string) =>
    request<OnboardingStatus>(`/v1/onboarding/profiles/${id}/status`),

  onboardingGenerateTopology: (id: string) =>
    request<{ topology: OnboardingTopology; next_step: { action: string; description: string } }>(
      `/v1/onboarding/profiles/${id}/topology`, { method: 'POST' }
    ),

  onboardingBootstrapPolicies: (id: string) =>
    request<{ policy_bundle: OnboardingPolicyBundle; next_step: { action: string; description: string } }>(
      `/v1/onboarding/profiles/${id}/bootstrap`, { method: 'POST' }
    ),

  onboardingGetDeployment: (id: string) =>
    request<{ deployment_package: OnboardingDeploymentPackage; next_step: { action: string; description: string } }>(
      `/v1/onboarding/profiles/${id}/deployment`
    ),

  onboardingSetShadowMode: (id: string, enabled: boolean) =>
    request<{ shadow_mode: boolean; message: string; next_step?: { action: string; description: string } }>(
      `/v1/onboarding/profiles/${id}/shadow`, { method: 'POST', body: JSON.stringify({ enabled }) }
    ),

  onboardingRequestSignoff: (id: string, body: {
    requested_by: string; enforcement_scope: string[]
    escalation_rules_accepted: boolean; kill_switch_authority: string; data_classes_governed: string[]
  }) => request<{ signoff: OnboardingSignoff; instructions: string }>(
    `/v1/onboarding/profiles/${id}/signoff/request`, { method: 'POST', body: JSON.stringify(body) }
  ),

  onboardingApproveSignoff: (signoffId: string, resolved_by: string) =>
    request<{ signoff: OnboardingSignoff; message: string }>(
      `/v1/onboarding/signoffs/${signoffId}/approve`,
      { method: 'POST', body: JSON.stringify({ resolved_by }) }
    ),

  onboardingGetExpansion: (id: string) =>
    request<{ signals: OnboardingExpansionSignal[]; count: number; high_severity_count: number; expansion_recommended: boolean }>(
      `/v1/onboarding/profiles/${id}/expansion`
    ),

  // â”€â”€ Fleet reconciliation / operations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  reconciliationImportInventory: (body: {
    source_system: string
    vendor_name?: string
    vendor_id?: string
    source_type?: string
    department?: string
    cohort_mode?: string
    posture?: string
    inventory: Array<{
      name: string
      vendor?: string
      vendor_name?: string
      vendor_id?: string
      department?: string
      scope?: string
      action?: string
      runtime_type?: string
      agent_id?: string
      connectors?: string[]
    }>
  }) => request<{ batch: ReconciliationBatch; next_step: { action: string; description: string } }>(
    '/v1/operations/reconciliation/import', { method: 'POST', body: JSON.stringify(body) }
  ),

  reconciliationListBatches: () =>
    request<{ batches: ReconciliationBatch[]; count: number }>('/v1/operations/reconciliation'),

  reconciliationGetBatch: (batchId: string) =>
    request<{ batch: ReconciliationBatch }>(`/v1/operations/reconciliation/${batchId}`),

  reconciliationHoldBatch: (batchId: string, actor: string, notes?: string) =>
    request<{ batch: ReconciliationBatch; message: string }>(`/v1/operations/reconciliation/${batchId}/hold`, {
      method: 'POST',
      body: JSON.stringify({ actor, action: 'hold', notes }),
    }),

  reconciliationMergeBatch: (batchId: string, actor: string, notes?: string) =>
    request<{ batch: ReconciliationBatch; merged: number }>(`/v1/operations/reconciliation/${batchId}/merge`, {
      method: 'POST',
      body: JSON.stringify({ actor, action: 'merge', notes }),
    }),

  reconciliationPromoteBatch: (batchId: string, actor: string, notes?: string) =>
    request<{ batch: ReconciliationBatch; promoted: number }>(`/v1/operations/reconciliation/${batchId}/promote`, {
      method: 'POST',
      body: JSON.stringify({ actor, action: 'promote', notes }),
    }),

  reconciliationRowAction: (batchId: string, rowKey: string, actor: string, action: string, notes?: string) =>
    request<{ batch: ReconciliationBatch; row: ReconciliationRow }>(`/v1/operations/reconciliation/${batchId}/rows/${rowKey}/action`, {
      method: 'POST',
      body: JSON.stringify({ actor, action, notes }),
    }),

  killSwitchStatus: () =>
    request<{ active: boolean; tenant_id: string; reason?: string; activated_at?: string; activated_by?: string }>(
      '/settings/kill-switch'
    ),

  killSwitchActivate: (reason: string, activated_by: string) =>
    request<{ active: boolean; message: string }>(
      '/settings/kill-switch',
      { method: 'POST', body: JSON.stringify({ reason, activated_by }) }
    ),

  killSwitchDeactivate: (deactivated_by: string) =>
    request<{ active: boolean; message: string }>(
      '/settings/kill-switch',
      { method: 'DELETE', body: JSON.stringify({ deactivated_by }) }
    ),
}

// ── Onboarding types ───────────────────────────────────────────────────────

export interface OnboardingProfile {
  profile_id: string
  tenant_id: string
  org_name: string
  created_at: string
  stage: string
  risk_tier: string
  risk_score: number
  all_data_classes: string[]
  all_actions: string[]
  external_sinks: string[]
  compliance_requirements: string[]
  identity_provider: string
  environments: string[]
  shadow_mode_enabled: boolean
  signed_off: boolean
  signed_off_at?: string
  signed_off_by?: string
  agent_systems: Array<{
    name: string; agent_type: string; actions: string[]
    data_classes: string[]; external_sinks: string[]; description: string
    vendor_name?: string; department?: string
  }>
}

export interface OnboardingStatus {
  profile_id: string
  stage: string
  stage_label: string
  risk_tier: string
  shadow_mode: boolean
  signed_off: boolean
  signed_off_at?: string
  steps: Array<{ step: number; name: string; done: boolean }>
  signoffs: OnboardingSignoff[]
}

export interface OnboardingTopology {
  profile_id: string
  enforcement_points: Array<{
    point_id: string; label: string; agent_system: string
    connector_type: string; intercepts: string[]; data_classes_at_risk: string[]
    is_external_boundary: boolean; priority: string; notes: string
  }>
  trust_boundaries: Array<{
    boundary_id: string; label: string; from_zone: string; to_zone: string
    data_classes: string[]; crossing_points: string[]; enforcement: string
  }>
  required_connectors: string[]
  deployment_modes: string[]
  summary: Record<string, number | string | string[]>
}

export interface OnboardingPolicyBundle {
  profile_id: string
  generated_at: string
  hard_safety: OnboardingPolicy[]
  operational: OnboardingPolicy[]
  intent_contracts: OnboardingPolicy[]
  total_count: number
}

export interface OnboardingPolicy {
  policy_id: string
  layer: string
  agent_system: string
  action_pattern: string
  decision: string
  reason: string
  constraints: Record<string, unknown>
  data_classes: string[]
  immutable_after_signoff: boolean
  priority: number
}

export interface OnboardingDeploymentPackage {
  profile_id: string
  deployment_mode: string
  helm_values: Record<string, unknown>
  env_vars: Record<string, string>
  connector_configs: Array<Record<string, unknown>>
  network_requirements: Record<string, unknown>
  identity_setup: Record<string, unknown>
  audit_pipeline: Record<string, unknown>
  rollback_plan: string[]
  estimated_setup_h: number
}

export interface OnboardingSignoff {
  signoff_id: string
  profile_id: string
  tenant_id: string
  requested_at: string
  requested_by: string
  status: string
  enforcement_scope: string[]
  data_classes_governed: string[]
  kill_switch_authority: string
  policy_count_hard_safety: number
  policy_count_operational: number
  policy_count_intent_contracts: number
  resolved_at?: string
  resolved_by?: string
}

export interface OnboardingExpansionSignal {
  signal_type: string
  severity: string
  title: string
  description: string
  evidence: Record<string, unknown>
  recommended_action: string
  detected_at: string
}

export interface RuntimeRegistration {
  runtime_id: string
  tenant_id: string
  runtime_name: string
  vendor_name: string
  vendor_id: string
  source_type: string
  agent_count: number
  department: string
  purpose: string
  runtime_type: string
  requested_access: string[]
  connectors: string[]
  governance_mode: 'shadow' | 'governed'
  status: string
  review_status: string
  risk_score: number
  risk_tier: string
  policy_simulation: Record<string, unknown>
  created_at: string
  updated_at: string
  reviewed_at?: string
  reviewed_by?: string
  promoted_at?: string
  promoted_by?: string
  promoted_agent_id?: string
}

export interface ReconciliationRow {
  row_key: string
  name: string
  vendor: string
  vendor_id: string
  department: string
  scope: string
  action: string
  runtime_type: string
  connectors: string[]
  status: string
  risk: string
  matched_agent_id?: string | null
  comparison?: Record<string, unknown>
  selected?: boolean
  audit?: Array<{ action: string; actor: string; notes: string; time: string }>
}

export interface ReconciliationBatch {
  batch_id: string
  source_system: string
  vendor_name: string
  vendor_id: string
  source_type: string
  department: string
  cohort_mode: string
  posture: string
  rows: ReconciliationRow[]
  missing: Array<Record<string, unknown>>
  summary: Record<string, unknown>
  selected_row_key?: string | null
  selected_batch?: string | null
  status: string
  created_at: string
  updated_at: string
}
