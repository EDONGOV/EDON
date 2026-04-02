// NOTE FOR APP.TSX: Add `/pilot` to the public paths list (alongside `/settings`, `/quickstart`, `/demo`)
// so clients can access this page without an existing token.
// Also add: import PilotKit from "./pages/PilotKit"; and <Route path="/pilot" element={<PilotKit />} />

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { edonApi, getBaseUrl } from "@/lib/api";
import { Link } from "react-router-dom";
import {
  Key, Copy, Check, Zap, Bot, Shield, Users,
  ChevronRight, Terminal, AlertTriangle, CheckCircle2,
  XCircle, HelpCircle, RefreshCw,
} from "lucide-react";

// ─── helpers ────────────────────────────────────────────────────────────────

function CopyButton({ text, size = "sm" }: { text: string; size?: "sm" | "xs" }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <button
      onClick={handle}
      className={`flex items-center gap-1 rounded-md border transition-colors ${
        size === "xs"
          ? "px-2 py-1 text-[10px]"
          : "px-2.5 py-1.5 text-xs"
      } ${
        copied
          ? "border-primary/40 bg-primary/10 text-primary"
          : "border-white/15 bg-white/5 text-muted-foreground hover:text-foreground hover:border-white/25"
      }`}
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function SectionLabel({ n, label }: { n: string; label: string }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <span className="font-mono text-[11px] text-primary/70 tracking-widest">{n}</span>
      <div className="h-px flex-1 bg-white/[0.06]" />
      <span className="text-xs font-medium tracking-widest uppercase text-muted-foreground/60">{label}</span>
    </div>
  );
}

// ─── code snippets ──────────────────────────────────────────────────────────

const makeSnippets = (gateway: string, token: string) => ({
  curl: `curl -X POST ${gateway}/v1/action \\
  -H "X-EDON-TOKEN: ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "action_type": "email.send",
    "agent_id":    "my-agent",
    "action_payload": {
      "to":      "user@example.com",
      "subject": "Hello from my agent"
    }
  }'`,

  python: `import httpx

EDON_GATEWAY = "${gateway}"
EDON_TOKEN   = "${token}"

response = httpx.post(
    f"{EDON_GATEWAY}/v1/action",
    headers={"X-EDON-TOKEN": EDON_TOKEN},
    json={
        "action_type": "email.send",
        "agent_id":    "my-agent",
        "action_payload": {
            "to":      "user@example.com",
            "subject": "Hello from my agent",
        },
    },
)

decision = response.json()
print(decision["verdict"])   # ALLOW | BLOCK | ESCALATE`,

  node: `import fetch from "node-fetch";   // or use native fetch in Node 18+

const EDON_GATEWAY = "${gateway}";
const EDON_TOKEN   = "${token}";

const res = await fetch(\`\${EDON_GATEWAY}/v1/action\`, {
  method:  "POST",
  headers: {
    "X-EDON-TOKEN": EDON_TOKEN,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    action_type: "email.send",
    agent_id:    "my-agent",
    action_payload: {
      to:      "user@example.com",
      subject: "Hello from my agent",
    },
  }),
});

const { verdict } = await res.json();
console.log(verdict); // ALLOW | BLOCK | ESCALATE`,
});

type Lang = "curl" | "python" | "node";

// ─── verdict display ─────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toUpperCase();
  if (v === "ALLOW" || v === "ALLOWED")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-sm font-mono font-medium text-emerald-400">
        <CheckCircle2 className="h-4 w-4" /> ALLOW
      </span>
    );
  if (v === "BLOCK" || v === "BLOCKED")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-sm font-mono font-medium text-red-400">
        <XCircle className="h-4 w-4" /> BLOCK
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-sm font-mono font-medium text-amber-400">
      <HelpCircle className="h-4 w-4" /> {v}
    </span>
  );
}

// ─── main page ───────────────────────────────────────────────────────────────

export default function PilotKit() {
  const { toast } = useToast();
  const gatewayUrl = getBaseUrl();

  // step 1 — key generation
  const [keyName, setKeyName]         = useState("pilot-agent");
  const [generating, setGenerating]   = useState(false);
  const [apiKey, setApiKey]           = useState<string | null>(null);
  const [keyPreview, setKeyPreview]   = useState<string | null>(null);
  const [keyCopied, setKeyCopied]     = useState(false);

  // step 3 — code tabs
  const [lang, setLang] = useState<Lang>("curl");

  // step 4 — live test
  const [testing, setTesting]     = useState(false);
  const [testResult, setTestResult] = useState<{ verdict: string; reason: string } | null>(null);

  // display token: real key if just generated, else placeholder
  const displayToken = apiKey ?? keyPreview ?? "<YOUR-EDON-TOKEN>";
  const snippets     = makeSnippets(gatewayUrl, displayToken);

  // try to load existing token from localStorage as a hint
  useEffect(() => {
    const stored = localStorage.getItem("edon_token") || localStorage.getItem("edon_api_key");
    if (stored && stored !== "demo") {
      setKeyPreview(stored.length > 12 ? stored.slice(0, 10) + "…" + stored.slice(-4) : stored);
    }
  }, []);

  const handleGenerate = async () => {
    if (!keyName.trim()) return;
    setGenerating(true);
    try {
      const result = await edonApi.createApiKey(keyName.trim());
      const raw = result?.api_key ?? null;
      if (raw) {
        setApiKey(raw);
        setKeyPreview(raw.slice(0, 10) + "…" + raw.slice(-4));
        toast({ title: "API key created", description: "Copy it now — it won't be shown again." });
      }
    } catch {
      // Gateway unreachable (demo mode or not connected) — show a placeholder
      const mock = `edon_sk_pilot_${Math.random().toString(36).slice(2, 14)}`;
      setApiKey(mock);
      setKeyPreview(mock.slice(0, 10) + "…" + mock.slice(-4));
      toast({ title: "Key generated (offline)", description: "Connect to your gateway to create a real key.", variant: "default" });
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyKey = () => {
    if (!apiKey) return;
    navigator.clipboard.writeText(apiKey).then(() => {
      setKeyCopied(true);
      setTimeout(() => setKeyCopied(false), 2000);
    });
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await edonApi.evaluateAction({
        action_type: "email.send",
        action_payload: { to: "test@example.com", subject: "Pilot test" },
      });
      setTestResult({
        verdict: res.decision || "UNKNOWN",
        reason: res.decision_reason || res.reason_code || "Policy evaluated.",
      });
    } catch (err) {
      setTestResult({
        verdict: "ERROR",
        reason: err instanceof Error ? err.message : "Request failed.",
      });
    } finally {
      setTesting(false);
    }
  };

  const testSuccess = testResult && testResult.verdict !== "ERROR";

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-10 space-y-10">

        {/* ── Hero ─────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <p className="text-xs font-medium uppercase tracking-[0.3em] text-primary/70 mb-2">
            Pilot Kit
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            You're ready to go live.
          </h1>
          <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
            Generate your API key, copy a code snippet, and send a test request — all in under two minutes.
          </p>
        </motion.div>

        {/* ── 01 · API Key ─────────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.07 }}
          className="glass-card p-6 space-y-5"
        >
          <SectionLabel n="01" label="API Key" />

          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Give your key a name — usually the project or agent it's for.
            </p>

            <div className="flex gap-2">
              <Input
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder="e.g. pilot-agent"
                disabled={!!apiKey}
                className="bg-black/20 border-white/10 font-mono text-sm flex-1"
                onKeyDown={(e) => e.key === "Enter" && !apiKey && handleGenerate()}
              />
              <Button
                onClick={handleGenerate}
                disabled={generating || !!apiKey || !keyName.trim()}
                className="gap-2 shrink-0"
              >
                {generating ? (
                  <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Generating…</>
                ) : apiKey ? (
                  <><Check className="h-3.5 w-3.5" /> Generated</>
                ) : (
                  <><Key className="h-3.5 w-3.5" /> Generate Key</>
                )}
              </Button>
            </div>
          </div>

          <AnimatePresence>
            {apiKey && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="space-y-3"
              >
                <div className="rounded-xl border border-amber-500/25 bg-amber-500/8 px-4 py-2.5 flex items-center gap-2">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                  <p className="text-xs text-amber-300/90">
                    Copy this key now — it won't be shown again after you leave this page.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-xs text-foreground/90 tracking-wider overflow-x-auto whitespace-nowrap">
                    {apiKey}
                  </div>
                  <button
                    onClick={handleCopyKey}
                    className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors shrink-0 ${
                      keyCopied
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-white/15 bg-white/5 text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {keyCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {keyCopied ? "Copied!" : "Copy"}
                  </button>
                </div>

                <p className="text-xs text-muted-foreground/60">
                  Manage and revoke keys any time from{" "}
                  <Link to="/api-keys" className="text-primary hover:underline">
                    API Keys →
                  </Link>
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.section>

        {/* ── 02 · Gateway Endpoint ────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.12 }}
          className="glass-card p-6 space-y-4"
        >
          <SectionLabel n="02" label="Gateway Endpoint" />

          <p className="text-sm text-muted-foreground">
            This is the base URL your agents send requests to. All governance decisions happen here.
          </p>

          <div className="flex items-center gap-2">
            <div className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm text-foreground/90 overflow-x-auto whitespace-nowrap">
              {gatewayUrl}
            </div>
            <CopyButton text={gatewayUrl} />
          </div>

          <div className="grid grid-cols-2 gap-3 pt-1">
            {[
              { path: "/v1/action",     desc: "Evaluate an action" },
              { path: "/health",        desc: "Gateway health check" },
              { path: "/audit/query",   desc: "Query decision history" },
              { path: "/policy-packs",  desc: "List policy packs" },
            ].map(({ path, desc }) => (
              <div
                key={path}
                className="rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2.5 flex flex-col gap-0.5"
              >
                <span className="font-mono text-xs text-primary/80">{path}</span>
                <span className="text-[11px] text-muted-foreground/70">{desc}</span>
              </div>
            ))}
          </div>
        </motion.section>

        {/* ── 03 · Code Snippets ───────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.17 }}
          className="glass-card p-6 space-y-4"
        >
          <SectionLabel n="03" label="Quick Start Code" />

          <p className="text-sm text-muted-foreground">
            Drop this into your agent to start governing actions immediately.
            {!apiKey && (
              <span className="text-amber-400/80"> Generate a key above to see your credentials substituted in.</span>
            )}
          </p>

          {/* Language tabs */}
          <div className="flex gap-1 border-b border-white/8 pb-0">
            {(["curl", "python", "node"] as Lang[]).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-3 py-2 text-xs font-mono font-medium transition-colors rounded-t-md -mb-px border-b-2 ${
                  lang === l
                    ? "text-primary border-primary bg-primary/5"
                    : "text-muted-foreground border-transparent hover:text-foreground"
                }`}
              >
                {l === "node" ? "node.js" : l}
              </button>
            ))}
            <div className="flex-1" />
            <div className="flex items-center pb-1">
              <CopyButton text={snippets[lang]} size="xs" />
            </div>
          </div>

          <div className="relative">
            <AnimatePresence mode="wait">
              <motion.pre
                key={lang}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="bg-black/40 rounded-xl p-4 font-mono text-xs text-foreground/80 overflow-x-auto leading-relaxed"
              >
                {snippets[lang]}
              </motion.pre>
            </AnimatePresence>
          </div>
        </motion.section>

        {/* ── 04 · Live Test ───────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.22 }}
          className="glass-card p-6 space-y-4"
        >
          <SectionLabel n="04" label="Live Test" />

          <p className="text-sm text-muted-foreground">
            Send a real governance request through your gateway. You'll see the verdict instantly.
          </p>

          <div className="rounded-lg border border-white/8 bg-black/20 px-4 py-3 font-mono text-xs text-muted-foreground space-y-1">
            <div><span className="text-primary/70">POST</span> {gatewayUrl}/v1/action</div>
            <div className="text-foreground/40">{"{ action_type: \"email.send\", to: \"test@example.com\" }"}</div>
          </div>

          <Button
            onClick={handleTest}
            disabled={testing}
            className="gap-2 w-full sm:w-auto"
            variant={testSuccess ? "outline" : "default"}
          >
            {testing ? (
              <><RefreshCw className="h-4 w-4 animate-spin" /> Sending request…</>
            ) : testSuccess ? (
              <><RefreshCw className="h-4 w-4" /> Run again</>
            ) : (
              <><Zap className="h-4 w-4" /> Send test request</>
            )}
          </Button>

          <AnimatePresence>
            {testResult && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                className={`rounded-xl border p-4 space-y-2 ${
                  testResult.verdict === "ERROR"
                    ? "border-red-500/20 bg-red-500/5"
                    : "border-white/10 bg-white/[0.02]"
                }`}
              >
                <div className="flex items-center gap-3">
                  {testResult.verdict === "ERROR" ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-sm font-mono font-medium text-red-400">
                      <XCircle className="h-4 w-4" /> ERROR
                    </span>
                  ) : (
                    <VerdictBadge verdict={testResult.verdict} />
                  )}
                  <span className="text-xs text-muted-foreground">Decision received</span>
                </div>
                <p className="text-sm text-foreground/70">{testResult.reason}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.section>

        {/* ── What's Next (after successful test) ─────────────── */}
        <AnimatePresence>
          {testSuccess && (
            <motion.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-white/[0.06]" />
                <span className="text-xs uppercase tracking-widest text-muted-foreground/50 font-medium">
                  What's next
                </span>
                <div className="h-px flex-1 bg-white/[0.06]" />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  {
                    icon: Bot,
                    title: "Register your agent",
                    desc: "Add your AI system to the agent fleet so its activity is tracked individually.",
                    to: "/agents",
                    color: "text-sky-400",
                    bg: "bg-sky-500/10 border-sky-500/20",
                  },
                  {
                    icon: Shield,
                    title: "Apply a policy",
                    desc: "Choose how strictly EDON governs actions — Safe, Business, or Autonomy mode.",
                    to: "/policies",
                    color: "text-primary",
                    bg: "bg-primary/10 border-primary/20",
                  },
                  {
                    icon: Users,
                    title: "Invite your team",
                    desc: "Add colleagues so they can review escalations and monitor agent activity.",
                    to: "/team",
                    color: "text-violet-400",
                    bg: "bg-violet-500/10 border-violet-500/20",
                  },
                ].map(({ icon: Icon, title, desc, to, color, bg }) => (
                  <Link key={to} to={to} className="group block">
                    <div className="glass-card p-5 h-full transition-all group-hover:border-white/20">
                      <div className={`w-9 h-9 rounded-xl border ${bg} flex items-center justify-center mb-3`}>
                        <Icon className={`h-4 w-4 ${color}`} />
                      </div>
                      <p className="text-sm font-medium mb-1">{title}</p>
                      <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
                      <div className={`flex items-center gap-1 mt-3 text-xs ${color} opacity-0 group-hover:opacity-100 transition-opacity`}>
                        Go <ChevronRight className="h-3 w-3" />
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        {/* ── Footer ───────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="flex items-center justify-between pt-4 border-t border-white/[0.06] text-xs text-muted-foreground/50"
        >
          <span>EDON Governance Console</span>
          <div className="flex items-center gap-1">
            <Terminal className="h-3 w-3" />
            <span className="font-mono">{gatewayUrl.replace("https://", "").replace("http://", "")}</span>
          </div>
        </motion.div>

      </main>
    </div>
  );
}
