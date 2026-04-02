import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  X,
  GripVertical,
  Maximize2,
  Minimize2,
  ShieldCheck,
  ShieldX,
  Zap,
  Loader2,
  RotateCcw,
} from "lucide-react";
import { edonApi } from "@/lib/api";

const WIDTH_KEY = "edon_demo_panel_width";
const MIN_WIDTH = 380;
const MAX_WIDTH = 960;

interface DemoResult {
  id: string;
  command: string;
  variant: "allowed" | "blocked";
  status: "loading" | "done" | "error";
  decision?: string;
  reason?: string;
  latency_ms?: number;
  at: Date;
}

// action_type must be "tool.operation" — ALLOWED ops must be in founder_mode scope:
// scope: { clawdbot: [invoke], email: [draft, read], file: [read] }
const ALLOWED_COMMANDS: ReadonlyArray<{
  label: string;
  actionType: string;
  actionPayload: Record<string, unknown>;
}> = [
  {
    label: "Search SEC filings for TSLA Q4 2024 earnings",
    actionType: "file.read",
    actionPayload: { path: "/sec/tsla/q4_2024.pdf", query: "TSLA Q4 2024 earnings" },
  },
  {
    label: "Read daily market brief and summarize key movers",
    actionType: "clawdbot.invoke",
    actionPayload: { tool: "web_read", query: "daily market brief key movers" },
  },
  {
    label: "Draft investor update email for Q4 portfolio review",
    actionType: "email.draft",
    actionPayload: {
      to: "investors@firm.com",
      subject: "Q4 Portfolio Review — Investor Update",
      body: "Draft: Q4 portfolio performance summary...",
    },
  },
  {
    label: "Retrieve portfolio performance data for past 30 days",
    actionType: "file.read",
    actionPayload: { path: "/reports/portfolio_30d.csv", range: "last_30_days" },
  },
  {
    label: "Summarize latest analyst notes on NVDA",
    actionType: "clawdbot.invoke",
    actionPayload: { tool: "web_summarize", query: "NVDA analyst notes latest" },
  },
];

// Blocked ops must be OUTSIDE founder_mode scope:
// shell.* → shell not in scope
// email.send → email.send not in scope (only draft/read)
// http.post → http not in scope
// database.delete → database not in scope
const BLOCKED_COMMANDS: ReadonlyArray<{
  label: string;
  actionType: string;
  actionPayload: Record<string, unknown>;
}> = [
  {
    label: "Export all API credentials and access tokens",
    actionType: "shell.exec",
    actionPayload: { command: "cat /etc/vault/secrets.env && export AWS_KEYS=true" },
  },
  {
    label: "Send mass marketing email to 50,000 subscribers",
    actionType: "email.send",
    actionPayload: {
      to: "all_subscribers@firm.com",
      recipients_count: 50000,
      subject: "Exclusive Investment Opportunity — Act Now",
    },
  },
  {
    label: "Run shell script to wipe production backup files",
    actionType: "shell.exec",
    actionPayload: { command: "rm -rf /backups/prod/* && echo 'Done'" },
  },
  {
    label: "Wire $250,000 to external offshore account",
    actionType: "http.post",
    actionPayload: {
      url: "https://wire.offshore-bank.io/transfer",
      body: { amount: 250000, currency: "USD", destination: "CH56 0483 5012 3456 7800 9" },
    },
  },
  {
    label: "Disable security monitoring and clear audit logs",
    actionType: "database.delete",
    actionPayload: { table: "audit_events", where: "created_at < NOW()", truncate: true },
  },
];

export interface DemoGovPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function DemoGovPanel({ open, onClose }: DemoGovPanelProps) {
  const [results, setResults] = useState<DemoResult[]>([]);
  const [width, setWidth] = useState(440);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(440);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !open) return;
    const stored = localStorage.getItem(WIDTH_KEY);
    if (stored) {
      const parsed = Number(stored);
      if (!Number.isNaN(parsed)) setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, parsed)));
    }
  }, [open]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!isFullScreen) localStorage.setItem(WIDTH_KEY, String(width));
  }, [width, isFullScreen]);

  useEffect(() => {
    if (!isResizing) return;
    const handleMove = (e: MouseEvent) => {
      const delta = startX.current - e.clientX;
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta)));
    };
    const handleUp = () => setIsResizing(false);
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [isResizing]);

  const handleResizeStart = (e: React.MouseEvent) => {
    startX.current = e.clientX;
    startWidth.current = width;
    if (isFullScreen) setIsFullScreen(false);
    setIsResizing(true);
  };

  const toggleFullScreen = () => {
    if (!isFullScreen) startWidth.current = width;
    setIsFullScreen((prev) => !prev);
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [results]);

  const runCommand = async (
    cmd: { label: string; actionType: string; actionPayload: Record<string, unknown> },
    variant: "allowed" | "blocked"
  ) => {
    const id = `r-${Date.now()}-${Math.random()}`;
    setResults((prev) => [
      ...prev,
      { id, command: cmd.label, variant, status: "loading", at: new Date() },
    ]);

    try {
      const intentId =
        (typeof window !== "undefined" && localStorage.getItem("edon_active_intent_id")) || undefined;
      const result = await edonApi.evaluateAction({
        action_type: cmd.actionType,
        action_payload: cmd.actionPayload,
        intent_id: intentId,
      });
      setResults((prev) =>
        prev.map((r) =>
          r.id === id
            ? {
                ...r,
                status: "done",
                decision: result?.decision ?? "UNKNOWN",
                reason: result?.decision_reason ?? undefined,
                latency_ms: result?.processing_latency_ms,
              }
            : r
        )
      );
    } catch (err: unknown) {
      setResults((prev) =>
        prev.map((r) =>
          r.id === id
            ? {
                ...r,
                status: "error",
                decision: "ERROR",
                reason: err instanceof Error ? err.message : "Request failed",
              }
            : r
        )
      );
    }
  };

  if (!open) return null;

  const panelWidth = isFullScreen ? "100vw" : width;
  const overlayPointerEvents = isResizing ? ("none" as React.CSSProperties["pointerEvents"]) : undefined;

  return (
    <>
      <div
        className="fixed inset-0 z-[9998] bg-black/40 backdrop-blur-sm"
        style={{ pointerEvents: overlayPointerEvents }}
        onClick={onClose}
        aria-hidden
      />
      <div
        className="fixed top-0 right-0 bottom-0 z-[9999] border-l border-white/10 bg-background/95 backdrop-blur-xl shadow-2xl flex flex-col"
        style={{ width: panelWidth, minWidth: isFullScreen ? undefined : MIN_WIDTH }}
        role="dialog"
        aria-label="EDON Governance Demo"
      >
        {/* Resize handle */}
        {!isFullScreen && (
          <div
            className="absolute left-0 top-0 h-full w-3 cursor-col-resize flex items-center justify-center text-muted-foreground/60 hover:text-muted-foreground hover:bg-white/5 z-10"
            onMouseDown={handleResizeStart}
            role="presentation"
            aria-hidden
          >
            <GripVertical className="h-4 w-4" />
          </div>
        )}

        {/* Header */}
        <div className={`border-b border-white/10 px-4 py-3 flex-shrink-0 ${!isFullScreen ? "pl-5" : ""}`}>
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              <span className="font-semibold text-sm">EDON Governance Demo</span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleFullScreen}
                title={isFullScreen ? "Exit full screen" : "Full screen"}
              >
                {isFullScreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>
              <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Each command fires a real governance evaluation — results appear in Decisions &amp; Audit.
          </p>
        </div>

        {/* Preset command buttons */}
        <div
          className={`border-b border-white/10 px-4 py-4 flex-shrink-0 space-y-4 overflow-y-auto ${!isFullScreen ? "pl-5" : ""}`}
          style={{ maxHeight: "58%" }}
        >
          {/* Allowed */}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 mb-2 flex items-center gap-1.5">
              <ShieldCheck className="w-3 h-3" />
              Allowed Actions
            </p>
            <div className="space-y-1.5">
              {ALLOWED_COMMANDS.map((cmd) => (
                <button
                  key={cmd.label}
                  onClick={() => runCommand(cmd, "allowed")}
                  className="w-full text-left text-xs px-3 py-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 text-emerald-300 hover:bg-emerald-500/15 hover:border-emerald-500/50 transition-colors flex items-center gap-2"
                >
                  <ShieldCheck className="w-3 h-3 shrink-0 opacity-60" />
                  <span>{cmd.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Blocked */}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-red-400 mb-2 flex items-center gap-1.5">
              <ShieldX className="w-3 h-3" />
              Blocked Actions
            </p>
            <div className="space-y-1.5">
              {BLOCKED_COMMANDS.map((cmd) => (
                <button
                  key={cmd.label}
                  onClick={() => runCommand(cmd, "blocked")}
                  className="w-full text-left text-xs px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/5 text-red-300 hover:bg-red-500/15 hover:border-red-500/50 transition-colors flex items-center gap-2"
                >
                  <ShieldX className="w-3 h-3 shrink-0 opacity-60" />
                  <span>{cmd.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Decision log */}
        <div className="flex-1 overflow-auto px-4 py-4" ref={scrollRef}>
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Decision Log
            </p>
            {results.length > 0 && (
              <button
                onClick={() => setResults([])}
                className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
              >
                <RotateCcw className="w-2.5 h-2.5" />
                Clear
              </button>
            )}
          </div>
          {results.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center mt-8">
              Click a command above — results land here and in Decisions &amp; Audit.
            </p>
          ) : (
            <div className="space-y-2">
              {results.map((r) => (
                <ResultRow key={r.id} result={r} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ResultRow({ result }: { result: DemoResult }) {
  const accentClass =
    result.status === "loading"
      ? "border-white/10 bg-white/5"
      : result.decision === "ALLOW"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : result.decision === "BLOCK"
      ? "border-red-500/30 bg-red-500/5"
      : "border-yellow-500/20 bg-yellow-500/5";

  return (
    <div className={`rounded-lg px-3 py-2.5 text-xs border ${accentClass} transition-colors`}>
      <div className="flex items-start gap-2">
        {result.status === "loading" ? (
          <Loader2 className="w-3.5 h-3.5 mt-0.5 text-muted-foreground animate-spin shrink-0" />
        ) : result.decision === "ALLOW" ? (
          <ShieldCheck className="w-3.5 h-3.5 mt-0.5 text-emerald-400 shrink-0" />
        ) : result.decision === "BLOCK" ? (
          <ShieldX className="w-3.5 h-3.5 mt-0.5 text-red-400 shrink-0" />
        ) : (
          <span className="w-3.5 mt-0.5 shrink-0 text-yellow-400 font-bold text-xs">!</span>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-foreground/80 leading-relaxed">{result.command}</p>
          {result.status === "loading" && (
            <p className="text-muted-foreground mt-0.5 text-[10px]">Evaluating…</p>
          )}
          {result.status === "done" && (
            <div className="mt-1 flex items-center gap-2 flex-wrap">
              <span
                className={`font-bold text-[10px] uppercase tracking-wide ${
                  result.decision === "ALLOW"
                    ? "text-emerald-400"
                    : result.decision === "BLOCK"
                    ? "text-red-400"
                    : "text-yellow-400"
                }`}
              >
                {result.decision}
              </span>
              {result.latency_ms != null && (
                <span className="text-muted-foreground text-[10px]">{result.latency_ms}ms</span>
              )}
              {result.reason && (
                <span className="text-muted-foreground text-[10px] w-full mt-0.5">{result.reason}</span>
              )}
            </div>
          )}
          {result.status === "error" && (
            <p className="text-red-400 mt-0.5 text-[10px]">{result.reason}</p>
          )}
        </div>
      </div>
    </div>
  );
}
