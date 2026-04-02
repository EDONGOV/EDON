import { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { edonApi, Decision } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Link } from 'react-router-dom';
import { toolOp } from '@/lib/utils';

const POLL_MS = 8000;

// Module-level flag — persists across remounts so we never retry audit after a 403
let auditForbidden = false;

interface DecisionStreamTableProps {
  onSelectDecision?: (decision: Decision) => void;
  limit?: number;
  autoRefresh?: boolean;
}

const verdictStyles = {
  allowed: 'badge-allowed',
  blocked: 'badge-blocked',
  confirm: 'badge-confirm',
};

function formatTime(ts: string | undefined | null): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function DecisionStreamTable({
  onSelectDecision,
  limit = 50,
  autoRefresh = true,
}: DecisionStreamTableProps) {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAuditFallback, setShowAuditFallback] = useState(false);

  const fetchDecisions = useCallback(async () => {
    try {
      const result = await edonApi.getDecisions({ limit });
      const list = Array.isArray(result?.decisions) ? result.decisions : [];
      if (list.length > 0) {
        setDecisions(list);
        setShowAuditFallback(false);
      } else if (!auditForbidden) {
        const audit = await edonApi.getAudit({ limit });
        if (audit === null) {
          auditForbidden = true;
          setShowAuditFallback(false);
        } else {
          const records = Array.isArray(audit?.records) ? audit.records : [];
          setDecisions(records);
          setShowAuditFallback(records.length > 0);
        }
      }
    } catch {
      setDecisions([]);
      setShowAuditFallback(false);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    if (!autoRefresh) {
      fetchDecisions();
      return;
    }

    let interval: number | undefined;

    const start = () => {
      if (interval) window.clearInterval(interval);
      interval = window.setInterval(fetchDecisions, POLL_MS);
    };
    const stop = () => {
      if (interval) { window.clearInterval(interval); interval = undefined; }
    };
    const onVis = () => {
      if (document.hidden) { stop(); } else { fetchDecisions(); start(); }
    };

    fetchDecisions();
    start();
    document.addEventListener('visibilitychange', onVis);
    return () => { stop(); document.removeEventListener('visibilitychange', onVis); };
  }, [fetchDecisions, autoRefresh]);

  const list = decisions ?? [];

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot" />
          <h2 className="font-semibold text-sm text-foreground">Live Decision Feed</h2>
        </div>
        <span className="text-xs text-muted-foreground">{list.length.toLocaleString()} events</span>
      </div>

      {showAuditFallback && (
        <p className="text-xs text-amber-400/80 mb-3">
          Showing audit fallback ·{' '}
          <Link to="/audit" className="underline hover:text-amber-300">Open Audit</Link>
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b border-white/5">
              <th className="text-left pb-2 font-medium">Verdict</th>
              <th className="text-left pb-2 font-medium">Agent</th>
              <th className="text-left pb-2 font-medium hidden md:table-cell">Tool.Op</th>
              <th className="text-left pb-2 font-medium hidden lg:table-cell">Reason</th>
              <th className="text-right pb-2 font-medium">ms</th>
              <th className="text-right pb-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-white/[0.03]">
                  <td colSpan={6} className="py-2">
                    <div className="h-4 bg-white/5 rounded animate-pulse" />
                  </td>
                </tr>
              ))
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-muted-foreground">
                  No decisions yet.{' '}
                  <Link to="/audit" className="text-primary hover:underline">Check Audit</Link>
                </td>
              </tr>
            ) : (
              <AnimatePresence initial={false}>
                {list.map((d, idx) => {
                  const v = (d?.verdict ?? '').toLowerCase() as keyof typeof verdictStyles;
                  const ts = d?.timestamp ?? d?.created_at;
                  const op = toolOp(d?.tool);
                  return (
                    <motion.tr
                      key={d?.id ?? `row-${idx}`}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.25 }}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors cursor-pointer"
                      onClick={() => d && onSelectDecision?.(d)}
                    >
                      <td className="py-2 pr-2">
                        <Badge className={`${verdictStyles[v] || 'badge-allowed'} text-[10px] px-1.5 py-0`}>
                          {d?.verdict ?? '—'}
                        </Badge>
                      </td>
                      <td className="py-2 pr-2">
                        <span className="font-mono text-foreground">{d?.agent_id ?? '—'}</span>
                      </td>
                      <td className="py-2 pr-2 hidden md:table-cell">
                        <span className="font-mono text-muted-foreground truncate max-w-[160px] block">{op}</span>
                      </td>
                      <td className="py-2 pr-2 hidden lg:table-cell">
                        {d?.reason_code ? (
                          <span className="text-red-400 font-medium">{d.reason_code}</span>
                        ) : (
                          <span className="text-muted-foreground/40">—</span>
                        )}
                      </td>
                      <td className="py-2 text-right font-mono text-muted-foreground">
                        {d?.latency_ms ?? '—'}
                      </td>
                      <td className="py-2 text-right text-muted-foreground whitespace-nowrap">
                        {formatTime(ts)}
                      </td>
                    </motion.tr>
                  );
                })}
              </AnimatePresence>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
