import { useState, useEffect, useCallback, useRef, Component, type ReactNode, type ErrorInfo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Shield, Activity, FileText, Users, ClipboardList,
  CheckCircle2, XCircle, AlertTriangle, RefreshCcw,
  Sun, Moon, LogOut, AlertCircle, ChevronRight,
  Lock, Search,
  Heart, Zap, Database, Clock, Bot, X, Send,
  ThumbsUp, ThumbsDown, Power, KeyRound, Eye, EyeOff,
  TimerOff, Filter, TrendingUp, Minus, ShieldAlert,
  ListChecks, FileDown, Bell, Settings, Menu, User,
  BarChart2, Wifi, WifiOff, Copy, Check, RefreshCw, Plus, Trash2, Link, Package, FlaskConical,
} from 'lucide-react'
import { api, type AuditEvent, type Agent, type PolicyRule, type TimeseriesPoint, type ComplianceHealth, type ReviewItem, type BlockReason, type MeResponse } from './api'

// ── Error Boundary ────────────────────────────────────────────────────────────

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null }
  static getDerivedStateFromError(e: Error) { return { error: e.message } }
  componentDidCatch(e: Error, info: ErrorInfo) { console.error('EDON Console error:', e, info) }
  render() {
    if (this.state.error) return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center px-4">
        <AlertCircle size={32} className="text-destructive opacity-60" />
        <p className="text-sm font-medium">Something went wrong</p>
        <p className="text-xs text-muted-foreground max-w-xs">{this.state.error}</p>
        <button onClick={() => this.setState({ error: null })}
          className="text-xs text-primary hover:underline flex items-center gap-1">
          <RefreshCcw size={12} /> Try again
        </button>
      </div>
    )
    return this.props.children
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

function saveAuth(gatewayUrl: string, token: string) {
  localStorage.setItem('edon_auth', JSON.stringify({ gatewayUrl, token }))
}
function clearAuth() {
  localStorage.removeItem('edon_auth')
  localStorage.removeItem('edon_reviewer_name')
  localStorage.removeItem('edon_reviewer_dept')
}
function getAuth() {
  const raw = localStorage.getItem('edon_auth')
  if (!raw) return null
  try { return JSON.parse(raw) as { gatewayUrl: string; token: string } } catch { return null }
}

// ── Session timeout ───────────────────────────────────────────────────────────

const SESSION_TIMEOUT_MS = 15 * 60 * 1000  // 15 min
const SESSION_WARN_MS    = 13 * 60 * 1000  // warn at 13 min
const ACTIVITY_EVENTS    = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'click'] as const

function useSessionTimeout(onTimeout: () => void) {
  const lastActivity = useRef(Date.now())
  const [warning, setWarning] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)

  useEffect(() => {
    const reset = () => { lastActivity.current = Date.now(); setWarning(false) }
    ACTIVITY_EVENTS.forEach(ev => document.addEventListener(ev, reset, { passive: true }))
    return () => ACTIVITY_EVENTS.forEach(ev => document.removeEventListener(ev, reset))
  }, [])

  useEffect(() => {
    const iv = setInterval(() => {
      if (!getAuth()) return
      const idle = Date.now() - lastActivity.current
      if (idle >= SESSION_TIMEOUT_MS) { clearInterval(iv); onTimeout(); return }
      if (idle >= SESSION_WARN_MS) {
        setSecondsLeft(Math.ceil((SESSION_TIMEOUT_MS - idle) / 1000))
        setWarning(true)
      } else { setWarning(false) }
    }, 10_000)
    return () => clearInterval(iv)
  }, [onTimeout])

  const extend = () => { lastActivity.current = Date.now(); setWarning(false) }
  return { warning, secondsLeft, extend }
}

// ── PIN helpers ───────────────────────────────────────────────────────────────

const PIN_KEY = 'edon_console_pin_hash'

async function sha256hex(str: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}
async function checkPin(pin: string) {
  const stored = localStorage.getItem(PIN_KEY)
  if (!stored) return false
  return (await sha256hex(pin)) === stored
}
async function savePin(pin: string) { localStorage.setItem(PIN_KEY, await sha256hex(pin)) }
const hasPinSet = () => !!localStorage.getItem(PIN_KEY)

// ── Reviewer name ─────────────────────────────────────────────────────────────

const REVIEWER_KEY = 'edon_reviewer_name'
const getReviewerName = () => localStorage.getItem(REVIEWER_KEY) || ''
const setReviewerName = (name: string) => localStorage.setItem(REVIEWER_KEY, name)

const DEPT_KEY = 'edon_reviewer_dept'
const getReviewerDept = () => localStorage.getItem(DEPT_KEY) || ''
const setReviewerDept = (dept: string) => localStorage.setItem(DEPT_KEY, dept)

const DEPARTMENTS: Record<string, string[]> = {
  'Clinical': [
    'Anesthesiology', 'Cardiology', 'Cardiothoracic Surgery', 'Dermatology',
    'Emergency Medicine', 'Endocrinology', 'Gastroenterology', 'General Surgery',
    'Geriatrics', 'Hematology', 'Infectious Disease', 'Intensive Care Unit (ICU)',
    'Internal Medicine', 'Neonatology', 'Nephrology', 'Neurology', 'Neurosurgery',
    'Obstetrics & Gynecology', 'Oncology', 'Ophthalmology', 'Oral & Maxillofacial Surgery',
    'Orthopedics', 'Otolaryngology (ENT)', 'Pathology', 'Pediatrics',
    'Plastic & Reconstructive Surgery', 'Psychiatry', 'Pulmonology', 'Radiology',
    'Rehabilitation Medicine', 'Rheumatology', 'Sports Medicine', 'Transplant Surgery',
    'Trauma Surgery', 'Urology', 'Vascular Surgery',
  ],
  'Allied Health': [
    'Dietetics & Nutrition', 'Medical Laboratory', 'Medical Imaging',
    'Occupational Therapy', 'Pharmacy', 'Physical Therapy',
    'Respiratory Therapy', 'Speech & Language Therapy', 'Social Work',
  ],
  'Nursing': [
    'Critical Care Nursing', 'Emergency Nursing', 'Nurse Practitioner',
    'Nursing Administration', 'Operating Room Nursing', 'Pediatric Nursing',
    'Psychiatric Nursing',
  ],
  'Administration & Operations': [
    'Administration', 'Compliance & Regulatory', 'Finance',
    'Health Information Management', 'Human Resources', 'Legal',
    'Patient Experience', 'Patient Services', 'Quality & Safety',
    'Risk Management', 'Supply Chain',
  ],
  'Technology & Research': [
    'Biomedical Engineering', 'Clinical Informatics', 'Clinical Research',
    'Data Analytics', 'Health IT', 'Information Security',
    'Innovation & AI', 'Medical Education', 'Research & Development',
  ],
}

// ── SLA helpers ───────────────────────────────────────────────────────────────

const SLA_MS: Record<string, number> = {
  critical: 5 * 60 * 1000,
  urgent: 30 * 60 * 1000,
  routine: 4 * 60 * 60 * 1000,
}
const getSlaMs = (u: string) => SLA_MS[u] ?? SLA_MS.routine
const msRemaining = (createdAt: string, urgency: string) =>
  Math.max(0, getSlaMs(urgency) - (Date.now() - new Date(createdAt).getTime()))

function fmtCountdown(ms: number) {
  if (ms <= 0) return '00:00'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

const URGENCY_CFG = {
  critical: { label: 'Critical', dot: 'bg-red-400',   badge: 'bg-red-500/15 text-red-400 border-red-500/25',     warn: 60000 },
  urgent:   { label: 'Urgent',   dot: 'bg-amber-400', badge: 'bg-amber-500/15 text-amber-400 border-amber-500/25', warn: 5*60000 },
  routine:  { label: 'Routine',  dot: 'bg-sky-400',   badge: 'bg-sky-500/15 text-sky-400 border-sky-500/25',     warn: 30*60000 },
} as const

const getUrgency = (item: ReviewItem): 'critical' | 'urgent' | 'routine' => item.meta?.urgency ?? 'routine'
const getDept = (item: ReviewItem) => String(item.meta?.department ?? item.agent_id.split('-')[0] ?? 'Unknown')

// ── Shared helpers ────────────────────────────────────────────────────────────

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
      <Database size={32} className="opacity-30" /><p className="text-sm">{message}</p>
    </div>
  )
}
function ErrorMsg({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <AlertCircle size={32} className="text-destructive opacity-60" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && <button onClick={onRetry} className="text-xs text-primary hover:underline flex items-center gap-1"><RefreshCcw size={12} /> Retry</button>}
    </div>
  )
}
function fmtTs(ts: string) { try { return new Date(ts).toLocaleString() } catch { return ts } }
function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ── SLA Timer ─────────────────────────────────────────────────────────────────

function SlaTimer({ item, onExpired }: { item: ReviewItem; onExpired: (item: ReviewItem) => void }) {
  const urgency = getUrgency(item)
  const cfg = URGENCY_CFG[urgency]
  const [ms, setMs] = useState(() => msRemaining(item.created_at, urgency))
  const fired = useRef(false)

  useEffect(() => {
    if (ms <= 0 && !fired.current) { fired.current = true; onExpired(item); return }
    const iv = setInterval(() => {
      const r = msRemaining(item.created_at, urgency)
      setMs(r)
      if (r <= 0 && !fired.current) { fired.current = true; onExpired(item) }
    }, 1000)
    return () => clearInterval(iv)
  }, [item, urgency, onExpired, ms])

  const isWarn = ms <= cfg.warn && ms > 0
  const expired = ms <= 0
  return (
    <div className={`flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded border ${
      expired ? 'text-red-400 border-red-500/30 bg-red-500/10'
      : isWarn ? 'text-amber-400 border-amber-500/30 bg-amber-500/10'
      : 'text-muted-foreground border-white/10 bg-white/[0.03]'
    }`}>
      {expired ? <><TimerOff size={9} /> Expired</> : <><Clock size={9} />{fmtCountdown(ms)}</>}
    </div>
  )
}

// ── PIN Modal ─────────────────────────────────────────────────────────────────

function PinModal({ mode, onSuccess, onCancel }: { mode: 'verify' | 'setup'; onSuccess: () => void; onCancel: () => void }) {
  const [pin, setPin] = useState(''), [confirm, setConfirm] = useState(''), [show, setShow] = useState(false)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 80) }, [])

  const submit = async () => {
    setError('')
    if (mode === 'setup') {
      if (pin.length < 4) { setError('PIN must be at least 4 characters.'); return }
      if (pin !== confirm) { setError('PINs do not match.'); return }
      setBusy(true); await savePin(pin); setBusy(false); onSuccess(); return
    }
    if (!pin) { setError('Enter your PIN.'); return }
    setBusy(true)
    const ok = await checkPin(pin)
    setBusy(false)
    if (ok) onSuccess(); else { setError('Incorrect PIN.'); setPin(''); inputRef.current?.focus() }
  }

  return (
    <motion.div initial={{ opacity: 0, scale: 0.95, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }} transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
      className="relative z-10 glass-card max-w-sm w-full p-6 space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
          <KeyRound size={16} className="text-primary" />
        </div>
        <div>
          <h3 className="font-semibold">{mode === 'setup' ? 'Set a reviewer PIN' : 'Confirm identity'}</h3>
          <p className="text-xs text-muted-foreground">{mode === 'setup' ? 'Required before signing reviews.' : 'Enter PIN to sign this review.'}</p>
        </div>
      </div>
      <div className="space-y-2">
        <div className="relative">
          <input ref={inputRef} type={show ? 'text' : 'password'} value={pin}
            onChange={e => { setPin(e.target.value); setError('') }}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder={mode === 'setup' ? 'Choose a PIN' : 'Enter PIN'}
            className="w-full bg-white/[0.04] border border-white/15 rounded-xl pl-4 pr-10 py-2.5 text-sm font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-primary/40" />
          <button type="button" onClick={() => setShow(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        {mode === 'setup' && (
          <input type={show ? 'text' : 'password'} value={confirm}
            onChange={e => { setConfirm(e.target.value); setError('') }}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="Confirm PIN"
            className="w-full bg-white/[0.04] border border-white/15 rounded-xl px-4 py-2.5 text-sm font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-primary/40" />
        )}
        {error && <p className="text-xs text-red-400 flex items-center gap-1"><AlertCircle size={11} />{error}</p>}
      </div>
      <div className="flex gap-3">
        <button onClick={onCancel} className="flex-1 py-2 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Cancel</button>
        <button onClick={submit} disabled={busy} className="flex-1 py-2 rounded-xl bg-primary/20 border border-primary/40 text-primary text-sm font-semibold hover:bg-primary/30 disabled:opacity-50 transition-colors">
          {busy ? <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin mx-auto" /> : mode === 'setup' ? 'Set PIN' : 'Confirm'}
        </button>
      </div>
    </motion.div>
  )
}

// ── Notifications Bell ────────────────────────────────────────────────────────

interface Notif { id: string; verdict: string; tool: string; agent_id: string; reason_code: string; timestamp: string }
const NOTIF_SEEN_KEY = 'edon_console_notifs_seen'

function NotificationsBell() {
  const [notifs, setNotifs] = useState<Notif[]>([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const lastSeen = useRef(localStorage.getItem(NOTIF_SEEN_KEY) || new Date(0).toISOString())

  const fetch = useCallback(async () => {
    try {
      const res = await api.auditQuery({ verdict: 'BLOCK', limit: 20 })
      const mapped: Notif[] = res.events.map(e => ({
        id: e.action_id || e.id || Math.random().toString(36).slice(2),
        verdict: e.decision_verdict,
        tool: e.tool_name || '—',
        agent_id: e.agent_id,
        reason_code: e.decision_reason_code || '—',
        timestamp: e.timestamp,
      }))
      setNotifs(mapped)
      setUnread(mapped.filter(n => new Date(n.timestamp) > new Date(lastSeen.current)).length)
    } catch { /* silent */ }
  }, [])

  useEffect(() => { fetch(); const iv = setInterval(fetch, 30000); return () => clearInterval(iv) }, [fetch])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const markRead = () => {
    const now = new Date().toISOString()
    lastSeen.current = now
    localStorage.setItem(NOTIF_SEEN_KEY, now)
    setUnread(0)
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => { setOpen(v => !v); if (!open && unread > 0) markRead() }}
        className="relative flex items-center justify-center w-8 h-8 rounded-xl border border-border bg-secondary hover:bg-muted transition-colors">
        <Bell size={14} className="text-muted-foreground" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }} transition={{ duration: 0.15 }}
            className="absolute right-0 top-10 w-80 rounded-xl border border-border bg-card shadow-2xl z-50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <ShieldAlert size={14} className="text-red-400" />
                <span className="text-sm font-semibold">Blocked Actions</span>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={markRead} className="text-[10px] text-muted-foreground hover:text-foreground">Mark read</button>
                <button onClick={() => setOpen(false)}><X size={13} className="text-muted-foreground hover:text-foreground" /></button>
              </div>
            </div>
            <div className="max-h-72 overflow-y-auto">
              {notifs.length === 0 ? (
                <div className="py-8 text-center">
                  <ShieldAlert size={24} className="text-emerald-400/50 mx-auto mb-2" />
                  <p className="text-xs text-muted-foreground">No blocked actions recently</p>
                </div>
              ) : notifs.map(n => (
                <div key={n.id} className="px-4 py-3 border-b border-white/5 hover:bg-white/5 transition-colors">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0 mt-1" />
                      <div className="min-w-0">
                        <p className="text-xs font-mono font-medium truncate">{n.tool}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">{n.reason_code} · {n.agent_id}</p>
                      </div>
                    </div>
                    <span className="text-[10px] text-muted-foreground/60 shrink-0">{relTime(n.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="px-4 py-2.5 border-t border-border">
              <p className="text-[10px] text-muted-foreground">Showing last 20 blocked actions · refreshes every 30s</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Chat Panel ────────────────────────────────────────────────────────────────

interface ChatMsg { id: string; role: 'user' | 'assistant'; content: string }

function getChatReply(q: string, tab: string): string {
  const lq = q.toLowerCase()
  if (/hello|hi|hey|help/.test(lq)) return `Ask me about what you see on this page. Try: "What do verdicts mean?", "How do I approve a review?", "What is SLA auto-deny?", "What is block rate?"`
  if (tab === 'review') {
    if (/approve|how.*approve/.test(lq)) return 'Click the green thumbs-up on any card. You\'ll be prompted for your PIN to sign the decision.'
    if (/reject|deny/.test(lq)) return 'Click the red thumbs-down. You can add an optional rejection note before confirming with your PIN.'
    if (/sla|time|expire|auto.?deny/.test(lq)) return 'SLA limits: Critical = 5 min, Urgent = 30 min, Routine = 4 hours. EDON auto-denies anything not actioned in time.'
    if (/pin/.test(lq)) return 'Your PIN is SHA-256 hashed and stored locally. It\'s required to sign every review.'
    if (/who am i|reviewer|name/.test(lq)) return 'Your reviewer name is shown in Settings. It\'s attached to every review signature in the audit trail.'
    return 'Review Queue shows escalated agent actions. Each card has a live SLA timer, inline approve/reject, and PIN confirmation.'
  }
  if (tab === 'decisions') {
    if (/allow|block|escalate|verdict/.test(lq)) return 'ALLOW = permitted. BLOCK = denied by policy. ESCALATE = sent to Review Queue for human approval.'
    if (/reason|code/.test(lq)) return 'Reason codes: SCOPE_VIOLATION, RISK_TOO_HIGH, DATA_EXFIL, OUT_OF_HOURS, NEED_CONFIRMATION, LOOP_DETECTED, PROMPT_INJECTION, ANOMALY_DETECTED.'
    if (/risk/.test(lq)) return 'Risk score 0–1. Above 0.7 typically triggers BLOCK or ESCALATE. Red = high, amber = medium.'
    return 'Decision stream shows every governance verdict. Filters by verdict, search by agent or tool, auto-refreshes every 15s.'
  }
  if (tab === 'agents') {
    if (/trend|block rate|rising|spike/.test(lq)) return 'Stable = normal. Rising = block rate >10%. Spiked = >20%. Investigate spiked agents immediately.'
    if (/status/.test(lq)) return 'Active = recently acted. Idle = no recent actions. Paused = manually suspended.'
    return 'Agents shows your registered fleet with block rate trends. A spiked agent is drifting outside policy.'
  }
  if (tab === 'audit') {
    if (/hash|chain|tamper/.test(lq)) return 'Every record gets a SHA-256 hash chained to the previous one. Tampered records break the chain. Use PDF export for a signed copy.'
    if (/export|pdf/.test(lq)) return 'Click "PDF" to generate a printable audit chain with all hashes. Opens in a new tab, auto-triggers print.'
    return 'Audit log with tamper-evident hash chain. Filter by verdict, click any row for full detail.'
  }
  if (tab === 'policies') {
    if (/toggle|enable|disable/.test(lq)) return 'Click the toggle to enable/disable a rule instantly. Takes effect on the gateway immediately.'
    return 'Policy rules grouped by regulation. Toggle rules to adjust what agents are allowed to do.'
  }
  if (tab === 'dashboard') {
    if (/compliance|health/.test(lq)) return 'Compliance health = pass/fail per regulation. Failing means required rules are missing — go to Policies to fix.'
    if (/block rate|blocked/.test(lq)) return 'Block rate = blocked ÷ total decisions. A sudden spike may mean a policy is too strict or an agent is misbehaving.'
    if (/block reason|why/.test(lq)) return 'Block Reasons shows the top reason codes for blocked actions this week. SCOPE_VIOLATION and RISK_TOO_HIGH are most common.'
    return 'Dashboard: 7-day stats, compliance health, block reason breakdown, decision volume trend, recent decisions. Refreshes every 30s.'
  }
  if (tab === 'settings') {
    if (/token|api key/.test(lq)) return 'Your API token authenticates all requests to the gateway. Change it here if you rotate keys.'
    if (/url|gateway/.test(lq)) return 'The gateway URL is where EDON sends all governance requests. Change it if you switch environments.'
    if (/reviewer|name/.test(lq)) return 'Your reviewer name is signed into every Review Queue decision. Set it here so decisions are traceable to you.'
    return 'Settings lets you change your gateway URL, API token, and reviewer display name without logging out.'
  }
  return 'Ask me about verdicts, SLA timers, review signing, audit hashes, block rates, or any feature.'
}

function ChatPanel({ open, onClose, tab }: { open: boolean; onClose: () => void; tab: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const greetings: Record<string, string> = {
      dashboard: 'Dashboard loaded. Ask about compliance health, block reasons, or decision volume.',
      decisions: 'Decision stream. Ask about verdict types, reason codes, or risk scores.',
      agents: 'Agents tab. Ask about block rate trends, status, or how to investigate a spike.',
      audit: 'Audit log. Ask about the hash chain, PDF export, or risk scores.',
      policies: 'Policies. Ask about toggling rules or what each regulation requires.',
      review: 'Review Queue. Ask about SLA timers, how to approve/reject, or PIN setup.',
      settings: 'Settings. Ask about changing your gateway URL, token, or reviewer name.',
    }
    setMessages([{ id: 'g', role: 'assistant', content: greetings[tab] ?? 'How can I help?' }])
    setTimeout(() => inputRef.current?.focus(), 120)
  }, [open, tab])

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages])

  const send = () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { id: `u-${Date.now()}`, role: 'user', content: text }])
    setLoading(true)
    setTimeout(() => {
      setMessages(prev => [...prev, { id: `a-${Date.now()}`, role: 'assistant', content: getChatReply(text, tab) }])
      setLoading(false)
    }, 280)
  }

  if (!open) return null

  const PROMPTS: Record<string, string[]> = {
    review: ['How to approve?', 'What is SLA?', 'PIN setup'],
    decisions: ['What do verdicts mean?', 'Reason codes?', 'Risk score?'],
    agents: ['Block rate trend?', 'Spiked mean?'],
    audit: ['Hash chain?', 'Export PDF?'],
    dashboard: ['Compliance health?', 'Block reasons?'],
    settings: ['Change token?', 'Reviewer name?'],
  }

  return (
    <>
      <div className="fixed inset-0 z-[90] bg-black/30 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed top-0 right-0 bottom-0 z-[91] w-full sm:w-96 flex flex-col border-l border-white/10 bg-background/98 backdrop-blur-xl shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Bot size={14} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold">Governance AI</p>
              <p className="text-[10px] text-muted-foreground capitalize">{tab} context</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1"><X size={15} /></button>
        </div>
        {(PROMPTS[tab] ?? []).length > 0 && (
          <div className="flex gap-2 px-4 py-2 border-b border-white/[0.06] overflow-x-auto shrink-0">
            {(PROMPTS[tab] ?? []).map(p => (
              <button key={p} onClick={() => { setInput(p); setTimeout(() => inputRef.current?.focus(), 50) }}
                className="shrink-0 text-[10px] px-2.5 py-1 rounded-lg border border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground hover:border-white/20 transition-colors whitespace-nowrap">
                {p}
              </button>
            ))}
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" ref={scrollRef}>
          {messages.map(m => (
            <div key={m.id} className={`rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
              m.role === 'user' ? 'ml-6 bg-primary/15 border border-primary/25 text-foreground' : 'mr-2 bg-white/[0.04] border border-white/[0.08] text-foreground/85'
            }`}>{m.content}</div>
          ))}
          {loading && (
            <div className="mr-2 rounded-xl px-3.5 py-2.5 bg-white/[0.04] border border-white/[0.08]">
              <div className="flex gap-1 items-center">
                {[0, 150, 300].map(d => <span key={d} className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
              </div>
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-white/10 shrink-0">
          <form onSubmit={e => { e.preventDefault(); send() }} className="flex gap-2">
            <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} disabled={loading}
              placeholder="Ask about this page…"
              className="flex-1 bg-white/[0.04] border border-white/15 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
            <button type="submit" disabled={loading || !input.trim()}
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30 disabled:opacity-40 disabled:pointer-events-none transition-colors">
              <Send size={14} />
            </button>
          </form>
        </div>
      </motion.div>
    </>
  )
}

// ── Login Screen ──────────────────────────────────────────────────────────────

const DEFAULT_GATEWAY = 'https://edon-gateway-prod.fly.dev'

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [token, setToken] = useState('')
  const [name, setName] = useState('')
  const [dept, setDept] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault(); setError(''); setLoading(true)
    saveAuth(DEFAULT_GATEWAY, token.trim())
    try {
      await api.health()
      if (name.trim()) setReviewerName(name.trim())
      if (dept.trim()) setReviewerDept(dept.trim())
      onLogin()
    } catch (err) {
      clearAuth()
      setError(err instanceof Error ? err.message : 'Connection failed')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 w-full max-w-md">
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
            <label className="text-xs text-muted-foreground mb-1 block">API Key</label>
            <input type="password" value={token} onChange={e => setToken(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono"
              placeholder="Paste your API key here" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Your Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="e.g. Dr. Sarah Chen" required />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Department</label>
              <div className="relative">
                <select value={dept} onChange={e => setDept(e.target.value)}
                  className="dept-select w-full pl-3 pr-8 py-2 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
                  required>
                  <option value="" disabled>Select department…</option>
                  {Object.entries(DEPARTMENTS).map(([group, depts]) => (
                    <optgroup key={group} label={group}>
                      {depts.map(d => <option key={d} value={d}>{d}</option>)}
                    </optgroup>
                  ))}
                </select>
                <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>
          {error && <p className="text-xs text-destructive flex items-center gap-1"><AlertCircle size={12} /> {error}</p>}
          <button type="submit" disabled={loading}
            className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Shield size={14} />}
            {loading ? 'Connecting…' : 'Connect to Gateway'}
          </button>
        </form>
      </motion.div>
    </div>
  )
}

// ── Settings Tab ──────────────────────────────────────────────────────────────

function SettingsTab({ onReconnect, isAdmin }: { onReconnect: () => void; isAdmin: boolean }) {
  const auth = getAuth()
  const [url, setUrl] = useState(auth?.gatewayUrl || '')
  const [token, setToken] = useState(auth?.token || '')
  const [showToken, setShowToken] = useState(false)
  const [reviewerName] = useState(getReviewerName)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saved, setSaved] = useState(false)
  const [showPinSetup, setShowPinSetup] = useState(false)

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    saveAuth(url.replace(/\/$/, ''), token.trim())
    try {
      const h = await api.health()
      setTestResult({ ok: true, msg: `Connected · v${h.version} · ${h.ok ? 'Healthy' : 'Degraded'}` })
      onReconnect()
    } catch (e) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : 'Connection failed' })
    } finally { setTesting(false) }
  }

  const save = () => {
    saveAuth(url.replace(/\/$/, ''), token.trim())
    setReviewerName(reviewerName.trim())
    setSaved(true); setTimeout(() => setSaved(false), 2000)
    onReconnect()
  }

  const resetPin = () => {
    if (confirm('Reset your reviewer PIN? You will need to set a new one on the next review.')) {
      localStorage.removeItem(PIN_KEY)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold mb-1 flex items-center gap-2"><Settings size={15} className="text-primary" /> Console Settings</h2>
        <p className="text-xs text-muted-foreground">Change your gateway connection, token, or reviewer identity without logging out.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* ── Left column: core settings ── */}
        <div className="space-y-5">
          {/* Gateway connection */}
          <div className="glass-card p-5 space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Wifi size={13} className="text-primary" /> Gateway Connection</h3>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Gateway URL</label>
              <input type="url" value={url} onChange={e => setUrl(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">API Token</label>
              <div className="relative">
                <input type={showToken ? 'text' : 'password'} value={token} onChange={e => setToken(e.target.value)}
                  className="w-full px-3 py-2 pr-10 rounded-lg bg-muted/50 border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary" />
                <button type="button" onClick={() => setShowToken(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            {testResult && (
              <p className={`text-xs flex items-center gap-1.5 ${testResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{testResult.msg}
              </p>
            )}
            <div className="flex gap-3">
              <button onClick={testConnection} disabled={testing}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50">
                {testing ? <div className="w-3.5 h-3.5 border border-muted/30 border-t-muted-foreground rounded-full animate-spin" /> : <WifiOff size={13} />}
                Test Connection
              </button>
              <button onClick={save}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary text-xs font-semibold hover:bg-primary/30 transition-colors">
                {saved ? <><CheckCircle2 size={13} /> Saved</> : 'Save Changes'}
              </button>
            </div>
          </div>

          {/* Reviewer identity */}
          <div className="glass-card p-5 space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-2"><User size={13} className="text-primary" /> Reviewer Identity</h3>
            <p className="text-xs text-muted-foreground">Your name and department are stamped on every Review Queue decision in the audit trail.</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Display Name</label>
                <input type="text" value={reviewerName} readOnly
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm opacity-60 cursor-not-allowed" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Department</label>
                <input type="text" value={getReviewerDept()} readOnly
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm opacity-60 cursor-not-allowed" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Identity is locked once set. Sign out to reset.</p>
            <div className="flex items-center justify-between">
              <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                <KeyRound size={11} />
                PIN: {hasPinSet() ? <span className="text-emerald-400">Set</span> : <span className="text-amber-400">Not set</span>}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setShowPinSetup(true)}
                  className="text-[10px] px-2.5 py-1 rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                  {hasPinSet() ? 'Change PIN' : 'Set PIN'}
                </button>
                {hasPinSet() && (
                  <button onClick={resetPin} className="text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition-colors">Reset</button>
                )}
              </div>
            </div>
            <button onClick={save}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary text-xs font-semibold hover:bg-primary/30 transition-colors">
              {saved ? <><CheckCircle2 size={13} /> Saved</> : 'Save Name'}
            </button>
          </div>

          {/* Session info */}
          <div className="glass-card p-5 space-y-2">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Clock size={13} className="text-primary" /> Session</h3>
            <p className="text-xs text-muted-foreground">Sessions auto-expire after <span className="text-foreground">15 minutes</span> of inactivity. A warning appears at 13 minutes.</p>
          </div>

          {isAdmin && <ShadowModeCard />}
        </div>

        {/* ── Right column: security & ops cards ── */}
        <div className="space-y-5">
          <ApiKeyRotationCard />
          <ConsoleLinkCard />
          <IpAllowlistCard />
          <WebhookAlertsCard />
          <SettingsQuickReferenceCard />
        </div>
      </div>

      <AnimatePresence>
        {showPinSetup && (
          <motion.div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <PinModal mode="setup" onSuccess={() => { setShowPinSetup(false); setSaved(true); setTimeout(() => setSaved(false), 2000) }} onCancel={() => setShowPinSetup(false)} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ShadowModeCard() {
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getShadowMode().then(r => setEnabled(r.enabled)).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const toggle = async () => {
    setSaving(true)
    try {
      const r = await api.setShadowMode(!enabled)
      setEnabled(r.enabled)
    } catch { /* ignore */ } finally { setSaving(false) }
  }

  return (
    <div className="glass-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Shadow Mode</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Log all decisions without blocking — use during trial periods</p>
        </div>
        <button onClick={toggle} disabled={loading || saving}
          className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none ${enabled ? 'bg-amber-500' : 'bg-muted/50 border border-border'}`}>
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200 ${enabled ? 'translate-x-5' : ''}`} />
        </button>
      </div>
      {enabled && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs">
          <span className="text-base">⚠</span>
          Governance is in observe-only mode. No actions are being blocked.
        </div>
      )}
    </div>
  )
}

function ApiKeyRotationCard() {
  const [keys, setKeys] = useState<Array<{ id: string; name?: string | null; role: string; status: string }>>([])
  const [loading, setLoading] = useState(true)
  const [overlapHours, setOverlapHours] = useState(24)
  const [rotating, setRotating] = useState(false)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.listApiKeys().then(r => setKeys(r.keys)).catch(() => setKeys([])).finally(() => setLoading(false))
  }, [])

  const rotate = async (keyId: string) => {
    setRotating(true); setNewKey(null)
    try {
      const r = await api.rotateApiKey(keyId, overlapHours)
      setNewKey(r.new_key)
      const updated = await api.listApiKeys()
      setKeys(updated.keys)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Rotation failed')
    } finally { setRotating(false) }
  }

  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <h3 className="text-sm font-semibold flex items-center gap-2"><RefreshCw size={13} className="text-primary" /> API Key Rotation</h3>
      <p className="text-xs text-muted-foreground">Rotate your key with zero downtime. The old key stays valid during the overlap window.</p>
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
      {keys.map(k => (
        <div key={k.id} className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{k.name ?? 'Unnamed key'}</p>
            <p className="text-[10px] font-mono text-muted-foreground/50 truncate">{k.id}</p>
          </div>
          <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${k.status === 'active' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400'}`}>{k.status}</span>
          <select value={overlapHours} onChange={e => setOverlapHours(Number(e.target.value))}
            className="text-xs bg-background border border-border rounded px-2 py-1 text-muted-foreground">
            <option value={1}>1h overlap</option>
            <option value={4}>4h overlap</option>
            <option value={24}>24h overlap</option>
            <option value={72}>3d overlap</option>
          </select>
          <button onClick={() => rotate(k.id)} disabled={rotating}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
            <RefreshCw size={13} className={rotating ? 'animate-spin' : ''} /> Rotate
          </button>
        </div>
      ))}
      {newKey && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-2">
          <p className="text-xs font-medium text-emerald-400 flex items-center gap-1.5"><Check size={13} /> New key — copy it now, shown once only</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-black/30 rounded px-3 py-2 break-all">{newKey}</code>
            <button onClick={() => copy(newKey)} className="p-2 rounded border border-border hover:bg-muted/50 transition-colors">
              {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} className="text-muted-foreground" />}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ConsoleLinkCard() {
  const [copied, setCopied] = useState(false)
  const auth = (() => { try { return JSON.parse(localStorage.getItem('edon_auth') || '{}') } catch { return {} } })()
  const url = `${window.location.origin}/#token=${auth.token || ''}&base=${encodeURIComponent(auth.gatewayUrl || '')}`

  const copy = () => {
    navigator.clipboard.writeText(url)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="glass-card p-5 space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-2"><Link size={13} className="text-primary" /> Console Access Link</h3>
      <p className="text-xs text-muted-foreground">Share with your team. Token is in the URL hash — never sent to servers or logged.</p>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2.5">
        <code className="flex-1 text-xs font-mono text-muted-foreground truncate">{url}</code>
        <button onClick={copy} className="p-1.5 rounded border border-border hover:bg-muted/50 transition-colors shrink-0">
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} className="text-muted-foreground" />}
        </button>
      </div>
      <p className="text-[10px] text-muted-foreground/50 flex items-center gap-1"><Shield size={11} /> #token= hash fragment — never transmitted to or stored by servers</p>
    </div>
  )
}

function IpAllowlistCard() {
  const [cidrs, setCidrs] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getIpAllowlist().then(r => setCidrs(r.cidrs)).catch(() => setCidrs([])).finally(() => setLoading(false))
  }, [])

  const add = async () => {
    if (!input.trim()) return
    setSaving(true)
    try {
      await api.addIpAllowlist(input.trim())
      const r = await api.getIpAllowlist()
      setCidrs(r.cidrs); setInput('')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add CIDR')
    } finally { setSaving(false) }
  }

  const remove = async (cidr: string) => {
    try {
      await api.removeIpAllowlist(cidr)
      setCidrs(c => c.filter(x => x !== cidr))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to remove CIDR')
    }
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Shield size={13} className="text-primary" /> IP Allowlist
        {cidrs.length > 0 && <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">Active</span>}
      </h3>
      <p className="text-xs text-muted-foreground">Restrict API access to specific IPs. Once any entry is added, all other IPs are blocked. <strong className="text-foreground/70">Add your IP first.</strong></p>
      {cidrs.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 text-xs text-yellow-400">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" /> Allowlist active — requests from unlisted IPs are rejected.
        </div>
      )}
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
      <div className="space-y-2">
        {cidrs.map(cidr => (
          <div key={cidr} className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2">
            <Shield size={12} className="text-emerald-400 shrink-0" />
            <code className="flex-1 text-xs font-mono">{cidr}</code>
            <button onClick={() => remove(cidr)} className="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input type="text" value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="203.0.113.0/24 or 1.2.3.4"
          className="flex-1 text-sm bg-muted/50 border border-border rounded-lg px-3 py-2 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary" />
        <button onClick={add} disabled={!input.trim() || saving}
          className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary font-semibold hover:bg-primary/30 transition-colors disabled:opacity-50">
          <Plus size={14} /> Add
        </button>
      </div>
    </div>
  )
}

// ── Webhook Alerts Card ───────────────────────────────────────────────────────

function WebhookAlertsCard() {
  const [webhooks, setWebhooks] = useState<Array<{ id: string; url: string; events: string[]; enabled: boolean }>>([])
  const [loading, setLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, 'ok' | 'fail'>>({})

  const load = () => api.listWebhooks().then(r => setWebhooks(r.webhooks ?? [])).catch(() => setWebhooks([])).finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const add = async () => {
    if (!url.trim()) return
    setSaving(true)
    try {
      await api.createWebhook(url.trim(), ['blocked', 'escalated', 'high_risk'])
      setUrl(''); await load()
    } catch (e) { alert(e instanceof Error ? e.message : 'Failed to add webhook') }
    finally { setSaving(false) }
  }

  const remove = async (id: string) => {
    try { await api.deleteWebhook(id); setWebhooks(w => w.filter(x => x.id !== id)) }
    catch (e) { alert(e instanceof Error ? e.message : 'Failed to remove') }
  }

  const test = async (id: string) => {
    setTesting(id)
    try {
      await api.testWebhook(id)
      setTestResult(r => ({ ...r, [id]: 'ok' }))
    } catch {
      setTestResult(r => ({ ...r, [id]: 'fail' }))
    } finally {
      setTesting(null)
      setTimeout(() => setTestResult(r => { const n = { ...r }; delete n[id]; return n }), 3000)
    }
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Bell size={13} className="text-primary" /> Webhook Alerts
        {webhooks.length > 0 && <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">{webhooks.length} active</span>}
      </h3>
      <p className="text-xs text-muted-foreground">Get notified when decisions are blocked, escalated, or flagged as high-risk. Signed with HMAC-SHA256.</p>
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
      <div className="space-y-2">
        {webhooks.map(w => (
          <div key={w.id} className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-mono truncate">{w.url}</p>
              <p className="text-[10px] text-muted-foreground">{w.events.join(', ')}</p>
            </div>
            {testResult[w.id] && (
              <span className={`text-[10px] font-medium ${testResult[w.id] === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult[w.id] === 'ok' ? '✓ sent' : '✗ fail'}
              </span>
            )}
            <button onClick={() => test(w.id)} disabled={testing === w.id}
              className="text-xs px-2 py-1 rounded border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
              {testing === w.id ? '…' : 'Test'}
            </button>
            <button onClick={() => remove(w.id)} className="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input type="url" value={url} onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="https://your-server.com/webhook"
          className="flex-1 text-sm bg-muted/50 border border-border rounded-lg px-3 py-2 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary" />
        <button onClick={add} disabled={!url.trim() || saving}
          className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary font-semibold hover:bg-primary/30 transition-colors disabled:opacity-50">
          <Plus size={14} /> Add
        </button>
      </div>
    </div>
  )
}

// ── Settings Quick Reference Card ────────────────────────────────────────────

function SettingsQuickReferenceCard() {
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number; components: Record<string, { status: string }> } | null>(null)
  const [me, setMe] = useState<{ tenant_id: string; role: string; plan: string } | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.me().then(setMe).catch(() => {})
  }, [])

  const uptimeStr = (s: number) => {
    if (s < 60) return `${s}s`
    if (s < 3600) return `${Math.floor(s / 60)}m`
    if (s < 86400) return `${Math.floor(s / 3600)}h`
    return `${Math.floor(s / 86400)}d`
  }

  const components = health ? Object.entries(health.components) : []
  const allHealthy = components.every(([, v]) => v.status === 'ok' || v.status === 'healthy')

  return (
    <>
      {/* Gateway status */}
      <div className="glass-card p-5 space-y-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Activity size={13} className="text-primary" /> Gateway Status
          {health && (
            <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full border font-medium ${allHealthy ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400'}`}>
              {allHealthy ? 'Healthy' : 'Degraded'}
            </span>
          )}
        </h3>
        {health ? (
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Version</span>
              <span className="font-mono">{health.version}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Uptime</span>
              <span className="font-mono">{uptimeStr(health.uptime_seconds)}</span>
            </div>
            {components.map(([name, val]) => (
              <div key={name} className="flex justify-between text-xs">
                <span className="text-muted-foreground capitalize">{name.replace(/_/g, ' ')}</span>
                <span className={`font-medium ${val.status === 'ok' || val.status === 'healthy' ? 'text-emerald-400' : 'text-yellow-400'}`}>{val.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Fetching status…</p>
        )}
      </div>

      {/* Account details */}
      {me && (
        <div className="glass-card p-5 space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><User size={13} className="text-primary" /> Account</h3>
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Tenant ID</span>
              <code className="font-mono text-[11px] text-muted-foreground/80 truncate max-w-[160px]">{me.tenant_id}</code>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Role</span>
              <span className={`font-medium capitalize ${me.role === 'admin' ? 'text-primary' : 'text-foreground'}`}>{me.role}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Plan</span>
              <span className="font-medium capitalize text-foreground">{me.plan}</span>
            </div>
          </div>
        </div>
      )}

      {/* Security checklist */}
      <div className="glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><ShieldAlert size={13} className="text-primary" /> Security Checklist</h3>
        <div className="space-y-2">
          {[
            { label: 'PIN set for reviews', ok: hasPinSet() },
            { label: 'Identity configured', ok: !!getReviewerName() },
            { label: 'Gateway reachable', ok: !!health?.ok },
          ].map(({ label, ok }) => (
            <div key={label} className="flex items-center gap-2 text-xs">
              {ok
                ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                : <AlertCircle size={13} className="text-amber-400 shrink-0" />}
              <span className={ok ? 'text-foreground' : 'text-amber-400'}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

// ── Dashboard Tab ─────────────────────────────────────────────────────────────

function DashboardTab() {
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [recent, setRecent] = useState<AuditEvent[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [blockReasons, setBlockReasons] = useState<BlockReason[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [ts, rec, h, br] = await Promise.all([
        api.timeseries(7), api.auditQuery({ limit: 20 }), api.complianceHealth(), api.blockReasons(7),
      ])
      setTimeseries(ts); setRecent(rec.events); setHealth(h); setBlockReasons(br)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load(); const iv = setInterval(load, 30000); return () => clearInterval(iv) }, [load])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const totals = timeseries.reduce(
    (acc, p) => ({ allow: acc.allow + p.allowed, block: acc.block + p.blocked, confirm: acc.confirm + p.confirm }),
    { allow: 0, block: 0, confirm: 0 }
  )
  const total = totals.allow + totals.block + totals.confirm
  const blockRate = total > 0 ? ((totals.block / total) * 100).toFixed(1) : '0.0'
  const maxReason = Math.max(...blockReasons.map(r => r.count), 1)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Decisions', value: total, icon: Activity, color: 'text-blue-400' },
          { label: 'Allowed', value: totals.allow, icon: CheckCircle2, color: 'text-emerald-400' },
          { label: 'Blocked', value: totals.block, icon: XCircle, color: 'text-red-400' },
          { label: 'Block Rate', value: `${blockRate}%`, icon: ShieldAlert, color: parseFloat(blockRate) > 20 ? 'text-red-400' : 'text-amber-400' },
        ].map(s => (
          <div key={s.label} className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <s.icon size={16} className={s.color} />
            </div>
            <p className="text-2xl font-semibold">{typeof s.value === 'number' ? s.value.toLocaleString() : s.value}</p>
            <p className="text-xs text-muted-foreground mt-1">last 7 days</p>
          </div>
        ))}
      </div>

      {health && (
        <div className="glass-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium flex items-center gap-2"><Heart size={14} className="text-primary" /> Compliance Health</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${health.overall === 'pass' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
              {health.overall.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {Object.entries(health.regulations).map(([key, reg]) => (
              <div key={key} className={`p-2 rounded-lg border text-xs ${reg.status === 'pass' ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-red-500/20 bg-red-500/5'}`}>
                <div className="flex items-center gap-1 mb-1">
                  {reg.status === 'pass' ? <CheckCircle2 size={10} className="text-emerald-400" /> : <XCircle size={10} className="text-red-400" />}
                  <span className="font-medium">{key}</span>
                </div>
                <p className="text-muted-foreground">{reg.rules_active}/{reg.rules_required} rules</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Block reason breakdown */}
      {blockReasons.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <BarChart2 size={14} className="text-primary" /> Block Reasons (7 days)
          </h3>
          <div className="space-y-2">
            {blockReasons.slice(0, 8).map(r => (
              <div key={r.reason} className="flex items-center gap-3 text-xs">
                <span className="text-muted-foreground font-mono w-40 truncate shrink-0">{r.reason}</span>
                <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                  <div className="h-full rounded-full bg-red-400/60" style={{ width: `${(r.count / maxReason) * 100}%` }} />
                </div>
                <span className="text-muted-foreground w-8 text-right tabular-nums">{r.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {timeseries.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2"><Activity size={14} className="text-primary" /> Decision Volume (7 days)</h3>
          <div className="flex items-end gap-1 h-24">
            {timeseries.map(p => {
              const max = Math.max(...timeseries.map(x => x.allowed + x.blocked + x.confirm), 1)
              const h = ((p.allowed + p.blocked + p.confirm) / max) * 100
              return (
                <div key={p.label} className="flex-1 flex flex-col items-center gap-1" title={`${p.label}: ${p.allowed + p.blocked + p.confirm}`}>
                  <div className="w-full rounded-t" style={{ height: `${Math.max(h, 4)}%`, background: 'hsl(var(--primary) / 0.6)' }} />
                  <span className="text-[10px] text-muted-foreground">{p.label.slice(5)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="glass-card p-4">
        <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Clock size={14} className="text-primary" /> Recent Decisions</h3>
        {recent.length === 0 ? <Empty message="No decisions recorded yet" /> : (
          <div className="space-y-2">
            {recent.map((e, i) => (
              <div key={e.action_id || e.id || i} className="flex items-center gap-3 py-2 border-b border-border/50 last:border-0 text-sm">
                <VerdictBadge verdict={e.decision_verdict} />
                <span className="text-muted-foreground font-mono text-xs flex-1 truncate">{e.agent_id}</span>
                <span className="text-xs text-muted-foreground hidden sm:block">{e.tool_name || '—'}</span>
                <span className="text-xs text-muted-foreground">{relTime(e.timestamp)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Decisions Tab ─────────────────────────────────────────────────────────────

function DecisionsTab() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [verdict, setVerdict] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AuditEvent | null>(null)

  const load = useCallback(async () => {
    setError('')
    try {
      const res = await api.auditQuery({ verdict: verdict || undefined, limit: 200 })
      setEvents(res.events)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [verdict])

  useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv) }, [load])

  const filtered = events.filter(e =>
    !search || (e.agent_id + (e.tool_name || '') + (e.decision_reason_code || '')).toLowerCase().includes(search.toLowerCase())
  )
  const counts = { ALLOW: 0, BLOCK: 0, ESCALATE: 0 }
  events.forEach(e => { const v = e.decision_verdict?.toUpperCase() as keyof typeof counts; if (v in counts) counts[v]++ })

  return (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap">
        {[
          { label: 'Allowed', key: 'ALLOW', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
          { label: 'Blocked', key: 'BLOCK', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
          { label: 'Escalated', key: 'ESCALATE', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
        ].map(c => (
          <button key={c.key} onClick={() => setVerdict(v => v === c.key ? '' : c.key)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${verdict === c.key ? c.color + ' ring-1 ring-current/30' : 'border-border text-muted-foreground bg-muted/30 hover:border-white/20'}`}>
            {c.label} <span className="font-mono font-bold">{counts[c.key as keyof typeof counts]}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agent, tool…"
            className="pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary w-52" />
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} decisions</span>
        <span className="flex items-center gap-1.5 text-xs text-emerald-400">
          <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"/><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"/></span>
          Live
        </span>
        <button onClick={load} className={`ml-auto text-muted-foreground hover:text-foreground transition ${loading ? 'animate-spin' : ''}`}><RefreshCcw size={14} /></button>
      </div>
      {loading ? <Spinner /> : error ? <ErrorMsg message={error} onRetry={load} /> : filtered.length === 0 ? <Empty message="No decisions found" /> : (
        <div className="glass-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-xs text-muted-foreground">
                <th className="text-left py-3 px-4">Verdict</th>
                <th className="text-left py-3 px-4">Agent</th>
                <th className="text-left py-3 px-4 hidden md:table-cell">Tool</th>
                <th className="text-left py-3 px-4 hidden lg:table-cell">Reason</th>
                <th className="text-left py-3 px-4 hidden lg:table-cell">Risk</th>
                <th className="text-left py-3 px-4">Time</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <tr key={e.action_id || e.id || i} className="border-b border-border/30 last:border-0 hover:bg-muted/20 cursor-pointer transition-colors" onClick={() => setSelected(e)}>
                  <td className="py-2.5 px-4"><VerdictBadge verdict={e.decision_verdict} /></td>
                  <td className="py-2.5 px-4 font-mono text-xs truncate max-w-[130px]">{e.agent_id}</td>
                  <td className="py-2.5 px-4 text-muted-foreground hidden md:table-cell text-xs">{e.tool_name || '—'}</td>
                  <td className="py-2.5 px-4 text-muted-foreground hidden lg:table-cell text-xs">{e.decision_reason_code || '—'}</td>
                  <td className="py-2.5 px-4 hidden lg:table-cell">
                    {e.risk_score != null && <span className={`text-xs font-mono ${e.risk_score > 0.7 ? 'text-red-400' : e.risk_score > 0.4 ? 'text-amber-400' : 'text-muted-foreground'}`}>{e.risk_score.toFixed(2)}</span>}
                  </td>
                  <td className="py-2.5 px-4 text-muted-foreground text-xs">{relTime(e.timestamp)}</td>
                  <td className="py-2.5 px-4"><ChevronRight size={14} className="text-muted-foreground" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AnimatePresence>
        {selected && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex justify-end" onClick={() => setSelected(null)}>
            <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="w-full max-w-md bg-card border-l border-border h-full overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-semibold">Decision Detail</h3>
                <button onClick={() => setSelected(null)}><X size={16} className="text-muted-foreground hover:text-foreground" /></button>
              </div>
              <div className="space-y-4 text-sm">
                <VerdictBadge verdict={selected.decision_verdict} />
                {[['Action ID', selected.action_id || selected.id], ['Agent', selected.agent_id], ['Tool', selected.tool_name], ['Reason Code', selected.decision_reason_code], ['Risk Score', selected.risk_score?.toFixed(3)], ['Policy Version', selected.policy_version], ['Timestamp', fmtTs(selected.timestamp)]].map(([label, value]) => value != null && (
                  <div key={String(label)}><p className="text-xs text-muted-foreground mb-1">{label}</p><p className="font-mono text-xs break-all">{String(value)}</p></div>
                ))}
                {selected.explanation && <div><p className="text-xs text-muted-foreground mb-1">Explanation</p><p className="text-xs leading-relaxed">{selected.explanation}</p></div>}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Agents Tab ────────────────────────────────────────────────────────────────

function getBlockTrend(agent: Agent): 'stable' | 'rising' | 'spiked' {
  const rate = agent.block_rate ?? (agent.decisions_total && agent.decisions_blocked ? agent.decisions_blocked / agent.decisions_total : 0)
  if (rate > 0.2) return 'spiked'; if (rate > 0.1) return 'rising'; return 'stable'
}
const TREND_CFG = {
  stable: { label: 'Stable', icon: Minus, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
  rising: { label: 'Rising', icon: TrendingUp, color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' },
  spiked: { label: 'Spiked', icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20' },
}

function AgentsTab() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.agents()
      setAgents(Array.isArray(res) ? res : (res as { agents?: Agent[]; items?: Agent[] }).agents || (res as { agents?: Agent[]; items?: Agent[] }).items || [])
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load agents') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = agents.filter(a => !search || (a.agent_id + (a.name || '') + (a.agent_type || '')).toLowerCase().includes(search.toLowerCase()))
  const spiked = filtered.filter(a => getBlockTrend(a) === 'spiked').length
  const rising = filtered.filter(a => getBlockTrend(a) === 'rising').length

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      {(spiked > 0 || rising > 0) && (
        <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${spiked > 0 ? 'border-red-500/30 bg-red-500/10 text-red-400' : 'border-amber-500/30 bg-amber-500/10 text-amber-400'}`}>
          <AlertTriangle size={15} className="shrink-0" />
          {spiked > 0 ? `${spiked} agent${spiked > 1 ? 's' : ''} with spiked block rate — investigate` : `${rising} agent${rising > 1 ? 's' : ''} with rising block rate`}
        </div>
      )}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents…"
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} agents</span>
        <button onClick={load} className="ml-auto text-muted-foreground hover:text-foreground transition"><RefreshCcw size={14} /></button>
      </div>
      {filtered.length === 0 ? <Empty message="No agents registered yet" /> : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map(a => {
            const trend = getBlockTrend(a); const tCfg = TREND_CFG[trend]; const TrendIcon = tCfg.icon
            const blockPct = a.decisions_total && a.decisions_blocked ? ((a.decisions_blocked / a.decisions_total) * 100).toFixed(1) : null
            return (
              <div key={a.agent_id} className="glass-card-hover p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{a.name || a.agent_id}</p>
                    <p className="text-xs text-muted-foreground font-mono truncate">{a.agent_id}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 ml-2">
                    {(() => { const r = a.block_rate ?? 0; return <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${r > 0.3 ? 'bg-red-500/10 border-red-500/20 text-red-400' : r > 0.1 ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'}`}>Risk {r > 0.3 ? 'High' : r > 0.1 ? 'Med' : 'Low'}</span> })()}
                    <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-medium ${tCfg.bg} ${tCfg.color}`}><TrendIcon size={9} />{tCfg.label}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${a.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : a.status === 'paused' ? 'bg-amber-500/15 text-amber-400' : 'bg-muted text-muted-foreground'}`}>{a.status || 'unknown'}</span>
                  </div>
                </div>
                {a.description && <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{a.description}</p>}
                <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                  {a.decisions_total != null && <span><span className="text-foreground font-medium">{a.decisions_total}</span> decisions</span>}
                  {blockPct && <span><span className={tCfg.color + ' font-medium'}>{blockPct}%</span> blocked</span>}
                  {a.policy_pack && <span className="text-primary">{a.policy_pack}</span>}
                  {a.last_seen && <span className="ml-auto">{relTime(a.last_seen)}</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

async function buildChain(events: AuditEvent[]): Promise<string[]> {
  const hashes: string[] = []; let prev = '0000000000000000'
  for (const e of events) {
    const h = await sha256hex(`${prev}|${e.action_id || e.id || ''}|${e.decision_verdict}|${e.timestamp}`)
    hashes.push(h.slice(0, 16)); prev = h.slice(0, 16)
  }
  return hashes
}

function exportAuditPdf(events: AuditEvent[], hashes: string[]) {
  const rows = events.map((e, i) => `<tr><td>${i + 1}</td><td>${e.decision_verdict}</td><td>${e.agent_id}</td><td>${e.tool_name || '—'}</td><td>${e.decision_reason_code || '—'}</td><td>${new Date(e.timestamp).toLocaleString()}</td><td style="font-family:monospace;font-size:10px">${hashes[i] || '—'}</td></tr>`).join('')
  const html = `<!DOCTYPE html><html><head><title>EDON Audit Chain</title><style>body{font-family:sans-serif;font-size:12px;padding:20px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left}th{background:#f5f5f5}h1{font-size:16px}p{color:#666;font-size:11px}</style></head><body><h1>EDON Audit Chain Export</h1><p>Generated: ${new Date().toLocaleString()} · ${events.length} records</p><table><thead><tr><th>#</th><th>Verdict</th><th>Agent</th><th>Tool</th><th>Reason</th><th>Timestamp</th><th>Hash</th></tr></thead><tbody>${rows}</tbody></table></body></html>`
  const w = window.open('', '_blank')
  if (w) { w.document.write(html); w.document.close(); setTimeout(() => w.print(), 300) }
}

function AuditTab() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [hashes, setHashes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [verdict, setVerdict] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AuditEvent | null>(null)
  const [showChain, setShowChain] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.auditQuery({ verdict: verdict || undefined, limit: 200 })
      setEvents(res.events)
      setHashes(await buildChain(res.events))
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load audit log') }
    finally { setLoading(false) }
  }, [verdict])

  useEffect(() => { load() }, [load])

  const filtered = events.filter(e => !search || (e.agent_id + (e.tool_name || '') + (e.decision_reason_code || '')).toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
            className="pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary w-48" />
        </div>
        <select value={verdict} onChange={e => setVerdict(e.target.value)}
          className="py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary">
          <option value="">All verdicts</option>
          <option value="ALLOW">ALLOW</option>
          <option value="BLOCK">BLOCK</option>
          <option value="ESCALATE">ESCALATE</option>
        </select>
        <span className="text-xs text-muted-foreground">{filtered.length} events</span>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setShowChain(v => !v)}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${showChain ? 'border-primary/40 text-primary bg-primary/10' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            <Shield size={12} /> Chain{hashes.length > 0 ? ` · ${hashes.length}` : ''}
          </button>
          {hashes.length > 0 && (
            <button onClick={() => exportAuditPdf(events, hashes)}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors">
              <FileDown size={12} /> PDF
            </button>
          )}
          <button onClick={load} className="text-muted-foreground hover:text-foreground transition"><RefreshCcw size={14} /></button>
        </div>
      </div>

      {showChain && hashes.length > 0 && (
        <div className="glass-card p-4">
          <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
            <Shield size={11} /> Hash Chain · tip: <span className="font-mono text-primary">{hashes[hashes.length - 1]}</span>
          </p>
          <div className="max-h-32 overflow-y-auto space-y-0.5">
            {hashes.map((h, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
                <span className="text-muted-foreground/40 w-6 text-right shrink-0">{i + 1}</span>
                <span className="text-primary/70">{h}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? <Spinner /> : error ? <ErrorMsg message={error} onRetry={load} /> : filtered.length === 0 ? <Empty message="No audit events found" /> : (
        <div className="glass-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-xs text-muted-foreground">
                <th className="text-left py-3 px-4">Verdict</th>
                <th className="text-left py-3 px-4">Agent</th>
                <th className="text-left py-3 px-4 hidden md:table-cell">Tool</th>
                <th className="text-left py-3 px-4 hidden lg:table-cell">Reason</th>
                <th className="text-left py-3 px-4 hidden lg:table-cell">Risk</th>
                <th className="text-left py-3 px-4">Timestamp</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => {
                const idx = events.indexOf(e)
                return (
                  <tr key={e.action_id || e.id || i} className="border-b border-border/30 last:border-0 hover:bg-muted/20 cursor-pointer transition-colors" onClick={() => setSelected(e)}>
                    <td className="py-2.5 px-4"><VerdictBadge verdict={e.decision_verdict} /></td>
                    <td className="py-2.5 px-4 font-mono text-xs truncate max-w-[150px]">{e.agent_id}</td>
                    <td className="py-2.5 px-4 text-muted-foreground hidden md:table-cell text-xs">{e.tool_name || '—'}</td>
                    <td className="py-2.5 px-4 text-muted-foreground hidden lg:table-cell text-xs">{e.decision_reason_code || '—'}</td>
                    <td className="py-2.5 px-4 hidden lg:table-cell">
                      {e.risk_score != null && <span className={`text-xs font-mono ${e.risk_score > 0.7 ? 'text-red-400' : e.risk_score > 0.4 ? 'text-amber-400' : 'text-muted-foreground'}`}>{e.risk_score.toFixed(2)}</span>}
                    </td>
                    <td className="py-2.5 px-4 text-muted-foreground text-xs">
                      {fmtTs(e.timestamp)}
                      {hashes[idx] && <p className="font-mono text-[9px] text-muted-foreground/40 mt-0.5">{hashes[idx]}</p>}
                    </td>
                    <td className="py-2.5 px-4"><ChevronRight size={14} className="text-muted-foreground" /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <AnimatePresence>
        {selected && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex justify-end" onClick={() => setSelected(null)}>
            <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="w-full max-w-md bg-card border-l border-border h-full overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-semibold">Audit Detail</h3>
                <button onClick={() => setSelected(null)}><X size={16} className="text-muted-foreground hover:text-foreground" /></button>
              </div>
              <div className="space-y-4 text-sm">
                <VerdictBadge verdict={selected.decision_verdict} />
                {[['Action ID', selected.action_id || selected.id], ['Agent', selected.agent_id], ['Tool', selected.tool_name], ['Reason Code', selected.decision_reason_code], ['Risk Score', selected.risk_score?.toFixed(3)], ['Policy Version', selected.policy_version], ['Timestamp', fmtTs(selected.timestamp)], ['Chain Hash', hashes[events.indexOf(selected)]]].map(([label, value]) => value != null && (
                  <div key={String(label)}><p className="text-xs text-muted-foreground mb-1">{label}</p><p className={`text-xs break-all ${String(label) === 'Chain Hash' ? 'font-mono text-primary/70' : 'font-mono'}`}>{String(value)}</p></div>
                ))}
                {selected.explanation && <div><p className="text-xs text-muted-foreground mb-1">Explanation</p><p className="text-xs leading-relaxed">{selected.explanation}</p></div>}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Policy Template Packs ─────────────────────────────────────────────────────

function PolicyTemplatePacks({ onApplied }: { onApplied: () => void }) {
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; description?: string; regulation?: string; rule_count?: number }>>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState<string | null>(null)
  const [applied, setApplied] = useState<string | null>(null)

  useEffect(() => {
    api.getPolicyTemplates().then(r => setTemplates(r.templates ?? r as never ?? [])).catch(() => setTemplates([])).finally(() => setLoading(false))
  }, [])

  const apply = async (id: string) => {
    setApplying(id)
    try {
      await api.applyPolicyTemplate(id)
      setApplied(id)
      setTimeout(() => setApplied(null), 3000)
      onApplied()
    } catch (e) { alert(e instanceof Error ? e.message : 'Failed to apply template') }
    finally { setApplying(null) }
  }

  if (loading || templates.length === 0) return null

  const colors: Record<string, string> = {
    hipaa: 'text-blue-400 border-blue-500/20 bg-blue-500/5',
    hitrust: 'text-purple-400 border-purple-500/20 bg-purple-500/5',
    soc2: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5',
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-2"><Package size={13} className="text-primary" /> Compliance Template Packs</h3>
        <p className="text-xs text-muted-foreground mt-0.5">Apply pre-built rule sets for industry regulations in one click.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {templates.map(t => {
          const cls = colors[t.id] ?? 'text-muted-foreground border-border bg-muted/20'
          return (
            <div key={t.id} className={`rounded-xl border p-4 space-y-2 ${cls}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider">{t.name}</span>
                {t.rule_count && <span className="text-[10px] opacity-70">{t.rule_count} rules</span>}
              </div>
              {t.description && <p className="text-[11px] opacity-80 leading-relaxed">{t.description}</p>}
              <button onClick={() => apply(t.id)} disabled={applying === t.id}
                className="w-full text-xs py-1.5 rounded-lg border border-current/30 hover:bg-current/10 font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5">
                {applied === t.id ? <><Check size={12} /> Applied</> : applying === t.id ? 'Applying…' : 'Apply Pack'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Policies Tab ──────────────────────────────────────────────────────────────

function PoliciesTab() {
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [rRes, hRes] = await Promise.allSettled([api.policyRules(), api.complianceHealth()])
      if (rRes.status === 'fulfilled') {
        const raw = rRes.value
        setRules(Array.isArray(raw) ? raw as PolicyRule[] : (raw as { rules: PolicyRule[] }).rules ?? [])
      }
      if (hRes.status === 'fulfilled') setHealth(hRes.value)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load policies') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const REGULATION_META: Record<string, { label: string; color: string; border: string; bg: string; desc: string }> = {
    HIPAA:    { label: 'HIPAA',     color: 'text-blue-400',   border: 'border-blue-500/30',   bg: 'bg-blue-500/5',   desc: 'Health Insurance Portability and Accountability Act' },
    HITRUST:  { label: 'HITRUST',   color: 'text-purple-400', border: 'border-purple-500/30', bg: 'bg-purple-500/5', desc: 'Health Information Trust Alliance CSF' },
    'SOC 2':  { label: 'SOC 2',     color: 'text-emerald-400',border: 'border-emerald-500/30',bg: 'bg-emerald-500/5',desc: 'Service Organization Control 2 Type II' },
    General:  { label: 'Additional Controls', color: 'text-muted-foreground', border: 'border-border', bg: 'bg-muted/10', desc: 'Organization-specific rules added on top of regulatory standards' },
  }

  const normalizeReg = (reg?: string) => {
    if (!reg) return 'General'
    const u = reg.toUpperCase()
    if (u.includes('HIPAA')) return 'HIPAA'
    if (u.includes('HITRUST')) return 'HITRUST'
    if (u.includes('SOC')) return 'SOC 2'
    return reg
  }
  const grouped = rules.reduce<Record<string, PolicyRule[]>>((acc, r) => {
    const key = normalizeReg(r.regulation); if (!acc[key]) acc[key] = []; acc[key].push(r); return acc
  }, {})

  // Regulation order: known regs first, General only if non-empty
  const regOrder = ['HIPAA', 'HITRUST', 'SOC 2', 'General']
  const sortedRegs = [
    ...regOrder.filter(k => grouped[k] && (k !== 'General' || grouped[k].length > 0)),
    ...Object.keys(grouped).filter(k => !regOrder.includes(k)),
  ]

  const knownRegs = sortedRegs.filter(k => k !== 'General')
  const totalRules = rules.length
  const activeRules = rules.filter(r => r.enabled).length
  const overallOk = totalRules === 0 || activeRules === totalRules

  return (
    <div className="space-y-6">
      {/* Overall posture banner */}
      <div className={`rounded-xl border p-4 flex items-center gap-4 ${overallOk ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-yellow-500/30 bg-yellow-500/5'}`}>
        <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${overallOk ? 'bg-emerald-500/15' : 'bg-yellow-500/15'}`}>
          {overallOk ? <CheckCircle2 size={20} className="text-emerald-400" /> : <AlertTriangle size={20} className="text-yellow-400" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${overallOk ? 'text-emerald-400' : 'text-yellow-400'}`}>
            {overallOk ? 'Compliance posture: Healthy' : 'Compliance posture: Needs attention'}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {activeRules} of {totalRules} rules enforced across {knownRegs.length} framework{knownRegs.length !== 1 ? 's' : ''} · Rules are locked to regulatory standards
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
          <Lock size={11} /> Standards enforced
        </div>
      </div>

      {/* One-click template packs (only shown if no regulation rules loaded yet) */}
      {sortedRegs.filter(k => k !== 'General').length === 0 && (
        <PolicyTemplatePacks onApplied={load} />
      )}

      {/* Regulation cards */}
      {sortedRegs.length === 0
        ? <Empty message="No policy rules configured" />
        : sortedRegs.map(reg => {
          const regRules = grouped[reg]
          const meta = REGULATION_META[reg] ?? REGULATION_META['General']
          const healthEntry = health?.regulations?.[reg.toLowerCase().replace(/ /g, '_')] ?? health?.regulations?.[reg.toLowerCase()]
          const activeCount = regRules.filter(r => r.enabled).length
          const isCustom = reg === 'General'
          const isExpanded = expanded === reg

          const statusColor = isCustom
            ? 'text-muted-foreground'
            : activeCount === regRules.length ? 'text-emerald-400' : 'text-yellow-400'
          const statusLabel = isCustom ? `${activeCount}/${regRules.length} active` : activeCount === regRules.length ? 'Compliant' : `${regRules.length - activeCount} gap${regRules.length - activeCount !== 1 ? 's' : ''}`

          return (
            <div key={reg} className={`rounded-xl border ${meta.border} ${meta.bg} overflow-hidden`}>
              {/* Card header */}
              <button
                className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-white/[0.02] transition-colors"
                onClick={() => setExpanded(isExpanded ? null : reg)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-sm font-bold ${meta.color}`}>{meta.label}</span>
                    {!isCustom && <span className="text-[10px] px-2 py-0.5 rounded-full border border-current/20 bg-current/10 text-muted-foreground font-medium flex items-center gap-1"><Lock size={9} /> Enforced</span>}
                    <span className={`text-xs font-semibold ml-auto ${statusColor}`}>{statusLabel}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{meta.desc}</p>
                  {healthEntry?.missing_rules && healthEntry.missing_rules.length > 0 && (
                    <p className="text-[10px] text-yellow-400 mt-1 flex items-center gap-1"><AlertTriangle size={9} /> Missing: {healthEntry.missing_rules.slice(0, 3).join(', ')}{healthEntry.missing_rules.length > 3 ? ` +${healthEntry.missing_rules.length - 3} more` : ''}</p>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <p className="text-lg font-bold tabular-nums">{activeCount}<span className="text-xs text-muted-foreground font-normal">/{regRules.length}</span></p>
                    <p className="text-[10px] text-muted-foreground">rules active</p>
                  </div>
                  <ChevronRight size={15} className={`text-muted-foreground transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                </div>
              </button>

              {/* Expanded rule list */}
              {isExpanded && (
                <div className="border-t border-current/10 px-5 py-3 space-y-1">
                  {regRules.map(rule => (
                    <div key={rule.rule_id} className="flex items-start gap-3 py-2.5 border-b border-white/5 last:border-0">
                      <div className={`mt-0.5 shrink-0 ${rule.enabled ? 'text-emerald-400' : 'text-muted-foreground/40'}`}>
                        <CheckCircle2 size={13} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium">{rule.name}</p>
                        {rule.description && <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{rule.description}</p>}
                      </div>
                      <div className="shrink-0 flex items-center gap-1.5">
                        {!isCustom && <span className="text-[10px] text-muted-foreground/50 flex items-center gap-0.5"><Lock size={9} /> Required</span>}
                        <span className={`text-[10px] font-medium ${rule.enabled ? 'text-emerald-400' : 'text-muted-foreground/50'}`}>
                          {rule.enabled ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })
      }

      {/* Custom rules note */}
      {sortedRegs.length > 0 && (
        <p className="text-[11px] text-muted-foreground/60 flex items-center gap-1.5 px-1">
          <Lock size={10} /> Regulatory rules (HIPAA, HITRUST, SOC 2) are enforced as healthcare standards and cannot be disabled.
        </p>
      )}
    </div>
  )
}

// ── Review Queue Tab ──────────────────────────────────────────────────────────

function ReviewTab() {
  const [pending, setPending] = useState<ReviewItem[]>([])
  const [resolved, setResolved] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [resolving, setResolving] = useState<string | null>(null)
  const [deptFilter, setDeptFilter] = useState('all')
  const [confirmItem, setConfirmItem] = useState<{ item: ReviewItem; action: 'approved' | 'rejected' } | null>(null)
  const [note, setNote] = useState('')
  const [pinStage, setPinStage] = useState<'none' | 'pin' | 'setup'>('none')
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)
  const [reviewerName, setReviewerNameLocal] = useState(getReviewerName)
  const [editingName, setEditingName] = useState(!getReviewerName())

  const showToast = (msg: string, type: 'ok' | 'err' = 'ok') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [pRes, aRes, rRes] = await Promise.allSettled([
        api.reviewQueue('pending'), api.reviewQueue('approved'), api.reviewQueue('rejected'),
      ])
      if (pRes.status === 'fulfilled') setPending(pRes.value?.queue ?? [])
      const approved = aRes.status === 'fulfilled' ? aRes.value?.queue ?? [] : []
      const rejected = rRes.status === 'fulfilled' ? rRes.value?.queue ?? [] : []
      setResolved([...approved, ...rejected].sort((a, b) => new Date(b.resolved_at ?? b.created_at).getTime() - new Date(a.resolved_at ?? a.created_at).getTime()).slice(0, 20))
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load review queue') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv) }, [load])

  const handleExpired = useCallback(async (item: ReviewItem) => {
    try {
      await api.rejectReview(item.decision_id, 'SYSTEM', `Auto-denied: SLA timeout (${getUrgency(item)})`)
      showToast(`Auto-denied: ${item.action_type}`, 'err'); load()
    } catch { /* already resolved */ }
  }, [load])

  const handleAction = (item: ReviewItem, action: 'approved' | 'rejected') => {
    if (!reviewerName.trim()) { setEditingName(true); showToast('Set your reviewer name first', 'err'); return }
    setNote(''); setConfirmItem({ item, action }); setPinStage(hasPinSet() ? 'pin' : 'setup')
  }

  const handleConfirm = async () => {
    if (!confirmItem) return
    const { item, action } = confirmItem
    setResolving(item.decision_id); setConfirmItem(null)
    try {
      const reviewerSignature = getReviewerDept() ? `${reviewerName} (${getReviewerDept()})` : reviewerName
      action === 'approved'
        ? await api.approveReview(item.decision_id, reviewerSignature, note || undefined)
        : await api.rejectReview(item.decision_id, reviewerSignature, note || undefined)
      showToast(`${action === 'approved' ? 'Approved' : 'Rejected'}: ${item.action_type}`, action === 'approved' ? 'ok' : 'err')
      load()
    } catch (e) { showToast(e instanceof Error ? e.message : 'Request failed', 'err') }
    finally { setResolving(null) }
  }

  const saveName = (name: string) => { setReviewerName(name); setReviewerNameLocal(name); setEditingName(false) }

  const allDepts = Array.from(new Set(pending.map(getDept))).sort()
  const filtered = deptFilter === 'all' ? pending : pending.filter(i => getDept(i) === deptFilter)
  const grouped = (['critical', 'urgent', 'routine'] as const)
    .map(u => ({ urgency: u, items: filtered.filter(i => getUrgency(i) === u) })).filter(g => g.items.length > 0)

  return (
    <div className="space-y-4">
      {/* Reviewer identity */}
      <div className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border text-xs ${reviewerName ? 'border-border bg-secondary/50' : 'border-amber-500/30 bg-amber-500/10'}`}>
        <User size={12} className={reviewerName ? 'text-muted-foreground' : 'text-amber-400'} />
        {editingName ? (
          <form className="flex items-center gap-2 flex-1" onSubmit={e => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem('name') as HTMLInputElement).value.trim(); if (v) saveName(v) }}>
            <input name="name" defaultValue={reviewerName} autoFocus placeholder="Your name for review signatures…"
              className="flex-1 bg-transparent border-b border-primary/40 text-sm focus:outline-none text-foreground pb-0.5" />
            <button type="submit" className="text-primary text-xs font-semibold hover:underline">Save</button>
          </form>
        ) : (
          <>
            <span className="text-muted-foreground">Reviewing as</span>
            <span className="font-medium text-foreground">{reviewerName}</span>
            {getReviewerDept() && (
              <>
                <span className="text-border">·</span>
                <span className="text-muted-foreground">{getReviewerDept()}</span>
              </>
            )}
          </>
        )}
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardList size={16} className="text-amber-400" />
          <span className="text-sm font-medium">Review Queue</span>
          {pending.length > 0 && <span className="flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-red-500 text-[10px] font-bold text-white">{pending.length}</span>}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {Object.entries(SLA_MS).map(([u, ms]) => (
            <span key={u} className="flex items-center gap-1 px-2 py-0.5 rounded border border-white/10 bg-white/[0.02]">
              <Clock size={9} /> <span className="capitalize">{u}</span> {ms >= 3600000 ? ms / 3600000 + 'h' : ms / 60000 + 'm'}
            </span>
          ))}
          <button onClick={load} className="text-muted-foreground hover:text-foreground transition ml-1"><RefreshCcw size={13} /></button>
        </div>
      </div>

      {allDepts.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <Filter size={12} className="text-muted-foreground" />
          {['all', ...allDepts].map(d => (
            <button key={d} onClick={() => setDeptFilter(d)}
              className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${deptFilter === d ? 'bg-primary/20 border-primary/40 text-primary' : 'border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20'}`}>
              {d === 'all' ? `All · ${pending.length}` : d}
              {d !== 'all' && <span className="ml-1 text-muted-foreground/60">· {pending.filter(i => getDept(i) === d).length}</span>}
            </button>
          ))}
        </div>
      )}

      {error && <div className="flex items-center gap-2 text-sm text-red-400 px-4 py-3 rounded-xl border border-red-500/30 bg-red-500/10"><AlertCircle size={15} />{error}</div>}
      {loading && <Spinner />}

      {!loading && filtered.length === 0 && !error && (
        <div className="flex flex-col items-center gap-3 py-20 rounded-2xl border border-white/[0.08] bg-white/[0.02]">
          <CheckCircle2 size={32} className="text-emerald-400" />
          <p className="font-semibold">All caught up</p>
          <p className="text-sm text-muted-foreground">No escalated actions require review.</p>
        </div>
      )}

      {!loading && grouped.map(({ urgency, items }) => {
        const cfg = URGENCY_CFG[urgency]
        return (
          <div key={urgency} className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${cfg.dot} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />
              <h3 className={`text-sm font-semibold ${urgency === 'critical' ? 'text-red-400' : urgency === 'urgent' ? 'text-amber-400' : 'text-sky-400'}`}>{cfg.label}</h3>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${cfg.badge}`}>{items.length}</span>
            </div>
            <AnimatePresence>
              {items.map(item => {
                const busy = resolving === item.decision_id
                return (
                  <motion.div key={item.decision_id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                    className={`glass-card p-4 border ${urgency === 'critical' ? 'border-red-500/25' : urgency === 'urgent' ? 'border-amber-500/25' : 'border-sky-500/20'}`}>
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium font-mono truncate">{item.action_type}</p>
                        <p className="text-xs text-muted-foreground truncate">{item.agent_id}{item.meta?.patient_id ? ` · ${item.meta.patient_id}` : ''}</p>
                      </div>
                      <SlaTimer item={item} onExpired={handleExpired} />
                      <button disabled={busy} onClick={() => handleAction(item, 'approved')} title="Approve"
                        className="flex items-center justify-center w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-40 transition-colors">
                        {busy ? <div className="w-3.5 h-3.5 border border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" /> : <ThumbsUp size={11} />}
                      </button>
                      <button disabled={busy} onClick={() => handleAction(item, 'rejected')} title="Reject"
                        className="flex items-center justify-center w-7 h-7 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 disabled:opacity-40 transition-colors">
                        {busy ? <div className="w-3.5 h-3.5 border border-red-400/30 border-t-red-400 rounded-full animate-spin" /> : <ThumbsDown size={11} />}
                      </button>
                    </div>
                    {item.escalation_question && <p className="text-xs text-muted-foreground mt-2 pl-5">{item.escalation_question}</p>}
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
        )
      })}

      {!loading && resolved.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2"><Activity size={13} /> Recently Resolved</h3>
          <div className="glass-card overflow-hidden divide-y divide-white/[0.04]">
            {resolved.map(item => (
              <div key={item.decision_id} className="flex items-center gap-3 px-4 py-2.5 text-xs">
                {item.resolution === 'approved' ? <CheckCircle2 size={12} className="text-emerald-400 shrink-0" /> : <XCircle size={12} className="text-red-400 shrink-0" />}
                <span className="font-mono flex-1 truncate">{item.action_type}</span>
                <span className="text-muted-foreground truncate hidden sm:block">{item.agent_id}</span>
                <span className={item.resolved_by === 'SYSTEM' ? 'text-muted-foreground' : item.resolution === 'approved' ? 'text-emerald-400' : 'text-red-400'}>
                  {item.resolution === 'approved' ? 'Approved' : 'Rejected'}{item.resolved_by ? ` · ${item.resolved_by}` : ''}
                </span>
                {item.resolved_at && <span className="text-muted-foreground/60 hidden md:block">{relTime(item.resolved_at)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
            className={`fixed bottom-6 right-6 z-[200] px-4 py-3 rounded-xl border shadow-xl text-sm font-medium ${toast.type === 'ok' ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400' : 'bg-red-500/20 border-red-500/30 text-red-400'}`}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* PIN modal */}
      <AnimatePresence>
        {pinStage !== 'none' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <PinModal mode={pinStage === 'setup' ? 'setup' : 'verify'} onSuccess={() => setPinStage('none')} onCancel={() => { setPinStage('none'); setConfirmItem(null) }} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confirm modal */}
      <AnimatePresence>
        {confirmItem && pinStage === 'none' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirmItem(null)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
              className="relative z-10 glass-card max-w-md w-full p-6 space-y-4">
              <div className="flex items-center gap-3">
                {confirmItem.action === 'approved' ? <CheckCircle2 size={20} className="text-emerald-400" /> : <XCircle size={20} className="text-red-400" />}
                <div>
                  <h3 className="font-semibold">{confirmItem.action === 'approved' ? 'Approve' : 'Reject'} this action?</h3>
                  <p className="text-xs text-muted-foreground font-mono mt-0.5">{confirmItem.item.action_type}</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <User size={11} /> Signed as <span className="text-foreground font-medium">{reviewerName}</span>
              </p>
              {confirmItem.action === 'rejected' && (
                <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="Rejection note (optional)…"
                  className="w-full bg-white/[0.04] border border-white/15 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none" />
              )}
              <div className="flex gap-3">
                <button onClick={() => setConfirmItem(null)} className="flex-1 py-2 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Cancel</button>
                <button onClick={handleConfirm}
                  className={`flex-1 py-2 rounded-xl text-sm font-semibold transition-colors ${confirmItem.action === 'approved' ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/30' : 'bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30'}`}>
                  Confirm {confirmItem.action === 'approved' ? 'Approval' : 'Rejection'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Red Team Tab ─────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'text-red-400 bg-red-500/10 border-red-500/30',
  advisory: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  stable:   'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
}
const PERTURB_LABEL: Record<string, string> = {
  prompt_injection:    'Prompt Injection',
  malformed_payload:   'Malformed Payload',
  boundary_input:      'Boundary Input',
  privilege_escalation:'Priv. Escalation',
  context_poisoning:   'Context Poisoning',
}

function RedTeamTab() {
  const [summary, setSummary]   = useState<import('./api').ShadowSummary | null>(null)
  const [findings, setFindings] = useState<import('./api').ShadowFinding[]>([])
  const [bypasses, setBypasses] = useState<import('./api').ConfirmedBypass[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [filter, setFilter]     = useState<'all' | 'critical' | 'advisory'>('all')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [chainRunning, setChainRunning] = useState(false)
  const [chainResult, setChainResult]   = useState<import('./api').ChainStressResponse | null>(null)
  const [chainError, setChainError]     = useState('')
  const [exporting, setExporting]       = useState(false)
  const [chainOpen, setChainOpen]       = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const [s, f, b] = await Promise.all([
        api.shadowSummary(),
        api.shadowFindings(undefined, 200),
        api.confirmedBypasses(),
      ])
      setSummary(s)
      setFindings(f.findings)
      setBypasses(b.confirmed_bypasses)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await api.shadowExport()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `edon_shadow_report_${Date.now()}.csv`
      a.click(); URL.revokeObjectURL(url)
    } catch (e) { alert(e instanceof Error ? e.message : 'Export failed') }
    finally { setExporting(false) }
  }

  const handleChainStress = async () => {
    if (!sessionId.trim()) return
    setChainRunning(true); setChainError(''); setChainResult(null)
    try {
      const r = await api.chainStress(sessionId.trim())
      setChainResult(r)
    } catch (e) { setChainError(e instanceof Error ? e.message : 'Chain stress failed') }
    finally { setChainRunning(false) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg message={error} onRetry={load} />

  const visible = filter === 'all' ? findings : findings.filter(f => f.severity === filter)

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <FlaskConical size={14} className="text-primary" /> Red Team
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">Adversarial shadow execution — continuous governance testing</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition">
            <RefreshCw size={13} />
          </button>
          <button onClick={handleExport} disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-muted/40 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition disabled:opacity-50">
            <FileDown size={13} />{exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Critical Findings', value: summary?.critical ?? 0,             icon: AlertTriangle, color: 'text-red-400',     highlight: (summary?.critical ?? 0) > 0 },
          { label: 'Advisory Findings', value: summary?.advisory ?? 0,             icon: AlertCircle,   color: 'text-amber-400',   highlight: false },
          { label: 'Confirmed Bypasses',value: summary?.confirmed_bypasses ?? 0,   icon: ShieldAlert,   color: 'text-red-400',     highlight: (summary?.confirmed_bypasses ?? 0) > 0 },
          { label: 'Governor Drift',    value: summary?.non_determinism_count ?? 0,icon: Activity,      color: 'text-blue-400',    highlight: false },
        ].map(s => (
          <div key={s.label} className={`glass-card p-4 ${s.highlight ? 'border-red-500/30' : ''}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <s.icon size={15} className={s.color} />
            </div>
            <p className={`text-2xl font-semibold ${s.value > 0 && s.highlight ? 'text-red-400' : ''}`}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Confirmed bypasses — top priority */}
      {bypasses.length > 0 && (
        <div className="glass-card border-red-500/30 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ShieldAlert size={14} className="text-red-400" />
            <h3 className="text-sm font-semibold text-red-400">Confirmed Bypasses</h3>
            <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 font-bold">
              {bypasses.length} REAL
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            These bypasses are not theoretical — the perturbation bypassed the governor AND the agent executed successfully.
          </p>
          <div className="space-y-2">
            {bypasses.map(b => (
              <div key={b.id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs space-y-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-muted-foreground">{b.agent_id}</span>
                  <span className="text-border">·</span>
                  <span className="font-medium">{b.action_type}</span>
                  <span className="text-border">·</span>
                  <span className="text-red-400/80">{PERTURB_LABEL[b.perturbation_type] ?? b.perturbation_type}</span>
                  <span className="ml-auto text-muted-foreground/60">{b.confirmed_at.slice(0, 10)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 rounded border border-red-500/30 text-red-400 font-mono">{b.original_verdict}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-400 font-mono">{b.shadow_verdict}</span>
                  <span className="text-muted-foreground mx-1">·</span>
                  <span className="text-emerald-400">Real execution: {b.real_outcome}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Findings table */}
      <div className="glass-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">Findings</h3>
          <div className="ml-auto flex rounded-lg border border-border overflow-hidden text-xs">
            {(['all', 'critical', 'advisory'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`px-3 py-1.5 capitalize transition ${filter === f ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
                {f === 'all' ? `All (${findings.length})` : f === 'critical' ? `Critical (${summary?.critical ?? 0})` : `Advisory (${summary?.advisory ?? 0})`}
              </button>
            ))}
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="flex flex-col items-center py-10 gap-3 text-center">
            <CheckCircle2 size={28} className="text-emerald-400 opacity-40" />
            <p className="text-sm text-muted-foreground">
              {filter === 'all' ? 'No findings yet — traces are being sampled.' : `No ${filter} findings.`}
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {visible.slice(0, 50).map(f => {
              const key = `${f.trace_id}-${f.perturbation_name}`
              const isOpen = expanded === key
              return (
                <div key={key} className={`rounded-lg border text-xs overflow-hidden transition-colors ${SEVERITY_COLOR[f.severity]}`}>
                  <button className="w-full flex items-center gap-3 p-3 text-left" onClick={() => setExpanded(isOpen ? null : key)}>
                    <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${SEVERITY_COLOR[f.severity]}`}>
                      {f.severity}
                    </span>
                    <span className="font-medium truncate">{f.action_type ?? '—'}</span>
                    <span className="text-muted-foreground/70 shrink-0">{PERTURB_LABEL[f.perturbation_type] ?? f.perturbation_type}</span>
                    <span className="text-muted-foreground/50 mx-1 shrink-0">
                      {f.trace_original_verdict} → {f.shadow_verdict}
                    </span>
                    <ChevronRight size={12} className={`ml-auto shrink-0 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  </button>
                  {isOpen && (
                    <div className="px-3 pb-3 space-y-2 border-t border-current/10 pt-2">
                      {(f.findings ?? []).map((txt, i) => (
                        <p key={i} className="text-muted-foreground leading-relaxed">{txt}</p>
                      ))}
                      {f.policy_recommendation && (
                        <div className="mt-2 p-2 rounded bg-primary/5 border border-primary/20 text-primary/80">
                          <span className="font-semibold text-primary">Policy recommendation: </span>
                          {f.policy_recommendation}
                        </div>
                      )}
                      <p className="text-muted-foreground/40">{f.created_at?.slice(0, 19).replace('T', ' ')} · field: {f.perturbed_field ?? '—'}</p>
                    </div>
                  )}
                </div>
              )
            })}
            {visible.length > 50 && (
              <p className="text-center text-xs text-muted-foreground py-2">
                Showing 50 of {visible.length} findings — export CSV for full report
              </p>
            )}
          </div>
        )}
      </div>

      {/* Chain stress panel */}
      <div className="glass-card p-4 space-y-3">
        <button className="w-full flex items-center gap-2 text-sm font-semibold" onClick={() => setChainOpen(v => !v)}>
          <Zap size={14} className="text-primary" /> Session Chain Stress Test
          <ChevronRight size={13} className={`ml-auto text-muted-foreground transition-transform ${chainOpen ? 'rotate-90' : ''}`} />
        </button>

        {chainOpen && (
          <div className="space-y-3 pt-1">
            <p className="text-xs text-muted-foreground">
              Inject adversarial perturbations at each step of a session and observe whether the effect cascades downstream.
              Use the <code className="bg-muted px-1 rounded">session_id</code> from your agent context (format: <code className="bg-muted px-1 rounded">auto:AGENT_ID:YYYYMMDDH</code>).
            </p>
            <div className="flex gap-2">
              <input
                value={sessionId} onChange={e => setSessionId(e.target.value)}
                placeholder="auto:agent_crm:2026041112"
                className="flex-1 text-xs bg-background border border-border rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary/50 font-mono"
              />
              <button onClick={handleChainStress} disabled={chainRunning || !sessionId.trim()}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary/15 border border-primary/30 text-primary text-xs font-semibold hover:bg-primary/25 transition disabled:opacity-40">
                {chainRunning ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />}
                {chainRunning ? 'Running…' : 'Run'}
              </button>
            </div>
            {chainError && <p className="text-xs text-red-400">{chainError}</p>}
            {chainResult && (
              <div className="space-y-2">
                {chainResult.message ? (
                  <p className="text-xs text-muted-foreground">{chainResult.message}</p>
                ) : chainResult.summary && (
                  <>
                    <div className="grid grid-cols-4 gap-2">
                      {[
                        { label: 'Tests run', value: chainResult.summary.total_tests },
                        { label: 'Critical',  value: chainResult.summary.critical,  color: chainResult.summary.critical > 0 ? 'text-red-400' : undefined },
                        { label: 'Advisory',  value: chainResult.summary.advisory,  color: chainResult.summary.advisory > 0 ? 'text-amber-400' : undefined },
                        { label: 'Max cascade', value: chainResult.summary.max_cascade },
                      ].map(s => (
                        <div key={s.label} className="glass-card p-2 text-center">
                          <p className={`text-lg font-bold ${s.color ?? ''}`}>{s.value}</p>
                          <p className="text-[10px] text-muted-foreground">{s.label}</p>
                        </div>
                      ))}
                    </div>
                    {chainResult.results.filter(r => r.severity !== 'stable').map((r, i) => (
                      <div key={i} className={`rounded-lg border p-3 text-xs ${SEVERITY_COLOR[r.severity]}`}>
                        <div className="flex items-center gap-2">
                          <span className="font-bold uppercase">{r.severity}</span>
                          <span>Step {r.injection_step} → {r.cascade_count} cascade{r.cascade_count !== 1 ? 's' : ''}</span>
                          <span className="text-muted-foreground ml-1">{PERTURB_LABEL[r.perturbation_type] ?? r.perturbation_type}</span>
                        </div>
                        {r.cascade_verdicts.map((cv, j) => (
                          <div key={j} className="mt-1.5 pl-2 border-l border-current/20 text-muted-foreground">
                            Step {cv.step} · {cv.action_type} · {cv.original} → {cv.shadow}
                          </div>
                        ))}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tabs config ───────────────────────────────────────────────────────────────

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: Activity },
  { id: 'decisions', label: 'Decisions', icon: ListChecks },
  { id: 'agents',    label: 'Agents',    icon: Users },
  { id: 'audit',     label: 'Audit',     icon: FileText },
  { id: 'policies',  label: 'Policies',  icon: Shield },
  { id: 'review',    label: 'Review',    icon: ClipboardList },
  { id: 'redteam',   label: 'Red Team',  icon: FlaskConical },
  { id: 'settings',  label: 'Settings',  icon: Settings },
] as const

type Tab = typeof TABS[number]['id']

// ── Live Key Claim Banner ─────────────────────────────────────────────────────

function LiveKeyClaimBanner() {
  const [pending, setPending] = useState(false)
  const [claiming, setClaiming] = useState(false)
  const [liveKey, setLiveKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    api.checkPendingLiveKey().then(r => setPending(r.pending)).catch(() => {})
  }, [])

  const claim = async () => {
    setClaiming(true)
    try {
      const r = await api.claimLiveKey()
      setLiveKey(r.key)
      setPending(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to claim key')
    } finally { setClaiming(false) }
  }

  const copy = () => {
    if (!liveKey) return
    navigator.clipboard.writeText(liveKey)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  if (dismissed || (!pending && !liveKey)) return null

  return (
    <AnimatePresence>
      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
        className="border-b border-emerald-500/40 bg-emerald-500/10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <Zap size={15} className="text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">You're ready to go live</span>
          </div>

          {!liveKey ? (
            <>
              <p className="text-xs text-emerald-300/80 flex-1">Your live production key is ready. Claim it now — it will only be shown once.</p>
              <button onClick={claim} disabled={claiming}
                className="shrink-0 flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {claiming ? 'Claiming…' : 'Reveal my live key'}
              </button>
            </>
          ) : (
            <>
              <div className="flex-1 flex items-center gap-2 min-w-0">
                <code className="flex-1 text-xs font-mono bg-black/30 rounded px-3 py-1.5 truncate text-emerald-300">{liveKey}</code>
                <button onClick={copy} className="shrink-0 p-1.5 rounded border border-emerald-500/30 hover:bg-emerald-500/10 transition-colors">
                  {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} className="text-emerald-400" />}
                </button>
              </div>
              <p className="text-[11px] text-emerald-300/60 shrink-0">Switch to this key to enable enforcement</p>
              <button onClick={() => setDismissed(true)} className="shrink-0 p-1 text-emerald-400/50 hover:text-emerald-400 transition-colors">
                <X size={14} />
              </button>
            </>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [authed, setAuthed] = useState(!!getAuth())
  const [meInfo, setMeInfo] = useState<MeResponse | null>(null)
  const isAdmin = meInfo?.is_admin === true || meInfo?.role === 'admin'
  const [tab, setTab] = useState<Tab>('dashboard')
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('edon_theme') as 'dark' | 'light') || 'dark')
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number } | null>(null)
  const [hgiHalt, setHgiHalt] = useState(() => localStorage.getItem('edon_hgi_halt') === 'true')
  const [lockdownConfirm, setLockdownConfirm] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('edon_theme', theme)
  }, [theme])

  useEffect(() => {
    if (!authed) return
    api.health().then(h => setHealth(h)).catch(() => {})
    api.me().then(m => setMeInfo(m)).catch(() => {})
    const fetchCount = async () => { try { const r = await api.reviewQueue('pending'); setPendingCount(r?.count ?? 0) } catch { /* silent */ } }
    fetchCount(); const iv = setInterval(fetchCount, 30000); return () => clearInterval(iv)
  }, [authed])

  const handleLogout = useCallback(() => { clearAuth(); setAuthed(false); setHealth(null); setMeInfo(null) }, [])

  // Session timeout
  const { warning: sessionWarn, secondsLeft, extend } = useSessionTimeout(handleLogout)

  const activateLockdown = () => { localStorage.setItem('edon_hgi_halt', 'true'); setHgiHalt(true); setLockdownConfirm(false) }
  const liftLockdown = () => { localStorage.removeItem('edon_hgi_halt'); setHgiHalt(false) }

  if (!authed) return <LoginScreen onLogin={() => setAuthed(true)} />

  const auth = getAuth()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Lockdown banner */}
      <AnimatePresence>
        {hgiHalt && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="flex items-center justify-between px-6 py-1.5 bg-red-500/15 border-b border-red-500/30">
            <div className="flex items-center gap-2 text-red-400 text-xs">
              <AlertTriangle size={13} className="animate-pulse shrink-0" />
              <span className="font-bold tracking-wider">EMERGENCY LOCKDOWN ACTIVE</span>
              <span className="text-red-400/60 hidden sm:inline">— all agent actions suspended</span>
            </div>
            <button onClick={liftLockdown} className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-red-400 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 transition-colors">
              Lift Lockdown
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 flex items-center gap-3 h-14">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Shield size={14} className="text-primary" />
            </div>
            <span className="text-sm font-semibold edon-brand tracking-widest">EDON</span>
            <span className="text-xs text-muted-foreground hidden sm:block">Console</span>
          </div>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-0.5 px-1 py-0.5 rounded-xl bg-muted/40 border border-border/40">
            {TABS.map(t => {
              const Icon = t.icon; const active = tab === t.id
              return (
                <button key={t.id} onClick={() => setTab(t.id)} title={t.label}
                  className={`nav-item relative flex items-center justify-center w-9 h-8 rounded-lg ${active ? 'nav-item-active' : ''}`}>
                  <Icon size={15} />
                  {t.id === 'review' && pendingCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                      {pendingCount > 9 ? '9+' : pendingCount}
                    </span>
                  )}
                </button>
              )
            })}
          </nav>

          <div className="flex items-center gap-2 ml-auto shrink-0">
            {health && (
              <div className="hidden lg:flex items-center gap-1.5 text-xs text-muted-foreground">
                <div className={`w-1.5 h-1.5 rounded-full animate-pulse-dot ${health.ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span>{health.ok ? 'Healthy' : 'Degraded'}</span>
                <span className="text-border">·</span>
                <span>v{health.version}</span>
              </div>
            )}

            {/* Reviewer identity pill */}
            {getReviewerName() && (
              <div className="hidden sm:flex items-center gap-1.5 px-2.5 h-7 rounded-full border border-border bg-secondary/60 text-xs text-muted-foreground">
                <User size={11} />
                <span className="font-medium text-foreground max-w-[100px] truncate">{getReviewerName()}</span>
                {isAdmin && (
                  <span className="px-1.5 py-0 rounded-full text-[9px] font-bold tracking-wider bg-primary/15 text-primary border border-primary/30">ADMIN</span>
                )}
                {!isAdmin && getReviewerDept() && (
                  <>
                    <span className="text-border">·</span>
                    <span className="max-w-[90px] truncate">{getReviewerDept()}</span>
                  </>
                )}
              </div>
            )}

            {/* Notifications */}
            <NotificationsBell />

            {/* AI Chat */}
            <button onClick={() => setChatOpen(true)} title="Governance AI"
              className="flex items-center justify-center w-8 h-8 rounded-xl border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary transition-colors">
              <Bot size={14} />
            </button>

            {/* Lockdown */}
            <button onClick={() => hgiHalt ? liftLockdown() : setLockdownConfirm(true)}
              title={hgiHalt ? 'Lockdown active — click to lift' : 'Emergency lockdown'}
              className={`hidden sm:flex items-center gap-1.5 px-2.5 h-8 rounded-xl border text-xs font-semibold transition-colors ${hgiHalt ? 'border-red-500/50 bg-red-500/20 text-red-400 animate-pulse' : 'border-red-500/25 bg-red-500/10 text-red-400/70 hover:text-red-400 hover:bg-red-500/15'}`}>
              <Power size={12} />{hgiHalt ? 'LOCKDOWN' : 'Lockdown'}
            </button>

            {/* Theme toggle */}
            <button onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition">
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>

            {/* Logout */}
            <button onClick={handleLogout} title="Disconnect"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition">
              <LogOut size={14} />
            </button>

            {/* Mobile hamburger */}
            <button onClick={() => setMobileOpen(v => !v)}
              className="flex md:hidden items-center justify-center w-8 h-8 rounded-lg border border-border bg-secondary hover:bg-muted transition-colors">
              {mobileOpen ? <X size={15} /> : <Menu size={15} />}
            </button>
          </div>
        </div>

        {/* Mobile nav drawer */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-border bg-background/95 overflow-hidden">
              <nav className="px-4 py-3 flex flex-col gap-1">
                {TABS.map(t => {
                  const Icon = t.icon; const active = tab === t.id
                  return (
                    <button key={t.id} onClick={() => { setTab(t.id); setMobileOpen(false) }}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'}`}>
                      <Icon size={15} />{t.label}
                      {t.id === 'review' && pendingCount > 0 && <span className="ml-auto flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">{pendingCount}</span>}
                    </button>
                  )
                })}
                <div className="border-t border-border/50 mt-1 pt-2">
                  <button onClick={() => { liftLockdown(); setMobileOpen(false) }}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm w-full transition-colors ${hgiHalt ? 'text-red-400 bg-red-500/10' : 'text-red-400/60 hover:text-red-400 hover:bg-red-500/10'}`}>
                    <Power size={15} />{hgiHalt ? 'Lift Lockdown' : 'Lockdown'}
                  </button>
                </div>
              </nav>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* Live key claim banner */}
      {meInfo?.is_sandbox && <LiveKeyClaimBanner />}

      {/* Sandbox banner */}
      <AnimatePresence>
        {meInfo?.is_sandbox && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="bg-purple-500/10 border-b border-purple-500/30">
            <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center gap-3">
              <div className="flex items-center gap-2 text-purple-300">
                <FlaskConical size={14} className="shrink-0" />
                <span className="text-xs font-semibold">Sandbox Mode</span>
              </div>
              <p className="text-xs text-purple-300/80">
                Your governance rules are active and logging every decision — but nothing is being blocked yet. This is your trial period to observe EDON in action before enforcement goes live.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Page content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.15 }}>
            <ErrorBoundary>
              {tab === 'dashboard' && <DashboardTab />}
              {tab === 'decisions' && <DecisionsTab />}
              {tab === 'agents'    && <AgentsTab />}
              {tab === 'audit'     && <AuditTab />}
              {tab === 'policies'  && <PoliciesTab />}
              {tab === 'review'    && <ReviewTab />}
              {tab === 'redteam'   && <RedTeamTab />}
              {tab === 'settings'  && <SettingsTab onReconnect={() => api.health().then(h => setHealth(h)).catch(() => {})} isAdmin={isAdmin} />}
            </ErrorBoundary>
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="border-t border-border/30 py-3 px-4 text-center">
        <p className="text-xs text-muted-foreground flex items-center justify-center gap-1.5">
          <Zap size={10} className="text-primary" /> EDON Governance Console
          <span className="text-border">·</span>
          <span className="font-mono">{auth?.gatewayUrl?.replace('https://', '')}</span>
        </p>
      </footer>

      {/* Chat */}
      <AnimatePresence>
        {chatOpen && <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} tab={tab} />}
      </AnimatePresence>

      {/* Session timeout warning */}
      <AnimatePresence>
        {sessionWarn && (
          <motion.div initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.97 }} transition={{ duration: 0.2 }}
            className="fixed bottom-6 right-6 z-[200] w-72 rounded-2xl border border-amber-500/30 bg-background/95 backdrop-blur-xl shadow-2xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/25 flex items-center justify-center shrink-0">
                <AlertTriangle size={14} className="text-amber-400" />
              </div>
              <div>
                <p className="text-sm font-semibold">Session expiring</p>
                <p className="text-xs text-muted-foreground">Inactivity detected</p>
              </div>
            </div>
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <Clock size={12} className="text-amber-400 shrink-0" />
              <span className="text-xs text-amber-400 font-mono font-semibold">
                {Math.floor(secondsLeft / 60) > 0 ? `${Math.floor(secondsLeft / 60)}m ${String(secondsLeft % 60).padStart(2, '0')}s` : `${secondsLeft}s`} remaining
              </span>
            </div>
            <div className="flex gap-2">
              <button onClick={handleLogout} className="flex-1 py-1.5 rounded-xl border border-white/10 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Sign out now</button>
              <button onClick={extend} className="flex-1 py-1.5 rounded-xl bg-amber-500/20 border border-amber-500/30 text-amber-400 text-xs font-semibold hover:bg-amber-500/30 transition-colors">Stay signed in</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Lockdown confirmation */}
      <AnimatePresence>
        {lockdownConfirm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setLockdownConfirm(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
              className="relative z-10 glass-card max-w-sm w-full p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/15 border border-red-500/30 flex items-center justify-center shrink-0">
                  <AlertTriangle size={20} className="text-red-400" />
                </div>
                <div>
                  <h2 className="text-lg font-bold">Activate Emergency Lockdown?</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Immediately suspends all agent actions.</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">All AI agent actions will be blocked system-wide until the lockdown is lifted. This is logged to your audit trail.</p>
              <div className="flex gap-3">
                <button onClick={() => setLockdownConfirm(false)} className="flex-1 py-2.5 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Cancel</button>
                <button onClick={activateLockdown} className="flex-1 py-2.5 rounded-xl bg-red-500/20 border border-red-500/40 text-red-400 text-sm font-bold hover:bg-red-500/30 transition-colors">Activate Lockdown</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
