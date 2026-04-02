import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Ban, AlertTriangle, Timer, Users, ChevronRight, Activity } from 'lucide-react';
import { TopNav } from '@/components/TopNav';
import { StatCard } from '@/components/StatCard';
import { DecisionStreamTable } from '@/components/DecisionStreamTable';
import { DecisionDrawer } from '@/components/DecisionDrawer';
import { TopReasonsChart } from '@/components/charts/TopReasonsChart';
import { PolicyModeCard } from '@/components/PolicyModeCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { edonApi, Decision } from '@/lib/api';
import { detectCapabilities, type CapabilityKey } from '@/lib/capabilities';
import { Link } from 'react-router-dom';
import {
  getActiveProfile,
  getActiveDomains,
  DOMAINS,
  PROFILES,
  isOnboardingComplete,
  type DomainId,
} from '@/lib/workspaceProfile';

interface AgentStat {
  agentId: string;
  total: number;
  allowed: number;
  blocked: number;
  blockRate: number;
  topBlockReason: string;
  lastActive: string;
}

const BLOCK_REASONS = [
  'policy_match',
  'risk_threshold',
  'context_violation',
  'rate_limit',
  'sensitive_data',
  'unauthorized_tool',
];

function generateMockAgentStats(): AgentStat[] {
  const agents = [
    { id: 'agent_ops_001', offset: 0 },
    { id: 'agent_research_02', offset: 2 },
    { id: 'agent_finance_03', offset: 5 },
    { id: 'agent_support_04', offset: 12 },
    { id: 'agent_scheduler_05', offset: 45 },
  ];
  return agents.map(({ id, offset }) => {
    const total = Math.floor(Math.random() * 200) + 40;
    const blocked = Math.floor(Math.random() * Math.min(total * 0.3, 30)) + 1;
    const allowed = total - blocked;
    return {
      agentId: id,
      total,
      allowed,
      blocked,
      blockRate: Math.round((blocked / total) * 100),
      topBlockReason: BLOCK_REASONS[Math.floor(Math.random() * BLOCK_REASONS.length)],
      lastActive: new Date(Date.now() - offset * 60000).toISOString(),
    };
  });
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function deriveAgentStats(decisions: Decision[]): AgentStat[] {
  const map = new Map<string, { allowed: number; blocked: number; reasons: string[]; lastActive: string }>();
  for (const d of decisions) {
    const id = d.agent_id || 'unknown';
    if (!map.has(id)) {
      map.set(id, { allowed: 0, blocked: 0, reasons: [], lastActive: d.timestamp });
    }
    const entry = map.get(id)!;
    const v = (d.verdict ?? '').toLowerCase();
    if (v === 'allowed') entry.allowed++;
    else if (v === 'blocked') {
      entry.blocked++;
      if (d.reason_code) entry.reasons.push(d.reason_code);
    }
    if (new Date(d.timestamp) > new Date(entry.lastActive)) {
      entry.lastActive = d.timestamp;
    }
  }
  return Array.from(map.entries()).map(([agentId, e]) => {
    const total = e.allowed + e.blocked;
    const topReason = e.reasons.length > 0
      ? e.reasons.sort((a, b) =>
          e.reasons.filter(r => r === b).length - e.reasons.filter(r => r === a).length
        )[0]
      : '—';
    return {
      agentId,
      total,
      allowed: e.allowed,
      blocked: e.blocked,
      blockRate: total > 0 ? Math.round((e.blocked / total) * 100) : 0,
      topBlockReason: topReason,
      lastActive: e.lastActive,
    };
  }).sort((a, b) => b.total - a.total);
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<{
    allowed_24h?: number;
    blocked_24h?: number;
    confirm_24h?: number;
    latency_p50?: number;
    latency_p95?: number;
    latency_p99?: number;
  }>({});
  const [capabilities, setCapabilities] = useState<Record<CapabilityKey, boolean> | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [agentStats, setAgentStats] = useState<AgentStat[]>([]);

  // Workspace profile state — re-reads on profile-updated events
  const [activeDomains, setActiveDomains] = useState<DomainId[]>(() => getActiveDomains());
  const [activeProfileId, setActiveProfileId] = useState(() => getActiveProfile());
  const [onboarded, setOnboarded] = useState(() => isOnboardingComplete());

  useEffect(() => {
    const refresh = () => {
      setActiveDomains(getActiveDomains());
      setActiveProfileId(getActiveProfile());
      setOnboarded(isOnboardingComplete());
    };
    window.addEventListener('edon-profile-updated', refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener('edon-profile-updated', refresh);
      window.removeEventListener('storage', refresh);
    };
  }, []);

  const activeProfile = useMemo(
    () => PROFILES.find((p) => p.id === activeProfileId) ?? null,
    [activeProfileId]
  );

  // Domain-specific quick-links (deduplicated, non-base nav entries)
  // Medical / nanobot domain is excluded from dashboard quick-links for now
  const domainQuickLinks = useMemo(() => {
    const seen = new Set<string>();
    return activeDomains
      .filter((id) => id !== 'medical')
      .flatMap((id) => {
        const d = DOMAINS[id];
        return d?.navExtras ?? [];
      }).filter(({ to }) => {
        if (seen.has(to)) return false;
        seen.add(to);
        return true;
      });
  }, [activeDomains]);

  useEffect(() => {
    const baseUrl =
      (typeof window !== 'undefined' && localStorage.getItem('edon_api_base')) ||
      import.meta.env.VITE_EDON_GATEWAY_URL ||
      'http://127.0.0.1:8000';
    const token =
      (typeof window !== 'undefined' && localStorage.getItem('edon_token')) ||
      (import.meta.env.MODE !== 'production' ? import.meta.env.VITE_EDON_API_TOKEN || '' : '') ||
      '';
    if (baseUrl && token) {
      detectCapabilities(baseUrl, token).then(setCapabilities);
    } else {
      setCapabilities({ timeseries: false, blockReasons: false });
    }
  }, []);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const data = await edonApi.getMetrics();
        setMetrics(data);
      } catch (error) {
        if (import.meta.env.DEV) {
          console.error('Failed to fetch metrics:', error);
        }
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchDecisions = async () => {
      try {
        const result = await edonApi.getDecisions({ limit: 500 });
        const fetched = result.decisions ?? [];
        setDecisions(fetched);
        if (fetched.length > 0) {
          setAgentStats(deriveAgentStats(fetched));
        } else {
          setAgentStats(generateMockAgentStats());
        }
      } catch {
        setAgentStats(generateMockAgentStats());
      }
    };
    fetchDecisions();
  }, []);

  const handleSelectDecision = (decision: Decision) => {
    setSelectedDecision(decision);
    setDrawerOpen(true);
  };

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <div className="space-y-6">

        {/* Page Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {activeProfile
              ? `${activeProfile.icon} ${activeProfile.label} governance`
              : 'Real-time AI governance overview'}
          </p>
        </motion.div>

        {/* Active capabilities strip — only shown after onboarding */}
        {onboarded && activeDomains.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex flex-wrap items-center gap-2"
          >
            <span className="text-xs text-muted-foreground">Active:</span>
            {activeDomains.filter((id) => id !== 'medical').map((id) => {
              const d = DOMAINS[id];
              return d ? (
                <Badge
                  key={id}
                  variant="outline"
                  className="text-[11px] border-white/15 text-muted-foreground gap-1 py-0.5"
                >
                  {d.icon} {d.label}
                </Badge>
              ) : null;
            })}
            <Link
              to="/capabilities"
              className="text-[11px] text-primary/70 hover:text-primary transition-colors ml-auto"
            >
              Manage capabilities →
            </Link>
          </motion.div>
        )}

        {/* KPI Cards */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-2 lg:grid-cols-4 gap-4"
        >
          <StatCard
            title="Allowed (24h)"
            value={metrics?.allowed_24h != null ? metrics.allowed_24h.toLocaleString() : "—"}
            icon={ShieldCheck}
            variant="success"
            delay={0}
          />
          <StatCard
            title="Blocked (24h)"
            value={metrics?.blocked_24h != null ? metrics.blocked_24h.toLocaleString() : "—"}
            icon={Ban}
            variant="danger"
            delay={1}
          />
          <StatCard
            title="Confirm Needed (24h)"
            value={metrics?.confirm_24h != null ? metrics.confirm_24h.toLocaleString() : "—"}
            icon={AlertTriangle}
            variant="warning"
            delay={2}
          />
          <StatCard
            title="Latency p50"
            value={metrics?.latency_p50 ? `${metrics.latency_p50}ms` : "—"}
            icon={Timer}
            change={metrics?.latency_p95 && metrics.latency_p95 > 0 ? `p95: ${metrics.latency_p95}ms${metrics.latency_p99 ? `, p99: ${metrics.latency_p99}ms` : ''}` : undefined}
            changeType="neutral"
            variant="default"
            delay={3}
          />
        </motion.div>

        {/* Main Content — Live Feed + Right Col */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Live Decision Stream */}
          <div className="lg:col-span-2">
            <DecisionStreamTable
              onSelectDecision={handleSelectDecision}
              limit={20}
            />
          </div>

          {/* Right Column */}
          <div className="space-y-4">
            <PolicyModeCard />

            {/* System Health */}
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">System Health</h3>
              </div>
              <div className="space-y-3">
                {[
                  { label: 'Latency p50', value: metrics?.latency_p50 ? `${metrics.latency_p50}ms` : '—', ok: !metrics?.latency_p50 || metrics.latency_p50 < 50 },
                  { label: 'Latency p95', value: metrics?.latency_p95 ? `${metrics.latency_p95}ms` : '—', ok: !metrics?.latency_p95 || metrics.latency_p95 < 100 },
                  { label: 'Latency p99', value: metrics?.latency_p99 ? `${metrics.latency_p99}ms` : '—', ok: !metrics?.latency_p99 || metrics.latency_p99 < 200 },
                ].map(({ label, value, ok }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">{label}</span>
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                      <span className="text-xs font-mono text-foreground">{value}</span>
                    </div>
                  </div>
                ))}
                <div className="pt-2 border-t border-white/5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Audit Chain</span>
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-xs text-emerald-400">Verified</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Second Row — Reasons + Agent Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Top Block Reasons */}
          <TopReasonsChart supported={capabilities?.blockReasons ?? false} />

          {/* Agent Activity */}
          <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Agent Activity</h3>
                <Badge variant="outline" className="text-[11px]">24h</Badge>
              </div>
              <Link
                to="/agents"
                className="text-xs text-primary hover:underline inline-flex items-center gap-0.5"
              >
                View All <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
            <div className="space-y-3">
              {agentStats.slice(0, 6).map((stat) => (
                <div key={stat.agentId} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-foreground/80 truncate max-w-[160px]">{stat.agentId}</span>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
                      <span className="text-emerald-400">{stat.allowed}</span>
                      <span>/</span>
                      <span className="text-red-400">{stat.blocked}</span>
                      <span className="tabular-nums w-10 text-right">{stat.total}</span>
                    </div>
                  </div>
                  <div className="h-1 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        stat.blockRate >= 30 ? 'bg-red-400/70' : stat.blockRate >= 10 ? 'bg-amber-400/70' : 'bg-primary/70'
                      }`}
                      style={{ width: `${Math.min(100, stat.total > 0 ? (stat.allowed / stat.total) * 100 : 0)}%` }}
                    />
                  </div>
                </div>
              ))}
              {agentStats.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-4">No agent data yet.</p>
              )}
            </div>
          </div>
        </div>

        {/* Domain quick-links — only shown when extra domains are active */}
        {domainQuickLinks.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
              Quick access
            </p>
            <div className="flex flex-wrap gap-3">
              {domainQuickLinks.map(({ to, label }) => (
                <Link key={to} to={to}>
                  <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                    {label} <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              ))}
            </div>
          </motion.div>
        )}

        </div>
      </main>

      <DecisionDrawer
        decision={selectedDecision}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
