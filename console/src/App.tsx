import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield, Activity, FileText, Users, ClipboardList,
  CheckCircle2, XCircle, AlertTriangle, RefreshCcw,
  Sun, Moon, LogOut, AlertCircle, ChevronRight,
  Lock, ToggleLeft, ToggleRight, Search,
  Heart, Zap, Database, Clock,
} from 'lucide-react'
import { api, type AuditEvent, type Agent, type PolicyRule, type TimeseriesPoint, type ComplianceHealth } from './api'

// ── Auth ──────────────────────────────────────────────────────────────────────

function saveAuth(gatewayUrl: string, token: string) {
  localStorage.setItem('edon_auth', JSON.stringify({ gatewayUrl, token }))
}
function clearAuth() {
  localStorage.removeItem('edon_auth')
}
function getAuth() {
  const raw = localStorage.getItem('edon_auth')
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict?.toUpperCase()
  if (v === 'ALLOW') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
      <CheckCircle2 size={10} /> ALLOW
    </span>
  )
  if (v === 'BLOCK') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/20">
      <XCircle size={10} /> BLOCK
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/20">
      <AlertTriangle size={10} /> {v || 'UNKNOWN'}
    </span>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
    </div>
  )
}

function Empty({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
      <Database size={32} className="opacity-30" />
      <p className="text-sm">{message}</p>
    </div>
  )
}

function ErrorMsg({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <AlertCircle size={32} className="text-destructive opacity-60" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-primary hover:underline flex items-center gap-1">
          <RefreshCcw size={12} /> Retry
        </button>
      )}
    </div>
  )
}

function fmtTs(ts: string) {
  try { return new Date(ts).toLocaleString() } catch { return ts }
}

// ── Login Screen ──────────────────────────────────────────────────────────────

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [url, setUrl] = useState('https://edon-gateway-prod.fly.dev')
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    saveAuth(url.replace(/\/$/, ''), token.trim())
    try {
      await api.health()
      onLogin()
    } catch (err) {
      clearAuth()
      setError(err instanceof Error ? err.message : 'Connection failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-8 w-full max-w-md"
      >
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Shield size={20} className="text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold edon-brand tracking-widest">EDON</h1>
            <p className="text-xs text-muted-foreground">Tenant Console</p>
          </div>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Gateway URL</label>
            <input
              type="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="https://edon-gateway-prod.fly.dev"
              required
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">API Token</label>
            <input
              type="password"
              value={token}
              onChange={e => setToken(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono"
              placeholder="Your X-EDON-TOKEN"
              required
            />
          </div>
          {error && (
            <p className="text-xs text-destructive flex items-center gap-1">
              <AlertCircle size={12} /> {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Shield size={14} />}
            {loading ? 'Connecting…' : 'Connect to Gateway'}
          </button>
        </form>
      </motion.div>
    </div>
  )
}

// ── Dashboard Tab ─────────────────────────────────────────────────────────────

function DashboardTab() {
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [recent, setRecent] = useState<AuditEvent[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [ts, rec, h] = await Promise.all([
        api.timeseries(7),
        api.auditQuery({ limit: 20 }),
        api.complianceHealth(),
      ])
      setTimeseries(ts)
      setRecent(rec.events)
      setHealth(h)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const totals = timeseries.reduce(
    (acc, p) => ({ allow: acc.allow + p.allowed, block: acc.block + p.blocked, confirm: acc.confirm + p.confirm }),
    { allow: 0, block: 0, confirm: 0 }
  )
  const total = totals.allow + totals.block + totals.confirm

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Decisions', value: total, icon: Activity, color: 'text-blue-400' },
          { label: 'Allowed', value: totals.allow, icon: CheckCircle2, color: 'text-emerald-400' },
          { label: 'Blocked', value: totals.block, icon: XCircle, color: 'text-red-400' },
          { label: 'Escalated', value: totals.confirm, icon: AlertTriangle, color: 'text-amber-400' },
        ].map(s => (
          <div key={s.label} className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <s.icon size={16} className={s.color} />
            </div>
            <p className="text-2xl font-semibold">{s.value.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground mt-1">last 7 days</p>
          </div>
        ))}
      </div>

      {/* Compliance status */}
      {health && (
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <Heart size={14} className="text-primary" /> Compliance Health
            </h3>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              health.overall === 'pass'
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-red-500/15 text-red-400'
            }`}>
              {health.overall.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {Object.entries(health.regulations).map(([key, reg]) => (
              <div key={key} className={`p-2 rounded-lg border text-xs ${
                reg.status === 'pass'
                  ? 'border-emerald-500/20 bg-emerald-500/5'
                  : 'border-red-500/20 bg-red-500/5'
              }`}>
                <div className="flex items-center gap-1 mb-1">
                  {reg.status === 'pass'
                    ? <CheckCircle2 size={10} className="text-emerald-400" />
                    : <XCircle size={10} className="text-red-400" />
                  }
                  <span className="font-medium">{key}</span>
                </div>
                <p className="text-muted-foreground">{reg.rules_active}/{reg.rules_required} rules</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeseries bars */}
      {timeseries.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <Activity size={14} className="text-primary" /> Decision Volume (7 days)
          </h3>
          <div className="flex items-end gap-1 h-24">
            {timeseries.map(p => {
              const max = Math.max(...timeseries.map(x => x.allowed + x.blocked + x.confirm), 1)
              const h = ((p.allowed + p.blocked + p.confirm) / max) * 100
              return (
                <div key={p.label} className="flex-1 flex flex-col items-center gap-1" title={`${p.label}: ${p.allowed + p.blocked + p.confirm} decisions`}>
                  <div className="w-full rounded-t" style={{ height: `${Math.max(h, 4)}%`, background: 'hsl(var(--primary) / 0.6)' }} />
                  <span className="text-[10px] text-muted-foreground">{p.label.slice(5)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Recent decisions */}
      <div className="glass-card p-4">
        <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
          <Clock size={14} className="text-primary" /> Recent Decisions
        </h3>
        {recent.length === 0
          ? <Empty message="No decisions recorded yet" />
          : (
            <div className="space-y-2">
              {recent.map((e, i) => (
                <div key={e.action_id || e.id || i} className="flex items-center gap-3 py-2 border-b border-border/50 last:border-0 text-sm">
                  <VerdictBadge verdict={e.decision_verdict} />
                  <span className="text-muted-foreground font-mono text-xs flex-1 truncate">{e.agent_id}</span>
                  <span className="text-xs text-muted-foreground">{e.tool_name || '—'}</span>
                  <span className="text-xs text-muted-foreground">{fmtTs(e.timestamp)}</span>
                </div>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}

// ── Agents Tab ────────────────────────────────────────────────────────────────

function AgentsTab() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.agents()
      const list = Array.isArray(res)
        ? res
        : (res as { agents?: Agent[]; items?: Agent[] }).agents
          || (res as { agents?: Agent[]; items?: Agent[] }).items
          || []
      setAgents(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = agents.filter(a =>
    !search || (a.agent_id + (a.name || '') + (a.agent_type || '')).toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search agents…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} agents</span>
        <button onClick={load} className="ml-auto text-muted-foreground hover:text-foreground transition">
          <RefreshCcw size={14} />
        </button>
      </div>

      {filtered.length === 0
        ? <Empty message="No agents registered yet" />
        : (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map(a => (
              <div key={a.agent_id} className="glass-card-hover p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <p className="text-sm font-medium">{a.name || a.agent_id}</p>
                    <p className="text-xs text-muted-foreground font-mono">{a.agent_id}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    a.status === 'active' ? 'bg-emerald-500/15 text-emerald-400'
                    : a.status === 'paused' ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-muted text-muted-foreground'
                  }`}>
                    {a.status || 'unknown'}
                  </span>
                </div>
                {a.agent_type && <p className="text-xs text-muted-foreground mb-2">{a.agent_type}</p>}
                {a.description && <p className="text-xs text-muted-foreground line-clamp-2">{a.description}</p>}
                <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
                  {a.decisions_total != null && <span>{a.decisions_total} decisions</span>}
                  {a.policy_pack && <span className="text-primary">{a.policy_pack}</span>}
                </div>
              </div>
            ))}
          </div>
        )
      }
    </div>
  )
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

function AuditTab() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [verdict, setVerdict] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AuditEvent | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.auditQuery({ verdict: verdict || undefined, limit: 200 })
      setEvents(res.events)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }, [verdict])

  useEffect(() => { load() }, [load])

  const filtered = events.filter(e =>
    !search || (e.agent_id + (e.tool_name || '') + (e.decision_reason_code || '')).toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            className="pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary w-48"
          />
        </div>
        <select
          value={verdict}
          onChange={e => setVerdict(e.target.value)}
          className="py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">All verdicts</option>
          <option value="ALLOW">ALLOW</option>
          <option value="BLOCK">BLOCK</option>
          <option value="ESCALATE">ESCALATE</option>
        </select>
        <span className="text-xs text-muted-foreground">{filtered.length} events</span>
        <button onClick={load} className="ml-auto text-muted-foreground hover:text-foreground transition">
          <RefreshCcw size={14} />
        </button>
      </div>

      {loading ? <Spinner /> : error ? <ErrorMsg message={error} onRetry={load} /> : filtered.length === 0 ? (
        <Empty message="No audit events found" />
      ) : (
        <div className="glass-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-xs text-muted-foreground">
                <th className="text-left py-3 px-4">Verdict</th>
                <th className="text-left py-3 px-4">Agent</th>
                <th className="text-left py-3 px-4 hidden md:table-cell">Tool</th>
                <th className="text-left py-3 px-4 hidden lg:table-cell">Reason</th>
                <th className="text-left py-3 px-4">Timestamp</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <tr
                  key={e.action_id || e.id || i}
                  className="border-b border-border/30 last:border-0 hover:bg-muted/20 cursor-pointer transition-colors"
                  onClick={() => setSelected(e)}
                >
                  <td className="py-2.5 px-4"><VerdictBadge verdict={e.decision_verdict} /></td>
                  <td className="py-2.5 px-4 font-mono text-xs truncate max-w-[150px]">{e.agent_id}</td>
                  <td className="py-2.5 px-4 text-muted-foreground hidden md:table-cell">{e.tool_name || '—'}</td>
                  <td className="py-2.5 px-4 text-muted-foreground hidden lg:table-cell text-xs">{e.decision_reason_code || '—'}</td>
                  <td className="py-2.5 px-4 text-muted-foreground text-xs">{fmtTs(e.timestamp)}</td>
                  <td className="py-2.5 px-4"><ChevronRight size={14} className="text-muted-foreground" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail drawer */}
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex justify-end"
            onClick={() => setSelected(null)}
          >
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="w-full max-w-md bg-card border-l border-border h-full overflow-y-auto p-6"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-semibold">Decision Detail</h3>
                <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground">✕</button>
              </div>
              <div className="space-y-4 text-sm">
                <div className="flex items-center gap-2">
                  <VerdictBadge verdict={selected.decision_verdict} />
                </div>
                {[
                  ['Action ID', selected.action_id || selected.id],
                  ['Agent', selected.agent_id],
                  ['Tool', selected.tool_name],
                  ['Reason Code', selected.decision_reason_code],
                  ['Risk Score', selected.risk_score],
                  ['Policy Version', selected.policy_version],
                  ['Timestamp', fmtTs(selected.timestamp)],
                ].map(([label, value]) => value != null && (
                  <div key={String(label)}>
                    <p className="text-xs text-muted-foreground mb-1">{label}</p>
                    <p className="font-mono text-xs break-all">{String(value)}</p>
                  </div>
                ))}
                {selected.explanation && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Explanation</p>
                    <p className="text-xs leading-relaxed">{selected.explanation}</p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Policies Tab ──────────────────────────────────────────────────────────────

function PoliciesTab() {
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toggling, setToggling] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.policyRules()
      const list = Array.isArray(res) ? res : (res as { rules: PolicyRule[] }).rules || []
      setRules(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load policies')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function toggleRule(rule: PolicyRule) {
    setToggling(rule.rule_id)
    try {
      if (rule.enabled) {
        await api.disableRule(rule.rule_id)
      } else {
        await api.enableRule(rule.rule_id)
      }
      setRules(prev => prev.map(r => r.rule_id === rule.rule_id ? { ...r, enabled: !r.enabled } : r))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to toggle rule')
    } finally {
      setToggling(null)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const grouped = rules.reduce<Record<string, PolicyRule[]>>((acc, r) => {
    const key = r.regulation || 'General'
    if (!acc[key]) acc[key] = []
    acc[key].push(r)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      {Object.keys(grouped).length === 0
        ? <Empty message="No policy rules configured" />
        : Object.entries(grouped).map(([reg, regRules]) => (
          <div key={reg} className="glass-card p-4">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
              <Lock size={14} className="text-primary" /> {reg}
              <span className="text-xs text-muted-foreground ml-auto">{regRules.filter(r => r.enabled).length}/{regRules.length} active</span>
            </h3>
            <div className="space-y-2">
              {regRules.map(rule => (
                <div key={rule.rule_id} className="flex items-center gap-3 py-2 border-b border-border/30 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{rule.name}</p>
                    {rule.description && <p className="text-xs text-muted-foreground truncate">{rule.description}</p>}
                    <p className="text-xs font-mono text-muted-foreground mt-0.5">{rule.rule_id}</p>
                  </div>
                  <button
                    onClick={() => toggleRule(rule)}
                    disabled={toggling === rule.rule_id}
                    className="flex items-center gap-1.5 text-xs transition-colors disabled:opacity-50"
                  >
                    {toggling === rule.rule_id
                      ? <div className="w-4 h-4 border border-primary/30 border-t-primary rounded-full animate-spin" />
                      : rule.enabled
                        ? <ToggleRight size={20} className="text-primary" />
                        : <ToggleLeft size={20} className="text-muted-foreground" />
                    }
                    <span className={rule.enabled ? 'text-primary' : 'text-muted-foreground'}>
                      {rule.enabled ? 'On' : 'Off'}
                    </span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))
      }
    </div>
  )
}

// ── Review Queue Tab ──────────────────────────────────────────────────────────

function ReviewTab() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.auditQuery({ verdict: 'ESCALATE', limit: 100 })
      setEvents(res.events)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load review queue')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClipboardList size={16} className="text-amber-400" />
          <span className="text-sm font-medium">Escalated Decisions</span>
          {events.length > 0 && (
            <span className="px-2 py-0.5 rounded-full text-xs bg-amber-500/15 text-amber-400 border border-amber-500/20">
              {events.length} pending
            </span>
          )}
        </div>
        <button onClick={load} className="text-muted-foreground hover:text-foreground transition">
          <RefreshCcw size={14} />
        </button>
      </div>

      {events.length === 0
        ? <Empty message="No escalated decisions — queue is clear" />
        : (
          <div className="space-y-3">
            {events.map((e, i) => (
              <div key={e.action_id || e.id || i} className="glass-card p-4">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle size={14} className="text-amber-400" />
                      <span className="text-sm font-medium font-mono">{e.agent_id}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{e.tool_name || 'Unknown operation'}</p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{fmtTs(e.timestamp)}</span>
                </div>
                {e.decision_reason_code && (
                  <p className="text-xs text-amber-400/80 mb-2">Reason: {e.decision_reason_code}</p>
                )}
                {e.explanation && (
                  <p className="text-xs text-muted-foreground leading-relaxed">{e.explanation}</p>
                )}
              </div>
            ))}
          </div>
        )
      }
    </div>
  )
}

// ── Top Navigation ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: Activity },
  { id: 'agents',    label: 'Agents',    icon: Users },
  { id: 'audit',     label: 'Audit',     icon: FileText },
  { id: 'policies',  label: 'Policies',  icon: Shield },
  { id: 'review',    label: 'Review',    icon: ClipboardList },
] as const

type Tab = typeof TABS[number]['id']

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [authed, setAuthed] = useState(!!getAuth())
  const [tab, setTab] = useState<Tab>('dashboard')
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    (localStorage.getItem('edon_theme') as 'dark' | 'light') || 'dark'
  )
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number } | null>(null)

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('edon_theme', theme)
  }, [theme])

  useEffect(() => {
    if (!authed) return
    api.health().then(h => setHealth(h)).catch(() => {})
  }, [authed])

  function handleLogout() {
    clearAuth()
    setAuthed(false)
    setHealth(null)
  }

  if (!authed) return <LoginScreen onLogin={() => setAuthed(true)} />

  const auth = getAuth()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 flex items-center gap-4 h-14">
          <div className="flex items-center gap-2 mr-4">
            <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Shield size={14} className="text-primary" />
            </div>
            <span className="text-sm font-semibold edon-brand tracking-widest">EDON</span>
            <span className="text-xs text-muted-foreground hidden sm:block">Console</span>
          </div>

          <nav className="flex items-center gap-1 flex-1 overflow-x-auto">
            {TABS.map(t => {
              const Icon = t.icon
              const active = tab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`nav-item flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${active ? 'nav-item-active' : ''}`}
                >
                  <Icon size={13} />
                  {t.label}
                </button>
              )
            })}
          </nav>

          <div className="flex items-center gap-2 ml-auto shrink-0">
            {health && (
              <div className="hidden md:flex items-center gap-1.5 text-xs text-muted-foreground">
                <div className={`w-1.5 h-1.5 rounded-full animate-pulse-dot ${health.ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span>{health.ok ? 'Healthy' : 'Degraded'}</span>
                <span className="text-border">·</span>
                <span>v{health.version}</span>
              </div>
            )}
            {auth && (
              <span className="hidden lg:block text-xs text-muted-foreground truncate max-w-[200px]">
                {auth.gatewayUrl.replace('https://', '')}
              </span>
            )}
            <button
              onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition"
            >
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition"
              title="Disconnect"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
          >
            {tab === 'dashboard' && <DashboardTab />}
            {tab === 'agents'    && <AgentsTab />}
            {tab === 'audit'     && <AuditTab />}
            {tab === 'policies'  && <PoliciesTab />}
            {tab === 'review'    && <ReviewTab />}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/30 py-3 px-4 text-center">
        <p className="text-xs text-muted-foreground flex items-center justify-center gap-1.5">
          <Zap size={10} className="text-primary" />
          EDON Governance Console
          <span className="text-border">·</span>
          <span className="font-mono">{auth?.gatewayUrl?.replace('https://', '')}</span>
        </p>
      </footer>
    </div>
  )
}
