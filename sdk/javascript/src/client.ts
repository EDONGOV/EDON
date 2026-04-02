/** EDON JavaScript/TypeScript SDK */

export interface EdonConfig {
  token: string;
  baseUrl?: string;
}

export interface EvaluateRequest {
  action_type: string;
  agent_id: string;
  payload?: Record<string, unknown>;
  intent_id?: string;
}

export interface Decision {
  action_id: string;
  verdict: "ALLOW" | "BLOCK" | "ESCALATE" | "DEGRADE" | "PAUSE" | "ERROR";
  reason_code: string;
  explanation: string;
  safe_alternative?: Record<string, unknown>;
  escalation_question?: string;
  escalation_options?: { id: string; label: string }[];
  policy_snapshot_hash: string;
  latency_ms?: number;
}

export class EdonClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor({ token, baseUrl = "https://edon-gateway.fly.dev" }: EdonConfig) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = { "X-EDON-TOKEN": token, "Content-Type": "application/json" };
  }

  async evaluate(req: EvaluateRequest): Promise<Decision> {
    return this.post<Decision>("/v1/action", req);
  }

  async health(): Promise<Record<string, unknown>> {
    return this.get("/health");
  }

  async stats(): Promise<Record<string, unknown>> {
    return this.get("/stats");
  }

  async listAgents(): Promise<unknown[]> {
    return this.get("/agents");
  }

  async listDecisions(params?: { agent_id?: string; verdict?: string; limit?: number }): Promise<unknown[]> {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.get(`/audit/query${qs ? "?" + qs : ""}`);
  }

  async applyPolicy(packName: string, objective?: string): Promise<Record<string, unknown>> {
    return this.post(`/policy-packs/${packName}/apply`, objective ? { objective } : {});
  }

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this.headers });
    if (!res.ok) throw new Error(`EDON ${res.status}: ${await res.text()}`);
    return res.json();
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, { method: "POST", headers: this.headers, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(`EDON ${res.status}: ${await res.text()}`);
    return res.json();
  }
}
