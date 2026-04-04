/**
 * Dashboard context for the side chat: everything the AI needs to answer
 * questions about the customer's audits, decisions, metrics, and policies.
 */

import { edonApi } from "@/lib/api";
import type { Decision } from "@/lib/api";

// ─────────────────────────────────────────────
// Governance mode catalogue (mirrors Policies.tsx GOVERNANCE_MODES)
// ─────────────────────────────────────────────
export interface GovernanceMode {
  key: string;
  packName: string;
  title: string;
  what: string;
  scope: string;
  escalation: string;
  useCase: string;
}

export const GOVERNANCE_MODES: GovernanceMode[] = [
  {
    key: "safe",
    packName: "casual_user",
    title: "Safe Mode",
    what: "Read-only by default. Stops any action that writes, sends, or modifies before it executes.",
    scope: "Web search, file reads, email reads, calendar reads. Everything else requires confirmation or is blocked.",
    escalation: "Immediate alert when a policy boundary is crossed. Every blocked action is logged.",
    useCase: "New deployments, consumer-facing agents, and any system where safety is non-negotiable.",
  },
  {
    key: "business",
    packName: "ops_commander",
    title: "Business Mode",
    what: "Full workflow automation. Writes, sends, and task management run freely with confirmation on high-stakes ops.",
    scope: "Emails, calendar, tasks, APIs, and database reads. Financial and destructive ops require human approval.",
    escalation: "Escalates to team lead or audit log — full accountability without slowing operations.",
    useCase: "Ops teams, business automation pipelines, and enterprise-scale deployments.",
  },
  {
    key: "autonomy",
    packName: "autonomy_mode",
    title: "Autonomy Mode",
    what: "EDON runs continuously — includes physical agent tools. Only true safety violations are blocked.",
    scope: "Nearly everything including navigation, sensors, shell, and code execution. Irreversible ops confirm first.",
    escalation: "Silent by design. Only critical safety violations — finance transfers, system admin — surface.",
    useCase: "High-trust environments, always-on automation, robotics, and physical AI deployments.",
  },
];

/** Look up a governance mode by any alias — title, packName, or key. */
export function findGovernanceMode(query: string): GovernanceMode | undefined {
  const q = query.toLowerCase().replace(/[_-]/g, " ").trim();
  return GOVERNANCE_MODES.find(
    (m) =>
      m.title.toLowerCase() === q ||
      m.key === q ||
      m.packName.replace(/_/g, " ") === q ||
      m.title.toLowerCase().includes(q) ||
      q.includes(m.title.toLowerCase()) ||
      q.split(" ").some((w) => w.length > 3 && m.title.toLowerCase().includes(w))
  );
}

// ─────────────────────────────────────────────
// Friendly display name helpers
// ─────────────────────────────────────────────

const PRESET_NAMES: Record<string, string> = {
  ops_admin:      "Autonomy Mode",
  work_safe:      "Work Safe Mode",
  personal_safe:  "Personal Safety Mode",
  strict:         "Strict Mode",
  permissive:     "Permissive Mode",
  monitor_only:   "Monitor Only",
  default:        "Standard Mode",
  balanced:       "Balanced Mode",
  high_trust:     "High Trust Mode",
  low_trust:      "Low Trust Mode",
};

const REASON_NAMES: Record<string, string> = {
  SCOPE_VIOLATION:    "Scope Violation",
  OUT_OF_HOURS:       "Outside Operating Hours",
  RISK_TOO_HIGH:      "Risk Too High",
  RATE_LIMIT:         "Rate Limited",
  RATE_LIMIT_EXCEEDED:"Rate Limit Exceeded",
  POLICY_VIOLATION:   "Policy Violation",
  INTENT_MISALIGN:    "Intent Mismatch",
  INTENT_MISMATCH:    "Intent Mismatch",
  HUMAN_REVIEW:       "Pending Human Review",
  HUMAN_REVIEW_REQUIRED: "Human Review Required",
  ANOMALY_DETECTED:   "Anomaly Detected",
  LOW_CONFIDENCE:     "Low Confidence",
  UNAUTHORIZED:       "Unauthorized",
  FORBIDDEN:          "Forbidden Action",
  PAYLOAD_TOO_LARGE:  "Payload Too Large",
  TIMEOUT:            "Timed Out",
  BUDGET_EXCEEDED:    "Budget Exceeded",
  DOSAGE_EXCEEDED:    "Dosage Exceeded",
  QUORUM_FAILED:      "Quorum Not Met",
  PROMPT_INJECTION:   "Prompt Injection Detected",
};

/** Convert any raw identifier to a readable label. */
export function friendlyName(raw: string | null | undefined): string {
  if (!raw) return "—";
  const preset = PRESET_NAMES[raw.toLowerCase().replace(/-/g, "_")];
  if (preset) return preset;
  const reason = REASON_NAMES[raw.toUpperCase()];
  if (reason) return reason;
  // Fallback: SNAKE_CASE → Title Case, underscore_name → Title Case
  return raw
    .replace(/[_-]/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface DashboardContext {
  fetched_at: string;
  metrics: {
    allowed_24h?: number;
    blocked_24h?: number;
    confirm_24h?: number;
    decisions_total?: number;
    latency_p50?: number;
    latency_p95?: number;
    latency_p99?: number;
  };
  health: {
    status?: string;
    version?: string;
    uptime_seconds?: number;
    active_preset?: string;
  } | null;
  recent_decisions: Array<{
    id: string;
    timestamp: string;
    verdict: string;
    reason_code?: string | null;
    explanation?: string;
    agent_id?: string | null;
    tool?: string;
    op?: string;
  }>;
  recent_audit: Array<{
    id: string;
    timestamp: string;
    verdict: string;
    reason_code?: string | null;
    explanation?: string;
    agent_id?: string | null;
    tool?: string;
    op?: string;
  }>;
  block_reasons: Array<{ reason: string; count: number }>;
  policy_packs: Array<{ name: string; description: string; risk_level: string }>;
}

const DEFAULT_LIMIT = 40;

/**
 * Fetch all dashboard data the chat AI should know about.
 * Call this before sending a message so the backend (or local reply) can use it.
 */
export async function fetchDashboardContext(): Promise<DashboardContext> {
  const fetched_at = new Date().toISOString();

  const [metricsRes, decisionsRes, auditRes, healthRes, blockReasonsRes, policyPacksRes] =
    await Promise.allSettled([
      edonApi.getMetrics(),
      edonApi.getDecisions({ limit: DEFAULT_LIMIT }),
      edonApi.getAudit({ limit: DEFAULT_LIMIT }).catch((e) => (e?.message === "forbidden" ? { records: [], total: 0 } : Promise.reject(e))),
      edonApi.getHealth(),
      edonApi.getBlockReasons?.() ?? Promise.resolve([]),
      edonApi.getPolicyPacks?.() ?? Promise.resolve([]),
    ]);

  const metrics =
    metricsRes.status === "fulfilled"
      ? (metricsRes.value as DashboardContext["metrics"])
      : {};

  const decisions =
    decisionsRes.status === "fulfilled" && decisionsRes.value?.decisions
      ? decisionsRes.value.decisions
      : [];

  let auditRecords: Decision[] = [];
  if (auditRes.status === "fulfilled" && auditRes.value?.records) {
    auditRecords = auditRes.value.records;
  }

  const health =
    healthRes.status === "fulfilled"
      ? {
          status: (healthRes.value as { status?: string }).status,
          version: (healthRes.value as { version?: string }).version,
          uptime_seconds: (healthRes.value as { uptime_seconds?: number }).uptime_seconds,
          active_preset: (healthRes.value as { governor?: { active_preset?: { preset_name?: string } } }).governor?.active_preset?.preset_name,
        }
      : null;

  const block_reasons =
    blockReasonsRes.status === "fulfilled" && Array.isArray(blockReasonsRes.value)
      ? blockReasonsRes.value
      : [];

  const policy_packs =
    policyPacksRes.status === "fulfilled" && Array.isArray(policyPacksRes.value)
      ? policyPacksRes.value.map((p: { name: string; description?: string; risk_level?: string }) => ({
          name: p.name,
          description: p.description ?? "",
          risk_level: p.risk_level ?? "",
        }))
      : [];

  const toSummary = (d: Decision) => ({
    id: d.id ?? "",
    timestamp: d.timestamp ?? d.created_at ?? "",
    verdict: typeof d.verdict === "string" ? d.verdict : "unknown",
    reason_code: d.reason_code ?? null,
    explanation: d.explanation ?? "",
    agent_id: d.agent_id ?? null,
    tool: typeof d.tool === "object" && d.tool?.name ? d.tool.name : undefined,
    op: typeof d.tool === "object" && d.tool?.op ? d.tool.op : (typeof d.tool === "string" ? d.tool : undefined),
  });

  return {
    fetched_at,
    metrics,
    health,
    recent_decisions: decisions.slice(0, DEFAULT_LIMIT).map(toSummary),
    recent_audit: auditRecords.slice(0, DEFAULT_LIMIT).map(toSummary),
    block_reasons,
    policy_packs,
  };
}

/**
 * Build a rich system prompt for the LLM that includes the full dashboard snapshot.
 * This is sent as the system message so the model answers from real-time data.
 */
export function buildGreeting(ctx: DashboardContext): string {
  const hour = new Date().getHours();
  const timeGreeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const displayName = localStorage.getItem("edon_display_name") || "";
  const firstName = displayName ? displayName.split(" ")[0] : null;
  const nameGreet = firstName ? `, ${firstName}` : "";

  const presetRaw = ctx.health?.active_preset;
  const preset = friendlyName(presetRaw);
  const status = ctx.health?.status ?? "unknown";
  const b = ctx.metrics?.blocked_24h ?? 0;
  const a = ctx.metrics?.allowed_24h ?? 0;
  const total = ctx.metrics?.decisions_total ?? a + b;

  const lines: string[] = [
    `${timeGreeting}${nameGreet}! I'm your EDON governance assistant — here to help you monitor, understand, and control everything your agents are doing.`,
    "",
  ];

  if (status === "healthy") {
    lines.push(`Your gateway is **healthy** and running in **${preset}**.`);
  } else if (status !== "unknown") {
    lines.push(`Your gateway is currently **${status}** and running in **${preset}**.`);
  }

  if (total > 0) {
    const blockPct = total > 0 ? Math.round((b / total) * 100) : 0;
    if (b > 0) {
      lines.push(`In the last 24h, **${b}** actions were blocked (${blockPct}% of ${total} total).`);
      if (ctx.block_reasons.length > 0) {
        lines.push(`Top reason: **${friendlyName(ctx.block_reasons[0].reason)}** — flagged ${ctx.block_reasons[0].count}× today.`);
      }
    } else {
      lines.push(`In the last 24h, **${a}** actions were allowed with no blocks.`);
    }
  }

  lines.push("", "What would you like to dig into?");
  return lines.join("\n");
}

export function buildSystemPrompt(ctx: DashboardContext): string {
  const activePack = ctx.health?.active_preset
    ? ctx.health.active_preset
    : localStorage.getItem("edon_active_policy_pack") || "unknown";

  const displayName = localStorage.getItem("edon_display_name") || "";
  const email = localStorage.getItem("edon_user_email") || "";
  const firstName = displayName ? displayName.split(" ")[0] : null;

  const teamMembers: Array<{ name: string; email: string; role: string }> = (() => {
    try { return JSON.parse(localStorage.getItem("edon_team_members") || "[]"); } catch { return []; }
  })();

  const sharedAudits: Array<{ record_summary: { action?: string; verdict?: string }; note?: string }> = (() => {
    try { return JSON.parse(localStorage.getItem("edon_shared_audits") || "[]"); } catch { return []; }
  })();

  const lines: string[] = [
    "You are EDON's dedicated governance intelligence assistant — a personalized AI advisor embedded directly in the customer's EDON dashboard.",
    "",
    "## Your Identity & Role",
    "- You represent EDON professionally: confident, precise, proactive, and genuinely helpful.",
    "- You are a governance expert — you understand AI agent safety, policy enforcement, audit trails, and compliance.",
    "- You speak like a trusted advisor, not a generic chatbot. Be warm but professional.",
    "- You always answer from the live dashboard data below — never make up numbers or events.",
    `- The customer's name is: ${firstName ? `**${firstName}**${displayName !== firstName ? ` (${displayName})` : ""}` : email || "unknown"}. Address them by first name when natural.`,
    "",
    "## How to Respond",
    "- Read the customer's intent, not just their exact words. 'what happened' means recent decisions. 'why is it blocking' means block reasons.",
    "- When showing data, be specific: use actual numbers, names, and reasons from the snapshot below.",
    "- NEVER show raw identifiers like `ops_admin`, `SCOPE_VIOLATION`, `work_safe`. Always convert them to friendly names: `ops_admin` → 'Autonomy Mode', `SCOPE_VIOLATION` → 'Scope Violation', `OUT_OF_HOURS` → 'Outside Operating Hours', etc.",
    "- If something looks unusual (e.g. very high block rate, degraded gateway), proactively mention it.",
    "- Keep responses focused. Don't include data sections that weren't asked about.",
    "- Format clearly with bold headings and bullet points when showing lists.",
    "- If you don't have data to answer, say so honestly and suggest where to find it.",
    "",
    "## Live Dashboard Snapshot",
    `Fetched at: ${ctx.fetched_at}`,
    "",
  ];

  // Metrics
  const a = ctx.metrics?.allowed_24h ?? 0;
  const b = ctx.metrics?.blocked_24h ?? 0;
  const c = ctx.metrics?.confirm_24h ?? 0;
  lines.push(
    "### Metrics (last 24h)",
    `- Allowed: ${a}`,
    `- Blocked: ${b}`,
    `- Confirm/escalate: ${c}`,
    `- Total: ${ctx.metrics?.decisions_total ?? a + b + c}`,
    ctx.metrics?.latency_p50 ? `- Latency p50: ${ctx.metrics.latency_p50}ms` : "",
    ctx.metrics?.latency_p95 ? `- Latency p95: ${ctx.metrics.latency_p95}ms` : "",
    ""
  );

  // Gateway
  if (ctx.health) {
    const uptime = ctx.health.uptime_seconds;
    lines.push(
      "### Gateway",
      `- Status: ${ctx.health.status ?? "unknown"}`,
      `- Active policy pack: ${activePack}`,
      uptime != null ? `- Uptime: ${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m` : "",
      ""
    );
  }

  // Top block reasons
  if (ctx.block_reasons?.length > 0) {
    lines.push("### Top block reasons");
    ctx.block_reasons.slice(0, 8).forEach((r) => lines.push(`- ${r.reason}: ${r.count} times`));
    lines.push("");
  }

  // Recent decisions sample
  if (ctx.recent_decisions?.length > 0) {
    lines.push("### Recent decisions (latest 20)");
    ctx.recent_decisions.slice(0, 20).forEach((d) => {
      const tool = d.tool && d.op ? `${d.tool}.${d.op}` : d.tool || "—";
      lines.push(`- [${d.verdict}] ${tool} | agent: ${d.agent_id ?? "—"} | reason: ${d.reason_code ?? "—"} | ${d.explanation?.slice(0, 80) ?? ""}`);
    });
    lines.push("");
  }

  // Recent audit sample
  if (ctx.recent_audit.length > 0) {
    lines.push("### Recent audit events (latest 20)");
    ctx.recent_audit.slice(0, 20).forEach((d) => {
      const tool = d.tool && d.op ? `${d.tool}.${d.op}` : d.tool || "—";
      lines.push(`- [${d.verdict}] ${tool} | agent: ${d.agent_id ?? "—"} | ${new Date(d.timestamp).toLocaleString()}`);
    });
    lines.push("");
  }

  // Policy packs
  if (ctx.policy_packs.length > 0) {
    lines.push("### Available policy packs");
    ctx.policy_packs.forEach((p) => lines.push(`- ${p.name} (${p.risk_level}): ${p.description}`));
    lines.push("");
  }

  // Customer identity
  if (displayName || email) {
    lines.push("### Customer");
    if (displayName) lines.push(`- Name: ${displayName}`);
    if (email) lines.push(`- Email: ${email}`);
    lines.push("");
  }

  // Team
  if (teamMembers.length > 0) {
    lines.push("### Team members");
    teamMembers.forEach((m) => lines.push(`- ${m.name} <${m.email}> — ${m.role}`));
    lines.push("");
  }

  // Shared audits
  if (sharedAudits.length > 0) {
    lines.push("### Shared audit records");
    sharedAudits.slice(0, 10).forEach((s) => {
      const action = s.record_summary?.action ?? "—";
      const verdict = s.record_summary?.verdict ?? "—";
      lines.push(`- ${action} [${verdict}]${s.note ? ` — note: ${s.note}` : ""}`);
    });
    lines.push("");
  }

  return lines.filter((l) => l !== undefined).join("\n");
}

/**
 * Generate a text summary of dashboard context for inclusion in an LLM prompt.
 * The backend can paste this into the system or user message so the model answers from real data.
 */
export function dashboardContextToPromptText(ctx: DashboardContext): string {
  const lines: string[] = [
    "## Dashboard snapshot (use this to answer the user)",
    `Fetched at: ${ctx.fetched_at}`,
    "",
    "### Metrics (24h)",
    `- Allowed: ${ctx.metrics?.allowed_24h ?? "—"}`,
    `- Blocked: ${ctx.metrics?.blocked_24h ?? "—"}`,
    `- Confirm needed: ${ctx.metrics?.confirm_24h ?? "—"}`,
    `- Total decisions: ${ctx.metrics?.decisions_total ?? "—"}`,
    ctx.metrics?.latency_p50 != null ? `- Latency p50: ${ctx.metrics.latency_p50}ms` : "",
    "",
  ];

  if (ctx.health) {
    lines.push(
      "### Gateway",
      `- Status: ${ctx.health.status ?? "—"}`,
      `- Active preset: ${ctx.health.active_preset ?? "—"}`,
      ctx.health.uptime_seconds != null
        ? `- Uptime: ${Math.floor(ctx.health.uptime_seconds / 3600)}h ${Math.floor((ctx.health.uptime_seconds % 3600) / 60)}m`
        : "",
      ""
    );
  }

  if (ctx.block_reasons.length > 0) {
    lines.push("### Top block reasons", "");
    ctx.block_reasons.slice(0, 10).forEach((r) => lines.push(`- ${r.reason}: ${r.count}`));
    lines.push("");
  }

  if (ctx.recent_decisions?.length > 0) {
    lines.push("### Recent decisions (sample)", "");
    ctx.recent_decisions.slice(0, 15).forEach((d) => {
      const toolOp = d.tool && d.op ? `${d.tool}.${d.op}` : "—";
      lines.push(`- ${d.timestamp} | ${d.verdict} | ${toolOp} | ${d.reason_code ?? ""} | ${d.explanation?.slice(0, 60) ?? ""}`);
    });
    lines.push("");
  }

  if (ctx.recent_audit.length > 0) {
    lines.push("### Recent audit events (sample)", "");
    ctx.recent_audit.slice(0, 15).forEach((d) => {
      const toolOp = d.tool && d.op ? `${d.tool}.${d.op}` : "—";
      lines.push(`- ${d.timestamp} | ${d.verdict} | ${d.agent_id ?? "—"} | ${toolOp} | ${d.reason_code ?? ""}`);
    });
    lines.push("");
  }

  if (ctx.policy_packs.length > 0) {
    lines.push("### Policy packs", "");
    ctx.policy_packs.forEach((p) => lines.push(`- ${p.name}: ${p.description} (${p.risk_level})`));
  }

  return lines.filter(Boolean).join("\n");
}

/* ─────────────────────────────────────────────
   Intent scoring — words that signal each topic
───────────────────────────────────────────── */
const INTENT_SIGNALS: Record<string, string[]> = {
  metrics: [
    "how many", "count", "total", "number", "how much", "stats", "statistics",
    "allowed", "blocked", "confirm", "escalat", "volume",
    "rate", "percent", "breakdown", "24h",
  ],
  why: [
    "why", "reason", "cause", "what caused", "because", "resulted",
    "what made", "due to", "how come",
  ],
  recent: [
    "recent", "latest", "last few", "what happened", "what's going on",
    "going on", "right now", "what occur", "today", "events", "all events",
    "tell me", "show me", "list", "activity",
  ],
  status: [
    "status", "health", "is it", "working", "running", "connected", "up", "down",
    "operational", "online", "offline",
  ],
  policy: [
    "policy", "policies", "preset", "presets", "rules", "rule", "configured",
    "setting", "pack", "packs", "restriction", "how many polic", "autonomy",
    "mode", "governance mode", "what mode",
  ],
  audit: [
    "audit", "log", "trail", "history", "record", "logged",
  ],
};

function scoreIntents(query: string): Record<string, number> {
  const q = query.toLowerCase();
  const scores: Record<string, number> = {};
  for (const [intent, signals] of Object.entries(INTENT_SIGNALS)) {
    scores[intent] = signals.filter((s) => q.includes(s)).length;
  }
  return scores;
}

/**
 * Local reply when the backend is unavailable or in demo mode:
 * answer from the actual dashboard context so the user gets accurate info.
 */
export function getDashboardAwareReply(query: string, ctx: DashboardContext): string {
  const scores = scoreIntents(query);

  // Data builders
  const metricsBlock = (): string => {
    const a = ctx.metrics?.allowed_24h ?? 0;
    const b = ctx.metrics?.blocked_24h ?? 0;
    const c = ctx.metrics?.confirm_24h ?? 0;
    const total = ctx.metrics?.decisions_total ?? a + b + c;
    const blockPct = total > 0 ? Math.round((b / total) * 100) : 0;
    return [
      "**Decisions (last 24h)**",
      `- Allowed: **${a}**`,
      `- Blocked: **${b}** (${blockPct}% of total)`,
      `- Confirm/escalate: **${c}**`,
      `- Total: **${total}**`,
    ].join("\n");
  };

  const friendlyVerdict = (v: string) =>
    v === "blocked" || v === "BLOCK" ? "Blocked"
    : v === "allowed" || v === "ALLOW" ? "Allowed"
    : v === "escalated" || v === "ESCALATE" ? "Escalated"
    : v === "confirm" || v === "CONFIRM" ? "Needs Review"
    : friendlyName(v);

  const whyBlock = (): string => {
    if (ctx.block_reasons.length > 0) {
      const lines = ctx.block_reasons.slice(0, 6).map((r) => `- **${friendlyName(r.reason)}**: ${r.count}×`);
      return "**Why actions were blocked**\n" + lines.join("\n");
    }
    const blocked = [...ctx.recent_decisions, ...ctx.recent_audit]
      .filter((d) => d.verdict === "blocked" || d.verdict === "BLOCK")
      .slice(0, 6);
    if (blocked.length === 0) return "No block-reason data in this snapshot.";
    const lines = blocked.map((d) => {
      const op = d.tool && d.op ? `${d.tool}.${d.op}` : d.tool ?? "—";
      return `- **${op}** — ${friendlyName(d.reason_code)}${d.explanation ? `: ${d.explanation.slice(0, 90)}` : ""}`;
    });
    return "**Recent blocked decisions**\n" + lines.join("\n");
  };

  const recentBlock = (): string => {
    const all = [...ctx.recent_decisions, ...ctx.recent_audit].slice(0, 8);
    if (all.length === 0) return "No recent decisions in this snapshot.";
    const lines = all.map((d) => {
      const op = d.tool && d.op ? `${d.tool}.${d.op}` : d.tool ?? "—";
      const ts = d.timestamp ? new Date(d.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      return `- [**${friendlyVerdict(d.verdict)}**] ${op}${d.reason_code ? ` — ${friendlyName(d.reason_code)}` : ""}${ts ? ` · ${ts}` : ""}`;
    });
    return "**Recent decisions**\n" + lines.join("\n");
  };

  const statusBlock = (): string => {
    const status = ctx.health?.status ?? "unknown";
    const preset = friendlyName(ctx.health?.active_preset);
    const uptime = ctx.health?.uptime_seconds;
    const up = uptime != null ? ` · uptime ${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m` : "";
    return `**Gateway:** ${status}${up} · **${preset}**`;
  };

  const policyBlock = (): string => {
    const preset = friendlyName(ctx.health?.active_preset);
    const n = ctx.policy_packs.length;
    const lines = [`**Active mode:** ${preset}`, `**Policy packs (${n}):**`];
    if (n > 0) {
      ctx.policy_packs.forEach((p) => lines.push(`- **${friendlyName(p.name)}** (${p.risk_level})${p.description ? `: ${p.description}` : ""}`));
    } else {
      lines.push("- No policy pack data in this snapshot. Open the Policies page to manage packs.");
    }
    return lines.join("\n");
  };

  const auditBlock = (): string => {
    const n = ctx.recent_audit.length;
    if (n === 0) return "No audit events in this snapshot. Open the Audit page for full history.";
    const lines = ctx.recent_audit.slice(0, 6).map((d) => {
      const op = d.tool && d.op ? `${d.tool}.${d.op}` : d.tool ?? "—";
      return `- [${friendlyVerdict(d.verdict)}] ${op} · ${d.agent_id ?? "—"}`;
    });
    return `**Audit events (${n} in context)**\n${lines.join("\n")}`;
  };

  const q = query.toLowerCase().trim();

  // Definition / "what is X" questions — don't dump data, give a targeted answer
  const isDefinitionQ = /^what (is|are|does|do)\b/.test(q) || /^(explain|describe|tell me about|how does)\b/.test(q);
  if (isDefinitionQ) {
    // Try to map the subject to something we know about
    // Check the governance mode catalogue first (covers Business Mode, Safe Mode, Autonomy Mode, etc.)
    const modeMatch = findGovernanceMode(subject || q);
    if (modeMatch) {
      const activePreset = friendlyName(ctx.health?.active_preset);
      const isActive = ctx.health?.active_preset === modeMatch.packName ||
        friendlyName(ctx.health?.active_preset).toLowerCase() === modeMatch.title.toLowerCase();
      return [
        `**${modeMatch.title}** is one of your EDON governance modes.`,
        "",
        `**What it does:** ${modeMatch.what}`,
        `**What's allowed:** ${modeMatch.scope}`,
        `**Escalation:** ${modeMatch.escalation}`,
        `**Best for:** ${modeMatch.useCase}`,
        "",
        isActive
          ? `You're currently running in **${modeMatch.title}**.`
          : `You're currently in **${activePreset}**. You can switch to ${modeMatch.title} from the Policies page.`,
      ].join("\n");
    }

    if (/preset|governance mode|policy mode/i.test(q)) {
      return policyBlock();
    }
    if (/audit/i.test(q)) {
      return `The **audit trail** is a tamper-evident log of every governance decision — every allowed, blocked, and escalated action is recorded with agent ID, tool, verdict, and reason.\n\n${auditBlock()}`;
    }
    if (/policy|pack/i.test(q)) {
      return policyBlock();
    }
    if (/agent/i.test(q)) {
      return `An **agent** is any AI system or autonomous process registered with EDON. Every action it tries to take goes through the governor first, which checks it against your active policy before allowing or blocking it. View your registered agents on the Agents page.`;
    }
    if (/governor|governance/i.test(q)) {
      const preset = friendlyName(ctx.health?.active_preset);
      return `The **EDON governor** is the real-time safety layer that sits between your agents and the outside world. Every action request is evaluated against your policy — the governor can allow it, block it, request human confirmation, or escalate it.\n\nYou're currently running in **${preset}**.`;
    }
    // Extract the subject being asked about (strip question words)
    const subject = q
      .replace(/^what (is|are|does|do)\s+/i, "")
      .replace(/^(explain|describe|tell me about|how does)\s+/i, "")
      .replace(/[?.,!]$/g, "")
      .trim();

    // Search policy packs for a fuzzy match
    const matchedPack = ctx.policy_packs.find((p) => {
      const packName = p.name.toLowerCase();
      const packDesc = p.description?.toLowerCase() ?? "";
      return (
        packName.includes(subject) ||
        subject.includes(packName) ||
        packDesc.includes(subject) ||
        subject.split(" ").some((w) => w.length > 3 && packName.includes(w))
      );
    });

    if (matchedPack) {
      return [
        `**${matchedPack.name}** is one of your governance presets.`,
        "",
        matchedPack.description ? matchedPack.description : "",
        `Risk level: **${matchedPack.risk_level}**`,
        "",
        `Your currently active mode is **${friendlyName(ctx.health?.active_preset)}**. You can switch to ${matchedPack.name} from the Policies page.`,
      ].filter(Boolean).join("\n");
    }

    // Nothing matched — say so and list governance modes + API packs
    const modeList = GOVERNANCE_MODES.map((m) => `- **${m.title}**: ${m.what}`).join("\n");
    const apiPacks = ctx.policy_packs.length > 0
      ? ctx.policy_packs.map((p) => `- **${friendlyName(p.name)}** (${p.risk_level}): ${p.description}`).join("\n")
      : "";

    return [
      `I don't see anything called "${subject}" in your workspace.`,
      "",
      `Your active mode is **${friendlyName(ctx.health?.active_preset)}**. Here are your available governance modes:`,
      "",
      modeList,
      apiPacks ? `\n**Policy packs:**\n${apiPacks}` : "",
    ].filter(Boolean).join("\n");
  }

  // Compose response from detected intents — only include sections that scored
  const parts: string[] = [];
  const has = (intent: string) => scores[intent] > 0;
  const totalSignals = Object.values(scores).reduce((s, v) => s + v, 0);

  if (totalSignals === 0) {
    // Completely ambiguous — full dashboard summary
    return [statusBlock(), "", metricsBlock(), "", ctx.block_reasons.length > 0 ? whyBlock() : ""].filter(Boolean).join("\n");
  }

  // Ordered by likely relevance; never include a section unless its intent scored
  if (has("status")) parts.push(statusBlock());
  if (has("metrics")) parts.push(metricsBlock());
  if (has("why")) parts.push(whyBlock());
  if (has("recent")) parts.push(recentBlock());
  if (has("policy")) parts.push(policyBlock());
  if (has("audit")) parts.push(auditBlock());

  if (parts.length === 0) {
    return [statusBlock(), "", metricsBlock(), "", whyBlock()].join("\n");
  }

  return parts.join("\n\n");
}
