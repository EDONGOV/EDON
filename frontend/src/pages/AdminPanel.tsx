import { useState } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { edonApi } from "@/lib/api";
import { isAdmin, PROFILES } from "@/lib/workspaceProfile";
import { Link } from "react-router-dom";
import {
  Crown, ShieldAlert, Users, Activity, AlertTriangle,
  CheckCircle2, Clock, TrendingUp, Zap, MessageSquare,
  RefreshCw, Send, ExternalLink, Info, Key, Copy, Check,
  Eye, EyeOff, UserPlus,
} from "lucide-react";
import { getBaseUrl } from "@/lib/api";

// ─── Mock data ──────────────────────────────────────────────────────────────

const MOCK_CUSTOMERS = [
  {
    id: "tenant_001", name: "Acme Corp", email: "ops@acme.com",
    profile: "ai_agents", plan: "professional",
    agents: 12, decisions_24h: 2847, blocked_24h: 23,
    last_seen: "2 min ago", status: "healthy",
  },
  {
    id: "tenant_002", name: "RoboLogix", email: "admin@robologix.io",
    profile: "industrial", plan: "enterprise",
    agents: 4, decisions_24h: 891, blocked_24h: 7,
    last_seen: "8 min ago", status: "healthy",
  },
  {
    id: "tenant_003", name: "SkyDrone Co", email: "cto@skydrone.ai",
    profile: "drones", plan: "starter",
    agents: 18, decisions_24h: 5621, blocked_24h: 145,
    last_seen: "1h ago", status: "warning",
  },
  {
    id: "tenant_004", name: "MedNano Labs", email: "dev@mednano.com",
    profile: "medical", plan: "enterprise",
    agents: 3, decisions_24h: 312, blocked_24h: 0,
    last_seen: "Just now", status: "healthy",
  },
  {
    id: "tenant_005", name: "BuiltBot Inc", email: "admin@builtbot.com",
    profile: "humanoids", plan: "professional",
    agents: 6, decisions_24h: 1203, blocked_24h: 89,
    last_seen: "3h ago", status: "warning",
  },
];

const MOCK_FLAGS = [
  {
    id: "flag_001", tenant: "SkyDrone Co", type: "high_block_rate",
    message: "Block rate above 2% for 30 min", severity: "warning", time: "45 min ago",
  },
  {
    id: "flag_002", tenant: "BuiltBot Inc", type: "no_activity",
    message: "No decisions in 3 hours", severity: "info", time: "3h ago",
  },
  {
    id: "flag_003", tenant: "Acme Corp", type: "policy_override",
    message: "Manual policy override by admin", severity: "info", time: "Yesterday",
  },
];

const PLATFORM_STATS = [
  { label: "Total Tenants", value: "5", icon: Users, color: "sky" },
  { label: "Decisions Today", value: "10,874", icon: Activity, color: "emerald" },
  { label: "Avg Block Rate", value: "1.2%", icon: TrendingUp, color: "amber" },
  { label: "Active Swarms", value: "3", icon: Zap, color: "violet" },
];

const PROFILE_ICONS: Record<string, string> = {
  ai_agents: "🤖", industrial: "🏭", drones: "🚁",
  humanoids: "🦾", medical: "💊", multi: "⚙️",
};

const PLAN_COLOR: Record<string, string> = {
  starter: "border-white/20 text-muted-foreground",
  professional: "border-sky-500/30 text-sky-400 bg-sky-500/10",
  enterprise: "border-violet-500/30 text-violet-400 bg-violet-500/10",
};

const STAT_COLOR: Record<string, string> = {
  sky: "text-sky-400 bg-sky-500/10",
  emerald: "text-emerald-400 bg-emerald-500/10",
  amber: "text-amber-400 bg-amber-500/10",
  violet: "text-violet-400 bg-violet-500/10",
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function AdminPanel() {
  const { toast } = useToast();
  const admin = isAdmin();

  // Quick actions state
  const [healthResult, setHealthResult] = useState<string | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [broadcastMsg, setBroadcastMsg] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteProfile, setInviteProfile] = useState("");
  const [inviting, setInviting] = useState(false);

  // Pilot client provisioning
  const [bootstrapSecret, setBootstrapSecret] = useState(
    () => sessionStorage.getItem("edon_bs") ?? ""
  );
  const [showSecret, setShowSecret] = useState(false);
  const [provCompany, setProvCompany] = useState("");
  const [provEmail, setProvEmail]     = useState("");
  const [provPlan, setProvPlan]       = useState<"starter" | "pro" | "enterprise">("starter");
  const [provisioning, setProvisioning] = useState(false);
  const [provResult, setProvResult] = useState<{
    token: string; tenantId: string; magicLink: string; status: string;
  } | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyField = (text: string, field: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 1800);
    });
  };

  const generateToken = () => {
    const arr = new Uint8Array(24);
    crypto.getRandomValues(arr);
    return "edon_sk_" + Array.from(arr).map((b) => b.toString(16).padStart(2, "0")).join("");
  };

  const toTenantId = (name: string) =>
    name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") +
    "-" + Math.random().toString(36).slice(2, 6);

  const handleProvision = async () => {
    if (!bootstrapSecret.trim() || !provCompany.trim() || !provEmail.trim()) {
      toast({ title: "Fill in all fields", variant: "destructive" });
      return;
    }
    sessionStorage.setItem("edon_bs", bootstrapSecret);
    setProvisioning(true);
    setProvResult(null);

    const token    = generateToken();
    const tenantId = toTenantId(provCompany);
    const gateway  = getBaseUrl();

    try {
      const res = await edonApi.provisionClient({
        bootstrapSecret: bootstrapSecret.trim(),
        token,
        tenantId,
        name:  `${provCompany} — pilot`,
        email: provEmail.trim(),
        plan:  provPlan,
      });
      const magicLink = `${window.location.origin}/pilot#token=${token}&base=${encodeURIComponent(gateway)}`;
      setProvResult({ token, tenantId: res.tenant_id, magicLink, status: res.status });
      toast({ title: res.status === "created" ? "Client provisioned" : "Already exists", description: res.message });
      setProvCompany("");
      setProvEmail("");
    } catch (err) {
      toast({
        title: "Provisioning failed",
        description: err instanceof Error ? err.message : "Check your bootstrap secret and gateway connection.",
        variant: "destructive",
      });
    } finally {
      setProvisioning(false);
    }
  };

  // Access denied
  if (!admin) {
    return (
      <div className="min-h-screen">
        <TopNav />
        <main className="container mx-auto px-6 py-24 max-w-md text-center">
          <div className="flex justify-center mb-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 border border-red-500/20">
              <ShieldAlert className="h-8 w-8 text-red-400" />
            </div>
          </div>
          <h1 className="text-xl font-semibold mb-2">Access Denied</h1>
          <p className="text-sm text-muted-foreground mb-6">
            This panel is only accessible to EDON team members.
          </p>
          <Link to="/">
            <Button variant="outline">Back to Dashboard</Button>
          </Link>
        </main>
      </div>
    );
  }

  const handleCheckHealth = async () => {
    setCheckingHealth(true);
    setHealthResult(null);
    try {
      const h = await edonApi.getHealth();
      const status = (h as { status?: string })?.status || "ok";
      setHealthResult(`✅ Gateway status: ${status}`);
    } catch {
      setHealthResult("❌ Could not reach gateway");
    } finally {
      setCheckingHealth(false);
    }
  };

  const handleBroadcast = () => {
    if (!broadcastMsg.trim()) return;
    toast({ title: "Notification sent", description: `"${broadcastMsg}" broadcast to all tenants.` });
    setBroadcastMsg("");
  };

  const handleInvite = () => {
    if (!inviteEmail.trim() || !inviteProfile) {
      toast({ title: "Fill in all fields", variant: "destructive" });
      return;
    }
    setInviting(true);
    setTimeout(() => {
      setInviting(false);
      toast({ title: "Invitation sent", description: `${inviteEmail} invited as ${inviteProfile} customer.` });
      setInviteEmail("");
      setInviteProfile("");
    }, 800);
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-5xl space-y-8">

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/15">
              <Crown className="h-5 w-5 text-amber-400" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold">Admin Panel</h1>
              <p className="text-xs text-muted-foreground">EDON team view — customer support & oversight</p>
            </div>
          </div>

          {/* Warning banner */}
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/8 px-4 py-3">
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-300/80">
              This view is only accessible to <code className="font-mono bg-white/10 px-1 rounded">@edoncore.com</code> accounts.
              Customer data shown here is for support purposes only.
            </p>
          </div>
        </motion.div>

        {/* Platform stats */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-3"
        >
          {PLATFORM_STATS.map((stat) => {
            const Icon = stat.icon;
            const colorClass = STAT_COLOR[stat.color] || STAT_COLOR["sky"];
            return (
              <div key={stat.label} className="glass-card p-4">
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg mb-3 ${colorClass}`}>
                  <Icon className="h-4 w-4" />
                </div>
                <p className="text-2xl font-semibold">{stat.value}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{stat.label}</p>
              </div>
            );
          })}
        </motion.div>

        {/* Customer table */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Customers</h2>
              <p className="text-xs text-muted-foreground mt-0.5">{MOCK_CUSTOMERS.length} active tenants</p>
            </div>
            <Dialog>
              <DialogTrigger asChild>
                <Button size="sm" className="gap-1.5">
                  <Users className="h-3.5 w-3.5" /> Invite Customer
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-[#0f1117] border border-white/10">
                <DialogHeader>
                  <DialogTitle>Invite a Customer</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Email</Label>
                    <Input
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      placeholder="ops@company.com"
                      className="bg-secondary/50"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Use Case Profile</Label>
                    <Select value={inviteProfile} onValueChange={setInviteProfile}>
                      <SelectTrigger className="bg-secondary/50">
                        <SelectValue placeholder="Select profile…" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0f1117] border border-white/10">
                        {PROFILES.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.icon} {p.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    className="w-full gap-2"
                    onClick={handleInvite}
                    disabled={inviting}
                  >
                    {inviting ? (
                      <><div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sending…</>
                    ) : (
                      <><Send className="h-3.5 w-3.5" /> Send Invitation</>
                    )}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/8">
                  {["Company", "Profile", "Plan", "Agents", "Decisions (24h)", "Blocked", "Last Active", "Status", ""].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MOCK_CUSTOMERS.map((c, i) => (
                  <tr
                    key={c.id}
                    className={`border-b border-white/5 hover:bg-white/3 transition-colors ${
                      i === MOCK_CUSTOMERS.length - 1 ? "border-none" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground/90">{c.name}</p>
                      <p className="text-xs text-muted-foreground">{c.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-base">{PROFILE_ICONS[c.profile] || "⚙️"}</span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={`text-[10px] capitalize ${PLAN_COLOR[c.plan] || ""}`}>
                        {c.plan}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{c.agents}</td>
                    <td className="px-4 py-3 text-muted-foreground">{c.decisions_24h.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <span className={c.blocked_24h > 50 ? "text-amber-400" : "text-muted-foreground"}>
                        {c.blocked_24h}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {c.last_seen}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {c.status === "healthy" ? (
                        <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-400 bg-emerald-500/10 gap-1">
                          <CheckCircle2 className="h-2.5 w-2.5" /> Healthy
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400 bg-amber-500/10 gap-1">
                          <AlertTriangle className="h-2.5 w-2.5" /> Warning
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground" disabled>
                          <ExternalLink className="h-3 w-3" /> View
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground"
                          onClick={() => toast({ title: `Support: ${c.name}`, description: "Opening support thread…" })}>
                          <MessageSquare className="h-3 w-3" /> Support
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>

        {/* ── Provision Pilot Client ─────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12 }}
          className="glass-card"
        >
          <div className="px-5 py-4 border-b border-white/10 flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <UserPlus className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h2 className="font-semibold">Provision Pilot Client</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Creates an isolated tenant + API key. Send the client the magic link to get them live.
              </p>
            </div>
          </div>

          <div className="p-5 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

              {/* Bootstrap secret */}
              <div className="md:col-span-2 space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  Bootstrap Secret
                  <span className="ml-2 text-muted-foreground/50">(stored in session only — clears when you close the tab)</span>
                </Label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Input
                      type={showSecret ? "text" : "password"}
                      value={bootstrapSecret}
                      onChange={(e) => setBootstrapSecret(e.target.value)}
                      placeholder="EDON_BOOTSTRAP_SECRET value"
                      className="bg-black/20 border-white/10 pr-9 font-mono text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showSecret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Company name */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Company Name</Label>
                <Input
                  value={provCompany}
                  onChange={(e) => setProvCompany(e.target.value)}
                  placeholder="Acme Corp"
                  className="bg-black/20 border-white/10"
                />
              </div>

              {/* Email */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Contact Email</Label>
                <Input
                  value={provEmail}
                  onChange={(e) => setProvEmail(e.target.value)}
                  placeholder="ops@acme.com"
                  className="bg-black/20 border-white/10"
                  type="email"
                />
              </div>

              {/* Plan */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Plan</Label>
                <Select value={provPlan} onValueChange={(v) => setProvPlan(v as typeof provPlan)}>
                  <SelectTrigger className="bg-black/20 border-white/10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#0f1117] border border-white/10">
                    <SelectItem value="starter">Starter</SelectItem>
                    <SelectItem value="pro">Pro</SelectItem>
                    <SelectItem value="enterprise">Enterprise</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Submit */}
              <div className="flex items-end">
                <Button
                  onClick={handleProvision}
                  disabled={provisioning || !bootstrapSecret.trim() || !provCompany.trim() || !provEmail.trim()}
                  className="gap-2 w-full"
                >
                  {provisioning ? (
                    <><div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" /> Provisioning…</>
                  ) : (
                    <><Key className="h-3.5 w-3.5" /> Provision Client</>
                  )}
                </Button>
              </div>
            </div>

            {/* Result */}
            {provResult && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3"
              >
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
                  <p className="text-sm font-medium text-primary">
                    {provResult.status === "created" ? "Client provisioned successfully" : "Tenant already exists — key returned"}
                  </p>
                </div>

                <div className="space-y-2 text-xs">
                  <p className="text-muted-foreground/60 uppercase tracking-widest">Tenant ID</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 font-mono bg-black/30 rounded px-2 py-1.5 text-foreground/80 overflow-x-auto whitespace-nowrap">
                      {provResult.tenantId}
                    </code>
                  </div>

                  <p className="text-muted-foreground/60 uppercase tracking-widest pt-1">API Key
                    <span className="ml-2 text-amber-400/70 normal-case tracking-normal">— copy now, not stored</span>
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 font-mono bg-black/30 rounded px-2 py-1.5 text-foreground/80 overflow-x-auto whitespace-nowrap">
                      {provResult.token}
                    </code>
                    <button
                      onClick={() => copyField(provResult.token, "token")}
                      className={`flex items-center gap-1 rounded border px-2 py-1.5 transition-colors shrink-0 ${
                        copiedField === "token"
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-white/15 bg-white/5 text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {copiedField === "token" ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    </button>
                  </div>

                  <p className="text-muted-foreground/60 uppercase tracking-widest pt-1">Magic Link
                    <span className="ml-2 text-muted-foreground/40 normal-case tracking-normal">— send this to the client</span>
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 font-mono bg-black/30 rounded px-2 py-1.5 text-foreground/80 overflow-x-auto whitespace-nowrap text-[11px]">
                      {provResult.magicLink}
                    </code>
                    <button
                      onClick={() => copyField(provResult.magicLink, "link")}
                      className={`flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs transition-colors shrink-0 ${
                        copiedField === "link"
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-white/15 bg-white/5 text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {copiedField === "link" ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedField === "link" ? "Copied" : "Copy link"}
                    </button>
                  </div>
                  <p className="text-muted-foreground/40 pt-1">
                    Client clicks the link → lands on their console → runs a test → they're live.
                  </p>
                </div>
              </motion.div>
            )}
          </div>
        </motion.div>

        {/* Support flags + Quick actions row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Support flags */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="glass-card"
          >
            <div className="px-5 py-4 border-b border-white/10">
              <h2 className="font-semibold">Support Flags</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Automated signals worth checking</p>
            </div>
            <div className="divide-y divide-white/5">
              {MOCK_FLAGS.map((flag) => (
                <div key={flag.id} className="px-5 py-3 flex items-start gap-3">
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5 ${
                    flag.severity === "warning"
                      ? "bg-amber-500/15"
                      : "bg-sky-500/15"
                  }`}>
                    {flag.severity === "warning"
                      ? <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                      : <Info className="h-3.5 w-3.5 text-sky-400" />
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-foreground/90">{flag.tenant}</p>
                      <p className="text-[10px] text-muted-foreground shrink-0">{flag.time}</p>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{flag.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Quick actions */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card"
          >
            <div className="px-5 py-4 border-b border-white/10">
              <h2 className="font-semibold">Quick Actions</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Common support operations</p>
            </div>
            <div className="p-5 space-y-4">

              {/* Gateway health */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Gateway Health</p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={handleCheckHealth}
                    disabled={checkingHealth}
                  >
                    {checkingHealth
                      ? <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Checking…</>
                      : <><RefreshCw className="h-3 w-3" /> Check Gateway</>
                    }
                  </Button>
                  {healthResult && (
                    <p className="text-xs text-muted-foreground">{healthResult}</p>
                  )}
                </div>
              </div>

              {/* View audit */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">All Audit Logs</p>
                <Link to="/audit">
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <ExternalLink className="h-3 w-3" /> Open Audit Trail
                  </Button>
                </Link>
              </div>

              {/* Broadcast */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Broadcast Notification</p>
                <div className="flex items-center gap-2">
                  <Input
                    value={broadcastMsg}
                    onChange={(e) => setBroadcastMsg(e.target.value)}
                    placeholder="Message to all tenants…"
                    className="bg-secondary/50 h-8 text-xs flex-1"
                    onKeyDown={(e) => e.key === "Enter" && handleBroadcast()}
                  />
                  <Button
                    size="sm"
                    className="gap-1 shrink-0"
                    onClick={handleBroadcast}
                    disabled={!broadcastMsg.trim()}
                  >
                    <Send className="h-3 w-3" /> Send
                  </Button>
                </div>
              </div>

            </div>
          </motion.div>
        </div>

      </main>
    </div>
  );
}
