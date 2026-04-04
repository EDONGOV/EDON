import { useState, useEffect, useRef, useCallback } from 'react'
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
  Lock,
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
  Sun,
  Moon,
  Plus,
  ClipboardList,
  ThumbsUp,
  ThumbsDown,
  LayoutList,
  LayoutGrid,
  Link2,
  ArrowRight,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type Verdict = 'ALLOW' | 'BLOCK' | 'ESCALATE'
type Tab = 'dashboard' | 'agents' | 'audit' | 'policies' | 'review'

interface HospitalAgent {
  id: string
  name: string
  department: string
  deptLabel: string
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
    for (let i = 0; i < dept.count; i++) {
      const nameBase = names[Math.floor(rng() * names.length)]
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

// ─── Healthcare Access Gate ───────────────────────────────────────────────────

const GATE_FEATURES = [
  {
    icon: Shield,
    label: 'Clinical safety governance',
    desc: 'Every AI action — medication orders, dosage changes, surgical pre-auth — evaluated against FDA SaMD and HIPAA policy before execution.',
  },
  {
    icon: Activity,
    label: 'Sub-10ms enforcement',
    desc: 'Real-time allow / block / escalate decisions that never slow clinical workflows.',
  },
  {
    icon: Brain,
    label: 'Physician escalation queue',
    desc: 'High-risk operations require attending confirmation. Human review built into the governance loop.',
  },
  {
    icon: FileText,
    label: 'Immutable HIPAA audit trail',
    desc: 'Every decision logged with agent ID, policy version, patient context, and policy hash — ready for compliance review.',
  },
]

// SHA-256 hash of the demo passcode (computed offline — not the passcode itself)
const PASSCODE_HASH = '6df06e04a6f94d20a8a7f82b078e95ee68d2b0566c40a53cae98a80fdd0dfd1c'

async function sha256hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

function HealthcareAccessGate({ onEnter }: { onEnter: () => void }) {
  const [code, setCode] = useState('')
  const [showCode, setShowCode] = useState(false)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const [shake, setShake] = useState(false)

  const handleSubmit = async () => {
    const trimmed = code.trim()
    if (!trimmed) { setError('Enter the access code to continue.'); return }
    setChecking(true)
    setError('')
    const hash = await sha256hex(trimmed)
    if (hash === PASSCODE_HASH) {
      onEnter()
    } else {
      setChecking(false)
      setError('Incorrect access code.')
      setShake(true)
      setTimeout(() => setShake(false), 600)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex">

      {/* Left panel — branding + features */}
      <div className="hidden lg:flex flex-col justify-between w-[440px] shrink-0 border-r border-white/10 bg-white/[0.02] px-10 py-12">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <Heart className="w-5 h-5 text-rose-400" />
            <span className="text-xl font-semibold tracking-[0.25em] text-foreground/90">EDON</span>
          </div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Healthcare Governance</p>
          <p className="text-sm text-muted-foreground leading-relaxed mt-6">
            The AI governance layer for clinical environments. Every agent action — from lab result retrieval to emergency surgery pre-auth — evaluated before it executes.
          </p>

          <div className="mt-10 space-y-6">
            {GATE_FEATURES.map(({ icon: Icon, label, desc }) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-start gap-3"
              >
                <div className="w-8 h-8 shrink-0 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center mt-0.5">
                  <Icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs text-muted-foreground/50">
            © {new Date().getFullYear()} EDON. Governing AI at scale.
          </p>
          <p className="text-xs text-muted-foreground/40">
            Demo environment — simulated data only
          </p>
        </div>
      </div>

      {/* Right panel — entry */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          {/* Mobile wordmark */}
          <div className="lg:hidden mb-8 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Heart className="w-5 h-5 text-rose-400" />
              <span className="text-xl font-semibold tracking-[0.25em] text-foreground/90">EDON</span>
            </div>
            <p className="text-xs text-muted-foreground uppercase tracking-widest">Healthcare Governance</p>
          </div>

          {/* Card */}
          <motion.div
            animate={shake ? { x: [-8, 8, -6, 6, -3, 3, 0] } : { x: 0 }}
            transition={{ duration: 0.5 }}
            className="rounded-2xl border border-white/10 bg-white/[0.03] p-8 shadow-2xl"
          >
            {/* Hospital badge */}
            <div className="flex items-center gap-2 mb-6">
              <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
                <Cross className="w-4 h-4 text-rose-400" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground/80">St. Mercy Health System</p>
                <p className="text-xs text-muted-foreground">EDON Clinical Safety Mode · 500 agents enrolled</p>
              </div>
            </div>

            <h1 className="text-xl font-semibold mb-1">Restricted Access</h1>
            <p className="text-sm text-muted-foreground mb-7 leading-relaxed">
              This demo is private. Enter your access code to continue.
            </p>

            <div className="space-y-3">
              {/* Passcode input */}
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                <input
                  type={showCode ? 'text' : 'password'}
                  autoFocus
                  value={code}
                  onChange={e => { setCode(e.target.value); setError('') }}
                  onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
                  placeholder=""
                  className="w-full bg-white/[0.04] border border-white/15 rounded-xl pl-10 pr-10 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/30 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowCode(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showCode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.p
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="text-xs text-red-400 flex items-center gap-1.5"
                  >
                    <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
                    {error}
                  </motion.p>
                )}
              </AnimatePresence>

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={checking}
                className="w-full h-11 inline-flex items-center justify-center gap-2 font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60 disabled:pointer-events-none transition-all duration-200 text-sm"
              >
                {checking
                  ? <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  : <Stethoscope className="w-4 h-4" />
                }
                {checking ? 'Verifying…' : 'Enter Healthcare Demo'}
              </button>

              <div className="relative flex items-center gap-3 pt-1">
                <div className="flex-1 h-px bg-white/10" />
                <span className="text-xs text-muted-foreground">demo highlights</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>

              <div className="grid grid-cols-2 gap-2 pt-0.5">
                {[
                  { icon: Pill,        text: 'Dosage cap enforcement' },
                  { icon: Brain,       text: 'Physician review queue' },
                  { icon: Activity,    text: 'Live decision stream' },
                  { icon: FileText,    text: 'HIPAA audit trail' },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2">
                    <Icon className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span className="text-xs text-muted-foreground">{text}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          <p className="text-center text-xs text-muted-foreground/50 mt-6">
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
}

function DashboardTab({ displayCount, speed, setSpeed, paused, setPaused, onReset, uptime, latency }: DashboardTabProps) {
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

function CrossAgentFeedHC() {
  const [expanded, setExpanded] = useState<string | null>(null)
  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Link2 size={14} className="text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Cross-Department Coordination</h3>
        <span className="text-xs text-muted-foreground bg-white/5 px-2 py-0.5 rounded-full border border-white/10">Automatic</span>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">
        These are <span className="text-foreground font-medium">EDON's automatic decisions</span> — no human involved. When one agent raises a risk signal for a patient, EDON instantly blocks or escalates related actions from other departments touching the same patient. Anything marked ESCALATE gets routed to the <span className="text-amber-400 font-medium">Review Queue</span> for physician sign-off.
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
                  return (
                    <div key={idx} className="flex items-center gap-1.5">
                      <div className={cn('flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-mono', vs.bg)}>
                        {vs.icon}
                        <DIcon size={10} className={dept?.color ?? ''} />
                        <span className="text-foreground/80">{step.deptLabel.split(' ')[0]}</span>
                        <span className="opacity-50">·</span>
                        <span className="opacity-60">{step.toolOp.split('.').slice(-1)[0]}</span>
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

interface AgentsTabProps {}

function AgentsTab(_props: AgentsTabProps) {
  const [selectedDept, setSelectedDept] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>('grouped')
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

  const filtered = ALL_AGENTS.filter(a => {
    const matchDept = selectedDept === 'all' || a.department === selectedDept
    const matchSearch =
      !search ||
      a.id.toLowerCase().includes(search.toLowerCase()) ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.deptLabel.toLowerCase().includes(search.toLowerCase())
    return matchDept && matchSearch
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // Group by department for grouped view
  const byDept = DEPARTMENTS.map(d => ({
    dept: d,
    agents: filtered.filter(a => a.department === d.key),
  })).filter(g => g.agents.length > 0)

  useEffect(() => { setPage(0) }, [selectedDept, search])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Hospital Agents</h1>
          <p className="text-muted-foreground text-sm mt-1">500 agents across 13 departments</p>
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
                            <Badge variant={r.variant}>{r.label}</Badge>
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
                          className={cn(
                            'rounded-2xl border p-4 hover:bg-white/[0.04] transition-colors space-y-3',
                            agent.status === 'alert' || agent.blockRateTrend === 'spiked'
                              ? 'border-red-500/30 bg-red-500/[0.04]'
                              : agent.blockRateTrend === 'rising'
                              ? 'border-amber-500/20 bg-white/[0.03]'
                              : 'border-white/10 bg-white/[0.03]',
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

            {/* Cross-department feed */}
            <CrossAgentFeedHC />
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

function AuditTab() {
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
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50">
              <option value="all">All Verdicts</option>
              <option value="allow">ALLOW</option>
              <option value="block">BLOCK</option>
              <option value="escalate">ESCALATE</option>
            </select>
            <select value={vendorFilter} onChange={e => { setVendorFilter(e.target.value); setPage(1) }}
              className="h-9 rounded-xl border border-white/15 bg-secondary/50 px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 min-w-[180px]">
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

  const selectClass = 'w-full bg-secondary border border-white/10 rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all'

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
                    <select value={agentScope} onChange={e => setAgentScope(e.target.value)} className={selectClass}>
                      {agentScopeOptions.map(o => <option key={o.label} value={o.label}>{o.label}</option>)}
                    </select>
                  </div>

                  {/* Device */}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      On which device / equipment?
                    </label>
                    <select value={device} onChange={e => setDevice(e.target.value)} className={selectClass}>
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
                    <select value={taskCode} onChange={e => setTaskCode(e.target.value)} className={selectClass}>
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

const SUGGESTED_QUESTIONS = [
  'What is the current block rate?',
  'Which department has the most violations?',
  'How many HIPAA violations today?',
  'Show me high-risk agents',
  'Any escalated events needing review?',
  'What are the top blocked operations?',
  'How is the system performing?',
  'Which agents are on alert?',
]

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: Date
}

function getMockResponse(question: string): string {
  const q = question.toLowerCase()

  if (q.includes('block rate') || (q.includes('block') && q.includes('rate'))) {
    return `The current block rate across all 500 agents is **${_BLOCK_RATE}%**. Out of ${ALL_EVENTS.length.toLocaleString()} governed actions in the last hour, **${_BLOCK_COUNT}** were blocked and **${_ALLOW_COUNT}** were allowed. The most common block reason is HIPAA Violation (${_HIPAA_COUNT} incidents), followed by Consent Missing (${_CONSENT_COUNT} incidents).`
  }
  if (q.includes('department') || q.includes('dept') || q.includes('most violation') || q.includes('which dept')) {
    return `**${_TOP_DEPT_LABEL}** has the highest violation count with **${_TOP_DEPT?.[1]}** blocked actions. Here's a quick breakdown of top departments by blocks:\n\n${Object.entries(_DEPT_BLOCKS).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => `• ${DEPARTMENTS.find(d => d.key === k)?.label ?? k}: ${v} blocks`).join('\n')}\n\nConsider reviewing policy thresholds for ${_TOP_DEPT_LABEL}.`
  }
  if (q.includes('hipaa')) {
    return `There have been **${_HIPAA_COUNT} HIPAA violations** flagged in the current audit window. These were all blocked automatically by the Clinical Safety policy pack. Additionally, **${_CONSENT_COUNT}** Consent Missing violations and **${_PROTO_COUNT}** Protocol Deviation incidents were intercepted. All audit records are HIPAA-compliant with SHA-256 hash chain verification.`
  }
  if (q.includes('high risk') || (q.includes('risk') && (q.includes('agent') || q.includes('show')))) {
    return `There are currently **${_HIGH_RISK} high-risk agents** and **${_MED_RISK} medium-risk agents** in the system. High-risk agents have block rates exceeding 20% or have triggered repeated anomaly patterns. I recommend reviewing the top blocked agent **${_TOP_BLOCKED_AGENT?.[0]}** which has been blocked **${_TOP_BLOCKED_AGENT?.[1]} times**. Navigate to the Agents tab and filter by Risk: High to see the full list.`
  }
  if (q.includes('escalat')) {
    return `**${_ESC_COUNT} actions** have been escalated to physician review in this session. Escalated operations include: emergency.surgery.authorize, high.risk.medication.approve, and dnr.status.update — all requiring a physician confirmation before execution. These are currently pending in the human review queue. No escalations have exceeded the 5-minute SLA timeout.`
  }
  if (q.includes('top blocked') || q.includes('blocked operation') || q.includes('what is being blocked')) {
    return `The top blocked operations are:\n\n• **medication.dose.override** — most frequently intercepted (DEA & protocol controls)\n• **ehr.bulk.export** — blocked to prevent unauthorized data exfiltration\n• **patient.data.transfer.external** — blocked by HIPAA perimeter policy\n• **controlled.substance.dispense** — requires pharmacy supervisor approval\n• **consent.bypass** — zero-tolerance enforcement\n\nAll blocks are logged with full intent tracing and chain-hash verification.`
  }
  if (q.includes('perform') || q.includes('latency') || q.includes('speed') || q.includes('uptime') || q.includes('system health') || q.includes('status')) {
    return `System performance is nominal:\n\n• **Latency:** p50 ~2.9ms · p95 ~8.6ms · p99 ~13.4ms — well within the 50ms SLO\n• **Uptime:** 99.97% (2d 2h 50m current session)\n• **Throughput:** ~${(ALL_EVENTS.length / 60).toFixed(0)} decisions/second sustained\n• **Chain Integrity:** SHA-256 hash chain fully verified — no tampering detected\n• **Agents Online:** ${_ACTIVE}/500 active right now\n\nAll governance infrastructure components are healthy.`
  }
  if (q.includes('alert') || q.includes('which agent') || (q.includes('agent') && q.includes('problem'))) {
    const alertAgents = ALL_AGENTS.filter(a => a.status === 'alert').slice(0, 5)
    return `**${_ALERT_AGENTS} agents** are currently in alert status:\n\n${alertAgents.map(a => `• **${a.id}** (${a.deptLabel}) — block rate ${a.blockRate}%`).join('\n')}\n\nAlert status is triggered when an agent exceeds a block threshold in a 10-minute rolling window or when anomaly scoring exceeds 80/100. These agents are still operational but under heightened monitoring.`
  }
  if (q.includes('icu') || q.includes('intensive care')) {
    const icuAgents = ALL_AGENTS.filter(a => a.department === 'icu')
    const icuBlocks = ALL_EVENTS.filter(e => e.department === 'icu' && e.verdict === 'BLOCK').length
    return `The **ICU Monitoring** department has **${icuAgents.length} agents** deployed across floors 4N and 4S. In this session: **${icuBlocks}** actions were blocked. ICU agents primarily handle patient.vitals.read, ecg.stream.read, and iv.drip.monitor operations — all currently allowed under Clinical Safety Mode. Any deviation from protocol (e.g. medication.dose.override) is blocked immediately.`
  }
  if (q.includes('pharmacy') || q.includes('medication') || q.includes('drug') || q.includes('dea')) {
    const rxAgents = ALL_AGENTS.filter(a => a.department === 'pharmacy')
    const rxBlocks = ALL_EVENTS.filter(e => e.department === 'pharmacy' && e.verdict === 'BLOCK').length
    return `**Pharmacy Automation** has **${rxAgents.length} agents** on floors 1C and B1. **${rxBlocks}** pharmacy-related actions were blocked in this session — primarily controlled.substance.dispense (requires DEA/CSA compliance check) and medication.dose.override. The DEA Compliance policy is active and enforced at the highest priority level. No controlled substance dispensing has bypassed governance.`
  }
  if (q.includes('radiology') || q.includes('imaging') || q.includes('scan')) {
    const radAgents = ALL_AGENTS.filter(a => a.department === 'radiology')
    const radBlocks = ALL_EVENTS.filter(e => e.department === 'radiology' && e.verdict === 'BLOCK').length
    return `**Radiology AI** has **${radAgents.length} agents** operating in B1 and B2. **${radBlocks}** actions were blocked — mainly attempts to bulk-export imaging data outside the hospital perimeter (HIPAA violation). Standard operations like imaging.scan.view are flowing normally with an average decision latency under 5ms.`
  }
  if (q.includes('how many agent') || q.includes('total agent') || q.includes('count')) {
    return `There are **500 agents** deployed across **13 departments** at St. Mercy Health System:\n\n${DEPARTMENTS.map(d => `• ${d.label}: ${d.count} agents`).join('\n')}\n\nCurrently **${_ACTIVE} are active**, ${ALL_AGENTS.filter(a => a.status === 'idle').length} idle, and ${_ALERT_AGENTS} in alert status.`
  }
  if (q.includes('audit') || q.includes('log') || q.includes('chain') || q.includes('hash')) {
    return `The audit trail contains **${ALL_EVENTS.length.toLocaleString()} records** in this session. The SHA-256 hash chain is intact — each event references the previous event's hash, forming a tamper-evident ledger. Chain verification passed ✅. You can export the full log as CSV or JSON from the Audit tab. All records include: Agent ID, Intent ID, Policy Version, Patient ID, Latency, Risk Score, and the full decision explanation.`
  }
  if (q.includes('policy') || q.includes('compliance') || q.includes('rule')) {
    return `**Clinical Safety Mode** is the active policy pack (500/500 agents enrolled). It enforces:\n\n• HIPAA & HITECH data access controls\n• FDA SaMD v1.2.0 safety constraints\n• DEA controlled substance rules\n• Consent validation before any patient data access\n• Physician confirmation for high-risk operations\n\nOther available packs (inactive): Emergency Override Mode, Research Mode (IRB), Pharmacy Strict Mode, Surgical Robotics Mode.`
  }
  if (q.includes('hello') || q.includes('hi') || q.includes('hey') || q.includes('help')) {
    return `Hello! I'm the **EDON AI Assistant** for St. Mercy Health System. I have full visibility into your 500 deployed agents, their decision patterns, and governance events.\n\nYou can ask me about:\n• Block rates and violation trends\n• Specific departments or agents\n• HIPAA compliance status\n• System performance and uptime\n• Escalated events needing review\n• Policy pack configurations\n\nWhat would you like to know?`
  }
  if (q.includes('trend') || q.includes('over time') || q.includes('pattern')) {
    return `Based on the current session data, I can see a few notable patterns:\n\n• **Block spike** in ICU and Pharmacy — consistent with end-of-shift medication reconciliation attempts\n• **HIPAA violations** are concentrated in EHR/Records agents (ehr.bulk.export attempts)\n• **Escalation rate** is holding at ${Math.round((_ESC_COUNT / ALL_EVENTS.length) * 100)}% — within normal clinical operating bounds\n• **Latency** has been stable at under 10ms p99 for the entire session\n\nNo anomalous patterns detected that require immediate intervention.`
  }
  // Default catch-all
  return `I searched across ${ALL_EVENTS.length.toLocaleString()} governance events and ${ALL_AGENTS.length} agent records for context on **"${question}"**.\n\nHere's what I found: the system is currently processing ~${Math.round(ALL_EVENTS.length / 60)} decisions/second with a ${_BLOCK_RATE}% block rate. The top concern is **${_TOP_DEPT_LABEL}** (${_TOP_DEPT?.[1]} violations). All ${_ACTIVE} active agents are operating within policy bounds.\n\nCould you clarify what you're looking for? Try asking about a specific department, operation type, or compliance standard.`
}

interface AIChatPanelProps {
  open: boolean
  onClose: () => void
}

function AIChatPanel({ open, onClose }: AIChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hi! I'm your **EDON AI Assistant**. I have live insight into all **500 agents** and **${ALL_EVENTS.length.toLocaleString()} governance events** at St. Mercy Health System.\n\nAsk me anything about your data.`,
      ts: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 300)
  }, [open])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  const send = async (text: string) => {
    const q = text.trim()
    if (!q) return
    setInput('')
    const userMsg: ChatMessage = { id: `u${Date.now()}`, role: 'user', content: q, ts: new Date() }
    setMessages(prev => [...prev, userMsg])
    setTyping(true)
    await new Promise(r => setTimeout(r, 600 + Math.random() * 600))
    setTyping(false)
    const aiMsg: ChatMessage = { id: `a${Date.now()}`, role: 'assistant', content: getMockResponse(q), ts: new Date() }
    setMessages(prev => [...prev, aiMsg])
  }

  // Render markdown-lite: **bold**, bullet lists
  function renderContent(text: string) {
    return text.split('\n').map((line, i) => {
      const parts = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={j} className="text-foreground font-semibold">{part.slice(2, -2)}</strong>
        }
        return part
      })
      const isBullet = line.trimStart().startsWith('•')
      return (
        <span key={i} className={cn('block', isBullet ? 'pl-2' : '', i > 0 ? 'mt-1' : '')}>
          {parts}
        </span>
      )
    })
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
                <p className="text-[10px] text-muted-foreground">St. Mercy · 500 agents · live data</p>
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
                      {renderContent(msg.content)}
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
                  {SUGGESTED_QUESTIONS.slice(0, 4).map(q => (
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

// ─── Top Nav ──────────────────────────────────────────────────────────────────

const NAV_TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard',     icon: BarChart3 },
  { id: 'agents',    label: 'Agents',        icon: Activity },
  { id: 'audit',     label: 'Audit',         icon: FileText },
  { id: 'policies',  label: 'Policies',      icon: Shield },
  { id: 'review',    label: 'Review Queue',  icon: ClipboardList },
]

interface TopNavProps {
  activeTab: Tab
  setActiveTab: (t: Tab) => void
  theme: 'dark' | 'light'
  onToggleTheme: () => void
  lockdown: boolean
  onLockdown: () => void
  pendingReviewCount: number
}

function TopNav({ activeTab, setActiveTab, theme, onToggleTheme, lockdown, onLockdown, pendingReviewCount }: TopNavProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-4 h-14">
          {/* Wordmark */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
              <Lock size={13} className="text-primary" />
            </div>
            <span className="edon-brand font-bold text-foreground text-sm tracking-widest">EDON</span>
            <span className="text-muted-foreground text-xs hidden sm:block">· St. Mercy Health System</span>
          </div>

          {/* Nav pills */}
          <nav className="flex items-center gap-1 bg-secondary/60 rounded-xl p-1 ml-2">
            {NAV_TABS.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200',
                    isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="absolute inset-0 rounded-lg"
                      style={{ background: 'var(--nav-indicator-bg)' }}
                      transition={{ type: 'spring', bounce: 0.2, duration: 0.35 }}
                    />
                  )}
                  <span className="relative flex items-center gap-1.5">
                    <Icon size={13} />
                    <span className="hidden sm:inline">{tab.label}</span>
                    {tab.id === 'review' && pendingReviewCount > 0 && (
                      <span className="flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-amber-500 text-[9px] font-bold text-black leading-none">
                        {pendingReviewCount}
                      </span>
                    )}
                  </span>
                </button>
              )
            })}
          </nav>

          {/* Right badges */}
          <div className="ml-auto flex items-center gap-2">
            {/* Theme toggle */}
            <button
              onClick={onToggleTheme}
              className="flex items-center justify-center w-8 h-8 rounded-xl border border-border bg-secondary hover:bg-muted transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'dark'
                ? <Sun size={14} className="text-muted-foreground" />
                : <Moon size={14} className="text-muted-foreground" />}
            </button>
            <Badge variant="green">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-dot" />
              Live
            </Badge>
            <Badge variant="default" className="hidden sm:inline-flex">
              <Shield size={10} className="text-primary" />
              Clinical Safety
            </Badge>
            <div className="flex items-center gap-1.5 bg-secondary rounded-xl px-2.5 py-1.5 border border-border">
              <User size={12} className="text-muted-foreground" />
              <span className="text-xs text-foreground font-medium hidden sm:block">Dr. Chen</span>
            </div>
            {/* Emergency Lockdown */}
            <button
              onClick={onLockdown}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all duration-200',
                lockdown
                  ? 'bg-red-500/20 border-red-400/60 text-red-400 animate-pulse'
                  : 'bg-red-500/10 border-red-500/30 text-red-400/80 hover:bg-red-500/20 hover:border-red-400/50 hover:text-red-400',
              )}
              title={lockdown ? 'Lockdown active — click to lift' : 'Emergency lockdown — halts all agents'}
            >
              <AlertTriangle size={12} />
              <span className="hidden sm:inline">{lockdown ? 'LOCKDOWN' : 'Lockdown'}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [showGate, setShowGate] = useState(true)
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
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    (localStorage.getItem('edon_theme') as 'dark' | 'light') ?? 'dark'
  )

  useEffect(() => {
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(theme)
    localStorage.setItem('edon_theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

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

  if (showGate) {
    return <HealthcareAccessGate onEnter={() => setShowGate(false)} />
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Demo banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/20 text-center py-1.5">
        <span className="text-amber-400 text-xs font-semibold tracking-widest">⚠ DEMO MODE</span>
        <span className="text-amber-400/70 text-xs ml-2">— Simulated data only · Not connected to live systems</span>
      </div>

      <TopNav activeTab={activeTab} setActiveTab={setActiveTab} theme={theme} onToggleTheme={toggleTheme} lockdown={lockdown} onLockdown={() => lockdown ? setLockdown(false) : setLockdownConfirm(true)} pendingReviewCount={pendingReviewCount} />

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
              />
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
              <AgentsTab />
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
              <AuditTab />
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
      <AIChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />

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
    </div>
  )
}
