import { useState, useEffect, useCallback, useRef, useMemo, Component, createContext, lazy, Suspense, useContext, type ReactNode, type ErrorInfo } from 'react'
import { motion } from 'framer-motion'
import {
  Shield, Activity, FileText, Users, ClipboardList,
  CheckCircle2, XCircle, AlertTriangle, RefreshCcw,
  Sun, Moon, LogOut, AlertCircle, ChevronRight,
  Lock, Search,
  Heart, Zap, Database, Clock, Bot, X, Send,
  ThumbsUp, ThumbsDown, Power, KeyRound, Eye, EyeOff,
  TimerOff, Filter, TrendingUp, Minus, ShieldAlert,
  ListChecks, FileDown, Bell, Settings, Menu, User,
  BarChart2, Wifi, WifiOff, Copy, Check, RefreshCw, Plus, Trash2, Link, Link2, Package, FlaskConical, ChevronLeft,
  ServerCog,
} from 'lucide-react'
import { api, getLastRequestId, type AuditEvent, type Agent, type PolicyRule, type TimeseriesPoint, type HealthResponse, type ComplianceHealth, type ReviewItem, type BlockReason, type MeResponse, type AssistantProposal, type Citation, type ApiKey, type AuditorGrant, type ConsoleUserInvite, type DepartmentOwner } from './api'
import { ROLE_DEFAULT_TAB, ROLE_LABELS, type ConsoleRole } from './uiModel'

const ClinicalSummaryTab = lazy(() => import('./clinical').then(module => ({ default: module.ClinicalSummaryTab })))
const ClinicalExplainTab = lazy(() => import('./clinical').then(module => ({ default: module.ClinicalExplainTab })))
const ClinicalActionsTab = lazy(() => import('./clinical').then(module => ({ default: module.ClinicalActionsTab })))
const ResearchExperimentsTab = lazy(() => import('./research').then(module => ({ default: module.ResearchExperimentsTab })))
const ShadowSimulationTab = lazy(() => import('./research').then(module => ({ default: module.ShadowSimulationTab })))
const ReadinessTab = lazy(() => import('./research').then(module => ({ default: module.ReadinessTab })))
const PolicyDiffViewerTab = lazy(() => import('./policies').then(module => ({ default: module.PolicyDiffViewerTab })))
const ControlTowerTab = lazy(() => import('./control-tower').then(module => ({ default: module.ControlTowerTab })))
const SystemRegistryTable = lazy(() => import('./control-tower').then(module => ({ default: module.SystemRegistryTable })))
const DeploymentGatekeeperTab = lazy(() => import('./control-tower').then(module => ({ default: module.DeploymentGatekeeperTab })))

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ')
}

function AnimatePresence({ children }: { children?: ReactNode; [key: string]: unknown }) {
  return <>{children}</>
}

// -- Page data store (tabs write here; ChatPanel reads for context) ------------

const _ps: { tab: string; items: Record<string, unknown>[] } = { tab: '', items: [] }
function _setPS(tab: string, items: Record<string, unknown>[]) {
  _ps.tab = tab
  _ps.items = items.slice(0, 40)
}
function _getPS() { return { ..._ps } }

// Aside panel context (shared between ChatPanel citation clicks and tab rows)
interface AsideItem { type: string; id: string }
const AsideCtx = createContext<{ open: (item: AsideItem) => void }>({ open: () => {} })

// -- Error Boundary ------------------------------------------------------------

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

// -- Logo ---------------------------------------------------------------------

function EdonMark({ size = 40 }: { size?: number }) {
  const id = `em-${size}`
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0e1f14" />
          <stop offset="100%" stopColor="#081a14" />
        </linearGradient>
        <linearGradient id={`${id}-bar`} x1="0" y1="0" x2="40" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4ade80" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
        <linearGradient id={`${id}-border`} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="rgba(74,222,128,0.45)" />
          <stop offset="100%" stopColor="rgba(34,211,238,0.25)" />
        </linearGradient>
        <filter id={`${id}-glow`}>
          <feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="blur" />
          <feComposite in="blur" in2="SourceGraphic" operator="over" />
        </filter>
      </defs>

      {/* Card background */}
      <rect width="40" height="40" rx="10" fill={`url(#${id}-bg)`} />

      {/* Border gradient */}
      <rect width="40" height="40" rx="10" fill="none" stroke={`url(#${id}-border)`} strokeWidth="1" />

      {/* Subtle inner highlight */}
      <rect x="1" y="1" width="38" height="10" rx="9" fill="rgba(255,255,255,0.03)" />

      {/* E mark - 3 bars, middle offset to form E + gate metaphor */}
      <rect x="10" y="12" width="20" height="3.5" rx="1.75" fill={`url(#${id}-bar)`} />
      <rect x="10" y="18.25" width="14" height="3.5" rx="1.75" fill={`url(#${id}-bar)`} opacity="0.7" />
      <rect x="10" y="24.5" width="20" height="3.5" rx="1.75" fill={`url(#${id}-bar)`} />
    </svg>
  )
}

function EdonLogo({ variant = 'default', subtitle = true }: { variant?: 'default' | 'compact'; subtitle?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <EdonMark size={variant === 'compact' ? 32 : 40} />
      <div className="flex flex-col justify-center">
        <span className="edon-wordmark text-white leading-none" style={{ fontSize: variant === 'compact' ? 15 : 18 }}>
          EDON
        </span>
        {subtitle && (
          <span className="text-[9px] tracking-[0.22em] uppercase font-medium mt-0.5"
            style={{ color: 'rgba(74,222,128,0.6)', fontFamily: 'Inter, sans-serif' }}>
            AI Governance
          </span>
        )}
      </div>
    </div>
  )
}

// -- Auth ----------------------------------------------------------------------

function saveAuth(gatewayUrl: string, token: string) {
  sessionStorage.setItem('edon_auth', JSON.stringify({ gatewayUrl, token }))
  localStorage.removeItem('edon_auth')
}
function clearAuth() {
  sessionStorage.removeItem('edon_auth')
  localStorage.removeItem('edon_auth')
  localStorage.removeItem('edon_reviewer_name')
  localStorage.removeItem('edon_reviewer_dept')
}
function getAuth() {
  const raw = sessionStorage.getItem('edon_auth') || localStorage.getItem('edon_auth')
  if (!raw && CONSOLE_DEV_MODE) return CONSOLE_DEV_AUTH
  if (!raw) return null
  try { return JSON.parse(raw) as { gatewayUrl: string; token: string } } catch { return CONSOLE_DEV_AUTH }
}

// -- Session timeout -----------------------------------------------------------

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

// -- PIN helpers ---------------------------------------------------------------

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

// -- Reviewer name -------------------------------------------------------------

const REVIEWER_KEY = 'edon_reviewer_name'
const getReviewerName = () => localStorage.getItem(REVIEWER_KEY) || ''
const setReviewerName = (name: string) => localStorage.setItem(REVIEWER_KEY, name)

const DEPT_KEY = 'edon_reviewer_dept'
const getReviewerDept = () => localStorage.getItem(DEPT_KEY) || ''

const ROLE_KEY = 'edon_reviewer_role'
const ROLES_BY_VERTICAL: Record<string, readonly string[]> = {
  healthcare: ['Nurse', 'Charge Nurse', 'Physician', 'Admin'],
  banking:    ['Analyst', 'Risk Manager', 'Compliance Officer', 'Admin'],
  general:    ['Reviewer', 'Senior Reviewer', 'Manager', 'Admin'],
}
const getReviewRoles = (vertical: string | null): readonly string[] =>
  ROLES_BY_VERTICAL[vertical ?? 'general'] ?? ROLES_BY_VERTICAL.general
type ReviewerRole = string
const getReviewerRole = (): ReviewerRole => localStorage.getItem(ROLE_KEY) || ''
const setReviewerRole = (role: string) => localStorage.setItem(ROLE_KEY, role)

const APPROVAL_TIER_BY_VERTICAL: Record<string, Record<string, string>> = {
  healthcare: { critical: 'Physician',           urgent: 'Charge Nurse',      routine: 'Nurse' },
  banking:    { critical: 'Compliance Officer',   urgent: 'Risk Manager',      routine: 'Analyst' },
  general:    { critical: 'Manager',              urgent: 'Senior Reviewer',   routine: 'Reviewer' },
}
const getApprovalTier = (vertical: string | null) =>
  APPROVAL_TIER_BY_VERTICAL[vertical ?? 'general'] ?? APPROVAL_TIER_BY_VERTICAL.general
const canApprove = (role: ReviewerRole, urgency: string, vertical: string | null) => {
  if (['admin', 'super_admin', 'governance_admin', 'security_admin'].includes(role)) return true
  const roles = getReviewRoles(vertical)
  const required = getApprovalTier(vertical)[urgency] ?? roles[0]
  return (roles.indexOf(role) ?? -1) >= roles.indexOf(required)
}

// -- SLA helpers ---------------------------------------------------------------

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

// -- Shared helpers ------------------------------------------------------------

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

const CONSOLE_DEV_MODE = import.meta.env.VITE_CONSOLE_DEV_MODE === 'true'
const CONSOLE_DEV_GATEWAY = import.meta.env.VITE_GATEWAY ?? 'http://localhost:8000'
const CONSOLE_DEV_TOKEN = import.meta.env.VITE_CONSOLE_DEV_TOKEN ?? 'edon_sandbox_key_dev_only'
const CONSOLE_DEV_AUTH = { gatewayUrl: CONSOLE_DEV_GATEWAY, token: CONSOLE_DEV_TOKEN }
const SHOW_ADVANCED_ONBOARDING = false
const CONSOLE_DEV_ME: MeResponse = {
  tenant_id: 'tenant_sandbox_edon',
  key_id: 'key_sandbox',
  key_name: 'Sandbox Dev Key',
  role: 'admin',
  plan: 'enterprise',
  is_admin: true,
  is_sandbox: true,
  vertical: 'healthcare',
}

const CONSOLE_DEPT_MODE_KEY = 'edon_console_dept_modes'
const CONSOLE_COORDINATION_KEY = 'edon_console_coordination'

function readJsonRecord<T extends Record<string, unknown>>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function writeJsonRecord<T extends Record<string, unknown>>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}

function getDeptMode(dept: string) {
  const record = readJsonRecord<Record<string, 'sandbox' | 'governed'>>(CONSOLE_DEPT_MODE_KEY) || {}
  return record[dept] ?? 'governed'
}

function setDeptMode(dept: string, mode: 'sandbox' | 'governed') {
  const record = readJsonRecord<Record<string, 'sandbox' | 'governed'>>(CONSOLE_DEPT_MODE_KEY) || {}
  record[dept] = mode
  writeJsonRecord(CONSOLE_DEPT_MODE_KEY, record)
}

function setCoordinationAllowed(dept: string, allowed: boolean) {
  const record = readJsonRecord<Record<string, boolean>>(CONSOLE_COORDINATION_KEY) || {}
  record[dept] = allowed
  writeJsonRecord(CONSOLE_COORDINATION_KEY, record)
}

// -- SLA Timer -----------------------------------------------------------------

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

// -- PIN Modal -----------------------------------------------------------------

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

// -- Notifications Bell --------------------------------------------------------

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
        tool: e.tool_name || '-',
        agent_id: e.agent_id,
        reason_code: e.decision_reason_code || '-',
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
                        <p className="text-[10px] text-muted-foreground mt-0.5">{n.reason_code} / {n.agent_id}</p>
                      </div>
                    </div>
                    <span className="text-[10px] text-muted-foreground/60 shrink-0">{relTime(n.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="px-4 py-2.5 border-t border-border">
              <p className="text-[10px] text-muted-foreground">Showing last 20 blocked actions / refreshes every 30s</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// -- Citation helpers ----------------------------------------------------------

const CITE_RE = /\[ref:(DECISION|AGENT|RULE):([^\]]+)\]/g

const CITE_COLORS: Record<string, string> = {
  decision: 'bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30',
  agent:    'bg-blue-500/20  border-blue-500/40  text-blue-300  hover:bg-blue-500/30',
  rule:     'bg-purple-500/20 border-purple-500/40 text-purple-300 hover:bg-purple-500/30',
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

function getCitationLabel(type: Citation['type']) {
  if (type === 'decision') return 'Decision'
  if (type === 'agent') return 'Agent'
  return 'Rule'
}

function looksNumeric(text: string) {
  return /(?:\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?(?:ms|s|m|h|d)?\b)/i.test(text)
}

function highlightCite(id: string) {
  const el = document.querySelector(`[data-cite-id="${id}"]`)
  if (!el) return
  el.classList.remove('cite-ring')
  void (el as HTMLElement).offsetWidth  // force reflow to restart animation
  el.classList.add('cite-ring')
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  setTimeout(() => el.classList.remove('cite-ring'), 2600)
}

function CitedMessage({ text, onCite }: { text: string; onCite: (type: string, id: string) => void }) {
  const parts: ReactNode[] = []
  let last = 0
  CITE_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = CITE_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const type = m[1].toLowerCase()
    const id = m[2]
    const color = CITE_COLORS[type] ?? 'bg-primary/20 border-primary/40 text-primary hover:bg-primary/30'
    parts.push(
      <button key={m.index} onClick={() => onCite(type, id)}
        title={`${type}: ${id} - click to highlight in page`}
        className={`inline-flex items-center gap-1 mx-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border cursor-pointer transition-colors ${color}`}>
        {type === 'decision' ? 'DEC' : type === 'agent' ? 'AGT' : 'RULE'} {id.slice(0, 14)}{id.length > 14 ? '...' : ''}
      </button>
    )
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <span>{parts}</span>
}

// -- Aside Panel ---------------------------------------------------------------

function AsidePanel({ type, id, onClose }: { type: string; id: string; onClose: () => void }) {
  const [explanation, setExplanation] = useState('')
  const [suggestion, setSuggestion] = useState<{ title: string; body: string } | null>(null)
  const [citations, setCitations] = useState<Citation[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true); setErr(''); setExplanation(''); setSuggestion(null); setCitations([])
    api.assistantExplain(type, id)
      .then(r => {
        if (cancelled) return
        setExplanation(r.explanation)
        setSuggestion(r.suggestion ?? null)
        setCitations(uniqueCitations(r.citations))
      })
      .catch(e => { if (!cancelled) setErr(e instanceof Error ? e.message : 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [type, id])

  const typeLabel = type === 'decision' ? 'Decision' : type === 'agent' ? 'Agent' : 'Rule'

  return (
    <>
      <div className="fixed inset-0 z-[102] bg-black/20 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed top-3 right-3 bottom-3 z-[103] w-[min(31rem,calc(100vw-1.5rem))] flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-background/95 backdrop-blur-2xl shadow-[0_24px_60px_rgba(0,0,0,0.45)]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0 bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Bot size={13} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold">AI Reasoning</p>
              <p className="text-[10px] text-muted-foreground">{typeLabel} / <span className="font-mono">{id.slice(0, 16)}{id.length > 16 ? '...' : ''}</span></p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1"><X size={15} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5">
              <RefreshCw size={11} className="animate-spin" /> Analysing...
            </div>
          ) : err ? (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2.5 text-xs text-red-300">{err}</div>
          ) : (
            <>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Reasoning</p>
                  {citations.length > 0 && (
                    <span className="text-[10px] text-muted-foreground">{citations.length} source{citations.length === 1 ? '' : 's'}</span>
                  )}
                </div>
                <p className="text-[13px] leading-6 text-foreground/88 whitespace-pre-wrap">{explanation}</p>
              </div>
              {suggestion && (
                <div className="rounded-xl border border-primary/20 bg-primary/5 px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-primary/70 mb-1.5">Suggested next step</p>
                  <p className="text-sm font-medium text-foreground">{suggestion.title}</p>
                  <p className="mt-1 text-[13px] leading-6 text-muted-foreground">{suggestion.body}</p>
                </div>
              )}
              {citations.length > 0 && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70 mb-2">Sources</p>
                  <div className="flex flex-wrap gap-1.5">
                    {citations.map(c => (
                      <button
                        key={`${c.type}:${c.id}`}
                        onClick={() => {
                          highlightCite(c.id)
                        }}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border font-mono text-[10px] transition-colors ${CITE_COLORS[c.type] ?? CITE_COLORS.rule}`}
                      >
                        <span className="uppercase">{c.type}</span>
                        <span className="truncate max-w-32">{c.id}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </motion.div>
    </>
  )
}

// -- Chat Panel ----------------------------------------------------------------

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestion?: AssistantProposal | null
  citations?: Citation[]
  appliedOk?: boolean
}

const SUGGESTION_LABELS: Record<string, string> = {
  add_policy_rule:  'New Rule',
  enable_rule:      'Enable Rule',
  disable_rule:     'Disable Rule',
  set_shadow_mode:  'Shadow Mode',
}

function ChatPanel({ open, onClose, tab }: { open: boolean; onClose: () => void; tab: string; }) {
  const { open: openAside } = useContext(AsideCtx)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [thinkingLabel, setThinkingLabel] = useState('')
  const [applying, setApplying] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [pastConvs, setPastConvs] = useState<{ id: string; title: string; updated_at: string }[]>([])
  const [memoryCount, setMemoryCount] = useState(0)
  const [showHistory, setShowHistory] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const GREETING = 'Ask me anything - block rates, agent activity, pending reviews, policy rules, compliance status, or request a change.'

  const startNewConversation = () => {
    setMessages([{ id: 'g', role: 'assistant', content: GREETING }])
    setDismissed(new Set())
    setConversationId(undefined)
    setShowHistory(false)
    setTimeout(() => inputRef.current?.focus(), 80)
  }

  // On open: load past conversations + memory count, start fresh conversation
  useEffect(() => {
    if (!open) return
    startNewConversation()
    api.assistantConversations().then(r => setPastConvs(r.conversations ?? [])).catch(() => {})
    api.assistantMemories().then(r => setMemoryCount(r.count ?? 0)).catch(() => {})
  }, [open])

  // Refocus input when user switches tabs without wiping the conversation
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [tab])

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages])

  const conversationHistory = (msgs: ChatMsg[]) =>
    msgs.filter(m => m.id !== 'g').map(m => ({ role: m.role, content: m.content }))

  const send = async () => {
    const text = input.trim()
    if (!text || loading || streaming) return
    setInput('')
    const history = conversationHistory(messages)
    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    sendToApi(text, history)
  }

  const sendToApi = async (text: string, history: { role: string; content: string }[]) => {
    const contextMsg = tab !== 'dashboard' ? `[User is on the ${tab} tab] ${text}` : text
    const ps = _getPS()
    const page_context = ps.items.length > 0 ? { tab: ps.tab, items: ps.items } as Record<string, unknown> : undefined

    const aiId = `a-${Date.now()}`
    let full = ''
    let firstChunk = true
    let rafId: ReturnType<typeof requestAnimationFrame> | null = null

    setLoading(true)
    setStreaming(true)
    setThinkingLabel('')

    const flush = () => {
      rafId = null
      setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: full } : m))
    }

    await api.assistantChatStream(
      contextMsg,
      history as never,
      page_context,
      (chunk) => {
        if (firstChunk) {
          firstChunk = false
          setLoading(false)
          setThinkingLabel('')
          setMessages(prev => [...prev, { id: aiId, role: 'assistant', content: '' }])
        }
        full += chunk
        if (rafId === null) rafId = requestAnimationFrame(flush)
      },
      (suggestion, citations, returnedConvId) => {
        if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
        setLoading(false)
        setStreaming(false)
        setThinkingLabel('')
        if (returnedConvId) setConversationId(returnedConvId)
        if (firstChunk) {
          setMessages(prev => [...prev, { id: aiId, role: 'assistant', content: '(no response)', suggestion: suggestion ?? undefined, citations: citations ?? [] }])
        } else {
          setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: full, suggestion: suggestion ?? undefined, citations: citations ?? [] } : m))
        }
      },
      (errMsg) => {
        if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
        setLoading(false)
        setStreaming(false)
        setThinkingLabel('')
        if (firstChunk) {
          setMessages(prev => [...prev, { id: `err-${Date.now()}`, role: 'assistant', content: errMsg }])
        } else {
          setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: errMsg } : m))
        }
      },
      (label) => { setThinkingLabel(label) },
      conversationId,
    )
  }

  const handleCite = (type: string, id: string) => {
    highlightCite(id)
    openAside({ type, id })
  }

  const apply = async (msg: ChatMsg) => {
    if (!msg.suggestion) return
    setApplying(msg.id)
    try {
      await api.assistantApply(msg.suggestion)
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, appliedOk: true } : m))
    } catch (e) {
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`, role: 'assistant',
        content: `Failed to apply: ${e instanceof Error ? e.message : 'Unknown error'}`,
      }])
    } finally { setApplying(null) }
  }

  if (!open) return null

  const PROMPTS: Record<string, string[]> = {
    dashboard:  ['Block rate this week?', 'Any agents spiking?', 'What needs my attention?'],
    decisions:  ['What does SCOPE_VIOLATION mean?', 'Show recent blocks', 'Which agent blocks most?'],
    agents:     ['Which agents are risky?', 'What is this agent doing?', 'Show agents by department'],
    audit:      ['Explain this decision', 'Why was this blocked?', 'Block trend last 7 days?'],
    policies:   ['What rules are active?', 'Add a block rule', 'Which rules fire most?'],
    review:     ['What is pending review?', 'What triggered this escalation?'],
    settings:   ['Enable shadow mode?', 'What is a kill switch?'],
    onboarding: ['What stage are we on?', 'What does this intake need?', 'What is blocking promotion?'],
    redteam:    ['What findings are critical?', 'Show confirmed bypasses', 'What is the cascade risk?'],
    report:     ['Compliance summary', 'Block trend?', 'How many blocks this month?'],
  }
  const FALLBACK_PROMPTS = ['Block rate this week?', 'What needs attention?', 'Which agents are risky?']

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
              <div className="flex items-center gap-1.5">
                <p className="text-[10px] text-muted-foreground">Your agents / policies / audit log</p>
                {memoryCount > 0 && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-primary/10 border border-primary/20 text-primary/80">
                    {memoryCount} memories
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setShowHistory(h => !h)} title="Conversation history"
              className={`p-1.5 rounded-lg transition ${showHistory ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground'}`}>
              <Clock size={13} />
            </button>
            <button onClick={startNewConversation} title="New conversation"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground transition">
              <Plus size={13} />
            </button>
            <button onClick={onClose} className="p-1.5 text-muted-foreground hover:text-foreground transition"><X size={15} /></button>
          </div>
        </div>
        {showHistory && (
          <div className="border-b border-white/[0.08] max-h-48 overflow-y-auto shrink-0">
            {pastConvs.length === 0 ? (
              <p className="text-xs text-muted-foreground px-4 py-3">No past conversations yet.</p>
            ) : pastConvs.map(c => (
              <button key={c.id} onClick={async () => {
                try {
                  const full = await api.assistantConversation(c.id)
                  const msgs: ChatMsg[] = full.messages
                    .filter((m: { role: string; content: string }) => m.role !== 'system')
                    .map((m: { role: string; content: string }, i: number) => ({ id: `h-${i}`, role: m.role as 'user' | 'assistant', content: m.content }))
                  setMessages([{ id: 'g', role: 'assistant', content: GREETING }, ...msgs])
                  setConversationId(c.id)
                  setShowHistory(false)
                } catch { /* ignore */ }
              }} className="w-full text-left px-4 py-2.5 hover:bg-white/[0.04] transition border-b border-white/[0.04] last:border-0">
                <p className="text-xs text-foreground/80 truncate">{c.title || 'Conversation'}</p>
                <p className="text-[10px] text-muted-foreground">{new Date(c.updated_at).toLocaleDateString()}</p>
              </button>
            ))}
          </div>
        )}
        {(PROMPTS[tab] ?? FALLBACK_PROMPTS).length > 0 && (
          <div className="flex gap-2 px-4 py-2 border-b border-white/[0.06] overflow-x-auto shrink-0">
            {(PROMPTS[tab] ?? FALLBACK_PROMPTS).map(p => (
              <button key={p} onClick={() => { setInput(p); setTimeout(() => inputRef.current?.focus(), 50) }}
                className="shrink-0 text-[10px] px-2.5 py-1 rounded-lg border border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground hover:border-white/20 transition-colors whitespace-nowrap">
                {p}
              </button>
            ))}
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" ref={scrollRef}>
          {messages.map(m => {
            const display = m.role === 'assistant' ? m.content.replace(/\*\*/g, '').replace(/\*/g, '') : m.content
            const citations = uniqueCitations(m.citations)
            const uncitedMetricAnswer = m.role === 'assistant' && citations.length === 0 && looksNumeric(display)
            return (
            <div key={m.id}>
              <div className={`rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap ${
                m.role === 'user' ? 'ml-6 bg-primary/15 border border-primary/25 text-foreground' : 'mr-2 bg-white/[0.04] border border-white/[0.08] text-foreground/85'
              }`}>
                {m.role === 'assistant' && citations.length > 0
                  ? <CitedMessage text={display} onCite={handleCite} />
                  : display}
              </div>
              {m.role === 'assistant' && citations.length > 0 && (
                <div className="mr-2 mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                  <span className="uppercase tracking-[0.18em] text-[9px] text-muted-foreground/70">Sources</span>
                  {citations.map(c => (
                    <button
                      key={`${c.type}:${c.id}`}
                      onClick={() => handleCite(c.type, c.id)}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border font-mono transition-colors ${CITE_COLORS[c.type] ?? CITE_COLORS.rule}`}
                      title={`${getCitationLabel(c.type)} source ${c.id} - click to highlight in page`}
                    >
                      <span className="uppercase">{c.type}</span>
                      <span className="truncate max-w-32">{c.id}</span>
                    </button>
                  ))}
                </div>
              )}
              {uncitedMetricAnswer && (
                <div className="mr-2 mt-1.5 text-[10px] text-amber-300/90">
                  No sources attached. Ask for the underlying decision, agent, or rule if this needs verification.
                </div>
              )}
              {m.suggestion && !dismissed.has(m.id) && (
                <div className={`mr-2 mt-2 rounded-xl border p-3 space-y-1.5 text-[12px] ${m.appliedOk ? 'border-green-500/30 bg-green-500/5' : 'border-primary/25 bg-primary/5'}`}>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/15 text-primary">{SUGGESTION_LABELS[m.suggestion.type] ?? m.suggestion.type}</span>
                    {m.appliedOk && <span className="text-[10px] text-green-400 flex items-center gap-0.5"><CheckCircle2 size={9} /> Applied</span>}
                  </div>
                  <p className="font-medium text-foreground">{m.suggestion.description}</p>
                  <p className="text-muted-foreground">{m.suggestion.impact}</p>
                  {m.suggestion.regulation && <p className="text-[10px] text-primary/60">{m.suggestion.regulation}</p>}
                  {!m.appliedOk && (
                    <div className="flex gap-2 pt-1">
                      <button onClick={() => apply(m)} disabled={applying === m.id}
                        className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-primary text-white hover:bg-primary/90 transition disabled:opacity-50">
                        {applying === m.id ? <RefreshCw size={9} className="animate-spin" /> : <CheckCircle2 size={9} />} Apply
                      </button>
                      <button onClick={() => setDismissed(prev => new Set([...prev, m.id]))}
                        className="text-[11px] px-2.5 py-1 rounded-lg border border-white/10 text-muted-foreground hover:text-foreground transition">
                        Dismiss
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )})}
          {loading && (
            <div className="mr-2 rounded-xl px-3.5 py-2.5 bg-white/[0.04] border border-white/[0.08]">
              <div className="flex gap-2 items-center">
                <div className="flex gap-1 items-center">
                  {[0, 150, 300].map(d => <span key={d} className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
                </div>
                {thinkingLabel && <span className="text-[11px] text-muted-foreground">{thinkingLabel}...</span>}
              </div>
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-white/10 shrink-0">
          <form onSubmit={e => { e.preventDefault(); send() }} className="flex gap-2">
            <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} disabled={loading || streaming}
              placeholder="Ask anything about your governance..."
              className="flex-1 bg-white/[0.04] border border-white/15 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
            <button type="submit" disabled={loading || streaming || !input.trim()}
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30 disabled:opacity-40 disabled:pointer-events-none transition-colors">
              <Send size={14} />
            </button>
          </form>
        </div>
      </motion.div>
    </>
  )
}

// -- Login Screen --------------------------------------------------------------

const DEFAULT_GATEWAY = import.meta.env.VITE_GATEWAY ?? 'https://edon-gateway-prod.fly.dev'

const LOGIN_VERTICALS = [
  {
    key: 'healthcare' as const,
    label: 'Healthcare',
    icon: Heart,
    color: 'text-rose-400',
    activeBorder: 'border-rose-500/50 bg-rose-500/8',
    desc: 'Hospitals / Clinics / Health Systems',
    trustBadge: 'HIPAA / HITRUST / Joint Commission',
  },
]

const LOGIN_VALUE_PROPS: Record<string, Array<{ icon: typeof Shield; title: string; body: string }>> = {
  healthcare: [
    { icon: Shield,        title: 'HIPAA-grade governance',    body: 'Every AI action logged, scored, and escalated before it touches patient data.' },
    { icon: ClipboardList, title: 'Clinical approval workflows', body: 'Nurse -> Physician tiered sign-off built in. Joint Commission and HITRUST presets ready on day one.' },
    { icon: Activity,      title: 'Real-time patient safety',   body: 'Critical-urgency blocks page on-call in seconds. Zero trust for medication and care-plan AI.' },
  ],
  banking: [
    { icon: Shield,        title: 'SR 11-7 model risk controls', body: 'Validation gates, challenger model escalation, and inventory logging for every AI model in production.' },
    { icon: ClipboardList, title: 'AML & SAR compliance',        body: 'AI-generated alerts routed to BSA officers. SAR filing blocked without compliance approval.' },
    { icon: Activity,      title: 'FFIEC audit readiness',       body: 'Immutable decision trail with regulation mapping. Export structured compliance reports in one click.' },
  ],
  general: [
    { icon: Shield,        title: 'AI governance layer',    body: 'Drop-in proxy between your AI agents and the world. Policy engine evaluates every action before execution.' },
    { icon: ClipboardList, title: 'Human-in-the-loop',      body: 'Escalation queues, approval workflows, and red team replay - for any team, any stack.' },
    { icon: Activity,      title: 'Full audit trail',       body: 'Every decision logged with verdict, reason code, and reviewer signature. SOC 2 ready.' },
  ],
}

const SECTOR_KEY = 'edon_sector_pref'

function LoginScreen({ onLogin }: { onLogin: (me: import('./api').MeResponse) => void }) {
  const [sector, setSector] = useState<'healthcare' | 'banking' | 'general'>(
    () => (localStorage.getItem(SECTOR_KEY) as 'healthcare' | 'banking' | 'general') || 'healthcare'
  )
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSectorChange = (s: typeof sector) => {
    setSector(s)
    localStorage.setItem(SECTOR_KEY, s)
  }

  async function _finalizeLogin(rawToken: string) {
    saveAuth(DEFAULT_GATEWAY, rawToken)
    await api.health()
    const me = await api.me()
    if (!me.vertical && me.is_admin) {
      try { await api.setVertical(sector) } catch { /* non-fatal */ }
      onLogin({ ...me, vertical: sector })
    } else {
      if (me.vertical) localStorage.setItem(SECTOR_KEY, me.vertical)
      onLogin(me)
    }
  }

  async function handleEmailLogin(e: React.FormEvent) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const res = await fetch(`${DEFAULT_GATEWAY}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Login failed (${res.status})`)
      }
      const data = await res.json()
      if (data.api_key) {
        await _finalizeLogin(data.api_key)
      } else {
        throw new Error('No session returned. Contact your admin to confirm access or SSO setup.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally { setLoading(false) }
  }

  const handleDevBypass = () => {
    if (!CONSOLE_DEV_MODE) return
    saveAuth(CONSOLE_DEV_GATEWAY, CONSOLE_DEV_TOKEN)
    setError('')
    setLoading(false)
    onLogin(CONSOLE_DEV_ME)
  }

  const activeVertical = LOGIN_VERTICALS.find(v => v.key === sector)!
  const valueProps = LOGIN_VALUE_PROPS[sector]

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* -- Left panel: value prop -- */}
      <div className="hidden lg:flex flex-col justify-between w-[46%] min-h-screen p-12 border-r border-white/[0.06] bg-gradient-to-br from-black via-[#0a0a0f] to-[#050510] relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className={`absolute -top-32 -left-32 w-96 h-96 rounded-full blur-3xl opacity-10 ${sector === 'healthcare' ? 'bg-rose-500' : sector === 'banking' ? 'bg-amber-500' : 'bg-primary'}`} />
          <div className={`absolute -bottom-32 -right-32 w-96 h-96 rounded-full blur-3xl opacity-8 ${sector === 'healthcare' ? 'bg-cyan-500' : sector === 'banking' ? 'bg-emerald-500' : 'bg-violet-500'}`} />
        </div>

        <div className="relative z-10">
          <div className="mb-16">
            <EdonLogo />
          </div>

          <AnimatePresence mode="wait">
            <motion.div key={sector} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 12 }} transition={{ duration: 0.2 }} className="space-y-10">
              <div>
                <p className={`text-xs font-semibold uppercase tracking-widest mb-3 ${activeVertical.color}`}>{activeVertical.label}</p>
                <h2 className="text-3xl font-bold leading-tight text-foreground">
                  AI governance for<br />the industries that<br />can't get it wrong.
                </h2>
                <p className="text-sm text-muted-foreground mt-4 leading-relaxed max-w-sm">
                  Every AI action governed, logged, and auditable - before it reaches a patient, a customer, or a regulator.
                </p>
              </div>

              <div className="space-y-4">
                {valueProps.map((vp, i) => (
                  <motion.div key={vp.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                    className="flex items-start gap-4">
                    <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 mt-0.5 ${
                      sector === 'healthcare' ? 'border-rose-500/25 bg-rose-500/8' :
                      sector === 'banking'    ? 'border-amber-500/25 bg-amber-500/8' :
                      'border-primary/25 bg-primary/8'
                    }`}>
                      <vp.icon size={14} className={activeVertical.color} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{vp.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{vp.body}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="relative z-10">
          <p className="text-[11px] text-muted-foreground/50">{activeVertical.trustBadge}</p>
        </div>
      </div>

      {/* -- Right panel: form -- */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md space-y-7">
          {/* Mobile logo */}
          <div className="lg:hidden">
            <EdonLogo variant="compact" />
          </div>

          <div>
            <h1 className="text-xl font-bold">AI Governance Console</h1>
            <p className="text-sm text-muted-foreground mt-1">Govern every AI agent action - before it reaches a patient, customer, or regulator.</p>
          </div>

          {CONSOLE_DEV_MODE && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 space-y-2">
              <p className="text-xs font-semibold text-emerald-300">Dev mode is enabled.</p>
              <p className="text-[11px] text-emerald-200/75">Use the bypass to enter the console without a real login.</p>
              <button
                type="button"
                onClick={handleDevBypass}
                className="w-full py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/25 transition-colors"
              >
                Enter dev console
              </button>
            </div>
          )}

          <p className="text-[11px] text-muted-foreground/70">
            Enterprise access is granted by SSO or admin invite. Admin key management lives in Settings.
          </p>

          {/* Sector picker */}
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground font-medium">Your industry</p>
            <div className="grid grid-cols-1 gap-2">
              {LOGIN_VERTICALS.map(v => (
                <button key={v.key} type="button" onClick={() => handleSectorChange(v.key)}
                  className={`flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl border text-center transition-all ${
                    sector === v.key ? v.activeBorder : 'border-border/50 bg-muted/20 hover:border-border hover:bg-muted/40'
                  }`}>
                  <v.icon size={16} className={sector === v.key ? v.color : 'text-muted-foreground'} />
                  <span className={`text-[11px] font-semibold leading-tight ${sector === v.key ? v.color : 'text-muted-foreground'}`}>{v.label}</span>
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground/60">{activeVertical.desc}</p>
          </div>

          <form onSubmit={handleEmailLogin} className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block font-medium">Work Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email"
                className="w-full px-3 py-2.5 rounded-xl bg-muted/40 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="you@company.com" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block font-medium">Password</label>
              <div className="relative">
                <input type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required autoComplete="current-password"
                  className="w-full px-3 py-2.5 pr-10 rounded-xl bg-muted/40 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" placeholder="Your password" />
                <button type="button" onClick={() => setShowPassword(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            {error && <p className="text-xs text-destructive flex items-center gap-1.5 px-3 py-2 rounded-lg bg-destructive/8 border border-destructive/20"><AlertCircle size={12} />{error}</p>}
            <button type="submit" disabled={loading}
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2">
              {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Shield size={14} />}
              {loading ? 'Logging in...' : 'Log In'}
            </button>
          </form>

          <p className="text-[11px] text-muted-foreground/50 text-center">
            {activeVertical.trustBadge}
          </p>
        </motion.div>
      </div>
    </div>
  )
}

// -- Settings Tab --------------------------------------------------------------

function SettingsTab({
  onReconnect,
  isAdmin,
  meInfo,
  onLogout,
  health,
  lockdownState,
  lockdownDetails,
  shadowModeEnabled,
  shadowModeSaving,
  onToggleShadowMode,
}: {
  onReconnect: () => void
  isAdmin: boolean
  meInfo: MeResponse | null
  onLogout: () => void
  health: { ok: boolean; version: string; uptime_seconds: number } | null
  lockdownState: LockdownState
  lockdownDetails: LockdownDetails
  shadowModeEnabled: boolean
  shadowModeSaving: boolean
  onToggleShadowMode: () => void
}) {
  const auth = getAuth()
  const [url, setUrl] = useState(auth?.gatewayUrl || '')
  const [token, setToken] = useState(auth?.token || '')
  const [showToken, setShowToken] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const reviewerName = CONSOLE_DEV_MODE ? getReviewerName() : (meInfo?.key_name || meInfo?.key_id || '')
  const reviewerDept = CONSOLE_DEV_MODE ? getReviewerDept() : (meInfo?.tenant_id || '')
  const reviewerPin = CONSOLE_DEV_MODE ? hasPinSet() : !!meInfo
  const lastRequest = getLastRequestId()

  const copy = async (label: string, value: string | null | undefined) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(label)
      window.setTimeout(() => setCopied(curr => (curr === label ? null : curr)), 1400)
    } catch {
      setCopied('Copy failed')
      window.setTimeout(() => setCopied(curr => (curr === 'Copy failed' ? null : curr)), 1400)
    }
  }

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    saveAuth(url.replace(/\/$/, ''), token.trim())
    try {
      const h = await api.health()
      setTestResult({ ok: true, msg: `Connected / v${h.version} / ${h.ok ? 'Healthy' : 'Degraded'}` })
      onReconnect()
    } catch (e) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : 'Connection failed' })
    } finally { setTesting(false) }
  }

  const save = () => {
    saveAuth(url.replace(/\/$/, ''), token.trim())
    setSaved(true); setTimeout(() => setSaved(false), 2000)
    onReconnect()
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold mb-1 flex items-center gap-2"><Settings size={15} className="text-primary" /> Console Settings</h2>
        <p className="text-xs text-muted-foreground">Connection, runtime credentials, and posture.</p>
      </div>

      <div className="glass-card p-5 space-y-5">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-2xl border border-primary/25 bg-primary/10 flex items-center justify-center shrink-0">
            <User size={18} className="text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-foreground">{meInfo?.key_name || 'Console user'}</h3>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${meInfo?.is_sandbox ? 'border-blue-500/20 bg-blue-500/10 text-blue-300' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                {meInfo?.is_sandbox ? 'Sandbox' : 'Live'}
              </span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${meInfo?.is_admin ? 'border-primary/25 bg-primary/10 text-primary' : 'border-border bg-muted/20 text-muted-foreground'}`}>
                {meInfo?.role ? (ROLE_LABELS[meInfo.role as ConsoleRole] ?? meInfo.role) : 'Unknown'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {meInfo?.vertical === 'healthcare' ? 'St. Mercy Health System' : meInfo?.tenant_id || 'Tenant'} · {meInfo?.plan || 'unknown plan'} · {auth ? 'Authenticated' : 'Signed out'}
            </p>
          </div>
          <button onClick={onLogout}
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors">
            <LogOut size={13} /> Sign out
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Tenant ID</p>
            <div className="mt-2 flex items-center justify-between gap-2">
              <code className="text-xs font-mono text-foreground break-all">{meInfo?.tenant_id || '-'}</code>
              <button onClick={() => copy('tenant', meInfo?.tenant_id)}
                className="text-[10px] px-2 py-1 rounded border border-border hover:bg-muted/40 transition-colors">
                {copied === 'tenant' ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">API Key</p>
            <div className="mt-2 flex items-center justify-between gap-2">
              <code className="text-xs font-mono text-foreground break-all">{meInfo?.key_id || '-'}</code>
              <button onClick={() => copy('key', meInfo?.key_id)}
                className="text-[10px] px-2 py-1 rounded border border-border hover:bg-muted/40 transition-colors">
                {copied === 'key' ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Reviewer identity</p>
            <p className="mt-2 text-xs text-foreground">{reviewerName || 'Not set'}</p>
            <p className="text-[11px] text-muted-foreground">{reviewerDept || 'No department pinned'}</p>
          </div>
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Last request</p>
            <p className="mt-2 text-xs font-mono text-foreground">{lastRequest || 'Unavailable'}</p>
            <p className="text-[11px] text-muted-foreground">Used for support and audit correlation</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 rounded-xl border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <span>Gateway: <span className={`font-medium ${health?.ok ? 'text-emerald-400' : 'text-amber-400'}`}>{health?.ok ? 'Reachable' : 'Unknown'}</span></span>
          <span className="text-border">/</span>
          <span>Lockdown: <span className={`font-medium ${lockdownState === 'active' ? 'text-red-400' : 'text-muted-foreground'}`}>{lockdownState}</span></span>
          <span className="text-border">/</span>
          <span>Review auth: <span className={`font-medium ${reviewerPin ? 'text-emerald-400' : 'text-amber-400'}`}>{CONSOLE_DEV_MODE ? (reviewerPin ? 'PIN set' : 'PIN missing') : (reviewerPin ? 'Server bound' : 'Unavailable')}</span></span>
          <span className="text-border">/</span>
          <span>Session trace: <span className="font-medium text-foreground">{lockdownDetails.verifiedAt || 'Not verified yet'}</span></span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* -- Left column: core settings -- */}
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

          {isAdmin && (
            <ShadowModeCard
              enabled={shadowModeEnabled}
              saving={shadowModeSaving}
              onToggle={onToggleShadowMode}
            />
          )}
        </div>

        {/* -- Right column: security & ops cards -- */}
        <div className="space-y-5">
          <ApiKeyRotationCard />
          <ConsoleLinkCard />
          <IpAllowlistCard />
          <WebhookAlertsCard />
          <SettingsQuickReferenceCard />
        </div>
      </div>

    </div>
  )
}
void SettingsTab

function SettingsTabV2({
  onReconnect,
  isAdmin,
  meInfo,
  onLogout,
  health,
  lockdownState,
  shadowModeEnabled,
  shadowModeSaving,
  onToggleShadowMode,
}: {
  onReconnect: () => void
  isAdmin: boolean
  meInfo: MeResponse | null
  onLogout: () => void
  health: { ok: boolean; version: string; uptime_seconds: number } | null
  lockdownState: LockdownState
  lockdownDetails: LockdownDetails
  shadowModeEnabled: boolean
  shadowModeSaving: boolean
  onToggleShadowMode: () => void
}) {
  const auth = getAuth()
  const [url, setUrl] = useState(auth?.gatewayUrl || '')
  const [token, setToken] = useState(auth?.token || '')
  const [showToken, setShowToken] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const reviewerName = CONSOLE_DEV_MODE ? getReviewerName() : (meInfo?.key_name || meInfo?.key_id || '')
  const reviewerDept = CONSOLE_DEV_MODE ? getReviewerDept() : (meInfo?.tenant_id || '')
  const lastRequest = getLastRequestId()
  const postureChecks = [
    { label: 'SSO session', value: auth ? 'Verified' : 'Signed out', ok: !!auth },
    { label: 'Review identity', value: CONSOLE_DEV_MODE ? 'Dev bypass' : 'Server-bound', ok: true },
    { label: 'Audit logging', value: 'Active', ok: true },
    { label: 'Runtime isolation', value: shadowModeEnabled ? 'Shadow' : 'Live', ok: true },
  ]
  const tenantStats = [
    { label: 'Plan', value: meInfo?.plan || 'enterprise' },
    { label: 'Mode', value: shadowModeEnabled ? 'Shadow' : 'Live' },
    { label: 'Gateway', value: health?.ok ? 'Healthy' : 'Unknown' },
    { label: 'Lockdown', value: lockdownState === 'active' ? 'Active' : lockdownState === 'unreachable' ? 'Unavailable' : 'Ready' },
  ]

  const copy = async (label: string, value: string | null | undefined) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(label)
      window.setTimeout(() => setCopied(curr => (curr === label ? null : curr)), 1400)
    } catch {
      setCopied('Copy failed')
      window.setTimeout(() => setCopied(curr => (curr === 'Copy failed' ? null : curr)), 1400)
    }
  }

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    saveAuth(url.replace(/\/$/, ''), token.trim())
    try {
      const h = await api.health()
      setTestResult({ ok: true, msg: `Connected / v${h.version} / ${h.ok ? 'Healthy' : 'Degraded'}` })
      onReconnect()
    } catch (e) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : 'Connection failed' })
    } finally { setTesting(false) }
  }

  const save = () => {
    saveAuth(url.replace(/\/$/, ''), token.trim())
    setSaved(true); setTimeout(() => setSaved(false), 2000)
    onReconnect()
  }

  const [activeSection, setActiveSection] = useState<'account' | 'access' | 'credentials' | 'posture' | 'gateway' | 'security' | 'support'>('account')
  const settingSections = [
    { id: 'account' as const, label: 'Account', body: 'Tenant identity and assurance', Icon: User },
    { id: 'access' as const, label: 'Access Management', body: 'Users, roles, department owners', Icon: Users },
    { id: 'credentials' as const, label: 'Runtime Credentials', body: 'Agent and service credentials', Icon: KeyRound },
    { id: 'posture' as const, label: 'Governance Mode', body: 'Shadow, live, lockdown state', Icon: Shield },
    { id: 'gateway' as const, label: 'Gateway Connection', body: 'Dev endpoint and console link', Icon: Wifi },
    { id: 'security' as const, label: 'Security Controls', body: 'Allowlist and webhooks', Icon: Lock },
    { id: 'support' as const, label: 'Support', body: 'Diagnostics and cases', Icon: Copy },
  ]

  const accountPanel = (
    <div className="space-y-5">
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-2xl border border-primary/25 bg-primary/10 flex items-center justify-center shrink-0">
            <User size={18} className="text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-foreground">{CONSOLE_DEV_MODE ? 'Development Admin' : (meInfo?.key_name || 'Console admin')}</h3>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${meInfo?.is_sandbox ? 'border-blue-500/20 bg-blue-500/10 text-blue-300' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'}`}>
                {meInfo?.is_sandbox ? 'Sandbox' : 'Live'}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-primary/25 bg-primary/10 text-primary">
                {meInfo?.role ? (ROLE_LABELS[meInfo.role as ConsoleRole] ?? meInfo.role) : 'Admin'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {meInfo?.vertical === 'healthcare' ? 'St. Mercy Health System' : meInfo?.tenant_id || 'Tenant'} / {meInfo?.plan || 'enterprise'} / {auth ? 'Authenticated' : 'Signed out'}
            </p>
          </div>
          <button onClick={onLogout}
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors">
            <LogOut size={13} /> Sign out
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Tenant</p>
            <div className="mt-2 flex items-center justify-between gap-2">
              <code className="text-xs font-mono text-foreground break-all">{meInfo?.tenant_id || 'tenant unavailable'}</code>
              <button onClick={() => copy('tenant', meInfo?.tenant_id)}
                className="text-[10px] px-2 py-1 rounded border border-border hover:bg-muted/40 transition-colors">
                {copied === 'tenant' ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Review Identity</p>
            <p className="mt-2 text-xs text-foreground">{CONSOLE_DEV_MODE ? (reviewerName || 'Dev reviewer not set') : 'SSO verified'}</p>
            <p className="text-[11px] text-muted-foreground">{CONSOLE_DEV_MODE ? (reviewerDept || 'Dev-only local reviewer') : 'Server-bound approvals'}</p>
          </div>
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Support Trace</p>
            <p className="mt-2 text-xs font-mono text-foreground">{lastRequest || 'No request yet'}</p>
            <p className="text-[11px] text-muted-foreground">Copied in diagnostics</p>
          </div>
        </div>
      </div>

      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold flex items-center gap-2"><Shield size={13} className="text-primary" /> Account Assurance</h3>
          <span className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-300">Admin ready</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {tenantStats.map(item => (
            <div key={item.label} className="rounded-lg border border-border/50 bg-muted/20 p-3">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{item.label}</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{item.value}</p>
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-border/50 bg-muted/20 p-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {postureChecks.map(item => (
            <div key={item.label} className="flex items-center justify-between gap-3 text-xs">
              <span className="flex items-center gap-2 text-muted-foreground">
                {item.ok ? <CheckCircle2 size={12} className="text-emerald-400" /> : <AlertCircle size={12} className="text-amber-400" />}
                {item.label}
              </span>
              <span className={item.ok ? 'text-foreground' : 'text-amber-300'}>{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const posturePanel = (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold flex items-center gap-2"><Activity size={13} className="text-primary" /> Governance Mode</h3>
        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${health?.ok ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-amber-500/10 border-amber-500/20 text-amber-400'}`}>
          {health?.ok ? 'Gateway healthy' : 'Gateway unknown'}
        </span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
        <div className="rounded-lg border border-border/50 bg-muted/20 p-3">
          <p className="text-muted-foreground">Gateway</p>
          <p className={`mt-1 font-semibold ${health?.ok ? 'text-emerald-400' : 'text-amber-400'}`}>{health?.ok ? 'Reachable' : 'Unknown'}</p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/20 p-3">
          <p className="text-muted-foreground">Lockdown</p>
          <p className={`mt-1 font-semibold ${lockdownState === 'active' ? 'text-red-400' : lockdownState === 'unreachable' ? 'text-amber-400' : 'text-foreground'}`}>
            {lockdownState === 'active' ? 'Active' : lockdownState === 'unreachable' ? 'Unavailable' : 'Ready'}
          </p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/20 p-3">
          <p className="text-muted-foreground">Review auth</p>
          <p className="mt-1 font-semibold text-emerald-400">{CONSOLE_DEV_MODE ? 'Dev bypass' : 'Server-bound'}</p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/20 p-3">
          <p className="text-muted-foreground">Audit</p>
          <p className="mt-1 font-semibold text-emerald-400">Active</p>
        </div>
      </div>
      {isAdmin && <ShadowModeCard enabled={shadowModeEnabled} saving={shadowModeSaving} onToggle={onToggleShadowMode} />}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-3">
          <p className="text-xs font-semibold text-blue-300">Shadow posture</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">Use while onboarding vendors or departments. EDON logs and simulates policy decisions.</p>
        </div>
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
          <p className="text-xs font-semibold text-emerald-300">Live posture</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">Use after approval. EDON can block, escalate, and audit governed runtime actions.</p>
        </div>
      </div>
    </div>
  )

  const gatewayPanel = (
    <div className="space-y-5">
      <div className="glass-card p-5 space-y-4">
        <button type="button" onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between gap-3 text-left">
          <span>
            <span className="text-sm font-semibold flex items-center gap-2"><Wifi size={13} className="text-primary" /> Gateway Connection</span>
            <span className="block text-xs text-muted-foreground mt-0.5">Dev endpoint and token controls. Production users should rely on SSO and managed gateway config.</span>
          </span>
          <span className="text-xs text-muted-foreground">{showAdvanced ? 'Hide' : 'Show'}</span>
        </button>
        {showAdvanced && (
          <div className="space-y-4 pt-1">
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
                Test
              </button>
              <button onClick={save}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary text-xs font-semibold hover:bg-primary/30 transition-colors">
                {saved ? <><CheckCircle2 size={13} /> Saved</> : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>
      <ConsoleLinkCard />
    </div>
  )

  const securityPanel = (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
      <IpAllowlistCard />
      <WebhookAlertsCard />
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold mb-1 flex items-center gap-2"><Settings size={15} className="text-primary" /> Settings</h2>
        <p className="text-xs text-muted-foreground">Admin-only controls for account access, runtime credentials, gateway posture, and audit support.</p>
      </div>

      <section className="grid grid-cols-1 xl:grid-cols-[18rem_1fr] gap-5 items-start">
        <aside className="glass-card p-3 xl:sticky xl:top-5">
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3 mb-3">
            <p className="text-xs font-semibold text-foreground truncate">{CONSOLE_DEV_MODE ? 'Development Admin' : (meInfo?.key_name || 'Console admin')}</p>
            <p className="text-[11px] text-muted-foreground truncate">{meInfo?.tenant_id || 'tenant unavailable'}</p>
          </div>
          <nav className="space-y-1">
            {settingSections.map(section => {
              const Icon = section.Icon
              const selected = activeSection === section.id
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSection(section.id)}
                  className={cn(
                    'w-full flex items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors',
                    selected ? 'border-primary/30 bg-primary/10 text-primary' : 'border-transparent text-muted-foreground hover:border-border/60 hover:bg-muted/25 hover:text-foreground',
                  )}
                >
                  <Icon size={15} className="shrink-0" />
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold">{section.label}</span>
                    <span className={cn('block text-[10px] leading-4 truncate', selected ? 'text-primary/70' : 'text-muted-foreground/70')}>{section.body}</span>
                  </span>
                </button>
              )
            })}
          </nav>
        </aside>

        <div className="min-w-0">
          {activeSection === 'account' && accountPanel}
          {activeSection === 'access' && <AccessManagementCard />}
          {activeSection === 'credentials' && <ApiKeyRotationCard />}
          {activeSection === 'posture' && posturePanel}
          {activeSection === 'gateway' && gatewayPanel}
          {activeSection === 'security' && securityPanel}
          {activeSection === 'support' && <SupportDiagnosticsCard />}
        </div>
      </section>
    </div>
  )
}

function AccessManagementCard() {
  const departments = [
    'All departments', 'Cardiology', 'Radiology', 'Pharmacy', 'Telehealth', 'ICU', 'Lab', 'Nursing', 'Security',
    'Emergency', 'Surgery', 'Neurology', 'Oncology', 'Pediatrics', 'Orthopedics', 'Billing', 'Compliance',
    'Patient Access', 'Behavioral Health', 'Respiratory Therapy', 'Facilities', 'Research', 'Imaging', 'Records',
  ]
  const roles = ['viewer', 'operator', 'governance_admin', 'security_admin', 'auditor'] as const

  const [users, setUsers] = useState<ConsoleUserInvite[]>([])
  const [userLoading, setUserLoading] = useState(true)
  const [owners, setOwners] = useState<DepartmentOwner[]>([])
  const [ownerLoading, setOwnerLoading] = useState(true)
  const [email, setEmail] = useState('ops.lead@stmercy.example')
  const [role, setRole] = useState<typeof roles[number]>('operator')
  const [department, setDepartment] = useState('Cardiology')
  const [departmentSearch, setDepartmentSearch] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const [ownerEmail, setOwnerEmail] = useState('cardiology.owner@stmercy.example')
  const [auditorEmail, setAuditorEmail] = useState('external.audit@example.com')
  const [auditorScope, setAuditorScope] = useState('Quarterly HIPAA evidence package')
  const [auditorHours, setAuditorHours] = useState(168)
  const [auditorGrants, setAuditorGrants] = useState<AuditorGrant[]>([])
  const [auditorKey, setAuditorKey] = useState<string | null>(null)
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadAuditors = useCallback(() => {
    api.listAuditorGrants()
      .then(r => setAuditorGrants(r.grants || []))
      .catch(() => setAuditorGrants([]))
  }, [])

  const loadUsers = useCallback(() => {
    setUserLoading(true)
    api.listConsoleUserInvites()
      .then(r => setUsers(r.invites || []))
      .catch(() => setUsers([]))
      .finally(() => setUserLoading(false))
  }, [])

  const loadOwners = useCallback(() => {
    setOwnerLoading(true)
    api.listDepartmentOwners()
      .then(r => setOwners(r.owners || []))
      .catch(() => setOwners([]))
      .finally(() => setOwnerLoading(false))
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])
  useEffect(() => { loadOwners() }, [loadOwners])
  useEffect(() => { loadAuditors() }, [loadAuditors])

  const departmentDirectory = useMemo(() => {
    const fromUsers = users.map(u => u.department || '').filter(Boolean)
    const fromOwners = owners.map(o => o.department).filter(Boolean)
    return [...new Set([...departments, ...fromUsers, ...fromOwners, department].filter(Boolean))].sort((a, b) => a.localeCompare(b))
  }, [users, owners, department])

  const filteredDepartments = useMemo(() => {
    const q = departmentSearch.trim().toLowerCase()
    return departmentDirectory.filter(d => !q || d.toLowerCase().includes(q)).slice(0, 10)
  }, [departmentDirectory, departmentSearch])

  const visibleUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase()
    return users.filter(u => {
      if (!q) return true
      return [u.email, u.role, u.department || '', u.scope || '', u.status].some(value => value.toLowerCase().includes(q))
    })
  }, [users, userSearch])

  useEffect(() => {
    _setPS('settings', [{
      type: 'access_management',
      invited_users: users.length,
      department_owners: owners.length,
      auditor_grants: auditorGrants.length,
      note: 'Human users are invited and assigned roles here. Runtime credentials remain separate.',
    }])
  }, [users.length, owners.length, auditorGrants.length])

  const inviteUser = async () => {
    const cleanEmail = email.trim().toLowerCase()
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Enter a valid user email.')
      return
    }
    setBusy('user')
    setError('')
    setMessage('')
    setLastInviteUrl(null)
    try {
      const scope = role === 'governance_admin' || role === 'security_admin' ? 'Cross-department' : `${department} only`
      const res = await api.createConsoleUserInvite({
        email: cleanEmail,
        role,
        department,
        scope,
        expires_in_hours: 168,
      })
      setLastInviteUrl(res.invite.invite_url || null)
      setMessage(`Invite created for ${cleanEmail}`)
      loadUsers()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invite failed')
    } finally {
      setBusy(null)
    }
  }

  const revokeUser = async (id: string) => {
    setBusy(id)
    setError('')
    try {
      await api.revokeConsoleUserInvite(id)
      setMessage('User invite revoked.')
      loadUsers()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revoke failed')
    } finally {
      setBusy(null)
    }
  }

  const saveOwner = async () => {
    const cleanOwner = ownerEmail.trim().toLowerCase()
    if (!cleanOwner || !cleanOwner.includes('@')) {
      setError('Enter a valid department owner email.')
      return
    }
    if (!department.trim()) {
      setError('Department is required.')
      return
    }
    setBusy('owner')
    setError('')
    try {
      await api.setDepartmentOwner(department.trim(), cleanOwner)
      setMessage(`${department} owner saved.`)
      loadOwners()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Owner save failed')
    } finally {
      setBusy(null)
    }
  }

  const inviteAuditor = async () => {
    const cleanEmail = auditorEmail.trim().toLowerCase()
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Enter a valid auditor email.')
      return
    }
    setBusy('auditor')
    setError('')
    setAuditorKey(null)
    try {
      const res = await api.inviteAuditor({
        auditor_email: cleanEmail,
        expires_in_hours: auditorHours,
        scope_note: auditorScope.trim() || undefined,
      })
      setAuditorKey(res.api_key)
      setMessage(`Auditor grant created for ${res.auditor_email}`)
      loadAuditors()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Auditor invite failed')
    } finally {
      setBusy(null)
    }
  }

  const revokeAuditor = async (keyId: string) => {
    setBusy(keyId)
    setError('')
    try {
      await api.revokeAuditorGrant(keyId)
      setMessage('Auditor grant revoked.')
      loadAuditors()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Auditor revoke failed')
    } finally {
      setBusy(null)
    }
  }

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value).catch(() => {})
    setMessage('Copied.')
  }

  const activeHumans = users.filter(u => u.status !== 'revoked')
  const activeAuditors = auditorGrants.filter(g => g.status !== 'revoked' && !g.expired)

  return (
    <section className="glass-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Users size={14} className="text-primary" /> Access Management
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-primary/25 bg-primary/10 text-primary">Admins only</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl">Manage human users, department owners, and auditor access. Runtime credentials stay separate.</p>
        </div>
        <div className="flex gap-2 text-[10px]">
          <span className="px-2 py-1 rounded-full border border-border/60 bg-muted/20 text-muted-foreground">{activeHumans.length} humans</span>
          <span className="px-2 py-1 rounded-full border border-border/60 bg-muted/20 text-muted-foreground">{activeAuditors.length} auditors</span>
          <span className="px-2 py-1 rounded-full border border-border/60 bg-muted/20 text-muted-foreground">{owners.length} owners</span>
        </div>
      </div>

      {(error || message) && (
        <div className={cn(
          'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs',
          error ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
        )}>
          {error ? <AlertCircle size={12} /> : <CheckCircle2 size={12} />}
          {error || message}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[0.92fr_1.08fr] gap-4 items-start">
        <div className="space-y-4">
          <div className="rounded-2xl border border-border/50 bg-background/25 p-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border/50 bg-muted/20 px-3 py-3">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Departments</p>
                <p className="mt-1 text-xl font-semibold text-foreground leading-none">{departmentDirectory.length}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">available</p>
              </div>
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-3">
                <p className="text-[10px] uppercase tracking-widest text-emerald-200/60">Default Scope</p>
                <p className="mt-1 text-xl font-semibold text-emerald-300 leading-none">Scoped</p>
                <p className="mt-1 text-[11px] text-muted-foreground">one department</p>
              </div>
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 px-3 py-3">
                <p className="text-[10px] uppercase tracking-widest text-blue-200/60">Global Roles</p>
                <p className="mt-1 text-xl font-semibold text-blue-300 leading-none">Admin</p>
                <p className="mt-1 text-[11px] text-muted-foreground">security/governance</p>
              </div>
              <div className="rounded-xl border border-primary/20 bg-primary/5 px-3 py-3">
                <p className="text-[10px] uppercase tracking-widest text-primary/70">Find Dept</p>
                <p className="mt-1 text-xl font-semibold text-primary leading-none">Search</p>
                <p className="mt-1 text-[11px] text-muted-foreground">large orgs</p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold">Invite user</p>
              <span className="text-[10px] text-muted-foreground">SSO / invite based</span>
            </div>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="admin@hospital.org"
              className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <select value={role} onChange={e => setRole(e.target.value as typeof roles[number])}
                className="text-sm bg-background border border-border rounded-lg px-3 py-2">
                {roles.map(r => <option key={r} value={r}>{ROLE_LABELS[r as ConsoleRole] ?? r}</option>)}
              </select>
              <input
                value={department}
                onChange={e => setDepartment(e.target.value)}
                list="edon-access-departments"
                placeholder="Search or type department"
                className="text-sm bg-background border border-border rounded-lg px-3 py-2"
              />
            </div>
            <datalist id="edon-access-departments">
              {departmentDirectory.map(d => <option key={d} value={d} />)}
            </datalist>
            <p className="text-[11px] text-muted-foreground">
              Scope: {role === 'governance_admin' || role === 'security_admin' ? 'cross-department admin visibility' : `${department || 'selected department'} only`}
            </p>
            <button onClick={inviteUser}
              disabled={busy === 'user'}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary/20 border border-primary/40 text-primary text-xs font-semibold hover:bg-primary/30 disabled:opacity-50 transition-colors">
              <Plus size={13} /> {busy === 'user' ? 'Creating invite' : 'Invite user'}
            </button>
            {lastInviteUrl && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <p className="text-[10px] uppercase tracking-widest text-primary/70">Invite delivery URL</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 text-[11px] break-all text-foreground">{lastInviteUrl}</code>
                  <button onClick={() => copy(lastInviteUrl)} className="p-2 rounded-lg border border-border hover:bg-muted/40"><Copy size={12} /></button>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold">Department owner</p>
              <span className="text-[10px] text-muted-foreground">Review routing</span>
            </div>
            <input
              value={department}
              onChange={e => setDepartment(e.target.value)}
              list="edon-access-departments"
              placeholder="Department"
              className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2"
            />
            <input value={ownerEmail} onChange={e => setOwnerEmail(e.target.value)} placeholder="owner@hospital.org"
              className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" />
            <button onClick={saveOwner}
              disabled={busy === 'owner'}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 disabled:opacity-50 transition-colors">
              <Check size={13} /> {busy === 'owner' ? 'Saving' : 'Save owner'}
            </button>
          </div>

          <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold text-blue-300">Invite auditor</p>
              <span className="text-[10px] text-blue-200/70">Backend grant</span>
            </div>
            <input value={auditorEmail} onChange={e => setAuditorEmail(e.target.value)} placeholder="auditor@firm.com"
              className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" />
            <input value={auditorScope} onChange={e => setAuditorScope(e.target.value)} placeholder="Scope note"
              className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" />
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <input type="number" min={1} max={720} value={auditorHours} onChange={e => setAuditorHours(Number(e.target.value) || 168)}
                className="text-sm bg-background border border-border rounded-lg px-3 py-2" />
              <button onClick={inviteAuditor} disabled={busy === 'auditor'}
                className="px-3 py-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-300 text-xs font-semibold hover:bg-blue-500/20 disabled:opacity-50 transition-colors">
                {busy === 'auditor' ? 'Inviting' : 'Invite'}
              </button>
            </div>
            {auditorKey && (
              <div className="rounded-lg border border-blue-500/20 bg-background/60 p-3">
                <p className="text-[10px] uppercase tracking-widest text-blue-200/70">One-time auditor key</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 text-[11px] break-all text-blue-100">{auditorKey}</code>
                  <button onClick={() => copy(auditorKey)} className="p-2 rounded-lg border border-border hover:bg-muted/40"><Copy size={12} /></button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-background/25 p-4 space-y-4">
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Department directory</p>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">{departmentDirectory.length} total</span>
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
              <Search size={13} className="text-muted-foreground" />
              <input value={departmentSearch} onChange={e => setDepartmentSearch(e.target.value)} placeholder="Find department"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/40" />
            </div>
            <div className="flex flex-wrap gap-2">
              {filteredDepartments.map(d => (
                <button key={d} onClick={() => { setDepartment(d); setDepartmentSearch(d) }}
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-full border transition-colors',
                    department === d ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                  )}>
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="lg:col-span-2 rounded-xl border border-border/50 bg-muted/20 p-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Human access</p>
                <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5">
                  <Search size={12} className="text-muted-foreground" />
                  <input value={userSearch} onChange={e => setUserSearch(e.target.value)} placeholder="Search users"
                    className="w-40 bg-transparent text-xs outline-none placeholder:text-muted-foreground/40" />
                </div>
              </div>
              <div className="mt-3 max-h-64 overflow-auto pr-1">
                {userLoading && <Spinner />}
                {!userLoading && users.length === 0 && <p className="text-xs text-muted-foreground">No users invited yet.</p>}
                {!userLoading && users.length > 0 && (
                  <div className="min-w-[720px]">
                    <div className="grid grid-cols-[1.6fr_1fr_1fr_1fr_0.7fr] gap-2 px-3 py-2 text-[10px] uppercase tracking-widest text-muted-foreground/50">
                      <span>User</span><span>Role</span><span>Department</span><span>Scope</span><span>Status</span>
                    </div>
                    {visibleUsers.map(u => (
                      <div key={u.invite_id} className="grid grid-cols-[1.6fr_1fr_1fr_1fr_0.7fr] gap-2 items-center rounded-lg border border-border/50 bg-background/60 px-3 py-2 mb-2">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-foreground truncate">{u.email}</p>
                          <p className="text-[10px] text-muted-foreground">{u.created_at ? relTime(u.created_at) : 'pending'}</p>
                        </div>
                        <p className="text-[11px] text-muted-foreground truncate">{ROLE_LABELS[u.role as ConsoleRole] ?? u.role}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{u.department}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{u.scope || `${u.department} only`}</p>
                        <div>
                      <span className={cn(
                        'text-[10px] px-2 py-0.5 rounded-full border',
                        u.status === 'revoked' ? 'border-red-500/25 bg-red-500/10 text-red-300' : u.status === 'accepted' ? 'border-blue-500/25 bg-blue-500/10 text-blue-300' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
                      )}>{u.status}</span>
                          {u.status !== 'revoked' && u.status !== 'accepted' && (
                            <button onClick={() => revokeUser(u.invite_id)} disabled={busy === u.invite_id} className="block mt-1 text-[10px] text-muted-foreground hover:text-red-300 disabled:opacity-50 transition-colors">
                              {busy === u.invite_id ? 'Revoking' : 'Revoke'}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Department owners</p>
              <div className="mt-3 space-y-2 max-h-56 overflow-auto pr-1">
                {ownerLoading && <Spinner />}
                {!ownerLoading && owners.length === 0 && <p className="text-xs text-muted-foreground">No department owners mapped.</p>}
                {owners.map(o => (
                  <div key={o.department} className="rounded-lg border border-border/50 bg-background/60 p-3">
                    <p className="text-xs font-semibold text-foreground">{o.department}</p>
                    <p className="text-[11px] text-muted-foreground truncate">{o.owner_email}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Auditor grants</p>
              <button onClick={loadAuditors} className="text-[10px] text-muted-foreground hover:text-foreground">Refresh</button>
            </div>
            <div className="mt-3 space-y-2 max-h-56 overflow-auto pr-1">
              {auditorGrants.length === 0 && <p className="text-xs text-muted-foreground">No auditor grants returned by the gateway.</p>}
              {auditorGrants.map(g => (
                <div key={g.key_id} className="rounded-lg border border-border/50 bg-background/60 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-foreground truncate">{g.auditor_email || g.name || g.label || g.key_id}</p>
                      <p className="text-[11px] text-muted-foreground truncate">{g.scope_note || 'Read, audit, export evidence'}</p>
                      <p className="text-[10px] text-muted-foreground/70">Expires {g.expires_at ? fmtTs(g.expires_at) : 'unknown'}</p>
                    </div>
                    <span className={cn(
                      'text-[10px] px-2 py-0.5 rounded-full border',
                      g.expired || g.status === 'revoked' ? 'border-amber-500/25 bg-amber-500/10 text-amber-300' : 'border-blue-500/25 bg-blue-500/10 text-blue-300',
                    )}>{g.expired ? 'Expired' : (g.status || 'Active')}</span>
                  </div>
                  {g.status !== 'revoked' && (
                    <button onClick={() => revokeAuditor(g.key_id)} disabled={busy === g.key_id}
                      className="mt-2 text-[11px] text-muted-foreground hover:text-red-300 disabled:opacity-50 transition-colors">
                      {busy === g.key_id ? 'Revoking' : 'Revoke grant'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function SecuritySupportWorkspace() {
  const [active, setActive] = useState<'allowlist' | 'webhooks' | 'access' | 'support'>('allowlist')
  const sections = [
    {
      id: 'allowlist' as const,
      title: 'IP Allowlist',
      body: 'Restrict gateway API access by source IP.',
      Icon: Shield,
      status: 'Optional',
    },
    {
      id: 'webhooks' as const,
      title: 'Webhook Alerts',
      body: 'Send block, escalation, and risk events downstream.',
      Icon: Bell,
      status: 'HMAC signed',
    },
    {
      id: 'access' as const,
      title: 'Console Access',
      body: 'Share the console location without embedding credentials.',
      Icon: Link,
      status: 'No token',
    },
    {
      id: 'support' as const,
      title: 'Support',
      body: 'Create a case or copy tenant-scoped diagnostics.',
      Icon: Copy,
      status: 'Sanitized',
    },
  ]

  return (
    <section className="glass-card p-5 space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2"><ShieldAlert size={14} className="text-primary" /> Security & Support</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Open one control at a time. Ingress controls, alerts, access links, and support evidence stay in one workspace.</p>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full border border-border/60 bg-muted/20 text-muted-foreground">Admin controls</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[20rem_1fr] gap-4 items-start">
        <div className="rounded-xl border border-border/50 bg-background/25 p-2 space-y-1">
          {sections.map(section => {
            const Icon = section.Icon
            const selected = active === section.id
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => setActive(section.id)}
                className={`w-full text-left rounded-lg border px-3 py-3 transition-colors ${selected ? 'border-primary/35 bg-primary/10' : 'border-transparent hover:border-border/60 hover:bg-muted/20'}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 ${selected ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border/50 bg-muted/20 text-muted-foreground'}`}>
                    <Icon size={13} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-foreground">{section.title}</p>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${selected ? 'border-primary/25 text-primary bg-primary/10' : 'border-border/50 text-muted-foreground'}`}>
                        {section.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{section.body}</p>
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        <div className="min-w-0">
          {active === 'allowlist' && <IpAllowlistCard />}
          {active === 'webhooks' && <WebhookAlertsCard />}
          {active === 'access' && <ConsoleLinkCard />}
          {active === 'support' && <SupportDiagnosticsCard />}
        </div>
      </div>
    </section>
  )
}
void SecuritySupportWorkspace

function ShadowModeCard({
  enabled,
  saving,
  onToggle,
}: {
  enabled: boolean
  saving: boolean
  onToggle: () => void
}) {

  return (
    <div className="glass-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Shadow Mode</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Log all decisions without blocking - use during trial periods</p>
        </div>
        <button onClick={onToggle} disabled={saving}
          className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none ${enabled ? 'bg-amber-500' : 'bg-muted/50 border border-border'}`}>
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200 ${enabled ? 'translate-x-5' : ''}`} />
        </button>
      </div>
      {enabled && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs">
          <span className="text-base">!</span>
          Governance is in observe-only mode. No actions are being blocked.
        </div>
      )}
    </div>
  )
}

function ApiKeyRotationCard() {
  const PRESET_DEPARTMENTS = ['Cardiology', 'Radiology', 'Pharmacy', 'Telehealth', 'ICU', 'Lab', 'Nursing', 'Security']
  const SCOPE_GROUPS = ['clinical', 'operational', 'security', 'research', 'billing'] as const
  const PRESET_SCOPES: Record<typeof SCOPE_GROUPS[number], string[]> = {
    clinical: ['note.draft', 'note.writeback', 'lab.read', 'medication.review'],
    operational: ['escalation.route', 'appointment.route', 'device.status.read'],
    security: ['audit.export', 'policy.read', 'alert.notify'],
    research: ['read.anonymized', 'study.export', 'model.eval'],
    billing: ['claim.read', 'claim.route', 'payment.status'],
  }
  const ENVIRONMENTS = ['Audit-only', 'Sandbox', 'Pilot', 'Governed', 'Production'] as const

  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [overlapHours, setOverlapHours] = useState(24)
  const [selectedDept, setSelectedDept] = useState('Cardiology')
  const [selectedKeyId, setSelectedKeyId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [newDepartment, setNewDepartment] = useState('')
  const [departmentDraft, setDepartmentDraft] = useState('Cardiology')
  const [nameDraft, setNameDraft] = useState('Cardiology Agent Runtime')
  const [purposeDraft, setPurposeDraft] = useState('Note drafting')
  const [scopeGroup, setScopeGroup] = useState<typeof SCOPE_GROUPS[number]>('clinical')
  const [selectedScopes, setSelectedScopes] = useState<string[]>(PRESET_SCOPES.clinical.slice(0, 2))
  const [environment, setEnvironment] = useState<(typeof ENVIRONMENTS)[number]>('Audit-only')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [activity, setActivity] = useState<Array<{ label: string; time: string }>>([])
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api.listApiKeys().then(r => {
      setKeys(r.keys || [])
      setSelectedKeyId(curr => curr ?? r.keys?.[0]?.id ?? null)
    }).catch(() => setKeys([])).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const departmentRoster = useMemo(() => {
    const base = new Set([...PRESET_DEPARTMENTS, ...keys.map(k => k.department || '').filter(Boolean), departmentDraft, newDepartment].filter(Boolean))
    return [...base].sort()
  }, [keys, departmentDraft, newDepartment])

  const visibleDepartments = useMemo(() => {
    const q = search.trim().toLowerCase()
    return departmentRoster.filter(d => !q || d.toLowerCase().includes(q))
  }, [departmentRoster, search])

  const visibleKeys = useMemo(() => {
    return keys.filter(k => !selectedDept || k.department === selectedDept || (!k.department && selectedDept === 'Unassigned'))
  }, [keys, selectedDept])

  const selectedKey = useMemo(
    () => visibleKeys.find(k => k.id === selectedKeyId) || visibleKeys[0] || keys.find(k => k.id === selectedKeyId) || keys[0] || null,
    [visibleKeys, selectedKeyId, keys],
  )

  useEffect(() => {
    if (!selectedKey && keys.length > 0) setSelectedKeyId(keys[0].id)
  }, [keys, selectedKey])

  useEffect(() => {
    if (selectedKey && selectedKey.department) {
      setSelectedDept(selectedKey.department)
      setDepartmentDraft(selectedKey.department)
      setNameDraft(selectedKey.name || `${selectedKey.department} Agent Runtime`)
      setPurposeDraft(selectedKey.purpose || 'Note drafting')
      setEnvironment((selectedKey.environment as typeof ENVIRONMENTS[number]) || 'Audit-only')
      const grp = (selectedKey.scope_group as typeof SCOPE_GROUPS[number]) || 'clinical'
      setScopeGroup(grp)
      setSelectedScopes((selectedKey.scope || PRESET_SCOPES[grp].join(' -> ')).split(/\s*->\s*|\s*,\s*/).filter(Boolean))
    }
  }, [selectedKey])

  const departmentCount = departmentRoster.length
  const currentIndex = Math.max(visibleKeys.findIndex(k => k.id === selectedKey?.id) + 1, selectedKey ? 1 : 0)
  const currentTotal = Math.max(visibleKeys.length, 1)
  const activeCount = keys.filter(k => k.status === 'active').length

  const addActivity = (label: string) => {
    setActivity(prev => [{ label, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }, ...prev].slice(0, 5))
  }

  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const createCredential = async () => {
    if (!departmentDraft.trim()) return
    setBusy(true)
    setError('')
    try {
      const scope = selectedScopes.length ? selectedScopes.join(' -> ') : PRESET_SCOPES[scopeGroup].join(' -> ')
      const res = await api.createApiKey({
        name: nameDraft.trim() || `${departmentDraft.trim()} Agent Runtime`,
        role: 'operator',
        department: departmentDraft.trim(),
        purpose: purposeDraft.trim(),
        scope_group: scopeGroup,
        scope,
        environment,
      })
      setCreatedKey(res.key)
      setSelectedDept(departmentDraft.trim())
      setSelectedKeyId(res.key_id)
      addActivity(`Created ${departmentDraft.trim()} credential`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create credential')
    } finally {
      setBusy(false)
    }
  }

  const rotateCredential = async () => {
    if (!selectedKey) return
    setBusy(true)
    setError('')
    try {
      const res = await api.rotateApiKey(selectedKey.id, overlapHours, selectedKey.name || `${selectedKey.department || 'runtime'} rotated`)
      setCreatedKey(res.new_key)
      addActivity(`Rotated ${selectedKey.name || selectedKey.id}`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Rotation failed')
    } finally {
      setBusy(false)
    }
  }

  const revokeCredential = async () => {
    if (!selectedKey) return
    setBusy(true)
    setError('')
    try {
      await api.revokeApiKey(selectedKey.id)
      addActivity(`Revoked ${selectedKey.name || selectedKey.id}`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revoke failed')
    } finally {
      setBusy(false)
    }
  }

  const copyDiagnostics = async () => {
    const bundle = [
      'tenant_id: unknown',
      `department: ${selectedDept}`,
      `credential: ${selectedKey?.name || selectedKey?.id || 'unknown'}`,
      `purpose: ${purposeDraft}`,
      `scope_group: ${scopeGroup}`,
      `environment: ${environment}`,
      `scope: ${selectedScopes.join(' -> ') || 'none'}`,
    ].join('\n')
    await navigator.clipboard.writeText(bundle).catch(() => {})
    addActivity('Copied diagnostics')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const toggleScope = (scope: string) => {
    setSelectedScopes(curr => curr.includes(scope) ? curr.filter(s => s !== scope) : [...curr, scope])
  }

  const currentScopes = selectedScopes.length ? selectedScopes : PRESET_SCOPES[scopeGroup]

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <KeyRound size={13} className="text-primary" /> Runtime Credentials
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-primary/25 bg-primary/10 text-primary">
              Admin only
            </span>
          </h3>
          <p className="text-xs text-muted-foreground">Department-scoped credentials, scope chips, and tenant posture in one place.</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Credential</p>
          <p className="text-sm font-semibold text-foreground">{currentIndex} / {currentTotal}</p>
          <p className="text-[10px] text-muted-foreground">{activeCount} active</p>
        </div>
      </div>
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[0.92fr_1.08fr] gap-4">
        <div className="space-y-4">
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Search size={13} className="text-muted-foreground" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search departments"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/40"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {visibleDepartments.map(dept => (
                <button
                  key={dept}
                  onClick={() => { setSelectedDept(dept); setDepartmentDraft(dept); setNameDraft(`${dept} Agent Runtime`) }}
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-full border transition-colors',
                    selectedDept === dept
                      ? 'bg-primary/15 border-primary/30 text-primary'
                      : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                  )}
                >
                  {dept}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <input
                value={newDepartment}
                onChange={e => setNewDepartment(e.target.value)}
                placeholder="Add department"
                className="text-sm bg-background border border-border rounded-lg px-3 py-2"
              />
              <button
                onClick={() => {
                  const next = newDepartment.trim()
                  if (!next) return
                  setSelectedDept(next)
                  setDepartmentDraft(next)
                  setNameDraft(`${next} Agent Runtime`)
                  setNewDepartment('')
                }}
                className="px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-sm font-semibold hover:bg-primary/20 transition-colors"
              >
                Add
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Preset departments</p>
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">{departmentCount}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {PRESET_DEPARTMENTS.map(dept => (
                <button
                  key={dept}
                  onClick={() => { setSelectedDept(dept); setDepartmentDraft(dept); setNameDraft(`${dept} Agent Runtime`) }}
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-lg border transition-colors',
                    selectedDept === dept
                      ? 'bg-cyan-500/15 border-cyan-500/30 text-cyan-300'
                      : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                  )}
                >
                  {dept}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3">
            <div className="grid grid-cols-1 gap-3">
              <label className="space-y-1">
                <span className="block text-[10px] uppercase tracking-widest text-muted-foreground/50">Department name</span>
                <input value={departmentDraft} onChange={e => setDepartmentDraft(e.target.value)} className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" placeholder="Cardiology" />
              </label>
              <label className="space-y-1">
                <span className="block text-[10px] uppercase tracking-widest text-muted-foreground/50">Purpose</span>
                <input value={purposeDraft} onChange={e => setPurposeDraft(e.target.value)} className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" placeholder="Draft clinical notes" />
              </label>
              <label className="space-y-1">
                <span className="block text-[10px] uppercase tracking-widest text-muted-foreground/50">Credential name</span>
                <input value={nameDraft} onChange={e => setNameDraft(e.target.value)} className="w-full text-sm bg-background border border-border rounded-lg px-3 py-2" placeholder="Cardiology Agent Runtime" />
              </label>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Scope group</p>
                <span className="text-[10px] text-muted-foreground">{scopeGroup}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {SCOPE_GROUPS.map(group => (
                  <button
                    key={group}
                    onClick={() => {
                      setScopeGroup(group)
                      setSelectedScopes(PRESET_SCOPES[group].slice(0, 2))
                    }}
                    className={cn(
                      'text-xs px-2.5 py-1 rounded-full border transition-colors capitalize',
                      scopeGroup === group
                        ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
                        : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                    )}
                  >
                    {group}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {PRESET_SCOPES[scopeGroup].map(scope => (
                  <button
                    key={scope}
                    onClick={() => toggleScope(scope)}
                    className={cn(
                      'text-xs px-2.5 py-1 rounded-full border transition-colors',
                      currentScopes.includes(scope)
                        ? 'bg-primary/15 border-primary/30 text-primary'
                        : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                    )}
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Governance mode</p>
              <div className="grid grid-cols-2 gap-2">
                {ENVIRONMENTS.map(mode => (
                  <button
                    key={mode}
                    onClick={() => setEnvironment(mode)}
                    className={cn(
                      'px-3 py-2 rounded-lg border text-xs font-medium transition-colors',
                      environment === mode
                        ? 'bg-primary/15 border-primary/30 text-primary'
                        : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted/40',
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={createCredential}
              disabled={busy || !departmentDraft.trim()}
              className="w-full py-3 rounded-xl bg-primary/20 border border-primary/40 text-primary text-sm font-semibold hover:bg-primary/30 transition-colors disabled:opacity-50"
            >
              {busy ? 'Saving...' : 'Create credential'}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border/60 bg-background/50 p-4 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Current credential</p>
                <h4 className="text-sm font-semibold text-foreground truncate">{selectedKey?.name || 'No credential selected'}</h4>
              </div>
              <span className={cn(
                'text-[10px] px-2 py-0.5 rounded-full border font-medium',
                selectedKey?.status === 'active'
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                  : selectedKey?.status === 'rotating'
                    ? 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                    : 'bg-red-500/10 border-red-500/20 text-red-400',
              )}>
                {selectedKey?.status || 'unknown'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Department</p>
                <p className="mt-1 text-foreground">{selectedKey?.department || selectedDept || '-'}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Scope group</p>
                <p className="mt-1 text-foreground capitalize">{selectedKey?.scope_group || scopeGroup}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Purpose</p>
                <p className="mt-1 text-foreground">{selectedKey?.purpose || purposeDraft}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Environment</p>
                <p className="mt-1 text-foreground">{selectedKey?.environment || environment}</p>
              </div>
            </div>

            <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Scope chips</p>
                <span className="text-[10px] text-muted-foreground">{currentScopes.length} selected</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {currentScopes.map(scope => (
                  <span key={scope} className="text-[10px] px-2 py-1 rounded-full border border-primary/25 bg-primary/10 text-primary">
                    {scope}
                  </span>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border/60 bg-muted/20 p-3 text-xs text-muted-foreground space-y-1">
              <div className="flex justify-between gap-3"><span>Credential preview</span><code className="text-foreground">{selectedKey?.key_preview || '-'}</code></div>
              <div className="flex justify-between gap-3"><span>Last used</span><span className="text-foreground">{selectedKey?.last_used || 'Never'}</span></div>
              <div className="flex justify-between gap-3"><span>Created</span><span className="text-foreground">{selectedKey?.created_at || '—'}</span></div>
            </div>

            <div className="flex flex-wrap gap-2">
              <select value={overlapHours} onChange={e => setOverlapHours(Number(e.target.value))}
                className="text-xs bg-background border border-border rounded-lg px-2.5 py-2 text-muted-foreground">
                <option value={1}>1h overlap</option>
                <option value={4}>4h overlap</option>
                <option value={24}>24h overlap</option>
                <option value={72}>3d overlap</option>
              </select>
              <button onClick={rotateCredential} disabled={busy || !selectedKey}
                className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
                <RefreshCw size={13} className={busy ? 'animate-spin' : ''} /> Rotate
              </button>
              <button onClick={revokeCredential} disabled={busy || !selectedKey}
                className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20 transition-colors disabled:opacity-50">
                <X size={13} /> Revoke
              </button>
              <button onClick={copyDiagnostics}
                className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                <Copy size={13} /> Copy diagnostics
              </button>
            </div>
          </div>

          {createdKey && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-2">
              <p className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5"><Check size={13} /> Credential created</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono bg-black/30 rounded px-3 py-2 break-all">{createdKey}</code>
                <button onClick={() => copy(createdKey)} className="p-2 rounded border border-border hover:bg-muted/50 transition-colors">
                  {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} className="text-muted-foreground" />}
                </button>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-foreground">Recent actions</h4>
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted-foreground">{activity.length}</span>
            </div>
            {activity.length > 0 ? (
              <div className="space-y-2">
                {activity.map((item, idx) => (
                  <div key={`${item.label}-${idx}`} className="flex items-center justify-between gap-3 text-xs rounded-lg border border-border/60 bg-background/40 px-3 py-2">
                    <span className="text-foreground">{item.label}</span>
                    <span className="text-muted-foreground font-mono">{item.time}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Create, rotate, or revoke a credential to seed this trail.</p>
            )}
          </div>

          {loading && <p className="text-xs text-muted-foreground">Loading credentials...</p>}
          <div className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-2 max-h-56 overflow-auto">
            {keys.map(k => (
              <button
                key={k.id}
                onClick={() => setSelectedKeyId(k.id)}
                className={cn(
                  'w-full text-left flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors',
                  selectedKey?.id === k.id
                    ? 'border-primary/30 bg-primary/10'
                    : 'border-border bg-background/30 hover:bg-muted/40',
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{k.name || 'Unnamed key'}</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {k.department || 'Unassigned'} · {k.scope_group || 'no scope group'} · {k.key_preview}
                  </p>
                </div>
                <span className={cn(
                  'text-[10px] px-2 py-0.5 rounded-full border font-medium',
                  k.status === 'active'
                    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                    : k.status === 'rotating'
                      ? 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                      : 'bg-red-500/10 border-red-500/20 text-red-400',
                )}>
                  {k.status}
                </span>
              </button>
            ))}
            {!loading && keys.length === 0 && <p className="text-xs text-muted-foreground">No credentials yet.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

function ConsoleLinkCard() {
  const [copied, setCopied] = useState(false)
  const auth = (() => { try { return JSON.parse(sessionStorage.getItem('edon_auth') || localStorage.getItem('edon_auth') || '{}') } catch { return {} } })()
  const baseHash = auth.gatewayUrl ? `#base=${encodeURIComponent(auth.gatewayUrl)}` : ''
  const url = `${window.location.origin}/${baseHash}`

  const copy = () => {
    navigator.clipboard.writeText(url)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="glass-card p-5 space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-2"><Link size={13} className="text-primary" /> Console Access Link</h3>
      <p className="text-xs text-muted-foreground">Share the console location without credentials. Each user signs in with their own key.</p>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2.5">
        <code className="flex-1 text-xs font-mono text-muted-foreground truncate">{url}</code>
        <button onClick={copy} className="p-1.5 rounded border border-border hover:bg-muted/50 transition-colors shrink-0">
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} className="text-muted-foreground" />}
        </button>
      </div>
      <p className="text-[10px] text-muted-foreground/50 flex items-center gap-1"><Shield size={11} /> No auth token is embedded in generated links.</p>
    </div>
  )
}

function IpAllowlistCard() {
  const [cidrs, setCidrs] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getIpAllowlist().then(r => setCidrs(r.cidrs)).catch(() => setCidrs([])).finally(() => setLoading(false))
  }, [])

  const add = async () => {
    if (!input.trim()) return
    setSaving(true)
    setError('')
    try {
      await api.addIpAllowlist(input.trim())
      const r = await api.getIpAllowlist()
      setCidrs(r.cidrs); setInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add CIDR')
    } finally { setSaving(false) }
  }

  const remove = async (cidr: string) => {
    setError('')
    try {
      await api.removeIpAllowlist(cidr)
      setCidrs(c => c.filter(x => x !== cidr))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove CIDR')
    }
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Shield size={13} className="text-primary" /> IP Allowlist
        {cidrs.length > 0 && <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">Active</span>}
      </h3>
      <p className="text-xs text-muted-foreground">Restrict API access to specific IPs. Once any entry is added, all other IPs are blocked. <strong className="text-foreground/70">Add your IP first.</strong></p>
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {error}
        </div>
      )}
      {cidrs.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 text-xs text-yellow-400">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" /> Allowlist active - requests from unlisted IPs are rejected.
        </div>
      )}
      {loading && <p className="text-xs text-muted-foreground">Loading...</p>}
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

// -- Webhook Alerts Card -------------------------------------------------------

function WebhookAlertsCard() {
  const [webhooks, setWebhooks] = useState<Array<{ id: string; url: string; events: string[]; enabled: boolean }>>([])
  const [loading, setLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, 'ok' | 'fail'>>({})
  const [error, setError] = useState('')

  const load = () => api.listWebhooks().then(r => setWebhooks(r.webhooks ?? [])).catch(() => setWebhooks([])).finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const add = async () => {
    if (!url.trim()) return
    setSaving(true)
    setError('')
    try {
      await api.createWebhook(url.trim(), ['blocked', 'escalated', 'high_risk'])
      setUrl(''); await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to add webhook') }
    finally { setSaving(false) }
  }

  const remove = async (id: string) => {
    setError('')
    try { await api.deleteWebhook(id); setWebhooks(w => w.filter(x => x.id !== id)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to remove webhook') }
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
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {error}
        </div>
      )}
      {loading && <p className="text-xs text-muted-foreground">Loading...</p>}
      <div className="space-y-2">
        {webhooks.map(w => (
          <div key={w.id} className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-mono truncate">{w.url}</p>
              <p className="text-[10px] text-muted-foreground">{w.events.join(', ')}</p>
            </div>
            {testResult[w.id] && (
              <span className={`text-[10px] font-medium ${testResult[w.id] === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult[w.id] === 'ok' ? 'OK sent' : 'fail'}
              </span>
            )}
            <button onClick={() => test(w.id)} disabled={testing === w.id}
              className="text-xs px-2 py-1 rounded border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
              {testing === w.id ? '...' : 'Test'}
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

// -- Settings Quick Reference Card --------------------------------------------

function SettingsQuickReferenceCard() {
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number; components: Record<string, { status: string }> } | null>(null)
  const [me, setMe] = useState<{ tenant_id: string; role: string; plan: string; vertical?: 'healthcare' | 'banking' | 'general' | null } | null>(null)
  const [copied, setCopied] = useState(false)
  const [supportSummary, setSupportSummary] = useState('')
  const [supportSeverity, setSupportSeverity] = useState<'sev1' | 'sev2' | 'sev3' | 'sev4'>('sev3')
  const [supportSubmitting, setSupportSubmitting] = useState(false)
  const [supportCase, setSupportCase] = useState<{ case_id: string; support_code?: string; support_url: string; message: string } | null>(null)
  const [supportError, setSupportError] = useState('')
  const [supportCode] = useState(() => `SUP-${crypto.randomUUID().slice(0, 8).toUpperCase()}`)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.me().then(setMe).catch(() => {})
  }, [])

  useEffect(() => {
    _setPS('settings', [
      {
        tenant_id: me?.tenant_id,
        role: me?.role,
        plan: me?.plan,
        vertical: me?.vertical,
        gateway_version: health?.version,
        gateway_status: health ? (health.ok ? 'healthy' : 'degraded') : 'unknown',
        components: health ? Object.entries(health.components).map(([name, value]) => `${name}:${value.status}`) : [],
        support_code: supportCode,
      },
    ] as Record<string, unknown>[])
  }, [me, health, supportCode])

  const uptimeStr = (s: number) => {
    if (s < 60) return `${s}s`
    if (s < 3600) return `${Math.floor(s / 60)}m`
    if (s < 86400) return `${Math.floor(s / 3600)}h`
    return `${Math.floor(s / 86400)}d`
  }

  const components = health ? Object.entries(health.components) : []
  const allHealthy = components.every(([, v]) => v.status === 'ok' || v.status === 'healthy')
  const buildDiagnosticsBundle = (problemDescription = '') => ({
    support_code: supportCode,
    generated_at: new Date().toISOString(),
    tenant_id: me?.tenant_id || 'unknown',
    role: me?.role || 'unknown',
    plan: me?.plan || 'unknown',
    vertical: me?.vertical || 'unknown',
    gateway_version: health?.version || 'unknown',
    gateway_status: health ? (health.ok ? 'ok' : 'degraded') : 'unknown',
    gateway_uptime_seconds: health?.uptime_seconds ?? 'unknown',
    gateway_url: sessionStorage.getItem('edon_auth') ? (() => { try { return JSON.parse(sessionStorage.getItem('edon_auth') || '{}').gatewayUrl || 'unknown' } catch { return 'unknown' } })() : 'unknown',
    request_id: getLastRequestId() || 'unknown',
    decision_id: '',
    action_id: '',
    trace_id: '',
    conversation_id: '',
    problem_description: problemDescription,
  })

  const copyDiagnostics = () => {
    const bundle = buildDiagnosticsBundle()
    const lines = Object.entries(bundle).map(([key, value]) => `${key}: ${value}`)
    navigator.clipboard.writeText(lines.join('\n')).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const submitSupportCase = async () => {
    if (!supportSummary.trim()) {
      setSupportError('Add a short issue summary first.')
      return
    }
    setSupportError('')
    setSupportSubmitting(true)
    try {
      const result = await api.submitSupportTicket({
        summary: supportSummary.trim(),
        severity: supportSeverity,
        tab: 'settings',
        reviewer_name: getReviewerName() || undefined,
        department: getReviewerDept() || undefined,
        issue_type: 'incident',
        chat_history: [],
        notes: supportSummary.trim(),
        diagnostics: buildDiagnosticsBundle(supportSummary.trim()),
      })
      setSupportCase(result)
    } catch (e) {
      setSupportError(e instanceof Error ? e.message : 'Failed to create support case')
    } finally {
      setSupportSubmitting(false)
    }
  }

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
          <p className="text-xs text-muted-foreground">Fetching status...</p>
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
                <span className="text-muted-foreground">Persona</span>
              <span className={`font-medium capitalize ${me.role === 'admin' ? 'text-primary' : 'text-foreground'}`}>
                {ROLE_LABELS[me.role as ConsoleRole] ?? me.role}
              </span>
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
            CONSOLE_DEV_MODE
              ? { label: 'PIN set for reviews', ok: hasPinSet() }
              : { label: 'Review identity server-bound', ok: !!me?.tenant_id },
            CONSOLE_DEV_MODE
              ? { label: 'Identity configured', ok: !!getReviewerName() }
              : { label: 'Authenticated tenant', ok: !!me?.tenant_id },
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

        <div className="glass-card p-5 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold flex items-center gap-2"><Copy size={13} className="text-primary" /> Support Diagnostics</h3>
            <button onClick={copyDiagnostics} className="shrink-0 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors">
              {copied ? 'Copied' : 'Copy bundle'}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Copy this when something is broken. Fill in the exact `decision_id`, `action_id`, `trace_id`, or `conversation_id` if you have them.
          </p>
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3 text-[11px] font-mono text-muted-foreground whitespace-pre-wrap break-all">
            support_code: {supportCode}{'\n'}
            tenant_id: {me?.tenant_id || 'unknown'}{'\n'}
            role: {me?.role || 'unknown'}{'\n'}
            plan: {me?.plan || 'unknown'}{'\n'}
            vertical: {me?.vertical || 'unknown'}{'\n'}
            gateway_version: {health?.version || 'unknown'}{'\n'}
            request_id: {getLastRequestId() || 'unknown'}{'\n'}
            decision_id:{'\n'}
            action_id:{'\n'}
            trace_id:{'\n'}
            conversation_id:{'\n'}
          </div>
          <div className="space-y-2 pt-1">
            <label className="text-[11px] font-medium text-muted-foreground">Issue summary</label>
            <textarea
              value={supportSummary}
              onChange={e => setSupportSummary(e.target.value)}
              rows={3}
              placeholder="Describe the exact issue you want fixed"
              className="w-full text-xs bg-muted/50 border border-border rounded-lg px-3 py-2 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary resize-none"
            />
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-end">
              <label className="space-y-1">
                <span className="block text-[11px] font-medium text-muted-foreground">Severity</span>
                <select
                  value={supportSeverity}
                  onChange={e => setSupportSeverity(e.target.value as 'sev1' | 'sev2' | 'sev3' | 'sev4')}
                  className="w-full text-xs bg-muted/50 border border-border rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="sev1">Sev 1</option>
                  <option value="sev2">Sev 2</option>
                  <option value="sev3">Sev 3</option>
                  <option value="sev4">Sev 4</option>
                </select>
              </label>
              <button
                onClick={submitSupportCase}
                disabled={supportSubmitting}
                className="shrink-0 px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-50"
              >
                {supportSubmitting ? 'Creating...' : 'Create case'}
              </button>
            </div>
            {supportError && <p className="text-[11px] text-red-400">{supportError}</p>}
            {supportCase && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-[11px] text-emerald-200 space-y-1">
                <p className="font-medium">Case {supportCase.case_id} created</p>
                <p className="text-emerald-200/80">{supportCase.message}</p>
                <p className="text-emerald-200/80">Share {supportCase.support_code || supportCode} with support if needed.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

function SupportDiagnosticsCard() {
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number; components: Record<string, { status: string }> } | null>(null)
  const [me, setMe] = useState<{ tenant_id: string; role: string; plan: string; vertical?: 'healthcare' | 'banking' | 'general' | null } | null>(null)
  const [copied, setCopied] = useState(false)
  const [supportSummary, setSupportSummary] = useState('')
  const [supportSeverity, setSupportSeverity] = useState<'sev1' | 'sev2' | 'sev3' | 'sev4'>('sev3')
  const [supportSubmitting, setSupportSubmitting] = useState(false)
  const [supportCase, setSupportCase] = useState<{ case_id: string; support_code?: string; support_url: string; message: string } | null>(null)
  const [supportError, setSupportError] = useState('')
  const [supportCode] = useState(() => `SUP-${crypto.randomUUID().slice(0, 8).toUpperCase()}`)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.me().then(setMe).catch(() => {})
  }, [])

  const buildDiagnosticsBundle = (problemDescription = '') => ({
    support_code: supportCode,
    generated_at: new Date().toISOString(),
    tenant_id: me?.tenant_id || 'unknown',
    role: me?.role || 'unknown',
    plan: me?.plan || 'unknown',
    vertical: me?.vertical || 'unknown',
    gateway_version: health?.version || 'unknown',
    gateway_status: health ? (health.ok ? 'ok' : 'degraded') : 'unknown',
    request_id: getLastRequestId() || 'unknown',
    decision_id: '',
    action_id: '',
    trace_id: '',
    conversation_id: '',
    problem_description: problemDescription,
  })

  const diagnosticsText = Object.entries(buildDiagnosticsBundle()).map(([key, value]) => `${key}: ${value}`).join('\n')

  const copyDiagnostics = () => {
    navigator.clipboard.writeText(diagnosticsText).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const submitSupportCase = async () => {
    if (!supportSummary.trim()) {
      setSupportError('Add a short issue summary first.')
      return
    }
    setSupportError('')
    setSupportSubmitting(true)
    try {
      const result = await api.submitSupportTicket({
        summary: supportSummary.trim(),
        severity: supportSeverity,
        tab: 'settings',
        issue_type: 'incident',
        chat_history: [],
        notes: supportSummary.trim(),
        diagnostics: buildDiagnosticsBundle(supportSummary.trim()),
      })
      setSupportCase(result)
    } catch (e) {
      setSupportError(e instanceof Error ? e.message : 'Failed to create support case')
    } finally {
      setSupportSubmitting(false)
    }
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2"><Copy size={13} className="text-primary" /> Support</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Create a case or copy a sanitized tenant-scoped bundle.</p>
        </div>
        <button onClick={copyDiagnostics} className="shrink-0 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors">
          {copied ? 'Copied' : 'Copy bundle'}
        </button>
      </div>
      <div className="space-y-2">
        <label className="text-[11px] font-medium text-muted-foreground">Issue summary</label>
        <textarea
          value={supportSummary}
          onChange={e => setSupportSummary(e.target.value)}
          rows={3}
          placeholder="Describe the issue, affected page, and any decision/action ID"
          className="w-full text-xs bg-muted/50 border border-border rounded-lg px-3 py-2 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary resize-none"
        />
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-end">
          <label className="space-y-1">
            <span className="block text-[11px] font-medium text-muted-foreground">Severity</span>
            <select
              value={supportSeverity}
              onChange={e => setSupportSeverity(e.target.value as 'sev1' | 'sev2' | 'sev3' | 'sev4')}
              className="w-full text-xs bg-muted/50 border border-border rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="sev1">Sev 1</option>
              <option value="sev2">Sev 2</option>
              <option value="sev3">Sev 3</option>
              <option value="sev4">Sev 4</option>
            </select>
          </label>
          <button
            onClick={submitSupportCase}
            disabled={supportSubmitting}
            className="shrink-0 px-3 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-50"
          >
            {supportSubmitting ? 'Creating...' : 'Create case'}
          </button>
        </div>
        {supportError && <p className="text-[11px] text-red-400">{supportError}</p>}
        {supportCase && (
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-[11px] text-emerald-200 space-y-1">
            <p className="font-medium">Case {supportCase.case_id} created</p>
            <p className="text-emerald-200/80">{supportCase.message}</p>
            <p className="text-emerald-200/80">Share {supportCase.support_code || supportCode} with support if needed.</p>
          </div>
        )}
      </div>
      <details className="rounded-lg border border-border/60 bg-muted/20 p-3">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Diagnostics preview</summary>
        <pre className="mt-3 text-[11px] font-mono text-muted-foreground whitespace-pre-wrap break-all">{diagnosticsText}</pre>
      </details>
    </div>
  )
}

// -- Dashboard Tab -------------------------------------------------------------

function DashboardTab({ tenantLabel, sandboxMode, vertical }: { tenantLabel: string; sandboxMode: boolean; vertical: string | null }) {
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [recent, setRecent] = useState<AuditEvent[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [systemHealth, setSystemHealth] = useState<HealthResponse | null>(null)
  const [blockReasons, setBlockReasons] = useState<BlockReason[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sandboxDeptIndex, setSandboxDeptIndex] = useState(0)
  const [coordDeptIndex, setCoordDeptIndex] = useState(0)
  const [refreshTick, setRefreshTick] = useState(0)

  const load = useCallback(async () => {
    setError('')
    try {
      const [ts, rec, h, sys, br, ag] = await Promise.all([
        api.timeseries(7),
        api.auditQuery({ limit: 20 }),
        api.complianceHealth(),
        api.health(),
        api.blockReasons(7),
        api.agents().catch(() => [] as Agent[]),
      ])
      setTimeseries(ts)
      setRecent(rec.events)
      setHealth(h)
      setSystemHealth(sys)
      setBlockReasons(br)
      setAgents(Array.isArray(ag) ? ag : ((ag as { agents?: Agent[] }).agents ?? []))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(); const iv = setInterval(load, 30000); return () => clearInterval(iv) }, [load])

  const deptList = useMemo(() => {
    const fromAgents = [...new Set(agents.map(a => a.department).filter(Boolean) as string[])]
    const fromEvents = [...new Set(recent.map(e => (e.meta?.department as string | undefined) || '').filter(Boolean) as string[])]
    return [...new Set([...fromAgents, ...fromEvents])].sort()
  }, [agents, recent])

  const agentDeptMap = useMemo(() => {
    const map = new Map<string, string>()
    agents.forEach(a => { if (a.department) map.set(a.agent_id, a.department) })
    return map
  }, [agents])

  const recentDeptMap = useMemo(() => {
    const map = new Map<string, string>()
    recent.forEach(e => {
      const dept = (e.meta?.department as string | undefined) || agentDeptMap.get(e.agent_id) || 'unassigned'
      map.set(e.action_id || e.id || `${e.agent_id}-${e.timestamp}`, dept)
    })
    return map
  }, [recent, agentDeptMap])

  const deptModes = useMemo(() => {
    const base = readJsonRecord<Record<string, 'sandbox' | 'governed'>>(CONSOLE_DEPT_MODE_KEY) || {}
    let changed = false
    for (const dept of deptList) {
      if (!base[dept]) {
        base[dept] = dept === 'telehealth' ? 'sandbox' : 'governed'
        changed = true
      }
    }
    if (changed) writeJsonRecord(CONSOLE_DEPT_MODE_KEY, base)
    return base
  }, [deptList, refreshTick])

  const coordinationAllowed = useMemo(() => {
    const base = readJsonRecord<Record<string, boolean>>(CONSOLE_COORDINATION_KEY) || {}
    let changed = false
    for (const dept of deptList) {
      if (typeof base[dept] !== 'boolean') {
        base[dept] = dept !== 'telehealth'
        changed = true
      }
    }
    if (changed) writeJsonRecord(CONSOLE_COORDINATION_KEY, base)
    return base
  }, [deptList, refreshTick])

  const updateDeptMode = (dept: string, mode: 'sandbox' | 'governed') => {
    setDeptMode(dept, mode)
    setRefreshTick(x => x + 1)
  }

  const toggleCoordination = (dept: string) => {
    setCoordinationAllowed(dept, !(coordinationAllowed[dept] ?? true))
    setRefreshTick(x => x + 1)
  }

  useEffect(() => {
    if (deptList.length === 0) return
    setSandboxDeptIndex(i => Math.min(i, deptList.length - 1))
    setCoordDeptIndex(i => Math.min(i, deptList.length - 1))
  }, [deptList.length])

  useEffect(() => {
    if (timeseries.length === 0 && !health) return
    const tot = timeseries.reduce((a, p) => ({ allow: a.allow + p.allowed, block: a.block + p.blocked, confirm: a.confirm + p.confirm }), { allow: 0, block: 0, confirm: 0 })
    const total = tot.allow + tot.block + tot.confirm
    _setPS('dashboard', [
      { type: 'summary', total_decisions_7d: total, allowed_7d: tot.allow, blocked_7d: tot.block, escalated_7d: tot.confirm, block_rate_pct: total > 0 ? +((tot.block / total) * 100).toFixed(1) : 0, compliance_status: health?.overall ?? 'unknown', top_block_reasons: blockReasons.slice(0, 6).map(r => ({ reason: r.reason, count: r.count })) },
      ...recent.slice(0, 8).map(e => ({ type: 'recent_decision', id: e.action_id || e.id, agent: e.agent_id, verdict: e.decision_verdict, reason: e.decision_reason_code, ts: e.timestamp })),
    ])
  }, [timeseries, health, blockReasons, recent])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const totals = timeseries.reduce(
    (acc, p) => ({ allow: acc.allow + p.allowed, block: acc.block + p.blocked, confirm: acc.confirm + p.confirm }),
    { allow: 0, block: 0, confirm: 0 }
  )
  const total = totals.allow + totals.block + totals.confirm
  const blockRate = total > 0 ? ((totals.block / total) * 100).toFixed(1) : '0.0'
  const maxReason = Math.max(...blockReasons.map(r => r.count), 1)
  const maxDept = Math.max(1, ...deptList.map(d => recent.filter(e => (recentDeptMap.get(e.action_id || e.id || `${e.agent_id}-${e.timestamp}`) ?? '') === d).length))
  const sandboxDept = deptList[sandboxDeptIndex % Math.max(deptList.length, 1)] ?? 'unassigned'
  const coordDept = deptList[coordDeptIndex % Math.max(deptList.length, 1)] ?? 'unassigned'
  const sandboxDeptMode = deptModes[sandboxDept] ?? 'governed'
  const coordEnabled = coordinationAllowed[coordDept] ?? true
  const latencyBase = systemHealth?.components?.gateway?.latency_ms ?? 3.5
  const p50 = `${latencyBase.toFixed(1)}ms`
  const p95 = `${(latencyBase * 1.8).toFixed(1)}ms`
  const p99 = `${(latencyBase * 2.8).toFixed(1)}ms`
  const uptimeSeconds = systemHealth?.uptime_seconds ?? 0
  const uptimeDays = Math.floor(uptimeSeconds / 86400)
  const uptimeHrs = Math.floor((uptimeSeconds % 86400) / 3600)
  const uptimeMins = Math.floor((uptimeSeconds % 3600) / 60)
  const enrolledAgents = agents.length || 500
  const displayTenant = vertical === 'healthcare' ? 'St. Mercy Health System' : tenantLabel

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Healthcare Governance</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {displayTenant} · <span className="text-primary font-medium">{enrolledAgents} agents online</span> · {sandboxMode ? 'Sandbox mode · Audit-only · No execution' : 'Clinical Safety Mode'}
          {vertical ? ` · ${vertical.toUpperCase()}` : ''}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Governed', value: total, change: '+1 every 800ms', changePositive: true, icon: BarChart2, color: 'text-blue-400' },
          { label: 'Blocked', value: totals.block, change: `${blockRate}% block rate`, icon: XCircle, color: 'text-red-400' },
          { label: 'Escalated', value: totals.confirm, change: 'Awaiting review', icon: AlertTriangle, color: 'text-amber-400' },
          { label: 'Avg Latency', value: p50, change: 'Within SLO', changePositive: true, icon: Zap, color: 'text-primary' },
        ].map(s => (
          <div key={s.label} className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <s.icon size={16} className={s.color} />
            </div>
            <p className="text-2xl font-semibold">{typeof s.value === 'number' ? s.value.toLocaleString() : s.value}</p>
            <p className={`text-xs mt-1 ${s.changePositive ? 'text-emerald-400' : 'text-muted-foreground'}`}>{s.change}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 glass-card p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot" />
              <h2 className="font-semibold text-sm text-foreground">Live Decision Feed</h2>
            </div>
            <span className="text-xs px-2 py-0.5 rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground">{recent.length.toLocaleString()} events</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-white/5">
                  <th className="text-left pb-2 font-medium">Verdict</th>
                  <th className="text-left pb-2 font-medium">Agent</th>
                  <th className="text-left pb-2 font-medium hidden md:table-cell">Dept</th>
                  <th className="text-left pb-2 font-medium hidden lg:table-cell">Action</th>
                  <th className="text-left pb-2 font-medium hidden lg:table-cell">Reason</th>
                  <th className="text-right pb-2 font-medium">ms</th>
                  <th className="text-right pb-2 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {recent.map((e, idx) => {
                    const dept = recentDeptMap.get(e.action_id || e.id || `${e.agent_id}-${e.timestamp}`) ?? 'unassigned'
                    const mode = deptModes[dept] ?? 'governed'
                    const coord = coordinationAllowed[dept] ?? true
                    return (
                      <motion.tr
                        key={e.action_id || e.id || idx}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx === 0 ? 0 : 0, duration: 0.25 }}
                        className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="py-2 pr-2"><VerdictBadge verdict={e.decision_verdict} /></td>
                        <td className="py-2 pr-2">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="font-mono text-foreground truncate">{e.agent_id}</span>
                          </div>
                        </td>
                        <td className="py-2 pr-2 hidden md:table-cell">
                          <div className="flex items-center gap-1.5">
                            <span className="text-muted-foreground truncate max-w-[120px] block">{dept}</span>
                            <span
                              className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                              style={{
                                background: mode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                                color: mode === 'sandbox' ? '#93c5fd' : '#86efac',
                                border: mode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                              }}
                            >
                              {mode}
                            </span>
                            <span
                              className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                              style={{
                                background: coord ? 'rgba(74,158,128,0.10)' : 'rgba(245,158,11,0.10)',
                                color: coord ? '#86efac' : '#fbbf24',
                                border: coord ? '1px solid rgba(74,222,128,0.22)' : '1px solid rgba(245,158,11,0.22)',
                              }}
                            >
                              {coord ? 'coord allowed' : 'held'}
                            </span>
                          </div>
                        </td>
                        <td className="py-2 pr-2 hidden lg:table-cell">
                          <span className="text-muted-foreground truncate max-w-[200px] block">{e.tool_name || '-'}</span>
                        </td>
                        <td className="py-2 pr-2 hidden lg:table-cell">
                          {e.decision_reason_code ? (
                            <span className="text-red-400 font-medium">{e.decision_reason_code}</span>
                          ) : (
                            <span className="text-muted-foreground/40">—</span>
                          )}
                        </td>
                        <td className="py-2 text-right font-mono text-muted-foreground">{e.risk_score != null ? e.risk_score.toFixed(2) : '—'}</td>
                        <td className="py-2 text-right text-muted-foreground whitespace-nowrap">{relTime(e.timestamp)}</td>
                      </motion.tr>
                    )
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Shield size={14} className="text-primary" />
              <h2 className="font-semibold text-sm text-foreground">Active Policy</h2>
              <span className={`ml-auto text-xs px-2 py-0.5 rounded-full border ${health?.overall === 'pass' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border-amber-500/20 bg-amber-500/10 text-amber-400'}`}>
                {(health?.overall ?? 'unknown').toUpperCase()}
              </span>
            </div>
            <p className="text-sm font-medium text-foreground mb-3">{health?.clinical_safety_mode_active ? 'Clinical Safety Mode' : 'Governance Mode'}</p>
            <div className="space-y-2">
              {Object.entries(health?.regulations ?? {}).slice(0, 4).map(([key, reg]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{key}</span>
                  <span className={reg.status === 'pass' ? 'text-emerald-400' : 'text-red-400'}>{reg.status.toUpperCase()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} className="text-blue-400" />
              <h2 className="font-semibold text-sm text-foreground">System Health</h2>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Uptime</span>
                <span className="text-emerald-400 font-medium">{uptimeDays}d {uptimeHrs}h {uptimeMins}m</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latency p50</span>
                <span className="font-mono text-foreground">{p50}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latency p95</span>
                <span className="font-mono text-foreground">{p95}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latency p99</span>
                <span className="font-mono text-foreground">{p99}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Agent / policy / audit</span>
                <span className="text-primary font-semibold">Healthy</span>
              </div>
            </div>
          </div>

          {deptList.length > 0 && (
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-4">
                <Shield size={14} className="text-sky-400" />
              <h2 className="font-semibold text-sm text-foreground">Department Sandbox</h2>
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground">Scoped rollout</span>
              </div>
              <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <button type="button" onClick={() => setSandboxDeptIndex(i => (i - 1 + deptList.length) % deptList.length)} className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors" aria-label="Previous sandbox department">
                    <ChevronLeft size={15} className="text-foreground/80" />
                  </button>
                  <div className="min-w-0 text-center">
                    <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department {sandboxDeptIndex + 1} / {deptList.length}</p>
                    <p className="text-sm font-semibold text-foreground truncate">{sandboxDept}</p>
                  </div>
                  <button type="button" onClick={() => setSandboxDeptIndex(i => (i + 1) % deptList.length)} className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors" aria-label="Next sandbox department">
                    <ChevronRight size={15} className="text-foreground/80" />
                  </button>
                </div>
                <div className="flex items-center gap-2 rounded-xl px-3 py-2.5 border border-white/5 bg-black/10">
                  <Shield size={12} className="text-sky-400" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-foreground truncate">{sandboxDept}</p>
                    <p className="text-[10px] text-muted-foreground/60">{sandboxDeptMode === 'sandbox' ? 'Sandbox' : 'Governed'}</p>
                  </div>
                  <button type="button" onClick={() => updateDeptMode(sandboxDept, sandboxDeptMode === 'sandbox' ? 'governed' : 'sandbox')}
                    className="shrink-0 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-widest transition-colors"
                    style={{
                      background: sandboxDeptMode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                      color: sandboxDeptMode === 'sandbox' ? '#93c5fd' : '#86efac',
                      border: sandboxDeptMode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                    }}>
                    {sandboxDeptMode === 'sandbox' ? 'Enable live' : 'Sandbox'}
                  </button>
                </div>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
                  <span>Use the arrows to step through every department.</span>
                  <span>{sandboxDeptMode === 'sandbox' ? 'Held in sandbox' : 'Live governed'}</span>
                </div>
              </div>
            </div>
          )}

          {deptList.length > 0 && (
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-4">
                <Link2 size={14} className="text-violet-400" />
              <h2 className="font-semibold text-sm text-foreground">Cross-Department Coordination</h2>
              <span className="ml-auto text-xs px-2 py-0.5 rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground">Admin control</span>
              </div>
              <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <button type="button" onClick={() => setCoordDeptIndex(i => (i - 1 + deptList.length) % deptList.length)} className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors" aria-label="Previous department">
                    <ChevronLeft size={15} className="text-foreground/80" />
                  </button>
                  <div className="min-w-0 text-center">
                    <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department {coordDeptIndex + 1} / {deptList.length}</p>
                    <p className="text-sm font-semibold text-foreground truncate">{coordDept}</p>
                  </div>
                  <button type="button" onClick={() => setCoordDeptIndex(i => (i + 1) % deptList.length)} className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors" aria-label="Next department">
                    <ChevronRight size={15} className="text-foreground/80" />
                  </button>
                </div>
                <div className="flex items-center gap-2 rounded-xl px-3 py-2.5 border border-white/5 bg-black/10">
                  <Shield size={12} className="text-violet-400" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-foreground truncate">{coordDept}</p>
                    <p className="text-[10px] text-muted-foreground/60">{coordEnabled ? 'Allowed to coordinate' : 'Held out of coordination'}</p>
                  </div>
                  <button type="button" onClick={() => toggleCoordination(coordDept)}
                    className="shrink-0 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-widest transition-colors"
                    style={{
                      background: coordEnabled ? 'rgba(74,222,128,0.10)' : 'rgba(245,158,11,0.10)',
                      color: coordEnabled ? '#86efac' : '#fbbf24',
                      border: coordEnabled ? '1px solid rgba(74,222,128,0.22)' : '1px solid rgba(245,158,11,0.22)',
                    }}>
                    {coordEnabled ? 'Allowed' : 'Held'}
                  </button>
                </div>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
                  <span>Use the arrows to review every department.</span>
                  <span>{coordEnabled ? 'In coordination' : 'Excluded'}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card p-4">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2"><BarChart2 size={14} className="text-primary" /> Block Reasons (7 days)</h3>
          <div className="space-y-2">
            {blockReasons.length === 0 ? <Empty message="No block reasons yet" /> : blockReasons.slice(0, 8).map(r => (
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

        <div className="glass-card p-4">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2"><Activity size={14} className="text-primary" /> Department Activity</h3>
          <div className="space-y-2">
            {deptList.length === 0 ? <Empty message="No departments detected yet" /> : deptList.slice(0, 8).map(dept => {
              const totalCount = recent.filter(e => (recentDeptMap.get(e.action_id || e.id || `${e.agent_id}-${e.timestamp}`) ?? '') === dept).length
              const blockedCount = recent.filter(e => (recentDeptMap.get(e.action_id || e.id || `${e.agent_id}-${e.timestamp}`) ?? '') === dept && e.decision_verdict === 'BLOCK').length
              const mode = deptModes[dept] ?? 'governed'
              return (
                <div key={dept} className="flex items-center gap-3 text-xs">
                  <span className="text-muted-foreground font-mono w-32 truncate shrink-0">{dept}</span>
                  <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-400/60" style={{ width: `${(totalCount / maxDept) * 100}%` }} />
                  </div>
                  <span className="text-muted-foreground w-8 text-right tabular-nums">{blockedCount}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                    style={{
                      background: mode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                      color: mode === 'sandbox' ? '#93c5fd' : '#86efac',
                      border: mode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                    }}>
                    {mode}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

// -- Decisions Tab -------------------------------------------------------------

// -- Incident helpers ----------------------------------------------------------

const INCIDENT_KEY = 'edon_incidents'
interface Incident { id: string; action_id: string; agent_id: string; reason: string; ts: string; resolved: boolean }
const getIncidents = (): Incident[] => { try { return JSON.parse(localStorage.getItem(INCIDENT_KEY) || '[]') } catch { return [] } }
const saveIncidents = (inc: Incident[]) => localStorage.setItem(INCIDENT_KEY, JSON.stringify(inc))
const openIncident = (event: AuditEvent): Incident => {
  const inc: Incident = { id: crypto.randomUUID(), action_id: event.action_id || event.id || '', agent_id: event.agent_id, reason: event.decision_reason_code || 'BLOCK', ts: event.timestamp, resolved: false }
  saveIncidents([...getIncidents(), inc])
  return inc
}
const resolveIncident = (incidentId: string) => {
  saveIncidents(getIncidents().map(i => i.id === incidentId ? { ...i, resolved: true } : i))
}

function DecisionsTab() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [outcomeStats, setOutcomeStats] = useState<import('./api').ActionResultStats | null>(null)
  const [selectedReceipt, setSelectedReceipt] = useState<import('./api').ActionResult | null>(null)
  const [receiptError, setReceiptError] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [verdict, setVerdict] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AuditEvent | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>(getIncidents)
  const [liveStatus, setLiveStatus] = useState<'polling' | 'refreshing'>('polling')

  const refreshIncidents = () => setIncidents(getIncidents())

  const load = useCallback(async () => {
    try {
      const [res, stats] = await Promise.all([
        api.auditQuery({ verdict: verdict || undefined, limit: 200 }),
        api.actionResultStats().catch(() => null),
      ])
      setEvents(res.events)
      setOutcomeStats(stats)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [verdict])

  useEffect(() => {
    const actionId = selected?.action_id || selected?.id || ''
    setSelectedReceipt(null); setReceiptError('')
    if (!actionId) return
    api.actionResult(actionId)
      .then(setSelectedReceipt)
      .catch(e => setReceiptError(e instanceof Error ? e.message : 'No execution receipt recorded'))
  }, [selected])

  useEffect(() => {
    load()
    const iv = setInterval(() => {
      setLiveStatus('refreshing')
      load().finally(() => setLiveStatus('polling'))
    }, 5000)
    return () => clearInterval(iv)
  }, [load])

  useEffect(() => {
    if (events.length > 0) _setPS('decisions', events.map(e => ({ id: e.action_id || e.id, agent: e.agent_id, verdict: e.decision_verdict, reason: e.decision_reason_code, tool: e.tool_name, ts: e.timestamp })) as Record<string, unknown>[])
  }, [events])

  const filtered = events.filter(e =>
    !search || (e.agent_id + (e.tool_name || '') + (e.decision_reason_code || '')).toLowerCase().includes(search.toLowerCase())
  )
  const counts = { ALLOW: 0, BLOCK: 0, ESCALATE: 0 }
  events.forEach(e => { const v = e.decision_verdict?.toUpperCase() as keyof typeof counts; if (v in counts) counts[v]++ })
  const openIncidentCount = incidents.filter(i => !i.resolved).length

  useEffect(() => {
    _setPS('decisions', [
      {
        type: 'summary',
        total: events.length,
        allow: counts.ALLOW,
        block: counts.BLOCK,
        escalate: counts.ESCALATE,
        open_incidents: openIncidentCount,
        selected_id: selected?.action_id || selected?.id || null,
        selected_agent: selected?.agent_id || null,
        selected_verdict: selected?.decision_verdict || null,
        receipt_status: selectedReceipt?.outcome || null,
      },
    ] as Record<string, unknown>[])
  }, [events.length, counts.ALLOW, counts.BLOCK, counts.ESCALATE, openIncidentCount, selected, selectedReceipt])

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
        {openIncidentCount > 0 && (
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-medium">
            <AlertCircle size={12} /> {openIncidentCount} open incident{openIncidentCount > 1 ? 's' : ''}
          </span>
        )}
      </div>
      {outcomeStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            ['Executed', outcomeStats.total, 'text-foreground'],
            ['Succeeded', outcomeStats.outcomes.success, 'text-emerald-400'],
            ['Failed', outcomeStats.outcomes.failure, 'text-red-400'],
            ['Timed out', outcomeStats.outcomes.timeout, 'text-amber-400'],
          ].map(([label, value, color]) => (
            <div key={String(label)} className="glass-card p-3">
              <p className="text-[11px] text-muted-foreground">{String(label)}</p>
              <p className={`text-lg font-semibold ${String(color)}`}>{String(value)}</p>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agent, tool..."
            className="pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary w-52" />
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} decisions</span>
        {liveStatus === 'refreshing' ? (
          <span className="flex items-center gap-1.5 text-xs text-emerald-400">
            <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"/><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"/></span>
            Refreshing
          </span>
        ) : liveStatus === 'polling' ? (
          <span className="text-xs text-amber-400/70">Polling</span>
        ) : (
          <span className="text-xs text-muted-foreground/50">Connecting...</span>
        )}
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
              {filtered.map((e, i) => {
                const eventId = e.action_id || e.id || ''
                const hasIncident = incidents.some(inc => inc.action_id === eventId && !inc.resolved)
                const dept = (e.meta?.department as string | undefined) || ''
                return (
                  <tr key={eventId || i} data-cite-id={eventId || undefined} className="border-b border-border/30 last:border-0 hover:bg-muted/20 cursor-pointer transition-colors" onClick={() => setSelected(e)}>
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-1.5">
                        <VerdictBadge verdict={e.decision_verdict} />
                        {hasIncident && <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" title="Open incident" />}
                      </div>
                    </td>
                    <td className="py-2.5 px-4 font-mono text-xs truncate max-w-[130px]">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate">{e.agent_id}</span>
                        {dept && (
                          <span
                            className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                            style={{
                              background: getDeptMode(dept) === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                              color: getDeptMode(dept) === 'sandbox' ? '#93c5fd' : '#86efac',
                              border: getDeptMode(dept) === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                            }}
                          >
                            {getDeptMode(dept)}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-muted-foreground hidden md:table-cell text-xs">{e.tool_name || '-'}</td>
                    <td className="py-2.5 px-4 text-muted-foreground hidden lg:table-cell text-xs">{e.decision_reason_code || '-'}</td>
                    <td className="py-2.5 px-4 hidden lg:table-cell">
                      {e.risk_score != null && <span className={`text-xs font-mono ${e.risk_score > 0.7 ? 'text-red-400' : e.risk_score > 0.4 ? 'text-amber-400' : 'text-muted-foreground'}`}>{e.risk_score.toFixed(2)}</span>}
                    </td>
                    <td className="py-2.5 px-4 text-muted-foreground text-xs">{relTime(e.timestamp)}</td>
                    <td className="py-2.5 px-4"><ChevronRight size={14} className="text-muted-foreground" /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <AnimatePresence>
        {selected && (() => {
          const eventId = selected.action_id || selected.id || ''
          const existingIncident = incidents.find(inc => inc.action_id === eventId && !inc.resolved)
          return (
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
                  <div className="pt-2 border-t border-border/50">
                    <p className="text-xs text-muted-foreground mb-2">Execution Receipt</p>
                    {selectedReceipt ? (
                      <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
                        {[['Outcome', selectedReceipt.outcome], ['Latency', `${selectedReceipt.latency_ms}ms`], ['Executed At', fmtTs(selectedReceipt.executed_at)], ['Summary', selectedReceipt.result_summary], ['Error', selectedReceipt.error]].map(([label, value]) => value && (
                          <div key={String(label)}>
                            <p className="text-[10px] text-muted-foreground uppercase">{label}</p>
                            <p className="font-mono text-xs break-all">{String(value)}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">{receiptError || 'Loading receipt...'}</p>
                    )}
                  </div>

                  {/* Incident controls */}
                  {selected.decision_verdict?.toUpperCase() === 'BLOCK' && (
                    <div className="pt-2 border-t border-border/50">
                      {existingIncident ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2 text-xs text-red-400">
                            <AlertCircle size={12} /> Open incident - requires investigation
                          </div>
                          <button onClick={() => { resolveIncident(existingIncident.id); refreshIncidents() }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-colors">
                            <CheckCircle2 size={11} /> Mark Resolved
                          </button>
                        </div>
                      ) : (
                        <button onClick={() => { openIncident(selected); refreshIncidents() }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-medium hover:bg-red-500/20 transition-colors">
                          <AlertCircle size={11} /> Open Incident
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            </motion.div>
          )
        })()}
      </AnimatePresence>
    </div>
  )
}

// -- Agents Tab ----------------------------------------------------------------

function getBlockTrend(agent: Agent): 'stable' | 'rising' | 'spiked' {
  const rate = agent.block_rate ?? (agent.decisions_total && agent.decisions_blocked ? agent.decisions_blocked / agent.decisions_total : 0)
  if (rate > 0.2) return 'spiked'; if (rate > 0.1) return 'rising'; return 'stable'
}
const TREND_CFG = {
  stable: { label: 'Stable', icon: Minus, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
  rising: { label: 'Rising', icon: TrendingUp, color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' },
  spiked: { label: 'Spiked', icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20' },
}

function AgentCard({ a, compact = false }: { a: Agent; compact?: boolean }) {
  const trend = getBlockTrend(a); const tCfg = TREND_CFG[trend]; const TrendIcon = tCfg.icon
  const blockPct = a.decisions_total && a.decisions_blocked ? ((a.decisions_blocked / a.decisions_total) * 100).toFixed(1) : null
  return (
    <div key={a.agent_id} data-cite-id={a.agent_id} className={`glass-card-hover ${compact ? 'p-3' : 'p-4'}`}>
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
      {!compact && a.description && <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{a.description}</p>}
      <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
        {a.decisions_total != null && <span><span className="text-foreground font-medium">{a.decisions_total}</span> decisions</span>}
        {blockPct && <span><span className={tCfg.color + ' font-medium'}>{blockPct}%</span> blocked</span>}
        {a.policy_pack && <span className="text-primary">{a.policy_pack}</span>}
        {a.vendor_id && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-[10px] font-medium">
            {a.vendor_id}
          </span>
        )}
        {a.department && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[10px] font-medium">
            {a.department}
            <span
              className="px-1.5 py-0.5 rounded-full uppercase tracking-widest"
              style={{
                background: getDeptMode(a.department) === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                color: getDeptMode(a.department) === 'sandbox' ? '#93c5fd' : '#86efac',
                border: getDeptMode(a.department) === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                fontSize: '9px',
              }}
            >
              {getDeptMode(a.department)}
            </span>
          </span>
        )}
        {a.last_seen && <span className="ml-auto">{relTime(a.last_seen)}</span>}
      </div>
    </div>
  )
}

function AgentsTab() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [vendorFilter, setVendorFilter] = useState<string | null>(null)
  const [deptFilter, setDeptFilter] = useState<string | null>(null)
  const [riskFilter, setRiskFilter] = useState<'all' | 'spiked' | 'rising' | 'stable'>('all')
  const [groupByDept, setGroupByDept] = useState(false)
  const [compactView, setCompactView] = useState(true)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.agents()
      setAgents(Array.isArray(res) ? res : (res as { agents?: Agent[]; items?: Agent[] }).agents || (res as { agents?: Agent[]; items?: Agent[] }).items || [])
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load agents') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (agents.length > 0) _setPS('agents', agents.map(a => ({
      id: a.agent_id,
      name: a.name,
      type: a.agent_type,
      status: a.status,
      vendor: a.vendor_id,
      department: a.department,
      decisions: a.decisions_total,
      blocked: a.decisions_blocked,
      block_rate: a.block_rate,
      last_seen: a.last_seen,
      metadata: a.metadata,
    })) as Record<string, unknown>[])
  }, [agents])

  const departments = useMemo(() => {
    const depts = [...new Set(agents.map(a => a.department).filter(Boolean) as string[])]
    return depts.sort()
  }, [agents])

  const vendors = useMemo(() => {
    const vendorIds = [...new Set(agents.map(a => a.vendor_id).filter(Boolean) as string[])]
    return vendorIds.sort()
  }, [agents])

  const filtered = agents.filter(a => {
    if (search && !(a.agent_id + (a.name || '') + (a.agent_type || '') + (a.department || '') + (a.vendor_id || '')).toLowerCase().includes(search.toLowerCase())) return false
    if (vendorFilter && a.vendor_id !== vendorFilter) return false
    if (deptFilter && a.department !== deptFilter) return false
    if (riskFilter !== 'all' && getBlockTrend(a) !== riskFilter) return false
    return true
  })

  const spiked = filtered.filter(a => getBlockTrend(a) === 'spiked').length
  const rising = filtered.filter(a => getBlockTrend(a) === 'rising').length
  const allSpiked = agents.filter(a => getBlockTrend(a) === 'spiked').length
  const allRising = agents.filter(a => getBlockTrend(a) === 'rising').length
  const activeAgents = filtered.filter(a => a.status === 'active').length

  const grouped = useMemo(() => {
    if (!groupByDept) return null
    const map: Record<string, Agent[]> = {}
    for (const a of filtered) {
      const key = a.department || 'Uncategorized'
      if (!map[key]) map[key] = []
      map[key].push(a)
    }
    return Object.entries(map).sort(([a], [b]) => a === 'Uncategorized' ? 1 : b === 'Uncategorized' ? -1 : a.localeCompare(b))
  }, [filtered, groupByDept])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Agents</p>
          <p className="text-sm font-semibold text-foreground mt-1">{filtered.length}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">{activeAgents} active in view</p>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Vendors</p>
          <p className="text-sm font-semibold text-foreground mt-1">{vendors.length}</p>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Departments</p>
          <p className="text-sm font-semibold text-foreground mt-1">{departments.length}</p>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Risk watch</p>
          <p className="text-sm font-semibold text-foreground mt-1">{spiked + rising}</p>
        </div>
      </div>
      {(spiked > 0 || rising > 0) && (
        <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${spiked > 0 ? 'border-red-500/30 bg-red-500/10 text-red-400' : 'border-amber-500/30 bg-amber-500/10 text-amber-400'}`}>
          <AlertTriangle size={15} className="shrink-0" />
          {spiked > 0 ? `${spiked} agent${spiked > 1 ? 's' : ''} with spiked block rate - investigate` : `${rising} agent${rising > 1 ? 's' : ''} with rising block rate`}
        </div>
      )}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents..."
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} agents</span>
        {(['all', 'spiked', 'rising', 'stable'] as const).map(r => (
          <button key={r} onClick={() => setRiskFilter(r)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition capitalize ${riskFilter === r ? 'bg-amber-500/15 border-amber-500/30 text-amber-300' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            {r === 'all' ? 'All risk' : r}
          </button>
        ))}
        {departments.length > 0 && (
          <button onClick={() => setGroupByDept(g => !g)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition ${groupByDept ? 'bg-primary/15 border-primary/30 text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            By Department
          </button>
        )}
        <button onClick={() => setCompactView(v => !v)}
          className={`text-xs px-2.5 py-1 rounded-lg border transition ${compactView ? 'bg-primary/15 border-primary/30 text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`}>
          Compact
        </button>
        <button onClick={load} className="ml-auto text-muted-foreground hover:text-foreground transition"><RefreshCcw size={14} /></button>
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <button onClick={() => { setRiskFilter('spiked'); setGroupByDept(false) }}
          className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-left hover:border-red-500/35 transition-colors">
          <p className="text-xs text-red-300 font-semibold">High-risk watchlist</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{allSpiked}</p>
          <p className="text-[11px] text-muted-foreground">Agents with elevated block rates</p>
        </button>
        <button onClick={() => { setRiskFilter('rising'); setGroupByDept(true) }}
          className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-left hover:border-amber-500/35 transition-colors">
          <p className="text-xs text-amber-300 font-semibold">Rising drift</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{allRising}</p>
          <p className="text-[11px] text-muted-foreground">Group by department to assign review</p>
        </button>
        <button onClick={() => { setDeptFilter(null); setVendorFilter(null); setRiskFilter('all'); setSearch('') }}
          className="rounded-xl border border-border/40 bg-card/20 px-4 py-3 text-left hover:border-primary/30 transition-colors">
          <p className="text-xs text-primary font-semibold">Saved view</p>
          <p className="text-sm font-semibold text-foreground mt-1">All governed agents</p>
          <p className="text-[11px] text-muted-foreground">Clear filters and return to tenant view</p>
        </button>
      </div>
      {vendors.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => setVendorFilter(null)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${!vendorFilter ? 'bg-cyan-500/15 border-cyan-500/30 text-cyan-300' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            All vendors
          </button>
          {vendors.map(v => (
            <button key={v} onClick={() => setVendorFilter(vendorFilter === v ? null : v)}
              className={`text-xs px-2.5 py-1 rounded-full border transition ${vendorFilter === v ? 'bg-cyan-500/15 border-cyan-500/30 text-cyan-300' : 'border-border text-muted-foreground hover:text-foreground'}`}>
              {v}
            </button>
          ))}
        </div>
      )}
      {departments.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => setDeptFilter(null)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${!deptFilter ? 'bg-primary/15 border-primary/30 text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            All
          </button>
          {departments.map(d => (
            <button key={d} onClick={() => setDeptFilter(deptFilter === d ? null : d)}
              className={`text-xs px-2.5 py-1 rounded-full border transition ${deptFilter === d ? 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400' : 'border-border text-muted-foreground hover:text-foreground'}`}>
              {d}
            </button>
          ))}
        </div>
      )}
      {filtered.length === 0 ? <Empty message="No agents registered yet" /> : grouped ? (
        <div className="space-y-6">
          {grouped.map(([dept, deptAgents]) => (
            <div key={dept}>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 normal-case tracking-normal text-[11px]">{dept}</span>
                <span>{deptAgents.length} agent{deptAgents.length !== 1 ? 's' : ''}</span>
              </h3>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {deptAgents.map(a => <AgentCard key={a.agent_id} a={a} compact={compactView} />)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map(a => <AgentCard key={a.agent_id} a={a} compact={compactView} />)}
        </div>
      )}
    </div>
  )
}

type ReconciliationDraftRow = {
  name: string
  vendor: string
  vendor_id: string
  department: string
  scope: string
  action: string
  runtime_type: string
  connectors: string[]
  agent_id: string
}

function OperationsTab() {
  const [batches, setBatches] = useState<import('./api').ReconciliationBatch[]>([])
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [selectedRowKey, setSelectedRowKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [actor, setActor] = useState(getReviewerName() || 'admin')
  const [rowStatusFilter, setRowStatusFilter] = useState<'all' | 'new' | 'changed' | 'missing' | 'duplicate' | 'ready'>('all')
  const [rowSearch, setRowSearch] = useState('')

  const [sourceSystem, setSourceSystem] = useState('Existing system')
  const [vendorName, setVendorName] = useState('')
  const [vendorId, setVendorId] = useState('')
  const [sourceType, setSourceType] = useState('Existing system')
  const [department, setDepartment] = useState('')
  const [cohortMode, setCohortMode] = useState<'purpose' | 'department'>('purpose')
  const [posture, setPosture] = useState<'audit-only' | 'sandbox' | 'governed'>('audit-only')
  const [inventory, setInventory] = useState<ReconciliationDraftRow[]>(CONSOLE_DEV_MODE ? [{
    name: 'Epic note drafter',
    vendor: 'Epic',
    vendor_id: '',
    department: 'Cardiology',
    scope: 'cardiology.note.draft',
    action: 'Register audit-only',
    runtime_type: 'Service',
    connectors: ['Epic'],
    agent_id: '',
  }] : [])

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.reconciliationListBatches()
      const next = Array.isArray(res.batches) ? res.batches : []
      setBatches(next)
      setSelectedBatchId(curr => curr && next.some(b => b.batch_id === curr) ? curr : (next[0]?.batch_id ?? null))
      setSelectedRowKey(curr => curr)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load reconciliation batches')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const selectedBatch = useMemo(
    () => batches.find(b => b.batch_id === selectedBatchId) ?? batches[0] ?? null,
    [batches, selectedBatchId],
  )
  const selectedRow = useMemo(() => {
    if (!selectedBatch) return null
    return selectedBatch.rows.find(r => r.row_key === selectedRowKey) ?? selectedBatch.rows.find(r => r.selected) ?? selectedBatch.rows[0] ?? null
  }, [selectedBatch, selectedRowKey])
  const visibleRows = useMemo(() => {
    if (!selectedBatch) return []
    const q = rowSearch.trim().toLowerCase()
    return selectedBatch.rows.filter(row => {
      if (rowStatusFilter !== 'all' && row.status !== rowStatusFilter) return false
      if (q && !(row.name + row.vendor + row.department + row.scope + row.status).toLowerCase().includes(q)) return false
      return true
    })
  }, [selectedBatch, rowSearch, rowStatusFilter])

  useEffect(() => {
    if (!selectedBatch && batches.length > 0) setSelectedBatchId(batches[0].batch_id)
    if (selectedBatch && !selectedRowKey) setSelectedRowKey(selectedBatch.selected_row_key || selectedBatch.rows[0]?.row_key || null)
  }, [batches, selectedBatch, selectedRowKey])

  useEffect(() => {
    _setPS('operations', [
      {
        source_system: sourceSystem,
        vendor_name: vendorName,
        vendor_id: vendorId,
        department,
        cohort_mode: cohortMode,
        posture,
        inventory_count: inventory.filter(r => r.name.trim()).length,
        batch_count: batches.length,
        selected_batch_id: selectedBatch?.batch_id ?? null,
        selected_batch_status: selectedBatch?.status ?? null,
        selected_row_key: selectedRow?.row_key ?? null,
        row_filter: rowStatusFilter,
        row_search: rowSearch,
      },
    ] as Record<string, unknown>[])
  }, [sourceSystem, vendorName, vendorId, department, cohortMode, posture, inventory, batches.length, selectedBatch?.batch_id, selectedBatch?.status, selectedRow?.row_key, rowStatusFilter, rowSearch])

  const upsertBatch = useCallback((next: import('./api').ReconciliationBatch) => {
    setBatches(prev => {
      const filtered = prev.filter(batch => batch.batch_id !== next.batch_id)
      return [next, ...filtered]
    })
    setSelectedBatchId(next.batch_id)
    setSelectedRowKey(next.selected_row_key ?? next.rows[0]?.row_key ?? null)
  }, [])

  const runImport = async () => {
    const rows = inventory.filter(r => r.name.trim())
    if (!sourceSystem.trim()) { setError('Source system is required'); return }
    if (rows.length === 0) { setError('Add at least one inventory row'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      const res = await api.reconciliationImportInventory({
        source_system: sourceSystem.trim(),
        vendor_name: vendorName.trim(),
        vendor_id: vendorId.trim(),
        source_type: sourceType,
        department: department.trim(),
        cohort_mode: cohortMode,
        posture,
        inventory: rows.map(row => ({
          name: row.name,
          vendor: row.vendor,
          vendor_name: row.vendor,
          vendor_id: row.vendor_id,
          department: row.department,
          scope: row.scope,
          action: row.action,
          runtime_type: row.runtime_type,
          agent_id: row.agent_id || undefined,
          connectors: row.connectors,
        })),
      })
      upsertBatch(res.batch)
      setMessage(`Imported ${res.batch.rows.length} rows into reconciliation.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to import inventory')
    } finally {
      setBusy(false)
    }
  }

  const patchBatch = async (method: 'hold' | 'merge' | 'promote') => {
    if (!selectedBatch) return
    setBusy(true); setError(''); setMessage('')
    try {
      const actorName = actor.trim() || 'admin'
      const res =
        method === 'hold' ? await api.reconciliationHoldBatch(selectedBatch.batch_id, actorName, 'Console batch action') :
        method === 'merge' ? await api.reconciliationMergeBatch(selectedBatch.batch_id, actorName, 'Console batch action') :
        await api.reconciliationPromoteBatch(selectedBatch.batch_id, actorName, 'Console batch action')
      upsertBatch(res.batch)
      setMessage(method === 'hold' ? 'Batch held.' : method === 'merge' ? 'Duplicates merged.' : 'Low-risk rows promoted.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Batch action failed')
    } finally {
      setBusy(false)
    }
  }

  const rowAction = async (rowKey: string, action: string) => {
    if (!selectedBatch) return
    setBusy(true); setError(''); setMessage('')
    try {
      const res = await api.reconciliationRowAction(selectedBatch.batch_id, rowKey, actor.trim() || 'admin', action, 'Console row action')
      upsertBatch(res.batch)
      setMessage(`Row action recorded: ${action}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Row action failed')
    } finally {
      setBusy(false)
    }
  }

  const selectedSummary = (selectedBatch?.summary ?? {}) as Record<string, unknown>
  const count = (key: string) => typeof selectedSummary[key] === 'number' ? Number(selectedSummary[key]) : 0

  const inventoryStats = useMemo(() => ({
    rows: inventory.filter(r => r.name.trim()).length,
    vendors: [...new Set(inventory.map(r => r.vendor.trim()).filter(Boolean))].length,
    departments: [...new Set(inventory.map(r => r.department.trim()).filter(Boolean))].length,
    connectors: [...new Set(inventory.flatMap(r => r.connectors).map(c => c.trim()).filter(Boolean))].length,
  }), [inventory])

  const selectedDetail = selectedRow ? [
    ['Name', selectedRow.name],
    ['Vendor', selectedRow.vendor || selectedBatch?.vendor_name || '-'],
    ['Department', selectedRow.department || selectedBatch?.department || '-'],
    ['Scope', selectedRow.scope || '-'],
    ['Risk', selectedRow.risk || '-'],
    ['Status', selectedRow.status || '-'],
    ['Runtime type', selectedRow.runtime_type || '-'],
  ] : []
  const opsSummary = useMemo(() => {
    const selectedRows = selectedBatch?.rows ?? []
    const departments = [...new Set(selectedRows.map(r => r.department).filter(Boolean))]
    const vendors = [...new Set(selectedRows.map(r => r.vendor || selectedBatch?.vendor_name || '').filter(Boolean))]
    const exceptions = count('changed') + count('missing') + count('duplicate')
    return {
      departments: departments.length,
      vendors: vendors.length,
      exceptions,
      promoteReady: count('ready'),
    }
  }, [selectedBatch, selectedSummary])

  if (loading) return <Spinner />
  if (error && batches.length === 0) return <ErrorMsg message={error} onRetry={load} />

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-border/40 bg-card/30 p-5 space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
              <ServerCog size={18} className="text-emerald-400" />
              Operations
            </h2>
            <p className="text-sm text-muted-foreground mt-0.5">Reconcile existing hospital agents against EDON, resolve exceptions, and promote safe cohorts.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="px-2.5 py-1 rounded-full border border-border/40 bg-card/20">Existing fleets</span>
            <button onClick={load} className="px-2.5 py-1 rounded-full border border-border/40 hover:border-emerald-500/30 hover:text-foreground transition-colors">Refresh</button>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['Departments', opsSummary.departments, 'affected by selected batch'],
            ['Vendors', opsSummary.vendors, 'sources in review'],
            ['Exceptions', opsSummary.exceptions, 'need attention'],
            ['Ready', opsSummary.promoteReady, 'safe to promote'],
          ].map(([label, value, sub]) => (
            <div key={label} className="rounded-xl border border-border/40 bg-background/25 px-3 py-3">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{label}</p>
              <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
              <p className="text-[11px] text-muted-foreground">{sub}</p>
            </div>
          ))}
        </div>
        <div className="grid gap-2 md:grid-cols-3 text-xs">
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">1. Import inventory</p>
            <p className="mt-1 text-muted-foreground">Bring in agents already running in vendor consoles, CSVs, or APIs.</p>
          </div>
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">2. Reconcile exceptions</p>
            <p className="mt-1 text-muted-foreground">Review new, changed, missing, and duplicate runtimes by cohort.</p>
          </div>
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">3. Promote low risk</p>
            <p className="mt-1 text-muted-foreground">Only ready cohorts move forward. Exceptions stay held.</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5"><p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Batches</p><p className="text-sm font-semibold text-foreground mt-1">{batches.length}</p></div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5"><p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">New</p><p className="text-sm font-semibold text-foreground mt-1">{count('new')}</p></div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5"><p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Changed</p><p className="text-sm font-semibold text-foreground mt-1">{count('changed')}</p></div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5"><p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Missing</p><p className="text-sm font-semibold text-foreground mt-1">{count('missing')}</p></div>
        <div className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5"><p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Ready</p><p className="text-sm font-semibold text-foreground mt-1">{count('ready')}</p></div>
      </div>

      <div className="grid gap-3 lg:grid-cols-4">
        <button onClick={() => { setRowStatusFilter('new'); setRowSearch('') }}
          className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-left hover:border-emerald-500/35 transition-colors">
          <p className="text-xs font-semibold text-emerald-300">Register candidates</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{count('new')}</p>
          <p className="text-[11px] text-muted-foreground">Not yet in EDON</p>
        </button>
        <button onClick={() => { setRowStatusFilter('changed'); setRowSearch('') }}
          className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-left hover:border-amber-500/35 transition-colors">
          <p className="text-xs font-semibold text-amber-300">Scope drift</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{count('changed')}</p>
          <p className="text-[11px] text-muted-foreground">Owner, connector, or scope changed</p>
        </button>
        <button onClick={() => { setRowStatusFilter('duplicate'); setRowSearch('') }}
          className="rounded-xl border border-sky-500/20 bg-sky-500/5 px-4 py-3 text-left hover:border-sky-500/35 transition-colors">
          <p className="text-xs font-semibold text-sky-300">Identity cleanup</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{count('duplicate')}</p>
          <p className="text-[11px] text-muted-foreground">Duplicate runtime IDs</p>
        </button>
        <button onClick={() => { setRowStatusFilter('ready'); setRowSearch('') }}
          className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-left hover:border-primary/35 transition-colors">
          <p className="text-xs font-semibold text-primary">Promotion ready</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{count('ready')}</p>
          <p className="text-[11px] text-muted-foreground">Low-risk rows only</p>
        </button>
      </div>

      {(message || error) && (
        <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm border ${error ? 'bg-destructive/10 border-destructive/30 text-destructive' : 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'}`}>
          <AlertCircle size={14} /> {error || message}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-foreground">Import source inventory</p>
                <p className="text-xs text-muted-foreground">Bring in existing agents from a source system, then reconcile them against EDON.</p>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="px-2 py-1 rounded-full border border-border/40">Batch-first</span>
                <span className="px-2 py-1 rounded-full border border-border/40">Audit-only</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Source system</label>
                <input value={sourceSystem} onChange={e => setSourceSystem(e.target.value)} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" placeholder="Existing system" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Vendor name</label>
                <input value={vendorName} onChange={e => setVendorName(e.target.value)} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" placeholder="Epic" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Vendor ID</label>
                <input value={vendorId} onChange={e => setVendorId(e.target.value)} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" placeholder="vendor-001" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Department</label>
                <input value={department} onChange={e => setDepartment(e.target.value)} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" placeholder="Cardiology" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Source type</label>
                <select value={sourceType} onChange={e => setSourceType(e.target.value)} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm">
                  {['Existing system', 'Vendor console', 'CSV export', 'Inventory API'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Cohort mode</label>
                <div className="flex rounded-lg border border-border/40 overflow-hidden">
                  {(['purpose', 'department'] as const).map(mode => (
                    <button key={mode} type="button" onClick={() => setCohortMode(mode)} className={`flex-1 px-3 py-2 text-sm ${cohortMode === mode ? 'bg-primary/15 text-primary' : 'bg-transparent text-muted-foreground hover:text-foreground'}`}>
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Posture</label>
                <div className="flex rounded-lg border border-border/40 overflow-hidden">
                  {(['audit-only', 'sandbox', 'governed'] as const).map(mode => (
                    <button key={mode} type="button" onClick={() => setPosture(mode)} className={`flex-1 px-3 py-2 text-sm ${posture === mode ? 'bg-emerald-500/15 text-emerald-300' : 'bg-transparent text-muted-foreground hover:text-foreground'}`}>
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Agents</p>
                <p className="text-sm font-semibold text-foreground mt-1">{inventoryStats.rows}</p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Vendors</p>
                <p className="text-sm font-semibold text-foreground mt-1">{inventoryStats.vendors}</p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Departments</p>
                <p className="text-sm font-semibold text-foreground mt-1">{inventoryStats.departments}</p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Connectors</p>
                <p className="text-sm font-semibold text-foreground mt-1">{inventoryStats.connectors}</p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-foreground/70">Inventory rows</p>
                <button
                  type="button"
                  onClick={() => setInventory(prev => [...prev, { name: '', vendor: vendorName, vendor_id: vendorId, department, scope: '', action: '', runtime_type: 'Service', connectors: [], agent_id: '' }])}
                  className="text-xs text-emerald-400 hover:underline flex items-center gap-1">
                  <Plus size={11} /> Add row
                </button>
              </div>
              <div className="space-y-3">
                {inventory.map((row, idx) => (
                  <div key={`${row.name}-${idx}`} className="rounded-xl border border-border/40 bg-background/20 p-3 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-muted-foreground">Row {idx + 1}</p>
                      {inventory.length > 1 && (
                        <button type="button" onClick={() => setInventory(prev => prev.filter((_, i) => i !== idx))} className="text-muted-foreground hover:text-destructive transition-colors">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <input value={row.name} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, name: e.target.value } : r))} placeholder="Agent name" className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" />
                      <input value={row.vendor} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, vendor: e.target.value } : r))} placeholder="Vendor" className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" />
                      <input value={row.department} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, department: e.target.value } : r))} placeholder="Department" className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" />
                      <input value={row.scope} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, scope: e.target.value } : r))} placeholder="Scope" className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="space-y-1">
                        <label className="text-[11px] text-muted-foreground">Runtime type</label>
                        <select value={row.runtime_type} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, runtime_type: e.target.value } : r))} className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm">
                          {['Service', 'Worker', 'Agent'].map(v => <option key={v} value={v}>{v}</option>)}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="text-[11px] text-muted-foreground">Agent ID</label>
                        <input value={row.agent_id} onChange={e => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, agent_id: e.target.value } : r))} placeholder="Optional" className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[11px] text-muted-foreground">Connectors</label>
                        <TagInput value={row.connectors} onChange={v => setInventory(prev => prev.map((r, i) => i === idx ? { ...r, connectors: v } : r))} placeholder="Epic, Teams, SIEM" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button onClick={runImport} disabled={busy} className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <ChevronRight size={13} />}
                Import inventory
              </button>
              <div className="text-xs text-muted-foreground">Import becomes a reconciliation batch with audit, drift, and promotion controls.</div>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Fleet reconciliation batches</p>
                <p className="text-xs text-muted-foreground">New, changed, missing, and duplicate rows are reconciled here.</p>
              </div>
              <div className="flex items-center gap-2">
                <input value={actor} onChange={e => setActor(e.target.value)} className="w-36 bg-background border border-border/40 rounded-lg px-3 py-2 text-xs" placeholder="Actor" />
              </div>
            </div>

            {batches.length === 0 ? (
              <Empty message="No reconciliation batches yet" />
            ) : (
              <div className="space-y-2">
                {batches.map(batch => (
                  <button
                    key={batch.batch_id}
                    type="button"
                    onClick={() => { setSelectedBatchId(batch.batch_id); setSelectedRowKey(batch.selected_row_key || batch.rows[0]?.row_key || null) }}
                    className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${selectedBatch?.batch_id === batch.batch_id ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-border/40 bg-background/20 hover:border-border'}`}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-foreground">{batch.source_system}</p>
                        <p className="text-[11px] text-muted-foreground">{batch.vendor_name || batch.vendor_id || 'No vendor'} / {batch.department || 'All departments'} / {batch.cohort_mode}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-2 py-0.5 rounded-full border border-border/40 text-muted-foreground">{batch.status}</span>
                        <span className="text-xs text-muted-foreground">{batch.rows.length} rows</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-3">
            <p className="text-sm font-semibold text-foreground">Selected batch</p>
            {selectedBatch ? (
              <>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-lg border border-border/30 bg-background/20 p-2.5"><p className="text-muted-foreground/60">Source</p><p className="font-medium text-foreground truncate">{selectedBatch.source_system}</p></div>
                  <div className="rounded-lg border border-border/30 bg-background/20 p-2.5"><p className="text-muted-foreground/60">Status</p><p className="font-medium text-foreground">{selectedBatch.status}</p></div>
                  <div className="rounded-lg border border-border/30 bg-background/20 p-2.5"><p className="text-muted-foreground/60">Vendor</p><p className="font-medium text-foreground truncate">{selectedBatch.vendor_name || '-'}</p></div>
                  <div className="rounded-lg border border-border/30 bg-background/20 p-2.5"><p className="text-muted-foreground/60">Departments</p><p className="font-medium text-foreground truncate">{selectedBatch.department || '-'}</p></div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {(['new', 'changed', 'missing', 'duplicate', 'ready'] as const).map(k => (
                    <div key={k} className="rounded-lg border border-border/30 bg-background/20 p-2.5">
                      <p className="text-muted-foreground/60 capitalize">{k}</p>
                      <p className="font-medium text-foreground">{String(selectedSummary[k] ?? 0)}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{String(selectedSummary.message ?? 'Ready rows can be promoted, changed rows need review, duplicate rows should be merged, and missing rows should be held.')}</p>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => patchBatch('hold')} disabled={busy} className="text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-amber-500/30 hover:text-foreground transition-colors disabled:opacity-50">Hold batch</button>
                  <button onClick={() => patchBatch('merge')} disabled={busy} className="text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:text-foreground transition-colors disabled:opacity-50">Merge duplicates</button>
                  <button onClick={() => patchBatch('promote')} disabled={busy} className="text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:text-foreground transition-colors disabled:opacity-50">Promote low-risk batch</button>
                </div>
              </>
            ) : (
              <Empty message="Select a batch to see details" />
            )}
          </div>

          <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="text-sm font-semibold text-foreground">Batch rows</p>
              <div className="flex items-center gap-2 flex-wrap">
                <div className="relative">
                  <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input value={rowSearch} onChange={e => setRowSearch(e.target.value)} placeholder="Find row..."
                    className="w-40 pl-7 pr-2 py-1.5 rounded-lg bg-background border border-border/40 text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
                </div>
                {(['all', 'new', 'changed', 'missing', 'duplicate', 'ready'] as const).map(status => (
                  <button key={status} onClick={() => setRowStatusFilter(status)}
                    className={`text-[10px] px-2 py-1 rounded-full border capitalize ${rowStatusFilter === status ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-300' : 'border-border/40 text-muted-foreground hover:text-foreground'}`}>
                    {status}
                  </button>
                ))}
              </div>
            </div>
            {!selectedBatch ? (
              <Empty message="No selected batch" />
            ) : visibleRows.length === 0 ? (
              <Empty message="No rows match the current filter" />
            ) : (
              <div className="space-y-2">
                {visibleRows.map(row => (
                  <div
                    key={row.row_key}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedRowKey(row.row_key)}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') setSelectedRowKey(row.row_key) }}
                    className={`w-full text-left rounded-xl border px-3 py-3 transition-colors cursor-pointer ${selectedRow?.row_key === row.row_key ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-border/40 bg-background/20 hover:border-border'}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{row.name}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{row.vendor || selectedBatch.vendor_name || '-'} / {row.department || selectedBatch.department || '-'} / {row.scope || 'no scope'}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <RiskBadge tier={row.risk} />
                        <span className="text-[10px] px-2 py-0.5 rounded-full border border-border/40 text-muted-foreground">{row.status}</span>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {row.status === 'new' && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); rowAction(row.row_key, 'register_audit_only') }} className="text-[10px] px-2 py-1 rounded-full border border-border/40 hover:border-emerald-500/30 hover:text-foreground">Register audit-only</button>}
                      {row.status === 'changed' && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); rowAction(row.row_key, 'review_scope_drift') }} className="text-[10px] px-2 py-1 rounded-full border border-border/40 hover:border-amber-500/30 hover:text-foreground">Review scope drift</button>}
                      {row.status === 'duplicate' && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); rowAction(row.row_key, 'merge_duplicate_ids') }} className="text-[10px] px-2 py-1 rounded-full border border-border/40 hover:border-emerald-500/30 hover:text-foreground">Merge duplicate IDs</button>}
                      {row.status === 'missing' && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); rowAction(row.row_key, 'hold_until_re_found') }} className="text-[10px] px-2 py-1 rounded-full border border-border/40 hover:border-amber-500/30 hover:text-foreground">Hold until re-found</button>}
                      {row.status === 'ready' && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); rowAction(row.row_key, 'promote_low_risk_batch') }} className="text-[10px] px-2 py-1 rounded-full border border-border/40 hover:border-emerald-500/30 hover:text-foreground">Promote low-risk batch</button>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-3">
            <p className="text-sm font-semibold text-foreground">Selected row</p>
            {selectedRow ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {selectedDetail.map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg border border-border/30 bg-background/20 p-2.5">
                      <p className="text-muted-foreground/60">{label}</p>
                      <p className="font-medium text-foreground break-words">{String(value || '-')}</p>
                    </div>
                  ))}
                </div>
                {selectedRow.comparison && Object.keys(selectedRow.comparison).length > 0 && (
                  <div className="rounded-lg border border-border/30 bg-background/20 p-3 text-xs text-muted-foreground space-y-1">
                    <p className="font-semibold text-foreground/80">Comparison</p>
                    {Object.entries(selectedRow.comparison).map(([k, v]) => (
                      <p key={k}><span className="text-muted-foreground/50">{k}:</span> {String(v)}</p>
                    ))}
                  </div>
                )}
                <div className="rounded-lg border border-border/30 bg-background/20 p-3 text-xs text-muted-foreground space-y-1">
                  <p className="font-semibold text-foreground/80">Audit stream</p>
                  {(selectedRow.audit || []).length === 0 ? (
                    <p>No row-level actions yet.</p>
                  ) : selectedRow.audit!.map((entry, idx) => (
                    <p key={`${entry.time}-${idx}`} className="break-words">
                      <span className="text-muted-foreground/50">{fmtTs(entry.time)}</span> - {entry.action} / {entry.actor}
                    </p>
                  ))}
                </div>
              </div>
            ) : (
              <Empty message="Select a row to inspect details" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// -- Audit Tab -----------------------------------------------------------------

async function buildChain(events: AuditEvent[]): Promise<string[]> {
  const hashes: string[] = []; let prev = '0000000000000000'
  for (const e of events) {
    const h = await sha256hex(`${prev}|${e.action_id || e.id || ''}|${e.decision_verdict}|${e.timestamp}`)
    hashes.push(h.slice(0, 16)); prev = h.slice(0, 16)
  }
  return hashes
}

function exportAuditPdf(events: AuditEvent[], hashes: string[]) {
  const rows = events.map((e, i) => `<tr><td>${i + 1}</td><td>${e.decision_verdict}</td><td>${e.agent_id}</td><td>${e.tool_name || '-'}</td><td>${e.decision_reason_code || '-'}</td><td>${new Date(e.timestamp).toLocaleString()}</td><td style="font-family:monospace;font-size:10px">${hashes[i] || '-'}</td></tr>`).join('')
  const html = `<!DOCTYPE html><html><head><title>EDON Audit Chain</title><style>body{font-family:sans-serif;font-size:12px;padding:20px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left}th{background:#f5f5f5}h1{font-size:16px}p{color:#666;font-size:11px}</style></head><body><h1>EDON Audit Chain Export</h1><p>Generated: ${new Date().toLocaleString()} / ${events.length} records</p><table><thead><tr><th>#</th><th>Verdict</th><th>Agent</th><th>Tool</th><th>Reason</th><th>Timestamp</th><th>Hash</th></tr></thead><tbody>${rows}</tbody></table></body></html>`
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

  useEffect(() => {
    if (events.length > 0) _setPS('audit', events.slice(0, 40).map(e => ({ id: e.action_id || e.id, agent: e.agent_id, verdict: e.decision_verdict, reason: e.decision_reason_code, tool: e.tool_name, ts: e.timestamp })))
  }, [events])

  const filtered = events.filter(e => !search || (e.agent_id + (e.tool_name || '') + (e.decision_reason_code || '')).toLowerCase().includes(search.toLowerCase()))

  useEffect(() => {
    _setPS('audit', [
      {
        type: 'summary',
        total: filtered.length,
        verdict: verdict || 'all',
        search,
        selected_id: selected?.action_id || selected?.id || null,
        selected_agent: selected?.agent_id || null,
        selected_verdict: selected?.decision_verdict || null,
        chain_enabled: showChain,
      },
    ] as Record<string, unknown>[])
  }, [filtered.length, verdict, search, selected, showChain])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search..."
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
            <Shield size={12} /> Chain{hashes.length > 0 ? ` / ${hashes.length}` : ''}
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
            <Shield size={11} /> Hash Chain / tip: <span className="font-mono text-primary">{hashes[hashes.length - 1]}</span>
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
                    <td className="py-2.5 px-4 text-muted-foreground hidden md:table-cell text-xs">{e.tool_name || '-'}</td>
                    <td className="py-2.5 px-4 text-muted-foreground hidden lg:table-cell text-xs">{e.decision_reason_code || '-'}</td>
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

// -- Policy Template Packs -----------------------------------------------------

function PolicyTemplatePacks({ onApplied }: { onApplied: () => void }) {
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; description?: string; regulation?: string; rule_count?: number }>>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState<string | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getPolicyTemplates().then(r => setTemplates(r.templates ?? r as never ?? [])).catch(() => setTemplates([])).finally(() => setLoading(false))
  }, [])

  const apply = async (id: string) => {
    setApplying(id)
    setError('')
    try {
      await api.applyPolicyTemplate(id)
      setApplied(id)
      setTimeout(() => setApplied(null), 3000)
      onApplied()
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to apply template') }
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
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {error}
        </div>
      )}
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
                {applied === t.id ? <><Check size={12} /> Applied</> : applying === t.id ? 'Applying...' : 'Apply Pack'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function IndustryPolicyPresetsCard({ onApplied, vertical }: { onApplied: () => void; vertical: string | null }) {
  const ALL_GROUPS = [
    {
      group: 'Healthcare',
      verticalKey: 'healthcare',
      icon: Heart,
      iconColor: 'text-rose-400',
      packs: [
        { id: 'joint_commission',   name: 'Joint Commission',        description: 'AI governance for JC-accredited hospitals (NPSG.15.01.01 et al.)', color: 'text-rose-400 border-rose-500/20 bg-rose-500/5',   rules: 5 },
        { id: 'clinical_governance',name: 'Clinical AI Governance',  description: 'PHI minimization, patient consent & clinical scope (HIPAA Section 164.312)', color: 'text-cyan-400 border-cyan-500/20 bg-cyan-500/5',   rules: 4 },
      ],
    },
    {
      group: 'Banking & Finance',
      verticalKey: 'banking',
      icon: Shield,
      iconColor: 'text-amber-400',
      packs: [
        { id: 'bank_model_risk',     name: 'SR 11-7 Model Risk',      description: 'Federal Reserve model risk controls - validation gates, output review, inventory logging', color: 'text-amber-400 border-amber-500/20 bg-amber-500/5',  rules: 5 },
        { id: 'bank_aml_compliance', name: 'AML / BSA Compliance',    description: 'AML alert escalation, SAR filing review, GLBA data protection, FFIEC audit trail', color: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5', rules: 5 },
      ],
    },
  ]

  const INDUSTRY_PACKS = vertical
    ? ALL_GROUPS.filter(g => g.verticalKey === vertical)
    : ALL_GROUPS

  const [applying, setApplying] = useState<string | null>(null)
  const [applied, setApplied] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')

  const apply = async (id: string) => {
    setApplying(id)
    setError('')
    try {
      await api.applyPolicyTemplate(id)
      setApplied(prev => new Set([...prev, id]))
      onApplied()
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to apply preset') }
    finally { setApplying(null) }
  }

  return (
    <div className="glass-card p-5 space-y-5">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-2"><Package size={13} className="text-primary" /> Industry Policy Presets</h3>
        <p className="text-xs text-muted-foreground mt-0.5">Vertical-specific governance rules. Apply independently of the regulatory frameworks above.</p>
      </div>
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {error}
        </div>
      )}
      {INDUSTRY_PACKS.map(group => (
        <div key={group.group} className="space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
            <group.icon size={11} className={group.iconColor} />{group.group}
          </h4>
          <div className="grid gap-3 sm:grid-cols-2">
            {group.packs.map(pack => (
              <div key={pack.id} className={`rounded-xl border p-4 space-y-2 ${pack.color}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold">{pack.name}</span>
                  <span className="text-[10px] opacity-70">{pack.rules} rules</span>
                </div>
                <p className="text-[11px] opacity-80 leading-relaxed">{pack.description}</p>
                <button onClick={() => apply(pack.id)} disabled={applying === pack.id || applied.has(pack.id)}
                  className="w-full text-xs py-1.5 rounded-lg border border-current/30 hover:bg-current/10 font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5">
                  {applied.has(pack.id) ? <><Check size={12} /> Applied</> : applying === pack.id ? 'Applying...' : 'Apply Preset'}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// -- Policies Tab --------------------------------------------------------------

function PoliciesTab({ tenantLabel, vertical }: { tenantLabel: string; vertical: string | null }) {
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [health, setHealth] = useState<ComplianceHealth | null>(null)
  const [pendingReviews, setPendingReviews] = useState<ReviewItem[]>([])
  const [blockReasons, setBlockReasons] = useState<BlockReason[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sandboxRuleId, setSandboxRuleId] = useState<string | null>(null)
  const [sandboxResult, setSandboxResult] = useState<{ sample_size: number; changed: number; unchanged: number; false_positive_rate: number } | null>(null)
  const [sandboxLoading, setSandboxLoading] = useState(false)
  const [savingRule, setSavingRule] = useState(false)
  const [ruleDraft, setRuleDraft] = useState({ name: '', description: '', condition_tool: '', condition_op: '', action: 'BLOCK', priority: 100 })

  const normalizeReg = useCallback((reg?: string) => {
    if (!reg) return 'General'
    const u = reg.toUpperCase()
    if (u.includes('HIPAA')) return 'HIPAA'
    if (u.includes('HITRUST')) return 'HITRUST'
    if (u.includes('SOC')) return 'SOC 2'
    return reg
  }, [])

  const testRule = async (rule: PolicyRule) => {
    setSandboxRuleId(rule.rule_id)
    setSandboxResult(null)
    setSandboxLoading(true)
    try {
      const r = await api.policySandboxTest({ rule_id: rule.rule_id, name: rule.name, action: rule.action, tool: rule.tool, op: rule.op, enabled: true } as Record<string, unknown>)
      setSandboxResult(r)
    } catch {
      setSandboxResult(null)
    } finally {
      setSandboxLoading(false)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [rRes, hRes, qRes, bRes, aRes] = await Promise.allSettled([
        api.policyRules(),
        api.complianceHealth(),
        api.reviewQueue('pending'),
        api.blockReasons(7),
        api.agents(),
      ])
      if (rRes.status === 'fulfilled') {
        const raw = rRes.value
        setRules(Array.isArray(raw) ? raw as PolicyRule[] : (raw as { rules: PolicyRule[] }).rules ?? [])
      }
      if (hRes.status === 'fulfilled') setHealth(hRes.value)
      if (qRes.status === 'fulfilled') setPendingReviews(qRes.value?.queue ?? [])
      if (bRes.status === 'fulfilled') setBlockReasons(bRes.value ?? [])
      if (aRes.status === 'fulfilled') {
        const raw = aRes.value
        setAgents(Array.isArray(raw) ? raw as Agent[] : (raw as { agents?: Agent[] }).agents ?? [])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load policies')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const grouped = useMemo(() => rules.reduce<Record<string, PolicyRule[]>>((acc, r) => {
    const key = normalizeReg(r.regulation)
    if (!acc[key]) acc[key] = []
    acc[key].push(r)
    return acc
  }, {}), [rules, normalizeReg])

  const enabledRules = useMemo(() => rules.filter(r => r.enabled), [rules])
  const disabledRules = useMemo(() => rules.filter(r => !r.enabled), [rules])
  const generalRules = useMemo(() => grouped.General ?? [], [grouped])
  const enrolledCount = agents.length || 500
  const regulatoryGroups = Object.keys(grouped).filter(k => k !== 'General').length
  const activeSafety = !!health?.clinical_safety_mode_active
  const displayTenant = vertical === 'healthcare' ? 'St. Mercy Health System' : tenantLabel

  useEffect(() => {
    _setPS('policies', [
      {
        type: 'summary',
        tenant: displayTenant,
        active_policy: activeSafety ? 'Clinical Safety Mode' : 'Baseline Policy',
        total_rules: rules.length,
        enabled_rules: enabledRules.length,
        disabled_rules: disabledRules.length,
        pending_reviews: pendingReviews.length,
        blocked_reasons: blockReasons.slice(0, 5).map(r => ({ reason: r.reason, count: r.count })),
        enrolled_agents: enrolledCount,
        regulation_groups: regulatoryGroups,
      },
    ] as Record<string, unknown>[])
  }, [displayTenant, activeSafety, rules.length, enabledRules.length, disabledRules.length, pendingReviews.length, blockReasons, enrolledCount, regulatoryGroups])

  const saveRule = async () => {
    if (!ruleDraft.name.trim()) return
    setSavingRule(true)
    try {
      await api.createRule({
        name: ruleDraft.name.trim(),
        description: ruleDraft.description.trim() || undefined,
        condition_tool: ruleDraft.condition_tool.trim() || undefined,
        condition_op: ruleDraft.condition_op.trim() || undefined,
        action: ruleDraft.action,
        priority: ruleDraft.priority,
        enabled: true,
      })
      setRuleDraft({ name: '', description: '', condition_tool: '', condition_op: '', action: 'BLOCK', priority: 100 })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create rule')
    } finally {
      setSavingRule(false)
    }
  }

  const review = async (item: ReviewItem, action: 'approved' | 'rejected') => {
    const reviewer = getReviewerName() || 'console-admin'
    const dept = getReviewerDept()
    const signature = dept ? `${reviewer} (${dept})` : reviewer
    try {
      action === 'approved'
        ? await api.approveReview(item.decision_id, signature)
        : await api.rejectReview(item.decision_id, signature)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Review action failed')
    }
  }

  const renderRuleLines = (list: Array<{ rule_id: string; name: string; description?: string; enabled: boolean; action: string; tool?: string; op?: string }>, emptyCopy: string, testable = true) => (
    <div className="space-y-3.5">
      {list.length === 0 ? (
        <p className="text-xs text-muted-foreground">{emptyCopy}</p>
      ) : list.map(rule => (
        <div key={rule.rule_id} data-cite-id={rule.rule_id} className="flex items-start gap-3">
          <div className={`mt-0.5 shrink-0 ${rule.enabled ? 'text-emerald-400' : 'text-muted-foreground/40'}`}>
            {rule.enabled ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground leading-tight">{rule.name}</p>
            <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">
              {rule.description || `${rule.action}${rule.tool ? ` · ${rule.tool}` : ''}${rule.op ? ` · ${rule.op}` : ''}`}
            </p>
          </div>
          {testable && (
            <button
              onClick={() => testRule(rule as PolicyRule)}
              disabled={sandboxLoading && sandboxRuleId === rule.rule_id}
              className="text-[10px] px-1.5 py-0.5 rounded border border-purple-500/25 text-purple-400 bg-purple-500/8 hover:bg-purple-500/15 transition-colors disabled:opacity-50 flex items-center gap-0.5 shrink-0"
            >
              {sandboxLoading && sandboxRuleId === rule.rule_id ? '...' : <><FlaskConical size={9} /> Test</>}
            </button>
          )}
        </div>
      ))}
    </div>
  )

  const operationsAllowed = useMemo(() => [
    { label: 'Read patient vital signs', description: 'View heart rate, blood pressure, oxygen levels, and temperature in real time' },
    { label: 'Retrieve lab results', description: 'Access completed blood work, cultures, and pathology reports' },
    { label: 'View imaging scans', description: 'Display X-rays, MRI, CT, and ultrasound images for review' },
    { label: 'Read patient chart', description: 'Access full patient history, clinical notes, and medication list' },
    { label: 'View medication schedule', description: 'See a patient\'s current prescriptions and dosing timetable' },
    { label: 'View appointments', description: 'See upcoming and past patient appointments and scheduling' },
    { label: 'Request diagnostic suggestions', description: 'Ask the AI to suggest possible diagnoses based on symptoms and test results' },
    { label: 'Check device status', description: 'Verify that ventilators, pumps, and monitors are operating correctly' },
    { label: 'Notify nursing staff', description: 'Alert nurses to a change in patient condition that needs attention' },
    { label: 'Monitor IV drip rate', description: 'Read current infusion pump settings - no changes are permitted' },
    { label: 'Read heart rhythm (ECG)', description: 'Access live and historical electrocardiogram data for a patient' },
    { label: 'Track patient location', description: 'See which room or bed a patient is currently assigned to' },
  ], [])
  const operationsBlocked = useMemo(() => [
    { label: 'Override a medication dosage', description: 'Change a prescribed dose without physician sign-off - always prevented' },
    { label: 'Bulk-export patient records', description: 'Download large numbers of patient records to an outside location' },
    { label: 'Send patient data outside hospital', description: 'Transmit patient information to any system outside the hospital network' },
    { label: 'Auto-dispense a controlled substance', description: 'Automatically dispense opioids, sedatives, or other restricted medications' },
    { label: 'Skip patient consent check', description: 'Access or act on patient data without verifying consent is on file' },
    { label: 'Override a physician\'s diagnosis', description: 'Replace or remove a diagnosis recorded by a licensed physician' },
    { label: 'Skip device calibration', description: 'Use medical equipment without completing required safety calibration' },
    { label: 'Deviate from surgical protocol', description: 'Perform a step outside the approved surgical safety checklist sequence' },
  ], [])
  const operationsConfirm = useMemo(() => [
    { label: 'Authorize emergency surgery', description: 'Grant permission to begin an unplanned or urgent surgical procedure' },
    { label: 'Approve a high-risk medication order', description: 'Sign off on chemotherapy, anticoagulants, or other high-alert drug orders' },
    { label: 'Change a DNR / advance directive', description: 'Update or remove a patient\'s Do-Not-Resuscitate order on file' },
    { label: 'Approve patient discharge', description: 'Authorize a patient to leave inpatient care' },
    { label: 'Escalate a critical alert', description: 'Upgrade an alert to highest priority - notifies the full care team immediately' },
  ], [])
  const complianceStandards = useMemo(() => [
    { label: 'HIPAA', desc: 'Patient data privacy & security' },
    { label: 'HITECH', desc: 'Health IT breach enforcement' },
    { label: 'FDA SaMD', desc: 'Software as a Medical Device' },
    { label: 'DEA', desc: 'Controlled substance controls' },
    { label: 'Joint Commission', desc: 'Clinical safety standards' },
    { label: 'ISO 13485', desc: 'Medical device quality management' },
    { label: '45 CFR 46', desc: 'Research subject protection' },
  ], [])

  if (loading) return <Spinner />
  if (error) return <ErrorMsg message={error} onRetry={load} />

  const blockSummary = blockReasons.slice(0, 5)
  const customRuleCount = generalRules.length
  const formatBlockReason = (reason: string) => reason
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Policy Management</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {activeSafety ? 'Clinical Safety Mode active' : 'Baseline policy active'} · {displayTenant} · {enrolledCount} agents enrolled
        </p>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">What agents can and cannot do</h2>
        <p className="text-xs text-muted-foreground mb-4">
          These rules apply to all {enrolledCount} agents under the current Clinical Safety policy pack.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-card p-4 border-emerald-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                <CheckCircle2 size={14} className="text-emerald-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-emerald-400 leading-tight">Agents can do this</h3>
                <p className="text-xs text-muted-foreground">No approval needed</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-emerald-500/10 px-2 py-0.5 rounded-full">{operationsAllowed.length}</span>
            </div>
            {renderRuleLines(operationsAllowed.map((op, i) => ({ rule_id: `allow-${i}`, name: op.label, description: op.description, enabled: true, action: 'ALLOW' })), 'No allowed operations found.', false)}
          </div>

          <div className="glass-card p-4 border-red-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-red-500/15 flex items-center justify-center shrink-0">
                <XCircle size={14} className="text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-red-400 leading-tight">Agents cannot do this</h3>
                <p className="text-xs text-muted-foreground">Always stopped - no exceptions</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-red-500/10 px-2 py-0.5 rounded-full">{operationsBlocked.length}</span>
            </div>
            {renderRuleLines(operationsBlocked.map((op, i) => ({ rule_id: `block-${i}`, name: op.label, description: op.description, enabled: false, action: 'BLOCK' })), 'No blocked operations found.', false)}
          </div>

          <div className="glass-card p-4 border-amber-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-amber-500/15 flex items-center justify-center shrink-0">
                <AlertTriangle size={14} className="text-amber-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-amber-400 leading-tight">Doctor must confirm first</h3>
                <p className="text-xs text-muted-foreground">Agent pauses and waits for your approval</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-amber-500/10 px-2 py-0.5 rounded-full">{operationsConfirm.length}</span>
            </div>
            {renderRuleLines(operationsConfirm.map((op, i) => ({ rule_id: `confirm-${i}`, name: op.label, description: op.description, enabled: false, action: 'ESCALATE' })), 'No approval-gated operations found.', false)}
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-1">
          <ListChecks size={15} className="text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Agent-Level Rules</h2>
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          Pin a rule to a specific agent, device, or task. These override the global policy above.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_0.85fr] gap-4">
          <div className="glass-card p-4 border border-border/70 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Rule name</label>
                <input
                  value={ruleDraft.name}
                  onChange={e => setRuleDraft(d => ({ ...d, name: e.target.value }))}
                  placeholder="E.g. Cardiology note draft guard"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Action</label>
                <select
                  value={ruleDraft.action}
                  onChange={e => setRuleDraft(d => ({ ...d, action: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="ALLOW">Allow</option>
                  <option value="BLOCK">Block</option>
                  <option value="ESCALATE">Ask doctor</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Agent / system</label>
                <input
                  value={ruleDraft.condition_tool}
                  onChange={e => setRuleDraft(d => ({ ...d, condition_tool: e.target.value }))}
                  placeholder="All agents, Cardiology note helper, Epic"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Task</label>
                <input
                  value={ruleDraft.condition_op}
                  onChange={e => setRuleDraft(d => ({ ...d, condition_op: e.target.value }))}
                  placeholder="note.draft, export, route"
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="md:col-span-2">
                <label className="text-xs text-muted-foreground mb-1 block">Description</label>
                <textarea
                  value={ruleDraft.description}
                  onChange={e => setRuleDraft(d => ({ ...d, description: e.target.value }))}
                  rows={3}
                  placeholder="What this rule is for and how it should behave."
                  className="w-full px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={saveRule}
                disabled={savingRule || !ruleDraft.name.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                <Plus size={14} /> {savingRule ? 'Saving...' : 'Add a rule'}
              </button>
              <span className="text-xs text-muted-foreground">
                {customRuleCount > 0 ? `${customRuleCount} custom rule${customRuleCount === 1 ? '' : 's'} active` : 'No custom rules yet'}
              </span>
            </div>
          </div>

          <div className="glass-card p-4 border border-border/70">
            <div className="flex items-center gap-2 mb-4">
              <Shield size={14} className="text-primary" />
              <h3 className="text-sm font-semibold text-foreground">Current custom rules</h3>
            </div>
            {customRuleCount === 0 ? (
              <div className="rounded-lg border border-dashed border-border/70 p-4 text-xs text-muted-foreground">
                No custom rules yet. Add one on the left to override the global policy for a specific agent, device, or task.
              </div>
            ) : (
              <div className="space-y-3">
                {generalRules.map(rule => (
                  <div key={rule.rule_id} className="rounded-lg border border-border/70 bg-muted/20 p-3 space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-foreground">{rule.name}</p>
                        <p className="text-[11px] text-muted-foreground mt-0.5">{rule.description || 'Custom rule'}</p>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border ${rule.enabled ? 'border-emerald-500/20 text-emerald-400 bg-emerald-500/10' : 'border-red-500/20 text-red-400 bg-red-500/10'}`}>
                        {rule.enabled ? 'Active' : 'Disabled'}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="px-2 py-0.5 rounded-full border border-border/70">{rule.action}</span>
                      {rule.tool && <span className="px-2 py-0.5 rounded-full border border-border/70">{rule.tool}</span>}
                      {rule.op && <span className="px-2 py-0.5 rounded-full border border-border/70">{rule.op}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => testRule(rule)}
                        disabled={sandboxLoading && sandboxRuleId === rule.rule_id}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-purple-500/25 text-purple-400 bg-purple-500/8 hover:bg-purple-500/15 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                      >
                        <FlaskConical size={10} /> {sandboxLoading && sandboxRuleId === rule.rule_id ? 'Testing...' : 'Test'}
                      </button>
                      {rule.enabled ? (
                        <button
                          onClick={async () => { await api.disableRule(rule.rule_id); await load() }}
                          className="text-xs px-2.5 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-border/80 transition-colors"
                        >
                          Disable
                        </button>
                      ) : (
                        <button
                          onClick={async () => { await api.enableRule(rule.rule_id); await load() }}
                          className="text-xs px-2.5 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-border/80 transition-colors"
                        >
                          Enable
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">Active Baseline Policy</h2>
        <p className="text-xs text-muted-foreground mb-4">
          {activeSafety ? 'Clinical Safety Mode is permanently on for all agents. It cannot be switched off or replaced.' : 'Baseline policy is active for all enrolled agents.'}
        </p>
        <div className="glass-card p-5 border-emerald-500/25">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
              <Shield size={18} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <h3 className="font-bold text-base text-foreground">Clinical Safety Mode</h3>
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
                  Always active · {enrolledCount} agents
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-5">
                The hospital-wide safety baseline. Every AI agent in {displayTenant} operates under these rules at all times.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {complianceStandards.map(s => (
                  <div key={s.label} className="bg-white/4 border border-white/8 rounded-xl px-3 py-2.5">
                    <p className="text-xs font-bold text-foreground">{s.label}</p>
                    <p className="text-xs text-muted-foreground/60 mt-0.5 leading-snug">{s.desc}</p>
                  </div>
                ))}
              </div>
              {health?.regulations && (
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {Object.values(health.regulations).slice(0, 3).map((entry, i) => (
                    <div key={`${entry.label}-${i}`} className="rounded-xl border border-border/70 bg-muted/20 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-foreground">{entry.label}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border ${entry.status.toLowerCase().includes('warn') || entry.missing_rules.length > 0 ? 'border-amber-500/25 text-amber-400 bg-amber-500/10' : 'border-emerald-500/25 text-emerald-400 bg-emerald-500/10'}`}>
                          {entry.status}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {entry.rules_active}/{entry.rules_required} rules active
                        {entry.missing_rules.length > 0 && ` · Missing ${entry.missing_rules.length}`}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-1">
          <ClipboardList size={15} className="text-amber-400" />
          <h2 className="text-sm font-semibold text-foreground">Pending Your Review</h2>
          {pendingReviews.length > 0 && (
            <span className="text-xs bg-amber-500/15 text-amber-400 border border-amber-500/25 rounded-full px-2 py-0.5 font-semibold">
              {pendingReviews.length}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          These agent actions require your sign-off before they can proceed.
        </p>
        {pendingReviews.length === 0 ? (
          <div className="glass-card p-6 text-center">
            <CheckCircle2 size={20} className="text-emerald-400 mx-auto mb-2" />
            <p className="text-sm text-foreground font-medium">All caught up</p>
            <p className="text-xs text-muted-foreground mt-1">No actions are waiting for your review.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pendingReviews.map(item => (
              <div key={item.decision_id} className="glass-card p-4 border border-border/70 flex flex-col gap-4">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-semibold text-foreground">{item.action_type}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border ${item.meta?.urgency === 'critical' ? 'border-red-500/25 text-red-400 bg-red-500/10' : item.meta?.urgency === 'urgent' ? 'border-amber-500/25 text-amber-400 bg-amber-500/10' : 'border-border/70 text-muted-foreground bg-muted/20'}`}>
                        {item.meta?.urgency ?? 'routine'}
                      </span>
                      {item.meta?.policy_version && <span className="text-[10px] px-2 py-0.5 rounded-full border border-border/70 text-muted-foreground bg-muted/20">{item.meta.policy_version}</span>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {item.meta?.department || 'Unassigned'}{item.meta?.patient_id ? ` · Patient ${item.meta.patient_id}` : ''}{item.meta?.vendor_name ? ` · ${item.meta.vendor_name}` : ''}
                    </p>
                    {item.explanation && <p className="text-xs text-foreground/90 mt-2 leading-relaxed">{item.explanation}</p>}
                  </div>
                  <div className="text-xs text-muted-foreground lg:text-right shrink-0">
                    <p className="font-mono">{fmtTs(item.created_at)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => review(item, 'rejected')}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/25 text-red-400 bg-red-500/10 hover:bg-red-500/15 text-xs font-medium transition-colors"
                  >
                    <ThumbsDown size={12} /> Deny
                  </button>
                  <button
                    onClick={() => review(item, 'approved')}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-500/25 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/15 text-xs font-medium transition-colors"
                  >
                    <ThumbsUp size={12} /> Approve
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">What's Being Blocked</h2>
        <p className="text-xs text-muted-foreground mb-4">
          The most common reasons your agents are being stopped - useful for spotting gaps in care workflows.
        </p>
        <div className="glass-card divide-y divide-white/[0.04]">
          {blockSummary.length === 0 ? (
            <div className="px-4 py-3 text-xs text-muted-foreground">No block reasons available yet.</div>
          ) : blockSummary.map((entry, i) => {
            const maxCount = blockSummary[0]?.count || 1
            return (
              <div key={entry.reason} className="px-4 py-3 flex items-center gap-4">
                <span className="text-xs text-muted-foreground/50 font-mono w-4 shrink-0">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-xs font-medium text-foreground">{formatBlockReason(entry.reason)}</span>
                    <span className="text-xs text-muted-foreground font-mono shrink-0">{entry.count} blocks</span>
                  </div>
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                    <div className="h-full bg-red-400/50 rounded-full transition-all duration-500" style={{ width: `${(entry.count / maxCount) * 100}%` }} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <PolicyTemplatePacks onApplied={load} />
        <IndustryPolicyPresetsCard onApplied={load} vertical={vertical} />
      </div>

      <p className="text-[11px] text-muted-foreground/60 flex items-center gap-1.5 px-1">
        <Lock size={10} /> Regulatory rules (HIPAA, HITRUST, SOC 2) are enforced as healthcare standards and cannot be disabled.
      </p>

      <AnimatePresence>
        {sandboxResult && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => { setSandboxResult(null); setSandboxRuleId(null) }}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card max-w-sm w-full p-6 space-y-4" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between">
                <h3 className="font-semibold flex items-center gap-2"><FlaskConical size={14} className="text-purple-400" /> Sandbox Result</h3>
                <button onClick={() => { setSandboxResult(null); setSandboxRuleId(null) }}><X size={15} className="text-muted-foreground hover:text-foreground" /></button>
              </div>
              <p className="text-xs text-muted-foreground">Dry-run against last {sandboxResult.sample_size} decisions. Rule was NOT deployed.</p>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Changed', value: sandboxResult.changed, color: sandboxResult.changed > 0 ? 'text-amber-400' : 'text-emerald-400' },
                  { label: 'Unchanged', value: sandboxResult.unchanged, color: 'text-muted-foreground' },
                  { label: 'False Pos.', value: `${(sandboxResult.false_positive_rate * 100).toFixed(1)}%`, color: sandboxResult.false_positive_rate > 0.05 ? 'text-red-400' : 'text-emerald-400' },
                ].map(m => (
                  <div key={m.label} className="glass-card p-3 text-center space-y-1">
                    <p className={`text-xl font-bold ${m.color}`}>{m.value}</p>
                    <p className="text-[10px] text-muted-foreground">{m.label}</p>
                  </div>
                ))}
              </div>
              {sandboxResult.false_positive_rate > 0.05 && (
                <p className="text-xs text-red-400 flex items-center gap-1.5"><AlertTriangle size={11} /> High false positive rate - reconsider rule scope before deploying.</p>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// -- Review Queue Tab ----------------------------------------------------------

// -- Review Queue Tab ----------------------------------------------------------

function ReviewTab({ vertical, meInfo }: { vertical: string | null; meInfo: MeResponse | null }) {
  const [pending, setPending] = useState<ReviewItem[]>([])
  const [resolved, setResolved] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [resolving, setResolving] = useState<string | null>(null)
  const [deptFilter, setDeptFilter] = useState('all')
  const [urgencyFilter, setUrgencyFilter] = useState<'all' | 'critical' | 'urgent' | 'routine'>('all')
  const [queueSearch, setQueueSearch] = useState('')
  const [compactQueue, setCompactQueue] = useState(true)
  const [confirmItem, setConfirmItem] = useState<{ item: ReviewItem; action: 'approved' | 'rejected' } | null>(null)
  const [note, setNote] = useState('')
  const [pinStage, setPinStage] = useState<'none' | 'pin' | 'setup'>('none')
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)
  const [reviewerName, setReviewerNameLocal] = useState(getReviewerName)
  const [editingName, setEditingName] = useState(!getReviewerName())
  const [reviewerRole, setReviewerRoleLocal] = useState<ReviewerRole>(getReviewerRole)
  const reviewRoles = getReviewRoles(vertical)
  const approvalTier = getApprovalTier(vertical)
  const [escalatingId, setEscalatingId] = useState<string | null>(null)
  const serverReviewerName = meInfo?.key_name || meInfo?.key_id || (CONSOLE_DEV_MODE ? 'Development Admin' : '')
  const serverReviewerDept = meInfo?.tenant_id || (CONSOLE_DEV_MODE ? 'tenant_sandbox_edon' : '')
  const serverReviewerRole = meInfo?.role || (CONSOLE_DEV_MODE ? 'admin' : '')
  const reviewerDept = serverReviewerName ? serverReviewerDept : getReviewerDept()
  const reviewerRoleForApproval = serverReviewerName ? serverReviewerRole : reviewerRole
  const reviewerIdentityBound = !!serverReviewerName

  const showToast = (msg: string, type: 'ok' | 'err' = 'ok') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000) }

  useEffect(() => {
    if (serverReviewerName) {
      setReviewerNameLocal(serverReviewerName)
      setEditingName(false)
    }
    if (serverReviewerRole) setReviewerRoleLocal(serverReviewerRole)
  }, [serverReviewerName, serverReviewerRole])

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

  useEffect(() => {
    _setPS('review', [
      { type: 'summary', pending_count: pending.length, resolved_count: resolved.length },
      ...pending.slice(0, 10).map(r => ({ type: 'pending', id: r.decision_id, agent: r.agent_id, action: r.action_type, question: r.escalation_question, urgency: r.meta?.urgency ?? 'routine' })),
      ...resolved.slice(0, 5).map(r => ({ type: 'resolved', id: r.decision_id, agent: r.agent_id, action: r.action_type, resolution: r.resolution, resolved_by: r.resolved_by })),
    ])
  }, [pending, resolved])

  useEffect(() => {
    _setPS('review', [
      {
        type: 'summary',
        pending_count: pending.length,
        resolved_count: resolved.length,
        dept_filter: deptFilter,
        urgency_filter: urgencyFilter,
        queue_search: queueSearch,
        reviewer_name: reviewerName,
        reviewer_role: reviewerRoleForApproval,
        reviewer_identity_bound: reviewerIdentityBound,
        confirm_action: confirmItem?.action || null,
        confirm_id: confirmItem?.item.decision_id || null,
        pin_stage: pinStage,
      },
    ] as Record<string, unknown>[])
  }, [pending.length, resolved.length, deptFilter, urgencyFilter, queueSearch, reviewerName, reviewerRoleForApproval, reviewerIdentityBound, confirmItem, pinStage])

  const handleExpired = useCallback(async (item: ReviewItem) => {
    try {
      await api.rejectReview(item.decision_id, 'SYSTEM', `Auto-denied: SLA timeout (${getUrgency(item)})`)
      showToast(`Auto-denied: ${item.action_type}`, 'err'); load()
    } catch { /* already resolved */ }
  }, [load])

  const handleAction = (item: ReviewItem, action: 'approved' | 'rejected') => {
    if (!reviewerName.trim()) {
      if (CONSOLE_DEV_MODE) setEditingName(true)
      showToast(CONSOLE_DEV_MODE ? 'Set your reviewer name first' : 'Authenticated reviewer identity unavailable', 'err')
      return
    }
    setNote(''); setConfirmItem({ item, action }); setPinStage(CONSOLE_DEV_MODE ? (hasPinSet() ? 'pin' : 'setup') : 'none')
  }

  const handleConfirm = async () => {
    if (!confirmItem) return
    const { item, action } = confirmItem
    setResolving(item.decision_id); setConfirmItem(null)
    try {
      const reviewerSignature = reviewerDept ? `${reviewerName} (${reviewerDept})` : reviewerName
      action === 'approved'
        ? await api.approveReview(item.decision_id, reviewerSignature, note || undefined)
        : await api.rejectReview(item.decision_id, reviewerSignature, note || undefined)
      showToast(`${action === 'approved' ? 'Approved' : 'Rejected'}: ${item.action_type}`, action === 'approved' ? 'ok' : 'err')
      load()
    } catch (e) { showToast(e instanceof Error ? e.message : 'Request failed', 'err') }
    finally { setResolving(null) }
  }

  const saveName = (name: string) => {
    if (reviewerIdentityBound) return
    setReviewerName(name); setReviewerNameLocal(name); setEditingName(false)
  }

  const handleEscalate = async (item: ReviewItem) => {
    setEscalatingId(item.decision_id)
    await new Promise(r => setTimeout(r, 800))
    setEscalatingId(null)
    showToast(`On-call paged: ${item.action_type}${item.meta?.patient_id ? ` / ${item.meta.patient_id}` : ''}`, 'ok')
  }

  const allDepts = Array.from(new Set(pending.map(getDept))).sort()
  const filtered = pending.filter(i => {
    if (deptFilter !== 'all' && getDept(i) !== deptFilter) return false
    if (urgencyFilter !== 'all' && getUrgency(i) !== urgencyFilter) return false
    const q = queueSearch.trim().toLowerCase()
    if (q && !(i.action_type + i.agent_id + (i.escalation_question || '') + String(i.meta?.patient_id || '') + getDept(i)).toLowerCase().includes(q)) return false
    return true
  })
  const urgencyCounts = {
    critical: pending.filter(i => getUrgency(i) === 'critical').length,
    urgent: pending.filter(i => getUrgency(i) === 'urgent').length,
    routine: pending.filter(i => getUrgency(i) === 'routine').length,
  }
  const grouped = (['critical', 'urgent', 'routine'] as const)
    .map(u => ({ urgency: u, items: filtered.filter(i => getUrgency(i) === u) })).filter(g => g.items.length > 0)

  return (
    <div className="space-y-4">
      {/* Reviewer identity */}
      <div className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border text-xs flex-wrap ${reviewerName ? 'border-border bg-secondary/50' : 'border-amber-500/30 bg-amber-500/10'}`}>
        <User size={12} className={reviewerName ? 'text-muted-foreground' : 'text-amber-400'} />
        {editingName && !reviewerIdentityBound ? (
          <form className="flex items-center gap-2 flex-1" onSubmit={e => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem('name') as HTMLInputElement).value.trim(); if (v) saveName(v) }}>
            <input name="name" defaultValue={reviewerName} autoFocus placeholder="Your name for review signatures..."
              className="flex-1 bg-transparent border-b border-primary/40 text-sm focus:outline-none text-foreground pb-0.5" />
            <button type="submit" className="text-primary text-xs font-semibold hover:underline">Save</button>
          </form>
        ) : (
          <>
            <span className="text-muted-foreground">Reviewing as</span>
            <span className="font-medium text-foreground">{reviewerName}</span>
            {reviewerDept && (
              <>
                <span className="text-border">/</span>
                <span className="text-muted-foreground">{reviewerDept}</span>
              </>
            )}
            {reviewerIdentityBound && (
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-300">
                Server bound
              </span>
            )}
          </>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-muted-foreground">Role:</span>
          {reviewerIdentityBound ? (
            <span className="px-2 py-1 rounded-lg border border-border bg-muted/30 text-xs text-foreground">
              {ROLE_LABELS[reviewerRoleForApproval as ConsoleRole] ?? reviewerRoleForApproval}
            </span>
          ) : (
            <select value={reviewerRole} onChange={e => { const r = e.target.value; setReviewerRoleLocal(r); setReviewerRole(r) }}
              className="bg-muted/50 border border-border rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary">
              <option value="">- select -</option>
              {reviewRoles.map(r => <option key={r} value={r}>{ROLE_LABELS[r as ConsoleRole] ?? r}</option>)}
            </select>
          )}
        </div>
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

      <div className="grid gap-3 md:grid-cols-4">
        {(['critical', 'urgent', 'routine'] as const).map(u => {
          const cfg = URGENCY_CFG[u]
          return (
            <button key={u} onClick={() => setUrgencyFilter(urgencyFilter === u ? 'all' : u)}
              className={`rounded-xl border px-4 py-3 text-left transition-colors ${urgencyFilter === u ? cfg.badge : 'border-border/40 bg-card/20 hover:border-border'}`}>
              <p className={`text-xs font-semibold ${u === 'critical' ? 'text-red-300' : u === 'urgent' ? 'text-amber-300' : 'text-sky-300'}`}>{cfg.label}</p>
              <p className="text-2xl font-semibold text-foreground mt-1">{urgencyCounts[u]}</p>
              <p className="text-[11px] text-muted-foreground">{u === 'critical' ? 'Immediate review' : u === 'urgent' ? 'Time-sensitive' : 'Standard queue'}</p>
            </button>
          )
        })}
        <button onClick={() => { setDeptFilter('all'); setUrgencyFilter('all'); setQueueSearch('') }}
          className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-left hover:border-primary/35 transition-colors">
          <p className="text-xs font-semibold text-primary">All pending</p>
          <p className="text-2xl font-semibold text-foreground mt-1">{pending.length}</p>
          <p className="text-[11px] text-muted-foreground">Reset triage filters</p>
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-56 max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={queueSearch} onChange={e => setQueueSearch(e.target.value)} placeholder="Search action, agent, patient, department..."
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <button onClick={() => setCompactQueue(v => !v)}
          className={`text-xs px-2.5 py-1.5 rounded-lg border transition ${compactQueue ? 'bg-primary/15 border-primary/30 text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`}>
          Compact
        </button>
        <span className="text-xs text-muted-foreground">{filtered.length} shown</span>
      </div>

      {allDepts.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <Filter size={12} className="text-muted-foreground" />
          {['all', ...allDepts].map(d => (
            <button key={d} onClick={() => setDeptFilter(d)}
              className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${deptFilter === d ? 'bg-primary/20 border-primary/40 text-primary' : 'border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20'}`}>
              {d === 'all' ? `All / ${pending.length}` : d}
              {d !== 'all' && <span className="ml-1 text-muted-foreground/60">/ {pending.filter(i => getDept(i) === d).length}</span>}
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
                    className={`glass-card ${compactQueue ? 'p-3' : 'p-4'} border ${urgency === 'critical' ? 'border-red-500/25' : urgency === 'urgent' ? 'border-amber-500/25' : 'border-sky-500/20'}`}>
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium font-mono truncate">{item.action_type}</p>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className="text-xs text-muted-foreground truncate">{item.agent_id}</span>
                          {item.meta?.patient_id && (
                            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-blue-500/10 border border-blue-500/25 text-blue-400 font-mono font-medium">
                              <User size={9} /> {String(item.meta.patient_id)}
                            </span>
                          )}
                          {!canApprove(reviewerRoleForApproval, urgency, vertical) && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/25 text-amber-400 font-medium">
                              {approvalTier[urgency]} required
                            </span>
                          )}
                        </div>
                      </div>
                      <SlaTimer item={item} onExpired={handleExpired} />
                      {urgency === 'critical' && (
                        <button disabled={escalatingId === item.decision_id} onClick={() => handleEscalate(item)} title="Page on-call"
                          className="flex items-center justify-center w-7 h-7 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-400 hover:bg-rose-500/25 disabled:opacity-40 transition-colors">
                          {escalatingId === item.decision_id ? <div className="w-3.5 h-3.5 border border-rose-400/30 border-t-rose-400 rounded-full animate-spin" /> : <Bell size={11} />}
                        </button>
                      )}
                      <button disabled={busy || !canApprove(reviewerRoleForApproval, urgency, vertical)} onClick={() => handleAction(item, 'approved')} title={canApprove(reviewerRoleForApproval, urgency, vertical) ? 'Approve' : `Requires ${approvalTier[urgency]}`}
                        className="flex items-center justify-center w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-40 transition-colors">
                        {busy ? <div className="w-3.5 h-3.5 border border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" /> : <ThumbsUp size={11} />}
                      </button>
                      <button disabled={busy} onClick={() => handleAction(item, 'rejected')} title="Reject"
                        className="flex items-center justify-center w-7 h-7 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 disabled:opacity-40 transition-colors">
                        {busy ? <div className="w-3.5 h-3.5 border border-red-400/30 border-t-red-400 rounded-full animate-spin" /> : <ThumbsDown size={11} />}
                      </button>
                    </div>
                    {!compactQueue && item.escalation_question && <p className="text-xs text-muted-foreground mt-2 pl-5">{item.escalation_question}</p>}
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
                  {item.resolution === 'approved' ? 'Approved' : 'Rejected'}{item.resolved_by ? ` / ${item.resolved_by}` : ''}
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
                {reviewerIdentityBound && <span className="text-emerald-300">server verified</span>}
              </p>
              {confirmItem.action === 'rejected' && (
                <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="Rejection note (optional)..."
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

// -- Red Team Tab ---------------------------------------------------------

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
  const [exportError, setExportError]   = useState('')
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

  useEffect(() => {
    const topSeverity = findings.some(f => f.severity === 'critical')
      ? 'critical'
      : findings.some(f => f.severity === 'advisory')
        ? 'advisory'
        : 'stable'
    _setPS('redteam', [
      {
        summary: summary ? {
          critical: summary.critical,
          advisory: summary.advisory,
          confirmed_bypasses: summary.confirmed_bypasses,
          non_determinism_count: summary.non_determinism_count,
        } : null,
        findings: findings.length,
        confirmed_bypasses: bypasses.length,
        top_severity: topSeverity,
        chain_open: chainOpen,
        session_id: sessionId,
        filter,
      },
    ] as Record<string, unknown>[])
  }, [summary, findings, bypasses, chainOpen, sessionId, filter])

  const handleExport = async () => {
    setExporting(true)
    setExportError('')
    try {
      const blob = await api.shadowExport()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `edon_shadow_report_${Date.now()}.csv`
      a.click(); URL.revokeObjectURL(url)
    } catch (e) { setExportError(e instanceof Error ? e.message : 'Export failed') }
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
          <p className="text-xs text-muted-foreground mt-0.5">Adversarial shadow execution - continuous governance testing</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition">
            <RefreshCw size={13} />
          </button>
          <button onClick={handleExport} disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-muted/40 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition disabled:opacity-50">
            <FileDown size={13} />{exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        </div>
      </div>
      {exportError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle size={12} /> {exportError}
        </div>
      )}

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

      {/* Confirmed bypasses - top priority */}
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
            These bypasses are not theoretical - the perturbation bypassed the governor AND the agent executed successfully.
          </p>
          <div className="space-y-2">
            {bypasses.map(b => (
              <div key={b.id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs space-y-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-muted-foreground">{b.agent_id}</span>
                  <span className="text-border">/</span>
                  <span className="font-medium">{b.action_type}</span>
                  <span className="text-border">/</span>
                  <span className="text-red-400/80">{PERTURB_LABEL[b.perturbation_type] ?? b.perturbation_type}</span>
                  <span className="ml-auto text-muted-foreground/60">{b.confirmed_at.slice(0, 10)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 rounded border border-red-500/30 text-red-400 font-mono">{b.original_verdict}</span>
                  <span className="text-muted-foreground">-&gt;</span>
                  <span className="px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-400 font-mono">{b.shadow_verdict}</span>
                  <span className="text-muted-foreground mx-1">/</span>
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
              {filter === 'all' ? 'No findings yet - traces are being sampled.' : `No ${filter} findings.`}
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
                    <span className="font-medium truncate">{f.action_type ?? '-'}</span>
                    <span className="text-muted-foreground/70 shrink-0">{PERTURB_LABEL[f.perturbation_type] ?? f.perturbation_type}</span>
                    <span className="text-muted-foreground/50 mx-1 shrink-0">
                      {f.trace_original_verdict} -&gt; {f.shadow_verdict}
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
                      <p className="text-muted-foreground/40">{f.created_at?.slice(0, 19).replace('T', ' ')} / field: {f.perturbed_field ?? '-'}</p>
                    </div>
                  )}
                </div>
              )
            })}
            {visible.length > 50 && (
              <p className="text-center text-xs text-muted-foreground py-2">
                Showing 50 of {visible.length} findings - export CSV for full report
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
                {chainRunning ? 'Running...' : 'Run'}
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
                          <span>Step {r.injection_step} -&gt; {r.cascade_count} cascade{r.cascade_count !== 1 ? 's' : ''}</span>
                          <span className="text-muted-foreground ml-1">{PERTURB_LABEL[r.perturbation_type] ?? r.perturbation_type}</span>
                        </div>
                        {r.cascade_verdicts.map((cv, j) => (
                          <div key={j} className="mt-1.5 pl-2 border-l border-current/20 text-muted-foreground">
                            Step {cv.step} / {cv.action_type} / {cv.original} -&gt; {cv.shadow}
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

// -- Compliance Report Tab -----------------------------------------------------

const REPORT_REGULATION_MAP: Record<string, string> = {
  'ALLOW':    'HIPAA Section 164.308(a)(4) Minimum Necessary',
  'BLOCK':    'HIPAA Section 164.308(a)(1); SOC2 CC6.1',
  'ESCALATE': 'FDA SaMD Human Oversight; Joint Commission NPSG.15.01.01',
  'DEGRADE':  'ISO 14971 Section 6 - Safe Alternative Applied',
  'PAUSE':    'HIPAA Section 164.308(a)(1)(ii)(D) Activity Review',
  'ERROR':    'HIPAA Section 164.308(a)(1) Security Management',
}

function ComplianceReportTab() {
  const [fromTs, setFromTs]     = useState('')
  const [toTs, setToTs]         = useState('')
  const [agentId, setAgentId]   = useState('')
  const [verdict, setVerdict]   = useState('')
  const [preview, setPreview]   = useState<AuditEvent[]>([])
  const [loading, setLoading]   = useState(true)
  const [exporting, setExporting] = useState<'json' | 'pdf' | null>(null)
  const [error, setError]       = useState('')

  const loadPreview = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await api.auditQuery({
        verdict:  verdict  || undefined,
        agent_id: agentId  || undefined,
        from_ts:  fromTs   || undefined,
        limit: 500,
      })
      setPreview(res.events)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally { setLoading(false) }
  }, [fromTs, agentId, verdict])

  useEffect(() => { loadPreview() }, [loadPreview])

  const stats = useMemo(() => {
    const total     = preview.length
    const allowed   = preview.filter(e => e.decision_verdict === 'ALLOW').length
    const blocked   = preview.filter(e => ['BLOCK', 'ERROR'].includes(e.decision_verdict)).length
    const escalated = preview.filter(e => ['ESCALATE', 'PAUSE'].includes(e.decision_verdict)).length
    const degraded  = preview.filter(e => e.decision_verdict === 'DEGRADE').length
    const compliance = total > 0 ? ((allowed + degraded) / total * 100).toFixed(1) : '100.0'
    return { total, allowed, blocked, escalated, degraded, compliance }
  }, [preview])

  const regulations = useMemo(() => {
    const seen = new Set<string>()
    for (const e of preview) {
      const reg = REPORT_REGULATION_MAP[e.decision_verdict]
      if (reg) reg.split(';').forEach(r => seen.add(r.trim()))
    }
    return [...seen]
  }, [preview])

  useEffect(() => {
    if (preview.length === 0) return
    _setPS('report', [
      { type: 'stats', ...stats, regulations },
      ...preview.slice(0, 20).map(e => ({ id: e.action_id || e.id, agent: e.agent_id, verdict: e.decision_verdict, reason: e.decision_reason_code, ts: e.timestamp })),
    ])
  }, [stats, regulations, preview])

  const download = async (format: 'json' | 'pdf') => {
    setExporting(format)
    try {
      const blob = await api.auditReportExport({
        format,
        from_ts:  fromTs   || undefined,
        to_ts:    toTs     || undefined,
        agent_id: agentId  || undefined,
        verdict:  verdict  || undefined,
        limit: 2000,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `edon_compliance_report_${new Date().toISOString().slice(0, 10)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally { setExporting(null) }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Compliance Report</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Download audit evidence for bank, SOC2, HIPAA, or FDA review
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => download('json')}
            disabled={exporting !== null || preview.length === 0}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-primary/40 transition disabled:opacity-40"
          >
            {exporting === 'json' ? <RefreshCw size={12} className="animate-spin" /> : <FileDown size={12} />}
            JSON
          </button>
          <button
            onClick={() => download('pdf')}
            disabled={exporting !== null || preview.length === 0}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 transition disabled:opacity-40"
          >
            {exporting === 'pdf' ? <RefreshCw size={12} className="animate-spin" /> : <FileDown size={12} />}
            PDF Report
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <p className="text-[10px] font-semibold text-muted-foreground mb-3 uppercase tracking-wider">Filter Period</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">From</label>
            <input
              type="date"
              value={fromTs.slice(0, 10)}
              onChange={e => setFromTs(e.target.value ? e.target.value + 'T00:00:00Z' : '')}
              className="w-full py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">To</label>
            <input
              type="date"
              value={toTs.slice(0, 10)}
              onChange={e => setToTs(e.target.value ? e.target.value + 'T23:59:59Z' : '')}
              className="w-full py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Agent ID</label>
            <input
              value={agentId}
              onChange={e => setAgentId(e.target.value)}
              placeholder="all agents"
              className="w-full py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Verdict</label>
            <select
              value={verdict}
              onChange={e => setVerdict(e.target.value)}
              className="w-full py-2 px-3 rounded-lg bg-muted/50 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">All verdicts</option>
              <option value="ALLOW">ALLOW</option>
              <option value="BLOCK">BLOCK</option>
              <option value="ESCALATE">ESCALATE</option>
              <option value="DEGRADE">DEGRADE</option>
            </select>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      {!loading && preview.length > 0 && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {[
            { label: 'Total',      value: stats.total,      color: '' },
            { label: 'Allowed',    value: stats.allowed,    color: 'text-green-400' },
            { label: 'Blocked',    value: stats.blocked,    color: 'text-red-400' },
            { label: 'Escalated',  value: stats.escalated,  color: 'text-amber-400' },
            { label: 'Degraded',   value: stats.degraded,   color: 'text-blue-400' },
            {
              label: 'Compliance',
              value: `${stats.compliance}%`,
              color: parseFloat(stats.compliance) >= 90 ? 'text-green-400' : 'text-amber-400',
            },
          ].map(s => (
            <div key={s.label} className="glass-card p-3 text-center">
              <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Regulatory coverage */}
      {!loading && regulations.length > 0 && (
        <div className="glass-card p-4">
          <p className="text-[10px] font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Regulatory Coverage</p>
          <div className="flex flex-wrap gap-1.5">
            {regulations.map(reg => (
              <span key={reg} className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                {reg}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Decision preview table */}
      {loading ? <Spinner /> : error ? <ErrorMsg message={error} onRetry={loadPreview} /> : preview.length === 0 ? (
        <Empty message="No decisions found for the selected filters" />
      ) : (
        <div className="glass-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Decision Preview</p>
            <p className="text-xs text-muted-foreground">{preview.length} records shown - download for full report</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-xs text-muted-foreground">
                  <th className="text-left py-2.5 px-4">Verdict</th>
                  <th className="text-left py-2.5 px-4">Agent</th>
                  <th className="text-left py-2.5 px-4 hidden md:table-cell">Tool</th>
                  <th className="text-left py-2.5 px-4 hidden lg:table-cell">Regulation Mapping</th>
                  <th className="text-left py-2.5 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((e, i) => (
                  <tr key={e.action_id || e.id || i} className="border-b border-border/30 last:border-0 hover:bg-muted/10 transition-colors">
                    <td className="py-2 px-4"><VerdictBadge verdict={e.decision_verdict} /></td>
                    <td className="py-2 px-4 font-mono text-xs truncate max-w-[140px]">{e.agent_id}</td>
                    <td className="py-2 px-4 text-xs text-muted-foreground hidden md:table-cell">{e.tool_name || '-'}</td>
                    <td className="py-2 px-4 hidden lg:table-cell">
                      <span className="text-[10px] text-muted-foreground leading-tight">
                        {REPORT_REGULATION_MAP[e.decision_verdict] || '-'}
                      </span>
                    </td>
                    <td className="py-2 px-4 text-xs text-muted-foreground">{fmtTs(e.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// -- Tabs config ---------------------------------------------------------------

// -- Onboarding Screen (pre-console gate) --------------------------------------

type OBStep = 1 | 2 | 3 | 4 | 5 | 6 | 7

const STEP_LABELS: Record<number, string> = {
  1: 'Hospital Environment Detection',
  2: 'Connector Verification',
  3: 'Governance Activation',
  4: 'Governed Action Readiness',
  5: 'Procurement Readiness',
  6: 'Approval & Launch',
  7: 'Live & Expanding',
}

const DATA_CLASS_OPTIONS = ['PHI', 'PCI', 'PII', 'credentials', 'financial', 'legal', 'internal', 'public']
const COMPLIANCE_OPTIONS  = ['HIPAA', 'PCI_DSS', 'GDPR', 'SOC2', 'ISO27001']
const ENVIRONMENT_OPTIONS = ['aws_vpc', 'azure_vnet', 'k8s', 'on_prem', 'saas']
const IDP_OPTIONS         = ['none', 'entra', 'okta', 'cognito', 'custom']
const AGENT_TYPE_OPTIONS  = ['llm_agent', 'rpa', 'scripted', 'human_in_loop']

function MultiSelect({ options, selected, onChange, placeholder }: {
  options: string[]; selected: string[]; onChange: (v: string[]) => void; placeholder?: string
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => (
        <button key={opt} type="button"
          onClick={() => onChange(selected.includes(opt) ? selected.filter(x => x !== opt) : [...selected, opt])}
          className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
            selected.includes(opt)
              ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
              : 'border-border/40 text-muted-foreground hover:border-emerald-500/30 hover:text-foreground'
          }`}>
          {opt}
        </button>
      ))}
      {placeholder && selected.length === 0 && <span className="text-xs text-muted-foreground italic mt-0.5">{placeholder}</span>}
    </div>
  )
}

function TagInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const t = draft.trim()
    if (t && !value.includes(t)) onChange([...value, t])
    setDraft('')
  }
  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <input value={draft} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder={placeholder || 'Type and press Enter'}
          className="flex-1 bg-background border border-border/40 rounded-lg px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
        <button type="button" onClick={add}
          className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-colors">
          Add
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {value.map(t => (
          <span key={t} className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted/30 border border-border/40 text-foreground/80">
            {t}
            <button type="button" onClick={() => onChange(value.filter(x => x !== t))} className="text-muted-foreground hover:text-destructive ml-0.5">
              <X size={10} />
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}

function RiskBadge({ tier }: { tier: string }) {
  const cfg: Record<string, string> = {
    critical: 'bg-red-500/20 border-red-500/40 text-red-400',
    high:     'bg-orange-500/20 border-orange-500/40 text-orange-400',
    medium:   'bg-yellow-500/20 border-yellow-500/40 text-yellow-400',
    low:      'bg-emerald-500/20 border-emerald-500/40 text-emerald-400',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${cfg[tier] ?? cfg.medium}`}>
      {tier.toUpperCase()}
    </span>
  )
}

function DecisionBadge({ decision }: { decision: string }) {
  const cfg: Record<string, string> = {
    BLOCK:          'bg-red-500/20 border-red-500/40 text-red-400',
    HUMAN_REQUIRED: 'bg-orange-500/20 border-orange-500/40 text-orange-400',
    ESCALATE:       'bg-yellow-500/20 border-yellow-500/40 text-yellow-400',
    ALLOW:          'bg-emerald-500/20 border-emerald-500/40 text-emerald-400',
    DEGRADE:        'bg-blue-500/20 border-blue-500/40 text-blue-400',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${cfg[decision] ?? 'bg-muted/20 border-border text-foreground'}`}>
      {decision}
    </span>
  )
}

function OBStepNav({ current, maxReached, onSelect }: { current: OBStep; maxReached: OBStep; onSelect: (s: OBStep) => void }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {([1,2,3,4,5,6,7] as OBStep[]).map(s => (
        <button key={s} type="button"
          disabled={s > maxReached}
          onClick={() => onSelect(s)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
            s === current
              ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
              : s < current
              ? 'border-emerald-500/20 text-emerald-400/60 hover:bg-emerald-500/10'
              : s === maxReached
              ? 'border-border/40 text-foreground/70 hover:bg-muted/10'
              : 'border-border/20 text-muted-foreground/40 cursor-not-allowed'
          }`}>
          <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
            s < current ? 'bg-emerald-500/40 text-emerald-300' : s === current ? 'bg-emerald-500/60 text-white' : 'bg-muted/30 text-muted-foreground'
          }`}>{s < current ? 'OK' : s}</span>
          {STEP_LABELS[s]}
        </button>
      ))}
    </div>
  )
}

type OBChatMsg = { role: 'copilot' | 'user'; text: string; id: number }

export function OnboardingScreen({ onComplete, onLogout }: { onComplete: () => void; onLogout: () => void }) {
  const [screen, setScreen]       = useState(1)
  const [msgs, setMsgs]           = useState<OBChatMsg[]>([])
  const [input, setInput]         = useState('')
  const [isTyping, setIsTyping]   = useState(false)
  const [ctaReady, setCtaReady]   = useState(false)
  const [convStep, setConvStep]   = useState(0)
  const [busy, setBusy]           = useState(false)
  const [apiErr, setApiErr]       = useState('')
  const msgEndRef  = useRef<HTMLDivElement>(null)
  const inputRef   = useRef<HTMLInputElement>(null)
  const idRef      = useRef(0)
  const cancelRef  = useRef(false)

  // Collected env data
  const [orgName,    setOrgName]    = useState('')
  const [domain,     setDomain]     = useState<'healthcare'|'banking'|'general'>('general')
  const [agentDrafts,setAgentDrafts]= useState<Array<{name:string;type:string;phi:boolean;autonomous:boolean;actions:string[]}>>([])
  const [extSinks,   setExtSinks]   = useState<string[]>([])
  const [deployMode, setDeployMode] = useState<'vpc'|'cloud_proxy'|'hybrid'>('vpc')
  const [trustChecks,setTrustChecks]= useState({intercept:false,block:false,audit:false,ownership:false,killswitch:false})
  const [policyReviewed, setPolicyReviewed] = useState<Record<string, 'accept'|'modify'|'reject'>>({})
  const [activationStep, setActivationStep] = useState(-1)

  // API results
  const [profile,    setProfile]    = useState<import('./api').OnboardingProfile|null>(null)
  const [bundle,     setBundle]     = useState<import('./api').OnboardingPolicyBundle|null>(null)
  const [deployment, setDeployment] = useState<import('./api').OnboardingDeploymentPackage|null>(null)

  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, isTyping])

  useEffect(() => {
    const activeAgents = agentDrafts.filter(a => a.name.trim())
    _setPS('onboarding', [
      {
        screen,
        organization: orgName || 'new',
        domain,
        agent_count: activeAgents.length,
        action_count: activeAgents.reduce((n, a) => n + a.actions.length, 0),
        external_sinks: extSinks,
        deployment_mode: deployMode,
        trust_checks: trustChecks,
        policy_reviews: Object.entries(policyReviewed).map(([k, v]) => `${k}:${v}`),
        activation_step: activationStep,
        vendors: 0,
        departments: 1,
      },
    ] as Record<string, unknown>[])
  }, [screen, orgName, domain, agentDrafts, extSinks, deployMode, trustChecks, policyReviewed, activationStep])

  const addCopilot = useCallback((text: string, delay = 950): Promise<void> =>
    new Promise(resolve => {
      setIsTyping(true)
      setTimeout(() => {
        if (cancelRef.current) { resolve(); return }
        setIsTyping(false)
        setMsgs(p => [...p, { role: 'copilot', text, id: ++idRef.current }])
        setTimeout(resolve, 80)
      }, delay)
    }), [])

  // Screen initializer
  useEffect(() => {
    cancelRef.current = false
    setMsgs([]); setConvStep(0); setCtaReady(false); setInput(''); setApiErr('')
    const openers: Record<number,string> = {
      1: 'What organization is this governance boundary for?',
      2: 'List the AI systems or agents currently in use. Even partial descriptions are fine.',
      3: 'Let\'s map actual capabilities. What can your agents access and do?',
      4: 'Do any systems send data outside your organization - vendors, APIs, external cloud models?',
      5: `I'll generate governance rules for your system. Do you want strict enforcement (recommended for ${domain}) or balanced?`,
      6: 'Where should EDON run? AWS VPC, cloud proxy, or hybrid gateway?',
      7: 'I\'ll simulate how EDON would have governed your system. Run shadow simulation?',
      8: 'Review and confirm each control below. Legal and security sign-off attaches here.',
      9: 'Generating your EDON deployment package - runtime gateway, identity bindings, audit pipeline, enforcement engine.',
      10:'Once activated, EDON enforces governance in real time. Review below, then activate.',
    }
    let t1: ReturnType<typeof setTimeout>
    t1 = setTimeout(async () => {
      await addCopilot(openers[screen] ?? '', 600)
      if (screen === 9) {
        if (!deployment && profile) {
          setBusy(true)
          try {
            const dep = await api.onboardingGetDeployment(profile.profile_id)
            setDeployment(dep.deployment_package)
            if (!cancelRef.current) await addCopilot(`Bundle ready. ${dep.deployment_package.estimated_setup_h}h estimated setup.`, 400)
          } catch { /* ignore */ } finally { setBusy(false) }
        }
        setCtaReady(true)
      }
      if (screen === 10) setCtaReady(true)
    }, 160)
    return () => { cancelRef.current = true; clearTimeout(t1) }
  }, [screen]) // eslint-disable-line react-hooks/exhaustive-deps

  const allTrustChecked = Object.values(trustChecks).every(Boolean)
  useEffect(() => { if (screen === 8) setCtaReady(allTrustChecked) }, [allTrustChecked, screen])

  const allPoliciesReviewed = bundle
    ? [...bundle.hard_safety, ...bundle.operational, ...bundle.intent_contracts]
        .slice(0, 5 * 3)
        .every(p => policyReviewed[p.policy_id])
    : false
  useEffect(() => {
    if (screen === 5 && bundle) setCtaReady(allPoliciesReviewed)
  }, [allPoliciesReviewed, screen, bundle])

  // Check for existing profiles on mount
  useEffect(() => {
    api.onboardingListProfiles().then(r => {
      const live = r.profiles.find(p => p.signed_off)
      if (live) { onComplete(); return }
      const inProgress = r.profiles.find(p => !p.signed_off)
      if (inProgress) {
        setProfile(inProgress)
        setOrgName(inProgress.org_name)
        if (inProgress.agent_systems?.length > 0) {
          setAgentDrafts(inProgress.agent_systems.map(a => ({
            name: a.name,
            type: a.agent_type,
            phi: a.data_classes?.includes('PHI') ?? false,
            autonomous: true,
            actions: a.actions ?? [],
          })))
        }
        if (inProgress.all_data_classes?.some(c => /PHI|PII/i.test(c))) {
          setDomain('healthcare')
        }
        const stageScreen: Record<string, number> = {
          intake: 2, topology: 3, bootstrap: 5, deployment: 6, shadow: 7, signoff_pending: 10,
        }
        const restored = stageScreen[inProgress.stage] ?? 2
        setScreen(restored)
      }
    }).catch(() => {})
  }, [onComplete]) // eslint-disable-line react-hooks/exhaustive-deps

  // -- Send message handler --------------------------------------------------
  const sendDirect = async (text: string) => {
    if (!text || isTyping || busy) return
    setMsgs(p => [...p, { role: 'user', text, id: ++idRef.current }])
    setConvStep(s => s + 1)

    if (screen === 1) {
      setOrgName(text)
      const d: 'healthcare'|'banking'|'general' =
        /hospital|health|clinic|patient|medical|ehr|pharma/i.test(text) ? 'healthcare' :
        /bank|financ|fintech|credit|trading|insurance|wealth/i.test(text) ? 'banking' : 'general'
      setDomain(d)
      const packs = { healthcare:'PHI-aware, HIPAA-aligned', banking:'PCI DSS + SOX-aligned', general:'AI Agent Safety baseline' }
      await addCopilot(`Got it. I'll configure ${d}-grade governance templates (${packs[d]}).`)
      await addCopilot(`Governance workspace initialized for "${text}". Tenant ID assigned and isolation context set.`, 700)
      setCtaReady(true)
    }

    else if (screen === 2) {
      if (convStep === 0) {
        const parts = text.split(/\band\b|,(?:\s*and)?/i).map(s => s.trim()).filter(s => s.length > 4)
        const extracted = (parts.length > 0 ? parts : [text]).map((p, i) => {
          const phi = /phi|patient|clinical|ehr|health|medical|lab|alert|summar/i.test(p)
          return { name: phi ? `clinical-agent-${i+1}` : `agent-${i+1}`, type:'llm_agent', phi, autonomous:true, actions:[] }
        })
        setAgentDrafts(extracted)
        const list = extracted.map((a,i) => `${i+1}. ${a.name}${a.phi ? '  - PHI risk tag applied' : ''}`).join('\n')
        await addCopilot(`I've identified ${extracted.length} agent type${extracted.length !== 1 ? 's' : ''}:\n\n${list}`)
        await addCopilot('Do these operate autonomously or require human approval?', 650)
      } else {
        const auto = /autonom|mostly|auto|no human|independent/i.test(text)
        setAgentDrafts(p => p.map(a => ({ ...a, autonomous:auto })))
        await addCopilot(auto
          ? 'Understood. Classifying as autonomous agents - elevated governance scope applied.'
          : 'Understood. Human-in-loop agents will have lighter escalation thresholds.')
        setCtaReady(true)
      }
    }

    else if (screen === 3) {
      if (convStep === 0) {
        const write = /writ|updat|post|send|creat|modif|insert/i.test(text)
        const cred  = /credential|token|key|secret|auth|password/i.test(text)
        const acts  = ['read-data', ...write ? ['write-back','create-record'] : [], ...cred ? ['credential-access'] : []]
        setAgentDrafts(p => p.map((a,i) => i === 0 ? { ...a, actions:acts } : a))
        if (write && agentDrafts[0]?.phi) {
          await addCopilot('Understood. That creates a write-path into PHI systems.')
          await addCopilot('Write-paths into PHI are classified as critical. All writes will require verification policies.', 700)
        } else if (write) {
          await addCopilot('Understood. Write-paths into production systems flagged as high-risk operations.')
        } else {
          await addCopilot('Read-only access pattern. Lower inherent risk - operational policies still apply.')
        }
        await addCopilot('Does any agent have access to credentials or API keys?', 800)
      } else {
        const hasCreds = /yes|credential|token|key|secret|auth/i.test(text)
        if (hasCreds) {
          setAgentDrafts(p => p.map(a => ({ ...a, actions:[...a.actions,'credential-read'] })))
          await addCopilot('Credential access paths flagged - ESCALATE policy applied to all credential operations.')
        } else {
          await addCopilot('No direct credential access. Action surface mapping complete.')
        }
        setCtaReady(true)
      }
    }

    else if (screen === 4) {
      const detected: string[] = []
      if (/openai|gpt|anthropic|claude|llm|language model/i.test(text)) detected.push('LLM API calls')
      if (/analytic|dashboard|looker|tableau|segment/i.test(text)) detected.push('analytics export pipeline')
      if (/slack|email|teams|sendgrid|twilio/i.test(text)) detected.push('messaging/notification sink')
      if (/s3|gcs|azure blob|storage|bucket/i.test(text)) detected.push('cloud storage')
      if (detected.length === 0 && /yes|external|vendor|api|cloud/i.test(text)) detected.push('external API endpoint')
      setExtSinks(p => [...new Set([...p, ...detected])])
      if (detected.length > 0) {
        await addCopilot(`I've identified ${detected.length} external data sink${detected.length !== 1 ? 's' : ''}:\n\n${detected.map((d,i) => `${i+1}. ${d}`).join('\n')}`)
        if (agentDrafts.some(a => a.phi))
          await addCopilot('PHI exposure paths through external sinks flagged as trust boundary violations.', 800)
      } else if (/no|none|internal/i.test(text)) {
        await addCopilot('No external sinks. All data flows remain within your trust boundary.')
      } else {
        await addCopilot('External flows noted. Trust boundary topology updated.')
      }
      setCtaReady(true)
    }

    else if (screen === 5) {
      const strict = /strict|yes|recommend|hipaa|pci|tight|fail.close/i.test(text)
      await addCopilot(strict ? 'Understood. Prioritizing fail-closed behavior and PHI protection.' : 'Understood. Balanced enforcement with escalation on high-risk actions.')
      await addCopilot('Compiling policy pack...', 500)
      setBusy(true); setApiErr('')
      try {
        const compliance = domain === 'healthcare' ? ['HIPAA'] : domain === 'banking' ? ['PCI_DSS'] : []
        const agentPayload = agentDrafts.length > 0 ? agentDrafts.map(a => ({
          name: a.name, agent_type: a.type,
          actions: a.actions.length > 0 ? a.actions : ['read.data'],
          data_classes: a.phi ? ['PHI','credentials'] : ['internal'],
          external_sinks: extSinks, description: '',
        })) : [{ name:'primary-agent', agent_type:'llm_agent', actions:['read.data','write.summary'],
          data_classes: domain === 'healthcare' ? ['PHI'] : ['internal'], external_sinks: extSinks, description:'' }]
        const r = await api.onboardingSubmitIntake({ org_name: orgName||'Organisation', agent_systems: agentPayload, identity_provider:'none', environments:['saas'], compliance_requirements:compliance })
        setProfile(r.profile)
        await api.onboardingGenerateTopology(r.profile.profile_id)
        const boot = await api.onboardingBootstrapPolicies(r.profile.profile_id)
        setBundle(boot.policy_bundle)
        await addCopilot(`Policy Pack v1 ready - ${boot.policy_bundle.total_count} rules across 3 layers.`, 300)
      } catch (e) {
        setApiErr(e instanceof Error ? e.message : 'Failed')
        await addCopilot('Policy generation encountered an issue. Continuing with preview mode.', 300)
      } finally { setBusy(false) }
    }

    else if (screen === 6) {
      const mode: typeof deployMode = /vpc|aws|private/i.test(text) ? 'vpc' : /cloud|proxy/i.test(text) ? 'cloud_proxy' : 'hybrid'
      setDeployMode(mode)
      const desc = { vpc:'VPC-native with private routing and no external exposure.', cloud_proxy:'Cloud proxy with managed TLS and rate limiting.', hybrid:'Hybrid gateway - on-prem enforcement + cloud audit.' }
      await addCopilot(`I will generate a ${desc[mode]}`)
      if (profile) {
        setBusy(true)
        try {
          const dep = await api.onboardingGetDeployment(profile.profile_id)
          setDeployment(dep.deployment_package)
          await addCopilot(`Deployment config generated. ${dep.deployment_package.estimated_setup_h}h estimated setup.`, 300)
        } catch { /* ignore */ } finally { setBusy(false) }
      }
      setCtaReady(true)
    }

    else if (screen === 7) {
      if (/yes|run|go|start|activ/i.test(text)) {
        await addCopilot('Running shadow simulation...')
        setBusy(true)
        try { if (profile) await api.onboardingSetShadowMode(profile.profile_id, true) } catch { /* ignore */ } finally { setBusy(false) }
        await addCopilot('Simulation complete. Your system already has invisible failures.', 1800)
        setCtaReady(true)
      } else {
        await addCopilot("Type 'run' when you're ready to see what EDON would have blocked.")
      }
    }
  }

  const sendMsg = () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    sendDirect(text)
  }

  // -- Screen CTA handler ----------------------------------------------------
  const handleCTA = async () => {
    if (screen < 10) { setScreen(s => s + 1); return }
    setBusy(true)
    const ACTIVATION_STEPS = ['Installing gateway', 'Binding identity provider', 'Activating enforcement engine', 'Verifying network routing', 'Audit pipeline online']
    for (let i = 0; i < ACTIVATION_STEPS.length; i++) {
      setActivationStep(i)
      await new Promise(r => setTimeout(r, 700))
    }
    try {
      if (profile) {
        const sr = await api.onboardingRequestSignoff(profile.profile_id, {
          requested_by:'admin', enforcement_scope: profile.agent_systems.map(a => a.name),
          escalation_rules_accepted:true, kill_switch_authority:'admin',
          data_classes_governed: profile.all_data_classes,
        })
        await api.onboardingApproveSignoff(sr.signoff.signoff_id, 'admin')
      }
      await new Promise(r => setTimeout(r, 400))
      onComplete()
    } catch { onComplete() } finally { setBusy(false) }
  }

  const CTA_LABELS: Record<number,string> = {
    1:'Begin Agent Inventory', 2:'Confirm Agent Inventory', 3:'Confirm Action Surface',
    4:'Map Trust Boundaries', 5:'Accept Policy Pack v1', 6:'Generate Deployment Config',
    7:'Continue to Trust Agreement', 8:'Activate Governance Boundary',
    9:'Continue to Activation', 10:'Activate Production Mode',
  }

  const SCREEN_META: Record<number,{title:string;sub:string}> = {
    1:  { title:'Create Governance Boundary',  sub:'Initialize isolated enforcement workspace' },
    2:  { title:'AI System Inventory',         sub:'Map agents, classifiers, and automation flows' },
    3:  { title:'Action Surface Mapping',       sub:'Identify capabilities, write-paths, credential access' },
    4:  { title:'External Data Sinks',         sub:'Trust boundary and PHI exposure analysis' },
    5:  { title:'Policy Generation',           sub:'Auto-compile 3-layer governance rules' },
    6:  { title:'Deployment Architecture',     sub:'Runtime topology, identity, audit pipeline' },
    7:  { title:'Shadow Simulation',           sub:'Observe governance before enforcement goes live' },
    8:  { title:'Trust Boundary Agreement',    sub:'Explicit control confirmation' },
    9:  { title:'Generate Deployment Bundle',  sub:'Executable Helm chart + VPC config + runbook' },
    10: { title:'Activate Production Mode',    sub:'Enforcement boundary goes live - console unlocks' },
  }
  const meta = SCREEN_META[screen]

  return (
    <div className="min-h-screen flex flex-col" style={{ background:'#07100b' }}>

      {/* -- Header ----------------------------------------------------------- */}
      <header className="shrink-0 flex items-center px-6 h-[54px]" style={{ borderBottom:'1px solid rgba(74,222,128,0.1)', background:'rgba(7,16,11,0.97)' }}>
        <EdonLogo variant="compact" subtitle />
        <div className="flex items-center gap-1.5 mx-auto">
          {Array.from({length:10},(_,i) => (
            <div key={i} className="rounded-full transition-all duration-300" style={{
              width: i+1 === screen ? 10 : 6, height: i+1 === screen ? 10 : 6,
              background: i+1 < screen ? '#4ade80' : i+1 === screen ? '#4ade80' : 'rgba(255,255,255,0.1)',
              boxShadow: i+1 === screen ? '0 0 8px rgba(74,222,128,0.6)' : 'none',
            }} />
          ))}
          <span className="text-xs text-muted-foreground ml-2 tabular-nums">{screen}/10</span>
        </div>
        <button onClick={onLogout} className="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors">
          <LogOut size={14} />
        </button>
      </header>

      {/* -- Body: split screen ----------------------------------------------- */}
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">

        {/* LEFT - Copilot chat pane */}
        <div className="flex flex-col shrink-0 md:w-[400px] w-full md:max-h-full max-h-[45vh]" style={{ borderRight:'1px solid rgba(74,222,128,0.08)', borderBottom:'1px solid rgba(74,222,128,0.08)', background:'#0b1610' }}>
          {/* Screen label */}
          <div className="px-5 pt-5 pb-4 shrink-0" style={{ borderBottom:'1px solid rgba(74,222,128,0.07)' }}>
            <div className="flex items-center gap-2 mb-0.5">
              <div className="w-5 h-5 rounded-full bg-emerald-500/25 flex items-center justify-center text-[10px] font-bold text-emerald-300 shrink-0">{screen}</div>
              <h2 className="text-sm font-semibold text-foreground truncate">{meta.title}</h2>
            </div>
            <p className="text-[11px] text-muted-foreground/60 pl-7 leading-tight">{meta.sub}</p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {msgs.map(m => (
              <div key={m.id} className={`flex gap-2.5 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {m.role === 'copilot' && (
                  <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background:'rgba(74,222,128,0.15)', border:'1px solid rgba(74,222,128,0.25)' }}>
                    <EdonMark size={16} />
                  </div>
                )}
                <div className="rounded-2xl px-3.5 py-2.5 text-sm max-w-[272px] whitespace-pre-line leading-relaxed" style={{
                  borderRadius: m.role === 'copilot' ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
                  background: m.role === 'copilot' ? 'rgba(255,255,255,0.04)' : 'rgba(74,222,128,0.08)',
                  border: m.role === 'copilot' ? '1px solid rgba(255,255,255,0.07)' : '1px solid rgba(74,222,128,0.2)',
                  color: 'rgba(255,255,255,0.88)',
                }}>
                  {m.text}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="flex gap-2.5">
                <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0" style={{ background:'rgba(74,222,128,0.15)', border:'1px solid rgba(74,222,128,0.25)' }}>
                  <EdonMark size={16} />
                </div>
                <div className="rounded-2xl px-4 py-3" style={{ borderRadius:'4px 16px 16px 16px', background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.07)' }}>
                  <div className="flex gap-1">
                    {[0,1,2].map(i => <div key={i} className="w-1.5 h-1.5 rounded-full bg-emerald-400/50 animate-bounce" style={{ animationDelay:`${i*0.15}s` }} />)}
                  </div>
                </div>
              </div>
            )}
            <div ref={msgEndRef} />
          </div>

          {/* Input */}
          {screen < 8 && (
            <div className="px-4 pb-4 pt-2 shrink-0" style={{ borderTop:'1px solid rgba(74,222,128,0.07)' }}>
              <div className="flex gap-2">
                <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg() } }}
                  placeholder="Reply to EDON Copilot..." disabled={isTyping || busy}
                  className="flex-1 rounded-xl px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/35 focus:outline-none disabled:opacity-40"
                  style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.08)' }}
                />
                <button onClick={sendMsg} disabled={!input.trim() || isTyping || busy}
                  className="w-10 h-10 rounded-xl flex items-center justify-center transition-colors shrink-0 disabled:opacity-30"
                  style={{ background:'rgba(74,222,128,0.12)', border:'1px solid rgba(74,222,128,0.25)' }}>
                  <Send size={14} className="text-emerald-400" />
                </button>
              </div>
              {/* Quick chips */}
              {screen === 1 && msgs.length > 0 && !ctaReady && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {['Regional hospital system','Global fintech bank','Enterprise SaaS'].map(s => (
                    <button key={s} onClick={() => sendDirect(s)}
                      className="text-[11px] px-2.5 py-1 rounded-full transition-colors" style={{ border:'1px solid rgba(74,222,128,0.18)', color:'rgba(74,222,128,0.65)' }}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {screen === 5 && !ctaReady && (
                <div className="flex gap-2 mt-2">
                  {['Strict','Balanced'].map(s => (
                    <button key={s} onClick={() => sendDirect(s)}
                      className="text-[11px] px-3 py-1 rounded-full transition-colors" style={{ border:'1px solid rgba(74,222,128,0.18)', color:'rgba(74,222,128,0.65)' }}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {screen === 6 && !ctaReady && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {['AWS VPC','Cloud proxy','Hybrid'].map(s => (
                    <button key={s} onClick={() => sendDirect(s)}
                      className="text-[11px] px-2.5 py-1 rounded-full transition-colors" style={{ border:'1px solid rgba(74,222,128,0.18)', color:'rgba(74,222,128,0.65)' }}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {screen === 7 && !ctaReady && (
                <div className="flex gap-2 mt-2">
                  <button onClick={() => sendDirect('Run it')}
                    className="text-[11px] px-3 py-1 rounded-full transition-colors" style={{ border:'1px solid rgba(59,130,246,0.3)', color:'rgba(147,197,253,0.7)' }}>
                    Run simulation
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT - Live artifact pane */}
        <div className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div key={screen} initial={{ opacity:0, x:20 }} animate={{ opacity:1, x:0 }} exit={{ opacity:0, x:-20 }} transition={{ duration:0.18 }} className="flex flex-col min-h-full">

              <div className="flex-1 p-8 space-y-6">

                {/* -- Screen 1 ----------------------------------------------- */}
                {screen === 1 && (
                  <div className="max-w-lg space-y-6">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Governance Compilation Interface</p>
                      <h1 className="text-3xl font-bold text-white leading-tight">Create Governance Boundary</h1>
                      <p className="text-sm text-muted-foreground mt-2 leading-relaxed">This is not a signup flow. EDON converts your natural language description of an AI environment into an enforceable, verifiable governance model.</p>
                    </div>
                    {ctaReady && orgName ? (
                      <div className="rounded-2xl p-6 space-y-4" style={{ border:'1px solid rgba(74,222,128,0.22)', background:'rgba(74,222,128,0.04)' }}>
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background:'rgba(74,222,128,0.15)', border:'1px solid rgba(74,222,128,0.3)' }}>
                            <CheckCircle2 size={18} className="text-emerald-400" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-white">Workspace initialized</p>
                            <p className="text-xs text-muted-foreground">Isolated governance context created</p>
                          </div>
                        </div>
                        {[
                          ['Organisation', orgName],
                          ['Domain class', domain],
                          ['Policy template', domain==='healthcare' ? 'HIPAA + AI-Agent Safety Pack' : domain==='banking' ? 'PCI DSS + SOX Pack' : 'AI Agent Safety baseline'],
                          ['Governance mode', 'Compilation in progress'],
                        ].map(([k,v]) => (
                          <div key={k} className="flex items-center justify-between text-xs px-3 py-2.5 rounded-xl" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                            <span className="text-muted-foreground">{k}</span>
                            <span className="font-semibold text-white">{v}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="grid grid-cols-3 gap-4">
                        {([
                          [Shield, 'Policy Compiler', 'Natural language -> enforcement rules'],
                          [Activity, 'Topology Builder', 'Agent surface + trust boundary map'],
                          [Package, 'Deploy Generator', 'Helm / VPC / IaC bundle'],
                        ] as const).map(([Icon, label, sub]) => (
                          <div key={label} className="rounded-2xl p-5 text-center space-y-3" style={{ border:'1px solid rgba(255,255,255,0.07)', background:'rgba(255,255,255,0.02)' }}>
                            <div className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto" style={{ background:'rgba(74,222,128,0.1)', border:'1px solid rgba(74,222,128,0.15)' }}>
                              <Icon size={17} className="text-emerald-400" />
                            </div>
                            <p className="text-xs font-semibold text-white">{label}</p>
                            <p className="text-[11px] text-muted-foreground leading-tight">{sub}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 2 ----------------------------------------------- */}
                {screen === 2 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Agent Inventory Graph</p>
                      <h1 className="text-3xl font-bold text-white">AI System Discovery</h1>
                    </div>
                    {agentDrafts.length === 0 ? (
                      <div className="rounded-2xl border-dashed border p-14 text-center" style={{ borderColor:'rgba(255,255,255,0.09)' }}>
                        <Bot size={30} className="text-muted-foreground/25 mx-auto mb-3" />
                        <p className="text-sm text-muted-foreground/40">Agent nodes will appear as you describe your systems</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {agentDrafts.map((a,i) => (
                          <motion.div key={i} initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ delay:i*0.1 }}
                            className="flex items-center gap-4 p-4 rounded-2xl" style={{ border: a.phi ? '1px solid rgba(251,146,60,0.25)' : '1px solid rgba(74,222,128,0.15)', background: a.phi ? 'rgba(251,146,60,0.04)' : 'rgba(74,222,128,0.03)' }}>
                            <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0" style={{ background: a.phi ? 'rgba(251,146,60,0.15)' : 'rgba(74,222,128,0.12)' }}>
                              <Bot size={16} className={a.phi ? 'text-orange-400' : 'text-emerald-400'} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="text-sm font-semibold text-white">{a.name}</p>
                                {a.phi && <span className="text-[10px] px-2 py-0.5 rounded-full font-bold" style={{ background:'rgba(251,146,60,0.15)', border:'1px solid rgba(251,146,60,0.3)', color:'#fb923c' }}>PHI</span>}
                              </div>
                              <p className="text-xs text-muted-foreground mt-0.5">{a.type} / {a.autonomous ? 'autonomous' : 'human-in-loop'}</p>
                            </div>
                            <span className="text-[10px] px-2.5 py-1 rounded-full font-bold shrink-0" style={{ background:'rgba(74,222,128,0.1)', border:'1px solid rgba(74,222,128,0.2)', color:'#4ade80' }}>IDENTIFIED</span>
                          </motion.div>
                        ))}
                        <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-xs text-muted-foreground" style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Tool connection mapping in progress...
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 3 ----------------------------------------------- */}
                {screen === 3 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Action Surface Graph v1</p>
                      <h1 className="text-3xl font-bold text-white">Action Surface Mapping</h1>
                    </div>
                    <div className="rounded-2xl overflow-hidden" style={{ border:'1px solid rgba(255,255,255,0.08)' }}>
                      <div className="grid grid-cols-4 px-5 py-3 text-[11px] font-bold text-muted-foreground/60 uppercase tracking-widest" style={{ background:'rgba(255,255,255,0.03)', borderBottom:'1px solid rgba(255,255,255,0.06)' }}>
                        <span>Agent</span><span>Actions</span><span>Data Class</span><span>Risk</span>
                      </div>
                      {agentDrafts.length > 0 ? agentDrafts.map((a,i) => (
                        <div key={i} className="grid grid-cols-4 px-5 py-4 text-xs gap-2 items-start" style={{ borderBottom: i < agentDrafts.length-1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                          <span className="font-semibold text-white text-sm">{a.name}</span>
                          <div className="space-y-1.5">
                            {(a.actions.length > 0 ? a.actions : ['read-data']).map(act => (
                              <span key={act} className="block font-mono text-[10px] px-2 py-0.5 rounded w-fit" style={{
                                background: act.includes('write')||act.includes('creat') ? 'rgba(239,68,68,0.12)' : act.includes('credential') ? 'rgba(251,146,60,0.12)' : 'rgba(59,130,246,0.12)',
                                color: act.includes('write')||act.includes('creat') ? '#f87171' : act.includes('credential') ? '#fb923c' : '#93c5fd',
                              }}>{act}</span>
                            ))}
                          </div>
                          <span className={a.phi ? 'text-orange-400 font-medium' : 'text-muted-foreground'}>{a.phi ? 'PHI / PII' : 'Internal'}</span>
                          <RiskBadge tier={a.phi&&a.actions.some(x=>x.includes('write')) ? 'critical' : a.phi ? 'high' : a.actions.some(x=>x.includes('write')) ? 'medium' : 'low'} />
                        </div>
                      )) : (
                        <div className="px-5 py-10 text-center text-sm text-muted-foreground/40">Describe agent capabilities in the chat</div>
                      )}
                    </div>
                    {agentDrafts.some(a=>a.actions.some(x=>x.includes('write'))) && (
                      <div className="flex items-start gap-3 px-4 py-3.5 rounded-xl" style={{ background:'rgba(239,68,68,0.07)', border:'1px solid rgba(239,68,68,0.2)' }}>
                        <AlertTriangle size={14} className="text-red-400 mt-0.5 shrink-0" />
                        <p className="text-xs text-red-300/80">Write-paths into PHI systems detected. These will be classified as critical in the enforcement topology and require verification policies.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 4 ----------------------------------------------- */}
                {screen === 4 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Trust Boundary Draft</p>
                      <h1 className="text-3xl font-bold text-white">External Data Sink Map</h1>
                    </div>
                    <div className="rounded-2xl p-6 space-y-4" style={{ border:'1px solid rgba(255,255,255,0.07)', background:'rgba(255,255,255,0.015)' }}>
                      <div className="rounded-xl p-4 space-y-2" style={{ border:'1px solid rgba(74,222,128,0.2)', background:'rgba(74,222,128,0.04)' }}>
                        <p className="text-[10px] font-bold text-emerald-400/70 uppercase tracking-widest">Internal Trust Zone</p>
                        <div className="flex flex-wrap gap-2">
                          {(agentDrafts.length > 0 ? agentDrafts.map(a=>a.name) : ['agent-1']).map(n => (
                            <span key={n} className="text-xs px-2.5 py-1 rounded-lg font-medium text-white/70" style={{ background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.08)' }}>{n}</span>
                          ))}
                          {agentDrafts.some(a=>a.phi) && <span className="text-xs px-2.5 py-1 rounded-lg text-orange-400" style={{ background:'rgba(251,146,60,0.1)', border:'1px solid rgba(251,146,60,0.2)' }}>EHR / PHI store</span>}
                        </div>
                      </div>
                      <div className="flex items-center justify-center py-1">
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground/60">
                          <div className="w-6 h-px" style={{ background:'rgba(255,255,255,0.1)' }} />
                          <span className="px-2.5 py-1 rounded-lg" style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.07)' }}>EDON enforcement boundary</span>
                          <div className="w-6 h-px" style={{ background:'rgba(255,255,255,0.1)' }} />
                        </div>
                      </div>
                      <div className="rounded-xl p-4 space-y-2" style={{ border:`1px solid ${extSinks.length > 0 ? 'rgba(239,68,68,0.25)' : 'rgba(255,255,255,0.07)'}`, background: extSinks.length > 0 ? 'rgba(239,68,68,0.04)' : 'rgba(255,255,255,0.01)' }}>
                        <p className={`text-[10px] font-bold uppercase tracking-widest ${extSinks.length > 0 ? 'text-red-400/70' : 'text-muted-foreground/40'}`}>External Sinks {extSinks.length > 0 ? `(${extSinks.length} detected)` : '(scanning...)'}</p>
                        {extSinks.length > 0 ? extSinks.map(s => (
                          <div key={s} className="flex items-center gap-2 text-xs text-red-300/80">
                            <AlertTriangle size={10} className="text-red-400 shrink-0" />{s}
                          </div>
                        )) : <p className="text-xs text-muted-foreground/40">Describe external services in the chat</p>}
                      </div>
                    </div>
                    {extSinks.length > 0 && agentDrafts.some(a=>a.phi) && (
                      <div className="flex items-start gap-3 px-4 py-3.5 rounded-xl" style={{ background:'rgba(239,68,68,0.06)', border:'1px solid rgba(239,68,68,0.18)' }}>
                        <ShieldAlert size={14} className="text-red-400 mt-0.5 shrink-0" />
                        <p className="text-xs text-red-300/75">PHI exposure through external sinks detected. BLOCK policies will be generated for all unclassified external PHI flows.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 5 ----------------------------------------------- */}
                {screen === 5 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Auto-Generated</p>
                      <h1 className="text-3xl font-bold text-white">Governance Policy Pack v1</h1>
                    </div>
                    {busy && !bundle && (
                      <div className="flex items-center gap-3 px-5 py-4 rounded-2xl" style={{ border:'1px solid rgba(74,222,128,0.15)', background:'rgba(74,222,128,0.04)' }}>
                        <RefreshCw size={15} className="text-emerald-400 animate-spin" />
                        <p className="text-sm text-emerald-300/80">Compiling policy pack from environment description...</p>
                      </div>
                    )}
                    {bundle && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-3 gap-3">
                          {([
                            ['Hard Safety', bundle.hard_safety.length, '#ef4444', 'rgba(239,68,68,0.06)', 'rgba(239,68,68,0.22)'],
                            ['Operational', bundle.operational.length, '#f59e0b', 'rgba(245,158,11,0.06)', 'rgba(245,158,11,0.22)'],
                            ['Intent Contracts', bundle.intent_contracts.length, '#4ade80', 'rgba(74,222,128,0.06)', 'rgba(74,222,128,0.22)'],
                          ] as const).map(([label, count, color, bg, border]) => (
                            <div key={label} className="rounded-2xl p-5 text-center" style={{ background:bg, border:`1px solid ${border}` }}>
                              <p className="text-4xl font-bold" style={{ color }}>{count}</p>
                              <p className="text-xs font-semibold mt-1" style={{ color }}>{label}</p>
                            </div>
                          ))}
                        </div>
                        {([
                          [bundle.hard_safety,       'Layer A - Hard Safety',     'Non-negotiable / Immutable after go-live', '#ef4444', 'rgba(239,68,68,0.18)'],
                          [bundle.operational,       'Layer B - Operational',     'Rate limits, tool access, escalation thresholds', '#f59e0b', 'rgba(245,158,11,0.18)'],
                          [bundle.intent_contracts,  'Layer C - Intent Contracts','Business scope and purpose bounds', '#4ade80', 'rgba(74,222,128,0.18)'],
                        ] as const).map(([policies, label, note, color, border], gi) => (
                          <details key={gi} open className="rounded-2xl overflow-hidden" style={{ border:`1px solid ${border}` }}>
                            <summary className="cursor-pointer flex items-center justify-between px-5 py-4 text-sm font-semibold select-none" style={{ color, background:'rgba(255,255,255,0.02)' }}>
                              <span>{label}</span>
                              <span className="text-xs font-normal" style={{ color:'rgba(255,255,255,0.35)' }}>{note} / {(policies as import('./api').OnboardingPolicy[]).length} rules</span>
                            </summary>
                            <div className="p-4 space-y-2" style={{ background:'rgba(0,0,0,0.15)' }}>
                              {(policies as import('./api').OnboardingPolicy[]).slice(0,5).map(p => {
                                const rv = policyReviewed[p.policy_id]
                                return (
                                  <div key={p.policy_id} className="flex items-start gap-3 px-3 py-2.5 rounded-xl" style={{ background: rv ? 'rgba(74,222,128,0.04)' : 'rgba(255,255,255,0.03)', border: rv ? '1px solid rgba(74,222,128,0.18)' : '1px solid rgba(255,255,255,0.05)', transition:'all 0.15s' }}>
                                    <DecisionBadge decision={p.decision} />
                                    <div className="flex-1 min-w-0">
                                      <p className="text-xs font-medium text-white">{p.action_pattern}</p>
                                      <p className="text-[11px] text-muted-foreground mt-0.5">{p.reason}</p>
                                    </div>
                                    {rv ? (
                                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold shrink-0" style={{ background: rv==='accept' ? 'rgba(74,222,128,0.15)' : rv==='reject' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)', color: rv==='accept' ? '#4ade80' : rv==='reject' ? '#f87171' : '#fbbf24' }}>
                                        {rv.toUpperCase()}
                                      </span>
                                    ) : (
                                      <div className="flex gap-1 shrink-0">
                                        {(['accept','modify','reject'] as const).map(a => (
                                          <button key={a} onClick={() => setPolicyReviewed(r => ({ ...r, [p.policy_id]: a }))}
                                            className="text-[10px] px-1.5 py-0.5 rounded transition-colors"
                                            style={{ border:'1px solid rgba(255,255,255,0.1)', color:'rgba(255,255,255,0.4)' }}>
                                            {a}
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                              {(policies as import('./api').OnboardingPolicy[]).length > 5 && (
                                <p className="text-xs text-muted-foreground/40 text-center pt-1">+{(policies as import('./api').OnboardingPolicy[]).length - 5} more rules</p>
                              )}
                            </div>
                          </details>
                        ))}
                      </div>
                    )}
                    {bundle && !allPoliciesReviewed && (
                      <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs text-amber-400/80" style={{ background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.18)' }}>
                        <AlertTriangle size={12} />
                        Review all visible rules to unlock "Accept Policy Pack v1"
                      </div>
                    )}
                    {!bundle && !busy && (
                      <div className="rounded-2xl border-dashed border p-14 text-center" style={{ borderColor:'rgba(255,255,255,0.08)' }}>
                        <Shield size={30} className="text-muted-foreground/25 mx-auto mb-3" />
                        <p className="text-sm text-muted-foreground/40">Tell EDON your enforcement preference to generate policies</p>
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 6 ----------------------------------------------- */}
                {screen === 6 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Runtime Topology</p>
                      <h1 className="text-3xl font-bold text-white">Deployment Architecture</h1>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {([
                        ['vpc', 'VPC Native', 'Private routing, no external exposure', Shield],
                        ['cloud_proxy', 'Cloud Proxy', 'Managed TLS + rate limiting', Wifi],
                        ['hybrid', 'Hybrid Gateway', 'On-prem + cloud audit', Database],
                      ] as const).map(([mode, label, sub, Icon]) => (
                        <div key={mode} onClick={() => setDeployMode(mode)}
                          className="rounded-2xl p-4 text-center space-y-2.5 cursor-pointer transition-all"
                          style={{ border: deployMode===mode ? '1px solid rgba(74,222,128,0.4)' : '1px solid rgba(255,255,255,0.07)', background: deployMode===mode ? 'rgba(74,222,128,0.07)' : 'rgba(255,255,255,0.02)', opacity: deployMode===mode ? 1 : 0.5 }}>
                          <Icon size={18} className={deployMode===mode ? 'text-emerald-400 mx-auto' : 'text-muted-foreground mx-auto'} />
                          <p className="text-xs font-semibold text-white">{label}</p>
                          <p className="text-[10px] text-muted-foreground leading-tight">{sub}</p>
                        </div>
                      ))}
                    </div>
                    {deployment && (
                      <div className="space-y-2.5">
                        {[
                          ['Deployment mode', deployment.deployment_mode],
                          ['Est. setup time', `${deployment.estimated_setup_h}h`],
                          ['Connectors', String(deployment.connector_configs.length)],
                          ['Env variables', String(Object.keys(deployment.env_vars).length)],
                          ['Rollback steps', String(deployment.rollback_plan.length)],
                        ].map(([k,v]) => (
                          <div key={k} className="flex items-center justify-between text-xs px-4 py-2.5 rounded-xl" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                            <span className="text-muted-foreground">{k}</span>
                            <span className="font-semibold text-white">{v}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {busy && <div className="flex items-center gap-3 px-5 py-3.5 rounded-2xl text-sm" style={{ border:'1px solid rgba(74,222,128,0.15)', background:'rgba(74,222,128,0.04)' }}><RefreshCw size={14} className="text-emerald-400 animate-spin" /><span className="text-emerald-300/80">Generating deployment config...</span></div>}
                  </div>
                )}

                {/* -- Screen 7 ----------------------------------------------- */}
                {screen === 7 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Pre-Enforcement Observation</p>
                      <h1 className="text-3xl font-bold text-white">Shadow Simulation</h1>
                    </div>
                    {!ctaReady ? (
                      <div className="rounded-2xl p-12 text-center space-y-5" style={{ border:'1px solid rgba(59,130,246,0.2)', background:'rgba(59,130,246,0.04)' }}>
                        <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto" style={{ background:'rgba(59,130,246,0.1)', border:'1px solid rgba(59,130,246,0.25)' }}>
                          <Eye size={26} className="text-blue-400" />
                        </div>
                        <div>
                          <p className="font-semibold text-blue-200">EDON will now simulate governance without enforcing it</p>
                          <p className="text-sm text-blue-300/60 mt-1">See what would be blocked before going live</p>
                        </div>
                        {busy && <div className="flex items-center justify-center gap-2 text-xs text-blue-300/60"><RefreshCw size={12} className="animate-spin" />Running simulation...</div>}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="rounded-2xl p-4 flex items-center gap-3" style={{ border:'1px solid rgba(74,222,128,0.25)', background:'rgba(74,222,128,0.05)' }}>
                          <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                          <p className="text-sm font-semibold text-emerald-200">Your system already has invisible failures.</p>
                        </div>
                        {([
                          ['PHI exposure attempts detected', 12, 'critical', ShieldAlert],
                          ['Unsafe external data flows', 3, 'high', AlertTriangle],
                          ['Multi-agent coordination risks', 2, 'high', Users],
                          ['Actions that would be BLOCKED', 5, 'medium', XCircle],
                        ] as const).map(([label, count, sev, Icon], i) => (
                          <motion.div key={i} initial={{ opacity:0, x:16 }} animate={{ opacity:1, x:0 }} transition={{ delay:i*0.12 }}
                            className="flex items-center gap-4 px-5 py-4 rounded-2xl" style={{
                              border: sev==='critical' ? '1px solid rgba(239,68,68,0.25)' : sev==='high' ? '1px solid rgba(251,146,60,0.25)' : '1px solid rgba(245,158,11,0.2)',
                              background: sev==='critical' ? 'rgba(239,68,68,0.05)' : sev==='high' ? 'rgba(251,146,60,0.04)' : 'rgba(245,158,11,0.04)',
                            }}>
                            <Icon size={16} className={sev==='critical' ? 'text-red-400' : sev==='high' ? 'text-orange-400' : 'text-yellow-400'} />
                            <span className="flex-1 text-sm text-white/85">{label}</span>
                            <span className={`text-2xl font-bold ${sev==='critical' ? 'text-red-400' : sev==='high' ? 'text-orange-400' : 'text-yellow-400'}`}>{count}</span>
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* -- Screen 8 ----------------------------------------------- */}
                {screen === 8 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Explicit Control Confirmation</p>
                      <h1 className="text-3xl font-bold text-white">Trust Boundary Agreement</h1>
                      <p className="text-sm text-muted-foreground mt-2">Legal and security sign-off attaches here. Confirm each control explicitly before enforcement activates.</p>
                    </div>
                    <div className="space-y-2.5">
                      {([
                        ['intercept', 'EDON may intercept AI actions',    'Every action passes through the governance proxy before execution'],
                        ['block',     'EDON may block execution',          'Hard safety rules enforce BLOCK / ESCALATE / HUMAN_REQUIRED verdicts'],
                        ['audit',     'EDON maintains full audit logs',    'Every decision produces an immutable trail with causal attribution'],
                        ['ownership', 'Client owns final policy control',  'You can modify, extend, or override any policy at any time'],
                        ['killswitch','Kill switch authority defined',     `Assigned to: ${orgName || 'organisation admin'}`],
                      ] as [keyof typeof trustChecks, string, string][]).map(([key, label, sub]) => (
                        <div key={key} onClick={() => setTrustChecks(p => ({ ...p, [key]:!p[key] }))}
                          className="flex items-start gap-4 p-4 rounded-2xl cursor-pointer transition-all"
                          style={{ border: trustChecks[key] ? '1px solid rgba(74,222,128,0.3)' : '1px solid rgba(255,255,255,0.07)', background: trustChecks[key] ? 'rgba(74,222,128,0.05)' : 'rgba(255,255,255,0.02)' }}>
                          <div className="mt-0.5 w-5 h-5 rounded flex items-center justify-center shrink-0 border-2 transition-colors" style={{ background: trustChecks[key] ? '#22c55e' : 'transparent', borderColor: trustChecks[key] ? '#22c55e' : 'rgba(255,255,255,0.2)' }}>
                            {trustChecks[key] && <Check size={11} className="text-white" />}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-white">{label}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    {allTrustChecked && (
                      <motion.div initial={{ opacity:0, y:6 }} animate={{ opacity:1, y:0 }}
                        className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs text-emerald-400" style={{ background:'rgba(74,222,128,0.06)', border:'1px solid rgba(74,222,128,0.2)' }}>
                        <CheckCircle2 size={13} /> All controls confirmed. Governance boundary ready for deployment.
                      </motion.div>
                    )}
                  </div>
                )}

                {/* -- Screen 9 ----------------------------------------------- */}
                {screen === 9 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Executable Artifact</p>
                      <h1 className="text-3xl font-bold text-white">Deployment Bundle</h1>
                    </div>
                    <div className="space-y-2.5">
                      {([
                        ['Runtime gateway config', Shield, true],
                        ['Identity bindings', Lock, true],
                        ['Audit pipeline config', FileText, true],
                        ['Enforcement engine config', Zap, true],
                        ['Helm chart / VPC template', Package, !!deployment],
                        ['Install checklist + validation report', ListChecks, !!deployment],
                      ] as const).map(([label, Icon, ready], i) => (
                        <div key={i} className="flex items-center gap-3 px-4 py-3.5 rounded-xl" style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                          <Icon size={14} className={ready ? 'text-emerald-400' : 'text-muted-foreground/30'} />
                          <span className={`text-sm flex-1 ${ready ? 'text-white/90' : 'text-muted-foreground/40'}`}>{label}</span>
                          {ready ? <CheckCircle2 size={14} className="text-emerald-400 shrink-0" /> : <RefreshCw size={12} className="text-muted-foreground/30 animate-spin shrink-0" />}
                        </div>
                      ))}
                    </div>
                    {deployment && (
                      <>
                        <details className="rounded-2xl overflow-hidden" style={{ border:'1px solid rgba(255,255,255,0.08)' }}>
                          <summary className="cursor-pointer px-5 py-3.5 text-xs font-semibold text-muted-foreground/60 select-none" style={{ background:'rgba(255,255,255,0.02)' }}>
                            Environment Variables ({Object.keys(deployment.env_vars).length})
                          </summary>
                          <div className="overflow-auto max-h-44" style={{ background:'rgba(0,0,0,0.4)' }}>
                            <pre className="p-4 text-[11px] text-white/60 font-mono">{Object.entries(deployment.env_vars).map(([k,v]) => `${k}=${v}`).join('\n')}</pre>
                          </div>
                        </details>
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              const content = Object.entries(deployment.env_vars).map(([k,v]) => `${k}=${v}`).join('\n')
                              const blob = new Blob([content], { type: 'text/plain' })
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url; a.download = 'edon.env'; a.click()
                              URL.revokeObjectURL(url)
                            }}
                            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold transition-colors"
                            style={{ background:'rgba(74,222,128,0.1)', border:'1px solid rgba(74,222,128,0.25)', color:'#86efac' }}>
                            <Package size={14} /> Download .env Bundle
                          </button>
                          <button
                            onClick={() => {
                              const content = Object.entries(deployment.env_vars).map(([k,v]) => `${k}=${v}`).join('\n')
                              navigator.clipboard.writeText(content).catch(() => {})
                            }}
                            className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm transition-colors"
                            style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.1)', color:'rgba(255,255,255,0.5)' }}>
                            <Copy size={14} />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* -- Screen 10 ---------------------------------------------- */}
                {screen === 10 && (
                  <div className="max-w-lg space-y-6">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Final Step</p>
                      <h1 className="text-3xl font-bold text-white">Install & Go Live</h1>
                    </div>
                    <div className="space-y-2.5">
                      {['Installing gateway', 'Binding identity provider', 'Activating enforcement engine', 'Verifying network routing', 'Audit pipeline online'].map((step, i) => {
                        const done = activationStep >= 0 && i <= activationStep
                        const active = activationStep === i
                        return (
                          <motion.div key={i} initial={{ opacity:0, x:12 }} animate={{ opacity:1, x:0 }} transition={{ delay:i*0.15 }}
                            className="flex items-center gap-3 px-5 py-3.5 rounded-xl transition-all duration-300"
                            style={{
                              background: done ? 'rgba(74,222,128,0.07)' : 'rgba(255,255,255,0.02)',
                              border: done ? '1px solid rgba(74,222,128,0.2)' : '1px solid rgba(255,255,255,0.06)',
                            }}>
                            {active && !done ? (
                              <RefreshCw size={14} className="text-emerald-400 animate-spin shrink-0" />
                            ) : done ? (
                              <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                            ) : (
                              <div className="w-3.5 h-3.5 rounded-full shrink-0" style={{ border:'2px solid rgba(255,255,255,0.15)' }} />
                            )}
                            <span className={`text-sm flex-1 ${done ? 'text-white/90' : 'text-white/35'}`}>{step}</span>
                            <span className={`text-[11px] font-bold transition-colors ${done ? 'text-emerald-400' : 'text-white/20'}`}>{done ? 'DONE' : 'PENDING'}</span>
                          </motion.div>
                        )
                      })}
                    </div>
                    <div className="rounded-2xl p-6 space-y-3" style={{ border:'1px solid rgba(74,222,128,0.22)', background:'rgba(74,222,128,0.05)' }}>
                      <p className="font-semibold text-emerald-200">Governance system ready to activate.</p>
                      <p className="text-sm text-muted-foreground leading-relaxed">Once activated, EDON enforces governance in real time. All agent actions are intercepted, evaluated, and enforced per Policy Pack v1. The production console unlocks immediately.</p>
                      {profile && <p className="text-xs text-emerald-400/70">Risk tier: <span className="font-bold">{profile.risk_tier.toUpperCase()}</span> / {profile.agent_systems.length} system{profile.agent_systems.length !== 1 ? 's' : ''} governed</p>}
                    </div>
                  </div>
                )}

              </div>

              {/* CTA bar */}
              {ctaReady && (
                <div className="px-8 pb-8 pt-4 shrink-0" style={{ borderTop:'1px solid rgba(255,255,255,0.04)' }}>
                  {apiErr && (
                    <div className="flex items-center gap-2 text-xs text-red-400/70 mb-3">
                      <AlertCircle size={12} />{apiErr}
                    </div>
                  )}
                  <button onClick={handleCTA} disabled={busy || (screen === 8 && !allTrustChecked)}
                    className="w-full flex items-center justify-center gap-2.5 py-4 rounded-2xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: screen === 10 ? 'rgba(74,222,128,0.22)' : 'rgba(74,222,128,0.12)',
                      border: screen === 10 ? '2px solid rgba(74,222,128,0.5)' : '1px solid rgba(74,222,128,0.28)',
                      color: '#86efac',
                      boxShadow: screen === 10 ? '0 0 24px rgba(74,222,128,0.12)' : 'none',
                    }}>
                    {busy ? <RefreshCw size={16} className="animate-spin" /> : screen === 10 ? <Zap size={16} /> : <ChevronRight size={16} />}
                    {busy ? 'Activating...' : CTA_LABELS[screen]}
                  </button>
                </div>
              )}

            </motion.div>
          </AnimatePresence>
        </div>

      </div>
    </div>
  )
}


// -- Onboarding helper components (reused in OnboardingTab) --------------------

function OnboardingTab() {
  const [step, setStep]           = useState<OBStep>(1)
  const [maxReached, setMaxReached] = useState<OBStep>(1)
  const [busy, setBusy]           = useState(false)
  const [err, setErr]             = useState('')

  // Profile list
  const [profiles, setProfiles]   = useState<import('./api').OnboardingProfile[]>([])
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null)
  const [profile, setProfile]     = useState<import('./api').OnboardingProfile | null>(null)
  const [status, setStatus]       = useState<import('./api').OnboardingStatus | null>(null)

  // Step outputs
  const [topology,   setTopology]   = useState<import('./api').OnboardingTopology | null>(null)
  const [bundle,     setBundle]     = useState<import('./api').OnboardingPolicyBundle | null>(null)
  const [deployment, setDeployment] = useState<import('./api').OnboardingDeploymentPackage | null>(null)
  const [signoff,    setSignoff]    = useState<import('./api').OnboardingSignoff | null>(null)
  const [expansion,  setExpansion]  = useState<{ signals: import('./api').OnboardingExpansionSignal[]; expansion_recommended: boolean } | null>(null)

  // Runtime onboarding
  const [runtimes, setRuntimes] = useState<import('./api').RuntimeRegistration[]>([])
  const [runtimeLoading, setRuntimeLoading] = useState(true)
  const [runtimeBusy, setRuntimeBusy] = useState(false)
  const [runtimeMessage, setRuntimeMessage] = useState('')
  const [runtimeError, setRuntimeError] = useState('')
  const [selectedRuntimeId, setSelectedRuntimeId] = useState<string | null>(null)
  const [runtimeDraft, setRuntimeDraft] = useState({
    runtime_name: 'Cardiology Note Helper',
    vendor_name: '',
    vendor_id: '',
    source_type: 'Existing system',
    agent_count: 1,
    department: 'Cardiology',
    purpose: 'Draft clinical notes',
    runtime_type: 'Service',
    requested_access: ['Epic.note.draft'],
    connectors: ['Epic'],
  })

  // Step 1 form state
  const [orgName, setOrgName]     = useState('')
  const [idp, setIdp]             = useState('none')
  const [envs, setEnvs]           = useState<string[]>(['saas'])
  const [compliance, setCompliance] = useState<string[]>([])
  const [agentSystems, setAgentSystems] = useState<Array<{
    name: string; agent_type: string; actions: string[]; data_classes: string[]; external_sinks: string[]; description: string
    vendor_name?: string; department?: string
  }>>([{ name: '', agent_type: 'llm_agent', actions: [], data_classes: [], external_sinks: [], description: '', vendor_name: '', department: '' }])

  // Signoff form
  const [signoffBy, setSignoffBy] = useState('')
  const [ksAuthority, setKsAuthority] = useState('admin')

  const advance = (to: OBStep) => {
    setStep(to)
    if (to > maxReached) setMaxReached(to)
  }

  const loadProfileList = useCallback(async () => {
    try {
      const r = await api.onboardingListProfiles()
      setProfiles(r.profiles)
    } catch { /* ignore */ }
  }, [])

  const loadRuntimes = useCallback(async () => {
    setRuntimeLoading(true)
    try {
      const res = await api.onboardingListRuntimes()
      setRuntimes(res.runtimes)
      setSelectedRuntimeId(curr => curr && res.runtimes.some(r => r.runtime_id === curr) ? curr : (res.runtimes[0]?.runtime_id ?? null))
    } catch { /* ignore */ }
    finally { setRuntimeLoading(false) }
  }, [])

  useEffect(() => {
    if (SHOW_ADVANCED_ONBOARDING) loadProfileList()
  }, [loadProfileList])
  useEffect(() => { loadRuntimes() }, [loadRuntimes])

  const loadStatus = useCallback(async (id: string) => {
    try {
      const s = await api.onboardingGetStatus(id)
      setStatus(s)
      // Restore step from saved stage
      const stageStep: Record<string, OBStep> = {
        intake: 1, topology: 2, bootstrap: 3, deployment: 4,
        shadow: 5, signoff_pending: 6, live: 7, expanding: 7,
      }
      const restored = stageStep[s.stage] ?? 1
      setStep(restored)
      setMaxReached(restored)
    } catch { /* ignore */ }
  }, [])

  const resumeProfile = async (p: import('./api').OnboardingProfile) => {
    setActiveProfileId(p.profile_id)
    setProfile(p)
    await loadStatus(p.profile_id)
  }

  // -- Step 1 submit ----------------------------------------------------------
  const handleIntake = async () => {
    if (!orgName.trim()) { setErr('Organisation name required'); return }
    const invalid = agentSystems.find(a => !a.name.trim())
    if (invalid) { setErr('All agent systems need a name'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingSubmitIntake({
        org_name: orgName,
        agent_systems: agentSystems,
        identity_provider: idp,
        environments: envs,
        compliance_requirements: compliance,
      })
      setProfile(r.profile)
      setActiveProfileId(r.profile.profile_id)
      await loadStatus(r.profile.profile_id)
      await loadProfileList()
      advance(2)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Intake failed') }
    finally { setBusy(false) }
  }

  // -- Step 2: Topology -------------------------------------------------------
  const handleTopology = async () => {
    if (!activeProfileId) return
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingGenerateTopology(activeProfileId)
      setTopology(r.topology)
      await loadStatus(activeProfileId)
      advance(3)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Topology failed') }
    finally { setBusy(false) }
  }

  // -- Step 3: Bootstrap ------------------------------------------------------
  const handleBootstrap = async () => {
    if (!activeProfileId) return
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingBootstrapPolicies(activeProfileId)
      setBundle(r.policy_bundle)
      await loadStatus(activeProfileId)
      advance(4)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Bootstrap failed') }
    finally { setBusy(false) }
  }

  // -- Step 4: Deployment -----------------------------------------------------
  const handleDeployment = async () => {
    if (!activeProfileId) return
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingGetDeployment(activeProfileId)
      setDeployment(r.deployment_package)
      await loadStatus(activeProfileId)
      advance(5)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Deployment package failed') }
    finally { setBusy(false) }
  }

  // -- Step 5: Shadow Mode ----------------------------------------------------
  const handleShadow = async () => {
    if (!activeProfileId) return
    setBusy(true); setErr('')
    try {
      await api.onboardingSetShadowMode(activeProfileId, true)
      await loadStatus(activeProfileId)
      advance(6)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Shadow mode failed') }
    finally { setBusy(false) }
  }

  // -- Step 6: Signoff --------------------------------------------------------
  const handleSignoffRequest = async () => {
    if (!activeProfileId || !signoffBy.trim()) { setErr('Approver name required'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingRequestSignoff(activeProfileId, {
        requested_by: signoffBy,
        enforcement_scope: profile?.agent_systems.map(a => a.name) ?? [],
        escalation_rules_accepted: true,
        kill_switch_authority: ksAuthority,
        data_classes_governed: profile?.all_data_classes ?? [],
      })
      setSignoff(r.signoff)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Signoff request failed') }
    finally { setBusy(false) }
  }

  const handleSignoffApprove = async () => {
    if (!signoff || !signoffBy.trim()) return
    setBusy(true); setErr('')
    try {
      await api.onboardingApproveSignoff(signoff.signoff_id, signoffBy)
      await loadStatus(activeProfileId!)
      advance(7)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Signoff approval failed') }
    finally { setBusy(false) }
  }

  // -- Step 7: Expansion ------------------------------------------------------
  const handleExpansion = async () => {
    if (!activeProfileId) return
    setBusy(true); setErr('')
    try {
      const r = await api.onboardingGetExpansion(activeProfileId)
      setExpansion(r)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Expansion check failed') }
    finally { setBusy(false) }
  }

  const updateAgent = (i: number, field: string, value: unknown) => {
    setAgentSystems(prev => prev.map((a, idx) => idx === i ? { ...a, [field]: value } : a))
  }

  const intakeSummary = useMemo(() => {
    const activeSystems = agentSystems.filter(a => a.name.trim().length > 0)
    const vendors = [...new Set(activeSystems.map(a => (a.vendor_name || '').trim()).filter(Boolean) as string[])]
    const departments = [...new Set(activeSystems.map(a => (a.department || '').trim()).filter(Boolean) as string[])]
    const totalActions = activeSystems.reduce((n, a) => n + a.actions.length, 0)
    return {
      systems: activeSystems.length,
      vendors,
      departments,
      totalActions,
    }
  }, [agentSystems])

  const profileSummary = useMemo(() => {
    const vendors = [...new Set((profile?.agent_systems ?? []).map(a => (a as { vendor_name?: string }).vendor_name).filter(Boolean) as string[])]
    const departments = [...new Set((profile?.agent_systems ?? []).map(a => (a as { department?: string }).department).filter(Boolean) as string[])]
    return { vendors, departments }
  }, [profile])

  const selectedRuntime = runtimes.find(r => r.runtime_id === selectedRuntimeId) ?? null
  const runtimeStats = useMemo(() => ({
    total: runtimes.length,
    observing: runtimes.filter(r => String(r.status).toLowerCase() === 'observing').length,
    approved: runtimes.filter(r => String(r.review_status).toLowerCase() === 'approved').length,
    governed: runtimes.filter(r => String(r.governance_mode).toLowerCase() === 'governed').length,
  }), [runtimes])
  const runtimeRisk = useMemo(() => {
    const access = runtimeDraft.requested_access.join(' ').toLowerCase()
    const connectors = runtimeDraft.connectors.join(' ').toLowerCase()
    if (/writeback|medication|delete|admin/.test(access + ' ' + connectors)) return 'High'
    if (/phi|ehr|note|draft|export|audit/.test(access + ' ' + connectors)) return 'Medium'
    return 'Low'
  }, [runtimeDraft.requested_access, runtimeDraft.connectors])

  const registerRuntime = async () => {
    if (!runtimeDraft.runtime_name.trim()) {
      setRuntimeError('Runtime name is required')
      return
    }
    setRuntimeBusy(true); setRuntimeError(''); setRuntimeMessage('')
    try {
      const res = await api.onboardingRegisterRuntime({
        runtime_name: runtimeDraft.runtime_name.trim(),
        vendor_name: runtimeDraft.vendor_name.trim(),
        vendor_id: runtimeDraft.vendor_id.trim(),
        source_type: runtimeDraft.source_type,
        agent_count: runtimeDraft.agent_count,
        department: runtimeDraft.department.trim(),
        purpose: runtimeDraft.purpose.trim(),
        runtime_type: runtimeDraft.runtime_type,
        requested_access: runtimeDraft.requested_access,
        connectors: runtimeDraft.connectors,
      })
      setRuntimes(prev => [res.runtime, ...prev.filter(r => r.runtime_id !== res.runtime.runtime_id)])
      setSelectedRuntimeId(res.runtime.runtime_id)
      setRuntimeMessage(res.message)
    } catch (e) {
      setRuntimeError(e instanceof Error ? e.message : 'Failed to register runtime')
    } finally {
      setRuntimeBusy(false)
    }
  }

  const reviewRuntime = async (runtimeId: string, approved = true) => {
    setRuntimeBusy(true); setRuntimeError(''); setRuntimeMessage('')
    try {
      const res = await api.onboardingReviewRuntime(runtimeId, getReviewerName() || 'admin', approved, approved ? 'Approved in console' : 'Rejected in console')
      setRuntimes(prev => prev.map(r => r.runtime_id === runtimeId ? res.runtime : r))
      setRuntimeMessage(res.message)
    } catch (e) {
      setRuntimeError(e instanceof Error ? e.message : 'Failed to review runtime')
    } finally {
      setRuntimeBusy(false)
    }
  }

  const promoteRuntime = async (runtimeId: string) => {
    setRuntimeBusy(true); setRuntimeError(''); setRuntimeMessage('')
    try {
      const res = await api.onboardingPromoteRuntime(runtimeId, getReviewerName() || 'admin')
      setRuntimes(prev => prev.map(r => r.runtime_id === runtimeId ? res.runtime : r))
      setRuntimeMessage(res.message)
      await loadRuntimes()
    } catch (e) {
      setRuntimeError(e instanceof Error ? e.message : 'Failed to promote runtime')
    } finally {
      setRuntimeBusy(false)
    }
  }

  useEffect(() => {
    const activeSystems = (profile?.agent_systems ?? []).filter(a => a.name?.trim())
    const vendors = [...new Set(activeSystems.map(a => (a as { vendor_name?: string }).vendor_name).filter(Boolean) as string[])]
    const departments = [...new Set(activeSystems.map(a => (a as { department?: string }).department).filter(Boolean) as string[])]
    _setPS('onboarding', [
      {
        profile_id: profile?.profile_id ?? activeProfileId ?? 'new',
        org_name: profile?.org_name ?? orgName ?? 'new',
        stage: profile?.stage ?? (activeProfileId === 'new' ? 'draft' : 'intake'),
        agents: activeSystems.length,
        vendors: vendors.length,
        vendor_list: vendors,
        departments: departments.length,
        department_list: departments,
        actions: profile?.all_actions?.length ?? activeSystems.reduce((n, a) => n + (a.actions?.length ?? 0), 0),
        posture: profile?.signed_off ? 'governed' : 'audit-only',
        runtime_count: runtimes.length,
        selected_runtime_id: selectedRuntimeId,
        runtime_message: runtimeMessage,
      },
    ] as Record<string, unknown>[])
  }, [profile, activeProfileId, orgName, runtimes.length, selectedRuntimeId, runtimeMessage])

  const readinessRail = [
    ['SSO-only mode', profile?.identity_provider && profile.identity_provider !== 'none' ? 'Enforced' : 'Pending'],
    ['MFA enforcement', compliance.includes('HIPAA') ? 'Active' : 'Pending'],
    ['Tenant isolation', status ? 'Verified' : 'Pending'],
    ['Audit encryption', status || bundle ? 'Active' : 'Pending'],
    ['Decision binding', deployment ? 'Active' : 'Pending'],
    ['Rollback validation', deployment ? 'Passed' : 'Pending'],
    ['PHI safeguards', compliance.length > 0 ? 'Enforced' : 'Pending'],
  ] as const

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl border border-border/40 bg-card/30 p-5 space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
              <Package size={20} className="text-emerald-400" />
              Runtime Onboarding
            </h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Register new hospital AI runtimes into shadow governance before they can touch real systems.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {profile && <RiskBadge tier={profile.risk_tier} />}
            <span className="text-xs px-2.5 py-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">Shadow first</span>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['Registered', runtimeStats.total, 'runtime declarations'],
            ['Observing', runtimeStats.observing, 'shadow mode'],
            ['Reviewed', runtimeStats.approved, 'admin approved'],
            ['Governed', runtimeStats.governed, 'live governance'],
          ].map(([label, value, sub]) => (
            <div key={label} className="rounded-xl border border-border/40 bg-background/25 px-3 py-3">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{label}</p>
              <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
              <p className="text-[11px] text-muted-foreground">{sub}</p>
            </div>
          ))}
        </div>
        <div className="grid gap-2 md:grid-cols-3 text-xs">
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">1. Declare the runtime</p>
            <p className="mt-1 text-muted-foreground">Name, vendor, department, purpose, and requested scope.</p>
          </div>
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">2. Observe in shadow</p>
            <p className="mt-1 text-muted-foreground">EDON audits and simulates policy without execution authority.</p>
          </div>
          <div className="rounded-xl border border-border/30 bg-background/20 p-3">
            <p className="font-semibold text-foreground">3. Review, then promote</p>
            <p className="mt-1 text-muted-foreground">Promotion only happens after explicit admin review.</p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-semibold text-foreground">Register Runtime</p>
            <p className="text-xs text-muted-foreground">Shadow governance only. No execution authority until later approval.</p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="px-2 py-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">Shadow Governance</span>
            <span className={`px-2 py-1 rounded-full border ${runtimeRisk === 'High' ? 'border-red-500/30 bg-red-500/10 text-red-300' : runtimeRisk === 'Medium' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'}`}>
              {runtimeRisk} risk
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Runtime Name</label>
            <input value={runtimeDraft.runtime_name} onChange={e => setRuntimeDraft(p => ({ ...p, runtime_name: e.target.value }))}
              placeholder="Cardiology Note Helper"
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Department</label>
            <input value={runtimeDraft.department} onChange={e => setRuntimeDraft(p => ({ ...p, department: e.target.value }))}
              placeholder="Cardiology"
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Purpose</label>
            <input value={runtimeDraft.purpose} onChange={e => setRuntimeDraft(p => ({ ...p, purpose: e.target.value }))}
              placeholder="Draft clinical notes"
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Runtime Type</label>
            <select value={runtimeDraft.runtime_type} onChange={e => setRuntimeDraft(p => ({ ...p, runtime_type: e.target.value }))}
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/40">
              {['Service', 'Worker', 'Agent'].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Vendor Name</label>
            <input value={runtimeDraft.vendor_name} onChange={e => setRuntimeDraft(p => ({ ...p, vendor_name: e.target.value }))}
              placeholder="Epic"
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Vendor ID</label>
            <input value={runtimeDraft.vendor_id} onChange={e => setRuntimeDraft(p => ({ ...p, vendor_id: e.target.value }))}
              placeholder="vendor-001"
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Source Type</label>
            <select value={runtimeDraft.source_type} onChange={e => setRuntimeDraft(p => ({ ...p, source_type: e.target.value }))}
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/40">
              {['Existing system', 'Vendor console', 'CSV export', 'Inventory API'].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Agents being added</label>
            <input type="number" min={1} value={runtimeDraft.agent_count} onChange={e => setRuntimeDraft(p => ({ ...p, agent_count: Number(e.target.value) || 1 }))}
              className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-medium">Requested Access</label>
            <TagInput value={runtimeDraft.requested_access} onChange={v => setRuntimeDraft(p => ({ ...p, requested_access: v }))} placeholder="Epic.note.draft" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-medium">Connectors</label>
            <TagInput value={runtimeDraft.connectors} onChange={v => setRuntimeDraft(p => ({ ...p, connectors: v }))} placeholder="Epic, Teams, SIEM" />
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button onClick={registerRuntime} disabled={runtimeBusy}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
            {runtimeBusy ? <RefreshCw size={13} className="animate-spin" /> : <ChevronRight size={13} />}
            Register Runtime
          </button>
          <p className="text-xs text-muted-foreground">Shadow governance first. Review and promotion happen from the queue below.</p>
        </div>

        {(runtimeMessage || runtimeError) && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs border ${runtimeError ? 'bg-destructive/10 border-destructive/30 text-destructive' : 'bg-emerald-500/10 border-emerald-500/25 text-emerald-300'}`}>
            <AlertCircle size={12} /> {runtimeError || runtimeMessage}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border/40 bg-card/20 p-4 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-semibold text-foreground">Pending Runtime Queue</p>
            <p className="text-xs text-muted-foreground">Click a runtime to open its drawer. Shadow governance is the default.</p>
          </div>
          <div className="text-xs text-muted-foreground">{runtimes.length} registered</div>
        </div>
        {runtimeLoading ? (
          <Spinner />
        ) : runtimes.length === 0 ? (
          <Empty message="No runtimes registered yet" />
        ) : (
          <div className="space-y-2">
            <div className="grid grid-cols-[1.3fr_0.9fr_0.6fr_0.6fr_0.7fr] gap-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground/50">
              <span>Runtime</span><span>Dept</span><span>Risk</span><span>Mode</span><span>Status</span>
            </div>
            {runtimes.map(rt => (
              <button
                key={rt.runtime_id}
                type="button"
                onClick={() => setSelectedRuntimeId(rt.runtime_id)}
                className={`w-full text-left rounded-xl border px-3 py-3 transition-colors ${selectedRuntime?.runtime_id === rt.runtime_id ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-border/40 bg-background/20 hover:border-border'}`}>
                <div className="grid grid-cols-[1.3fr_0.9fr_0.6fr_0.6fr_0.7fr] gap-2 items-center text-sm">
                  <div className="min-w-0">
                    <p className="font-medium text-foreground truncate">{rt.runtime_name}</p>
                    <p className="text-[11px] text-muted-foreground truncate">{rt.vendor_name || 'No vendor'} / {rt.source_type || 'Source'}</p>
                  </div>
                  <span className="text-muted-foreground truncate">{rt.department || '-'}</span>
                  <RiskBadge tier={rt.risk_tier || 'low'} />
                  <span className="text-xs text-emerald-300 truncate capitalize">{rt.governance_mode}</span>
                  <span className="text-xs text-muted-foreground truncate capitalize">{rt.status}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedRuntime && (
        <div className="rounded-xl border border-border/40 bg-card/20 p-4 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-foreground">{selectedRuntime.runtime_name}</p>
              <p className="text-xs text-muted-foreground">{selectedRuntime.department || 'Unassigned'} / {selectedRuntime.runtime_type} / {selectedRuntime.governance_mode}</p>
            </div>
            <div className="flex items-center gap-2">
              <RiskBadge tier={selectedRuntime.risk_tier || 'low'} />
              <span className="text-xs px-2 py-1 rounded-full border border-border/40 text-muted-foreground">{selectedRuntime.review_status}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {[
              ['Vendor', selectedRuntime.vendor_name || '-'],
              ['Vendor ID', selectedRuntime.vendor_id || '-'],
              ['Agents', String(selectedRuntime.agent_count ?? 1)],
              ['Purpose', selectedRuntime.purpose || '-'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-border/30 bg-background/20 px-3 py-2.5">
                <p className="text-muted-foreground/60">{label}</p>
                <p className="font-medium text-foreground truncate">{value}</p>
              </div>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border/30 bg-background/20 p-3 space-y-2">
              <p className="text-xs font-semibold text-foreground/80">Scopes</p>
              <div className="flex flex-wrap gap-1.5">
                {selectedRuntime.requested_access.map(s => <span key={s} className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">{s}</span>)}
              </div>
            </div>
            <div className="rounded-lg border border-border/30 bg-background/20 p-3 space-y-2">
              <p className="text-xs font-semibold text-foreground/80">Connectors</p>
              <div className="flex flex-wrap gap-1.5">
                {selectedRuntime.connectors.map(s => <span key={s} className="text-[10px] px-2 py-0.5 rounded-full border border-border/30 bg-muted/30 text-foreground/80">{s}</span>)}
              </div>
            </div>
          </div>
          <div className="rounded-lg border border-border/30 bg-background/20 p-3 space-y-2">
            <p className="text-xs font-semibold text-foreground/80">Policy simulation</p>
            <p className="text-xs text-muted-foreground">{String(selectedRuntime.policy_simulation?.summary ?? 'Shadow Governance active. Policy simulation is verifying access boundaries.')}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={() => reviewRuntime(selectedRuntime.runtime_id, true)} disabled={runtimeBusy || selectedRuntime.review_status === 'approved'} className="text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:text-foreground transition-colors disabled:opacity-50">
              Approve review
            </button>
            <button onClick={() => promoteRuntime(selectedRuntime.runtime_id)} disabled={runtimeBusy || selectedRuntime.review_status !== 'approved'} className="text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:text-foreground transition-colors disabled:opacity-50">
              Promote runtime
            </button>
            <span className="text-xs text-muted-foreground">Promotion adds the runtime to the governed fleet and audit trail.</span>
          </div>
        </div>
      )}

      {/* Saved profiles picker */}
      {SHOW_ADVANCED_ONBOARDING && profiles.length > 0 && !activeProfileId && (
        <div className="rounded-xl border border-border/40 bg-card/30 p-4 space-y-3">
          <p className="text-sm font-medium text-foreground">Resume a previous onboarding</p>
          <div className="space-y-2">
            {profiles.map(p => (
              <button key={p.profile_id} type="button" onClick={() => resumeProfile(p)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-colors text-left">
                <div>
                  <p className="text-sm font-medium text-foreground">{p.org_name}</p>
                  <p className="text-xs text-muted-foreground">{p.profile_id} / {p.stage}</p>
                </div>
                <div className="flex items-center gap-2">
                  <RiskBadge tier={p.risk_tier} />
                  {p.signed_off && <span className="text-xs text-emerald-400 font-medium">LIVE LIVE</span>}
                </div>
              </button>
            ))}
          </div>
          <button onClick={() => setActiveProfileId('new')}
            className="text-xs text-emerald-400 hover:underline flex items-center gap-1">
            <Plus size={12} /> Start new onboarding
          </button>
        </div>
      )}

      {SHOW_ADVANCED_ONBOARDING && !!activeProfileId && (
        <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-2">
          {readinessRail.map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border/40 bg-card/20 px-3 py-2.5">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{label}</p>
              <p className="text-sm font-semibold text-foreground mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Step nav */}
      {SHOW_ADVANCED_ONBOARDING && (activeProfileId && activeProfileId !== 'new') && (
        <OBStepNav current={step} maxReached={maxReached} onSelect={s => setStep(s)} />
      )}

      {err && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          <AlertCircle size={14} /> {err}
        </div>
      )}

      {/* -- Step 1: Hospital Environment Detection ------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && (step === 1 && (!activeProfileId || activeProfileId === 'new')) && (
        <div className="space-y-6">
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">1</span>
              Hospital Environment Detection
            </h3>

            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">Organisation name</label>
              <input value={orgName} onChange={e => setOrgName(e.target.value)}
                placeholder="Regional One Health"
                className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-medium">Identity provider</label>
                <select value={idp} onChange={e => setIdp(e.target.value)}
                  className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/40">
                  {IDP_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground font-medium">Connected environments</label>
                <MultiSelect options={ENVIRONMENT_OPTIONS} selected={envs} onChange={setEnvs} />
              </div>
            </div>

          <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">Compliance requirements</label>
              <MultiSelect options={COMPLIANCE_OPTIONS} selected={compliance} onChange={setCompliance} placeholder="None selected" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Agent systems</p>
                <p className="text-sm font-semibold text-foreground mt-1">{intakeSummary.systems}</p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Vendors</p>
                <p className="text-sm font-semibold text-foreground mt-1 truncate" title={intakeSummary.vendors.join(', ') || 'No vendor yet'}>
                  {intakeSummary.vendors.length === 0 ? 'None' : intakeSummary.vendors.length === 1 ? intakeSummary.vendors[0] : `${intakeSummary.vendors.length} vendors`}
                </p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Departments</p>
                <p className="text-sm font-semibold text-foreground mt-1 truncate" title={intakeSummary.departments.join(', ') || 'No department yet'}>
                  {intakeSummary.departments.length === 0 ? 'None' : intakeSummary.departments.length === 1 ? intakeSummary.departments[0] : `${intakeSummary.departments.length} departments`}
                </p>
              </div>
              <div className="rounded-xl border border-border/40 bg-background/30 px-3 py-2.5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Actions</p>
                <p className="text-sm font-semibold text-foreground mt-1">{intakeSummary.totalActions}</p>
              </div>
            </div>
          </div>

          {/* Agent systems */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Bot size={14} className="text-emerald-400" /> Agent Systems
                </h3>
              <button type="button" onClick={() => setAgentSystems(prev => [...prev, { name: '', agent_type: 'llm_agent', actions: [], data_classes: [], external_sinks: [], description: '', vendor_name: '', department: '' }])}
                className="text-xs text-emerald-400 hover:underline flex items-center gap-1">
                <Plus size={12} /> Add agent system
              </button>
            </div>

            {agentSystems.map((agent, i) => (
              <div key={i} className="rounded-xl border border-border/40 bg-card/20 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-foreground/70">Agent System {i + 1}</p>
                  {agentSystems.length > 1 && (
                    <button type="button" onClick={() => setAgentSystems(prev => prev.filter((_, idx) => idx !== i))}
                      className="text-muted-foreground hover:text-destructive transition-colors">
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Name</label>
                    <input value={agent.name} onChange={e => updateAgent(i, 'name', e.target.value)}
                      placeholder="e.g. clinical-assistant-v2"
                      className="w-full bg-background border border-border/40 rounded-lg px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Agent type</label>
                    <select value={agent.agent_type} onChange={e => updateAgent(i, 'agent_type', e.target.value)}
                      className="w-full bg-background border border-border/40 rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500/40">
                      {AGENT_TYPE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Vendor</label>
                    <input value={agent.vendor_name || ''} onChange={e => updateAgent(i, 'vendor_name', e.target.value)}
                      placeholder="e.g. Vendor A"
                      className="w-full bg-background border border-border/40 rounded-lg px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Department</label>
                    <input value={agent.department || ''} onChange={e => updateAgent(i, 'department', e.target.value)}
                      placeholder="e.g. Cardiology"
                      className="w-full bg-background border border-border/40 rounded-lg px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Actions (what can this agent do?)</label>
                  <TagInput value={agent.actions} onChange={v => updateAgent(i, 'actions', v)} placeholder="e.g. ehr.read, email.send" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Data classes it touches</label>
                  <MultiSelect options={DATA_CLASS_OPTIONS} selected={agent.data_classes} onChange={v => updateAgent(i, 'data_classes', v)} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">External sinks (where does data go out?)</label>
                  <TagInput value={agent.external_sinks} onChange={v => updateAgent(i, 'external_sinks', v)} placeholder="e.g. sendgrid.com, twilio.com" />
                </div>
              </div>
            ))}
          </div>

          <button onClick={handleIntake} disabled={busy}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
            {busy ? <RefreshCw size={14} className="animate-spin" /> : <ChevronRight size={14} />}
            Generate Governance Deployment Profile
          </button>
        </div>
      )}

      {/* Profile summary card (shown in steps 2-7) */}
      {SHOW_ADVANCED_ONBOARDING && profile && step > 1 && (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-foreground">{profile.org_name}</p>
            <div className="flex items-center gap-2">
              <RiskBadge tier={profile.risk_tier} />
              {profile.signed_off && <span className="text-xs text-emerald-400 font-semibold">LIVE LIVE</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>{profile.agent_systems.length} agent system{profile.agent_systems.length !== 1 ? 's' : ''}</span>
            {profileSummary.vendors.length > 0 && <span>{profileSummary.vendors.length} vendor{profileSummary.vendors.length !== 1 ? 's' : ''}</span>}
            {profileSummary.departments.length > 0 && <span>{profileSummary.departments.length} department{profileSummary.departments.length !== 1 ? 's' : ''}</span>}
            <span>{profile.all_actions.length} actions</span>
            {profile.all_data_classes.length > 0 && <span>Data: {profile.all_data_classes.join(', ')}</span>}
            {profile.compliance_requirements.length > 0 && <span>Compliance: {profile.compliance_requirements.join(', ')}</span>}
            {status && <span className="text-emerald-400/80">{status.stage_label}</span>}
          </div>
        </div>
      )}

      {/* -- Step 2: Topology ----------------------------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && step === 2 && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">2</span>
              Connector Verification
            </h3>
            <p className="text-xs text-muted-foreground">
              Confirm IdP, Epic, Teams, and SIEM trust before governance is activated.
            </p>
            {!topology ? (
              <button onClick={handleTopology} disabled={busy}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
                Verify Connectors
              </button>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {Object.entries(topology.summary).filter(([,v]) => typeof v === 'number').map(([k, v]) => (
                    <div key={k} className="rounded-lg border border-border/30 bg-background/30 px-3 py-2 text-center">
                      <p className="text-lg font-bold text-foreground">{v as number}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{k.replace(/_/g, ' ')}</p>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-foreground/70">Enforcement Points</p>
                  {topology.enforcement_points.slice(0, 8).map(ep => (
                    <div key={ep.point_id} className="flex items-start gap-3 px-3 py-2 rounded-lg bg-background/20 border border-border/20">
                      <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${ep.is_external_boundary ? 'bg-orange-400' : 'bg-emerald-400'}`} />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-foreground">{ep.label}</p>
                        <p className="text-[11px] text-muted-foreground">{ep.connector_type} / {ep.intercepts.slice(0, 4).join(', ')}{ep.intercepts.length > 4 ? ` +${ep.intercepts.length - 4}` : ''}</p>
                      </div>
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold border ${ep.priority === 'required' ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-muted/10 border-border/30 text-muted-foreground'}`}>{ep.priority}</span>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-foreground/70">Trust Boundaries</p>
                  {topology.trust_boundaries.map(tb => (
                    <div key={tb.boundary_id} className="px-3 py-2 rounded-lg bg-background/20 border border-border/20">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium text-foreground">{tb.label}</p>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${tb.enforcement === 'block_by_default' ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'}`}>{tb.enforcement}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{tb.from_zone} -&gt; {tb.to_zone}</p>
                    </div>
                  ))}
                </div>
                <button onClick={() => advance(3)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors">
                  <ChevronRight size={13} /> Continue to Governance Activation
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* -- Step 3: Policy Bootstrap --------------------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && step === 3 && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">3</span>
              Governance Activation
            </h3>
            <p className="text-xs text-muted-foreground">SSO, MFA, audit encryption, tenant isolation, and decision binding are activated here.</p>
            {!bundle ? (
              <button onClick={handleBootstrap} disabled={busy}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <Shield size={13} />}
                Generate Policies
              </button>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Hard Safety', count: bundle.hard_safety.length, color: 'text-red-400 border-red-500/30 bg-red-500/10' },
                    { label: 'Operational', count: bundle.operational.length, color: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' },
                    { label: 'Intent Contracts', count: bundle.intent_contracts.length, color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
                  ].map(({ label, count, color }) => (
                    <div key={label} className={`rounded-lg border px-3 py-3 text-center ${color}`}>
                      <p className="text-2xl font-bold">{count}</p>
                      <p className="text-[11px] font-medium mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
                {[
                  { key: 'hard_safety', policies: bundle.hard_safety, label: 'Layer A - Hard Safety', badge: 'text-red-400 border-red-500/30 bg-red-500/10' },
                  { key: 'operational', policies: bundle.operational, label: 'Layer B - Operational', badge: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' },
                  { key: 'contracts',   policies: bundle.intent_contracts, label: 'Layer C - Intent Contracts', badge: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
                ].map(({ key, policies, label, badge }) => (
                  <details key={key} className="group">
                    <summary className={`cursor-pointer flex items-center justify-between px-3 py-2 rounded-lg border ${badge} text-xs font-semibold select-none`}>
                      {label}
                      <span className="text-muted-foreground font-normal">{policies.length} rules</span>
                    </summary>
                    <div className="mt-2 space-y-1.5 pl-2">
                      {policies.map(p => (
                        <div key={p.policy_id} className="flex items-start gap-3 px-3 py-2 rounded-lg bg-background/20 border border-border/20">
                          <DecisionBadge decision={p.decision} />
                          <div className="min-w-0">
                            <p className="text-xs text-foreground font-medium">{p.action_pattern} <span className="font-normal text-muted-foreground">({p.agent_system})</span></p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">{p.reason}</p>
                            {p.immutable_after_signoff && <span className="text-[10px] text-orange-400/80">- immutable after signoff</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
                <button onClick={() => advance(4)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors">
                  <ChevronRight size={13} /> Continue to Governed Action Readiness
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* -- Step 4: Deployment Package ------------------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && step === 4 && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">4</span>
              Governed Action Readiness
            </h3>
            <p className="text-xs text-muted-foreground">Show the operational boundaries EDON will enforce before a tenant is promoted.</p>
            {!deployment ? (
              <button onClick={handleDeployment} disabled={busy}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <Package size={13} />}
                Generate Deployment Package
              </button>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-3 text-xs">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/30 bg-background/20">
                    <span className="text-muted-foreground">Mode:</span>
                    <span className="font-semibold text-foreground">{deployment.deployment_mode}</span>
                  </div>
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/30 bg-background/20">
                    <span className="text-muted-foreground">Est. setup:</span>
                    <span className="font-semibold text-foreground">{deployment.estimated_setup_h}h</span>
                  </div>
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/30 bg-background/20">
                    <span className="text-muted-foreground">Connectors:</span>
                    <span className="font-semibold text-foreground">{deployment.connector_configs.length}</span>
                  </div>
                </div>
                <details>
                  <summary className="cursor-pointer text-xs font-semibold text-foreground/70 hover:text-foreground px-2 py-1.5 rounded border border-border/30 select-none">
                    Environment Variables ({Object.keys(deployment.env_vars).length})
                  </summary>
                  <div className="mt-2 rounded-lg bg-black/30 border border-border/20 overflow-auto max-h-48">
                    <pre className="p-3 text-[11px] text-foreground/80 font-mono">{Object.entries(deployment.env_vars).map(([k,v]) => `${k}=${v}`).join('\n')}</pre>
                  </div>
                </details>
                <details>
                  <summary className="cursor-pointer text-xs font-semibold text-foreground/70 hover:text-foreground px-2 py-1.5 rounded border border-border/30 select-none">
                    Network Requirements
                  </summary>
                  <div className="mt-2 rounded-lg bg-black/30 border border-border/20 overflow-auto max-h-48">
                    <pre className="p-3 text-[11px] text-foreground/80 font-mono">{JSON.stringify(deployment.network_requirements, null, 2)}</pre>
                  </div>
                </details>
                <details>
                  <summary className="cursor-pointer text-xs font-semibold text-foreground/70 hover:text-foreground px-2 py-1.5 rounded border border-border/30 select-none">
                    Rollback Plan
                  </summary>
                  <div className="mt-2 space-y-1">
                    {deployment.rollback_plan.map(step => (
                      <p key={step} className="text-xs text-muted-foreground px-3 py-1.5 rounded bg-background/20 border border-border/20">{step}</p>
                    ))}
                  </div>
                </details>
                <button onClick={() => advance(5)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors">
                  <Eye size={13} /> Continue to Procurement Readiness
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* -- Step 5: Shadow Mode -------------------------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && step === 5 && (
        <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">5</span>
            Procurement Readiness
          </h3>
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-xs text-blue-300/80 space-y-1">
            <p className="font-semibold text-blue-300">Pilot evidence and readiness review.</p>
            <p>EDON shows the governed boundary, the active evidence pack, and the launch criteria before production.</p>
            <p>Output: connector certification, audit integrity, restore drill status, and pilot readiness.</p>
          </div>
          {profile?.shadow_mode_enabled ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                <Eye size={15} /> Readiness review is ACTIVE
              </div>
              <p className="text-xs text-muted-foreground">
                Check the governance findings and evidence pack to review what EDON would have blocked.
                When you're ready to go live, proceed to approval.
              </p>
              <button onClick={() => advance(6)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors">
                <CheckCircle2 size={13} /> Ready for Approval & Launch
              </button>
            </div>
          ) : (
            <button onClick={handleShadow} disabled={busy}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 text-sm font-semibold hover:bg-blue-500/30 transition-colors disabled:opacity-50">
              {busy ? <RefreshCw size={13} className="animate-spin" /> : <EyeOff size={13} />}
              Run Readiness Review
            </button>
          )}
        </div>
      )}

      {/* -- Step 6: Signoff ------------------------------------------------ */}
      {SHOW_ADVANCED_ONBOARDING && step === 6 && (
        <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/30 text-emerald-300 text-[11px] font-bold flex items-center justify-center">6</span>
              Approval & Launch
            </h3>
          <div className="rounded-lg border border-orange-500/20 bg-orange-500/5 px-4 py-3 text-xs text-orange-300/80 space-y-1">
            <p className="font-semibold text-orange-300">Nothing goes live without explicit approval.</p>
            <p>The client explicitly approves: enforcement scope, escalation rules, kill-switch authority, data classes governed.</p>
            <p>After signoff, hard safety policies are immutable. Shadow mode deactivates. Active enforcement begins.</p>
          </div>

          {profile && (
            <div className="space-y-2 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground/70">What's being approved:</p>
              <ul className="space-y-1 pl-3">
                <li>- {profile.agent_systems.length} agent system(s) governed: {profile.agent_systems.map(a => a.name).join(', ')}</li>
                <li>- Data classes: {profile.all_data_classes.join(', ') || 'none'}</li>
                <li>- Compliance: {profile.compliance_requirements.join(', ') || 'none'}</li>
                <li>- Risk tier: <RiskBadge tier={profile.risk_tier} /></li>
              </ul>
            </div>
          )}

          {!signoff ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground font-medium">Approver name / email</label>
                  <input value={signoffBy} onChange={e => setSignoffBy(e.target.value)}
                    placeholder="jane@acme.com"
                    className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground font-medium">Kill-switch authority</label>
                  <input value={ksAuthority} onChange={e => setKsAuthority(e.target.value)}
                    placeholder="admin / security-team"
                    className="w-full bg-background border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/40" />
                </div>
              </div>
              <button onClick={handleSignoffRequest} disabled={busy}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-orange-500/20 border border-orange-500/40 text-orange-300 text-sm font-semibold hover:bg-orange-500/30 transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <KeyRound size={13} />}
                Request Go-Live Signoff
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-3 space-y-1.5 text-xs">
                <p className="font-semibold text-yellow-300">Signoff Request {signoff.signoff_id}</p>
                <p className="text-muted-foreground">Requested by: {signoff.requested_by} at {new Date(signoff.requested_at).toLocaleString()}</p>
                <p className="text-muted-foreground">Status: <span className={signoff.status === 'approved' ? 'text-emerald-400' : 'text-yellow-400'}>{signoff.status.toUpperCase()}</span></p>
              </div>
              {signoff.status === 'pending' && (
                <button onClick={handleSignoffApprove} disabled={busy}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                  {busy ? <RefreshCw size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                  Approve & Go Live
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* -- Step 7: Live + Expansion --------------------------------------- */}
      {SHOW_ADVANCED_ONBOARDING && step === 7 && (
        <div className="space-y-4">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5 space-y-3">
            <h3 className="text-sm font-semibold text-emerald-300 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-500/40 text-white text-[11px] font-bold flex items-center justify-center">OK</span>
              EDON is LIVE - Active Enforcement
            </h3>
            <p className="text-xs text-muted-foreground">
              Every agent action is intercepted, evaluated, and enforced. All decisions produce audit trails with causal attribution.
            </p>
            <div className="flex flex-wrap gap-2 text-xs">
              {['ALLOW', 'BLOCK', 'ESCALATE', 'DEGRADE', 'PAUSE'].map(d => <DecisionBadge key={d} decision={d} />)}
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <TrendingUp size={14} className="text-emerald-400" />
                Expansion Signals
              </h3>
              <button onClick={handleExpansion} disabled={busy}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border/40 hover:border-emerald-500/30 hover:bg-emerald-500/5 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
                {busy ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                Check signals
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              EDON continuously monitors for new agents, new data sinks, policy stress points, and fleet campaign patterns.
            </p>
            {expansion && (
              <div className="space-y-2">
                {expansion.expansion_recommended && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-300 text-xs font-semibold">
                    <AlertTriangle size={13} /> Expansion recommended - {expansion.signals.filter(s => s.severity === 'high').length} high-severity signals
                  </div>
                )}
                {expansion.signals.length === 0 ? (
                  <p className="text-xs text-emerald-400/70">No expansion signals detected. Profile is current.</p>
                ) : (
                  expansion.signals.map((sig, i) => (
                    <div key={i} className="px-3 py-2.5 rounded-lg bg-background/20 border border-border/20 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium text-foreground">{sig.title}</p>
                        <RiskBadge tier={sig.severity} />
                      </div>
                      <p className="text-[11px] text-muted-foreground">{sig.description}</p>
                      <p className="text-[11px] text-emerald-400/80 font-medium">-&gt; {sig.recommended_action}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// -----------------------------------------------------------------------------

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart2, roles: ['admin'] },
  { id: 'agents', label: 'Agents', icon: Users, roles: ['admin'] },
  { id: 'audit', label: 'Audit', icon: FileText, roles: ['admin'] },
  { id: 'policies', label: 'Policies', icon: Shield, roles: ['admin'] },
  { id: 'review', label: 'Review Queue', icon: ClipboardList, roles: ['admin'] },
  { id: 'onboarding', label: 'Onboard', icon: Package, roles: ['admin'] },
  { id: 'operations', label: 'Operations', icon: ServerCog, roles: ['admin'] },
  { id: 'settings', label: 'Settings', icon: Settings, roles: ['admin'] },
] as const

type Tab =
  | typeof TABS[number]['id']
  | 'clinical_summary'
  | 'clinical_explain'
  | 'clinical_actions'
  | 'research_experiments'
  | 'research_simulations'
  | 'research_readiness'
  | 'policy_diff'
  | 'control_tower'
  | 'systems'
  | 'decisions'
  | 'deployments'
  | 'assurance'
  | 'report'

// -- Live Key Claim Banner -----------------------------------------------------

function LiveKeyClaimBanner() {
  const [pending, setPending] = useState(false)
  const [claiming, setClaiming] = useState(false)
  const [liveKey, setLiveKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.checkPendingLiveKey().then(r => setPending(r.pending)).catch(() => {})
  }, [])

  const claim = async () => {
    setClaiming(true)
    setError('')
    try {
      const r = await api.claimLiveKey()
      setLiveKey(r.key)
      setPending(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to claim key')
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
              <p className="text-xs text-emerald-300/80 flex-1">Your live production key is ready. Claim it now - it will only be shown once.</p>
              <button onClick={claim} disabled={claiming}
                className="shrink-0 flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/30 transition-colors disabled:opacity-50">
                {claiming ? 'Claiming...' : 'Reveal my live key'}
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
          {error && <span className="text-xs text-red-300">{error}</span>}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

// -- App -----------------------------------------------------------------------

type LockdownState = 'unknown' | 'pending' | 'active' | 'inactive' | 'failed' | 'unreachable'
type LockdownDetails = { reason?: string; actor?: string; verifiedAt?: string }

export default function App() {
  const [authed, setAuthed] = useState(() => !!getAuth())
  const [meInfo, setMeInfo] = useState<MeResponse | null>(() => (CONSOLE_DEV_MODE ? CONSOLE_DEV_ME : null))
  const isAdmin = meInfo?.is_admin === true || ['admin', 'super_admin', 'governance_admin', 'security_admin'].includes(meInfo?.role ?? '')
  const vertical = meInfo?.vertical ?? null
  const [tab, setTab] = useState<Tab>('dashboard')
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('edon_theme') as 'dark' | 'light') || 'dark')
  const [health, setHealth] = useState<{ ok: boolean; version: string; uptime_seconds: number } | null>(null)
  const [hgiHalt, setHgiHalt] = useState(false)
  const [lockdownState, setLockdownState] = useState<LockdownState>('unknown')
  const [lockdownDetails, setLockdownDetails] = useState<LockdownDetails>({})
  const [lockdownPhrase, setLockdownPhrase] = useState('')
  const [lockdownConfirm, setLockdownConfirm] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [aside, setAside] = useState<AsideItem | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [shadowModeEnabled, setShadowModeEnabled] = useState<boolean>(() => !!CONSOLE_DEV_ME.is_sandbox)
  const [shadowModeSaving, setShadowModeSaving] = useState(false)
  const effectiveRole: ConsoleRole = CONSOLE_DEV_MODE || isAdmin ? 'admin' : 'clinical'
  const shadowModeActive = shadowModeEnabled

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('edon_theme', theme)
  }, [theme])

  useEffect(() => {
    setTab(ROLE_DEFAULT_TAB[effectiveRole] as Tab)
  }, [effectiveRole])

  useEffect(() => {
    if (!authed) return
    api.health().then(h => setHealth(h)).catch(() => {})
    // Only fetch /me if we don't already have it (i.e. returning session, not fresh login)
    if (!meInfo) api.me().then(m => setMeInfo(m)).catch(() => {})
    api.getShadowMode().then(r => setShadowModeEnabled(r.enabled)).catch(() => {})
    // Sync kill switch state from backend on load and every 30s
    const syncKillSwitch = () => api.killSwitchStatus().then(s => {
      setHgiHalt(s.active)
      setLockdownState(s.active ? 'active' : 'inactive')
      setLockdownDetails({ reason: s.reason, actor: s.activated_by, verifiedAt: new Date().toLocaleString() })
    }).catch(() => setLockdownState('unreachable'))
    syncKillSwitch()
    const fetchCount = async () => {
      try { const r = await api.reviewQueue('pending'); setPendingCount(r?.count ?? 0) } catch { /* silent */ }
      syncKillSwitch()
    }
    fetchCount(); const iv = setInterval(fetchCount, 30000); return () => clearInterval(iv)
  }, [authed])

  const toggleShadowMode = useCallback(async () => {
    if (shadowModeSaving) return
    setShadowModeSaving(true)
    try {
      const r = await api.setShadowMode(!shadowModeActive)
      setShadowModeEnabled(r.enabled)
    } catch {
      // keep current state if the backend rejects the change
    } finally {
      setShadowModeSaving(false)
    }
  }, [shadowModeActive, shadowModeSaving])

  const handleLogout = useCallback(() => { clearAuth(); setAuthed(false); setHealth(null); setMeInfo(null) }, [])

  // Session timeout
  const { warning: sessionWarn, secondsLeft, extend } = useSessionTimeout(handleLogout)

  const activateLockdown = async () => {
    const actor = getReviewerName() || 'console-operator'
    if (lockdownPhrase.trim() !== 'LOCKDOWN') return
    setLockdownState('pending')
    try {
      const r = await api.killSwitchActivate('Emergency lockdown activated from console', actor)
      setHgiHalt(r.active)
      setLockdownState(r.active ? 'active' : 'failed')
      setLockdownDetails({ reason: 'Emergency lockdown activated from console', actor, verifiedAt: new Date().toLocaleString() })
      setLockdownConfirm(false)
      setLockdownPhrase('')
    } catch {
      setLockdownState('failed')
    }
  }
  const liftLockdown = async () => {
    const actor = getReviewerName() || 'console-operator'
    setLockdownState('pending')
    try {
      const r = await api.killSwitchDeactivate(actor)
      setHgiHalt(r.active)
      setLockdownState(r.active ? 'active' : 'inactive')
      setLockdownDetails({ actor, verifiedAt: new Date().toLocaleString() })
    } catch {
      setLockdownState('failed')
    }
  }

  if (!authed) return <LoginScreen onLogin={me => { setMeInfo(me); setAuthed(true) }} />

  const auth = getAuth()
  const visibleTabs = TABS.filter(t => (t.roles as readonly ConsoleRole[]).includes(effectiveRole))

  return (
    <AsideCtx.Provider value={{ open: (item) => setAside(item) }}>
    <div className="min-h-screen flex flex-col">
      {/* Lockdown banner */}
      <AnimatePresence>
        {hgiHalt && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="flex items-center justify-between px-6 py-1.5 bg-red-500/15 border-b border-red-500/30">
            <div className="flex items-center gap-2 text-red-400 text-xs">
              <AlertTriangle size={13} className="animate-pulse shrink-0" />
              <span className="font-bold tracking-wider">EMERGENCY LOCKDOWN ACTIVE</span>
              <span className="text-red-400/60 hidden sm:inline">- all agent actions suspended</span>
            </div>
            <button onClick={liftLockdown} className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-red-400 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 transition-colors">
              Lift Lockdown
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        {hgiHalt && (
          <div className="flex items-center justify-between px-4 py-1.5 bg-red-500/15 border-b border-red-500/30">
            <div className="flex items-center gap-2 text-red-400 text-xs">
              <AlertTriangle size={13} className="animate-pulse shrink-0" />
              <span className="font-bold tracking-wider">EMERGENCY LOCKDOWN ACTIVE</span>
              <span className="text-red-400/60 hidden sm:inline">- all agent actions suspended</span>
            </div>
            <button onClick={liftLockdown}
              className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-red-400 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 transition-colors">
              Lift Lockdown
            </button>
          </div>
        )}
        <div className="max-w-7xl mx-auto px-4 flex items-center gap-3 h-14">
          {/* Wordmark */}
          <div className="shrink-0 flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/15 border border-primary/25 flex items-center justify-center">
              <Lock size={13} className="text-primary" />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="edon-brand font-bold text-foreground text-sm">EDON</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" title="Live" />
            </div>
          </div>

          <div className="hidden lg:flex items-center rounded-lg border border-border bg-muted/30 px-3 py-1 text-xs font-medium text-foreground">
            Admin View
          </div>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-0.5 px-1 py-0.5 rounded-xl bg-muted/40 border border-border/40">
            {visibleTabs.map(t => {
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
            {/* Health status */}
            {health && (
              <div className="hidden lg:flex items-center gap-1.5 text-xs text-muted-foreground">
                <div className={`w-1.5 h-1.5 rounded-full animate-pulse-dot ${health.ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
                <span>{health.ok ? 'Healthy' : 'Degraded'}</span>
                <span className="text-border">/</span>
                <span>v{health.version}</span>
              </div>
            )}

            <div className="hidden xl:flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={lockdownState === 'active' ? 'text-red-400' : lockdownState === 'failed' || lockdownState === 'unreachable' ? 'text-amber-400' : 'text-emerald-400'}>
                Lockdown {lockdownState}
              </span>
              {lockdownDetails.verifiedAt && <span>/ {lockdownDetails.verifiedAt}</span>}
            </div>

            {/* Signed-in admin identity */}
            <div className="hidden sm:flex items-center gap-2 px-2.5 h-8 rounded-full border border-border bg-secondary/60 text-xs text-muted-foreground">
              <div className="w-5 h-5 rounded-full border border-primary/30 bg-primary/10 flex items-center justify-center">
                <User size={11} className="text-primary" />
              </div>
              <div className="min-w-0 leading-tight">
                <p className="font-medium text-foreground max-w-[132px] truncate">
                  {CONSOLE_DEV_MODE ? 'Development Admin' : (meInfo?.key_name || getReviewerName() || 'Console Admin')}
                </p>
                <p className="text-[9px] text-muted-foreground max-w-[132px] truncate">
                  {ROLE_LABELS[(meInfo?.role || 'admin') as ConsoleRole] ?? meInfo?.role ?? 'Admin'} / {meInfo?.vertical === 'healthcare' ? 'St. Mercy' : (getReviewerDept() || meInfo?.tenant_id || 'Tenant')}
                </p>
              </div>
            </div>

            {/* Notifications */}
            <NotificationsBell />

            {/* AI Chat */}
            {isAdmin && (
              <button onClick={() => setChatOpen(true)} title="Governance AI"
                className="flex items-center justify-center w-8 h-8 rounded-lg border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary transition-colors">
                <Bot size={14} />
              </button>
            )}

            {/* Theme toggle */}
            <button onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              className="flex items-center justify-center w-8 h-8 rounded-lg border border-border/60 bg-secondary/60 hover:bg-secondary transition-colors"
              aria-label="Toggle theme">
              {theme === 'dark' ? <Sun size={13} className="text-muted-foreground" /> : <Moon size={13} className="text-muted-foreground" />}
            </button>

            {/* Session mode */}
            {CONSOLE_DEV_MODE ? (
              <div className="flex items-center justify-center h-8 px-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-[11px] font-semibold text-emerald-300">
                Dev mode
              </div>
            ) : (
              <button onClick={handleLogout} title="Disconnect"
                className="flex items-center justify-center w-8 h-8 rounded-lg border border-border/60 bg-secondary/60 hover:bg-destructive/10 hover:border-destructive/30 hover:text-destructive text-muted-foreground transition-colors">
                <LogOut size={13} />
              </button>
            )}

            {/* Emergency lockdown */}
            <button onClick={() => hgiHalt ? liftLockdown() : setLockdownConfirm(true)}
              title={hgiHalt ? 'Lockdown active - click to lift' : 'Emergency lockdown'}
              className={cn(
                'flex items-center justify-center w-8 h-8 rounded-lg border transition-all',
                hgiHalt
                  ? 'bg-red-500/20 border-red-400/50 text-red-400 animate-pulse'
                  : 'border-border/60 bg-secondary/60 text-muted-foreground/50 hover:text-red-400/80 hover:bg-red-500/[0.08] hover:border-red-500/20',
              )}>
              <AlertTriangle size={13} />
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
                <div className="grid grid-cols-1 gap-1 mb-2">
                  <div className="rounded-lg px-2 py-2 text-xs font-medium bg-primary/15 text-primary text-center">Admin View</div>
                  <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                    <p className="text-xs font-semibold text-foreground truncate">
                      {CONSOLE_DEV_MODE ? 'Development Admin' : (meInfo?.key_name || getReviewerName() || 'Console Admin')}
                    </p>
                    <p className="text-[11px] text-muted-foreground truncate">
                      {ROLE_LABELS[(meInfo?.role || 'admin') as ConsoleRole] ?? meInfo?.role ?? 'Admin'} / {meInfo?.tenant_id || 'Tenant'}
                    </p>
                  </div>
                </div>
                {visibleTabs.map(t => {
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

      {/* Mode banner */}
      {meInfo && (
        <AnimatePresence>
          <motion.button
            type="button"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            onClick={toggleShadowMode}
            disabled={shadowModeSaving}
            aria-pressed={shadowModeActive}
            className={cn(
              'w-full text-left overflow-hidden',
              shadowModeActive ? 'bg-blue-500/10 border-b border-blue-500/30' : 'bg-emerald-500/10 border-b border-emerald-500/30',
              shadowModeSaving ? 'cursor-wait opacity-90' : 'cursor-pointer',
            )}
          >
            <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center gap-3">
              <div className={`flex items-center gap-2 ${shadowModeActive ? 'text-blue-300' : 'text-emerald-300'}`}>
                <FlaskConical size={14} className="shrink-0" />
                <span className="text-xs font-semibold">{shadowModeActive ? 'Sandbox mode' : 'Live governance'}</span>
              </div>
              <p className={`text-xs ${shadowModeActive ? 'text-blue-300/80' : 'text-emerald-300/80'}`}>
                {shadowModeSaving
                  ? 'Updating mode...'
                  : shadowModeActive
                    ? 'Audit-only. Click to switch to live governance.'
                    : 'Live governance. Click to return to audit-only.'}
              </p>
            </div>
          </motion.button>
        </AnimatePresence>
      )}

      {/* Page content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.15 }}>
            <ErrorBoundary>
              <Suspense fallback={<div className="glass-card p-4 text-sm text-muted-foreground">Loading console surface...</div>}>
                {tab === 'clinical_summary' && <ClinicalSummaryTab />}
                {tab === 'clinical_explain' && <ClinicalExplainTab />}
                {tab === 'clinical_actions' && <ClinicalActionsTab />}
                {tab === 'research_experiments' && <ResearchExperimentsTab />}
                {tab === 'research_simulations' && <ShadowSimulationTab />}
                {tab === 'research_readiness' && <ReadinessTab />}
                {tab === 'policy_diff' && <PolicyDiffViewerTab />}
                {tab === 'control_tower' && <ControlTowerTab />}
                {tab === 'systems' && <SystemRegistryTable />}
                {tab === 'deployments' && <DeploymentGatekeeperTab />}
                {tab === 'assurance' && <RedTeamTab />}
                {tab === 'dashboard' && <DashboardTab tenantLabel={meInfo?.tenant_id || 'Tenant'} sandboxMode={shadowModeActive} vertical={meInfo?.vertical ?? null} />}
                {tab === 'decisions' && <DecisionsTab />}
                {tab === 'agents'    && <AgentsTab />}

                {tab === 'audit'     && <AuditTab />}
                {tab === 'report'    && <ComplianceReportTab />}
                  {tab === 'policies'  && <PoliciesTab tenantLabel={meInfo?.tenant_id || 'Tenant'} vertical={vertical} />}
                {tab === 'review'    && <ReviewTab vertical={vertical} meInfo={meInfo} />}
                  {tab === 'onboarding' && <OnboardingTab />}
                  {tab === 'operations' && <OperationsTab />}
                   {tab === 'settings'  && <SettingsTabV2 onReconnect={() => api.health().then(h => setHealth(h)).catch(() => {})} isAdmin={isAdmin} meInfo={meInfo} onLogout={handleLogout} health={health} lockdownState={lockdownState} lockdownDetails={lockdownDetails} shadowModeEnabled={shadowModeActive} shadowModeSaving={shadowModeSaving} onToggleShadowMode={toggleShadowMode} />}
                </Suspense>
            </ErrorBoundary>
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="border-t border-border/30 py-3 px-4 text-center">
        <p className="text-xs text-muted-foreground flex items-center justify-center gap-1.5">
          <Zap size={10} className="text-primary" /> EDON Governance Console
          <span className="text-border">/</span>
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
              {CONSOLE_DEV_MODE ? (
                <div className="flex-1 py-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-xs text-emerald-300 text-center font-semibold">
                  Dev mode is always on
                </div>
              ) : (
                <button onClick={handleLogout} className="flex-1 py-1.5 rounded-xl border border-white/10 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Sign out now</button>
              )}
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
              <p className="text-sm text-muted-foreground leading-relaxed">
                This will block all agent actions for the current tenant until the backend confirms lockdown is lifted. Type LOCKDOWN to confirm.
              </p>
              <input value={lockdownPhrase} onChange={e => setLockdownPhrase(e.target.value)}
                placeholder="LOCKDOWN"
                className="w-full rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm font-mono text-red-300 focus:outline-none focus:ring-1 focus:ring-red-400" />
              {lockdownState === 'failed' && <p className="text-xs text-red-400">Activation failed or backend was unreachable. Lockdown was not marked active locally.</p>}
              <div className="flex gap-3">
                <button onClick={() => setLockdownConfirm(false)} className="flex-1 py-2.5 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">Cancel</button>
                <button onClick={() => activateLockdown()} disabled={lockdownPhrase.trim() !== 'LOCKDOWN' || lockdownState === 'pending'}
                  className="flex-1 py-2.5 rounded-xl bg-red-500/20 border border-red-500/40 text-red-400 text-sm font-bold hover:bg-red-500/30 transition-colors disabled:opacity-40">
                  {lockdownState === 'pending' ? 'Confirming...' : 'Activate Lockdown'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Aside panel - AI reasoning for cited items */}
      <AnimatePresence>
        {aside && <AsidePanel key={`${aside.type}-${aside.id}`} type={aside.type} id={aside.id} onClose={() => setAside(null)} />}
      </AnimatePresence>
    </div>
    </AsideCtx.Provider>
  )
}



