import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Search, Filter, ChevronLeft, ChevronRight } from 'lucide-react'
import AccountLayout, { PageHeader, VerdictBadge, Spinner, EmptyState } from './AccountLayout'
import { gwAuditQuery, gwAuditExportUrl } from '../../lib/gateway'
import { toast } from 'sonner'
import { getToken } from '../../lib/gateway'

const VERDICTS = ['', 'ALLOW', 'BLOCK', 'ESCALATE', 'DEGRADE', 'ERROR']
const PAGE_SIZE = 20

export default function Audit() {
  const [agentFilter, setAgentFilter] = useState('')
  const [verdictFilter, setVerdictFilter] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(0)

  const params = {
    agent_id: agentFilter || undefined,
    verdict: verdictFilter || undefined,
    from: fromDate || undefined,
    to: toDate || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  }

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['audit', params],
    queryFn: () => gwAuditQuery(params),
    keepPreviousData: true,
  } as any)

  const decisions = (data as any)?.decisions ?? []
  const total: number = (data as any)?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  function applyFilters() {
    setPage(0)
  }

  async function downloadCsv() {
    const url = gwAuditExportUrl({
      agent_id: agentFilter || undefined,
      verdict: verdictFilter || undefined,
      from: fromDate || undefined,
      to: toDate || undefined,
    })
    try {
      const res = await fetch(url, { headers: { 'X-EDON-TOKEN': getToken() } })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `edon-audit-${new Date().toISOString().split('T')[0]}.csv`
      a.click()
    } catch {
      toast.error('Export failed — try again or contact support.')
    }
  }

  return (
    <AccountLayout>
      <div className="p-6 max-w-6xl">
        <PageHeader
          title="Audit Log"
          description={`${total.toLocaleString()} total decisions`}
          action={
            <button
              onClick={downloadCsv}
              className="flex items-center gap-1.5 rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
            >
              <Download className="h-3.5 w-3.5" /> Export CSV
            </button>
          }
        />

        {/* Filters */}
        <div className="mb-5 flex flex-wrap gap-3 rounded-lg border border-border bg-card p-3">
          <div className="relative flex-1 min-w-[160px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Agent ID"
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
              className="w-full rounded border border-input bg-background pl-8 pr-3 py-1.5 text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div className="relative">
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={verdictFilter}
              onChange={(e) => { setVerdictFilter(e.target.value); applyFilters() }}
              className="rounded border border-input bg-background pl-8 pr-3 py-1.5 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring appearance-none"
            >
              {VERDICTS.map((v) => (
                <option key={v} value={v}>{v || 'All verdicts'}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="rounded border border-input bg-background px-2 py-1.5 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="rounded border border-input bg-background px-2 py-1.5 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <button
            onClick={applyFilters}
            className="rounded border border-border px-3 py-1.5 text-xs hover:bg-secondary transition-colors"
          >
            Apply
          </button>
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {isLoading ? (
            <Spinner />
          ) : decisions.length === 0 ? (
            <EmptyState message="No decisions match your filters." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground bg-secondary/30">
                    <th className="px-4 py-2.5 text-left font-medium">Timestamp</th>
                    <th className="px-4 py-2.5 text-left font-medium">Agent</th>
                    <th className="px-4 py-2.5 text-left font-medium">Tool</th>
                    <th className="px-4 py-2.5 text-left font-medium">Verdict</th>
                    <th className="px-4 py-2.5 text-left font-medium">Reason</th>
                    <th className="px-4 py-2.5 text-left font-medium">Risk</th>
                    <th className="px-4 py-2.5 text-left font-medium">Explanation</th>
                  </tr>
                </thead>
                <tbody className={`divide-y divide-border ${isFetching ? 'opacity-60' : ''}`}>
                  {decisions.map((d: any) => (
                    <tr key={d.action_id} className="hover:bg-secondary/20 transition-colors">
                      <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(d.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground max-w-[100px] truncate">
                        {d.agent_id ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono max-w-[120px] truncate">
                        {d.tool ?? '—'}
                      </td>
                      <td className="px-4 py-2.5">
                        <VerdictBadge verdict={d.verdict} />
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                        {d.reason_code}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">
                        {d.risk_score != null ? (
                          <span className={d.risk_score > 0.7 ? 'text-destructive' : d.risk_score > 0.4 ? 'text-status-warning' : ''}>
                            {(d.risk_score * 100).toFixed(0)}%
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-[200px] truncate" title={d.explanation}>
                        {d.explanation ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded border border-border p-1.5 hover:bg-secondary disabled:opacity-40 transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <span className="px-2">Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="rounded border border-border p-1.5 hover:bg-secondary disabled:opacity-40 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </AccountLayout>
  )
}
