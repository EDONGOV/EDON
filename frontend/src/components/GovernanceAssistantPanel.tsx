import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { X, GripVertical, Maximize2, Minimize2 } from "lucide-react";
import { edonApi } from "@/lib/api";

const WIDTH_KEY = "edon_governance_assistant_width";
const MIN_WIDTH = 320;
const MAX_WIDTH = 960;

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: Date;
}

type PanelContext = {
  health: { status?: string; uptime_seconds?: number; governor?: { active_preset?: { preset_name?: string } } } | null;
  presetName: string;
  connected: boolean;
}

/** Scale-first governance: cohorts, roles, environments, risk states. Not individual agents. */
function getAssistantReply(query: string, ctx: PanelContext): string {
  const q = query.toLowerCase().trim();
  const preset = ctx.presetName || "unknown";

  if (!ctx.connected) {
    return "Gateway is not connected. Connect in Settings to get live data. I can still explain how governance at scale works: cohorts, roles, risk states.";
  }

  // ── Individual agent (redirect to cohort/risk mindset) ──
  if (/why was (agent|)\s*\d+\s*blocked/i.test(q) || /why did (agent|)\s*\d+\s*get blocked/i.test(q) || /agent\s*\d+/i.test(q) && /block|flag|reason/i.test(q)) {
    return "At scale we focus on cohorts and risk states, not individual IDs. To investigate a specific decision: use Audit or Decisions, filter by role/cohort/environment, or search by agent ID when you need one instance. Normal agents stay invisible; investigate when something is abnormal or escalated.";
  }

  // ── Risk-first: what's abnormal, what changed, what escalated ──
  if (/what('s|s)?\s*(abnormal|wrong|concerning)/i.test(q) || /show me what('s)?\s*(abnormal|changed|escalated)/i.test(q) || /what changed|what escalated/i.test(q)) {
    return "Risk-first view: use the Dashboard and Decisions to see flagged/blocked counts by cohort or role. Filter by verdict (blocked, confirm) and time range. 'Normal' agents are invisible—silence means a healthy system. Surface what's abnormal, what changed, what escalated; then drill in by cohort or search.";
  }

  // ── Cohorts, roles, domains ──
  if (/cohort|role|domain|agent type|warehouse|support|drone|humanoid/i.test(q) && !/individual|single|one agent/i.test(q)) {
    return "Governance scales by structure: Organization → Domain (e.g. Warehouse Ops, Support) → Agent Type (Drone, Humanoid, LLM) → Role (Picker, Supervisor) → Instance. Default view should be cohort-based: e.g. '400K Support Agents', '20K Warehouse Humanoids', with risk overlays (flagged %, blocked %). Use Dashboard and Decisions filters by role/cohort; search when you need to narrow.";
  }

  // ── Environments, tags, metadata ──
  if (/environment|tag|metadata|prod|staging|location|model version|firmware/i.test(q)) {
    return "Every agent should have metadata: location, model version, task scope, environment (prod/staging), risk profile, owner team. Filter with queries like 'drones in restricted airspace on firmware v1.2'. Governance at scale is search-driven, not scroll-driven. Use Audit/Decisions filters and search by tag or policy trigger.";
  }

  // ── Drift, clusters, patterns ──
  if (/drift|cluster|pattern|similar behavior|emerging/i.test(q)) {
    return "Think in patterns: drift by cohort (e.g. 'Drift rising in Support Tier 2'), clusters of similar behavior, auto-grouped anomalous agents. Example: '237 warehouse humanoids exhibiting similar path deviation'—investigate the cluster, not 237 individuals. Use Dashboard drift/trend views and Audit to see by role or tag.";
  }

  // ── High-risk, violations, blocked ──
  if (/high[- ]?risk|violations?|blocked|flagged/i.test(q)) {
    return "View risk at cohort level: e.g. '2.1% flagged, 0.02% blocked' with breakdown by domain/role. Use Dashboard and Decisions filtered by verdict and time; Policies to see which rules fire. Don't scroll rows—use aggregated risk and search when investigating.";
  }

  // ── Search, filter, visualize ──
  if (/search|filter|heat map|cluster map|distribution|visuali(z|s)ation/i.test(q)) {
    return "Governance at scale is search-driven: by ID, role, tag, anomaly score, policy trigger, timestamp. Visualize with heat maps, risk distribution curves, drift trend lines—never 1M rows. Dashboard and Decisions support filters; use them to see aggregated intelligence, then search to investigate.";
  }

  // ── Digital passport / single-agent investigation ──
  if (/passport|identity|history|lineage|fingerprint|investigate (one|single|a specific)/i.test(q)) {
    return "Digital passport (identity, history, policy lineage, behavioral fingerprint) is for investigation only. You don't monitor every agent—you monitor systems and cohorts, and drill into an agent when needed. Use Audit or Decisions and search by ID when investigating a specific instance.";
  }

  // ── System status, policy ──
  if (/system status|health|operational/i.test(q)) {
    const status = ctx.health?.status ?? "unknown";
    const uptime = ctx.health?.uptime_seconds;
    const uptimeStr = uptime != null ? `Uptime: ${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m.` : "";
    return `System status: **${status}**. ${uptimeStr} Active preset: **${preset}**. At scale, default view is cohort-based and risk-first.`;
  }
  if (/active (policy|preset)|current (policy|preset)|what('s|s) (the )?policy/i.test(q)) {
    return `Active preset: **${preset}**. Change it in Policies or Settings. Governance scales by structuring abstraction: cohorts, roles, environments, risk states—not by tracking every identity.`;
  }

  // ── Help, intro ──
  if (/hello|hi|hey|help|what can you do|how does (this|governance) work/i.test(q)) {
    return "Governance at scale: think in **cohorts, roles, environments, risk states**—not individual agents. Default view is cohort-based (e.g. 400K Support, 20K Warehouse Humanoids) with risk overlays. Risk-first: show what's abnormal, what changed, what escalated. Search-driven: by ID, role, tag, policy trigger. Try: 'What's abnormal?', 'Risk by cohort', 'Drift by role', 'Search by tag'. I recommend only—no actions.";
  }

  return "At scale, governance is about **patterns, risk zones, policy clusters, trend shifts**—not individuals. Ask: 'What's abnormal?', 'Risk by cohort or role', 'Drift by environment', or 'Search by role/tag'. I recommend only; use Dashboard, Decisions, and Audit to act.";
}

export interface GovernanceAssistantPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function GovernanceAssistantPanel({ open, onClose }: GovernanceAssistantPanelProps) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<PanelContext["health"]>(null);
  const [connected, setConnected] = useState(false);
  const [width, setWidth] = useState(420);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(420);
  const scrollRef = useRef<HTMLDivElement>(null);

  const presetName =
    health?.governor?.active_preset?.preset_name ?? "";

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const h = await edonApi.getHealth();
        if (cancelled) return;
        setHealth(h as PanelContext["health"]);
        setConnected(true);
      } catch {
        if (!cancelled) {
          setHealth(null);
          setConnected(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

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
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    const userMsg: AssistantMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      at: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const ctx: PanelContext = { health, presetName, connected };
    const replyText = getAssistantReply(text, ctx);

    const assistantMsg: AssistantMessage = {
      id: `a-${Date.now()}`,
      role: "assistant",
      content: replyText.replace(/\*\*([^*]+)\*\*/g, "$1"),
      at: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setLoading(false);
  };

  if (!open) return null;

  const panelWidth = isFullScreen ? "100vw" : width;
  const overlayPointerEvents = isResizing ? "none" : undefined;

  return (
    <>
      <div
        className="fixed inset-0 z-[9998] bg-black/40 backdrop-blur-sm"
        style={{ pointerEvents: overlayPointerEvents }}
        onClick={onClose}
        aria-hidden
      />
      <div
        className="fixed top-0 right-0 bottom-0 z-[9999] border-l border-white/10 bg-background/95 backdrop-blur-xl shadow-2xl flex flex-col transition-[width] duration-150"
        style={{ width: panelWidth, minWidth: isFullScreen ? undefined : MIN_WIDTH }}
        role="dialog"
        aria-label="Governance AI Assistant"
      >
        {/* Resize handle (left edge) */}
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

        <div className={`border-b border-white/10 px-4 py-3 flex-shrink-0 ${!isFullScreen ? "pl-5" : ""}`}>
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="font-semibold text-sm text-foreground">Governance AI</span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleFullScreen}
                aria-label={isFullScreen ? "Exit full screen" : "Full screen"}
                title={isFullScreen ? "Exit full screen" : "Full screen"}
              >
                {isFullScreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
              <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Think in cohorts, roles, risk states—not individual agents. Search-driven governance. Recommendations only.
          </p>
        </div>

        <div className="flex-1 overflow-auto px-4 py-4" ref={scrollRef}>
          <div className="space-y-4 pr-2">
            {messages.length === 0 && (
              <div className="space-y-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground/90">Scale by abstraction, not identity.</p>
                <p>Try:</p>
                <ul className="list-disc list-inside space-y-1 pl-1">
                  <li>&ldquo;What&apos;s abnormal?&rdquo;</li>
                  <li>&ldquo;Show risk by cohort or role&rdquo;</li>
                  <li>&ldquo;Drift by environment?&rdquo;</li>
                  <li>&ldquo;Search by role, tag, or policy trigger&rdquo;</li>
                  <li>&ldquo;How does governance at scale work?&rdquo;</li>
                </ul>
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={`rounded-lg px-4 py-3 text-xs ${
                  m.role === "user"
                    ? "ml-8 bg-primary/15 text-foreground border border-primary/20"
                    : "mr-2 bg-white/5 text-muted-foreground border border-white/10"
                }`}
              >
                {m.content}
              </div>
            ))}
            {loading && (
              <div className="rounded-lg px-4 py-3 text-xs bg-white/5 text-muted-foreground border border-white/10">
                Thinking…
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-white/10 px-4 py-3 flex-shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="flex gap-2"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Cohorts, risk, drift, search…"
              disabled={loading}
              className="bg-secondary/50 text-sm h-9 flex-1"
              aria-label="Message"
            />
            <Button type="submit" size="sm" disabled={loading || !input.trim()} className="h-9">
              Send
            </Button>
          </form>
        </div>
      </div>
    </>
  );
}
