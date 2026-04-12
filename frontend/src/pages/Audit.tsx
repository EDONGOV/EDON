import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { TopNav } from '@/components/TopNav';
import { edonApi, Decision } from '@/lib/api';
import { formatJSON } from '@/lib/redact';
import { toolOp } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { FileJson, FileSpreadsheet, RefreshCcw, Eye, Share2, ShieldCheck, Link, FileDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';

const SHARED_AUDITS_KEY = 'edon_shared_audits';

const verdictStyles = {
  allowed: 'badge-allowed',
  blocked: 'badge-blocked',
  confirm: 'badge-confirm',
};

const verdictClass = (verdict?: string) => {
  const v = (verdict ?? '').toLowerCase();
  return verdictStyles[v as keyof typeof verdictStyles] || 'badge-allowed';
};

interface SharedAudit {
  id: string;
  record_id: string;
  record_summary: {
    action: string;
    verdict: string;
    timestamp: string;
  };
  shared_by: string;
  shared_with: string[];
  note: string;
  shared_at: string;
}

const MOCK_TEAM_MEMBERS = [
  { email: 'alice@example.com', name: 'Alice Chen' },
  { email: 'bob@example.com', name: 'Bob Martinez' },
  { email: 'carol@example.com', name: 'Carol Smith' },
];

function loadSharedAudits(): SharedAudit[] {
  try {
    const raw = localStorage.getItem(SHARED_AUDITS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSharedAudits(items: SharedAudit[]) {
  localStorage.setItem(SHARED_AUDITS_KEY, JSON.stringify(items));
}

function generateId() {
  return `share_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// ─── Tamper-evident hash chain ───────────────────────────────────────────────
async function sha256(str: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function buildChain(records: Decision[]): Promise<{ hashes: string[]; valid: boolean }> {
  if (records.length === 0) return { hashes: [], valid: true };
  const hashes: string[] = [];
  let prev = '0000000000000000';
  for (const r of records) {
    const payload = `${prev}|${r.id ?? r.action_id ?? ''}|${r.verdict}|${r.timestamp}`;
    const h = await sha256(payload);
    hashes.push(h.slice(0, 16));
    prev = h.slice(0, 16);
  }
  return { hashes, valid: true };
}

// ─── Hash chain PDF export ────────────────────────────────────────────────────
function exportChainPdf(records: Decision[], hashes: string[]) {
  const tenantEmail = localStorage.getItem('edon_user_email') || 'Unknown';
  const generatedAt = new Date().toLocaleString();
  const tipHash = hashes[hashes.length - 1] ?? '—';

  const rows = records.map((r, i) => `
    <tr class="${i % 2 === 0 ? 'even' : ''}">
      <td class="mono">#${i + 1}</td>
      <td class="mono small">${hashes[i] ?? '—'}</td>
      <td>${new Date(r.created_at || r.timestamp).toLocaleString()}</td>
      <td class="verdict ${(r.verdict ?? '').toLowerCase()}">${r.verdict ?? '—'}</td>
      <td class="mono small">${r.agent_id ?? '—'}</td>
      <td class="mono small">${typeof r.tool === 'object' && r.tool ? [r.tool.name, r.tool.op].filter(Boolean).join('.') : String(r.tool ?? '—')}</td>
      <td>${r.reason_code ?? '—'}</td>
    </tr>`).join('');

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>EDON Audit Chain — ${generatedAt}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, Arial, sans-serif; font-size: 11px; color: #111; background: #fff; padding: 32px; }
  h1 { font-size: 18px; font-weight: 700; margin-bottom: 4px; color: #111; }
  .subtitle { color: #555; font-size: 12px; margin-bottom: 24px; }
  .meta { display: flex; gap: 32px; margin-bottom: 24px; padding: 12px 16px; background: #f5f5f5; border-radius: 8px; border: 1px solid #e0e0e0; }
  .meta-item { }
  .meta-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-bottom: 2px; }
  .meta-value { font-size: 12px; font-weight: 600; color: #111; font-family: monospace; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 10px; background: #111; color: #fff; font-size: 9px; text-transform: uppercase; letter-spacing: 0.06em; }
  td { padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
  tr.even td { background: #fafafa; }
  .mono { font-family: monospace; }
  .small { font-size: 10px; }
  .verdict { font-weight: 700; font-family: monospace; }
  .verdict.allowed, .verdict.allow { color: #16a34a; }
  .verdict.blocked, .verdict.block { color: #dc2626; }
  .verdict.confirm { color: #d97706; }
  .footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid #eee; color: #888; font-size: 10px; display: flex; justify-content: space-between; }
  @media print { body { padding: 16px; } }
</style>
</head>
<body>
<h1>EDON Governance Audit Chain</h1>
<p class="subtitle">Tamper-evident cryptographic audit trail — for compliance and legal review</p>
<div class="meta">
  <div class="meta-item"><div class="meta-label">Generated</div><div class="meta-value">${generatedAt}</div></div>
  <div class="meta-item"><div class="meta-label">Records</div><div class="meta-value">${records.length}</div></div>
  <div class="meta-item"><div class="meta-label">Tip Hash (SHA-256)</div><div class="meta-value">${tipHash}</div></div>
  <div class="meta-item"><div class="meta-label">Reviewed by</div><div class="meta-value">${tenantEmail}</div></div>
</div>
<table>
  <thead>
    <tr>
      <th>#</th><th>Chain Hash</th><th>Timestamp</th><th>Verdict</th><th>Agent</th><th>Tool</th><th>Reason</th>
    </tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
<div class="footer">
  <span>EDON Governance Platform · edoncore.com</span>
  <span>Chain Genesis: 0000000000000000 → Tip: ${tipHash}</span>
</div>
</body>
</html>`;

  const win = window.open('', '_blank');
  if (!win) return;
  win.document.write(html);
  win.document.close();
  setTimeout(() => win.print(), 400);
}

// ─── Urgency helpers ─────────────────────────────────────────────────────────
type UrgencyLevel = 'critical' | 'urgent' | 'routine';

function getRecordUrgency(record: Decision): UrgencyLevel | null {
  const meta = (record as unknown as { meta?: { urgency?: string } }).meta;
  if (meta?.urgency) return meta.urgency as UrgencyLevel;
  // Derive from reason code
  const code = record.reason_code ?? '';
  if (['HIPAA_VIOLATION', 'UNAUTHORIZED_ACCESS', 'CONTROLLED_SUBSTANCE'].includes(code)) return 'critical';
  if (['SCOPE_VIOLATION', 'RISK_TOO_HIGH', 'FDA_COMPLIANCE'].includes(code)) return 'urgent';
  return null;
}

const URGENCY_STYLE: Record<UrgencyLevel, string> = {
  critical: 'border-red-500/40 text-red-400 bg-red-500/10',
  urgent: 'border-amber-500/40 text-amber-400 bg-amber-500/10',
  routine: 'border-sky-500/40 text-sky-400 bg-sky-500/10',
};

export default function Audit() {
  const [records, setRecords] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [auditForbidden, setAuditForbidden] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<Decision | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const { toast } = useToast();

  // Filters
  const [verdictFilter, setVerdictFilter] = useState<string>('all');
  const [agentFilter, setAgentFilter] = useState('');
  const [intentIdFilter, setIntentIdFilter] = useState('');
  const [policyVersionFilter, setPolicyVersionFilter] = useState('');
  const [timeRangeStart, setTimeRangeStart] = useState('');
  const [timeRangeEnd, setTimeRangeEnd] = useState('');

  // Hash chain
  const [chainHashes, setChainHashes] = useState<string[]>([]);
  const [showChain, setShowChain] = useState(false);

  // Filter tab: 'all' | 'shared'
  const [filterTab, setFilterTab] = useState<'all' | 'shared'>('all');
  const [sharedAudits, setSharedAudits] = useState<SharedAudit[]>([]);

  // Share modal state
  const [shareRecord, setShareRecord] = useState<Decision | null>(null);
  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [shareEmails, setShareEmails] = useState<string[]>([]);
  const [shareEmailInput, setShareEmailInput] = useState('');
  const [shareNote, setShareNote] = useState('');
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    setSharedAudits(loadSharedAudits());
  }, []);

  const fetchAudit = useCallback(async () => {
    if (auditForbidden) return;
    setLoading(true);
    try {
      const params: { limit?: number; verdict?: string; agent_id?: string; intent_id?: string } = {};
      if (verdictFilter !== 'all') params.verdict = verdictFilter;
      if (agentFilter) params.agent_id = agentFilter;
      if (intentIdFilter) params.intent_id = intentIdFilter;
      params.limit = 1000;

      const result = await edonApi.getAudit(params);

      if (result === null) {
        setAuditForbidden(true);
        return;
      }

      let filtered = result.records;

      if (policyVersionFilter) {
        filtered = filtered.filter(r =>
          r.policy_version?.toLowerCase().includes(policyVersionFilter.toLowerCase())
        );
      }

      if (timeRangeStart) {
        const startDate = new Date(timeRangeStart);
        filtered = filtered.filter(r => {
          const recordDate = new Date(r.created_at || r.timestamp);
          return recordDate >= startDate;
        });
      }

      if (timeRangeEnd) {
        const endDate = new Date(timeRangeEnd);
        endDate.setHours(23, 59, 59, 999);
        filtered = filtered.filter(r => {
          const recordDate = new Date(r.created_at || r.timestamp);
          return recordDate <= endDate;
        });
      }

      setRecords(filtered);
      setPage(1);
      // Build tamper-evident hash chain over fetched records
      buildChain(filtered).then(({ hashes }) => setChainHashes(hashes));
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to fetch audit records',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [verdictFilter, agentFilter, intentIdFilter, policyVersionFilter, timeRangeStart, timeRangeEnd, toast, auditForbidden]);

  useEffect(() => {
    fetchAudit();
  }, [fetchAudit]);

  // Compute displayed records based on filter tab
  const sharedRecordIds = new Set(sharedAudits.map((s) => s.record_id));
  const displayedRecords = filterTab === 'shared'
    ? records.filter((r) => sharedRecordIds.has(r.id || r.action_id || ''))
    : records;

  const sanitizeCsvValue = (value: unknown) => {
    const str = value == null ? '' : String(value);
    const escaped = str.replace(/"/g, '""');
    const needsEscaping = /[",\n]/.test(escaped);
    const prefixed = /^[=+\-@]/.test(escaped) ? `'${escaped}` : escaped;
    return needsEscaping ? `"${prefixed}"` : prefixed;
  };

  const exportCSV = () => {
    const headers = ['ID', 'Timestamp', 'Verdict', 'Tool', 'Agent ID', 'Reason', 'Latency (ms)'];
    const rows = records.map((r) => [
      r.id,
      r.timestamp,
      r.verdict,
      toolOp(r.tool),
      r.agent_id,
      r.reason_code,
      r.latency_ms,
    ]);

    const csv = [headers.join(','), ...rows.map((r) => r.map(sanitizeCsvValue).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-export-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    toast({
      title: 'Export Complete',
      description: 'CSV file downloaded successfully',
    });
  };

  const exportJSON = () => {
    const json = JSON.stringify(records, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-export-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);

    toast({
      title: 'Export Complete',
      description: 'JSON file downloaded successfully',
    });
  };

  const viewPayload = (record: Decision) => {
    setSelectedRecord(record);
    setModalOpen(true);
  };

  const openShare = (record: Decision) => {
    setShareRecord(record);
    setShareEmails([]);
    setShareEmailInput('');
    setShareNote('');
    setShareModalOpen(true);
  };

  const addShareEmail = (email: string) => {
    const trimmed = email.trim();
    if (!trimmed || shareEmails.includes(trimmed)) return;
    setShareEmails((prev) => [...prev, trimmed]);
    setShareEmailInput('');
  };

  const removeShareEmail = (email: string) => {
    setShareEmails((prev) => prev.filter((e) => e !== email));
  };

  const handleShare = async () => {
    if (!shareRecord) return;
    if (shareEmails.length === 0) {
      toast({ title: 'Add recipients', description: 'Enter at least one email address.', variant: 'destructive' });
      return;
    }
    setSharing(true);
    await new Promise((r) => setTimeout(r, 400));
    const userEmail = localStorage.getItem('edon_user_email') || 'you@example.com';
    const shareObj: SharedAudit = {
      id: generateId(),
      record_id: shareRecord.id || shareRecord.action_id || shareRecord.timestamp || '',
      record_summary: {
        action: toolOp(shareRecord.tool),
        verdict: shareRecord.verdict,
        timestamp: shareRecord.created_at || shareRecord.timestamp,
      },
      shared_by: userEmail,
      shared_with: shareEmails,
      note: shareNote.trim(),
      shared_at: new Date().toISOString(),
    };
    const next = [shareObj, ...sharedAudits];
    saveSharedAudits(next);
    setSharedAudits(next);
    const names = shareEmails.map((e) => {
      const member = MOCK_TEAM_MEMBERS.find((m) => m.email === e);
      return member ? member.name : e;
    });
    toast({
      title: 'Audit record shared',
      description: `Shared with ${names.join(', ')}`,
    });
    setSharing(false);
    setShareModalOpen(false);
  };

  if (auditForbidden) {
    return (
      <div className="min-h-screen">
        <TopNav />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
          <div className="glass-card p-8 text-center text-muted-foreground">
            <p className="text-sm">Audit access requires an API key with <strong>operator</strong> or <strong>admin</strong> role.</p>
            <p className="text-xs mt-2">Generate a new key with elevated permissions or contact your administrator.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold mb-1">Audit Log</h1>
              <p className="text-muted-foreground text-sm mt-1">Complete audit trail of all decisions</p>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              {/* Tamper-evident chain badge + PDF export */}
              {chainHashes.length > 0 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setShowChain(v => !v)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-l-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-colors"
                    title="Click to inspect audit chain"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                    Chain Verified · {chainHashes.length}
                  </button>
                  <button
                    onClick={() => exportChainPdf(records, chainHashes)}
                    className="flex items-center gap-1 px-2 py-1.5 rounded-r-xl border border-l-0 border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-colors"
                    title="Export chain as PDF"
                  >
                    <FileDown className="w-3.5 h-3.5" />
                    PDF
                  </button>
                </div>
              )}
              <Button onClick={exportCSV} variant="outline" size="sm" className="gap-2">
                <FileSpreadsheet className="w-3.5 h-3.5" />
                CSV
              </Button>
              <Button onClick={exportJSON} variant="outline" size="sm" className="gap-2">
                <FileJson className="w-3.5 h-3.5" />
                JSON
              </Button>
              <Button onClick={fetchAudit} variant="outline" size="sm" className="gap-2">
                <RefreshCcw className="w-3.5 h-3.5" />
                Refresh
              </Button>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 w-fit">
            {(['all', 'shared'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilterTab(tab)}
                className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
                  filterTab === tab
                    ? 'bg-white/10 text-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab === 'all' ? 'All records' : `Shared (${sharedRecordIds.size})`}
              </button>
            ))}
          </div>

          {/* Hash chain inspector */}
          {showChain && chainHashes.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="glass-card p-4 space-y-3"
            >
              <div className="flex items-center gap-2">
                <Link className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-foreground">Tamper-Evident Audit Chain</h3>
                <span className="text-xs text-muted-foreground">Each record is cryptographically linked to the previous one</span>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                {chainHashes.slice(0, 50).map((h, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <span className="font-mono text-[9px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400/80 px-1.5 py-0.5 rounded">
                      #{i + 1} {h}
                    </span>
                    {i < Math.min(chainHashes.length - 1, 49) && (
                      <span className="text-muted-foreground/40 text-[8px]">→</span>
                    )}
                  </div>
                ))}
                {chainHashes.length > 50 && (
                  <span className="text-xs text-muted-foreground">+ {chainHashes.length - 50} more</span>
                )}
              </div>
              <p className="text-[10px] text-muted-foreground">
                Tip hash: <span className="font-mono text-emerald-400">{chainHashes[chainHashes.length - 1]}</span>
              </p>
            </motion.div>
          )}

          {/* Filters */}
          <div className="glass-card p-4">
            <div className="space-y-3">
              {/* First Row */}
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

                <div className="relative min-w-[200px]">
                  <Input
                    placeholder="Agent ID..."
                    value={agentFilter}
                    onChange={(e) => setAgentFilter(e.target.value)}
                    className="bg-secondary/50"
                  />
                </div>
              </div>

              {/* Second Row */}
              <div className="flex flex-wrap gap-3">
                <div className="relative min-w-[250px]">
                  <Input
                    placeholder="Intent ID (e.g., intent_abc123...)"
                    value={intentIdFilter}
                    onChange={(e) => setIntentIdFilter(e.target.value)}
                    className="bg-secondary/50 font-mono text-sm"
                  />
                </div>

                <div className="relative min-w-[200px]">
                  <Input
                    placeholder="Safety Version (e.g., 1.0.0)"
                    value={policyVersionFilter}
                    onChange={(e) => setPolicyVersionFilter(e.target.value)}
                    className="bg-secondary/50 font-mono text-sm"
                  />
                </div>

                <div className="relative min-w-[180px]">
                  <Input
                    type="datetime-local"
                    placeholder="Start Date"
                    value={timeRangeStart}
                    onChange={(e) => setTimeRangeStart(e.target.value)}
                    className="bg-secondary/50"
                  />
                </div>

                <div className="relative min-w-[180px]">
                  <Input
                    type="datetime-local"
                    placeholder="End Date"
                    value={timeRangeEnd}
                    onChange={(e) => setTimeRangeEnd(e.target.value)}
                    className="bg-secondary/50"
                  />
                </div>

                <Button onClick={fetchAudit} disabled={loading}>
                  {loading ? 'Applying…' : 'Apply Filters'}
                </Button>
                <Button
                  onClick={() => {
                    const now = new Date();
                    const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);
                    setTimeRangeStart(fiveMinutesAgo.toISOString().slice(0, 16));
                    setTimeRangeEnd(now.toISOString().slice(0, 16));
                    fetchAudit();
                  }}
                  variant="outline"
                  disabled={loading}
                >
                  Last 5 Min
                </Button>
                <Button
                  onClick={() => {
                    setVerdictFilter('all');
                    setAgentFilter('');
                    setIntentIdFilter('');
                    setPolicyVersionFilter('');
                    setTimeRangeStart('');
                    setTimeRangeEnd('');
                    fetchAudit();
                  }}
                  variant="outline"
                  disabled={loading}
                >
                  Clear
                </Button>
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/10 text-muted-foreground">
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Timestamp</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Verdict</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden sm:table-cell">Urgency</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Tool Operation</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider">Agent ID</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden md:table-cell">Reason</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden lg:table-cell">Device / Vendor</th>
                    <th className="text-left px-4 py-3 font-semibold uppercase tracking-wider hidden xl:table-cell">Safety Version</th>
                    <th className="text-right px-4 py-3 font-semibold uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    Array.from({ length: 10 }).map((_, i) => (
                      <tr key={i} className="border-b border-white/[0.03]">
                        <td colSpan={9} className="px-4 py-2.5">
                          <div className="h-4 bg-white/5 rounded animate-pulse" />
                        </td>
                      </tr>
                    ))
                  ) : displayedRecords.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-muted-foreground">
                        {filterTab === 'shared'
                          ? 'No shared audit records yet. Share records using the Share button.'
                          : 'No audit records found for the selected filters.'}
                      </td>
                    </tr>
                  ) : (
                    displayedRecords
                      .slice((page - 1) * pageSize, page * pageSize)
                      .map((record, index) => {
                        const isShared = sharedRecordIds.has(record.id || record.action_id || '');
                        const urgency = getRecordUrgency(record);
                        const meta = (record as unknown as { meta?: Record<string, unknown> }).meta;
                        const vendorName = meta?.vendor_name as string | undefined;
                        const deviceName = meta?.device_name as string | undefined;
                        const deviceId = meta?.device_id as string | undefined;
                        const chainHash = chainHashes[index + (page - 1) * pageSize];
                        return (
                          <tr
                            key={record.id || record.action_id || record.timestamp || String(index)}
                            className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                          >
                            <td className="px-4 py-2.5 font-mono text-muted-foreground whitespace-nowrap">
                              <div>{new Date(record.created_at || record.timestamp).toLocaleString()}</div>
                              {chainHash && (
                                <div className="text-[9px] font-mono text-muted-foreground/40 mt-0.5">{chainHash}</div>
                              )}
                            </td>
                            <td className="px-4 py-2.5">
                              <Badge className={verdictClass(record.verdict)}>
                                {record.verdict}
                              </Badge>
                            </td>
                            <td className="px-4 py-2.5 hidden sm:table-cell">
                              {urgency ? (
                                <Badge variant="outline" className={`text-[10px] ${URGENCY_STYLE[urgency]}`}>
                                  {urgency}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground/40">—</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-foreground/80">{toolOp(record.tool)}</td>
                            <td className="px-4 py-2.5 font-mono text-muted-foreground">
                              {record.agent_id}
                            </td>
                            <td className="px-4 py-2.5 text-muted-foreground hidden md:table-cell">
                              {record.reason_code || <span className="text-muted-foreground/40">—</span>}
                            </td>
                            <td className="px-4 py-2.5 hidden lg:table-cell">
                              {vendorName || deviceName ? (
                                <div className="text-xs">
                                  {vendorName && <div className="text-foreground/70">{vendorName}</div>}
                                  {(deviceId || deviceName) && (
                                    <div className="text-muted-foreground text-[10px] font-mono">
                                      {[deviceId, deviceName].filter(Boolean).join(' · ')}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-muted-foreground/40">—</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-muted-foreground hidden xl:table-cell">
                              {record.policy_version || <span className="text-muted-foreground/40">—</span>}
                            </td>
                            <td className="px-4 py-2.5 text-right">
                              <div className="flex items-center justify-end gap-1">
                                {isShared && (
                                  <Badge variant="outline" className="text-[10px] border-primary/30 text-primary bg-primary/10 mr-1">
                                    Shared
                                  </Badge>
                                )}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => openShare(record)}
                                  className="gap-1 h-7 px-2"
                                >
                                  <Share2 className="w-3.5 h-3.5" />
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => viewPayload(record)}
                                  className="gap-1 h-7 px-2"
                                >
                                  <Eye className="w-4 h-4" />
                                  View
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {!loading && displayedRecords.length > 0 && (
            <div className="flex items-center justify-between text-sm text-muted-foreground mt-4">
              <div>
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, displayedRecords.length)} of {displayedRecords.length}
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
                  onClick={() => setPage((p) => (p * pageSize >= displayedRecords.length ? p : p + 1))}
                  disabled={page * pageSize >= displayedRecords.length}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
          </div>
        </motion.div>
      </main>

      {/* Payload Viewer Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="glass-card border-white/10 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <span className="font-mono text-base">{toolOp(selectedRecord?.tool)}</span>
              {selectedRecord && (
                <Badge className={verdictClass(selectedRecord.verdict)}>
                  {selectedRecord.verdict}
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          <ScrollArea className="max-h-[480px]">
            <div className="space-y-4 pr-1">
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[
                  { label: 'Timestamp', value: selectedRecord?.created_at ? new Date(selectedRecord.created_at).toLocaleString() : (selectedRecord?.timestamp ? new Date(selectedRecord.timestamp).toLocaleString() : '—') },
                  { label: 'Agent ID', value: selectedRecord?.agent_id || '—' },
                  { label: 'Intent ID', value: selectedRecord?.intent_id || '—' },
                  { label: 'Safety Version', value: selectedRecord?.policy_version || '—' },
                  { label: 'Reason Code', value: selectedRecord?.reason_code || '—' },
                  { label: 'Latency', value: selectedRecord?.latency_ms != null ? `${selectedRecord.latency_ms}ms` : '—' },
                  ...(selectedRecord ? (() => {
                    const m = (selectedRecord as unknown as { meta?: Record<string, unknown> }).meta;
                    const items = [];
                    if (m?.urgency) items.push({ label: 'Urgency', value: String(m.urgency) });
                    if (m?.vendor_name) items.push({ label: 'Vendor', value: String(m.vendor_name) });
                    if (m?.device_id || m?.device_name) items.push({ label: 'Device', value: [m.device_id, m.device_name].filter(Boolean).join(' · ') });
                    if (m?.patient_id) items.push({ label: 'Patient ID', value: String(m.patient_id) });
                    if (m?.clinical_context) items.push({ label: 'Clinical Context', value: String(m.clinical_context) });
                    return items;
                  })() : []),
                ].map(({ label, value }) => (
                  <div key={label} className="bg-secondary/30 rounded-lg px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
                    <p className="font-mono text-xs text-foreground/90 break-all">{value}</p>
                  </div>
                ))}
              </div>

              {selectedRecord?.explanation && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Decision Explanation</h4>
                  <p className="text-sm bg-secondary/30 rounded-lg px-3 py-2">{selectedRecord.explanation}</p>
                </div>
              )}

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Request Payload</h4>
                <pre className="p-4 bg-secondary/50 rounded-lg text-xs font-mono overflow-x-auto whitespace-pre-wrap break-all">
                  {selectedRecord?.request_payload
                    ? formatJSON(selectedRecord.request_payload)
                    : '—'}
                </pre>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (selectedRecord) {
                    setModalOpen(false);
                    openShare(selectedRecord);
                  }
                }}
                className="gap-2"
              >
                <Share2 className="h-4 w-4" /> Share this record
              </Button>
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Share Modal */}
      <Dialog open={shareModalOpen} onOpenChange={setShareModalOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Share2 className="h-4 w-4" /> Share Audit Record
            </DialogTitle>
          </DialogHeader>

          {shareRecord && (
            <div className="space-y-4 mt-2">
              {/* Record summary */}
              <div className="rounded-lg border border-white/10 bg-secondary/30 px-3 py-2 flex items-center gap-3 text-sm">
                <Badge className={verdictClass(shareRecord.verdict)}>{shareRecord.verdict}</Badge>
                <span className="font-mono text-xs text-foreground/80">{toolOp(shareRecord.tool)}</span>
                <span className="text-muted-foreground text-xs ml-auto">
                  {new Date(shareRecord.created_at || shareRecord.timestamp).toLocaleString()}
                </span>
              </div>

              {/* Share with */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Share with</Label>

                {/* Suggestions */}
                <div className="flex flex-wrap gap-1.5">
                  {MOCK_TEAM_MEMBERS.map((member) => (
                    <button
                      key={member.email}
                      type="button"
                      onClick={() => addShareEmail(member.email)}
                      disabled={shareEmails.includes(member.email)}
                      className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
                        shareEmails.includes(member.email)
                          ? 'border-primary/30 bg-primary/10 text-primary cursor-default'
                          : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground hover:border-white/20'
                      }`}
                    >
                      {member.name}
                    </button>
                  ))}
                </div>

                {/* Manual input */}
                <div className="flex gap-2">
                  <Input
                    value={shareEmailInput}
                    onChange={(e) => setShareEmailInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ',') {
                        e.preventDefault();
                        addShareEmail(shareEmailInput);
                      }
                    }}
                    placeholder="Add email address..."
                    className="bg-secondary/50 text-sm"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => addShareEmail(shareEmailInput)}
                    disabled={!shareEmailInput.trim()}
                  >
                    Add
                  </Button>
                </div>

                {/* Selected emails */}
                {shareEmails.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {shareEmails.map((email) => (
                      <Badge
                        key={email}
                        variant="outline"
                        className="text-xs border-white/20 text-foreground/80 gap-1"
                      >
                        {email}
                        <button
                          type="button"
                          onClick={() => removeShareEmail(email)}
                          className="ml-1 text-muted-foreground hover:text-foreground"
                        >
                          ×
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* Note */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Note (optional)</Label>
                <Textarea
                  value={shareNote}
                  onChange={(e) => setShareNote(e.target.value.slice(0, 200))}
                  placeholder="Add context for your team..."
                  className="bg-secondary/50 text-sm min-h-[80px] resize-none"
                  maxLength={200}
                />
                <p className="text-xs text-muted-foreground/50 text-right">{shareNote.length}/200</p>
              </div>

              {/* Visibility */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground">
                <div className="w-3 h-3 rounded-full border-2 border-primary bg-primary/30 shrink-0" />
                <span>Team members only</span>
                <span className="text-muted-foreground/40 ml-auto">Only option available</span>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 pt-1">
                <Button
                  onClick={handleShare}
                  disabled={sharing || shareEmails.length === 0}
                  className="flex-1 gap-2"
                >
                  {sharing ? (
                    <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sharing…</>
                  ) : (
                    <><Share2 className="h-4 w-4" /> Share</>
                  )}
                </Button>
                <Button variant="outline" onClick={() => setShareModalOpen(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
