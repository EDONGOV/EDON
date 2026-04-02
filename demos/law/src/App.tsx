import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  Scale,
  Building2,
  Lightbulb,
  Home,
  Users,
  DollarSign,
  Shield,
  Heart,
  Globe,
  CheckSquare,
  BookOpen,
  FileText,
  FilePen,
  AlertCircle,
  Clock,
  Gavel,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Hash,
  Search,
  ChevronLeft,
  ChevronRight,
  User,
  BarChart3,
  TrendingUp,
  Zap,
  Lock,
  Share2,
  Eye,
  FileJson,
  FileSpreadsheet,
  RefreshCcw,
  X,
  MessageSquare,
  Send,
  Sparkles,
  Bot,
  Briefcase,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type Verdict = 'ALLOW' | 'BLOCK' | 'ESCALATE'
type Tab = 'dashboard' | 'agents' | 'audit' | 'policies'

interface LawAgent {
  id: string
  name: string
  department: string
  deptLabel: string
  status: 'active' | 'idle' | 'alert'
  decisions24h: number
  blocked24h: number
  blockRate: number
  lastAction: string
  lastActiveMin: number
  riskLevel: 'low' | 'medium' | 'high'
  office: string
  barNo: string
  matterLoad: number
}

interface DemoEvent {
  id: string
  verdict: Verdict
  agent: string
  department: string
  deptLabel: string
  toolOp: string
  reasonCode: string | null
  latencyMs: number
  ts: Date
  hash: string
  riskScore: number
  matterId: string
  intentId: string
  policyVersion: string
  explanation: string
}

interface SharedAuditRecord {
  id: string
  recordId: string
  summary: { toolOp: string; verdict: string; ts: string }
  sharedBy: string
  sharedWith: string[]
  note: string
  sharedAt: string
}

// ─── Seeded RNG ───────────────────────────────────────────────────────────────

function makeRng(initSeed: number) {
  let seed = initSeed >>> 0
  return function rng(): number {
    seed = (Math.imul(seed ^ (seed >>> 16), 0x45d9f3b) >>> 0)
    seed = (Math.imul(seed ^ (seed >>> 16), 0x45d9f3b) >>> 0)
    return (seed >>> 0) / 0xffffffff
  }
}

function murmurHash(str: string): string {
  let h = 0xdeadbeef
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 0x5bd1e995)
    h ^= h >>> 13
  }
  h = Math.imul(h ^ (h >>> 15), 0x27d4eb2f)
  return (((h >>> 0) * 0x100000000 + (h >>> 0)) >>> 0).toString(16).padStart(16, '0') +
    (((h >>> 4) * 0x100000001 + (h >>> 2)) >>> 0).toString(16).padStart(16, '0')
}

// ─── Department Config ────────────────────────────────────────────────────────

interface DeptConfig {
  key: string
  label: string
  icon: LucideIcon
  color: string
  bgColor: string
  borderColor: string
  count: number
  offices: string[]
}

// 50+42+38+35+40+32+28+25+30+45+50+48+37 = 500
const DEPARTMENTS: DeptConfig[] = [
  { key: 'litigation',  label: 'Litigation',          icon: Gavel,       color: 'text-red-400',    bgColor: 'bg-red-500/10',    borderColor: 'border-red-500/30',    count: 50, offices: ['Floor 12', 'Floor 11'] },
  { key: 'corporate',   label: 'Corporate & M&A',     icon: Building2,   color: 'text-blue-400',   bgColor: 'bg-blue-500/10',   borderColor: 'border-blue-500/30',   count: 42, offices: ['Floor 10', 'Floor 9'] },
  { key: 'ip',          label: 'Intellectual Property',icon: Lightbulb,  color: 'text-amber-400',  bgColor: 'bg-amber-500/10',  borderColor: 'border-amber-500/30',  count: 38, offices: ['Floor 8'] },
  { key: 'realestate',  label: 'Real Estate',         icon: Home,        color: 'text-emerald-400',bgColor: 'bg-emerald-500/10',borderColor: 'border-emerald-500/30',count: 35, offices: ['Floor 7'] },
  { key: 'employment',  label: 'Employment & Labor',  icon: Users,       color: 'text-violet-400', bgColor: 'bg-violet-500/10', borderColor: 'border-violet-500/30', count: 40, offices: ['Floor 6', 'Floor 5'] },
  { key: 'tax',         label: 'Tax & Finance',       icon: DollarSign,  color: 'text-yellow-400', bgColor: 'bg-yellow-500/10', borderColor: 'border-yellow-500/30', count: 32, offices: ['Floor 5'] },
  { key: 'criminal',    label: 'Criminal Defense',    icon: Shield,      color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/30', count: 28, offices: ['Floor 4'] },
  { key: 'family',      label: 'Family Law',          icon: Heart,       color: 'text-pink-400',   bgColor: 'bg-pink-500/10',   borderColor: 'border-pink-500/30',   count: 25, offices: ['Floor 3'] },
  { key: 'immigration', label: 'Immigration',         icon: Globe,       color: 'text-cyan-400',   bgColor: 'bg-cyan-500/10',   borderColor: 'border-cyan-500/30',   count: 30, offices: ['Floor 3', 'Floor 2'] },
  { key: 'compliance',  label: 'Compliance & Ethics', icon: CheckSquare, color: 'text-teal-400',   bgColor: 'bg-teal-500/10',   borderColor: 'border-teal-500/30',   count: 45, offices: ['Floor 2'] },
  { key: 'research',    label: 'Legal Research',      icon: BookOpen,    color: 'text-sky-400',    bgColor: 'bg-sky-500/10',    borderColor: 'border-sky-500/30',    count: 50, offices: ['Floor 1', 'Floor 2'] },
  { key: 'documents',   label: 'Document Review',     icon: FileText,    color: 'text-indigo-400', bgColor: 'bg-indigo-500/10', borderColor: 'border-indigo-500/30', count: 48, offices: ['Floor 1', 'B1'] },
  { key: 'contracts',   label: 'Contract Management', icon: FilePen,     color: 'text-lime-400',   bgColor: 'bg-lime-500/10',   borderColor: 'border-lime-500/30',   count: 37, offices: ['Floor 9', 'Floor 10'] },
]

// ─── Generate Agents ──────────────────────────────────────────────────────────

const AGENT_NAMES: Record<string, string[]> = {
  litigation:  ['Argus',    'Verdict',   'Pleader',  'Trialer',   'Counsel',   'Advocate'],
  corporate:   ['Merger',   'Nexus',     'Accord',   'Diligence', 'Acquire',   'Arbor'],
  ip:          ['Patent',   'Lumina',    'Invent',   'Marca',     'Creativa',  'Ingenio'],
  realestate:  ['Title',    'Escrow',    'Parcel',   'Deed',      'Equity',    'Tenure'],
  employment:  ['Arbitra',  'Labor',     'Wager',    'Equitas',   'Employ',    'Staffa'],
  tax:         ['Fiscal',   'Levita',    'Deduct',   'Audit',     'Revenue',   'Remit'],
  criminal:    ['Defenda',  'Alibi',     'Exonera',  'Proof',     'Acquit',    'Juris'],
  family:      ['Custodio', 'Divida',    'Heritag',  'Adopta',    'Mediat',    'Amicus'],
  immigration: ['Visa',     'Asylum',    'Border',   'Status',    'Natura',    'Transit'],
  compliance:  ['Ethica',   'Conform',   'Audita',   'Regula',    'Compass',   'Vigil'],
  research:    ['Lexis',    'Prece',     'Citator',  'Statute',   'Digest',    'Scholar'],
  documents:   ['Review',   'Scan',      'Redact',   'Index',     'Extract',   'Tagger'],
  contracts:   ['Clause',   'Draft',     'Signio',   'Obligo',    'Proviso',   'Term'],
}

const LAST_ACTIONS: string[] = [
  'contract.review.clause', 'case.search.precedent', 'document.redact.pii',
  'matter.status.update', 'billing.time.record', 'court.filing.check',
  'conflict.check.run', 'deposition.draft.prepare', 'settlement.analyze',
  'discovery.docs.process', 'client.comm.log', 'deadline.calendar.check',
]

function generateAgents(): LawAgent[] {
  const rng = makeRng(0xdeadbeef)
  const agents: LawAgent[] = []
  for (const dept of DEPARTMENTS) {
    const names = AGENT_NAMES[dept.key] ?? ['Bot']
    for (let i = 0; i < dept.count; i++) {
      const nameBase = names[Math.floor(rng() * names.length)]
      const num = String(i + 1).padStart(3, '0')
      const id = `${dept.key.toUpperCase().slice(0, 3)}-${num}`
      const decisions = Math.floor(rng() * 800 + 50)
      const blockRate = rng() * 0.28
      const blocked = Math.floor(decisions * blockRate)
      const statusR = rng()
      const status: LawAgent['status'] = statusR > 0.85 ? 'idle' : statusR > 0.93 ? 'alert' : 'active'
      const riskR = rng()
      const riskLevel: LawAgent['riskLevel'] = riskR > 0.85 ? 'high' : riskR > 0.6 ? 'medium' : 'low'
      const office = dept.offices[Math.floor(rng() * dept.offices.length)]
      agents.push({
        id,
        name: `${nameBase}-${num}`,
        department: dept.key,
        deptLabel: dept.label,
        status,
        decisions24h: decisions,
        blocked24h: blocked,
        blockRate: Math.round(blockRate * 1000) / 10,
        lastAction: LAST_ACTIONS[Math.floor(rng() * LAST_ACTIONS.length)],
        lastActiveMin: Math.floor(rng() * 30),
        riskLevel,
        office,
        barNo: `BAR-${Math.floor(rng() * 900000 + 100000)}`,
        matterLoad: Math.floor(rng() * 18 + 1),
      })
    }
  }
  return agents
}

// ─── Generate Events ──────────────────────────────────────────────────────────

const ALLOWED_OPS = [
  'contract.review.clause', 'case.search.precedent', 'document.redact.pii',
  'matter.status.update', 'billing.time.record', 'court.filing.check',
  'conflict.check.run', 'deposition.draft.prepare', 'settlement.analyze',
  'discovery.docs.process', 'client.comm.log', 'deadline.calendar.check',
  'ip.prior.art.search', 'tax.deduction.verify', 'immigration.status.check',
  'compliance.reg.lookup', 'legal.research.query', 'contract.term.extract',
]
const BLOCKED_OPS = [
  'privilege.breach.attempt', 'unauthorized.case.access', 'client.data.bulk.export',
  'billing.rate.override', 'settlement.unauthorized.accept', 'filing.deadline.extend',
  'conflict.check.bypass', 'matter.reassign.unauthorized', 'court.doc.alter',
  'opposing.counsel.contact', 'aml.check.skip', 'gdpr.consent.bypass',
]
const ESCALATE_OPS = [
  'settlement.approve.major', 'conflict.waiver.authorize', 'privilege.waiver.sign',
  'court.consent.order.file', 'client.terminate.represent', 'ethics.complaint.respond',
]
const BLOCK_REASONS = [
  'PRIVILEGE_VIOLATION', 'CONFLICT_OF_INTEREST', 'UNAUTHORIZED_ACCESS',
  'AML_COMPLIANCE', 'BILLING_ANOMALY', 'CONFIDENTIALITY_BREACH', 'BAR_ETHICS_VIOLATION',
]

function generateEvents(agents: LawAgent[]): DemoEvent[] {
  const rng = makeRng(0xcafebabe)
  const now = new Date()
  const events: DemoEvent[] = []
  let prevHash = '0000000000000000'
  for (let i = 0; i < 1000; i++) {
    const verdictR = rng()
    const verdict: Verdict = verdictR < 0.55 ? 'ALLOW' : verdictR < 0.90 ? 'BLOCK' : 'ESCALATE'
    const agent = agents[Math.floor(rng() * agents.length)]
    const toolOp =
      verdict === 'ALLOW'   ? ALLOWED_OPS[Math.floor(rng() * ALLOWED_OPS.length)]
      : verdict === 'BLOCK' ? BLOCKED_OPS[Math.floor(rng() * BLOCKED_OPS.length)]
                            : ESCALATE_OPS[Math.floor(rng() * ESCALATE_OPS.length)]
    const reasonCode = verdict === 'BLOCK' ? BLOCK_REASONS[Math.floor(rng() * BLOCK_REASONS.length)] : null
    const latencyMs = Math.floor(rng() * 18 + 1)
    const minutesAgo = rng() * 60
    const ts = new Date(now.getTime() - minutesAgo * 60 * 1000)
    const matterId = `MTR-${String(Math.floor(rng() * 99999 + 10000))}`
    const riskScore = Math.round(rng() * 100)
    const payload = `${i}|${verdict}|${agent.id}|${toolOp}|${ts.toISOString()}|${prevHash}`
    const hash = murmurHash(payload)
    prevHash = hash
    const intentId = `int_${murmurHash(`intent${i}`).slice(0, 8)}`
    const policyVersions = ['bar-ethics-v3.1.0', 'privilege-protection-v2.4.0', 'aml-compliance-v1.8.0', 'gdpr-legal-v2.0.0', 'model-rules-v3.2.1']
    const policyVersion = policyVersions[Math.floor(rng() * policyVersions.length)]
    const explanations: Record<string, string> = {
      ALLOW:    `Agent ${agent.id} requested ${toolOp}. Intent verified within scope of ${policyVersion}. Risk score ${riskScore}/100 — within threshold. Action permitted.`,
      BLOCK:    `Agent ${agent.id} attempted ${toolOp}. Blocked by ${policyVersion}: ${reasonCode ?? 'policy_match'}. Risk score ${riskScore}/100 exceeds configured limit. Action denied.`,
      ESCALATE: `Agent ${agent.id} requested ${toolOp} on matter ${matterId}. Action requires partner approval per ${policyVersion}. Routed to human review queue.`,
    }
    events.push({
      id: `EVT-${String(i + 1).padStart(6, '0')}`,
      verdict, agent: agent.id, department: agent.department, deptLabel: agent.deptLabel,
      toolOp, reasonCode, latencyMs, ts, hash, riskScore, matterId,
      intentId, policyVersion, explanation: explanations[verdict],
    })
  }
  return events.sort((a, b) => b.ts.getTime() - a.ts.getTime())
}

// ─── Static Data ──────────────────────────────────────────────────────────────

const ALL_AGENTS = generateAgents()
const ALL_EVENTS = generateEvents(ALL_AGENTS)

// ─── Utility Components ───────────────────────────────────────────────────────

function cn(...classes: (string | undefined | false | null)[]) {
  return classes.filter(Boolean).join(' ')
}

interface BadgeProps {
  children: React.ReactNode
  variant?: 'allow' | 'block' | 'escalate' | 'default' | 'outline' | 'green' | 'amber' | 'red'
  className?: string
}
function Badge({ children, variant = 'default', className }: BadgeProps) {
  const base = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border'
  const variants: Record<string, string> = {
    allow:    'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    block:    'bg-red-500/15 text-red-400 border-red-500/30',
    escalate: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    default:  'bg-white/5 text-muted-foreground border-white/10',
    outline:  'bg-transparent text-foreground border-white/20',
    green:    'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    amber:    'bg-amber-500/15 text-amber-400 border-amber-500/30',
    red:      'bg-red-500/15 text-red-400 border-red-500/30',
  }
  return <span className={cn(base, variants[variant], className)}>{children}</span>
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}
function Button({ children, variant = 'default', size = 'md', className, ...props }: ButtonProps) {
  const base = 'inline-flex items-center gap-2 font-medium rounded-xl transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:pointer-events-none'
  const variants: Record<string, string> = {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90',
    outline: 'bg-transparent border border-white/20 text-foreground hover:bg-white/5',
    ghost:   'bg-transparent text-muted-foreground hover:text-foreground hover:bg-white/5',
  }
  const sizes: Record<string, string> = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm', lg: 'px-5 py-2.5 text-base' }
  return <button className={cn(base, variants[variant], sizes[size], className)} {...props}>{children}</button>
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}
function Input({ className, ...props }: InputProps) {
  return (
    <input className={cn('w-full bg-secondary border border-white/10 rounded-xl px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all', className)} {...props} />
  )
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string; value: string; change?: string; changePositive?: boolean
  icon: LucideIcon; accentClass?: string; delay?: number
}
function StatCard({ label, value, change, changePositive, icon: Icon, accentClass = 'text-primary', delay = 0 }: StatCardProps) {
  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4 }} className="glass-card-hover p-5">
      <div className="absolute inset-0 opacity-20 rounded-2xl pointer-events-none" style={{ background: 'radial-gradient(ellipse at 80% 0%, hsl(142 70% 45% / 0.12) 0%, transparent 70%)' }} />
      <div className="relative">
        <div className="flex items-start justify-between mb-3">
          <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">{label}</p>
          <div className={cn('p-2 rounded-lg bg-white/5', accentClass)}><Icon size={16} /></div>
        </div>
        <p className="text-2xl font-bold text-foreground tabular-nums">{value}</p>
        {change && <p className={cn('text-xs mt-1', changePositive ? 'text-emerald-400' : 'text-red-400')}>{change}</p>}
      </div>
    </motion.div>
  )
}

// ─── Verdict helpers ──────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  if (verdict === 'ALLOW')    return <Badge variant="allow"><CheckCircle2 size={10} />ALLOW</Badge>
  if (verdict === 'BLOCK')    return <Badge variant="block"><XCircle size={10} />BLOCK</Badge>
  return <Badge variant="escalate"><AlertTriangle size={10} />ESCALATE</Badge>
}

function DeptIcon({ deptKey, size = 14 }: { deptKey: string; size?: number }) {
  const dept = DEPARTMENTS.find(d => d.key === deptKey)
  if (!dept) return null
  const Icon = dept.icon
  return <Icon size={size} className={dept.color} />
}

function formatTime(ts: Date): string {
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - ts.getTime()) / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  return `${Math.floor(diffMin / 60)}h ago`
}

// ─── Dashboard Tab ────────────────────────────────────────────────────────────

const BLOCK_REASON_LABELS: Record<string, string> = {
  PRIVILEGE_VIOLATION:   'Privilege Violation',
  CONFLICT_OF_INTEREST:  'Conflict of Interest',
  UNAUTHORIZED_ACCESS:   'Unauthorized Access',
  AML_COMPLIANCE:        'AML Compliance',
  BILLING_ANOMALY:       'Billing Anomaly',
  CONFIDENTIALITY_BREACH:'Confidentiality Breach',
  BAR_ETHICS_VIOLATION:  'Bar Ethics Violation',
}

function computeBlockReasonCounts(events: DemoEvent[]) {
  const counts: Record<string, number> = {}
  for (const e of events) {
    if (e.verdict === 'BLOCK' && e.reasonCode)
      counts[e.reasonCode] = (counts[e.reasonCode] ?? 0) + 1
  }
  return Object.entries(counts)
    .map(([k, v]) => ({ key: k, label: BLOCK_REASON_LABELS[k] ?? k, count: v }))
    .sort((a, b) => b.count - a.count).slice(0, 6)
}

function computeDeptActivity(events: DemoEvent[]) {
  const total: Record<string, number> = {}
  const blocked: Record<string, number> = {}
  for (const e of events) {
    total[e.department] = (total[e.department] ?? 0) + 1
    if (e.verdict === 'BLOCK') blocked[e.department] = (blocked[e.department] ?? 0) + 1
  }
  return DEPARTMENTS.slice(0, 8).map(d => ({
    key: d.key, label: d.label, icon: d.icon, color: d.color,
    total: total[d.key] ?? 0, blocked: blocked[d.key] ?? 0,
    blockPct: total[d.key] ? Math.round(((blocked[d.key] ?? 0) / total[d.key]) * 100) : 0,
  }))
}

interface DashboardTabProps {
  displayCount: number; speed: number; setSpeed: (s: number) => void
  paused: boolean; setPaused: (p: boolean) => void; onReset: () => void
  uptime: number; latency: number
}

function DashboardTab({ displayCount, speed, setSpeed, paused, setPaused, onReset, uptime, latency }: DashboardTabProps) {
  const visibleEvents = ALL_EVENTS.slice(0, displayCount)
  const feedEvents = visibleEvents.slice(0, 25)
  const blockReasons = computeBlockReasonCounts(visibleEvents)
  const deptActivity = computeDeptActivity(visibleEvents)
  const maxBlockCount = Math.max(1, ...blockReasons.map(r => r.count))
  const maxDeptTotal  = Math.max(1, ...deptActivity.map(d => d.total))

  const totalGoverned  = 62184 + displayCount
  const totalBlocked   = 19421 + Math.floor(visibleEvents.filter(e => e.verdict === 'BLOCK').length * 0.5)
  const totalEscalated = 2073  + visibleEvents.filter(e => e.verdict === 'ESCALATE').length

  const uptimeDays = Math.floor(uptime / 86400)
  const uptimeHrs  = Math.floor((uptime % 86400) / 3600)
  const uptimeMins = Math.floor((uptime % 3600) / 60)
  const p50 = (latency * 0.6).toFixed(1)
  const p95 = (latency * 1.8).toFixed(1)
  const p99 = (latency * 2.8).toFixed(1)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Legal Governance</h1>
        <p className="text-muted-foreground text-sm mt-1">
          ⚖️ Blackstone &amp; Associates LLP · <span className="text-primary font-medium">500 agents online</span> · Bar Ethics Mode
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Governed"      value={totalGoverned.toLocaleString()}  change="+1 every 800ms"            changePositive  icon={BarChart3}     delay={0} />
        <StatCard label="Blocked"             value={totalBlocked.toLocaleString()}   change="30.7% block rate"           accentClass="text-red-400"    icon={XCircle}       delay={0.05} />
        <StatCard label="Escalated to Partner"value={totalEscalated.toLocaleString()} change="Awaiting partner review"    accentClass="text-amber-400"  icon={AlertTriangle} delay={0.1} />
        <StatCard label="Avg Latency"         value={`${latency.toFixed(1)}ms`}       change="Well within 50ms SLO"      changePositive  accentClass="text-blue-400"   icon={Zap}           delay={0.15} />
      </div>

      {/* Main 2-col */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Live feed */}
        <div className="lg:col-span-2 glass-card p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot" />
              <h2 className="font-semibold text-sm text-foreground">Live Decision Feed</h2>
            </div>
            <Badge variant="default">{displayCount.toLocaleString()} events</Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-white/5">
                  <th className="text-left pb-2 font-medium">Verdict</th>
                  <th className="text-left pb-2 font-medium">Agent</th>
                  <th className="text-left pb-2 font-medium hidden md:table-cell">Tool.Op</th>
                  <th className="text-left pb-2 font-medium hidden lg:table-cell">Reason</th>
                  <th className="text-right pb-2 font-medium">ms</th>
                  <th className="text-right pb-2 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {feedEvents.map((e, idx) => (
                    <motion.tr key={e.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx === 0 ? 0 : 0, duration: 0.25 }}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                      <td className="py-2 pr-2"><VerdictBadge verdict={e.verdict} /></td>
                      <td className="py-2 pr-2">
                        <div className="flex items-center gap-1.5">
                          <DeptIcon deptKey={e.department} size={12} />
                          <span className="font-mono text-foreground">{e.agent}</span>
                        </div>
                      </td>
                      <td className="py-2 pr-2 hidden md:table-cell">
                        <span className="font-mono text-muted-foreground truncate max-w-[160px] block">{e.toolOp}</span>
                      </td>
                      <td className="py-2 pr-2 hidden lg:table-cell">
                        {e.reasonCode
                          ? <span className="text-red-400 font-medium">{e.reasonCode}</span>
                          : <span className="text-muted-foreground/40">—</span>}
                      </td>
                      <td className="py-2 text-right font-mono text-muted-foreground">{e.latencyMs}</td>
                      <td className="py-2 text-right text-muted-foreground whitespace-nowrap">{formatTime(e.ts)}</td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>

        {/* Right col */}
        <div className="space-y-4">
          {/* Active Policy card */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Scale size={14} className="text-primary" />
              <h2 className="font-semibold text-sm text-foreground">Active Policy</h2>
              <Badge variant="green" className="ml-auto">ACTIVE</Badge>
            </div>
            <p className="text-sm font-medium text-foreground mb-3">Bar Ethics Mode</p>
            <div className="space-y-2">
              {[
                { label: 'ABA Model Rules',    status: 'ENFORCED' },
                { label: 'Privilege Protection', status: 'ENFORCED' },
                { label: 'Conflict Screening', status: 'ENFORCED' },
                { label: 'Audit Chain',        status: 'VERIFIED' },
              ].map(item => (
                <div key={item.label} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="text-emerald-400 flex items-center gap-1"><CheckCircle2 size={10} /> {item.status}</span>
                </div>
              ))}
            </div>
          </div>

          {/* System Health card */}
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
                <span className="font-mono text-foreground">{p50}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latency p95</span>
                <span className="font-mono text-foreground">{p95}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latency p99</span>
                <span className="font-mono text-foreground">{p99}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Agents Online</span>
                <span className="text-primary font-semibold">500 / 500</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Second row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Block reasons */}
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={14} className="text-red-400" />
            <h2 className="font-semibold text-sm text-foreground">Top Block Reasons</h2>
          </div>
          <div className="space-y-3">
            {blockReasons.map((r, i) => (
              <div key={r.key}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">{r.label}</span>
                  <span className="text-foreground font-medium">{r.count}</span>
                </div>
                <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(r.count / maxBlockCount) * 100}%` }}
                    transition={{ delay: i * 0.05, duration: 0.6 }}
                    className="h-full rounded-full bg-red-400" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dept activity */}
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} className="text-emerald-400" />
            <h2 className="font-semibold text-sm text-foreground">Practice Area Activity</h2>
          </div>
          <div className="space-y-2.5">
            {deptActivity.map((d, i) => {
              const Icon = d.icon
              return (
                <div key={d.key} className="flex items-center gap-2">
                  <Icon size={12} className={d.color} />
                  <span className="text-muted-foreground text-xs w-28 shrink-0 truncate">{d.label}</span>
                  <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${(d.total / maxDeptTotal) * 100}%` }}
                      transition={{ delay: i * 0.04, duration: 0.5 }}
                      className="h-full rounded-full bg-emerald-400/60" />
                  </div>
                  <span className="text-xs text-red-400 w-10 text-right shrink-0">{d.blockPct}%</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Simulation Controls */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-muted-foreground text-xs font-medium">SIMULATION SPEED</span>
          {([0.5, 1, 2, 4] as const).map(s => (
            <Button key={s} variant={speed === s ? 'default' : 'outline'} size="sm" onClick={() => setSpeed(s)}>{s}×</Button>
          ))}
          <div className="w-px h-5 bg-white/10" />
          <Button variant="outline" size="sm" onClick={() => setPaused(!paused)}>{paused ? '▶ Resume' : '⏸ Pause'}</Button>
          <Button variant="ghost" size="sm" onClick={onReset}>↺ Reset</Button>
          <span className="ml-auto text-xs text-muted-foreground">{displayCount.toLocaleString()} / 1,000 events streamed</span>
        </div>
      </div>
    </div>
  )
}

// ─── Agents Tab ───────────────────────────────────────────────────────────────

function AgentsTab() {
  const [selectedDept, setSelectedDept] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 25

  const filtered = ALL_AGENTS.filter(a => {
    const matchDept   = selectedDept === 'all' || a.department === selectedDept
    const matchSearch = !search || a.id.toLowerCase().includes(search.toLowerCase()) || a.name.toLowerCase().includes(search.toLowerCase()) || a.deptLabel.toLowerCase().includes(search.toLowerCase())
    return matchDept && matchSearch
  })
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated  = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  useEffect(() => { setPage(0) }, [selectedDept, search])

  const statusConfig: Record<LawAgent['status'], { label: string; color: string; dot: string }> = {
    active: { label: 'Active', color: 'text-emerald-400', dot: 'bg-emerald-400' },
    idle:   { label: 'Idle',   color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
    alert:  { label: 'Alert',  color: 'text-red-400', dot: 'bg-red-400' },
  }
  const riskConfig: Record<LawAgent['riskLevel'], { label: string; variant: BadgeProps['variant'] }> = {
    low:    { label: 'Low',  variant: 'allow' },
    medium: { label: 'Med',  variant: 'amber' },
    high:   { label: 'High', variant: 'block' },
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Legal Agents</h1>
        <p className="text-muted-foreground text-sm mt-1">500 agents across 13 practice areas</p>
      </div>

      {/* Department filter pills */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setSelectedDept('all')}
          className={cn('inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
            selectedDept === 'all'
              ? 'bg-primary/20 text-primary border-primary/40'
              : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground')}>
          All · 500
        </button>
        {DEPARTMENTS.map(d => {
          const Icon = d.icon
          return (
            <button key={d.key} onClick={() => setSelectedDept(d.key)}
              className={cn('inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
                selectedDept === d.key
                  ? 'bg-primary/20 text-primary border-primary/40'
                  : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground')}>
              <Icon size={11} className={selectedDept === d.key ? 'text-primary' : d.color} />
              {d.label} · {d.count}
            </button>
          )
        })}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search agents..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10 text-muted-foreground">
                <th className="text-left px-4 py-3 font-medium">Agent ID</th>
                <th className="text-left px-4 py-3 font-medium hidden sm:table-cell">Practice Area</th>
                <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Office</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Decisions/24h</th>
                <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Blocked</th>
                <th className="text-left px-4 py-3 font-medium hidden xl:table-cell">Block Rate</th>
                <th className="text-left px-4 py-3 font-medium">Risk</th>
                <th className="text-right px-4 py-3 font-medium hidden md:table-cell">Last Active</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map(agent => {
                const s = statusConfig[agent.status]
                const r = riskConfig[agent.riskLevel]
                const dept = DEPARTMENTS.find(d => d.key === agent.department)
                const Icon = dept?.icon ?? Activity
                return (
                  <tr key={agent.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Icon size={13} className={dept?.color ?? 'text-muted-foreground'} />
                        <div>
                          <div className="font-mono text-foreground font-medium">{agent.id}</div>
                          <div className="text-muted-foreground/70">{agent.name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className="text-muted-foreground">{agent.deptLabel}</span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="font-mono text-muted-foreground">{agent.office}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse-dot', s.dot)} />
                        <span className={s.color}>{s.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                      <span className="font-mono text-foreground">{agent.decisions24h.toLocaleString()}</span>
                    </td>
                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                      <span className="font-mono text-red-400">{agent.blocked24h.toLocaleString()}</span>
                    </td>
                    <td className="px-4 py-3 hidden xl:table-cell">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-secondary rounded-full overflow-hidden">
                          <div className="h-full rounded-full bg-red-400/70" style={{ width: `${Math.min(agent.blockRate, 100)}%` }} />
                        </div>
                        <span className="text-muted-foreground">{agent.blockRate.toFixed(1)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3"><Badge variant={r.variant}>{r.label}</Badge></td>
                    <td className="px-4 py-3 text-right hidden md:table-cell">
                      <span className="text-muted-foreground">{agent.lastActiveMin === 0 ? 'just now' : `${agent.lastActiveMin}m ago`}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-t border-white/5">
          <span className="text-xs text-muted-foreground">Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}</span>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}><ChevronLeft size={14} /></Button>
            <span className="text-xs text-muted-foreground px-2">{page + 1} / {totalPages}</span>
            <Button variant="ghost" size="sm" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}><ChevronRight size={14} /></Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────

const SHARED_KEY = 'edon_law_demo_shared_audits'
const TEAM_MEMBERS = [
  { email: 'a.blackstone@bafirm.com',  name: 'A. Blackstone' },
  { email: 'm.chen@bafirm.com',        name: 'M. Chen' },
  { email: 'r.patel@bafirm.com',       name: 'R. Patel' },
  { email: 'compliance@bafirm.com',    name: 'Compliance' },
]

function loadShared(): SharedAuditRecord[] {
  try { const r = localStorage.getItem(SHARED_KEY); return r ? JSON.parse(r) : [] } catch { return [] }
}
function saveShared(items: SharedAuditRecord[]) { localStorage.setItem(SHARED_KEY, JSON.stringify(items)) }

function AuditTab() {
  const [verdictFilter, setVerdictFilter] = useState('all')
  const [agentFilter,   setAgentFilter]   = useState('')
  const [intentFilter,  setIntentFilter]  = useState('')
  const [policyFilter,  setPolicyFilter]  = useState('')
  const [startFilter,   setStartFilter]   = useState('')
  const [endFilter,     setEndFilter]     = useState('')
  const [filterTab,     setFilterTab]     = useState<'all' | 'shared'>('all')
  const [page,          setPage]          = useState(1)
  const PAGE_SIZE = 50

  const [sharedAudits, setSharedAudits] = useState<SharedAuditRecord[]>(() => loadShared())
  const [selected,     setSelected]     = useState<DemoEvent | null>(null)
  const [modalOpen,    setModalOpen]    = useState(false)
  const [shareRecord,  setShareRecord]  = useState<DemoEvent | null>(null)
  const [shareOpen,    setShareOpen]    = useState(false)
  const [shareEmails,  setShareEmails]  = useState<string[]>([])
  const [shareInput,   setShareInput]   = useState('')
  const [shareNote,    setShareNote]    = useState('')
  const [sharing,      setSharing]      = useState(false)

  const sharedIds = new Set(sharedAudits.map(s => s.recordId))

  const filtered = ALL_EVENTS.filter(e => {
    if (verdictFilter !== 'all' && e.verdict.toLowerCase() !== verdictFilter) return false
    if (agentFilter  && !e.agent.toLowerCase().includes(agentFilter.toLowerCase())) return false
    if (intentFilter && !e.intentId.toLowerCase().includes(intentFilter.toLowerCase())) return false
    if (policyFilter && !e.policyVersion.toLowerCase().includes(policyFilter.toLowerCase())) return false
    if (startFilter) { if (e.ts < new Date(startFilter)) return false }
    if (endFilter)   { const end = new Date(endFilter); end.setHours(23,59,59,999); if (e.ts > end) return false }
    return true
  })

  const displayed  = filterTab === 'shared' ? filtered.filter(e => sharedIds.has(e.id)) : filtered
  const paged      = displayed.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(displayed.length / PAGE_SIZE)

  const clearFilters = () => { setVerdictFilter('all'); setAgentFilter(''); setIntentFilter(''); setPolicyFilter(''); setStartFilter(''); setEndFilter(''); setPage(1) }
  const last5Min = () => {
    const now = new Date(); const ago = new Date(now.getTime() - 5*60*1000)
    setStartFilter(ago.toISOString().slice(0,16)); setEndFilter(now.toISOString().slice(0,16)); setPage(1)
  }

  const exportCSV = () => {
    const hdrs = ['ID','Timestamp','Verdict','Tool.Op','Agent ID','Department','Matter ID','Reason','Intent ID','Policy Version','Latency ms','Risk Score']
    const rows = displayed.map(e => [e.id, e.ts.toISOString(), e.verdict, e.toolOp, e.agent, e.deptLabel, e.matterId, e.reasonCode ?? '', e.intentId, e.policyVersion, e.latencyMs, e.riskScore])
    const csv = [hdrs, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n')
    Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type:'text/csv' })), download: `ba-audit-${new Date().toISOString().split('T')[0]}.csv` }).click()
  }
  const exportJSON = () => {
    Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([JSON.stringify(displayed, null, 2)], { type:'application/json' })), download: `ba-audit-${new Date().toISOString().split('T')[0]}.json` }).click()
  }

  const addEmail = (email: string) => {
    const t = email.trim(); if (!t || shareEmails.includes(t)) return
    setShareEmails(prev => [...prev, t]); setShareInput('')
  }
  const doShare = async () => {
    if (!shareRecord || shareEmails.length === 0) return
    setSharing(true)
    await new Promise(r => setTimeout(r, 400))
    const obj: SharedAuditRecord = {
      id: `share_${Date.now()}`, recordId: shareRecord.id,
      summary: { toolOp: shareRecord.toolOp, verdict: shareRecord.verdict, ts: shareRecord.ts.toISOString() },
      sharedBy: 'a.blackstone@bafirm.com', sharedWith: shareEmails, note: shareNote.trim(), sharedAt: new Date().toISOString(),
    }
    const next = [obj, ...sharedAudits]; saveShared(next); setSharedAudits(next)
    setSharing(false); setShareOpen(false); setShareEmails([]); setShareNote('')
  }

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }} className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Audit Log</h1>
          <p className="text-muted-foreground text-sm mt-1">Complete ABA-compliant audit trail · {ALL_EVENTS.length.toLocaleString()} records · SHA-256 hash chain</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="green"><CheckCircle2 size={10} /> Chain Verified</Badge>
          <Button variant="outline" size="sm" onClick={exportCSV}><FileSpreadsheet size={13} /> Export CSV</Button>
          <Button variant="outline" size="sm" onClick={exportJSON}><FileJson size={13} /> Export JSON</Button>
          <Button variant="outline" size="sm" onClick={() => setPage(1)}><RefreshCcw size={13} /> Refresh</Button>
        </div>
      </motion.div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 w-fit">
        {(['all', 'shared'] as const).map(t => (
          <button key={t} onClick={() => { setFilterTab(t); setPage(1) }}
            className={cn('text-xs px-3 py-1.5 rounded-lg transition-colors', filterTab === t ? 'bg-white/10 text-foreground font-medium' : 'text-muted-foreground hover:text-foreground')}>
            {t === 'all' ? `All records (${ALL_EVENTS.length.toLocaleString()})` : `Shared (${sharedIds.size})`}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3">
            <select value={verdictFilter} onChange={e => { setVerdictFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50">
              <option value="all">All Verdicts</option>
              <option value="allow">ALLOW</option>
              <option value="block">BLOCK</option>
              <option value="escalate">ESCALATE</option>
            </select>
            <input value={agentFilter} onChange={e => { setAgentFilter(e.target.value); setPage(1) }} placeholder="Agent ID…"
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[160px]" />
          </div>
          <div className="flex flex-wrap gap-3">
            <input value={intentFilter} onChange={e => { setIntentFilter(e.target.value); setPage(1) }} placeholder="Intent ID (e.g. int_a1b2c3d4)…"
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[220px]" />
            <input value={policyFilter} onChange={e => { setPolicyFilter(e.target.value); setPage(1) }} placeholder="Policy version (e.g. bar-ethics)…"
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[220px]" />
            <input type="datetime-local" value={startFilter} onChange={e => { setStartFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50" />
            <input type="datetime-local" value={endFilter} onChange={e => { setEndFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50" />
            <Button size="sm" onClick={last5Min} variant="outline">Last 5 Min</Button>
            <Button size="sm" onClick={clearFilters} variant="outline">Clear</Button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10 text-muted-foreground">
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Timestamp</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Verdict</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Tool Operation</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Agent ID</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden md:table-cell">Reason</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden lg:table-cell">Intent ID</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden xl:table-cell">Policy Version</th>
                <th className="text-right px-4 py-3 font-semibold uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paged.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-muted-foreground">
                  {filterTab === 'shared' ? 'No shared records yet. Share records using the Share button.' : 'No records match the selected filters.'}
                </td></tr>
              ) : paged.map((e, i) => {
                const isShared = sharedIds.has(e.id)
                return (
                  <tr key={e.id} className={cn('border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors', i === 0 && page === 1 ? 'animate-slideIn' : '')}>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground whitespace-nowrap">{e.ts.toLocaleString()}</td>
                    <td className="px-4 py-2.5"><VerdictBadge verdict={e.verdict} /></td>
                    <td className="px-4 py-2.5 font-mono text-foreground/80">{e.toolOp}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <DeptIcon deptKey={e.department} size={11} />
                        <span className="font-mono text-muted-foreground">{e.agent}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell">
                      {e.reasonCode ? <span className="text-amber-400 font-medium">{e.reasonCode}</span> : <span className="text-muted-foreground/30">—</span>}
                    </td>
                    <td className="px-4 py-2.5 hidden lg:table-cell">
                      <span className="font-mono text-sky-400/70 text-[11px] truncate max-w-[160px] block" title={e.intentId}>{e.intentId}</span>
                    </td>
                    <td className="px-4 py-2.5 hidden xl:table-cell">
                      <span className="font-mono text-muted-foreground/60 text-[11px]">{e.policyVersion}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {isShared && <Badge variant="outline" className="text-[10px] border-primary/30 text-primary bg-primary/10 mr-1">Shared</Badge>}
                        <button onClick={() => { setShareRecord(e); setShareEmails([]); setShareInput(''); setShareNote(''); setShareOpen(true) }}
                          className="p-1.5 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors" title="Share">
                          <Share2 size={13} />
                        </button>
                        <button onClick={() => { setSelected(e); setModalOpen(true) }}
                          className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors text-xs">
                          <Eye size={13} /> View
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {displayed.length > 0 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Showing {((page-1)*PAGE_SIZE+1).toLocaleString()}–{Math.min(page*PAGE_SIZE, displayed.length).toLocaleString()} of {displayed.length.toLocaleString()}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}><ChevronLeft size={13} /> Prev</Button>
            <span className="px-1">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p+1))} disabled={page >= totalPages}>Next <ChevronRight size={13} /></Button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {modalOpen && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setModalOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <motion.div initial={{ opacity:0, scale:0.96, y:8 }} animate={{ opacity:1, scale:1, y:0 }}
            onClick={e => e.stopPropagation()} className="relative glass-card w-full max-w-2xl p-6 z-10">
            <button onClick={() => setModalOpen(false)} className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"><X size={16} /></button>
            <div className="flex items-center gap-3 mb-5">
              <span className="font-mono text-base font-semibold text-foreground">{selected.toolOp}</span>
              <VerdictBadge verdict={selected.verdict} />
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm mb-4">
              {[
                { label: 'Timestamp',      value: selected.ts.toLocaleString() },
                { label: 'Agent ID',       value: selected.agent },
                { label: 'Matter ID',      value: selected.matterId },
                { label: 'Department',     value: selected.deptLabel },
                { label: 'Intent ID',      value: selected.intentId },
                { label: 'Policy Version', value: selected.policyVersion },
                { label: 'Reason Code',    value: selected.reasonCode ?? '—' },
                { label: 'Latency',        value: `${selected.latencyMs}ms` },
                { label: 'Risk Score',     value: String(selected.riskScore) },
              ].map(({ label, value }) => (
                <div key={label} className="bg-secondary/30 rounded-xl px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
                  <p className="font-mono text-xs text-foreground/90 break-all">{value}</p>
                </div>
              ))}
            </div>
            <div className="mb-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Decision Explanation</p>
              <p className="text-sm bg-secondary/30 rounded-xl px-3 py-2 text-foreground/80 leading-relaxed">{selected.explanation}</p>
            </div>
            <div className="mb-5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Chain Hash</p>
              <div className="flex items-center gap-2 bg-secondary/30 rounded-xl px-3 py-2">
                <Hash size={12} className="text-muted-foreground/50 shrink-0" />
                <span className="font-mono text-xs text-muted-foreground/70 break-all">{selected.hash}</span>
              </div>
            </div>
            <div className="mb-5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Request Payload</p>
              <pre className="p-3 bg-secondary/50 rounded-xl text-xs font-mono text-foreground/70 overflow-x-auto whitespace-pre-wrap break-all">
{JSON.stringify({ agent_id: selected.agent, intent_id: selected.intentId, tool: { op: selected.toolOp }, matter_id: selected.matterId, policy_version: selected.policyVersion, timestamp: selected.ts.toISOString() }, null, 2)}
              </pre>
            </div>
            <Button variant="outline" size="sm" onClick={() => { setModalOpen(false); setShareRecord(selected); setShareEmails([]); setShareInput(''); setShareNote(''); setShareOpen(true) }}>
              <Share2 size={13} /> Share this record
            </Button>
          </motion.div>
        </div>
      )}

      {/* Share Modal */}
      {shareOpen && shareRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShareOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <motion.div initial={{ opacity:0, scale:0.96, y:8 }} animate={{ opacity:1, scale:1, y:0 }}
            onClick={e => e.stopPropagation()} className="relative glass-card w-full max-w-md p-6 z-10">
            <button onClick={() => setShareOpen(false)} className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"><X size={16} /></button>
            <div className="flex items-center gap-2 mb-5">
              <Share2 size={16} className="text-primary" />
              <h3 className="text-base font-semibold">Share Audit Record</h3>
            </div>
            <div className="rounded-xl border border-white/10 bg-secondary/30 px-3 py-2.5 flex items-center gap-3 text-xs mb-4">
              <VerdictBadge verdict={shareRecord.verdict} />
              <span className="font-mono text-foreground/80 truncate">{shareRecord.toolOp}</span>
              <span className="text-muted-foreground ml-auto shrink-0">{shareRecord.ts.toLocaleString()}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-2">Share with</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {TEAM_MEMBERS.map(m => (
                <button key={m.email} onClick={() => addEmail(m.email)} disabled={shareEmails.includes(m.email)}
                  className={cn('text-xs px-2.5 py-1 rounded-lg border transition-colors',
                    shareEmails.includes(m.email) ? 'border-primary/30 bg-primary/10 text-primary cursor-default' : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground hover:border-white/20')}>
                  {m.name}
                </button>
              ))}
            </div>
            <div className="flex gap-2 mb-3">
              <input value={shareInput} onChange={e => setShareInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addEmail(shareInput) } }}
                placeholder="Add email address…"
                className="flex-1 h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50" />
              <Button size="sm" variant="outline" onClick={() => addEmail(shareInput)} disabled={!shareInput.trim()}>Add</Button>
            </div>
            {shareEmails.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {shareEmails.map(email => (
                  <span key={email} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-white/20 bg-white/5 text-foreground/80">
                    {email}
                    <button onClick={() => setShareEmails(prev => prev.filter(e => e !== email))} className="ml-0.5 text-muted-foreground hover:text-foreground">×</button>
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground mb-1">Note (optional)</p>
            <textarea value={shareNote} onChange={e => setShareNote(e.target.value.slice(0,200))}
              placeholder="Add context for your team…" maxLength={200} rows={3}
              className="w-full rounded-xl border border-white/15 bg-secondary/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none mb-1" />
            <p className="text-[10px] text-muted-foreground/50 text-right mb-4">{shareNote.length}/200</p>
            <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground mb-4">
              <span className="w-2.5 h-2.5 rounded-full border-2 border-primary bg-primary/30 shrink-0" />
              Team members only · Privileged &amp; confidential · ABA Model Rule 1.6
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={doShare} disabled={sharing || shareEmails.length === 0} className="flex-1">
                {sharing ? <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sharing…</> : <><Share2 size={14} /> Share</>}
              </Button>
              <Button variant="outline" onClick={() => setShareOpen(false)}>Cancel</Button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}

// ─── Policies Tab ─────────────────────────────────────────────────────────────

const ALLOWED_OPERATIONS = [
  'contract.review.clause', 'case.search.precedent', 'document.redact.pii',
  'matter.status.update', 'billing.time.record', 'court.filing.check',
  'conflict.check.run', 'deposition.draft.prepare', 'settlement.analyze',
  'discovery.docs.process', 'client.comm.log', 'deadline.calendar.check',
]
const BLOCKED_OPERATIONS = [
  'privilege.breach.attempt', 'unauthorized.case.access', 'client.data.bulk.export',
  'billing.rate.override', 'settlement.unauthorized.accept', 'filing.deadline.extend',
  'conflict.check.bypass', 'matter.reassign.unauthorized', 'court.doc.alter',
]
const PARTNER_CONFIRM = [
  'settlement.approve.major', 'conflict.waiver.authorize', 'privilege.waiver.sign',
  'court.consent.order.file', 'client.terminate.represent', 'ethics.complaint.respond',
]

interface PolicyPack {
  name: string; description: string; standard: string
  status: 'active' | 'inactive' | 'emergency'; agents: number; lastUpdated: string
}
const POLICY_PACKS: PolicyPack[] = [
  { name: 'Bar Ethics Mode',            description: 'Default mode enforcing ABA Model Rules, attorney-client privilege, and conflict-of-interest screening.',         standard: 'ABA Model Rules',          status: 'active',   agents: 500, lastUpdated: '2026-03-15' },
  { name: 'AML Strict Mode',            description: 'Enhanced anti-money laundering controls for high-risk clients. Requires EDD and beneficial ownership checks.',    standard: 'FATF · FinCEN',            status: 'inactive', agents: 0,   lastUpdated: '2026-02-28' },
  { name: 'Litigation Hold Mode',       description: 'Locks all documents and communications related to active litigation. Prevents deletions and unauthorized exports.',standard: 'FRCP Rule 37',             status: 'inactive', agents: 0,   lastUpdated: '2026-03-01' },
  { name: 'GDPR Data Privacy Mode',     description: 'Governs EU personal data in client matters. Enforces consent logging, data minimization, and breach notifications.', standard: 'GDPR · CCPA',           status: 'inactive', agents: 0,   lastUpdated: '2026-03-10' },
  { name: 'Model Rules Strictest Mode', description: 'Applies the most conservative interpretation of all Model Rules. Recommended for regulated-industry matters.',    standard: 'ABA Model Rules v3.2.1',   status: 'inactive', agents: 0,   lastUpdated: '2026-03-12' },
  { name: 'Lockdown Mode',              description: 'Maximum restriction. All non-critical agent operations suspended pending manual review.',                         standard: 'EMERGENCY PROTOCOL',       status: 'emergency',agents: 0,   lastUpdated: '2026-01-01' },
]

function PoliciesTab() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Policy Packs</h1>
        <p className="text-muted-foreground text-sm mt-1">Legal compliance governance · Blackstone &amp; Associates LLP</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card p-4 border-emerald-500/20">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={14} className="text-emerald-400" />
            <h3 className="font-semibold text-sm text-emerald-400">Allowed Operations</h3>
            <span className="ml-auto text-xs text-muted-foreground">{ALLOWED_OPERATIONS.length}</span>
          </div>
          <div className="space-y-1.5">
            {ALLOWED_OPERATIONS.map(op => (
              <div key={op} className="flex items-center gap-2 text-xs">
                <span className="w-1 h-1 rounded-full bg-emerald-400/60 shrink-0" />
                <span className="font-mono text-muted-foreground">{op}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card p-4 border-red-500/20">
          <div className="flex items-center gap-2 mb-3">
            <XCircle size={14} className="text-red-400" />
            <h3 className="font-semibold text-sm text-red-400">Blocked Operations</h3>
            <span className="ml-auto text-xs text-muted-foreground">{BLOCKED_OPERATIONS.length}</span>
          </div>
          <div className="space-y-1.5">
            {BLOCKED_OPERATIONS.map(op => (
              <div key={op} className="flex items-center gap-2 text-xs">
                <span className="w-1 h-1 rounded-full bg-red-400/60 shrink-0" />
                <span className="font-mono text-muted-foreground">{op}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card p-4 border-amber-500/20">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-amber-400" />
            <h3 className="font-semibold text-sm text-amber-400">Partner Approval Required</h3>
            <span className="ml-auto text-xs text-muted-foreground">{PARTNER_CONFIRM.length}</span>
          </div>
          <div className="space-y-1.5">
            {PARTNER_CONFIRM.map(op => (
              <div key={op} className="flex items-center gap-2 text-xs">
                <span className="w-1 h-1 rounded-full bg-amber-400/60 shrink-0" />
                <span className="font-mono text-muted-foreground">{op}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-3">Policy Packs</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {POLICY_PACKS.map((pack, i) => {
            const isActive    = pack.status === 'active'
            const isEmergency = pack.status === 'emergency'
            return (
              <motion.div key={pack.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                className={cn('glass-card-hover p-5', isActive && 'border-primary/30', isEmergency && 'border-red-500/30')}>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <h3 className="font-semibold text-sm text-foreground leading-tight">{pack.name}</h3>
                  {isActive    && <Badge variant="green">ACTIVE</Badge>}
                  {isEmergency && <Badge variant="red">EMERGENCY</Badge>}
                  {!isActive && !isEmergency && <Badge variant="default">INACTIVE</Badge>}
                </div>
                <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{pack.description}</p>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground/70 font-mono">{pack.standard}</span>
                  <span className="text-muted-foreground">{pack.agents > 0 ? <span className="text-primary">{pack.agents} agents</span> : 'Inactive'}</span>
                </div>
                <div className="mt-3 pt-3 border-t border-white/5 text-xs text-muted-foreground/50">Updated {pack.lastUpdated}</div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── AI Chat Panel ────────────────────────────────────────────────────────────

const _ALLOW_COUNT  = ALL_EVENTS.filter(e => e.verdict === 'ALLOW').length
const _BLOCK_COUNT  = ALL_EVENTS.filter(e => e.verdict === 'BLOCK').length
const _ESC_COUNT    = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE').length
const _BLOCK_RATE   = Math.round((_BLOCK_COUNT / ALL_EVENTS.length) * 100)
const _HIGH_RISK    = ALL_AGENTS.filter(a => a.riskLevel === 'high').length
const _MED_RISK     = ALL_AGENTS.filter(a => a.riskLevel === 'medium').length
const _ACTIVE_CNT   = ALL_AGENTS.filter(a => a.status === 'active').length
const _ALERT_AGENTS = ALL_AGENTS.filter(a => a.status === 'alert').length

const _DEPT_BLOCKS: Record<string, number> = {}
for (const e of ALL_EVENTS) { if (e.verdict === 'BLOCK') _DEPT_BLOCKS[e.department] = (_DEPT_BLOCKS[e.department] ?? 0) + 1 }
const _TOP_DEPT       = Object.entries(_DEPT_BLOCKS).sort((a, b) => b[1] - a[1])[0]
const _TOP_DEPT_LABEL = DEPARTMENTS.find(d => d.key === _TOP_DEPT?.[0])?.label ?? _TOP_DEPT?.[0]
const _PRIV_COUNT     = ALL_EVENTS.filter(e => e.reasonCode === 'PRIVILEGE_VIOLATION').length
const _CONFLICT_COUNT = ALL_EVENTS.filter(e => e.reasonCode === 'CONFLICT_OF_INTEREST').length
const _AML_COUNT      = ALL_EVENTS.filter(e => e.reasonCode === 'AML_COMPLIANCE').length

const _AGENT_BLOCKS: Record<string, number> = {}
for (const e of ALL_EVENTS) { if (e.verdict === 'BLOCK') _AGENT_BLOCKS[e.agent] = (_AGENT_BLOCKS[e.agent] ?? 0) + 1 }
const _TOP_BLOCKED_AGENT = Object.entries(_AGENT_BLOCKS).sort((a, b) => b[1] - a[1])[0]

const SUGGESTED_QUESTIONS = [
  'What is the current block rate?',
  'Which practice area has the most violations?',
  'How many privilege violations today?',
  'Show me high-risk agents',
  'Any escalated matters needing review?',
  'What are the top blocked operations?',
  'How is the system performing?',
  'Which agents are on alert?',
]

interface ChatMessage { id: string; role: 'user' | 'assistant'; content: string; ts: Date }

function getMockResponse(question: string): string {
  const q = question.toLowerCase()
  if (q.includes('block rate') || (q.includes('block') && q.includes('rate'))) {
    return `The current block rate across all 500 agents is **${_BLOCK_RATE}%**. Out of ${ALL_EVENTS.length.toLocaleString()} governed actions, **${_BLOCK_COUNT}** were blocked and **${_ALLOW_COUNT}** were allowed. The most common block reason is Privilege Violation (${_PRIV_COUNT} incidents), followed by Conflict of Interest (${_CONFLICT_COUNT} incidents).`
  }
  if (q.includes('practice area') || q.includes('department') || q.includes('most violation')) {
    return `**${_TOP_DEPT_LABEL}** has the highest violation count with **${_TOP_DEPT?.[1]}** blocked actions. Top practice areas by blocks:\n\n${Object.entries(_DEPT_BLOCKS).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([k,v])=>`• ${DEPARTMENTS.find(d=>d.key===k)?.label??k}: ${v} blocks`).join('\n')}\n\nConsider reviewing policy thresholds for ${_TOP_DEPT_LABEL}.`
  }
  if (q.includes('privilege')) {
    return `There have been **${_PRIV_COUNT} Privilege Violations** flagged in the current audit window — all automatically blocked by the Privilege Protection policy pack. Additionally, **${_CONFLICT_COUNT}** Conflict of Interest incidents and **${_AML_COUNT}** AML Compliance flags were intercepted. All records are in the audit trail with full hash-chain verification.`
  }
  if (q.includes('high risk') || (q.includes('risk') && q.includes('agent'))) {
    return `There are currently **${_HIGH_RISK} high-risk agents** and **${_MED_RISK} medium-risk agents** in the system. High-risk agents have block rates exceeding 20% or have triggered repeated anomaly patterns. The top blocked agent is **${_TOP_BLOCKED_AGENT?.[0]}** with **${_TOP_BLOCKED_AGENT?.[1]} blocks**. Navigate to the Agents tab and filter by Risk: High to see the full list.`
  }
  if (q.includes('escalat') || q.includes('partner')) {
    return `**${_ESC_COUNT} actions** have been escalated to partner review in this session. Escalated operations include: settlement.approve.major, conflict.waiver.authorize, and privilege.waiver.sign — all requiring partner confirmation before execution. These are pending in the human review queue. No escalations have exceeded the 5-minute SLA timeout.`
  }
  if (q.includes('top blocked') || q.includes('blocked operation')) {
    return `The top blocked operations are:\n\n• **privilege.breach.attempt** — highest frequency (privilege protection enforcement)\n• **unauthorized.case.access** — blocked by access control policy\n• **client.data.bulk.export** — blocked to prevent data exfiltration\n• **billing.rate.override** — requires partner authorization\n• **conflict.check.bypass** — zero-tolerance enforcement\n\nAll blocks are logged with full intent tracing and chain-hash verification.`
  }
  if (q.includes('perform') || q.includes('latency') || q.includes('uptime') || q.includes('system')) {
    return `System performance is nominal:\n\n• **Latency:** p50 ~2.9ms · p95 ~8.6ms · p99 ~13.4ms — well within the 50ms SLO\n• **Uptime:** 99.97% current session\n• **Throughput:** ~${(ALL_EVENTS.length/60).toFixed(0)} decisions/second sustained\n• **Chain Integrity:** SHA-256 hash chain fully verified — no tampering detected\n• **Agents Online:** ${_ACTIVE_CNT}/500 active right now`
  }
  if (q.includes('alert') || (q.includes('agent') && q.includes('problem'))) {
    const alertAgents = ALL_AGENTS.filter(a=>a.status==='alert').slice(0,5)
    return `**${_ALERT_AGENTS} agents** are currently in alert status:\n\n${alertAgents.map(a=>`• **${a.id}** (${a.deptLabel}) — block rate ${a.blockRate}%`).join('\n')}\n\nAlert status triggers when an agent exceeds a block threshold in a 10-minute rolling window. These agents are still operational but under heightened monitoring.`
  }
  if (q.includes('litigation')) {
    const litAgents = ALL_AGENTS.filter(a=>a.department==='litigation')
    const litBlocks = ALL_EVENTS.filter(e=>e.department==='litigation'&&e.verdict==='BLOCK').length
    return `**Litigation** has **${litAgents.length} agents** deployed across Floors 11 and 12. In this session: **${litBlocks}** actions were blocked. Litigation agents primarily handle case.search.precedent, deposition.draft.prepare, and court.filing.check operations — all currently allowed under Bar Ethics Mode.`
  }
  if (q.includes('how many agent') || q.includes('total agent') || q.includes('count')) {
    return `There are **500 agents** deployed across **13 practice areas** at Blackstone & Associates LLP:\n\n${DEPARTMENTS.map(d=>`• ${d.label}: ${d.count} agents`).join('\n')}\n\nCurrently **${_ACTIVE_CNT} are active**, ${ALL_AGENTS.filter(a=>a.status==='idle').length} idle, and ${_ALERT_AGENTS} in alert status.`
  }
  if (q.includes('audit') || q.includes('chain') || q.includes('hash')) {
    return `The audit trail contains **${ALL_EVENTS.length.toLocaleString()} records** in this session. The SHA-256 hash chain is intact — each event references the previous event's hash, forming a tamper-evident ledger. Chain verification passed ✅. Export the full log as CSV or JSON from the Audit tab. All records include: Agent ID, Intent ID, Policy Version, Matter ID, Latency, Risk Score, and full decision explanation.`
  }
  if (q.includes('policy') || q.includes('compliance') || q.includes('rule')) {
    return `**Bar Ethics Mode** is the active policy pack (500/500 agents enrolled). It enforces:\n\n• ABA Model Rules of Professional Conduct\n• Attorney-client privilege protection\n• Conflict of interest screening\n• AML/FATF compliance controls\n• Partner confirmation for high-risk operations\n\nOther available packs (inactive): AML Strict Mode, Litigation Hold Mode, GDPR Data Privacy Mode, Model Rules Strictest Mode.`
  }
  if (q.includes('hello') || q.includes('hi') || q.includes('hey') || q.includes('help')) {
    return `Hello! I'm the **EDON AI Assistant** for Blackstone & Associates LLP. I have full visibility into all **500 agents** and **${ALL_EVENTS.length.toLocaleString()} governance events**.\n\nYou can ask me about:\n• Block rates and violation trends\n• Specific practice areas or agents\n• Privilege and ethics compliance\n• System performance and uptime\n• Escalated matters needing review\n• Policy pack configurations\n\nWhat would you like to know?`
  }
  if (q.includes('trend') || q.includes('pattern')) {
    return `Based on the current session data, I can see a few notable patterns:\n\n• **Privilege violations** concentrated in Document Review and Corporate agents\n• **Conflict of interest** flags rising in Litigation department\n• **Escalation rate** holding at ${Math.round((_ESC_COUNT/ALL_EVENTS.length)*100)}% — within normal operating bounds\n• **Latency** stable at under 10ms p99 for the entire session\n\nNo anomalous patterns requiring immediate intervention detected.`
  }
  return `I searched across ${ALL_EVENTS.length.toLocaleString()} governance events and ${ALL_AGENTS.length} agent records for **"${question}"**.\n\nHere's what I found: the system is processing ~${Math.round(ALL_EVENTS.length/60)} decisions/second with a ${_BLOCK_RATE}% block rate. The top concern is **${_TOP_DEPT_LABEL}** (${_TOP_DEPT?.[1]} violations). All ${_ACTIVE_CNT} active agents are operating within policy bounds.\n\nCould you clarify what you're looking for?`
}

interface AIChatPanelProps { open: boolean; onClose: () => void }

function AIChatPanel({ open, onClose }: AIChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: 'welcome', role: 'assistant', ts: new Date(),
    content: `Hi! I'm your **EDON AI Assistant**. I have live insight into all **500 agents** and **${ALL_EVENTS.length.toLocaleString()} governance events** at Blackstone & Associates LLP.\n\nAsk me anything about your data.`,
  }])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 300) }, [open])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  const send = async (text: string) => {
    const q = text.trim(); if (!q) return
    setInput('')
    setMessages(prev => [...prev, { id: `u${Date.now()}`, role: 'user', content: q, ts: new Date() }])
    setTyping(true)
    await new Promise(r => setTimeout(r, 600 + Math.random() * 600))
    setTyping(false)
    setMessages(prev => [...prev, { id: `a${Date.now()}`, role: 'assistant', content: getMockResponse(q), ts: new Date() }])
  }

  function renderContent(text: string) {
    return text.split('\n').map((line, i) => {
      const parts = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**')) return <strong key={j} className="text-foreground font-semibold">{part.slice(2,-2)}</strong>
        return part
      })
      return <span key={i} className={cn('block', line.trimStart().startsWith('•') ? 'pl-2' : '', i > 0 ? 'mt-1' : '')}>{parts}</span>
    })
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div key="chat-backdrop" initial={{ opacity:0 }} animate={{ opacity:1 }} exit={{ opacity:0 }}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden" onClick={onClose} />
          <motion.div key="chat-panel" initial={{ x:'100%', opacity:0 }} animate={{ x:0, opacity:1 }} exit={{ x:'100%', opacity:0 }}
            transition={{ type:'spring', stiffness:300, damping:32 }}
            className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-sm flex flex-col"
            style={{ background:'hsl(220 14% 9%)', borderLeft:'1px solid rgba(255,255,255,0.1)', boxShadow:'-8px 0 40px rgba(0,0,0,0.5)' }}>
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/10 shrink-0">
              <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                <Sparkles size={15} className="text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground leading-tight">EDON AI Assistant</p>
                <p className="text-[10px] text-muted-foreground">Blackstone & Assoc. · 500 agents · live data</p>
              </div>
              <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/8 transition-colors shrink-0"><X size={16} /></button>
            </div>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
              <AnimatePresence initial={false}>
                {messages.map(msg => (
                  <motion.div key={msg.id} initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.22 }}
                    className={cn('flex gap-2.5', msg.role==='user' ? 'flex-row-reverse' : 'flex-row')}>
                    <div className={cn('w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5',
                      msg.role==='assistant' ? 'bg-primary/15 border border-primary/30' : 'bg-white/10 border border-white/20')}>
                      {msg.role==='assistant' ? <Bot size={12} className="text-primary" /> : <User size={12} className="text-foreground" />}
                    </div>
                    <div className={cn('max-w-[85%] px-3 py-2.5 rounded-2xl text-xs leading-relaxed',
                      msg.role==='assistant' ? 'bg-white/5 border border-white/8 text-foreground/90 rounded-tl-sm' : 'bg-primary/20 border border-primary/30 text-foreground rounded-tr-sm')}>
                      {renderContent(msg.content)}
                      <p className="text-[9px] text-muted-foreground/50 mt-1.5">{msg.ts.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</p>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              {typing && (
                <motion.div initial={{ opacity:0 }} animate={{ opacity:1 }} className="flex gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                    <Bot size={12} className="text-primary" />
                  </div>
                  <div className="bg-white/5 border border-white/8 rounded-2xl rounded-tl-sm px-3 py-2.5 flex items-center gap-1">
                    {[0,0.15,0.3].map((delay,i) => <span key={i} className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-pulse-dot" style={{ animationDelay:`${delay}s` }} />)}
                  </div>
                </motion.div>
              )}
              <div ref={bottomRef} />
            </div>
            {/* Suggested */}
            {!typing && (
              <div className="px-4 pb-3 shrink-0">
                <p className="text-[10px] text-muted-foreground mb-2 font-medium uppercase tracking-wider">Suggested</p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTED_QUESTIONS.slice(0,4).map(q => (
                    <button key={q} onClick={() => send(q)}
                      className="text-[10px] px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-muted-foreground hover:text-foreground hover:bg-white/10 hover:border-white/20 transition-colors text-left">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {/* Input */}
            <div className="px-4 pb-4 pt-2 border-t border-white/10 shrink-0">
              <div className="flex gap-2 items-end">
                <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(input)} }}
                  placeholder="Ask about agents, violations, trends…"
                  className="flex-1 bg-secondary border border-white/10 rounded-xl px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all" />
                <button onClick={() => send(input)} disabled={!input.trim()||typing}
                  className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shrink-0 hover:bg-primary/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                  <Send size={14} className="text-primary-foreground" />
                </button>
              </div>
              <p className="text-[9px] text-muted-foreground/40 mt-1.5 text-center">Simulated AI · responses based on mock data</p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

// ─── Top Nav ──────────────────────────────────────────────────────────────────

const NAV_TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
  { id: 'agents',    label: 'Agents',    icon: Briefcase },
  { id: 'audit',     label: 'Audit',     icon: FileText },
  { id: 'policies',  label: 'Policies',  icon: Scale },
]

interface TopNavProps { activeTab: Tab; setActiveTab: (t: Tab) => void; onChatOpen: () => void }

function TopNav({ activeTab, setActiveTab, onChatOpen }: TopNavProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-background/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-4 h-14">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
              <Scale size={13} className="text-primary" />
            </div>
            <span className="edon-brand font-bold text-foreground text-sm tracking-widest">EDON</span>
            <span className="text-muted-foreground text-xs hidden sm:block">· Blackstone &amp; Associates LLP</span>
          </div>
          <nav className="flex items-center gap-1 bg-secondary/60 rounded-xl p-1 ml-2">
            {NAV_TABS.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={cn('relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200', isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                  {isActive && <motion.div layoutId="nav-indicator" className="absolute inset-0 bg-white/15 rounded-lg" transition={{ type:'spring', bounce:0.2, duration:0.35 }} />}
                  <span className="relative flex items-center gap-1.5"><Icon size={13} /><span className="hidden sm:inline">{tab.label}</span></span>
                </button>
              )
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Badge variant="green"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />Live</Badge>
            <Badge variant="default" className="hidden sm:inline-flex"><Shield size={10} className="text-primary" />Bar Ethics</Badge>
            <div className="flex items-center gap-1.5 bg-secondary rounded-xl px-2.5 py-1.5 border border-white/10">
              <User size={12} className="text-muted-foreground" />
              <span className="text-xs text-foreground font-medium hidden sm:block">A. Blackstone</span>
            </div>
            <button onClick={onChatOpen} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-primary/15 border border-primary/30 text-primary hover:bg-primary/25 transition-colors text-xs font-medium">
              <Sparkles size={12} /><span className="hidden sm:inline">Ask AI</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [activeTab,     setActiveTab]     = useState<Tab>('dashboard')
  const [displayCount,  setDisplayCount]  = useState(30)
  const [speed,         setSpeed]         = useState<number>(1)
  const [paused,        setPaused]        = useState(false)
  const [uptime,        setUptime]        = useState(183440)
  const [latency,       setLatency]       = useState(4.8)
  const [chatOpen,      setChatOpen]      = useState(false)

  const speedRef        = useRef(speed)
  const pausedRef       = useRef(paused)
  const displayCountRef = useRef(displayCount)
  speedRef.current        = speed
  pausedRef.current       = paused
  displayCountRef.current = displayCount

  useEffect(() => {
    const tick = () => { if (!pausedRef.current && displayCountRef.current < 1000) setDisplayCount(c => Math.min(c + 1, 1000)) }
    const id = setInterval(tick, 800 / speedRef.current)
    return () => clearInterval(id)
  }, [speed, paused])

  useEffect(() => { const id = setInterval(() => setUptime(u => u + 1), 1000); return () => clearInterval(id) }, [])

  useEffect(() => {
    const id = setInterval(() => setLatency(prev => Math.min(10.4, Math.max(2.1, prev + (Math.random()-0.5)*1.6))), 1800)
    return () => clearInterval(id)
  }, [])

  const handleReset = useCallback(() => { setDisplayCount(30); setPaused(false) }, [])

  return (
    <div className="min-h-screen bg-background">
      {/* Demo banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/20 text-center py-1.5">
        <span className="text-amber-400 text-xs font-semibold tracking-widest">⚠ DEMO MODE</span>
        <span className="text-amber-400/70 text-xs ml-2">— Simulated data only · Not connected to live systems</span>
      </div>

      <TopNav activeTab={activeTab} setActiveTab={setActiveTab} onChatOpen={() => setChatOpen(true)} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <AnimatePresence mode="wait">
          {activeTab === 'dashboard' && (
            <motion.div key="dashboard" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }} transition={{ duration:0.25 }}>
              <DashboardTab displayCount={displayCount} speed={speed} setSpeed={setSpeed} paused={paused} setPaused={setPaused} onReset={handleReset} uptime={uptime} latency={latency} />
            </motion.div>
          )}
          {activeTab === 'agents' && (
            <motion.div key="agents" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }} transition={{ duration:0.25 }}>
              <AgentsTab />
            </motion.div>
          )}
          {activeTab === 'audit' && (
            <motion.div key="audit" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }} transition={{ duration:0.25 }}>
              <AuditTab />
            </motion.div>
          )}
          {activeTab === 'policies' && (
            <motion.div key="policies" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }} transition={{ duration:0.25 }}>
              <PoliciesTab />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Floating chat button */}
      <AnimatePresence>
        {!chatOpen && (
          <motion.button key="chat-fab" initial={{ scale:0, opacity:0 }} animate={{ scale:1, opacity:1 }} exit={{ scale:0, opacity:0 }}
            whileHover={{ scale:1.08 }} whileTap={{ scale:0.95 }}
            onClick={() => setChatOpen(true)}
            className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-2xl bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 transition-colors"
            style={{ boxShadow:'0 4px 24px rgba(100,220,120,0.35)' }}>
            <MessageSquare size={16} />
            <span className="text-sm font-semibold">Ask AI</span>
            <span className="w-2 h-2 rounded-full bg-primary-foreground/60 animate-pulse-dot" />
          </motion.button>
        )}
      </AnimatePresence>

      <AIChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  )
}
