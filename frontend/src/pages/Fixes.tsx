import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Wrench, RefreshCcw, CheckCircle2, XCircle, Loader2, AlertTriangle,
  ChevronRight, Shield, Zap, Eye, Play, ToggleLeft, ToggleRight,
  ArrowRight, Clock, AlertCircle, ShieldCheck, Rocket, CircleDot,
} from 'lucide-react';
import { TopNav } from '@/components/TopNav';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { edonApi, FixProposal, HealingResult, HealingVerification } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

type FilterTab = 'all' | 'pending_review' | 'approved' | 'applied' | 'rejected';

// ─── Pipeline stages ──────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { id: 'shadow',   label: 'Shadow Detection',   icon: Eye,         desc: 'Shadow engine detects divergence' },
  { id: 'proposal', label: 'Proposal Generated', icon: Wrench,      desc: 'EDON generates a fix proposal' },
  { id: 'review',   label: 'Pending Review',     icon: Clock,       desc: 'Human reviews and approves' },
  { id: 'deployed', label: 'Rule Deployed',      icon: Rocket,      desc: 'Healing rule is live' },
  { id: 'verified', label: 'Verified',           icon: ShieldCheck, desc: 'Post-deploy verification passed' },
];

function proposalStage(p: FixProposal): number {
  if (p.status === 'applied') return 4; // verified
  if (p.status === 'approved') return 3; // deployed
  if (p.status === 'pending_review') return 2; // review
  return 1; // proposal generated (rejected stays here)
}

// ─── Status colours ───────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  pending_review: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
  approved:       'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
  applied:        'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  rejected:       'bg-slate-600/30 text-slate-400 border border-slate-600/40',
};

const STATUS_LABELS: Record<string, string> = {
  pending_review: 'Pending Review',
  approved:       'Approved',
  applied:        'Applied',
  rejected:       'Rejected',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-400 border border-red-500/30',
  advisory: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
};

const ACTION_COLORS: Record<string, string> = {
  BLOCK:    'bg-red-500/15 text-red-400 border border-red-500/30',
  ESCALATE: 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
};

// ─── Mock fallback proposals (shown when API returns empty/404) ────────────────

const MOCK_PROPOSALS: FixProposal[] = [
  {
    proposal_id: 'fix-001',
    trace_id: 'trace-a1b2',
    perturbation_name: 'FieldNullation',
    perturbation_type: 'field_removal',
    severity: 'critical',
    original_verdict: 'ALLOW',
    shadow_verdict: 'BLOCK',
    perturbed_field: 'patient_consent',
    suggested_action: 'BLOCK',
    condition_tool: 'ehr_write',
    condition_op: 'field_null',
    rule_description: 'Block EHR writes when patient_consent is null',
    rationale: 'Shadow engine found that removing patient_consent flips the verdict from ALLOW to BLOCK, revealing an unguarded path in the EHR write policy.',
    tenant_id: null,
    agent_id: 'apex-medical-agent',
    action_type: 'ehr.write',
    status: 'pending_review',
    created_at: new Date(Date.now() - 8 * 60000).toISOString(),
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
  },
  {
    proposal_id: 'fix-002',
    trace_id: 'trace-c3d4',
    perturbation_name: 'RoleEscalation',
    perturbation_type: 'value_substitution',
    severity: 'critical',
    original_verdict: 'ALLOW',
    shadow_verdict: 'BLOCK',
    perturbed_field: 'user_role',
    suggested_action: 'BLOCK',
    condition_tool: 'admin_api',
    condition_op: 'role_change',
    rule_description: 'Block admin_api calls when user_role is escalated beyond granted scope',
    rationale: 'Substituting user_role to "superadmin" caused the shadow engine to produce a BLOCK — the production policy has no guard on role elevation.',
    tenant_id: null,
    agent_id: 'apex-ops-agent',
    action_type: 'admin.role_update',
    status: 'approved',
    created_at: new Date(Date.now() - 45 * 60000).toISOString(),
    resolved_at: new Date(Date.now() - 30 * 60000).toISOString(),
    resolved_by: 'admin@example.com',
    resolution_note: 'Confirmed — role guard was missing. Approved for deployment.',
  },
  {
    proposal_id: 'fix-003',
    trace_id: 'trace-e5f6',
    perturbation_name: 'OutsideHours',
    perturbation_type: 'temporal_shift',
    severity: 'advisory',
    original_verdict: 'ALLOW',
    shadow_verdict: 'ESCALATE',
    perturbed_field: 'request_timestamp',
    suggested_action: 'ESCALATE',
    condition_tool: null,
    condition_op: null,
    rule_description: 'Escalate outreach emails sent outside business hours',
    rationale: 'Shifting the timestamp to 2 AM caused the shadow engine to escalate — after-hours email sends should require human confirmation.',
    tenant_id: null,
    agent_id: 'apex-outreach-agent',
    action_type: 'email.send',
    status: 'applied',
    created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    resolved_at: new Date(Date.now() - 90 * 60000).toISOString(),
    resolved_by: 'admin@example.com',
    resolution_note: 'Deployed and verified — 3 states mitigated post-deploy.',
  },
  {
    proposal_id: 'fix-004',
    trace_id: 'trace-g7h8',
    perturbation_name: 'DataExfil',
    perturbation_type: 'payload_expansion',
    severity: 'advisory',
    original_verdict: 'ALLOW',
    shadow_verdict: 'BLOCK',
    perturbed_field: 'export_fields',
    suggested_action: 'BLOCK',
    condition_tool: 'data_export',
    condition_op: 'field_count_gt',
    rule_description: 'Block data exports with more than 50 fields',
    rationale: 'Expanding export_fields to include PII columns caused a BLOCK verdict in shadow — the current policy does not limit field counts on bulk exports.',
    tenant_id: null,
    agent_id: 'apex-research-agent',
    action_type: 'data.export',
    status: 'rejected',
    created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
    resolved_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    resolved_by: 'admin@example.com',
    resolution_note: 'Rejected — existing DLP policy already covers this case.',
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function Fixes() {
  const { toast } = useToast();

  const [proposals, setProposals] = useState<FixProposal[]>([]);
  const [counts, setCounts] = useState({ total: 0, pending: 0, approved: 0, rejected: 0, applied: 0 });
  const [loading, setLoading] = useState(true);
  const [filterTab, setFilterTab] = useState<FilterTab>('all');
  const [selected, setSelected] = useState<FixProposal | null>(null);

  const [autoEnabled, setAutoEnabled] = useState(false);
  const [healingLoading, setHealingLoading] = useState(false);
  const [lastRun, setLastRun] = useState<HealingResult | null>(null);

  const [noteText, setNoteText] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [deployResult, setDeployResult] = useState<{ rule_id: string; verification: HealingVerification } | null>(null);

  const [usingMock, setUsingMock] = useState(false);

  // ── Fetch proposals ──────────────────────────────────────────────────────────
  const fetchProposals = useCallback(async () => {
    setLoading(true);
    try {
      const data = await edonApi.getFixProposals({ limit: 100 });
      if (data.proposals.length === 0) {
        setProposals(MOCK_PROPOSALS);
        setCounts({
          total: MOCK_PROPOSALS.length,
          pending: MOCK_PROPOSALS.filter(p => p.status === 'pending_review').length,
          approved: MOCK_PROPOSALS.filter(p => p.status === 'approved').length,
          rejected: MOCK_PROPOSALS.filter(p => p.status === 'rejected').length,
          applied: MOCK_PROPOSALS.filter(p => p.status === 'applied').length,
        });
        setUsingMock(true);
      } else {
        setProposals(data.proposals);
        setCounts({ total: data.total, pending: data.pending, approved: data.approved, rejected: data.rejected, applied: data.applied });
        setUsingMock(false);
      }
    } catch {
      // API not yet implemented — use mock data
      setProposals(MOCK_PROPOSALS);
      setCounts({
        total: MOCK_PROPOSALS.length,
        pending: MOCK_PROPOSALS.filter(p => p.status === 'pending_review').length,
        approved: MOCK_PROPOSALS.filter(p => p.status === 'approved').length,
        rejected: MOCK_PROPOSALS.filter(p => p.status === 'rejected').length,
        applied: MOCK_PROPOSALS.filter(p => p.status === 'applied').length,
      });
      setUsingMock(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Fetch healing status ─────────────────────────────────────────────────────
  const fetchHealingStatus = useCallback(async () => {
    try {
      const s = await edonApi.getHealingStatus();
      setAutoEnabled(s.auto_enabled);
      setLastRun(s.last_run);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchProposals();
    fetchHealingStatus();
  }, [fetchProposals, fetchHealingStatus]);

  // ── Run healing pass ─────────────────────────────────────────────────────────
  const handleRunHealing = async () => {
    setHealingLoading(true);
    try {
      const result = await edonApi.runHealingPass(true);
      setLastRun(result);
      toast({ title: 'Healing pass complete', description: `${result.rules_deployed} rule(s) deployed, ${result.states_mitigated} state(s) mitigated.` });
      fetchProposals();
    } catch {
      toast({ title: 'Healing pass failed', description: 'The endpoint may not be available yet.', variant: 'destructive' });
    } finally {
      setHealingLoading(false);
    }
  };

  // ── Approve proposal ─────────────────────────────────────────────────────────
  const handleApprove = async (p: FixProposal) => {
    setActionLoading(true);
    try {
      if (usingMock) {
        const updated = { ...p, status: 'approved' as const, resolved_at: new Date().toISOString(), resolved_by: 'admin@example.com', resolution_note: noteText || null };
        setProposals(prev => prev.map(x => x.proposal_id === p.proposal_id ? updated : x));
        setSelected(updated);
        setCounts(c => ({ ...c, pending: Math.max(0, c.pending - 1), approved: c.approved + 1 }));
        toast({ title: 'Proposal approved', description: 'Now deploy the rule from the detail panel.' });
      } else {
        const updated = await edonApi.approveFixProposal(p.proposal_id, 'admin@example.com', noteText || undefined);
        setProposals(prev => prev.map(x => x.proposal_id === p.proposal_id ? updated : x));
        setSelected(updated);
        toast({ title: 'Proposal approved', description: 'Now deploy the rule from the detail panel.' });
        fetchProposals();
      }
      setNoteText('');
    } catch {
      toast({ title: 'Approval failed', description: 'Could not approve this proposal.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  // ── Reject proposal ──────────────────────────────────────────────────────────
  const handleReject = async (p: FixProposal) => {
    setActionLoading(true);
    try {
      if (usingMock) {
        const updated = { ...p, status: 'rejected' as const, resolved_at: new Date().toISOString(), resolved_by: 'admin@example.com', resolution_note: noteText || null };
        setProposals(prev => prev.map(x => x.proposal_id === p.proposal_id ? updated : x));
        setSelected(updated);
        setCounts(c => ({ ...c, pending: Math.max(0, c.pending - 1), rejected: c.rejected + 1 }));
        toast({ title: 'Proposal rejected' });
      } else {
        const updated = await edonApi.rejectFixProposal(p.proposal_id, 'admin@example.com', noteText || undefined);
        setProposals(prev => prev.map(x => x.proposal_id === p.proposal_id ? updated : x));
        setSelected(updated);
        toast({ title: 'Proposal rejected' });
        fetchProposals();
      }
      setNoteText('');
    } catch {
      toast({ title: 'Rejection failed', description: 'Could not reject this proposal.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  // ── Deploy rule ──────────────────────────────────────────────────────────────
  const handleDeploy = async (p: FixProposal) => {
    setActionLoading(true);
    setDeployResult(null);
    try {
      if (usingMock) {
        const mockVerif: HealingVerification = { verified: 3, mitigated: 3, mitigated_ids: ['s1', 's2', 's3'] };
        const updated = { ...p, status: 'applied' as const };
        setProposals(prev => prev.map(x => x.proposal_id === p.proposal_id ? updated : x));
        setSelected(updated);
        setDeployResult({ rule_id: `rule-mock-${p.proposal_id}`, verification: mockVerif });
        setCounts(c => ({ ...c, approved: Math.max(0, c.approved - 1), applied: c.applied + 1 }));
        toast({ title: 'Rule deployed', description: '3 states verified and mitigated.' });
      } else {
        const res = await edonApi.deployHealingRule(p.proposal_id);
        setDeployResult({ rule_id: res.rule_id, verification: res.verification });
        toast({ title: 'Rule deployed', description: `${res.verification.mitigated} state(s) mitigated.` });
        fetchProposals();
      }
    } catch {
      toast({ title: 'Deploy failed', description: 'Could not deploy healing rule.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  // ── Filtered list ────────────────────────────────────────────────────────────
  const filtered = filterTab === 'all' ? proposals : proposals.filter(p => p.status === filterTab);

  // ── Stage counts ─────────────────────────────────────────────────────────────
  const stageCounts = [
    proposals.length,                                                    // shadow (all)
    proposals.length,                                                    // proposal generated (all)
    proposals.filter(p => p.status === 'pending_review').length,        // pending
    proposals.filter(p => p.status === 'approved').length,              // deployed
    proposals.filter(p => p.status === 'applied').length,               // verified
  ];

  const FILTER_TABS: { id: FilterTab; label: string }[] = [
    { id: 'all',           label: 'All' },
    { id: 'pending_review', label: 'Pending' },
    { id: 'approved',      label: 'Approved' },
    { id: 'applied',       label: 'Applied' },
    { id: 'rejected',      label: 'Rejected' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      <TopNav />

      <div className="flex-1 flex flex-col px-6 py-6 gap-5 max-w-[1400px] mx-auto w-full">

        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Wrench className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-100">Fix Transparency</h1>
              <p className="text-sm text-slate-500">Shadow findings → autonomous remediation pipeline</p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Summary badges */}
            <span className="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
              {counts.pending} pending
            </span>
            <span className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
              {counts.approved} approved
            </span>
            <span className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
              {counts.applied} applied
            </span>

            {/* Auto-heal toggle */}
            <button
              onClick={() => setAutoEnabled(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300 hover:bg-slate-700 transition-colors"
            >
              {autoEnabled
                ? <ToggleRight className="w-4 h-4 text-primary" />
                : <ToggleLeft className="w-4 h-4 text-slate-500" />
              }
              Auto-heal {autoEnabled ? 'on' : 'off'}
            </button>

            {/* Run healing pass */}
            <Button
              size="sm"
              onClick={handleRunHealing}
              disabled={healingLoading}
              className="gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20"
              variant="ghost"
            >
              {healingLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Run Healing Pass
            </Button>

            <Button
              size="icon"
              variant="ghost"
              onClick={fetchProposals}
              className="text-slate-500 hover:text-slate-300"
              title="Refresh"
            >
              <RefreshCcw className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* ── Mock mode notice ── */}
        {usingMock && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-amber-500/8 border border-amber-500/20 text-amber-400 text-xs">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            Showing demo proposals — the fix proposals API endpoint is not yet available.
          </div>
        )}

        {/* ── Pipeline stage banner ── */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center gap-1 overflow-x-auto">
            {PIPELINE_STAGES.map((stage, idx) => {
              const Icon = stage.icon;
              const count = stageCounts[idx];
              const isActive = count > 0;
              return (
                <div key={stage.id} className="flex items-center gap-1 flex-shrink-0">
                  <div className={`flex flex-col items-center gap-1.5 px-4 py-2.5 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary/10 border border-primary/20'
                      : 'bg-slate-800/50 border border-slate-800'
                  }`}>
                    <div className="flex items-center gap-1.5">
                      <Icon className={`w-4 h-4 ${isActive ? 'text-primary' : 'text-slate-600'}`} />
                      <span className={`text-xs font-medium ${isActive ? 'text-slate-200' : 'text-slate-600'}`}>
                        {stage.label}
                      </span>
                    </div>
                    <span className={`text-lg font-bold leading-none ${isActive ? 'text-primary' : 'text-slate-700'}`}>
                      {count}
                    </span>
                  </div>
                  {idx < PIPELINE_STAGES.length - 1 && (
                    <ArrowRight className="w-4 h-4 text-slate-700 flex-shrink-0 mx-0.5" />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Two-panel layout ── */}
        <div className="flex gap-4 min-h-0 flex-1">

          {/* ── Left: Proposal list ── */}
          <div className="w-[360px] flex-shrink-0 flex flex-col gap-3">

            {/* Filter tabs */}
            <div className="flex gap-1 p-1 bg-slate-900 border border-slate-800 rounded-xl">
              {FILTER_TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setFilterTab(tab.id)}
                  className={`flex-1 text-xs py-1.5 px-2 rounded-lg font-medium transition-all ${
                    filterTab === tab.id
                      ? 'bg-slate-700 text-slate-100'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Proposal cards */}
            <div className="flex flex-col gap-2 overflow-y-auto pr-1" style={{ maxHeight: 'calc(100vh - 380px)' }}>
              {loading ? (
                <div className="flex items-center justify-center py-16 text-slate-600">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-600">
                  <Wrench className="w-8 h-8" />
                  <p className="text-sm">No proposals yet</p>
                </div>
              ) : (
                <AnimatePresence mode="popLayout">
                  {filtered.map((p) => (
                    <motion.div
                      key={p.proposal_id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.18 }}
                    >
                      <button
                        onClick={() => { setSelected(p); setDeployResult(null); setNoteText(''); }}
                        className={`w-full text-left rounded-xl border p-3.5 transition-all ${
                          selected?.proposal_id === p.proposal_id
                            ? 'border-primary/40 bg-primary/8'
                            : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        {/* Top row: severity + status */}
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide ${SEVERITY_COLORS[p.severity]}`}>
                            {p.severity}
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ml-auto ${STATUS_COLORS[p.status]}`}>
                            {STATUS_LABELS[p.status]}
                          </span>
                        </div>

                        {/* Title */}
                        <p className="text-sm text-slate-200 font-medium leading-snug mb-1 line-clamp-2">
                          {p.rule_description}
                        </p>

                        {/* Subtitle */}
                        <p className="text-xs text-slate-500 mb-2 truncate">
                          {p.agent_id} · {p.action_type}
                        </p>

                        {/* Time */}
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-slate-600 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {relativeTime(p.created_at)}
                          </span>
                          {p.status === 'pending_review' && (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={(e) => { e.stopPropagation(); setSelected(p); handleApprove(p); }}
                                className="p-1 rounded-md bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors"
                                title="Approve"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); setSelected(p); handleReject(p); }}
                                className="p-1 rounded-md bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
                                title="Reject"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          )}
                        </div>
                      </button>
                    </motion.div>
                  ))}
                </AnimatePresence>
              )}
            </div>
          </div>

          {/* ── Right: Detail panel ── */}
          <div className="flex-1 min-w-0">
            <AnimatePresence mode="wait">
              {selected ? (
                <motion.div
                  key={selected.proposal_id}
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-col gap-4 h-full overflow-y-auto pr-1"
                  style={{ maxHeight: 'calc(100vh - 280px)' }}
                >
                  {/* Detail header */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-semibold uppercase tracking-wide ${SEVERITY_COLORS[selected.severity]}`}>
                          {selected.severity}
                        </span>
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_COLORS[selected.status]}`}>
                          {STATUS_LABELS[selected.status]}
                        </span>
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${ACTION_COLORS[selected.suggested_action]}`}>
                          {selected.suggested_action}
                        </span>
                      </div>
                      <span className="text-xs text-slate-600 flex-shrink-0">{relativeTime(selected.created_at)}</span>
                    </div>
                    <h2 className="text-base font-semibold text-slate-100 mb-1">{selected.rule_description}</h2>
                    <p className="text-xs text-slate-500">{selected.agent_id} · {selected.action_type} · trace {selected.trace_id.slice(0, 12)}</p>
                  </div>

                  {/* Pipeline position */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">Pipeline Position</p>
                    <div className="flex items-center gap-1">
                      {PIPELINE_STAGES.map((stage, idx) => {
                        const Icon = stage.icon;
                        const active = proposalStage(selected) >= idx;
                        const current = proposalStage(selected) === idx;
                        return (
                          <div key={stage.id} className="flex items-center gap-1 flex-shrink-0">
                            <div className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                              current
                                ? 'bg-primary/20 border border-primary/40 text-primary'
                                : active
                                  ? 'bg-slate-800 border border-slate-700 text-slate-300'
                                  : 'bg-slate-900 border border-slate-800/50 text-slate-700'
                            }`}>
                              <Icon className={`w-3 h-3 ${current ? 'text-primary' : active ? 'text-slate-400' : 'text-slate-700'}`} />
                              <span className="hidden sm:inline">{stage.label}</span>
                            </div>
                            {idx < PIPELINE_STAGES.length - 1 && (
                              <ChevronRight className="w-3 h-3 text-slate-700 flex-shrink-0" />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Trigger section */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                      <h3 className="text-sm font-semibold text-slate-200">What the Shadow Engine Found</h3>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div className="space-y-1">
                        <p className="text-[10px] text-slate-600 uppercase tracking-wider">Perturbation</p>
                        <p className="text-slate-300 font-medium">{selected.perturbation_name}</p>
                        <p className="text-xs text-slate-500">{selected.perturbation_type.replace(/_/g, ' ')}</p>
                      </div>
                      {selected.perturbed_field && (
                        <div className="space-y-1">
                          <p className="text-[10px] text-slate-600 uppercase tracking-wider">Field Mutated</p>
                          <code className="text-slate-300 font-mono text-xs bg-slate-800 px-2 py-1 rounded">
                            {selected.perturbed_field}
                          </code>
                        </div>
                      )}
                    </div>

                    {/* Verdict diff */}
                    <div className="mt-4 flex items-center gap-3">
                      <div className="flex-1 px-3 py-2.5 rounded-lg bg-slate-800 border border-slate-700 text-center">
                        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Original Verdict</p>
                        <span className="text-sm font-bold text-emerald-400">{selected.original_verdict}</span>
                      </div>
                      <ArrowRight className="w-4 h-4 text-slate-600 flex-shrink-0" />
                      <div className="flex-1 px-3 py-2.5 rounded-lg bg-red-500/8 border border-red-500/20 text-center">
                        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Shadow Verdict</p>
                        <span className="text-sm font-bold text-red-400">{selected.shadow_verdict}</span>
                      </div>
                    </div>
                  </div>

                  {/* Fix section */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Wrench className="w-4 h-4 text-primary" />
                      <h3 className="text-sm font-semibold text-slate-200">What EDON Proposes</h3>
                    </div>

                    {(selected.condition_tool || selected.condition_op) && (
                      <div className="mb-3 px-3 py-2.5 rounded-lg bg-slate-800 border border-slate-700">
                        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Rule Condition</p>
                        <code className="text-xs text-slate-300 font-mono">
                          {[selected.condition_tool, selected.condition_op].filter(Boolean).join(' → ')}
                        </code>
                      </div>
                    )}

                    <div className="mb-3">
                      <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Description</p>
                      <p className="text-sm text-slate-300">{selected.rule_description}</p>
                    </div>

                    <div>
                      <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Rationale</p>
                      <p className="text-sm text-slate-400 leading-relaxed">{selected.rationale}</p>
                    </div>
                  </div>

                  {/* Status/action section */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <CircleDot className="w-4 h-4 text-slate-400" />
                      <h3 className="text-sm font-semibold text-slate-200">Actions</h3>
                    </div>

                    {/* PENDING → show approve/reject */}
                    {selected.status === 'pending_review' && (
                      <div className="space-y-3">
                        <Textarea
                          placeholder="Optional note (reason for approval/rejection)..."
                          value={noteText}
                          onChange={(e) => setNoteText(e.target.value)}
                          className="bg-slate-800 border-slate-700 text-slate-200 text-sm placeholder:text-slate-600 resize-none h-20"
                        />
                        <div className="flex gap-2">
                          <Button
                            onClick={() => handleApprove(selected)}
                            disabled={actionLoading}
                            className="flex-1 gap-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30"
                            variant="ghost"
                          >
                            {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                            Approve Fix
                          </Button>
                          <Button
                            onClick={() => handleReject(selected)}
                            disabled={actionLoading}
                            className="flex-1 gap-1.5 bg-red-500/15 hover:bg-red-500/25 text-red-400 border border-red-500/30"
                            variant="ghost"
                          >
                            {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                            Reject
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* APPROVED → show deploy */}
                    {selected.status === 'approved' && (
                      <div className="space-y-3">
                        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-emerald-500/8 border border-emerald-500/20">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                          <div>
                            <p className="text-sm text-emerald-400 font-medium">Approved</p>
                            {selected.resolved_by && (
                              <p className="text-xs text-slate-500">by {selected.resolved_by} · {selected.resolved_at ? relativeTime(selected.resolved_at) : ''}</p>
                            )}
                            {selected.resolution_note && (
                              <p className="text-xs text-slate-400 mt-1">"{selected.resolution_note}"</p>
                            )}
                          </div>
                        </div>

                        <Button
                          onClick={() => handleDeploy(selected)}
                          disabled={actionLoading}
                          className="w-full gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20"
                          variant="ghost"
                        >
                          {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
                          Deploy Healing Rule
                        </Button>

                        {deployResult && (
                          <div className="px-3 py-2.5 rounded-lg bg-blue-500/8 border border-blue-500/20 space-y-1">
                            <p className="text-xs font-medium text-blue-400">Rule deployed</p>
                            <p className="text-xs text-slate-500 font-mono">{deployResult.rule_id}</p>
                            <p className="text-xs text-slate-400">
                              {deployResult.verification.verified} state(s) verified · {deployResult.verification.mitigated} mitigated
                            </p>
                            {deployResult.verification.error && (
                              <p className="text-xs text-amber-400">{deployResult.verification.error}</p>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* APPLIED → show verification summary */}
                    {selected.status === 'applied' && (
                      <div className="space-y-3">
                        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-blue-500/8 border border-blue-500/20">
                          <ShieldCheck className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                          <div>
                            <p className="text-sm text-blue-400 font-medium">Rule applied and verified</p>
                            {selected.resolved_by && (
                              <p className="text-xs text-slate-500">by {selected.resolved_by} · {selected.resolved_at ? relativeTime(selected.resolved_at) : ''}</p>
                            )}
                            {selected.resolution_note && (
                              <p className="text-xs text-slate-400 mt-1">"{selected.resolution_note}"</p>
                            )}
                          </div>
                        </div>
                        {deployResult && (
                          <div className="px-3 py-2.5 rounded-lg bg-slate-800 border border-slate-700 space-y-1">
                            <p className="text-xs font-medium text-slate-300">Verification result</p>
                            <p className="text-xs text-slate-400">
                              {deployResult.verification.verified} state(s) verified · {deployResult.verification.mitigated} mitigated
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* REJECTED */}
                    {selected.status === 'rejected' && (
                      <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-slate-800 border border-slate-700">
                        <XCircle className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
                        <div>
                          <p className="text-sm text-slate-400 font-medium">Proposal rejected</p>
                          {selected.resolved_by && (
                            <p className="text-xs text-slate-600">by {selected.resolved_by} · {selected.resolved_at ? relativeTime(selected.resolved_at) : ''}</p>
                          )}
                          {selected.resolution_note && (
                            <p className="text-xs text-slate-500 mt-1">"{selected.resolution_note}"</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* CREAO execution modes info box */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-4 h-4 text-primary" />
                      <h3 className="text-sm font-semibold text-slate-200">CREAO Execution Modes</h3>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="px-3 py-3 rounded-lg bg-emerald-500/8 border border-emerald-500/20">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="w-2 h-2 rounded-full bg-emerald-400" />
                          <p className="text-xs font-semibold text-emerald-400">Suggest Mode</p>
                          <span className="text-[10px] text-emerald-500 ml-auto">Active</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed">Shadow engine proposes fixes. No changes applied without review.</p>
                      </div>

                      <div className="px-3 py-3 rounded-lg bg-primary/8 border border-primary/20">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="w-2 h-2 rounded-full bg-primary" />
                          <p className="text-xs font-semibold text-primary">Assisted Mode</p>
                          <span className="text-[10px] text-primary/80 ml-auto">Active</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed">Approved proposals are queued for one-click deployment. Approval required.</p>
                      </div>

                      <div className="px-3 py-3 rounded-lg bg-slate-800 border border-slate-700">
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="w-2 h-2 rounded-full bg-slate-600" />
                          <p className="text-xs font-semibold text-slate-500">Autonomous Mode</p>
                          <span className="text-[10px] text-slate-600 ml-auto">Phase 2</span>
                        </div>
                        <p className="text-xs text-slate-600 leading-relaxed">EDON deploys rules automatically. Requires trust score &gt;95 and explicit opt-in.</p>
                      </div>
                    </div>
                  </div>

                </motion.div>
              ) : (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col items-center justify-center h-full min-h-[400px] text-center gap-4"
                >
                  <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center">
                    <Wrench className="w-7 h-7 text-slate-700" />
                  </div>
                  <div>
                    <p className="text-slate-500 font-medium">Select a proposal</p>
                    <p className="text-sm text-slate-700 mt-1">Choose a fix proposal from the left to review details and take action</p>
                  </div>
                  {proposals.length > 0 && (
                    <button
                      onClick={() => setSelected(proposals[0])}
                      className="text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
                    >
                      Open first proposal <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Last healing run footer */}
        {lastRun && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-500">
            <Shield className="w-3.5 h-3.5 text-primary" />
            Last healing pass: {relativeTime(lastRun.started_at)} ·{' '}
            {lastRun.rules_deployed} rule(s) deployed ·{' '}
            {lastRun.states_mitigated} state(s) mitigated
            {lastRun.skipped && lastRun.reason ? ` · Skipped: ${lastRun.reason}` : ''}
          </div>
        )}

      </div>
    </div>
  );
}
