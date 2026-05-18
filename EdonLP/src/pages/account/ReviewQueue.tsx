import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, XCircle, Clock, Loader2, RefreshCw } from 'lucide-react'
import AccountLayout, { PageHeader, Spinner, EmptyState } from './AccountLayout'
import { gwReviewQueue, gwReviewDecide } from '../../lib/gateway'
import { toast } from 'sonner'

export default function ReviewQueue() {
  const qc = useQueryClient()
  const [deciding, setDeciding] = useState<string | null>(null)
  const [note, setNote] = useState<Record<string, string>>({})

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['review-queue'],
    queryFn: gwReviewQueue,
    refetchInterval: 15_000,
  })

  const decideMutation = useMutation({
    mutationFn: ({ id, decision, n }: { id: string; decision: 'approve' | 'block'; n?: string }) =>
      gwReviewDecide(id, decision, n),
    onMutate: ({ id }) => setDeciding(id),
    onSuccess: (_, { decision }) => {
      toast.success(decision === 'approve' ? 'Action approved.' : 'Action blocked.')
      qc.invalidateQueries({ queryKey: ['review-queue'] })
      setDeciding(null)
    },
    onError: (err: Error) => {
      toast.error(err.message)
      setDeciding(null)
    },
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <AccountLayout>
      <div className="p-6 max-w-4xl">
        <PageHeader
          title="Review Queue"
          description={
            total > 0
              ? `${total} action${total !== 1 ? 's' : ''} awaiting your decision`
              : 'No pending escalations.'
          }
          action={
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        {total > 0 && (
          <div className="mb-5 flex items-center gap-2 rounded-lg border border-status-warning/20 bg-status-warning/5 px-4 py-3 text-sm">
            <AlertTriangle className="h-4 w-4 text-status-warning shrink-0" />
            <span className="text-status-warning">
              {total} agent action{total !== 1 ? 's are' : ' is'} blocked waiting for human approval.
            </span>
          </div>
        )}

        {isLoading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-border bg-card">
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <CheckCircle className="h-10 w-10 text-status-active/40 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">All clear</p>
              <p className="text-xs text-muted-foreground/60 mt-1">No pending escalations. Queue refreshes every 15s.</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {items.map((item) => (
              <div
                key={item.review_id}
                className="rounded-lg border border-status-warning/20 bg-card p-5"
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle className="h-4 w-4 text-status-warning" />
                      <span className="font-space font-semibold text-sm">Escalated action</span>
                      {item.risk_score != null && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${item.risk_score > 0.7 ? 'bg-destructive/10 text-destructive' : 'bg-status-warning/10 text-status-warning'}`}>
                          Risk {(item.risk_score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>Agent: <span className="font-mono">{item.agent_id}</span></span>
                      {item.tool && <span>Tool: <span className="font-mono">{item.tool}</span></span>}
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(item.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Question */}
                {item.escalation_question && (
                  <div className="mb-3 rounded border border-border bg-secondary/30 px-3 py-2.5">
                    <p className="text-xs font-medium text-muted-foreground mb-0.5">Agent asks:</p>
                    <p className="text-sm">{item.escalation_question}</p>
                  </div>
                )}

                {/* Explanation */}
                <p className="text-xs text-muted-foreground mb-4 leading-relaxed">
                  {item.explanation}
                </p>

                {/* Note input */}
                <textarea
                  rows={2}
                  placeholder="Add a note (optional)…"
                  value={note[item.review_id] ?? ''}
                  onChange={(e) => setNote((n) => ({ ...n, [item.review_id]: e.target.value }))}
                  className="w-full mb-3 rounded border border-input bg-background px-3 py-2 text-xs placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                />

                {/* Actions */}
                <div className="flex flex-wrap items-center gap-2">
                  {item.escalation_options && item.escalation_options.length > 0 ? (
                    item.escalation_options.map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() =>
                          decideMutation.mutate({
                            id: item.review_id,
                            decision: opt.id.includes('block') || opt.id.includes('deny') ? 'block' : 'approve',
                            n: note[item.review_id],
                          })
                        }
                        disabled={deciding === item.review_id}
                        className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-secondary disabled:opacity-50 transition-colors"
                      >
                        {deciding === item.review_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {opt.label}
                      </button>
                    ))
                  ) : (
                    <>
                      <button
                        onClick={() =>
                          decideMutation.mutate({ id: item.review_id, decision: 'approve', n: note[item.review_id] })
                        }
                        disabled={deciding === item.review_id}
                        className="flex items-center gap-1.5 rounded-md bg-status-active/10 border border-status-active/20 px-4 py-1.5 text-xs font-medium text-status-active hover:bg-status-active/20 disabled:opacity-50 transition-colors"
                      >
                        {deciding === item.review_id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <CheckCircle className="h-3.5 w-3.5" />
                        )}
                        Approve
                      </button>
                      <button
                        onClick={() =>
                          decideMutation.mutate({ id: item.review_id, decision: 'block', n: note[item.review_id] })
                        }
                        disabled={deciding === item.review_id}
                        className="flex items-center gap-1.5 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 disabled:opacity-50 transition-colors"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Block
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AccountLayout>
  )
}
