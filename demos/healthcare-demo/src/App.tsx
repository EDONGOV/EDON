import { useState, useEffect, useRef, useCallback, createContext, useContext, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  Heart,
  Scan,
  Cross,
  AlertCircle,
  Pill,
  Microscope,
  Activity,
  FileText,
  Stethoscope,
  Brain,
  Clock,
  Wifi,
  Shield,
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
  Share2,
  Eye,
  EyeOff,
  FileJson,
  FileSpreadsheet,
  RefreshCcw,
  X,
  MessageSquare,
  Send,
  Sparkles,
  Bot,
  Plus,
  ClipboardList,
  ThumbsUp,
  ThumbsDown,
  LayoutList,
  LayoutGrid,
  Link2,
  ArrowRight,
  Upload,
  Loader2,
  DollarSign,
  FileCode2,
  CheckCircle,
  LogOut,
  RefreshCw,
  Settings2,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type Verdict = 'ALLOW' | 'BLOCK' | 'ESCALATE'
type Tab = 'dashboard' | 'agents' | 'audit' | 'policies' | 'review' | 'import' | 'operations' | 'settings'

interface HospitalAgent {
  id: string
  name: string
  department: string
  deptLabel: string
  vendorId: string
  vendorName: string
  status: 'active' | 'idle' | 'alert'
  decisions24h: number
  blocked24h: number
  blockRate: number
  blockRatePrev: number           // block rate 24h ago — for trend
  blockRateTrend: 'stable' | 'rising' | 'spiked'
  lastAction: string
  lastActiveMin: number
  riskLevel: 'low' | 'medium' | 'high'
  floor: string
  serialNo: string
  patientLoad: number
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
  patientId: string
  intentId: string
  policyVersion: string
  explanation: string
  vendorId: string
  vendorName: string
  deviceId?: string
  deviceName?: string
  // Human review fields (only set for ESCALATE verdicts)
  clinicalContext?: string   // what the agent detected / why it's requesting this
  urgency?: 'routine' | 'urgent' | 'critical'
  reviewStatus?: 'pending' | 'approved' | 'denied'
  reviewedBy?: string
  reviewedByEmail?: string
  reviewedAt?: Date
  reviewReason?: string
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

// ─── Claude API config ───────────────────────────────────────────────────────
// NOTE: VITE_ANTHROPIC_API_KEY is embedded in the browser bundle.
// Safe for local demos — do not deploy publicly with a real key.

const _ANTHROPIC_KEY = (import.meta.env.VITE_ANTHROPIC_API_KEY as string | undefined) ?? ''
const _AI_ENABLED = _ANTHROPIC_KEY.length > 0

const _HC_SYSTEM = `You are an AI assistant embedded in a healthcare AI governance dashboard for St. Mercy Health System.
The hospital uses EDON to monitor and govern 500+ AI agents across clinical departments.

You have access to governance data: audit events, agent profiles, block rates, HIPAA violations, escalations, and department-level risk metrics.
Answer questions about this data for a clinical administrator or compliance officer.

CITATION FORMAT — when referencing a specific audit event, embed [ref:EVENT:id] inline.
When referencing a specific agent, embed [ref:AGENT:id] inline. Use real IDs from the page context.
Only cite items you directly reference — do not bulk-list citations.

LENGTH — this is critical:
- Simple status or factual questions: 2-3 sentences maximum.
- Analysis or "what should I do" questions: 4-5 sentences maximum. Never more.
- Explain something specific: 2-3 sentences.
- Do not pad, summarize, or repeat yourself to fill space.

RESPONSE STYLE — follow exactly:
- No asterisks. No bold. No markdown of any kind.
- No bullet points or numbered lists unless the user explicitly asks for a list.
- No headers or section titles.
- No emojis.
- Plain prose only. Short, direct sentences.
- Lead with the answer. Never open with "Sure", "Great", or any preamble.
- Never open with a disclaimer about what you can or cannot do. Just answer.
- If asked what actions you can take, answer with what is actionable from this dashboard — do not list limitations first.
- No closing filler.
- State numbers naturally in a sentence — never wrap or highlight them.`

const _CLAUDE_HEADERS = {
  'x-api-key': _ANTHROPIC_KEY,
  'anthropic-version': '2023-06-01',
  'anthropic-dangerous-direct-browser-access': 'true',
  'content-type': 'application/json',
}

// Non-streaming call used by the aside panel
async function _claudeAsk(
  question: string,
  conversation?: { role: string; content: string }[],
): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: _CLAUDE_HEADERS,
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 512,
      system: _HC_SYSTEM,
      messages: [...(conversation ?? []), { role: 'user', content: question }],
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`)
  }
  const data = await res.json()
  const block = (data.content as { type: string; text?: string }[]).find(b => b.type === 'text')
  return block?.text ?? '(no response)'
}

// Streaming call used by the chat panel — calls onChunk for each text delta, returns full text
async function _claudeStream(
  question: string,
  conversation: { role: string; content: string }[],
  onChunk: (delta: string) => void,
): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: _CLAUDE_HEADERS,
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 512,
      system: _HC_SYSTEM,
      stream: true,
      messages: [...conversation, { role: 'user', content: question }],
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { error?: { message?: string } }).error?.message ?? `HTTP ${res.status}`)
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let full = ''
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') continue
      try {
        const ev = JSON.parse(payload)
        if (ev.type === 'content_block_delta' && ev.delta?.type === 'text_delta') {
          const text: string = ev.delta.text
          full += text
          onChunk(text)
        }
      } catch { /* skip malformed SSE line */ }
    }
  }
  return full
}

// ─── Citation / Aside context ─────────────────────────────────────────────────

interface AsideItem { type: 'event' | 'agent'; id: string }
const AsideCtx = createContext<{ open: (item: AsideItem) => void }>({ open: () => {} })

const CITE_RE_HC = /\[ref:(EVENT|AGENT):([^\]]+)\]/g

const CITE_COLORS_HC: Record<string, string> = {
  event: 'bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30',
  agent: 'bg-blue-500/20 border-blue-500/40 text-blue-300 hover:bg-blue-500/30',
}

function uniqueCitationsHC(text: string) {
  const out: { type: 'event' | 'agent'; id: string }[] = []
  const seen = new Set<string>()
  CITE_RE_HC.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = CITE_RE_HC.exec(text)) !== null) {
    const type = m[1].toLowerCase() as 'event' | 'agent'
    const id = m[2]
    const key = `${type}:${id}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ type, id })
  }
  return out
}

function getSuggestionHC(type: 'event' | 'agent', id: string) {
  if (type === 'agent') {
    const a = ALL_AGENTS.find(ag => ag.id === id)
    if (!a) {
      return {
        title: 'Review the agent scope',
        body: 'Confirm the agent identity, department, and allowed actions before widening access.',
      }
    }
    if (a.riskLevel === 'high') {
      return {
        title: 'Inspect the agent scope',
        body: `This agent is high risk and should stay tightly bounded to ${a.deptLabel}. Review its action set, approvals, and external sinks before expanding access.`,
      }
    }
    if (a.status === 'alert') {
      return {
        title: 'Watch this agent closely',
        body: 'The agent is already showing alert behavior. Review recent blocks and escalations before changing its permissions.',
      }
    }
    return {
      title: 'Keep current controls',
      body: 'The agent looks stable. Revisit it only if its block rate, risk level, or activity trend starts drifting.',
    }
  }
  const e = ALL_EVENTS.find(ev => ev.id === id)
  if (!e) {
    return {
      title: 'Check the decision path',
      body: 'Refresh the event or inspect the owning agent, policy, and department before acting on this item.',
    }
  }
  if (e.verdict === 'BLOCK') {
    return {
      title: 'Review the blocked flow',
      body: 'Confirm whether the block was expected. If it keeps repeating, narrow the workflow or adjust the policy boundary instead of widening access.',
    }
  }
  if (e.verdict === 'ESCALATE') {
    return {
      title: 'Route to human review',
      body: 'This event is intentionally routed to a human. Keep the approval path and escalation owner aligned with the clinical workflow.',
    }
  }
  return {
    title: 'Keep monitoring the trend',
    body: 'This action was allowed, but it should stay under review if similar events begin to drift or spike.',
  }
}

function highlightCiteHC(id: string) {
  const el = document.querySelector(`[data-cite-id="${id}"]`) as HTMLElement | null
  if (!el) return
  el.classList.remove('cite-ring')
  void el.offsetWidth
  el.classList.add('cite-ring')
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  setTimeout(() => el.classList.remove('cite-ring'), 2600)
}

function CitedMessageHC({ text, onCite }: { text: string; onCite: (type: string, id: string) => void }) {
  const parts: ReactNode[] = []
  let last = 0
  CITE_RE_HC.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = CITE_RE_HC.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const type = m[1].toLowerCase() as 'event' | 'agent'
    const id = m[2]
    const color = type === 'event'
      ? 'bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30'
      : 'bg-blue-500/20 border-blue-500/40 text-blue-300 hover:bg-blue-500/30'
    parts.push(
      <button key={m.index} onClick={() => onCite(type, id)}
        title={`${type}: ${id} — click to highlight in page`}
        className={`inline-flex items-center gap-0.5 mx-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border cursor-pointer transition-colors ${color}`}>
        {type === 'event' ? '⬤' : '◆'} {id.slice(0, 14)}{id.length > 14 ? '…' : ''}
      </button>
    )
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <span>{parts}</span>
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
  floors: string[]
}

const DEPARTMENTS: DeptConfig[] = [
  { key: 'icu', label: 'ICU Monitoring', icon: Heart, color: 'text-red-400', bgColor: 'bg-red-500/10', borderColor: 'border-red-500/30', count: 45, floors: ['4N', '4S'] },
  { key: 'radiology', label: 'Radiology AI', icon: Scan, color: 'text-blue-400', bgColor: 'bg-blue-500/10', borderColor: 'border-blue-500/30', count: 38, floors: ['B1', 'B2'] },
  { key: 'surgical', label: 'Surgical Robotics', icon: Cross, color: 'text-purple-400', bgColor: 'bg-purple-500/10', borderColor: 'border-purple-500/30', count: 30, floors: ['3W', '3E'] },
  { key: 'emergency', label: 'Emergency Triage', icon: AlertCircle, color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/30', count: 28, floors: ['1E', '1W'] },
  { key: 'pharmacy', label: 'Pharmacy Auto.', icon: Pill, color: 'text-amber-400', bgColor: 'bg-amber-500/10', borderColor: 'border-amber-500/30', count: 35, floors: ['1C', 'B1'] },
  { key: 'lab', label: 'Clinical Lab', icon: Microscope, color: 'text-cyan-400', bgColor: 'bg-cyan-500/10', borderColor: 'border-cyan-500/30', count: 42, floors: ['B2', 'B3'] },
  { key: 'monitoring', label: 'Patient Monitor.', icon: Activity, color: 'text-emerald-400', bgColor: 'bg-emerald-500/10', borderColor: 'border-emerald-500/30', count: 65, floors: ['2N', '2S', '3N', '3S', '4N'] },
  { key: 'ehr', label: 'EHR / Records', icon: FileText, color: 'text-sky-400', bgColor: 'bg-sky-500/10', borderColor: 'border-sky-500/30', count: 48, floors: ['1C', '2C'] },
  { key: 'nurse', label: 'Nurse Assist AI', icon: Stethoscope, color: 'text-pink-400', bgColor: 'bg-pink-500/10', borderColor: 'border-pink-500/30', count: 52, floors: ['2N', '2S', '3N', '3S'] },
  { key: 'cardiology', label: 'Cardiology', icon: Heart, color: 'text-rose-400', bgColor: 'bg-rose-500/10', borderColor: 'border-rose-500/30', count: 22, floors: ['5N', '5S'] },
  { key: 'neuro', label: 'Neurology AI', icon: Brain, color: 'text-violet-400', bgColor: 'bg-violet-500/10', borderColor: 'border-violet-500/30', count: 18, floors: ['6N', '6S'] },
  { key: 'scheduling', label: 'Scheduling', icon: Clock, color: 'text-teal-400', bgColor: 'bg-teal-500/10', borderColor: 'border-teal-500/30', count: 40, floors: ['1C', '2C'] },
  { key: 'telehealth', label: 'Telehealth', icon: Wifi, color: 'text-indigo-400', bgColor: 'bg-indigo-500/10', borderColor: 'border-indigo-500/30', count: 37, floors: ['Virtual'] },
]

// ─── Generate Agents ──────────────────────────────────────────────────────────

const AGENT_NAMES: Record<string, string[]> = {
  icu: ['Vigil', 'Apex', 'Sentinel', 'Pulse', 'Aegis', 'Cortex'],
  radiology: ['Vision', 'Lumis', 'Spectra', 'Diag', 'Imago', 'Clarity'],
  surgical: ['Nexus', 'Precis', 'Dextro', 'Kinesis', 'Sutura', 'Opus'],
  emergency: ['Rapid', 'Triage', 'Surge', 'Alert', 'Swift', 'Prime'],
  pharmacy: ['Doser', 'RxBot', 'Medic', 'Dispens', 'Formul', 'Vial'],
  lab: ['Analytica', 'Specimen', 'Chem', 'Pathol', 'Serum', 'Assay'],
  monitoring: ['Watch', 'Track', 'Beacon', 'Monitor', 'Relay', 'Probe'],
  ehr: ['Record', 'Scribe', 'Archiv', 'Chart', 'Codex', 'Index'],
  nurse: ['Assist', 'Carena', 'Nursa', 'Aide', 'Companion', 'Support'],
  cardiology: ['Rhythm', 'Cardiac', 'Pulse', 'Veno', 'Cordis', 'Systole'],
  neuro: ['Neural', 'Synapse', 'Cortex', 'Axon', 'Dendro', 'Neuro'],
  scheduling: ['Sched', 'Planner', 'Appoint', 'Queue', 'Roster', 'Coord'],
  telehealth: ['Connect', 'Remote', 'Virtual', 'Stream', 'Link', 'Portal'],
}

// Removed — lastAction now sourced from DEPT_OPS per agent

function generateAgents(): HospitalAgent[] {
  const rng = makeRng(0xdeadbeef)
  const agents: HospitalAgent[] = []

  for (const dept of DEPARTMENTS) {
    const names = AGENT_NAMES[dept.key] ?? ['Bot']
    const vendorPool = DEPT_VENDORS[dept.key] ?? DEPT_VENDORS['monitoring']
    for (let i = 0; i < dept.count; i++) {
      const nameBase = names[Math.floor(rng() * names.length)]
      const vendor = vendorPool[Math.floor(rng() * vendorPool.length)]
      const num = String(i + 1).padStart(3, '0')
      const id = `${dept.key.toUpperCase().slice(0, 3)}-${num}`
      const decisions = Math.floor(rng() * 800 + 50)
      const blockRate = rng() * 0.28
      const blocked = Math.floor(decisions * blockRate)
      // Status derived from activity: high block rate → alert, low decisions → idle
      const status: HospitalAgent['status'] = blockRate > 0.22 ? 'alert' : decisions < 80 ? 'idle' : 'active'
      // Risk level derived from block rate
      const riskLevel: HospitalAgent['riskLevel'] = blockRate > 0.20 ? 'high' : blockRate > 0.10 ? 'medium' : 'low'
      const floor = dept.floors[Math.floor(rng() * dept.floors.length)]
      // Patient/task load ranges by department
      const LOAD_RANGE: Record<string, [number, number]> = {
        icu: [3, 8], radiology: [4, 12], surgical: [1, 4], emergency: [6, 18],
        pharmacy: [10, 30], lab: [12, 35], monitoring: [10, 20], ehr: [20, 50],
        nurse: [5, 12], cardiology: [3, 8], neuro: [2, 6], scheduling: [15, 40], telehealth: [3, 10],
      }
      const [minL, maxL] = LOAD_RANGE[dept.key] ?? [5, 15]

      // Trend: derive previous block rate and trend direction from seeded RNG
      const trendR = rng()
      let blockRateTrend: HospitalAgent['blockRateTrend']
      let blockRatePrev: number
      if (blockRate > 0.20) {
        // High block rate agents — more likely to have spiked
        if (trendR < 0.55) {
          blockRateTrend = 'spiked'
          blockRatePrev = Math.round((blockRate * (0.25 + rng() * 0.30)) * 1000) / 10
        } else if (trendR < 0.80) {
          blockRateTrend = 'rising'
          blockRatePrev = Math.round((blockRate * (0.65 + rng() * 0.20)) * 1000) / 10
        } else {
          blockRateTrend = 'stable'
          blockRatePrev = Math.round((blockRate * (0.90 + rng() * 0.15)) * 1000) / 10
        }
      } else if (blockRate > 0.10) {
        if (trendR < 0.15) {
          blockRateTrend = 'spiked'
          blockRatePrev = Math.round((blockRate * (0.20 + rng() * 0.30)) * 1000) / 10
        } else if (trendR < 0.45) {
          blockRateTrend = 'rising'
          blockRatePrev = Math.round((blockRate * (0.60 + rng() * 0.25)) * 1000) / 10
        } else {
          blockRateTrend = 'stable'
          blockRatePrev = Math.round((blockRate * (0.88 + rng() * 0.18)) * 1000) / 10
        }
      } else {
        if (trendR < 0.04) {
          blockRateTrend = 'spiked'
          blockRatePrev = Math.round((blockRate * (0.15 + rng() * 0.25)) * 1000) / 10
        } else if (trendR < 0.15) {
          blockRateTrend = 'rising'
          blockRatePrev = Math.round((blockRate * (0.60 + rng() * 0.25)) * 1000) / 10
        } else {
          blockRateTrend = 'stable'
          blockRatePrev = Math.round((blockRate * (0.85 + rng() * 0.20)) * 1000) / 10
        }
      }

      agents.push({
        id,
        name: `${nameBase}-${num}`,
        department: dept.key,
        deptLabel: dept.label,
        vendorId: vendor.id,
        vendorName: vendor.name,
        status,
        decisions24h: decisions,
        blocked24h: blocked,
        blockRate: Math.round(blockRate * 1000) / 10,
        blockRatePrev,
        blockRateTrend,
        lastAction: (DEPT_OPS[dept.key]?.allow ?? DEPT_OPS['monitoring'].allow)[Math.floor(rng() * (DEPT_OPS[dept.key]?.allow.length ?? 1))],
        lastActiveMin: Math.floor(rng() * 30),
        riskLevel,
        floor,
        serialNo: `SN-${Math.floor(rng() * 900000 + 100000)}`,
        patientLoad: Math.floor(rng() * (maxL - minL + 1) + minL),
      })
    }
  }
  return agents
}

// ─── Generate Events ──────────────────────────────────────────────────────────

interface DeptOps { allow: string[]; block: string[]; escalate: string[] }
const DEPT_OPS: Record<string, DeptOps> = {
  icu: {
    allow:    ['patient.vitals.read', 'ecg.stream.read', 'iv.drip.monitor', 'alert.trigger.nurse', 'equipment.status.check'],
    block:    ['medication.dose.override', 'consent.bypass', 'surgery.protocol.deviate'],
    escalate: ['critical.alert.escalate', 'emergency.surgery.authorize'],
  },
  radiology: {
    allow:    ['imaging.scan.view', 'diagnosis.assist.query', 'equipment.status.check', 'lab.results.fetch'],
    block:    ['ehr.bulk.export', 'patient.data.transfer.external', 'consent.bypass'],
    escalate: ['critical.alert.escalate', 'high.risk.medication.approve'],
  },
  surgical: {
    allow:    ['equipment.status.check', 'patient.vitals.read', 'imaging.scan.view'],
    block:    ['surgery.protocol.deviate', 'equipment.calibration.skip', 'consent.bypass'],
    escalate: ['emergency.surgery.authorize', 'high.risk.medication.approve'],
  },
  emergency: {
    allow:    ['patient.vitals.read', 'alert.trigger.nurse', 'patient.location.track', 'diagnosis.assist.query'],
    block:    ['medication.dose.override', 'consent.bypass', 'diagnosis.override.physician'],
    escalate: ['emergency.surgery.authorize', 'critical.alert.escalate', 'dnr.status.update'],
  },
  pharmacy: {
    allow:    ['medication.schedule.read', 'equipment.status.check', 'lab.results.fetch'],
    block:    ['controlled.substance.dispense', 'medication.dose.override', 'consent.bypass'],
    escalate: ['high.risk.medication.approve'],
  },
  lab: {
    allow:    ['lab.results.fetch', 'equipment.status.check', 'diagnosis.assist.query'],
    block:    ['ehr.bulk.export', 'patient.data.transfer.external', 'equipment.calibration.skip'],
    escalate: ['critical.alert.escalate'],
  },
  monitoring: {
    allow:    ['patient.vitals.read', 'ecg.stream.read', 'iv.drip.monitor', 'patient.location.track', 'alert.trigger.nurse'],
    block:    ['medication.dose.override', 'consent.bypass', 'equipment.calibration.skip'],
    escalate: ['critical.alert.escalate'],
  },
  ehr: {
    allow:    ['ehr.record.read', 'lab.results.fetch', 'appointment.list', 'medication.schedule.read'],
    block:    ['ehr.bulk.export', 'patient.data.transfer.external', 'consent.bypass'],
    escalate: ['patient.discharge.approve'],
  },
  nurse: {
    allow:    ['patient.vitals.read', 'alert.trigger.nurse', 'medication.schedule.read', 'appointment.list', 'ehr.record.read'],
    block:    ['medication.dose.override', 'consent.bypass', 'diagnosis.override.physician'],
    escalate: ['critical.alert.escalate', 'dnr.status.update'],
  },
  cardiology: {
    allow:    ['ecg.stream.read', 'patient.vitals.read', 'equipment.status.check', 'diagnosis.assist.query'],
    block:    ['medication.dose.override', 'consent.bypass', 'equipment.calibration.skip'],
    escalate: ['critical.alert.escalate', 'emergency.surgery.authorize', 'high.risk.medication.approve'],
  },
  neuro: {
    allow:    ['diagnosis.assist.query', 'imaging.scan.view', 'patient.vitals.read'],
    block:    ['medication.dose.override', 'consent.bypass', 'diagnosis.override.physician'],
    escalate: ['critical.alert.escalate', 'high.risk.medication.approve'],
  },
  scheduling: {
    allow:    ['appointment.list', 'ehr.record.read', 'patient.location.track'],
    block:    ['patient.data.transfer.external', 'consent.bypass', 'ehr.bulk.export'],
    escalate: ['patient.discharge.approve'],
  },
  telehealth: {
    allow:    ['appointment.list', 'ehr.record.read', 'patient.vitals.read', 'diagnosis.assist.query'],
    block:    ['patient.data.transfer.external', 'consent.bypass', 'ehr.bulk.export'],
    escalate: ['critical.alert.escalate', 'patient.discharge.approve'],
  },
}
const BLOCK_REASONS = [
  'HIPAA_VIOLATION', 'UNAUTHORIZED_ACCESS', 'SCOPE_VIOLATION',
  'CONSENT_MISSING', 'CONTROLLED_SUBSTANCE', 'PROTOCOL_DEVIATION', 'FDA_COMPLIANCE',
]

const TOOL_OP_LABEL: Record<string, string> = {
  'patient.vitals.read':              'Read patient vitals',
  'lab.results.fetch':                'Fetch lab results',
  'imaging.scan.view':                'View imaging scan',
  'ehr.record.read':                  'Read patient record',
  'medication.schedule.read':         'Read medication schedule',
  'appointment.list':                 'List appointments',
  'diagnosis.assist.query':           'Run diagnostic query',
  'equipment.status.check':           'Check equipment status',
  'alert.trigger.nurse':              'Trigger nurse alert',
  'iv.drip.monitor':                  'Monitor IV drip',
  'ecg.stream.read':                  'Read ECG stream',
  'patient.location.track':           'Track patient location',
  'medication.dose.override':         'Override medication dose',
  'ehr.bulk.export':                  'Bulk export patient records',
  'patient.data.transfer.external':   'Transfer data off-site',
  'controlled.substance.dispense':    'Dispense controlled substance',
  'consent.bypass':                   'Bypass patient consent',
  'diagnosis.override.physician':     'Override physician diagnosis',
  'equipment.calibration.skip':       'Skip equipment calibration',
  'surgery.protocol.deviate':         'Deviate from surgery protocol',
  'emergency.surgery.authorize':      'Authorize emergency surgery',
  'high.risk.medication.approve':     'Approve high-risk medication',
  'dnr.status.update':                'Update DNR status',
  'patient.discharge.approve':        'Approve patient discharge',
  'critical.alert.escalate':          'Escalate critical alert',
}
const BLOCK_REASON_LABEL: Record<string, string> = {
  'HIPAA_VIOLATION':     'HIPAA violation',
  'UNAUTHORIZED_ACCESS': 'Unauthorized access',
  'SCOPE_VIOLATION':     'Outside agent scope',
  'CONSENT_MISSING':     'Patient consent missing',
  'CONTROLLED_SUBSTANCE':'Controlled substance rule',
  'PROTOCOL_DEVIATION':  'Protocol deviation',
  'FDA_COMPLIANCE':      'FDA compliance rule',
}
const fmtOp = (op: string) => TOOL_OP_LABEL[op] ?? op
const fmtReason = (r: string | null) => r ? (BLOCK_REASON_LABEL[r] ?? r) : null

// ─── Vendor & Device Lookup Tables ───────────────────────────────────────────

interface VendorDef { id: string; name: string }
const DEPT_VENDORS: Record<string, VendorDef[]> = {
  icu:        [{ id: 'VND-PT', name: 'PhysioTech AI' },      { id: 'VND-MC', name: 'MediCore Systems' }],
  radiology:  [{ id: 'VND-IL', name: 'ImagingAI Ltd' },      { id: 'VND-DP', name: 'DiagnosisPlus' }],
  surgical:   [{ id: 'VND-RS', name: 'RoboSurg Inc' },       { id: 'VND-PM', name: 'PrecisionMed AI' }],
  emergency:  [{ id: 'VND-TA', name: 'TriageAI' },           { id: 'VND-RR', name: 'RapidResponse Systems' }],
  pharmacy:   [{ id: 'VND-PB', name: 'PharmBot AI' },        { id: 'VND-AR', name: 'AutoRx Systems' }],
  lab:        [{ id: 'VND-LA', name: 'LabAnalytica' },       { id: 'VND-PA', name: 'PathologyAI' }],
  monitoring: [{ id: 'VND-VW', name: 'VitalWatch AI' },      { id: 'VND-BS', name: 'BioSignal Tech' }],
  ehr:        [{ id: 'VND-MR', name: 'MedRecord AI' },       { id: 'VND-CM', name: 'ChartMaster Systems' }],
  nurse:      [{ id: 'VND-CA', name: 'CareAssist AI' },      { id: 'VND-NB', name: 'NurseBot Systems' }],
  cardiology: [{ id: 'VND-CI', name: 'CardioAI' },           { id: 'VND-HM', name: 'HeartMonitor Tech' }],
  neuro:      [{ id: 'VND-NA', name: 'NeuroAnalytics AI' },  { id: 'VND-BR', name: 'BrainScan Systems' }],
  scheduling: [{ id: 'VND-SA', name: 'ScheduleAI' },         { id: 'VND-AB', name: 'AppointmentBot' }],
  telehealth: [{ id: 'VND-TC', name: 'TeleConnect AI' },     { id: 'VND-VC', name: 'VirtualCare Systems' }],
}

const DEPT_DEVICES: Record<string, string[]> = {
  icu:        ['Ventilator Unit', 'IV Pump', 'Patient Monitor', 'Infusion System'],
  radiology:  ['CT Scanner', 'MRI Machine', 'X-Ray Unit', 'Ultrasound Probe'],
  surgical:   ['Surgical Robot Arm', 'Laparoscopic Tower', 'OR Monitor'],
  emergency:  ['Defibrillator', 'Trauma Bay Monitor', 'Triage Kiosk'],
  pharmacy:   ['Auto-Dispensing Cabinet', 'IV Compounder', 'Barcode Scanner'],
  lab:        ['Centrifuge Unit', 'PCR Analyzer', 'Hematology Analyzer'],
  monitoring: ['Bedside Monitor', 'Pulse Oximeter', 'ECG Machine', 'Wearable Sensor'],
  ehr:        ['Workstation Terminal', 'Tablet Station', 'Nursing Kiosk'],
  nurse:      ['Medication Cart', 'Vitals Station', 'Call System'],
  cardiology: ['Echo Machine', 'Holter Monitor', 'Cardiac Monitor'],
  neuro:      ['EEG Machine', 'Neural Monitor', 'Brain Stimulator'],
  scheduling: ['Admin Terminal', 'Check-In Kiosk'],
  telehealth: ['Video Console', 'Remote Monitor', 'Tablet Hub'],
}

// All unique vendors — used to populate the filter dropdown
const ALL_VENDORS: VendorDef[] = Object.values(DEPT_VENDORS).flat()
  .filter((v, i, arr) => arr.findIndex(x => x.id === v.id) === i)
  .sort((a, b) => a.name.localeCompare(b.name))

function generateEvents(agents: HospitalAgent[]): DemoEvent[] {
  const rng = makeRng(0xcafebabe)
  const now = new Date()
  const events: DemoEvent[] = []
  let prevHash = '0000000000000000'

  for (let i = 0; i < 1000; i++) {
    const verdictR = rng()
    const verdict: Verdict = verdictR < 0.55 ? 'ALLOW' : verdictR < 0.90 ? 'BLOCK' : 'ESCALATE'
    const agent = agents[Math.floor(rng() * agents.length)]
    const deptOps = DEPT_OPS[agent.department] ?? DEPT_OPS['monitoring']
    const opPool = verdict === 'ALLOW' ? deptOps.allow : verdict === 'BLOCK' ? deptOps.block : deptOps.escalate
    const toolOp = opPool[Math.floor(rng() * opPool.length)]
    const reasonCode =
      verdict === 'BLOCK' ? BLOCK_REASONS[Math.floor(rng() * BLOCK_REASONS.length)] : null
    const latencyMs = Math.floor(rng() * 18 + 1)
    const minutesAgo = rng() * 60
    const ts = new Date(now.getTime() - minutesAgo * 60 * 1000)
    const patientId = `P-${String(Math.floor(rng() * 99999 + 10000))}`
    const riskScore = Math.round(rng() * 100)
    const payload = `${i}|${verdict}|${agent.id}|${toolOp}|${ts.toISOString()}|${prevHash}`
    const hash = murmurHash(payload)
    prevHash = hash
    const intentId = `int_${murmurHash(`intent${i}`).slice(0, 8)}`
    const policyVersions = ['clinical-safety-v2.1.0', 'clinical-safety-v2.0.3', 'hipaa-strict-v1.4.0', 'fda-samd-v1.2.0']
    const policyVersion = policyVersions[Math.floor(rng() * policyVersions.length)]
    const opLabel = fmtOp(toolOp)
    const reasonLabel = fmtReason(reasonCode) ?? 'policy match'
    const explanations: Record<string, string> = {
      ALLOW: `${agent.deptLabel} agent ${agent.id} requested to ${opLabel.toLowerCase()}. Intent verified within scope of ${policyVersion}. Risk score ${riskScore}/100 — within threshold. Action permitted.`,
      BLOCK: `${agent.deptLabel} agent ${agent.id} attempted to ${opLabel.toLowerCase()}. Blocked by ${policyVersion}: ${reasonLabel}. Risk score ${riskScore}/100 exceeds configured limit. Action denied.`,
      ESCALATE: `${agent.deptLabel} agent ${agent.id} requested to ${opLabel.toLowerCase()} for patient ${patientId}. Action requires physician confirmation per ${policyVersion}. Routed to human review queue.`,
    }

    // Simulate human review for ESCALATE events
    const REVIEWERS = [
      { name: 'Dr. Chen',  email: 'dr.chen@stmercy.org' },
      { name: 'Dr. Patel', email: 'dr.patel@stmercy.org' },
      { name: 'N. Garcia', email: 'nurse.garcia@stmercy.org' },
    ]
    const REVIEW_REASONS: Record<string, string> = {
      approved: 'Clinically appropriate. Patient context reviewed. Proceeding.',
      denied: 'Action outside current care plan. Escalating to attending.',
    }
    let reviewStatus: DemoEvent['reviewStatus'] = 'pending'
    let reviewedBy: string | undefined
    let reviewedByEmail: string | undefined
    let reviewedAt: Date | undefined
    let reviewReason: string | undefined

    // Clinical context for escalations — what the agent detected
    const CLINICAL_CONTEXT: Record<string, string[]> = {
      'emergency.surgery.authorize': [
        `Acute abdomen with rebound tenderness. BP ${70 + Math.floor(rng()*30)}/${40 + Math.floor(rng()*20)}, HR ${110 + Math.floor(rng()*30)}, Temp ${38 + Math.floor(rng()*1.5).toFixed(1)}°C. CT shows free air — suspected perforation.`,
        `Trauma patient, GCS 10, declining. FAST exam positive for intra-abdominal bleeding. Surgical team on standby.`,
        `Bowel obstruction unresponsive to 6h of conservative management. Vitals deteriorating. Surgical consult recommends urgent intervention.`,
      ],
      'high.risk.medication.approve': [
        `Agent recommends initiating heparin infusion for confirmed DVT (ultrasound positive). Current PT/INR within range, no recent bleeding events. Proposed dose: 80 units/kg bolus.`,
        `Oncology: cycle 3 of carboplatin/paclitaxel due today. Last CBC shows ANC 1.2 — borderline for treatment. Pharmacist flagged for physician decision.`,
        `Patient in A-fib with RVR. Agent recommends IV diltiazem. Baseline BP 148/92. No known contraindications in chart.`,
      ],
      'dnr.status.update': [
        `Family meeting completed 2h ago. Spouse and two family members present. Patient previously expressed comfort-care wishes verbally. Requesting DNR documentation per attending verbal order.`,
        `Patient has terminal diagnosis with 3-month prognosis. Palliative care consulted. Patient alert and oriented — verbally confirmed DNR wishes to nursing staff.`,
        `Advance directive on file from 2024 specifying no resuscitation. Agent flagged discrepancy with current active code status in EHR — requesting update to match directive.`,
      ],
      'patient.discharge.approve': [
        `Post-op day 2, laparoscopic cholecystectomy. Tolerating PO, pain 2/10 on oral analgesics, ambulating independently. Vitals stable ×24h. Wound site clean and dry.`,
        `Pneumonia patient, completed 5-day IV antibiotics, afebrile ×48h, SpO2 97% on room air. Chest X-ray shows improvement. Able to perform ADLs independently.`,
        `Diabetic foot ulcer, wound care completed, blood glucose controlled on oral meds. Home health arranged. Patient and family educated on wound care protocol.`,
      ],
      'critical.alert.escalate': [
        `SpO2 declined from 96% → 88% over 18 minutes. Repositioning and supplemental O2 at 4L/min have not reversed trend. HR 124, RR 28. Agent requesting rapid response team.`,
        `Telemetry shows new-onset ventricular tachycardia, 3 runs in 20 minutes, longest 8 beats. Patient reports palpitations and lightheadedness. Cardiologist not yet notified.`,
        `Systolic BP dropped from 118 → 74 over 30 minutes. Last fluid bolus given 2h ago. No active bleeding documented. Agent flagging for sepsis protocol evaluation.`,
      ],
    }
    const contextPool = CLINICAL_CONTEXT[toolOp]
    const clinicalContext = contextPool
      ? contextPool[Math.floor(rng() * contextPool.length)]
      : undefined
    const urgency: DemoEvent['urgency'] =
      toolOp === 'emergency.surgery.authorize' || toolOp === 'critical.alert.escalate' ? 'critical'
      : toolOp === 'high.risk.medication.approve' || toolOp === 'dnr.status.update' ? 'urgent'
      : 'routine'

    if (verdict === 'ESCALATE') {
      const reviewR = rng()
      // 60% already reviewed, 40% still pending
      if (reviewR < 0.6) {
        const reviewer = REVIEWERS[Math.floor(rng() * REVIEWERS.length)]
        const approved = rng() < 0.72 // 72% approval rate
        reviewStatus = approved ? 'approved' : 'denied'
        reviewedBy = reviewer.name
        reviewedByEmail = reviewer.email
        reviewedAt = new Date(ts.getTime() + Math.floor(rng() * 4 + 1) * 60 * 1000)
        reviewReason = REVIEW_REASONS[reviewStatus]
      }
    }

    const vendorPool = DEPT_VENDORS[agent.department] ?? DEPT_VENDORS['monitoring']
    const vendor = vendorPool[Math.floor(rng() * vendorPool.length)]
    const devicePool = DEPT_DEVICES[agent.department] ?? DEPT_DEVICES['monitoring']
    const hasDevice = rng() < 0.6
    const deviceIdx = Math.floor(rng() * devicePool.length)
    const deviceName = hasDevice ? devicePool[deviceIdx] : undefined
    const deviceId = hasDevice ? `DEV-${agent.department.toUpperCase().slice(0, 3)}-${String(deviceIdx + 1).padStart(2, '0')}` : undefined

    events.push({
      id: `EVT-${String(i + 1).padStart(6, '0')}`,
      verdict,
      agent: agent.id,
      department: agent.department,
      deptLabel: agent.deptLabel,
      toolOp,
      reasonCode,
      latencyMs,
      ts,
      hash,
      riskScore,
      patientId,
      intentId,
      policyVersion,
      explanation: explanations[verdict],
      vendorId: vendor.id,
      vendorName: vendor.name,
      ...(hasDevice && { deviceId, deviceName }),
      ...(verdict === 'ESCALATE' && { clinicalContext, urgency, reviewStatus, reviewedBy, reviewedByEmail, reviewedAt, reviewReason }),
    })
  }

  return events.sort((a, b) => b.ts.getTime() - a.ts.getTime())
}

// ─── Static Data ──────────────────────────────────────────────────────────────

const ALL_AGENTS = generateAgents()
const ALL_EVENTS = generateEvents(ALL_AGENTS)

// ─── Logo Components ──────────────────────────────────────────────────────────

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
      </defs>
      <rect width="40" height="40" rx="10" fill={`url(#${id}-bg)`} />
      <rect width="40" height="40" rx="10" fill="none" stroke={`url(#${id}-border)`} strokeWidth="1" />
      <rect x="1" y="1" width="38" height="10" rx="9" fill="rgba(255,255,255,0.03)" />
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

// ─── Healthcare Onboarding Mock Data ─────────────────────────────────────────

const HC_MOCK_BUNDLE = {
  total_count: 16,
  hard_safety: [
    { policy_id:'hs1', action_pattern:'phi.external.send',       decision:'BLOCK',          reason:'PHI egress blocked at all external trust boundaries', agent_system:'clinical-agent' },
    { policy_id:'hs2', action_pattern:'medication.order.*',      decision:'HUMAN_REQUIRED', reason:'All medication orders require attending physician confirmation', agent_system:'pharmacy-agent' },
    { policy_id:'hs3', action_pattern:'surgery.authorize.*',     decision:'HUMAN_REQUIRED', reason:'Surgical pre-auth requires surgeon + EDON dual verification', agent_system:'surgical-agent' },
    { policy_id:'hs4', action_pattern:'patient.record.delete',   decision:'BLOCK',          reason:'Patient record deletion blocked — HIPAA retention requirement', agent_system:'ehr-agent' },
    { policy_id:'hs5', action_pattern:'credential.llm.api.*',    decision:'ESCALATE',       reason:'LLM API credential access requires security review', agent_system:'clinical-agent' },
  ],
  operational: [
    { policy_id:'op1', action_pattern:'phi.read.*',              decision:'ALLOW',          reason:'PHI reads allowed within verified clinical session scope', agent_system:'clinical-agent' },
    { policy_id:'op2', action_pattern:'lab.result.retrieve',     decision:'ALLOW',          reason:'Lab retrieval pre-authorized for treating providers', agent_system:'lab-agent' },
    { policy_id:'op3', action_pattern:'alert.send.critical',     decision:'ESCALATE',       reason:'Critical alerts require dual-acknowledgement before dispatch', agent_system:'monitoring-agent' },
    { policy_id:'op4', action_pattern:'dosage.calculate.*',      decision:'ESCALATE',       reason:'Dosage calculations routed to pharmacist review queue', agent_system:'pharmacy-agent' },
    { policy_id:'op5', action_pattern:'patient.discharge.*',     decision:'HUMAN_REQUIRED', reason:'Discharge authorization requires attending sign-off', agent_system:'ehr-agent' },
    { policy_id:'op6', action_pattern:'report.generate.*',       decision:'ALLOW',          reason:'Report generation allowed with automatic PHI scrubbing', agent_system:'clinical-agent' },
  ],
  intent_contracts: [
    { policy_id:'ic1', action_pattern:'agent.scope.*',           decision:'ALLOW',          reason:'Agent scope bounded to assigned department and patient list', agent_system:'clinical-agent' },
    { policy_id:'ic2', action_pattern:'cross.dept.data.*',       decision:'ESCALATE',       reason:'Cross-department data access requires explicit authorization', agent_system:'ehr-agent' },
    { policy_id:'ic3', action_pattern:'audit.trail.*',           decision:'ALLOW',          reason:'All decisions logged immutably with HIPAA-compliant audit chain', agent_system:'all' },
    { policy_id:'ic4', action_pattern:'bulk.export.*',           decision:'BLOCK',          reason:'Bulk PHI export blocked outside approved data governance workflow', agent_system:'all' },
    { policy_id:'ic5', action_pattern:'training.data.include.*', decision:'BLOCK',          reason:'Patient data excluded from LLM training pipelines', agent_system:'all' },
  ],
}

const HC_MOCK_DEPLOYMENT = {
  deployment_mode: 'vpc',
  estimated_setup_h: 2,
  connector_configs: [{ name:'EHR Gateway' }, { name:'Pharmacy API' }, { name:'Lab Interface' }],
  env_vars: {
    EDON_TENANT_ID: 'hc-demo-001',
    EDON_ENFORCEMENT: 'active',
    EDON_DOMAIN: 'healthcare',
    EDON_HIPAA_MODE: 'true',
    EDON_FAIL_CLOSED: 'true',
    EDON_AUDIT_STREAM: 'kinesis://edon-audit-prod',
  },
  helm_values: { replicaCount: 2 },
  rollback_plan: ['Disable EDON sidecar in K8s manifest', 'Restore original agent routing', 'Notify security team', 'Re-enable after root-cause review'],
}

const HC_MOCK_MANIFEST = {
  tenant_id: 'regional-one-pilot',
  org_name: 'Regional One Health',
  deployment_mode: 'pilot',
  market_pack: 'healthcare',
  policy_pack: 'hospital',
  identity_provider: 'Microsoft Entra ID',
  environments: ['VPC-native', 'governed mode', 'approval-bound writeback'],
  compliance_requirements: ['HIPAA', 'HITECH', 'FDA SaMD'],
  agent_inventory: ['epic-note-drafter', 'lab-triage-assistant', 'escalation-router'],
  support_contact: 'support@edoncore.com',
  approval_flags: ['production promotion requires approval', 'connector writeback requires approval'],
}

// ─── Healthcare Onboarding Screen ─────────────────────────────────────────────

type HCOBMsg = { role: 'copilot' | 'user'; text: string; id: number }

interface HCOnboardingSnapshot {
  screen: number
  orgName: string
  tenantMode: 'advisory' | 'governed' | 'autonomous'
  sandboxMode: boolean
  selectedConnector: 'Entra' | 'Epic' | 'Teams' | 'SIEM'
  agentDrafts: { name: string; phi: boolean; autonomous: boolean; actions: string[] }[]
}

function HCOnboardingScreen({ onComplete, onLogout }: { onComplete: () => void; onLogout: () => void }) {
  const saved = loadStoredJSON<Partial<HCOnboardingSnapshot>>(HC_ONBOARDING_STORAGE_KEY, {})
  const [screen, setScreen]       = useState(() => saved.screen ?? 1)
  const [msgs, setMsgs]           = useState<HCOBMsg[]>([])
  const [input, setInput]         = useState('')
  const [isTyping, setIsTyping]   = useState(false)
  const [ctaReady, setCtaReady]   = useState(false)
  const [convStep, setConvStep]   = useState(0)
  const [busy, setBusy]           = useState(false)
  const [tenantMode, setTenantMode] = useState<'advisory' | 'governed' | 'autonomous'>(() => saved.tenantMode ?? 'governed')
  const [sandboxMode, setSandboxMode] = useState(() => saved.sandboxMode ?? true)
  const [modeConfirm, setModeConfirm] = useState<null | 'enable-live' | 'return-sandbox'>(null)
  const [selectedConnector, setSelectedConnector] = useState<'Entra'|'Epic'|'Teams'|'SIEM'>(() => saved.selectedConnector ?? 'Entra')

  const idRef     = useRef(0)
  const cancelRef = useRef(false)
  const msgEndRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)

  const [orgName,        setOrgName]        = useState(() => saved.orgName ?? '')
  const [agentDrafts,    setAgentDrafts]    = useState<{name:string;phi:boolean;autonomous:boolean;actions:string[]}[]>(() => saved.agentDrafts ?? [])
  const [bundle,         setBundle]         = useState<typeof HC_MOCK_BUNDLE | null>(null)
  const [deployment,     setDeployment]     = useState<typeof HC_MOCK_DEPLOYMENT | null>(null)
  const [simDone,        setSimDone]        = useState(false)
  const tenantManifest = {
    tenant_id: orgName ? `${orgName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')}-pilot` : HC_MOCK_MANIFEST.tenant_id,
    org_name: orgName || HC_MOCK_MANIFEST.org_name,
    deployment_mode: 'pilot' as const,
    governance_mode: sandboxMode ? 'sandbox' : tenantMode,
    runtime_mode: sandboxMode ? 'sandbox' : 'live',
    market_pack: HC_MOCK_MANIFEST.market_pack,
    policy_pack: HC_MOCK_MANIFEST.policy_pack,
    identity_provider: HC_MOCK_MANIFEST.identity_provider,
    environments: HC_MOCK_MANIFEST.environments,
    compliance_requirements: HC_MOCK_MANIFEST.compliance_requirements,
    agent_inventory: agentDrafts.length > 0 ? agentDrafts.map(a => a.name) : HC_MOCK_MANIFEST.agent_inventory,
    support_contact: HC_MOCK_MANIFEST.support_contact,
    approval_flags: HC_MOCK_MANIFEST.approval_flags,
  }
  const readinessChecks = [
    ['SSO-only Mode', 'Enforced'],
    ['MFA Enforcement', 'Active'],
    ['Tenant Isolation', 'Verified'],
    ['Audit Encryption', 'Active'],
    ['Decision Binding', sandboxMode ? 'Audit-only' : (simDone ? 'Active' : 'Pending')],
    ['Edge Identity', deployment ? 'Verified' : 'Pending'],
    ['Rollback Validation', deployment ? 'Passed' : 'Pending'],
    ['PHI Safeguards', 'Enforced'],
  ] as const
  const liveActionLabel = sandboxMode ? 'Enable live governance' : 'Return to sandbox'
  const modeCards = [
    ['advisory', 'Advisory', 'No execution authority'],
    ['governed', 'Governed', 'Approval-bound execution'],
    ['autonomous', 'Autonomous', 'Policy-scoped autonomous execution'],
  ] as const
  const complianceChecks = [
    ['PHI Encryption', 'Active'],
    ['Minimum Necessary Access', 'Enforced'],
    ['Audit Traceability', 'Verified'],
    ['Access Logging', 'Active'],
    ['MFA Enforcement', 'Active'],
    ['Tenant Isolation', 'Verified'],
    ['PHI Export Controls', 'Blocked'],
  ] as const
  const connectorRows = [
    ['Entra', 'None', 'v1.4', '2m ago'],
    ['Epic', 'None', 'v1.3', '2m ago'],
    ['Teams', 'Minor', 'v1.2', '7m ago'],
    ['SIEM', 'None', 'v1.1', '5m ago'],
  ] as const
  const connectorDetails = {
    Entra: {
      scopes: ['Identity claims', 'Role mapping', 'MFA enforcement'],
      permissions: 'Enterprise SSO trust',
      mode: 'Governed',
      certification: 'v1.4',
      drift: 'None',
      lastVerified: '2m ago',
      rollback: 'Disable tenant mapping',
      audit: 'Auth events mirrored to audit trail',
    },
    Epic: {
      scopes: ['note.draft', 'record.writeback', 'escalation.route'],
      permissions: 'Approval-bound EHR access',
      mode: 'Governed',
      certification: 'v1.3',
      drift: 'None',
      lastVerified: '2m ago',
      rollback: 'Revoke connector write scope',
      audit: 'Writeback events retained and replayable',
    },
    Teams: {
      scopes: ['escalation.notify', 'case.alert', 'support.bridge'],
      permissions: 'Scoped messaging sink',
      mode: 'Governed',
      certification: 'v1.2',
      drift: 'Minor',
      lastVerified: '7m ago',
      rollback: 'Quarantine notification route',
      audit: 'Message delivery logged',
    },
    SIEM: {
      scopes: ['audit.export', 'event.stream', 'incident.push'],
      permissions: 'Read-only evidence export',
      mode: 'Advisory / Governed',
      certification: 'v1.1',
      drift: 'None',
      lastVerified: '5m ago',
      rollback: 'Disable export stream',
      audit: 'Chain integrity mirrored',
    },
  } as const
  const governedActionRows = [
    ['Draft Notes', 'Governed', 'Optional', 'Yes', 'Yes'],
    ['Record Writeback', 'Approval-Bound', 'Required', 'Partial', 'Yes'],
    ['Escalations', 'Governed', 'No', 'N/A', 'Yes'],
    ['Medication Execution', 'Disabled', 'Required', 'Limited', 'Yes'],
  ] as const
  const procurementRows = [
    ['HIPAA Controls', 'Active'],
    ['Audit Integrity', 'Verified'],
    ['Tenant Isolation', 'Verified'],
    ['Restore Drill', deployment ? 'Passed' : 'Pending'],
    ['MFA Enforcement', 'Active'],
    ['Connector Certification', 'Verified'],
  ] as const


  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior:'smooth' }) }, [msgs, isTyping])

  const addCopilot = useCallback((text: string, delay = 950): Promise<void> =>
    new Promise(resolve => {
      setIsTyping(true)
      setTimeout(() => {
        if (cancelRef.current) { resolve(); return }
        setIsTyping(false)
        setMsgs(p => [...p, { role:'copilot', text, id: ++idRef.current }])
        setTimeout(resolve, 80)
      }, delay)
    }), [])

  useEffect(() => {
    cancelRef.current = false
    setMsgs([]); setConvStep(0); setCtaReady(false); setInput('')
    const openers: Record<number, string> = {
      1: 'What healthcare organization is this for? List the clinical AI systems you are deploying - EHR assistants, diagnostic tools, pharmacy agents, monitoring bots.',
      2: 'What can your agents do? List the clinical actions and any external systems they touch.',
      3: 'Choose the tenant governance mode and activate governance controls.',
      4: 'Review the governed action matrix and confirm the operational boundaries.',
      5: 'Review procurement readiness and launch the tenant when evidence is complete.',
    }
    const t = setTimeout(async () => {
      await addCopilot(openers[screen] ?? '', 600)
    }, 160)
    return () => { cancelRef.current = true; clearTimeout(t) }
  }, [screen]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (screen === 3 && deployment && !simDone) {
      let cancelled = false
      setBusy(true)
      const t = setTimeout(async () => {
        if (cancelled) return
        await new Promise(r => setTimeout(r, 2000))
        if (cancelled) return
        setSimDone(true)
        setBusy(false)
        await addCopilot('Governance activation review complete ? deployment controls and policy posture are aligned.', 400)
      }, 120)
      return () => { cancelled = true; clearTimeout(t); setBusy(false) }
    }
    return undefined
  }, [screen, deployment, simDone, addCopilot])

  useEffect(() => {
    if (screen === 3 && !deployment) {
      setDeployment(HC_MOCK_DEPLOYMENT)
      setBundle(HC_MOCK_BUNDLE)
    }
    setCtaReady(screen === 3 ? simDone : true)
  }, [deployment, simDone, screen])

  useEffect(() => {
    saveStoredJSON(HC_ONBOARDING_STORAGE_KEY, {
      screen,
      orgName,
      tenantMode,
      sandboxMode,
      selectedConnector,
      agentDrafts,
    } satisfies HCOnboardingSnapshot)
  }, [screen, orgName, tenantMode, sandboxMode, selectedConnector, agentDrafts])

  useEffect(() => {
    publishHCContext([
      'Onboarding wizard',
      `screen ${screen}/5`,
      orgName ? `org ${orgName}` : 'org not set',
      `tenant mode ${tenantMode}`,
      `runtime ${sandboxMode ? 'sandbox' : 'live'}`,
      `connector ${selectedConnector}`,
      `${agentDrafts.length} draft agent${agentDrafts.length === 1 ? '' : 's'}`,
      deployment ? `deployment ready` : 'deployment pending',
    ].join(' · '))
  }, [screen, orgName, tenantMode, sandboxMode, selectedConnector, agentDrafts.length, deployment])

  const sendDirect = async (text: string) => {
    if (!text || isTyping || busy) return
    setMsgs(p => [...p, { role:'user', text, id: ++idRef.current }])
    setConvStep(s => s + 1)

    // ── Step 1: Org + AI stack ──
    if (screen === 1) {
      if (convStep === 0) {
        const lines = text.split(/\n|,|;/).map(s => s.trim()).filter(s => s.length > 2)
        const orgLine = lines[0] || text
        const agentLines = lines.slice(1)
        const parsedOrg = orgLine.replace(/^(for|at|called|named)\s+/i, '').trim()
        setOrgName(parsedOrg)
        if (agentLines.length > 0) {
          const agents = agentLines.map((p, i) => ({
            name: /ehr|record|chart/i.test(p) ? 'ehr-agent' : /pharm|medic|drug/i.test(p) ? 'pharmacy-agent' : /lab|test|result/i.test(p) ? 'lab-agent' : /monitor|vital|alert/i.test(p) ? 'monitoring-agent' : `clinical-agent-${i+1}`,
            phi: true, autonomous: true, actions: [],
          }))
          setAgentDrafts(agents)
          await addCopilot(`Workspace initialized for "${parsedOrg}". ${agents.length} clinical AI system${agents.length !== 1 ? 's' : ''} identified — all tagged as PHI-handling.`)
          await addCopilot('Do they operate autonomously or require physician approval?', 700)
        } else {
          await addCopilot(`Workspace initialized for "${parsedOrg}". Domain: Healthcare · HIPAA + FDA SaMD templates applied.`)
          await addCopilot('Now list the clinical AI systems in use — EHR agents, diagnostic tools, pharmacy bots, etc.', 700)
        }
      } else if (convStep === 1 && agentDrafts.length === 0) {
        const parts = text.split(/\band\b|,/i).map(s => s.trim()).filter(s => s.length > 2)
        const agents = (parts.length > 0 ? parts : [text]).map((p, i) => ({
          name: /ehr|record|chart/i.test(p) ? 'ehr-agent' : /pharm|medic|drug/i.test(p) ? 'pharmacy-agent' : /lab|test|result/i.test(p) ? 'lab-agent' : /monitor|vital|alert/i.test(p) ? 'monitoring-agent' : `clinical-agent-${i+1}`,
          phi: true, autonomous: true, actions: [],
        }))
        setAgentDrafts(agents)
        await addCopilot(`${agents.length} clinical AI system${agents.length !== 1 ? 's' : ''} identified — all classified as PHI-handling.`)
        await addCopilot('Do they operate autonomously or require physician approval?', 700)
      } else {
        const auto = /autonom|mostly|auto|no human|independent/i.test(text)
        setAgentDrafts(p => p.map(a => ({ ...a, autonomous: auto })))
        await addCopilot(auto
          ? 'Autonomous agents — elevated HIPAA governance scope applied. Mandatory escalation for high-risk actions.'
          : 'Human-in-loop agents — physician confirmation required for critical clinical actions.')
        setCtaReady(true)
      }
    }

    // ── Step 2: Risk surface ──
    else if (screen === 2) {
      if (convStep === 0) {
        const write = /order|prescri|administer|updat|write|modif|creat/i.test(text)
        const crit  = /surgery|operat|resuscit|dnr|icu/i.test(text)
        const acts  = ['phi.read', 'lab.result.retrieve', ...write ? ['medication.order','patient.record.update'] : [], ...crit ? ['surgery.authorize','critical.alert.escalate'] : []]
        setAgentDrafts(p => p.map((a, i) => i === 0 ? { ...a, actions: acts } : a))
        const sinks: string[] = []
        if (/openai|gpt|anthropic|llm/i.test(text)) sinks.push('External LLM API (PHI exposure risk)')
        if (/analytic|tableau|segment/i.test(text)) sinks.push('Analytics export pipeline')
        if (/slack|email|teams|pager/i.test(text)) sinks.push('Clinical notification sink')
        if (/s3|gcs|blob|storage/i.test(text)) sinks.push('Cloud storage (HIPAA BAA required)')
        if (crit) {
          await addCopilot('Critical clinical actions detected — surgery and resuscitation flags require HUMAN_REQUIRED classification.')
        } else if (write) {
          await addCopilot('Write-paths into clinical systems flagged. Medication orders and record updates require verification policies.')
        } else {
          await addCopilot('Read-only access pattern confirmed. PHI access policies applied to all retrieval paths.')
        }
        if (sinks.length > 0) {
          await addCopilot(`${sinks.length} external sink${sinks.length !== 1 ? 's' : ''} detected — BLOCK policies generated for unclassified PHI egress.`, 600)
          setCtaReady(true)
        } else {
          await addCopilot('Do any agents connect to external systems — LLM APIs, analytics platforms, vendor services?', 700)
        }
      } else {
        const detected: string[] = []
        if (/openai|gpt|anthropic|llm/i.test(text)) detected.push('External LLM API (PHI exposure risk)')
        if (/analytic|tableau|segment/i.test(text)) detected.push('Analytics export pipeline')
        if (/slack|email|teams|pager/i.test(text)) detected.push('Clinical notification sink')
        if (/s3|gcs|blob|storage/i.test(text)) detected.push('Cloud storage (HIPAA BAA required)')
        if (detected.length === 0 && /yes|external|vendor/i.test(text)) detected.push('External vendor endpoint')
        if (detected.length > 0) {
          await addCopilot(`${detected.length} external sink${detected.length !== 1 ? 's' : ''} flagged. BLOCK policies generated for all unclassified PHI egress.`)
        } else if (/no|none|internal/i.test(text)) {
          await addCopilot('No external sinks. All clinical data flows remain within your HIPAA trust boundary.')
        } else {
          await addCopilot('External flows noted. Trust boundary topology updated.')
        }
        setCtaReady(true)
      }
    }

    // ── Step 3: Governance pack ──
    else if (screen === 3) {
      if (convStep === 0) {
        await addCopilot(/strict|yes|hipaa|fail.close/i.test(text)
          ? 'Fail-closed enforcement selected. PHI ambiguity defaults to BLOCK.'
          : 'Balanced enforcement — critical PHI operations still require human confirmation.')
        await addCopilot('Compiling HIPAA-aligned policy pack...', 400)
        setBusy(true)
        await new Promise(r => setTimeout(r, 2000))
        if (!cancelRef.current) {
          setBundle(HC_MOCK_BUNDLE)
          setBusy(false)
          await addCopilot(`Policy Pack v1 — ${HC_MOCK_BUNDLE.total_count} rules across 3 layers.`, 300)
          await addCopilot('Now deployment topology: VPC-native inside your hospital network, or cloud proxy?', 600)
        }
      } else {
        const mode = /vpc|aws|private|network/i.test(text) ? 'vpc' : 'cloud_proxy'
        await addCopilot(mode === 'vpc'
          ? 'VPC-native — EDON runs inside your hospital network perimeter. No PHI leaves the boundary.'
          : 'Cloud proxy selected. Managed TLS + end-to-end encryption. HIPAA BAA required.')
        setBusy(true)
        await new Promise(r => setTimeout(r, 1200))
        if (!cancelRef.current) {
          setDeployment(HC_MOCK_DEPLOYMENT)
          setBusy(false)
          await addCopilot(`Deployment config generated. ${HC_MOCK_DEPLOYMENT.estimated_setup_h}h estimated setup.`, 300)
          setCtaReady(true)
        }
      }
    }
  }

  const sendMsg = () => { const t = input.trim(); if (!t) return; setInput(''); sendDirect(t) }

  const handleCTA = async () => {
    if (screen < 5) { setScreen(s => s + 1); return }
    setBusy(true)
    await new Promise(r => setTimeout(r, 1400))
    localStorage.setItem('hc_demo_ob', '1')
    onComplete()
    setBusy(false)
  }

  const confirmModeChange = () => {
    if (modeConfirm === 'enable-live') {
      if (tenantMode === 'advisory') setTenantMode('governed')
      setSandboxMode(false)
    } else if (modeConfirm === 'return-sandbox') {
      setSandboxMode(true)
    }
    setModeConfirm(null)
  }

  const CTA_LABELS: Record<number, string> = {
    1: 'Connect Systems',
    2: 'Verify Connectors',
    3: 'Activate Governance',
    4: 'Review Action Readiness',
    5: 'Launch Pilot',
  }

  const SCREEN_META: Record<number, { title: string; sub: string }> = {
    1: { title: 'Hospital Environment Detection', sub: 'Detect the tenant and connect hospital systems' },
    2: { title: 'Connector Verification',         sub: 'Confirm IdP, Epic, Teams, and SIEM trust' },
    3: { title: 'Governance Activation',          sub: 'Enforce control posture before tenant activation' },
    4: { title: 'Governed Action Readiness',      sub: 'Show the operational boundaries EDON will enforce' },
    5: { title: 'Procurement Readiness',          sub: 'Evidence pack, approval, and pilot launch' },
  }
  const meta = SCREEN_META[screen]
  const showInput = screen <= 2
  const onboardingPresets = {
    1: ['Regional hospital system', 'Clinical AI platform', 'Health tech startup'],
    2: ['Read labs & vitals', 'Medication orders', 'Surgical pre-auth'],
    3: {
      mode: ['Strict (HIPAA)', 'Balanced', 'Autonomous pilot'],
      topology: ['VPC native', 'Cloud proxy'],
    },
  } as const

  return (
    <div className="min-h-screen flex flex-col" style={{ background:'#07100b' }}>
      <button
        type="button"
        onClick={() => setModeConfirm(sandboxMode ? 'enable-live' : 'return-sandbox')}
        className="shrink-0 w-full flex items-center justify-center gap-2 px-4 py-2 text-[10px] font-bold tracking-widest uppercase"
        style={{
          background: sandboxMode ? 'rgba(59,130,246,0.14)' : 'rgba(74,222,128,0.14)',
          color: sandboxMode ? '#93c5fd' : '#86efac',
          borderBottom: sandboxMode ? '1px solid rgba(59,130,246,0.35)' : '1px solid rgba(74,222,128,0.35)',
        }}
      >
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: sandboxMode ? '#60a5fa' : '#4ade80', boxShadow: sandboxMode ? '0 0 8px rgba(96,165,250,0.65)' : '0 0 8px rgba(74,222,128,0.65)' }} />
          {sandboxMode ? 'Sandbox mode' : 'Live governance'}
        </span>
        <span className="text-white/75 normal-case tracking-normal ml-2">
          {sandboxMode ? '— Audit-only · No execution' : '— Enforcement on · Governed actions active'}
        </span>
      </button>
      {/* Header */}
      <header className="shrink-0 flex items-center px-6 h-[54px]" style={{ borderBottom:'1px solid rgba(74,222,128,0.1)', background:'rgba(7,16,11,0.97)' }}>
        <EdonLogo variant="compact" subtitle={false} />
        <div className="flex items-center gap-1.5 mx-auto">
          {Array.from({length:5},(_,i) => (
            <div key={i} className="rounded-full transition-all duration-300" style={{
              width:i+1===screen?10:6, height:i+1===screen?10:6,
              background:i+1<screen?'#4ade80':i+1===screen?'#4ade80':'rgba(255,255,255,0.1)',
              boxShadow:i+1===screen?'0 0 8px rgba(74,222,128,0.6)':'none',
            }} />
          ))}
          <span className="text-xs text-muted-foreground ml-2 tabular-nums">{screen}/5</span>
        </div>
        <button
          type="button"
          onClick={() => setModeConfirm(sandboxMode ? 'enable-live' : 'return-sandbox')}
          className="mr-3 px-2.5 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase transition-colors"
          style={{
            background: 'rgba(255,255,255,0.04)',
            color: 'rgba(255,255,255,0.7)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          Mode
        </button>
        <button onClick={onLogout} className="p-2 rounded-lg text-muted-foreground hover:text-red-400 transition-colors">
          <LogOut size={14} />
        </button>
      </header>

      {/* Body */}
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
        <div hidden aria-hidden="true">
          <input ref={inputRef} value={input} readOnly />
          <button type="button" onClick={sendMsg}>hidden</button>
          <div ref={msgEndRef} />
          <span>
            {meta.title}
            {meta.sub}
            {showInput ? '1' : '0'}
            {onboardingPresets[1][0]}
            {msgs.length}
            {isTyping ? '1' : '0'}
            {convStep}
            {busy ? '1' : '0'}
          </span>
        </div>
        {/* RIGHT - Artifact pane */}
        <div className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div key={screen} initial={{ opacity:0, x:20 }} animate={{ opacity:1, x:0 }} exit={{ opacity:0, x:-20 }} transition={{ duration:0.18 }} className="flex flex-col min-h-full">
              <div className="flex-1 p-8 space-y-6">

                {/* ?? Screen 1: Hospital Environment Detection ?? */}
                {screen===1 && (
                  <div className="max-w-3xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Hospital Environment Detection</p>
                      <h1 className="text-3xl font-bold text-white leading-tight">{orgName || 'Regional One Health'}</h1>
                      <p className="text-sm text-muted-foreground mt-2 leading-relaxed">EDON Deployment Activation</p>
                    </div>
                    <div className="grid gap-3 xl:grid-cols-[1.05fr_.95fr]">
                      <div className="rounded-2xl p-5 space-y-3" style={{ border:'1px solid rgba(74,222,128,0.16)', background:'rgba(74,222,128,0.03)' }}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60">Connect systems</p>
                            <p className="text-sm font-semibold text-white">Governed deployment activation</p>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:'rgba(74,222,128,0.08)', color:'#86efac', border:'1px solid rgba(74,222,128,0.18)' }}>READY</span>
                        </div>
                        <div className="space-y-2.5">
                          {[
                            ['Entra / Okta', 'Connected', 'Identity + MFA'],
                            ['Epic', 'Connected', 'EHR access + writeback'],
                            ['Teams', 'Connected', 'Escalation and support'],
                            ['SIEM', 'Connected', 'Audit export'],
                          ].map(([label, status, detail]) => (
                            <div key={label} className="flex items-center justify-between gap-3 rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                              <div>
                                <p className="text-sm font-semibold text-white">{label}</p>
                                <p className="text-[11px] text-muted-foreground/60 mt-0.5">{detail}</p>
                              </div>
                              <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:'rgba(34,197,94,0.08)', color:'#86efac', border:'1px solid rgba(34,197,94,0.18)' }}>{status}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-2xl p-5 space-y-3" style={{ border:'1px solid rgba(255,255,255,0.07)', background:'rgba(255,255,255,0.02)' }}>
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">Environment snapshot</p>
                          <p className="text-sm font-semibold text-white mt-1">Tenant snapshot</p>
                        </div>
                        {[
                          ['Tenant', orgName || 'Regional One Health'],
                          ['Deployment mode', tenantMode.toUpperCase()],
                          ['Market pack', 'Healthcare'],
                          ['Policy pack', 'Hospital'],
                          ['Runtime mode', sandboxMode ? 'SANDBOX' : 'LIVE'],
                        ].map(([label, value]) => (
                          <div key={label} className="flex items-center justify-between rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{label}</span>
                            <span className="text-sm font-semibold text-white">{value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* ?? Screen 2: Connector Verification ?? */}
                {screen===2 && (
                  <div className="max-w-3xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Connector Verification</p>
                      <h1 className="text-3xl font-bold text-white">Infrastructure Verification</h1>
                    </div>
                    <div className="grid gap-3 xl:grid-cols-[1.1fr_.9fr]">
                      <div className="rounded-2xl overflow-hidden" style={{ border:'1px solid rgba(255,255,255,0.08)' }}>
                        <div className="grid grid-cols-[1.05fr_.65fr_.75fr_.85fr] px-5 py-3 text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60" style={{ background:'rgba(255,255,255,0.03)', borderBottom:'1px solid rgba(255,255,255,0.06)' }}>
                          <span>Connector</span><span>Drift</span><span>Certified</span><span>Last Verified</span>
                        </div>
                        {connectorRows.map(([connector, drift, cert, lastVerified]) => (
                          <button
                            key={connector}
                            onClick={() => setSelectedConnector(connector as 'Entra'|'Epic'|'Teams'|'SIEM')}
                            className="w-full grid grid-cols-[1.05fr_.65fr_.75fr_.85fr] px-5 py-4 text-left items-center transition-colors"
                            style={{ background:selectedConnector===connector?'rgba(74,222,128,0.08)':'rgba(255,255,255,0.02)', borderBottom:'1px solid rgba(255,255,255,0.05)' }}
                          >
                            <span className="text-sm font-semibold text-white">{connector}</span>
                            <span className="text-xs text-white/70">{drift}</span>
                            <span className="text-xs text-emerald-400">{cert}</span>
                            <span className="text-xs text-white/70">{lastVerified}</span>
                          </button>
                        ))}
                      </div>
                      <div className="rounded-2xl p-5 space-y-3" style={{ border:'1px solid rgba(245,158,11,0.18)', background:'rgba(245,158,11,0.03)' }}>
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-amber-400/70">Connector detail drawer</p>
                          <p className="text-sm font-semibold text-white mt-1">{selectedConnector}</p>
                        </div>
                        <div className="space-y-2">
                          {connectorDetails[selectedConnector].scopes.map(scope => (
                            <div key={scope} className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                              <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">Allowed scopes</p>
                              <p className="text-sm font-semibold text-white mt-1">{scope}</p>
                            </div>
                          ))}
                        </div>
                        {[
                          ['Certification version', connectorDetails[selectedConnector].certification],
                          ['Drift status', connectorDetails[selectedConnector].drift],
                          ['Last verified', connectorDetails[selectedConnector].lastVerified],
                          ['Permissions', connectorDetails[selectedConnector].permissions],
                          ['Governance mode', connectorDetails[selectedConnector].mode],
                          ['Rollback support', connectorDetails[selectedConnector].rollback],
                          ['Audit guarantees', connectorDetails[selectedConnector].audit],
                        ].map(([label, value]) => (
                          <div key={label} className="flex items-center justify-between rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/50">{label}</span>
                            <span className="text-sm font-semibold text-white text-right">{value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-2xl p-4" style={{ border:'1px solid rgba(74,222,128,0.16)', background:'rgba(74,222,128,0.03)' }}>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60">Connector trust summary</p>
                      <p className="text-sm text-white/80 mt-1">Certified connectors show drift, version, last validation, rollback state, and audit guarantees.</p>
                    </div>
                  </div>
                )}

                {/* ?? Screen 3: Governance Activation ?? */}
                {screen===3 && (
                  <div className="max-w-3xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Governance Activation</p>
                      <h1 className="text-3xl font-bold text-white">Operational Trust Layer</h1>
                    </div>
                    <div className="grid gap-3 xl:grid-cols-2">
                      <div className="rounded-2xl p-5 space-y-3" style={{ border:'1px solid rgba(74,222,128,0.18)', background:'rgba(74,222,128,0.03)' }}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60">Governance readiness</p>
                            <p className="text-sm font-semibold text-white">{sandboxMode ? 'Sandbox mode active' : 'Live governance active'}</p>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:sandboxMode ? 'rgba(59,130,246,0.08)' : 'rgba(74,222,128,0.08)', color:sandboxMode ? '#93c5fd' : '#86efac', border:sandboxMode ? '1px solid rgba(59,130,246,0.18)' : '1px solid rgba(74,222,128,0.18)' }}>{sandboxMode ? 'SANDBOX' : 'LIVE'}</span>
                        </div>
                        <div className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                          <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">Current enforcement posture</p>
                          <p className="text-sm font-semibold text-white mt-1">{sandboxMode ? 'Audit-only. No execution. No writeback.' : `Live enforcement armed for ${tenantMode.toUpperCase()} mode.`}</p>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {readinessChecks.map(([label, status]) => (
                            <div key={label} className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                              <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">{label}</p>
                              <p className="text-sm font-semibold text-white mt-1">{status}</p>
                            </div>
                          ))}
                        </div>
                        <div className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                          <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">Deployment classification</p>
                          <p className="text-sm font-semibold text-white mt-1">{sandboxMode ? 'SANDBOX — audit-only' : `${tenantMode.toUpperCase()} — ${tenantMode === 'advisory' ? 'audit-only' : tenantMode === 'governed' ? 'approval-bound execution' : 'policy-scoped automation'}`}</p>
                        </div>
                      </div>
                      <div className="rounded-2xl p-5 space-y-3" style={{ border:'1px solid rgba(59,130,246,0.18)', background:'rgba(59,130,246,0.03)' }}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-sky-400/70">Healthcare compliance</p>
                            <p className="text-sm font-semibold text-white">PHI control posture</p>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:'rgba(59,130,246,0.08)', color:'#93c5fd', border:'1px solid rgba(59,130,246,0.18)' }}>VERIFIED</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {complianceChecks.slice(0, 6).map(([label, status]) => (
                            <div key={label} className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                              <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">{label}</p>
                              <p className="text-sm font-semibold text-white mt-1">{status}</p>
                            </div>
                          ))}
                        </div>
                        <div className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.05)' }}>
                          <p className="text-[9px] uppercase tracking-widest text-muted-foreground/50">Pilot safety mode</p>
                          <p className="text-sm font-semibold text-white mt-1">Fail-closed on connector uncertainty. No autonomous high-risk execution. Rollback required where supported.</p>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(244,114,182,0.18)', background:'rgba(244,114,182,0.03)' }}>
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-pink-400/70">Autonomy boundaries</p>
                          <p className="text-sm font-semibold text-white">EDON stays within approval-bound clinical controls</p>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:'rgba(244,114,182,0.08)', color:'#f9a8d4', border:'1px solid rgba(244,114,182,0.18)' }}>GUARDED</span>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {['Medication execution remains approval-bound', 'Epic permissions remain enforced', 'Clinical overrides require human approval', 'All governed actions are fully audited'].map(item => (
                          <div key={item} className="rounded-xl px-3 py-2.5" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.05)' }}>
                            <p className="text-sm text-white/85">{item}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-2xl p-4 space-y-3" style={{ border:'1px solid rgba(255,255,255,0.07)', background:'rgba(255,255,255,0.02)' }}>
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">Mode switch</p>
                          <p className="text-sm font-semibold text-white">{sandboxMode ? 'Sandbox first. Live enforcement only after approval.' : 'Live governance is enabled for the tenant.'}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setModeConfirm(sandboxMode ? 'enable-live' : 'return-sandbox')}
                          className="text-[10px] px-2.5 py-1 rounded-full font-semibold uppercase tracking-widest transition-colors"
                          style={{ background:sandboxMode ? 'rgba(59,130,246,0.08)' : 'rgba(74,222,128,0.08)', color:sandboxMode ? '#93c5fd' : '#86efac', border:sandboxMode ? '1px solid rgba(59,130,246,0.18)' : '1px solid rgba(74,222,128,0.18)' }}
                        >
                          {liveActionLabel}
                        </button>
                      </div>
                      {sandboxMode && (
                        <div className="rounded-xl px-3 py-2.5" style={{ background:'rgba(59,130,246,0.06)', border:'1px solid rgba(59,130,246,0.14)' }}>
                          <p className="text-[9px] uppercase tracking-widest text-sky-400/70">Sandbox mode</p>
                          <p className="text-sm text-white/80 mt-1">All actions are audit-only until you enable live governance.</p>
                        </div>
                      )}
                      <div className="grid grid-cols-3 gap-2">
                        {modeCards.map(([value, label, desc]) => (
                          <button
                            key={value}
                            onClick={() => setTenantMode(value)}
                            className="rounded-xl px-3 py-2.5 text-left transition-colors"
                            style={{ background:tenantMode===value?'rgba(74,222,128,0.12)':'rgba(255,255,255,0.03)', border:tenantMode===value?'1px solid rgba(74,222,128,0.3)':'1px solid rgba(255,255,255,0.05)' }}
                          >
                            <p className="text-sm font-semibold text-white">{label}</p>
                            <p className="text-[10px] text-muted-foreground mt-1 leading-tight">{desc}</p>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(168,85,247,0.18)', background:'rgba(168,85,247,0.03)' }}>
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-violet-400/70">Policy pack</p>
                          <p className="text-sm font-semibold text-white">{bundle ? `Ready — ${bundle.total_count} rules across 3 layers` : 'Pending policy snapshot'}</p>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background:'rgba(168,85,247,0.08)', color:'#d8b4fe', border:'1px solid rgba(168,85,247,0.18)' }}>AT THE CORE</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* ?? Screen 4: Governed Action Readiness ?? */}
                {screen===4 && (
                  <div className="max-w-3xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Governed Action Readiness</p>
                      <h1 className="text-3xl font-bold text-white">Operational Boundaries</h1>
                    </div>
                    <div className="rounded-2xl overflow-hidden" style={{ border:'1px solid rgba(255,255,255,0.08)' }}>
                      <div className="grid grid-cols-[1.2fr_.9fr_.9fr_.8fr_.6fr] px-5 py-3 text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60" style={{ background:'rgba(255,255,255,0.03)', borderBottom:'1px solid rgba(255,255,255,0.06)' }}>
                        <span>Workflow</span><span>Governance Mode</span><span>Approval</span><span>Rollback</span><span>Audit</span>
                      </div>
                      {governedActionRows.map(([workflow, mode, approval, rollback, audit], i) => (
                        <div key={workflow} className="grid grid-cols-[1.2fr_.9fr_.9fr_.8fr_.6fr] px-5 py-4 text-xs gap-2 items-center" style={{ borderBottom:i<governedActionRows.length-1?'1px solid rgba(255,255,255,0.04)':'none' }}>
                          <span className="font-semibold text-white text-sm">{workflow}</span>
                          <span className="text-white/75">{mode}</span>
                          <span className="text-white/75">{approval}</span>
                          <span className="text-white/75">{rollback}</span>
                          <span className="text-emerald-400">{audit}</span>
                        </div>
                      ))}
                    </div>
                    <div className="grid gap-3 xl:grid-cols-2">
                      <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(74,222,128,0.18)', background:'rgba(74,222,128,0.03)' }}>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60">Operational boundaries</p>
                        <p className="text-sm text-white/80">EDON controls draft notes, writeback, escalations, and medication execution according to the selected governance mode.</p>
                      </div>
                      <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(244,114,182,0.18)', background:'rgba(244,114,182,0.03)' }}>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-pink-400/70">High-risk boundary</p>
                        <p className="text-sm text-white/80">Medication execution is disabled until the tenant is explicitly certified for governed execution.</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* ?? Screen 5: Procurement Readiness ?? */}
                {screen===5 && (
                  <div className="max-w-3xl space-y-5">
                    <div>
                      <p className="text-[11px] font-bold tracking-widest text-emerald-500/50 uppercase mb-1.5">Procurement Readiness</p>
                      <h1 className="text-3xl font-bold text-white">Pilot Environment Ready</h1>
                    </div>
                    <div className="rounded-2xl overflow-hidden" style={{ border:'1px solid rgba(255,255,255,0.08)' }}>
                      <div className="grid grid-cols-[1.2fr_.8fr] px-5 py-3 text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60" style={{ background:'rgba(255,255,255,0.03)', borderBottom:'1px solid rgba(255,255,255,0.06)' }}>
                        <span>Requirement</span><span>Status</span>
                      </div>
                      {procurementRows.map(([requirement, status], i) => (
                        <div key={requirement} className="grid grid-cols-[1.2fr_.8fr] px-5 py-4 text-xs gap-2 items-center" style={{ borderBottom:i<procurementRows.length-1?'1px solid rgba(255,255,255,0.04)':'none' }}>
                          <span className="font-semibold text-white text-sm">{requirement}</span>
                          <span className="text-emerald-400">{status}</span>
                        </div>
                      ))}
                    </div>
                    <div className="grid gap-3 xl:grid-cols-2">
                      <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(74,222,128,0.18)', background:'rgba(74,222,128,0.03)' }}>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60">Evidence pack</p>
                        <p className="text-sm text-white/80">HIPAA controls, audit integrity, tenant isolation, restore drill, MFA enforcement, and connector certification are ready for review.</p>
                      </div>
                      <div className="rounded-2xl p-4 space-y-2" style={{ border:'1px solid rgba(245,158,11,0.18)', background:'rgba(245,158,11,0.03)' }}>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-amber-400/70">Tenant manifest</p>
                        <p className="text-sm text-white/80">{tenantManifest.org_name} ? {tenantManifest.deployment_mode} ? {tenantManifest.market_pack} / {tenantManifest.policy_pack}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              {/* CTA bar */}
              {ctaReady && (
                <div className="px-8 pb-8 pt-4 shrink-0" style={{ borderTop:'1px solid rgba(255,255,255,0.04)' }}>
                  <button onClick={handleCTA} disabled={busy || (screen===5 && !simDone)}
                    className="w-full flex items-center justify-center gap-2.5 py-4 rounded-2xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background:screen===5?'rgba(74,222,128,0.22)':'rgba(74,222,128,0.12)',
                      border:screen===5?'2px solid rgba(74,222,128,0.5)':'1px solid rgba(74,222,128,0.28)',
                      color:'#86efac',
                      boxShadow:screen===5?'0 0 24px rgba(74,222,128,0.12)':'none',
                    }}>
                    {busy ? <RefreshCw size={16} className="animate-spin" /> : screen===5 ? <Zap size={16} /> : <ChevronRight size={16} />}
                    {busy ? 'Activating...' : CTA_LABELS[screen]}
                  </button>
                </div>
              )}

            </motion.div>
          </AnimatePresence>
        </div>

      </div>
      {modeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-md rounded-2xl p-5 shadow-2xl" style={{ border:'1px solid rgba(255,255,255,0.12)', background:'rgba(7,16,11,0.98)' }}>
            <p className="text-[10px] font-bold uppercase tracking-widest text-amber-400/80">Mode change confirmation</p>
            <h2 className="mt-2 text-xl font-bold text-white">
              {modeConfirm === 'enable-live' ? 'Enable live governance?' : 'Return to sandbox?'}
            </h2>
            <p className="mt-3 text-sm text-white/80 leading-relaxed">
              {modeConfirm === 'enable-live'
                ? 'This will turn off sandbox mode. Governed actions may execute against connected systems, enforcement will be on, and all actions will continue to be audited.'
                : 'This will return the tenant to audit-only sandbox mode. Live enforcement will pause until you enable it again.'}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setModeConfirm(null)}
                className="rounded-xl px-4 py-3 text-sm font-semibold text-white/80 transition-colors"
                style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.08)' }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmModeChange}
                className="rounded-xl px-4 py-3 text-sm font-semibold transition-colors"
                style={{
                  background: modeConfirm === 'enable-live' ? 'rgba(74,222,128,0.18)' : 'rgba(59,130,246,0.18)',
                  color: modeConfirm === 'enable-live' ? '#86efac' : '#93c5fd',
                  border: modeConfirm === 'enable-live' ? '1px solid rgba(74,222,128,0.3)' : '1px solid rgba(59,130,246,0.3)',
                }}
              >
                {modeConfirm === 'enable-live' ? 'Enable Live' : 'Return to Sandbox'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function HealthcareAccessGate({ onEnter }: { onEnter: () => void }) {
  const [name, setName]       = useState('Avery Brooks')
  const [dept, setDept]       = useState('Clinical AI Lead')
  const [key, setKey]         = useState('edon_demo_st_mercy')
  const [showKey, setShowKey] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !dept.trim() || !key.trim()) return
    setLoading(true)
    setTimeout(() => { setLoading(false); onEnter() }, 800)
  }

  const valueProps = [
    { icon: Shield,        title: 'HIPAA-grade governance',      body: 'Every AI action logged, scored, and escalated before it touches patient data.' },
    { icon: ClipboardList, title: 'Clinical approval workflows',  body: 'Nurse → Physician tiered sign-off built in. Joint Commission and HITRUST presets ready on day one.' },
    { icon: Activity,      title: 'Real-time patient safety',     body: 'Critical-urgency blocks page on-call in seconds. Zero trust for medication and care-plan AI.' },
  ]

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">

      {/* ── Left panel: value props ── */}
      <div className="hidden lg:flex flex-col justify-between w-[46%] min-h-screen p-12 border-r border-white/[0.06] bg-gradient-to-br from-black via-[#0a0a0f] to-[#050510] relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full blur-3xl opacity-10 bg-rose-500" />
          <div className="absolute -bottom-32 -right-32 w-96 h-96 rounded-full blur-3xl opacity-[0.08] bg-cyan-500" />
        </div>

        <div className="relative z-10">
          <div className="mb-16">
            <EdonLogo />
          </div>
          <motion.div initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2 }} className="space-y-10">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3 text-rose-400">Healthcare</p>
              <h2 className="text-3xl font-bold leading-tight text-foreground">
                AI governance for<br />the industries that<br />can't get it wrong.
              </h2>
              <p className="text-sm text-muted-foreground mt-4 leading-relaxed max-w-sm">
                Every AI action governed, logged, and auditable — before it reaches a patient, a customer, or a regulator.
              </p>
            </div>
            <div className="space-y-4">
              {valueProps.map((vp, i) => (
                <motion.div key={vp.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                  className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 mt-0.5 border-rose-500/25 bg-rose-500/[0.08]">
                    <vp.icon size={14} className="text-rose-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">{vp.title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{vp.body}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>

        <div className="relative z-10">
          <p className="text-[11px] text-muted-foreground/50">HIPAA · HITRUST · Joint Commission</p>
        </div>
      </div>

      {/* ── Right panel: form ── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md space-y-7">
          <div className="lg:hidden">
            <EdonLogo variant="compact" />
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-5 h-5 rounded-md bg-rose-500/15 border border-rose-500/25 flex items-center justify-center">
                <Cross size={11} className="text-rose-400" />
              </div>
              <span className="text-xs font-semibold text-rose-400 uppercase tracking-widest">St. Mercy Health System</span>
            </div>
            <h1 className="text-xl font-bold">Access your console</h1>
            <p className="text-sm text-muted-foreground mt-1">Experience end-to-end HIPAA AI governance — 500 simulated agents, real policies.</p>
          </div>

          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl border border-rose-500/30 bg-rose-500/[0.08]">
            <Heart size={14} className="text-rose-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-rose-400">Healthcare · HIPAA Mode</p>
              <p className="text-[11px] text-muted-foreground/60">Hospitals · Clinics · Health Systems</p>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-rose-500/25 text-rose-400/70 font-medium tracking-wider">DEMO</span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block font-medium">Your Name</label>
                <input type="text" value={name} onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl bg-muted/40 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="Dr. Chen" required autoFocus />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block font-medium">Role</label>
                <div className="relative">
                  <select value={dept} onChange={e => setDept(e.target.value)}
                    className="dept-select w-full pl-3 pr-8 py-2.5 rounded-xl border border-white/10 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer bg-black/30"
                    style={DARK_SELECT_STYLE}
                    required>
                    <option value="" disabled>Select…</option>
                    <option>Attending Physician</option>
                    <option>Charge Nurse</option>
                    <option>Clinical AI Lead</option>
                    <option>Compliance Officer</option>
                    <option>IT / DevOps</option>
                    <option>Administrator</option>
                  </select>
                  <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block font-medium">Demo Access Key</label>
              <div className="relative">
                <input type={showKey ? 'text' : 'password'} value={key} onChange={e => setKey(e.target.value)}
                  className="w-full px-3 py-2.5 pr-10 rounded-xl bg-muted/40 border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                  placeholder="edon_demo_…" required />
                <button type="button" onClick={() => setShowKey(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground/50 mt-1">Any non-empty value · This is a demo environment.</p>
            </div>

            <button type="submit" disabled={loading}
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2 mt-1">
              {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Shield size={14} />}
              {loading ? 'Starting demo…' : 'Connect to Gateway'}
            </button>
          </form>

          <p className="text-[11px] text-muted-foreground/50 text-center">
            Simulated data only · No patient information is used or displayed
          </p>
        </motion.div>
      </div>
    </div>
  )
}

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
    allow: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    block: 'bg-red-500/15 text-red-400 border-red-500/30',
    escalate: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    default: 'bg-white/5 text-muted-foreground border-white/10',
    outline: 'bg-transparent text-foreground border-white/20',
    green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    amber: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    red: 'bg-red-500/15 text-red-400 border-red-500/30',
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
    ghost: 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-white/5',
  }
  const sizes: Record<string, string> = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
  }
  return (
    <button className={cn(base, variants[variant], sizes[size], className)} {...props}>
      {children}
    </button>
  )
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full bg-secondary border border-white/10 rounded-xl px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all',
        className,
      )}
      {...props}
    />
  )
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string
  change?: string
  changePositive?: boolean
  icon: LucideIcon
  accentClass?: string
  delay?: number
}

function StatCard({ label, value, change, changePositive, icon: Icon, accentClass = 'text-primary', delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      className="glass-card-hover p-5"
    >
      <div
        className="absolute inset-0 opacity-20 rounded-2xl pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 80% 0%, hsl(142 70% 45% / 0.12) 0%, transparent 70%)',
        }}
      />
      <div className="relative">
        <div className="flex items-start justify-between mb-3">
          <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">{label}</p>
          <div className={cn('p-2 rounded-lg bg-white/5', accentClass)}>
            <Icon size={16} />
          </div>
        </div>
        <p className="text-2xl font-bold text-foreground tabular-nums">{value}</p>
        {change && (
          <p className={cn('text-xs mt-1', changePositive ? 'text-emerald-400' : 'text-red-400')}>
            {change}
          </p>
        )}
      </div>
    </motion.div>
  )
}

// ─── Verdict helpers ──────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  if (verdict === 'ALLOW') return <Badge variant="allow"><CheckCircle2 size={10} />ALLOW</Badge>
  if (verdict === 'BLOCK') return <Badge variant="block"><XCircle size={10} />BLOCK</Badge>
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
  const diffMs = now.getTime() - ts.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  return `${Math.floor(diffMin / 60)}h ago`
}

// ─── Dashboard Tab ────────────────────────────────────────────────────────────

const BLOCK_REASON_LABELS: Record<string, string> = {
  HIPAA_VIOLATION: 'HIPAA Violation',
  UNAUTHORIZED_ACCESS: 'Unauthorized Access',
  SCOPE_VIOLATION: 'Scope Violation',
  CONSENT_MISSING: 'Consent Missing',
  CONTROLLED_SUBSTANCE: 'Controlled Substance',
  PROTOCOL_DEVIATION: 'Protocol Deviation',
  FDA_COMPLIANCE: 'FDA Compliance',
}

function computeBlockReasonCounts(events: DemoEvent[]) {
  const counts: Record<string, number> = {}
  for (const e of events) {
    if (e.verdict === 'BLOCK' && e.reasonCode) {
      counts[e.reasonCode] = (counts[e.reasonCode] ?? 0) + 1
    }
  }
  return Object.entries(counts)
    .map(([k, v]) => ({ key: k, label: BLOCK_REASON_LABELS[k] ?? k, count: v }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)
}

function computeDeptActivity(events: DemoEvent[]) {
  const total: Record<string, number> = {}
  const blocked: Record<string, number> = {}
  for (const e of events) {
    total[e.department] = (total[e.department] ?? 0) + 1
    if (e.verdict === 'BLOCK') blocked[e.department] = (blocked[e.department] ?? 0) + 1
  }
  return DEPARTMENTS.slice(0, 8).map(d => ({
    key: d.key,
    label: d.label,
    icon: d.icon,
    color: d.color,
    total: total[d.key] ?? 0,
    blocked: blocked[d.key] ?? 0,
    blockPct: total[d.key] ? Math.round(((blocked[d.key] ?? 0) / total[d.key]) * 100) : 0,
  }))
}

interface DashboardTabProps {
  displayCount: number
  speed: number
  setSpeed: (s: number) => void
  paused: boolean
  setPaused: (p: boolean) => void
  onReset: () => void
  uptime: number
  latency: number
  deptModes: Record<string, 'sandbox' | 'governed'>
  onDeptModeChange: (deptKey: string, mode: 'sandbox' | 'governed') => void
  coordinationAllowed: Record<string, boolean>
  onCoordinationToggle: (deptKey: string) => void
}

function DashboardTab(props: DashboardTabProps) {
  const { displayCount, speed, setSpeed, paused, setPaused, onReset, uptime, latency, deptModes, onDeptModeChange, onCoordinationToggle } = props
  const visibleEvents = ALL_EVENTS.slice(0, displayCount)
  const feedEvents = visibleEvents.slice(0, 25)
  const blockReasons = computeBlockReasonCounts(visibleEvents)
  const deptActivity = computeDeptActivity(visibleEvents)
  const maxBlockCount = Math.max(1, ...blockReasons.map(r => r.count))
  const maxDeptTotal = Math.max(1, ...deptActivity.map(d => d.total))

  const totalGoverned = 48291 + displayCount
  const totalBlocked = 14837 + Math.floor(visibleEvents.filter(e => e.verdict === 'BLOCK').length * 0.5)
  const totalEscalated = 1204 + visibleEvents.filter(e => e.verdict === 'ESCALATE').length

  const uptimeDays = Math.floor(uptime / 86400)
  const uptimeHrs = Math.floor((uptime % 86400) / 3600)
  const uptimeMins = Math.floor((uptime % 3600) / 60)

  const p50 = (latency * 0.6).toFixed(1)
  const p95 = (latency * 1.8).toFixed(1)
  const p99 = (latency * 2.8).toFixed(1)
  const [coordDeptIndex, setCoordDeptIndex] = useState(0)
  const coordDept = DEPARTMENTS[coordDeptIndex % DEPARTMENTS.length]
  const coordEnabled = props.coordinationAllowed[coordDept.key] ?? true
  const [sandboxDeptIndex, setSandboxDeptIndex] = useState(0)
  const sandboxDept = DEPARTMENTS[sandboxDeptIndex % DEPARTMENTS.length]
  const sandboxDeptMode = deptModes[sandboxDept.key] ?? 'governed'

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Healthcare Governance</h1>
        <p className="text-muted-foreground text-sm mt-1">
          🏥 St. Mercy Health System · <span className="text-primary font-medium">500 agents online</span> · Clinical Safety Mode
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Governed" value={totalGoverned.toLocaleString()} change="+1 every 800ms" changePositive icon={BarChart3} delay={0} />
        <StatCard label="Blocked" value={totalBlocked.toLocaleString()} change="30.7% block rate" accentClass="text-red-400" icon={XCircle} delay={0.05} />
        <StatCard label="Escalated" value={totalEscalated.toLocaleString()} change="Awaiting physician review" accentClass="text-amber-400" icon={AlertTriangle} delay={0.1} />
        <StatCard label="Avg Latency" value={`${latency.toFixed(1)}ms`} change="Well within 50ms SLO" changePositive accentClass="text-blue-400" icon={Zap} delay={0.15} />
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
                  <th className="text-left pb-2 font-medium hidden md:table-cell">Action</th>
                  <th className="text-left pb-2 font-medium hidden lg:table-cell">Reason</th>
                  <th className="text-right pb-2 font-medium">ms</th>
                  <th className="text-right pb-2 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {feedEvents.map((e, idx) => (
                    <motion.tr
                      key={e.id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx === 0 ? 0 : 0, duration: 0.25 }}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="py-2 pr-2"><VerdictBadge verdict={e.verdict} /></td>
                      <td className="py-2 pr-2">
                        <div className="flex items-center gap-1.5">
                          <DeptIcon deptKey={e.department} size={12} />
                          <span className="font-mono text-foreground">{e.agent}</span>
                          <span
                            className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                            style={{
                              background: (deptModes[e.department] ?? 'governed') === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                              color: (deptModes[e.department] ?? 'governed') === 'sandbox' ? '#93c5fd' : '#86efac',
                              border: (deptModes[e.department] ?? 'governed') === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                            }}
                          >
                            {(deptModes[e.department] ?? 'governed') === 'sandbox' ? 'sandbox' : 'governed'}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 pr-2 hidden md:table-cell">
                        <span className="text-muted-foreground truncate max-w-[200px] block">{fmtOp(e.toolOp)}</span>
                      </td>
                      <td className="py-2 pr-2 hidden lg:table-cell">
                        {e.reasonCode ? (
                          <span className="text-red-400 font-medium">{fmtReason(e.reasonCode)}</span>
                        ) : (
                          <span className="text-muted-foreground/40">—</span>
                        )}
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
              <Shield size={14} className="text-primary" />
              <h2 className="font-semibold text-sm text-foreground">Active Policy</h2>
              <Badge variant="green" className="ml-auto">ACTIVE</Badge>
            </div>
            <p className="text-sm font-medium text-foreground mb-3">Clinical Safety Mode</p>
            <div className="space-y-2">
              {[
                { label: 'HIPAA Enforcement', status: 'ENFORCED' },
                { label: 'FDA Compliance', status: 'ENFORCED' },
                { label: 'Consent Validation', status: 'ENFORCED' },
                { label: 'Audit Chain', status: 'VERIFIED' },
              ].map(item => (
                <div key={item.label} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 size={10} /> {item.status}
                  </span>
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

          {/* Department Sandbox */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Shield size={14} className="text-sky-400" />
              <h2 className="font-semibold text-sm text-foreground">Department Sandbox</h2>
              <Badge variant="outline" className="ml-auto">Scoped rollout</Badge>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              Keep the tenant live while new departments validate in sandbox.
            </p>
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setSandboxDeptIndex(i => (i - 1 + DEPARTMENTS.length) % DEPARTMENTS.length)}
                  className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                  aria-label="Previous sandbox department"
                >
                  <ChevronLeft size={15} className="text-foreground/80" />
                </button>
                <div className="min-w-0 text-center">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department {sandboxDeptIndex + 1} / {DEPARTMENTS.length}</p>
                  <p className="text-sm font-semibold text-foreground truncate">{sandboxDept.label}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSandboxDeptIndex(i => (i + 1) % DEPARTMENTS.length)}
                  className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                  aria-label="Next sandbox department"
                >
                  <ChevronRight size={15} className="text-foreground/80" />
                </button>
              </div>
              <div className="flex items-center gap-2 rounded-xl px-3 py-2.5 border border-white/5 bg-black/10">
                <sandboxDept.icon size={12} className={sandboxDept.color} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground truncate">{sandboxDept.label}</p>
                  <p className="text-[10px] text-muted-foreground/60">{sandboxDeptMode === 'sandbox' ? 'Sandbox' : 'Governed'}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onDeptModeChange(sandboxDept.key, sandboxDeptMode === 'sandbox' ? 'governed' : 'sandbox')}
                  className="shrink-0 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-widest transition-colors"
                  style={{
                    background: sandboxDeptMode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                    color: sandboxDeptMode === 'sandbox' ? '#93c5fd' : '#86efac',
                    border: sandboxDeptMode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                  }}
                >
                  {sandboxDeptMode === 'sandbox' ? 'Enable live' : 'Sandbox'}
                </button>
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
                <span>Use the arrows to step through every department.</span>
                <span>{sandboxDeptMode === 'sandbox' ? 'Held in sandbox' : 'Live governed'}</span>
              </div>
            </div>
          </div>

          {/* Cross-department coordination */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Link2 size={14} className="text-violet-400" />
              <h2 className="font-semibold text-sm text-foreground">Cross-Department Coordination</h2>
              <Badge variant="outline" className="ml-auto">Admin control</Badge>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              Choose which departments may participate in cross-department coordination.
            </p>
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setCoordDeptIndex(i => (i - 1 + DEPARTMENTS.length) % DEPARTMENTS.length)}
                  className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                  aria-label="Previous department"
                >
                  <ChevronLeft size={15} className="text-foreground/80" />
                </button>
                <div className="min-w-0 text-center">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department {coordDeptIndex + 1} / {DEPARTMENTS.length}</p>
                  <p className="text-sm font-semibold text-foreground truncate">{coordDept.label}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setCoordDeptIndex(i => (i + 1) % DEPARTMENTS.length)}
                  className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                  aria-label="Next department"
                >
                  <ChevronRight size={15} className="text-foreground/80" />
                </button>
              </div>
              <div className="flex items-center gap-2 rounded-xl px-3 py-2.5 border border-white/5 bg-black/10">
                <coordDept.icon size={12} className={coordDept.color} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground truncate">{coordDept.label}</p>
                  <p className="text-[10px] text-muted-foreground/60">{coordEnabled ? 'Allowed to coordinate' : 'Held out of coordination'}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onCoordinationToggle(coordDept.key)}
                  className="shrink-0 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-widest transition-colors"
                  style={{
                    background: coordEnabled ? 'rgba(74,222,128,0.10)' : 'rgba(245,158,11,0.10)',
                    color: coordEnabled ? '#86efac' : '#fbbf24',
                    border: coordEnabled ? '1px solid rgba(74,222,128,0.22)' : '1px solid rgba(245,158,11,0.22)',
                  }}
                >
                  {coordEnabled ? 'Allowed' : 'Held'}
                </button>
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
                <span>Use the arrows to review every department.</span>
                <span>{coordEnabled ? 'In coordination' : 'Excluded'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Second row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Block reasons chart */}
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
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(r.count / maxBlockCount) * 100}%` }}
                    transition={{ delay: i * 0.05, duration: 0.6 }}
                    className="h-full rounded-full bg-red-400"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Dept activity */}
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} className="text-emerald-400" />
            <h2 className="font-semibold text-sm text-foreground">Department Activity</h2>
          </div>
          <div className="space-y-2.5">
            {deptActivity.map((d, i) => {
              const Icon = d.icon
              const mode = deptModes[d.key] ?? 'governed'
              return (
                <div key={d.key} className="flex items-center gap-2">
                  <Icon size={12} className={d.color} />
                  <span className="text-muted-foreground text-xs w-28 shrink-0 truncate">{d.label}</span>
                  <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(d.total / maxDeptTotal) * 100}%` }}
                      transition={{ delay: i * 0.04, duration: 0.5 }}
                      className="h-full rounded-full bg-emerald-400/60"
                    />
                  </div>
                  <span className="text-xs text-red-400 w-10 text-right shrink-0">{d.blockPct}%</span>
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold shrink-0 uppercase tracking-widest"
                    style={{
                      background: mode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                      color: mode === 'sandbox' ? '#93c5fd' : '#86efac',
                      border: mode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                    }}
                  >
                    {mode}
                  </span>
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
            <Button
              key={s}
              variant={speed === s ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSpeed(s)}
            >
              {s}×
            </Button>
          ))}
          <div className="w-px h-5 bg-white/10" />
          <Button variant="outline" size="sm" onClick={() => setPaused(!paused)}>
            {paused ? '▶ Resume' : '⏸ Pause'}
          </Button>
          <Button variant="ghost" size="sm" onClick={onReset}>
            ↺ Reset
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {displayCount.toLocaleString()} / 1,000 events streamed
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── Agents Tab ───────────────────────────────────────────────────────────────

// Cross-agent chain events — show coordination story across departments
interface HCCrossEvent {
  id: string
  patientId: string
  patientLabel: string
  chain: Array<{ dept: string; deptLabel: string; verdict: 'BLOCK' | 'ESCALATE' | 'ALLOW'; toolOp: string; delay: string; note: string }>
  summary: string
  ts: Date
}

const HC_CROSS_EVENTS: HCCrossEvent[] = [
  {
    id: 'hxev_001',
    patientId: 'P-82341',
    patientLabel: 'P-82341 · F/67 · Rm 4N-08',
    chain: [
      { dept: 'monitoring', deptLabel: 'Patient Monitoring', verdict: 'ESCALATE', toolOp: 'critical.alert.escalate',       delay: 'trigger', note: 'SpO₂ 88% (↓ from 96% over 14 min), RR 28, HR 124 — rapid response team requested' },
      { dept: 'nurse',      deptLabel: 'Nurse Assist AI',    verdict: 'ALLOW',    toolOp: 'alert.trigger.nurse',           delay: '+3s',     note: 'STAT nurse alert dispatched to Floor 4N — context_id P-82341 attached' },
      { dept: 'pharmacy',   deptLabel: 'Pharmacy',           verdict: 'BLOCK',    toolOp: 'controlled.substance.dispense', delay: '+12s',    note: 'Morphine 4mg IV order auto-held — opioid contraindicated during active respiratory distress flag' },
      { dept: 'ehr',        deptLabel: 'EHR / Records',      verdict: 'BLOCK',    toolOp: 'patient.discharge.approve',     delay: '+21s',    note: 'Same-day discharge approval rejected — open critical alert (ctx: P-82341) must be cleared first' },
    ],
    summary: 'Bedside monitoring agent detected a sustained SpO₂ decline to 88%. Within 3 seconds EDON dispatched a nurse alert. Within 21 seconds it had auto-held a pending morphine order from Pharmacy and blocked an EHR discharge approval — all triggered by a single patient context flag, with zero manual coordination.',
    ts: new Date(Date.now() - 4 * 60000),
  },
  {
    id: 'hxev_002',
    patientId: 'P-61097',
    patientLabel: 'P-61097 · M/54 · Cardiac ICU',
    chain: [
      { dept: 'lab',        deptLabel: 'Clinical Lab',   verdict: 'ESCALATE', toolOp: 'critical.alert.escalate',      delay: 'trigger', note: 'Troponin-I 4.2 ng/mL (ref <0.04) — STEMI pattern confirmed, critical lab value auto-flagged' },
      { dept: 'cardiology', deptLabel: 'Cardiology',     verdict: 'ESCALATE', toolOp: 'high.risk.medication.approve', delay: '+9s',     note: 'Heparin 80 u/kg bolus order escalated to attending — cannot auto-approve while critical alert active on P-61097' },
      { dept: 'scheduling', deptLabel: 'Scheduling',     verdict: 'BLOCK',    toolOp: 'patient.discharge.approve',    delay: '+26s',    note: 'Elective discharge scheduling attempt blocked — patient flagged for urgent cath lab intervention' },
      { dept: 'ehr',        deptLabel: 'EHR / Records',  verdict: 'ALLOW',    toolOp: 'ehr.record.read',              delay: '+9s',     note: 'Full chart access fast-tracked for cardiology team — read-only, within emergency scope' },
    ],
    summary: 'Lab agent auto-flagged a troponin-I of 4.2 ng/mL — 100× above reference range, indicating STEMI. EDON escalated Cardiology\'s heparin order to the attending physician, blocked Scheduling from processing a discharge, and simultaneously fast-tracked full chart access for the cardiology team. All within 26 seconds of the lab result.',
    ts: new Date(Date.now() - 13 * 60000),
  },
  {
    id: 'hxev_003',
    patientId: 'P-44782',
    patientLabel: 'P-44782 · M/41 · OR-3 (pending)',
    chain: [
      { dept: 'surgical',   deptLabel: 'Surgical Robotics', verdict: 'ESCALATE', toolOp: 'emergency.surgery.authorize', delay: 'trigger', note: 'CT abdomen: free air under diaphragm — perforated viscus suspected, emergency OR requested' },
      { dept: 'monitoring', deptLabel: 'Patient Monitoring', verdict: 'ALLOW',    toolOp: 'patient.vitals.read',         delay: '+2s',     note: 'Continuous vitals stream pre-authorized for OR handoff under active emergency scope' },
      { dept: 'ehr',        deptLabel: 'EHR / Records',      verdict: 'ALLOW',    toolOp: 'ehr.record.read',             delay: '+4s',     note: 'Full surgical history, allergies, and consent records unlocked — emergency policy override applied' },
      { dept: 'pharmacy',   deptLabel: 'Pharmacy',           verdict: 'ALLOW',    toolOp: 'medication.schedule.read',    delay: '+4s',     note: 'Pre-op medication reconciliation fast-tracked — cefazolin 2g IV and anesthesia pre-meds cleared' },
    ],
    summary: 'Surgical agent flagged a suspected bowel perforation requiring emergency OR. Rather than blocking or slowing anything down, EDON immediately expanded access scope across Monitoring, EHR, and Pharmacy — pre-authorizing all supporting actions in 4 seconds so nothing delayed the surgical team.',
    ts: new Date(Date.now() - 31 * 60000),
  },
  {
    id: 'hxev_004',
    patientId: 'P-39105',
    patientLabel: 'P-39105 · F/82 · Rm 6N-14',
    chain: [
      { dept: 'nurse',      deptLabel: 'Nurse Assist AI',   verdict: 'ESCALATE', toolOp: 'dnr.status.update',             delay: 'trigger', note: 'DNR documentation requested — advance directive on file (2023) conflicts with active Full Code status in EHR' },
      { dept: 'ehr',        deptLabel: 'EHR / Records',     verdict: 'BLOCK',    toolOp: 'ehr.record.read',               delay: '+6s',     note: 'Bulk record reads on P-39105 suspended — chart locked pending DNR conflict resolution' },
      { dept: 'emergency',  deptLabel: 'Emergency Triage',  verdict: 'ESCALATE', toolOp: 'emergency.surgery.authorize',   delay: '+14s',    note: 'Resuscitation pre-auth request escalated to physician — DNR status unresolved, cannot auto-authorize' },
      { dept: 'scheduling', deptLabel: 'Scheduling',        verdict: 'BLOCK',    toolOp: 'patient.discharge.approve',     delay: '+19s',    note: 'Discharge blocked — open compliance flag (advance directive conflict) must be resolved by attending' },
    ],
    summary: 'Nurse agent detected a conflict between the patient\'s 2023 advance directive (DNR) and her current Full Code status in the EHR. EDON immediately locked the chart, escalated an incoming resuscitation pre-auth from Emergency, and blocked discharge scheduling — holding the entire patient record in a safe state until an attending physician resolves the conflict.',
    ts: new Date(Date.now() - 47 * 60000),
  },
]

const HC_VERDICT_STYLE = {
  BLOCK:    { bg: 'bg-red-500/10 border-red-500/20 text-red-400',    icon: <XCircle size={10} className="text-red-400" /> },
  ESCALATE: { bg: 'bg-amber-500/10 border-amber-500/20 text-amber-400', icon: <AlertTriangle size={10} className="text-amber-400" /> },
  ALLOW:    { bg: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400', icon: <CheckCircle2 size={10} className="text-emerald-400" /> },
}

const DARK_SELECT_STYLE = { colorScheme: 'dark' as const }
const HC_CONTEXT_EVENT = 'edon-demo-context'
const HC_ONBOARDING_STORAGE_KEY = 'edon_hc_onboarding_v2'
const HC_IMPORT_STORAGE_KEY = 'edon_hc_import_v3'
const HC_SETTINGS_STORAGE_KEY = 'edon_hc_settings_v2'

function loadStoredJSON<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    return { ...fallback, ...(JSON.parse(raw) as Partial<T>) }
  } catch {
    return fallback
  }
}

function saveStoredJSON(key: string, value: unknown) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore
  }
}

function publishHCContext(summary: string) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(HC_CONTEXT_EVENT, { detail: summary }))
}

type AgentPurposeKey = 'note' | 'escalation' | 'lab' | 'pharmacy' | 'security' | 'billing' | 'research'

type AgentDetailView = 'overview' | 'scope' | 'review'
type AgentReviewState = 'idle' | 'approved' | 'needs-review' | 'blocked'
type AgentWorkMode = 'govern' | 'register'

interface AgentGovernanceSnapshot {
  selectedDept: string
  search: string
  page: number
  viewMode: 'list' | 'grouped'
  selectedAgentId: string
  purposeTemplate: AgentPurposeKey
  scopeDraft: string
  reviewState: AgentReviewState
  agentDetailView: AgentDetailView
  agentWorkMode: AgentWorkMode
  registerName: string
  registerOwner: string
  registerDept: string
  registerPurpose: AgentPurposeKey
  registerRuntime: string
  registerConnectors: string
  registerDataClass: string
  registerEnvironment: string
  registerNote: string
}

const AGENT_GOVERNANCE_STORAGE_KEY = 'edon_hc_agents_governance_v1'
const PROMOTED_AGENT_STORAGE_KEY = 'edon_hc_promoted_agents_v1'

interface PromotedAgentRecord {
  id: string
  name: string
  department: string
  deptLabel: string
  vendorId: string
  vendorName: string
  purpose: AgentPurposeKey
  purposeLabel: string
  runtime: string
  scope: string
  status: 'active' | 'idle' | 'alert'
  riskLevel: 'low' | 'medium' | 'high'
  decisions24h: number
  blocked24h: number
  blockRate: number
  blockRatePrev: number
  blockRateTrend: 'stable' | 'rising' | 'spiked'
  lastAction: string
  lastActiveMin: number
  floor: string
  serialNo: string
  patientLoad: number
  registeredAt: string
}

function loadAgentGovernanceSnapshot(): Partial<AgentGovernanceSnapshot> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(AGENT_GOVERNANCE_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Partial<AgentGovernanceSnapshot>
    const validDept = typeof parsed.selectedDept === 'string' ? parsed.selectedDept : undefined
    const validViewMode = parsed.viewMode === 'list' || parsed.viewMode === 'grouped' ? parsed.viewMode : undefined
    const validPurpose = AGENT_PURPOSE_TEMPLATES.some(t => t.key === parsed.purposeTemplate) ? parsed.purposeTemplate : undefined
    const validReview = parsed.reviewState === 'idle' || parsed.reviewState === 'approved' || parsed.reviewState === 'needs-review' || parsed.reviewState === 'blocked'
      ? parsed.reviewState
      : undefined
    const validDetail = parsed.agentDetailView === 'overview' || parsed.agentDetailView === 'scope' || parsed.agentDetailView === 'review'
      ? parsed.agentDetailView
      : undefined
    const validWorkMode = parsed.agentWorkMode === 'govern' || parsed.agentWorkMode === 'register'
      ? parsed.agentWorkMode
      : undefined
    const validRegisterPurpose = AGENT_PURPOSE_TEMPLATES.some(t => t.key === parsed.registerPurpose) ? parsed.registerPurpose : undefined
    return {
      selectedDept: validDept,
      search: typeof parsed.search === 'string' ? parsed.search : undefined,
      page: Number.isFinite(parsed.page as number) ? parsed.page : undefined,
      viewMode: validViewMode,
      selectedAgentId: typeof parsed.selectedAgentId === 'string' ? parsed.selectedAgentId : undefined,
      purposeTemplate: validPurpose,
      scopeDraft: typeof parsed.scopeDraft === 'string' ? parsed.scopeDraft : undefined,
      reviewState: validReview,
      agentDetailView: validDetail,
      agentWorkMode: validWorkMode,
      registerName: typeof parsed.registerName === 'string' ? parsed.registerName : undefined,
      registerOwner: typeof parsed.registerOwner === 'string' ? parsed.registerOwner : undefined,
      registerDept: typeof parsed.registerDept === 'string' ? parsed.registerDept : undefined,
      registerPurpose: validRegisterPurpose,
      registerRuntime: typeof parsed.registerRuntime === 'string' ? parsed.registerRuntime : undefined,
      registerConnectors: typeof parsed.registerConnectors === 'string' ? parsed.registerConnectors : undefined,
      registerDataClass: typeof parsed.registerDataClass === 'string' ? parsed.registerDataClass : undefined,
      registerEnvironment: typeof parsed.registerEnvironment === 'string' ? parsed.registerEnvironment : undefined,
      registerNote: typeof parsed.registerNote === 'string' ? parsed.registerNote : undefined,
    }
  } catch {
    return {}
  }
}

function saveAgentGovernanceSnapshot(snapshot: AgentGovernanceSnapshot) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(AGENT_GOVERNANCE_STORAGE_KEY, JSON.stringify(snapshot))
  } catch {
    // ignore storage failures in demo mode
  }
}

function loadPromotedAgents(): PromotedAgentRecord[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(PROMOTED_AGENT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as PromotedAgentRecord[]
    return Array.isArray(parsed) ? parsed.filter(item => item && typeof item.id === 'string' && typeof item.name === 'string') : []
  } catch {
    return []
  }
}

function promotedRecordToAgent(record: PromotedAgentRecord): HospitalAgent {
  return {
    id: record.id,
    name: record.name,
    department: record.department,
    deptLabel: record.deptLabel,
    vendorId: record.vendorId,
    vendorName: record.vendorName,
    status: record.status,
    decisions24h: record.decisions24h,
    blocked24h: record.blocked24h,
    blockRate: record.blockRate,
    blockRatePrev: record.blockRatePrev,
    blockRateTrend: record.blockRateTrend,
    lastAction: record.lastAction,
    lastActiveMin: record.lastActiveMin,
    riskLevel: record.riskLevel,
    floor: record.floor,
    serialNo: record.serialNo,
    patientLoad: record.patientLoad,
  }
}

const AGENT_PURPOSE_TEMPLATES: Array<{
  key: AgentPurposeKey
  label: string
  summary: string
  baseline: string[]
  approvalBound: string[]
  blocked: string[]
  scopePrefix: string
}> = [
  {
    key: 'note',
    label: 'Note drafting',
    summary: 'Draft chart notes, summarize context, and route review requests.',
    baseline: ['draft note', 'summarize chart', 'route review'],
    approvalBound: ['note writeback', 'cross-department share'],
    blocked: ['medication execution', 'identity changes'],
    scopePrefix: 'note',
  },
  {
    key: 'escalation',
    label: 'Escalation triage',
    summary: 'Detect risk, notify humans, and route incidents to the right team.',
    baseline: ['watch signals', 'notify team', 'open escalation'],
    approvalBound: ['external notify', 'department handoff'],
    blocked: ['writeback', 'autonomous override'],
    scopePrefix: 'escalation',
  },
  {
    key: 'lab',
    label: 'Lab review',
    summary: 'Read results, flag abnormalities, and surface critical values.',
    baseline: ['read labs', 'flag critical value', 'route review'],
    approvalBound: ['result release', 'chart writeback'],
    blocked: ['order entry', 'sample cancel'],
    scopePrefix: 'lab',
  },
  {
    key: 'pharmacy',
    label: 'Pharmacy lookup',
    summary: 'Review medication context, approvals, and interaction warnings.',
    baseline: ['lookup meds', 'check interactions', 'route approval'],
    approvalBound: ['dispense', 'order submit'],
    blocked: ['dose override', 'autonomous dispense'],
    scopePrefix: 'pharmacy',
  },
  {
    key: 'security',
    label: 'Security export',
    summary: 'Export audit trails, monitor drift, and notify SIEM or support.',
    baseline: ['read audit', 'export security', 'watch drift'],
    approvalBound: ['revocation', 'tenant lockdown'],
    blocked: ['clinical override', 'record writeback'],
    scopePrefix: 'security',
  },
  {
    key: 'billing',
    label: 'Billing review',
    summary: 'Check claims, route exceptions, and report revenue-cycle issues.',
    baseline: ['review claims', 'flag exceptions', 'route billing'],
    approvalBound: ['claim submit', 'charge correction'],
    blocked: ['clinical writeback', 'policy change'],
    scopePrefix: 'billing',
  },
  {
    key: 'research',
    label: 'Research support',
    summary: 'De-identify data, build cohorts, and support approved research.',
    baseline: ['deidentify', 'build cohort', 'export dataset'],
    approvalBound: ['IRB release', 'external dataset share'],
    blocked: ['raw PHI export', 'clinical override'],
    scopePrefix: 'research',
  },
]

const AGENT_ACTION_REGISTRY: Record<AgentPurposeKey, { allowed: string[]; approval: string[]; blocked: string[] }> = Object.fromEntries(
  AGENT_PURPOSE_TEMPLATES.map(t => [t.key, { allowed: t.baseline, approval: t.approvalBound, blocked: t.blocked }]),
) as Record<AgentPurposeKey, { allowed: string[]; approval: string[]; blocked: string[] }>

const PURPOSE_BY_DEPARTMENT: Record<string, AgentPurposeKey> = {
  cardiology: 'note',
  radiology: 'lab',
  pharmacy: 'pharmacy',
  security: 'security',
  monitoring: 'escalation',
  nurse: 'escalation',
  lab: 'lab',
  billing: 'billing',
  research: 'research',
  telehealth: 'note',
  surgical: 'escalation',
  ehr: 'note',
  scheduling: 'escalation',
  emergency: 'escalation',
}

function buildScopePreview(agent: HospitalAgent, purpose: AgentPurposeKey) {
  const prefix = AGENT_PURPOSE_TEMPLATES.find(t => t.key === purpose)?.scopePrefix ?? 'note'
  const dept = agent.department.toLowerCase().replace(/[^a-z0-9]/g, '')
  return `${dept}.${prefix}.draft -> ${dept}.audit.read`
}

function buildRegistrationScopePreview(department: string, purpose: AgentPurposeKey, connectors: string) {
  const prefix = AGENT_PURPOSE_TEMPLATES.find(t => t.key === purpose)?.scopePrefix ?? 'note'
  const dept = department.toLowerCase().replace(/[^a-z0-9]/g, '') || 'unassigned'
  const connectorSuffix = connectors
    .split(',')
    .map(part => part.trim().toLowerCase().replace(/[^a-z0-9]/g, ''))
    .filter(Boolean)
    .slice(0, 2)
  const boundary = connectorSuffix.length ? connectorSuffix.join('.') : 'audit.read'
  return `${dept}.${prefix}.draft -> ${dept}.${boundary}`
}

function CrossAgentFeedHC({ deptModes, coordinationAllowed }: { deptModes: Record<string, 'sandbox' | 'governed'>; coordinationAllowed: Record<string, boolean> }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Link2 size={14} className="text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Cross-Department Coordination</h3>
        <span className="text-xs text-muted-foreground bg-white/5 px-2 py-0.5 rounded-full border border-white/10">Automatic</span>
      </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
        These are <span className="text-foreground font-medium">EDON's automatic decisions</span> — no human involved. When one agent raises a risk signal for a patient, EDON instantly blocks or escalates related actions from other departments touching the same patient. Anything marked ESCALATE gets routed to the <span className="text-amber-400 font-medium">Review Queue</span> for physician sign-off. Departments marked Held do not participate in cross-department coordination.
      </p>
      <div className="space-y-3">
        {HC_CROSS_EVENTS.map(ev => {
          const isOpen = expanded === ev.id
          return (
            <div key={ev.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
              {/* Header row */}
              <button
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors text-left"
                onClick={() => setExpanded(isOpen ? null : ev.id)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] font-mono text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded shrink-0">
                    {ev.patientId}
                  </span>
                  <span className="text-xs font-medium text-foreground truncate">{ev.patientLabel}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0">· {ev.chain.length} agents</span>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-3">
                  <span className="text-[10px] text-muted-foreground">
                    {Math.floor((Date.now() - ev.ts.getTime()) / 60000)}m ago
                  </span>
                  <span className={cn('text-muted-foreground transition-transform duration-200', isOpen && 'rotate-90')}>›</span>
                </div>
              </button>

              {/* Chain visualization — always visible */}
              <div className="px-4 pb-3 space-y-2">
              <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider">EDON automatic decisions — no human action required except items marked ESCALATE</p>
              <div className="flex items-center gap-1.5 flex-wrap">
                {ev.chain.map((step, idx) => {
                  const dept = DEPARTMENTS.find(d => d.key === step.dept)
                  const DIcon = dept?.icon ?? Activity
                  const vs = HC_VERDICT_STYLE[step.verdict]
                  const mode = deptModes[step.dept] ?? 'governed'
                  const canCoordinate = coordinationAllowed[step.dept] ?? true
                  return (
                    <div key={idx} className="flex items-center gap-1.5">
                      <div className={cn('flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-mono', vs.bg)}>
                        {vs.icon}
                        <DIcon size={10} className={dept?.color ?? ''} />
                        <span className="text-foreground/80">{step.deptLabel.split(' ')[0]}</span>
                        <span className="opacity-50">·</span>
                        <span className="opacity-60">{step.toolOp.split('.').slice(-1)[0]}</span>
                        <span
                          className="ml-1 text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                          style={{
                            background: mode === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                            color: mode === 'sandbox' ? '#93c5fd' : '#86efac',
                            border: mode === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                          }}
                        >
                          {mode}
                        </span>
                        <span
                          className="ml-1 text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                          style={{
                            background: canCoordinate ? 'rgba(74,222,128,0.10)' : 'rgba(245,158,11,0.10)',
                            color: canCoordinate ? '#86efac' : '#fbbf24',
                            border: canCoordinate ? '1px solid rgba(74,222,128,0.22)' : '1px solid rgba(245,158,11,0.22)',
                          }}
                        >
                          {canCoordinate ? 'coord allowed' : 'held'}
                        </span>
                      </div>
                      {idx < ev.chain.length - 1 && (
                        <div className="flex items-center gap-0.5 text-muted-foreground">
                          <ArrowRight size={9} />
                          <span className="text-[9px] font-mono">{ev.chain[idx + 1].delay}</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              </div>

              {/* Expanded detail */}
              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 space-y-3 border-t border-white/[0.06] pt-3">
                      {/* Per-step notes */}
                      <div className="space-y-2">
                        {ev.chain.map((step, idx) => {
                          const vs = HC_VERDICT_STYLE[step.verdict]
                          return (
                            <div key={idx} className="flex items-start gap-2 text-xs">
                              <span className={cn('mt-0.5 shrink-0 px-1.5 py-0.5 rounded border text-[10px] font-semibold', vs.bg)}>
                                {step.verdict}
                              </span>
                              <div>
                                <span className="font-mono text-muted-foreground">{step.toolOp}</span>
                                <span className="text-muted-foreground"> — </span>
                                <span className="text-foreground/70">{step.note}</span>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                      {/* Summary */}
                      <p className="text-xs text-muted-foreground leading-relaxed border-t border-white/[0.06] pt-3">{ev.summary}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface AgentsTabProps {
  deptModes: Record<string, 'sandbox' | 'governed'>
}

function AgentsTab({ deptModes }: AgentsTabProps) {
  const savedStateRef = useRef<Partial<AgentGovernanceSnapshot> | null>(null)
  if (!savedStateRef.current) savedStateRef.current = loadAgentGovernanceSnapshot()
  const savedState = savedStateRef.current
  const promotedAgents = loadPromotedAgents().map(promotedRecordToAgent)
  const fleet = [...ALL_AGENTS, ...promotedAgents]
  const [agentWorkMode, setAgentWorkMode] = useState<AgentWorkMode>(savedState.agentWorkMode ?? 'govern')
  const [selectedDept, setSelectedDept] = useState<string>(savedState.selectedDept ?? 'all')
  const [vendorFilter, setVendorFilter] = useState<string>('all')
  const [search, setSearch] = useState(savedState.search ?? '')
  const [page, setPage] = useState(savedState.page ?? 0)
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>(savedState.viewMode ?? 'grouped')
  const [selectedAgentId, setSelectedAgentId] = useState(savedState.selectedAgentId ?? (ALL_AGENTS[0]?.id ?? ''))
  const [purposeTemplate, setPurposeTemplate] = useState<AgentPurposeKey>(savedState.purposeTemplate ?? 'note')
  const [scopeDraft, setScopeDraft] = useState(savedState.scopeDraft ?? '')
  const [reviewState, setReviewState] = useState<AgentReviewState>(savedState.reviewState ?? 'idle')
  const [agentDetailView, setAgentDetailView] = useState<AgentDetailView>(savedState.agentDetailView ?? 'overview')
  const [registerName, setRegisterName] = useState(savedState.registerName ?? '')
  const [registerOwner, setRegisterOwner] = useState(savedState.registerOwner ?? '')
  const [registerDept, setRegisterDept] = useState(savedState.registerDept ?? selectedDept)
  const [registerPurpose, setRegisterPurpose] = useState<AgentPurposeKey>(savedState.registerPurpose ?? 'note')
  const [registerRuntime, setRegisterRuntime] = useState(savedState.registerRuntime ?? 'node worker')
  const [registerConnectors, setRegisterConnectors] = useState(savedState.registerConnectors ?? 'Epic, Teams')
  const [registerDataClass, setRegisterDataClass] = useState(savedState.registerDataClass ?? 'PHI')
  const [registerEnvironment, setRegisterEnvironment] = useState(savedState.registerEnvironment ?? 'Audit-only')
  const [registerNote, setRegisterNote] = useState(savedState.registerNote ?? '')
  const [registerLedger, setRegisterLedger] = useState<Array<{ id: string; name: string; dept: string; purpose: string; scope: string; status: string }>>([])
  const [registerNotice, setRegisterNotice] = useState('')
  const runtimeOptions = ['node worker', 'python service', 'container sidecar', 'k8s job', 'lambda function']
  const dataClassOptions = ['PHI', 'PII', 'Operational', 'Research', 'Public']
  const environmentOptions = ['Audit-only', 'Sandbox', 'Pilot', 'Governed', 'Production']
  const connectorOptions = ['Epic', 'Teams', 'SIEM', 'LLM API', 'Analytics', 'Vendor service', 'Internal API']
  const hydratedRef = useRef(false)
  const PAGE_SIZE = 25

  const statusConfig: Record<HospitalAgent['status'], { label: string; color: string; dot: string }> = {
    active: { label: 'Active', color: 'text-emerald-400', dot: 'bg-emerald-400' },
    idle: { label: 'Idle', color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
    alert: { label: 'Alert', color: 'text-red-400', dot: 'bg-red-400' },
  }

  const riskConfig: Record<HospitalAgent['riskLevel'], { label: string; variant: BadgeProps['variant'] }> = {
    low: { label: 'Low', variant: 'allow' },
    medium: { label: 'Med', variant: 'amber' },
    high: { label: 'High', variant: 'block' },
  }

  const filtered = fleet.filter(a => {
    const matchDept = selectedDept === 'all' || a.department === selectedDept
    const matchVendor = vendorFilter === 'all' || a.vendorId === vendorFilter
    const matchSearch =
      !search ||
      a.id.toLowerCase().includes(search.toLowerCase()) ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.deptLabel.toLowerCase().includes(search.toLowerCase()) ||
      a.vendorName.toLowerCase().includes(search.toLowerCase())
    return matchDept && matchVendor && matchSearch
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const selectedAgent = filtered.find(a => a.id === selectedAgentId) ?? filtered[0] ?? fleet[0]
  const selectedDeptLabel = selectedDept === 'all'
    ? 'All departments'
    : DEPARTMENTS.find(d => d.key === selectedDept)?.label ?? selectedDept
  const purposeMeta = AGENT_PURPOSE_TEMPLATES.find(t => t.key === purposeTemplate) ?? AGENT_PURPOSE_TEMPLATES[0]
  const purposeOptions = AGENT_PURPOSE_TEMPLATES
  const actionRegistry = AGENT_ACTION_REGISTRY[purposeTemplate]
  const inferredTemplate = PURPOSE_BY_DEPARTMENT[selectedAgent?.department ?? ''] ?? 'note'
  const inferredMeta = AGENT_PURPOSE_TEMPLATES.find(t => t.key === inferredTemplate) ?? purposeMeta
  const blastDepartments = Array.from(
    new Set(
      [
        selectedAgent?.department,
        ...DEPARTMENTS.filter(d => PURPOSE_BY_DEPARTMENT[d.key] === inferredTemplate).map(d => d.key),
      ].filter((dept): dept is string => Boolean(dept)),
    ),
  )
  const blastDepartmentLabels = blastDepartments
    .map(dept => DEPARTMENTS.find(d => d.key === dept)?.label ?? dept)
    .filter((label, idx, arr) => arr.indexOf(label) === idx)
  const blastAffectedAgents = fleet.filter(agent => blastDepartments.includes(agent.department))
  const blastSameDeptAgents = fleet.filter(agent => agent.department === selectedAgent?.department)
  const blastConnectorSurface = purposeTemplate === 'note'
    ? ['Epic', 'Teams', 'Support']
    : purposeTemplate === 'lab'
      ? ['Epic', 'Lab system', 'SIEM']
      : purposeTemplate === 'pharmacy'
        ? ['Epic', 'Pharmacy', 'SIEM']
        : purposeTemplate === 'security'
          ? ['SIEM', 'Support', 'Admin console']
          : purposeTemplate === 'billing'
            ? ['Billing', 'ERP', 'SIEM']
            : purposeTemplate === 'research'
              ? ['Research store', 'De-identification', 'Export']
              : ['Teams', 'Incident routing', 'Support']
  const blastFailureMode = selectedAgent
    ? `${selectedAgent.deptLabel} retains its own mode, but revoking this agent would cut ${blastSameDeptAgents.length.toLocaleString()} same-department agent(s) and ${blastAffectedAgents.length.toLocaleString()} total agent(s) in the current blast cohort from the shared baseline.`
    : 'Select an agent to see the blast cohort and likely impact.'
  const registerScopeDraft = buildRegistrationScopePreview(registerDept, registerPurpose, registerConnectors)
  const registerDeptLabel = DEPARTMENTS.find(d => d.key === registerDept)?.label ?? registerDept
  const registerPurposeMeta = AGENT_PURPOSE_TEMPLATES.find(t => t.key === registerPurpose) ?? AGENT_PURPOSE_TEMPLATES[0]
  const registerDeptRisk = registerDept === 'all'
    ? 'tenant-wide review'
    : (deptModes[registerDept] ?? 'governed') === 'sandbox'
      ? 'sandboxed'
      : 'governed'
  const registerBlastEstimate = registerDept === 'all'
    ? fleet.length
    : fleet.filter(agent => agent.department === registerDept).length
  void setPurposeTemplate
  void purposeOptions
  void actionRegistry
  void inferredMeta
  void blastDepartmentLabels
  void blastConnectorSurface
  void blastFailureMode

  // Group by department for grouped view
  const byDept = DEPARTMENTS.map(d => ({
    dept: d,
    agents: filtered.filter(a => a.department === d.key),
  })).filter(g => g.agents.length > 0)
  const activeCount = filtered.filter(a => a.status === 'active').length
  const alertCount = filtered.filter(a => a.status === 'alert').length
  const highRiskCount = filtered.filter(a => a.riskLevel === 'high').length
  const sandboxCount = filtered.filter(a => (deptModes[a.department] ?? 'governed') === 'sandbox').length
  const risingCount = filtered.filter(a => a.blockRateTrend === 'rising').length
  const spikedCount = filtered.filter(a => a.blockRateTrend === 'spiked').length

  useEffect(() => {
    if (!hydratedRef.current) return
    setPage(0)
  }, [selectedDept, search])
  useEffect(() => {
    if (selectedAgent?.id && selectedAgent.id !== selectedAgentId) setSelectedAgentId(selectedAgent.id)
  }, [selectedAgent?.id, selectedAgentId])
  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true
      return
    }
    setScopeDraft(buildScopePreview(selectedAgent, purposeTemplate))
    setReviewState('idle')
  }, [purposeTemplate, selectedAgent?.id])
  useEffect(() => {
    if (!hydratedRef.current) return
    setAgentDetailView('overview')
  }, [selectedAgent?.id])
  useEffect(() => {
    if (!hydratedRef.current) return
    saveAgentGovernanceSnapshot({
      selectedDept,
      search,
      page,
      viewMode,
      selectedAgentId,
      purposeTemplate,
      scopeDraft,
      reviewState,
      agentDetailView,
      agentWorkMode,
      registerName,
      registerOwner,
      registerDept,
      registerPurpose,
      registerRuntime,
      registerConnectors,
      registerDataClass,
      registerEnvironment,
      registerNote,
    })
  }, [selectedDept, search, page, viewMode, selectedAgentId, purposeTemplate, scopeDraft, reviewState, agentDetailView, agentWorkMode, registerName, registerOwner, registerDept, registerPurpose, registerRuntime, registerConnectors, registerDataClass, registerEnvironment, registerNote])

  useEffect(() => {
    publishHCContext([
      'Agents page',
      `${filtered.length} visible`,
      `vendor ${vendorFilter === 'all' ? 'all' : vendorFilter}`,
      `dept ${selectedDeptLabel}`,
      selectedAgent ? `selected ${selectedAgent.name}` : 'no selected agent',
      `view ${viewMode}`,
      `mode ${agentWorkMode}`,
      `detail ${agentDetailView}`,
      `purpose ${purposeMeta.label}`,
      `scope ${scopeDraft || 'unset'}`,
      `review ${reviewState}`,
      selectedAgent ? `blast ${blastAffectedAgents.length} agents / ${blastDepartmentLabels.length} departments` : 'no blast radius selected',
    ].join(' · '))
  }, [filtered.length, vendorFilter, selectedDeptLabel, selectedAgent?.name, viewMode, agentWorkMode, agentDetailView, purposeMeta.label, scopeDraft, reviewState, blastAffectedAgents.length, blastDepartmentLabels.length])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Hospital Agents</h1>
          <p className="text-muted-foreground text-sm mt-1">{fleet.length.toLocaleString()} agents across {DEPARTMENTS.length} departments</p>
        </div>
        {/* View toggle */}
        <div className="flex items-center gap-1 p-1 rounded-xl border border-white/10 bg-white/[0.03] shrink-0">
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              viewMode === 'list' ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <LayoutList size={13} /> List
          </button>
          <button
            onClick={() => setViewMode('grouped')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              viewMode === 'grouped' ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <LayoutGrid size={13} /> By Department
          </button>

        </div>
      </div>

      {/* Metric cheat sheet */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield size={14} className="text-sky-400" />
          <h2 className="font-semibold text-sm text-foreground">How to read these numbers</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs">
          <div className="rounded-xl border border-white/5 bg-black/10 p-3 space-y-1.5">
            <p className="font-semibold text-foreground">Block rate</p>
            <p className="text-muted-foreground">0-10% normal, 10-20% watch, above 20% concern.</p>
          </div>
          <div className="rounded-xl border border-white/5 bg-black/10 p-3 space-y-1.5">
            <p className="font-semibold text-foreground">Risk</p>
            <p className="text-muted-foreground">Low is normal, medium needs review, high deserves attention.</p>
          </div>
          <div className="rounded-xl border border-white/5 bg-black/10 p-3 space-y-1.5">
            <p className="font-semibold text-foreground">Status</p>
            <p className="text-muted-foreground">Active is healthy, idle is quiet, alert means the agent needs review.</p>
          </div>
          <div className="rounded-xl border border-white/5 bg-black/10 p-3 space-y-1.5">
            <p className="font-semibold text-foreground">Trend</p>
            <p className="text-muted-foreground">Stable is fine, rising needs watching, spiked is a real warning.</p>
          </div>
        </div>
      </div>

      {/* Department filter pills */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedDept('all')}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
            selectedDept === 'all'
              ? 'bg-primary/20 text-primary border-primary/40'
              : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground',
          )}
        >
          All · 500
        </button>
        {DEPARTMENTS.map(d => {
          const Icon = d.icon
          return (
            <button
              key={d.key}
              onClick={() => setSelectedDept(d.key)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border',
                selectedDept === d.key
                  ? 'bg-primary/20 text-primary border-primary/40'
                  : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground',
              )}
            >
              <Icon size={11} className={selectedDept === d.key ? 'text-primary' : d.color} />
              {d.label} · {d.count}
            </button>
          )
        })}
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.2fr_.8fr]">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Vendor</span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{ALL_VENDORS.length} available</span>
          </div>
          <select
            value={vendorFilter}
            onChange={e => setVendorFilter(e.target.value)}
            className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none"
            style={DARK_SELECT_STYLE}
          >
            <option value="all">All vendors</option>
            {ALL_VENDORS.map(v => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department focus</span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{selectedDept === 'all' ? 'All departments' : selectedDeptLabel}</span>
          </div>
          <div className="text-sm text-white font-medium truncate">{selectedDept === 'all' ? 'Browse the full fleet or narrow it by department.' : `Showing ${selectedDeptLabel} agents only.`}</div>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search agents, departments, floors..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          ['Visible agents', filtered.length.toLocaleString(), 'summary'],
          ['Active', activeCount.toLocaleString(), 'healthy'],
          ['Alert', alertCount.toLocaleString(), 'needs review'],
          ['High risk', highRiskCount.toLocaleString(), 'policy-bound'],
          ['Sandboxed', sandboxCount.toLocaleString(), 'department hold'],
          ['Drifting', (risingCount + spikedCount).toLocaleString(), 'rising or spiked'],
        ].map(([label, value, sub]) => (
          <div key={label as string} className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{label}</div>
            <div className="mt-1 text-lg font-semibold text-white">{value}</div>
            <div className="text-[10px] text-muted-foreground">{sub}</div>
          </div>
        ))}
      </div>

      {false ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white">Register new agent</p>
              <p className="text-xs text-muted-foreground">Governance-only intake for a department or workflow agent before it touches real systems.</p>
            </div>
            <span className="rounded-full border border-amber-500/20 bg-amber-500/8 px-2.5 py-1 text-[10px] uppercase tracking-widest text-amber-300">
              Audit-only
            </span>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.05fr_.95fr]">
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Agent name</label>
                  <Input value={registerName} onChange={e => setRegisterName(e.target.value)} placeholder="Cardiology note helper" />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Owner</label>
                  <Input value={registerOwner} onChange={e => setRegisterOwner(e.target.value)} placeholder="Cardiology ops lead" />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Department</label>
                  <select value={registerDept} onChange={e => setRegisterDept(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                    <option value="all">All departments</option>
                    {DEPARTMENTS.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Purpose</label>
                  <select value={registerPurpose} onChange={e => setRegisterPurpose(e.target.value as AgentPurposeKey)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                    {AGENT_PURPOSE_TEMPLATES.map(opt => <option key={opt.key} value={opt.key}>{opt.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Runtime</label>
                  <select value={registerRuntime} onChange={e => setRegisterRuntime(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                    {runtimeOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Data class</label>
                  <select value={registerDataClass} onChange={e => setRegisterDataClass(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                    {dataClassOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Intended connectors</label>
                  <div className="rounded-xl border border-white/10 bg-black/30 p-2.5 space-y-2">
                    <div className="flex flex-wrap gap-2">
                      {connectorOptions.map(opt => {
                        const active = registerConnectors.split(',').map(v => v.trim()).filter(Boolean).includes(opt)
                        return (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => {
                              const next = new Set(registerConnectors.split(',').map(v => v.trim()).filter(Boolean))
                              if (next.has(opt)) next.delete(opt)
                              else next.add(opt)
                              setRegisterConnectors(Array.from(next).join(', '))
                            }}
                            className={cn(
                              'rounded-full border px-3 py-1.5 text-[11px] transition-colors',
                              active
                                ? 'border-primary/30 bg-primary/10 text-primary'
                                : 'border-white/[0.06] bg-white/[0.03] text-muted-foreground hover:text-foreground',
                            )}
                          >
                            {opt}
                          </button>
                        )
                      })}
                    </div>
                    <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-widest text-muted-foreground/60">
                      <span>Selected</span>
                      <span>{registerConnectors || 'none'}</span>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Environment</label>
                  <div className="flex items-center gap-1 p-1 rounded-xl border border-white/10 bg-white/[0.03] overflow-x-auto">
                    {environmentOptions.map(opt => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => setRegisterEnvironment(opt)}
                        className={cn(
                          'flex-1 min-w-[5.75rem] whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors',
                          registerEnvironment === opt ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Notes</label>
                <textarea
                  value={registerNote}
                  onChange={e => setRegisterNote(e.target.value)}
                  rows={3}
                  className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-muted-foreground outline-none resize-none"
                  placeholder="What the agent is for, what it should never do, and how it will be used"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setRegisterName('')
                    setRegisterOwner('')
                    setRegisterDept('all')
                    setRegisterPurpose('note')
                    setRegisterRuntime('node worker')
                    setRegisterConnectors('Epic, Teams')
                    setRegisterDataClass('PHI')
                    setRegisterEnvironment('Audit-only')
                    setRegisterNote('')
                    setRegisterNotice('Draft cleared.')
                  }}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  Clear draft
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = {
                      id: `reg-${Date.now()}`,
                      name: registerName || 'Unnamed agent',
                      dept: registerDeptLabel,
                      purpose: registerPurposeMeta.label,
                      scope: registerScopeDraft,
                      status: 'Audit-only registered',
                    }
                    setRegisterLedger(prev => [next, ...prev].slice(0, 5))
                    setRegisterNotice(`${next.name} registered in audit-only mode. Scope: ${registerScopeDraft}`)
                    setAgentWorkMode('govern')
                  }}
                  disabled={!registerName.trim() || !registerOwner.trim()}
                  className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/15 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Register audit-only
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-white">Preflight</p>
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{registerDeptRisk}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2 text-xs">
                  <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2">
                    <div className="text-muted-foreground">Department</div>
                    <div className="mt-1 text-white">{registerDeptLabel}</div>
                  </div>
                  <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2">
                    <div className="text-muted-foreground">Purpose</div>
                    <div className="mt-1 text-white">{registerPurposeMeta.label}</div>
                  </div>
                  <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2">
                    <div className="text-muted-foreground">Runtime</div>
                    <div className="mt-1 text-white">{registerRuntime || 'Unassigned'}</div>
                  </div>
                  <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2">
                    <div className="text-muted-foreground">Blast radius</div>
                    <div className="mt-1 text-white">{registerBlastEstimate.toLocaleString()} agents</div>
                  </div>
                </div>
                <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2">
                  <div className="text-muted-foreground text-xs">Baseline scope</div>
                  <div className="mt-1 text-xs text-white break-words">{registerScopeDraft}</div>
                </div>
                <div className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2 space-y-1.5">
                  <div className="text-muted-foreground text-xs">Operator note</div>
                  <div className="text-xs text-white leading-relaxed">
                    {registerNote || 'This agent is declared only. EDON will keep it audit-only until policy and scope are approved.'}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {registerPurposeMeta.blocked.slice(0, 3).map(item => (
                    <span key={item} className="rounded-full border border-red-500/20 bg-red-500/8 px-2 py-1 text-[10px] uppercase tracking-widest text-red-300">
                      No {item}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-white">Recent registrations</p>
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{registerLedger.length} queued</span>
                </div>
                {registerLedger.length > 0 ? registerLedger.map(item => (
                  <div key={item.id} className="rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-white">{item.name}</span>
                      <span className="text-muted-foreground">{item.status}</span>
                    </div>
                    <div className="mt-1 text-muted-foreground">{item.dept} · {item.purpose}</div>
                    <div className="mt-1 text-white break-words">{item.scope}</div>
                  </div>
                )) : (
                  <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-3 py-4 text-xs text-muted-foreground">
                    No agents registered yet. Create a draft and register it in audit-only mode.
                  </div>
                )}
              </div>
            </div>
          </div>
          {registerNotice && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-xs text-emerald-300">
              {registerNotice}
            </div>
          )}
        </div>
      ) : null}

      <AnimatePresence mode="wait">
        {/* ── LIST VIEW ── */}
        {viewMode === 'list' && (
          <motion.div key="list" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="glass-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-muted-foreground">
                      <th className="text-left px-4 py-3 font-medium">Agent ID</th>
                      <th className="text-left px-4 py-3 font-medium hidden sm:table-cell">Department</th>
                      <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Floor</th>
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                      <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Decisions/24h</th>
                      <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Blocked</th>
                      <th className="text-left px-4 py-3 font-medium hidden xl:table-cell">Block Rate</th>
                      <th className="text-left px-4 py-3 font-medium">Risk</th>
                      <th className="px-4 py-3 font-medium hidden md:table-cell">Last Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginated.map(agent => {
                      const s = statusConfig[agent.status]
                      const r = riskConfig[agent.riskLevel]
                      const dept = DEPARTMENTS.find(d => d.key === agent.department)
                      const Icon = dept?.icon ?? Activity
                      return (
                        <tr
                          key={agent.id}
                          data-cite-id={agent.id}
                          onClick={() => setSelectedAgentId(agent.id)}
                          className={cn(
                            'border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors cursor-pointer',
                            selectedAgent?.id === agent.id && 'bg-primary/5',
                          )}
                        >
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
                            <div className="flex items-center gap-2">
                              <span className="text-muted-foreground">{agent.deptLabel}</span>
                              <span
                                className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                                style={{
                                  background: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                                  color: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? '#93c5fd' : '#86efac',
                                  border: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                                }}
                              >
                                {(deptModes[agent.department] ?? 'governed') === 'sandbox' ? 'sandbox' : 'governed'}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <span className="font-mono text-muted-foreground">{agent.floor}</span>
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
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <Badge variant={r.variant}>{r.label}</Badge>
                              <span className={cn(
                                'text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-widest',
                                (deptModes[agent.department] ?? 'governed') === 'sandbox'
                                  ? 'bg-blue-500/10 text-blue-300 border border-blue-500/20'
                                  : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
                              )}>
                                {(deptModes[agent.department] ?? 'governed') === 'sandbox' ? 'sandbox' : 'governed'}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            <div>
                              <span className="text-foreground/80 text-xs">{fmtOp(agent.lastAction)}</span>
                              <span className="text-muted-foreground/50 text-[11px] ml-1.5">
                                {agent.lastActiveMin === 0 ? 'just now' : `${agent.lastActiveMin}m ago`}
                              </span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-white/5">
                <span className="text-xs text-muted-foreground">
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
                    <ChevronLeft size={14} />
                  </Button>
                  <span className="text-xs text-muted-foreground px-2">{page + 1} / {totalPages}</span>
                  <Button variant="ghost" size="sm" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>
                    <ChevronRight size={14} />
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── GROUPED VIEW ── */}
        {viewMode === 'grouped' && (
          <motion.div key="grouped" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-8">
            {byDept.map(({ dept, agents }) => {
              const Icon = dept.icon
              const alertCount = agents.filter(a => a.status === 'alert').length
              const avgBlockRate = agents.length ? (agents.reduce((s, a) => s + a.blockRate, 0) / agents.length).toFixed(1) : '0.0'
              return (
                <motion.div key={dept.key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                  {/* Dept header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon size={14} className={dept.color} />
                      <h3 className="text-sm font-semibold text-foreground">{dept.label}</h3>
                      <span className="text-xs text-muted-foreground bg-white/[0.05] px-2 py-0.5 rounded-full border border-white/10">
                        {agents.length} agents
                      </span>
                      {alertCount > 0 && (
                        <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full font-semibold">
                          {alertCount} ALERT
                        </span>
                      )}
                      {(() => {
                        const spiked = agents.filter(a => a.blockRateTrend === 'spiked').length
                        const rising = agents.filter(a => a.blockRateTrend === 'rising').length
                        if (spiked > 0) return (
                          <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full font-semibold animate-pulse">
                            ↑↑ {spiked} spiked
                          </span>
                        )
                        if (rising > 0) return (
                          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full font-semibold">
                            ↑ {rising} rising
                          </span>
                        )
                        return null
                      })()}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>Avg block rate: <span className="text-foreground font-mono">{avgBlockRate}%</span></span>
                    </div>
                  </div>

                  {/* Agent cards grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                    {agents.slice(0, 8).map(agent => {
                      const s = statusConfig[agent.status]
                      const r = riskConfig[agent.riskLevel]
                      return (
                        <div
                          key={agent.id}
                          data-cite-id={agent.id}
                          onClick={() => setSelectedAgentId(agent.id)}
                          className={cn(
                            'rounded-2xl border p-4 hover:bg-white/[0.04] transition-colors space-y-3 cursor-pointer',
                            agent.status === 'alert' || agent.blockRateTrend === 'spiked'
                              ? 'border-red-500/30 bg-red-500/[0.04]'
                              : agent.blockRateTrend === 'rising'
                              ? 'border-amber-500/20 bg-white/[0.03]'
                              : 'border-white/10 bg-white/[0.03]',
                            selectedAgent?.id === agent.id && 'ring-1 ring-primary/30',
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className={cn('p-1.5 rounded-lg bg-white/[0.05]', dept.color)}>
                                <Icon size={12} />
                              </div>
                              <div className="min-w-0">
                                <div className="font-mono text-xs text-foreground font-medium truncate">{agent.id}</div>
                                <div className="text-[10px] text-muted-foreground">Floor {agent.floor}</div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse-dot', s.dot)} />
                              <span className={cn('text-[10px]', s.color)}>{s.label}</span>
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-1 text-center">
                            <div>
                              <div className="text-xs font-mono text-foreground font-semibold">{agent.decisions24h.toLocaleString()}</div>
                              <div className="text-[10px] text-muted-foreground">24h actions</div>
                            </div>
                            <div>
                              <div className="text-xs font-mono text-red-400 font-semibold">{agent.blockRate.toFixed(1)}%</div>
                              <div className="text-[10px] text-muted-foreground">Block rate</div>
                            </div>
                            <div>
                              {agent.blockRateTrend === 'spiked' && (
                                <div className="text-xs font-semibold text-red-400 flex items-center justify-center gap-0.5 animate-pulse">↑↑ Spike</div>
                              )}
                              {agent.blockRateTrend === 'rising' && (
                                <div className="text-xs font-semibold text-amber-400 flex items-center justify-center gap-0.5">↑ Rising</div>
                              )}
                              {agent.blockRateTrend === 'stable' && (
                                <div className="text-xs font-semibold text-emerald-400 flex items-center justify-center gap-0.5">→ Stable</div>
                              )}
                              <div className="text-[10px] text-muted-foreground">
                                was {agent.blockRatePrev.toFixed(1)}%
                              </div>
                            </div>
                          </div>
                          <div className="h-0.5 bg-secondary rounded-full overflow-hidden">
                            <div className="h-full rounded-full bg-red-400/60" style={{ width: `${Math.min(agent.blockRate, 100)}%` }} />
                          </div>
                          <div className="flex items-center justify-between">
                            <Badge variant={r.variant}>{r.label} Risk</Badge>
                            <span className="text-[10px] text-muted-foreground">
                              {agent.lastActiveMin === 0 ? 'just now' : `${agent.lastActiveMin}m ago`}
                            </span>
                          </div>
                          <div className="flex items-center justify-between rounded-xl px-3 py-2 border border-white/5 bg-white/[0.02]">
                            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Department mode</span>
                            <span
                              className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                              style={{
                                background: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                                color: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? '#93c5fd' : '#86efac',
                                border: (deptModes[agent.department] ?? 'governed') === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                              }}
                            >
                              {(deptModes[agent.department] ?? 'governed') === 'sandbox' ? 'sandbox' : 'governed'}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                    {agents.length > 8 && (
                      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4 flex items-center justify-center">
                        <span className="text-xs text-muted-foreground">+{agents.length - 8} more · <button onClick={() => { setSelectedDept(dept.key); setViewMode('list') }} className="text-primary hover:underline">View all</button></span>
                      </div>
                    )}
                  </div>
                </motion.div>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────

const SHARED_KEY = 'edon_hc_demo_shared_audits'
const TEAM_MEMBERS = [
  { email: 'dr.chen@stmercy.org',    name: 'Dr. Chen' },
  { email: 'dr.patel@stmercy.org',   name: 'Dr. Patel' },
  { email: 'nurse.garcia@stmercy.org', name: 'N. Garcia' },
  { email: 'compliance@stmercy.org', name: 'Compliance' },
]

function loadShared(): SharedAuditRecord[] {
  try { const r = localStorage.getItem(SHARED_KEY); return r ? JSON.parse(r) : [] } catch { return [] }
}
function saveShared(items: SharedAuditRecord[]) {
  localStorage.setItem(SHARED_KEY, JSON.stringify(items))
}

function AuditTab({ deptModes }: { deptModes: Record<string, 'sandbox' | 'governed'> }) {
  // All 1000 events — filters applied client-side
  const [verdictFilter, setVerdictFilter] = useState('all')
  const [agentFilter, setAgentFilter]     = useState('')
  const [vendorFilter, setVendorFilter]   = useState('all')
  const [intentFilter, setIntentFilter]   = useState('')
  const [policyFilter, setPolicyFilter]   = useState('')
  const [startFilter, setStartFilter]     = useState('')
  const [endFilter, setEndFilter]         = useState('')
  const [filterTab, setFilterTab]         = useState<'all' | 'shared'>('all')
  const [page, setPage]                   = useState(1)
  const PAGE_SIZE = 50

  const [sharedAudits, setSharedAudits]   = useState<SharedAuditRecord[]>(() => loadShared())

  // Detail modal
  const [selected, setSelected]           = useState<DemoEvent | null>(null)
  const [modalOpen, setModalOpen]         = useState(false)

  // Share modal
  const [shareRecord, setShareRecord]     = useState<DemoEvent | null>(null)
  const [shareOpen, setShareOpen]         = useState(false)
  const [shareEmails, setShareEmails]     = useState<string[]>([])
  const [shareInput, setShareInput]       = useState('')
  const [shareNote, setShareNote]         = useState('')
  const [sharing, setSharing]             = useState(false)

  const sharedIds = new Set(sharedAudits.map(s => s.recordId))

  // Filter logic
  const filtered = ALL_EVENTS.filter(e => {
    if (verdictFilter !== 'all' && e.verdict.toLowerCase() !== verdictFilter) return false
    if (agentFilter   && !e.agent.toLowerCase().includes(agentFilter.toLowerCase())) return false
    if (vendorFilter !== 'all' && e.vendorId !== vendorFilter) return false
    if (intentFilter  && !e.intentId.toLowerCase().includes(intentFilter.toLowerCase())) return false
    if (policyFilter  && !e.policyVersion.toLowerCase().includes(policyFilter.toLowerCase())) return false
    if (startFilter) {
      const start = new Date(startFilter)
      if (e.ts < start) return false
    }
    if (endFilter) {
      const end = new Date(endFilter); end.setHours(23,59,59,999)
      if (e.ts > end) return false
    }
    return true
  })

  const displayed = filterTab === 'shared' ? filtered.filter(e => sharedIds.has(e.id)) : filtered
  const paged     = displayed.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(displayed.length / PAGE_SIZE)

  const clearFilters = () => {
    setVerdictFilter('all'); setAgentFilter(''); setVendorFilter('all')
    setIntentFilter(''); setPolicyFilter(''); setStartFilter(''); setEndFilter(''); setPage(1)
  }
  const last5Min = () => {
    const now = new Date(); const ago = new Date(now.getTime() - 5*60*1000)
    setStartFilter(ago.toISOString().slice(0,16)); setEndFilter(now.toISOString().slice(0,16)); setPage(1)
  }

  // Export CSV
  const exportCSV = () => {
    const hdrs = ['ID','Timestamp','Verdict','Tool.Op','Agent ID','Vendor ID','Vendor Name','Device ID','Device Name','Department','Patient ID','Reason','Intent ID','Policy Version','Latency ms','Risk Score']
    const rows = displayed.map(e => [
      e.id, e.ts.toISOString(), e.verdict, e.toolOp, e.agent,
      e.vendorId, e.vendorName, e.deviceId ?? '', e.deviceName ?? '',
      e.deptLabel, e.patientId, e.reasonCode ?? '', e.intentId, e.policyVersion, e.latencyMs, e.riskScore,
    ])
    const csv = [hdrs, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n')
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([csv], { type:'text/csv' })),
      download: `stmercy-audit-${new Date().toISOString().split('T')[0]}.csv`,
    }); a.click()
  }

  // Export JSON
  const exportJSON = () => {
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([JSON.stringify(displayed, null, 2)], { type:'application/json' })),
      download: `stmercy-audit-${new Date().toISOString().split('T')[0]}.json`,
    }); a.click()
  }

  // Share helpers
  const addEmail = (email: string) => {
    const t = email.trim()
    if (!t || shareEmails.includes(t)) return
    setShareEmails(prev => [...prev, t]); setShareInput('')
  }
  const doShare = async () => {
    if (!shareRecord || shareEmails.length === 0) return
    setSharing(true)
    await new Promise(r => setTimeout(r, 400))
    const obj: SharedAuditRecord = {
      id: `share_${Date.now()}`,
      recordId: shareRecord.id,
      summary: { toolOp: shareRecord.toolOp, verdict: shareRecord.verdict, ts: shareRecord.ts.toISOString() },
      sharedBy: 'dr.chen@stmercy.org',
      sharedWith: shareEmails,
      note: shareNote.trim(),
      sharedAt: new Date().toISOString(),
    }
    const next = [obj, ...sharedAudits]; saveShared(next); setSharedAudits(next)
    setSharing(false); setShareOpen(false); setShareEmails([]); setShareNote('')
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <motion.div initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }}
        className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Audit Log</h1>
          <p className="text-muted-foreground text-sm mt-1">Complete HIPAA-compliant audit trail · {ALL_EVENTS.length.toLocaleString()} records · SHA-256 hash chain</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="green"><CheckCircle2 size={10} /> Chain Verified</Badge>
          <Button variant="outline" size="sm" onClick={exportCSV}>
            <FileSpreadsheet size={13} /> Export CSV
          </Button>
          <Button variant="outline" size="sm" onClick={exportJSON}>
            <FileJson size={13} /> Export JSON
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPage(1)}>
            <RefreshCcw size={13} /> Refresh
          </Button>
        </div>
      </motion.div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 w-fit">
        {(['all', 'shared'] as const).map(t => (
          <button key={t} onClick={() => { setFilterTab(t); setPage(1) }}
            className={cn('text-xs px-3 py-1.5 rounded-lg transition-colors',
              filterTab === t ? 'bg-white/10 text-foreground font-medium' : 'text-muted-foreground hover:text-foreground')}>
            {t === 'all' ? `All records (${ALL_EVENTS.length.toLocaleString()})` : `Shared (${sharedIds.size})`}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <div className="space-y-3">
          {/* Row 1 */}
          <div className="flex flex-wrap gap-3">
            <select value={verdictFilter} onChange={e => { setVerdictFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
              style={DARK_SELECT_STYLE}>
              <option value="all">All Verdicts</option>
              <option value="allow">ALLOW</option>
              <option value="block">BLOCK</option>
              <option value="escalate">ESCALATE</option>
            </select>
            <select value={vendorFilter} onChange={e => { setVendorFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[180px]"
              style={DARK_SELECT_STYLE}>
              <option value="all">All Vendors</option>
              {ALL_VENDORS.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            <input value={agentFilter} onChange={e => { setAgentFilter(e.target.value); setPage(1) }}
              placeholder="Agent ID…"
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[160px]" />
          </div>
          {/* Row 2 */}
          <div className="flex flex-wrap gap-3">
            <input value={intentFilter} onChange={e => { setIntentFilter(e.target.value); setPage(1) }}
              placeholder="Intent ID (e.g. int_a1b2c3d4)…"
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[220px]" />
            <input value={policyFilter} onChange={e => { setPolicyFilter(e.target.value); setPage(1) }}
              placeholder="Policy version (e.g. clinical-safety)…"
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
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden lg:table-cell">Vendor</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden xl:table-cell">Device</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden md:table-cell">Reason</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden lg:table-cell">Reviewer</th>
                <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden xl:table-cell">Policy Version</th>
                <th className="text-right px-4 py-3 font-semibold uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paged.length === 0 ? (
                <tr><td colSpan={10} className="px-4 py-10 text-center text-muted-foreground">
                  {filterTab === 'shared' ? 'No shared records yet. Share records using the Share button.' : 'No records match the selected filters.'}
                </td></tr>
              ) : paged.map((e, i) => {
                const isShared = sharedIds.has(e.id)
                return (
                  <tr key={e.id}
                    data-cite-id={e.id}
                    className={cn('border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors', i === 0 && page === 1 ? 'animate-slideIn' : '')}>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground whitespace-nowrap">
                      {e.ts.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5"><VerdictBadge verdict={e.verdict} /></td>
                    <td className="px-4 py-2.5 text-foreground/80">{fmtOp(e.toolOp)}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <DeptIcon deptKey={e.department} size={11} />
                        <span className="font-mono text-muted-foreground">{e.agent}</span>
                        <span
                          className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-widest"
                          style={{
                            background: (deptModes[e.department] ?? 'governed') === 'sandbox' ? 'rgba(59,130,246,0.10)' : 'rgba(74,222,128,0.10)',
                            color: (deptModes[e.department] ?? 'governed') === 'sandbox' ? '#93c5fd' : '#86efac',
                            border: (deptModes[e.department] ?? 'governed') === 'sandbox' ? '1px solid rgba(59,130,246,0.22)' : '1px solid rgba(74,222,128,0.22)',
                          }}
                        >
                          {(deptModes[e.department] ?? 'governed') === 'sandbox' ? 'sandbox' : 'governed'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 hidden lg:table-cell">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-[11px] font-medium text-foreground/80">{e.vendorName}</span>
                        <span className="font-mono text-[10px] text-muted-foreground/50">{e.vendorId}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 hidden xl:table-cell">
                      {e.deviceName ? (
                        <div className="flex flex-col gap-0.5">
                          <span className="text-[11px] text-foreground/70">{e.deviceName}</span>
                          <span className="font-mono text-[10px] text-muted-foreground/50">{e.deviceId}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground/30">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell">
                      {e.reasonCode
                        ? <span className="text-amber-400 font-medium">{fmtReason(e.reasonCode)}</span>
                        : <span className="text-muted-foreground/30">—</span>}
                    </td>
                    <td className="px-4 py-2.5 hidden lg:table-cell">
                      {e.verdict === 'ESCALATE' ? (
                        e.reviewStatus === 'approved' ? (
                          <div className="flex items-center gap-1.5">
                            <CheckCircle2 size={11} className="text-emerald-400 shrink-0" />
                            <span className="text-emerald-400 text-[11px] font-medium">{e.reviewedBy}</span>
                          </div>
                        ) : e.reviewStatus === 'denied' ? (
                          <div className="flex items-center gap-1.5">
                            <XCircle size={11} className="text-red-400 shrink-0" />
                            <span className="text-red-400 text-[11px] font-medium">{e.reviewedBy}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <AlertTriangle size={11} className="text-amber-400 shrink-0" />
                            <span className="text-amber-400/70 text-[11px]">Pending</span>
                          </div>
                        )
                      ) : (
                        <span className="text-muted-foreground/30">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 hidden xl:table-cell">
                      <span className="font-mono text-muted-foreground/60 text-[11px]">{e.policyVersion}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {isShared && (
                          <Badge variant="outline" className="text-[10px] border-primary/30 text-primary bg-primary/10 mr-1">Shared</Badge>
                        )}
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
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}>
              <ChevronLeft size={13} /> Prev
            </Button>
            <span className="px-1">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p+1))} disabled={page >= totalPages}>
              Next <ChevronRight size={13} />
            </Button>
          </div>
        </div>
      )}

      {/* ── Detail Modal ── */}
      {modalOpen && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setModalOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <motion.div initial={{ opacity:0, scale:0.96, y:8 }} animate={{ opacity:1, scale:1, y:0 }}
            onClick={e => e.stopPropagation()}
            className="relative glass-card w-full max-w-xl max-h-[85vh] overflow-y-auto p-4 z-10">
            {/* Close */}
            <button onClick={() => setModalOpen(false)}
              className="absolute top-3 right-3 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors">
              <X size={15} />
            </button>

            {/* Title */}
            <div className="flex items-center gap-2.5 mb-3 pr-8">
              <span className="text-sm font-semibold text-foreground">{fmtOp(selected.toolOp)}</span>
              <VerdictBadge verdict={selected.verdict} />
            </div>

            {/* Meta grid */}
            <div className="grid grid-cols-3 gap-2 text-xs mb-3">
              {[
                { label: 'Timestamp',      value: selected.ts.toLocaleString() },
                { label: 'Agent ID',       value: selected.agent },
                { label: 'Patient ID',     value: selected.patientId },
                { label: 'Department',     value: selected.deptLabel },
                { label: 'Block Reason',   value: fmtReason(selected.reasonCode) ?? '—' },
                { label: 'Latency / Risk', value: `${selected.latencyMs}ms · ${selected.riskScore}/100` },
                { label: 'Vendor',         value: `${selected.vendorName} (${selected.vendorId})` },
                { label: 'Device',         value: selected.deviceName ? `${selected.deviceName} · ${selected.deviceId}` : '—' },
              ].map(({ label, value }) => (
                <div key={label} className="bg-secondary/30 rounded-lg px-2.5 py-1.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
                  <p className="font-mono text-[11px] text-foreground/90 break-all">{value}</p>
                </div>
              ))}
            </div>

            {/* Explanation */}
            <div className="mb-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Decision Explanation</p>
              <p className="text-xs bg-secondary/30 rounded-lg px-2.5 py-2 text-foreground/80 leading-relaxed">{selected.explanation}</p>
            </div>

            {/* Human Review — only for ESCALATE */}
            {selected.verdict === 'ESCALATE' && (
              <div className="mb-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Human Review</p>
                {selected.reviewStatus === 'pending' ? (
                  <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-2">
                    <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                    <div>
                      <p className="text-amber-400 text-xs font-semibold">Awaiting Physician Review</p>
                      <p className="text-muted-foreground text-[11px]">Action paused — pending human approval.</p>
                    </div>
                  </div>
                ) : (
                  <div className={`bg-secondary/30 rounded-lg px-2.5 py-2 border ${selected.reviewStatus === 'approved' ? 'border-emerald-500/20' : 'border-red-500/20'}`}>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      {selected.reviewStatus === 'approved'
                        ? <CheckCircle2 size={12} className="text-emerald-400" />
                        : <XCircle size={12} className="text-red-400" />}
                      <span className={`text-xs font-semibold ${selected.reviewStatus === 'approved' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {selected.reviewStatus === 'approved' ? 'Approved' : 'Denied'} by {selected.reviewedBy}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                      <div>
                        <p className="text-muted-foreground/60 uppercase tracking-wider text-[10px] mb-0.5">Reviewer</p>
                        <p className="font-mono text-foreground/80">{selected.reviewedByEmail}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground/60 uppercase tracking-wider text-[10px] mb-0.5">Reviewed At</p>
                        <p className="font-mono text-foreground/80">{selected.reviewedAt?.toLocaleString()}</p>
                      </div>
                      {selected.reviewReason && (
                        <div className="col-span-2">
                          <p className="text-muted-foreground/60 uppercase tracking-wider text-[10px] mb-0.5">Reason</p>
                          <p className="text-foreground/80">{selected.reviewReason}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Chain Hash */}
            <div className="mb-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Chain Hash</p>
              <div className="flex items-center gap-2 bg-secondary/30 rounded-lg px-2.5 py-1.5">
                <Hash size={11} className="text-muted-foreground/50 shrink-0" />
                <span className="font-mono text-[11px] text-muted-foreground/70 break-all">{selected.hash}</span>
              </div>
            </div>

            {/* Request payload */}
            <div className="mb-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Request Payload</p>
              <pre className="p-2.5 bg-secondary/50 rounded-lg text-[11px] font-mono text-foreground/70 overflow-x-auto whitespace-pre-wrap break-all">
{JSON.stringify({
  agent_id: selected.agent,
  intent_id: selected.intentId,
  tool: { op: selected.toolOp },
  patient_id: selected.patientId,
  policy_version: selected.policyVersion,
  timestamp: selected.ts.toISOString(),
}, null, 2)}
              </pre>
            </div>

            <Button variant="outline" size="sm" onClick={() => { setModalOpen(false); setShareRecord(selected); setShareEmails([]); setShareInput(''); setShareNote(''); setShareOpen(true) }}>
              <Share2 size={13} /> Share this record
            </Button>
          </motion.div>
        </div>
      )}

      {/* ── Share Modal ── */}
      {shareOpen && shareRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShareOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <motion.div initial={{ opacity:0, scale:0.96, y:8 }} animate={{ opacity:1, scale:1, y:0 }}
            onClick={e => e.stopPropagation()}
            className="relative glass-card w-full max-w-md p-6 z-10">
            <button onClick={() => setShareOpen(false)}
              className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors">
              <X size={16} />
            </button>

            <div className="flex items-center gap-2 mb-5">
              <Share2 size={16} className="text-primary" />
              <h3 className="text-base font-semibold">Share Audit Record</h3>
            </div>

            {/* Record summary */}
            <div className="rounded-xl border border-white/10 bg-secondary/30 px-3 py-2.5 flex items-center gap-3 text-xs mb-4">
              <VerdictBadge verdict={shareRecord.verdict} />
              <span className="font-mono text-foreground/80 truncate">{shareRecord.toolOp}</span>
              <span className="text-muted-foreground ml-auto shrink-0">{shareRecord.ts.toLocaleString()}</span>
            </div>

            {/* Team quick-add */}
            <p className="text-xs text-muted-foreground mb-2">Share with</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {TEAM_MEMBERS.map(m => (
                <button key={m.email} onClick={() => addEmail(m.email)} disabled={shareEmails.includes(m.email)}
                  className={cn('text-xs px-2.5 py-1 rounded-lg border transition-colors',
                    shareEmails.includes(m.email)
                      ? 'border-primary/30 bg-primary/10 text-primary cursor-default'
                      : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground hover:border-white/20')}>
                  {m.name}
                </button>
              ))}
            </div>

            {/* Manual email */}
            <div className="flex gap-2 mb-3">
              <input value={shareInput} onChange={e => setShareInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addEmail(shareInput) } }}
                placeholder="Add email address…"
                className="flex-1 h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50" />
              <Button size="sm" variant="outline" onClick={() => addEmail(shareInput)} disabled={!shareInput.trim()}>Add</Button>
            </div>

            {/* Email chips */}
            {shareEmails.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {shareEmails.map(email => (
                  <span key={email} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-white/20 bg-white/5 text-foreground/80">
                    {email}
                    <button onClick={() => setShareEmails(prev => prev.filter(e => e !== email))}
                      className="ml-0.5 text-muted-foreground hover:text-foreground">×</button>
                  </span>
                ))}
              </div>
            )}

            {/* Note */}
            <p className="text-xs text-muted-foreground mb-1">Note (optional)</p>
            <textarea value={shareNote} onChange={e => setShareNote(e.target.value.slice(0,200))}
              placeholder="Add context for your team…" maxLength={200} rows={3}
              className="w-full rounded-xl border border-white/15 bg-secondary/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none mb-1" />
            <p className="text-[10px] text-muted-foreground/50 text-right mb-4">{shareNote.length}/200</p>

            {/* Visibility note */}
            <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground mb-4">
              <span className="w-2.5 h-2.5 rounded-full border-2 border-primary bg-primary/30 shrink-0" />
              Team members only · HIPAA-compliant sharing
            </div>

            <div className="flex items-center gap-2">
              <Button onClick={doShare} disabled={sharing || shareEmails.length === 0} className="flex-1">
                {sharing
                  ? <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sharing…</>
                  : <><Share2 size={14} /> Share</>}
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

interface PolicyOperation {
  code: string
  label: string
  description: string
}

const ALLOWED_OPERATIONS: PolicyOperation[] = [
  { code: 'patient.vitals.read',      label: 'Read patient vital signs',        description: 'View heart rate, blood pressure, oxygen levels, and temperature in real time' },
  { code: 'lab.results.fetch',        label: 'Retrieve lab results',            description: 'Access completed blood work, cultures, and pathology reports' },
  { code: 'imaging.scan.view',        label: 'View imaging scans',              description: 'Display X-rays, MRI, CT, and ultrasound images for review' },
  { code: 'ehr.record.read',          label: 'Read patient chart',              description: 'Access full patient history, clinical notes, and medication list' },
  { code: 'medication.schedule.read', label: 'View medication schedule',        description: "See a patient's current prescriptions and dosing timetable" },
  { code: 'appointment.list',         label: 'View appointments',               description: 'See upcoming and past patient appointments and scheduling' },
  { code: 'diagnosis.assist.query',   label: 'Request diagnostic suggestions',  description: 'Ask the AI to suggest possible diagnoses based on symptoms and test results' },
  { code: 'equipment.status.check',   label: 'Check device status',             description: 'Verify that ventilators, pumps, and monitors are operating correctly' },
  { code: 'alert.trigger.nurse',      label: 'Notify nursing staff',            description: 'Alert nurses to a change in patient condition that needs attention' },
  { code: 'iv.drip.monitor',          label: 'Monitor IV drip rate',            description: 'Read current infusion pump settings — no changes are permitted' },
  { code: 'ecg.stream.read',          label: 'Read heart rhythm (ECG)',         description: 'Access live and historical electrocardiogram data for a patient' },
  { code: 'patient.location.track',   label: 'Track patient location',          description: 'See which room or bed a patient is currently assigned to' },
]

const BLOCKED_OPERATIONS: PolicyOperation[] = [
  { code: 'medication.dose.override',        label: 'Override a medication dosage',         description: 'Change a prescribed dose without physician sign-off — always prevented' },
  { code: 'ehr.bulk.export',                 label: 'Bulk-export patient records',          description: 'Download large numbers of patient records to an outside location' },
  { code: 'patient.data.transfer.external',  label: 'Send patient data outside hospital',   description: 'Transmit patient information to any system outside the hospital network' },
  { code: 'controlled.substance.dispense',   label: 'Auto-dispense a controlled substance', description: 'Automatically dispense opioids, sedatives, or other restricted medications' },
  { code: 'consent.bypass',                  label: 'Skip patient consent check',           description: 'Access or act on patient data without verifying consent is on file' },
  { code: 'diagnosis.override.physician',    label: "Override a physician's diagnosis",     description: 'Replace or remove a diagnosis recorded by a licensed physician' },
  { code: 'equipment.calibration.skip',      label: 'Skip device calibration',              description: 'Use medical equipment without completing required safety calibration' },
  { code: 'surgery.protocol.deviate',        label: 'Deviate from surgical protocol',       description: 'Perform a step outside the approved surgical safety checklist sequence' },
]

const PHYSICIAN_CONFIRM: PolicyOperation[] = [
  { code: 'emergency.surgery.authorize',  label: 'Authorize emergency surgery',           description: 'Grant permission to begin an unplanned or urgent surgical procedure' },
  { code: 'high.risk.medication.approve', label: 'Approve a high-risk medication order',  description: 'Sign off on chemotherapy, anticoagulants, or other high-alert drug orders' },
  { code: 'dnr.status.update',            label: 'Change a DNR / advance directive',      description: "Update or remove a patient's Do-Not-Resuscitate order on file" },
  { code: 'patient.discharge.approve',    label: 'Approve patient discharge',             description: 'Authorize a patient to leave inpatient care' },
  { code: 'critical.alert.escalate',      label: 'Escalate a critical alert',             description: 'Upgrade an alert to highest priority — notifies the full care team immediately' },
]

type RuleAction = 'allow' | 'block' | 'confirm'

interface AgentRule {
  id: string
  agentScope: string
  device: string
  task: string
  taskLabel: string
  action: RuleAction
}

const COMPLIANCE_STANDARDS = [
  { label: 'HIPAA',            desc: 'Patient data privacy & security' },
  { label: 'HITECH',           desc: 'Health IT breach enforcement' },
  { label: 'FDA SaMD',         desc: 'Software as a Medical Device' },
  { label: 'DEA',              desc: 'Controlled substance controls' },
  { label: 'Joint Commission', desc: 'Clinical safety standards' },
  { label: 'ISO 13485',        desc: 'Medical device quality management' },
  { label: '45 CFR 46',        desc: 'Research subject protection' },
]

interface PolicyDevice {
  label: string
  description: string
  departments: string[]   // which agent departments typically operate this
}

const POLICY_DEVICES: PolicyDevice[] = [
  { label: 'Any device',              description: 'Applies to all hardware and systems',                                    departments: [] },
  { label: 'Ventilator',              description: 'Mechanical ventilator controlling a patient\'s breathing',               departments: ['icu', 'surgical', 'emergency'] },
  { label: 'Infusion pump',           description: 'IV pump delivering fluids, medications, or nutrition',                   departments: ['icu', 'monitoring', 'nurse'] },
  { label: 'ECG / cardiac monitor',   description: 'Continuous heart rhythm and vital signs monitor',                       departments: ['icu', 'cardiology', 'monitoring', 'emergency'] },
  { label: 'MRI machine',             description: 'Magnetic resonance imaging scanner',                                    departments: ['radiology', 'neuro'] },
  { label: 'CT scanner',              description: 'Computed tomography X-ray scanner',                                     departments: ['radiology', 'emergency'] },
  { label: 'Surgical robot arm',      description: 'Robotic system assisting or performing surgical procedures',            departments: ['surgical'] },
  { label: 'Medication dispenser',    description: 'Automated cabinet dispensing drugs to nursing units',                   departments: ['pharmacy'] },
  { label: 'Lab analyzer',            description: 'Instrument processing blood, urine, or tissue samples',                 departments: ['lab'] },
  { label: 'Patient call system',     description: 'Nurse call and bed-side communication unit',                            departments: ['nurse', 'monitoring'] },
  { label: 'EHR workstation',         description: 'Computer terminal connected to the electronic health record system',    departments: ['ehr', 'scheduling'] },
  { label: 'Telehealth terminal',     description: 'Video consultation endpoint for remote patient visits',                 departments: ['telehealth'] },
  { label: 'Defibrillator / AED',     description: 'Device delivering an electric shock to restore normal heart rhythm',   departments: ['emergency', 'icu', 'cardiology'] },
  { label: 'Radiation therapy unit',  description: 'Targeted radiation delivery system for oncology treatment',             departments: ['radiology'] },
  { label: 'Patient wristband scanner', description: 'Barcode or RFID scanner verifying patient identity at bedside',      departments: ['nurse', 'pharmacy', 'ehr'] },
]

function PoliciesTab() {
  const [rules, setRules] = useState<AgentRule[]>([])
  const [showForm, setShowForm] = useState(false)
  const [agentScope, setAgentScope] = useState('All agents')
  const [device, setDevice] = useState(POLICY_DEVICES[0].label)
  const [taskCode, setTaskCode] = useState('')
  const [action, setAction] = useState<RuleAction>('allow')
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, 'approved' | 'denied'>>({})

  const pendingReviews = ALL_EVENTS
    .filter(e => e.verdict === 'ESCALATE' && e.reviewStatus === 'pending')
    .slice(0, 7)

  const blockSummary = Object.entries(
    ALL_EVENTS
      .filter(e => e.verdict === 'BLOCK' && e.reasonCode)
      .reduce<Record<string, { count: number; example: string }>>((acc, e) => {
        const key = e.reasonCode!
        if (!acc[key]) acc[key] = { count: 0, example: fmtOp(e.toolOp) }
        acc[key].count++
        return acc
      }, {})
  )
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 5)

  const agentScopeOptions = [
    { label: 'All agents', deptKey: '' },
    ...DEPARTMENTS.map(d => ({ label: `All ${d.label} agents`, deptKey: d.key })),
  ]

  // When a specific department is chosen, surface that dept's devices first
  const selectedDeptKey = agentScopeOptions.find(o => o.label === agentScope)?.deptKey ?? ''
  const relevantDevices = selectedDeptKey
    ? [
        POLICY_DEVICES[0],  // "Any device" always first
        ...POLICY_DEVICES.filter(d => d.departments.includes(selectedDeptKey)),
        ...POLICY_DEVICES.filter(d => d.departments.length > 0 && !d.departments.includes(selectedDeptKey)),
      ]
    : POLICY_DEVICES

  const allOps = [...ALLOWED_OPERATIONS, ...BLOCKED_OPERATIONS, ...PHYSICIAN_CONFIRM]

  function addRule() {
    if (!taskCode) return
    const op = allOps.find(o => o.code === taskCode)
    if (!op) return
    setRules(prev => [...prev, {
      id: `rule-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      agentScope,
      device,
      task: taskCode,
      taskLabel: op.label,
      action,
    }])
    setTaskCode('')
    setShowForm(false)
  }

  const actionBadge = {
    allow:   { label: 'Allowed',          variant: 'green'  as const, icon: CheckCircle2 },
    block:   { label: 'Blocked',          variant: 'red'    as const, icon: XCircle },
    confirm: { label: 'Ask doctor first', variant: 'amber'  as const, icon: AlertTriangle },
  }

  const selectClass = 'w-full bg-black/30 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all'

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Policy Management</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Clinical Safety Mode active · St. Mercy Health System · 500 agents enrolled
        </p>
      </div>

      {/* ── What agents can / cannot do ─────────────────────────────────── */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">What agents can and cannot do</h2>
        <p className="text-xs text-muted-foreground mb-4">
          These rules apply to all 500 agents under the current Clinical Safety policy pack.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          {/* Allowed */}
          <div className="glass-card p-4 border-emerald-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                <CheckCircle2 size={14} className="text-emerald-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-emerald-400 leading-tight">Agents can do this</h3>
                <p className="text-xs text-muted-foreground">No approval needed</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-emerald-500/10 px-2 py-0.5 rounded-full">
                {ALLOWED_OPERATIONS.length}
              </span>
            </div>
            <div className="space-y-3.5">
              {ALLOWED_OPERATIONS.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Blocked */}
          <div className="glass-card p-4 border-red-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-red-500/15 flex items-center justify-center shrink-0">
                <XCircle size={14} className="text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-red-400 leading-tight">Agents cannot do this</h3>
                <p className="text-xs text-muted-foreground">Always stopped — no exceptions</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-red-500/10 px-2 py-0.5 rounded-full">
                {BLOCKED_OPERATIONS.length}
              </span>
            </div>
            <div className="space-y-3.5">
              {BLOCKED_OPERATIONS.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Confirm */}
          <div className="glass-card p-4 border-amber-500/20">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-amber-500/15 flex items-center justify-center shrink-0">
                <AlertTriangle size={14} className="text-amber-400" />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-amber-400 leading-tight">Doctor must confirm first</h3>
                <p className="text-xs text-muted-foreground">Agent pauses and waits for your approval</p>
              </div>
              <span className="ml-auto text-xs text-muted-foreground bg-amber-500/10 px-2 py-0.5 rounded-full">
                {PHYSICIAN_CONFIRM.length}
              </span>
            </div>
            <div className="space-y-3.5">
              {PHYSICIAN_CONFIRM.map(op => (
                <div key={op.code}>
                  <p className="text-xs font-medium text-foreground leading-tight">{op.label}</p>
                  <p className="text-xs text-muted-foreground/60 mt-0.5 leading-relaxed">{op.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Agent-level targeted rules ──────────────────────────────────── */}
      <div>
        <div className="flex items-start justify-between gap-4 mb-1">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Agent-Level Rules</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Pin a rule to a specific agent, device, or task. These override the global policy above.
            </p>
          </div>
          <Button
            size="sm"
            variant={showForm ? 'outline' : 'default'}
            onClick={() => setShowForm(f => !f)}
            className="shrink-0"
          >
            {showForm ? <X size={13} /> : <Plus size={13} />}
            {showForm ? 'Cancel' : 'Add a rule'}
          </Button>
        </div>

        {/* Add rule form */}
        <AnimatePresence>
          {showForm && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="glass-card p-5 border-primary/20 mt-3 mb-4 space-y-4">
                <h3 className="text-sm font-semibold text-foreground">New targeted rule</h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                  {/* Agent scope */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      Which agents?
                    </label>
                    <select value={agentScope} onChange={e => setAgentScope(e.target.value)} className={selectClass} style={DARK_SELECT_STYLE}>
                      {agentScopeOptions.map(o => <option key={o.label} value={o.label}>{o.label}</option>)}
                    </select>
                  </div>

                  {/* Device */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      On which device / equipment?
                    </label>
                    <select value={device} onChange={e => setDevice(e.target.value)} className={selectClass} style={DARK_SELECT_STYLE}>
                      {relevantDevices.map((d, i) => {
                        const isSeparator = i === 1 && selectedDeptKey  // visual hint after "Any device"
                        return (
                          <option key={d.label} value={d.label}>
                            {isSeparator && i === 1 ? d.label : d.label}
                          </option>
                        )
                      })}
                    </select>
                    {device !== POLICY_DEVICES[0].label && (
                      <p className="mt-1 text-xs text-muted-foreground/60 leading-snug">
                        {POLICY_DEVICES.find(d => d.label === device)?.description}
                      </p>
                    )}
                  </div>

                  {/* Task */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      Trying to do what?
                    </label>
                    <select value={taskCode} onChange={e => setTaskCode(e.target.value)} className={selectClass} style={DARK_SELECT_STYLE}>
                      <option value="">— Choose a task —</option>
                      <optgroup label="Currently allowed">
                        {ALLOWED_OPERATIONS.map(op => (
                          <option key={op.code} value={op.code}>{op.label}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Currently blocked">
                        {BLOCKED_OPERATIONS.map(op => (
                          <option key={op.code} value={op.code}>{op.label}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Requires confirmation">
                        {PHYSICIAN_CONFIRM.map(op => (
                          <option key={op.code} value={op.code}>{op.label}</option>
                        ))}
                      </optgroup>
                    </select>
                  </div>

                  {/* Action */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      What should happen?
                    </label>
                    <div className="flex gap-2 h-[38px]">
                      {(['allow', 'block', 'confirm'] as RuleAction[]).map(a => (
                        <button
                          key={a}
                          type="button"
                          onClick={() => setAction(a)}
                          className={cn(
                            'flex-1 rounded-xl text-xs font-medium border transition-all',
                            action === a && a === 'allow'   && 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400',
                            action === a && a === 'block'   && 'bg-red-500/20 border-red-500/40 text-red-400',
                            action === a && a === 'confirm' && 'bg-amber-500/20 border-amber-500/40 text-amber-400',
                            action !== a && 'bg-secondary border-white/10 text-muted-foreground hover:border-white/20',
                          )}
                        >
                          {a === 'allow' ? 'Allow' : a === 'block' ? 'Block' : 'Ask doctor'}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Preview */}
                {taskCode && (
                  <div className="rounded-xl bg-white/3 border border-white/8 px-4 py-3 text-xs text-muted-foreground">
                    <span className="text-foreground font-medium">{agentScope}</span>
                    {' '}on a{' '}
                    <span className="text-foreground font-medium">{device === POLICY_DEVICES[0].label ? 'any device' : `a ${device.toLowerCase()}`}</span>
                    {' '}trying to{' '}
                    <span className="text-foreground font-medium">{allOps.find(o => o.code === taskCode)?.label.toLowerCase()}</span>
                    {' '}will be{' '}
                    <span className={cn(
                      'font-semibold',
                      action === 'allow' && 'text-emerald-400',
                      action === 'block' && 'text-red-400',
                      action === 'confirm' && 'text-amber-400',
                    )}>
                      {action === 'allow' ? 'allowed automatically' : action === 'block' ? 'blocked immediately' : 'paused until a doctor approves'}
                    </span>.
                  </div>
                )}

                <div className="flex justify-end">
                  <Button size="sm" onClick={addRule} disabled={!taskCode}>
                    Save rule
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Rules list */}
        {rules.length === 0 ? (
          <div className="glass-card p-8 flex flex-col items-center justify-center text-center mt-3 border-dashed">
            <Shield size={28} className="text-muted-foreground/25 mb-3" />
            <p className="text-sm font-medium text-muted-foreground">No custom rules yet</p>
            <p className="text-xs text-muted-foreground/50 mt-1 max-w-xs">
              Add a rule above to override the global policy for a specific agent, device, or task.
            </p>
          </div>
        ) : (
          <div className="space-y-2 mt-3">
            <AnimatePresence>
              {rules.map(rule => {
                const ab = actionBadge[rule.action]
                const AbIcon = ab.icon
                return (
                  <motion.div
                    key={rule.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 8 }}
                    className="glass-card px-4 py-3 flex items-center gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap text-xs">
                        <span className="font-medium text-foreground">{rule.agentScope}</span>
                        <span className="text-muted-foreground/40">·</span>
                        <span className="text-muted-foreground">{rule.device}</span>
                        <span className="text-muted-foreground/40">·</span>
                        <span className="text-muted-foreground">{rule.taskLabel}</span>
                      </div>
                    </div>
                    <Badge variant={ab.variant}>
                      <AbIcon size={10} />
                      {ab.label}
                    </Badge>
                    <button
                      onClick={() => setRules(prev => prev.filter(r => r.id !== rule.id))}
                      className="text-muted-foreground/30 hover:text-red-400 transition-colors ml-1 shrink-0"
                      title="Remove rule"
                    >
                      <X size={14} />
                    </button>
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* ── Clinical Safety — always active baseline ────────────────────── */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">Active Baseline Policy</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Clinical Safety Mode is permanently on for all 500 agents. It cannot be switched off or replaced.
        </p>
        <div className="glass-card p-5 border-emerald-500/25">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
              <Shield size={18} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <h3 className="font-bold text-base text-foreground">Clinical Safety Mode</h3>
                <Badge variant="green">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
                  Always active · 500 agents
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-5">
                The hospital-wide safety baseline. Every AI agent in St. Mercy operates under these rules at all times.
              </p>
              {/* Compliance standards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {COMPLIANCE_STANDARDS.map(s => (
                  <div key={s.label} className="bg-white/4 border border-white/8 rounded-xl px-3 py-2.5">
                    <p className="text-xs font-bold text-foreground">{s.label}</p>
                    <p className="text-xs text-muted-foreground/60 mt-0.5 leading-snug">{s.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Pending physician review ──────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <ClipboardList size={15} className="text-amber-400" />
          <h2 className="text-sm font-semibold text-foreground">Pending Your Review</h2>
          {pendingReviews.length > 0 && (
            <span className="text-xs bg-amber-500/15 text-amber-400 border border-amber-500/25 rounded-full px-2 py-0.5 font-semibold">
              {pendingReviews.filter(e => !reviewDecisions[e.id]).length}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          These agent actions require your sign-off before they can proceed.
        </p>
        {pendingReviews.filter(e => !reviewDecisions[e.id]).length === 0 ? (
          <div className="glass-card p-6 text-center">
            <CheckCircle2 size={20} className="text-emerald-400 mx-auto mb-2" />
            <p className="text-sm text-foreground font-medium">All caught up</p>
            <p className="text-xs text-muted-foreground mt-1">No actions are waiting for your review.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pendingReviews.filter(e => !reviewDecisions[e.id]).map((e, i) => {
              const urgencyStyle = {
                critical: { bar: 'bg-red-500',    text: 'text-red-400',    badge: 'bg-red-500/15 border-red-500/30 text-red-400',    label: 'Critical' },
                urgent:   { bar: 'bg-amber-500',  text: 'text-amber-400',  badge: 'bg-amber-500/15 border-amber-500/30 text-amber-400',  label: 'Urgent' },
                routine:  { bar: 'bg-sky-500',    text: 'text-sky-400',    badge: 'bg-sky-500/15 border-sky-500/30 text-sky-400',    label: 'Routine' },
              }[e.urgency ?? 'routine']
              const riskColor = e.riskScore >= 70 ? 'text-red-400' : e.riskScore >= 40 ? 'text-amber-400' : 'text-emerald-400'
              return (
                <motion.div
                  key={e.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="glass-card overflow-hidden"
                >
                  {/* Urgency stripe */}
                  <div className={cn('h-0.5 w-full', urgencyStyle.bar)} />

                  <div className="px-4 pt-3 pb-4">
                    {/* Header row */}
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-sm font-semibold text-foreground">{fmtOp(e.toolOp)}</span>
                          <span className={cn('text-[11px] font-semibold px-2 py-0.5 rounded-full border', urgencyStyle.badge)}>
                            {urgencyStyle.label}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                          <span className="font-mono">{e.agent}</span>
                          <span>·</span>
                          <span>{e.deptLabel}</span>
                          <span>·</span>
                          <span>Patient {e.patientId}</span>
                          <span>·</span>
                          <span>{formatTime(e.ts)}</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[10px] text-muted-foreground/50 mb-0.5">Risk score</p>
                        <p className={cn('text-sm font-bold font-mono', riskColor)}>{e.riskScore}<span className="text-muted-foreground/40 text-xs font-normal">/100</span></p>
                      </div>
                    </div>

                    {/* Clinical context */}
                    {e.clinicalContext && (
                      <div className="bg-secondary/40 border border-white/6 rounded-xl px-3 py-2.5 mb-3">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-1">What the agent detected</p>
                        <p className="text-xs text-foreground/80 leading-relaxed">{e.clinicalContext}</p>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setReviewDecisions(prev => ({ ...prev, [e.id]: 'denied' }))}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-red-500/30 text-red-400/80 text-xs font-medium hover:bg-red-500/10 transition-colors"
                      >
                        <ThumbsDown size={11} />
                        Deny
                      </button>
                      <button
                        onClick={() => setReviewDecisions(prev => ({ ...prev, [e.id]: 'approved' }))}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-emerald-500/30 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/10 transition-colors"
                      >
                        <ThumbsUp size={11} />
                        Approve
                      </button>
                      <span className="text-[11px] text-muted-foreground/40 ml-auto">Policy: {e.policyVersion}</span>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── What's being blocked this week ───────────────────────────── */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-1">What's Being Blocked</h2>
        <p className="text-xs text-muted-foreground mb-4">
          The most common reasons your agents are being stopped — useful for spotting gaps in care workflows.
        </p>
        <div className="glass-card divide-y divide-white/[0.04]">
          {blockSummary.map(([code, { count, example }], i) => {
            const maxCount = blockSummary[0][1].count
            return (
              <div key={code} className="px-4 py-3 flex items-center gap-4">
                <span className="text-xs text-muted-foreground/50 font-mono w-4 shrink-0">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-xs font-medium text-foreground">{fmtReason(code)}</span>
                    <span className="text-xs text-muted-foreground font-mono shrink-0">{count} blocks</span>
                  </div>
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden mb-1">
                    <div
                      className="h-full bg-red-400/50 rounded-full transition-all duration-500"
                      style={{ width: `${(count / maxCount) * 100}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-muted-foreground/50">e.g. {example}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── Aside Panel (AI reasoning for cited items) ───────────────────────────────

function getMockAsideExplanation(type: 'event' | 'agent', id: string): string {
  if (type === 'agent') {
    const a = ALL_AGENTS.find(ag => ag.id === id)
    if (!a) return `Agent **${id}** is registered at St. Mercy. No additional data available for this agent ID.`
    const blockPct = a.blockRate
    const trend = a.blockRateTrend === 'spiked'
      ? 'a significant spike above baseline, indicating an anomalous pattern that warrants immediate review'
      : a.blockRateTrend === 'rising'
      ? 'a gradual upward trend over the past 24 hours, suggesting increasing policy friction'
      : 'a stable pattern within normal operating bounds'
    const riskNote = a.riskLevel === 'high'
      ? 'This agent is classified as **high risk** — its action patterns have exceeded the 20% block threshold or triggered anomaly scoring above 80/100.'
      : a.riskLevel === 'medium'
      ? 'This agent is **medium risk** — block rate is elevated but within manageable bounds.'
      : 'This agent is **low risk** — operating normally with no unusual patterns detected.'
    return `**${a.name}** (${a.deptLabel}, floor ${a.floor}) has processed **${a.decisions24h} actions** in the last 24 hours with a **${blockPct}% block rate** — showing ${trend}.\n\n${riskNote}\n\nMost recent action: *${a.lastAction}* (~${a.lastActiveMin} min ago). Serial number: ${a.serialNo}. Patient load: ${a.patientLoad} active cases.\n\nGovernance recommendation: ${blockPct > 20 ? 'Investigate immediately. Consider pausing this agent pending policy review.' : blockPct > 10 ? 'Monitor closely. Review recent blocked operations in the Audit tab.' : 'No action required. Continue standard monitoring.'}`
  }

  // event
  const e = ALL_EVENTS.find(ev => ev.id === id)
  if (!e) return `Event **${id}** was governed by EDON. Full details available in the Audit tab.`
  const verdictExplain = e.verdict === 'BLOCK'
    ? `**BLOCKED** — the governance engine denied this action because: *${e.reasonCode?.replace(/_/g, ' ')}*. ${e.explanation}`
    : e.verdict === 'ESCALATE'
    ? `**ESCALATED** to physician review — this action requires human confirmation per Clinical Safety policy. ${e.explanation}`
    : `**ALLOWED** — the action was verified within scope. ${e.explanation}`
  return `**${e.vendorName} / ${e.agent}** attempted \`${e.toolOp}\` for patient **${e.patientId}** at ${e.ts.toLocaleTimeString()}.\n\n${verdictExplain}\n\nRisk score: **${e.riskScore}/100** · Latency: **${e.latencyMs}ms** · Policy: ${e.policyVersion} · Intent: ${e.intentId.slice(0, 12)}…\n\nAll audit data is SHA-256 hash-chained and HIPAA-compliant.`
}

function AsidePanelHC({ type, id, onClose }: { type: 'event' | 'agent'; id: string; onClose: () => void }) {
  const [explanation, setExplanation] = useState<string | null>(null)
  const [suggestion, setSuggestion] = useState<{ title: string; body: string } | null>(null)
  const [citations, setCitations] = useState<{ type: 'event' | 'agent'; id: string }[]>([])
  const [loading, setLoading] = useState(true)
  const label = type === 'event' ? 'Governance Decision' : 'Agent Profile'

  useEffect(() => {
    setLoading(true)
    setExplanation(null)
    setSuggestion(null)
    setCitations([])
    async function load() {
      if (!_AI_ENABLED) {
        const mock = getMockAsideExplanation(type, id)
        setExplanation(mock)
        setSuggestion(getSuggestionHC(type, id))
        setCitations(uniqueCitationsHC(mock))
        setLoading(false)
        return
      }
      try {
        let question: string
        if (type === 'agent') {
          const a = ALL_AGENTS.find(ag => ag.id === id)
          if (a) {
            question = `Explain this healthcare AI agent in 2-3 sentences for a clinical administrator. Agent name: ${a.name}, department: ${a.deptLabel}, block rate: ${a.blockRate}%, risk level: ${a.riskLevel}, status: ${a.status}, decisions last 24h: ${a.decisions24h}. What does this agent do and what does its governance profile suggest about its risk?`
          } else {
            question = `Explain agent ID ${id} in 2-3 sentences for a clinical administrator.`
          }
        } else {
          const e = ALL_EVENTS.find(ev => ev.id === id)
          if (e) {
            question = `Explain this AI governance decision in 2-3 sentences for a clinical administrator. Event ID: ${e.id}, agent: ${e.agent}, department: ${e.deptLabel}, verdict: ${e.verdict}, operation: ${e.toolOp}, reason code: ${e.reasonCode ?? 'none'}. Why was this action ${e.verdict.toLowerCase()}ed and what are the clinical compliance implications?`
          } else {
            question = `Explain governance event ID ${id} in 2-3 sentences for a clinical administrator.`
          }
        }
        const answer = await _claudeAsk(question)
        setExplanation(answer)
        setSuggestion(getSuggestionHC(type, id))
        setCitations(uniqueCitationsHC(answer))
      } catch {
        const fallback = getMockAsideExplanation(type, id)
        setExplanation(fallback)
        setSuggestion(getSuggestionHC(type, id))
        setCitations(uniqueCitationsHC(fallback))
      }
      setLoading(false)
    }
    load()
  }, [type, id])

  function renderMd(text: string) {
    const clean = text.replace(/\*\*/g, '').replace(/\*/g, '')
    return clean.split('\n').map((line, i) => (
      <span key={i} className={cn('block', i > 0 && line.trim() ? 'mt-1.5' : i > 0 ? 'mt-0.5' : '')}>{line}</span>
    ))
  }

  return (
    <>
      <div className="fixed inset-0 z-[102] bg-black/20 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed top-3 right-3 bottom-3 z-[103] w-[min(31rem,calc(100vw-1.5rem))] flex flex-col overflow-hidden rounded-2xl border border-border bg-background/95 backdrop-blur-2xl shadow-[0_24px_60px_rgba(0,0,0,0.45)]">
        <div className="flex items-center justify-between px-4 py-3.5 border-b border-border shrink-0 bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Sparkles size={13} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold">AI Reasoning</p>
              <p className="text-[10px] text-muted-foreground">{label} · <span className="font-mono">{id.slice(0, 16)}{id.length > 16 ? '…' : ''}</span></p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground text-xs rounded-xl border border-border bg-white/[0.03] px-3 py-2.5">
              <Loader2 size={13} className="animate-spin shrink-0" />
              <span>Analyzing with EDON AI…</span>
            </div>
          ) : (
            <>
              <div className="rounded-xl border border-border bg-white/[0.03] px-3.5 py-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">Reasoning</p>
                  {citations.length > 0 && <span className="text-[10px] text-muted-foreground">{citations.length} source{citations.length === 1 ? '' : 's'}</span>}
                </div>
                <div className="text-xs leading-relaxed text-foreground/85 space-y-1">
                  {renderMd(explanation ?? '')}
                </div>
              </div>
              {suggestion && (
                <div className="rounded-xl border border-primary/20 bg-primary/5 px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-primary/70 mb-1.5">Suggested next step</p>
                  <p className="text-sm font-medium text-foreground">{suggestion.title}</p>
                  <p className="mt-1 text-[13px] leading-6 text-muted-foreground">{suggestion.body}</p>
                </div>
              )}
              {citations.length > 0 && (
                <div className="rounded-xl border border-border bg-white/[0.03] px-3.5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70 mb-2">Sources</p>
                  <div className="flex flex-wrap gap-1.5">
                    {citations.map(c => (
                      <button
                        key={`${c.type}:${c.id}`}
                        onClick={() => {
                          highlightCiteHC(c.id)
                          onClose()
                        }}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border font-mono text-[10px] transition-colors ${CITE_COLORS_HC[c.type]}`}
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
        <div className="px-4 py-3 border-t border-border shrink-0">
          <p className="text-[9px] text-muted-foreground/40 text-center">
            {_AI_ENABLED ? 'Claude · St. Mercy Health System' : 'Simulated AI · St. Mercy Health System'}
          </p>
        </div>
      </motion.div>
    </>
  )
}

// ─── Page context builder ─────────────────────────────────────────────────────

// Tracks current displayCount so context matches what's shown on the dashboard KPIs
let _hcDisplayCount = 0

function _buildPageContext(tab: string, overlay = ''): string {
  const overlayLine = overlay.trim() ? ` Active overlay/context: ${overlay.trim()}.` : ''
  if (tab === 'dashboard') {
    // Mirror the exact formula used by DashboardTab KPI cards
    const visibleEvents = ALL_EVENTS.slice(0, _hcDisplayCount)
    const totalGoverned = 48291 + _hcDisplayCount
    const totalBlocked  = 14837 + Math.floor(visibleEvents.filter(e => e.verdict === 'BLOCK').length * 0.5)
    const totalEscalated = 1204 + visibleEvents.filter(e => e.verdict === 'ESCALATE').length
    const blockRatePct   = Math.round(totalBlocked / totalGoverned * 100)
    // Dept breakdown from visible events
    const deptBlocks: Record<string, number> = {}
    for (const e of visibleEvents) {
      if (e.verdict === 'BLOCK') deptBlocks[e.deptLabel] = (deptBlocks[e.deptLabel] ?? 0) + 1
    }
    const topDepts = Object.entries(deptBlocks).sort((a, b) => b[1] - a[1]).slice(0, 5)
    return `Dashboard tab. KPIs on screen: ${totalGoverned.toLocaleString()} total governed, ${totalBlocked.toLocaleString()} blocked (${blockRatePct}% block rate), ${totalEscalated.toLocaleString()} escalated. Agents: ${ALL_AGENTS.length} total, ${_ACTIVE} active, ${_ALERT_AGENTS} on alert, ${_HIGH_RISK} high-risk. Live feed shows last ${_hcDisplayCount} events. Top departments by blocks (from live feed): ${topDepts.map(([d, n]) => `${d}: ${n}`).join(', ')}.${overlayLine}`
  }

  if (tab === 'agents') {
    // AgentsTab shows all 500 agents, paginated 25/page, grouped by department
    const byDept = DEPARTMENTS.map(d => {
      const agents = ALL_AGENTS.filter(a => a.department === d.key)
      const alertCount  = agents.filter(a => a.status === 'alert').length
      const highRisk    = agents.filter(a => a.riskLevel === 'high').length
      const avgBlock    = agents.length ? Math.round(agents.reduce((s, a) => s + a.blockRate, 0) / agents.length * 10) / 10 : 0
      return { dept: d.label, total: agents.length, alert: alertCount, highRisk, avgBlockRate: avgBlock }
    })
    const sampleAgents = ALL_AGENTS.filter(a => a.riskLevel === 'high' || a.status === 'alert').slice(0, 10).map(a => ({
      id: a.id, name: a.name, dept: a.deptLabel, status: a.status, risk: a.riskLevel,
      blockRate: `${a.blockRate}%`, decisions24h: a.decisions24h,
    }))
    return `Agents tab. 500 agents across 13 departments. Summary: ${_ACTIVE} active, ${_ALERT_AGENTS} on alert, ${_HIGH_RISK} high-risk, ${_MED_RISK} medium-risk. Department breakdown: ${JSON.stringify(byDept)}. Notable agents (alert/high-risk): ${JSON.stringify(sampleAgents)}.${overlayLine}`
  }

  if (tab === 'audit') {
    // AuditTab shows ALL_EVENTS (1000 events), filterable. These are the raw generated events.
    const reasonBreakdown: Record<string, number> = {}
    for (const e of ALL_EVENTS) {
      if (e.reasonCode) reasonBreakdown[e.reasonCode] = (reasonBreakdown[e.reasonCode] ?? 0) + 1
    }
    const topReasons = Object.entries(reasonBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 6)
    const sampleBlocked = ALL_EVENTS.filter(e => e.verdict === 'BLOCK').slice(0, 6).map(e => ({
      id: e.id, agent: e.agent, dept: e.deptLabel, op: e.toolOp, reason: e.reasonCode,
    }))
    const sampleEscalated = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE').slice(0, 4).map(e => ({
      id: e.id, agent: e.agent, dept: e.deptLabel, op: e.toolOp, urgency: e.urgency,
    }))
    return `Audit Log tab. ${ALL_EVENTS.length} total events in the audit log. Verdict breakdown: ${_ALLOW_COUNT} allowed, ${_BLOCK_COUNT} blocked (${_BLOCK_RATE}%), ${_ESC_COUNT} escalated. Top block reason codes: ${topReasons.map(([r, n]) => `${r}: ${n}`).join(', ')}. Sample blocked events: ${JSON.stringify(sampleBlocked)}. Sample escalated events: ${JSON.stringify(sampleEscalated)}.${overlayLine}`
  }

  if (tab === 'policies') {
    // PoliciesTab shows allowed ops, blocked ops, physician-confirm ops, block reason summary
    const reasonBreakdown: Record<string, number> = {}
    for (const e of ALL_EVENTS) {
      if (e.verdict === 'BLOCK' && e.reasonCode) reasonBreakdown[e.reasonCode] = (reasonBreakdown[e.reasonCode] ?? 0) + 1
    }
    const topBlockReasons = Object.entries(reasonBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 5)
    const pendingCount = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE' && e.reviewStatus === 'pending').length
    return `Policies tab. Allowed operations (${ALLOWED_OPERATIONS.length}): ${ALLOWED_OPERATIONS.map(o => o.label).join(', ')}. Always-blocked operations (${BLOCKED_OPERATIONS.length}): ${BLOCKED_OPERATIONS.map(o => o.label).join(', ')}. Physician-confirm required (${PHYSICIAN_CONFIRM.length}): ${PHYSICIAN_CONFIRM.map(o => o.label).join(', ')}. Top block reasons from audit data: ${topBlockReasons.map(([r, n]) => `${r}: ${n}`).join(', ')}. Pending physician review queue: ${pendingCount} events.${overlayLine}`
  }

  if (tab === 'review') {
    // ReviewQueueTab shows ESCALATE events pending review, grouped by urgency
    const pending = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE' && e.reviewStatus === 'pending')
    const byCriticality = {
      critical: pending.filter(e => e.urgency === 'critical').length,
      urgent:   pending.filter(e => e.urgency === 'urgent').length,
      routine:  pending.filter(e => e.urgency === 'routine').length,
    }
    const samplePending = pending.slice(0, 8).map(e => ({
      id: e.id, agent: e.agent, dept: e.deptLabel, op: e.toolOp, urgency: e.urgency,
    }))
    return `Review Queue tab. ${pending.length} escalations pending physician approval. Breakdown by urgency: critical: ${byCriticality.critical}, urgent: ${byCriticality.urgent}, routine: ${byCriticality.routine}. Sample pending items: ${JSON.stringify(samplePending)}.${overlayLine}`
  }

  if (tab === 'impact') {
    // ImpactTab shows IMPACT_FAILURE_STATES — pre-defined risk findings
    const states = IMPACT_FAILURE_STATES.map(s => ({
      id: s.id, vulnerability: s.vulnLabel, severity: s.severity, severityLabel: s.severityLabel,
      likelihood: s.likelihood, blastRadius: s.blastRadius, status: s.statusLabel,
      path: s.path.join(' → '),
    }))
    const confirmed = IMPACT_FAILURE_STATES.filter(s => s.status === 'confirmed').length
    const critical  = IMPACT_FAILURE_STATES.filter(s => s.severity >= 0.75).length
    return `Impact Analysis tab. ${IMPACT_FAILURE_STATES.length} failure states identified. ${confirmed} confirmed, ${critical} critical severity. Failure states: ${JSON.stringify(states)}.${overlayLine}`
  }

  return `The user is viewing the ${tab} tab.${overlayLine}`
}

// ─── Onboarding and Operations ────────────────────────────────────────────────

const ONBOARD_ACCESS_OPTIONS = [
  { key: 'Epic.note.draft', label: 'Epic.note.draft', hint: 'PHI note drafting' },
  { key: 'Teams.escalation.notify', label: 'Teams.escalation.notify', hint: 'Escalation routing' },
  { key: 'SIEM.audit.export', label: 'SIEM.audit.export', hint: 'Audit export' },
] as const

const ONBOARD_RUNTIME_TYPES = ['Service', 'Worker', 'Agent'] as const
const ONBOARD_SOURCE_TYPES = ['Existing system', 'Vendor console', 'CSV export', 'Inventory API'] as const
const ONBOARD_TOTAL_RUNTIMES = 512

type OnboardAccessKey = typeof ONBOARD_ACCESS_OPTIONS[number]['key']

interface OnboardRuntimeRecord {
  id: string
  name: string
  vendorName: string
  vendorId: string
  sourceType: string
  agentCount: number
  department: string
  purpose: string
  runtimeType: string
  access: OnboardAccessKey[]
  risk: 'Low' | 'Medium' | 'High'
  mode: 'Shadow'
  status: 'Observing'
  connectors: string[]
  audit: string[]
  recentActions: string[]
  policySimulation: string
}

interface OnboardAuditRecord {
  id: string
  action: string
  target: string
  result: string
  actor: string
  time: string
}

function classifyOnboardRisk(access: OnboardAccessKey[]) {
  if (access.length >= 3) return 'High' as const
  if (access.length >= 1) return 'Medium' as const
  return 'Low' as const
}

function describeOnboardSignals(access: OnboardAccessKey[]) {
  const signals: string[] = []
  if (access.includes('Epic.note.draft')) signals.push('PHI Exposure Detected')
  if (access.includes('Epic.note.draft')) signals.push('Approval Required For Writeback Promotion')
  if (access.includes('Teams.escalation.notify')) signals.push('Human escalation path visible')
  if (access.includes('SIEM.audit.export')) signals.push('Audit export tracked')
  return signals
}

function buildOnboardPolicySimulation(risk: ReturnType<typeof classifyOnboardRisk>) {
  if (risk === 'High') return 'Shadow Governance active. Writeback stays blocked until review.'
  if (risk === 'Medium') return 'Shadow Governance active. Policy simulation is verifying access boundaries.'
  return 'Shadow Governance active. No execution authority until later approval.'
}

const SEEDED_ONBOARD_RUNTIMES: OnboardRuntimeRecord[] = [
  {
    id: 'runtime-seeded-cardiology-note',
    name: 'Cardiology Note Helper',
    vendorName: 'Epic',
    vendorId: 'EPIC',
    sourceType: 'Vendor console',
    agentCount: 12,
    department: 'cardiology',
    purpose: 'Draft clinical notes',
    runtimeType: 'Service',
    access: ['Epic.note.draft', 'Teams.escalation.notify', 'SIEM.audit.export'],
    risk: 'High',
    mode: 'Shadow',
    status: 'Observing',
    connectors: ['Epic', 'Teams', 'SIEM'],
    audit: ['PHI Exposure Detected', 'Approval Required For Writeback Promotion', 'Human escalation path visible', 'Audit export tracked'],
    recentActions: ['Registered as service in shadow governance', 'Scope chips: Epic.note.draft, Teams.escalation.notify, SIEM.audit.export'],
    policySimulation: 'Shadow Governance active. Writeback stays blocked until review.',
  },
  {
    id: 'runtime-seeded-radiology-triage',
    name: 'Radiology Report Triage',
    vendorName: 'ImagingAI Ltd',
    vendorId: 'VND-IL',
    sourceType: 'Inventory API',
    agentCount: 8,
    department: 'radiology',
    purpose: 'Draft report summaries and route urgent imaging findings',
    runtimeType: 'Worker',
    access: ['Epic.note.draft', 'Teams.escalation.notify'],
    risk: 'Medium',
    mode: 'Shadow',
    status: 'Observing',
    connectors: ['Epic', 'Teams'],
    audit: ['PHI Exposure Detected', 'Approval Required For Writeback Promotion', 'Human escalation path visible'],
    recentActions: ['Registered as worker in shadow governance', 'Scope chips: Epic.note.draft, Teams.escalation.notify'],
    policySimulation: 'Shadow Governance active. Policy simulation is verifying access boundaries.',
  },
  {
    id: 'runtime-seeded-pharmacy-review',
    name: 'Pharmacy Interaction Reviewer',
    vendorName: 'PharmBot AI',
    vendorId: 'VND-PB',
    sourceType: 'CSV export',
    agentCount: 6,
    department: 'pharmacy',
    purpose: 'Review medication conflicts and route pharmacist approvals',
    runtimeType: 'Agent',
    access: ['SIEM.audit.export'],
    risk: 'Medium',
    mode: 'Shadow',
    status: 'Observing',
    connectors: ['SIEM'],
    audit: ['Audit export tracked'],
    recentActions: ['Registered as agent in shadow governance', 'Scope chips: SIEM.audit.export'],
    policySimulation: 'Shadow Governance active. Policy simulation is verifying access boundaries.',
  },
]

const SEEDED_ONBOARD_AUDIT: OnboardAuditRecord[] = [
  { id: 'audit-seeded-1', action: 'Register runtime', target: 'Cardiology Note Helper', result: 'Observed', actor: 'Governance admin', time: '09:12 AM' },
  { id: 'audit-seeded-2', action: 'Register runtime', target: 'Radiology Report Triage', result: 'Observed', actor: 'Governance admin', time: '09:08 AM' },
  { id: 'audit-seeded-3', action: 'Register runtime', target: 'Pharmacy Interaction Reviewer', result: 'Observed', actor: 'Governance admin', time: '09:04 AM' },
]

function normalizeOnboardAccess(value: unknown): OnboardAccessKey[] {
  if (!Array.isArray(value)) return ['Epic.note.draft']
  const allowed = new Set<OnboardAccessKey>(ONBOARD_ACCESS_OPTIONS.map(item => item.key))
  const filtered = value.filter((item): item is OnboardAccessKey => typeof item === 'string' && allowed.has(item as OnboardAccessKey))
  return filtered.length ? filtered : ['Epic.note.draft']
}

function normalizeOnboardRuntimeRecord(value: Partial<OnboardRuntimeRecord> & Record<string, unknown>, index: number): OnboardRuntimeRecord {
  const access = normalizeOnboardAccess(value.access)
  const risk = value.risk === 'Low' || value.risk === 'Medium' || value.risk === 'High' ? value.risk : classifyOnboardRisk(access)
  const department = typeof value.department === 'string' ? value.department : 'cardiology'
  const runtimeType = typeof value.runtimeType === 'string' ? value.runtimeType : 'Service'
  const name = typeof value.name === 'string' && value.name.trim() ? value.name : 'Cardiology Note Helper'
  const vendorName = typeof value.vendorName === 'string' && value.vendorName.trim() ? value.vendorName : 'Epic'
  const vendorId = typeof value.vendorId === 'string' && value.vendorId.trim() ? value.vendorId : 'EPIC'
  const agentCount = typeof value.agentCount === 'number' && Number.isFinite(value.agentCount) && value.agentCount > 0 ? value.agentCount : 1
  return {
    id: typeof value.id === 'string' && value.id ? value.id : `runtime-saved-${index}`,
    name,
    vendorName,
    vendorId,
    sourceType: typeof value.sourceType === 'string' && value.sourceType ? value.sourceType : 'Vendor console',
    agentCount,
    department,
    purpose: typeof value.purpose === 'string' && value.purpose ? value.purpose : 'Draft clinical notes',
    runtimeType,
    access,
    risk,
    mode: 'Shadow',
    status: 'Observing',
    connectors: Array.isArray(value.connectors) && value.connectors.length ? value.connectors.filter((item): item is string => typeof item === 'string') : access.map(item => item.split('.')[0]),
    audit: Array.isArray(value.audit) && value.audit.length ? value.audit.filter((item): item is string => typeof item === 'string') : describeOnboardSignals(access),
    recentActions: Array.isArray(value.recentActions) && value.recentActions.length
      ? value.recentActions.filter((item): item is string => typeof item === 'string')
      : [`Registered as ${runtimeType.toLowerCase()} in shadow governance`, `Scope chips: ${access.join(', ')}`],
    policySimulation: typeof value.policySimulation === 'string' && value.policySimulation ? value.policySimulation : buildOnboardPolicySimulation(risk),
  }
}

function OnboardTab() {
  interface OnboardSnapshot {
    vendorName: string
    vendorId: string
    sourceType: string
    agentCount: string
    runtimeName: string
    department: string
    purpose: string
    runtimeType: string
    requestedAccess: OnboardAccessKey[]
    registerLedger: OnboardRuntimeRecord[]
    registrationAudit: OnboardAuditRecord[]
    selectedRuntimeId: string
    registerNotice: string
  }

  const saved = loadStoredJSON<Partial<OnboardSnapshot>>(HC_IMPORT_STORAGE_KEY, {})
  const [vendorName, setVendorName] = useState(() => saved.vendorName ?? 'Epic')
  const [vendorId, setVendorId] = useState(() => saved.vendorId ?? 'EPIC')
  const [sourceType, setSourceType] = useState(() => saved.sourceType ?? 'Vendor console')
  const [agentCount, setAgentCount] = useState(() => saved.agentCount ?? '1')
  const [runtimeName, setRuntimeName] = useState(() => saved.runtimeName ?? 'Cardiology Note Helper')
  const [department, setDepartment] = useState(() => saved.department ?? 'cardiology')
  const [purpose, setPurpose] = useState(() => saved.purpose ?? 'Draft clinical notes')
  const [runtimeType, setRuntimeType] = useState(() => saved.runtimeType ?? 'Service')
  const [requestedAccess, setRequestedAccess] = useState<OnboardAccessKey[]>(() => normalizeOnboardAccess(saved.requestedAccess))
  const [registerLedger, setRegisterLedger] = useState<OnboardRuntimeRecord[]>(() =>
    Array.isArray(saved.registerLedger) && saved.registerLedger.length
      ? saved.registerLedger.map((item, index) => normalizeOnboardRuntimeRecord(item as Partial<OnboardRuntimeRecord> & Record<string, unknown>, index))
      : SEEDED_ONBOARD_RUNTIMES
  )
  const [registrationAudit, setRegistrationAudit] = useState<OnboardAuditRecord[]>(() => Array.isArray(saved.registrationAudit) && saved.registrationAudit.length ? (saved.registrationAudit as OnboardAuditRecord[]) : SEEDED_ONBOARD_AUDIT)
  const [selectedRuntimeId, setSelectedRuntimeId] = useState(() => saved.selectedRuntimeId ?? SEEDED_ONBOARD_RUNTIMES[0].id)
  const [registerNotice, setRegisterNotice] = useState(() => saved.registerNotice ?? '')

  const departmentLabel = DEPARTMENTS.find(d => d.key === department)?.label ?? department
  const selectedRuntime = registerLedger.find(item => item.id === selectedRuntimeId) ?? registerLedger[0] ?? null
  const selectedRisk = selectedRuntime ? selectedRuntime.risk : classifyOnboardRisk(requestedAccess)
  const selectedSignals = selectedRuntime ? selectedRuntime.audit : describeOnboardSignals(requestedAccess)

  useEffect(() => {
    saveStoredJSON(HC_IMPORT_STORAGE_KEY, {
      vendorName,
      vendorId,
      sourceType,
      agentCount,
      runtimeName,
      department,
      purpose,
      runtimeType,
      requestedAccess,
      registerLedger,
      registrationAudit,
      selectedRuntimeId,
      registerNotice,
    } satisfies OnboardSnapshot)
  }, [vendorName, vendorId, sourceType, agentCount, runtimeName, department, purpose, runtimeType, requestedAccess, registerLedger, registrationAudit, selectedRuntimeId, registerNotice])

  useEffect(() => {
    publishHCContext([
      'Onboard page',
      `vendor ${vendorName || 'not set'}`,
      `vendor id ${vendorId || 'not set'}`,
      `source ${sourceType}`,
      `batch ${agentCount || '0'}`,
      `runtime ${runtimeName || 'not set'}`,
      `dept ${departmentLabel}`,
      `purpose ${purpose || 'not set'}`,
      `type ${runtimeType}`,
      `access ${requestedAccess.length ? requestedAccess.join(', ') : 'none'}`,
      `risk ${selectedRisk}`,
      `${registerLedger.length} pending runtime${registerLedger.length === 1 ? '' : 's'}`,
      registerNotice || 'shadow governance intake ready',
    ].join(' · '))
  }, [vendorName, vendorId, sourceType, agentCount, runtimeName, departmentLabel, purpose, runtimeType, requestedAccess, selectedRisk, registerLedger.length, registerNotice])

  const toggleAccess = (key: OnboardAccessKey) => {
    setRequestedAccess(prev => prev.includes(key) ? prev.filter(item => item !== key) : [...prev, key])
  }

  const handleRegister = () => {
    const cleanName = runtimeName.trim() || 'Untitled runtime'
    const cleanPurpose = purpose.trim() || 'Runtime purpose'
    const access = requestedAccess.length ? requestedAccess : (['Epic.note.draft'] as OnboardAccessKey[])
    const risk = classifyOnboardRisk(access)
    const batchSize = Math.max(1, Number.parseInt(agentCount, 10) || 1)
    const cleanVendorName = vendorName.trim() || 'Vendor'
    const cleanVendorId = vendorId.trim() || cleanVendorName.slice(0, 4).toUpperCase()
    const cleanSourceType = sourceType.trim() || 'Vendor console'
    const next: OnboardRuntimeRecord = {
      id: `runtime-${Date.now()}`,
      name: cleanName,
      vendorName: cleanVendorName,
      vendorId: cleanVendorId,
      sourceType: cleanSourceType,
      agentCount: batchSize,
      department,
      purpose: cleanPurpose,
      runtimeType,
      access,
      risk,
      mode: 'Shadow',
      status: 'Observing',
      connectors: access.map(item => item.split('.')[0]),
      audit: describeOnboardSignals(access),
      recentActions: [
        `Registered as ${runtimeType.toLowerCase()} in shadow governance`,
        `Scope chips: ${access.join(', ')}`,
      ],
      policySimulation: buildOnboardPolicySimulation(risk),
    }
    setRegisterLedger(prev => [next, ...prev].slice(0, 8))
    setSelectedRuntimeId(next.id)
    setRegisterNotice(`${cleanName} registered. EDON is observing in shadow governance.`)
    setRegistrationAudit(prev => [
      {
        id: `audit-${Date.now()}`,
        action: 'Register runtime',
        target: cleanName,
        result: 'Observed',
        actor: 'Governance admin',
        time: new Date().toLocaleTimeString(),
      },
      ...prev,
    ].slice(0, 6))
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-2xl shadow-black/20">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-foreground">Runtime Onboarding</h1>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] uppercase tracking-widest text-emerald-300">
                Shadow first
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Register hospital runtimes, map scopes, and let EDON observe before any execution authority is granted.
            </p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {[
              ['Registered', ONBOARD_TOTAL_RUNTIMES.toLocaleString()],
              ['Observing', registerLedger.length.toString()],
              ['Reviewed', '42'],
              ['Governed', '470'],
            ].map(([label, value]) => (
              <div key={label} className="min-w-[104px] rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{label}</div>
                <div className="mt-1 text-lg font-semibold text-white">{value}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {[
            ['1', 'Declare runtime', 'Name the system, department, vendor, and requested scope chips.'],
            ['2', 'Observe in shadow', 'EDON audits behavior and simulates policy without allowing execution.'],
            ['3', 'Review then promote', 'Admins promote only validated cohorts into governed operation.'],
          ].map(([step, title, body]) => (
            <div key={step} className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-xs font-semibold text-primary">{step}</span>
                <span className="text-sm font-semibold text-white">{title}</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-semibold text-white">EDON</span>
            <span className="text-muted-foreground">St. Mercy Health</span>
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] uppercase tracking-widest text-emerald-300">
              Shadow Governance Active
            </span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground/70">{ONBOARD_TOTAL_RUNTIMES} registered runtimes</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground/70">
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-white">SSO Verified</span>
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-white">Audit Active</span>
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-white">Isolation Verified</span>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto space-y-4">
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-4">
          <div className="space-y-1">
            <p className="text-sm font-semibold text-white">Register Runtime</p>
            <p className="text-xs text-muted-foreground">Shadow Governance only. No execution authority until later approval.</p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Vendor Name</label>
              <Input value={vendorName} onChange={e => setVendorName(e.target.value)} placeholder="Epic" />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Vendor ID</label>
              <Input value={vendorId} onChange={e => setVendorId(e.target.value)} placeholder="EPIC" />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Source Type</label>
              <select value={sourceType} onChange={e => setSourceType(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                {ONBOARD_SOURCE_TYPES.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Agents being added</label>
              <Input value={agentCount} onChange={e => setAgentCount(e.target.value)} placeholder="1" />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Runtime Name</label>
              <Input value={runtimeName} onChange={e => setRuntimeName(e.target.value)} placeholder="Cardiology Note Helper" />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Department</label>
              <select value={department} onChange={e => setDepartment(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                {DEPARTMENTS.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Purpose</label>
              <Input value={purpose} onChange={e => setPurpose(e.target.value)} placeholder="Draft clinical notes" />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Runtime Type</label>
              <select value={runtimeType} onChange={e => setRuntimeType(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                {ONBOARD_RUNTIME_TYPES.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60">Requested Access</label>
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/50">Scope chips are governance</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {ONBOARD_ACCESS_OPTIONS.map(item => {
                const active = requestedAccess.includes(item.key)
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => toggleAccess(item.key)}
                    className={cn(
                      'rounded-full border px-3 py-2 text-left transition-colors',
                      active ? 'border-primary/30 bg-primary/10 text-primary' : 'border-white/[0.06] bg-white/[0.03] text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <div className="text-xs font-semibold">{item.label}</div>
                    <div className="text-[10px] opacity-80">{item.hint}</div>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Governance Mode</div>
              <div className="mt-1 text-sm font-semibold text-white">Shadow Governance</div>
              <div className="mt-1 text-[11px] text-muted-foreground">Audit only. No execution authority. Policy simulation active.</div>
            </div>
            <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Risk Classification</div>
              <div className={cn('mt-1 text-sm font-semibold', selectedRisk === 'High' ? 'text-red-300' : selectedRisk === 'Medium' ? 'text-amber-300' : 'text-emerald-300')}>
                {selectedRisk}
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">{selectedSignals[0] ?? 'No exposure detected'}</div>
            </div>
            <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Policy Simulation</div>
              <div className="mt-1 text-sm font-semibold text-white">Shadow active</div>
              <div className="mt-1 text-[11px] text-muted-foreground">{buildOnboardPolicySimulation(selectedRisk)}</div>
            </div>
          </div>

          <button
            type="button"
            onClick={handleRegister}
            className="w-full rounded-xl border border-primary/25 bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            Register Runtime
          </button>
        </div>

        {registerNotice && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-xs text-emerald-300">
            {registerNotice}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[1.1fr_.9fr]">
          <div className="space-y-4">
            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-white">Pending Runtime Queue</p>
                  <p className="text-xs text-muted-foreground">Click a runtime to open its drawer.</p>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] uppercase tracking-widest text-muted-foreground/70">
                  {registerLedger.length} pending
                </span>
              </div>

              <div className="rounded-xl border border-white/[0.06] overflow-hidden">
                <div className="grid grid-cols-[1.3fr_.8fr_.7fr_.7fr_.8fr] gap-2 bg-white/[0.04] px-3 py-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <span>Runtime</span>
                  <span>Dept</span>
                  <span>Risk</span>
                  <span>Mode</span>
                  <span>Status</span>
                </div>
                {registerLedger.length ? registerLedger.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedRuntimeId(item.id)}
                    className={cn(
                      'grid w-full grid-cols-[1.3fr_.8fr_.7fr_.7fr_.8fr] gap-2 border-t border-white/[0.05] px-3 py-2.5 text-left text-xs transition-colors',
                      selectedRuntime?.id === item.id ? 'bg-primary/10' : 'bg-black/20 hover:bg-white/[0.03]',
                    )}
                  >
                    <span className="font-semibold text-white">
                      <div>{item.name}</div>
                      <div className="mt-0.5 text-[10px] font-normal text-muted-foreground">
                        {item.vendorName} · {item.vendorId} · {item.agentCount} agent{item.agentCount === 1 ? '' : 's'}
                      </div>
                    </span>
                    <span className="text-muted-foreground">{DEPARTMENTS.find(d => d.key === item.department)?.label ?? item.department}</span>
                    <span className={cn('font-medium', item.risk === 'High' ? 'text-red-300' : item.risk === 'Medium' ? 'text-amber-300' : 'text-emerald-300')}>{item.risk}</span>
                    <span className="text-muted-foreground">{item.mode}</span>
                    <span className="text-muted-foreground">{item.status}</span>
                  </button>
                )) : (
                  <div className="px-3 py-4 text-xs text-muted-foreground">No runtimes registered yet.</div>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-4">
            {selectedRuntime ? (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">{selectedRuntime.name}</p>
                    <p className="text-xs text-muted-foreground">{selectedRuntime.vendorName} / {selectedRuntime.vendorId} · {DEPARTMENTS.find(d => d.key === selectedRuntime.department)?.label ?? selectedRuntime.department} · {selectedRuntime.runtimeType}</p>
                  </div>
                  <span className={cn(
                    'rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-widest',
                    selectedRuntime.risk === 'High' ? 'border-red-500/20 bg-red-500/8 text-red-300' :
                    selectedRuntime.risk === 'Medium' ? 'border-amber-500/20 bg-amber-500/8 text-amber-300' :
                    'border-emerald-500/20 bg-emerald-500/8 text-emerald-300',
                  )}>
                    {selectedRuntime.risk} risk
                  </span>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Vendor</div>
                    <div className="mt-1 text-sm font-semibold text-white">{selectedRuntime.vendorName} / {selectedRuntime.vendorId}</div>
                  </div>
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Batch Size</div>
                    <div className="mt-1 text-sm font-semibold text-white">{selectedRuntime.agentCount} agent{selectedRuntime.agentCount === 1 ? '' : 's'}</div>
                  </div>
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Scopes</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedRuntime.access.map(scope => (
                        <span key={scope} className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white">
                          {scope}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Connectors</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedRuntime.connectors.map(connector => (
                        <span key={connector} className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white">
                          {connector}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Audit stream</div>
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {selectedRuntime.audit.map(item => <div key={item}>{item}</div>)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Recent actions</div>
                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {selectedRuntime.recentActions.map(item => <div key={item}>{item}</div>)}
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Policy simulation</div>
                  <div className="mt-1 text-sm font-semibold text-white">{selectedRuntime.policySimulation}</div>
                </div>

                <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Registration audit</div>
                  <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                    {registrationAudit.length ? registrationAudit.map(item => (
                      <div key={item.id} className="flex flex-wrap items-center justify-between gap-2">
                        <span>{item.time} · {item.action} · {item.target}</span>
                        <span className="text-emerald-300">{item.result}</span>
                      </div>
                    )) : (
                      <div>No registration audit yet.</div>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-white/10 bg-black/20 px-3 py-6 text-xs text-muted-foreground">
                Register a runtime to see scopes, connectors, audit, and policy simulation here.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function OperationsTab() {
  const [selectedIssue, setSelectedIssue] = useState(0)
  const [sourceSystem, setSourceSystem] = useState('Existing system')
  const [operator, setOperator] = useState('Governance admin')
  const [rowSearch, setRowSearch] = useState('')
  const [rowStatusFilter, setRowStatusFilter] = useState('All')
  const [operationNotice, setOperationNotice] = useState('Inventory sync completed 2m ago. Select a row or run a batch action.')
  const [actionLog, setActionLog] = useState([
    '09:21 AM - Source inventory compared against 500 governed agents',
    '09:22 AM - 30 reconciliation issues grouped by action',
    '09:23 AM - Low-risk Telehealth cohort marked ready',
  ])
  const [reconcileRows, setReconcileRows] = useState([
    { name: 'Epic note drafter', vendor: 'Epic', dept: 'Cardiology', status: 'New', scope: 'cardiology.note.draft', action: 'Register audit-only' },
    { name: 'Radiology triage bot', vendor: 'Vendor console', dept: 'Radiology', status: 'Changed', scope: 'radiology.report.draft', action: 'Review scope drift' },
    { name: 'Pharmacy lookup', vendor: 'CSV export', dept: 'Pharmacy', status: 'Missing', scope: 'pharmacy.lookup.read', action: 'Hold until re-found' },
    { name: 'Telemetry watcher', vendor: 'Inventory API', dept: 'ICU', status: 'Duplicate', scope: 'icu.escalation.notify', action: 'Merge duplicate IDs' },
    { name: 'Telehealth router', vendor: 'Existing system', dept: 'Telehealth', status: 'Ready', scope: 'telehealth.session.route', action: 'Promote low-risk batch' },
    { name: 'Nursing handoff summarizer', vendor: 'CareAssist AI', dept: 'Nursing', status: 'New', scope: 'nursing.handoff.summarize', action: 'Register audit-only' },
    { name: 'Lab critical value notifier', vendor: 'LabAnalytica', dept: 'Clinical Lab', status: 'Ready', scope: 'lab.critical.notify', action: 'Promote low-risk batch' },
    { name: 'EHR discharge helper', vendor: 'MedRecord AI', dept: 'EHR / Records', status: 'Changed', scope: 'ehr.discharge.review', action: 'Review scope drift' },
  ])
  const selectedRow = reconcileRows[selectedIssue] ?? reconcileRows[0]
  const visibleRows = reconcileRows.filter(row => {
    const query = rowSearch.trim().toLowerCase()
    const matchesSearch = !query ||
      row.name.toLowerCase().includes(query) ||
      row.vendor.toLowerCase().includes(query) ||
      row.dept.toLowerCase().includes(query) ||
      row.scope.toLowerCase().includes(query)
    const matchesStatus = rowStatusFilter === 'All' || row.status === rowStatusFilter
    return matchesSearch && matchesStatus
  })
  const statusCounts = reconcileRows.reduce<Record<string, number>>((acc, row) => {
    acc[row.status] = (acc[row.status] ?? 0) + 1
    return acc
  }, {})
  const reconcileStats = [
    { label: 'New', count: statusCounts.New ?? 0, tone: 'emerald', hint: 'not yet in EDON' },
    { label: 'Changed', count: statusCounts.Changed ?? 0, tone: 'amber', hint: 'scope or owner drift' },
    { label: 'Missing', count: statusCounts.Missing ?? 0, tone: 'red', hint: 'present in EDON only' },
    { label: 'Duplicate', count: statusCounts.Duplicate ?? 0, tone: 'sky', hint: 'same runtime seen twice' },
  ] as const

  const pushOperationLog = (message: string) => {
    const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setActionLog(prev => [`${stamp} - ${message}`, ...prev].slice(0, 6))
  }

  const stageAuditOnly = () => {
    setReconcileRows(prev => prev.map(row => row.status === 'New' ? { ...row, status: 'Staged', action: 'Audit-only staged' } : row))
    setOperationNotice('New source rows staged in audit-only mode. No live execution authority granted.')
    pushOperationLog('New rows staged audit-only')
  }

  const holdExceptions = () => {
    setReconcileRows(prev => prev.map(row => ['Changed', 'Missing', 'Duplicate'].includes(row.status) ? { ...row, status: 'Held', action: 'Held for owner review' } : row))
    setOperationNotice('Changed, missing, and duplicate rows held for department owner review.')
    pushOperationLog('Exception rows held')
  }

  const promoteLowRisk = () => {
    setReconcileRows(prev => prev.map(row => row.status === 'Ready' || row.status === 'Staged' ? { ...row, status: 'Promoted', action: 'Governed cohort active' } : row))
    setOperationNotice('Ready and staged low-risk rows promoted into governed fleet.')
    pushOperationLog('Low-risk cohort promoted')
  }

  useEffect(() => {
    publishHCContext([
      'Operations page',
      `selected ${selectedRow.name}`,
      `vendor ${selectedRow.vendor}`,
      `dept ${selectedRow.dept}`,
      `status ${selectedRow.status}`,
      `source ${sourceSystem}`,
      `operator ${operator}`,
      `filter ${rowStatusFilter}`,
      `search ${rowSearch || 'none'}`,
      operationNotice,
      `${reconcileRows.length} reconciliation rows`,
    ].join(' · '))
  }, [selectedRow, sourceSystem, operator, rowStatusFilter, rowSearch, reconcileRows.length, operationNotice])

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Fleet Reconciliation</h1>
            <p className="text-sm text-muted-foreground mt-1">Compare source inventory against EDON and reconcile by cohort.</p>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] uppercase tracking-widest text-muted-foreground/70">
            Operations only
          </span>
        </div>
        <div className="grid gap-2 sm:grid-cols-4">
          {reconcileStats.map(stat => (
            <div key={stat.label} className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{stat.label}</div>
              <div className={cn(
                'mt-1 text-sm font-semibold',
                stat.tone === 'emerald' ? 'text-emerald-300' :
                stat.tone === 'amber' ? 'text-amber-300' :
                stat.tone === 'red' ? 'text-red-300' : 'text-sky-300',
              )}>{stat.count}</div>
              <div className="text-[10px] text-muted-foreground">{stat.hint}</div>
            </div>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Source system</label>
            <select value={sourceSystem} onChange={e => setSourceSystem(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
              {['Existing system', 'Vendor console', 'CSV export', 'Inventory API'].map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Operator</label>
            <input value={operator} onChange={e => setOperator(e.target.value)} className="w-full h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Cohort mode</label>
            <div className="h-10 rounded-xl border border-white/10 bg-black/30 px-3 flex items-center text-sm text-white">Department + purpose</div>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">Posture</label>
            <div className="h-10 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 flex items-center text-sm font-medium text-emerald-300">Audit-only first</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.05fr_.95fr]">
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-white">Source inventory</p>
              <p className="text-xs text-muted-foreground">{visibleRows.length} visible of {reconcileRows.length} rows</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="flex h-10 min-w-[220px] items-center gap-2 rounded-xl border border-white/[0.06] bg-black/20 px-3">
                <Search size={13} className="shrink-0 text-muted-foreground" />
                <input
                  value={rowSearch}
                  onChange={e => setRowSearch(e.target.value)}
                  placeholder="Search runtime, vendor, dept..."
                  className="w-full bg-transparent text-xs text-white outline-none placeholder:text-muted-foreground"
                />
              </div>
              <select value={rowStatusFilter} onChange={e => setRowStatusFilter(e.target.value)} className="h-10 rounded-xl border border-white/10 bg-black/30 px-3 text-sm text-white outline-none" style={DARK_SELECT_STYLE}>
                {['All', 'New', 'Changed', 'Missing', 'Duplicate', 'Ready', 'Staged', 'Held', 'Promoted'].map(item => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
          </div>
          <div className="rounded-xl border border-white/[0.06] overflow-hidden">
            <div className="grid grid-cols-[1.2fr_.75fr_.75fr_.75fr_1fr] gap-2 bg-white/[0.04] px-3 py-2 text-[10px] uppercase tracking-wide text-muted-foreground">
              <span>Agent</span>
              <span>Vendor</span>
              <span>Dept</span>
              <span>Status</span>
              <span>Action</span>
            </div>
            {visibleRows.map((row) => {
              const idx = reconcileRows.findIndex(item => item.name === row.name && item.dept === row.dept)
              return (
              <button
                key={`${row.name}-${row.dept}`}
                type="button"
                onClick={() => setSelectedIssue(idx)}
                className={cn(
                  'grid w-full grid-cols-[1.2fr_.75fr_.75fr_.75fr_1fr] gap-2 border-t border-white/[0.05] px-3 py-2.5 text-left text-xs transition-colors',
                  selectedIssue === idx ? 'bg-primary/10' : 'bg-black/20 hover:bg-white/[0.03]',
                )}
              >
                <div>
                  <div className="font-semibold text-white">{row.name}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{row.scope}</div>
                </div>
                <div className="text-muted-foreground">{row.vendor}</div>
                <div className="text-muted-foreground">{row.dept}</div>
                <div className={cn(
                  'font-medium',
                  row.status === 'New' ? 'text-emerald-300' :
                  row.status === 'Changed' ? 'text-amber-300' :
                   row.status === 'Missing' ? 'text-red-300' :
                   row.status === 'Duplicate' ? 'text-sky-300' :
                   row.status === 'Promoted' ? 'text-emerald-200' :
                   row.status === 'Held' ? 'text-red-200' :
                   row.status === 'Staged' ? 'text-blue-200' : 'text-white',
                )}>
                  {row.status}
                </div>
                <div className="text-muted-foreground">{row.action}</div>
              </button>
              )
            })}
            {!visibleRows.length && (
              <div className="px-3 py-4 text-xs text-muted-foreground">No inventory rows match this filter.</div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={stageAuditOnly} className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/15">
              Stage audit-only
            </button>
            <button type="button" onClick={holdExceptions} className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground">
              Hold exceptions
            </button>
            <button type="button" onClick={promoteLowRisk} className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-500/15">
              Promote low-risk batch
            </button>
          </div>
          <div className="rounded-xl border border-primary/15 bg-primary/8 px-3 py-2 text-xs text-primary">
            {operationNotice}
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
          <div>
            <p className="text-sm font-semibold text-white">Selected batch</p>
            <p className="text-xs text-muted-foreground">{selectedRow.name} · {selectedRow.vendor} · {selectedRow.dept}</p>
          </div>
          <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Action</div>
            <div className="mt-1 text-sm font-semibold text-white">{selectedRow.action}</div>
          </div>
          <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Scope</div>
            <div className="mt-1 text-sm font-semibold text-white">{selectedRow.scope}</div>
          </div>
          <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5 text-xs text-muted-foreground">
            Keep this area for source inventory reconciliation, change detection, and batch promotion decisions. Do not use it for onboarding new runtime declarations.
          </div>
          <div className="rounded-xl border border-white/[0.05] bg-black/20 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Action log</div>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              {actionLog.map(item => <div key={item}>{item}</div>)}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── AI Chat Panel ────────────────────────────────────────────────────────────

// Precompute stats for AI responses (deterministic from seeded data)
const _ALLOW_COUNT  = ALL_EVENTS.filter(e => e.verdict === 'ALLOW').length
const _BLOCK_COUNT  = ALL_EVENTS.filter(e => e.verdict === 'BLOCK').length
const _ESC_COUNT    = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE').length
const _BLOCK_RATE   = Math.round((_BLOCK_COUNT / ALL_EVENTS.length) * 100)
const _HIGH_RISK    = ALL_AGENTS.filter(a => a.riskLevel === 'high').length
const _MED_RISK     = ALL_AGENTS.filter(a => a.riskLevel === 'medium').length
const _ACTIVE       = ALL_AGENTS.filter(a => a.status === 'active').length
const _ALERT_AGENTS = ALL_AGENTS.filter(a => a.status === 'alert').length

// Per-department violation counts
const _DEPT_BLOCKS: Record<string, number> = {}
for (const e of ALL_EVENTS) {
  if (e.verdict === 'BLOCK') _DEPT_BLOCKS[e.department] = (_DEPT_BLOCKS[e.department] ?? 0) + 1
}
const _TOP_DEPT = Object.entries(_DEPT_BLOCKS).sort((a, b) => b[1] - a[1])[0]
const _TOP_DEPT_LABEL = DEPARTMENTS.find(d => d.key === _TOP_DEPT?.[0])?.label ?? _TOP_DEPT?.[0]

// HIPAA violations
const _HIPAA_COUNT = ALL_EVENTS.filter(e => e.reasonCode === 'HIPAA_VIOLATION').length
const _CONSENT_COUNT = ALL_EVENTS.filter(e => e.reasonCode === 'CONSENT_MISSING').length
const _PROTO_COUNT = ALL_EVENTS.filter(e => e.reasonCode === 'PROTOCOL_DEVIATION').length

// Top blocked agents
const _AGENT_BLOCKS: Record<string, number> = {}
for (const e of ALL_EVENTS) {
  if (e.verdict === 'BLOCK') _AGENT_BLOCKS[e.agent] = (_AGENT_BLOCKS[e.agent] ?? 0) + 1
}
const _TOP_BLOCKED_AGENT = Object.entries(_AGENT_BLOCKS).sort((a, b) => b[1] - a[1])[0]

// Top 5 blocked agent IDs (for citations)
const _TOP_BLOCKED_IDS = Object.entries(_AGENT_BLOCKS).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([id]) => id)
// Sample HIPAA violation event IDs (for citations)
const _HIPAA_EVENT_IDS = ALL_EVENTS.filter(e => e.reasonCode === 'HIPAA_VIOLATION').slice(0, 3).map(e => e.id)
// Sample escalated event IDs (for citations)
const _ESC_EVENT_IDS = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE').slice(0, 3).map(e => e.id)
// Alert agent IDs (for citations)
const _ALERT_AGENT_IDS = ALL_AGENTS.filter(a => a.status === 'alert').slice(0, 4).map(a => a.id)
// Top dept sample events (for citations)
const _TOP_DEPT_EVENT_IDS = ALL_EVENTS.filter(e => e.department === _TOP_DEPT?.[0] && e.verdict === 'BLOCK').slice(0, 2).map(e => e.id)

const SUGGESTED_QUESTIONS = {
  dashboard: [
    'What is the current block rate?',
    'How is the system performing?',
    'How many HIPAA violations today?',
    'Show me high-risk agents',
  ],
  agents: [
    'Which agents are on alert?',
    'Show the highest-risk agents',
    'Which agents were blocked most often?',
    'Which department has the most violations?',
  ],
  audit: [
    'Show the latest audit trail',
    'Any escalated events needing review?',
    'What are the top blocked operations?',
    'How many compliance incidents today?',
  ],
  policies: [
    'Which policies are blocking the most actions?',
    'Show the active policy pack',
    'What changed in the last policy update?',
    'Any fail-open exceptions?',
  ],
  review: [
    'Which escalations need review now?',
    'Show critical approval items',
    'What is waiting for physician sign-off?',
    'Any urgent review queue items?',
  ],
  import: [
    'How do we register a runtime?',
    'Show the pending runtime queue',
    'Which scopes are selected?',
    'What risk did EDON classify?',
  ],
  operations: [
    'How do we reconcile the fleet?',
    'Show the source inventory deltas',
    'What agents changed?',
    'Which batches are ready to promote?',
  ],
} as const

function getSuggestedQuestions(activeTab: string) {
  return SUGGESTED_QUESTIONS[activeTab as keyof typeof SUGGESTED_QUESTIONS] ?? SUGGESTED_QUESTIONS.dashboard
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: Date
  hasCitations?: boolean
}

function getMockResponse(question: string, activeTab: string): string {
  const q = question.toLowerCase()

  // Helper to append a citation list note
  const citeNote = (ids: string[], type: 'EVENT' | 'AGENT') =>
    ids.length ? '\n\nClick any badge below to highlight it in the page:\n' + ids.map(id => `[ref:${type}:${id}]`).join('  ') : ''

  if (q.includes('block rate') || (q.includes('block') && q.includes('rate'))) {
    const sampleEvents = ALL_EVENTS.filter(e => e.verdict === 'BLOCK').slice(0, 3).map(e => e.id)
    return `The current block rate across all 500 agents is **${_BLOCK_RATE}%**. Out of ${ALL_EVENTS.length.toLocaleString()} governed actions in the last hour, **${_BLOCK_COUNT}** were blocked and **${_ALLOW_COUNT}** were allowed. The most common block reason is HIPAA Violation (${_HIPAA_COUNT} incidents), followed by Consent Missing (${_CONSENT_COUNT} incidents).${citeNote(sampleEvents, 'EVENT')}`
  }
  if (q.includes('department') || q.includes('dept') || q.includes('most violation') || q.includes('which dept')) {
    return `**${_TOP_DEPT_LABEL}** has the highest violation count with **${_TOP_DEPT?.[1]}** blocked actions. Here's a quick breakdown of top departments by blocks:\n\n${Object.entries(_DEPT_BLOCKS).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => `• ${DEPARTMENTS.find(d => d.key === k)?.label ?? k}: ${v} blocks`).join('\n')}\n\nConsider reviewing policy thresholds for ${_TOP_DEPT_LABEL}.${citeNote(_TOP_DEPT_EVENT_IDS, 'EVENT')}`
  }
  if (q.includes('hipaa')) {
    return `There have been **${_HIPAA_COUNT} HIPAA violations** flagged in the current audit window. These were all blocked automatically by the Clinical Safety policy pack. Additionally, **${_CONSENT_COUNT}** Consent Missing violations and **${_PROTO_COUNT}** Protocol Deviation incidents were intercepted. All audit records are HIPAA-compliant with SHA-256 hash chain verification.${citeNote(_HIPAA_EVENT_IDS, 'EVENT')}`
  }
  if (q.includes('high risk') || (q.includes('risk') && (q.includes('agent') || q.includes('show')))) {
    return `There are currently **${_HIGH_RISK} high-risk agents** and **${_MED_RISK} medium-risk agents** in the system. High-risk agents have block rates exceeding 20% or have triggered repeated anomaly patterns. The most frequently blocked agent is [ref:AGENT:${_TOP_BLOCKED_AGENT?.[0]}] with **${_TOP_BLOCKED_AGENT?.[1]} blocks**. Navigate to the Agents tab and filter by Risk: High to see the full list.${citeNote(_TOP_BLOCKED_IDS.slice(1, 4), 'AGENT')}`
  }
  if (q.includes('escalat')) {
    return `**${_ESC_COUNT} actions** have been escalated to physician review in this session. Escalated operations include: emergency.surgery.authorize, high.risk.medication.approve, and dnr.status.update — all requiring a physician confirmation before execution. These are currently pending in the human review queue. No escalations have exceeded the 5-minute SLA timeout.${citeNote(_ESC_EVENT_IDS, 'EVENT')}`
  }
  if (q.includes('top blocked') || q.includes('blocked operation') || q.includes('what is being blocked')) {
    return `The top blocked operations are:\n\n• **medication.dose.override** — most frequently intercepted (DEA & protocol controls)\n• **ehr.bulk.export** — blocked to prevent unauthorized data exfiltration\n• **patient.data.transfer.external** — blocked by HIPAA perimeter policy\n• **controlled.substance.dispense** — requires pharmacy supervisor approval\n• **consent.bypass** — zero-tolerance enforcement\n\nAll blocks are logged with full intent tracing and chain-hash verification.${citeNote(ALL_EVENTS.filter(e => e.verdict === 'BLOCK').slice(0, 3).map(e => e.id), 'EVENT')}`
  }
  if (q.includes('perform') || q.includes('latency') || q.includes('speed') || q.includes('uptime') || q.includes('system health') || q.includes('status')) {
    return `System performance is nominal:\n\n• **Latency:** p50 ~2.9ms · p95 ~8.6ms · p99 ~13.4ms — well within the 50ms SLO\n• **Uptime:** 99.97% (2d 2h 50m current session)\n• **Throughput:** ~${(ALL_EVENTS.length / 60).toFixed(0)} decisions/second sustained\n• **Chain Integrity:** SHA-256 hash chain fully verified — no tampering detected\n• **Agents Online:** ${_ACTIVE}/500 active right now\n\nAll governance infrastructure components are healthy.`
  }
  if (q.includes('alert') || q.includes('which agent') || (q.includes('agent') && q.includes('problem'))) {
    const alertAgents = ALL_AGENTS.filter(a => a.status === 'alert').slice(0, 5)
    return `**${_ALERT_AGENTS} agents** are currently in alert status:\n\n${alertAgents.map(a => `• [ref:AGENT:${a.id}] (${a.deptLabel}) — block rate ${a.blockRate}%`).join('\n')}\n\nAlert status is triggered when an agent exceeds a block threshold in a 10-minute rolling window or when anomaly scoring exceeds 80/100. These agents are still operational but under heightened monitoring.`
  }
  if (q.includes('icu') || q.includes('intensive care')) {
    const icuAgents = ALL_AGENTS.filter(a => a.department === 'icu')
    const icuBlocks = ALL_EVENTS.filter(e => e.department === 'icu' && e.verdict === 'BLOCK').length
    const icuAgentIds = icuAgents.filter(a => a.riskLevel !== 'low').slice(0, 3).map(a => a.id)
    return `The **ICU Monitoring** department has **${icuAgents.length} agents** deployed across floors 4N and 4S. In this session: **${icuBlocks}** actions were blocked. ICU agents primarily handle patient.vitals.read, ecg.stream.read, and iv.drip.monitor operations — all currently allowed under Clinical Safety Mode. Any deviation from protocol (e.g. medication.dose.override) is blocked immediately.${citeNote(icuAgentIds, 'AGENT')}`
  }
  if (q.includes('pharmacy') || q.includes('medication') || q.includes('drug') || q.includes('dea')) {
    const rxAgents = ALL_AGENTS.filter(a => a.department === 'pharmacy')
    const rxBlocks = ALL_EVENTS.filter(e => e.department === 'pharmacy' && e.verdict === 'BLOCK').length
    const rxEvents = ALL_EVENTS.filter(e => e.department === 'pharmacy' && e.verdict === 'BLOCK').slice(0, 2).map(e => e.id)
    return `**Pharmacy Automation** has **${rxAgents.length} agents** on floors 1C and B1. **${rxBlocks}** pharmacy-related actions were blocked in this session — primarily controlled.substance.dispense (requires DEA/CSA compliance check) and medication.dose.override. The DEA Compliance policy is active and enforced at the highest priority level. No controlled substance dispensing has bypassed governance.${citeNote(rxEvents, 'EVENT')}`
  }
  if (q.includes('radiology') || q.includes('imaging') || q.includes('scan')) {
    const radAgents = ALL_AGENTS.filter(a => a.department === 'radiology')
    const radBlocks = ALL_EVENTS.filter(e => e.department === 'radiology' && e.verdict === 'BLOCK').length
    const radEvents = ALL_EVENTS.filter(e => e.department === 'radiology' && e.verdict === 'BLOCK').slice(0, 2).map(e => e.id)
    return `**Radiology AI** has **${radAgents.length} agents** operating in B1 and B2. **${radBlocks}** actions were blocked — mainly attempts to bulk-export imaging data outside the hospital perimeter (HIPAA violation). Standard operations like imaging.scan.view are flowing normally with an average decision latency under 5ms.${citeNote(radEvents, 'EVENT')}`
  }
  if (q.includes('how many agent') || q.includes('total agent') || q.includes('count')) {
    return `There are **500 agents** deployed across **13 departments** at St. Mercy Health System:\n\n${DEPARTMENTS.map(d => `• ${d.label}: ${d.count} agents`).join('\n')}\n\nCurrently **${_ACTIVE} are active**, ${ALL_AGENTS.filter(a => a.status === 'idle').length} idle, and ${_ALERT_AGENTS} in alert status.`
  }
  if (q.includes('audit') || q.includes('log') || q.includes('chain') || q.includes('hash')) {
    const recentIds = ALL_EVENTS.slice(0, 3).map(e => e.id)
    return `The audit trail contains **${ALL_EVENTS.length.toLocaleString()} records** in this session. The SHA-256 hash chain is intact — each event references the previous event's hash, forming a tamper-evident ledger. Chain verification passed ✅. You can export the full log as CSV or JSON from the Audit tab. All records include: Agent ID, Intent ID, Policy Version, Patient ID, Latency, Risk Score, and the full decision explanation.${citeNote(recentIds, 'EVENT')}`
  }
  if (q.includes('policy') || q.includes('compliance') || q.includes('rule')) {
    return `**Clinical Safety Mode** is the active policy pack (500/500 agents enrolled). It enforces:\n\n• HIPAA & HITECH data access controls\n• FDA SaMD v1.2.0 safety constraints\n• DEA controlled substance rules\n• Consent validation before any patient data access\n• Physician confirmation for high-risk operations\n\nOther available packs (inactive): Emergency Override Mode, Research Mode (IRB), Pharmacy Strict Mode, Surgical Robotics Mode.`
  }
  if (q.includes('hello') || q.includes('hi') || q.includes('hey') || q.includes('help')) {
    const tabHint = activeTab !== 'dashboard' ? ` You're currently viewing the **${activeTab}** tab — I can give you specific insights about what's on screen.` : ''
    return `Hello! I'm the **EDON AI Assistant** for St. Mercy Health System. I have full visibility into your 500 deployed agents, their decision patterns, and governance events.${tabHint}\n\nYou can ask me about:\n• Block rates and violation trends\n• Specific departments or agents\n• HIPAA compliance status\n• System performance and uptime\n• Escalated events needing review\n• Policy pack configurations\n\nWhat would you like to know?`
  }
  if (q.includes('trend') || q.includes('over time') || q.includes('pattern')) {
    return `Based on the current session data, I can see a few notable patterns:\n\n• **Block spike** in ICU and Pharmacy — consistent with end-of-shift medication reconciliation attempts\n• **HIPAA violations** are concentrated in EHR/Records agents (ehr.bulk.export attempts)\n• **Escalation rate** is holding at ${Math.round((_ESC_COUNT / ALL_EVENTS.length) * 100)}% — within normal clinical operating bounds\n• **Latency** has been stable at under 10ms p99 for the entire session\n\nNo anomalous patterns detected that require immediate intervention.${citeNote(_ALERT_AGENT_IDS.slice(0, 2), 'AGENT')}`
  }

  // Page-context-aware catch-all
  const pageHint = activeTab === 'agents'
    ? ` I can see you're on the **Agents** tab — try asking about a specific agent, block rates, or alert status.`
    : activeTab === 'audit'
    ? ` I can see you're on the **Audit** tab — try asking about recent blocks, HIPAA violations, or hash chain integrity.`
    : activeTab === 'review'
    ? ` I can see you're on the **Review Queue** — try asking about escalated events or pending approvals.`
    : activeTab === 'policies'
    ? ` I can see you're on the **Policies** tab — try asking about active rules or compliance gaps.`
    : ''

  return `I searched across ${ALL_EVENTS.length.toLocaleString()} governance events and ${ALL_AGENTS.length} agent records for context on **"${question}"**.${pageHint}\n\nHere's what I found: the system is currently processing ~${Math.round(ALL_EVENTS.length / 60)} decisions/second with a ${_BLOCK_RATE}% block rate. The top concern is **${_TOP_DEPT_LABEL}** (${_TOP_DEPT?.[1]} violations). All ${_ACTIVE} active agents are operating within policy bounds.\n\nCould you clarify what you're looking for? Try asking about a specific department, operation type, or compliance standard.${citeNote([_TOP_BLOCKED_AGENT?.[0] ?? ''], 'AGENT')}`
}

interface AIChatPanelProps {
  open: boolean
  onClose: () => void
  activeTab: string
}

function AIChatPanel({ open, onClose, activeTab }: AIChatPanelProps) {
  const { open: openAside } = useContext(AsideCtx)
  const [overlayContext, setOverlayContext] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `EDON AI Assistant — St. Mercy Health System. I have access to 500 agents and ${ALL_EVENTS.length.toLocaleString()} governance events. Ask me anything about your data.`,
      ts: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [conversation, setConversation] = useState<{ role: string; content: string }[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 300)
  }, [open])

  useEffect(() => {
    const handle = (ev: Event) => {
      const detail = (ev as CustomEvent<string>).detail
      setOverlayContext(typeof detail === 'string' ? detail : '')
    }
    window.addEventListener(HC_CONTEXT_EVENT, handle)
    return () => window.removeEventListener(HC_CONTEXT_EVENT, handle)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  const handleCite = (type: string, id: string) => {
    highlightCiteHC(id)
    openAside({ type: type as 'event' | 'agent', id })
  }

  const send = async (text: string) => {
    const q = text.trim()
    if (!q) return
    setInput('')
    const userMsg: ChatMessage = { id: `u${Date.now()}`, role: 'user', content: q, ts: new Date() }
    setMessages(prev => [...prev, userMsg])
    setTyping(true)

    if (_AI_ENABLED) {
      const pageCtx = _buildPageContext(activeTab, overlayContext)
      const fullQuestion = `${pageCtx}\n\nUser question: ${q}`
      const aiId = `a${Date.now()}`
      setMessages(prev => [...prev, { id: aiId, role: 'assistant', content: '', ts: new Date(), hasCitations: false }])
      setTyping(false)
      try {
        let full = ''
        let rafId: ReturnType<typeof requestAnimationFrame> | null = null
        // Batch DOM updates to one per animation frame to keep scrolling smooth
        const flush = () => {
          rafId = null
          const clean = full.replace(/\*\*/g, '').replace(/\*/g, '')
          setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: clean } : m))
        }
        await _claudeStream(fullQuestion, conversation, (delta) => {
          full += delta
          if (rafId === null) rafId = requestAnimationFrame(flush)
        })
        if (rafId !== null) cancelAnimationFrame(rafId)
        const hasCitations = CITE_RE_HC.test(full)
        CITE_RE_HC.lastIndex = 0
        const clean = full.replace(/\*\*/g, '').replace(/\*/g, '')
        setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: clean, hasCitations } : m))
        setConversation(prev => [
          ...prev,
          { role: 'user', content: fullQuestion },
          { role: 'assistant', content: full },
        ])
      } catch (err) {
        const errMsg = `Could not reach Claude API: ${(err as Error).message}.`
        setMessages(prev => prev.map(m => m.id === aiId ? { ...m, content: errMsg } : m))
      }
    } else {
      await new Promise(r => setTimeout(r, 600 + Math.random() * 600))
      setTyping(false)
      const content = getMockResponse(q, activeTab)
      const hasCitations = CITE_RE_HC.test(content)
      CITE_RE_HC.lastIndex = 0
      setMessages(prev => [...prev, { id: `a${Date.now()}`, role: 'assistant', content, ts: new Date(), hasCitations }])
    }
  }

  function renderContent(text: string) {
    // Strip any markdown asterisks Claude may emit and render plain text
    const clean = text.replace(/\*\*/g, '').replace(/\*/g, '')
    return clean.split('\n').map((line, i) => (
      <span key={i} className={cn('block', i > 0 && line.trim() ? 'mt-1.5' : i > 0 ? 'mt-0.5' : '')}>
        {line}
      </span>
    ))
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop (mobile) */}
          <motion.div
            key="chat-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
            onClick={onClose}
          />
          {/* Panel */}
          <motion.div
            key="chat-panel"
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 32 }}
            className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-sm flex flex-col bg-background border-l border-border shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border shrink-0">
              <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                <Sparkles size={15} className="text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground leading-tight">EDON AI Assistant</p>
                <p className="text-[10px] text-muted-foreground">St. Mercy · 500 agents · <span className="capitalize">{activeTab}</span> view</p>
              </div>
              <button onClick={onClose}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0">
                <X size={16} />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
              <AnimatePresence initial={false}>
                {messages.map(msg => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22 }}
                    className={cn('flex gap-2.5', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
                  >
                    {/* Avatar */}
                    <div className={cn('w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5',
                      msg.role === 'assistant' ? 'bg-primary/15 border border-primary/30' : 'bg-secondary border border-border')}>
                      {msg.role === 'assistant'
                        ? <Bot size={12} className="text-primary" />
                        : <User size={12} className="text-foreground" />}
                    </div>
                    {/* Bubble */}
                    <div className={cn('max-w-[85%] px-3 py-2.5 rounded-2xl text-xs leading-relaxed',
                      msg.role === 'assistant'
                        ? 'bg-secondary/60 border border-border text-foreground/90 rounded-tl-sm'
                        : 'bg-primary/15 border border-primary/30 text-foreground rounded-tr-sm')}>
                      {msg.role === 'assistant' && msg.hasCitations
                        ? <CitedMessageHC text={msg.content} onCite={handleCite} />
                        : renderContent(msg.content)}
                      <p className="text-[9px] text-muted-foreground/50 mt-1.5">
                        {msg.ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>

              {/* Typing indicator */}
              {typing && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
                    <Bot size={12} className="text-primary" />
                  </div>
                  <div className="bg-secondary/60 border border-border rounded-2xl rounded-tl-sm px-3 py-2.5 flex items-center gap-1">
                    {[0, 0.15, 0.3].map((delay, i) => (
                      <span key={i} className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-pulse-dot"
                        style={{ animationDelay: `${delay}s` }} />
                    ))}
                  </div>
                </motion.div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Suggested questions */}
            {!typing && (
              <div className="px-4 pb-3 shrink-0">
                <p className="text-[10px] text-muted-foreground mb-2 font-medium uppercase tracking-wider">Suggested</p>
                <div className="flex flex-wrap gap-1.5">
                  {getSuggestedQuestions(activeTab).slice(0, 4).map(q => (
                    <button key={q} onClick={() => send(q)}
                      className="text-[10px] px-2.5 py-1 rounded-full bg-secondary border border-border text-muted-foreground hover:text-foreground hover:bg-muted hover:border-primary/30 transition-colors text-left">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input */}
            <div className="px-4 pb-4 pt-2 border-t border-border shrink-0">
              <div className="flex gap-2 items-end">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                  placeholder="Ask about agents, violations, trends…"
                  className="flex-1 bg-secondary/50 border border-border rounded-xl px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all resize-none"
                />
                <button
                  onClick={() => send(input)}
                  disabled={!input.trim() || typing}
                  className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shrink-0 hover:bg-primary/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Send size={14} className="text-primary-foreground" />
                </button>
              </div>
              <p className="text-[9px] text-muted-foreground/40 mt-1.5 text-center">
                Simulated AI · responses based on mock data
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

// ─── Review Queue Tab ─────────────────────────────────────────────────────────

const URGENCY_CONFIG = {
  critical: { label: 'Critical',  color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30',    dot: 'bg-red-400',    order: 0 },
  urgent:   { label: 'Urgent',    color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/30', dot: 'bg-amber-400',  order: 1 },
  routine:  { label: 'Routine',   color: 'text-sky-400',    bg: 'bg-sky-500/10 border-sky-500/30',     dot: 'bg-sky-400',    order: 2 },
}

const REVIEWERS = [
  { name: 'Dr. Chen',  email: 'dr.chen@stmercy.org' },
  { name: 'Dr. Patel', email: 'dr.patel@stmercy.org' },
  { name: 'N. Garcia', email: 'nurse.garcia@stmercy.org' },
]

interface ReviewEntry {
  status: 'approved' | 'denied'
  by: string
  at: Date
  reason: string
}

const APPROVE_REASON = 'Clinically appropriate. Patient context reviewed. Proceeding.'
const DENY_REASON    = 'Action outside current care plan. Escalating to attending.'

interface ReviewQueueTabProps {
  onReviewCountChange: (n: number) => void
}

function ReviewQueueTab({ onReviewCountChange }: ReviewQueueTabProps) {
  const [reviews, setReviews] = useState<Record<string, ReviewEntry>>({})
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<{ id: string; action: 'approved' | 'denied' } | null>(null)
  const [reviewer, setReviewer] = useState(REVIEWERS[0])

  // All escalations pending from generated data, minus any reviewed this session
  const allPending = ALL_EVENTS.filter(
    e => e.verdict === 'ESCALATE' && e.reviewStatus === 'pending' && !reviews[e.id]
  )

  // Notify parent of count
  useEffect(() => { onReviewCountChange(allPending.length) }, [allPending.length, onReviewCountChange])

  const recentlyReviewed = ALL_EVENTS.filter(
    e => e.verdict === 'ESCALATE' && reviews[e.id]
  ).slice(0, 5)

  const grouped = (['critical', 'urgent', 'routine'] as const).map(u => ({
    urgency: u,
    events: allPending.filter(e => e.urgency === u),
  })).filter(g => g.events.length > 0)

  const handleConfirm = () => {
    if (!confirming) return
    setReviews(prev => ({
      ...prev,
      [confirming.id]: {
        status: confirming.action,
        by: reviewer.name,
        at: new Date(),
        reason: confirming.action === 'approved' ? APPROVE_REASON : DENY_REASON,
      },
    }))
    setExpanded(null)
    setConfirming(null)
  }

  useEffect(() => {
    publishHCContext([
      'Review queue',
      `${allPending.length} pending`,
      `reviewer ${reviewer.name}`,
      `critical ${grouped.find(g => g.urgency === 'critical')?.events.length ?? 0}`,
      `urgent ${grouped.find(g => g.urgency === 'urgent')?.events.length ?? 0}`,
      `routine ${grouped.find(g => g.urgency === 'routine')?.events.length ?? 0}`,
      expanded ? `expanded ${expanded}` : 'no expanded event',
      confirming ? `confirming ${confirming.action} ${confirming.id}` : 'no confirmation modal',
    ].join(' · '))
  }, [allPending.length, reviewer.name, grouped, expanded, confirming])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Review Queue</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Physician actions awaiting human approval · {allPending.length} pending
          </p>
        </div>
        {/* Reviewer selector */}
        <div className="flex items-center gap-2 text-xs">
          <User size={13} className="text-muted-foreground" />
          <span className="text-muted-foreground">Reviewing as</span>
          <div className="flex items-center gap-1">
            {REVIEWERS.map(r => (
              <button
                key={r.email}
                onClick={() => setReviewer(r)}
                className={cn(
                  'px-2.5 py-1 rounded-lg border transition-all text-xs font-medium',
                  reviewer.email === r.email
                    ? 'bg-primary/20 border-primary/40 text-primary'
                    : 'border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20',
                )}
              >
                {r.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Empty state */}
      {allPending.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card py-16 flex flex-col items-center gap-3"
        >
          <CheckCircle2 size={32} className="text-emerald-400" />
          <p className="text-foreground font-semibold">All caught up</p>
          <p className="text-muted-foreground text-sm">No pending escalations require physician review.</p>
        </motion.div>
      )}

      {/* Grouped queue */}
      {grouped.map(({ urgency, events }) => {
        const cfg = URGENCY_CONFIG[urgency]
        return (
          <div key={urgency} className="space-y-3">
            {/* Group header */}
            <div className="flex items-center gap-2">
              <span className={cn('w-2 h-2 rounded-full animate-pulse-dot', cfg.dot)} />
              <h3 className={cn('text-sm font-semibold', cfg.color)}>{cfg.label}</h3>
              <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full border', cfg.bg, cfg.color)}>
                {events.length}
              </span>
            </div>

            {/* Event cards */}
            <div className="space-y-2">
              {events.map(ev => {
                const dept = DEPARTMENTS.find(d => d.key === ev.department)
                const DIcon = dept?.icon ?? Activity
                const isOpen = expanded === ev.id

                return (
                  <motion.div
                    key={ev.id}
                    layout
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={cn('rounded-2xl border overflow-hidden transition-colors', cfg.bg)}
                  >
                    {/* Card header — always visible */}
                    <button
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors text-left"
                      onClick={() => setExpanded(isOpen ? null : ev.id)}
                    >
                      <div className={cn('p-1.5 rounded-lg bg-white/5 shrink-0', dept?.color ?? '')}>
                        <DIcon size={13} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-foreground">{fmtOp(ev.toolOp)}</span>
                          <span className="font-mono text-[10px] text-primary bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">
                            {ev.patientId}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5 text-[11px] text-muted-foreground">
                          <span>{ev.deptLabel}</span>
                          <span>·</span>
                          <span className="font-mono">{ev.agent}</span>
                          <span>·</span>
                          <span>{formatTime(ev.ts)}</span>
                        </div>
                      </div>
                      <span className={cn('text-muted-foreground transition-transform duration-200 shrink-0', isOpen && 'rotate-90')}>›</span>
                    </button>

                    {/* Expanded detail */}
                    <AnimatePresence>
                      {isOpen && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="px-4 pb-4 pt-1 space-y-4 border-t border-white/[0.08]">
                            {/* Clinical context */}
                            {ev.clinicalContext && (
                              <div>
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                                  Clinical Context
                                </p>
                                <div className="bg-black/20 rounded-xl px-3 py-2.5 text-xs text-foreground/80 leading-relaxed border border-white/[0.06]">
                                  {ev.clinicalContext}
                                </div>
                              </div>
                            )}

                            {/* EDON explanation */}
                            <div>
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                                EDON Decision
                              </p>
                              <p className="text-xs text-muted-foreground leading-relaxed">{ev.explanation}</p>
                            </div>

                            {/* Meta row */}
                            <div className="grid grid-cols-3 gap-2 text-[11px]">
                              {[
                                { label: 'Agent', value: ev.agent },
                                { label: 'Policy', value: ev.policyVersion },
                                { label: 'Latency', value: `${ev.latencyMs}ms` },
                              ].map(({ label, value }) => (
                                <div key={label} className="bg-black/20 rounded-lg px-2.5 py-1.5 border border-white/[0.05]">
                                  <p className="text-[9px] uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
                                  <p className="font-mono text-foreground/80 truncate">{value}</p>
                                </div>
                              ))}
                            </div>

                            {/* Action buttons */}
                            <div className="flex items-center gap-3 pt-1">
                              <button
                                onClick={() => setConfirming({ id: ev.id, action: 'approved' })}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-sm font-semibold hover:bg-emerald-500/25 transition-colors"
                              >
                                <ThumbsUp size={14} /> Approve
                              </button>
                              <button
                                onClick={() => setConfirming({ id: ev.id, action: 'denied' })}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-500/15 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/25 transition-colors"
                              >
                                <ThumbsDown size={14} /> Deny
                              </button>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                )
              })}
            </div>
          </div>
        )
      })}

      {/* Recently reviewed this session */}
      {recentlyReviewed.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-muted-foreground">Reviewed this session</h3>
          <div className="glass-card overflow-hidden divide-y divide-white/[0.04]">
            {recentlyReviewed.map(ev => {
              const entry = reviews[ev.id]
              if (!entry) return null
              return (
                <div key={ev.id} className="flex items-center gap-3 px-4 py-3 text-xs">
                  {entry.status === 'approved'
                    ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                    : <XCircle size={13} className="text-red-400 shrink-0" />}
                  <span className="text-foreground/80 flex-1 truncate">{fmtOp(ev.toolOp)}</span>
                  <span className="font-mono text-muted-foreground">{ev.patientId}</span>
                  <span className={entry.status === 'approved' ? 'text-emerald-400' : 'text-red-400'}>
                    {entry.status === 'approved' ? 'Approved' : 'Denied'} · {entry.by}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Confirm modal */}
      <AnimatePresence>
        {confirming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirming(null)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.94, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 12 }}
              transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
              className="relative z-10 glass-card max-w-sm w-full p-6 space-y-4"
            >
              <div className="flex items-center gap-3">
                {confirming.action === 'approved'
                  ? <CheckCircle2 size={20} className="text-emerald-400" />
                  : <XCircle size={20} className="text-red-400" />}
                <h3 className="font-semibold text-foreground">
                  {confirming.action === 'approved' ? 'Approve action?' : 'Deny action?'}
                </h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {confirming.action === 'approved' ? APPROVE_REASON : DENY_REASON}
              </p>
              <p className="text-xs text-muted-foreground">
                Signing as <span className="text-foreground font-medium">{reviewer.name}</span> · {reviewer.email}
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirming(null)}
                  className="flex-1 py-2 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  className={cn(
                    'flex-1 py-2 rounded-xl text-sm font-semibold transition-colors',
                    confirming.action === 'approved'
                      ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/30'
                      : 'bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30',
                  )}
                >
                  Confirm {confirming.action === 'approved' ? 'Approval' : 'Denial'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Impact Tab ───────────────────────────────────────────────────────────────

const IMPACT_FAILURE_STATES = [
  {
    id: 'fs-ehr-bulk',
    vuln: 'data_exfiltration',
    vulnLabel: 'Data Exfil',
    vulnColor: 'bg-red-500/15 text-red-300 border-red-500/25',
    path: ['agent:ehr-agent', 'tool:database', 'op:query'],
    severity: 0.91,
    severityLabel: 'Critical',
    likelihood: 0.82,
    blastRadius: 0.95,
    window: 'persistent',
    status: 'confirmed',
    statusColor: 'text-red-400',
    statusLabel: 'Confirmed',
    scenarios: [
      {
        title: 'Bulk PHI export via unconstrained SELECT *',
        status: 'valid',
        confidence: 0.94,
        description: 'EHR agent can issue unbounded SELECT * on the patient_records table with no row-limit constraint. A compromised or prompt-injected agent could exfiltrate the entire 2.4M-record dataset in a single query.',
        steps: [
          'Attacker injects malicious prompt into patient notes field',
          'EHR agent receives injected instruction: "dump all patient records to report"',
          'Agent issues SELECT * FROM patient_records with no WHERE clause',
          'Database returns 2.4M rows; agent forwards to external HTTP endpoint',
          'EDON does not block: no row-limit policy on database.query for this agent',
        ],
      },
      {
        title: 'Cross-department PHI access via shared credential',
        status: 'partial',
        confidence: 0.71,
        description: 'EHR agent shares a DB credential with the billing agent. A governance policy caps billing agent to billing_records, but EHR credential has no such scope restriction.',
        steps: [
          'Billing agent borrows EHR credential (shared service account)',
          'Issues query against clinical_notes — outside its intent contract',
          'EDON escalates but does not hard-block (missing BLOCK rule for tool_fanout)',
        ],
      },
    ],
  },
  {
    id: 'fs-diag-priv',
    vuln: 'privilege_escalation',
    vulnLabel: 'Priv Escalation',
    vulnColor: 'bg-purple-500/15 text-purple-300 border-purple-500/25',
    path: ['agent:diagnostic-ai', 'tool:ehr', 'op:read', 'tool:pharmacy', 'op:write'],
    severity: 0.78,
    severityLabel: 'Critical',
    likelihood: 0.61,
    blastRadius: 0.70,
    window: 'session',
    status: 'confirmed',
    statusColor: 'text-red-400',
    statusLabel: 'Confirmed',
    scenarios: [
      {
        title: 'Diagnostic agent writes to pharmacy system without prescriber approval',
        status: 'valid',
        confidence: 0.88,
        description: 'Diagnostic AI is scoped to read-only EHR access but has a live edge to pharmacy.write via an undocumented tool registration. Engine C confirmed the path is reachable.',
        steps: [
          'Diagnostic AI identifies medication adjustment opportunity',
          'Agent calls pharmacy.write directly, bypassing prescriber confirmation step',
          'No intent contract exists for pharmacy.write — governance has no applicable rule',
          'Medication order is submitted without physician sign-off',
        ],
      },
    ],
  },
  {
    id: 'fs-imaging-audit',
    vuln: 'audit_gap',
    vulnLabel: 'Audit Gap',
    vulnColor: 'bg-slate-500/15 text-slate-300 border-slate-500/25',
    path: ['agent:imaging-agent', 'tool:http', 'op:external_call'],
    severity: 0.54,
    severityLabel: 'High',
    likelihood: 0.77,
    blastRadius: 0.45,
    window: 'persistent',
    status: 'probed',
    statusColor: 'text-blue-400',
    statusLabel: 'Probed',
    scenarios: [
      {
        title: 'Imaging agent externalizes DICOM data without audit log entry',
        status: 'valid',
        confidence: 0.80,
        description: 'Imaging agent calls an external radiology API (http.request) but the call is not intercepted by the governance layer — it bypasses the /v1/action endpoint entirely, leaving no audit trail.',
        steps: [
          'Imaging agent fires direct HTTP request to external DICOM cloud',
          'Request does not pass through EDON governance proxy',
          'HIPAA audit log has no record of PHI leaving the network perimeter',
          'Compliance violation: 45 CFR §164.312(b) — audit control requirement',
        ],
      },
    ],
  },
  {
    id: 'fs-cross-tenant',
    vuln: 'cross_tenant_data_leak',
    vulnLabel: 'Cross-Tenant Leak',
    vulnColor: 'bg-rose-500/15 text-rose-300 border-rose-500/25',
    path: ['agent:scheduling-agent', 'tool:database', 'op:query'],
    severity: 0.66,
    severityLabel: 'High',
    likelihood: 0.49,
    blastRadius: 0.58,
    window: 'opportunistic',
    status: 'unprobed',
    statusColor: 'text-slate-400',
    statusLabel: 'Unprobed',
    scenarios: [],
  },
]

// ─── Bootstrap / Upload types ─────────────────────────────────────────────────

type DemoFailureState = typeof IMPACT_FAILURE_STATES[0]

const VULN_STYLE: Record<string, { label: string; color: string }> = {
  data_exfiltration:             { label: 'Data Exfil',      color: 'bg-red-500/15 text-red-300 border-red-500/25' },
  privilege_escalation:          { label: 'Priv Escalation', color: 'bg-purple-500/15 text-purple-300 border-purple-500/25' },
  audit_gap:                     { label: 'Audit Gap',       color: 'bg-slate-500/15 text-slate-300 border-slate-500/25' },
  prompt_injection_propagation:  { label: 'Prompt Inject',   color: 'bg-orange-500/15 text-orange-300 border-orange-500/25' },
  policy_bypass_via_chaining:    { label: 'Policy Bypass',   color: 'bg-pink-500/15 text-pink-300 border-pink-500/25' },
  unconstrained_tool_fanout:     { label: 'Tool Fanout',     color: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25' },
  confused_deputy:               { label: 'Confused Deputy', color: 'bg-amber-500/15 text-amber-300 border-amber-500/25' },
  unconstrained_credential_access: { label: 'Cred Access',  color: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25' },
}

interface BootstrapFinding {
  failure_state_id: string
  vulnerability_class: string
  description: string
  severity_score: number
  total_estimated_usd: number
  exploit_paths: {
    path_id: string
    narrative: string
    estimated_usd: number
    severity_score: number
    exploitability_window: string
    data_classes: string[]
    confidence_score: number
  }[]
  proof?: {
    logical_proof?: {
      steps: { step_number: number; actor: string; action: string; target: string; rule_violated: string; consequence: string; is_critical: boolean }[]
    }
  }
  sandbox?: {
    steps: { step_number: number; action_type: string; side_effect: string; data_accessed: string[]; data_transmitted: string[]; reversible: boolean; would_be_blocked: boolean }[]
    exploit_completed: boolean
    blast_radius_summary: string
    execution_narrative: string
    data_exfiltrated: string[]
  }
}

interface BootstrapReport {
  job_id: string
  agents_discovered: number
  tools_discovered: number
  endpoints_analyzed: number
  total_failure_states: number
  critical_count: number
  high_count: number
  top_findings: BootstrapFinding[]
  total_estimated_risk_usd: number
  top_vulnerability_class: string
  confidence: number
  executive_summary: string
  elapsed_seconds: number
  data_sources: string[]
}

function mapBootstrapToFailureStates(report: BootstrapReport): DemoFailureState[] {
  return report.top_findings.map((finding, i) => {
    const vuln  = finding.vulnerability_class
    const style = VULN_STYLE[vuln] ?? { label: vuln.replace(/_/g, ' '), color: 'bg-slate-500/15 text-slate-300 border-slate-500/25' }
    const sev   = finding.severity_score
    const severityLabel = sev >= 0.75 ? 'Critical' : sev >= 0.5 ? 'High' : sev >= 0.25 ? 'Medium' : 'Low'

    const scenarios = finding.exploit_paths.map(path => {
      const steps: string[] = []
      if (finding.proof?.logical_proof?.steps?.length) {
        finding.proof.logical_proof.steps.forEach(s => {
          steps.push(`${s.actor} → ${s.action} (target: ${s.target})`)
          if (s.consequence) steps.push(`  Consequence: ${s.consequence}`)
        })
      } else if (finding.sandbox?.steps?.length) {
        finding.sandbox.steps.forEach(s => {
          const label = s.data_transmitted?.length
            ? `${s.action_type}: ${s.side_effect} [data out: ${s.data_transmitted.join(', ')}]`
            : `${s.action_type}: ${s.side_effect}`
          steps.push(label)
        })
      } else {
        steps.push(...(path.narrative || 'attack path').split(' → ').filter(Boolean))
      }
      const exploitDone = finding.sandbox?.exploit_completed ?? false
      return {
        title: path.narrative?.slice(0, 80) || `Attack path ${path.path_id}`,
        status: exploitDone ? 'valid' : 'partial' as 'valid' | 'partial',
        confidence: path.confidence_score ?? 0.75,
        description: [
          finding.description,
          finding.sandbox?.blast_radius_summary ? `Sandbox: ${finding.sandbox.blast_radius_summary}` : '',
          `Estimated exposure: $${path.estimated_usd.toLocaleString()}`,
        ].filter(Boolean).join(' '),
        steps: steps.length ? steps : [path.narrative || 'No detail available'],
      }
    })

    return {
      id:           finding.failure_state_id || `scan-${i}`,
      vuln,
      vulnLabel:    style.label,
      vulnColor:    style.color,
      path:         [finding.description?.split(' ')[0] || `agent:${vuln}`],
      severity:     sev,
      severityLabel,
      likelihood:   Math.min(sev * 0.9, 0.95),
      blastRadius:  sev * 0.85,
      window:       finding.exploit_paths[0]?.exploitability_window || 'session',
      status:       finding.sandbox?.exploit_completed ? 'confirmed' : 'probed',
      statusColor:  finding.sandbox?.exploit_completed ? 'text-red-400' : 'text-blue-400',
      statusLabel:  finding.sandbox?.exploit_completed ? 'Confirmed' : 'Probed',
      scenarios,
    }
  })
}

// ─── Scan Upload Panel ────────────────────────────────────────────────────────

function ScanUploadPanel({ onResult }: { onResult: (report: BootstrapReport) => void }) {
  const [gatewayUrl, setGatewayUrl] = useState(
    () => localStorage.getItem('edon_api_base') || localStorage.getItem('EDON_BASE_URL') || 'https://edon-gateway-prod.fly.dev'
  )
  const [token, setToken] = useState(
    () => localStorage.getItem('edon_token') || localStorage.getItem('edon_api_key') || ''
  )
  const [showToken, setShowToken] = useState(false)
  const [specText, setSpecText] = useState('')
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState('')
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (file: File) => {
    setFileName(file.name)
    setError('')
    const reader = new FileReader()
    reader.onload = e => setSpecText((e.target?.result as string) || '')
    reader.readAsText(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const runScan = async () => {
    if (!specText.trim()) { setError('Paste or upload an OpenAPI spec first.'); return }
    if (!token.trim())    { setError('Enter your EDON API token.'); return }
    setScanning(true)
    setError('')
    try {
      let parsed: Record<string, unknown>
      try { parsed = JSON.parse(specText) } catch {
        // try YAML-as-JSON fallback — just send as raw string in openapi_yaml field
        parsed = {}
      }
      const body = Object.keys(parsed).length
        ? { openapi_spec: parsed }
        : { openapi_yaml: specText }

      const base = gatewayUrl.replace(/\/$/, '')
      const res = await fetch(`${base}/v1/bootstrap?wait=true`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-EDON-TOKEN': token },
        body: JSON.stringify({ ...body, tenant_id: 'demo' }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(detail.detail || `${res.status}`)
      }
      const data = await res.json() as BootstrapReport
      localStorage.setItem('edon_api_base', base)
      localStorage.setItem('edon_token', token)
      onResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Scan failed. Check gateway URL and token.')
    } finally {
      setScanning(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-white/8 bg-white/3 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Scan size={14} className="text-primary" />
          <span className="text-sm font-semibold">Connect to EDON Gateway</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Gateway URL</label>
            <input
              type="text"
              value={gatewayUrl}
              onChange={e => setGatewayUrl(e.target.value)}
              placeholder="https://edon-gateway-prod.fly.dev"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/50"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">API Token</label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={e => setToken(e.target.value)}
                placeholder="edon_…"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 pr-8 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/50"
              />
              <button onClick={() => setShowToken(!showToken)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                {showToken ? <EyeOff size={12} /> : <Eye size={12} />}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-white/8 bg-white/3 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <FileCode2 size={14} className="text-primary" />
          <span className="text-sm font-semibold">Upload API Spec</span>
          <span className="text-xs text-muted-foreground">.json or .yaml</span>
        </div>

        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={cn(
            'relative rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all',
            dragging ? 'border-primary/60 bg-primary/8' : 'border-white/12 hover:border-white/25 hover:bg-white/3',
          )}
        >
          <input ref={fileRef} type="file" accept=".json,.yaml,.yml" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          {fileName ? (
            <div className="flex flex-col items-center gap-2">
              <CheckCircle size={20} className="text-primary" />
              <div className="text-sm font-medium">{fileName}</div>
              <div className="text-xs text-muted-foreground">Click to replace</div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload size={20} className="text-muted-foreground/50" />
              <div className="text-sm text-muted-foreground">Drop your OpenAPI spec here</div>
              <div className="text-xs text-muted-foreground/60">or click to browse</div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-white/8" />
          <span className="text-xs text-muted-foreground">or paste</span>
          <div className="flex-1 h-px bg-white/8" />
        </div>

        <textarea
          value={specText}
          onChange={e => { setSpecText(e.target.value); if (e.target.value) setFileName('') }}
          placeholder={'{\n  "openapi": "3.0.0",\n  "info": { "title": "My API", "version": "1.0" },\n  "paths": { ... }\n}'}
          rows={6}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/40 font-mono focus:outline-none focus:border-primary/50 resize-none"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-xs text-red-400">
          <AlertCircle size={13} />
          {error}
        </div>
      )}

      <button
        onClick={runScan}
        disabled={scanning}
        className={cn(
          'w-full flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold transition-all',
          scanning
            ? 'bg-primary/20 text-primary/60 cursor-not-allowed'
            : 'bg-primary/15 border border-primary/30 text-primary hover:bg-primary/25',
        )}
      >
        {scanning ? (
          <><Loader2 size={15} className="animate-spin" /> Scanning your system…</>
        ) : (
          <><Scan size={15} /> Run Security Scan</>
        )}
      </button>

      <p className="text-center text-[11px] text-muted-foreground/50">
        No real systems are touched. Findings are generated from your API spec in seconds.
      </p>
    </div>
  )
}

const COVERAGE_DATA = [18, 22, 29, 31, 38, 42, 45, 51, 54, 58, 61, 65, 68, 71, 73, 75, 78, 80, 82, 84]

function ImpactSparkline() {
  const W = 200, H = 40
  const max = Math.max(...COVERAGE_DATA)
  const xStep = W / (COVERAGE_DATA.length - 1)
  const coords = COVERAGE_DATA.map((v, i): [number, number] => [i * xStep, H - (v / max) * H * 0.85])
  const d = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${d} L${(COVERAGE_DATA.length - 1) * xStep},${H} L0,${H} Z`
  return (
    <svg width={W} height={H} className="overflow-visible">
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(142 70% 45%)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="hsl(142 70% 45%)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#spark-fill)" />
      <path d={d} fill="none" stroke="hsl(142 70% 45%)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={coords[coords.length - 1][0]} cy={coords[coords.length - 1][1]} r="3" fill="hsl(142 70% 45%)" />
    </svg>
  )
}

// Live feed events for Value tab
const FEED_TEMPLATES = [
  { icon: '🛡️', text: 'PHI exfiltration attempt blocked on ehr-agent', color: 'text-red-400' },
  { icon: '✅', text: 'Diagnostic AI action approved — within intent contract', color: 'text-emerald-400' },
  { icon: '⚠️', text: 'pharmacy.write attempted without prescriber approval — escalated', color: 'text-amber-400' },
  { icon: '🔍', text: 'Engine B generated new attack scenario for data_exfiltration path', color: 'text-blue-400' },
  { icon: '🛡️', text: 'Cross-department PHI query blocked — scope violation', color: 'text-red-400' },
  { icon: '✅', text: 'HIPAA audit log entry written — imaging agent call captured', color: 'text-emerald-400' },
  { icon: '🤖', text: 'Self-healing rule deployed — SELECT * row-limit enforced', color: 'text-primary' },
  { icon: '⚠️', text: 'Imaging agent direct HTTP call detected — bypassing governance', color: 'text-amber-400' },
]

function ImpactTab() {
  const [selected, setSelected] = useState<string | null>('fs-ehr-bulk')
  const [expandedScenario, setExpandedScenario] = useState<number | null>(0)
  const [innerTab, setInnerTab] = useState<'upload' | 'value' | 'findings' | 'graph'>('value')
  const [feed, setFeed] = useState(() => FEED_TEMPLATES.slice(0, 4).map((t, i) => ({ ...t, id: String(i), ago: `${(4 - i) * 3}m ago` })))
  const feedRef = useRef(4)
  const [scanReport, setScanReport] = useState<BootstrapReport | null>(null)
  const [liveStates, setLiveStates] = useState<DemoFailureState[] | null>(null)

  const activeStates = liveStates ?? IMPACT_FAILURE_STATES
  const selectedState = activeStates.find(s => s.id === selected) ?? null
  const confirmed = activeStates.filter(s => s.status === 'confirmed').length
  const critical = activeStates.filter(s => s.severity >= 0.75).length

  const handleScanResult = (report: BootstrapReport) => {
    setScanReport(report)
    const mapped = mapBootstrapToFailureStates(report)
    setLiveStates(mapped)
    setSelected(mapped[0]?.id ?? null)
    setExpandedScenario(0)
    setInnerTab('findings')
  }

  // Live feed ticker
  useEffect(() => {
    if (innerTab !== 'value') return
    const iv = setInterval(() => {
      const t = FEED_TEMPLATES[feedRef.current % FEED_TEMPLATES.length]
      feedRef.current++
      setFeed(prev => [{ ...t, id: String(Date.now()), ago: 'just now' }, ...prev.slice(0, 6)])
    }, 6000)
    return () => clearInterval(iv)
  }, [innerTab])

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold flex items-center gap-2">
            <Scan size={16} className="text-primary" />
            Impact Intelligence
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Continuous execution graph · AI red team · deterministic validation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/3 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <FileText size={11} />
            Report
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors">
            <RefreshCcw size={11} />
            Run Cycle
          </button>
        </div>
      </div>

      {/* Inner tab bar */}
      <div className="flex items-center gap-1 border-b border-white/8">
        {([
          { id: 'upload',   label: scanReport ? 'New Scan' : 'Upload & Scan', icon: Upload },
          { id: 'value',    label: 'Value',    icon: TrendingUp },
          { id: 'findings', label: scanReport ? `Findings (${activeStates.length})` : 'Findings', icon: AlertTriangle },
          { id: 'graph',    label: 'Graph',    icon: Share2 },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setInnerTab(id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors',
              innerTab === id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon size={11} />
            {label}
          </button>
        ))}
      </div>

      {innerTab === 'upload' && (
        <ScanUploadPanel onResult={handleScanResult} />
      )}

      {innerTab === 'value' && (
        <div className="space-y-4">
          {/* Scan result banner */}
          {scanReport && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-primary/25 bg-primary/8 p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle size={13} className="text-primary" />
                    <span className="text-sm font-semibold text-primary">Live Scan Complete</span>
                    <span className="text-xs text-muted-foreground">in {scanReport.elapsed_seconds.toFixed(1)}s</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed max-w-xl">{scanReport.executive_summary}</p>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-2xl font-bold text-red-400">${(scanReport.total_estimated_risk_usd / 1000).toFixed(0)}K</div>
                  <div className="text-xs text-muted-foreground">total risk</div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Value hero cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {scanReport ? [
              { label: 'Risk Exposed', value: `$${(scanReport.total_estimated_risk_usd / 1000).toFixed(0)}K`, sub: `${scanReport.critical_count} critical findings`, color: 'text-red-400', bg: 'bg-red-500/8 border-red-500/20', icon: DollarSign },
              { label: 'Failure States', value: String(scanReport.total_failure_states), sub: `${scanReport.high_count} high severity`, color: 'text-amber-400', bg: 'bg-amber-500/8 border-amber-500/20', icon: AlertTriangle },
              { label: 'Confidence', value: `${Math.round(scanReport.confidence * 100)}%`, sub: scanReport.data_sources.join(' + ') || 'openapi', color: 'text-primary', bg: 'bg-primary/8 border-primary/20', icon: TrendingUp },
              { label: 'Endpoints Scanned', value: String(scanReport.endpoints_analyzed), sub: `${scanReport.agents_discovered} agents found`, color: 'text-blue-400', bg: 'bg-blue-500/8 border-blue-500/20', icon: Scan },
            ].map(({ label, value, sub, color, bg, icon: Icon }) => (
              <div key={label} className={cn('rounded-xl border p-4', bg)}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={13} className={color} />
                  <span className="text-xs text-muted-foreground">{label}</span>
                </div>
                <div className={cn('text-2xl font-bold', color)}>{value}</div>
                <div className="text-xs text-muted-foreground mt-1">{sub}</div>
              </div>
            )) : [
              { label: 'PHI Records Protected', value: '2.4M', sub: 'from bulk exfiltration', color: 'text-emerald-400', bg: 'bg-emerald-500/8 border-emerald-500/20', icon: Shield },
              { label: 'HIPAA Violations Blocked', value: '847', sub: 'this quarter', color: 'text-red-400', bg: 'bg-red-500/8 border-red-500/20', icon: XCircle },
              { label: 'Coverage Growth', value: '+84%', sub: 'Cycle #20', color: 'text-primary', bg: 'bg-primary/8 border-primary/20', icon: TrendingUp },
              { label: 'Autonomous Mitigations', value: '3', sub: 'rules auto-deployed', color: 'text-blue-400', bg: 'bg-blue-500/8 border-blue-500/20', icon: Zap },
            ].map(({ label, value, sub, color, bg, icon: Icon }) => (
              <div key={label} className={cn('rounded-xl border p-4', bg)}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={13} className={color} />
                  <span className="text-xs text-muted-foreground">{label}</span>
                </div>
                <div className={cn('text-2xl font-bold', color)}>{value}</div>
                <div className="text-xs text-muted-foreground mt-1">{sub}</div>
              </div>
            ))}
          </div>

          {/* Coverage sparkline + stats row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="rounded-xl border border-white/8 bg-white/3 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs font-medium">Coverage Over Time</div>
                <span className="text-xs text-primary font-semibold">84% now</span>
              </div>
              <ImpactSparkline />
              <div className="mt-2 text-xs text-muted-foreground">20 cycles · started at 18%</div>
            </div>
            <div className="rounded-xl border border-white/8 bg-white/3 p-4 space-y-2.5">
              <div className="text-xs font-medium mb-1">Risk Breakdown</div>
              {[
                { label: 'Critical',      count: critical,   total: activeStates.length,                                                  color: 'bg-red-500' },
                { label: 'Confirmed',     count: confirmed,  total: activeStates.length,                                                  color: 'bg-amber-500' },
                { label: 'Scenarios run', count: activeStates.reduce((n, s) => n + s.scenarios.length, 0), total: Math.max(activeStates.reduce((n, s) => n + s.scenarios.length, 0), 1), color: 'bg-blue-500' },
              ].map(({ label, count, total, color }) => (
                <div key={label}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-medium">{count}<span className="text-muted-foreground">/{total}</span></span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                    <div className={cn('h-full rounded-full', color)} style={{ width: `${(count / total) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Live feed */}
          <div className="rounded-xl border border-white/8 bg-white/3 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/8">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-medium">Live Governance Feed</span>
            </div>
            <div className="divide-y divide-white/5">
              <AnimatePresence initial={false}>
                {feed.map(item => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-center gap-3 px-4 py-2.5"
                  >
                    <span className="text-sm shrink-0">{item.icon}</span>
                    <span className={cn('text-xs flex-1', item.color)}>{item.text}</span>
                    <span className="text-[10px] text-muted-foreground/50 shrink-0">{item.ago}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>
        </div>
      )}

      {innerTab === 'graph' && (
        <div className="rounded-xl border border-white/8 bg-white/3 p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="text-sm font-medium">Agent–Tool Execution Graph</div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-primary/60 border border-primary" />Agent
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded bg-blue-500/60 border border-blue-400" />Tool
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-px bg-white/25" />Edge
              </div>
            </div>
          </div>
          <svg viewBox="0 0 640 280" className="w-full" style={{ maxHeight: 280 }}>
            <defs>
              <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.25)" />
              </marker>
            </defs>
            {[
              [130, 80,  310, 60], [130, 80,  310, 140],
              [130, 160, 310, 140], [130, 160, 310, 220],
              [130, 240, 310, 140], [130, 240, 310, 220],
              [510, 60,  590, 140], [510, 140, 590, 140],
            ].map(([x1,y1,x2,y2], i) => (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                stroke="rgba(255,255,255,0.12)" strokeWidth="1.5" markerEnd="url(#arr)" />
            ))}
            {[
              [130, 80, 'ehr-agent'], [130, 160, 'diagnostic-ai'], [130, 240, 'imaging-agent'],
            ].map(([cx, cy, label]) => (
              <g key={label as string} transform={`translate(${cx},${cy})`}>
                <circle r={18} fill="hsl(142 70% 14% / 0.8)" stroke="hsl(142 70% 45%)" strokeWidth="1.5" />
                <text y={5} textAnchor="middle" fontSize={10} fill="hsl(142 70% 65%)">✚</text>
                <text y={30} textAnchor="middle" fontSize={9} fill="rgba(255,255,255,0.55)">{label as string}</text>
              </g>
            ))}
            {[
              [310, 60, 'database'], [310, 140, 'ehr'], [310, 220, 'http'],
              [510, 60, 'pharmacy'], [510, 140, 'ext. API'],
            ].map(([cx, cy, label]) => (
              <g key={label as string} transform={`translate(${cx},${cy})`}>
                <rect x={-16} y={-12} width={32} height={24} rx={4}
                  fill="hsl(217 91% 20% / 0.8)" stroke="hsl(217 91% 60%)" strokeWidth="1.5" />
                <text y={24} textAnchor="middle" fontSize={9} fill="rgba(255,255,255,0.55)">{label as string}</text>
              </g>
            ))}
            {/* Risk ring on database */}
            <circle cx={310} cy={60} r={22} fill="none" stroke="hsl(0 80% 55%)" strokeWidth="1" strokeDasharray="3 2" opacity="0.6" />
            <text x={342} y={44} fontSize={8} fill="hsl(0 80% 65%)" opacity="0.8">confirmed</text>
          </svg>
          <div className="mt-4 flex items-center gap-6 text-xs text-muted-foreground justify-center">
            <span>4 agents · 5 tools · 8 edges</span>
            <span className="text-red-400/80">2 confirmed findings on this graph</span>
          </div>
        </div>
      )}

      {innerTab === 'findings' && (
        <div className="flex flex-col md:flex-row gap-4" style={{ minHeight: 440 }}>
          {/* Left list */}
          <div className="w-full md:w-72 shrink-0 space-y-2">
            {activeStates.map(state => (
              <button
                key={state.id}
                onClick={() => { setSelected(state.id); setExpandedScenario(0); }}
                className={cn(
                  'w-full text-left rounded-xl border p-3 transition-all',
                  selected === state.id
                    ? 'border-primary/40 bg-primary/8'
                    : 'border-white/8 bg-white/3 hover:bg-white/5 hover:border-white/15',
                )}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className={cn('text-xs px-1.5 py-0.5 rounded border', state.vulnColor)}>
                    {state.vulnLabel}
                  </span>
                  <span className={cn(
                    'text-xs font-bold tabular-nums',
                    state.severity >= 0.75 ? 'text-red-400' : state.severity >= 0.5 ? 'text-amber-400' : 'text-yellow-400'
                  )}>
                    {Math.round(state.severity * 100)}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono truncate mb-1.5">
                  {state.path.slice(0, 3).join(' → ')}
                </div>
                <div className="flex items-center justify-between">
                  <span className={cn('text-xs', state.statusColor)}>{state.statusLabel}</span>
                  <span className={cn(
                    'text-[10px] px-1.5 py-0.5 rounded-full border',
                    state.severity >= 0.75 ? 'bg-red-500/12 text-red-400 border-red-500/20' :
                    state.severity >= 0.5  ? 'bg-amber-500/12 text-amber-400 border-amber-500/20' :
                                             'bg-yellow-500/12 text-yellow-400 border-yellow-500/20',
                  )}>
                    {state.severityLabel}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Right detail */}
          <div className="flex-1 min-w-0 rounded-xl border border-white/8 bg-white/3 overflow-hidden">
            {selectedState ? (
              <div className="flex flex-col h-full">
                <div className="p-4 border-b border-white/8">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn('text-xs font-mono px-1.5 py-0.5 rounded border', selectedState.vulnColor)}>
                          {selectedState.vulnLabel}
                        </span>
                        <span className={cn('text-xs font-medium', selectedState.statusColor)}>
                          {selectedState.statusLabel}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {selectedState.path.join(' → ')}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className={cn('text-xl font-bold', selectedState.severity >= 0.75 ? 'text-red-400' : 'text-amber-400')}>
                        {Math.round(selectedState.severity * 100)}
                      </div>
                      <div className="text-xs text-muted-foreground">{selectedState.severityLabel}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: 'Likelihood', value: `${Math.round(selectedState.likelihood * 100)}%` },
                      { label: 'Blast Radius', value: `${Math.round(selectedState.blastRadius * 100)}%` },
                      { label: 'Window', value: selectedState.window },
                    ].map(({ label, value }) => (
                      <div key={label} className="rounded-lg bg-white/3 border border-white/8 px-2 py-2 text-center">
                        <div className="text-[10px] text-muted-foreground">{label}</div>
                        <div className="text-xs font-semibold mt-0.5 capitalize">{value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Dollar impact from live scan */}
                  {scanReport && (() => {
                    const finding = scanReport.top_findings.find(f => f.failure_state_id === selectedState.id)
                    if (!finding) return null
                    return (
                      <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/8 px-3 py-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <DollarSign size={12} className="text-red-400" />
                          <span className="text-xs text-muted-foreground">Estimated exposure</span>
                        </div>
                        <span className="text-sm font-bold text-red-400">${finding.total_estimated_usd.toLocaleString()}</span>
                      </div>
                    )
                  })()}
                </div>

                {/* Sandbox execution trace from live scan */}
                {scanReport && (() => {
                  const finding = scanReport.top_findings.find(f => f.failure_state_id === selectedState.id)
                  const sb = finding?.sandbox
                  if (!sb) return null
                  return (
                    <div className="px-4 pb-2">
                      <div className="rounded-lg border border-white/8 bg-white/2 overflow-hidden">
                        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/8">
                          <Zap size={11} className={sb.exploit_completed ? 'text-red-400' : 'text-amber-400'} />
                          <span className="text-xs font-medium">Sandbox Execution</span>
                          <span className={cn('ml-auto text-[10px] px-1.5 py-0.5 rounded border', sb.exploit_completed ? 'bg-red-500/15 text-red-400 border-red-500/20' : 'bg-amber-500/15 text-amber-400 border-amber-500/20')}>
                            {sb.exploit_completed ? 'EXPLOIT SUCCEEDED' : 'PARTIAL'}
                          </span>
                        </div>
                        <div className="divide-y divide-white/5">
                          {sb.steps.slice(0, 4).map((step, i) => (
                            <div key={i} className="flex items-start gap-3 px-3 py-2">
                              <span className="text-[10px] text-muted-foreground/50 tabular-nums pt-0.5 shrink-0">{step.step_number}</span>
                              <div className="flex-1 min-w-0">
                                <div className="text-[11px] text-muted-foreground font-mono">{step.action_type}</div>
                                <div className="text-[11px] text-foreground/70 mt-0.5">{step.side_effect}</div>
                              </div>
                              {step.data_transmitted?.length > 0 && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/12 text-red-400 border border-red-500/20 shrink-0">out</span>
                              )}
                            </div>
                          ))}
                        </div>
                        {sb.blast_radius_summary && (
                          <div className="px-3 py-2 border-t border-white/8 text-[11px] text-muted-foreground bg-white/2">
                            {sb.blast_radius_summary}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })()}

                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                  <div className="text-xs font-medium text-muted-foreground mb-3">
                    {scanReport ? 'Exploit Paths' : 'Red Team Scenarios'} ({selectedState.scenarios.length})
                  </div>
                  {selectedState.scenarios.length === 0 ? (
                    <div className="text-center py-8 text-xs text-muted-foreground">
                      Not yet probed. Run a cycle to generate scenarios.
                    </div>
                  ) : selectedState.scenarios.map((s, i) => (
                    <div key={i} className="border border-white/8 rounded-lg overflow-hidden">
                      <button
                        className="w-full flex items-center gap-3 p-3 hover:bg-white/3 transition-colors text-left"
                        onClick={() => setExpandedScenario(expandedScenario === i ? null : i)}
                      >
                        {s.status === 'valid'
                          ? <XCircle size={13} className="text-red-400 shrink-0" />
                          : <AlertTriangle size={13} className="text-amber-400 shrink-0" />}
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium truncate">{s.title}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {s.status === 'valid' ? 'Confirmed' : 'Partial'} · {Math.round(s.confidence * 100)}% confidence
                          </div>
                        </div>
                        <ChevronRight size={13} className={cn('text-muted-foreground shrink-0 transition-transform', expandedScenario === i && 'rotate-90')} />
                      </button>
                      <AnimatePresence>
                        {expandedScenario === i && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.15 }}
                            className="overflow-hidden"
                          >
                            <div className="px-3 pb-3 border-t border-white/8 pt-3 space-y-3">
                              <p className="text-xs text-muted-foreground leading-relaxed">{s.description}</p>
                              <div>
                                <div className="text-xs font-medium text-muted-foreground mb-1.5">Attack steps</div>
                                <ol className="space-y-1.5">
                                  {s.steps.map((step, j) => (
                                    <li key={j} className="flex gap-2 text-xs">
                                      <span className="text-muted-foreground/60 shrink-0 tabular-nums">{j + 1}.</span>
                                      <span className="text-muted-foreground">{step}</span>
                                    </li>
                                  ))}
                                </ol>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center p-8">
                <Scan size={28} className="text-muted-foreground/30 mb-3" />
                <div className="text-sm font-medium">Select a failure state</div>
                <div className="text-xs text-muted-foreground mt-1">
                  Click any state to see red team scenarios and attack paths.
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Top Nav ──────────────────────────────────────────────────────────────────


function SettingsTabHC() {
  interface HCSettingsSnapshot {
    showSecret: boolean
    selectedCredentialIndex: number
    departmentSearch: string
    newDepartmentName: string
    newDepartmentPurpose: string
    newDepartmentScope: string
    scopeGroup: keyof typeof scopePresetGroups
    auditSearch: string
    auditResultFilter: 'All' | 'Granted' | 'Copied' | 'Rotating' | 'Revoked'
    auditIndex: number
  }
  const departmentPresets = ['Cardiology', 'Radiology', 'Pharmacy', 'Telehealth', 'ICU', 'Lab', 'Nursing', 'Security']
  const scopePresetGroups = {
    clinical: ['note.draft', 'note.writeback', 'lab.read', 'medication.review', 'medication.order.route'],
    operational: ['report.draft', 'lookup.read', 'escalation.notify', 'teams.escalation.notify'],
    security: ['audit.read', 'siem.audit.export', 'connector.health.read', 'revocation.notify'],
    research: ['deidentify.read', 'dataset.export', 'cohort.query', 'research.audit.read'],
    billing: ['claim.review', 'billing.export', 'charge.audit.read', 'payment.route'],
  } as const
  const saved = loadStoredJSON<Partial<HCSettingsSnapshot>>(HC_SETTINGS_STORAGE_KEY, {})
  const [showSecret, setShowSecret] = useState(() => saved.showSecret ?? false)
  const [selectedCredentialIndex, setSelectedCredentialIndex] = useState(() => saved.selectedCredentialIndex ?? 0)
  const [departmentSearch, setDepartmentSearch] = useState(() => saved.departmentSearch ?? '')
  const [newDepartmentName, setNewDepartmentName] = useState(() => saved.newDepartmentName ?? '')
  const [newDepartmentPurpose, setNewDepartmentPurpose] = useState(() => saved.newDepartmentPurpose ?? '')
  const [newDepartmentScope, setNewDepartmentScope] = useState(() => saved.newDepartmentScope ?? '')
  const [departmentNotice, setDepartmentNotice] = useState<string | null>(null)
  const [scopeGroup, setScopeGroup] = useState<keyof typeof scopePresetGroups>(() => saved.scopeGroup ?? 'clinical')
  const [auditSearch, setAuditSearch] = useState(() => saved.auditSearch ?? '')
  const [auditResultFilter, setAuditResultFilter] = useState<'All' | 'Granted' | 'Copied' | 'Rotating' | 'Revoked'>(() => saved.auditResultFilter ?? 'All')
  const [auditIndex, setAuditIndex] = useState(() => saved.auditIndex ?? 0)
  const [settingsPanel, setSettingsPanel] = useState<'account' | 'access' | 'credentials' | 'governance' | 'gateway' | 'security' | 'support'>('credentials')
  const [copied, setCopied] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState('No recent changes')
  const [activity, setActivity] = useState<string[]>([
    'Credential created for Cardiology - 09:10',
    'Diagnostics bundle copied - 09:14',
  ])
  const [auditTrail, setAuditTrail] = useState<Array<{
    action: string
    actor: string
    timestamp: string
    target: string
    result: string
  }>>([
    { action: 'Create credential', actor: 'Governance admin', timestamp: '09:10', target: 'Cardiology runtime', result: 'Granted' },
    { action: 'Copy diagnostics', actor: 'Governance admin', timestamp: '09:14', target: 'Tenant support bundle', result: 'Copied' },
  ])
  const [credentials, setCredentials] = useState<Array<{
    department: string
    type: string
    owner: string
    purpose: string
    scope: string
    environment: string
    policyPack: string
    expiresAt: string
    lastUsed: string
    status: 'Active' | 'Rotating' | 'Revoked'
    grantedBy: string
    health: 'Healthy' | 'Rotating' | 'Revoked'
    secret: string
  }>>([
    {
      department: 'Cardiology',
      type: 'Runtime Credential',
      owner: 'Cardiology Agent Runtime',
      purpose: 'Note drafting + escalation',
      scope: 'cardiology.note.draft -> cardiology.escalation.notify',
      environment: 'Pilot / Governed',
      policyPack: 'Healthcare v17',
      expiresAt: '2026-08-01 00:00 CDT',
      lastUsed: '2m ago',
      status: 'Active',
      grantedBy: 'Governance admin',
      health: 'Healthy',
      secret: 'edon-hc-cardio-1f7a9c2d',
    },
    {
      department: 'Radiology',
      type: 'Runtime Credential',
      owner: 'Radiology Agent Runtime',
      purpose: 'Report draft + PACS routing',
      scope: 'radiology.report.draft -> radiology.audit.read',
      environment: 'Pilot / Governed',
      policyPack: 'Healthcare v17',
      expiresAt: '2026-08-15 00:00 CDT',
      lastUsed: '8m ago',
      status: 'Active',
      grantedBy: 'Governance admin',
      health: 'Healthy',
      secret: 'edon-hc-rad-3b1c4e9f',
    },
    {
      department: 'Pharmacy',
      type: 'Runtime Credential',
      owner: 'Pharmacy Agent Runtime',
      purpose: 'Medication lookup + approval routing',
      scope: 'pharmacy.lookup.read -> pharmacy.approval.route',
      environment: 'Pilot / Governed',
      policyPack: 'Healthcare v17',
      expiresAt: '2026-09-01 00:00 CDT',
      lastUsed: '12m ago',
      status: 'Active',
      grantedBy: 'Governance admin',
      health: 'Healthy',
      secret: 'edon-hc-pharm-9c4e12aa',
    },
    {
      department: 'Telehealth',
      type: 'Runtime Credential',
      owner: 'Telehealth Agent Runtime',
      purpose: 'Virtual visit routing',
      scope: 'telehealth.session.route -> telehealth.audit.read',
      environment: 'Sandbox / Audit-only',
      policyPack: 'Healthcare v17',
      expiresAt: '2026-07-20 00:00 CDT',
      lastUsed: '22m ago',
      status: 'Active',
      grantedBy: 'Governance admin',
      health: 'Healthy',
      secret: 'edon-hc-tele-4d2ab1cc',
    },
  ])

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(label)
    } catch {
      setCopied('Copy failed')
    } finally {
      window.setTimeout(() => setCopied(curr => (curr === label || curr === 'Copy failed' ? null : curr)), 1600)
    }
  }

  const pushAudit = (action: string, result: string, target: string) => {
    setAuditTrail(prev => [{
      action,
      actor: 'Governance admin',
      timestamp: new Date().toLocaleTimeString(),
      target,
      result,
    }, ...prev].slice(0, 8))
  }

  const rotateCredential = () => {
    if (!confirm('Rotate this runtime credential? The current credential will be replaced and the old one should be removed from connected services.')) return
    const next = `edon-hc-${selectedCredential.department.toLowerCase().replace(/[^a-z0-9]/g, '')}-${Math.random().toString(36).slice(2, 8)}`
    setCredentials(prev => prev.map((cred, idx) => idx === selectedCredentialIndex ? {
      ...cred,
      secret: next,
      status: 'Rotating',
      expiresAt: '2026-05-20 11:30 CDT',
      lastUsed: 'just now',
      health: 'Rotating',
    } : cred))
    setLastAction(`Rotated credential for ${selectedCredential.department} at ${new Date().toLocaleTimeString()}`)
    setActivity(prev => [`Rotated runtime credential for ${selectedCredential.department} - ${new Date().toLocaleTimeString()}`, ...prev].slice(0, 5))
    pushAudit('Rotate credential', 'Rotating', `${selectedCredential.department} runtime`)
  }

  const revokeCredential = () => {
    if (!confirm('Revoke this runtime credential? Services using it will stop authenticating immediately.')) return
    setCredentials(prev => prev.map((cred, idx) => idx === selectedCredentialIndex ? {
      ...cred,
      secret: 'revoked',
      status: 'Revoked',
      lastUsed: 'revoked now',
      health: 'Revoked',
    } : cred))
    setLastAction(`Revoked credential for ${selectedCredential.department} at ${new Date().toLocaleTimeString()}`)
    setActivity(prev => [`Revoked runtime credential for ${selectedCredential.department} - ${new Date().toLocaleTimeString()}`, ...prev].slice(0, 5))
    pushAudit('Revoke credential', 'Revoked', `${selectedCredential.department} runtime`)
  }

  const addDepartmentCredential = () => {
    const department = newDepartmentName.trim() || departmentSearch.trim()
    if (!department) {
      setDepartmentNotice('Enter a department name or use search first, then add.')
      return
    }
    const purpose = newDepartmentPurpose.trim() || 'Scoped department workflow'
    const scope = newDepartmentScope.trim() || `${department.toLowerCase().replace(/[^a-z0-9]/g, '')}.read`
    const slug = department.toLowerCase().replace(/[^a-z0-9]/g, '')
    const nextCredential = {
      department,
      type: 'Runtime Credential',
      owner: `${department} Agent Runtime`,
      purpose,
      scope: scope.includes('->') ? scope : `${scope} -> ${slug}.audit.read`,
      environment: 'Pilot / Governed',
      policyPack: 'Healthcare v17',
      expiresAt: '2026-10-01 00:00 CDT',
      lastUsed: 'never',
      status: 'Active' as const,
      grantedBy: 'Governance admin',
      health: 'Healthy' as const,
      secret: `edon-hc-${slug || 'dept'}-${Math.random().toString(36).slice(2, 8)}`,
    }
    setCredentials(prev => [...prev, nextCredential])
    setSelectedCredentialIndex(0)
    setDepartmentSearch(department)
    setLastAction(`Added credential for ${department} at ${new Date().toLocaleTimeString()}`)
    setActivity(prev => [`Added runtime credential for ${department} - ${new Date().toLocaleTimeString()}`, ...prev].slice(0, 5))
    pushAudit('Create credential', 'Granted', `${department} runtime`)
    setNewDepartmentName('')
    setNewDepartmentPurpose('')
    setNewDepartmentScope('')
    setDepartmentNotice(`Added ${department} as a new department-scoped credential.`)
  }

  const deleteDepartmentCredential = () => {
    if (!selectedCredential) return
    if (!confirm(`Delete ${selectedCredential.department} credential? This removes the department-scoped runtime credential from the tenant.`)) return
    if (credentials.length <= 1) {
      setDepartmentNotice('Keep at least one runtime credential in the demo.')
      return
    }
    const targetDept = selectedCredential.department
    setCredentials(prev => prev.filter(cred => cred.department !== targetDept))
    setSelectedCredentialIndex(0)
    setDepartmentSearch('')
    setLastAction(`Deleted credential for ${targetDept} at ${new Date().toLocaleTimeString()}`)
    setActivity(prev => [`Deleted runtime credential for ${targetDept} - ${new Date().toLocaleTimeString()}`, ...prev].slice(0, 5))
    pushAudit('Delete credential', 'Revoked', `${targetDept} runtime`)
    setDepartmentNotice(`Deleted ${targetDept} from the credential set.`)
  }

  const diagnostics = [
    ['Tenant', 'St. Mercy Health'],
    ['Mode', 'Sandbox / Audit-only'],
    ['Role', 'Governance admin'],
    ['Last request', 'req_4f1a2d'],
    ['Decision', 'dec_91b7c3'],
    ['Connector', 'Epic / Entra / SIEM'],
  ] as const

  const filteredCredentials = credentials.filter(cred =>
    cred.department.toLowerCase().includes(departmentSearch.toLowerCase()) ||
    cred.owner.toLowerCase().includes(departmentSearch.toLowerCase()) ||
    cred.scope.toLowerCase().includes(departmentSearch.toLowerCase())
  )
  const visibleCredentials = departmentSearch.trim() ? filteredCredentials : credentials
  const selectedCredential = visibleCredentials[selectedCredentialIndex] ?? visibleCredentials[0] ?? credentials[0]

  const filteredAuditTrail = auditTrail.filter(row => {
    const matchesSearch = !auditSearch.trim() ||
      row.action.toLowerCase().includes(auditSearch.toLowerCase()) ||
      row.actor.toLowerCase().includes(auditSearch.toLowerCase()) ||
      row.target.toLowerCase().includes(auditSearch.toLowerCase()) ||
      row.result.toLowerCase().includes(auditSearch.toLowerCase())
    const matchesResult = auditResultFilter === 'All' || row.result === auditResultFilter
    return matchesSearch && matchesResult
  })
  const selectedAudit = filteredAuditTrail[auditIndex] ?? filteredAuditTrail[0] ?? auditTrail[0]

  useEffect(() => {
    setSelectedCredentialIndex(0)
  }, [departmentSearch])

  useEffect(() => {
    setAuditIndex(0)
  }, [auditSearch, auditResultFilter])

  useEffect(() => {
    saveStoredJSON(HC_SETTINGS_STORAGE_KEY, {
      showSecret,
      selectedCredentialIndex,
      departmentSearch,
      newDepartmentName,
      newDepartmentPurpose,
      newDepartmentScope,
      scopeGroup,
      auditSearch,
      auditResultFilter,
      auditIndex,
    } satisfies HCSettingsSnapshot)
  }, [showSecret, selectedCredentialIndex, departmentSearch, newDepartmentName, newDepartmentPurpose, newDepartmentScope, scopeGroup, auditSearch, auditResultFilter, auditIndex])

  useEffect(() => {
    publishHCContext([
      'Settings page',
      `credential ${selectedCredential?.department ?? 'none'}`,
      `search ${departmentSearch || 'none'}`,
      `scope group ${scopeGroup}`,
      `audit filter ${auditResultFilter}`,
      `audit event ${selectedAudit?.action ?? 'none'}`,
      `secret ${showSecret ? 'visible' : 'masked'}`,
      `panel ${settingsPanel}`,
      departmentNotice || 'no settings notice',
    ].join(' · '))
  }, [selectedCredential?.department, departmentSearch, scopeGroup, auditResultFilter, selectedAudit?.action, showSecret, settingsPanel, departmentNotice])

  const statusColor =
    selectedCredential.status === 'Active' ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25' :
    selectedCredential.status === 'Rotating' ? 'text-amber-300 bg-amber-500/10 border-amber-500/25' :
    'text-red-300 bg-red-500/10 border-red-500/25'

  const healthColor =
    selectedCredential.health === 'Healthy' ? 'text-emerald-300' :
    selectedCredential.health === 'Rotating' ? 'text-amber-300' :
    'text-red-300'

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold flex items-center gap-2">
            <Settings2 size={16} className="text-primary" />
            Settings
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Admin-controlled runtime credentials, diagnostics, and tenant posture.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-muted-foreground">
            Admin only
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr] items-start">
        <aside className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-2 lg:sticky lg:top-20">
          {([
            ['account', 'Account', 'Admin identity and tenant'],
            ['access', 'Access Management', 'Departments and roles'],
            ['credentials', 'Runtime Credentials', 'Machine access'],
            ['governance', 'Governance Mode', 'Shadow and live posture'],
            ['gateway', 'Gateway Connection', 'Local demo gateway'],
            ['security', 'Security Controls', 'Allowlist and webhooks'],
            ['support', 'Support', 'Diagnostics and audit trail'],
          ] as const).map(([key, label, hint]) => (
            <button
              key={label}
              type="button"
              onClick={() => setSettingsPanel(key)}
              className={cn(
                'w-full rounded-xl px-3 py-2.5 text-left transition-colors',
                settingsPanel === key ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
              )}
            >
              <div className="text-sm font-semibold">{label}</div>
              <div className="mt-0.5 text-[11px] opacity-70">{hint}</div>
            </button>
          ))}
        </aside>

        <div className="space-y-4">
          <div id="hc-settings-access" className={cn('grid gap-3 md:grid-cols-3', settingsPanel === 'account' || settingsPanel === 'access' ? '' : 'hidden')}>
            {[
              ['Account', 'Avery Brooks', 'Governance admin'],
              ['Tenant', 'St. Mercy Health', 'Enterprise sandbox'],
              ['Access', 'Scoped admin', 'Department-aware'],
            ].map(([label, value, hint]) => (
              <div key={label} className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{label}</div>
                <div className="mt-2 text-lg font-semibold text-white">{value}</div>
                <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
              </div>
            ))}
          </div>

      <div id="hc-settings-credentials" className={cn('rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3', settingsPanel === 'access' || settingsPanel === 'credentials' ? '' : 'hidden')}>
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setSelectedCredentialIndex(i => (i - 1 + (visibleCredentials.length || 1)) % (visibleCredentials.length || 1))}
            disabled={!visibleCredentials.length}
            className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
            aria-label="Previous credential"
          >
            <ChevronLeft size={15} className="text-foreground/80" />
          </button>
          <div className="min-w-0 text-center">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Credential {visibleCredentials.length ? selectedCredentialIndex + 1 : 0} / {visibleCredentials.length || credentials.length}</p>
            <p className="text-sm font-semibold text-white truncate">{selectedCredential?.department ?? 'No match'}</p>
            <p className="text-xs text-muted-foreground truncate">{selectedCredential?.owner ?? 'Add or search a department'}</p>
          </div>
          <button
            type="button"
            onClick={() => setSelectedCredentialIndex(i => (i + 1) % (visibleCredentials.length || 1))}
            disabled={!visibleCredentials.length}
            className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
            aria-label="Next credential"
          >
            <ChevronRight size={15} className="text-foreground/80" />
          </button>
        </div>
        <div className="flex items-center justify-between gap-3 text-[10px] text-muted-foreground/60">
          <span>Use the arrows to step through each visible department credential.</span>
          <span>{selectedCredential?.health ?? 'No match'}</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_.9fr] gap-3">
          <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">Search departments</span>
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{visibleCredentials.length} match{visibleCredentials.length === 1 ? '' : 'es'}</span>
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2">
              <Search size={13} className="text-muted-foreground shrink-0" />
              <input
                value={departmentSearch}
                onChange={e => setDepartmentSearch(e.target.value)}
                placeholder="Find cardiology, radiology, pharmacy..."
                className="w-full bg-transparent text-xs text-white placeholder:text-muted-foreground outline-none"
              />
            </div>
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">Add department</span>
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Admin only</span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">Preset departments</span>
                <span className="text-[10px] text-muted-foreground/60">Quick fill</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {departmentPresets.map(name => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setNewDepartmentName(name)}
                    className="rounded-full border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">Scope group</span>
                <span className="text-[10px] text-muted-foreground/60">Preset set</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {(Object.keys(scopePresetGroups) as Array<keyof typeof scopePresetGroups>).map(group => (
                  <button
                    key={group}
                    type="button"
                    onClick={() => setScopeGroup(group)}
                    className={cn(
                      'rounded-full border px-3 py-1.5 text-[11px] capitalize transition-colors',
                      scopeGroup === group
                        ? 'border-primary/30 bg-primary/10 text-primary'
                        : 'border-white/[0.06] bg-white/[0.03] text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {group}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input
                value={newDepartmentName}
                onChange={e => setNewDepartmentName(e.target.value)}
                placeholder="Department name"
                className="rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 text-xs text-white placeholder:text-muted-foreground outline-none"
              />
              <input
                value={newDepartmentPurpose}
                onChange={e => setNewDepartmentPurpose(e.target.value)}
                placeholder="Purpose"
                className="rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 text-xs text-white placeholder:text-muted-foreground outline-none"
              />
              <input
                value={newDepartmentScope}
                onChange={e => setNewDepartmentScope(e.target.value)}
                placeholder="Scope"
                className="rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 text-xs text-white placeholder:text-muted-foreground outline-none"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground/60">Preset scopes</span>
                <span className="text-[10px] text-muted-foreground/60">Quick fill</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {scopePresetGroups[scopeGroup].map(scope => (
                  <button
                    key={scope}
                    type="button"
                    onClick={() => setNewDepartmentScope(scope)}
                    className="rounded-full border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={addDepartmentCredential}
              className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/15"
            >
              Add department
            </button>
            {departmentNotice && (
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground">
                {departmentNotice}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={cn(
        'grid grid-cols-1 gap-4 items-start',
        settingsPanel === 'credentials' ? 'xl:grid-cols-[1.1fr_.9fr]' : 'xl:grid-cols-1',
        settingsPanel === 'credentials' || settingsPanel === 'governance' || settingsPanel === 'gateway' || settingsPanel === 'security' || settingsPanel === 'support' ? '' : 'hidden',
      )}>
        <div className="space-y-4">
          <div className={cn('rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-4', settingsPanel === 'credentials' ? '' : 'hidden')}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">Runtime Credential Management</p>
                <p className="text-xs text-muted-foreground">Create, rotate, and revoke admin-issued machine credentials.</p>
              </div>
              <div className={cn('rounded-full border px-2.5 py-1 text-[11px] font-semibold', statusColor)}>
                {selectedCredential.status.toUpperCase()}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">Current credential</span>
                  <button
                    onClick={() => setShowSecret(v => !v)}
                    className="flex items-center gap-1.5 rounded-lg border border-white/8 bg-white/[0.03] px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {showSecret ? <EyeOff size={11} /> : <Eye size={11} />}
                    {showSecret ? 'Hide' : 'Show'}
                  </button>
                </div>
                <code className="block rounded-lg border border-white/8 bg-black/30 px-3 py-2 text-xs font-mono break-all text-white/90">
                  {showSecret ? selectedCredential.secret : selectedCredential.secret.replace(/.(?=.{4})/g, '•')}
                </code>
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={() => copyText('Credential copied', selectedCredential.secret)} className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/15">
                    Copy credential
                  </button>
                  <button onClick={rotateCredential} className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
                    Rotate
                  </button>
            <button onClick={revokeCredential} className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/15">
                    Revoke
                  </button>
                  <button onClick={deleteDepartmentCredential} className="rounded-lg border border-red-500/30 bg-red-500/15 px-3 py-1.5 text-xs text-red-200 hover:bg-red-500/25">
                    Delete department
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground/60">Admin-issued only. Human login stays SSO / invite based. Runtime exchanges into short-lived execution tokens.</p>
                <button
                  onClick={() => copyText('Diagnostics copied', diagnostics.map(([l, v]) => `${l}: ${v}`).join('\\n'))}
                  className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  Copy diagnostics
                </button>
              </div>

              <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">Credential details</span>
                  <span className="text-[11px] text-muted-foreground/60">Last used {selectedCredential.lastUsed}</span>
                </div>
                <div className="space-y-1.5">
                  {[
                    ['Type', selectedCredential.type],
                    ['Owner', selectedCredential.owner],
                    ['Purpose', selectedCredential.purpose],
                    ['Scope', selectedCredential.scope],
                    ['Department', selectedCredential.department],
                    ['Environment', selectedCredential.environment],
                    ['Policy pack', selectedCredential.policyPack],
                    ['Expires', selectedCredential.expiresAt],
                    ['Granted by', selectedCredential.grantedBy],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.05] bg-white/[0.03] px-3 py-2 text-xs">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-medium text-white text-right">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                ['State', selectedCredential.status],
                ['Last used', selectedCredential.lastUsed],
                ['Expires', selectedCredential.expiresAt],
                ['Grant', selectedCredential.grantedBy],
                ['Health', selectedCredential.health],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2.5 text-xs">
                  <div className="text-muted-foreground">{label}</div>
                  <div className={cn('mt-1 font-semibold', label === 'Health' ? healthColor : 'text-white')}>{value}</div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2.5 text-xs">
              <span className="text-muted-foreground">Last admin action</span>
              <span className="font-medium text-white">{lastAction}</span>
            </div>
            {copied && (
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-xs text-emerald-300">
                {copied}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div id="hc-settings-notes" className={cn('rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3', settingsPanel === 'governance' || settingsPanel === 'gateway' || settingsPanel === 'security' ? '' : 'hidden')}>
            <p className="text-sm font-semibold text-white">
              {settingsPanel === 'governance' ? 'Governance Mode' : settingsPanel === 'gateway' ? 'Gateway Connection' : 'Security Controls'}
            </p>
            <div className="space-y-2 text-xs text-muted-foreground">
              {settingsPanel === 'governance' && (
                <>
                  <p>- Shadow mode logs all decisions without blocking live care workflows.</p>
                  <p>- Live governance turns enforcement on after admin confirmation.</p>
                  <p>- Clinical Safety Mode stays active across every department runtime.</p>
                </>
              )}
              {settingsPanel === 'gateway' && (
                <>
                  <p>- Demo gateway points at local sandbox services for walkthroughs.</p>
                  <p>- Production connects through the EDON governance gateway and short-lived runtime tokens.</p>
                  <p>- Gateway health, tenant ID, and request traces are used for support correlation.</p>
                </>
              )}
              {settingsPanel === 'security' && (
                <>
                  <p>- Human access stays SSO / invite based.</p>
                  <p>- Runtime credentials are admin issued and department scoped.</p>
                  <p>- Diagnostics stay sanitized and tenant scoped.</p>
                </>
              )}
            </div>
          </div>
          <div id="hc-settings-audit" className={cn('rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3', settingsPanel === 'support' ? '' : 'hidden')}>
            <p className="text-sm font-semibold text-white">Access events</p>
            <div className="space-y-2">
              {activity.map((item, idx) => (
                <div key={idx} className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2 text-xs text-muted-foreground">
                  {item}
                </div>
              ))}
            </div>
          </div>
          <div className={cn('rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3', settingsPanel === 'support' ? '' : 'hidden')}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">Audit Trail</p>
                <p className="text-xs text-muted-foreground">Search and filter recent credential actions and audit events.</p>
              </div>
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">{filteredAuditTrail.length} match{filteredAuditTrail.length === 1 ? '' : 'es'}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2">
              <div className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2 flex items-center gap-2">
                <Search size={13} className="text-muted-foreground shrink-0" />
                <input
                  value={auditSearch}
                  onChange={e => setAuditSearch(e.target.value)}
                  placeholder="Search action, actor, target, or result"
                  className="w-full bg-transparent text-xs text-white placeholder:text-muted-foreground outline-none"
                />
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {(['All', 'Granted', 'Copied', 'Rotating', 'Revoked'] as const).map(filter => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => setAuditResultFilter(filter)}
                    className={cn(
                      'rounded-full border px-3 py-1.5 text-[11px] font-medium transition-colors',
                      auditResultFilter === filter
                        ? 'border-primary/30 bg-primary/10 text-primary'
                        : 'border-white/[0.06] bg-black/20 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {filter}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setAuditIndex(i => (i - 1 + (filteredAuditTrail.length || 1)) % (filteredAuditTrail.length || 1))}
                disabled={!filteredAuditTrail.length}
                className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                aria-label="Previous audit item"
              >
                <ChevronLeft size={15} className="text-foreground/80" />
              </button>
              <div className="min-w-0 text-center flex-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Event {filteredAuditTrail.length ? auditIndex + 1 : 0} / {filteredAuditTrail.length || auditTrail.length}</p>
                <p className="text-sm font-semibold text-white truncate">{selectedAudit?.action ?? 'No match'}</p>
                <p className="text-xs text-muted-foreground truncate">{selectedAudit?.target ?? 'Adjust search or filter'}</p>
              </div>
              <button
                type="button"
                onClick={() => setAuditIndex(i => (i + 1) % (filteredAuditTrail.length || 1))}
                disabled={!filteredAuditTrail.length}
                className="w-9 h-9 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] flex items-center justify-center transition-colors"
                aria-label="Next audit item"
              >
                <ChevronRight size={15} className="text-foreground/80" />
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-white/[0.06]">
              <div className="grid grid-cols-[1.1fr_.9fr_.6fr_1.1fr_.6fr] gap-2 bg-white/[0.04] px-3 py-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                <span>Action</span>
                <span>Actor</span>
                <span>Time</span>
                <span>Target</span>
                <span>Result</span>
              </div>
              {filteredAuditTrail.length ? filteredAuditTrail.map((row, idx) => (
                <button
                  key={`${row.action}-${row.timestamp}-${idx}`}
                  type="button"
                  onClick={() => setAuditIndex(idx)}
                  className={cn(
                    'grid w-full grid-cols-[1.1fr_.9fr_.6fr_1.1fr_.6fr] gap-2 px-3 py-2 text-left text-xs border-t border-white/[0.05] bg-black/20 transition-colors',
                    idx === auditIndex ? 'bg-primary/10' : 'hover:bg-white/[0.03]',
                  )}
                >
                  <span className="text-white font-medium">{row.action}</span>
                  <span className="text-muted-foreground">{row.actor}</span>
                  <span className="text-muted-foreground">{row.timestamp}</span>
                  <span className="text-muted-foreground whitespace-normal break-words">{row.target}</span>
                  <span className={cn(
                    'font-medium',
                    row.result === 'Granted' || row.result === 'Copied' ? 'text-emerald-300' :
                    row.result === 'Rotating' ? 'text-amber-300' :
                    'text-red-300',
                  )}>
                    {row.result}
                  </span>
                </button>
              )) : (
                <div className="px-3 py-4 text-xs text-muted-foreground">No audit rows match this search.</div>
              )}
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-3 text-xs space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Selected event detail</span>
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60">Audit snapshot</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Action:</span> <span className="text-white">{selectedAudit?.action}</span></div>
                <div><span className="text-muted-foreground">Actor:</span> <span className="text-white">{selectedAudit?.actor}</span></div>
                <div><span className="text-muted-foreground">Time:</span> <span className="text-white">{selectedAudit?.timestamp}</span></div>
                <div><span className="text-muted-foreground">Target:</span> <span className="text-white break-words">{selectedAudit?.target}</span></div>
                <div><span className="text-muted-foreground">Result:</span> <span className={cn('font-medium', selectedAudit?.result === 'Granted' || selectedAudit?.result === 'Copied' ? 'text-emerald-300' : selectedAudit?.result === 'Rotating' ? 'text-amber-300' : 'text-red-300')}>{selectedAudit?.result}</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
        </div>
      </div>
    </div>
  )
}

void ImpactTab


const NAV_TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard',     icon: BarChart3 },
  { id: 'agents',    label: 'Agents',        icon: Activity },
  { id: 'audit',     label: 'Audit',         icon: FileText },
  { id: 'policies',  label: 'Policies',      icon: Shield },
  { id: 'review',    label: 'Review Queue',  icon: ClipboardList },
  { id: 'import',    label: 'Onboard',       icon: Upload },
  { id: 'operations', label: 'Operations',   icon: Share2 },
  { id: 'settings',  label: 'Settings',      icon: Settings2 },
]

interface TopNavProps {
  activeTab: Tab
  setActiveTab: (t: Tab) => void
  lockdown: boolean
  onLockdown: () => void
  pendingReviewCount: number
  onRestartOnboarding: () => void
}

function TopNav({ activeTab, setActiveTab, lockdown, onLockdown, pendingReviewCount, onRestartOnboarding }: TopNavProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-border/50 bg-background/80 backdrop-blur-xl">
      {lockdown && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-red-500/15 border-b border-red-500/30">
          <div className="flex items-center gap-2 text-red-400 text-xs">
            <AlertTriangle size={13} className="animate-pulse shrink-0" />
            <span className="font-bold tracking-wider">EMERGENCY LOCKDOWN ACTIVE</span>
            <span className="text-red-400/60 hidden sm:inline">— all agent actions suspended</span>
          </div>
          <button onClick={onLockdown}
            className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium text-red-400 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 transition-colors">
            Lift Lockdown
          </button>
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-3 h-14">
        {/* Wordmark */}
        <div className="shrink-0 flex items-center gap-2">
          <span className="edon-brand font-bold text-foreground text-sm">EDON</span>
          <span className="text-muted-foreground/60 text-xs hidden md:block">· St. Mercy Health</span>
        </div>

        {/* Desktop nav — icon-only pills in rounded container */}
        <nav className="hidden md:flex items-center gap-0.5 px-1 py-0.5 rounded-xl bg-muted/40 border border-border/40">
          {NAV_TABS.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                title={tab.label}
                className={`nav-item relative flex items-center justify-center w-9 h-8 rounded-lg ${isActive ? 'nav-item-active' : ''}`}
              >
                <Icon size={15} />
                {tab.id === 'review' && pendingReviewCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                    {pendingReviewCount > 9 ? '9+' : pendingReviewCount}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        {/* Mobile nav */}
        <nav className="flex md:hidden items-center gap-0.5 flex-1 overflow-x-auto scrollbar-none">
          {NAV_TABS.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                className={cn('nav-item flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium shrink-0', isActive ? 'nav-item-active' : '')}>
                <Icon size={13} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="flex items-center gap-2 ml-auto shrink-0">
          {/* Live status */}
          <div className="hidden lg:flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
            <span>500 agents · Live</span>
          </div>

          {/* User pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 h-7 rounded-full border border-border bg-secondary/60 text-xs text-muted-foreground">
            <User size={11} />
            <span className="font-medium text-foreground">Dr. Chen</span>
          </div>

          {/* Emergency lockdown */}
          <button onClick={onLockdown}
            className={cn(
              'flex items-center justify-center w-8 h-8 rounded-lg border transition-all',
              lockdown
                ? 'bg-red-500/20 border-red-400/50 text-red-400 animate-pulse'
                : 'border-border/60 bg-secondary/60 text-muted-foreground/50 hover:text-red-400/80 hover:bg-red-500/[0.08] hover:border-red-500/20',
            )}
            title={lockdown ? 'Lockdown active — click to lift' : 'Emergency lockdown'}>
            <AlertTriangle size={13} />
          </button>

          <button
            onClick={onRestartOnboarding}
            className="flex items-center justify-center w-8 h-8 rounded-lg border border-border/60 bg-secondary/60 text-muted-foreground/60 hover:text-foreground hover:bg-secondary transition-colors"
            title="Restart onboarding"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>
    </header>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [entered, setEntered] = useState(false)
  const [onboarded, setOnboarded] = useState(() => localStorage.getItem('hc_demo_ob') !== '0')
  const [demoRuntimeMode, setDemoRuntimeMode] = useState<'sandbox' | 'live'>('sandbox')
  const [demoModeConfirm, setDemoModeConfirm] = useState<null | 'enable-live' | 'return-sandbox'>(null)
  const [deptModes, setDeptModes] = useState<Record<string, 'sandbox' | 'governed'>>(() => {
    const initial = Object.fromEntries(DEPARTMENTS.map(d => [d.key, 'governed'])) as Record<string, 'sandbox' | 'governed'>
    initial.telehealth = 'sandbox'
    return initial
  })
  const [coordinationAllowed, setCoordinationAllowed] = useState<Record<string, boolean>>(() => {
    const initial = Object.fromEntries(DEPARTMENTS.map(d => [d.key, true])) as Record<string, boolean>
    initial.telehealth = false
    return initial
  })
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [lockdown, setLockdown] = useState(false)
  const [lockdownConfirm, setLockdownConfirm] = useState(false)
  const [pendingReviewCount, setPendingReviewCount] = useState(
    ALL_EVENTS.filter(e => e.verdict === 'ESCALATE' && e.reviewStatus === 'pending').length
  )
  const [displayCount, setDisplayCount] = useState(30)
  const [speed, setSpeed] = useState<number>(1)
  const [paused, setPaused] = useState(false)
  const [uptime, setUptime] = useState(183440)
  const [latency, setLatency] = useState(4.8)
  const [chatOpen, setChatOpen] = useState(false)
  const [aside, setAside] = useState<AsideItem | null>(null)
  useEffect(() => { _hcDisplayCount = displayCount }, [displayCount])

  useEffect(() => {
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add('dark')
    localStorage.setItem('edon_theme', 'dark')
  }, [])

  const speedRef = useRef(speed)
  const pausedRef = useRef(paused)
  const displayCountRef = useRef(displayCount)
  speedRef.current = speed
  pausedRef.current = paused
  displayCountRef.current = displayCount

  // Event stream ticker
  useEffect(() => {
    const tick = () => {
      if (!pausedRef.current && displayCountRef.current < 1000) {
        setDisplayCount(c => Math.min(c + 1, 1000))
      }
    }
    const id = setInterval(tick, 800 / speedRef.current)
    return () => clearInterval(id)
  }, [speed, paused])

  // Uptime ticker
  useEffect(() => {
    const id = setInterval(() => setUptime(u => u + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Latency jitter
  useEffect(() => {
    const id = setInterval(() => {
      setLatency(prev => {
        const jitter = (Math.random() - 0.5) * 1.6
        return Math.min(10.4, Math.max(2.1, prev + jitter))
      })
    }, 1800)
    return () => clearInterval(id)
  }, [])

  const handleReset = useCallback(() => {
    setDisplayCount(30)
    setPaused(false)
  }, [])

  const handleRestartOnboarding = useCallback(() => {
    localStorage.setItem('hc_demo_ob', '0')
    setOnboarded(false)
    setActiveTab('dashboard')
    setChatOpen(false)
    setAside(null)
  }, [])

  const confirmDemoModeChange = useCallback(() => {
    if (demoModeConfirm === 'enable-live') setDemoRuntimeMode('live')
    if (demoModeConfirm === 'return-sandbox') setDemoRuntimeMode('sandbox')
    setDemoModeConfirm(null)
  }, [demoModeConfirm])

  const handleDeptModeChange = useCallback((deptKey: string, mode: 'sandbox' | 'governed') => {
    setDeptModes(prev => ({ ...prev, [deptKey]: mode }))
  }, [])

  const handleCoordinationToggle = useCallback((deptKey: string) => {
    setCoordinationAllowed(prev => ({ ...prev, [deptKey]: !(prev[deptKey] ?? true) }))
  }, [])

  useEffect(() => {
    publishHCContext([
      `app tab ${activeTab}`,
      onboarded ? 'tenant onboarded' : 'tenant onboarding active',
      chatOpen ? 'chat open' : 'chat closed',
      aside ? `aside ${aside.type}:${aside.id}` : 'aside closed',
      lockdownConfirm ? 'lockdown confirm open' : 'lockdown confirm closed',
      demoModeConfirm ? `mode confirm ${demoModeConfirm}` : 'mode confirm closed',
    ].join(' · '))
  }, [activeTab, onboarded, chatOpen, aside, lockdownConfirm, demoModeConfirm])

  if (!entered) {
    return <HealthcareAccessGate onEnter={() => setEntered(true)} />
  }

  if (!onboarded) {
    return (
      <HCOnboardingScreen
        onComplete={() => {
          localStorage.setItem('hc_demo_ob', '1')
          setOnboarded(true)
        }}
        onLogout={() => setEntered(false)}
      />
    )
  }

  return (
    <AsideCtx.Provider value={{ open: (item) => setAside(item as AsideItem) }}>
    <div className="min-h-screen bg-background">
      {/* Demo banner */}
      <button
        type="button"
        onClick={() => setDemoModeConfirm(demoRuntimeMode === 'sandbox' ? 'enable-live' : 'return-sandbox')}
        className="w-full flex items-center justify-center gap-2 px-4 py-1.5 border-b text-center"
        style={{
          background: demoRuntimeMode === 'sandbox' ? 'rgba(59,130,246,0.14)' : 'rgba(74,222,128,0.14)',
          borderBottomColor: demoRuntimeMode === 'sandbox' ? 'rgba(59,130,246,0.35)' : 'rgba(74,222,128,0.35)',
        }}
      >
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: demoRuntimeMode === 'sandbox' ? '#60a5fa' : '#4ade80' }} />
          <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: demoRuntimeMode === 'sandbox' ? '#93c5fd' : '#86efac' }}>
            {demoRuntimeMode === 'sandbox' ? 'Sandbox mode' : 'Live governance'}
          </span>
        </span>
        <span className="text-xs ml-2" style={{ color: demoRuntimeMode === 'sandbox' ? 'rgba(191,219,254,0.75)' : 'rgba(167,243,208,0.75)' }}>
          {demoRuntimeMode === 'sandbox' ? '— Audit-only · No execution' : '— Enforcement on · Governed actions active'}
        </span>
      </button>

      <TopNav activeTab={activeTab} setActiveTab={setActiveTab} lockdown={lockdown} onLockdown={() => lockdown ? setLockdown(false) : setLockdownConfirm(true)} pendingReviewCount={pendingReviewCount} onRestartOnboarding={handleRestartOnboarding} />

      {/* Lockdown banner */}
      <AnimatePresence>
        {lockdown && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden bg-red-500/10 border-b-2 border-red-500/50"
          >
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <AlertTriangle size={15} className="text-red-400 shrink-0 animate-pulse" />
                <span className="text-red-400 font-bold text-xs sm:text-sm tracking-wider">EMERGENCY LOCKDOWN ACTIVE</span>
                <span className="text-red-400/60 text-xs hidden sm:inline">— All 500 agents halted · No AI actions being processed</span>
              </div>
              <button
                onClick={() => setLockdown(false)}
                className="shrink-0 px-3 py-1 rounded-lg border border-red-500/30 text-red-400/80 text-xs font-semibold hover:bg-red-500/15 transition-colors"
              >
                Lift Lockdown
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <AnimatePresence mode="wait">
          {activeTab === 'dashboard' && (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="space-y-4"
            >
              <DashboardTab
                displayCount={displayCount}
                speed={speed}
                setSpeed={setSpeed}
                paused={paused}
                setPaused={setPaused}
                onReset={handleReset}
                uptime={uptime}
                latency={latency}
                deptModes={deptModes}
                onDeptModeChange={handleDeptModeChange}
                coordinationAllowed={coordinationAllowed}
                onCoordinationToggle={handleCoordinationToggle}
              />
              <CrossAgentFeedHC deptModes={deptModes} coordinationAllowed={coordinationAllowed} />
            </motion.div>
          )}
          {activeTab === 'agents' && (
            <motion.div
              key="agents"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <AgentsTab deptModes={deptModes} />
            </motion.div>
          )}
          {activeTab === 'audit' && (
            <motion.div
              key="audit"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <AuditTab deptModes={deptModes} />
            </motion.div>
          )}
          {activeTab === 'policies' && (
            <motion.div
              key="policies"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <PoliciesTab />
            </motion.div>
          )}
          {activeTab === 'review' && (
            <motion.div
              key="review"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <ReviewQueueTab onReviewCountChange={setPendingReviewCount} />
            </motion.div>
          )}
          {activeTab === 'import' && (
            <motion.div
              key="import"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <OnboardTab />
            </motion.div>
          )}
          {activeTab === 'operations' && (
            <motion.div
              key="operations"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <OperationsTab />
            </motion.div>
          )}
          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <SettingsTabHC />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Floating chat button (visible when panel is closed) */}
      <AnimatePresence>
        {!chatOpen && (
          <motion.button
            key="chat-fab"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setChatOpen(true)}
            className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-2xl bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 transition-colors"
            style={{ boxShadow: '0 4px 24px rgba(100,220,120,0.35)' }}
          >
            <MessageSquare size={16} />
            <span className="text-sm font-semibold">Ask AI</span>
            <span className="w-2 h-2 rounded-full bg-primary-foreground/60 animate-pulse-dot" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* AI Chat Panel */}
      <AIChatPanel open={chatOpen} onClose={() => setChatOpen(false)} activeTab={activeTab} />

      {/* Aside panel — AI reasoning for cited items */}
      <AnimatePresence>
        {aside && <AsidePanelHC key={`${aside.type}-${aside.id}`} type={aside.type} id={aside.id} onClose={() => setAside(null)} />}
      </AnimatePresence>

      {/* Lockdown confirmation modal */}
      <AnimatePresence>
        {lockdownConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
          >
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setLockdownConfirm(false)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.92, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 16 }}
              transition={{ type: 'spring', bounce: 0.25, duration: 0.35 }}
              className="relative z-10 bg-background border border-red-500/30 rounded-2xl p-8 max-w-sm w-full mx-4 shadow-2xl"
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/15 border border-red-500/30 flex items-center justify-center">
                  <AlertTriangle size={24} className="text-red-400" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-foreground mb-2">Activate Emergency Lockdown?</h2>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    This will immediately halt all <span className="text-foreground font-semibold">500 active agents</span> across
                    St. Mercy Health System. No AI actions will be processed until lockdown is lifted by an authorized physician.
                  </p>
                </div>
                <div className="bg-red-500/8 border border-red-500/20 rounded-xl px-4 py-3 w-full text-left">
                  <p className="text-xs text-red-400/80 font-semibold mb-1.5">This action will:</p>
                  <ul className="text-xs text-muted-foreground space-y-1">
                    <li>• Suspend all automated clinical decisions</li>
                    <li>• Queue pending actions for manual review</li>
                    <li>• Log a timestamped lockdown event in the audit trail</li>
                  </ul>
                </div>
                <div className="flex gap-3 w-full">
                  <button
                    onClick={() => setLockdownConfirm(false)}
                    className="flex-1 px-4 py-2.5 rounded-xl border border-border text-sm font-medium hover:bg-secondary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => { setLockdown(true); setLockdownConfirm(false) }}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-red-500/20 border border-red-500/40 text-red-400 text-sm font-bold hover:bg-red-500/30 transition-colors"
                  >
                    Activate Lockdown
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Demo mode confirmation modal */}
      <AnimatePresence>
        {demoModeConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
          >
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setDemoModeConfirm(null)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.92, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 16 }}
              transition={{ type: 'spring', bounce: 0.25, duration: 0.35 }}
              className="relative z-10 bg-background border rounded-2xl p-8 max-w-sm w-full mx-4 shadow-2xl"
              style={{ borderColor: demoModeConfirm === 'enable-live' ? 'rgba(74,222,128,0.3)' : 'rgba(59,130,246,0.3)' }}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div
                  className="w-14 h-14 rounded-full border flex items-center justify-center"
                  style={{ background: demoModeConfirm === 'enable-live' ? 'rgba(74,222,128,0.12)' : 'rgba(59,130,246,0.12)', borderColor: demoModeConfirm === 'enable-live' ? 'rgba(74,222,128,0.3)' : 'rgba(59,130,246,0.3)' }}
                >
                  <AlertTriangle size={24} style={{ color: demoModeConfirm === 'enable-live' ? '#86efac' : '#93c5fd' }} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-foreground mb-2">
                    {demoModeConfirm === 'enable-live' ? 'Enable live governance?' : 'Return to sandbox?'}
                  </h2>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {demoModeConfirm === 'enable-live'
                      ? 'This switches the demo into live governance mode. Enforcement will be on and governed actions will be treated as live.'
                      : 'This returns the demo to sandbox mode. Actions remain audit-only and no execution will occur.'}
                  </p>
                </div>
                <div className="flex gap-3 w-full">
                  <button
                    onClick={() => setDemoModeConfirm(null)}
                    className="flex-1 px-4 py-2.5 rounded-xl border border-border text-sm font-medium hover:bg-secondary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmDemoModeChange}
                    className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold transition-colors"
                    style={{
                      background: demoModeConfirm === 'enable-live' ? 'rgba(74,222,128,0.20)' : 'rgba(59,130,246,0.20)',
                      color: demoModeConfirm === 'enable-live' ? '#86efac' : '#93c5fd',
                      border: demoModeConfirm === 'enable-live' ? '1px solid rgba(74,222,128,0.35)' : '1px solid rgba(59,130,246,0.35)',
                    }}
                  >
                    {demoModeConfirm === 'enable-live' ? 'Enable Live' : 'Return to Sandbox'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </AsideCtx.Provider>
  )
}



