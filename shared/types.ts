/**
 * Shared EDON types — imported by both frontend and SDK.
 * Source of truth for all decision, agent, and policy shapes.
 */

// ── Decisions ─────────────────────────────────────────────────────────────

export type Verdict = "ALLOW" | "BLOCK" | "ESCALATE" | "DEGRADE" | "PAUSE" | "ERROR";

export type ReasonCode =
  | "APPROVED"
  | "SCOPE_VIOLATION"
  | "RISK_TOO_HIGH"
  | "DATA_EXFIL"
  | "OUT_OF_HOURS"
  | "NEED_CONFIRMATION"
  | "LOOP_DETECTED"
  | "RATE_LIMIT"
  | "PROMPT_INJECTION"
  | "ANOMALY_DETECTED";

export interface Decision {
  id: string;
  action_id?: string;
  timestamp: string;
  verdict: Verdict;
  reason_code?: ReasonCode;
  explanation?: string;
  agent_id?: string;
  tool?: string | { name?: string; op?: string };
  latency_ms?: number;
  policy_version?: string;
  intent_id?: string;
  safe_alternative?: Record<string, unknown>;
  escalation_question?: string;
  escalation_options?: { id: string; label: string }[];
  policy_snapshot_hash?: string;
  request_payload?: Record<string, unknown>;
}

export interface EscalationOption {
  id: string;
  label: string;
}

// ── Agents ────────────────────────────────────────────────────────────────

export type AgentStatus = "active" | "paused" | "retired";

export interface AgentStats {
  total_actions: number;
  allow_count: number;
  block_count: number;
  block_rate: number;
  last_action_at?: string;
}

export interface AgentProfile {
  agent_id: string;
  name: string;
  agent_type: string;
  description?: string;
  capabilities?: string[];
  policy_pack?: string;
  status: AgentStatus;
  registered_at: string;
  last_seen_at?: string;
  metadata?: Record<string, unknown>;
  mag_enabled?: boolean;
  stats?: AgentStats;
  trend_7d?: TimeSeriesPoint[];
  top_tools?: string[];
  top_block_reasons?: BlockReason[];
  behavioral_cav_state?: string;
}

// ── Policies ──────────────────────────────────────────────────────────────

export type PolicyPackName =
  | "casual_user"
  | "market_analyst"
  | "ops_commander"
  | "founder_mode"
  | "helpdesk"
  | "autonomy_mode";

export interface PolicyPack {
  name: PolicyPackName | string;
  description: string;
  risk_level: "low" | "medium" | "high";
}

export type GovernanceModeKey = "safe" | "business" | "autonomy";

export interface GovernanceMode {
  key: GovernanceModeKey;
  label: string;
  packName: PolicyPackName;
  description: string;
}

// ── Metrics ───────────────────────────────────────────────────────────────

export interface Metrics {
  allowed_24h?: number;
  blocked_24h?: number;
  confirm_24h?: number;
  decisions_total?: number;
  latency_p50?: number;
  latency_p95?: number;
  latency_p99?: number;
}

export interface TimeSeriesPoint {
  timestamp: string;
  label: string;
  allowed: number;
  blocked: number;
  confirm: number;
}

export interface BlockReason {
  reason: ReasonCode | string;
  count: number;
}

// ── Gateway Health ────────────────────────────────────────────────────────

export interface GatewayHealth {
  status: "ok" | "degraded" | "down";
  version?: string;
  uptime_seconds?: number;
  active_preset?: string;
}

// ── Alerts ────────────────────────────────────────────────────────────────

export interface AlertPreferences {
  alert_on_blocked?: boolean;
  alert_on_policy_violation?: boolean;
  alert_on_drift?: boolean;
  alert_on_escalation?: boolean;
}

// ── Domains ───────────────────────────────────────────────────────────────

export type DomainId =
  | "ai_agents"
  | "industrial"
  | "drones"
  | "humanoids"
  | "medical"
  | "edge"
  | "swarm";
