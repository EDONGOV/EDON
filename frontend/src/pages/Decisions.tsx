import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { TopNav } from '@/components/TopNav';
import { DecisionDrawer } from '@/components/DecisionDrawer';
import { edonApi, Decision } from '@/lib/api';
import { toolOp } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Search, RefreshCcw, Download, ListChecks } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';

const verdictStyles = {
  allowed: 'badge-allowed',
  blocked: 'badge-blocked',
  confirm: 'badge-confirm',
};

const verdictClass = (verdict?: string) => {
  const v = (verdict ?? '').toLowerCase();
  return verdictStyles[v as keyof typeof verdictStyles] || 'badge-allowed';
};

export default function Decisions() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showAuditFallback, setShowAuditFallback] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const { toast } = useToast();
  
  // Filters
  const [verdictFilter, setVerdictFilter] = useState<string>('all');
  const [toolFilter, setToolFilter] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [intentIdFilter, setIntentIdFilter] = useState('');
  const [policyVersionFilter, setPolicyVersionFilter] = useState('');
  const [timeRangeStart, setTimeRangeStart] = useState('');
  const [timeRangeEnd, setTimeRangeEnd] = useState('');

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    setShowAuditFallback(false);
    try {
      const activeIntentId = typeof window !== 'undefined' ? (localStorage.getItem('edon_active_intent_id') || '').trim() : '';
      const params: { verdict?: string; tool?: string; intent_id?: string; limit?: number } = {};
      if (activeIntentId) params.intent_id = activeIntentId;
      params.limit = 50;
      if (verdictFilter !== 'all') params.verdict = verdictFilter;
      if (toolFilter) params.tool = toolFilter;
      
      const result = await edonApi.getDecisions(params);
      let list = Array.isArray(result?.decisions) ? result.decisions : [];
      
      // Client-side filtering (no agent_id on main stream)
      if (intentIdFilter) {
        list = list.filter(d => d?.intent_id?.includes(intentIdFilter));
      }
      if (agentFilter) {
        list = list.filter(d => d?.agent_id?.includes(agentFilter));
      }
      if (policyVersionFilter) {
        list = list.filter(d => 
          d?.policy_version?.toLowerCase().includes(policyVersionFilter.toLowerCase())
        );
      }
      
      if (timeRangeStart) {
        const startDate = new Date(timeRangeStart);
        list = list.filter(d => {
          const decisionDate = new Date(d?.created_at ?? d?.timestamp ?? 0);
          return decisionDate >= startDate;
        });
      }
      
      if (timeRangeEnd) {
        const endDate = new Date(timeRangeEnd);
        endDate.setHours(23, 59, 59, 999); // End of day
        list = list.filter(d => {
          const decisionDate = new Date(d?.created_at ?? d?.timestamp ?? 0);
          return decisionDate <= endDate;
        });
      }
      
      if (list.length > 0) {
        setDecisions(list);
      } else {
        const audit = await edonApi.getAudit({ limit: 1000 });
        const records = Array.isArray(audit?.records) ? audit.records : [];
        setDecisions(records);
        setShowAuditFallback(records.length > 0);
      }
      setPage(1);
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error('Failed to fetch decisions:', error);
      }
      setDecisions([]);
      toast({
        title: 'Error',
        description: 'Failed to fetch decisions. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [
    verdictFilter,
    toolFilter,
    intentIdFilter,
    agentFilter,
    policyVersionFilter,
    timeRangeStart,
    timeRangeEnd,
    toast,
  ]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  const handleSelectDecision = (decision: Decision) => {
    setSelectedDecision(decision);
    setDrawerOpen(true);
  };

  const exportDecisions = (format: 'json' | 'csv') => {
    if (decisions.length === 0) return;
    let content: string;
    let mime: string;
    let ext: string;
    if (format === 'json') {
      content = JSON.stringify(decisions, null, 2);
      mime = 'application/json';
      ext = 'json';
    } else {
      const headers = ['id','timestamp','verdict','tool','agent_id','reason_code','intent_id','policy_version','latency_ms'];
      const rows = decisions.map((d) => [
        d.id ?? '',
        d.timestamp ?? d.created_at ?? '',
        d.verdict ?? '',
        typeof d.tool === 'object' && d.tool ? [d.tool.name, d.tool.op].filter(Boolean).join('.') : String(d.tool ?? ''),
        d.agent_id ?? '',
        d.reason_code ?? '',
        d.intent_id ?? '',
        d.policy_version ?? '',
        d.latency_ms ?? '',
      ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
      content = [headers.join(','), ...rows].join('\n');
      mime = 'text/csv';
      ext = 'csv';
    }
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `edon-decisions-${new Date().toISOString().slice(0,10)}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: `Exported ${decisions.length} decisions as ${ext.toUpperCase()}` });
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="space-y-6">
          {typeof window !== "undefined" && !(localStorage.getItem("edon_active_intent_id") ?? "").trim() && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              No active intent. Apply a policy pack first.
            </div>
          )}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold mb-1">Decisions</h1>
              <p className="text-muted-foreground text-sm mt-1">View and analyze all agent decisions</p>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={() => exportDecisions('csv')} variant="outline" size="sm" className="gap-1.5 text-xs" disabled={decisions.length === 0}>
                <Download className="w-3.5 h-3.5" /> CSV
              </Button>
              <Button onClick={() => exportDecisions('json')} variant="outline" size="sm" className="gap-1.5 text-xs" disabled={decisions.length === 0}>
                <Download className="w-3.5 h-3.5" /> JSON
              </Button>
              <Button onClick={fetchDecisions} variant="outline" size="sm" className="gap-1.5">
                <RefreshCcw className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Filters */}
          <div className="glass-card p-4">
            <div className="flex flex-wrap gap-3">
              <Select value={verdictFilter} onValueChange={setVerdictFilter}>
                <SelectTrigger className="w-[180px] bg-secondary/50">
                  <SelectValue placeholder="Filter by verdict" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Verdicts</SelectItem>
                  <SelectItem value="allowed">Allowed</SelectItem>
                  <SelectItem value="blocked">Blocked</SelectItem>
                  <SelectItem value="confirm">Confirm</SelectItem>
                </SelectContent>
              </Select>

              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Filter by tool operation..."
                  value={toolFilter}
                  onChange={(e) => setToolFilter(e.target.value)}
                  className="pl-10 bg-secondary/50"
                />
              </div>

              <div className="relative min-w-[200px]">
                <Input
                  placeholder="Agent ID..."
                  value={agentFilter}
                  onChange={(e) => setAgentFilter(e.target.value)}
                  className="bg-secondary/50"
                />
              </div>

              <Button onClick={fetchDecisions} disabled={loading} variant="outline" size="sm">
                {loading ? 'Applying…' : 'Apply Filters'}
              </Button>
              <Button 
                onClick={() => {
                  const now = new Date();
                  const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);
                  setTimeRangeStart(fiveMinutesAgo.toISOString().slice(0, 16));
                  setTimeRangeEnd(now.toISOString().slice(0, 16));
                  fetchDecisions();
                }}
                variant="outline"
                disabled={loading}
              >
                Last 5 Min
              </Button>
              <Button 
                onClick={() => {
                  setVerdictFilter('all');
                  setToolFilter('');
                  setAgentFilter('');
                  setIntentIdFilter('');
                  setPolicyVersionFilter('');
                  setTimeRangeStart('');
                  setTimeRangeEnd('');
                  fetchDecisions();
                }}
                variant="outline"
                disabled={loading}
              >
                Clear
              </Button>
            </div>
          </div>

          {showAuditFallback && (
            <div className="glass-card p-3 mb-4 border border-amber-500/30 bg-amber-500/5 rounded-lg text-sm text-muted-foreground">
              Showing audit fallback; no decisions found for active intent.{' '}
              <Link to="/audit" className="text-primary hover:underline">Open Audit</Link>
            </div>
          )}

          {/* Table */}
          <div className="glass-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="border-white/10 hover:bg-white/5">
                  <TableHead className="text-muted-foreground">Timestamp</TableHead>
                  <TableHead className="text-muted-foreground">Verdict</TableHead>
                  <TableHead className="text-muted-foreground">Tool Operation</TableHead>
                  <TableHead className="text-muted-foreground">Agent ID</TableHead>
                  <TableHead className="text-muted-foreground">Reason</TableHead>
                  <TableHead className="text-muted-foreground">Intent ID</TableHead>
                  <TableHead className="text-muted-foreground">Policy Version</TableHead>
                  <TableHead className="text-muted-foreground text-right">Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <TableRow key={i} className="border-white/10">
                      <TableCell colSpan={8}>
                        <div className="h-8 bg-white/5 rounded animate-pulse" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (decisions ?? []).length === 0 ? (
                  <TableRow className="border-white/10">
                    <TableCell colSpan={8} className="py-16 text-center">
                      <div className="flex flex-col items-center gap-3">
                        <div className="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                          <ListChecks className="w-5 h-5 text-muted-foreground/50" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-muted-foreground">No decisions yet</p>
                          <p className="text-xs text-muted-foreground/60 mt-1">
                            Decisions appear here once agents start sending actions through EDON.
                          </p>
                        </div>
                        <Link to="/audit" className="text-xs text-primary hover:underline">Check Audit →</Link>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  (decisions ?? [])
                    .slice((page - 1) * pageSize, page * pageSize)
                    .map((decision, idx) => (
                      <TableRow
                        key={decision?.id ?? `row-${idx}`}
                        className="border-white/10 cursor-pointer hover:bg-white/5 transition-colors"
                        onClick={() => decision && handleSelectDecision(decision)}
                      >
                        <TableCell className="font-mono text-sm">
                          {decision?.created_at ?? decision?.timestamp
                            ? new Date(decision.created_at ?? decision.timestamp).toLocaleString()
                            : '—'}
                        </TableCell>
                        <TableCell>
                          <Badge className={verdictClass(decision?.verdict)}>
                            {decision?.verdict ?? '—'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono">{toolOp(decision?.tool)}</TableCell>
                        <TableCell className="font-mono text-muted-foreground">
                          {decision?.agent_id ?? '—'}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {decision?.reason_code ?? '—'}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {decision?.intent_id ? (
                            <span className="truncate max-w-[200px] block" title={decision.intent_id}>
                              {decision.intent_id}
                            </span>
                          ) : (
                            <span className="text-muted-foreground/50">—</span>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {decision?.policy_version ?? <span className="text-muted-foreground/50">—</span>}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {decision?.latency_ms != null ? `${decision.latency_ms}ms` : '—'}
                        </TableCell>
                      </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          {!loading && (decisions ?? []).length > 0 && (
            <div className="flex items-center justify-between text-sm text-muted-foreground mt-4">
              <div>
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, (decisions ?? []).length)} of {(decisions ?? []).length}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  Prev
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => (p * pageSize >= (decisions ?? []).length ? p : p + 1))}
                  disabled={page * pageSize >= (decisions ?? []).length}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
          </div>
        </motion.div>
      </main>

      <DecisionDrawer
        decision={selectedDecision}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
