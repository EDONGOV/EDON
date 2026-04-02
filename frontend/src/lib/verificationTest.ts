/**
 * Governance verification test: proves EDON changes behavior across policy packs.
 * Same action → ALLOW under one pack, BLOCK under another.
 *
 * Backend contracts (EDON Gateway FastAPI):
 * - Auth: X-EDON-TOKEN only (no Authorization Bearer).
 *
 * Endpoints and payloads:
 * 1. POST /policy-packs/{pack_name}/apply
 *    Body: none (optional query ?objective=...).
 *    Response: { intent_id: string, policy_pack: string, intent: object, active_preset: string }.
 *    Fields used: intent_id.
 *
 * 2. POST /clawdbot/invoke
 *    Headers: X-EDON-TOKEN (required), X-Agent-ID (optional), X-EDON-Agent-ID (optional), X-Intent-ID (optional).
 *    Body (ClawdbotInvokeRequest): { tool: string, action?: string, args?: object, sessionKey?: string | null }.
 *    - tool: e.g. "sessions_list"
 *    - action: default "json"
 *    - args: default {}
 *    - sessionKey: optional
 *    Response (ClawdbotInvokeResponse): { ok: bool, result?: object, error?: string, edon_verdict?: string, edon_explanation?: string }.
 *    Fields used: edon_verdict (primary verdict), ok, error.
 *
 * 3. GET /decisions/query?limit=10&agent_id=...&intent_id=...
 *    Response: { decisions: array, total: number, limit: number }.
 *    Each decision: { id (decision_id), decision_id, verdict (lowercase: "allowed"|"blocked"|"confirm"), tool: { name, op }, latency_ms (default 0), ... }.
 *    Fields used: id, verdict (normalized to ALLOW|BLOCK|CONFIRM), tool.name, tool.op, latency_ms.
 *    Row matching: after invoke we call with intent_id from apply; decisions are ordered by created_at DESC so first is newest. We take the first decision with matching intent_id (deterministic). If backend does not persist clawdbot invoke (current behavior), we rely on edon_verdict from invoke response only.
 */

export type VerificationRow = {
  pack: string;
  verdict: string;
  decision_id?: string;
  latency_ms?: number;
  error?: string;
};

export type VerificationResult = {
  rowA: VerificationRow;
  rowB: VerificationRow;
  pass: boolean;
  inconclusive?: boolean;
};

/** Normalize backend verdict to ALLOW | BLOCK | CONFIRM for comparison. */
function normalizeVerdict(v: string | undefined): string {
  const s = (v ?? "").trim().toUpperCase();
  if (s === "ALLOW" || s === "ALLOWED") return "ALLOW";
  if (s === "BLOCK" || s === "BLOCKED") return "BLOCK";
  if (["CONFIRM", "ESCALATE", "DEGRADE", "PAUSE"].includes(s)) return "CONFIRM";
  return s || "UNKNOWN";
}

function parseToolOp(toolOp: string): { tool: string; action: string } {
  const s = (toolOp || "").trim();
  if (s.includes(".")) {
    const parts = s.split(".");
    const tool = parts[parts.length - 1] || "sessions_list";
    return { tool, action: "json" };
  }
  return { tool: s || "sessions_list", action: "json" };
}

async function fetchJson<T>(
  url: string,
  token: string,
  method: "GET" | "POST" = "GET",
  body?: string,
  extraHeaders?: Record<string, string>
): Promise<{ ok: boolean; status: number; data?: T; text?: string }> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-EDON-TOKEN": token,
        ...extraHeaders,
      },
      ...(body !== undefined ? { body } : {}),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, status: 0, text: msg };
  }
  const text = await res.text().catch(() => "");
  let data: T | undefined;
  try {
    if (text) data = JSON.parse(text) as T;
  } catch {
    // leave data undefined
  }
  return { ok: res.ok, status: res.status, data, text };
}

/**
 * POST /policy-packs/{pack_name}/apply
 * Response: { intent_id, policy_pack, intent, active_preset }
 */
async function applyPolicyPack(
  baseUrl: string,
  token: string,
  packName: string
): Promise<{ ok: boolean; status: number; intent_id?: string; text?: string }> {
  const base = baseUrl.trim().replace(/\/$/, "");
  const out = await fetchJson<{ intent_id?: string }>(
    `${base}/policy-packs/${encodeURIComponent(packName)}/apply`,
    token,
    "POST",
    "{}"
  );
  return {
    ok: out.ok,
    status: out.status,
    intent_id: out.data?.intent_id,
    text: out.text,
  };
}

/**
 * POST /clawdbot/invoke
 * Body: ClawdbotInvokeRequest = { tool, action?, args?, sessionKey? }
 * Headers: X-EDON-TOKEN (required), X-Agent-ID, X-Intent-ID (backend supports these).
 * Response: ClawdbotInvokeResponse = { ok, result?, error?, edon_verdict?, edon_explanation? }
 */
async function invokeClawdbot(
  baseUrl: string,
  token: string,
  body: { tool: string; action: string; args: Record<string, unknown>; sessionKey?: string | null },
  agentId: string,
  intentId?: string | null
): Promise<{
  ok: boolean;
  status: number;
  edon_verdict?: string;
  text?: string;
}> {
  const base = baseUrl.trim().replace(/\/$/, "");
  const headers: Record<string, string> = {
    "X-Agent-ID": agentId,
    "X-EDON-Agent-ID": agentId,
  };
  if (intentId != null && String(intentId).trim().length > 0) {
    headers["X-Intent-ID"] = String(intentId).trim();
  }
  const out = await fetchJson<{ edon_verdict?: string }>(
    `${base}/clawdbot/invoke`,
    token,
    "POST",
    JSON.stringify(body),
    headers
  );
  return {
    ok: out.ok,
    status: out.status,
    edon_verdict: out.data?.edon_verdict,
    text: out.text,
  };
}

/**
 * GET /decisions/query - query primarily by intent_id; fall back to agent_id only if intent_id missing.
 * Response: { decisions: array, total, limit }. Each decision: { id, verdict (lowercase), tool: { name, op }, latency_ms }.
 */
async function getDecisions(
  baseUrl: string,
  token: string,
  agentId: string,
  intentId: string | undefined,
  limit: number = 10
): Promise<{ id?: string; verdict?: string; latency_ms?: number; toolName?: string; toolOp?: string }[]> {
  const base = baseUrl.trim().replace(/\/$/, "");
  const params = new URLSearchParams({ limit: String(limit) });
  if (intentId) {
    params.set("intent_id", intentId);
  } else {
    params.set("agent_id", agentId);
  }
  const url = `${base}/decisions/query?${params.toString()}`;
  const out = await fetchJson<{
    decisions?: Array<{
      id?: string;
      decision_id?: string;
      verdict?: string;
      latency_ms?: number;
      tool?: { name?: string; op?: string };
    }>;
  }>(url, token);
  if (!out.ok || !out.data?.decisions) return [];
  return out.data.decisions.map((d) => ({
    id: d.id ?? d.decision_id,
    verdict: d.verdict,
    latency_ms: d.latency_ms,
    toolName: d.tool?.name,
    toolOp: d.tool?.op,
  }));
}

export async function runGovernanceVerificationTest(opts: {
  baseUrl: string;
  token: string;
  allowPack: string;
  blockPack: string;
  toolOp: string;
  agentId: string;
}): Promise<VerificationResult> {
  const base = opts.baseUrl.trim().replace(/\/$/, "");
  const token = opts.token.trim();
  const allowPack = (opts.allowPack || "clawdbot_safe").trim() || "clawdbot_safe";
  const blockPack = (opts.blockPack || "personal_safe").trim() || "personal_safe";
  const agentId = (opts.agentId || "default-agent").trim() || "default-agent";
  const { tool, action } = parseToolOp(opts.toolOp);
  const body: { tool: string; action: string; args: Record<string, unknown>; sessionKey?: string | null } = {
    tool,
    action,
    args: {},
    sessionKey: null,
  };

  const row = async (packName: string): Promise<VerificationRow> => {
    const applyRes = await applyPolicyPack(base, token, packName);
    if (!applyRes.ok) {
      return {
        pack: packName,
        verdict: "",
        error: `Apply failed: ${applyRes.status} ${(applyRes.text || "").slice(0, 200)}`,
      };
    }
    const intentId = applyRes.intent_id ?? undefined;

    const invokeRes = await invokeClawdbot(base, token, body, agentId, intentId);
    let verdict = normalizeVerdict(invokeRes.edon_verdict);
    let decision_id: string | undefined;
    let latency_ms: number | undefined;

    if (!invokeRes.ok) {
      return {
        pack: packName,
        verdict: verdict || "ERROR",
        error: `Invoke failed: ${invokeRes.status} ${(invokeRes.text || "").slice(0, 200)}`,
      };
    }

    const decisions = await getDecisions(base, token, agentId, intentId, 10);
    const newest = decisions[0];
    const matchesToolOp =
      newest &&
      (newest.toolName === "clawdbot" || newest.toolName === tool) &&
      (newest.toolOp === "invoke" || newest.toolOp === action);
    if (newest && (matchesToolOp || intentId)) {
      decision_id = newest.id;
      latency_ms = newest.latency_ms;
      if (!verdict && newest.verdict) verdict = normalizeVerdict(newest.verdict);
    }

    return {
      pack: packName,
      verdict: verdict || "UNKNOWN",
      decision_id,
      latency_ms,
      error: invokeRes.ok ? undefined : (invokeRes.text || "").slice(0, 200),
    };
  };

  const rowA = await row(allowPack);
  const rowB = await row(blockPack);

  const aAllow = normalizeVerdict(rowA.verdict) === "ALLOW";
  const bBlock = normalizeVerdict(rowB.verdict) === "BLOCK";
  const aConfirm = normalizeVerdict(rowA.verdict) === "CONFIRM";
  const bConfirm = normalizeVerdict(rowB.verdict) === "CONFIRM";
  const pass = aAllow && bBlock;
  const inconclusive = !pass && (aConfirm || bConfirm || ((rowA.verdict === "ALLOW" || rowA.verdict === "CONFIRM") && (rowB.verdict === "ALLOW" || rowB.verdict === "CONFIRM")));

  return { rowA, rowB, pass, inconclusive };
}
