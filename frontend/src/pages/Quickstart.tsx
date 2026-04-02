import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { edonApi } from "@/lib/api";
import {
  Check, Copy, ChevronRight, ChevronLeft, Globe, Shield, Zap, Bot, Lock,
  Eye, EyeOff, AlertTriangle, X,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { PROFILES, ProfileId, initWorkspace } from "@/lib/workspaceProfile";

const TOTAL_STEPS = 5; // Step 0: Use Case + original 4 steps

interface PolicyOption {
  name: string;
  packName: string;
  description: string;
  riskLevel: "low" | "medium" | "high";
  riskColor: string;
  icon: typeof Shield;
  bullets: string[];
}

const POLICY_OPTIONS: PolicyOption[] = [
  {
    name: "Safe Mode",
    packName: "personal_safe",
    description: "Conservative governance. High-risk actions blocked automatically before they run.",
    riskLevel: "low",
    riskColor: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    icon: Lock,
    bullets: [
      "Blocks high-impact actions by default",
      "Escalates on policy violations",
      "Best starting point for new deployments",
    ],
  },
  {
    name: "Business Mode",
    packName: "work_safe",
    description: "Business workflows run freely. Sensitive actions require explicit approval.",
    riskLevel: "medium",
    riskColor: "text-sky-400 border-sky-500/30 bg-sky-500/10",
    icon: Shield,
    bullets: [
      "Finance and data actions need approval",
      "Full audit trail for compliance",
      "Built for ops teams and enterprises",
    ],
  },
  {
    name: "Founder Mode",
    packName: "founder_mode",
    description: "Full access minus destructive bulk operations. Move fast, stay safe.",
    riskLevel: "high",
    riskColor: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    icon: Zap,
    bullets: [
      "Nearly all tools enabled",
      "Blocks system.admin and bulk deletes",
      "For trusted operators with full context",
    ],
  },
  {
    name: "Autonomy Mode",
    packName: "autonomy_mode",
    description: "Agent operates continuously. Only critical violations surface.",
    riskLevel: "high",
    riskColor: "text-red-400 border-red-500/30 bg-red-500/10",
    icon: Bot,
    bullets: [
      "All tools enabled",
      "Silent by design — minimal interruptions",
      "For 24/7 always-on pipelines",
    ],
  },
];

const CODE_SNIPPET = `POST https://gateway.edoncore.com/clawdbot/invoke
X-EDON-TOKEN: <your-token>
Content-Type: application/json

{
  "tool": "email",
  "action": "send",
  "args": {
    "to": "user@example.com",
    "subject": "Hello from your agent"
  }
}`;

export default function Quickstart() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [step, setStep] = useState(0); // Start at step 0: use-case picker

  // Step 0: Use case
  const [selectedProfile, setSelectedProfile] = useState<ProfileId | null>(null);

  // Step 1
  const [backendUrl, setBackendUrl] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [probeConnection, setProbeConnection] = useState(true);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<"ok" | "fail" | null>(null);

  // Step 2
  const [selectedPack, setSelectedPack] = useState<string | null>(null);
  const [applyingPack, setApplyingPack] = useState(false);
  const [packApplied, setPackApplied] = useState(false);

  // Step 3
  const [edonToken, setEdonToken] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);

  // Step 4
  const [testingFlow, setTestingFlow] = useState(false);
  const [testResult, setTestResult] = useState<{
    verdict: string;
    reason: string;
  } | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("edon_token") || "";
    setEdonToken(stored);
  }, []);

  const handleTestConnection = async () => {
    if (!backendUrl.trim()) {
      toast({ title: "Backend URL required", description: "Enter your agent backend URL first.", variant: "destructive" });
      return;
    }
    setTestingConnection(true);
    setConnectionResult(null);
    try {
      await edonApi.connectClawdbot({
        base_url: backendUrl.trim(),
        secret: authToken.trim(),
        auth_mode: "token",
        credential_id: "agent_gateway",
        probe: probeConnection,
      });
      setConnectionResult("ok");
      toast({ title: "Connection successful", description: "EDON can reach your backend." });
    } catch {
      setConnectionResult("fail");
      toast({ title: "Connection failed", description: "Could not reach your backend. Check the URL and token.", variant: "destructive" });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleApplyPolicy = async () => {
    if (!selectedPack) {
      toast({ title: "Select a policy", description: "Choose a governance mode first.", variant: "destructive" });
      return;
    }
    setApplyingPack(true);
    try {
      await edonApi.applyPolicyPack(selectedPack);
      setPackApplied(true);
      localStorage.setItem("edon_active_policy_pack", selectedPack);
      toast({ title: "Policy applied", description: `${selectedPack} is now active.` });
    } catch (err: unknown) {
      toast({
        title: "Failed to apply policy",
        description: err instanceof Error ? err.message : "Could not apply policy.",
        variant: "destructive",
      });
    } finally {
      setApplyingPack(false);
    }
  };

  const copyToken = async () => {
    if (!edonToken) {
      toast({ title: "No token found", description: "Go to Settings to configure your access key.", variant: "destructive" });
      return;
    }
    try {
      await navigator.clipboard.writeText(edonToken);
      toast({ title: "Copied", description: "Token copied to clipboard." });
    } catch {
      toast({ title: "Copy failed", description: "Clipboard access blocked.", variant: "destructive" });
    }
  };

  const handleTestFlow = async () => {
    setTestingFlow(true);
    setTestResult(null);
    try {
      const res = await edonApi.evaluateAction({
        action_type: "email.send",
        action_payload: { to: "test@example.com", subject: "Onboarding test" },
      });
      setTestResult({
        verdict: res.decision || "UNKNOWN",
        reason: res.decision_reason || res.reason_code || "Policy evaluated.",
      });
    } catch (err: unknown) {
      setTestResult({
        verdict: "ERROR",
        reason: err instanceof Error ? err.message : "Test request failed.",
      });
    } finally {
      setTestingFlow(false);
    }
  };

  const canProceed = () => {
    if (step === 0) return selectedProfile !== null;
    if (step === 1) return true; // can always skip
    if (step === 2) return selectedPack !== null;
    if (step === 3) return true;
    return true;
  };

  const nextStep = () => {
    if (step === 0 && selectedProfile) {
      initWorkspace(selectedProfile);
      window.dispatchEvent(new Event("edon-profile-updated"));
    }
    if (step < TOTAL_STEPS - 1) setStep((s) => s + 1);
  };
  const prevStep = () => {
    if (step > 0) setStep((s) => s - 1);
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-2xl">

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">B2B Onboarding</p>
            <h1 className="text-2xl font-semibold mt-1">Set up EDON</h1>
          </div>
          <Link
            to="/"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip setup →
          </Link>
        </div>

        {/* Progress */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-muted-foreground">Step {step + 1} of {TOTAL_STEPS}</p>
            <p className="text-xs text-muted-foreground">{Math.round(((step + 1) / TOTAL_STEPS) * 100)}% complete</p>
          </div>
          <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-primary rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${((step + 1) / TOTAL_STEPS) * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
          <div className="flex justify-between mt-3">
            {["Use Case", "Connect Backend", "Choose Policy", "Your Token", "Test Flow"].map((label, i) => (
              <button
                key={i}
                type="button"
                onClick={() => { if (i <= step) setStep(i); }}
                className={`text-xs transition-colors ${
                  step === i
                    ? "text-primary font-medium"
                    : step > i
                    ? "text-foreground/60"
                    : "text-muted-foreground/40"
                }`}
              >
                {step > i ? <span className="inline-flex items-center gap-1"><Check className="h-3 w-3 text-primary" />{label}</span> : label}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
          >

            {/* ── STEP 0: Use Case Picker ─────────────── */}
            {step === 0 && (
              <div className="space-y-5">
                <div className="glass-card p-6">
                  <h2 className="text-lg font-semibold mb-1">What are you governing?</h2>
                  <p className="text-sm text-muted-foreground">
                    We'll tailor your dashboard to show only what's relevant. You can always add more later.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  {PROFILES.map((profile) => {
                    const isSelected = selectedProfile === profile.id;
                    return (
                      <button
                        key={profile.id}
                        type="button"
                        onClick={() => setSelectedProfile(profile.id)}
                        className={`w-full text-left rounded-xl border px-5 py-4 transition-all ${
                          isSelected
                            ? "border-primary/50 bg-primary/10 ring-1 ring-primary/30"
                            : "border-white/10 bg-white/5 hover:bg-white/10"
                        }`}
                      >
                        <div className="flex items-start gap-4">
                          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-2xl ${
                            isSelected ? "bg-primary/20" : "bg-white/10"
                          }`}>
                            {profile.icon}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <p className="font-semibold">{profile.label}</p>
                              {isSelected && (
                                <Badge className="bg-primary/20 text-primary border-primary/30 text-[10px] ml-auto">
                                  <Check className="h-2.5 w-2.5 mr-1" /> Selected
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground">{profile.tagline}</p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>

                <p className="text-xs text-center text-muted-foreground">
                  Not sure? Pick <strong>AI Agents</strong> — it's the simplest starting point.
                </p>
              </div>
            )}

            {/* ── STEP 1: Connect Backend ─────────────── */}
            {step === 1 && (
              <div className="glass-card p-6 space-y-5">
                <div>
                  <h2 className="text-lg font-semibold mb-1">Connect your agent backend</h2>
                  <p className="text-sm text-muted-foreground">
                    EDON sits between your agent and your backend. Point us at your backend URL so we can govern and proxy requests.
                  </p>
                </div>

                <div className="space-y-4">
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Backend URL</Label>
                    <div className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
                      <Input
                        value={backendUrl}
                        onChange={(e) => { setBackendUrl(e.target.value); setConnectionResult(null); }}
                        placeholder="https://your-agent-backend.example.com"
                        className="bg-secondary/50"
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">Auth Token <span className="text-muted-foreground/50">(optional)</span></Label>
                    <Input
                      type="password"
                      value={authToken}
                      onChange={(e) => setAuthToken(e.target.value)}
                      placeholder="Bearer token for your backend"
                      className="bg-secondary/50"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="probe"
                      checked={probeConnection}
                      onCheckedChange={(v) => setProbeConnection(!!v)}
                    />
                    <Label htmlFor="probe" className="text-sm cursor-pointer">Probe connection before saving</Label>
                  </div>
                </div>

                {connectionResult === "ok" && (
                  <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400">
                    <Check className="h-4 w-4 shrink-0" /> Connection successful
                  </div>
                )}
                {connectionResult === "fail" && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                    <X className="h-4 w-4 shrink-0" /> Connection failed — check URL and token
                  </div>
                )}

                <div className="flex items-center gap-3 pt-1">
                  <Button
                    onClick={handleTestConnection}
                    variant="outline"
                    disabled={testingConnection || !backendUrl.trim()}
                    className="gap-2"
                  >
                    {testingConnection ? (
                      <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> Testing…</>
                    ) : (
                      "Test Connection"
                    )}
                  </Button>
                  <button
                    type="button"
                    onClick={nextStep}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    I'll set this up later →
                  </button>
                </div>
              </div>
            )}

            {/* ── STEP 2: Choose Policy ─────────────── */}
            {step === 2 && (
              <div className="space-y-5">
                <div className="glass-card p-6">
                  <h2 className="text-lg font-semibold mb-1">Set your governance policy</h2>
                  <p className="text-sm text-muted-foreground">
                    Choose how strictly EDON governs your agent's actions. You can change this any time.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  {POLICY_OPTIONS.map((opt) => {
                    const Icon = opt.icon;
                    const isSelected = selectedPack === opt.packName;
                    return (
                      <button
                        key={opt.packName}
                        type="button"
                        onClick={() => { setSelectedPack(opt.packName); setPackApplied(false); }}
                        className={`w-full text-left rounded-xl border px-5 py-4 transition-all ${
                          isSelected
                            ? "border-primary/50 bg-primary/10 ring-1 ring-primary/30"
                            : "border-white/10 bg-white/5 hover:bg-white/10"
                        }`}
                      >
                        <div className="flex items-start gap-4">
                          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                            isSelected ? "bg-primary/20" : "bg-white/10"
                          }`}>
                            <Icon className={`h-5 w-5 ${isSelected ? "text-primary" : "text-foreground/80"}`} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <p className="font-semibold">{opt.name}</p>
                              <Badge variant="outline" className={`text-[10px] ${opt.riskColor}`}>
                                {opt.riskLevel} risk
                              </Badge>
                              {isSelected && (
                                <Badge className="bg-primary/20 text-primary border-primary/30 text-[10px] ml-auto">
                                  <Check className="h-2.5 w-2.5 mr-1" /> Selected
                                </Badge>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground mb-2">{opt.description}</p>
                            <ul className="space-y-0.5">
                              {opt.bullets.map((b) => (
                                <li key={b} className="text-xs text-muted-foreground flex items-center gap-1.5">
                                  <span className="w-1 h-1 rounded-full bg-muted-foreground/50 shrink-0" />
                                  {b}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>

                {packApplied && (
                  <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400">
                    <Check className="h-4 w-4 shrink-0" /> Policy applied successfully
                  </div>
                )}

                <Button
                  onClick={handleApplyPolicy}
                  disabled={!selectedPack || applyingPack || packApplied}
                  className="w-full gap-2"
                >
                  {applyingPack ? (
                    <><div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> Applying…</>
                  ) : packApplied ? (
                    <><Check className="h-4 w-4" /> Applied</>
                  ) : (
                    "Apply Policy"
                  )}
                </Button>
              </div>
            )}

            {/* ── STEP 3: EDON Token ─────────────────── */}
            {step === 3 && (
              <div className="glass-card p-6 space-y-5">
                <div>
                  <h2 className="text-lg font-semibold mb-1">Your EDON API token</h2>
                  <p className="text-sm text-muted-foreground">
                    Your agents use this token to authenticate with EDON. Keep it secret.
                  </p>
                </div>

                {edonToken ? (
                  <>
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Token</Label>
                      <div className="flex items-center gap-2">
                        <Input
                          value={tokenVisible ? edonToken : edonToken.replace(/./g, "•")}
                          readOnly
                          className="bg-secondary/50 font-mono text-sm flex-1"
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setTokenVisible((v) => !v)}
                          className="shrink-0"
                        >
                          {tokenVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={copyToken}
                          className="gap-1.5 shrink-0"
                        >
                          <Copy className="h-3.5 w-3.5" /> Copy
                        </Button>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">How to use it</Label>
                      <pre className="bg-secondary/50 rounded-lg p-4 text-xs font-mono text-foreground/80 overflow-x-auto whitespace-pre-wrap">
                        {CODE_SNIPPET}
                      </pre>
                    </div>
                  </>
                ) : (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-medium text-amber-400">No token found</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Go to Settings → Gateway Connection to add your EDON access key.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-xs text-muted-foreground">
                  Your token is stored locally and never shared with third parties. Revoke it any time from your account dashboard.
                </div>
              </div>
            )}

            {/* ── STEP 4: Test Flow ─────────────────── */}
            {step === 4 && (
              <div className="glass-card p-6 space-y-5">
                <div>
                  <h2 className="text-lg font-semibold mb-1">Send a test request</h2>
                  <p className="text-sm text-muted-foreground">
                    Verify everything is working end-to-end. We'll send a sample <code className="font-mono text-xs bg-white/10 px-1 rounded">email.send</code> request through EDON.
                  </p>
                </div>

                <div className="rounded-lg bg-secondary/30 border border-white/10 px-4 py-3 text-xs font-mono text-muted-foreground">
                  <p><span className="text-primary">POST</span> /v1/action</p>
                  <p className="mt-1">{"{"} "action_type": "email.send", "agent_id": "onboarding-test" {"}"}</p>
                </div>

                <Button
                  onClick={handleTestFlow}
                  disabled={testingFlow}
                  className="w-full gap-2"
                >
                  {testingFlow ? (
                    <><div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> Sending…</>
                  ) : (
                    "Send Test Request"
                  )}
                </Button>

                {testResult && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`rounded-xl border px-4 py-4 space-y-2 ${
                      testResult.verdict === "ALLOW"
                        ? "border-emerald-500/30 bg-emerald-500/10"
                        : testResult.verdict === "BLOCK"
                        ? "border-red-500/30 bg-red-500/10"
                        : testResult.verdict === "CONFIRM"
                        ? "border-amber-500/30 bg-amber-500/10"
                        : "border-white/10 bg-white/5"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`text-sm font-mono ${
                          testResult.verdict === "ALLOW"
                            ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/20"
                            : testResult.verdict === "BLOCK"
                            ? "border-red-500/40 text-red-400 bg-red-500/20"
                            : "border-amber-500/40 text-amber-400 bg-amber-500/20"
                        }`}
                      >
                        {testResult.verdict}
                      </Badge>
                      <span className="text-sm text-muted-foreground">Decision received</span>
                    </div>
                    <p className="text-sm text-foreground/80">{testResult.reason}</p>
                  </motion.div>
                )}

                {testResult && (
                  <Button
                    onClick={() => navigate("/")}
                    className="w-full gap-2"
                    variant="outline"
                  >
                    Go to Dashboard <ChevronRight className="h-4 w-4" />
                  </Button>
                )}
              </div>
            )}

          </motion.div>
        </AnimatePresence>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <Button
            variant="ghost"
            onClick={prevStep}
            disabled={step === 0}
            className="gap-2"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </Button>

          {step < TOTAL_STEPS - 1 && (
            <Button
              onClick={nextStep}
              disabled={!canProceed()}
              className="gap-2"
            >
              {step === 2 && !packApplied ? "Skip for now" : "Next"}
              <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </main>
    </div>
  );
}
