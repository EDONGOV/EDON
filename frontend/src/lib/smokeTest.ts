/**
 * Governance smoke test: verifies EDON Gateway connectivity and governance path end-to-end.
 * All requests use X-EDON-TOKEN only (no Authorization Bearer).
 */

export type SmokeStep = {
  name: string;
  ok: boolean;
  status?: number;
  ms: number;
  details?: string;
};

const MAX_DETAILS_LEN = 300;

async function fetchStep(
  url: string,
  token: string,
  method: "GET" | "POST" = "GET",
  body?: string
): Promise<{ ok: boolean; status: number; ms: number; details?: string }> {
  const start = performance.now();
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-EDON-TOKEN": token,
      },
      ...(body !== undefined ? { body } : {}),
    });
  } catch (err) {
    const ms = Math.round(performance.now() - start);
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, status: 0, ms, details: msg.slice(0, MAX_DETAILS_LEN) };
  }
  const ms = Math.round(performance.now() - start);
  let details: string | undefined;
  if (!res.ok) {
    try {
      const text = await res.text();
      details = text.slice(0, MAX_DETAILS_LEN);
      if (text.length > MAX_DETAILS_LEN) details += "...";
    } catch {
      details = res.statusText || `HTTP ${res.status}`;
    }
  }
  return { ok: res.ok, status: res.status, ms, details };
}

export async function runGovernanceSmokeTest(opts: {
  baseUrl: string;
  token: string;
  packName?: string;
}): Promise<{ steps: SmokeStep[]; ok: boolean }> {
  const base = opts.baseUrl.trim().replace(/\/$/, "");
  const token = opts.token.trim();
  const packName = (opts.packName || "clawdbot_safe").trim() || "clawdbot_safe";

  const steps: SmokeStep[] = [];

  // Step A: GET /health
  const a = await fetchStep(`${base}/health`, token);
  steps.push({ name: "GET /health", ok: a.ok, status: a.status, ms: a.ms, details: a.details });

  // Step B: GET /integrations/account/integrations
  const b = await fetchStep(`${base}/integrations/account/integrations`, token);
  steps.push({
    name: "GET /integrations/account/integrations",
    ok: b.ok,
    status: b.status,
    ms: b.ms,
    details: b.details,
  });

  // Step C: GET /policy-packs
  const c = await fetchStep(`${base}/policy-packs`, token);
  steps.push({ name: "GET /policy-packs", ok: c.ok, status: c.status, ms: c.ms, details: c.details });

  // Step D: POST /policy-packs/{pack}/apply
  const d = await fetchStep(`${base}/policy-packs/${packName}/apply`, token, "POST", "{}");
  steps.push({
    name: `POST /policy-packs/${packName}/apply`,
    ok: d.ok,
    status: d.status,
    ms: d.ms,
    details: d.details,
  });

  // Step E: GET /decisions/query?limit=1
  const e = await fetchStep(`${base}/decisions/query?limit=1`, token);
  steps.push({
    name: "GET /decisions/query?limit=1",
    ok: e.ok,
    status: e.status,
    ms: e.ms,
    details: e.details,
  });

  const ok = steps.every((s) => s.ok);
  return { steps, ok };
}
