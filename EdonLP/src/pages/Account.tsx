import Navigation from "@/components/Navigation";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useUser, useAuth } from "@clerk/clerk-react";
import { Copy, Check, Key, Trash2 } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { fetchWithTimeout } from "@/lib/fetcher";
import { getGatewayUrl, getGatewayAuthHeaders, getGatewayBase, getDisplayGatewayUrl } from "@/lib/gatewayClient";

type ApiKey = {
  id?: string | number;
  name?: string;
  is_active?: boolean;
  status?: string;
  key_preview?: string;
  created_at?: string;
  last_used?: string;
};

type IntegrationsInfo = {
  // Legacy fields (may still be returned by some backend versions)
  endpoint?: string;
  instructions?: string;
  clawdbot_configured?: boolean;
  // Current backend shape
  clawdbot?: {
    connected?: boolean;
    base_url?: string;
    active_policy_pack?: string | null;
  };
  telegram?: { connected?: boolean };
  slack?: { connected?: boolean };
  discord?: { connected?: boolean };
  alert_preferences?: {
    alert_on_blocked?: boolean;
    alert_on_policy_violation?: boolean;
    alert_on_drift?: boolean;
    alert_on_escalation?: boolean;
  };
};

type BillingUsage = {
  today?: number | null;
  decisions?: number | null;
  policies?: number | null;
  agents?: number | null;
};

type BillingLimits = {
  requests_per_day?: number | null;
};

type BillingDecision = {
  timestamp?: string;
  agent?: string;
  verdict?: string;
  policy?: string;
};

type BillingStatus = {
  plan?: string;
  status?: string;
  usage?: BillingUsage;
  limits?: BillingLimits;
  recent_decisions?: BillingDecision[];
};

type SystemStatus = {
  runtime?: string;
  gateway?: string;
  lastIncident?: string;
};

type TimeSeriesPoint = {
  timestamp?: string;
  label?: string;
  allowed?: number;
  blocked?: number;
  confirm?: number;
};

type BlockReason = {
  reason: string;
  count: number;
};

type DecisionRecord = {
  agent_id?: string;
  timestamp?: string;
  created_at?: string;
};

type AgentSummary = {
  agent: string;
  decisions: number;
  lastSeen?: string;
};

const Account = () => {
  const { user } = useUser();
  const { getToken, isLoaded } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [copied, setCopied] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState(true);
  const [newKeyName, setNewKeyName] = useState("");
  const [creatingKey, setCreatingKey] = useState(false);
  const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);
  const [keyToDelete, setKeyToDelete] = useState<{ id: string; name: string } | null>(null);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationsInfo | null>(null);
  const [isLoadingIntegrations, setIsLoadingIntegrations] = useState(true);
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null);
  const [isLoadingBilling, setIsLoadingBilling] = useState(true);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [isLoadingSystem, setIsLoadingSystem] = useState(true);
  const [timeRange, setTimeRange] = useState<"1d" | "7d" | "30d">("7d");
  const [usageSeries, setUsageSeries] = useState<TimeSeriesPoint[]>([]);
  const [blockReasons, setBlockReasons] = useState<BlockReason[]>([]);
  const [isLoadingUsage, setIsLoadingUsage] = useState(true);
  const [agentsSummary, setAgentsSummary] = useState<AgentSummary[]>([]);
  const [isLoadingAgents, setIsLoadingAgents] = useState(true);
  const authToastShownRef = useRef(false);
  const [paymentSuccess, setPaymentSuccess] = useState(false);

  const GATEWAY_BASE = getGatewayBase();
  const GATEWAY_DISPLAY = getDisplayGatewayUrl();

  // Detect Stripe post-payment redirect (?payment=success)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("payment") === "success") {
      setPaymentSuccess(true);
      toast.success("Payment successful! Your plan is being activated.");
      navigate("/account/billing", { replace: true });
      // Refresh billing status so the new plan reflects immediately
      const token = localStorage.getItem("edon_api_key") || localStorage.getItem("edon_session_token") || "";
      if (token) loadBillingStatus(token);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Run data load once when user is available. Do not depend on getToken (Clerk can give a new ref each render and would retrigger endlessly).
  const initRanRef = useRef<string | null>(null);
  /** Token used to load the current API keys list; use this for revoke so we don't send a different tenant's token (404). */
  const tokenUsedForApiKeysRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isLoaded) return;
    if (!user) {
      navigate("/");
      return;
    }
    const userId = user.id;
    if (initRanRef.current === userId) return;
    initRanRef.current = userId;

    let isMounted = true;
    const init = async () => {
      try {
        // If a permanent EDON API key is already stored, try it first —
        // but if the gateway rejects it (stale/revoked), clear it and fall
        // through to Clerk JWT so the user isn't stuck with a broken key.
        const storedApiKey = localStorage.getItem("edon_api_key");
        if (storedApiKey) {
          if (!isMounted) return;
          const keyOk = await loadApiKeys(storedApiKey);
          if (keyOk) {
            await Promise.all([
              loadIntegrations(storedApiKey),
              loadBillingStatus(storedApiKey),
              loadUsage(storedApiKey),
              loadAgents(storedApiKey),
              loadSystemStatus(),
            ]);
            // Sync Clerk email to gateway so console shows correct email
            getToken().then((t) => {
              if (t) {
                fetchWithTimeout(getGatewayUrl("/auth/sync"), {
                  method: "POST",
                  headers: { ...getGatewayAuthHeaders(t) },
                  timeoutMs: 5000,
                }).catch(() => {});
              }
            });
            return;
          }
          // Stored key was rejected — remove it and re-auth via Clerk JWT
          localStorage.removeItem("edon_api_key");
        }

        // No stored API key — get a fresh Clerk JWT to call the gateway.
        // Right after sign-in redirect Clerk may not be ready yet; retry up to 5 times.
        let clerkToken = await getToken();
        let attempts = 0;
        while (!clerkToken && attempts < 5 && isMounted) {
          await new Promise((r) => setTimeout(r, 300));
          clerkToken = await getToken();
          attempts++;
        }
        if (!isMounted) return;
        if (clerkToken) {
          localStorage.setItem("edon_session_token", clerkToken);
          // Sync email to gateway so console shows correct email (fixes unknown@edoncore.com)
          fetchWithTimeout(getGatewayUrl("/auth/sync"), {
            method: "POST",
            headers: { ...getGatewayAuthHeaders(clerkToken) },
            timeoutMs: 5000,
          }).catch(() => {});
        } else {
          const stored = localStorage.getItem("edon_session_token");
          if (stored && stored.startsWith("eyJ")) {
            localStorage.removeItem("edon_session_token");
          }
        }
        // Don't fire requests without a token — avoids 401 and "Authentication required" toast
        if (!clerkToken) {
          setIsLoadingKeys(false);
          setIsLoadingIntegrations(false);
          setIsLoadingBilling(false);
          setIsLoadingUsage(false);
          setIsLoadingAgents(false);
          navigate("/login");
          return;
        }
        await Promise.all([
          loadApiKeys(clerkToken),
          loadIntegrations(clerkToken),
          loadBillingStatus(clerkToken),
          loadUsage(clerkToken),
          loadAgents(clerkToken),
          loadSystemStatus(),
        ]);
      } catch (error) {
        if (import.meta.env.DEV) {
          console.error("Failed to sync Clerk token:", error);
        }
      }
    };

    init();
    return () => {
      isMounted = false;
    };
  }, [user, isLoaded, navigate, getToken]);

  const themeClasses = {
    page: "bg-white text-gray-900",
    card: "bg-white border-gray-200",
    cardAlt: "bg-gray-50 border-gray-200",
    border: "border-gray-200",
    text: "text-gray-900",
    textMuted: "text-gray-600",
    navActive: "bg-gray-100 text-gray-900",
    navInactive: "text-gray-500 hover:text-gray-900 hover:bg-gray-100",
  };

  const resolveAuthToken = () => {
    // Prefer the permanent EDON API key (edon-xxx, no expiry) over the short-lived Clerk JWT.
    const edonApiKey = localStorage.getItem("edon_api_key");
    if (edonApiKey) return edonApiKey;

    const sessionToken = localStorage.getItem("edon_session_token");

    // If the session token is a Clerk JWT (eyJ...), check whether it has expired.
    // Clerk JWTs have a 60-second TTL — don't use stale ones.
    if (sessionToken && sessionToken.startsWith("eyJ") && sessionToken.includes(".")) {
      try {
        const payload = JSON.parse(atob(sessionToken.split(".")[1]));
        if (payload.exp && payload.exp * 1000 < Date.now()) {
          localStorage.removeItem("edon_session_token");
          return "";
        }
      } catch {
        // Ignore parse errors — treat as potentially valid
      }
      return sessionToken;
    }

    const metadataToken =
      (typeof user?.publicMetadata?.edon_api_key === "string" && user.publicMetadata.edon_api_key) ||
      (typeof user?.publicMetadata?.api_key === "string" && user.publicMetadata.api_key) ||
      "";

    return sessionToken || metadataToken;
  };

  const handleOpenConsole = async () => {
    const consoleTarget =
      import.meta.env.VITE_CONSOLE_URL ||
      import.meta.env.VITE_AGENT_UI_URL ||
      (import.meta.env.DEV ? "http://localhost:8080" : "https://console.edoncore.com");
    try {
      // Prefer permanent EDON API key (no expiry) over short-lived Clerk JWT
      const edonKey = localStorage.getItem("edon_api_key");
      const token = edonKey || (await getToken()) || resolveAuthToken();
      const email = user?.emailAddresses?.[0]?.emailAddress || "";
      const targetUrl = new URL(consoleTarget);
      targetUrl.searchParams.set("base", GATEWAY_DISPLAY);
      if (token) {
        // Pass token (and email) in URL fragment — never sent to servers or in Referer headers
        const hashQuery = new URLSearchParams();
        hashQuery.set("token", token);
        if (email) hashQuery.set("email", email);
        targetUrl.hash = hashQuery.toString();
      }
      window.open(targetUrl.toString(), "_blank", "noopener,noreferrer");
    } catch {
      window.open(consoleTarget, "_blank", "noopener,noreferrer");
    }
  };

  const isAbortError = (error: unknown) =>
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" && error !== null && "name" in error && (error as { name: string }).name === "AbortError");

  const resolveDays = () => (timeRange === "1d" ? 1 : timeRange === "7d" ? 7 : 30);

  const loadIntegrations = async (tokenOverride?: string | null) => {
    try {
      const token = tokenOverride || resolveAuthToken();
      if (!token) {
        setIsLoadingIntegrations(false);
        return;
      }

      const response = await fetchWithTimeout(getGatewayUrl("/integrations/account/integrations"), {
        headers: {
          ...getGatewayAuthHeaders(token),
        },
        timeoutMs: 8000,
        retries: 2,
      });

      if (response.ok) {
        const data = await response.json();
        setIntegrations(data);
      } else if (response.status === 401) {
        if (!authToastShownRef.current) {
          authToastShownRef.current = true;
          toast.error("Authentication required");
        }
      }
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (!import.meta.env.DEV) {
        console.error("Failed to load integrations:", error);
        toast.error("Failed to load integrations");
      }
    } finally {
      setIsLoadingIntegrations(false);
    }
  };

  const loadApiKeys = async (tokenOverride?: string | null): Promise<boolean> => {
    try {
      const token = tokenOverride || resolveAuthToken();
      if (!token) {
        setIsLoadingKeys(false);
        return false;
      }

      const response = await fetchWithTimeout(getGatewayUrl("/billing/api-keys"), {
        headers: {
          ...getGatewayAuthHeaders(token),
        },
        timeoutMs: 8000,
        retries: 2,
      });

      if (response.ok) {
        const data = await response.json();
        setApiKeys(data.keys || []);
        tokenUsedForApiKeysRef.current = token;
        return true;
      } else if (response.status === 401) {
        tokenUsedForApiKeysRef.current = null;
        if (!authToastShownRef.current) {
          authToastShownRef.current = true;
          toast.error("Authentication required");
        }
        return false;
      }
      return false;
    } catch (error) {
      if (isAbortError(error)) {
        return false;
      }
      if (!import.meta.env.DEV) {
        console.error("Failed to load API keys:", error);
        toast.error("Failed to load API keys");
      }
      return false;
    } finally {
      setIsLoadingKeys(false);
    }
  };

  const createApiKey = async () => {
    if (!newKeyName.trim()) {
      toast.error("Enter name for API");
      return;
    }
    const name = newKeyName.trim();
    // Prefer stored permanent key; fall back to fresh Clerk JWT if the stored JWT expired
    let token = resolveAuthToken();
    if (!token) {
      try {
        token = (await getToken({ skipCache: true })) || "";
        let attempts = 0;
        while (!token && attempts < 5) {
          await new Promise((r) => setTimeout(r, 300));
          token = (await getToken({ skipCache: true })) || "";
          attempts++;
        }
      } catch {
        token = "";
      }
    }
    if (!token) {
      toast.error("Authentication required");
      return;
    }
    setCreatingKey(true);
    try {
      const response = await fetchWithTimeout(getGatewayUrl("/billing/api-keys"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getGatewayAuthHeaders(token),
        },
        body: JSON.stringify({ name }),
        timeoutMs: 12000,
        retries: 1,
      });
      if (!response.ok) {
        const body = await response.text().catch(() => "");
        let message = body || `Error ${response.status}`;
        try {
          const parsed = JSON.parse(body);
          const detail = parsed?.detail;
          if (typeof detail === "string" && (detail.toLowerCase().includes("internal server error") || response.status === 400)) {
            message = "Enter name for API";
          } else if (typeof detail === "string") {
            message = detail;
          }
        } catch {
          if (response.status === 400 || body.includes("Internal server error")) message = "Enter name for API";
        }
        throw new Error(message);
      }
      const data = await response.json();
      const fullKey: string = data.api_key || data.key || "";
      if (!fullKey) throw new Error("No key returned from server");
      setNewlyCreatedKey(fullKey);
      setNewKeyName("");
      // Store for use as auth token (and track ID so delete can detect self-deletion)
      localStorage.setItem("edon_api_key", fullKey);
      if (data.api_key_id) localStorage.setItem("edon_api_key_id", String(data.api_key_id));
      // Refresh the key list using the new permanent key so subsequent deletes use it
      await loadApiKeys(fullKey);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create key";
      toast.error(msg.startsWith("{") ? "Enter name for API" : msg);
    } finally {
      setCreatingKey(false);
    }
  };

  const revokeApiKey = async (apiKeyId: string) => {
    // Prefer resolveAuthToken (validates JWT expiry, picks up new EDON key) over a potentially-stale ref
    let token = resolveAuthToken() || tokenUsedForApiKeysRef.current || "";
    if (!token) {
      try {
        token = (await getToken({ skipCache: true })) || "";
        let attempts = 0;
        while (!token && attempts < 5) {
          await new Promise((r) => setTimeout(r, 300));
          token = (await getToken({ skipCache: true })) || "";
          attempts++;
        }
      } catch {
        token = "";
      }
    }
    if (!token) {
      toast.error("Authentication required");
      return;
    }
    setRevokingKeyId(apiKeyId);
    try {
      const response = await fetchWithTimeout(getGatewayUrl(`/billing/api-keys/${encodeURIComponent(apiKeyId)}`), {
        method: "DELETE",
        headers: getGatewayAuthHeaders(token),
        timeoutMs: 8000,
      });
      // 404 = key not found (already deleted or wrong tenant) — remove from UI and treat as done
      if (response.status === 404) {
        setApiKeys((prev) => prev.filter((k) => String(k.id) !== String(apiKeyId)));
        setRevokingKeyId(null);
        return;
      }
      if (!response.ok) {
        const body = await response.text().catch(() => "");
        let message = body || `Error ${response.status}`;
        try {
          const parsed = JSON.parse(body);
          if (typeof parsed?.detail === "string") message = parsed.detail;
        } catch {
          /* use message as-is */
        }
        throw new Error(message);
      }
      toast.success("API key deleted");
      // If we just deleted the key we're authenticating with, clear it from
      // localStorage and reload using a fresh Clerk token — otherwise the next
      // loadApiKeys call returns 401 and fires a confusing auth-error toast.
      const storedKeyId = localStorage.getItem("edon_api_key_id");
      if (storedKeyId && String(storedKeyId) === String(apiKeyId)) {
        localStorage.removeItem("edon_api_key");
        localStorage.removeItem("edon_api_key_id");
        const freshToken = await getToken().catch(() => null);
        await loadApiKeys(freshToken);
      } else {
        await loadApiKeys(token);
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to delete key");
      await loadApiKeys(token);
    } finally {
      setRevokingKeyId(null);
    }
  };

  const loadBillingStatus = async (tokenOverride?: string | null) => {
    try {
      const token = tokenOverride || resolveAuthToken();
      if (!token) {
        setIsLoadingBilling(false);
        return;
      }

      const response = await fetchWithTimeout(getGatewayUrl("/billing/status"), {
        headers: {
          ...getGatewayAuthHeaders(token),
        },
        timeoutMs: 8000,
        retries: 2,
      });

      if (response.ok) {
        const data = await response.json();
        setBillingStatus(data);
      } else if (response.status === 401) {
        if (!authToastShownRef.current) {
          authToastShownRef.current = true;
          toast.error("Authentication required");
        }
      }
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (!import.meta.env.DEV) {
        console.error("Failed to load billing status:", error);
        toast.error("Failed to load billing status");
      }
    } finally {
      setIsLoadingBilling(false);
    }
  };

  const loadUsage = async (tokenOverride?: string | null) => {
    try {
      const token = tokenOverride || resolveAuthToken();
      if (!token) {
        setIsLoadingUsage(false);
        return;
      }
      const days = resolveDays();
      const [seriesRes, reasonsRes] = await Promise.all([
        fetchWithTimeout(getGatewayUrl(`/timeseries?days=${days}`), {
          headers: getGatewayAuthHeaders(token),
          timeoutMs: 8000,
          retries: 1,
        }),
        fetchWithTimeout(getGatewayUrl(`/block-reasons?days=${days}`), {
          headers: getGatewayAuthHeaders(token),
          timeoutMs: 8000,
          retries: 1,
        }),
      ]);

      if (seriesRes.ok) {
        const data = await seriesRes.json();
        setUsageSeries(Array.isArray(data) ? data : []);
      }
      if (reasonsRes.ok) {
        const data = await reasonsRes.json();
        setBlockReasons(Array.isArray(data) ? data : []);
      }
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (!import.meta.env.DEV) {
        console.error("Failed to load usage data:", error);
        toast.error("Failed to load usage data");
      }
    } finally {
      setIsLoadingUsage(false);
    }
  };

  const loadAgents = async (tokenOverride?: string | null) => {
    try {
      const token = tokenOverride || resolveAuthToken();
      if (!token) {
        setIsLoadingAgents(false);
        return;
      }
      const response = await fetchWithTimeout(getGatewayUrl("/decisions/query?limit=200"), {
        headers: getGatewayAuthHeaders(token),
        timeoutMs: 8000,
        retries: 1,
      });
      if (!response.ok) {
        setAgentsSummary([]);
        return;
      }
      const data = await response.json();
      const decisions: DecisionRecord[] = Array.isArray(data?.decisions) ? data.decisions : [];
      const byAgent = new Map<string, AgentSummary>();
      decisions.forEach((decision) => {
        const agentId = decision.agent_id || "unknown";
        const lastSeen = decision.timestamp || decision.created_at || "";
        const entry = byAgent.get(agentId);
        if (!entry) {
          byAgent.set(agentId, { agent: agentId, decisions: 1, lastSeen });
        } else {
          entry.decisions += 1;
          if (lastSeen && (!entry.lastSeen || new Date(lastSeen) > new Date(entry.lastSeen))) {
            entry.lastSeen = lastSeen;
          }
        }
      });
      const summary = Array.from(byAgent.values()).sort((a, b) => b.decisions - a.decisions).slice(0, 10);
      setAgentsSummary(summary);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (!import.meta.env.DEV) {
        console.error("Failed to load agent activity:", error);
        toast.error("Failed to load agent activity");
      }
    } finally {
      setIsLoadingAgents(false);
    }
  };

  useEffect(() => {
    if (!isLoaded || !user) return;
    let isMounted = true;
    (async () => {
      try {
        // Prefer permanent EDON API key; fall back to fresh Clerk JWT.
        // getToken intentionally not in deps — avoids infinite render loops.
        const token = localStorage.getItem("edon_api_key") || await getToken(); // eslint-disable-line react-hooks/exhaustive-deps
        if (!isMounted || !token) return;
        setIsLoadingUsage(true);
        loadUsage(token);
      } catch {
        // Ignore token errors on range change
      }
    })();
    return () => { isMounted = false; };
  }, [timeRange, user, isLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSystemStatus = async () => {
    setIsLoadingSystem(true);
    try {
      const response = await fetchWithTimeout(getGatewayUrl("/health"), {
        timeoutMs: 6000,
        retries: 1,
      });
      if (response.ok) {
        const data = await response.json();
        setSystemStatus({
          runtime: data.status || "ok",
          gateway: data.gateway_status || "online",
          lastIncident: data.last_incident || "None reported",
        });
      } else {
        setSystemStatus(null);
      }
    } catch (error) {
      setSystemStatus(null);
    } finally {
      setIsLoadingSystem(false);
    }
  };

  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopied(type);
    toast.success(`${type} copied to clipboard`);
    setTimeout(() => setCopied(null), 2000);
  };

  // Get tenant_id from Clerk user metadata or your backend
  const tenantId = user?.publicMetadata?.tenant_id as string || "";
  const endpoint = tenantId 
    ? `${GATEWAY_DISPLAY}/${tenantId}/clawdbot/invoke`
    : "";

  const planRaw = (billingStatus?.plan || (user?.publicMetadata?.plan as string) || "pending").toString().toLowerCase();
  const PLAN_LABELS: Record<string, string> = {
    free: "Free",
    starter: "Starter — $49/mo",
    growth: "Growth — $199/mo",
    business: "Business — $499/mo",
    enterprise: "Enterprise",
    pro: "Pro",
    "pro+": "Pro+",
    ultra: "Ultra",
    pending: "Pending activation",
  };
  const planLabel = PLAN_LABELS[planRaw] ?? (planRaw.charAt(0).toUpperCase() + planRaw.slice(1));
  const statusRaw = (billingStatus?.status || "inactive").toString().toLowerCase();
  // Free plan is stored as status="trial" in the DB — display it as "active" so users aren't confused
  const statusLabel = (statusRaw === "trial" && planRaw === "free") ? "active" : statusRaw;
  const statusNormalized = statusRaw;
  const isPaid = billingStatus?.status
    ? statusNormalized === "active" || statusNormalized === "trialing"
    : false;
  const isFreeUser = planRaw === "free" || planRaw === "pending";
  // Free users get console access; paid users always have it
  const hasConsoleAccess = isPaid || isFreeUser;
  const agentUiUrl = import.meta.env.VITE_CONSOLE_URL
    || import.meta.env.VITE_AGENT_UI_URL
    || (import.meta.env.DEV ? "http://localhost:8080" : "https://console.edoncore.com");
  const usageToday = billingStatus?.usage?.today ?? null;
  const dailyLimit = billingStatus?.limits?.requests_per_day ?? null;
  // Paused when a free user has hit or exceeded their daily decision limit
  const isLimitReached = isFreeUser && dailyLimit !== null && (usageToday ?? 0) >= dailyLimit;
  const decisionsEvaluated = billingStatus?.usage?.decisions ?? null;
  const policiesTriggered = billingStatus?.usage?.policies ?? null;
  const agentsGoverned = billingStatus?.usage?.agents ?? null;
  const recentDecisions = billingStatus?.recent_decisions ?? [];

  if (!user) {
    return null;
  }

  // Determine which tab to show based on route
  const path = location.pathname;
  const showQuickStart = path.includes("/quick-start") || path === "/account" || path.endsWith("/account/");
  const showBilling = path.includes("/billing");
  const showTokens = path.includes("/tokens");
  const showIntegrations = path.includes("/integrations");
  const showAgents = path.includes("/agents");
  const showUsage = path.includes("/usage");
  const showConsole = path.includes("/console");
  const showOverview = path.includes("/overview");

  return (
    <div className={`min-h-screen font-sans ${themeClasses.page}`}>
      <SEOHead
        title="Account | EDON"
        description="Manage your EDON account settings, billing, and API tokens"
        canonical="https://edoncore.com/account"
      />
      <Navigation />

      <section className="py-24 px-6 pt-28">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-[240px_1fr] gap-8">
          <aside className="space-y-6">
            <div className={`rounded-xl border p-4 ${themeClasses.card}`}>
              <p className={`text-xs mb-2 ${themeClasses.textMuted}`}>Signed in</p>
              <p className={`text-[13px] ${themeClasses.text}`}>{user.emailAddresses[0]?.emailAddress || "N/A"}</p>
              <div className={`mt-3 flex items-center gap-2 text-xs ${themeClasses.textMuted}`}>
                <span className="px-2 py-1 rounded-full bg-gray-100 text-gray-700">
                  {planLabel}
                </span>
                <span className="uppercase">{statusLabel}</span>
              </div>
            </div>

            <nav className="space-y-1 text-[13px]">
              <Link
                to="/account/quick-start"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showQuickStart ? themeClasses.navActive : themeClasses.navInactive
                }`}
              >
                Quick start
              </Link>
              <Link
                to="/account/overview"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showOverview ? themeClasses.navActive : themeClasses.navInactive
                }`}
              >
                Overview
              </Link>
              <Link
                to="/account/integrations"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showIntegrations
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                Integrations
              </Link>
              <Link
                to="/account/agents"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showAgents
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                Agents
              </Link>
              <Link
                to="/account/usage"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showUsage
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                Usage
              </Link>
              <Link
                to="/account/billing"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showBilling
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                Billing
              </Link>
              <Link
                to="/account/tokens"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showTokens
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                API Tokens
              </Link>
              <Link
                to="/account/console"
                className={`flex items-center rounded-lg px-3 py-2 ${
                  showConsole
                    ? themeClasses.navActive
                    : themeClasses.navInactive
                }`}
              >
                Console
              </Link>
              <div className="pt-2 mt-2 border-t border-gray-100">
                <a
                  href="https://platform.edoncore.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex items-center justify-between rounded-lg px-3 py-2 ${themeClasses.navInactive}`}
                >
                  <span>Developer Platform</span>
                  <svg className="w-3 h-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                </a>
              </div>
            </nav>
          </aside>

          <main className="space-y-8">
            {/* Global limit-reached banner — shown on every tab for free users who are paused */}
            {isLimitReached && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <p className="text-[13px] font-semibold text-amber-900">Your free plan is paused</p>
                  <p className="text-[12px] text-amber-800 mt-0.5">
                    You've used all {dailyLimit?.toLocaleString()} decisions for this period. Upgrade to restore access and increase your limits.
                  </p>
                </div>
                <Link to="/pricing" className="shrink-0">
                  <Button className="rounded-full text-[12px] font-medium px-5 py-2 bg-black text-white hover:bg-neutral-800 whitespace-nowrap">
                    View plans
                  </Button>
                </Link>
              </div>
            )}

            {showQuickStart && (
              <div className="space-y-6">
                <div className={`rounded-xl border p-6 ${themeClasses.card}`}>
                  <h2 className={`text-[18px] font-semibold mb-1 ${themeClasses.text}`}>Get started in minutes</h2>
                  <p className={`text-[13px] mb-6 ${themeClasses.textMuted}`}>
                    Route your agent’s tool calls through EDON to get real-time allow/block decisions and a full audit trail — no changes to your agent logic required.
                  </p>
                  <ol className="space-y-6">
                    <li className="flex gap-4">
                      <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-900 text-white text-[13px] font-semibold flex items-center justify-center">1</span>
                      <div>
                        <p className={`font-medium text-[14px] ${themeClasses.text}`}>Get your API token</p>
                        <p className={`text-[13px] mt-1 ${themeClasses.textMuted}`}>
                          Your API token authenticates every request to EDON. Get it from the API Tokens tab (copy when you create a key — it's only shown once). Keep it secure — you’ll add it as the <code className="bg-gray-100 px-1 rounded text-xs">X-EDON-TOKEN</code> header.
                        </p>
                        <Link to="/account/tokens" className="inline-block mt-2">
                          <Button variant="outline" size="sm" className="rounded-full text-[12px] font-medium bg-white text-black border-gray-300 hover:bg-gray-50 hover:text-black">
                            View API Tokens
                          </Button>
                        </Link>
                      </div>
                    </li>
                    <li className="flex gap-4">
                      <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-900 text-white text-[13px] font-semibold flex items-center justify-center">2</span>
                      <div>
                        <p className={`font-medium text-[14px] ${themeClasses.text}`}>Register your agent endpoint</p>
                        <p className={`text-[13px] mt-1 ${themeClasses.textMuted}`}>
                          Tell EDON the base URL of your agent or backend so it knows where to forward approved requests. This only needs to be set once.
                        </p>
                        <Link to="/account/integrations" className="inline-block mt-2">
                          <Button variant="outline" size="sm" className="rounded-full text-[12px] font-medium bg-white text-black border-gray-300 hover:bg-gray-50 hover:text-black">
                            Set up Integrations
                          </Button>
                        </Link>
                      </div>
                    </li>
                    <li className="flex gap-4">
                      <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-900 text-white text-[13px] font-semibold flex items-center justify-center">3</span>
                      <div>
                        <p className={`font-medium text-[14px] ${themeClasses.text}`}>Point your agent at EDON</p>
                        <p className={`text-[13px] mt-1 ${themeClasses.textMuted}`}>
                          Replace your agent’s tool-invoke URL with your EDON endpoint below, and add <code className="bg-gray-100 px-1 rounded text-xs">X-EDON-TOKEN: &lt;your-token&gt;</code> to the request headers. The request body stays the same.
                        </p>
                        {integrations?.endpoint && (
                          <div className="flex items-center gap-2 mt-2">
                            <code className="flex-1 border px-3 py-2 rounded text-[12px] font-mono break-all bg-gray-50 border-gray-200">
                              {integrations.endpoint}/agent/invoke
                            </code>
                            <Button variant="outline" size="icon" className="bg-white border-gray-300 text-black hover:bg-gray-50" onClick={() => copyToClipboard(`${integrations?.endpoint || ""}/agent/invoke`, "Invoke URL")}>
                              {copied === "Invoke URL" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                            </Button>
                          </div>
                        )}
                        {!integrations?.endpoint && (
                          <p className={`text-[12px] mt-2 ${themeClasses.textMuted}`}>
                            Complete step 2 to see your endpoint here.
                          </p>
                        )}
                      </div>
                    </li>
                    <li className="flex gap-4">
                      <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-900 text-white text-[13px] font-semibold flex items-center justify-center">4</span>
                      <div>
                        <p className={`font-medium text-[14px] ${themeClasses.text}`}>Verify in the console</p>
                        <p className={`text-[13px] mt-1 ${themeClasses.textMuted}`}>
                          Run a test call from your agent, then open the governance console to confirm the decision was logged. From there you can adjust your policy, review the audit trail, and monitor live activity.
                        </p>
                        {isLimitReached ? (
                          <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 flex items-center justify-between gap-3">
                            <p className="text-[12px] text-amber-800">Decision limit reached — console paused.</p>
                            <Link to="/pricing">
                              <Button size="sm" className="rounded-full text-[11px] font-medium px-3 py-1 bg-white text-black border border-gray-300 hover:bg-gray-50">
                                Upgrade
                              </Button>
                            </Link>
                          </div>
                        ) : hasConsoleAccess ? (
                          <Link to="/account/console" className="inline-block mt-2">
                            <Button variant="outline" size="sm" className="rounded-full text-[12px] font-medium bg-white text-black border-gray-300 hover:bg-gray-50 hover:text-black">
                              Open Console
                            </Button>
                          </Link>
                        ) : null}
                      </div>
                    </li>
                  </ol>
                  <div className={`mt-6 rounded-xl border p-4 ${themeClasses.cardAlt}`}>
                    <p className={`text-xs font-semibold uppercase tracking-wide mb-2 ${themeClasses.textMuted}`}>
                      TypeScript / JavaScript — call EDON from your agent
                    </p>
                    <pre className="text-[11px] md:text-[12px] font-mono overflow-x-auto p-4 rounded-lg bg-gray-900 text-gray-100 border border-gray-700">
{`const EDON_GATEWAY = "${integrations?.endpoint || GATEWAY_DISPLAY}";
const response = await fetch(\`\${EDON_GATEWAY}/v1/action\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-EDON-TOKEN": process.env.EDON_API_TOKEN, // or your token
  },
  body: JSON.stringify({
    agent_id: "my-agent",
    action_type: "tool_call",
    action_payload: {
      tool: "send_email",
      op: "draft",
      params: { subject: "Hello", body: "..." },
    },
  }),
});
const result = await response.json();
// result.verdict === "ALLOW" | "BLOCK" | "CONFIRM"`}
                    </pre>
                    <p className={`text-[11px] mt-2 ${themeClasses.textMuted}`}>
                      Use your real gateway URL and API token. Same pattern for <code className="bg-gray-200 px-1 rounded">/agent/invoke</code> when proxying tool calls.
                    </p>
                  </div>
                  <div className="mt-6 pt-4 border-t border-gray-200">
                    <p className={`text-[12px] ${themeClasses.textMuted}`}>
                      Need more detail?{" "}
                      <span className="text-gray-900 underline">Read the integration guide</span>
                      {" "}or{" "}
                      <span className="text-gray-900 underline">contact support</span>.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {showOverview && (
              <>
                <section className="space-y-4">
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>Overview</h2>
                  <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                    <div className="grid md:grid-cols-2 gap-6">
                      <div className={`space-y-4 text-[13px] ${themeClasses.textMuted}`}>
                        <div>
                          <div className="text-xs uppercase tracking-wide mb-1">Current plan</div>
                          <div className={`text-[17px] font-semibold ${themeClasses.text}`}>{planLabel}</div>
                          <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium uppercase ${
                            isPaid
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-gray-100 text-gray-500 border border-gray-200"
                          }`}>
                            {statusLabel}
                          </span>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-wide mb-1">Account email</div>
                          <div className={`text-[13px] ${themeClasses.text}`}>{user.emailAddresses[0]?.emailAddress || "N/A"}</div>
                        </div>
                        <div>
                          <div className="text-xs uppercase tracking-wide mb-1">EDON endpoint</div>
                          <div className={`text-[12px] font-mono break-all ${themeClasses.textMuted}`}>
                            {integrations?.endpoint || endpoint || "—"}
                          </div>
                          {!integrations?.endpoint && !endpoint && (
                            <Link to="/account/integrations" className={`text-xs underline mt-0.5 inline-block ${themeClasses.textMuted}`}>
                              Set up Integrations to see your endpoint
                            </Link>
                          )}
                        </div>
                      </div>
                      <div className={`space-y-4 text-[13px] ${themeClasses.textMuted}`}>
                        <div>
                          <div className="text-xs uppercase tracking-wide mb-1">Requests today</div>
                          <div className={`text-[17px] font-semibold ${themeClasses.text}`}>
                            {isLoadingBilling ? "—" : (usageToday ?? 0).toLocaleString()}
                            {dailyLimit && (
                              <span className={`text-[13px] font-normal ml-1 ${themeClasses.textMuted}`}>
                                / {dailyLimit.toLocaleString()}
                              </span>
                            )}
                          </div>
                          {dailyLimit && !isLoadingBilling && (
                            <div className="mt-2 h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gray-900 rounded-full"
                                style={{ width: `${Math.min(100, ((usageToday ?? 0) / dailyLimit) * 100)}%` }}
                              />
                            </div>
                          )}
                        </div>
                        <div className="pt-1">
                          <Link to="/contact">
                            <Button
                              variant="outline"
                              className="rounded-full text-[13px] font-medium px-5 py-2 border-gray-300 text-black bg-white hover:bg-gray-50"
                            >
                              Contact
                            </Button>
                          </Link>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                <section className="space-y-4">
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>Usage — Current Period</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Decisions evaluated</div>
                      <div className={`text-[20px] font-semibold ${themeClasses.text}`}>
                        {isLoadingBilling ? "—" : (decisionsEvaluated ?? "—").toLocaleString?.() ?? "—"}
                      </div>
                    </div>
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Policies triggered</div>
                      <div className={`text-[20px] font-semibold ${themeClasses.text}`}>
                        {isLoadingBilling ? "—" : (policiesTriggered ?? "—").toLocaleString?.() ?? "—"}
                      </div>
                    </div>
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Agents governed</div>
                      <div className={`text-[20px] font-semibold ${themeClasses.text}`}>
                        {isLoadingBilling ? "—" : (agentsGoverned ?? "—").toLocaleString?.() ?? "—"}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="space-y-4">
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>Recent Decisions</h2>
                  <div className={`rounded-xl border overflow-hidden ${themeClasses.card}`}>
                    <table className="w-full text-[13px]">
                      <thead>
                        <tr className={`border-b ${themeClasses.border}`}>
                          {["Timestamp", "Agent", "Verdict", "Policy"].map((h) => (
                            <th key={h} className={`text-left px-4 py-3 text-xs uppercase tracking-wide font-medium ${themeClasses.textMuted}`}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {recentDecisions.length === 0 ? (
                          <tr>
                            <td colSpan={4} className={`px-4 py-4 text-[13px] ${themeClasses.textMuted}`}>
                              No decisions yet. Send a request through your EDON endpoint to see it here.
                            </td>
                          </tr>
                        ) : (
                          recentDecisions.map((decision: BillingDecision, index: number) => (
                            <tr key={index} className={`border-b ${themeClasses.border} last:border-0`}>
                              <td className={`px-4 py-3 ${themeClasses.textMuted}`}>
                                {decision.timestamp ? new Date(decision.timestamp).toLocaleString() : "—"}
                              </td>
                              <td className={`px-4 py-3 font-mono ${themeClasses.text}`}>{decision.agent || "—"}</td>
                              <td className={`px-4 py-3 font-medium ${
                                decision.verdict === "ALLOW" ? "text-emerald-700" :
                                decision.verdict === "BLOCK" ? "text-red-600" : themeClasses.text
                              }`}>
                                {decision.verdict || "—"}
                              </td>
                              <td className={`px-4 py-3 ${themeClasses.textMuted}`}>{decision.policy || "—"}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="space-y-4">
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>System Status</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Runtime</div>
                      <div className={`text-[15px] font-semibold capitalize ${
                        systemStatus?.runtime === "ok" || systemStatus?.runtime === "online"
                          ? "text-emerald-700" : themeClasses.text
                      }`}>
                        {isLoadingSystem ? "—" : systemStatus?.runtime || "Unknown"}
                      </div>
                    </div>
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Gateway</div>
                      <div className={`text-[15px] font-semibold capitalize ${
                        systemStatus?.gateway === "online" || systemStatus?.gateway === "ok"
                          ? "text-emerald-700" : themeClasses.text
                      }`}>
                        {isLoadingSystem ? "—" : systemStatus?.gateway || "Unknown"}
                      </div>
                    </div>
                    <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                      <div className={`text-xs mb-2 ${themeClasses.textMuted}`}>Last incident</div>
                      <div className={`text-[13px] ${themeClasses.text}`}>
                        {isLoadingSystem ? "—" : systemStatus?.lastIncident || "None reported"}
                      </div>
                    </div>
                  </div>
                </section>
              </>
            )}

          {/* Billing Tab */}
          {showBilling && (
            <div className="space-y-6">
              {paymentSuccess && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3">
                  <span className="text-emerald-600 text-lg leading-none">✓</span>
                  <div>
                    <p className="text-[13px] font-semibold text-emerald-800">Payment confirmed</p>
                    <p className="text-[12px] text-emerald-700 mt-0.5">
                      Your subscription is being activated. It may take a minute to reflect below — refresh if needed.
                    </p>
                  </div>
                </div>
              )}
              <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                <h2 className={`text-[16px] font-semibold mb-4 ${themeClasses.text}`}>Billing</h2>
                <div className={`grid md:grid-cols-2 gap-6 text-[13px] ${themeClasses.textMuted}`}>
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs uppercase tracking-wide mb-1">Current plan</div>
                      <div className={`text-[15px] font-semibold ${themeClasses.text}`}>{planLabel}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide mb-1">Status</div>
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium uppercase ${
                        isPaid
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-gray-100 text-gray-500 border border-gray-200"
                      }`}>
                        {statusLabel}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs uppercase tracking-wide mb-1">Usage today</div>
                      <div className={`text-[15px] font-semibold ${themeClasses.text}`}>
                        {isLoadingBilling ? "—" : (usageToday ?? 0).toLocaleString()}
                        {dailyLimit && (
                          <span className={`text-[13px] font-normal ml-1 ${themeClasses.textMuted}`}>
                            / {dailyLimit.toLocaleString()} requests
                          </span>
                        )}
                      </div>
                      {dailyLimit && !isLoadingBilling && (
                        <div className="mt-2 h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gray-900 rounded-full"
                            style={{ width: `${Math.min(100, ((usageToday ?? 0) / dailyLimit) * 100)}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide mb-1">Decisions this period</div>
                      <div className={themeClasses.text}>
                        {isLoadingBilling ? "—" : (decisionsEvaluated ?? "—").toLocaleString?.() ?? "—"}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mt-5 pt-4 border-t border-gray-100 flex flex-wrap items-center gap-3">
                  {!isPaid && (
                    <Link to="/pricing">
                      <Button
                        className="rounded-full text-[12px] font-medium px-3 py-1.5 bg-black text-white hover:bg-neutral-800"
                      >
                        Upgrade Plan
                      </Button>
                    </Link>
                  )}
                  <Link to="/contact">
                    <Button
                      variant="outline"
                      className="rounded-full text-[12px] font-medium px-3 py-1.5 border-gray-300 text-black bg-white hover:bg-gray-50"
                    >
                      Contact
                    </Button>
                  </Link>
                  <Link to="/account/tokens">
                    <Button
                      variant="outline"
                      className="rounded-full text-[12px] font-medium px-3 py-1.5 border-gray-300 text-black bg-white hover:bg-gray-50"
                    >
                      Manage API Tokens
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          )}

          {/* Tokens Tab */}
          {showTokens && (
            <div className="space-y-6">
              <div className={`rounded-xl border p-6 ${themeClasses.card}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Key className="h-4 w-4 text-gray-500" />
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>API Tokens</h2>
                </div>
                <p className={`text-[13px] mb-5 ${themeClasses.textMuted}`}>
                  Use your token to authenticate every request to EDON. Send it as the{" "}
                  <code className="bg-gray-100 px-1 rounded text-xs">X-EDON-TOKEN</code> header.
                </p>

                {/* One-time reveal banner */}
                {newlyCreatedKey && (
                  <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                    <p className="text-[13px] font-semibold text-emerald-800 mb-1">
                      Copy your token now — it won’t be shown again
                    </p>
                    <p className="text-[12px] text-emerald-700 mb-3">
                      Save this somewhere secure. Once you close this, only a masked preview will be shown.
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 border border-emerald-200 px-3 py-2 rounded text-[12px] font-mono break-all bg-white text-gray-900">
                        {newlyCreatedKey}
                      </code>
                      <Button
                        variant="outline"
                        size="icon"
                        className="shrink-0 bg-white border-emerald-300 text-black hover:bg-emerald-50"
                        onClick={() => copyToClipboard(newlyCreatedKey, "New API Key")}
                        title="Copy token"
                      >
                        {copied === "New API Key" ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                    <button
                      onClick={() => setNewlyCreatedKey(null)}
                      className="mt-3 text-[11px] text-emerald-700 underline hover:text-emerald-900"
                    >
                      I’ve saved it — dismiss
                    </button>
                  </div>
                )}

                {/* Existing keys */}
                {isLoadingKeys ? (
                  <p className={`text-[13px] ${themeClasses.textMuted}`}>Loading tokens...</p>
                ) : apiKeys.length > 0 ? (
                  <div className="space-y-4">
                    {apiKeys.map((key) => (
                      <div key={key.id} className={`border rounded-xl p-4 ${themeClasses.cardAlt}`}>
                        <div className="flex items-center justify-between mb-3">
                          <p className={`text-[13px] font-medium ${themeClasses.text}`}>{key.name || "Unnamed Key"}</p>
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                              key.is_active
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-gray-100 text-gray-500 border border-gray-200"
                            }`}>
                              {key.status?.toUpperCase() ?? "UNKNOWN"}
                            </span>
                            {key.id != null && (
                              <Button
                                variant="outline"
                                size="icon"
                                className="shrink-0 bg-white border-red-500 text-red-600 hover:bg-red-50 hover:border-red-600 hover:text-red-700"
                                title="Delete API key"
                                disabled={revokingKeyId === String(key.id)}
                                onClick={() => setKeyToDelete({ id: String(key.id), name: key.name || "Unnamed Key" })}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                        <div>
                          <label className={`block text-xs uppercase tracking-wide mb-1.5 ${themeClasses.textMuted}`}>
                            Token
                          </label>
                          <div className="flex items-center gap-2">
                            <code className="flex-1 border px-3 py-2 rounded text-[12px] font-mono break-all bg-white border-gray-200 text-gray-900">
                              {key.key_preview || "edon_••••••••••••"}
                            </code>
                            <Button
                              variant="outline"
                              size="icon"
                              className="bg-white border-gray-300 text-black hover:bg-gray-50"
                              onClick={() => {
                                toast.info(
                                  "The full token is only shown once at creation. Generate a new token below to get a copyable key."
                                );
                              }}
                              title="Full token not available — generate a new key to get one"
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                          </div>
                          <p className={`mt-1.5 text-[11px] ${themeClasses.textMuted}`}>
                            Full token only shown once at creation. Generate a new key if you need to copy a token.
                          </p>
                        </div>
                        <div className={`mt-3 text-xs space-y-0.5 ${themeClasses.textMuted}`}>
                          <p>Created: {key.created_at ? new Date(key.created_at).toLocaleString() : "—"}</p>
                          {key.last_used && (
                            <p>Last used: {new Date(key.last_used).toLocaleString()}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className={`text-[13px] ${themeClasses.textMuted}`}>
                    No API tokens yet. Generate one below.
                  </p>
                )}

                {/* Generate new key form */}
                <div className={`mt-6 pt-5 border-t ${themeClasses.border ?? "border-gray-200"}`}>
                  <p className={`text-[13px] font-medium mb-3 ${themeClasses.text}`}>Generate new token</p>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="Token name (e.g. Production)"
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[13px] bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900"
                      onKeyDown={(e) => { if (e.key === "Enter") createApiKey(); }}
                    />
                    <Button
                      onClick={createApiKey}
                      disabled={creatingKey}
                      className="rounded-full text-[12px] font-medium px-4 py-2 bg-black text-white hover:bg-neutral-800 whitespace-nowrap"
                    >
                      {creatingKey ? "Generating…" : "Generate"}
                    </Button>
                  </div>
                </div>

                <AlertDialog open={!!keyToDelete} onOpenChange={(open) => { if (!open) setKeyToDelete(null); }}>
                  <AlertDialogContent className="max-w-md">
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete API key?</AlertDialogTitle>
                      <AlertDialogDescription>
                        {keyToDelete ? (
                          <>Delete &quot;{keyToDelete.name}&quot;? This key will stop working immediately and cannot be undone.</>
                        ) : (
                          "This key will stop working immediately and cannot be undone."
                        )}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
                        onClick={() => {
                          if (!keyToDelete) return;
                          const id = keyToDelete.id;
                          if (!apiKeys.some((k) => String(k.id) === id)) {
                            setKeyToDelete(null);
                            return;
                          }
                          setKeyToDelete(null);
                          setApiKeys((prev) => prev.filter((k) => String(k.id) !== id));
                          revokeApiKey(id);
                        }}
                      >
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>
          )}

          {/* Integrations Tab */}
          {showIntegrations && (
            <div className="space-y-6">
              <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                <h2 className={`text-[16px] font-semibold mb-4 ${themeClasses.text}`}>Integrations</h2>
                {isLoadingIntegrations ? (
                  <p className={`text-[13px] ${themeClasses.textMuted}`}>Loading integration details...</p>
                ) : (() => {
                  const displayEndpoint = integrations?.endpoint || integrations?.clawdbot?.base_url || endpoint || GATEWAY_DISPLAY;
                  return (
                    <div className="space-y-6">
                      <div>
                        <label className={`block text-xs uppercase tracking-wide mb-2 ${themeClasses.textMuted}`}>
                          EDON Endpoint
                        </label>
                        <div className="flex items-center gap-2">
                          <code className="flex-1 border px-4 py-2 rounded text-[12px] font-mono break-all bg-white border-gray-200 text-gray-900">
                            {displayEndpoint}
                          </code>
                          <Button
                            variant="outline"
                            size="icon"
                            className="bg-white border-gray-300 text-black hover:bg-gray-50"
                            onClick={() => copyToClipboard(displayEndpoint, "Endpoint")}
                          >
                            {copied === "Endpoint" ? (
                              <Check className="h-4 w-4" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                        {integrations?.instructions && (
                          <p className={`mt-2 text-xs ${themeClasses.textMuted}`}>
                            {integrations.instructions}
                          </p>
                        )}
                      </div>

                      <div className={`border rounded-lg p-4 ${themeClasses.cardAlt}`}>
                        <h3 className={`text-[13px] font-medium mb-2 ${themeClasses.text}`}>
                          Quick Setup — 5 steps
                        </h3>
                        <ol className={`list-decimal list-inside space-y-2 text-[13px] ${themeClasses.textMuted}`}>
                          <li>Copy your EDON Endpoint above</li>
                          <li>Replace your agent's existing gateway URL with this endpoint</li>
                          <li>Add the header <code className="bg-gray-100 text-gray-800 px-1 rounded">X-EDON-TOKEN: &lt;your-token&gt;</code> to every request</li>
                          <li>Find your token under API Tokens</li>
                          <li>Send a test request and verify the decision appears in the console</li>
                        </ol>
                      </div>

                      {(integrations?.clawdbot_configured || integrations?.clawdbot?.connected) && (
                        <div className="bg-[#163826] border border-[#1f3d2b] rounded-lg p-4">
                          <p className="text-[13px] text-[#b7f3cf]">
                            Agent credentials are configured in EDON
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          )}
          {showAgents && (
            <div className="space-y-6">
              <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                <h2 className={`text-[16px] font-semibold mb-4 ${themeClasses.text}`}>Agents</h2>
                <p className={`text-[13px] ${themeClasses.textMuted}`}>
                  Live agent activity pulled from recent decisions.
                </p>
                <div className="mt-4">
                  {isLoadingAgents ? (
                    <p className={`text-[13px] ${themeClasses.textMuted}`}>Loading agent activity...</p>
                  ) : agentsSummary.length > 0 ? (
                    <div className="space-y-2">
                      <div className={`grid grid-cols-3 gap-4 text-xs uppercase tracking-wide ${themeClasses.textMuted}`}>
                        <div>Agent</div>
                        <div>Decisions</div>
                        <div>Last seen</div>
                      </div>
                      {agentsSummary.map((agent) => (
                        <div key={agent.agent} className="grid grid-cols-3 gap-4 text-[13px]">
                          <div className={themeClasses.text}>{agent.agent}</div>
                          <div className={themeClasses.text}>{agent.decisions}</div>
                          <div className={themeClasses.textMuted}>
                            {agent.lastSeen ? new Date(agent.lastSeen).toLocaleString() : "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className={`text-[13px] ${themeClasses.textMuted}`}>
                      No agent activity yet. Complete the{" "}
                      <Link to="/account/quick-start" className="underline text-gray-700">Quick Start</Link>{" "}
                      to connect your first agent.
                    </p>
                  )}
                </div>
                <div className="mt-5 pt-4 border-t border-gray-100 flex flex-wrap items-center gap-3">
                  {isLimitReached ? (
                    <div className="w-full rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[13px] font-semibold text-amber-900">Decision limit reached — monitoring paused</p>
                        <p className="text-[12px] text-amber-800 mt-0.5">
                          Upgrade to resume agent monitoring and increase your limits.
                        </p>
                      </div>
                      <Link to="/pricing" className="shrink-0">
                        <Button className="rounded-full text-[12px] font-medium px-4 py-1.5 bg-black text-white hover:bg-neutral-800">
                          Upgrade
                        </Button>
                      </Link>
                    </div>
                  ) : hasConsoleAccess ? (
                    <Button
                      onClick={handleOpenConsole}
                      className="rounded-full text-[13px] font-medium px-5 py-2 border-gray-300 text-white bg-black hover:bg-gray-900"
                    >
                      Open Console
                    </Button>
                  ) : (
                    <div>
                      <p className={`text-[12px] mb-2 ${themeClasses.textMuted}`}>
                        Sign up to unlock agent monitoring.
                      </p>
                      <Link to="/signup">
                        <Button variant="outline" className="rounded-full text-[12px] px-3 py-1.5 border-gray-300 text-black bg-white hover:bg-gray-50">
                          Get started free
                        </Button>
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          {showConsole && (
            <div className="space-y-6">
              <div className={`rounded-xl border p-5 ${themeClasses.card}`}>
                <h2 className={`text-[16px] font-semibold mb-4 ${themeClasses.text}`}>Console</h2>
                <p className={`text-[13px] ${themeClasses.textMuted}`}>
                  Access the live Agent UI console for audits, decisions, and real-time oversight.
                </p>
                <div className="mt-4">
                  {isLimitReached ? (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 space-y-3">
                      <div>
                        <p className="text-[13px] font-semibold text-amber-900">Decision limit reached</p>
                        <p className="text-[12px] text-amber-800 mt-1">
                          Your free plan allowance of {dailyLimit?.toLocaleString()} decisions has been used up for this period. Console access is paused until you upgrade.
                        </p>
                      </div>
                      <Link to="/pricing">
                        <Button className="rounded-full text-[12px] font-medium px-4 py-1.5 bg-black text-white hover:bg-neutral-800">
                          Upgrade for higher limits
                        </Button>
                      </Link>
                    </div>
                  ) : hasConsoleAccess ? (
                    <Button
                      onClick={handleOpenConsole}
                      className="rounded-full text-[13px] font-medium px-5 py-2 shadow-sm transition-all border-gray-300 text-white bg-black hover:bg-gray-900"
                    >
                      Open Console
                    </Button>
                  ) : (
                    <div className="space-y-2">
                      <p className={`text-[12px] ${themeClasses.textMuted}`}>
                        Sign up to access the Console.
                      </p>
                      <Link to="/signup">
                        <Button
                          variant="outline"
                          className="rounded-full text-[12px] font-medium px-3 py-1.5 shadow-sm transition-all border-gray-300 text-black bg-white hover:bg-gray-50"
                        >
                          Get started free
                        </Button>
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          {showUsage && (
            <div className="space-y-6">
              {/* Decisions over time */}
              <div className={`rounded-xl border ${themeClasses.card}`}>
                <div className="flex items-center justify-between px-5 pt-5 pb-3">
                  <div>
                    <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>Decisions over time</h2>
                    <p className={`text-[12px] mt-0.5 ${themeClasses.textMuted}`}>Allow / Block / Pending breakdown by period</p>
                  </div>
                  <div className="flex items-center gap-1 text-[12px]">
                    {(["1d", "7d", "30d"] as const).map((range) => (
                      <button
                        key={range}
                        type="button"
                        onClick={() => setTimeRange(range)}
                        className={`px-2.5 py-1 rounded-md border ${
                          timeRange === range
                            ? "bg-gray-100 border-gray-300 text-gray-900"
                            : "border-transparent text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                        }`}
                      >
                        {range}
                      </button>
                    ))}
                  </div>
                </div>
                {isLoadingUsage ? (
                  <p className={`px-5 pb-5 text-[13px] ${themeClasses.textMuted}`}>Loading...</p>
                ) : usageSeries.length === 0 ? (
                  <p className={`px-5 pb-5 text-[13px] ${themeClasses.textMuted}`}>No data for this range yet.</p>
                ) : (
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className={`border-t border-b ${themeClasses.border} bg-gray-50`}>
                        <th className={`text-left px-5 py-2.5 text-xs uppercase tracking-wide font-medium ${themeClasses.textMuted}`}>Period</th>
                        <th className={`text-right px-5 py-2.5 text-xs uppercase tracking-wide font-medium text-emerald-700`}>Allowed</th>
                        <th className={`text-right px-5 py-2.5 text-xs uppercase tracking-wide font-medium text-red-600`}>Blocked</th>
                        <th className={`text-right px-5 py-2.5 text-xs uppercase tracking-wide font-medium ${themeClasses.textMuted}`}>Pending</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageSeries.map((point, idx) => (
                        <tr key={`${point.timestamp || point.label}-${idx}`} className={`border-b ${themeClasses.border} last:border-0`}>
                          <td className={`px-5 py-3 ${themeClasses.textMuted}`}>{point.label || "—"}</td>
                          <td className="px-5 py-3 text-right text-emerald-700 font-medium">{(point.allowed ?? 0).toLocaleString()}</td>
                          <td className="px-5 py-3 text-right text-red-600 font-medium">{(point.blocked ?? 0).toLocaleString()}</td>
                          <td className={`px-5 py-3 text-right ${themeClasses.text}`}>{(point.confirm ?? 0).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Block reasons */}
              <div className={`rounded-xl border ${themeClasses.card}`}>
                <div className="px-5 pt-5 pb-3">
                  <h2 className={`text-[16px] font-semibold ${themeClasses.text}`}>Top block reasons</h2>
                  <p className={`text-[12px] mt-0.5 ${themeClasses.textMuted}`}>Most common reasons decisions were blocked</p>
                </div>
                {isLoadingUsage ? (
                  <p className={`px-5 pb-5 text-[13px] ${themeClasses.textMuted}`}>Loading...</p>
                ) : blockReasons.length === 0 ? (
                  <p className={`px-5 pb-5 text-[13px] ${themeClasses.textMuted}`}>No block events in this range.</p>
                ) : (
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className={`border-t border-b ${themeClasses.border} bg-gray-50`}>
                        <th className={`text-left px-5 py-2.5 text-xs uppercase tracking-wide font-medium ${themeClasses.textMuted}`}>Reason</th>
                        <th className={`text-right px-5 py-2.5 text-xs uppercase tracking-wide font-medium ${themeClasses.textMuted}`}>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blockReasons.map((reason) => (
                        <tr key={reason.reason} className={`border-b ${themeClasses.border} last:border-0`}>
                          <td className={`px-5 py-3 ${themeClasses.text}`}>{reason.reason}</td>
                          <td className={`px-5 py-3 text-right font-medium ${themeClasses.textMuted}`}>{reason.count.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
          </main>
        </div>
      </section>

      <ScrollToTop />
    </div>
  );
};

export default Account;
