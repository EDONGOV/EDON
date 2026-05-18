import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Target,
  RefreshCw,
  AlertTriangle,
  Shield,
  GitBranch,
  Zap,
  ChevronRight,
  Circle,
} from 'lucide-react';
import { edonApi } from '@/lib/api';
import type { ImpactFailureState, ImpactGraphData } from '@/lib/api';

// ─── Vuln class config ────────────────────────────────────────────────────────

const VULN_CLASSES = [
  { key: 'data_exfiltration', label: 'Data Exfil', color: 'bg-red-500/20 text-red-400 border-red-500/30' },
  { key: 'privilege_escalation', label: 'Priv Esc', color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  { key: 'confused_deputy', label: 'Confused Deputy', color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  { key: 'prompt_injection_propagation', label: 'Prompt Inject', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  { key: 'policy_bypass_via_chaining', label: 'Policy Bypass', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  { key: 'unconstrained_credential_access', label: 'Credential Access', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  { key: 'unconstrained_tool_fanout', label: 'Tool Fanout', color: 'bg-violet-500/20 text-violet-400 border-violet-500/30' },
  { key: 'audit_gap', label: 'Audit Gap', color: 'bg-slate-500/20 text-slate-400 border-slate-500/30' },
  { key: 'kill_switch_bypass', label: 'Kill Switch', color: 'bg-rose-500/20 text-rose-400 border-rose-500/30' },
];

function getVulnClass(key: string) {
  return (
    VULN_CLASSES.find((v) => v.key === key) ?? {
      key,
      label: key.replace(/_/g, ' '),
      color: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    }
  );
}

function severityColor(score: number) {
  if (score >= 0.75) return 'bg-red-500';
  if (score >= 0.5) return 'bg-orange-500';
  return 'bg-yellow-500';
}

function severityTextColor(score: number) {
  if (score >= 0.75) return 'text-red-400';
  if (score >= 0.5) return 'text-orange-400';
  return 'text-yellow-400';
}

function statusDotColor(status: string) {
  switch (status) {
    case 'confirmed': return 'bg-red-500';
    case 'probed': return 'bg-orange-400';
    case 'mitigated': return 'bg-emerald-500';
    default: return 'bg-slate-500';
  }
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  sub?: string;
}

function StatCard({ label, value, icon, sub }: StatCardProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-start gap-3">
      <div className="mt-0.5 text-slate-400">{icon}</div>
      <div>
        <div className="text-2xl font-bold text-slate-100">{value}</div>
        <div className="text-xs text-slate-400 mt-0.5">{label}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

// ─── Attack Paths Tab ─────────────────────────────────────────────────────────

interface AttackPathsTabProps {
  selected: ImpactFailureState | null;
}

function AttackPathsTab({ selected }: AttackPathsTabProps) {
  if (!selected) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <GitBranch className="w-8 h-8 opacity-40" />
        <p className="text-sm">Select a failure state from the left panel</p>
      </div>
    );
  }

  const vc = getVulnClass(selected.vulnerability_class);
  const likelihoodPct = ((selected.likelihood_score ?? 0) * 100).toFixed(0);
  const blastPct = ((selected.blast_radius_score ?? 0) * 100).toFixed(0);
  const recov = selected.recoverability_factor ?? 1;
  const compositeRisk = (
    ((selected.likelihood_score ?? 0) * (selected.blast_radius_score ?? 0)) /
    Math.max(recov, 0.01)
  ).toFixed(3);

  const statusScenarios = [
    { label: 'Initial entry vector exploited', status: selected.status !== 'unprobed' ? 'confirmed' : 'pending' },
    { label: 'Lateral movement across path', status: selected.status === 'confirmed' || selected.status === 'probed' ? 'partial' : 'pending' },
    { label: 'Terminal impact reached', status: selected.status === 'confirmed' ? 'confirmed' : 'pending' },
    { label: 'Mitigation applied & verified', status: selected.status === 'mitigated' ? 'confirmed' : 'pending' },
  ];

  const scenarioDot: Record<string, string> = {
    confirmed: 'bg-red-500',
    partial: 'bg-orange-400',
    pending: 'bg-slate-600',
  };
  const scenarioLabel: Record<string, string> = {
    confirmed: 'Confirmed',
    partial: 'Partial',
    pending: 'Pending',
  };

  return (
    <motion.div
      key={selected.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-5"
    >
      {/* Header */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded border ${vc.color}`}>{vc.label}</span>
        <span className={`text-xs font-mono ${severityTextColor(selected.severity_score)}`}>
          Severity {(selected.severity_score * 100).toFixed(0)}%
        </span>
        {selected.exploitability_window && (
          <span className="text-xs px-2 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-300">
            Window: {selected.exploitability_window}
          </span>
        )}
      </div>

      {/* Path chain */}
      <div>
        <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Attack Path</p>
        <div className="flex items-center flex-wrap gap-1">
          {(selected.path ?? []).map((step, i) => (
            <div key={i} className="flex items-center gap-1">
              <span className="text-xs font-mono bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300">
                {step}
              </span>
              {i < selected.path.length - 1 && (
                <ChevronRight className="w-3 h-3 text-slate-600 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Severity breakdown */}
      <div>
        <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Severity Breakdown</p>
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Likelihood</span>
            <span className="text-slate-200 font-mono">{likelihoodPct}%</span>
          </div>
          <div className="w-full h-1.5 bg-slate-700 rounded-full">
            <div
              className="h-full bg-blue-500 rounded-full"
              style={{ width: `${likelihoodPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Blast Radius</span>
            <span className="text-slate-200 font-mono">{blastPct}%</span>
          </div>
          <div className="w-full h-1.5 bg-slate-700 rounded-full">
            <div
              className={`h-full rounded-full ${severityColor(selected.blast_radius_score ?? 0)}`}
              style={{ width: `${blastPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Recoverability Factor</span>
            <span className="text-slate-200 font-mono">{(recov * 100).toFixed(0)}%</span>
          </div>
          <div className="pt-1 border-t border-slate-700 flex justify-between text-xs">
            <span className="text-slate-400">Composite Risk Score</span>
            <span className={`font-mono font-semibold ${severityTextColor(selected.severity_score)}`}>
              {compositeRisk}
            </span>
          </div>
        </div>
      </div>

      {/* Scenarios */}
      <div>
        <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Scenario Checklist</p>
        <div className="space-y-2">
          {statusScenarios.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full shrink-0 ${scenarioDot[s.status]}`} />
              <span className="text-sm text-slate-300 flex-1">{s.label}</span>
              <span className="text-xs text-slate-500">{scenarioLabel[s.status]}</span>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Blast Radius Tab ─────────────────────────────────────────────────────────

interface BlastRadiusTabProps {
  states: ImpactFailureState[];
}

function BlastRadiusTab({ states }: BlastRadiusTabProps) {
  const [tooltip, setTooltip] = useState<{
    x: number; y: number; item: ImpactFailureState;
  } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const W = 560;
  const H = 320;
  const PAD = 48;
  const innerW = W - PAD * 2;
  const innerH = H - PAD * 2;

  const toX = (v: number) => PAD + v * innerW;
  const toY = (v: number) => PAD + (1 - v) * innerH;

  const meaningful = states.filter(
    (s) => s.likelihood_score != null && s.blast_radius_score != null
  );

  if (meaningful.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <Target className="w-8 h-8 opacity-30" />
        <p className="text-sm">No blast radius data available yet</p>
        <p className="text-xs text-slate-600">
          Failure states need likelihood_score and blast_radius_score populated
        </p>
      </div>
    );
  }

  const quadrantLabels = [
    { x: PAD + innerW * 0.1, y: PAD + innerH * 0.85, text: 'Low Priority', anchor: 'start' as const },
    { x: PAD + innerW * 0.1, y: PAD + innerH * 0.1, text: 'Likely Low Impact', anchor: 'start' as const },
    { x: PAD + innerW * 0.9, y: PAD + innerH * 0.1, text: 'High Priority', anchor: 'end' as const },
    { x: PAD + innerW * 0.9, y: PAD + innerH * 0.85, text: 'Latent Risk', anchor: 'end' as const },
  ];

  return (
    <div className="relative select-none">
      <p className="text-xs text-slate-500 mb-3 uppercase tracking-wide">
        X = Likelihood · Y = Blast Radius · Size = Severity
      </p>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full rounded-lg bg-slate-800/40 border border-slate-700"
        style={{ maxHeight: 340 }}
        onMouseLeave={() => setTooltip(null)}
      >
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map((v) => (
          <g key={v}>
            <line
              x1={toX(v)} y1={PAD} x2={toX(v)} y2={PAD + innerH}
              stroke={v === 0.5 ? '#475569' : '#1e293b'} strokeWidth={v === 0.5 ? 1 : 0.5}
              strokeDasharray={v === 0.5 ? '4 4' : undefined}
            />
            <line
              x1={PAD} y1={toY(v)} x2={PAD + innerW} y2={toY(v)}
              stroke={v === 0.5 ? '#475569' : '#1e293b'} strokeWidth={v === 0.5 ? 1 : 0.5}
              strokeDasharray={v === 0.5 ? '4 4' : undefined}
            />
          </g>
        ))}

        {/* Axis labels */}
        <text x={W / 2} y={H - 6} textAnchor="middle" className="fill-slate-500" fontSize={10}>
          Likelihood →
        </text>
        <text
          x={12} y={H / 2} textAnchor="middle" className="fill-slate-500" fontSize={10}
          transform={`rotate(-90, 12, ${H / 2})`}
        >
          Blast Radius →
        </text>

        {/* Tick labels */}
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <text x={toX(v)} y={PAD + innerH + 14} textAnchor="middle" fill="#64748b" fontSize={9}>
              {(v * 100).toFixed(0)}%
            </text>
            <text x={PAD - 6} y={toY(v) + 3} textAnchor="end" fill="#64748b" fontSize={9}>
              {(v * 100).toFixed(0)}%
            </text>
          </g>
        ))}

        {/* Quadrant labels */}
        {quadrantLabels.map((q, i) => (
          <text key={i} x={q.x} y={q.y} textAnchor={q.anchor} fill="#334155" fontSize={9} fontStyle="italic">
            {q.text}
          </text>
        ))}

        {/* Data points */}
        {meaningful.map((s) => {
          const cx = toX(s.likelihood_score!);
          const cy = toY(s.blast_radius_score!);
          const r = Math.max(4, s.severity_score * 14);
          const fill =
            s.severity_score >= 0.75
              ? 'rgba(239,68,68,0.75)'
              : s.severity_score >= 0.5
              ? 'rgba(249,115,22,0.75)'
              : 'rgba(234,179,8,0.75)';
          const stroke =
            s.severity_score >= 0.75
              ? '#ef4444'
              : s.severity_score >= 0.5
              ? '#f97316'
              : '#eab308';

          return (
            <circle
              key={s.id}
              cx={cx}
              cy={cy}
              r={r}
              fill={fill}
              stroke={stroke}
              strokeWidth={1.5}
              style={{ cursor: 'pointer' }}
              onMouseEnter={(e) => {
                const svg = svgRef.current;
                if (!svg) return;
                const rect = svg.getBoundingClientRect();
                const scaleX = rect.width / W;
                const scaleY = rect.height / H;
                setTooltip({
                  x: cx * scaleX + rect.left - (window.scrollX ?? 0),
                  y: cy * scaleY + rect.top - (window.scrollY ?? 0),
                  item: s,
                });
              }}
            />
          );
        })}
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl text-xs"
          style={{ left: tooltip.x + 12, top: tooltip.y - 40 }}
        >
          <div className={`font-semibold mb-1 ${severityTextColor(tooltip.item.severity_score)}`}>
            {getVulnClass(tooltip.item.vulnerability_class).label}
          </div>
          <div className="text-slate-400">Severity: {(tooltip.item.severity_score * 100).toFixed(0)}%</div>
          <div className="text-slate-400">Likelihood: {((tooltip.item.likelihood_score ?? 0) * 100).toFixed(0)}%</div>
          <div className="text-slate-400">Blast Radius: {((tooltip.item.blast_radius_score ?? 0) * 100).toFixed(0)}%</div>
        </div>
      )}
    </div>
  );
}

// ─── Entry Vectors Tab ────────────────────────────────────────────────────────

interface EntryVectorsTabProps {
  states: ImpactFailureState[];
}

function EntryVectorsTab({ states }: EntryVectorsTabProps) {
  const vectorMap = new Map<
    string,
    { count: number; maxSeverity: number; classes: Set<string> }
  >();

  for (const s of states) {
    const entry = s.path?.[0];
    if (!entry) continue;
    if (!vectorMap.has(entry)) {
      vectorMap.set(entry, { count: 0, maxSeverity: 0, classes: new Set() });
    }
    const v = vectorMap.get(entry)!;
    v.count += 1;
    v.maxSeverity = Math.max(v.maxSeverity, s.severity_score);
    v.classes.add(s.vulnerability_class);
  }

  const vectors = Array.from(vectorMap.entries())
    .map(([name, data]) => ({ name, ...data, classes: Array.from(data.classes) }))
    .sort((a, b) => b.maxSeverity - a.maxSeverity);

  if (vectors.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <Zap className="w-8 h-8 opacity-30" />
        <p className="text-sm">No entry vectors identified yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {vectors.map((v, i) => {
        const pct = v.maxSeverity * 100;
        return (
          <motion.div
            key={v.name}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 space-y-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-sm text-slate-200 truncate">{v.name}</span>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-slate-400">{v.count} path{v.count !== 1 ? 's' : ''}</span>
                <span className={`text-xs font-semibold ${severityTextColor(v.maxSeverity)}`}>
                  {pct.toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="w-full h-1 bg-slate-700 rounded-full">
              <div
                className={`h-full rounded-full ${severityColor(v.maxSeverity)}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-1">
              {v.classes.map((c) => {
                const vc = getVulnClass(c);
                return (
                  <span
                    key={c}
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${vc.color}`}
                  >
                    {vc.label}
                  </span>
                );
              })}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = 'paths' | 'blast' | 'vectors';

export default function RiskExplorer() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [states, setStates] = useState<ImpactFailureState[]>([]);
  const [graph, setGraph] = useState<ImpactGraphData | null>(null);
  const [selectedClass, setSelectedClass] = useState<string>('all');
  const [selectedState, setSelectedState] = useState<ImpactFailureState | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('paths');

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const [fsResult, graphResult] = await Promise.allSettled([
        edonApi.getImpactFailureStates(),
        edonApi.getImpactGraph(),
      ]);
      if (fsResult.status === 'fulfilled') {
        setStates(fsResult.value.failure_states ?? []);
      }
      if (graphResult.status === 'fulfilled') {
        setGraph(graphResult.value);
      }
    } catch {
      // errors handled per-call above
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Derived stats
  const totalSurface = states.length;
  const confirmedPaths = states.filter((s) => s.verified === true).length;

  const entryVectorSet = new Set<string>();
  for (const s of states) {
    if (s.path?.[0]) entryVectorSet.add(s.path[0]);
  }
  const entryVectorCount = entryVectorSet.size;

  const blastScores = states.filter((s) => s.blast_radius_score != null).map((s) => s.blast_radius_score!);
  const avgBlast = blastScores.length
    ? blastScores.reduce((a, b) => a + b, 0) / blastScores.length
    : 0;

  // Filtered list
  const filteredStates =
    selectedClass === 'all'
      ? states
      : states.filter((s) => s.vulnerability_class === selectedClass);

  const TABS: { id: Tab; label: string }[] = [
    { id: 'paths', label: 'Attack Paths' },
    { id: 'blast', label: 'Blast Radius' },
    { id: 'vectors', label: 'Entry Vectors' },
  ];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="min-h-screen bg-slate-950 text-slate-200 p-6 space-y-6"
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <Target className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100">Risk Explorer</h1>
            <p className="text-xs text-slate-500">Attack surface · paths · blast radius · entry vectors</p>
          </div>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing || loading}
          className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* ── Stat bar ── */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4 h-20 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="Attack Surface"
            value={totalSurface}
            icon={<AlertTriangle className="w-5 h-5" />}
            sub="total failure states"
          />
          <StatCard
            label="Entry Vectors"
            value={entryVectorCount}
            icon={<Zap className="w-5 h-5" />}
            sub="unique agent entry points"
          />
          <StatCard
            label="Confirmed Paths"
            value={confirmedPaths}
            icon={<Shield className="w-5 h-5" />}
            sub="verified failure states"
          />
          <StatCard
            label="Blast Radius"
            value={`${(avgBlast * 100).toFixed(0)}%`}
            icon={<Target className="w-5 h-5" />}
            sub="avg across all paths"
          />
        </div>
      )}

      {/* ── Two-column body ── */}
      <div className="flex gap-4 min-h-[600px]">
        {/* Left panel */}
        <div
          className="shrink-0 flex flex-col gap-3"
          style={{ width: 320 }}
        >
          {/* Filter pills */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Vulnerability Class</p>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setSelectedClass('all')}
                className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                  selectedClass === 'all'
                    ? 'bg-primary/10 border-primary/30 text-primary'
                    : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-300'
                }`}
              >
                All
              </button>
              {VULN_CLASSES.map((vc) => (
                <button
                  key={vc.key}
                  onClick={() => setSelectedClass(vc.key)}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                    selectedClass === vc.key
                      ? vc.color
                      : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-300'
                  }`}
                >
                  {vc.label}
                </button>
              ))}
            </div>
          </div>

          {/* Failure state list */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4 space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-16 bg-slate-800 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : filteredStates.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-slate-500 gap-2">
                <Circle className="w-6 h-6 opacity-30" />
                <p className="text-xs">No failure states found</p>
              </div>
            ) : (
              <div className="p-2 space-y-1.5">
                {filteredStates.map((s) => {
                  const vc = getVulnClass(s.vulnerability_class);
                  const isSelected = selectedState?.id === s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => {
                        setSelectedState(s);
                        setActiveTab('paths');
                      }}
                      className={`w-full text-left rounded-lg border p-2.5 transition-all ${
                        isSelected
                          ? 'border-primary/40 bg-primary/8'
                          : 'border-slate-800 bg-slate-800/40 hover:bg-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${vc.color}`}>
                          {vc.label}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${statusDotColor(s.status)}`}
                          />
                          <span className="text-[10px] text-slate-500 capitalize">{s.status}</span>
                        </div>
                      </div>
                      <div className="w-full h-1 bg-slate-700 rounded-full mb-1.5">
                        <div
                          className={`h-full rounded-full ${severityColor(s.severity_score)}`}
                          style={{ width: `${s.severity_score * 100}%` }}
                        />
                      </div>
                      <p className="font-mono text-[10px] text-slate-400 truncate">
                        {(s.path ?? []).join(' → ')}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right panel */}
        <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl flex flex-col min-w-0">
          {/* Tab bar */}
          <div className="flex border-b border-slate-800 px-4 pt-3 gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`text-xs px-3 py-2 rounded-t-md border-b-2 transition-colors ${
                  activeTab === t.id
                    ? 'border-primary text-primary font-medium'
                    : 'border-transparent text-slate-400 hover:text-slate-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-5">
            {activeTab === 'paths' && <AttackPathsTab selected={selectedState} />}
            {activeTab === 'blast' && <BlastRadiusTab states={states} />}
            {activeTab === 'vectors' && <EntryVectorsTab states={states} />}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
