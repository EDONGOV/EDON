/**
 * EDON Gateway API client for the consumer dashboard.
 * Configure VITE_EDON_GATEWAY_URL in .env.local
 */

const BASE_URL = (import.meta.env.VITE_EDON_GATEWAY_URL || "https://edon-gateway.fly.dev").replace(/\/$/, "");

function getToken(): string {
  return (
    localStorage.getItem("edon_token") ||
    localStorage.getItem("edon_session_token") ||
    localStorage.getItem("edon_api_key") ||
    ""
  ).trim();
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  if (!token) {
    throw new Error("Authentication required. Set your token in Settings.");
  }
  return fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-EDON-TOKEN": token,
      ...options.headers,
    },
  });
}

export interface Decision {
  id: string;
  decision_id: string;
  agent_id: string;
  verdict: string;
  explanation: string;
  reason_code: string | null;
  created_at: string;
  action_type?: string;
}

export interface HealthStatus {
  status: string;
  version: string;
  uptime_seconds: number;
  components: Record<string, { status: string; latency_ms?: number }>;
}

export interface PlanInfo {
  name: string;
  slug: string;
  price_usd: number | null;
  decisions_per_month: number | null;
  max_agents: number | null;
  audit_retention_days: number | null;
  compliance_suite: boolean;
  contact_us?: boolean;
}

export const edonApi = {
  setApiKey(key: string) {
    localStorage.setItem("edon_api_key", key);
    localStorage.setItem("edon_token", key);
    localStorage.setItem("edon_session_token", key);
  },

  getApiKey(): string {
    return getToken();
  },

  clearApiKey() {
    localStorage.removeItem("edon_api_key");
    localStorage.removeItem("edon_token");
    localStorage.removeItem("edon_session_token");
  },

  async health(): Promise<HealthStatus> {
    const res = await apiFetch("/health");
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
  },

  async getDecisions(limit = 50, agentId?: string): Promise<Decision[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (agentId) params.set("agent_id", agentId);
    const res = await apiFetch(`/decisions/query?${params}`);
    if (!res.ok) throw new Error(`Failed to fetch decisions: ${res.status}`);
    const data = await res.json();
    return data.decisions || [];
  },

  async getAuditEvents(limit = 50, agentId?: string): Promise<Decision[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (agentId) params.set("agent_id", agentId);
    const res = await apiFetch(`/audit/query?${params}`);
    if (!res.ok) {
      if (res.status === 403) return []; // agent role lacks 'audit' permission
      throw new Error(`Failed to fetch audit events: ${res.status}`);
    }
    const data = await res.json();
    return data.events || [];
  },

  async getPlans(): Promise<{ plans: PlanInfo[] }> {
    const res = await apiFetch("/billing/plans");
    if (!res.ok) throw new Error(`Failed to fetch plans: ${res.status}`);
    return res.json();
  },

  async checkout(plan: string): Promise<{ checkout_url: string | null; message?: string }> {
    const res = await apiFetch("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan }),
    });
    if (!res.ok) throw new Error(`Checkout failed: ${res.status}`);
    return res.json();
  },

  async getPolicyRules(): Promise<unknown[]> {
    const res = await apiFetch("/policy/rules");
    if (!res.ok) return [];
    const data = await res.json();
    return data.rules || [];
  },

  async verifyChain(): Promise<{ valid: boolean; total_events: number; message?: string }> {
    const res = await apiFetch("/audit/verify-chain");
    if (!res.ok) throw new Error(`Chain verify failed: ${res.status}`);
    return res.json();
  },
};
