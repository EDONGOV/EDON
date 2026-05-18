import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle, XCircle, Zap, Wifi, WifiOff } from 'lucide-react'
import AccountLayout, { PageHeader, StatCard, VerdictBadge, Spinner, EmptyState } from './AccountLayout'
import { gwStats, gwHealth, gwAuditQuery } from '../../lib/gateway'

export default function Overview() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: gwStats, refetchInterval: 30_000 })
  const health = useQuery({ queryKey: ['health'], queryFn: gwHealth, refetchInterval: 30_000 })
  const recent = useQuery({
    queryKey: ['recent-decisions'],
    queryFn: () => gwAuditQuery({ limit: 8 }),
    refetchInterval: 15_000,
  })

  const s = stats.data
  const h = health.data
  const decisions = recent.data?.decisions ?? []

  return (
    <AccountLayout>
      <div className="p-6 max-w-5xl">
        <PageHeader
          title="Overview"
          description="Live governance summary for your workspace."
          action={
            <div className="flex items-center gap-1.5 text-xs">
              {h?.status === 'healthy' ? (
                <><Wifi className="h-3.5 w-3.5 text-status-active" /><span className="text-status-active">Gateway online</span></>
              ) : health.isLoading ? (
                <span className="text-muted-foreground">Checking…</span>
              ) : (
                <><WifiOff className="h-3.5 w-3.5 text-destructive" /><span className="text-destructive">Gateway unreachable</span></>
              )}
            </div>
          }
        />

        {/* Stat cards */}
        {stats.isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-4 animate-pulse h-20" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="Total decisions"
              value={s?.total_decisions?.toLocaleString() ?? '—'}
              sub="all time"
            />
            <StatCard
              label="Today"
              value={s?.decisions_today?.toLocaleString() ?? '—'}
              sub="decisions"
              accent="green"
            />
            <StatCard
              label="Blocked"
              value={s?.blocked?.toLocaleString() ?? '—'}
              sub={s ? `${((s.blocked / (s.total_decisions || 1)) * 100).toFixed(1)}% of total` : undefined}
              accent="red"
            />
            <StatCard
              label="Avg latency"
              value={s?.avg_latency_ms != null ? `${s.avg_latency_ms.toFixed(1)}ms` : '—'}
              sub="governance overhead"
              accent="default"
            />
          </div>
        )}

        {/* Decision breakdown */}
        {s && (
          <div className="grid grid-cols-3 gap-3 mb-8">
            {[
              { label: 'Allowed', value: s.allowed, icon: CheckCircle, color: 'text-status-active' },
              { label: 'Blocked', value: s.blocked, icon: XCircle, color: 'text-destructive' },
              { label: 'Escalated', value: s.escalated, icon: AlertTriangle, color: 'text-status-warning' },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="rounded-lg border border-border bg-card px-4 py-3 flex items-center gap-3">
                <Icon className={`h-5 w-5 ${color}`} />
                <div>
                  <p className="font-space text-lg font-bold">{value?.toLocaleString() ?? '—'}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Recent decisions */}
        <div className="rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Recent decisions</span>
            </div>
            <a href="/account/audit" className="text-xs text-primary hover:underline">View all →</a>
          </div>

          {recent.isLoading ? (
            <Spinner />
          ) : decisions.length === 0 ? (
            <EmptyState message="No decisions yet. Connect an agent to get started." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 text-left font-medium">Time</th>
                    <th className="px-4 py-2.5 text-left font-medium">Agent</th>
                    <th className="px-4 py-2.5 text-left font-medium">Tool</th>
                    <th className="px-4 py-2.5 text-left font-medium">Verdict</th>
                    <th className="px-4 py-2.5 text-left font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {decisions.map((d) => (
                    <tr key={d.action_id} className="hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(d.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground truncate max-w-[100px]">
                        {d.agent_id ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono truncate max-w-[120px]">
                        {d.tool ?? '—'}
                      </td>
                      <td className="px-4 py-2.5">
                        <VerdictBadge verdict={d.verdict} />
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground truncate max-w-[140px]">
                        {d.reason_code}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Gateway info */}
        {h && (
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground">
            {h.version && <span className="flex items-center gap-1"><Zap className="h-3 w-3" /> v{h.version}</span>}
            {h.uptime_seconds && (
              <span>Uptime: {Math.floor(h.uptime_seconds / 3600)}h {Math.floor((h.uptime_seconds % 3600) / 60)}m</span>
            )}
            {h.components && Object.entries(h.components).map(([k, v]) => (
              <span key={k} className={v === 'ok' || v === 'healthy' ? 'text-status-active' : 'text-status-warning'}>
                {k}: {v}
              </span>
            ))}
          </div>
        )}
      </div>
    </AccountLayout>
  )
}
