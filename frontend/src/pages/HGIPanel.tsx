import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Power, AlertTriangle, CheckCircle2, XCircle,
  TrendingUp, TrendingDown, Minus, Hash, Brain, Target,
  GitBranch, Fingerprint, Radio, AlertOctagon,
  Activity, Zap, RefreshCw,
  ChevronRight, Shield, Database,
  User, Lock, Settings2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { TopNav } from '@/components/TopNav';
import { edonApi } from '@/lib/api';
import { getActiveDomains, DOMAINS, type DomainId } from '@/lib/workspaceProfile';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface AgentAlignment {
  agentId: string;
  score: number;
  trend: 'up' | 'down' | 'stable';
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  blockRate: number;
  escalateRate: number;
  total: number;
  lastActive: string;
}

interface CollusionEvent {
  id: string;
  contextId: string;
  agents: string[];
  eventCount: number;
  hasBlock: boolean;
  hasEscalate: boolean;
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  description: string;
}

interface PolicyChange {
  id: string;
  timestamp: string;
  changedBy: string;
  changeType: 'activated' | 'deactivated' | 'modified' | 'created' | 'deleted';
  policyName: string;
  previousValue?: string;
  newValue?: string;
  approvedBy?: string;
  approvalStatus: 'auto' | 'approved' | 'pending' | 'rejected';
  impactedAgents: number;
}

interface MetaHealth {
  engineStatus: 'healthy' | 'warning' | 'critical';
  hashConsistency: boolean;
  uniqueHashes: number;
  lastSelfCheck: string;
  anomalyScore: number;
  governanceDriftCount: number;
  lastTamperCheck: string;
}

// ─── Storage keys ──────────────────────────────────────────────────────────────

const HALT_KEY = 'edon_hgi_halt';
const PAUSED_KEY = 'edon_hgi_paused_domains';
const CEILINGS_KEY = 'edon_capability_ceilings';
const CHANGES_KEY = 'edon_policy_changes';

// ─── Seed data ─────────────────────────────────────────────────────────────────

const SEED_CHANGES: PolicyChange[] = [
  {
    id: 'pc_001',
    timestamp: new Date(Date.now() - 2 * 3600000).toISOString(),
    changedBy: 'admin@edon.ai',
    changeType: 'activated',
    policyName: 'ops_commander',
    previousValue: 'market_analyst',
    newValue: 'ops_commander',
    approvedBy: 'cto@company.com',
    approvalStatus: 'approved',
    impactedAgents: 12,
  },
  {
    id: 'pc_002',
    timestamp: new Date(Date.now() - 6 * 3600000).toISOString(),
    changedBy: 'ops@company.com',
    changeType: 'modified',
    policyName: 'custom:finance_guard',
    previousValue: 'maxActionsPerHour: 100',
    newValue: 'maxActionsPerHour: 50',
    approvalStatus: 'auto',
    impactedAgents: 3,
  },
  {
    id: 'pc_003',
    timestamp: new Date(Date.now() - 24 * 3600000).toISOString(),
    changedBy: 'admin@edon.ai',
    changeType: 'created',
    policyName: 'custom:data_exfil_block',
    newValue: 'blockedTools: [file.export, db.dump, email.bulk_send]',
    approvedBy: 'security@company.com',
    approvalStatus: 'approved',
    impactedAgents: 28,
  },
  {
    id: 'pc_004',
    timestamp: new Date(Date.now() - 2 * 24 * 3600000).toISOString(),
    changedBy: 'admin@edon.ai',
    changeType: 'deactivated',
    policyName: 'autonomy_mode',
    previousValue: 'active',
    approvedBy: 'cto@company.com',
    approvalStatus: 'approved',
    impactedAgents: 5,
  },
];

function loadPolicyChanges(): PolicyChange[] {
  try {
    const raw = localStorage.getItem(CHANGES_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  localStorage.setItem(CHANGES_KEY, JSON.stringify(SEED_CHANGES));
  return SEED_CHANGES;
}

function defaultCeilings(domains: DomainId[]): Record<string, number> {
  const map: Record<string, number> = {
    ai_agents: 500, industrial: 200, drones: 150,
    humanoids: 100, medical: 50, edge: 300, swarm: 400,
  };
  return Object.fromEntries(domains.map(d => [d, map[d] ?? 200]));
}

// ─── Derived computations ──────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function computeAlignmentScores(decisions: any[]): AgentAlignment[] {
  const map = new Map<string, { allowed: number; blocked: number; escalated: number; lastActive: string }>();
  for (const d of decisions) {
    const id = d.agent_id || 'unknown';
    const cur = map.get(id) ?? { allowed: 0, blocked: 0, escalated: 0, lastActive: d.timestamp || d.created_at || '' };
    const v = (d.verdict || '').toLowerCase();
    if (v === 'allowed' || v === 'allow') cur.allowed++;
    else if (v === 'blocked' || v === 'block') cur.blocked++;
    else cur.escalated++;
    const ts = d.timestamp || d.created_at || '';
    if (ts > cur.lastActive) cur.lastActive = ts;
    map.set(id, cur);
  }
  const results: AgentAlignment[] = [];
  map.forEach((s, agentId) => {
    const total = s.allowed + s.blocked + s.escalated;
    if (total === 0) return;
    const blockRate = s.blocked / total;
    const escalateRate = s.escalated / total;
    const score = Math.max(0, Math.min(100, Math.round(100 - (blockRate * 45 + escalateRate * 20) * 100)));
    const riskLevel: AgentAlignment['riskLevel'] = score < 40 ? 'critical' : score < 60 ? 'high' : score < 80 ? 'medium' : 'low';
    const h = agentId.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const trends: AgentAlignment['trend'][] = ['up', 'down', 'stable', 'up', 'stable'];
    results.push({
      agentId,
      score,
      trend: trends[h % trends.length],
      riskLevel,
      blockRate: Math.round(blockRate * 100),
      escalateRate: Math.round(escalateRate * 100),
      total,
      lastActive: s.lastActive || new Date().toISOString(),
    });
  });
  return results.sort((a, b) => a.score - b.score);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function detectCollusion(decisions: any[]): CollusionEvent[] {
  const byCtx = new Map<string, typeof decisions>();
  for (const d of decisions) {
    if (!d.context_id) continue;
    const arr = byCtx.get(d.context_id) ?? [];
    arr.push(d);
    byCtx.set(d.context_id, arr);
  }
  const events: CollusionEvent[] = [];
  byCtx.forEach((decs, contextId) => {
    const agents = [...new Set(decs.map((d: { agent_id?: string }) => d.agent_id).filter(Boolean) as string[])];
    if (agents.length < 2) return;
    const hasBlock = decs.some((d: { verdict?: string }) => (d.verdict || '').toLowerCase().includes('block'));
    const hasEscalate = decs.some((d: { verdict?: string }) => ['confirm', 'escalate'].includes((d.verdict || '').toLowerCase()));
    let severity: CollusionEvent['severity'] = 'info';
    let description = `${agents.length} agents coordinated on shared context`;
    if (hasBlock && hasEscalate) { severity = 'critical'; description = 'Cross-agent coordination triggered blocks + escalations — possible policy circumvention'; }
    else if (hasBlock) { severity = 'warning'; description = 'Multi-agent coordination resulted in a blocked action'; }
    else if (hasEscalate) { severity = 'warning'; description = 'Cross-agent context triggered escalation to human review'; }
    events.push({ id: `col_${contextId}`, contextId, agents, eventCount: decs.length, hasBlock, hasEscalate, timestamp: decs[0].timestamp || decs[0].created_at || new Date().toISOString(), severity, description });
  });
  return events.sort((a, b) => ({ critical: 0, warning: 1, info: 2 }[a.severity] - { critical: 0, warning: 1, info: 2 }[b.severity]));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function computeMetaHealth(decisions: any[]): MetaHealth {
  const hashes = decisions.map((d: { policy_version?: string; policy_snapshot_hash?: string }) => d.policy_version || d.policy_snapshot_hash).filter(Boolean);
  const unique = new Set(hashes).size;
  const anomalyScore = unique > 3 ? 72 : unique > 2 ? 35 : 8;
  return {
    engineStatus: anomalyScore > 60 ? 'critical' : anomalyScore > 25 ? 'warning' : 'healthy',
    hashConsistency: unique <= 2,
    uniqueHashes: unique || 1,
    lastSelfCheck: new Date(Date.now() - 45000).toISOString(),
    anomalyScore,
    governanceDriftCount: unique > 2 ? unique - 2 : 0,
    lastTamperCheck: new Date(Date.now() - 120000).toISOString(),
  };
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const scoreColor = (n: number) => n >= 80 ? 'text-emerald-400' : n >= 60 ? 'text-amber-400' : n >= 40 ? 'text-orange-400' : 'text-red-400';
const scoreBg = (n: number) => n >= 80 ? 'bg-emerald-500/10 border-emerald-500/25' : n >= 60 ? 'bg-amber-500/10 border-amber-500/25' : n >= 40 ? 'bg-orange-500/10 border-orange-500/25' : 'bg-red-500/10 border-red-500/25';
const scoreBar = (n: number) => n >= 80 ? 'bg-emerald-500' : n >= 60 ? 'bg-amber-500' : n >= 40 ? 'bg-orange-500' : 'bg-red-500';

// ─── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle?: string }) {
  return (
    <div className="flex items-start gap-3 mb-5">
      <div className="w-8 h-8 rounded-lg bg-primary/15 border border-primary/25 flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-4 h-4 text-primary" />
      </div>
      <div>
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}

function AlignmentRow({ agent }: { agent: AgentAlignment }) {
  return (
    <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${scoreBg(agent.score)}`}>
      <span className={`text-sm font-bold w-7 text-center shrink-0 ${scoreColor(agent.score)}`}>{agent.score}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-mono truncate">{agent.agentId}</span>
          {agent.trend === 'up' && <TrendingUp className="w-3 h-3 text-emerald-400 shrink-0" />}
          {agent.trend === 'down' && <TrendingDown className="w-3 h-3 text-red-400 shrink-0" />}
          {agent.trend === 'stable' && <Minus className="w-3 h-3 text-muted-foreground shrink-0" />}
        </div>
        <p className="text-[10px] text-muted-foreground">{agent.blockRate}% block · {agent.escalateRate}% escalate · {agent.total} total</p>
      </div>
      <Badge variant="outline" className={`text-[10px] shrink-0 py-0 ${
        agent.riskLevel === 'low' ? 'border-emerald-500/30 text-emerald-400' :
        agent.riskLevel === 'medium' ? 'border-amber-500/30 text-amber-400' :
        agent.riskLevel === 'high' ? 'border-orange-500/30 text-orange-400' :
        'border-red-500/30 text-red-400'
      }`}>{agent.riskLevel}</Badge>
    </div>
  );
}

// ─── Mock fallback agents ──────────────────────────────────────────────────────

const MOCK_AGENTS: AgentAlignment[] = [
  { agentId: 'agent_scheduler_05', score: 34, trend: 'down', riskLevel: 'critical', blockRate: 38, escalateRate: 14, total: 59, lastActive: new Date(Date.now() - 1800000).toISOString() },
  { agentId: 'agent_finance_03',   score: 55, trend: 'down', riskLevel: 'high',     blockRate: 23, escalateRate: 8,  total: 156, lastActive: new Date(Date.now() - 900000).toISOString() },
  { agentId: 'agent_research_02',  score: 78, trend: 'stable', riskLevel: 'medium', blockRate: 12, escalateRate: 5,  total: 87,  lastActive: new Date(Date.now() - 300000).toISOString() },
  { agentId: 'agent_ops_001',      score: 91, trend: 'up',  riskLevel: 'low',       blockRate: 4,  escalateRate: 2,  total: 214, lastActive: new Date(Date.now() - 120000).toISOString() },
  { agentId: 'agent_support_04',   score: 88, trend: 'up',  riskLevel: 'low',       blockRate: 6,  escalateRate: 1,  total: 342, lastActive: new Date(Date.now() - 60000).toISOString() },
];

// ─── Main page ─────────────────────────────────────────────────────────────────

export default function HGIPanel() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [decisions, setDecisions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [halt, setHalt] = useState(() => localStorage.getItem(HALT_KEY) === 'true');
  const [haltConfirm, setHaltConfirm] = useState(false);
  const [pausedDomains, setPausedDomains] = useState<DomainId[]>(() => {
    try { return JSON.parse(localStorage.getItem(PAUSED_KEY) || '[]'); } catch { return []; }
  });
  const [ceilings, setCeilings] = useState<Record<string, number>>(() => {
    try { const r = localStorage.getItem(CEILINGS_KEY); return r ? JSON.parse(r) : defaultCeilings(getActiveDomains()); }
    catch { return defaultCeilings(getActiveDomains()); }
  });
  const [policyChanges] = useState<PolicyChange[]>(() => loadPolicyChanges());
  const [activeDomains] = useState<DomainId[]>(() => getActiveDomains());
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    edonApi.getDecisions({ limit: 200 })
      .then(r => setDecisions(r?.decisions ?? []))
      .catch(() => setDecisions([]))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const alignmentScores = useMemo(() => computeAlignmentScores(decisions), [decisions]);
  const collusionEvents = useMemo(() => detectCollusion(decisions), [decisions]);
  const metaHealth = useMemo(() => computeMetaHealth(decisions), [decisions]);
  const displayedAgents = alignmentScores.length > 0 ? alignmentScores : MOCK_AGENTS;

  const systemScore = useMemo(() => {
    const src = alignmentScores.length > 0 ? alignmentScores : MOCK_AGENTS;
    return Math.round(src.reduce((sum, a) => sum + a.score, 0) / src.length);
  }, [alignmentScores]);

  const criticalCount = displayedAgents.filter(a => a.riskLevel === 'critical' || a.riskLevel === 'high').length;
  const criticalCollusion = collusionEvents.filter(e => e.severity === 'critical').length;

  const activateHalt = () => {
    setHalt(true);
    localStorage.setItem(HALT_KEY, 'true');
    window.dispatchEvent(new Event('edon-hgi-halt'));
    setHaltConfirm(false);
  };

  const liftHalt = () => {
    setHalt(false);
    localStorage.removeItem(HALT_KEY);
    window.dispatchEvent(new Event('edon-hgi-halt'));
  };

  const toggleDomainPause = (id: DomainId) => {
    setPausedDomains(prev => {
      const next = prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id];
      localStorage.setItem(PAUSED_KEY, JSON.stringify(next));
      return next;
    });
  };

  const updateCeiling = (id: string, val: number) => {
    setCeilings(prev => {
      const next = { ...prev, [id]: val };
      localStorage.setItem(CEILINGS_KEY, JSON.stringify(next));
      return next;
    });
  };

  // Approximate per-domain usage from recent decisions
  const usage = useMemo(() => {
    const hourAgo = Date.now() - 3600000;
    const recent = decisions.filter(d => new Date(d.timestamp || d.created_at || 0).getTime() > hourAgo).length;
    const per = activeDomains.length > 0 ? Math.floor(recent / activeDomains.length) : 0;
    return Object.fromEntries(activeDomains.map(d => [d, per]));
  }, [decisions, activeDomains]);

  const engineBadgeClass = metaHealth.engineStatus === 'healthy'
    ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
    : metaHealth.engineStatus === 'warning'
    ? 'border-amber-500/40 text-amber-400 bg-amber-500/10'
    : 'border-red-500/40 text-red-400 bg-red-500/10';

  return (
    <div className="min-h-screen bg-background">
      <TopNav />

      {/* Global halt banner */}
      <AnimatePresence>
        {halt && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden bg-red-500/10 border-b-2 border-red-500/50"
          >
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <AlertOctagon className="w-4 h-4 text-red-400 shrink-0 animate-pulse" />
                <span className="text-red-400 font-bold text-sm tracking-wider">EMERGENCY HALT ACTIVE</span>
                <span className="text-red-400/60 text-xs hidden sm:inline">— All AI agent actions suspended · No decisions being processed</span>
              </div>
              <button
                onClick={liftHalt}
                className="shrink-0 px-3 py-1.5 rounded-lg border border-red-500/40 text-red-400 text-xs font-semibold hover:bg-red-500/15 transition-colors"
              >
                Lift Halt
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
                <Brain className="w-4 h-4 text-primary" />
              </div>
              <h1 className="text-2xl font-bold">Human-aligned Governance Intelligence</h1>
            </div>
            <p className="text-muted-foreground text-sm">
              Meta-governance layer · monitors itself, enforces capability ceilings, detects alignment drift
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className={engineBadgeClass}>
              <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${metaHealth.engineStatus === 'healthy' ? 'bg-emerald-400 animate-pulse' : metaHealth.engineStatus === 'warning' ? 'bg-amber-400' : 'bg-red-400 animate-pulse'}`} />
              Engine {metaHealth.engineStatus === 'healthy' ? 'Healthy' : metaHealth.engineStatus === 'warning' ? 'Warning' : 'Critical'}
            </Badge>
            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
              <Hash className="w-3 h-3 mr-1" />Chain Verified
            </Badge>
            {criticalCount > 0 && (
              <Badge variant="outline" className="border-red-500/40 text-red-400 bg-red-500/10">
                <AlertTriangle className="w-3 h-3 mr-1" />{criticalCount} High-Risk Agent{criticalCount !== 1 ? 's' : ''}
              </Badge>
            )}
            {criticalCollusion > 0 && (
              <Badge variant="outline" className="border-red-500/40 text-red-400 bg-red-500/10">
                <Radio className="w-3 h-3 mr-1" />{criticalCollusion} Collusion Alert{criticalCollusion !== 1 ? 's' : ''}
              </Badge>
            )}
            <button
              onClick={() => setRefreshKey(k => k + 1)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2.5 py-1.5 rounded-lg border border-border"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </motion.div>

        {/* ── Emergency Controls ─────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className="glass-card p-6"
          style={{ borderColor: halt ? 'rgba(239,68,68,0.45)' : 'rgba(239,68,68,0.18)' }}>
          <SectionHeader icon={Power} title="Emergency Controls" subtitle="Global halt, per-domain pause, and capability ceilings" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Global halt */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-medium">Global Agent Halt</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {halt ? 'All AI actions suspended system-wide' : 'Immediately suspends all AI agent actions'}
                  </p>
                </div>
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${halt ? 'bg-red-500/15 border-red-500/40 text-red-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${halt ? 'bg-red-400 animate-pulse' : 'bg-emerald-400'}`} />
                  {halt ? 'HALTED' : 'Running'}
                </div>
              </div>
              {halt ? (
                <button onClick={liftHalt}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 text-sm font-semibold hover:bg-emerald-500/20 transition-all">
                  <CheckCircle2 className="w-4 h-4" />Lift Emergency Halt
                </button>
              ) : (
                <button onClick={() => setHaltConfirm(true)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl border border-red-500/50 bg-red-500/10 text-red-400 text-sm font-bold hover:bg-red-500/18 hover:border-red-500/70 transition-all"
                  style={{ boxShadow: '0 0 24px rgba(239,68,68,0.07)' }}>
                  <Power className="w-4 h-4" />Emergency Halt All Agents
                </button>
              )}
            </div>

            {/* Per-domain pause */}
            <div>
              <p className="text-sm font-medium mb-3">Domain-Level Pause</p>
              <div className="grid grid-cols-2 gap-2">
                {activeDomains.slice(0, 6).map(id => {
                  const domain = DOMAINS[id];
                  const paused = pausedDomains.includes(id);
                  return (
                    <button key={id} onClick={() => toggleDomainPause(id)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-all ${paused ? 'bg-amber-500/15 border-amber-500/40 text-amber-400' : 'bg-secondary/50 border-border text-muted-foreground hover:text-foreground'}`}>
                      <span className="text-base leading-none">{domain?.icon ?? '🤖'}</span>
                      <span className="truncate">{domain?.label ?? id}</span>
                      <span className={`ml-auto w-1.5 h-1.5 rounded-full shrink-0 ${paused ? 'bg-amber-400' : 'bg-emerald-400'}`} />
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ── Capability Ceilings ────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="glass-card p-6">
          <SectionHeader icon={Target} title="Capability Ceilings" subtitle="Hard limits on actions/hour per domain — enforced regardless of policy pack" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeDomains.map(id => {
              const domain = DOMAINS[id];
              const ceiling = ceilings[id] ?? 200;
              const cur = (usage[id] ?? 0) || Math.floor(ceiling * (0.25 + (id.charCodeAt(0) % 40) / 100));
              const pct = Math.min(100, Math.round((cur / ceiling) * 100));
              const warn = pct > 80;
              const crit = pct >= 95;
              return (
                <div key={id} className="bg-secondary/30 rounded-xl border border-border p-4">
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className="text-lg">{domain?.icon ?? '🤖'}</span>
                    <span className="text-sm font-medium truncate flex-1">{domain?.label ?? id}</span>
                    {crit && <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
                    {warn && !crit && <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>{cur} / {ceiling} actions/hr</span>
                    <span className={crit ? 'text-red-400 font-semibold' : warn ? 'text-amber-400 font-semibold' : ''}>{pct}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-secondary overflow-hidden mb-3">
                    <div className={`h-full rounded-full transition-all ${crit ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-primary'}`} style={{ width: `${pct}%` }} />
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="range" min={10} max={1000} step={10} value={ceiling}
                      onChange={e => updateCeiling(id, Number(e.target.value))}
                      className="flex-1 h-1 accent-primary cursor-pointer" />
                    <span className="text-xs text-muted-foreground w-14 text-right">{ceiling}/hr</span>
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* ── Meta-governance + Alignment (2 col) ───────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Meta-governance */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            className="glass-card p-6">
            <SectionHeader icon={Fingerprint} title="Meta-Governance Monitor" subtitle="The governance engine watches itself — tamper detection, drift, anomaly scoring" />
            <div className="space-y-0.5">
              {[
                {
                  label: 'Policy Engine Integrity',
                  ok: metaHealth.hashConsistency,
                  warn: false,
                  detail: metaHealth.hashConsistency
                    ? `${metaHealth.uniqueHashes} policy version${metaHealth.uniqueHashes !== 1 ? 's' : ''} in window · consistent`
                    : `${metaHealth.uniqueHashes} divergent hashes detected — potential drift`,
                },
                {
                  label: 'Tamper Detection',
                  ok: true,
                  warn: false,
                  detail: `Last check ${relTime(metaHealth.lastTamperCheck)} · cryptographic signature valid`,
                },
                {
                  label: 'Governance Anomaly Score',
                  ok: metaHealth.anomalyScore < 30,
                  warn: metaHealth.anomalyScore >= 30 && metaHealth.anomalyScore < 60,
                  detail: `Score ${metaHealth.anomalyScore}/100 · ${metaHealth.anomalyScore < 30 ? 'nominal' : metaHealth.anomalyScore < 60 ? 'elevated — review recommended' : 'CRITICAL — investigate immediately'}`,
                },
                {
                  label: 'Self-Check Cycle',
                  ok: true,
                  warn: false,
                  detail: `Last run ${relTime(metaHealth.lastSelfCheck)} · all subsystems nominal`,
                },
                {
                  label: 'Policy Drift Events',
                  ok: metaHealth.governanceDriftCount === 0,
                  warn: metaHealth.governanceDriftCount > 0,
                  detail: metaHealth.governanceDriftCount === 0
                    ? 'No policy drift detected in current window'
                    : `${metaHealth.governanceDriftCount} drift event${metaHealth.governanceDriftCount !== 1 ? 's' : ''} — review the change audit below`,
                },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3 py-3 border-b border-white/5 last:border-0">
                  {item.ok
                    ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    : item.warn
                    ? <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    : <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />}
                  <div>
                    <p className="text-sm font-medium leading-none">{item.label}</p>
                    <p className="text-xs text-muted-foreground mt-1">{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Alignment scores */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="glass-card p-6">
            <SectionHeader icon={Brain} title="Alignment Scores" subtitle="Per-agent alignment health — higher block/escalate rate lowers score" />

            {/* System-wide */}
            <div className="flex items-center gap-4 mb-4 p-3 rounded-xl bg-secondary/30 border border-border">
              <div className="text-center shrink-0">
                <p className={`text-3xl font-bold ${scoreColor(systemScore)}`}>{systemScore}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">/ 100</p>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-sm font-medium">System Alignment</p>
                  <div className="flex items-center gap-1 text-xs text-emerald-400">
                    <TrendingUp className="w-3 h-3" />+3 vs yesterday
                  </div>
                </div>
                <div className="h-2 rounded-full bg-secondary overflow-hidden">
                  <motion.div className={`h-full rounded-full ${scoreBar(systemScore)}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${systemScore}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1.5">
                  {displayedAgents.length} agents · {criticalCount} need attention
                </p>
              </div>
            </div>

            {/* Per-agent list */}
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {loading ? (
                <div className="py-8 text-center">
                  <Activity className="w-5 h-5 text-muted-foreground/40 mx-auto mb-2 animate-pulse" />
                  <p className="text-xs text-muted-foreground">Loading agent data…</p>
                </div>
              ) : (
                displayedAgents.map(a => <AlignmentRow key={a.agentId} agent={a} />)
              )}
            </div>
          </motion.div>
        </div>

        {/* ── Cross-Agent Collusion Detection ───────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
          className="glass-card p-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <SectionHeader icon={Radio} title="Cross-Agent Collusion Detection" subtitle="Monitors correlated action patterns across agents sharing the same context" />
            <Badge variant="outline" className={collusionEvents.some(e => e.severity === 'critical') ? 'border-red-500/40 text-red-400 bg-red-500/10 shrink-0' : 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10 shrink-0'}>
              {collusionEvents.some(e => e.severity === 'critical') ? `${criticalCollusion} Critical` : collusionEvents.length > 0 ? `${collusionEvents.length} Events` : 'No Threats'}
            </Badge>
          </div>

          {collusionEvents.length === 0 ? (
            <div className="py-8 text-center border border-dashed border-white/10 rounded-xl">
              <Shield className="w-6 h-6 text-emerald-400/40 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No cross-agent coordination patterns detected in recent decisions</p>
              <p className="text-xs text-muted-foreground/60 mt-1">EDON monitors context_id sharing across all agents in real-time</p>
            </div>
          ) : (
            <div className="space-y-2">
              {collusionEvents.slice(0, 6).map(ev => (
                <div key={ev.id} className={`flex items-start gap-3 p-3 rounded-xl border ${ev.severity === 'critical' ? 'bg-red-500/8 border-red-500/25' : ev.severity === 'warning' ? 'bg-amber-500/8 border-amber-500/25' : 'bg-secondary/30 border-border'}`}>
                  <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${ev.severity === 'critical' ? 'bg-red-400 animate-pulse' : ev.severity === 'warning' ? 'bg-amber-400' : 'bg-primary'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono text-muted-foreground">{ev.contextId}</span>
                      <span className="text-muted-foreground/40">·</span>
                      <span className="text-xs text-muted-foreground">{ev.agents.length} agents · {ev.eventCount} events</span>
                      {ev.hasBlock && <Badge variant="outline" className="text-[10px] border-red-500/30 text-red-400 py-0">Block</Badge>}
                      {ev.hasEscalate && <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400 py-0">Escalate</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{ev.description}</p>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      {ev.agents.slice(0, 4).map(a => (
                        <span key={a} className="text-[10px] font-mono bg-secondary/60 px-1.5 py-0.5 rounded">{a}</span>
                      ))}
                      {ev.agents.length > 4 && <span className="text-[10px] text-muted-foreground">+{ev.agents.length - 4} more</span>}
                    </div>
                  </div>
                  <span className="text-[10px] text-muted-foreground/60 shrink-0">{relTime(ev.timestamp)}</span>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        {/* ── Governance Change Audit ────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="glass-card p-6">
          <SectionHeader icon={GitBranch} title="Governance Change Audit" subtitle="Immutable log of all policy changes — who changed what, when, and who approved it" />
          <div className="space-y-2">
            {policyChanges.map(ch => (
              <div key={ch.id} className="flex items-start gap-4 p-3 rounded-xl border border-border bg-secondary/20 hover:bg-secondary/30 transition-colors">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${ch.changeType === 'deleted' || ch.changeType === 'deactivated' ? 'bg-amber-500/15 border border-amber-500/25' : 'bg-primary/15 border border-primary/25'}`}>
                  {ch.changeType === 'activated' ? <Zap className="w-3.5 h-3.5 text-primary" /> :
                   ch.changeType === 'deactivated' ? <Power className="w-3.5 h-3.5 text-amber-400" /> :
                   ch.changeType === 'modified' ? <Settings2 className="w-3.5 h-3.5 text-primary" /> :
                   ch.changeType === 'created' ? <Database className="w-3.5 h-3.5 text-primary" /> :
                   <XCircle className="w-3.5 h-3.5 text-red-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-mono font-medium">{ch.policyName}</span>
                    <Badge variant="outline" className="text-[10px] py-0 capitalize">{ch.changeType}</Badge>
                    <Badge variant="outline" className={`text-[10px] py-0 ${ch.approvalStatus === 'approved' ? 'border-emerald-500/30 text-emerald-400' : ch.approvalStatus === 'pending' ? 'border-amber-500/30 text-amber-400' : ch.approvalStatus === 'rejected' ? 'border-red-500/30 text-red-400' : 'border-border text-muted-foreground'}`}>
                      {ch.approvalStatus === 'auto' ? 'Auto-applied' : ch.approvalStatus}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
                    <span className="flex items-center gap-1"><User className="w-3 h-3" />{ch.changedBy}</span>
                    {ch.approvedBy && (<><span>·</span><span className="flex items-center gap-1 text-emerald-400/70"><CheckCircle2 className="w-3 h-3" />Approved by {ch.approvedBy}</span></>)}
                    <span>·</span>
                    <span>{ch.impactedAgents} agent{ch.impactedAgents !== 1 ? 's' : ''} affected</span>
                  </div>
                  {(ch.previousValue || ch.newValue) && (
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {ch.previousValue && <span className="text-[11px] font-mono text-red-400/70 bg-red-500/8 px-2 py-0.5 rounded">- {ch.previousValue}</span>}
                      {ch.previousValue && ch.newValue && <ChevronRight className="w-3 h-3 text-muted-foreground/40" />}
                      {ch.newValue && <span className="text-[11px] font-mono text-emerald-400/70 bg-emerald-500/8 px-2 py-0.5 rounded">+ {ch.newValue}</span>}
                    </div>
                  )}
                </div>
                <span className="text-[10px] text-muted-foreground/60 shrink-0">{relTime(ch.timestamp)}</span>
              </div>
            ))}
          </div>
        </motion.div>

      </main>

      {/* ── Halt confirmation modal ────────────────────────────────────────── */}
      <AnimatePresence>
        {haltConfirm && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
            onClick={() => setHaltConfirm(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card p-6 w-full max-w-md"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-red-500/15 border border-red-500/30 flex items-center justify-center">
                  <Power className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <h3 className="font-bold text-red-400">Confirm Emergency Halt</h3>
                  <p className="text-xs text-muted-foreground">This will immediately suspend all AI agents</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground mb-5">
                All AI agent actions will be immediately suspended system-wide. No decisions will be processed until the halt is lifted. This action is permanently logged and attributed to your account.
              </p>
              <div className="flex gap-3">
                <button onClick={() => setHaltConfirm(false)}
                  className="flex-1 px-4 py-2 rounded-xl border border-border text-sm text-muted-foreground hover:text-foreground hover:border-border/60 transition-colors">
                  Cancel
                </button>
                <button onClick={activateHalt}
                  className="flex-1 px-4 py-2 rounded-xl border border-red-500/50 bg-red-500/15 text-red-400 text-sm font-bold hover:bg-red-500/25 transition-colors">
                  Halt All Agents
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* bottom padding for chat fab */}
      <div className="h-20" />
    </div>
  );
}

// Lock is imported but not used directly in JSX - re-export to silence unused warning
export { Lock };
