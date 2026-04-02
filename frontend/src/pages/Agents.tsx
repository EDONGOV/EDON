import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, ChevronLeft, ChevronRight, Bot, Cpu, Navigation, UserRound, Wifi, Eye,
  Mic, Globe, Database, Puzzle, Activity, LayoutList, LayoutGrid,
  ArrowRight, Link2, AlertTriangle, CheckCircle2, Clock,
} from 'lucide-react';
import { TopNav } from '@/components/TopNav';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { edonApi, AgentProfile } from '@/lib/api';

const PAGE_SIZE = 25;

// Map agent_type → icon + color
const TYPE_CONFIG: Record<string, { label: string; icon: React.FC<{ size?: number; className?: string }>; color: string }> = {
  humanoid:      { label: 'Humanoid',       icon: UserRound,  color: 'text-purple-400' },
  drone:         { label: 'Drone',          icon: Navigation, color: 'text-sky-400' },
  ground_robot:  { label: 'Ground Robot',   icon: Cpu,        color: 'text-orange-400' },
  iot:           { label: 'IoT Device',     icon: Wifi,       color: 'text-cyan-400' },
  vision:        { label: 'Vision',         icon: Eye,        color: 'text-pink-400' },
  digital:       { label: 'Digital Agent',  icon: Bot,        color: 'text-primary' },
  voice:         { label: 'Voice Agent',    icon: Mic,        color: 'text-yellow-400' },
  browser:       { label: 'Browser Agent',  icon: Globe,      color: 'text-blue-400' },
  data_pipeline: { label: 'Data Pipeline',  icon: Database,   color: 'text-teal-400' },
  custom:        { label: 'Custom',         icon: Puzzle,     color: 'text-muted-foreground' },
};

const getTypeCfg = (t: string) => TYPE_CONFIG[t] ?? { label: t, icon: Activity, color: 'text-muted-foreground' };

const STATUS_CONFIG = {
  active:  { label: 'Active',  color: 'text-emerald-400', dot: 'bg-emerald-400' },
  paused:  { label: 'Paused',  color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
  retired: { label: 'Retired', color: 'text-red-400', dot: 'bg-red-400' },
};

function relTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ─── Cross-agent feed mock ────────────────────────────────────────────────────
interface CrossAgentEvent {
  id: string;
  context_id: string;
  context_label: string;
  agents: Array<{ id: string; verdict: 'blocked' | 'confirm' | 'allowed'; tool: string; delay: string }>;
  summary: string;
  ts: string;
}

const CROSS_AGENT_EVENTS: CrossAgentEvent[] = [
  {
    id: 'xev_001',
    context_id: 'ctx_acme_q1deal',
    context_label: 'ACME Q1 Deal',
    agents: [
      { id: 'apex-research-agent',  verdict: 'confirm',  tool: 'http.request', delay: 'trigger' },
      { id: 'apex-outreach-agent',  verdict: 'blocked',  tool: 'email.send',   delay: '+18s' },
      { id: 'apex-analyst-agent',   verdict: 'confirm',  tool: 'db.query',     delay: '+23s' },
    ],
    summary: 'Research flagged contract liability risk → EDON auto-held Outreach email to ACME CEO and paused Analyst query on the same deal.',
    ts: new Date(Date.now() - 2 * 60000).toISOString(),
  },
  {
    id: 'xev_002',
    context_id: 'ctx_deploy_v3',
    context_label: 'Deploy v3.1.0',
    agents: [
      { id: 'apex-devops-agent',   verdict: 'confirm', tool: 'shell.exec',   delay: 'trigger' },
      { id: 'apex-analyst-agent',  verdict: 'confirm', tool: 'db.query',     delay: '+2m' },
    ],
    summary: 'DevOps triggered production deployment requiring approval. Analyst\'s live-traffic query deferred until deployment window closes.',
    ts: new Date(Date.now() - 11 * 60000).toISOString(),
  },
];

const VERDICT_ICON = {
  blocked: <AlertTriangle size={11} className="text-red-400" />,
  confirm: <Clock size={11} className="text-amber-400" />,
  allowed: <CheckCircle2 size={11} className="text-emerald-400" />,
};

const VERDICT_BG = {
  blocked: 'bg-red-500/10 border-red-500/20 text-red-400',
  confirm: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
  allowed: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
};

// ─── Agent Card (for grouped view) ───────────────────────────────────────────
function AgentCard({ agent }: { agent: AgentProfile }) {
  const cfg = getTypeCfg(agent.agent_type);
  const Icon = cfg.icon;
  const s = STATUS_CONFIG[agent.status] ?? STATUS_CONFIG.paused;
  const blockRate = agent.stats?.block_rate ?? 0;
  const totalActions = agent.stats?.total_actions ?? 0;
  const blockCount = agent.stats?.block_count ?? 0;
  const lastActive = agent.stats?.last_action_at ?? agent.last_seen_at;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card-hover p-4 space-y-3"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`p-1.5 rounded-lg bg-white/[0.05] ${cfg.color}`}>
            <Icon size={14} />
          </div>
          <div className="min-w-0">
            <div className="font-mono text-sm text-foreground font-medium truncate">{agent.agent_id}</div>
            <div className="text-xs text-muted-foreground truncate">{agent.name}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full animate-pulse-dot ${s.dot}`} />
          <span className={`text-xs ${s.color}`}>{s.label}</span>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-xs font-mono text-foreground font-semibold">{totalActions.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">Actions</div>
        </div>
        <div>
          <div className="text-xs font-mono text-red-400 font-semibold">{blockCount}</div>
          <div className="text-[10px] text-muted-foreground">Blocked</div>
        </div>
        <div>
          <div className="text-xs font-mono text-muted-foreground font-semibold">{blockRate.toFixed(1)}%</div>
          <div className="text-[10px] text-muted-foreground">Block Rate</div>
        </div>
      </div>

      {/* Block rate bar */}
      <div className="h-0.5 bg-secondary rounded-full overflow-hidden">
        <div className="h-full rounded-full bg-red-400/60" style={{ width: `${Math.min(blockRate, 100)}%` }} />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span className={cfg.color}>{cfg.label}</span>
        <span>Last active {relTime(lastActive)}</span>
      </div>
    </motion.div>
  );
}

// ─── Department Group ─────────────────────────────────────────────────────────
function DepartmentGroup({ dept, agents }: { dept: string; agents: AgentProfile[] }) {
  const totalActions = agents.reduce((s, a) => s + (a.stats?.total_actions ?? 0), 0);
  const totalBlocked = agents.reduce((s, a) => s + (a.stats?.block_count ?? 0), 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">{dept}</h3>
          <span className="text-xs text-muted-foreground bg-white/[0.05] px-2 py-0.5 rounded-full">
            {agents.length} agent{agents.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{totalActions.toLocaleString()} actions</span>
          {totalBlocked > 0 && <span className="text-red-400">{totalBlocked} blocked</span>}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {agents.map(agent => <AgentCard key={agent.agent_id} agent={agent} />)}
      </div>
    </motion.div>
  );
}

// ─── Cross-Agent Feed ─────────────────────────────────────────────────────────
function CrossAgentFeed() {
  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Link2 size={14} className="text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Cross-Agent Events</h3>
        <span className="text-xs text-muted-foreground bg-white/[0.05] px-2 py-0.5 rounded-full">Live</span>
      </div>
      <p className="text-xs text-muted-foreground">
        When one agent triggers a risk signal, EDON automatically holds related actions across other agents working in the same context.
      </p>
      <div className="space-y-4">
        {CROSS_AGENT_EVENTS.map(ev => (
          <div key={ev.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
            {/* Context header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                  {ev.context_id}
                </span>
                <span className="text-xs font-medium text-foreground">{ev.context_label}</span>
              </div>
              <span className="text-[10px] text-muted-foreground">{relTime(ev.ts)}</span>
            </div>

            {/* Chain visualization */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {ev.agents.map((ag, idx) => (
                <div key={ag.id} className="flex items-center gap-1.5">
                  <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono ${VERDICT_BG[ag.verdict]}`}>
                    {VERDICT_ICON[ag.verdict]}
                    <span className="text-foreground/80">{ag.id.replace('apex-', '').replace('-agent', '')}</span>
                    <span className="opacity-60">·</span>
                    <span className="opacity-70 text-[10px]">{ag.tool}</span>
                  </div>
                  {idx < ev.agents.length - 1 && (
                    <div className="flex items-center gap-0.5 text-muted-foreground">
                      <ArrowRight size={10} />
                      <span className="text-[10px] font-mono">{ev.agents[idx + 1].delay}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Summary */}
            <p className="text-xs text-muted-foreground leading-relaxed">{ev.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function Agents() {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [viewMode, setViewMode] = useState<'list' | 'grouped'>('grouped');

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    try {
      const res = await edonApi.listAgents();
      setAgents(res?.agents ?? []);
    } catch {
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);
  useEffect(() => { setPage(0); }, [selectedType, search]);

  const agentTypes = Array.from(new Set(agents.map(a => a.agent_type))).sort();

  const filtered = agents.filter(a => {
    const matchType = selectedType === 'all' || a.agent_type === selectedType;
    const q = search.toLowerCase();
    const matchSearch = !q ||
      a.agent_id.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      a.agent_type.toLowerCase().includes(q) ||
      String(a.metadata?.group ?? '').toLowerCase().includes(q) ||
      String(a.metadata?.department ?? '').toLowerCase().includes(q);
    return matchType && matchSearch;
  });

  // Group agents by department for grouped view
  const byDept = filtered.reduce<Record<string, AgentProfile[]>>((acc, a) => {
    const dept = String(a.metadata?.department ?? 'Ungrouped');
    if (!acc[dept]) acc[dept] = [];
    acc[dept].push(a);
    return acc;
  }, {});

  const departments = Object.keys(byDept).sort();

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Check if any agents have cross-agent events (context_id data)
  const hasCrossAgentData = CROSS_AGENT_EVENTS.length > 0;

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <div className="space-y-5">

            {/* Header */}
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-foreground">Agents</h1>
                <p className="text-muted-foreground text-sm mt-1">
                  {loading ? 'Loading agents…' : `${agents.length} registered agents`}
                </p>
              </div>
              {/* View toggle */}
              <div className="flex items-center gap-1 p-1 rounded-xl border border-white/10 bg-white/[0.03]">
                <button
                  onClick={() => setViewMode('list')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    viewMode === 'list'
                      ? 'bg-primary/20 text-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <LayoutList size={13} />
                  List
                </button>
                <button
                  onClick={() => setViewMode('grouped')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    viewMode === 'grouped'
                      ? 'bg-primary/20 text-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <LayoutGrid size={13} />
                  By Department
                </button>
              </div>
            </div>

            {/* Type filter pills */}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setSelectedType('all')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border ${
                  selectedType === 'all'
                    ? 'bg-primary/20 text-primary border-primary/40'
                    : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground'
                }`}
              >
                All · {agents.length}
              </button>
              {agentTypes.map(type => {
                const cfg = getTypeCfg(type);
                const Icon = cfg.icon;
                const count = agents.filter(a => a.agent_type === type).length;
                return (
                  <button
                    key={type}
                    onClick={() => setSelectedType(type)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all border ${
                      selectedType === type
                        ? 'bg-primary/20 text-primary border-primary/40'
                        : 'bg-secondary text-muted-foreground border-white/10 hover:border-white/20 hover:text-foreground'
                    }`}
                  >
                    <Icon size={11} className={selectedType === type ? 'text-primary' : cfg.color} />
                    {cfg.label} · {count}
                  </button>
                );
              })}
            </div>

            {/* Search */}
            <div className="relative max-w-sm">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search agents, departments..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* ── LIST VIEW ── */}
            <AnimatePresence mode="wait">
              {viewMode === 'list' && (
                <motion.div
                  key="list"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="glass-card overflow-hidden"
                >
                  {loading ? (
                    <div className="space-y-px">
                      {Array.from({ length: 8 }).map((_, i) => (
                        <div key={i} className="h-12 bg-white/[0.02] animate-pulse" />
                      ))}
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-white/10 text-muted-foreground">
                            <th className="text-left px-4 py-3 font-medium">Agent</th>
                            <th className="text-left px-4 py-3 font-medium hidden sm:table-cell">Type</th>
                            <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Department</th>
                            <th className="text-left px-4 py-3 font-medium">Status</th>
                            <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Actions</th>
                            <th className="text-right px-4 py-3 font-medium hidden lg:table-cell">Blocked</th>
                            <th className="text-left px-4 py-3 font-medium hidden xl:table-cell">Block Rate</th>
                            <th className="text-right px-4 py-3 font-medium hidden md:table-cell">Last Active</th>
                          </tr>
                        </thead>
                        <tbody>
                          {paginated.length === 0 ? (
                            <tr>
                              <td colSpan={8} className="px-4 py-10 text-center text-muted-foreground">
                                No agents match your filters.
                              </td>
                            </tr>
                          ) : paginated.map(agent => {
                            const cfg = getTypeCfg(agent.agent_type);
                            const Icon = cfg.icon;
                            const s = STATUS_CONFIG[agent.status] ?? STATUS_CONFIG.paused;
                            const blockRate = agent.stats?.block_rate ?? 0;
                            const totalActions = agent.stats?.total_actions ?? 0;
                            const blockCount = agent.stats?.block_count ?? 0;
                            const lastActive = agent.stats?.last_action_at ?? agent.last_seen_at;
                            const department = String(agent.metadata?.department ?? '—');
                            return (
                              <tr key={agent.agent_id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                                <td className="px-4 py-3">
                                  <div className="flex items-center gap-2">
                                    <Icon size={13} className={cfg.color} />
                                    <div>
                                      <div className="font-mono text-foreground font-medium">{agent.agent_id}</div>
                                      <div className="text-muted-foreground/70">{agent.name}</div>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-3 hidden sm:table-cell">
                                  <span className="text-muted-foreground">{cfg.label}</span>
                                </td>
                                <td className="px-4 py-3 hidden md:table-cell">
                                  <span className="font-mono text-muted-foreground">{department}</span>
                                </td>
                                <td className="px-4 py-3">
                                  <div className="flex items-center gap-1.5">
                                    <span className={`w-1.5 h-1.5 rounded-full animate-pulse-dot ${s.dot}`} />
                                    <span className={s.color}>{s.label}</span>
                                  </div>
                                </td>
                                <td className="px-4 py-3 text-right hidden lg:table-cell">
                                  <span className="font-mono text-foreground">{totalActions.toLocaleString()}</span>
                                </td>
                                <td className="px-4 py-3 text-right hidden lg:table-cell">
                                  <span className="font-mono text-red-400">{blockCount.toLocaleString()}</span>
                                </td>
                                <td className="px-4 py-3 hidden xl:table-cell">
                                  <div className="flex items-center gap-2">
                                    <div className="w-16 h-1 bg-secondary rounded-full overflow-hidden">
                                      <div
                                        className="h-full rounded-full bg-red-400/70"
                                        style={{ width: `${Math.min(blockRate, 100)}%` }}
                                      />
                                    </div>
                                    <span className="text-muted-foreground">{blockRate.toFixed(1)}%</span>
                                  </div>
                                </td>
                                <td className="px-4 py-3 text-right hidden md:table-cell">
                                  <span className="text-muted-foreground">{relTime(lastActive)}</span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Pagination */}
                  {!loading && filtered.length > 0 && (
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
                  )}
                </motion.div>
              )}

              {/* ── GROUPED VIEW ── */}
              {viewMode === 'grouped' && (
                <motion.div
                  key="grouped"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="space-y-8"
                >
                  {loading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="h-36 rounded-2xl bg-white/[0.02] animate-pulse" />
                      ))}
                    </div>
                  ) : departments.length === 0 ? (
                    <div className="glass-card py-12 text-center text-muted-foreground text-sm">
                      No agents match your filters.
                    </div>
                  ) : (
                    departments.map(dept => (
                      <DepartmentGroup key={dept} dept={dept} agents={byDept[dept]} />
                    ))
                  )}

                  {/* Cross-agent feed — show when grouped view active */}
                  {!loading && hasCrossAgentData && (
                    <CrossAgentFeed />
                  )}
                </motion.div>
              )}
            </AnimatePresence>

          </div>
        </motion.div>
      </main>
    </div>
  );
}
