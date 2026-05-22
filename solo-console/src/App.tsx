import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock3,
  Copy,
  Database,
  Download,
  FileText,
  Filter,
  ListChecks,
  LogOut,
  MoonStar,
  Plus,
  RefreshCw,
  Save,
  Shield,
  ShieldAlert,
  Sparkles,
  SunMedium,
  Trash2,
  User,
  Users,
  Wrench,
  X,
} from 'lucide-react'
import {
  api,
  clearAuth,
  getAuth,
  getLastRequestId,
  saveAuth,
  type Agent,
  type AuditEvent,
  type AssistantExplainSuggestion,
  type AssistantProposal,
  type BlockReason,
  type Citation,
  type ComplianceHealth,
  type HealthResponse,
  type MeResponse,
  type PolicyRule,
  type TimeseriesPoint,
} from './api'

type WorkspaceMode = 'sandbox' | 'governed'
type TabId = 'overview' | 'agents' | 'audit' | 'policies' | 'workspace' | 'settings'
type RiskTier = 'low' | 'medium' | 'high'

type WorkspaceAgent = {
  agent_id: string
  name: string
  scope: string
  risk_tier: RiskTier
  mode: WorkspaceMode
  source: 'remote' | 'custom'
  status?: string
  block_rate?: number
  decisions_total?: number
  last_action?: string
}

type WorkspaceManifest = {
  version: number
  workspace_name: string
  operator_name: string
  mode: WorkspaceMode
  notes: string
  tools: string[]
  agents: WorkspaceAgent[]
  updated_at: string
}

type WorkspaceEvent = {
  id: string
  ts: string
  kind: 'workspace' | 'audit'
  title: string
  detail: string
  refId?: string
  verdict?: string
}

type InspectorSelection =
  | { type: 'agent'; id: string; payload: WorkspaceAgent }
  | { type: 'decision'; id: string; payload: AuditEvent }
  | { type: 'rule'; id: string; payload: PolicyRule }

type WorkspaceState = {
  timeseries: TimeseriesPoint[]
  recent: AuditEvent[]
  health: ComplianceHealth | null
  systemHealth: HealthResponse | null
  rules: PolicyRule[]
  remoteAgents: Agent[]
  blockReasons: BlockReason[]
  loading: boolean
  error: string
  reload: () => Promise<void>
}

const MANIFEST_KEY = 'edon_solo_manifest_v2'
const EVENTS_KEY = 'edon_solo_events_v1'
const MODE_KEY = 'edon_solo_mode_v1'

const CITE_RE = /\[ref:(DECISION|AGENT|RULE):([^\]]+)\]/g
const CITE_COLORS: Record<string, string> = {
  decision: 'bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30',
  agent: 'bg-blue-500/20 border-blue-500/40 text-blue-300 hover:bg-blue-500/30',
  rule: 'bg-purple-500/20 border-purple-500/40 text-purple-300 hover:bg-purple-500/30',
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ')
}

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function writeJson<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function fmtDateTime(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function uniqueCitations(citations?: Citation[]) {
  const seen = new Set<string>()
  return (citations ?? []).filter(c => {
    const key = `${c.type}:${c.id}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function citationLabel(type: string) {
  if (type === 'decision') return 'DEC'
  if (type === 'agent') return 'AGT'
  return 'RULE'
}

function highlightCite(id: string) {
  const el = document.querySelector(`[data-cite-id="${id}"]`)
  if (!el) return
  el.classList.remove('cite-ring')
  void (el as HTMLElement).offsetWidth
  el.classList.add('cite-ring')
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  setTimeout(() => el.classList.remove('cite-ring'), 2600)
}

function CitedText({ text, onCite }: { text: string; onCite: (type: string, id: string) => void }) {
  const parts: ReactNode[] = []
  let last = 0
  CITE_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = CITE_RE.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const type = match[1].toLowerCase()
    const id = match[2]
    const color = CITE_COLORS[type] ?? CITE_COLORS.rule
    parts.push(
      <button
        key={`${match.index}-${id}`}
        onClick={() => onCite(type, id)}
        className={cn('mx-0.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold border transition-colors', color)}
      >
        {citationLabel(type)} {id.length > 14 ? `${id.slice(0, 14)}…` : id}
      </button>,
    )
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <span>{parts}</span>
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toUpperCase()
  const cfg = v === 'ALLOW'
    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    : v === 'BLOCK'
      ? 'bg-red-500/10 text-red-400 border-red-500/20'
      : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
  return <span className={cn('inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest', cfg)}>{v}</span>
}

function ModeChip({ mode }: { mode: WorkspaceMode }) {
  const cls = mode === 'sandbox'
    ? 'border-blue-500/25 bg-blue-500/10 text-blue-300'
    : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
  return <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest', cls)}>{mode}</span>
}

function RiskChip({ risk }: { risk: RiskTier }) {
  const cls = risk === 'high'
    ? 'border-red-500/25 bg-red-500/10 text-red-400'
    : risk === 'medium'
      ? 'border-amber-500/25 bg-amber-500/10 text-amber-400'
      : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
  return <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest', cls)}>{risk}</span>
}

function StatCard({ label, value, hint, icon: Icon, tone = 'text-emerald-400' }: { label: string; value: string | number; hint?: string; icon: typeof Activity; tone?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 shadow-[0_20px_50px_rgba(0,0,0,0.22)]">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className={cn('flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04]', tone)}>
          <Icon size={16} />
        </div>
      </div>
    </div>
  )
}

function Panel({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] shadow-[0_20px_50px_rgba(0,0,0,0.22)]">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div>
          {eyebrow && <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground/80">{eyebrow}</p>}
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function makeId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`
}

function defaultManifest(me: MeResponse | null, remoteAgents: Agent[] = []): WorkspaceManifest {
  const agentSeeds: WorkspaceAgent[] = (remoteAgents.length > 0 ? remoteAgents : [
    { agent_id: 'pm-scheduler', name: 'Project Scheduler', scope: 'project coordination', risk_tier: 'low', mode: 'sandbox', source: 'custom' },
    { agent_id: 'ops-helper', name: 'Ops Helper', scope: 'workflow automation', risk_tier: 'medium', mode: 'sandbox', source: 'custom' },
  ]).map(a => ({
    agent_id: a.agent_id,
    name: a.name ?? a.agent_id,
    scope: (a as Partial<WorkspaceAgent>).scope ?? (a as Agent).description ?? 'general workspace scope',
    risk_tier: (((a as Agent).block_rate ?? 0) > 0.2 ? 'high' : ((a as Agent).block_rate ?? 0) > 0.1 ? 'medium' : 'low') as RiskTier,
    mode: 'sandbox',
    source: remoteAgents.length > 0 ? 'remote' : 'custom',
    status: (a as Agent).status,
    block_rate: (a as Agent).block_rate,
    decisions_total: (a as Agent).decisions_total,
    last_action: (a as Agent).last_seen ? `last seen ${relTime((a as Agent).last_seen!)}` : undefined,
  }))

  return {
    version: 1,
    workspace_name: localStorage.getItem('edon_solo_workspace') || 'Personal Workspace',
    operator_name: localStorage.getItem('edon_solo_name') || 'Solo Operator',
    mode: me?.is_sandbox ? 'sandbox' : 'sandbox',
    notes: 'Sandbox-first personal governance workspace.',
    tools: ['GitHub', 'Slack', 'Local APIs', 'Databases'],
    agents: agentSeeds,
    updated_at: new Date().toISOString(),
  }
}

function readManifest(): WorkspaceManifest | null {
  return readJson<WorkspaceManifest>(MANIFEST_KEY)
}

function saveManifest(next: WorkspaceManifest) {
  writeJson(MANIFEST_KEY, next)
}

function readEvents(): WorkspaceEvent[] {
  return readJson<WorkspaceEvent[]>(EVENTS_KEY) ?? []
}

function saveEvents(events: WorkspaceEvent[]) {
  writeJson(EVENTS_KEY, events.slice(0, 150))
}

function pushEvent(event: Omit<WorkspaceEvent, 'id' | 'ts'>) {
  const next = [
    {
      ...event,
      id: makeId('evt'),
      ts: new Date().toISOString(),
    },
    ...readEvents(),
  ]
  saveEvents(next)
  return next
}

function getMode(): WorkspaceMode {
  return (localStorage.getItem(MODE_KEY) as WorkspaceMode | null) ?? 'sandbox'
}

function setMode(mode: WorkspaceMode) {
  localStorage.setItem(MODE_KEY, mode)
}

function useWorkspaceData(enabled: boolean): WorkspaceState {
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [recent, setRecent] = useState<AuditEvent[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [systemHealth, setSystemHealth] = useState<HealthResponse | null>(null)
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [remoteAgents, setRemoteAgents] = useState<Agent[]>([])
  const [blockReasons, setBlockReasons] = useState<BlockReason[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!enabled) return
    setError('')
    setLoading(true)
    try {
      const [ts, rec, h, sys, br, ag, rs] = await Promise.all([
        api.timeseries(7),
        api.auditQuery({ limit: 40 }),
        api.complianceHealth(),
        api.health(),
        api.blockReasons(7),
        api.agents().catch(() => [] as Agent[]),
        api.policyRules().catch(() => [] as PolicyRule[]),
      ])
      setTimeseries(ts)
      setRecent(rec.events)
      setHealth(h)
      setSystemHealth(sys)
      setBlockReasons(br)
      setRemoteAgents(Array.isArray(ag) ? ag : ((ag as { agents?: Agent[] }).agents ?? (ag as { items?: Agent[] }).items ?? []))
      setRules(Array.isArray(rs) ? rs : ((rs as { rules?: PolicyRule[] }).rules ?? []))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workspace')
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) return
    load()
    const iv = window.setInterval(load, 30000)
    return () => window.clearInterval(iv)
  }, [enabled, load])

  return { timeseries, recent, health, systemHealth, rules, remoteAgents, blockReasons, loading, error, reload: load }
}

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [gatewayUrl, setGatewayUrl] = useState(getAuth()?.gatewayUrl ?? 'https://edon-gateway-prod.fly.dev')
  const [token, setToken] = useState(getAuth()?.token ?? '')
  const [name, setName] = useState(localStorage.getItem('edon_solo_name') ?? 'Solo Operator')
  const [workspace, setWorkspace] = useState(localStorage.getItem('edon_solo_workspace') ?? 'Personal Workspace')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const login = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      saveAuth(gatewayUrl.replace(/\/$/, ''), token.trim())
      localStorage.setItem('edon_solo_name', name.trim())
      localStorage.setItem('edon_solo_workspace', workspace.trim())
      await api.me()
      onLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="glass-card w-full max-w-xl space-y-6 p-6 md:p-7">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-emerald-400/80">EDON Solo</p>
          <h1 className="mt-2 text-2xl font-bold">Personal governance workspace</h1>
          <p className="mt-2 text-sm text-muted-foreground">Sandbox-first. Auditable. Built for one operator and many agents.</p>
        </div>
        <form className="space-y-4" onSubmit={login}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block space-y-1.5 text-sm">
              <span className="text-xs text-muted-foreground">Workspace</span>
              <input value={workspace} onChange={e => setWorkspace(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 outline-none ring-0" />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-xs text-muted-foreground">Display name</span>
              <input value={name} onChange={e => setName(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 outline-none ring-0" />
            </label>
          </div>
          <label className="block space-y-1.5 text-sm">
            <span className="text-xs text-muted-foreground">Gateway URL</span>
            <input value={gatewayUrl} onChange={e => setGatewayUrl(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 outline-none ring-0" />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-xs text-muted-foreground">API token</span>
            <input value={token} onChange={e => setToken(e.target.value)} type="password" placeholder="edon-..." className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 font-mono outline-none ring-0" />
          </label>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button type="submit" disabled={loading} className="w-full rounded-xl bg-emerald-500 px-4 py-2.5 font-semibold text-black disabled:opacity-50">
            {loading ? 'Connecting...' : 'Open workspace'}
          </button>
        </form>
      </div>
    </div>
  )
}

function AssistantDrawer({
  open,
  onClose,
  tab,
  manifest,
  agents,
}: {
  open: boolean
  onClose: () => void
  tab: TabId
  manifest: WorkspaceManifest
  agents: WorkspaceAgent[]
}) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string; citations?: Citation[]; suggestion?: AssistantProposal | null }[]>([
    { role: 'assistant', content: 'Ask about a spike, an agent, a policy, or how to tighten the workspace.' },
  ])
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setLoading(true)
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(prev => [...prev, { role: 'user', content: q }])
    try {
      const response = await api.assistantChat(q, history, {
        tab,
        workspace: manifest.workspace_name,
        mode: manifest.mode,
        agent_count: agents.length,
        recent_agents: agents.slice(0, 5).map(a => ({ id: a.agent_id, mode: a.mode, risk: a.risk_tier })),
      })
      setMessages(prev => [...prev, { role: 'assistant', content: response.answer, citations: uniqueCitations(response.citations), suggestion: response.suggestion }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: e instanceof Error ? e.message : 'Assistant unavailable' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-3 top-3 bottom-3 z-50 flex w-[min(34rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-3xl border border-white/10 bg-background/95 shadow-[0_24px_60px_rgba(0,0,0,0.45)] backdrop-blur-2xl"
          >
            <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.02] px-4 py-3">
              <div>
                <p className="text-sm font-semibold">Solo Assistant</p>
                <p className="text-[10px] text-muted-foreground">Tenant-aware, audit-backed, workspace-first</p>
              </div>
              <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground">
                <X size={16} />
              </button>
            </div>
            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
              {messages.map((m, idx) => (
                <div key={idx} className={m.role === 'user' ? 'ml-8' : 'mr-2'}>
                  <div className={cn('rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed', m.role === 'user' ? 'border border-emerald-500/25 bg-emerald-500/15' : 'border border-white/10 bg-white/[0.04]')}>
                    {m.role === 'assistant' && (m.citations?.length ?? 0) > 0 ? (
                      <CitedText text={m.content} onCite={(_, id) => highlightCite(id)} />
                    ) : (
                      m.content
                    )}
                  </div>
                  {m.role === 'assistant' && m.suggestion && (
                    <div className="mt-2 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-3">
                      <p className="text-[10px] uppercase tracking-[0.18em] text-emerald-400/70">Suggested next step</p>
                      <p className="mt-1 text-sm font-medium text-foreground">{m.suggestion.description}</p>
                      <p className="mt-1 text-[13px] leading-6 text-muted-foreground">{m.suggestion.impact}</p>
                    </div>
                  )}
                  {m.role === 'assistant' && m.citations?.length ? (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Sources</span>
                      {m.citations.map(c => (
                        <button key={`${c.type}:${c.id}`} onClick={() => highlightCite(c.id)} className={cn('rounded-full border px-2 py-0.5 font-mono text-[10px]', CITE_COLORS[c.type])}>
                          {c.type}:{c.id}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
              {loading && <div className="text-xs text-muted-foreground">Thinking...</div>}
            </div>
            <div className="border-t border-white/10 p-4">
              <div className="flex gap-2">
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && send()}
                  className="flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-sm outline-none ring-0"
                  placeholder="Ask about a spike, agent, policy, or mode change..."
                />
                <button onClick={send} className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500 text-black">
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function InspectorDrawer({
  selection,
  onClose,
}: {
  selection: InspectorSelection | null
  onClose: () => void
}) {
  const [explanation, setExplanation] = useState('')
  const [suggestion, setSuggestion] = useState<AssistantExplainSuggestion | null>(null)
  const [citations, setCitations] = useState<Citation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!selection) return
    let cancelled = false
    setLoading(true)
    setExplanation('')
    setSuggestion(null)
    setCitations([])
    api.assistantExplain(selection.type, selection.id)
      .then(r => {
        if (cancelled) return
        setExplanation(r.explanation)
        setSuggestion(r.suggestion ?? null)
        setCitations(uniqueCitations(r.citations))
      })
      .catch(e => {
        if (!cancelled) setExplanation(e instanceof Error ? e.message : 'Failed to load reasoning')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selection])

  const label = selection?.type === 'agent' ? 'Agent profile' : selection?.type === 'decision' ? 'Decision replay' : 'Rule detail'

  return (
    <AnimatePresence>
      {selection && (
        <>
          <motion.div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-3 top-3 bottom-3 z-50 flex w-[min(34rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-3xl border border-white/10 bg-background/95 shadow-[0_24px_60px_rgba(0,0,0,0.45)] backdrop-blur-2xl"
          >
            <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.02] px-4 py-3">
              <div>
                <p className="text-sm font-semibold">AI Reasoning</p>
                <p className="text-[10px] text-muted-foreground">
                  {label} · <span className="font-mono">{selection.id}</span>
                </p>
              </div>
              <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground">
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
              {selection.type === 'decision' && selection.payload && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Replay</p>
                  <div className="mt-2 grid gap-2 text-xs text-muted-foreground">
                    <div className="flex justify-between gap-3"><span>Verdict</span><span className="text-foreground">{selection.payload.decision_verdict}</span></div>
                    <div className="flex justify-between gap-3"><span>Agent</span><span className="font-mono text-foreground">{selection.payload.agent_id}</span></div>
                    <div className="flex justify-between gap-3"><span>Tool</span><span className="text-foreground">{selection.payload.tool_name || '—'}</span></div>
                    <div className="flex justify-between gap-3"><span>Reason</span><span className="text-foreground">{selection.payload.decision_reason_code || '—'}</span></div>
                    <div className="flex justify-between gap-3"><span>Time</span><span className="text-foreground">{fmtDateTime(selection.payload.timestamp)}</span></div>
                    {selection.payload.risk_score != null && (
                      <div className="flex justify-between gap-3"><span>Risk</span><span className="text-foreground">{selection.payload.risk_score.toFixed(2)}</span></div>
                    )}
                  </div>
                </div>
              )}
              {selection.type === 'agent' && selection.payload && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Agent snapshot</p>
                  <div className="mt-2 grid gap-2 text-xs text-muted-foreground">
                    <div className="flex justify-between gap-3"><span>Name</span><span className="text-foreground">{selection.payload.name}</span></div>
                    <div className="flex justify-between gap-3"><span>Scope</span><span className="text-foreground">{selection.payload.scope}</span></div>
                    <div className="flex justify-between gap-3"><span>Mode</span><span className="text-foreground">{selection.payload.mode}</span></div>
                    <div className="flex justify-between gap-3"><span>Risk</span><span className="text-foreground">{selection.payload.risk_tier}</span></div>
                    <div className="flex justify-between gap-3"><span>Block rate</span><span className="text-foreground">{selection.payload.block_rate != null ? `${(selection.payload.block_rate * 100).toFixed(1)}%` : '—'}</span></div>
                    <div className="flex justify-between gap-3"><span>Decisions</span><span className="text-foreground">{selection.payload.decisions_total ?? 0}</span></div>
                  </div>
                </div>
              )}
              {selection.type === 'rule' && selection.payload && (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Rule snapshot</p>
                  <div className="mt-2 grid gap-2 text-xs text-muted-foreground">
                    <div className="flex justify-between gap-3"><span>Name</span><span className="text-foreground">{selection.payload.name}</span></div>
                    <div className="flex justify-between gap-3"><span>Status</span><span className="text-foreground">{selection.payload.enabled ? 'active' : 'off'}</span></div>
                    <div className="flex justify-between gap-3"><span>Regulation</span><span className="text-foreground">{selection.payload.regulation || '—'}</span></div>
                  </div>
                </div>
              )}
              {loading ? (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3 text-xs text-muted-foreground">
                  <RefreshCw size={11} className="mr-2 inline animate-spin" />
                  Analysing...
                </div>
              ) : (
                <>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                    <p className="mb-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Reasoning</p>
                    <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">{explanation}</p>
                  </div>
                  {suggestion && (
                    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-3">
                      <p className="text-[10px] uppercase tracking-[0.18em] text-emerald-400/70">Suggested next step</p>
                      <p className="mt-1 text-sm font-semibold text-foreground">{suggestion.title}</p>
                      <p className="mt-1 text-[13px] leading-6 text-muted-foreground">{suggestion.body}</p>
                    </div>
                  )}
                  {citations.length > 0 && (
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                      <p className="mb-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Sources</p>
                      <div className="flex flex-wrap gap-1.5">
                        {citations.map(c => (
                          <button
                            key={`${c.type}:${c.id}`}
                            onClick={() => highlightCite(c.id)}
                            className={cn('rounded-full border px-2 py-0.5 font-mono text-[10px]', CITE_COLORS[c.type])}
                          >
                            {c.type}:{c.id}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function emptyManifest(me: MeResponse | null, remoteAgents: Agent[] = []): WorkspaceManifest {
  return defaultManifest(me, remoteAgents)
}

function LoginAndWorkspace() {
  const [authReady, setAuthReady] = useState(!!getAuth())
  const [me, setMe] = useState<MeResponse | null>(null)
  const [tab, setTab] = useState<TabId>('overview')
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [inspector, setInspector] = useState<InspectorSelection | null>(null)
  const [modeConfirm, setModeConfirm] = useState<WorkspaceMode | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('edon_solo_theme') as 'dark' | 'light') || 'dark')
  const [workspaceManifest, setWorkspaceManifest] = useState<WorkspaceManifest | null>(() => readManifest())
  const [manifestDraft, setManifestDraft] = useState('')
  const [newAgentName, setNewAgentName] = useState('')
  const [newAgentScope, setNewAgentScope] = useState('')
  const [newAgentRisk, setNewAgentRisk] = useState<RiskTier>('medium')
  const [newAgentMode, setNewAgentMode] = useState<WorkspaceMode>('sandbox')
  const workspace = useWorkspaceData(authReady)

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('edon_solo_theme', theme)
  }, [theme])

  useEffect(() => {
    if (!authReady) return
    api.me().then(m => {
      setMe(m)
      const current = readManifest()
      if (!current) {
        const seeded = emptyManifest(m, [])
        setWorkspaceManifest(seeded)
        saveManifest(seeded)
        setManifestDraft(JSON.stringify(seeded, null, 2))
      } else {
        setWorkspaceManifest(current)
        setManifestDraft(JSON.stringify(current, null, 2))
      }
    }).catch(() => setAuthReady(false))
  }, [authReady])

  useEffect(() => {
    if (!workspaceManifest && me) {
      const seeded = emptyManifest(me, workspace.remoteAgents)
      setWorkspaceManifest(seeded)
      saveManifest(seeded)
      setManifestDraft(JSON.stringify(seeded, null, 2))
    }
  }, [workspaceManifest, me, workspace.remoteAgents])

  useEffect(() => {
    if (!workspaceManifest) return
    setMode(workspaceManifest.mode)
    if (localStorage.getItem(MODE_KEY) !== workspaceManifest.mode) {
      localStorage.setItem(MODE_KEY, workspaceManifest.mode)
    }
  }, [workspaceManifest])

  const currentMode = workspaceManifest?.mode ?? getMode()

  const allAgents = useMemo(() => {
    const byId = new Map<string, WorkspaceAgent>()
    for (const agent of workspaceManifest?.agents ?? []) byId.set(agent.agent_id, agent)
    for (const remote of workspace.remoteAgents) {
      if (!byId.has(remote.agent_id)) {
        byId.set(remote.agent_id, {
          agent_id: remote.agent_id,
          name: remote.name ?? remote.agent_id,
          scope: remote.description ?? 'remote agent',
          risk_tier: (remote.block_rate ?? 0) > 0.2 ? 'high' : (remote.block_rate ?? 0) > 0.1 ? 'medium' : 'low',
          mode: currentMode,
          source: 'remote',
          status: remote.status,
          block_rate: remote.block_rate,
          decisions_total: remote.decisions_total,
          last_action: remote.last_seen ? `last seen ${relTime(remote.last_seen)}` : undefined,
        })
      } else {
        const current = byId.get(remote.agent_id)!
        byId.set(remote.agent_id, {
          ...current,
          status: current.status ?? remote.status,
          block_rate: current.block_rate ?? remote.block_rate,
          decisions_total: current.decisions_total ?? remote.decisions_total,
        })
      }
    }
    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [workspaceManifest?.agents, workspace.remoteAgents, currentMode])

  const agentModes = useMemo(() => Object.fromEntries(allAgents.map(a => [a.agent_id, a.mode])) as Record<string, WorkspaceMode>, [allAgents])
  const recentEvents = useMemo(() => readEvents(), [workspaceManifest, workspace.recent])

  const workspaceTimeline = useMemo(() => {
    const auditEvents: WorkspaceEvent[] = workspace.recent.slice(0, 30).map(evt => ({
      id: evt.action_id || evt.id || makeId('audit'),
      ts: evt.timestamp,
      kind: 'audit',
      title: `${evt.decision_verdict} · ${evt.agent_id}`,
      detail: `${evt.tool_name || 'action'} · ${evt.decision_reason_code || 'no reason'} · ${evt.risk_score != null ? `risk ${evt.risk_score.toFixed(2)}` : 'no risk score'}`,
      refId: evt.action_id || evt.id || undefined,
      verdict: evt.decision_verdict,
    }))
    return [...recentEvents, ...auditEvents].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()).slice(0, 12)
  }, [recentEvents, workspace.recent])

  const stats = useMemo(() => {
    const total = workspace.timeseries.reduce((sum, p) => sum + p.allowed + p.blocked + p.confirm, 0)
    const blocked = workspace.timeseries.reduce((sum, p) => sum + p.blocked, 0)
    const escalated = workspace.timeseries.reduce((sum, p) => sum + p.confirm, 0)
    const blockRate = total > 0 ? (blocked / total) * 100 : 0
    return {
      total,
      blocked,
      escalated,
      agents: allAgents.length,
      blockRate,
    }
  }, [workspace.timeseries, allAgents.length])

  const topBlockReasons = useMemo(() => [...workspace.blockReasons].sort((a, b) => b.count - a.count).slice(0, 4), [workspace.blockReasons])
  const totalRulesEnabled = workspace.rules.filter(r => r.enabled).length
  const sandboxCount = allAgents.filter(a => a.mode === 'sandbox').length
  const governedCount = allAgents.length - sandboxCount

  const saveCurrentManifest = (next: WorkspaceManifest, note?: string) => {
    setWorkspaceManifest(next)
    saveManifest(next)
    setManifestDraft(JSON.stringify(next, null, 2))
    pushEvent({
      kind: 'workspace',
      title: note || 'Workspace updated',
      detail: `${next.workspace_name} · ${next.mode} · ${next.agents.length} agents`,
    })
  }

  const setWorkspaceMode = (mode: WorkspaceMode) => {
    if (!workspaceManifest) return
    const next = { ...workspaceManifest, mode, updated_at: new Date().toISOString() }
    saveCurrentManifest(next, mode === 'sandbox' ? 'Sandbox enabled' : 'Live governance enabled')
    setMode(mode)
    setModeConfirm(null)
  }

  const updateAgentMode = (agentId: string, mode: WorkspaceMode) => {
    if (!workspaceManifest) return
    const nextAgents = workspaceManifest.agents.map(agent => agent.agent_id === agentId ? { ...agent, mode } : agent)
    saveCurrentManifest({ ...workspaceManifest, agents: nextAgents, updated_at: new Date().toISOString() }, `Agent ${agentId} moved to ${mode}`)
  }

  const addAgent = () => {
    if (!workspaceManifest) return
    if (!newAgentName.trim()) return
    const agent: WorkspaceAgent = {
      agent_id: `${newAgentName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${Math.random().toString(36).slice(2, 5)}`,
      name: newAgentName.trim(),
      scope: newAgentScope.trim() || 'workspace scope',
      risk_tier: newAgentRisk,
      mode: newAgentMode,
      source: 'custom',
    }
    saveCurrentManifest({
      ...workspaceManifest,
      agents: [agent, ...workspaceManifest.agents],
      updated_at: new Date().toISOString(),
    }, `Added agent ${agent.name}`)
    setNewAgentName('')
    setNewAgentScope('')
    setNewAgentRisk('medium')
    setNewAgentMode(currentMode)
  }

  const removeAgent = (agentId: string) => {
    if (!workspaceManifest) return
    const nextAgents = workspaceManifest.agents.filter(agent => agent.agent_id !== agentId)
    saveCurrentManifest({ ...workspaceManifest, agents: nextAgents, updated_at: new Date().toISOString() }, `Removed agent ${agentId}`)
  }

  const applyManifestDraft = () => {
    try {
      const parsed = JSON.parse(manifestDraft) as WorkspaceManifest
      const normalized: WorkspaceManifest = {
        version: parsed.version ?? 1,
        workspace_name: parsed.workspace_name || 'Personal Workspace',
        operator_name: parsed.operator_name || (me?.key_name || 'Solo Operator'),
        mode: parsed.mode === 'governed' ? 'governed' : 'sandbox',
        notes: parsed.notes || '',
        tools: Array.isArray(parsed.tools) ? parsed.tools : [],
        agents: Array.isArray(parsed.agents) ? parsed.agents.map(agent => ({
          agent_id: agent.agent_id,
          name: agent.name || agent.agent_id,
          scope: agent.scope || 'workspace scope',
          risk_tier: (['low', 'medium', 'high'].includes(agent.risk_tier) ? agent.risk_tier : 'medium') as RiskTier,
          mode: agent.mode === 'governed' ? 'governed' : 'sandbox',
          source: agent.source === 'remote' ? 'remote' : 'custom',
          status: agent.status,
          block_rate: agent.block_rate,
          decisions_total: agent.decisions_total,
          last_action: agent.last_action,
        })) : [],
        updated_at: new Date().toISOString(),
      }
      saveCurrentManifest(normalized, 'Manifest imported')
      setMode(normalized.mode)
    } catch {
      pushEvent({
        kind: 'workspace',
        title: 'Manifest import failed',
        detail: 'Could not parse the JSON manifest.',
      })
    }
  }

  const exportManifest = () => {
    if (!workspaceManifest) return
    downloadText(`${workspaceManifest.workspace_name.replace(/\s+/g, '-').toLowerCase()}-manifest.json`, JSON.stringify(workspaceManifest, null, 2))
    pushEvent({
      kind: 'workspace',
      title: 'Manifest exported',
      detail: 'Downloaded workspace manifest JSON.',
    })
  }

  const copyDiagnostics = async () => {
    const bundle = {
      workspace_name: workspaceManifest?.workspace_name ?? 'Personal Workspace',
      operator_name: workspaceManifest?.operator_name ?? 'Solo Operator',
      mode: currentMode,
      tenant_id: me?.tenant_id,
      role: me?.role,
      plan: me?.plan,
      gateway_request_id: getLastRequestId() ?? null,
      stats,
      top_block_reasons: topBlockReasons,
      manifest_version: workspaceManifest?.version,
      agent_modes: agentModes,
      updated_at: workspaceManifest?.updated_at,
    }
    await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2))
    pushEvent({
      kind: 'workspace',
      title: 'Diagnostics copied',
      detail: 'Support bundle copied to the clipboard.',
    })
  }

  if (!authReady) {
    return <LoginScreen onLogin={() => setAuthReady(true)} />
  }

  const canSwitchLive = currentMode === 'sandbox'

  return (
    <div className="min-h-screen">
      <AnimatePresence>
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className={currentMode === 'sandbox' ? 'border-b border-blue-500/30 bg-blue-500/10' : 'border-b border-emerald-500/30 bg-emerald-500/10'}
        >
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5">
            <div className={cn('flex items-center gap-2', currentMode === 'sandbox' ? 'text-blue-300' : 'text-emerald-300')}>
              <Sparkles size={14} />
              <span className="text-xs font-semibold">{currentMode === 'sandbox' ? 'Sandbox mode' : 'Live governance'}</span>
            </div>
            <p className={cn('text-xs', currentMode === 'sandbox' ? 'text-blue-300/80' : 'text-emerald-300/80')}>
              {currentMode === 'sandbox'
                ? 'Audit-only · No execution · transparent workspace review'
                : 'Enforcement on · Governed actions active · all live actions are audited'}
            </p>
            <button
              className="ml-auto rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-muted-foreground"
              onClick={() => setModeConfirm(currentMode === 'sandbox' ? 'governed' : 'sandbox')}
            >
              {currentMode === 'sandbox' ? 'Enable live governance' : 'Return to sandbox'}
            </button>
          </div>
        </motion.div>
      </AnimatePresence>

      <header className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/15">
            <Shield size={18} className="text-emerald-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.22em] text-emerald-400/80">EDON Solo</p>
            <h1 className="truncate text-lg font-bold">{workspaceManifest?.workspace_name || me?.tenant_id || 'Personal Workspace'}</h1>
            <p className="truncate text-xs text-muted-foreground">
              Role: {me?.role || '—'} · Plan: {me?.plan || '—'} · Last request: {getLastRequestId() ?? '—'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} className="rounded-xl border border-white/10 bg-white/[0.03] p-2 text-muted-foreground hover:text-foreground">
            {theme === 'dark' ? <SunMedium size={14} /> : <MoonStar size={14} />}
          </button>
          <button onClick={() => setAssistantOpen(true)} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
            Assistant
          </button>
          <button onClick={() => { clearAuth(); setAuthReady(false) }} className="rounded-xl border border-white/10 bg-white/[0.03] p-2 text-muted-foreground hover:text-foreground">
            <LogOut size={14} />
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-8">
        <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Decisions" value={stats.total.toLocaleString()} hint="last 7 days" icon={ListChecks} tone="text-blue-400" />
          <StatCard label="Blocked" value={stats.blocked.toLocaleString()} hint={`${stats.blockRate.toFixed(1)}% block rate`} icon={ShieldAlert} tone="text-red-400" />
          <StatCard label="Escalated" value={stats.escalated.toLocaleString()} hint="approval-bound" icon={ClipboardList} tone="text-amber-400" />
          <StatCard label="Agents" value={stats.agents.toLocaleString()} hint={`${sandboxCount} sandbox · ${governedCount} governed`} icon={Users} tone="text-emerald-400" />
        </div>

        <div className="mb-5 flex flex-wrap items-center gap-2">
          {([
            ['overview', 'Overview', Activity],
            ['agents', 'Agents', Users],
            ['audit', 'Audit', FileText],
            ['policies', 'Policies', Shield],
            ['workspace', 'Workspace', Database],
            ['settings', 'Settings', Wrench],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn('flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors', tab === id ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground')}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
          <span className="ml-auto text-xs text-muted-foreground">Workspace mode: {currentMode}</span>
        </div>

        {workspace.loading ? (
          <div className="glass-card p-5 text-sm text-muted-foreground">Loading workspace...</div>
        ) : workspace.error ? (
          <div className="glass-card p-5 text-sm text-red-400">{workspace.error}</div>
        ) : (
          <>
            {tab === 'overview' && (
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-2">
                  <Panel
                    eyebrow="Live Decisions"
                    title="Recent governed actions"
                    action={<button onClick={workspace.reload} className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground"><RefreshCw size={14} /></button>}
                  >
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="text-xs text-muted-foreground">
                          <tr className="border-b border-white/5">
                            <th className="pb-2 text-left font-medium">Verdict</th>
                            <th className="pb-2 text-left font-medium">Agent</th>
                            <th className="pb-2 text-left font-medium hidden md:table-cell">Tool</th>
                            <th className="pb-2 text-left font-medium hidden lg:table-cell">Reason</th>
                            <th className="pb-2 text-right font-medium">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {workspace.recent.slice(0, 10).map((event, idx) => (
                            <tr
                              key={event.action_id || event.id || idx}
                              data-cite-id={event.action_id || event.id || undefined}
                              className="border-b border-white/[0.03] transition-colors hover:bg-white/[0.02]"
                              onClick={() => setInspector({ type: 'decision', id: event.action_id || event.id || `audit-${idx}`, payload: event })}
                            >
                              <td className="py-2.5 pr-2"><VerdictBadge verdict={event.decision_verdict} /></td>
                              <td className="py-2.5 pr-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-mono text-foreground">{event.agent_id}</span>
                                  <ModeChip mode={allAgents.find(a => a.agent_id === event.agent_id)?.mode ?? currentMode} />
                                </div>
                              </td>
                              <td className="hidden py-2.5 pr-2 text-muted-foreground md:table-cell">{event.tool_name || '—'}</td>
                              <td className="hidden py-2.5 pr-2 text-muted-foreground lg:table-cell">{event.decision_reason_code || '—'}</td>
                              <td className="py-2.5 text-right whitespace-nowrap text-muted-foreground">{relTime(event.timestamp)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Panel>

                  <Panel eyebrow="Workspace Timeline" title="Change log and replay trail">
                    <div className="space-y-3">
                      {workspaceTimeline.map(item => (
                        <button
                          key={item.id}
                          data-cite-id={item.refId || item.id}
                        onClick={() => {
                          if (item.kind !== 'audit' || !item.refId) return
                          const replay = workspace.recent.find(e => (e.action_id || e.id) === item.refId)
                          if (!replay) return
                          setInspector({ type: 'decision', id: item.refId, payload: replay })
                        }}
                          className="flex w-full items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3 text-left transition-colors hover:bg-white/[0.05]"
                        >
                          <div className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border', item.kind === 'audit' ? 'border-amber-500/20 bg-amber-500/10 text-amber-400' : 'border-blue-500/20 bg-blue-500/10 text-blue-400')}>
                            {item.kind === 'audit' ? <FileText size={14} /> : <Sparkles size={14} />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-medium text-foreground">{item.title}</p>
                              {item.verdict && <VerdictBadge verdict={item.verdict} />}
                              <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">{item.kind}</span>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-xs text-muted-foreground">{relTime(item.ts)}</p>
                            <p className="mt-1 text-[10px] text-muted-foreground/70">{fmtDateTime(item.ts)}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </Panel>
                </div>

                <div className="space-y-4">
                  <Panel eyebrow="Workspace Posture" title="What is currently on">
                    <div className="space-y-2 text-xs">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">Mode</span>
                        <ModeChip mode={currentMode} />
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">Workspace</span>
                        <span className="font-medium text-foreground">{workspaceManifest?.workspace_name || '—'}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">Operator</span>
                        <span className="font-medium text-foreground">{workspaceManifest?.operator_name || '—'}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">Request ID</span>
                        <span className="font-mono text-foreground">{getLastRequestId() ?? '—'}</span>
                      </div>
                    </div>
                  </Panel>

                  <Panel eyebrow="Confidence Guide" title="How to read the numbers">
                    <div className="space-y-2 text-xs text-muted-foreground">
                      <p><span className="text-foreground">0-10%</span> block rate = normal.</p>
                      <p><span className="text-foreground">10-20%</span> block rate = watch.</p>
                      <p><span className="text-foreground">20%+</span> block rate = concern.</p>
                      <p><span className="text-foreground">Stable</span> is good. <span className="text-foreground">Rising</span> means review. <span className="text-foreground">Spiked</span> means attention.</p>
                    </div>
                  </Panel>

                  <Panel eyebrow="Pressure Points" title="What needs attention">
                    <div className="space-y-2">
                      {topBlockReasons.length > 0 ? topBlockReasons.map(reason => (
                        <div key={reason.reason} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
                          <span className="text-muted-foreground">{reason.reason}</span>
                          <span className="font-semibold text-foreground">{reason.count}</span>
                        </div>
                      )) : (
                        <p className="text-xs text-muted-foreground">No block reasons yet.</p>
                      )}
                    </div>
                  </Panel>
                </div>
              </div>
            )}

            {tab === 'agents' && (
              <div className="space-y-4">
                <Panel
                  eyebrow="Add agent"
                  title="Create a workspace agent"
                  action={<span className="text-xs text-muted-foreground">Each agent stays scoped and auditable.</span>}
                >
                  <div className="grid gap-3 md:grid-cols-4">
                    <label className="space-y-1 text-xs">
                      <span className="text-muted-foreground">Name</span>
                      <input value={newAgentName} onChange={e => setNewAgentName(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5" placeholder="Release Helper" />
                    </label>
                    <label className="space-y-1 text-xs md:col-span-2">
                      <span className="text-muted-foreground">Scope</span>
                      <input value={newAgentScope} onChange={e => setNewAgentScope(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5" placeholder="GitHub releases and changelog drafts" />
                    </label>
                    <div className="space-y-1 text-xs">
                      <span className="text-muted-foreground">Risk</span>
                      <select value={newAgentRisk} onChange={e => setNewAgentRisk(e.target.value as RiskTier)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                      </select>
                    </div>
                    <div className="space-y-1 text-xs">
                      <span className="text-muted-foreground">Mode</span>
                      <select value={newAgentMode} onChange={e => setNewAgentMode(e.target.value as WorkspaceMode)} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
                        <option value="sandbox">sandbox</option>
                        <option value="governed">governed</option>
                      </select>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <button onClick={addAgent} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-3 py-2 text-sm font-semibold text-black">
                      <Plus size={14} /> Add agent
                    </button>
                    <button
                      onClick={() => {
                        if (!workspaceManifest) return
                        const seeded = emptyManifest(me, workspace.remoteAgents)
                        saveCurrentManifest({ ...workspaceManifest, agents: seeded.agents, updated_at: new Date().toISOString() }, 'Workspace agents reset')
                      }}
                      className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
                    >
                      Reset list
                    </button>
                  </div>
                </Panel>

                <div className="grid gap-3 xl:grid-cols-2">
                  {allAgents.map(agent => {
                    const rate = agent.block_rate != null ? agent.block_rate * 100 : null
                    const trend = rate != null && rate > 20 ? 'spiked' : rate != null && rate > 10 ? 'rising' : 'stable'
                    const tone = trend === 'spiked' ? 'border-red-500/20 bg-red-500/5' : trend === 'rising' ? 'border-amber-500/20 bg-amber-500/5' : 'border-white/10 bg-white/[0.03]'
                    return (
                      <button
                        key={agent.agent_id}
                        data-cite-id={agent.agent_id}
                        onClick={() => setInspector({ type: 'agent', id: agent.agent_id, payload: agent })}
                        className={cn('glass-card-hover p-4 text-left', tone)}
                      >
                        <div className="mb-2 flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold">{agent.name}</p>
                            <p className="truncate font-mono text-xs text-muted-foreground">{agent.agent_id}</p>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <ModeChip mode={agent.mode} />
                            <RiskChip risk={agent.risk_tier} />
                          </div>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{agent.scope}</p>
                        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                          <span><span className="font-medium text-foreground">{agent.decisions_total ?? 0}</span> decisions</span>
                          <span><span className="font-medium text-foreground">{rate != null ? `${rate.toFixed(1)}%` : '—'}</span> block rate</span>
                          <span className={agent.status === 'alert' ? 'text-red-400' : agent.status === 'active' ? 'text-emerald-400' : 'text-muted-foreground'}>{agent.status || 'unknown'}</span>
                          <span>{agent.last_action || 'no recent action'}</span>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <button
                            onClick={e => { e.stopPropagation(); updateAgentMode(agent.agent_id, 'sandbox') }}
                            className={cn('rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest', agent.mode === 'sandbox' ? 'border-blue-500/30 bg-blue-500/15 text-blue-300' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground')}
                          >
                            sandbox
                          </button>
                          <button
                            onClick={e => { e.stopPropagation(); updateAgentMode(agent.agent_id, 'governed') }}
                            className={cn('rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest', agent.mode === 'governed' ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground')}
                          >
                            governed
                          </button>
                          <button
                            onClick={e => { e.stopPropagation(); removeAgent(agent.agent_id) }}
                            className="ml-auto inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground"
                          >
                            <Trash2 size={10} /> remove
                          </button>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {tab === 'audit' && (
              <div className="space-y-4">
                <Panel eyebrow="Filters" title="Audit feed" action={<span className="text-xs text-muted-foreground">{workspace.recent.length} events</span>}>
                  <div className="flex flex-wrap gap-2">
                    {(['all', 'ALLOW', 'BLOCK', 'CONFIRM'] as const).map(filter => (
                      <button key={filter} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
                        <Filter size={11} className="mr-1 inline" />
                        {filter}
                      </button>
                    ))}
                  </div>
                </Panel>

                <Panel eyebrow="Replay" title="Decision rows">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-xs text-muted-foreground">
                        <tr className="border-b border-white/5">
                          <th className="pb-2 text-left font-medium">Verdict</th>
                          <th className="pb-2 text-left font-medium">Agent</th>
                          <th className="pb-2 text-left font-medium hidden md:table-cell">Tool</th>
                          <th className="pb-2 text-left font-medium hidden lg:table-cell">Reason</th>
                          <th className="pb-2 text-left font-medium hidden lg:table-cell">Risk</th>
                          <th className="pb-2 text-right font-medium">Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {workspace.recent.map((event, idx) => {
                          const agent = allAgents.find(a => a.agent_id === event.agent_id)
                          return (
                            <tr
                              key={event.action_id || event.id || idx}
                              data-cite-id={event.action_id || event.id || undefined}
                              className="cursor-pointer border-b border-white/[0.03] transition-colors hover:bg-white/[0.02]"
                              onClick={() => setInspector({ type: 'decision', id: event.action_id || event.id || `audit-${idx}`, payload: event })}
                            >
                              <td className="py-2.5 pr-2"><VerdictBadge verdict={event.decision_verdict} /></td>
                              <td className="py-2.5 pr-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-mono text-xs text-foreground">{event.agent_id}</span>
                                  {agent && <ModeChip mode={agent.mode} />}
                                </div>
                              </td>
                              <td className="hidden py-2.5 pr-2 text-xs text-muted-foreground md:table-cell">{event.tool_name || '—'}</td>
                              <td className="hidden py-2.5 pr-2 text-xs text-muted-foreground lg:table-cell">{event.decision_reason_code || '—'}</td>
                              <td className="hidden py-2.5 pr-2 lg:table-cell">
                                {event.risk_score != null ? (
                                  <span className={cn('font-mono text-xs', event.risk_score > 0.7 ? 'text-red-400' : event.risk_score > 0.4 ? 'text-amber-400' : 'text-muted-foreground')}>
                                    {event.risk_score.toFixed(2)}
                                  </span>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="py-2.5 text-right text-xs text-muted-foreground">{relTime(event.timestamp)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>
            )}

            {tab === 'policies' && (
              <div className="space-y-4">
                <Panel eyebrow="Policy health" title="Rules and controls" action={<span className="text-xs text-muted-foreground">{totalRulesEnabled} active</span>}>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {workspace.rules.map(rule => (
                      <button
                        key={rule.rule_id}
                        data-cite-id={rule.rule_id}
                        onClick={() => setInspector({ type: 'rule', id: rule.rule_id, payload: rule })}
                        className="glass-card-hover p-4 text-left"
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-medium">{rule.name}</p>
                            <p className="text-xs text-muted-foreground">{rule.regulation || 'No regulation tagged'}</p>
                          </div>
                          <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest', rule.enabled ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border-white/10 bg-white/[0.03] text-muted-foreground')}>
                            {rule.enabled ? 'active' : 'off'}
                          </span>
                        </div>
                        <p className="line-clamp-3 text-xs text-muted-foreground">{rule.description || 'No description provided.'}</p>
                        <div className="mt-3 flex items-center gap-2">
                          <button
                            onClick={async e => {
                              e.stopPropagation()
                              await api.enableRule(rule.rule_id)
                              workspace.reload()
                              pushEvent({ kind: 'workspace', title: `Rule enabled`, detail: rule.name })
                            }}
                            className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground"
                          >
                            enable
                          </button>
                          <button
                            onClick={async e => {
                              e.stopPropagation()
                              await api.disableRule(rule.rule_id)
                              workspace.reload()
                              pushEvent({ kind: 'workspace', title: `Rule disabled`, detail: rule.name })
                            }}
                            className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground"
                          >
                            disable
                          </button>
                        </div>
                      </button>
                    ))}
                  </div>
                </Panel>
              </div>
            )}

            {tab === 'workspace' && workspaceManifest && (
              <div className="grid gap-4 lg:grid-cols-2">
                <Panel eyebrow="Manifest" title="Workspace manifest">
                  <div className="space-y-3 text-xs">
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="space-y-1">
                        <span className="text-muted-foreground">Workspace name</span>
                        <input
                          value={workspaceManifest.workspace_name}
                          onChange={e => saveCurrentManifest({ ...workspaceManifest, workspace_name: e.target.value, updated_at: new Date().toISOString() }, 'Workspace renamed')}
                          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="text-muted-foreground">Operator</span>
                        <input
                          value={workspaceManifest.operator_name}
                          onChange={e => saveCurrentManifest({ ...workspaceManifest, operator_name: e.target.value, updated_at: new Date().toISOString() }, 'Operator changed')}
                          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
                        />
                      </label>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="space-y-1">
                        <span className="text-muted-foreground">Default mode</span>
                        <select
                          value={workspaceManifest.mode}
                          onChange={e => saveCurrentManifest({ ...workspaceManifest, mode: e.target.value === 'governed' ? 'governed' : 'sandbox', updated_at: new Date().toISOString() }, `Workspace mode ${e.target.value}`)}
                          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
                        >
                          <option value="sandbox">sandbox</option>
                          <option value="governed">governed</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <span className="text-muted-foreground">Tools</span>
                        <input
                          value={workspaceManifest.tools.join(', ')}
                          onChange={e => saveCurrentManifest({ ...workspaceManifest, tools: e.target.value.split(',').map(v => v.trim()).filter(Boolean), updated_at: new Date().toISOString() }, 'Tools updated')}
                          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
                          placeholder="GitHub, Slack, Local APIs"
                        />
                      </label>
                    </div>
                    <label className="space-y-1 block">
                      <span className="text-muted-foreground">Notes</span>
                      <textarea
                        rows={4}
                        value={workspaceManifest.notes}
                        onChange={e => saveCurrentManifest({ ...workspaceManifest, notes: e.target.value, updated_at: new Date().toISOString() }, 'Workspace notes updated')}
                        className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
                      />
                    </label>
                    <div className="flex flex-wrap items-center gap-2">
                      <button onClick={exportManifest} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        <Download size={14} /> Export JSON
                      </button>
                      <button onClick={() => navigator.clipboard.writeText(JSON.stringify(workspaceManifest, null, 2))} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        <Copy size={14} /> Copy JSON
                      </button>
                      <button onClick={copyDiagnostics} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        <ClipboardList size={14} /> Copy diagnostics
                      </button>
                    </div>
                  </div>
                </Panel>

                <Panel eyebrow="Import / replay" title="Manifest JSON">
                  <div className="space-y-3">
                    <textarea
                      value={manifestDraft}
                      onChange={e => setManifestDraft(e.target.value)}
                      rows={20}
                      className="h-full min-h-[26rem] w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-2 font-mono text-[12px] text-foreground outline-none"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button onClick={applyManifestDraft} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-3 py-2 text-sm font-semibold text-black">
                        <Save size={14} /> Apply import
                      </button>
                      <button
                        onClick={() => {
                          const seeded = emptyManifest(me, workspace.remoteAgents)
                          setManifestDraft(JSON.stringify(seeded, null, 2))
                          pushEvent({ kind: 'workspace', title: 'Manifest reset', detail: 'Restored the default workspace manifest draft.' })
                        }}
                        className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
                      >
                        Reset template
                      </button>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3.5 py-3 text-xs text-muted-foreground">
                      Import/export keeps the workspace portable. Use this to move a solo setup between machines or version it in git.
                    </div>
                  </div>
                </Panel>

                <Panel eyebrow="Timeline" title="Portable audit trail">
                  <div className="space-y-2">
                    {workspaceTimeline.map(item => (
                      <div key={item.id} className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2.5">
                        <div className={cn('mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg border', item.kind === 'audit' ? 'border-amber-500/20 bg-amber-500/10 text-amber-400' : 'border-blue-500/20 bg-blue-500/10 text-blue-400')}>
                          {item.kind === 'audit' ? <FileText size={13} /> : <Sparkles size={13} />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-medium text-foreground">{item.title}</p>
                            {item.verdict && <VerdictBadge verdict={item.verdict} />}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
                        </div>
                        <div className="text-right text-[10px] text-muted-foreground">
                          <p>{relTime(item.ts)}</p>
                          <p className="mt-1">{fmtDateTime(item.ts)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </div>
            )}

            {tab === 'settings' && workspaceManifest && (
              <div className="grid gap-4 md:grid-cols-2">
                <Panel eyebrow="Workspace posture" title="Mode and connection">
                  <div className="space-y-3 text-xs">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">Mode</span>
                      <ModeChip mode={currentMode} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">Workspace</span>
                      <span className="font-medium text-foreground">{workspaceManifest.workspace_name}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">Operator</span>
                      <span className="font-medium text-foreground">{workspaceManifest.operator_name}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">Request ID</span>
                      <span className="font-mono text-foreground">{getLastRequestId() ?? '—'}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">Last update</span>
                      <span className="text-foreground">{fmtDateTime(workspaceManifest.updated_at)}</span>
                    </div>
                    <div className="flex flex-wrap gap-2 pt-2">
                      <button onClick={() => setModeConfirm(currentMode === 'sandbox' ? 'governed' : 'sandbox')} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        {currentMode === 'sandbox' ? <ArrowUpRight size={14} /> : <ArrowDownToLine size={14} />}
                        {currentMode === 'sandbox' ? 'Enable governed mode' : 'Return to sandbox'}
                      </button>
                      <button onClick={copyDiagnostics} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        <ClipboardList size={14} /> Copy diagnostics
                      </button>
                      <button onClick={() => { clearAuth(); setAuthReady(false) }} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
                        <LogOut size={14} /> Sign out
                      </button>
                    </div>
                  </div>
                </Panel>

                <Panel eyebrow="Transparency" title="What stays visible">
                  <div className="space-y-2 text-xs text-muted-foreground">
                    <p>Every decision shows a verdict, a reason, a timestamp, and a replay drawer.</p>
                    <p>Every agent shows its mode, scope, block rate, and recent action state.</p>
                    <p>Every policy shows whether it is active and why it matters.</p>
                    <p>The workspace timeline keeps both audit events and local configuration changes in one feed.</p>
                  </div>
                </Panel>
              </div>
            )}
          </>
        )}
      </main>

      <AnimatePresence>
        {modeConfirm && workspaceManifest && (
          <motion.div className="fixed inset-0 z-[70] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setModeConfirm(null)} />
            <motion.div initial={{ opacity: 0, scale: 0.96, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }}
              className="relative z-10 w-full max-w-md rounded-3xl border border-white/10 bg-background/95 p-6 shadow-[0_24px_60px_rgba(0,0,0,0.45)]">
              <div className="flex items-center gap-3">
                <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl border', modeConfirm === 'governed' ? 'border-amber-500/30 bg-amber-500/15 text-amber-400' : 'border-blue-500/30 bg-blue-500/15 text-blue-300')}>
                  <AlertCircle size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-bold">{modeConfirm === 'governed' ? 'Enable live governance?' : 'Return to sandbox?'}</h3>
                  <p className="text-xs text-muted-foreground">This changes how the workspace handles execution.</p>
                </div>
              </div>
              <p className="mt-4 text-sm leading-6 text-muted-foreground">
                {modeConfirm === 'governed'
                  ? 'Live governance will enforce policies, bind execution to decisions, and audit governed actions.'
                  : 'Sandbox will keep the workspace audit-only and prevent live execution for governed actions.'}
              </p>
              <div className="mt-5 flex gap-3">
                <button onClick={() => setModeConfirm(null)} className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground">
                  Cancel
                </button>
                <button onClick={() => setWorkspaceMode(modeConfirm)} className={cn('flex-1 rounded-xl px-3 py-2.5 text-sm font-semibold', modeConfirm === 'governed' ? 'bg-amber-500 text-black' : 'bg-blue-500 text-white')}>
                  {modeConfirm === 'governed' ? 'Enable live governance' : 'Return to sandbox'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {inspector && <InspectorDrawer selection={inspector} onClose={() => setInspector(null)} />}
      </AnimatePresence>

      <AssistantDrawer open={assistantOpen} onClose={() => setAssistantOpen(false)} tab={tab} manifest={workspaceManifest ?? emptyManifest(me, workspace.remoteAgents)} agents={allAgents} />
    </div>
  )
}

export default function App() {
  return <LoginAndWorkspace />
}
