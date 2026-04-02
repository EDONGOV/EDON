import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { edonApi } from "@/lib/api";
import { ShieldCheck, Zap, BarChart2, Users, Eye, EyeOff } from "lucide-react";

const isLikelyToken = (s: string) =>
  /^(edon_[A-Za-z0-9._-]{16,}|[a-f0-9]{64}|[a-f0-9]{128}|[A-Za-z0-9._-]{24,})$/i.test(s);

const features = [
  { icon: ShieldCheck, label: "Real-time governance", desc: "Every agent action evaluated against your policy before it executes" },
  { icon: Zap,         label: "Instant enforcement", desc: "Sub-50ms allow/block/confirm decisions across all agent types" },
  { icon: BarChart2,   label: "Full audit trail",    desc: "Every decision logged with reason, agent, tool, and policy version" },
  { icon: Users,       label: "Team governance",     desc: "Share audit records, manage roles, and escalate across your team" },
];

export const AccessGate = () => {
  const [showManual, setShowManual] = useState(false);
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    const trimmed = key.trim();
    if (!trimmed) { setError("Please enter your access key."); return; }
    if (!isLikelyToken(trimmed)) { setError("Key format doesn't look right. Check and try again."); return; }
    setConnecting(true);
    localStorage.setItem("edon_token", trimmed);
    localStorage.setItem("edon_api_key", trimmed);
    localStorage.setItem("edon_session_token", trimmed);

    try {
      const session = await edonApi.getSession();
      if (session?.email) localStorage.setItem("edon_user_email", session.email);
      if (session?.plan) localStorage.setItem("edon_plan", session.plan);
    } catch {
      if (!localStorage.getItem("edon_token")) {
        setError("Key not recognised by the gateway. Check and try again.");
        setConnecting(false);
        return;
      }
    }

    window.dispatchEvent(new Event("edon-auth-updated"));
  };

  const handleDemo = () => {
    localStorage.setItem("edon_plan", "Starter");
    localStorage.setItem("edon_token", "demo");
    window.dispatchEvent(new Event("edon-auth-updated"));
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      {/* Left panel — branding + features */}
      <div className="hidden lg:flex flex-col justify-between w-[420px] shrink-0 border-r border-white/10 bg-white/[0.02] px-10 py-12">
        <div>
          <span className="edon-brand text-xl font-semibold tracking-[0.3em] text-foreground/90">EDON</span>
          <p className="text-xs uppercase tracking-widest text-muted-foreground mt-1">Governance Console</p>
          <p className="text-sm text-muted-foreground leading-relaxed mt-6">
            The control plane for AI agents. Govern every action — physical or digital — before it executes.
          </p>

          <div className="mt-10 space-y-6">
            {features.map(({ icon: Icon, label, desc }) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-start gap-3"
              >
                <div className="w-8 h-8 shrink-0 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center mt-0.5">
                  <Icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        <p className="text-xs text-muted-foreground/50">
          © {new Date().getFullYear()} EDON. Governing AI at scale.
        </p>
      </div>

      {/* Right panel — access form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          {/* Mobile wordmark */}
          <div className="lg:hidden mb-8 text-center">
            <span className="edon-brand text-xl font-semibold tracking-[0.3em] text-foreground/90">EDON</span>
            <p className="text-xs text-muted-foreground mt-1 uppercase tracking-widest">Governance Console</p>
          </div>

          <div className="glass-card p-8">
            <h1 className="text-xl font-semibold mb-1">Welcome back</h1>
            <p className="text-sm text-muted-foreground mb-7 leading-relaxed">
              Sign in at edoncore.com to open this console automatically, or enter your access key below.
            </p>

            {!showManual ? (
              <div className="space-y-3">
                <a href="https://edoncore.com/login" className="block">
                  <Button className="w-full h-10 font-medium">
                    Sign in on edoncore.com
                  </Button>
                </a>
                <Button
                  variant="outline"
                  className="w-full h-10 border-white/15"
                  onClick={() => setShowManual(true)}
                >
                  Enter access key manually
                </Button>
                <div className="relative flex items-center gap-3 my-1">
                  <div className="flex-1 h-px bg-white/10" />
                  <span className="text-xs text-muted-foreground">or</span>
                  <div className="flex-1 h-px bg-white/10" />
                </div>
                <Button
                  variant="ghost"
                  className="w-full h-9 text-sm text-muted-foreground hover:text-foreground border border-white/8"
                  onClick={handleDemo}
                >
                  Explore in demo mode
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    autoFocus
                    value={key}
                    onChange={(e) => { setKey(e.target.value); setError(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter") handleConnect(); }}
                    placeholder="edon_sk_••••••••••••"
                    className="w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2.5 pr-10 text-sm placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {error && (
                  <p className="text-xs text-red-400 flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-red-400" />
                    {error}
                  </p>
                )}

                <div className="flex gap-2">
                  <Button className="flex-1 gap-2 h-10" onClick={handleConnect} disabled={connecting}>
                    {connecting && <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />}
                    {connecting ? "Connecting…" : "Connect"}
                  </Button>
                  <Button variant="outline" className="border-white/15" onClick={() => { setShowManual(false); setKey(""); setError(""); }} disabled={connecting}>
                    Back
                  </Button>
                </div>

                <p className="text-xs text-muted-foreground/60 text-center pt-1">
                  Find your key at{" "}
                  <a href="https://edoncore.com/settings/api-keys" className="text-primary hover:underline">
                    edoncore.com/settings/api-keys
                  </a>
                </p>
              </div>
            )}
          </div>

          <p className="text-center text-xs text-muted-foreground/50 mt-6">
            New to EDON?{" "}
            <a href="https://edoncore.com/signup" className="text-primary hover:underline">
              Get started free →
            </a>
          </p>
        </motion.div>
      </div>
    </div>
  );
};
