/**
 * EDON Healthcare Demo — St. Mercy Health System
 * Fully standalone: no API calls, no auth, 500 hospital agents, 1000 pre-generated events.
 * Matches the exact visual design of the EDON agent UI.
 */
import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck, Ban, AlertTriangle, Timer, Users, Activity,
  CheckCircle2, Clock, Zap, Play, Pause, RotateCcw, Filter,
  ChevronRight, ChevronDown, Search, Hash, FileText,
  Heart, Stethoscope, Pill, Microscope, Scan, Cpu,
  Cross, Syringe, Brain, Eye, Wind, Thermometer, Bell,
  Shield, Lock, AlertCircle, TrendingUp, BarChart2,
} from 'lucide-react';
import { StatCard } from '@/components/StatCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

// ─── Types ────────────────────────────────────────────────────────────────────

type Verdict = 'ALLOW' | 'BLOCK' | 'ESCALATE';
type Tab = 'dashboard' | 'agents' | 'audit' | 'policies';

interface HospitalAgent {
  id: string;
  name: string;
  department: string;
  type: string;
  status: 'active' | 'idle' | 'alert';
  decisions24h: number;
  blocked24h: number;
  blockRate: number;
  lastAction: string;
  lastActiveMin: number; // minutes ago
  riskLevel: 'low' | 'medium' | 'high';
  floor: string;
  serialNo: string;
}

interface DemoEvent {
  id: string;
  verdict: Verdict;
  agent: string;
  department: string;
  toolOp: string;
  reasonCode: string | null;
  latencyMs: number;
  ts: Date;
  hash: string;
  riskScore: number;
  patientId: string;
}

// ─── Hospital seed data ───────────────────────────────────────────────────────

const DEPARTMENTS = [
  { id: 'icu',       label: 'ICU',               icon: Heart,       count: 45, color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/20',    riskBase: 0.12 },
  { id: 'radiology', label: 'Radiology',          icon: Scan,        count: 38, color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/20',   riskBase: 0.06 },
  { id: 'surgery',   label: 'Surgical Robotics',  icon: Cross,       count: 30, color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/20', riskBase: 0.08 },
  { id: 'er',        label: 'Emergency',          icon: AlertCircle, count: 28, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/20', riskBase: 0.15 },
  { id: 'pharmacy',  label: 'Pharmacy',           icon: Pill,        count: 35, color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/20',  riskBase: 0.22 },
  { id: 'lab',       label: 'Clinical Lab',       icon: Microscope,  count: 42, color: 'text-cyan-400',   bg: 'bg-cyan-500/10',   border: 'border-cyan-500/20',   riskBase: 0.05 },
  { id: 'monitoring',label: 'Patient Monitoring', icon: Activity,    count: 65, color: 'text-emerald-400',bg: 'bg-emerald-500/10',border: 'border-emerald-500/20',riskBase: 0.03 },
  { id: 'ehr',       label: 'EHR / Records',      icon: FileText,    count: 48, color: 'text-sky-400',    bg: 'bg-sky-500/10',    border: 'border-sky-500/20',    riskBase: 0.18 },
  { id: 'nursing',   label: 'Nurse Assist',       icon: Stethoscope, count: 52, color: 'text-pink-400',   bg: 'bg-pink-500/10',   border: 'border-pink-500/20',   riskBase: 0.07 },
  { id: 'cardio',    label: 'Cardiology',         icon: Heart,       count: 22, color: 'text-rose-400',   bg: 'bg-rose-500/10',   border: 'border-rose-500/20',   riskBase: 0.09 },
  { id: 'neuro',     label: 'Neurology',          icon: Brain,       count: 18, color: 'text-violet-400', bg: 'bg-violet-500/10', border: 'border-violet-500/20', riskBase: 0.08 },
  { id: 'scheduling',label: 'Scheduling',         icon: Clock,       count: 40, color: 'text-teal-400',   bg: 'bg-teal-500/10',   border: 'border-teal-500/20',   riskBase: 0.04 },
  { id: 'telehealth',label: 'Telehealth',         icon: Wind,        count: 37, color: 'text-indigo-400', bg: 'bg-indigo-500/10', border: 'border-indigo-500/20', riskBase: 0.05 },
] as const;

type DeptId = typeof DEPARTMENTS[number]['id'];

const DEPT_PREFIXES: Record<string, string> = {
  icu: 'icu-mon', radiology: 'rad-ai', surgery: 'surg-bot', er: 'er-triage',
  pharmacy: 'rx-bot', lab: 'lab-auto', monitoring: 'pt-mon', ehr: 'ehr-agent',
  nursing: 'nurse-ai', cardio: 'cardio-ai', neuro: 'neuro-ai',
  scheduling: 'sched-bot', telehealth: 'tele-agent',
};

const FLOORS: Record<string, string[]> = {
  icu: ['Floor 4 ICU', 'Floor 5 ICU-B', 'Floor 4 ICU-C'],
  radiology: ['Floor 2 Radiology', 'Floor B1 Imaging'],
  surgery: ['Floor 3 OR-1', 'Floor 3 OR-2', 'Floor 3 OR-3'],
  er: ['Floor 1 ER', 'Floor 1 Trauma'],
  pharmacy: ['Floor 1 Pharmacy', 'Floor 3 Satellite Rx'],
  lab: ['Floor B2 Lab', 'Floor 1 Point-of-Care'],
  monitoring: ['Floor 2', 'Floor 3', 'Floor 4', 'Floor 5', 'Floor 6'],
  ehr: ['Floor 1 HIM', 'Remote / Cloud'],
  nursing: ['Floor 2', 'Floor 3', 'Floor 4', 'Floor 5'],
  cardio: ['Floor 6 Cardiology', 'Floor 6 Cath Lab'],
  neuro: ['Floor 7 Neurology'],
  scheduling: ['Floor 1 Admin', 'Remote'],
  telehealth: ['Remote / Telehealth'],
};

const ALLOWED_OPS = [
  'patient.vitals.read', 'lab.results.fetch', 'imaging.scan.view',
  'ehr.record.read', 'medication.schedule.read', 'appointment.list',
  'diagnosis.assist.query', 'equipment.status.check', 'staff.schedule.read',
  'alert.trigger.nurse', 'iv.drip.monitor', 'ecg.stream.read',
  'patient.location.track', 'consent.form.read', 'allergy.record.fetch',
];

const BLOCKED_OPS = [
  'medication.dose.override', 'ehr.bulk.export', 'patient.data.transfer.external',
  'controlled.substance.dispense', 'consent.bypass', 'diagnosis.override.physician',
  'equipment.calibration.skip', 'surgery.protocol.deviate', 'billing.record.modify',
  'patient.identity.reassign',
];

const ESCALATE_OPS = [
  'emergency.surgery.authorize', 'high.risk.medication.approve',
  'dnr.status.update', 'patient.discharge.approve', 'critical.alert.escalate',
  'experimental.treatment.flag',
];

const BLOCK_REASONS = [
  'HIPAA_VIOLATION', 'UNAUTHORIZED_ACCESS', 'SCOPE_VIOLATION',
  'CONSENT_MISSING', 'CONTROLLED_SUBSTANCE', 'PROTOCOL_DEVIATION',
  'FDA_COMPLIANCE', 'BUDGET_EXCEEDED',
];

const REASON_LABELS: Record<string, string> = {
  HIPAA_VIOLATION:      'HIPAA Violation',
  UNAUTHORIZED_ACCESS:  'Unauthorized Access',
  SCOPE_VIOLATION:      'Scope Violation',
  CONSENT_MISSING:      'Consent Missing',
  CONTROLLED_SUBSTANCE: 'Controlled Substance',
  PROTOCOL_DEVIATION:   'Protocol Deviation',
  FDA_COMPLIANCE:       'FDA Compliance',
  BUDGET_EXCEEDED:      'Budget Exceeded',
  HUMAN_REVIEW:         'Needs Review',
};

// ─── Generate 500 agents ──────────────────────────────────────────────────────

let rngSeed = 0xdeadbeef;
function rng() {
  rngSeed = Math.imul(rngSeed ^ (rngSeed >>> 16), 0x45d9f3b);
  rngSeed = Math.imul(rngSeed ^ (rngSeed >>> 16), 0x45d9f3b);
  return (rngSeed >>> 0) / 0xffffffff;
}

function generateAgents(): HospitalAgent[] {
  rngSeed = 0xdeadbeef;
  const agents: HospitalAgent[] = [];
  let globalIdx = 1;

  for (const dept of DEPARTMENTS) {
    const floors = FLOORS[dept.id] ?? ['Floor 1'];
    for (let i = 1; i <= dept.count; i++) {
      const decisions24h = Math.floor(rng() * 280) + 20;
      const blockRateRaw = dept.riskBase + (rng() - 0.5) * 0.08;
      const blockRate = Math.max(0.01, Math.min(0.45, blockRateRaw));
      const blocked24h = Math.round(decisions24h * blockRate);
      const lastActiveMin = Math.floor(rng() * 30);
      const statusRoll = rng();
      const status: 'active' | 'idle' | 'alert' =
        statusRoll < 0.72 ? 'active' : statusRoll < 0.88 ? 'idle' : 'alert';
      const riskLevel: 'low' | 'medium' | 'high' =
        blockRate < 0.08 ? 'low' : blockRate < 0.20 ? 'medium' : 'high';

      agents.push({
        id: `${DEPT_PREFIXES[dept.id]}-${String(i).padStart(3, '0')}`,
        name: `${dept.label} Agent ${String(i).padStart(3, '0')}`,
        department: dept.id,
        type: dept.label,
        status,
        decisions24h,
        blocked24h,
        blockRate: Math.round(blockRate * 100),
        lastAction: ALLOWED_OPS[Math.floor(rng() * ALLOWED_OPS.length)],
        lastActiveMin,
        riskLevel,
        floor: floors[Math.floor(rng() * floors.length)],
        serialNo: `SN-${Math.floor(rng() * 9_000_000 + 1_000_000)}`,
      });
      globalIdx++;
    }
  }
  return agents;
}

const ALL_AGENTS = generateAgents();

// ─── Generate 1000 events ─────────────────────────────────────────────────────

function murmur(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return (h >>> 0).toString(16).padStart(8, '0');
}

function generateEvents(): DemoEvent[] {
  rngSeed = 0xcafebabe;
  const events: DemoEvent[] = [];
  const now = Date.now();
  const span = 3_600_000; // 60 minutes
  let prevHash = '0'.repeat(40);

  for (let i = 0; i < 1000; i++) {
    const ts = new Date(now - span + i * 3_600);
    const agent = ALL_AGENTS[Math.floor(rng() * ALL_AGENTS.length)];
    const dept = DEPARTMENTS.find(d => d.id === agent.department)!;
    const roll = rng();

    let verdict: Verdict;
    let toolOp: string;
    let reasonCode: string | null = null;

    if (roll < 0.55) {
      verdict = 'ALLOW';
      toolOp = ALLOWED_OPS[Math.floor(rng() * ALLOWED_OPS.length)];
    } else if (roll < 0.90) {
      verdict = 'BLOCK';
      toolOp = BLOCKED_OPS[Math.floor(rng() * BLOCKED_OPS.length)];
      reasonCode = BLOCK_REASONS[Math.floor(rng() * BLOCK_REASONS.length)];
    } else {
      verdict = 'ESCALATE';
      toolOp = ESCALATE_OPS[Math.floor(rng() * ESCALATE_OPS.length)];
      reasonCode = 'HUMAN_REVIEW';
    }

    // High-risk departments block more
    if (verdict === 'ALLOW' && rng() < dept.riskBase * 0.8) {
      verdict = 'BLOCK';
      toolOp = BLOCKED_OPS[Math.floor(rng() * BLOCKED_OPS.length)];
      reasonCode = BLOCK_REASONS[Math.floor(rng() * BLOCK_REASONS.length)];
    }

    const id = `evt_${String(i).padStart(5, '0')}`;
    const hash = murmur(id + prevHash) + murmur(prevHash + id) + murmur(id);
    const patN = Math.floor(rng() * 9_000 + 1_000);
    prevHash = hash;

    events.push({
      id,
      verdict,
      agent: agent.id,
      department: agent.department,
      toolOp,
      reasonCode,
      latencyMs: 2 + Math.floor(rng() * 11),
      ts,
      hash,
      riskScore: verdict === 'ALLOW' ? Math.floor(rng() * 35) : verdict === 'ESCALATE' ? 55 + Math.floor(rng() * 30) : 38 + Math.floor(rng() * 45),
      patientId: `PT-${patN}`,
    });
  }
  return events.reverse(); // newest first
}

const ALL_EVENTS = generateEvents();

// Aggregate stats
const TOTAL_DECISIONS_BASE = 48_291;
const BLOCKED_BASE = ALL_EVENTS.filter(e => e.verdict === 'BLOCK').length + 14_837;
const ESCALATED_BASE = ALL_EVENTS.filter(e => e.verdict === 'ESCALATE').length + 1_204;
const AGENTS_ONLINE = ALL_AGENTS.filter(a => a.status === 'active').length;

// ─── Small UI helpers ─────────────────────────────────────────────────────────

function formatTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

function formatUptime(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${h}h ${m}m ${sec}s`;
}

function relTime(min: number) {
  if (min === 0) return 'just now';
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  if (verdict === 'ALLOW') return (
    <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/25 gap-1 font-semibold text-[11px] py-0.5">
      <CheckCircle2 className="w-3 h-3" /> ALLOW
    </Badge>
  );
  if (verdict === 'BLOCK') return (
    <Badge className="bg-red-500/15 text-red-400 border-red-500/25 gap-1 font-semibold text-[11px] py-0.5">
      <Ban className="w-3 h-3" /> BLOCK
    </Badge>
  );
  return (
    <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/25 gap-1 font-semibold text-[11px] py-0.5">
      <AlertTriangle className="w-3 h-3" /> ESCALATE
    </Badge>
  );
}

function RiskBadge({ level }: { level: 'low' | 'medium' | 'high' }) {
  const s = level === 'low'
    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    : level === 'medium'
    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    : 'bg-red-500/10 text-red-400 border-red-500/20';
  return <Badge className={`${s} text-[10px] py-0 font-semibold capitalize`}>{level}</Badge>;
}

// ─── Demo-mode top nav (standalone, no API calls) ─────────────────────────────

function DemoNav({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const NAV: { label: string; tab: Tab }[] = [
    { label: 'Dashboard', tab: 'dashboard' },
    { label: 'Agents',    tab: 'agents'    },
    { label: 'Audit',     tab: 'audit'     },
    { label: 'Policies',  tab: 'policies'  },
  ];
  return (
    <motion.header
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      className="sticky top-0 z-50 border-b border-white/10 backdrop-blur-xl bg-background/70"
    >
      {/* Demo banner */}
      <div className="flex items-center justify-between px-6 py-1.5 bg-amber-500/8 border-b border-amber-500/20">
        <div className="flex items-center gap-2 text-amber-400 text-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          <span className="font-semibold">DEMO MODE</span>
          <span className="text-amber-400/60 hidden sm:inline">— St. Mercy Health System · Simulation only</span>
        </div>
        <a href="https://edoncore.com/contact" target="_blank" rel="noopener noreferrer"
          className="text-xs text-amber-400 hover:text-amber-300 font-medium flex items-center gap-1 transition-colors">
          Deploy for your hospital <ChevronRight className="w-3 h-3" />
        </a>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <span className="edon-brand text-sm font-semibold tracking-[0.3em] text-foreground/90">EDON</span>
            <span className="hidden sm:inline text-xs text-muted-foreground/60 border-l border-white/10 pl-3">St. Mercy Health System</span>
          </div>

          <nav className="hidden md:flex items-center gap-1 bg-secondary/60 rounded-xl p-1 ml-2">
            {NAV.map(({ label, tab: t }) => (
              <button key={t} onClick={() => setTab(t)}
                className={`relative flex items-center gap-2 rounded-lg px-4 py-2 text-sm transition-colors ${
                  tab === t ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}>
                {tab === t && (
                  <motion.div layoutId="demo-nav-indicator"
                    className="absolute inset-0 bg-white/15 rounded-lg"
                    transition={{ type: 'spring', bounce: 0.2, duration: 0.35 }} />
                )}
                <span className="relative z-10">{label}</span>
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className="flex items-center gap-1.5 text-xs border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="hidden sm:inline">Live</span>
            </Badge>
            <Badge variant="outline" className="text-xs border-primary/30 text-primary bg-primary/10 gap-1">
              <Zap className="w-3 h-3" /> Clinical Safety
            </Badge>
            <div className="flex items-center gap-1.5 bg-secondary rounded-xl px-2.5 py-1.5 border border-white/10">
              <div className="w-5 h-5 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center text-[10px] font-bold text-primary">D</div>
              <span className="hidden sm:text-xs text-foreground/80 sm:inline">Dr. Chen</span>
            </div>
            <button className="flex md:hidden items-center justify-center w-8 h-8 rounded-lg border border-white/10 bg-white/5"
              onClick={() => setMobileOpen(v => !v)}>
              <span className="text-xs text-muted-foreground">☰</span>
            </button>
          </div>
        </div>
      </div>

      {/* Mobile nav */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-white/10 bg-background/95 overflow-hidden">
            <nav className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-col gap-1">
              {NAV.map(({ label, tab: t }) => (
                <button key={t} onClick={() => { setTab(t); setMobileOpen(false); }}
                  className={`flex items-center rounded-lg px-3 py-2.5 text-sm transition-colors text-left ${
                    tab === t ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                  }`}>{label}</button>
              ))}
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function DemoMode() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [displayCount, setDisplayCount] = useState(30);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState<0.5 | 1 | 2 | 4>(1);
  const [uptime, setUptime] = useState(183_440); // ~2 days
  const [latency, setLatency] = useState(4.8);
  const [deptFilter, setDeptFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [agentPage, setAgentPage] = useState(0);
  const AGENTS_PER_PAGE = 25;

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const t = setInterval(() => setUptime(u => u + 1), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setLatency(l => Math.max(2.1, Math.min(10.4, l + (Math.random() - 0.5) * 1.6)));
    }, 1800);
    return () => clearInterval(t);
  }, []);

  // Stream events
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (paused || displayCount >= ALL_EVENTS.length) return;
    const delay = Math.round(800 / speed);
    intervalRef.current = setInterval(() => {
      setDisplayCount(n => Math.min(n + 1, ALL_EVENTS.length));
    }, delay);
    return () => clearInterval(intervalRef.current!);
  }, [paused, speed, displayCount]);

  // Visible events
  const events = ALL_EVENTS.slice(0, displayCount);
  const feedEvents = events.slice(0, 25);
  const auditEvents = events.slice(0, 80);

  // Stats
  const total = TOTAL_DECISIONS_BASE + displayCount;
  const blocked = BLOCKED_BASE + events.filter(e => e.verdict === 'BLOCK').length;
  const escalated = ESCALATED_BASE + events.filter(e => e.verdict === 'ESCALATE').length;
  const blockRate = ((blocked / total) * 100).toFixed(1);
  const p95 = (latency * 1.85 + 1.3).toFixed(1);
  const p99 = (latency * 3.1 + 2.8).toFixed(1);

  // Block reason breakdown
  const reasonCounts = useMemo(() => {
    const base: Record<string, number> = {
      HIPAA_VIOLATION: 5832, UNAUTHORIZED_ACCESS: 3241, SCOPE_VIOLATION: 2109,
      CONSENT_MISSING: 1847, CONTROLLED_SUBSTANCE: 843, PROTOCOL_DEVIATION: 612,
    };
    for (const e of events) {
      if (e.reasonCode && e.verdict === 'BLOCK') {
        base[e.reasonCode] = (base[e.reasonCode] ?? 0) + 1;
      }
    }
    return Object.entries(base).sort(([, a], [, b]) => b - a).slice(0, 6);
  }, [displayCount]);
  const maxReason = reasonCounts[0]?.[1] ?? 1;

  // Department stats
  const deptStats = useMemo(() => {
    const map: Record<string, { blocks: number; total: number }> = {};
    for (const e of events) {
      if (!map[e.department]) map[e.department] = { blocks: 0, total: 0 };
      map[e.department].total++;
      if (e.verdict === 'BLOCK') map[e.department].blocks++;
    }
    return map;
  }, [displayCount]);

  // Agent filtering
  const filteredAgents = useMemo(() => {
    let result = ALL_AGENTS;
    if (deptFilter !== 'all') result = result.filter(a => a.department === deptFilter);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(a =>
        a.id.toLowerCase().includes(q) ||
        a.type.toLowerCase().includes(q) ||
        a.floor.toLowerCase().includes(q)
      );
    }
    return result;
  }, [deptFilter, searchQuery]);

  const pagedAgents = filteredAgents.slice(agentPage * AGENTS_PER_PAGE, (agentPage + 1) * AGENTS_PER_PAGE);
  const totalPages = Math.ceil(filteredAgents.length / AGENTS_PER_PAGE);

  const handleReset = () => { setDisplayCount(30); setPaused(false); };

  return (
    <div className="min-h-screen">
      <DemoNav tab={tab} setTab={setTab} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">

        {/* ── DASHBOARD TAB ── */}
        {tab === 'dashboard' && (
          <>
            {/* Page header */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
              className="mb-8 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold mb-1">Healthcare Governance</h1>
                <p className="text-sm text-muted-foreground">
                  🏥 St. Mercy Health System · {AGENTS_ONLINE} agents online · Clinical Safety Mode active
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge variant="outline" className="text-xs border-white/15 text-muted-foreground gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  {displayCount.toLocaleString()} / 1,000 events
                </Badge>
              </div>
            </motion.div>

            {/* KPI cards */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <StatCard title="Governed (24h)"   value={total.toLocaleString()}     icon={ShieldCheck}    variant="success"  delay={0} />
              <StatCard title="Blocked (24h)"    value={blocked.toLocaleString()}   icon={Ban}            variant="danger"   delay={1} change={`${blockRate}% block rate`} changeType="negative" />
              <StatCard title="Escalated (24h)"  value={escalated.toLocaleString()} icon={AlertTriangle}  variant="warning"  delay={2} change="Awaiting physician review" changeType="neutral" />
              <StatCard title="Avg Latency"       value={`${latency.toFixed(1)}ms`}  icon={Timer}          variant="default"  delay={3} change={`p95: ${p95}ms · p99: ${p99}ms`} changeType="neutral" />
            </motion.div>

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">

              {/* Decision feed */}
              <div className="lg:col-span-2 glass-card overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    <h2 className="text-sm font-semibold">Live Decision Feed</h2>
                  </div>
                  <span className="text-xs text-muted-foreground font-mono">last 25 events</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Verdict</th>
                        <th className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Agent</th>
                        <th className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden sm:table-cell">Tool.Op</th>
                        <th className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden md:table-cell">Reason</th>
                        <th className="text-right px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">ms</th>
                        <th className="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {feedEvents.map((e, i) => (
                        <tr key={e.id}
                          className={`border-b border-white/5 hover:bg-white/[0.03] transition-colors ${i === 0 ? 'animate-[slideIn_0.3s_ease-out]' : ''}`}>
                          <td className="px-4 py-2.5"><VerdictBadge verdict={e.verdict} /></td>
                          <td className="px-3 py-2.5 font-mono text-xs text-foreground/70">{e.agent}</td>
                          <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground hidden sm:table-cell">{e.toolOp}</td>
                          <td className="px-3 py-2.5 hidden md:table-cell">
                            {e.reasonCode
                              ? <span className="text-amber-400 text-xs font-medium">{REASON_LABELS[e.reasonCode] ?? e.reasonCode}</span>
                              : <span className="text-muted-foreground/40">—</span>}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono text-xs text-muted-foreground">{e.latencyMs}ms</td>
                          <td className="px-4 py-2.5 text-right font-mono text-[10px] text-muted-foreground/60">{formatTime(e.ts)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Right column */}
              <div className="flex flex-col gap-6">
                {/* Policy mode card */}
                <div className="glass-card p-5">
                  <div className="flex items-center gap-2 mb-4">
                    <Shield className="w-4 h-4 text-primary" />
                    <h3 className="text-sm font-semibold">Active Policy</h3>
                    <Badge className="ml-auto bg-primary/15 text-primary border-primary/25 text-[10px] font-bold">ACTIVE</Badge>
                  </div>
                  <div className="text-lg font-bold text-foreground mb-1">Clinical Safety Mode</div>
                  <p className="text-xs text-muted-foreground mb-4">HIPAA + FDA AI/ML SaMD compliance enforced. All medication overrides require physician confirmation.</p>
                  <div className="space-y-2">
                    {[
                      { label: 'HIPAA', val: 'Enforced', ok: true },
                      { label: 'FDA SaMD', val: 'Enforced', ok: true },
                      { label: 'Consent Gate', val: 'Active', ok: true },
                      { label: 'Audit Chain', val: 'Verified ✓', ok: true },
                    ].map(({ label, val, ok }) => (
                      <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/5">
                        <span className="text-xs text-muted-foreground">{label}</span>
                        <span className={`text-xs font-semibold ${ok ? 'text-emerald-400' : 'text-red-400'}`}>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Gateway health */}
                <div className="glass-card p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">System Health</h3>
                  <div className="space-y-2">
                    {[
                      { k: 'Uptime',    v: formatUptime(uptime) },
                      { k: 'p50',       v: `${latency.toFixed(1)}ms` },
                      { k: 'p95',       v: `${p95}ms` },
                      { k: 'p99',       v: `${p99}ms` },
                      { k: 'Agents',    v: `${AGENTS_ONLINE} / ${ALL_AGENTS.length}` },
                      { k: 'Events/hr', v: Math.round(displayCount * 1.2).toLocaleString() },
                    ].map(({ k, v }) => (
                      <div key={k} className="flex items-center justify-between py-1 border-b border-white/5">
                        <span className="text-xs text-muted-foreground">{k}</span>
                        <span className="text-xs font-mono font-semibold text-foreground/80">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Block reasons + dept breakdown */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">

              {/* Top block reasons */}
              <div className="glass-card p-5">
                <div className="flex items-center gap-2 mb-5">
                  <BarChart2 className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Top Block Reasons</h3>
                  <Badge variant="outline" className="text-xs ml-auto">24h</Badge>
                </div>
                <div className="space-y-3.5">
                  {reasonCounts.map(([code, count]) => (
                    <div key={code}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs text-foreground/70 font-medium">{REASON_LABELS[code] ?? code}</span>
                        <span className="text-xs font-mono text-muted-foreground tabular-nums">{count.toLocaleString()}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${Math.min(100, (count / maxReason) * 100)}%` }}
                          transition={{ duration: 0.7, delay: 0.1 }}
                          className="h-full rounded-full bg-red-400/60"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Department activity */}
              <div className="glass-card p-5">
                <div className="flex items-center gap-2 mb-5">
                  <TrendingUp className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Department Activity</h3>
                  <Badge variant="outline" className="text-xs ml-auto">Live</Badge>
                </div>
                <div className="space-y-2.5">
                  {DEPARTMENTS.slice(0, 8).map(dept => {
                    const stats = deptStats[dept.id] ?? { total: 0, blocks: 0 };
                    const pct = stats.total > 0 ? Math.round((stats.blocks / stats.total) * 100) : 0;
                    const Icon = dept.icon;
                    return (
                      <div key={dept.id} className="flex items-center gap-3">
                        <div className={`w-6 h-6 rounded-md flex items-center justify-center ${dept.bg} shrink-0`}>
                          <Icon className={`w-3.5 h-3.5 ${dept.color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-xs text-foreground/70 font-medium truncate">{dept.label}</span>
                            <span className="text-xs font-mono text-muted-foreground shrink-0 ml-2">{stats.total} ev</span>
                          </div>
                          <div className="h-1 rounded-full bg-white/8 overflow-hidden">
                            <div className={`h-full rounded-full transition-all duration-700 ${pct >= 20 ? 'bg-red-400/60' : pct >= 10 ? 'bg-amber-400/60' : 'bg-primary/60'}`}
                              style={{ width: `${Math.min(100, pct * 4)}%` }} />
                          </div>
                        </div>
                        <span className={`text-xs font-semibold w-8 text-right tabular-nums shrink-0 ${pct >= 20 ? 'text-red-400' : pct >= 10 ? 'text-amber-400' : 'text-emerald-400'}`}>{pct}%</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Simulation controls */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
              className="glass-card p-4">
              <div className="flex items-center gap-4 flex-wrap">
                <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Simulation</span>
                <div className="flex items-center gap-1">
                  {([0.5, 1, 2, 4] as const).map(s => (
                    <Button key={s} variant={speed === s ? 'default' : 'outline'} size="sm"
                      onClick={() => setSpeed(s)}
                      className={`h-7 px-2.5 text-xs font-mono ${speed === s ? 'bg-primary/20 text-primary border-primary/30' : 'border-white/10 text-muted-foreground'}`}>
                      {s}×
                    </Button>
                  ))}
                </div>
                <Button variant="outline" size="sm" onClick={() => setPaused(p => !p)}
                  className="h-7 px-3 text-xs border-white/10 text-muted-foreground gap-1.5">
                  {paused ? <><Play className="w-3 h-3" /> Resume</> : <><Pause className="w-3 h-3" /> Pause</>}
                </Button>
                <Button variant="outline" size="sm" onClick={handleReset}
                  className="h-7 px-3 text-xs border-white/10 text-muted-foreground gap-1.5">
                  <RotateCcw className="w-3 h-3" /> Reset
                </Button>
                <span className="text-xs text-muted-foreground ml-auto font-mono">
                  {displayCount.toLocaleString()} / 1,000 events streamed
                </span>
              </div>
            </motion.div>
          </>
        )}

        {/* ── AGENTS TAB ── */}
        {tab === 'agents' && (
          <>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h1 className="text-2xl font-bold mb-1">Hospital Agents</h1>
                  <p className="text-sm text-muted-foreground">{ALL_AGENTS.length} agents across 13 departments · {AGENTS_ONLINE} online</p>
                </div>
                <Badge variant="outline" className="text-xs border-white/15 text-muted-foreground">
                  {filteredAgents.length} shown
                </Badge>
              </div>

              {/* Department pills */}
              <div className="flex flex-wrap gap-2 mb-4">
                <button onClick={() => { setDeptFilter('all'); setAgentPage(0); }}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${deptFilter === 'all' ? 'bg-primary/15 text-primary border-primary/30' : 'border-white/10 text-muted-foreground hover:border-white/20 hover:text-foreground'}`}>
                  All ({ALL_AGENTS.length})
                </button>
                {DEPARTMENTS.map(dept => {
                  const Icon = dept.icon;
                  return (
                    <button key={dept.id} onClick={() => { setDeptFilter(dept.id); setAgentPage(0); }}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${deptFilter === dept.id ? `${dept.bg} ${dept.color} ${dept.border}` : 'border-white/10 text-muted-foreground hover:border-white/20 hover:text-foreground'}`}>
                      <Icon className="w-3 h-3" /> {dept.label} ({dept.count})
                    </button>
                  );
                })}
              </div>

              {/* Search */}
              <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input value={searchQuery} onChange={e => { setSearchQuery(e.target.value); setAgentPage(0); }}
                  placeholder="Search agent ID, type, floor…"
                  className="pl-9 h-9 bg-secondary/50 border-white/10 text-sm" />
              </div>
            </motion.div>

            <div className="glass-card overflow-hidden mb-4">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Agent ID</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Department</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden md:table-cell">Floor</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Status</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Decisions/24h</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Blocked</th>
                      <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[100px]">Block Rate</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden lg:table-cell">Risk</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden lg:table-cell">Last Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedAgents.map((agent, i) => {
                      const dept = DEPARTMENTS.find(d => d.id === agent.department);
                      const DeptIcon = dept?.icon ?? Activity;
                      return (
                        <motion.tr key={agent.id}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.02 }}
                          className="border-b border-white/5 hover:bg-white/[0.03] transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className={`w-6 h-6 rounded-md flex items-center justify-center ${dept?.bg ?? 'bg-white/5'} shrink-0`}>
                                <DeptIcon className={`w-3 h-3 ${dept?.color ?? 'text-muted-foreground'}`} />
                              </div>
                              <span className="font-mono text-xs text-foreground/90">{agent.id}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground">{agent.type}</td>
                          <td className="px-4 py-3 text-xs text-muted-foreground hidden md:table-cell">{agent.floor}</td>
                          <td className="px-4 py-3">
                            <Badge className={`text-[10px] font-semibold ${
                              agent.status === 'active' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                              agent.status === 'alert'  ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                              'bg-white/5 text-muted-foreground border-white/10'
                            }`}>
                              {agent.status === 'active' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1 inline-block" />}
                              {agent.status === 'alert'  && <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse mr-1 inline-block" />}
                              {agent.status}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums text-xs">{agent.decisions24h.toLocaleString()}</td>
                          <td className="px-4 py-3 text-right">
                            <span className="inline-flex items-center gap-1 tabular-nums text-xs">
                              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                              <span className="text-red-400">{agent.blocked24h}</span>
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden min-w-[60px]">
                                <div className={`h-full rounded-full transition-all ${
                                  agent.blockRate >= 25 ? 'bg-red-400/80' : agent.blockRate >= 12 ? 'bg-amber-400/80' : 'bg-primary/70'
                                }`} style={{ width: `${Math.min(100, agent.blockRate)}%` }} />
                              </div>
                              <span className="text-xs tabular-nums text-muted-foreground w-7 text-right">{agent.blockRate}%</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 hidden lg:table-cell"><RiskBadge level={agent.riskLevel} /></td>
                          <td className="px-4 py-3 text-right text-xs text-muted-foreground hidden lg:table-cell">{relTime(agent.lastActiveMin)}</td>
                        </motion.tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Showing {agentPage * AGENTS_PER_PAGE + 1}–{Math.min((agentPage + 1) * AGENTS_PER_PAGE, filteredAgents.length)} of {filteredAgents.length} agents
              </span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setAgentPage(p => Math.max(0, p - 1))}
                  disabled={agentPage === 0} className="h-7 px-3 text-xs border-white/10">
                  ← Prev
                </Button>
                <span className="text-xs text-muted-foreground px-1">{agentPage + 1} / {totalPages}</span>
                <Button variant="outline" size="sm" onClick={() => setAgentPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={agentPage >= totalPages - 1} className="h-7 px-3 text-xs border-white/10">
                  Next →
                </Button>
              </div>
            </div>
          </>
        )}

        {/* ── AUDIT TAB ── */}
        {tab === 'audit' && (
          <>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h1 className="text-2xl font-bold mb-1">Audit Trail</h1>
                  <p className="text-sm text-muted-foreground">SHA-256 hash chain · tamper-evident · HIPAA-compliant immutable log</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 gap-1 text-xs">
                    <CheckCircle2 className="w-3 h-3" /> Chain Verified
                  </Badge>
                  <Button variant="outline" size="sm" className="h-8 px-3 text-xs border-white/10 text-muted-foreground gap-1.5">
                    <FileText className="w-3 h-3" /> Export
                  </Button>
                </div>
              </div>
            </motion.div>

            <div className="glass-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      {['Time', 'Verdict', 'Agent', 'Department', 'Tool.Op', 'Patient', 'Reason', 'Risk', 'Chain Hash'].map(h => (
                        <th key={h} className="text-left px-3 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map(e => {
                      const dept = DEPARTMENTS.find(d => d.id === e.department);
                      const DeptIcon = dept?.icon ?? Activity;
                      return (
                        <tr key={e.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                          <td className="px-3 py-2.5 font-mono text-[10px] text-muted-foreground/60 whitespace-nowrap">{formatTime(e.ts)}</td>
                          <td className="px-3 py-2.5"><VerdictBadge verdict={e.verdict} /></td>
                          <td className="px-3 py-2.5 font-mono text-xs text-foreground/70">{e.agent}</td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1.5">
                              <DeptIcon className={`w-3 h-3 ${dept?.color}`} />
                              <span className="text-xs text-muted-foreground">{dept?.label}</span>
                            </div>
                          </td>
                          <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{e.toolOp}</td>
                          <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground/60">{e.patientId}</td>
                          <td className="px-3 py-2.5">
                            {e.reasonCode
                              ? <span className="text-amber-400 text-xs font-medium">{REASON_LABELS[e.reasonCode] ?? e.reasonCode}</span>
                              : <span className="text-muted-foreground/30">—</span>}
                          </td>
                          <td className="px-3 py-2.5">
                            <span className={`text-xs font-mono font-bold ${e.riskScore < 30 ? 'text-emerald-400' : e.riskScore < 60 ? 'text-amber-400' : 'text-red-400'}`}>
                              {e.riskScore}
                            </span>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1.5">
                              <Hash className="w-3 h-3 text-muted-foreground/30 shrink-0" />
                              <span className="font-mono text-[10px] text-muted-foreground/40 max-w-[140px] truncate">{e.hash}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {/* ── POLICIES TAB ── */}
        {tab === 'policies' && (
          <>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
              <h1 className="text-2xl font-bold mb-1">Policy Packs</h1>
              <p className="text-sm text-muted-foreground">Healthcare compliance policies governing all 500 agents at St. Mercy Health System</p>
            </motion.div>

            {/* Tool permissions */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
              {[
                {
                  title: 'Allowed Operations', icon: CheckCircle2, color: 'text-emerald-400',
                  border: 'border-emerald-500/20', bg: 'bg-emerald-500/5',
                  items: ALLOWED_OPS,
                },
                {
                  title: 'Blocked Operations', icon: Ban, color: 'text-red-400',
                  border: 'border-red-500/20', bg: 'bg-red-500/5',
                  items: BLOCKED_OPS,
                },
                {
                  title: 'Physician Confirm Required', icon: AlertTriangle, color: 'text-amber-400',
                  border: 'border-amber-500/20', bg: 'bg-amber-500/5',
                  items: ESCALATE_OPS,
                },
              ].map(({ title, icon: Icon, color, border, bg, items }) => (
                <div key={title} className={`glass-card p-5 ${border} ${bg}`}>
                  <div className="flex items-center gap-2 mb-4">
                    <Icon className={`w-4 h-4 ${color}`} />
                    <h3 className={`text-sm font-semibold ${color}`}>{title}</h3>
                  </div>
                  <div className="space-y-1.5">
                    {items.map(op => (
                      <div key={op} className="flex items-center gap-2">
                        <span className={`w-1 h-1 rounded-full ${color.replace('text-', 'bg-')}/60 shrink-0`} />
                        <span className="font-mono text-[11px] text-foreground/60">{op}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Policy packs grid */}
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">Available Policy Packs</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                {
                  name: 'Clinical Safety Mode', badge: 'ACTIVE', badgeClass: 'bg-primary/15 text-primary border-primary/25',
                  icon: <Shield className="w-5 h-5 text-primary" />, borderClass: 'border-primary/25',
                  desc: 'HIPAA + FDA AI/ML SaMD compliance. All medication overrides and diagnoses require physician confirmation. Audit chain enforced.',
                  tags: ['HIPAA', 'FDA SaMD', 'SOC 2'],
                },
                {
                  name: 'Emergency Override Mode', badge: 'AVAILABLE', badgeClass: 'bg-white/5 text-muted-foreground border-white/10',
                  icon: <AlertCircle className="w-5 h-5 text-orange-400" />, borderClass: 'border-white/10',
                  desc: 'Expands agent permissions during declared emergencies. All overrides logged and flagged for post-incident review.',
                  tags: ['Emergency', 'Audit Required'],
                },
                {
                  name: 'Research Mode', badge: 'AVAILABLE', badgeClass: 'bg-white/5 text-muted-foreground border-white/10',
                  icon: <Microscope className="w-5 h-5 text-cyan-400" />, borderClass: 'border-white/10',
                  desc: 'IRB-compliant research operations. Anonymized data access only. De-identification enforced before export.',
                  tags: ['IRB', 'De-identification'],
                },
                {
                  name: 'Pharmacy Strict Mode', badge: 'AVAILABLE', badgeClass: 'bg-white/5 text-muted-foreground border-white/10',
                  icon: <Pill className="w-5 h-5 text-amber-400" />, borderClass: 'border-white/10',
                  desc: 'All controlled substance dispensing requires dual-pharmacist verification. DEA schedule tracking enforced.',
                  tags: ['DEA', 'Dual Verify'],
                },
                {
                  name: 'Surgical Robotics Mode', badge: 'AVAILABLE', badgeClass: 'bg-white/5 text-muted-foreground border-white/10',
                  icon: <Cross className="w-5 h-5 text-purple-400" />, borderClass: 'border-white/10',
                  desc: 'ISO 13485 surgical robot governance. All actuator commands validated against pre-approved surgical protocol.',
                  tags: ['ISO 13485', 'Protocol Gate'],
                },
                {
                  name: 'Lockdown Mode', badge: 'EMERGENCY', badgeClass: 'bg-red-500/10 text-red-400 border-red-500/25',
                  icon: <Lock className="w-5 h-5 text-red-400" />, borderClass: 'border-red-500/20',
                  desc: 'Full freeze — all autonomous agent actions suspended. Triggers hospital incident response protocol and mandatory audit.',
                  tags: ['Full Freeze', 'Incident Response'],
                },
              ].map(pack => (
                <div key={pack.name} className={`glass-card p-5 ${pack.borderClass}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-white/5 border border-white/10">
                      {pack.icon}
                    </div>
                    <Badge className={`text-[10px] font-bold ${pack.badgeClass}`}>{pack.badge}</Badge>
                  </div>
                  <h4 className="text-sm font-bold text-foreground/85 mb-2">{pack.name}</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-3">{pack.desc}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {pack.tags.map(tag => (
                      <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 bg-white/5 text-muted-foreground font-medium">{tag}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </main>

      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
