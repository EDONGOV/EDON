import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield, LogOut, Key, KeyRound, RefreshCcw,
  AlertCircle, CheckCircle2, Eye, EyeOff, Copy,
  Plus, ChevronDown, ChevronUp, Activity,
  ScrollText, Building2, RotateCcw, Search, X,
  DollarSign, BarChart2, Globe, ToggleLeft, ToggleRight,
  UserCheck, CalendarClock, TrendingUp, FileText, Clock,
  Trophy, Server, FlaskConical, Lock, Power,
  Mic, MicOff, Volume2, VolumeX, Send, Bot, Loader2,
} from 'lucide-react'

// ── Constants ─────────────────────────────────────────────────────────────────

const GATEWAY     = 'https://edon-gateway-prod.fly.dev'
const SECRET_KEY  = 'edon_admin_secret'

const getSavedSecret  = () => localStorage.getItem(SECRET_KEY) || ''
const saveSecret      = (s: string) => localStorage.setItem(SECRET_KEY, s)
const clearSecret     = () => localStorage.removeItem(SECRET_KEY)

// ── Types ─────────────────────────────────────────────────────────────────────

interface TenantSummary {
  tenant_id: string
  plan: string
  status: string
  created_at?: string
  updated_at?: string
  active_key_count: number
  total_key_count: number
}

interface AuditEntry {
  id: string
  timestamp: string
  action_type: string
  tenant_affected?: string
  performed_by_ip?: string
  details: Record<string, unknown>
  bootstrap_key_hint?: string
}

interface Contract {
  id: string
  tenant_id: string
  acv: number
  term_months: number
  renewal_date: string
  status: 'active' | 'pilot' | 'suspended' | 'cancelled'
  agents_licensed: number
  decisions_included: number
  notes?: string
  created_at: string
  updated_at: string
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function adminRequest<T>(path: string, secret: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${GATEWAY}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Bootstrap-Secret': secret, ...(options.headers || {}) },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `${res.status}`)
  }
  return res.json()
}

function fmtAcv(n: number) { return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}` }
function fmtDate(iso: string) { return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function daysUntil(iso: string) { return Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000) }
function fmtTime(iso: string) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

// ── Shared UI ─────────────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return <div style={{ width: size, height: size }} className="border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
}

function Toast({ msg, type, onClose }: { msg: string; type: 'ok' | 'err'; onClose: () => void }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t) }, [onClose])
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
      className={`fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-medium shadow-xl ${type === 'ok' ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400' : 'bg-red-500/15 border-red-500/30 text-red-400'}`}>
      {type === 'ok' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
      {msg}
      <button onClick={onClose} className="ml-1 opacity-60 hover:opacity-100"><X size={12} /></button>
    </motion.div>
  )
}

function CopyButton({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  return (
    <button onClick={copy} title="Copy" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition">
      {copied ? <CheckCircle2 size={12} className="text-emerald-400" /> : <Copy size={12} />}
      {label && <span>{copied ? 'Copied' : label}</span>}
    </button>
  )
}

function RevealedKeyBanner({ keyValue, label, onDismiss }: { keyValue: string; label: string; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false)
  return (
    <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
      className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/25 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5"><CheckCircle2 size={12} /> {label} — copy now, shown once</p>
        <button onClick={onDismiss} className="text-muted-foreground/50 hover:text-muted-foreground"><X size={13} /></button>
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-[11px] font-mono break-all bg-emerald-500/10 px-2 py-1.5 rounded border border-emerald-500/20 text-emerald-300 select-all">
          {visible ? keyValue : '•'.repeat(Math.min(keyValue.length, 40))}
        </code>
        <button onClick={() => setVisible(v => !v)} className="text-muted-foreground hover:text-foreground transition">
          {visible ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
        <CopyButton value={keyValue} />
      </div>
    </motion.div>
  )
}

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${color}`}>{label}</span>
}

const STATUS_COLOR: Record<string, string> = {
  active:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  pilot:     'text-teal-400 bg-teal-500/10 border-teal-500/20',
  suspended: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  cancelled: 'text-red-400 bg-red-500/10 border-red-500/20',
}
const ACTION_COLORS: Record<string, string> = {
  bootstrap_key_provisioned: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  tenant_updated:            'text-blue-400 bg-blue-500/10 border-blue-500/20',
  support_key_created:       'text-purple-400 bg-purple-500/10 border-purple-500/20',
  ip_allowlist_add:          'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  ip_allowlist_remove:       'text-orange-400 bg-orange-500/10 border-orange-500/20',
  ip_brute_force_unlocked:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
  contract_created:          'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  contract_updated:          'text-blue-400 bg-blue-500/10 border-blue-500/20',
  contract_deleted:          'text-red-400 bg-red-500/10 border-red-500/20',
  feature_flag_set:          'text-violet-400 bg-violet-500/10 border-violet-500/20',
  feature_flag_deleted:      'text-orange-400 bg-orange-500/10 border-orange-500/20',
}

const ALL_FEATURES = [
  { id: 'hipaa_advanced_audit',      label: 'HIPAA Advanced Audit',       description: 'Extended retention + tamper-evident export' },
  { id: 'custom_policy_packs',       label: 'Custom Policy Packs',        description: 'Upload and deploy custom governance rule sets' },
  { id: 'sso_saml',                  label: 'SSO / SAML',                 description: 'Single sign-on via SAML 2.0 identity providers' },
  { id: 'multi_agent_orchestration', label: 'Multi-Agent Orchestration',  description: 'Coordinate multiple AI agents with shared policies' },
  { id: 'real_time_webhooks',        label: 'Real-Time Webhooks',         description: 'Push decision events to external systems instantly' },
  { id: 'telegram_alerts',           label: 'Telegram Alerts',            description: 'Governance alerts and daily summaries via Telegram' },
  { id: 'api_rate_limit_override',   label: 'Rate Limit Override',        description: 'Custom rate limits above contract default' },
]

// ── Access Gate ───────────────────────────────────────────────────────────────

function AccessGate({ onUnlock }: { onUnlock: (secret: string) => void }) {
  const [secret, setSecret]   = useState(getSavedSecret)
  const [visible, setVisible] = useState(false)
  const [remember, setRemember] = useState(!!getSavedSecret())
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      await adminRequest('/admin/tenants', secret.trim())
      if (remember) saveSecret(secret.trim()); else clearSecret()
      onUnlock(secret.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid bootstrap secret')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Shield size={20} className="text-primary" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-widest" style={{ color: 'hsl(38 95% 55%)' }}>EDON ADMIN</h1>
            <p className="text-xs text-muted-foreground">Internal operations dashboard</p>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Bootstrap Secret</label>
            <div className="relative">
              <input type={visible ? 'text' : 'password'} value={secret} onChange={e => setSecret(e.target.value)}
                className="w-full px-3 py-2 pr-9 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                placeholder="edon-bootstrap-…" autoFocus required />
              <button type="button" onClick={() => setVisible(v => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition">
                {visible ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} className="rounded border-border" />
            Remember on this device
          </label>
          {error && <p className="text-xs text-destructive flex items-center gap-1"><AlertCircle size={12} />{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? <Spinner size={14} /> : <KeyRound size={14} />}
            {loading ? 'Authenticating…' : 'Enter Admin Panel'}
          </button>
        </form>
      </motion.div>
    </div>
  )
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [health, setHealth]           = useState<{ ok: boolean; version: string; uptime_seconds: number; components: Record<string, { status: string }> } | null>(null)
  const [tenantCount, setTenantCount] = useState<number | null>(null)
  const [auditCount, setAuditCount]   = useState<number | null>(null)
  const [contracts, setContracts]     = useState<Contract[]>([])
  const [recentAudit, setRecentAudit] = useState<AuditEntry[]>([])
  const [loading, setLoading]         = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [h, t, a, c, audit] = await Promise.all([
          fetch(`${GATEWAY}/health`).then(r => r.json()),
          adminRequest<{ tenants: TenantSummary[] }>('/admin/tenants', secret).then(r => r.tenants?.length ?? 0),
          adminRequest<{ total: number }>('/admin/audit-log?limit=1', secret).then(r => r.total),
          adminRequest<{ contracts: Contract[]; total_arr: number }>('/admin/contracts', secret).catch(() => ({ contracts: [], total_arr: 0 })),
          adminRequest<{ entries: AuditEntry[] }>('/admin/audit-log?limit=4', secret).catch(() => ({ entries: [] })),
        ])
        setHealth(h); setTenantCount(t); setAuditCount(a)
        setContracts(c.contracts || [])
        setRecentAudit(audit.entries || [])
      } catch { toast('Failed to load overview', 'err') }
      finally { setLoading(false) }
    }
    load()
  }, [secret, toast])

  const uptimeFmt = (s: number) => { const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600); return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((s%3600)/60)}m` }

  const paying = contracts.filter(c => c.status === 'active' && c.acv > 0)
  const pilots = contracts.filter(c => c.status === 'pilot')
  const arr = paying.reduce((s, c) => s + c.acv, 0)
  const renewingSoon = paying.filter(c => c.renewal_date && daysUntil(c.renewal_date) <= 90 && daysUntil(c.renewal_date) > 0)

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'ARR',              value: arr > 0 ? fmtAcv(arr) : '—',   icon: DollarSign,    color: 'text-emerald-400', sub: `${paying.length} active contracts` },
          { label: 'Avg Contract',     value: paying.length > 0 ? fmtAcv(Math.round(arr / paying.length)) : '—', icon: FileText, color: 'text-blue-400', sub: 'avg ACV' },
          { label: 'Total Clients',    value: tenantCount ?? '—',             icon: Building2,     color: 'text-primary',    sub: `${pilots.length} pilots in eval` },
          { label: 'Renewing ≤90d',    value: renewingSoon.length,            icon: CalendarClock, color: renewingSoon.length > 0 ? 'text-amber-400' : 'text-emerald-400', sub: renewingSoon.map(c => c.tenant_id.split('-')[0]).join(', ') || 'none upcoming' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{c.label}</span>
              <c.icon size={14} className={c.color} />
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60 truncate">{c.sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Contract breakdown */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><FileText size={13} className="text-primary" /> Contract Breakdown</h3>
          {paying.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 py-2">No active contracts yet.</p>
          ) : (
            <div className="space-y-2.5">
              {([12, 24, 36] as const).map(term => {
                const group = paying.filter(c => c.term_months === term)
                if (!group.length) return null
                const groupArr = group.reduce((s, c) => s + c.acv, 0)
                return (
                  <div key={term} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-14 shrink-0">{term/12}-year</span>
                    <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                      <div className="h-full rounded-full bg-primary/60" style={{ width: `${(groupArr / arr) * 100}%` }} />
                    </div>
                    <span className="text-xs font-semibold w-12 text-right">{fmtAcv(groupArr)}</span>
                    <span className="text-[10px] text-muted-foreground/50 w-8">{group.length} co.</span>
                  </div>
                )
              })}
            </div>
          )}
          <div className="pt-1 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><FlaskConical size={11} className="text-teal-400" /> Pilot pipeline</span>
            <span className="text-teal-400 font-semibold">{pilots.length} org{pilots.length !== 1 ? 's' : ''} evaluating</span>
          </div>
        </div>

        {/* Recent admin actions */}
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><ScrollText size={13} className="text-primary" /> Recent Admin Actions</h3>
          {recentAudit.length === 0 ? (
            <p className="text-xs text-muted-foreground/60 py-2">No audit entries yet.</p>
          ) : (
            <div className="space-y-2">
              {recentAudit.map(e => (
                <div key={e.id} className="flex items-start gap-2.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0 mt-1.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge label={e.action_type.replace(/_/g, ' ')} color={ACTION_COLORS[e.action_type] || 'text-muted-foreground bg-muted/30 border-border'} />
                      {e.tenant_affected && <span className="text-xs font-mono text-primary truncate">{e.tenant_affected}</span>}
                    </div>
                    <span className="text-[11px] text-muted-foreground/50">{fmtTime(e.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {health && (
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><Server size={13} className="text-primary" /> Gateway Health</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-1">
            {[
              { label: 'Status',       value: health.ok ? 'Healthy' : 'Degraded', color: health.ok ? 'text-emerald-400' : 'text-red-400' },
              { label: 'Version',      value: health.version || '—',              color: 'text-muted-foreground' },
              { label: 'Uptime',       value: health.uptime_seconds ? uptimeFmt(health.uptime_seconds) : '—', color: 'text-emerald-400' },
              { label: 'Admin Actions', value: (auditCount ?? 0).toLocaleString(), color: 'text-foreground' },
            ].map(m => (
              <div key={m.label} className="bg-muted/20 rounded-lg px-3 py-2.5 border border-border/40">
                <p className="text-[10px] text-muted-foreground mb-0.5">{m.label}</p>
                <p className={`text-sm font-semibold ${m.color}`}>{m.value}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Object.entries(health.components || {}).map(([name, info]) => (
              <div key={name} className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/20 border border-border/40 text-xs">
                <span className="text-muted-foreground capitalize">{name.replace(/_/g, ' ')}</span>
                <div className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full ${info.status === 'ok' ? 'bg-emerald-400 animate-pulse-dot' : 'bg-red-400'}`} />
                  <span className={info.status === 'ok' ? 'text-emerald-400' : 'text-red-400'}>{info.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Scale Tab ─────────────────────────────────────────────────────────────────

function MilestoneBar({ label, current, target, fmt }: { label: string; current: number; target: number; fmt: (n: number) => string }) {
  const pct = Math.min((current / target) * 100, 100)
  const reached = pct >= 100
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          {reached ? <Trophy size={11} className="text-primary shrink-0" /> : <div className="w-2.5 h-2.5 rounded-full border-2 border-muted-foreground/30 shrink-0" />}
          <span className={reached ? 'text-primary font-semibold' : 'text-muted-foreground'}>{label}</span>
        </div>
        <div className="flex items-center gap-2 tabular-nums">
          <span className="font-semibold">{fmt(current)}</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-muted-foreground/60">{fmt(target)}</span>
          {reached && <span className="px-1.5 py-0 rounded-full text-[9px] font-bold bg-primary/15 text-primary border border-primary/30">HIT</span>}
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-muted/40 overflow-hidden">
        <motion.div className={`h-full rounded-full ${reached ? 'bg-primary' : 'bg-primary/50'}`}
          initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, ease: 'easeOut' }} />
      </div>
      <div className="flex justify-end">
        <span className={`text-[10px] ${reached ? 'text-primary font-semibold' : 'text-muted-foreground/50'}`}>
          {reached ? '✓ Milestone reached' : `${pct.toFixed(1)}% · ${fmt(target - current)} to go`}
        </span>
      </div>
    </div>
  )
}

function ScaleTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [tenantCount, setTenantCount] = useState<number | null>(null)
  const [auditTotal, setAuditTotal]   = useState<number | null>(null)
  const [contracts, setContracts]     = useState<Contract[]>([])
  const [usageRows, setUsageRows]     = useState<{ tenant_id: string; total_decisions: number; unique_agents: number }[]>([])
  const [loading, setLoading]         = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [t, a, c, u] = await Promise.all([
          adminRequest<{ tenants: TenantSummary[] }>('/admin/tenants', secret).then(r => r.tenants?.length ?? 0),
          adminRequest<{ total: number }>('/admin/audit-log?limit=1', secret).then(r => r.total),
          adminRequest<{ contracts: Contract[] }>('/admin/contracts', secret),
          adminRequest<{ by_tenant: { tenant_id: string; total_decisions: number; unique_agents: number }[] }>('/admin/usage?period=365', secret).catch(() => ({ by_tenant: [] })),
        ])
        setTenantCount(t); setAuditTotal(a)
        setContracts(c.contracts || [])
        setUsageRows(u.by_tenant || [])
      } catch { toast('Failed to load scale data', 'err') }
      finally { setLoading(false) }
    }
    load()
  }, [secret, toast])

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  const paying = contracts.filter(x => x.status === 'active' && x.acv > 0)
  const pilots = contracts.filter(x => x.status === 'pilot')
  const arr = paying.reduce((s, c) => s + c.acv, 0)
  const totalAgentsEver = usageRows.reduce((s, r) => s + r.unique_agents, 0)
  const totalDecisions  = usageRows.reduce((s, r) => s + r.total_decisions, 0)

  const milestones = [
    { label: 'Paying Clients',      current: paying.length,      target: 10,       fmt: (n: number) => `${n}` },
    { label: 'Total Clients',       current: tenantCount ?? 0,   target: 25,        fmt: (n: number) => `${n}` },
    { label: 'ARR',                 current: arr,                target: 500_000,   fmt: (n: number) => fmtAcv(n) },
    { label: 'AI Agents Governed',  current: totalAgentsEver,    target: 100,       fmt: (n: number) => `${n}` },
    { label: 'Decisions Governed',  current: totalDecisions,     target: 1_000_000, fmt: (n: number) => totalDecisions >= 1000 ? `${(n/1000).toFixed(0)}k` : `${n}` },
    { label: 'Admin Actions',       current: auditTotal ?? 0,    target: 1000,      fmt: (n: number) => `${n}` },
  ]

  const daysRunning = contracts.length > 0
    ? Math.ceil((Date.now() - Math.min(...contracts.map(c => new Date(c.created_at).getTime()))) / 86400000)
    : 0

  return (
    <div className="space-y-5">
      {/* Big counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Paying Clients',  value: paying.length || '—',            icon: Trophy,   color: 'text-emerald-400', sub: `${pilots.length} pilots in eval` },
          { label: 'ARR',             value: arr > 0 ? fmtAcv(arr) : '—',    icon: DollarSign, color: 'text-primary',   sub: 'from active contracts'           },
          { label: 'AI Agents',       value: totalAgentsEver || '—',          icon: Server,   color: 'text-blue-400',   sub: 'ever governed (all time)'        },
          { label: 'Days Running',    value: daysRunning || '—',              icon: Clock,    color: 'text-muted-foreground', sub: 'since first client' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{c.label}</span>
              <c.icon size={14} className={c.color} />
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Milestone tracker */}
      <div className="glass-card p-5 space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold flex items-center gap-2"><Trophy size={13} className="text-primary" /> Milestone Tracker</h3>
          <span className="text-xs text-muted-foreground/60">{milestones.filter(m => m.current >= m.target).length}/{milestones.length} reached</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {milestones.map(m => <MilestoneBar key={m.label} {...m} />)}
        </div>
      </div>

      {/* Growth velocity */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><TrendingUp size={13} className="text-emerald-400" /> Decision Volume by Client</h3>
        {usageRows.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 py-4 text-center">No decisions recorded yet. Telemetry will appear here once clients start running agents.</p>
        ) : (
          <>
            <div className="flex items-end gap-2 h-24">
              {usageRows.slice(0, 10).map(r => {
                const maxD = Math.max(1, ...usageRows.map(x => x.total_decisions))
                return (
                  <div key={r.tenant_id} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                    <span className="text-[9px] text-muted-foreground/60 truncate w-full text-center">{r.total_decisions >= 1000 ? `${(r.total_decisions/1000).toFixed(0)}k` : r.total_decisions}</span>
                    <div className="w-full rounded-t bg-primary/30 border-t border-primary/50" style={{ height: `${(r.total_decisions / maxD) * 80}px` }} />
                    <span className="text-[9px] text-muted-foreground/50 truncate w-full text-center">{r.tenant_id.split('-')[0]}</span>
                  </div>
                )
              })}
            </div>
            <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Total: <span className="text-foreground font-semibold">{totalDecisions.toLocaleString()} decisions</span></span>
              <span>{usageRows.length} active tenants · last 365 days</span>
            </div>
          </>
        )}
      </div>

      {/* All-time totals */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">All-Time Totals</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Decisions Governed', value: totalDecisions > 0 ? totalDecisions.toLocaleString() : '—' },
            { label: 'Audit Log Entries',  value: (auditTotal ?? 0).toLocaleString() },
            { label: 'Clients Onboarded',  value: tenantCount ?? '—' },
            { label: 'AI Agents Active',   value: totalAgentsEver || '—' },
            { label: 'Paying Contracts',   value: paying.length || '—' },
            { label: 'Pilot Evals',        value: pilots.length || '—' },
            { label: 'ARR',                value: arr > 0 ? fmtAcv(arr) : '—' },
            { label: 'Days Running',       value: daysRunning || '—' },
          ].map(s => (
            <div key={s.label} className="bg-muted/20 rounded-lg px-3 py-2.5 border border-border/40">
              <p className="text-[10px] text-muted-foreground mb-0.5">{s.label}</p>
              <p className="text-sm font-semibold">{s.value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Clients Tab ───────────────────────────────────────────────────────────────

const STATUSES = ['active', 'pilot', 'suspended', 'cancelled'] as const

function ClientsTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [tenants, setTenants]   = useState<TenantSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [search, setSearch]     = useState('')
  const [filter, setFilter]     = useState<'all' | 'active' | 'pilot' | 'suspended'>('all')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [revealedKey, setRevealedKey] = useState<{ key: string; label: string } | null>(null)

  const [showNew, setShowNew]   = useState(false)
  const [pTenantId, setPTenantId] = useState('')
  const [pName, setPName]       = useState('')
  const [pEmail, setPEmail]     = useState('')
  const [pTerm, setPTerm]       = useState('1')
  const [pPilot, setPPilot]     = useState(false)
  const [pToken] = useState(() => `edon-admin-${crypto.randomUUID().replace(/-/g, '')}`)
  const [provisioning, setProvisioning] = useState(false)

  const [addKeyTarget, setAddKeyTarget] = useState<string | null>(null)
  const [addKeyLabel, setAddKeyLabel]   = useState('')
  const [addKeyRole, setAddKeyRole]     = useState('user')
  const [addKeyToken] = useState(() => `edon-${crypto.randomUUID().replace(/-/g, '')}`)
  const [addingKey, setAddingKey]       = useState(false)

  const fetchTenants = useCallback(async () => {
    setLoading(true)
    try {
      const r = await adminRequest<{ tenants: TenantSummary[] }>('/admin/tenants', secret)
      setTenants(r.tenants || [])
    } catch { toast('Failed to load clients', 'err') }
    finally { setLoading(false) }
  }, [secret, toast])

  useEffect(() => { fetchTenants() }, [fetchTenants])

  const provisionTenant = async (e: React.FormEvent) => {
    e.preventDefault(); setProvisioning(true)
    try {
      await adminRequest('/admin/bootstrap-api-key', secret, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: pTenantId.trim(), token: pToken, name: pName.trim() || `${pTenantId.trim()}-admin`, email: pEmail.trim(), role: 'admin', plan: 'enterprise' }),
      })
      // Create contract record via API
      const renewalDate = new Date(Date.now() + parseInt(pTerm) * 365 * 86400_000).toISOString().slice(0, 10)
      await adminRequest('/admin/contracts', secret, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: pTenantId.trim(), acv: 0, term_months: parseInt(pTerm) * 12, renewal_date: renewalDate, status: pPilot ? 'pilot' : 'active', agents_licensed: 0, decisions_included: 0 }),
      }).catch(() => {}) // Non-fatal — contract can be added in Billing tab
      setRevealedKey({ key: pToken, label: `Admin key for ${pTenantId.trim()}` })
      toast('Client provisioned', 'ok')
      setShowNew(false); setPTenantId(''); setPName(''); setPEmail('')
      fetchTenants()
    } catch (err) { toast(err instanceof Error ? err.message : 'Provision failed', 'err') }
    finally { setProvisioning(false) }
  }

  const createSupportKey = async (tenantId: string) => {
    try {
      const r = await adminRequest<{ key: string; label: string }>(`/admin/tenants/${tenantId}/support-key`, secret, { method: 'POST', body: JSON.stringify({}) })
      setRevealedKey({ key: r.key, label: `Support key for ${tenantId}` })
      toast('Support key created — revoke when done', 'ok')
    } catch (err) { toast(err instanceof Error ? err.message : 'Failed', 'err') }
  }

  const updateStatus = async (tenantId: string, status: string) => {
    try {
      await adminRequest(`/admin/tenants/${tenantId}`, secret, { method: 'PATCH', body: JSON.stringify({ status }) })
      toast('Status updated', 'ok'); fetchTenants()
    } catch (err) { toast(err instanceof Error ? err.message : 'Update failed', 'err') }
  }

  const addKey = async (e: React.FormEvent) => {
    e.preventDefault(); if (!addKeyTarget) return; setAddingKey(true)
    try {
      await adminRequest('/admin/bootstrap-api-key', secret, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: addKeyTarget, token: addKeyToken, name: addKeyLabel || `${addKeyTarget}-key`, role: addKeyRole, plan: 'enterprise' }),
      })
      setRevealedKey({ key: addKeyToken, label: `${addKeyRole} key for ${addKeyTarget}` })
      toast('Key created', 'ok'); setAddKeyTarget(null); setAddKeyLabel(''); fetchTenants()
    } catch (err) { toast(err instanceof Error ? err.message : 'Failed', 'err') }
    finally { setAddingKey(false) }
  }

  const [contracts, setContracts] = useState<Contract[]>([])
  useEffect(() => {
    if (!secret) return
    adminRequest<{ contracts: Contract[] }>('/admin/contracts', secret)
      .then(r => setContracts(r.contracts || []))
      .catch(() => {})
  }, [secret])

  const contractByTenant = Object.fromEntries(contracts.map(c => [c.tenant_id, c]))
  const filtered = tenants.filter(t => {
    const matchSearch = t.tenant_id.toLowerCase().includes(search.toLowerCase())
    const contractStatus = contractByTenant[t.tenant_id]?.status ?? t.status
    return matchSearch && (filter === 'all' || contractStatus === filter || t.status === filter)
  })

  return (
    <div className="space-y-4">
      {revealedKey && <RevealedKeyBanner keyValue={revealedKey.key} label={revealedKey.label} onDismiss={() => setRevealedKey(null)} />}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-40">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search clients…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <div className="flex rounded-lg border border-border overflow-hidden text-xs">
          {(['all','active','pilot','suspended'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-2 capitalize transition ${filter === f ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>{f}</button>
          ))}
        </div>
        <button onClick={() => setShowNew(v => !v)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition">
          <Plus size={13} /> New Client
        </button>
        <button onClick={fetchTenants} className="p-2 rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition">
          <RefreshCcw size={13} />
        </button>
      </div>

      {/* New client form */}
      <AnimatePresence>
        {showNew && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={provisionTenant} className="glass-card p-5 space-y-4 overflow-hidden">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Building2 size={13} className="text-primary" /> Onboard New Client</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Tenant ID *</label>
                <input value={pTenantId} onChange={e => setPTenantId(e.target.value)} required placeholder="hospital-name"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Client Name</label>
                <input value={pName} onChange={e => setPName(e.target.value)} placeholder="Mercy General Hospital"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Email</label>
                <input type="email" value={pEmail} onChange={e => setPEmail(e.target.value)} placeholder="admin@hospital.com"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Contract Term</label>
                <select value={pTerm} onChange={e => setPTerm(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="1">1-year</option>
                  <option value="2">2-year</option>
                  <option value="3">3-year</option>
                </select>
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={pPilot} onChange={e => setPPilot(e.target.checked)} className="rounded border-border" />
              <FlaskConical size={12} className="text-teal-400" /> Start as pilot (no charge, eval period)
            </label>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Initial Admin Key — copy before provisioning</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[11px] font-mono break-all bg-muted/30 px-2 py-1.5 rounded border border-border text-muted-foreground select-all">{pToken}</code>
                <CopyButton value={pToken} />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={provisioning}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
                {provisioning ? <Spinner size={12} /> : <Plus size={12} />} Provision
              </button>
              <button type="button" onClick={() => setShowNew(false)}
                className="px-4 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground transition">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Add key form */}
      <AnimatePresence>
        {addKeyTarget && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={addKey} className="glass-card p-5 space-y-3 overflow-hidden border-primary/20">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Key size={13} className="text-primary" /> Add Key — <span className="font-mono text-primary">{addKeyTarget}</span></h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Label</label>
                <input value={addKeyLabel} onChange={e => setAddKeyLabel(e.target.value)} placeholder="Key name"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Role</label>
                <select value={addKeyRole} onChange={e => setAddKeyRole(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary">
                  {['admin','operator','user','read_only'].map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Generated key</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[11px] font-mono break-all bg-muted/30 px-2 py-1.5 rounded border border-border text-muted-foreground select-all">{addKeyToken}</code>
                <CopyButton value={addKeyToken} />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={addingKey}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
                {addingKey ? <Spinner size={12} /> : <Key size={12} />} Create Key
              </button>
              <button type="button" onClick={() => setAddKeyTarget(null)}
                className="px-4 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground transition">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size={20} /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">{search ? 'No clients match.' : 'No clients provisioned yet.'}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map(t => {
            const isOpen = expanded === t.tenant_id
            const contract = contractByTenant[t.tenant_id]
            const status = contract?.status ?? t.status
            const renewDays = contract?.renewal_date ? daysUntil(contract.renewal_date) : null
            const renewSoon = renewDays !== null && renewDays <= 90 && renewDays > 0
            return (
              <div key={t.tenant_id} className={`glass-card overflow-hidden ${renewSoon ? 'border-amber-500/20' : ''}`}>
                <button className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-white/[0.02] transition"
                  onClick={() => setExpanded(isOpen ? null : t.tenant_id)}>
                  <Building2 size={15} className="text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium">{t.tenant_id}</span>
                      {status === 'pilot' && <FlaskConical size={11} className="text-teal-400" />}
                      {renewSoon && <span className="text-[10px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 rounded">renews {renewDays}d</span>}
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${STATUS_COLOR[status] || STATUS_COLOR['active']}`}>{status}</span>
                  {contract?.acv ? <span className="text-xs font-semibold text-emerald-400 hidden sm:block">{fmtAcv(contract.acv)}/yr</span> : null}
                  {contract?.term_months ? <span className="text-xs text-muted-foreground hidden sm:block">{Math.round(contract.term_months/12)}yr</span> : null}
                  <span className="text-xs text-muted-foreground">{t.active_key_count}/{t.total_key_count} keys</span>
                  {isOpen ? <ChevronUp size={14} className="text-muted-foreground shrink-0" /> : <ChevronDown size={14} className="text-muted-foreground shrink-0" />}
                </button>
                <AnimatePresence>
                  {isOpen && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden border-t border-border/50">
                      <div className="px-5 py-4 space-y-4">
                        <div className="flex flex-wrap gap-2">
                          <button onClick={() => { setAddKeyTarget(t.tenant_id); setExpanded(null) }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium hover:bg-primary/20 transition">
                            <Plus size={12} /> Add Key
                          </button>
                          <button onClick={() => createSupportKey(t.tenant_id)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/20 transition">
                            <Eye size={12} /> Support Access
                          </button>
                          {status !== 'suspended' ? (
                            <button onClick={() => updateStatus(t.tenant_id, 'suspended')}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-medium hover:bg-amber-500/20 transition">
                              <Power size={12} /> Suspend
                            </button>
                          ) : (
                            <button onClick={() => updateStatus(t.tenant_id, 'active')}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition">
                              <CheckCircle2 size={12} /> Reactivate
                            </button>
                          )}
                        </div>
                        <div>
                          <label className="text-xs text-muted-foreground mb-1 block">Status</label>
                          <select defaultValue={status}
                            onChange={e => updateStatus(t.tenant_id, e.target.value)}
                            className="px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs focus:outline-none focus:ring-1 focus:ring-primary">
                            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                          </select>
                        </div>
                        {t.created_at && <p className="text-xs text-muted-foreground/60">Provisioned {new Date(t.created_at).toLocaleString()}</p>}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Billing Tab ───────────────────────────────────────────────────────────────

function BillingTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [arr, setArr]             = useState(0)
  const [loading, setLoading]     = useState(true)
  const [editing, setEditing]     = useState<string | null>(null)  // contract id or 'new'
  const [editTenantId, setEditTenantId] = useState('')
  const [editAcv, setEditAcv]     = useState('')
  const [editTerm, setEditTerm]   = useState('12')
  const [editRenewal, setEditRenewal] = useState('')
  const [editStatus, setEditStatus] = useState<Contract['status']>('active')
  const [saving, setSaving]       = useState(false)

  const loadContracts = useCallback(async () => {
    setLoading(true)
    try {
      const r = await adminRequest<{ contracts: Contract[]; total_arr: number }>('/admin/contracts', secret)
      setContracts(r.contracts || []); setArr(r.total_arr || 0)
    } catch { toast('Failed to load contracts', 'err') }
    finally { setLoading(false) }
  }, [secret, toast])

  useEffect(() => { loadContracts() }, [loadContracts])

  const openEdit = (c: Contract) => {
    setEditTenantId(c.tenant_id); setEditAcv(String(c.acv)); setEditTerm(String(c.term_months))
    setEditRenewal(c.renewal_date); setEditStatus(c.status); setEditing(c.id)
  }

  const openNew = () => {
    setEditTenantId(''); setEditAcv(''); setEditTerm('12'); setEditRenewal(''); setEditStatus('active'); setEditing('new')
  }

  const saveContract = async () => {
    setSaving(true)
    try {
      const body = { tenant_id: editTenantId, acv: parseInt(editAcv) || 0, term_months: parseInt(editTerm) || 12, renewal_date: editRenewal, status: editStatus, agents_licensed: 0, decisions_included: 0 }
      if (editing === 'new') {
        await adminRequest('/admin/contracts', secret, { method: 'POST', body: JSON.stringify(body) })
      } else {
        await adminRequest(`/admin/contracts/${editing}`, secret, { method: 'PATCH', body: JSON.stringify(body) })
      }
      toast('Contract saved', 'ok'); setEditing(null); loadContracts()
    } catch (err) { toast(err instanceof Error ? err.message : 'Save failed', 'err') }
    finally { setSaving(false) }
  }

  const deleteContract = async (id: string) => {
    if (!confirm('Delete this contract?')) return
    try {
      await adminRequest(`/admin/contracts/${id}`, secret, { method: 'DELETE' })
      toast('Contract deleted', 'ok'); loadContracts()
    } catch (err) { toast(err instanceof Error ? err.message : 'Delete failed', 'err') }
  }

  const paying = contracts.filter(c => c.status === 'active' && c.acv > 0)
  const tcv = contracts.filter(c => c.acv > 0).reduce((s, c) => s + c.acv * Math.round(c.term_months / 12), 0)
  const renewingSoon = contracts.filter(c => c.renewal_date && daysUntil(c.renewal_date) <= 90 && daysUntil(c.renewal_date) > 0)

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'ARR',           value: arr > 0 ? fmtAcv(arr) : '—',  color: 'text-emerald-400', sub: `${paying.length} active contracts` },
          { label: 'Avg ACV',       value: paying.length > 0 ? fmtAcv(Math.round(arr / paying.length)) : '—', color: 'text-blue-400', sub: 'per contract' },
          { label: 'TCV',           value: tcv > 0 ? fmtAcv(tcv) : '—', color: 'text-primary',     sub: 'committed revenue' },
          { label: 'Renewing ≤90d', value: renewingSoon.length,           color: renewingSoon.length > 0 ? 'text-amber-400' : 'text-emerald-400', sub: 'action required' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4 space-y-2">
            <div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">{c.label}</span><DollarSign size={13} className={c.color} /></div>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-[11px] text-muted-foreground/60">{c.sub}</p>
          </div>
        ))}
      </div>

      {renewingSoon.length > 0 && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-amber-500/8 border border-amber-500/20 text-xs text-amber-400">
          <CalendarClock size={13} />
          <span><strong>{renewingSoon.length} contract{renewingSoon.length > 1 ? 's' : ''}</strong> renewing within 90 days: {renewingSoon.map(c => `${c.tenant_id} (${daysUntil(c.renewal_date)}d)`).join(', ')}</span>
        </div>
      )}

      <div className="glass-card p-5 space-y-2">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Contract Registry</h3>
          <button onClick={openNew} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium hover:bg-primary/20 transition">
            <Plus size={11} /> Add Contract
          </button>
        </div>

        {/* New / edit form */}
        <AnimatePresence>
          {editing && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border border-primary/20 rounded-lg bg-muted/10 mb-3">
              <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Tenant ID</label>
                  <input value={editTenantId} onChange={e => setEditTenantId(e.target.value)} placeholder="hospital-name" disabled={editing !== 'new'}
                    className="w-full px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60" />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">ACV ($/yr)</label>
                  <input value={editAcv} onChange={e => setEditAcv(e.target.value)} placeholder="48000"
                    className="w-full px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Term (months)</label>
                  <select value={editTerm} onChange={e => setEditTerm(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs focus:outline-none focus:ring-1 focus:ring-primary">
                    <option value="12">12 months (1yr)</option><option value="24">24 months (2yr)</option><option value="36">36 months (3yr)</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Renewal date</label>
                  <input type="date" value={editRenewal} onChange={e => setEditRenewal(e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Status</label>
                  <select value={editStatus} onChange={e => setEditStatus(e.target.value as Contract['status'])}
                    className="w-full px-2 py-1.5 rounded-lg bg-muted/50 border border-border text-xs focus:outline-none focus:ring-1 focus:ring-primary">
                    <option value="active">active</option><option value="pilot">pilot</option><option value="suspended">suspended</option><option value="cancelled">cancelled</option>
                  </select>
                </div>
              </div>
              <div className="px-4 pb-3 flex gap-2">
                <button onClick={saveContract} disabled={saving}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
                  {saving ? <Spinner size={11} /> : <CheckCircle2 size={11} />} Save
                </button>
                <button onClick={() => setEditing(null)}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground transition">Cancel</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {contracts.length === 0 ? (
          <p className="text-center py-6 text-muted-foreground text-sm">No contracts yet. Click "Add Contract" to create one.</p>
        ) : (
          contracts.map(c => (
            <div key={c.id} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-border/40 hover:bg-muted/10 transition text-xs">
              <Building2 size={12} className="text-muted-foreground shrink-0" />
              <span className="flex-1 font-mono font-medium">{c.tenant_id}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${STATUS_COLOR[c.status] || STATUS_COLOR['active']}`}>{c.status}</span>
              <span className={`font-mono font-semibold w-20 text-right ${c.acv ? 'text-emerald-400' : 'text-muted-foreground/30'}`}>{c.acv ? `${fmtAcv(c.acv)}/yr` : 'no ACV'}</span>
              <span className="text-muted-foreground/50 w-14 text-right">{Math.round(c.term_months / 12)}yr</span>
              <span className={`w-28 text-right ${c.renewal_date && daysUntil(c.renewal_date) <= 90 ? 'text-amber-400 font-semibold' : 'text-muted-foreground/40'}`}>
                {c.renewal_date ? `renews ${fmtDate(c.renewal_date)}` : '—'}
              </span>
              <button onClick={() => openEdit(c)} className="text-muted-foreground/40 hover:text-primary transition"><BarChart2 size={11} /></button>
              <button onClick={() => deleteContract(c.id)} className="text-muted-foreground/40 hover:text-red-400 transition"><X size={11} /></button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ── IP Allowlist Tab ──────────────────────────────────────────────────────────

function IPAllowlistTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [tenants, setTenants]     = useState<TenantSummary[]>([])
  const [allowlists, setAllowlists] = useState<Record<string, string[]>>({})
  const [loading, setLoading]     = useState(true)
  const [newCidr, setNewCidr]     = useState<Record<string, string>>({})
  const [saving, setSaving]       = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const r = await adminRequest<{ tenants: TenantSummary[] }>('/admin/tenants', secret)
        const ts = r.tenants || []
        setTenants(ts)
        const lists = await Promise.all(ts.map(t =>
          adminRequest<{ cidrs: string[] }>(`/admin/ip-allowlist/${t.tenant_id}`, secret)
            .then(r => [t.tenant_id, r.cidrs] as [string, string[]])
            .catch(() => [t.tenant_id, []] as [string, string[]])
        ))
        setAllowlists(Object.fromEntries(lists))
      } catch { toast('Failed to load IP allowlists', 'err') }
      finally { setLoading(false) }
    }
    load()
  }, [secret, toast])

  const addCidr = async (tenantId: string) => {
    const cidr = newCidr[tenantId]?.trim()
    if (!cidr) return
    setSaving(tenantId)
    try {
      await adminRequest('/admin/ip-allowlist', secret, { method: 'POST', body: JSON.stringify({ tenant_id: tenantId, cidr }) })
      setAllowlists(p => ({ ...p, [tenantId]: [...(p[tenantId] || []), cidr] }))
      setNewCidr(p => ({ ...p, [tenantId]: '' }))
      toast(`${cidr} added`, 'ok')
    } catch (err) { toast(err instanceof Error ? err.message : 'Failed', 'err') }
    finally { setSaving(null) }
  }

  const removeCidr = async (tenantId: string, cidr: string) => {
    try {
      await adminRequest('/admin/ip-allowlist', secret, { method: 'DELETE', body: JSON.stringify({ tenant_id: tenantId, cidr }) })
      setAllowlists(p => ({ ...p, [tenantId]: p[tenantId].filter(c => c !== cidr) }))
      toast(`${cidr} removed`, 'ok')
    } catch (err) { toast(err instanceof Error ? err.message : 'Failed', 'err') }
  }

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-blue-500/8 border border-blue-500/20 text-xs text-blue-400">
        <Lock size={12} />
        IP allowlists restrict which source IPs can reach the EDON gateway per client. Clients with no rules accept requests from any IP.
      </div>
      <div className="space-y-3">
        {tenants.filter(t => t.status !== 'cancelled').map(t => {
          const cidrs = allowlists[t.tenant_id] || []
          return (
            <div key={t.tenant_id} className="glass-card p-4 space-y-3">
              <div className="flex items-center gap-3">
                <Globe size={14} className="text-muted-foreground shrink-0" />
                <span className="flex-1 font-mono text-sm font-medium">{t.tenant_id}</span>
                <div className="flex items-center gap-1.5 text-xs">
                  {cidrs.length > 0
                    ? <><div className="w-1.5 h-1.5 rounded-full bg-emerald-400" /><span className="text-emerald-400 font-medium">{cidrs.length} rule{cidrs.length !== 1 ? 's' : ''}</span></>
                    : <><div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" /><span className="text-muted-foreground">unrestricted</span></>}
                </div>
              </div>
              {cidrs.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {cidrs.map(cidr => (
                    <div key={cidr} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono">
                      {cidr}
                      <button onClick={() => removeCidr(t.tenant_id, cidr)} className="hover:text-red-400 transition"><X size={10} /></button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-2">
                <input value={newCidr[t.tenant_id] || ''} onChange={e => setNewCidr(p => ({ ...p, [t.tenant_id]: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCidr(t.tenant_id))}
                  placeholder="e.g. 10.0.0.0/8 or 203.0.113.5/32"
                  className="flex-1 px-3 py-1.5 rounded-lg bg-muted/50 border border-border text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary" />
                <button onClick={() => addCidr(t.tenant_id)} disabled={saving === t.tenant_id}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium hover:bg-primary/20 transition disabled:opacity-50 shrink-0">
                  {saving === t.tenant_id ? <Spinner size={11} /> : <Plus size={11} />} Add
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Feature Flags Tab ─────────────────────────────────────────────────────────

function FeatureFlagsTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [tenants, setTenants]   = useState<TenantSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [flags, setFlags]       = useState<Record<string, boolean>>({})
  const [flagsLoading, setFlagsLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    adminRequest<{ tenants: TenantSummary[] }>('/admin/tenants', secret)
      .then(r => { const ts = r.tenants || []; setTenants(ts); if (ts.length) setSelected(ts[0].tenant_id) })
      .catch(() => toast('Failed to load clients', 'err'))
      .finally(() => setLoading(false))
  }, [secret, toast])

  useEffect(() => {
    if (!selected) return
    setFlagsLoading(true)
    adminRequest<{ flags: Record<string, boolean> }>(`/admin/feature-flags/${selected}`, secret)
      .then(r => setFlags(r.flags || {}))
      .catch(() => setFlags({}))
      .finally(() => setFlagsLoading(false))
  }, [selected, secret])

  const toggle = async (tenantId: string, featureId: string) => {
    const cur = flags[featureId] ?? false
    const updated = { ...flags, [featureId]: !cur }
    setFlags(updated)
    try {
      await adminRequest('/admin/feature-flags', secret, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId, flag: featureId, enabled: !cur }),
      })
      toast(`${featureId} ${cur ? 'disabled' : 'enabled'}`, 'ok')
    } catch (err) {
      setFlags(flags) // revert
      toast(err instanceof Error ? err.message : 'Failed', 'err')
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  const tenant = tenants.find(t => t.tenant_id === selected)

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-muted/20 border border-border/40 text-xs text-muted-foreground">
        <AlertCircle size={12} />
        Feature flags are persisted in the gateway database per tenant.
      </div>

      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">Select Client</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {tenants.map(t => (
            <button key={t.tenant_id} onClick={() => setSelected(t.tenant_id)}
              className={`text-left px-3 py-2 rounded-lg border text-xs transition ${selected === t.tenant_id ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
              <p className="font-mono font-medium truncate">{t.tenant_id}</p>
              <span className={`text-[10px] ${STATUS_COLOR[t.status]?.split(' ')[0] || 'text-muted-foreground'}`}>{t.status}</span>
            </button>
          ))}
        </div>
      </div>

      {tenant && (
        <div className="glass-card p-5 space-y-1">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold font-mono">{tenant.tenant_id}</h3>
            <div className="flex items-center gap-2">
              {flagsLoading && <Spinner size={12} />}
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${STATUS_COLOR[tenant.status] || ''}`}>{tenant.status}</span>
            </div>
          </div>
          {ALL_FEATURES.map(f => {
            const enabled = flags[f.id] ?? false
            return (
              <div key={f.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted/10 transition">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium">{f.label}</p>
                  <p className="text-[11px] text-muted-foreground/60">{f.description}</p>
                </div>
                <button onClick={() => toggle(tenant.tenant_id, f.id)} className="shrink-0 hover:opacity-80 transition">
                  {enabled ? <ToggleRight size={20} className="text-primary" /> : <ToggleLeft size={20} className="text-muted-foreground/40" />}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Support Keys Tab ──────────────────────────────────────────────────────────

const SUPPORT_KEY_TTL_MS = 7 * 24 * 60 * 60 * 1000 // 7 days

function SupportKeysTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminRequest<{ entries: AuditEntry[]; total: number }>('/admin/audit-log?limit=100', secret)
      .then(r => setEntries((r.entries || []).filter(e => e.action_type === 'support_key_created')))
      .catch(() => toast('Failed to load support keys', 'err'))
      .finally(() => setLoading(false))
  }, [secret, toast])

  if (loading) return <div className="flex justify-center py-12"><Spinner size={20} /></div>

  const now = Date.now()
  const active  = entries.filter(e => now - new Date(e.timestamp).getTime() < SUPPORT_KEY_TTL_MS)
  const expired = entries.filter(e => now - new Date(e.timestamp).getTime() >= SUPPORT_KEY_TTL_MS)

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Active Support Keys', value: active.length,    color: 'text-blue-400'         },
          { label: 'Total Issued',        value: entries.length,   color: 'text-foreground'       },
          { label: 'Expired / Revoked',   value: expired.length,   color: 'text-muted-foreground' },
        ].map(c => (
          <div key={c.label} className="glass-card p-4">
            <p className="text-xs text-muted-foreground mb-1">{c.label}</p>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
          </div>
        ))}
      </div>

      <div className="glass-card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold flex items-center gap-2"><UserCheck size={13} className="text-primary" /> Support Key Log</h3>
          <span className="text-xs text-muted-foreground">7-day expiry · operator-scoped access</span>
        </div>
        {entries.length === 0 ? (
          <p className="text-center py-8 text-muted-foreground text-sm">No support keys issued yet.</p>
        ) : (
          <div className="space-y-2">
            {entries.map(e => {
              const isActive = now - new Date(e.timestamp).getTime() < SUPPORT_KEY_TTL_MS
              const expiresAt = new Date(new Date(e.timestamp).getTime() + SUPPORT_KEY_TTL_MS)
              const label = e.details && e.details['label'] != null ? String(e.details['label']) : null
              return (
                <div key={e.id} className="flex items-center gap-3 px-3 py-3 rounded-lg border border-border/40 hover:bg-muted/10 transition text-xs">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${isActive ? 'bg-blue-400 animate-pulse-dot' : 'bg-muted-foreground/30'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="font-mono font-medium truncate">{e.tenant_affected}</p>
                    {label && <p className="text-[11px] text-muted-foreground/60">{label}</p>}
                  </div>
                  <div className="hidden sm:block text-muted-foreground/60 shrink-0 text-right">
                    <p>created {fmtTime(e.timestamp)}</p>
                    <p>from {e.performed_by_ip}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={isActive ? 'text-blue-400 font-medium' : 'text-muted-foreground/50'}>
                      {isActive ? `expires ${fmtDate(expiresAt.toISOString())}` : 'expired'}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        <p className="text-xs text-muted-foreground/50 flex items-center gap-1.5">
          <AlertCircle size={11} />
          All support key usage is captured in the immutable audit log.
        </p>
      </div>
    </div>
  )
}

// ── Recovery Tab ──────────────────────────────────────────────────────────────

function RecoveryTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [tenantId, setTenantId] = useState('')
  const [newKey] = useState(() => `edon-admin-${crypto.randomUUID().replace(/-/g, '')}`)
  const [loading, setLoading]   = useState(false)
  const [revealedKey, setRevealedKey] = useState<{ key: string; label: string } | null>(null)

  const recover = async (e: React.FormEvent) => {
    e.preventDefault(); setLoading(true)
    try {
      await adminRequest('/admin/bootstrap-api-key', secret, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId.trim(), token: newKey, name: `Recovery Key ${new Date().toISOString().slice(0, 10)}`, role: 'admin', plan: 'enterprise' }),
      })
      setRevealedKey({ key: newKey, label: `New admin key for ${tenantId.trim()}` })
      toast('Recovery key provisioned', 'ok')
    } catch (err) { toast(err instanceof Error ? err.message : 'Recovery failed', 'err') }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-lg space-y-5">
      <div className="glass-card p-5 border-amber-500/20 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-amber-400"><KeyRound size={14} /> Emergency Admin Key Recovery</h3>
        <p className="text-xs text-muted-foreground">Provision a fresh admin key for any client using only the bootstrap secret. Every recovery is logged immutably in the admin audit trail.</p>
      </div>
      {revealedKey && <RevealedKeyBanner keyValue={revealedKey.key} label={revealedKey.label} onDismiss={() => setRevealedKey(null)} />}
      <form onSubmit={recover} className="glass-card p-5 space-y-4">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Tenant ID</label>
          <input value={tenantId} onChange={e => setTenantId(e.target.value)} required placeholder="hospital-name"
            className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Key that will be created</label>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-[11px] font-mono break-all bg-muted/30 px-2 py-1.5 rounded border border-border text-muted-foreground select-all">{newKey}</code>
            <CopyButton value={newKey} />
          </div>
          <p className="text-[10px] text-muted-foreground/60 mt-1">Copy this before submitting.</p>
        </div>
        <button type="submit" disabled={loading || !tenantId.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500/20 border border-amber-500/30 text-amber-400 text-sm font-semibold hover:bg-amber-500/30 transition disabled:opacity-50">
          {loading ? <Spinner size={14} /> : <RotateCcw size={14} />}
          {loading ? 'Provisioning…' : 'Provision Recovery Key'}
        </button>
      </form>
    </div>
  )
}

// ── Audit Log Tab ─────────────────────────────────────────────────────────────

function AuditLogTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [total, setTotal]     = useState(0)
  const [loading, setLoading] = useState(true)
  const [filterTenant, setFilterTenant] = useState('')
  const [offset, setOffset]   = useState(0)
  const LIMIT = 50

  const fetchLog = useCallback(async () => {
    setLoading(true)
    try {
      const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
      if (filterTenant.trim()) qs.set('tenant_id', filterTenant.trim())
      const r = await adminRequest<{ entries: AuditEntry[]; total: number }>(`/admin/audit-log?${qs}`, secret)
      setEntries(r.entries || []); setTotal(r.total || 0)
    } catch { toast('Failed to load audit log', 'err') }
    finally { setLoading(false) }
  }, [secret, offset, filterTenant, toast])

  useEffect(() => { fetchLog() }, [fetchLog])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={filterTenant} onChange={e => { setFilterTenant(e.target.value); setOffset(0) }} placeholder="Filter by tenant…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono" />
        </div>
        <button onClick={fetchLog} className="p-2 rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition"><RefreshCcw size={13} /></button>
        <span className="text-xs text-muted-foreground">{total} total · append-only</span>
        <div className="flex items-center gap-1.5 text-xs text-emerald-400">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" /> Immutable
        </div>
      </div>
      {loading ? <div className="flex justify-center py-12"><Spinner size={20} /></div>
        : entries.length === 0 ? <div className="text-center py-12 text-muted-foreground text-sm">No audit entries yet.</div>
        : (
          <>
            <div className="space-y-2">
              {entries.map(e => (
                <div key={e.id} className="glass-card px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                  <span className="text-xs text-muted-foreground/60 shrink-0 tabular-nums w-28">{fmtTime(e.timestamp)}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${ACTION_COLORS[e.action_type] || 'text-muted-foreground bg-muted/30 border-border'}`}>
                    {e.action_type.replace(/_/g, ' ')}
                  </span>
                  {e.tenant_affected && <span className="font-mono text-xs text-primary shrink-0">{e.tenant_affected}</span>}
                  <span className="text-xs text-muted-foreground/50 shrink-0">IP: {e.performed_by_ip}</span>
                  {Object.keys(e.details).length > 0 && (
                    <span className="text-xs text-muted-foreground/50 truncate">
                      {Object.entries(e.details).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                    </span>
                  )}
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between pt-2">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition">← Previous</button>
              <span className="text-xs text-muted-foreground">{offset + 1}–{Math.min(offset + LIMIT, total)} of {total}</span>
              <button disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}
                className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition">Next →</button>
            </div>
          </>
        )}
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

// ── Command Tab (Chief of Staff voice agent) ──────────────────────────────────

const OPENAI_KEY_STORAGE = 'edon_openai_key'
const ANTHROPIC_KEY_STORAGE = 'edon_anthropic_key'
const MULTICA_TOKEN_STORAGE = 'edon_multica_token'
// const GITHUB_TOKEN_STORAGE = 'edon_github_token' // kept for future workflow dispatch

interface Message { id: string; role: 'user' | 'assistant'; text: string; ts: Date }

const AGENTS = [
  { id: 'ef9f0db2-a950-4da5-855e-d93ba5bd368e', name: 'Chief of Staff' },
  { id: '69a47ffe-4946-4d93-9684-a44778e81eb1', name: 'Follow-up Agent' },
  { id: '1207bbe1-7366-4f50-8696-2b10f37719d8', name: 'Content Agent' },
  { id: '452cc1a2-25d9-4b38-afb6-c443bd071213', name: 'Competitor Monitor' },
  { id: 'bb8b01dd-03f1-4941-8835-8a55fc74b4e0', name: 'Ops Agent' },
  { id: 'e741e622-0fe9-45df-9304-30e27235641f', name: 'Security Monitor' },
  { id: '3662f54d-f95b-4394-9157-c8f11e03ed24', name: 'Regulatory Watcher' },
  { id: 'a513778b-c811-485c-8a8e-ded276920838', name: 'Product Intelligence' },
  { id: '2bb1f44d-df03-4bb2-9438-8b68a6229677', name: 'Account Manager' },
  { id: 'fca62eac-b056-4ad4-aeda-6e17a3545ec6', name: 'Incident Agent' },
  { id: 'e5c71521-f2a0-496d-bb33-6b9aff88aa68', name: 'Nightly QA' },
  { id: '4de2c22c-c6fc-4ef8-b850-f27ae81b76ab', name: 'Code Agent' },
  { id: 'a9696685-b394-4375-a3c6-6cb3ead19503', name: 'Integration Agent' },
]

// GitHub workflow dispatch kept for future use
// async function triggerGitHubWorkflow(workflow: string, githubToken: string, inputs: Record<string, string> = {}) { ... }

async function transcribeAudio(blob: Blob, openaiKey: string): Promise<string> {
  const form = new FormData()
  form.append('file', blob, 'audio.webm')
  form.append('model', 'whisper-1')
  const res = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${openaiKey}` },
    body: form,
  })
  if (!res.ok) throw new Error(`Whisper ${res.status}`)
  const data = await res.json() as { text: string }
  return data.text
}

async function chiefOfStaffReason(transcript: string, anthropicKey: string): Promise<string> {
  const system = `You are the Chief of Staff AI for EDON, an AI governance startup. The founder is talking to you directly.
You manage a team of agents through Multica: ${AGENTS.map(a => `${a.name} (id: ${a.id})`).join(', ')}.
All agent tasks are dispatched through Multica. When the founder asks you to delegate, take action, or assign a task — respond with a clear plan and include a JSON block at the end:
{"action": "multica_issue" | "none", "agent": "<agent_id>", "task": "<brief task description>"}
Use "multica_issue" any time an agent should do something. Use "none" only for pure conversation or status questions.
Keep responses concise and direct. You are the founder's right hand.`

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': anthropicKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 1024,
      system,
      messages: [{ role: 'user', content: transcript }],
    }),
  })
  if (!res.ok) throw new Error(`Claude ${res.status}: ${await res.text()}`)
  const data = await res.json() as { content: Array<{ type: string; text: string }> }
  return data.content[0].text
}

async function speakText(text: string, openaiKey: string) {
  // Strip JSON block before speaking
  const clean = text.replace(/\{[\s\S]*?\}/g, '').trim()
  const res = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: { Authorization: `Bearer ${openaiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'tts-1', voice: 'onyx', input: clean, speed: 1.05 }),
  })
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const audio = new Audio(url)
  audio.play()
}

function CommandTab() {
  const [openaiKey, setOpenaiKey]       = useState(() => localStorage.getItem(OPENAI_KEY_STORAGE) || '')
  const [anthropicKey, setAnthropicKey] = useState(() => localStorage.getItem(ANTHROPIC_KEY_STORAGE) || '')
  const [multicaToken, setMulticaToken] = useState(() => localStorage.getItem(MULTICA_TOKEN_STORAGE) || '')
  const [messages, setMessages]         = useState<Message[]>([
    { id: 'welcome', role: 'assistant', text: "Chief of Staff online. Type a task and pick an agent — I'll dispatch it immediately.", ts: new Date() }
  ])
  const [recording, setRecording]       = useState(false)
  const [processing, setProcessing]     = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [textInput, setTextInput]       = useState('')
  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0].id)
  const [showConfig, setShowConfig]     = useState(false)
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const addMessage = (role: 'user' | 'assistant', text: string) =>
    setMessages(prev => [...prev, { id: Date.now().toString(), role, text, ts: new Date() }])

  const dispatchToMultica = async (task: string, agentId: string) => {
    if (!multicaToken) {
      addMessage('assistant', '⚠ Multica token not set — open Config to add it.')
      return
    }
    const agent = AGENTS.find(a => a.id === agentId)
    await fetch('https://edon-multica-api.fly.dev/api/issues', {
      method: 'POST',
      headers: { Authorization: `Bearer ${multicaToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: task, assignee: agentId }),
    })
    addMessage('assistant', `✓ Task sent to ${agent?.name ?? agentId}. The agent will handle it now.`)
  }

  const processInput = async (text: string) => {
    if (!text.trim()) return
    addMessage('user', text)
    setProcessing(true)
    try {
      // If Anthropic key available, use Claude to reason first (enhanced mode)
      if (anthropicKey) {
        const reply = await chiefOfStaffReason(text, anthropicKey)
        addMessage('assistant', reply)
        const match = reply.match(/\{[\s\S]*?\}/)
        if (match) {
          try {
            const action = JSON.parse(match[0]) as { action: string; agent: string; task: string }
            if (action.action === 'multica_issue' && action.agent) {
              await dispatchToMultica(action.task || text, action.agent)
            }
          } catch { /* parse failed — just show reply */ }
        }
        if (voiceEnabled && openaiKey) speakText(reply, openaiKey)
      } else {
        // Direct mode — no API key needed, go straight to Multica
        await dispatchToMultica(text, selectedAgent)
      }
    } catch (e) {
      addMessage('assistant', `Error: ${e instanceof Error ? e.message : 'Something went wrong'}`)
    } finally { setProcessing(false) }
  }

  const startRecording = async () => {
    if (!openaiKey) {
      addMessage('assistant', '⚠ OpenAI key needed for mic — add it in Config, or type your command instead.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = e => chunksRef.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setProcessing(true)
        try {
          const transcript = await transcribeAudio(blob, openaiKey)
          await processInput(transcript)
        } catch (e) {
          addMessage('assistant', `Transcription failed: ${e instanceof Error ? e.message : 'Unknown error'}`)
        } finally { setProcessing(false) }
      }
      mr.start()
      setMediaRecorder(mr)
      setRecording(true)
    } catch { addMessage('assistant', 'Microphone access denied.') }
  }

  const stopRecording = () => {
    mediaRecorder?.stop()
    setMediaRecorder(null)
    setRecording(false)
  }

  const saveConfig = () => {
    localStorage.setItem(OPENAI_KEY_STORAGE, openaiKey)
    localStorage.setItem(ANTHROPIC_KEY_STORAGE, anthropicKey)
    localStorage.setItem(MULTICA_TOKEN_STORAGE, multicaToken)
    setShowConfig(false)
  }

  const configured = !!multicaToken

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
            <Bot size={18} className="text-emerald-400" />
          </div>
          <div>
            <h2 className="font-semibold text-sm">Chief of Staff</h2>
            <p className="text-[10px] text-muted-foreground">{anthropicKey ? 'Claude · Enhanced mode' : 'Direct mode'} · Multica dispatch</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setVoiceEnabled(v => !v)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${voiceEnabled ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' : 'border-border text-muted-foreground'}`}>
            {voiceEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
            {voiceEnabled ? 'Voice on' : 'Voice off'}
          </button>
          <button onClick={() => setShowConfig(v => !v)}
            className="text-xs px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors">
            {configured ? '⚙ Config' : '⚠ Setup'}
          </button>
        </div>
      </div>

      {/* Config panel */}
      <AnimatePresence>
        {showConfig && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="mb-4 rounded-xl border border-border bg-black/30 p-4 space-y-3 overflow-hidden">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Config</h3>
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Multica Token <span className="text-primary font-semibold">required</span></label>
              <input type="password" value={multicaToken} onChange={e => setMulticaToken(e.target.value)}
                placeholder="multica_..." className="w-full text-xs bg-muted/30 border border-border rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-1 focus:ring-primary/40" />
            </div>
            <p className="text-[10px] text-muted-foreground/50">Optional — unlock Claude reasoning + voice:</p>
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Anthropic API Key (Claude enhanced mode)</label>
              <input type="password" value={anthropicKey} onChange={e => setAnthropicKey(e.target.value)}
                placeholder="sk-ant-..." className="w-full text-xs bg-muted/30 border border-border rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-1 focus:ring-primary/40" />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">OpenAI API Key (mic + voice)</label>
              <input type="password" value={openaiKey} onChange={e => setOpenaiKey(e.target.value)}
                placeholder="sk-..." className="w-full text-xs bg-muted/30 border border-border rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-1 focus:ring-primary/40" />
            </div>
            <button onClick={saveConfig} className="text-xs px-4 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary font-semibold hover:bg-primary/30 transition-colors">
              Save
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Agent selector — only shown in direct mode (no Anthropic key) */}
      {!anthropicKey && (
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[10px] text-muted-foreground shrink-0">Assign to:</span>
          <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)}
            className="flex-1 text-xs bg-muted/30 border border-border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary/40 text-foreground">
            {AGENTS.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
        {messages.map(m => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-primary/20 border border-primary/30 text-foreground'
                : 'bg-muted/30 border border-border text-foreground'
            }`}>
              {m.text.replace(/\{[\s\S]*?\}/g, '').trim()}
              <div className="text-[9px] text-muted-foreground/40 mt-1 text-right">
                {m.ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}
        {processing && (
          <div className="flex justify-start">
            <div className="bg-muted/30 border border-border rounded-2xl px-4 py-2.5">
              <Loader2 size={14} className="animate-spin text-muted-foreground" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="flex gap-2 items-center">
        <button
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onTouchStart={startRecording}
          onTouchEnd={stopRecording}
          disabled={processing}
          className={`shrink-0 w-12 h-12 rounded-2xl border flex items-center justify-center transition-all ${
            recording
              ? 'bg-red-500/20 border-red-500/50 text-red-400 scale-110 shadow-[0_0_20px_rgba(239,68,68,0.3)]'
              : 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/20'
          } disabled:opacity-50`}>
          {recording ? <MicOff size={18} /> : <Mic size={18} />}
        </button>
        <input
          type="text"
          value={textInput}
          onChange={e => setTextInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); processInput(textInput); setTextInput('') } }}
          placeholder={recording ? 'Recording… release to send' : 'Or type a command…'}
          disabled={recording || processing}
          className="flex-1 text-sm bg-muted/30 border border-border rounded-2xl px-4 py-3 focus:outline-none focus:ring-1 focus:ring-primary/40 placeholder:text-muted-foreground/40 disabled:opacity-50"
        />
        <button
          onClick={() => { processInput(textInput); setTextInput('') }}
          disabled={!textInput.trim() || processing || recording}
          className="shrink-0 w-12 h-12 rounded-2xl border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 flex items-center justify-center transition-colors disabled:opacity-50">
          <Send size={16} />
        </button>
      </div>
      <p className="text-center text-[10px] text-muted-foreground/40 mt-2">Hold mic to speak · Release to send · Or type below</p>
    </div>
  )
}

const TABS = [
  { id: 'command',  label: 'Command',   icon: Mic         },
  { id: 'overview', label: 'Overview',  icon: Activity    },
  { id: 'scale',    label: 'Scale',     icon: Trophy      },
  { id: 'clients',  label: 'Clients',   icon: Building2   },
  { id: 'billing',  label: 'Billing',   icon: DollarSign  },
  { id: 'usage',    label: 'Usage',     icon: BarChart2   },
  { id: 'ip',       label: 'IP Rules',  icon: Globe       },
  { id: 'flags',    label: 'Features',  icon: Server      },
  { id: 'supkeys',  label: 'Sup. Keys', icon: UserCheck   },
  { id: 'recovery', label: 'Recovery',  icon: KeyRound    },
  { id: 'audit',    label: 'Audit Log', icon: ScrollText  },
] as const

type Tab = typeof TABS[number]['id']

interface UsageRow { tenant_id: string; total_decisions: number; allowed: number; blocked: number; unique_agents: number; last_event?: string }

function UsageTab({ secret, toast }: { secret: string; toast: (m: string, t: 'ok' | 'err') => void }) {
  const [data, setData]         = useState<{ totals: { decisions: number; allowed: number; blocked: number; tenants_active: number }; by_tenant: UsageRow[] } | null>(null)
  const [period, setPeriod]     = useState(30)
  const [loading, setLoading]   = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await adminRequest<{ period_days: number; totals: UsageRow; by_tenant: UsageRow[] }>(`/admin/usage?period=${period}`, secret)
      setData(r as never)
    } catch { toast('Failed to load usage data', 'err') }
    finally { setLoading(false) }
  }, [secret, period, toast])

  useEffect(() => { load() }, [load])

  const maxDecisions = Math.max(1, ...(data?.by_tenant.map(r => r.total_decisions) || []))

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold flex items-center gap-2"><BarChart2 size={13} className="text-primary" /> Usage Analytics</h2>
        <div className="flex rounded-lg border border-border overflow-hidden text-xs ml-auto">
          {[7, 30, 90].map(d => (
            <button key={d} onClick={() => setPeriod(d)}
              className={`px-3 py-1.5 transition ${period === d ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
              {d}d
            </button>
          ))}
        </div>
        <button onClick={load} className="p-2 rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition"><RefreshCcw size={13} /></button>
      </div>

      {loading ? <div className="flex justify-center py-12"><Spinner size={20} /></div> : !data ? null : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Total Decisions',  value: data.totals.decisions,       color: 'text-foreground'  },
              { label: 'Allowed',          value: data.totals.allowed,         color: 'text-emerald-400' },
              { label: 'Blocked',          value: data.totals.blocked,         color: 'text-red-400'     },
              { label: 'Active Tenants',   value: data.totals.tenants_active,  color: 'text-blue-400'    },
            ].map(c => (
              <div key={c.label} className="glass-card p-4 space-y-2">
                <span className="text-xs text-muted-foreground">{c.label}</span>
                <p className={`text-2xl font-bold ${c.color}`}>{c.value ?? 0}</p>
                <p className="text-[11px] text-muted-foreground/60">last {period} days</p>
              </div>
            ))}
          </div>

          <div className="glass-card p-5 space-y-3">
            <h3 className="text-sm font-semibold">Per-Tenant Breakdown</h3>
            {data.by_tenant.length === 0 ? (
              <p className="text-center py-6 text-muted-foreground text-sm">No decisions in the last {period} days.</p>
            ) : (
              data.by_tenant.map(row => {
                const pct = (row.total_decisions / maxDecisions) * 100
                const blockRate = row.total_decisions > 0 ? Math.round((row.blocked / row.total_decisions) * 100) : 0
                return (
                  <div key={row.tenant_id} className="space-y-1">
                    <div className="flex items-center gap-3 text-xs">
                      <span className="font-mono font-medium w-40 truncate">{row.tenant_id}</span>
                      <div className="flex-1 h-2 rounded-full bg-muted/40 overflow-hidden">
                        <motion.div className="h-full rounded-full bg-primary/60"
                          initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6, ease: 'easeOut' }} />
                      </div>
                      <span className="w-16 text-right tabular-nums font-medium">{row.total_decisions.toLocaleString()}</span>
                      <span className="w-10 text-right text-muted-foreground/60">{row.unique_agents}ag</span>
                      <span className={`w-14 text-right ${blockRate > 10 ? 'text-red-400' : 'text-muted-foreground/50'}`}>{blockRate}% blk</span>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default function App() {
  const [secret, setSecret]   = useState('')
  const [tab, setTab]         = useState<Tab>('command')
  const [toastData, setToastData] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  const toast = useCallback((msg: string, type: 'ok' | 'err') => setToastData({ msg, type }), [])
  const handleLogout = () => { clearSecret(); setSecret('') }

  if (!secret) return <AccessGate onUnlock={setSecret} />

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border/40 bg-background/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 flex items-center gap-4 h-14">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Shield size={14} className="text-primary" />
            </div>
            <span className="text-sm font-bold tracking-widest" style={{ color: 'hsl(38 95% 55%)' }}>EDON</span>
            <span className="text-xs text-muted-foreground px-1.5 py-0.5 rounded border border-border bg-muted/40">ADMIN</span>
          </div>

          <nav className="flex items-center gap-0.5 px-1 py-0.5 rounded-xl bg-muted/40 border border-border/40 overflow-x-auto">
            {TABS.map(t => {
              const Icon = t.icon
              const isActive = tab === t.id
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`relative nav-item flex items-center gap-1.5 px-2.5 h-8 text-xs font-medium rounded-lg shrink-0 ${isActive ? 'text-primary font-semibold' : ''}`}>
                  {isActive && (
                    <motion.div layoutId="nav-pill" className="absolute inset-0 rounded-lg"
                      style={{ background: 'hsl(38 95% 55% / 0.12)', border: '1px solid hsl(38 95% 55% / 0.25)' }}
                      transition={{ type: 'spring', stiffness: 400, damping: 32 }} />
                  )}
                  <Icon size={12} className="relative z-10" />
                  <span className="hidden lg:inline relative z-10">{t.label}</span>
                </button>
              )
            })}
          </nav>

          <div className="flex items-center gap-3 ml-auto shrink-0">
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
              <span>{GATEWAY.replace('https://', '')}</span>
            </div>
            <button onClick={handleLogout} title="Disconnect"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            {tab === 'command'  && <CommandTab />}
            {tab === 'overview' && <OverviewTab secret={secret} toast={toast} />}
            {tab === 'scale'    && <ScaleTab    secret={secret} toast={toast} />}
            {tab === 'clients'  && <ClientsTab  secret={secret} toast={toast} />}
            {tab === 'billing'  && <BillingTab  secret={secret} toast={toast} />}
            {tab === 'usage'    && <UsageTab    secret={secret} toast={toast} />}
            {tab === 'ip'       && <IPAllowlistTab secret={secret} toast={toast} />}
            {tab === 'flags'    && <FeatureFlagsTab secret={secret} toast={toast} />}
            {tab === 'supkeys'  && <SupportKeysTab  secret={secret} toast={toast} />}
            {tab === 'recovery' && <RecoveryTab  secret={secret} toast={toast} />}
            {tab === 'audit'    && <AuditLogTab  secret={secret} toast={toast} />}
          </motion.div>
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {toastData && <Toast msg={toastData.msg} type={toastData.type} onClose={() => setToastData(null)} />}
      </AnimatePresence>
    </div>
  )
}
