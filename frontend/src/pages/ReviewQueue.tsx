import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ClipboardList, CheckCircle2, XCircle, ThumbsUp, ThumbsDown,
  AlertTriangle, Clock, ChevronRight, RefreshCcw, User,
  Activity, Shield, Loader2, AlertCircle, Filter, KeyRound,
  Eye, EyeOff, TimerOff, Bot, X, Send,
} from 'lucide-react';
import { TopNav } from '@/components/TopNav';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { edonApi, ReviewQueueItem } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import { getRoleLabel, getUserRole } from '@/lib/auth';

// ─── SLA timeouts per urgency (ms) ───────────────────────────────────────────
const SLA_MS: Record<string, number> = {
  critical: 5 * 60 * 1000,   // 5 min
  urgent:   30 * 60 * 1000,  // 30 min
  routine:  4 * 60 * 60 * 1000, // 4 h
};

function getSlaMs(urgency: string) {
  return SLA_MS[urgency] ?? SLA_MS.routine;
}

function msRemaining(createdAt: string, urgency: string): number {
  const elapsed = Date.now() - new Date(createdAt).getTime();
  return Math.max(0, getSlaMs(urgency) - elapsed);
}

function fmtCountdown(ms: number): string {
  if (ms <= 0) return '00:00';
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ─── PIN helpers ─────────────────────────────────────────────────────────────
const PIN_HASH_KEY = 'edon_reviewer_pin_hash';

async function sha256hex(str: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function checkPin(pin: string): Promise<boolean> {
  const stored = localStorage.getItem(PIN_HASH_KEY);
  if (!stored) return false;
  const hash = await sha256hex(pin);
  return hash === stored;
}

async function setPin(pin: string): Promise<void> {
  const hash = await sha256hex(pin);
  localStorage.setItem(PIN_HASH_KEY, hash);
}

function hasPinSet(): boolean {
  return !!localStorage.getItem(PIN_HASH_KEY);
}

// ─── Urgency config ───────────────────────────────────────────────────────────
const URGENCY_CONFIG = {
  critical: {
    label: 'Critical',
    color: 'text-red-400',
    bg: 'bg-red-500/10 border-red-500/25',
    dot: 'bg-red-400',
    badge: 'border-red-500/40 text-red-400 bg-red-500/10',
    timerWarn: 60000, // go red at <1min
  },
  urgent: {
    label: 'Urgent',
    color: 'text-amber-400',
    bg: 'bg-amber-500/10 border-amber-500/25',
    dot: 'bg-amber-400',
    badge: 'border-amber-500/40 text-amber-400 bg-amber-500/10',
    timerWarn: 5 * 60000,
  },
  routine: {
    label: 'Routine',
    color: 'text-sky-400',
    bg: 'bg-sky-500/10 border-sky-500/20',
    dot: 'bg-sky-400',
    badge: 'border-sky-500/40 text-sky-400 bg-sky-500/10',
    timerWarn: 30 * 60000,
  },
} as const;

function getUrgency(item: ReviewQueueItem): 'critical' | 'urgent' | 'routine' {
  return item.meta?.urgency ?? 'routine';
}

function getDept(item: ReviewQueueItem): string {
  return String(item.meta?.department ?? item.agent_id.split('-')[0] ?? 'Unknown');
}

interface ReviewerInfo {
  name: string;
  email: string;
  verified: boolean; // true = came from live session endpoint, not just localStorage
}

interface ConfirmState {
  item: ReviewQueueItem;
  action: 'approved' | 'rejected';
  note: string;
}

// ─── SLA Countdown ────────────────────────────────────────────────────────────
function SlaTimer({
  item,
  onExpired,
}: {
  item: ReviewQueueItem;
  onExpired: (item: ReviewQueueItem) => void;
}) {
  const urgency = getUrgency(item);
  const cfg = URGENCY_CONFIG[urgency];
  const [ms, setMs] = useState(() => msRemaining(item.created_at, urgency));
  const firedRef = useRef(false);

  useEffect(() => {
    if (ms <= 0 && !firedRef.current) {
      firedRef.current = true;
      onExpired(item);
      return;
    }
    const iv = setInterval(() => {
      const remaining = msRemaining(item.created_at, urgency);
      setMs(remaining);
      if (remaining <= 0 && !firedRef.current) {
        firedRef.current = true;
        onExpired(item);
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [item, urgency, onExpired, ms]);

  const isWarn = ms <= cfg.timerWarn && ms > 0;
  const isExpired = ms <= 0;

  return (
    <div className={`flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded border ${
      isExpired ? 'text-red-400 border-red-500/40 bg-red-500/10' :
      isWarn    ? 'text-amber-400 border-amber-500/40 bg-amber-500/10' :
                  'text-muted-foreground border-white/10 bg-white/[0.03]'
    }`}>
      {isExpired
        ? <><TimerOff size={9} className="shrink-0" /> Expired</>
        : <><Clock size={9} className="shrink-0" />{fmtCountdown(ms)}</>
      }
    </div>
  );
}

// ─── Review Card ─────────────────────────────────────────────────────────────
function ReviewCard({
  item,
  onAction,
  resolving,
  onExpired,
  canReview,
}: {
  item: ReviewQueueItem;
  onAction: (item: ReviewQueueItem, action: 'approved' | 'rejected') => void;
  resolving: string | null;
  onExpired: (item: ReviewQueueItem) => void;
  canReview: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const urgency = getUrgency(item);
  const cfg = URGENCY_CONFIG[urgency];
  const busy = resolving === item.decision_id || !canReview;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8, height: 0 }}
      className={`rounded-2xl border overflow-hidden ${cfg.bg}`}
    >
      {/* Card header — always visible, inline actions here */}
      <div className="flex items-center gap-3 px-4 py-3">
        <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />

        {/* Clickable summary to expand */}
        <button
          className="flex-1 min-w-0 text-left hover:opacity-80 transition-opacity"
          onClick={() => setExpanded(v => !v)}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-foreground font-mono">{item.action_type}</span>
            {item.meta?.patient_id && (
              <span className="font-mono text-[10px] text-primary bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">
                {item.meta.patient_id as string}
              </span>
            )}
            <Badge variant="outline" className={`text-[10px] ${cfg.badge}`}>{cfg.label}</Badge>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[11px] text-muted-foreground flex-wrap">
            <span className="font-mono">{item.agent_id}</span>
            {item.meta?.device_name && <><span>·</span><span>{item.meta.device_name as string}</span></>}
          </div>
        </button>

        {/* Right: SLA timer + inline action buttons */}
        <div className="flex items-center gap-1.5 shrink-0">
          <SlaTimer item={item} onExpired={onExpired} />

          {/* Inline approve */}
          <button
            disabled={busy}
            onClick={e => { e.stopPropagation(); onAction(item, 'approved'); }}
            title="Approve"
            className="flex items-center justify-center w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <ThumbsUp size={11} />}
          </button>

          {/* Inline reject */}
          <button
            disabled={busy}
            onClick={e => { e.stopPropagation(); onAction(item, 'rejected'); }}
            title="Reject"
            className="flex items-center justify-center w-7 h-7 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <ThumbsDown size={11} />}
          </button>

          <button
            onClick={() => setExpanded(v => !v)}
            className="flex items-center justify-center w-6 h-6 text-muted-foreground"
          >
            <ChevronRight size={13} className={`transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`} />
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 space-y-4 border-t border-white/[0.08]">
              {/* Escalation question */}
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Review Question</p>
                <p className="text-sm text-foreground/90 leading-relaxed">{item.escalation_question}</p>
              </div>

              {item.meta?.clinical_context && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Context</p>
                  <div className="bg-black/20 rounded-xl px-3 py-2.5 text-xs text-foreground/80 leading-relaxed border border-white/[0.06]">
                    {item.meta.clinical_context as string}
                  </div>
                </div>
              )}

              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">EDON Explanation</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{item.explanation}</p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
                {[
                  { label: 'Agent', value: item.agent_id },
                  { label: 'Action', value: item.action_type },
                  ...(item.meta?.policy_version ? [{ label: 'Policy', value: item.meta.policy_version as string }] : []),
                  ...(item.meta?.vendor_name ? [{ label: 'Vendor', value: item.meta.vendor_name as string }] : []),
                  ...(item.meta?.device_id ? [{ label: 'Device', value: `${item.meta.device_id}${item.meta.device_name ? ` · ${item.meta.device_name}` : ''}` }] : []),
                  { label: 'SLA', value: `${getSlaMs(getUrgency(item)) / 60000 < 60 ? getSlaMs(getUrgency(item)) / 60000 + 'm' : getSlaMs(getUrgency(item)) / 3600000 + 'h'}` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-black/20 rounded-lg px-2.5 py-1.5 border border-white/[0.05]">
                    <p className="text-[9px] uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
                    <p className="font-mono text-foreground/80 truncate">{value}</p>
                  </div>
                ))}
              </div>

              {item.action_payload && Object.keys(item.action_payload).length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Action Payload</p>
                  <pre className="bg-black/20 rounded-xl px-3 py-2.5 text-[10px] text-foreground/70 border border-white/[0.06] overflow-x-auto font-mono">
                    {JSON.stringify(item.action_payload, null, 2)}
                  </pre>
                </div>
              )}

              {/* Full-size approve/reject in expanded view */}
              {!canReview ? (
                <div className="flex items-center gap-2 py-2.5 px-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-xs text-amber-400">
                  <AlertTriangle size={12} className="shrink-0" />
                  Identity not verified — cannot sign reviews
                </div>
              ) : (
                <div className="flex items-center gap-3 pt-1">
                  <button
                    disabled={busy}
                    onClick={() => onAction(item, 'approved')}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-sm font-semibold hover:bg-emerald-500/25 disabled:opacity-50 disabled:pointer-events-none transition-colors"
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <ThumbsUp size={14} />}
                    Approve
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => onAction(item, 'rejected')}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-500/15 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/25 disabled:opacity-50 disabled:pointer-events-none transition-colors"
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <ThumbsDown size={14} />}
                    Reject
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── PIN Modal ────────────────────────────────────────────────────────────────
function PinModal({
  mode,
  onSuccess,
  onCancel,
}: {
  mode: 'verify' | 'setup';
  onSuccess: (pin: string) => void;
  onCancel: () => void;
}) {
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 80); }, []);

  const handleSubmit = async () => {
    setError('');
    if (mode === 'setup') {
      if (pin.length < 4) { setError('PIN must be at least 4 characters.'); return; }
      if (pin !== confirmPin) { setError('PINs do not match.'); return; }
      setChecking(true);
      await setPin(pin);
      setChecking(false);
      onSuccess(pin);
      return;
    }
    // verify
    if (!pin) { setError('Enter your PIN.'); return; }
    setChecking(true);
    const ok = await checkPin(pin);
    setChecking(false);
    if (ok) { onSuccess(pin); }
    else { setError('Incorrect PIN.'); setPin(''); inputRef.current?.focus(); }
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 12 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
      className="relative z-10 glass-card max-w-sm w-full p-6 space-y-4"
    >
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0">
          <KeyRound size={16} className="text-primary" />
        </div>
        <div>
          <h3 className="font-semibold text-foreground">
            {mode === 'setup' ? 'Set a reviewer PIN' : 'Confirm your identity'}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {mode === 'setup'
              ? 'Required before signing reviews. Stored locally on this device.'
              : 'Enter your PIN to sign this review.'}
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <div className="relative">
          <input
            ref={inputRef}
            type={show ? 'text' : 'password'}
            value={pin}
            onChange={e => { setPin(e.target.value); setError(''); }}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
            placeholder={mode === 'setup' ? 'Choose a PIN' : 'Enter PIN'}
            className="w-full bg-white/[0.04] border border-white/15 rounded-xl pl-4 pr-10 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 font-mono tracking-widest"
          />
          <button type="button" onClick={() => setShow(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>

        {mode === 'setup' && (
          <input
            type={show ? 'text' : 'password'}
            value={confirmPin}
            onChange={e => { setConfirmPin(e.target.value); setError(''); }}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
            placeholder="Confirm PIN"
            className="w-full bg-white/[0.04] border border-white/15 rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 font-mono tracking-widest"
          />
        )}

        {error && <p className="text-xs text-red-400 flex items-center gap-1.5"><AlertCircle size={11} />{error}</p>}
      </div>

      <div className="flex gap-3">
        <button onClick={onCancel} className="flex-1 py-2 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors">
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={checking}
          className="flex-1 py-2 rounded-xl bg-primary/20 border border-primary/40 text-primary text-sm font-semibold hover:bg-primary/30 disabled:opacity-50 transition-colors"
        >
          {checking ? <Loader2 size={13} className="animate-spin mx-auto" /> : mode === 'setup' ? 'Set PIN' : 'Confirm'}
        </button>
      </div>

      {mode === 'verify' && (
        <button
          onClick={async () => {
            if (confirm('Reset your PIN? You will need to set a new one.')) {
              localStorage.removeItem(PIN_HASH_KEY);
              onCancel();
            }
          }}
          className="text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors w-full text-center"
        >
          Forgot PIN? Reset
        </button>
      )}
    </motion.div>
  );
}

// ─── Review Queue Chat Panel ─────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface QueueContext {
  pending: ReviewQueueItem[];
  resolved: ReviewQueueItem[];
  reviewer: ReviewerInfo;
}

function getReviewReply(query: string, ctx: QueueContext): string {
  const q = query.toLowerCase().trim();
  const { pending, resolved, reviewer } = ctx;

  const criticalCount = pending.filter(i => getUrgency(i) === 'critical').length;
  const urgentCount   = pending.filter(i => getUrgency(i) === 'urgent').length;
  const routineCount  = pending.filter(i => getUrgency(i) === 'routine').length;

  const deptCounts: Record<string, number> = {};
  pending.forEach(i => { const d = getDept(i); deptCounts[d] = (deptCounts[d] ?? 0) + 1; });
  const topDept = Object.entries(deptCounts).sort((a, b) => b[1] - a[1])[0];

  const approvedCount = resolved.filter(r => r.resolution === 'approved').length;
  const rejectedCount = resolved.filter(r => r.resolution === 'rejected').length;
  const autoCount     = resolved.filter(r => r.resolved_by === 'SYSTEM').length;

  const expired = pending.filter(i => msRemaining(i.created_at, getUrgency(i)) <= 0);

  // ── SLA / urgency questions ──
  if (/critical|most urgent|highest priority|emergency/i.test(q)) {
    if (criticalCount === 0) return 'No critical items in the queue right now. You have ' + (urgentCount + routineCount) + ' lower-priority items pending.';
    const items = pending.filter(i => getUrgency(i) === 'critical');
    return `${criticalCount} critical item${criticalCount > 1 ? 's' : ''} — 5-minute SLA. Top: "${items[0]?.action_type}" from ${items[0]?.agent_id}. Review these immediately.`;
  }

  if (/sla|time|expir|overdue|timeout/i.test(q)) {
    if (expired.length === 0) return `All items are within SLA. ${criticalCount} critical (5m), ${urgentCount} urgent (30m), ${routineCount} routine (4h).`;
    return `${expired.length} item${expired.length > 1 ? 's have' : ' has'} exceeded SLA and will be auto-denied. Act now or they will be rejected by the system automatically.`;
  }

  // ── Summary / how many ──
  if (/how many|count|total|summary|overview|status/i.test(q)) {
    const total = pending.length;
    if (total === 0) return 'Queue is clear — no pending escalations. ' + (approvedCount + rejectedCount) + ' items resolved recently.';
    return `${total} pending: ${criticalCount} critical, ${urgentCount} urgent, ${routineCount} routine. Recently resolved: ${approvedCount} approved, ${rejectedCount} rejected${autoCount > 0 ? `, ${autoCount} auto-denied by SLA` : ''}.`;
  }

  // ── Department questions ──
  if (/department|dept|which team|where|area/i.test(q)) {
    if (Object.keys(deptCounts).length === 0) return 'No pending items right now.';
    const breakdown = Object.entries(deptCounts).sort((a, b) => b[1] - a[1]).map(([d, n]) => `${d} (${n})`).join(', ');
    return `By department: ${breakdown}. ${topDept ? `Highest load: ${topDept[0]} with ${topDept[1]} item${topDept[1] > 1 ? 's' : ''}.` : ''}`;
  }

  // ── Reviewer / identity ──
  if (/who am i|reviewer|identity|verified|sign|my role/i.test(q)) {
    const role = getRoleLabel(getUserRole());
    if (!reviewer.verified) return `Your session is not verified — you cannot sign reviews until your API connection is confirmed. Check Settings and re-authenticate.`;
    return `You are ${reviewer.name} (${reviewer.email}), role: ${role}. Your identity is verified from a live session token — all review signatures are traceable to your account.`;
  }

  // ── Approve/reject guidance ──
  if (/approve|accept|allow/i.test(q)) {
    return 'To approve: click the green thumbs-up on any card, or expand a card and use the full-size Approve button. You must have a PIN set — you will be prompted to enter it before confirming.';
  }
  if (/reject|deny|block/i.test(q)) {
    return 'To reject: click the red thumbs-down on any card, or expand it and use the Reject button. You can add an optional rejection note before confirming with your PIN.';
  }

  // ── Auto-deny / system actions ──
  if (/auto.?den|system reject|auto reject|what happens/i.test(q)) {
    return 'If a review is not actioned before its SLA expires, EDON auto-denies it (resolved_by = SYSTEM) and logs the rejection. Critical: 5 min, Urgent: 30 min, Routine: 4 hours.';
  }

  // ── PIN ──
  if (/pin|password|credential/i.test(q)) {
    return 'PIN confirmation is required for every review signature. It is hashed with SHA-256 and stored locally on your device — EDON never transmits your PIN. First-time users are prompted to set one.';
  }

  // ── What to do first / triage ──
  if (/what (should|do) (i|we)|triage|priorit|start with|first/i.test(q)) {
    if (criticalCount > 0) return `Start with the ${criticalCount} critical item${criticalCount > 1 ? 's' : ''} — they expire in 5 minutes. Then move to ${urgentCount} urgent (30m window). Routine items have 4 hours.`;
    if (urgentCount > 0)   return `No critical items. Address the ${urgentCount} urgent item${urgentCount > 1 ? 's' : ''} first (30-minute window), then the ${routineCount} routine items.`;
    if (routineCount > 0)  return `Only routine items pending (${routineCount}). You have up to 4 hours per item — but review sooner to avoid auto-deny.`;
    return 'Queue is clear. Nothing requires attention right now.';
  }

  // ── Help / greeting ──
  if (/hello|hi|hey|help|what can you/i.test(q)) {
    return `Hi ${reviewer.name || 'reviewer'}! I can help with: queue status, SLA timers, department breakdown, how to approve/reject, PIN setup, reviewer identity, or what to prioritize. What do you need?`;
  }

  // ── Fallback ──
  return `${pending.length} pending item${pending.length !== 1 ? 's' : ''}: ${criticalCount} critical, ${urgentCount} urgent, ${routineCount} routine. Ask me about SLA status, department breakdown, how to approve/reject, or what to do first.`;
}

function ReviewQueueChat({
  open,
  onClose,
  pending,
  resolved,
  reviewer,
}: {
  open: boolean;
  onClose: () => void;
  pending: ReviewQueueItem[];
  resolved: ReviewQueueItem[];
  reviewer: ReviewerInfo;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Seed greeting on open
  useEffect(() => {
    if (!open) return;
    const critCount = pending.filter(i => getUrgency(i) === 'critical').length;
    const greeting = critCount > 0
      ? `${critCount} critical item${critCount > 1 ? 's' : ''} in queue — SLA expires in 5 minutes. How can I help?`
      : pending.length > 0
        ? `${pending.length} item${pending.length > 1 ? 's' : ''} pending review. Ask me about priorities, SLA status, or how to sign a review.`
        : `Queue is clear. Ask me anything about the review workflow.`;
    setMessages([{ id: 'greeting', role: 'assistant', content: greeting }]);
    setTimeout(() => inputRef.current?.focus(), 120);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const send = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    // Small delay for realism
    setTimeout(() => {
      const reply = getReviewReply(text, { pending, resolved, reviewer });
      setMessages(prev => [...prev, { id: `a-${Date.now()}`, role: 'assistant', content: reply }]);
      setLoading(false);
    }, 280);
  };

  if (!open) return null;

  const criticalCount = pending.filter(i => getUrgency(i) === 'critical').length;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[90] bg-black/30 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Panel */}
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed top-0 right-0 bottom-0 z-[91] w-full sm:w-96 flex flex-col border-l border-white/10 bg-background/98 backdrop-blur-xl shadow-2xl"
        role="dialog"
        aria-label="Review Queue Assistant"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Bot size={14} className="text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Review Assistant</p>
              <p className="text-[10px] text-muted-foreground">
                {criticalCount > 0
                  ? <span className="text-red-400 font-medium">{criticalCount} critical · act now</span>
                  : `${pending.length} pending`}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors p-1">
            <X size={15} />
          </button>
        </div>

        {/* Quick prompts */}
        <div className="flex gap-2 px-4 py-2.5 border-b border-white/[0.06] overflow-x-auto shrink-0">
          {['What to review first?', 'SLA status', 'Department breakdown', 'How to approve'].map(prompt => (
            <button
              key={prompt}
              onClick={() => { setInput(prompt); setTimeout(() => inputRef.current?.focus(), 50); }}
              className="shrink-0 text-[10px] px-2.5 py-1 rounded-lg border border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground hover:border-white/20 transition-colors whitespace-nowrap"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" ref={scrollRef}>
          {messages.map(m => (
            <div
              key={m.id}
              className={`rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                m.role === 'user'
                  ? 'ml-6 bg-primary/15 border border-primary/25 text-foreground'
                  : 'mr-2 bg-white/[0.04] border border-white/[0.08] text-foreground/85'
              }`}
            >
              {m.content}
            </div>
          ))}
          {loading && (
            <div className="mr-2 rounded-xl px-3.5 py-2.5 bg-white/[0.04] border border-white/[0.08]">
              <div className="flex gap-1 items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-white/10 shrink-0">
          <form
            onSubmit={e => { e.preventDefault(); send(); }}
            className="flex gap-2"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={loading}
              placeholder="Ask about the queue…"
              className="flex-1 bg-white/[0.04] border border-white/15 rounded-xl px-3.5 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30 disabled:opacity-40 disabled:pointer-events-none transition-colors"
            >
              <Send size={14} />
            </button>
          </form>
        </div>
      </motion.div>
    </>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function ReviewQueue() {
  const { toast } = useToast();
  const [pending, setPending] = useState<ReviewQueueItem[]>([]);
  const [resolved, setResolved] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);

  // Confirm flow state
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [noteInput, setNoteInput] = useState('');
  const [pinStage, setPinStage] = useState<'none' | 'pin' | 'setup'>('none');

  // Department filter
  const [deptFilter, setDeptFilter] = useState<string>('all');

  // Chat panel
  const [chatOpen, setChatOpen] = useState(false);

  // ── Server-verified reviewer identity ─────────────────────────────────────
  const [reviewer, setReviewer] = useState<ReviewerInfo>({
    name: localStorage.getItem('edon_display_name') || localStorage.getItem('edon_user_email') || '',
    email: localStorage.getItem('edon_user_email') || '',
    verified: false,
  });

  useEffect(() => {
    edonApi.getSession()
      .then(session => {
        if (session?.email) {
          setReviewer({
            email: session.email,
            name: localStorage.getItem('edon_display_name') || session.email.split('@')[0],
            verified: true,
          });
          // Keep localStorage in sync
          localStorage.setItem('edon_user_email', session.email);
        }
      })
      .catch(() => {
        // Session fetch failed — reviewer stays unverified, block signing
        setReviewer(r => ({ ...r, verified: false }));
      });
  }, []);

  const fetchQueue = useCallback(async () => {
    try {
      const [pendingRes, approvedRes, rejectedRes] = await Promise.allSettled([
        edonApi.getReviewQueue('pending'),
        edonApi.getReviewQueue('approved'),
        edonApi.getReviewQueue('rejected'),
      ]);
      if (pendingRes.status === 'fulfilled') {
        setPending(pendingRes.value?.queue ?? []);
        setError(null);
      }
      const approvedItems = approvedRes.status === 'fulfilled' ? (approvedRes.value?.queue ?? []) : [];
      const rejectedItems = rejectedRes.status === 'fulfilled' ? (rejectedRes.value?.queue ?? []) : [];
      const combined = [...approvedItems, ...rejectedItems]
        .sort((a, b) => new Date(b.resolved_at ?? b.created_at).getTime() - new Date(a.resolved_at ?? a.created_at).getTime())
        .slice(0, 20);
      setResolved(combined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 15000);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  // ── SLA auto-deny ────────────────────────────────────────────────────────
  const handleExpired = useCallback(async (item: ReviewQueueItem) => {
    // Only auto-deny if still pending (fetchQueue may have already removed it)
    try {
      await edonApi.rejectReview(
        item.decision_id,
        'SYSTEM',
        `Auto-denied: SLA timeout (${getUrgency(item)} — ${getSlaMs(getUrgency(item)) / 60000}m)`
      );
      toast({
        title: 'SLA timeout — auto-denied',
        description: `${item.action_type} · ${item.agent_id}`,
        variant: 'destructive',
      });
      fetchQueue();
    } catch {
      // Already resolved — ignore
    }
  }, [fetchQueue, toast]);

  // ── Action flow ──────────────────────────────────────────────────────────
  const handleAction = (item: ReviewQueueItem, action: 'approved' | 'rejected') => {
    if (!reviewer.verified) {
      toast({
        title: 'Identity not verified',
        description: 'Cannot sign reviews until your session is verified. Check your API connection.',
        variant: 'destructive',
      });
      return;
    }
    setNoteInput('');
    setConfirm({ item, action, note: '' });
    // Show PIN stage immediately
    setPinStage(hasPinSet() ? 'pin' : 'setup');
  };

  const handlePinSuccess = (_pin: string) => {
    setPinStage('none');
    // Now show the confirm modal (confirm is already set)
  };

  const handlePinCancel = () => {
    setPinStage('none');
    setConfirm(null);
  };

  const handleConfirm = async () => {
    if (!confirm) return;
    const { item, action, note } = confirm;
    setResolving(item.decision_id);
    setConfirm(null);
    try {
      if (action === 'approved') {
        await edonApi.approveReview(item.decision_id, reviewer.name || reviewer.email, note || undefined);
      } else {
        await edonApi.rejectReview(item.decision_id, reviewer.name || reviewer.email, note || undefined);
      }
      toast({
        title: action === 'approved' ? 'Action approved' : 'Action rejected',
        description: `${item.action_type} — ${item.agent_id}`,
      });
      await fetchQueue();
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Request failed',
        variant: 'destructive',
      });
    } finally {
      setResolving(null);
    }
  };

  // ── Department filter ────────────────────────────────────────────────────
  const allDepts = Array.from(new Set(pending.map(getDept))).sort();
  const filteredPending = deptFilter === 'all'
    ? pending
    : pending.filter(i => getDept(i) === deptFilter);

  const grouped = (['critical', 'urgent', 'routine'] as const)
    .map(u => ({ urgency: u, items: filteredPending.filter(i => getUrgency(i) === u) }))
    .filter(g => g.items.length > 0);

  const pendingCount = pending.length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopNav />
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ClipboardList size={18} className="text-primary" />
              <h1 className="text-2xl font-bold text-foreground">Review Queue</h1>
              {pendingCount > 0 && (
                <span className="flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-red-500 text-[10px] font-bold text-white">
                  {pendingCount}
                </span>
              )}
            </div>
            <p className="text-muted-foreground text-sm">Escalated agent actions awaiting human approval</p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Reviewer identity + PIN status */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs transition-colors ${
              reviewer.verified
                ? 'border-border bg-secondary'
                : 'border-amber-500/30 bg-amber-500/10'
            }`}>
              {reviewer.verified
                ? <User size={12} className="text-muted-foreground" />
                : <AlertTriangle size={12} className="text-amber-400" />
              }
              <span className="text-muted-foreground">Reviewing as</span>
              <span className="text-foreground font-medium">{reviewer.name || reviewer.email || 'Unknown'}</span>
              {reviewer.verified && (
                <Badge variant="outline" className="text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/10 px-1 py-0">
                  {getRoleLabel(getUserRole())}
                </Badge>
              )}
              {!reviewer.verified && (
                <span className="text-amber-400 text-[10px] font-medium">Unverified</span>
              )}
              {hasPinSet()
                ? <Shield size={10} className="text-emerald-400" title="PIN set" />
                : <KeyRound size={10} className="text-amber-400" title="No PIN set — required on first review" />
              }
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setChatOpen(true)}
              className="gap-1.5 border-primary/30 text-primary hover:bg-primary/10"
            >
              <Bot size={13} />
              Ask AI
            </Button>

            <Button variant="outline" size="sm" onClick={fetchQueue} disabled={loading} className="gap-1.5">
              <RefreshCcw size={13} className={loading ? 'animate-spin' : ''} />
              Refresh
            </Button>
          </div>
        </div>

        {/* SLA legend */}
        <div className="flex flex-wrap gap-2 text-[11px]">
          {Object.entries(SLA_MS).map(([u, ms]) => (
            <div key={u} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/[0.08] bg-white/[0.02] text-muted-foreground">
              <Clock size={10} />
              <span className="capitalize font-medium">{u}</span>
              <span>→ auto-deny after {ms >= 3600000 ? ms / 3600000 + 'h' : ms / 60000 + 'm'}</span>
            </div>
          ))}
        </div>

        {/* Unverified identity warning */}
        {!reviewer.verified && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-3 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3"
          >
            <AlertTriangle size={15} className="text-amber-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-amber-400">Identity not verified — reviews are locked</p>
              <p className="text-xs text-amber-400/70 mt-0.5">Your session could not be confirmed. Check your API connection or re-authenticate in Settings.</p>
            </div>
          </motion.div>
        )}

        {/* Department filter */}
        {allDepts.length > 1 && (
          <div className="flex items-center gap-2 flex-wrap">
            <Filter size={12} className="text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Department:</span>
            {['all', ...allDepts].map(dept => (
              <button
                key={dept}
                onClick={() => setDeptFilter(dept)}
                className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${
                  deptFilter === dept
                    ? 'bg-primary/20 border-primary/40 text-primary'
                    : 'border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20'
                }`}
              >
                {dept === 'all' ? `All · ${pendingCount}` : dept}
                {dept !== 'all' && (
                  <span className="ml-1 text-muted-foreground/60">
                    · {pending.filter(i => getDept(i) === dept).length}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
            <AlertCircle size={16} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-16 rounded-2xl bg-white/[0.04] animate-pulse" />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && filteredPending.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center gap-3 py-20 rounded-2xl border border-white/[0.08] bg-white/[0.02]"
          >
            <CheckCircle2 size={32} className="text-emerald-400" />
            <p className="text-foreground font-semibold">All caught up</p>
            <p className="text-muted-foreground text-sm">
              {deptFilter !== 'all' ? `No pending escalations in ${deptFilter}.` : 'No escalated actions require review right now.'}
            </p>
          </motion.div>
        )}

        {/* Grouped pending */}
        {!loading && grouped.map(({ urgency, items }) => {
          const cfg = URGENCY_CONFIG[urgency];
          return (
            <div key={urgency} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${cfg.dot} ${urgency === 'critical' ? 'animate-pulse' : ''}`} />
                <h3 className={`text-sm font-semibold ${cfg.color}`}>{cfg.label}</h3>
                <Badge variant="outline" className={`text-[10px] ${cfg.badge}`}>{items.length}</Badge>
              </div>
              <AnimatePresence>
                {items.map(item => (
                  <ReviewCard
                    key={item.decision_id}
                    item={item}
                    onAction={handleAction}
                    resolving={resolving}
                    onExpired={handleExpired}
                    canReview={reviewer.verified}
                  />
                ))}
              </AnimatePresence>
            </div>
          );
        })}

        {/* Recently resolved */}
        {!loading && resolved.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <Activity size={13} />
              Recently Resolved
            </h3>
            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] overflow-hidden divide-y divide-white/[0.04]">
              {resolved.map(item => (
                <div key={item.decision_id} className="flex items-center gap-3 px-4 py-2.5 text-xs">
                  {item.resolution === 'approved'
                    ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                    : <XCircle size={13} className="text-red-400 shrink-0" />}
                  <span className="font-mono text-foreground/80 flex-1 truncate">{item.action_type}</span>
                  <span className="text-muted-foreground font-mono hidden sm:block truncate max-w-[120px]">{item.agent_id}</span>
                  <span className={`shrink-0 ${item.resolved_by === 'SYSTEM' ? 'text-muted-foreground' : item.resolution === 'approved' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {item.resolution === 'approved' ? 'Approved' : 'Rejected'}
                    {item.resolved_by ? ` · ${item.resolved_by}` : ''}
                  </span>
                  <span className="text-muted-foreground/60 shrink-0 hidden md:block">
                    {item.resolved_at ? relTime(item.resolved_at) : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Stats */}
        {!loading && (
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Pending', value: pending.length, icon: Clock, color: 'text-amber-400' },
              { label: 'Approved', value: resolved.filter(r => r.resolution === 'approved').length, icon: CheckCircle2, color: 'text-emerald-400' },
              { label: 'Rejected', value: resolved.filter(r => r.resolution === 'rejected').length, icon: XCircle, color: 'text-red-400' },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="glass-card p-4 flex flex-col items-center gap-1.5 text-center">
                <Icon size={15} className={color} />
                <p className={`text-xl font-bold tabular-nums ${color}`}>{value}</p>
                <p className="text-[11px] text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* ── Chat Panel ── */}
      <AnimatePresence>
        {chatOpen && (
          <ReviewQueueChat
            open={chatOpen}
            onClose={() => setChatOpen(false)}
            pending={pending}
            resolved={resolved}
            reviewer={reviewer}
          />
        )}
      </AnimatePresence>

      {/* ── Overlays ── */}
      <AnimatePresence>

        {/* PIN modal (shown before confirm modal) */}
        {pinStage !== 'none' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
            <PinModal
              mode={pinStage === 'setup' ? 'setup' : 'verify'}
              onSuccess={handlePinSuccess}
              onCancel={handlePinCancel}
            />
          </motion.div>
        )}

        {/* Confirm modal (shown after PIN verified) */}
        {confirm && pinStage === 'none' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirm(null)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
              className="relative z-10 glass-card max-w-md w-full p-6 space-y-4"
            >
              <div className="flex items-center gap-3">
                {confirm.action === 'approved'
                  ? <CheckCircle2 size={20} className="text-emerald-400" />
                  : <XCircle size={20} className="text-red-400" />}
                <div>
                  <h3 className="font-semibold text-foreground">
                    {confirm.action === 'approved' ? 'Approve this action?' : 'Reject this action?'}
                  </h3>
                  <p className="text-xs text-muted-foreground font-mono mt-0.5">{confirm.item.action_type}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs">
                <Shield size={11} className="text-emerald-400" />
                <span className="text-muted-foreground">
                  Signed as <span className="text-foreground font-medium">{reviewer.name || reviewer.email}</span>
                  {reviewer.email && reviewer.name && <span className="text-muted-foreground/60"> · {reviewer.email}</span>}
                </span>
                <Badge variant="outline" className="text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/10 ml-1">
                  PIN verified
                </Badge>
              </div>

              {confirm.action === 'rejected' && (
                <div>
                  <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
                    Rejection note (optional)
                  </label>
                  <textarea
                    value={noteInput}
                    onChange={e => { setNoteInput(e.target.value); setConfirm(c => c ? { ...c, note: e.target.value } : c); }}
                    placeholder="Reason for rejection..."
                    rows={2}
                    className="w-full bg-white/[0.04] border border-white/15 rounded-xl px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
                  />
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => setConfirm(null)}
                  className="flex-1 py-2 rounded-xl border border-white/15 text-sm text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  className={`flex-1 py-2 rounded-xl text-sm font-semibold transition-colors ${
                    confirm.action === 'approved'
                      ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/30'
                      : 'bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30'
                  }`}
                >
                  Confirm {confirm.action === 'approved' ? 'Approval' : 'Rejection'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
