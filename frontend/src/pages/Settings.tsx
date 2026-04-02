import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { edonApi } from "@/lib/api";
import {
  Lock, Briefcase, Bot, Check, Save,
  Wifi, WifiOff, ChevronRight, ChevronDown,
  AlertTriangle, Send, Plus, Trash2, Edit2, Zap, Globe, Key,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import type { AlertPreferences } from "@/lib/api";
import { Link } from "react-router-dom";

const BASE_URL_KEY = "edon_api_base";
const TOKEN_KEY = "edon_token";
const EMAIL_KEY = "edon_user_email";
const PLAN_KEY = "edon_plan";
const WEBHOOKS_KEY = "edon_webhooks";
const LEGACY_BASE_KEYS = ["EDON_BASE_URL", "edon_api_base", "edon_base_url"] as const;

const normalizeBaseUrl = (value: string) => {
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.origin;
  } catch {
    return "";
  }
};

function getStoredBaseUrl(envUrl?: string, isProd?: boolean) {
  const v =
    LEGACY_BASE_KEYS.map((k) => localStorage.getItem(k))
      .find((x) => (x ?? "").trim().length > 0) ||
    envUrl ||
    (isProd ? "https://edon-gateway.fly.dev" : "http://127.0.0.1:8000");
  return v.trim();
}

function getStoredToken(envToken?: string) {
  return (envToken || localStorage.getItem(TOKEN_KEY) || "").trim();
}

const isLikelyToken = (s: string) =>
  /^(edon_[A-Za-z0-9._-]{16,}|[a-f0-9]{64}|[a-f0-9]{128}|[A-Za-z0-9._-]{24,})$/i.test(s);

async function safeText(res: Response) {
  try {
    return (await res.text()) || "";
  } catch {
    return "";
  }
}

const SAFETY_MODES = [
  {
    packName: "personal_safe",
    label: "Safe Mode",
    icon: Lock,
    description: "High-risk actions are blocked before they run. Best starting point for any deployment.",
    recommended: true,
    caution: false,
  },
  {
    packName: "work_safe",
    label: "Business Mode",
    icon: Briefcase,
    description: "Business operations run freely. Sensitive actions (financial, data access) require approval.",
    recommended: false,
    caution: false,
  },
  {
    packName: "ops_admin",
    label: "Autonomy Mode",
    icon: Bot,
    description: "Agents operate without interruption. Only critical safety violations are surfaced.",
    recommended: false,
    caution: true,
  },
] as const;

const WEBHOOK_EVENTS = [
  { id: "decision.blocked", label: "Decision blocked" },
  { id: "decision.allowed", label: "Decision allowed" },
  { id: "decision.confirm", label: "Decision needs confirmation" },
  { id: "policy.changed", label: "Policy changed" },
  { id: "agent.connected", label: "Agent connected" },
];

interface Webhook {
  id: string;
  url: string;
  events: string[];
  secret: string;
  status: "active" | "paused";
  createdAt: string;
}

const loadWebhooks = (): Webhook[] => {
  try {
    const raw = localStorage.getItem(WEBHOOKS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveWebhooks = (hooks: Webhook[]) => {
  localStorage.setItem(WEBHOOKS_KEY, JSON.stringify(hooks));
};

export default function Settings() {
  const { toast } = useToast();
  const isProd = import.meta.env.MODE === "production";

  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8000");
  const [token, setToken] = useState("");
  const [connectionStatus, setConnectionStatus] = useState<"unknown" | "connected" | "failed">("unknown");
  const [testing, setTesting] = useState(false);
  const [applyingSafety, setApplyingSafety] = useState<string | null>(null);
  const [connectionOpen, setConnectionOpen] = useState(false);

  const [userName, setUserName] = useState<string>("");
  const [planName, setPlanName] = useState<string>("");
  const [decisionsUsed, setDecisionsUsed] = useState<number | null>(null);
  const [decisionsLimit, setDecisionsLimit] = useState<number | null>(null);
  const [safetyPreset, setSafetyPreset] = useState<string | null>(null);
  const [telegramConnected, setTelegramConnected] = useState(false);
  const [slackConnected, setSlackConnected] = useState(false);
  const [discordConnected, setDiscordConnected] = useState(false);

  const [telegramOpen, setTelegramOpen] = useState(false);
  const [slackOpen, setSlackOpen] = useState(false);
  const [discordOpen, setDiscordOpen] = useState(false);

  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");

  const [connectingChannel, setConnectingChannel] = useState<string | null>(null);
  const [alertPrefs, setAlertPrefs] = useState<AlertPreferences>({
    alert_on_blocked: true,
    alert_on_policy_violation: true,
    alert_on_drift: true,
    alert_on_escalation: true,
  });
  const [savingAlertPrefs, setSavingAlertPrefs] = useState(false);
  const [loadingAccount, setLoadingAccount] = useState(false);

  // Integrations tab state
  const [backendUrl, setBackendUrl] = useState("");
  const [backendAuthToken, setBackendAuthToken] = useState("");
  const [credentialId, setCredentialId] = useState("agent_gateway");
  const [probeOnConnect, setProbeOnConnect] = useState(true);
  const [connectingBackend, setConnectingBackend] = useState(false);
  const [backendConnected, setBackendConnected] = useState(false);
  const [backendConnectedUrl, setBackendConnectedUrl] = useState("");
  const [backendError, setBackendError] = useState("");

  // Webhooks tab state
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [addWebhookOpen, setAddWebhookOpen] = useState(false);
  const [editWebhook, setEditWebhook] = useState<Webhook | null>(null);
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookEvents, setNewWebhookEvents] = useState<string[]>(["decision.blocked"]);
  const [newWebhookSecret, setNewWebhookSecret] = useState("");

  useEffect(() => {
    const envUrl = import.meta.env.VITE_EDON_GATEWAY_URL as string | undefined;
    const envToken = import.meta.env.VITE_EDON_API_TOKEN as string | undefined;
    setBaseUrl(getStoredBaseUrl(envUrl, isProd));
    setToken(getStoredToken(envToken));
    setUserName(localStorage.getItem(EMAIL_KEY) || "");
    setPlanName(localStorage.getItem(PLAN_KEY) || "");
    setWebhooks(loadWebhooks());
  }, [isProd]);

  const persist = (trimmedBase: string, trimmedToken: string) => {
    localStorage.setItem(BASE_URL_KEY, trimmedBase);
    localStorage.setItem(TOKEN_KEY, trimmedToken);
    localStorage.setItem("edon_api_key", trimmedToken);
    localStorage.setItem("EDON_BASE_URL", trimmedBase);
    localStorage.setItem("edon_base_url", trimmedBase);
  };

  const loadAccountAndIntegrations = async () => {
    const t = getStoredToken();
    if (!t || !isLikelyToken(t)) return;
    setLoadingAccount(true);
    try {
      const [session, billing, health, integrations] = await Promise.all([
        edonApi.getSession().catch(() => null),
        edonApi.getBillingStatus().catch(() => null),
        edonApi.getHealth().catch(() => null),
        edonApi.getIntegrations().catch(() => ({})),
      ]);

      if (session?.email) {
        setUserName(session.email);
        localStorage.setItem(EMAIL_KEY, session.email);
      }
      if (session?.plan) {
        setPlanName(session.plan);
        localStorage.setItem(PLAN_KEY, session.plan);
      }
      if (billing) {
        setPlanName((billing as { plan?: string }).plan ?? planName);
        const usage = (billing as { usage?: { today?: number } }).usage;
        const limits = (billing as { limits?: { requests_per_month?: number } }).limits;
        const used = usage?.today ?? null;
        const limit = limits?.requests_per_month ?? null;
        if (typeof used === "number") setDecisionsUsed(used);
        if (typeof limit === "number") setDecisionsLimit(limit);
      }
      if (health?.governor?.active_preset?.preset_name) {
        setSafetyPreset(health.governor.active_preset.preset_name);
      }
      if (integrations && typeof integrations === "object") {
        const obj = integrations as Record<string, unknown>;
        const tg = obj.telegram as { connected?: boolean } | undefined;
        const slack = obj.slack as { connected?: boolean } | undefined;
        const discord = obj.discord as { connected?: boolean } | undefined;
        setTelegramConnected(!!tg?.connected);
        setSlackConnected(!!slack?.connected);
        setDiscordConnected(!!discord?.connected);
        const prefs = obj.alert_preferences as AlertPreferences | undefined;
        if (prefs && typeof prefs === "object") {
          setAlertPrefs({
            alert_on_blocked: prefs.alert_on_blocked ?? true,
            alert_on_policy_violation: prefs.alert_on_policy_violation ?? true,
            alert_on_drift: prefs.alert_on_drift ?? true,
            alert_on_escalation: prefs.alert_on_escalation ?? true,
          });
        } else {
          const alertPrefsData = await edonApi.getAlertPreferences().catch(() => null);
          if (alertPrefsData) {
            setAlertPrefs({
              alert_on_blocked: alertPrefsData.alert_on_blocked ?? true,
              alert_on_policy_violation: alertPrefsData.alert_on_policy_violation ?? true,
              alert_on_drift: alertPrefsData.alert_on_drift ?? true,
              alert_on_escalation: alertPrefsData.alert_on_escalation ?? true,
            });
          }
        }
      }
    } catch {
      // silently keep existing state
    } finally {
      setLoadingAccount(false);
    }
  };

  useEffect(() => {
    loadAccountAndIntegrations();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const applySafetyMode = async (packName: string) => {
    setApplyingSafety(packName);
    try {
      await edonApi.applyPolicyPack(packName);
      setSafetyPreset(packName);
      const label = SAFETY_MODES.find((m) => m.packName === packName)?.label ?? packName;
      toast({ title: "Safety mode updated", description: `${label} is now active.` });
      loadAccountAndIntegrations();
    } catch (err: unknown) {
      toast({
        title: "Failed to set safety mode",
        description: err instanceof Error ? err.message : "Could not apply.",
        variant: "destructive",
      });
    } finally {
      setApplyingSafety(null);
    }
  };

  const saveSettings = () => {
    const trimmedBase = baseUrl.trim();
    const trimmedToken = token.trim();
    const safeBase = normalizeBaseUrl(trimmedBase);

    if (/PASTE_YOUR_|NEW_GATEWAY_TOKEN_|TOKEN_HERE/i.test(trimmedToken)) {
      toast({ title: "Invalid access key", description: "Paste your real EDON access key.", variant: "destructive" });
      return;
    }
    if (!safeBase) {
      toast({ title: "Invalid gateway URL", description: "Enter a valid https:// URL.", variant: "destructive" });
      return;
    }
    if (!isLikelyToken(trimmedToken)) {
      toast({ title: "Invalid access key", description: "The key format doesn't look right.", variant: "destructive" });
      return;
    }
    persist(safeBase, trimmedToken);
    toast({ title: "Saved", description: "Your connection settings have been saved." });
  };

  const testConnection = async () => {
    setTesting(true);
    setConnectionStatus("unknown");
    const trimmedBase = baseUrl.trim();
    const trimmedToken = token.trim();
    const safeBase = normalizeBaseUrl(trimmedBase);

    try {
      if (!safeBase || !isLikelyToken(trimmedToken)) {
        throw new Error("Add a valid gateway URL and access key first.");
      }
      persist(safeBase, trimmedToken);
      const base = safeBase.replace(/\/$/, "");
      const res = await fetch(`${base}/health`, {
        method: "GET",
        headers: { "X-EDON-TOKEN": trimmedToken },
      });
      if (res.status === 401) throw new Error("Access key not accepted.");
      if (!res.ok) throw new Error(`Connection error (${res.status}). ${await safeText(res)}`);

      setConnectionStatus("connected");
      toast({ title: "Connected", description: "Gateway is reachable and your key is accepted." });
      loadAccountAndIntegrations();
    } catch (err: unknown) {
      setConnectionStatus("failed");
      toast({
        title: "Connection failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setTesting(false);
    }
  };

  const connectBackend = async () => {
    if (!backendUrl.trim()) {
      toast({ title: "Backend URL required", description: "Enter your agent backend URL.", variant: "destructive" });
      return;
    }
    setConnectingBackend(true);
    setBackendError("");
    try {
      await edonApi.connectClawdbot({
        base_url: backendUrl.trim(),
        secret: backendAuthToken.trim(),
        auth_mode: "token",
        credential_id: credentialId.trim() || "agent_gateway",
        probe: probeOnConnect,
      });
      setBackendConnected(true);
      setBackendConnectedUrl(backendUrl.trim());
      toast({ title: "Backend connected", description: `EDON will now proxy allowed requests to ${backendUrl.trim()}.` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not connect to backend.";
      setBackendError(msg);
      toast({ title: "Connection failed", description: msg, variant: "destructive" });
    } finally {
      setConnectingBackend(false);
    }
  };

  // Webhook helpers
  const persistWebhooks = (next: Webhook[]) => {
    setWebhooks(next);
    saveWebhooks(next);
  };

  const openAddWebhook = () => {
    setEditWebhook(null);
    setNewWebhookUrl("");
    setNewWebhookEvents(["decision.blocked"]);
    setNewWebhookSecret("");
    setAddWebhookOpen(true);
  };

  const openEditWebhook = (hook: Webhook) => {
    setEditWebhook(hook);
    setNewWebhookUrl(hook.url);
    setNewWebhookEvents([...hook.events]);
    setNewWebhookSecret(hook.secret);
    setAddWebhookOpen(true);
  };

  const saveWebhook = () => {
    if (!newWebhookUrl.trim()) {
      toast({ title: "URL required", description: "Enter a webhook URL.", variant: "destructive" });
      return;
    }
    if (newWebhookEvents.length === 0) {
      toast({ title: "Select events", description: "Choose at least one event.", variant: "destructive" });
      return;
    }
    if (editWebhook) {
      const next = webhooks.map((h) =>
        h.id === editWebhook.id
          ? { ...h, url: newWebhookUrl.trim(), events: newWebhookEvents, secret: newWebhookSecret.trim() }
          : h
      );
      persistWebhooks(next);
      toast({ title: "Webhook updated" });
    } else {
      const hook: Webhook = {
        id: `wh_${Date.now()}`,
        url: newWebhookUrl.trim(),
        events: newWebhookEvents,
        secret: newWebhookSecret.trim(),
        status: "active",
        createdAt: new Date().toISOString(),
      };
      persistWebhooks([hook, ...webhooks]);
      toast({ title: "Webhook added" });
    }
    setAddWebhookOpen(false);
  };

  const deleteWebhook = (id: string) => {
    persistWebhooks(webhooks.filter((h) => h.id !== id));
    toast({ title: "Webhook removed" });
  };

  const toggleWebhookStatus = (id: string) => {
    const next = webhooks.map((h) =>
      h.id === id ? { ...h, status: h.status === "active" ? ("paused" as const) : ("active" as const) } : h
    );
    persistWebhooks(next);
  };

  const testWebhook = (hook: Webhook) => {
    toast({ title: "Test event sent", description: `Mock ping sent to ${hook.url.slice(0, 40)}…` });
  };

  const toggleWebhookEvent = (eventId: string) => {
    setNewWebhookEvents((prev) =>
      prev.includes(eventId) ? prev.filter((e) => e !== eventId) : [...prev, eventId]
    );
  };

  // Seed mock webhook on first load if empty
  useEffect(() => {
    const existing = loadWebhooks();
    if (existing.length === 0) {
      const mock: Webhook = {
        id: "wh_example",
        url: "https://your-app.example.com/webhooks/edon",
        events: ["decision.blocked", "policy.changed"],
        secret: "",
        status: "active",
        createdAt: new Date(Date.now() - 86400000 * 3).toISOString(),
      };
      saveWebhooks([mock]);
      setWebhooks([mock]);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeSafetyPack = safetyPreset ?? "personal_safe";
  const usagePct = decisionsUsed != null && decisionsLimit != null && decisionsLimit > 0
    ? Math.min(100, (decisionsUsed / decisionsLimit) * 100)
    : null;

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-2xl">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">

          {/* Page title */}
          <div>
            <h1 className="text-xl font-semibold text-foreground/90">Settings</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage your account, safety mode, channels, integrations, and webhooks.
            </p>
          </div>

          <Tabs defaultValue="general" className="w-full">
            <TabsList className="w-full grid grid-cols-5 bg-white/5 border border-white/10 rounded-xl p-1 mb-6">
              <TabsTrigger value="general" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-foreground rounded-lg">General</TabsTrigger>
              <TabsTrigger value="channels" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-foreground rounded-lg">Channels</TabsTrigger>
              <TabsTrigger value="integrations" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-foreground rounded-lg">Integrations</TabsTrigger>
              <TabsTrigger value="webhooks" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-foreground rounded-lg">Webhooks</TabsTrigger>
              <TabsTrigger value="chat" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-foreground rounded-lg">Chat AI</TabsTrigger>
            </TabsList>

            {/* ── GENERAL TAB ─────────────────────────── */}
            <TabsContent value="general" className="space-y-6 mt-0">

              {/* ACCOUNT */}
              <section>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Account</p>
                <div className="glass-card divide-y divide-white/5">
                  <div className="px-5 py-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">{userName || "Signed in"}</p>
                      {planName && (
                        <p className="text-xs text-muted-foreground mt-0.5 capitalize">{planName} plan</p>
                      )}
                    </div>
                    <a
                      href="https://edoncore.com/account"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline inline-flex items-center gap-0.5 shrink-0"
                    >
                      Manage account <ChevronRight className="h-3 w-3" />
                    </a>
                  </div>
                  <div className="px-5 py-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-muted-foreground">Decisions today</p>
                      {decisionsUsed != null && decisionsLimit != null ? (
                        <p className="text-xs font-medium tabular-nums">
                          {decisionsUsed.toLocaleString()} / {decisionsLimit.toLocaleString()}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground/50">
                          {loadingAccount ? "Loading…" : "—"}
                        </p>
                      )}
                    </div>
                    {usagePct != null ? (
                      <>
                        <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              usagePct >= 90 ? "bg-red-400/80" : usagePct >= 70 ? "bg-amber-400/80" : "bg-primary/70"
                            }`}
                            style={{ width: `${usagePct}%` }}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground mt-1.5">
                          {Math.max(0, decisionsLimit! - decisionsUsed!).toLocaleString()} remaining today
                        </p>
                      </>
                    ) : (
                      <div className="h-1.5 rounded-full bg-white/10" />
                    )}
                  </div>
                </div>
              </section>

              {/* SAFETY MODE */}
              <section>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Safety Mode</p>
                  <Link to="/policies" className="text-xs text-primary hover:underline inline-flex items-center gap-0.5">
                    Advanced <ChevronRight className="h-3 w-3" />
                  </Link>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  Controls how much your agents can do without asking for approval.
                </p>
                <div className="space-y-2">
                  {SAFETY_MODES.map((mode) => {
                    const Icon = mode.icon;
                    const isActive = activeSafetyPack === mode.packName;
                    return (
                      <button
                        key={mode.packName}
                        type="button"
                        onClick={() => !isActive && applySafetyMode(mode.packName)}
                        disabled={applyingSafety === mode.packName}
                        className={`w-full flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left transition-colors ${
                          isActive
                            ? "border-primary/50 bg-primary/10"
                            : "border-white/10 bg-white/5 hover:bg-white/10 cursor-pointer"
                        }`}
                      >
                        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                          isActive ? "bg-primary/20" : "bg-white/10"
                        }`}>
                          <Icon className={`h-4 w-4 ${isActive ? "text-primary" : "text-foreground/80"}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-medium text-sm">{mode.label}</p>
                            {mode.recommended && !isActive && (
                              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
                                Recommended
                              </span>
                            )}
                            {mode.caution && !isActive && (
                              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/25 flex items-center gap-1">
                                <AlertTriangle className="h-2.5 w-2.5" /> High trust
                              </span>
                            )}
                            {isActive && (
                              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30 flex items-center gap-1">
                                <Check className="h-2.5 w-2.5" /> Active
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">{mode.description}</p>
                        </div>
                        {applyingSafety === mode.packName && (
                          <div className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>
              </section>

              {/* ALERT PREFERENCES */}
              <section>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Alert preferences</p>
                <p className="text-xs text-muted-foreground mb-3">
                  Choose what to be notified about (via your connected channels).
                </p>
                <div className="glass-card px-5 py-4 space-y-4">
                  {[
                    { key: "alert_on_blocked" as const, label: "Blocked decisions", desc: "When a decision is blocked by policy" },
                    { key: "alert_on_policy_violation" as const, label: "Policy violations", desc: "When a policy rule is violated" },
                    { key: "alert_on_drift" as const, label: "Drift / anomalies", desc: "When behavior drifts from baseline" },
                    { key: "alert_on_escalation" as const, label: "Escalations", desc: "When an action requires human approval" },
                  ].map(({ key, label, desc }) => (
                    <div key={key} className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">{label}</p>
                        <p className="text-xs text-muted-foreground">{desc}</p>
                      </div>
                      <Switch
                        checked={!!alertPrefs[key]}
                        disabled={savingAlertPrefs}
                        onCheckedChange={async (checked) => {
                          const next = { ...alertPrefs, [key]: checked };
                          setAlertPrefs(next);
                          setSavingAlertPrefs(true);
                          try {
                            await edonApi.patchAlertPreferences({ [key]: checked });
                            toast({ title: "Saved", description: "Alert preferences updated." });
                          } catch {
                            setAlertPrefs(alertPrefs);
                            toast({ title: "Error", description: "Could not save preferences.", variant: "destructive" });
                          } finally {
                            setSavingAlertPrefs(false);
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>
              </section>

              {/* GATEWAY CONNECTION */}
              <section>
                <button
                  type="button"
                  onClick={() => setConnectionOpen((v) => !v)}
                  className="w-full flex items-center justify-between px-5 py-3 glass-card text-sm text-muted-foreground hover:text-foreground/80 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    {connectionStatus === "connected" ? (
                      <Wifi className="h-3.5 w-3.5 text-emerald-400" />
                    ) : connectionStatus === "failed" ? (
                      <WifiOff className="h-3.5 w-3.5 text-red-400" />
                    ) : (
                      <Wifi className="h-3.5 w-3.5 text-muted-foreground/50" />
                    )}
                    <span>
                      Gateway connection
                      {connectionStatus === "connected" && <span className="ml-2 text-xs text-emerald-400">● Active</span>}
                      {connectionStatus === "failed" && <span className="ml-2 text-xs text-red-400">● Failed</span>}
                    </span>
                  </div>
                  <ChevronDown className={`h-4 w-4 transition-transform ${connectionOpen ? "rotate-180" : ""}`} />
                </button>

                {connectionOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="glass-card mt-1 px-5 py-4 space-y-4 border-t-0 rounded-t-none"
                  >
                    <p className="text-xs text-muted-foreground">
                      This is set automatically when you sign in from{" "}
                      <a href="https://edoncore.com" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                        edoncore.com
                      </a>
                      . Only update this if you're running a self-hosted gateway.
                    </p>
                    <div className="space-y-1">
                      <Label htmlFor="baseUrl" className="text-xs text-muted-foreground">EDON Gateway URL</Label>
                      <Input
                        id="baseUrl"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        placeholder="https://api.edoncore.com"
                        className="bg-secondary/50 mt-1 font-mono text-sm"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="token" className="text-xs text-muted-foreground">Access key</Label>
                      <Input
                        id="token"
                        type="password"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        placeholder="Your EDON access key"
                        className="bg-secondary/50 mt-1"
                      />
                      <p className="text-xs text-muted-foreground/60">
                        Find your access key under API Keys at edoncore.com/account
                      </p>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <Button onClick={testConnection} disabled={testing} variant="outline" size="sm" className="gap-2">
                        {testing ? (
                          <>
                            <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                            Checking…
                          </>
                        ) : (
                          <>
                            {connectionStatus === "connected" ? (
                              <Wifi className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <WifiOff className="w-3 h-3" />
                            )}
                            {connectionStatus === "connected" ? "Re-test" : "Test connection"}
                          </>
                        )}
                      </Button>
                      <Button onClick={saveSettings} size="sm" className="gap-2">
                        <Save className="w-3 h-3" />
                        Save
                      </Button>
                    </div>
                  </motion.div>
                )}
              </section>
            </TabsContent>

            {/* ── CHANNELS TAB ─────────────────────────── */}
            <TabsContent value="channels" className="space-y-4 mt-0">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1">Channels</p>
                <p className="text-xs text-muted-foreground mb-4">
                  Get updates via Telegram, Slack, or Discord. Choose what to be alerted on in the General tab.
                </p>
              </div>

              {/* Telegram */}
              <div className="glass-card px-5 py-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                      <Send className="h-3.5 w-3.5 text-foreground/80" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Telegram</p>
                      <p className="text-xs text-muted-foreground">
                        {telegramConnected ? "Receiving governance alerts" : "Get alerts via Telegram bot"}
                      </p>
                    </div>
                  </div>
                  {telegramConnected ? (
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs shrink-0">
                      <Check className="h-3 w-3 mr-1" /> Connected
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setTelegramOpen((v) => !v)}
                      className="text-xs text-primary hover:underline shrink-0"
                    >
                      {telegramOpen ? "Cancel" : "Connect →"}
                    </button>
                  )}
                </div>
                {!telegramConnected && telegramOpen && (
                  <div className="space-y-2 pt-1">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Bot Token</Label>
                      <Input
                        type="password"
                        value={telegramToken}
                        onChange={(e) => setTelegramToken(e.target.value)}
                        placeholder="123456789:AAF..."
                        className="bg-secondary/50 text-sm"
                      />
                      <p className="text-xs text-muted-foreground/60">From @BotFather on Telegram</p>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Chat ID</Label>
                      <Input
                        value={telegramChatId}
                        onChange={(e) => setTelegramChatId(e.target.value)}
                        placeholder="-1001234567890"
                        className="bg-secondary/50 text-sm"
                      />
                      <p className="text-xs text-muted-foreground/60">Your chat or group ID</p>
                    </div>
                    <Button
                      size="sm"
                      disabled={!telegramToken || !telegramChatId || connectingChannel === "telegram"}
                      onClick={async () => {
                        setConnectingChannel("telegram");
                        try {
                          await edonApi.connectTelegram(telegramToken, telegramChatId);
                          setTelegramConnected(true);
                          setTelegramOpen(false);
                          setTelegramToken("");
                          setTelegramChatId("");
                          toast({ title: "Telegram connected", description: "You'll receive alerts via your bot." });
                        } catch (err: unknown) {
                          toast({ title: "Failed", description: err instanceof Error ? err.message : "Could not connect.", variant: "destructive" });
                        } finally {
                          setConnectingChannel(null);
                        }
                      }}
                      className="w-full gap-2"
                    >
                      {connectingChannel === "telegram" ? (
                        <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Connecting…</>
                      ) : "Save Telegram"}
                    </Button>
                  </div>
                )}
              </div>

              {/* Slack */}
              <div className="glass-card px-5 py-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                      <Send className="h-3.5 w-3.5 text-foreground/80" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Slack</p>
                      <p className="text-xs text-muted-foreground">
                        {slackConnected ? "Receiving governance alerts" : "Get alerts posted to a Slack channel"}
                      </p>
                    </div>
                  </div>
                  {slackConnected ? (
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs shrink-0">
                      <Check className="h-3 w-3 mr-1" /> Connected
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setSlackOpen((v) => !v)}
                      className="text-xs text-primary hover:underline shrink-0"
                    >
                      {slackOpen ? "Cancel" : "Connect →"}
                    </button>
                  )}
                </div>
                {!slackConnected && slackOpen && (
                  <div className="space-y-2 pt-1">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Incoming Webhook URL</Label>
                      <Input
                        type="password"
                        value={slackWebhook}
                        onChange={(e) => setSlackWebhook(e.target.value)}
                        placeholder="https://hooks.slack.com/services/..."
                        className="bg-secondary/50 text-sm"
                      />
                      <p className="text-xs text-muted-foreground/60">From your Slack app's Incoming Webhooks settings</p>
                    </div>
                    <Button
                      size="sm"
                      disabled={!slackWebhook || connectingChannel === "slack"}
                      onClick={async () => {
                        setConnectingChannel("slack");
                        try {
                          await edonApi.connectSlack(slackWebhook);
                          setSlackConnected(true);
                          setSlackOpen(false);
                          setSlackWebhook("");
                          toast({ title: "Slack connected", description: "You'll receive alerts in your Slack channel." });
                        } catch (err: unknown) {
                          toast({ title: "Failed", description: err instanceof Error ? err.message : "Could not connect.", variant: "destructive" });
                        } finally {
                          setConnectingChannel(null);
                        }
                      }}
                      className="w-full gap-2"
                    >
                      {connectingChannel === "slack" ? (
                        <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Connecting…</>
                      ) : "Save Slack"}
                    </Button>
                  </div>
                )}
              </div>

              {/* Discord */}
              <div className="glass-card px-5 py-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                      <Send className="h-3.5 w-3.5 text-foreground/80" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Discord</p>
                      <p className="text-xs text-muted-foreground">
                        {discordConnected ? "Receiving governance alerts" : "Get alerts posted to a Discord channel"}
                      </p>
                    </div>
                  </div>
                  {discordConnected ? (
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs shrink-0">
                      <Check className="h-3 w-3 mr-1" /> Connected
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setDiscordOpen((v) => !v)}
                      className="text-xs text-primary hover:underline shrink-0"
                    >
                      {discordOpen ? "Cancel" : "Connect →"}
                    </button>
                  )}
                </div>
                {!discordConnected && discordOpen && (
                  <div className="space-y-2 pt-1">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Webhook URL</Label>
                      <Input
                        type="password"
                        value={discordWebhook}
                        onChange={(e) => setDiscordWebhook(e.target.value)}
                        placeholder="https://discord.com/api/webhooks/..."
                        className="bg-secondary/50 text-sm"
                      />
                      <p className="text-xs text-muted-foreground/60">From your Discord server's channel settings → Integrations</p>
                    </div>
                    <Button
                      size="sm"
                      disabled={!discordWebhook || connectingChannel === "discord"}
                      onClick={async () => {
                        setConnectingChannel("discord");
                        try {
                          await edonApi.connectDiscord(discordWebhook);
                          setDiscordConnected(true);
                          setDiscordOpen(false);
                          setDiscordWebhook("");
                          toast({ title: "Discord connected", description: "You'll receive alerts in your Discord channel." });
                        } catch (err: unknown) {
                          toast({ title: "Failed", description: err instanceof Error ? err.message : "Could not connect.", variant: "destructive" });
                        } finally {
                          setConnectingChannel(null);
                        }
                      }}
                      className="w-full gap-2"
                    >
                      {connectingChannel === "discord" ? (
                        <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Connecting…</>
                      ) : "Save Discord"}
                    </Button>
                  </div>
                )}
              </div>
            </TabsContent>

            {/* ── INTEGRATIONS TAB ─────────────────────── */}
            <TabsContent value="integrations" className="space-y-6 mt-0">
              <div>
                <h2 className="text-base font-semibold mb-1">Connect Your Agent Backend</h2>
                <p className="text-sm text-muted-foreground">
                  Point EDON at your agent's backend. EDON will govern all requests and proxy allowed ones to your backend.
                </p>
              </div>

              {backendConnected && (
                <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                  <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-emerald-400">Connected</p>
                    <p className="text-xs text-muted-foreground truncate">
                      Backend connected. EDON will now proxy allowed requests to {backendConnectedUrl}
                    </p>
                  </div>
                </div>
              )}

              {backendError && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
                  <p className="text-sm text-red-400">{backendError}</p>
                </div>
              )}

              <div className="glass-card px-5 py-5 space-y-4">
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Backend URL</Label>
                  <Input
                    value={backendUrl}
                    onChange={(e) => setBackendUrl(e.target.value)}
                    placeholder="https://your-agent-backend.example.com"
                    className="bg-secondary/50"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Auth Token</Label>
                  <div className="flex items-center gap-2">
                    <Key className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <Input
                      type="password"
                      value={backendAuthToken}
                      onChange={(e) => setBackendAuthToken(e.target.value)}
                      placeholder="Bearer token EDON sends to your backend"
                      className="bg-secondary/50"
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Credential ID</Label>
                  <Input
                    value={credentialId}
                    onChange={(e) => setCredentialId(e.target.value)}
                    placeholder="agent_gateway"
                    className="bg-secondary/50 font-mono"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="probe"
                    checked={probeOnConnect}
                    onCheckedChange={(v) => setProbeOnConnect(!!v)}
                  />
                  <Label htmlFor="probe" className="text-sm cursor-pointer">Probe on connect — test connection before saving</Label>
                </div>
                <Button
                  onClick={connectBackend}
                  disabled={connectingBackend}
                  className="w-full gap-2"
                >
                  {connectingBackend ? (
                    <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Connecting…</>
                  ) : (
                    <><Globe className="h-4 w-4" /> Connect Backend</>
                  )}
                </Button>
              </div>

              <div className="glass-card px-5 py-5 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold">How it works</h3>
                </div>
                <ol className="space-y-2.5">
                  {[
                    "Your agent calls EDON's /agent/invoke with {tool, action, args}",
                    "EDON applies governance policy → ALLOW or BLOCK",
                    "On ALLOW, EDON calls your backend's /tools/invoke and returns the response",
                    "Your backend receives: {tool, action, args} with Authorization: Bearer <your-token>",
                  ].map((step, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/10 text-[10px] font-semibold text-foreground/80 mt-0.5">
                        {i + 1}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </TabsContent>

            {/* ── WEBHOOKS TAB ─────────────────────────── */}
            <TabsContent value="webhooks" className="space-y-6 mt-0">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold">Webhook Endpoints</h2>
                  <p className="text-sm text-muted-foreground mt-0.5">Receive real-time events when governance decisions occur.</p>
                </div>
                <Button onClick={openAddWebhook} size="sm" className="gap-2">
                  <Plus className="h-3.5 w-3.5" /> Add Webhook
                </Button>
              </div>

              {webhooks.length === 0 ? (
                <div className="glass-card px-5 py-8 text-center text-muted-foreground text-sm">
                  No webhooks configured. Click "Add Webhook" to get started.
                </div>
              ) : (
                <div className="space-y-3">
                  {webhooks.map((hook) => (
                    <div key={hook.id} className="glass-card px-5 py-4 space-y-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-mono text-foreground/90 truncate" title={hook.url}>
                            {hook.url.length > 55 ? hook.url.slice(0, 55) + "…" : hook.url}
                          </p>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {hook.events.map((ev) => (
                              <Badge key={ev} variant="outline" className="text-[10px] px-1.5 py-0.5 border-white/20 text-muted-foreground">
                                {ev}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <Badge
                            variant="outline"
                            className={`text-[10px] cursor-pointer ${
                              hook.status === "active"
                                ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                : "border-white/20 text-muted-foreground"
                            }`}
                            onClick={() => toggleWebhookStatus(hook.id)}
                          >
                            {hook.status === "active" ? "Active" : "Paused"}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[10px] text-muted-foreground/60">
                          Added {new Date(hook.createdAt).toLocaleDateString()}
                        </p>
                        <div className="flex items-center gap-1">
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1" onClick={() => testWebhook(hook)}>
                            Test
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => openEditWebhook(hook)}>
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-red-400 hover:text-red-300" onClick={() => deleteWebhook(hook.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* ── CHAT AI TAB ─────────────────────────── */}
            <TabsContent value="chat" className="space-y-6 mt-0">
              <ChatAiTab />
            </TabsContent>

          </Tabs>

        </motion.div>
      </main>

      {/* Add/Edit Webhook Dialog */}
      <Dialog open={addWebhookOpen} onOpenChange={setAddWebhookOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle>{editWebhook ? "Edit Webhook" : "Add Webhook"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">URL</Label>
              <Input
                value={newWebhookUrl}
                onChange={(e) => setNewWebhookUrl(e.target.value)}
                placeholder="https://your-app.example.com/webhooks/edon"
                className="bg-secondary/50 font-mono text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Events</Label>
              <div className="space-y-2">
                {WEBHOOK_EVENTS.map((ev) => (
                  <div key={ev.id} className="flex items-center gap-2">
                    <Checkbox
                      id={`ev-${ev.id}`}
                      checked={newWebhookEvents.includes(ev.id)}
                      onCheckedChange={() => toggleWebhookEvent(ev.id)}
                    />
                    <Label htmlFor={`ev-${ev.id}`} className="text-sm cursor-pointer font-mono text-xs text-foreground/90">
                      {ev.id}
                      <span className="text-muted-foreground ml-2 font-sans">{ev.label}</span>
                    </Label>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Secret (optional)</Label>
              <Input
                type="password"
                value={newWebhookSecret}
                onChange={(e) => setNewWebhookSecret(e.target.value)}
                placeholder="Used to sign payloads for verification"
                className="bg-secondary/50 text-sm"
              />
              <p className="text-xs text-muted-foreground/60">EDON will HMAC-SHA256 sign payloads with this secret.</p>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button onClick={saveWebhook} className="flex-1">
                {editWebhook ? "Save Changes" : "Add Webhook"}
              </Button>
              <Button variant="outline" onClick={() => setAddWebhookOpen(false)}>Cancel</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Chat AI Configuration tab
───────────────────────────────────────────────────────── */
function ChatAiTab() {
  const { toast } = useToast();
  const [provider, setProvider] = useState<"anthropic" | "openai" | "gateway">(
    () => (localStorage.getItem("edon_chat_provider") as "anthropic" | "openai" | "gateway") || "gateway"
  );
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("edon_chat_api_key") || "");
  const [model, setModel] = useState(() => localStorage.getItem("edon_chat_model") || "");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);

  const ANTHROPIC_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"];
  const OPENAI_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"];
  const defaultModel = provider === "anthropic" ? "claude-sonnet-4-6" : provider === "openai" ? "gpt-4o" : "";

  const handleSave = async () => {
    setSaving(true);
    localStorage.setItem("edon_chat_provider", provider);
    localStorage.setItem("edon_chat_api_key", apiKey.trim());
    localStorage.setItem("edon_chat_model", model || defaultModel);
    window.dispatchEvent(new Event("edon-chat-config-updated"));
    await new Promise((r) => setTimeout(r, 400));
    setSaving(false);
    toast({ title: "Chat AI saved", description: `Using ${provider === "anthropic" ? "Anthropic Claude" : provider === "openai" ? "OpenAI" : "EDON Gateway"}` });
  };

  const handleTest = () => {
    localStorage.setItem("edon_chat_provider", provider);
    localStorage.setItem("edon_chat_api_key", apiKey.trim());
    localStorage.setItem("edon_chat_model", model || defaultModel);
    window.dispatchEvent(new Event("edon-chat-config-updated"));
    window.dispatchEvent(new Event("edon-chat-open"));
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("edon-chat-command", { detail: { message: "What's my gateway status and how many decisions were made in the last 24 hours?" } }));
    }, 700);
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Chat AI Configuration</h3>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Connect an LLM to power the EDON governance assistant. It receives your full dashboard — metrics, decisions, audit trail, policies, agent activity — as context on every message.
        </p>
      </div>

      {/* Provider */}
      <div className="space-y-3">
        <Label className="text-xs text-muted-foreground">LLM Provider</Label>
        <div className="grid grid-cols-3 gap-2">
          {([
            { id: "anthropic" as const, label: "Anthropic Claude", color: "border-orange-500/40 text-orange-300 bg-orange-500/10" },
            { id: "openai" as const, label: "OpenAI", color: "border-sky-500/40 text-sky-300 bg-sky-500/10" },
            { id: "gateway" as const, label: "Via EDON Gateway", color: "border-white/20 text-foreground/80 bg-white/5" },
          ]).map((p) => (
            <button
              key={p.id}
              onClick={() => { setProvider(p.id); setModel(""); }}
              className={`rounded-xl border px-3 py-3 text-xs font-medium transition-all ${
                provider === p.id
                  ? p.color + " ring-1 ring-offset-0"
                  : "border-white/10 text-muted-foreground bg-white/[0.02] hover:bg-white/5"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {provider !== "gateway" ? (
        <>
          {/* API Key */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">
              {provider === "anthropic" ? "Anthropic API Key" : "OpenAI API Key"}
            </Label>
            <div className="flex gap-2">
              <Input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={provider === "anthropic" ? "sk-ant-api03-..." : "sk-..."}
                className="bg-secondary/50 font-mono text-sm flex-1"
              />
              <Button variant="outline" size="sm" onClick={() => setShowKey(!showKey)} className="shrink-0 text-xs">
                {showKey ? "Hide" : "Show"}
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground/60">
              Stored in localStorage only — never sent to EDON servers. Calls go directly to {provider === "anthropic" ? "api.anthropic.com" : "api.openai.com"}.
            </p>
          </div>

          {/* Model */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Model</Label>
            <div className="flex flex-wrap gap-2">
              {(provider === "anthropic" ? ANTHROPIC_MODELS : OPENAI_MODELS).map((m) => (
                <button
                  key={m}
                  onClick={() => setModel(m)}
                  className={`rounded-full border px-3 py-1 text-[11px] font-mono transition-colors ${
                    (model || defaultModel) === m
                      ? "border-[#64dc78]/40 bg-[#64dc78]/10 text-[#64dc78]"
                      : "border-white/10 bg-white/5 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {/* Context info */}
          <div className="rounded-xl border border-[#64dc78]/15 bg-[#64dc78]/5 p-4 space-y-2">
            <p className="text-xs font-medium text-[#64dc78]">What the LLM sees on every message</p>
            <ul className="space-y-1">
              {[
                "Live metrics: allowed / blocked / confirm counts (24h)",
                "Up to 20 recent decisions and 20 audit events",
                "Top block reasons with counts",
                "Active policy pack and all available packs",
                "Gateway health and uptime",
                "Team members and shared audit records",
                "Full multi-turn conversation history",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <span className="text-[#64dc78] mt-0.5 shrink-0">✓</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
          <p className="text-xs font-medium text-foreground">Using EDON Gateway as chat backend</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Messages are routed via your connected backend (configure in Integrations tab). Dashboard context is sent in the request args so your backend LLM can use it.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">Tool name</Label>
              <Input
                defaultValue={localStorage.getItem("edon_chat_tool") || "chat"}
                onBlur={(e) => localStorage.setItem("edon_chat_tool", e.target.value)}
                className="bg-secondary/50 font-mono text-xs h-8"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">Action</Label>
              <Input
                defaultValue={localStorage.getItem("edon_chat_action") || "json"}
                onBlur={(e) => localStorage.setItem("edon_chat_action", e.target.value)}
                className="bg-secondary/50 font-mono text-xs h-8"
              />
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <Button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 bg-[#64dc78]/15 border border-[#64dc78]/30 text-[#64dc78] hover:bg-[#64dc78]/25 hover:border-[#64dc78]/50"
        >
          {saving ? "Saving..." : <><Save className="w-3.5 h-3.5 mr-2" />Save Configuration</>}
        </Button>
        {provider !== "gateway" && apiKey && (
          <Button variant="outline" onClick={handleTest} className="shrink-0 text-xs">
            Test Chat
          </Button>
        )}
      </div>
    </div>
  );
}
