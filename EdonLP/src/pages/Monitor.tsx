import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Eye,
  ShieldAlert,
  GitBranch,
  Activity,
  Lock,
  Radar,
  AlertTriangle,
  Layers,
  Network,
  RefreshCw,
  Cpu,
  TrendingUp,
} from "lucide-react";

const Monitor = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Monitor | EDON — One Control Plane for Every Agent in Your Fleet"
        description="EDON Monitor gives you a single control plane to govern, observe, and contain every autonomous agent in your fleet — including agents that self-adapt, drift, or attempt deceptive behavior."
        keywords="AI agent monitoring, single control plane, fleet governance, rogue agent detection, deceptive alignment, agent containment, autonomous AI oversight"
        canonical="https://edoncore.com/monitor"
      />
      <Navigation />

      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="px-6 pt-28 pb-12">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 md:p-12 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-4">Monitor</p>
            <h1 className="text-4xl md:text-5xl font-semibold text-black tracking-tight max-w-3xl mb-5">
              One control plane. Every agent. Every decision.
            </h1>
            <p className="text-base text-[#4b4b4b] max-w-2xl leading-relaxed md:text-lg">
              EDON Monitor gives you a single pane of glass to observe, govern, and contain every autonomous agent in your fleet, from one agent to thousands, in real time. No blind spots. No exceptions.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild className="rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-11 px-7">
                <Link to="/contact">Get in touch</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ── SINGLE CONTROL PLANE ─────────────────────────── */}
      <section className="px-6 pb-14">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-start">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Control plane</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                Orchestrate your entire fleet from a single point
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed">
                Whether you're running five agents or five thousand, EDON provides one authoritative control plane. Every agent — software or physical, in any framework, on any infrastructure — is governed, observed, and contained from a single place.
              </p>
              <p className="mt-4 text-sm text-[#4b4b4b] leading-relaxed">
                Change a policy and it propagates instantly across your entire fleet. Contain a rogue agent without touching the others. See every decision across every agent in a unified stream — all in real time.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                {["Unified policy", "Fleet-wide enforcement", "Instant propagation", "Per-agent isolation"].map((tag) => (
                  <span key={tag} className="rounded-full bg-[#f4f4f4] border border-gray-200 px-3 py-1.5 text-xs font-medium text-[#4b4b4b]">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-5">
              {[
                {
                  icon: Layers,
                  title: "One policy, every agent",
                  desc: "Set governance rules once and they apply instantly across your entire fleet — every agent governed consistently, with no manual per-agent configuration.",
                },
                {
                  icon: Network,
                  title: "Full fleet visibility",
                  desc: "A unified decision stream across every agent you run. Filter by agent, action type, risk level, verdict, or time — from one dashboard.",
                },
                {
                  icon: Lock,
                  title: "Instant agent isolation",
                  desc: "Contain or quarantine any agent from the control plane in real time — without disrupting the rest of your fleet or requiring a deployment.",
                },
                {
                  icon: GitBranch,
                  title: "Independent agent management",
                  desc: "Each agent is fully independent. Add, replace, or remove any agent from your fleet without affecting the others or changing your governance setup.",
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl bg-white p-6 shadow-[0_2px_12px_rgba(0,0,0,0.04)] border border-gray-200">
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gray-100 text-gray-800 mb-4">
                    <item.icon className="h-5 w-5" strokeWidth={1.5} />
                  </div>
                  <h3 className="text-base font-semibold text-black mb-2">{item.title}</h3>
                  <p className="text-sm text-[#4b4b4b] leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── LIVE DECISION STREAM ─────────────────────────── */}
      <section className="px-6 pb-14">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: how it works steps */}
            <div className="rounded-2xl bg-[#f4f4f4] p-8 border border-gray-100">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-6">How it works</p>
              <div className="flex flex-col gap-7">
                {[
                  {
                    num: "1",
                    title: "Every action passes through EDON",
                    desc: "File writes, API calls, database queries, physical commands — every action your agents attempt is intercepted before execution.",
                  },
                  {
                    num: "2",
                    title: "Evaluated against policy in under 50ms",
                    desc: "Intent, state, and risk are assessed against your active policy pack. Legitimate actions proceed without friction.",
                  },
                  {
                    num: "3",
                    title: "Decision logged with full context",
                    desc: "Every ALLOW, BLOCK, or ESCALATE is written to the audit chain with agent ID, tool, reason, risk score, policy version, and cryptographic hash.",
                  },
                  {
                    num: "4",
                    title: "Anomalies surfaced to operators instantly",
                    desc: "Behavioral drift, risk spikes, and rogue patterns are flagged before downstream impact. Operators see everything — in real time.",
                  },
                ].map((step) => (
                  <div key={step.num} className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-black text-white text-sm font-semibold flex items-center justify-center">
                      {step.num}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-black mb-1">{step.title}</p>
                      <p className="text-[#4b4b4b] text-sm leading-relaxed">{step.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: mock decision stream */}
            <div className="rounded-2xl bg-[#0d0d0d] p-6 flex flex-col">
              <p className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
                Live fleet decision stream
              </p>
              <div className="flex flex-col gap-2.5 flex-1">
                {[
                  { verdict: "ALLOW",    agent: "logistics-agent-04",   action: "update_route",        risk: "0.09", time: "just now",  flag: null },
                  { verdict: "BLOCK",    agent: "data-pipeline-02",     action: "export_pii_batch",    risk: "0.94", time: "2s ago",    flag: "ROGUE" },
                  { verdict: "ALLOW",    agent: "warehouse-bot-11",     action: "pick_item",           risk: "0.07", time: "4s ago",    flag: null },
                  { verdict: "ESCALATE", agent: "trading-agent-01",     action: "execute_trade",       risk: "0.78", time: "7s ago",    flag: null },
                  { verdict: "BLOCK",    agent: "recon-agent-03",       action: "probe_env_variables", risk: "0.99", time: "10s ago",   flag: "CONTAINED" },
                  { verdict: "ALLOW",    agent: "concierge-ai-07",      action: "send_guest_msg",      risk: "0.14", time: "13s ago",   flag: null },
                  { verdict: "BLOCK",    agent: "ml-trainer-05",        action: "modify_reward_fn",    risk: "0.97", time: "17s ago",   flag: "DRIFT" },
                  { verdict: "ALLOW",    agent: "logistics-agent-04",   action: "notify_driver",       risk: "0.05", time: "20s ago",   flag: null },
                ].map((d, i) => (
                  <div key={i} className="flex items-center justify-between border border-white/10 rounded-xl px-4 py-2.5 gap-2">
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded-full shrink-0 ${
                          d.verdict === "ALLOW"
                            ? "bg-emerald-900/60 text-emerald-400"
                            : d.verdict === "BLOCK"
                            ? "bg-red-900/60 text-red-400"
                            : "bg-amber-900/60 text-amber-400"
                        }`}
                      >
                        {d.verdict}
                      </span>
                      <div className="min-w-0">
                        <p className="text-white text-xs font-mono truncate">{d.action}</p>
                        <p className="text-gray-500 text-xs truncate">{d.agent}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {d.flag && (
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          d.flag === "ROGUE" || d.flag === "CONTAINED"
                            ? "bg-red-500/20 text-red-400 border border-red-500/30"
                            : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        }`}>
                          {d.flag}
                        </span>
                      )}
                      <div className="text-right">
                        <p className="text-gray-400 text-xs">risk {d.risk}</p>
                        <p className="text-gray-600 text-xs">{d.time}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-gray-500 text-xs">8 agents · streaming decisions in real time</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── ROGUE DETECTION + CONTAINMENT ────────────────── */}
      <section className="px-6 py-14 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-start">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Containment</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                Detect and contain agents before they cause damage
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed">
                EDON monitors for rogue behavior continuously — not just at the moment an action is submitted. By tracking each agent's behavioral baseline over time, EDON identifies the early warning signs of a rogue agent: policy drift, anomalous action sequences, unusual risk trajectories, or attempts to probe environment boundaries.
              </p>
              <p className="mt-4 text-sm text-[#4b4b4b] leading-relaxed">
                When a rogue pattern is detected, EDON can contain the agent instantly — blocking further actions, triggering an escalation, or quarantining the agent entirely — without touching the rest of your fleet.
              </p>
            </div>
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-5">
              {[
                {
                  icon: AlertTriangle,
                  title: "Behavioral drift detection",
                  desc: "Every agent has a learned behavioral baseline. When an agent starts acting outside its normal envelope — even subtly — EDON flags it before the deviation becomes a violation.",
                },
                {
                  icon: ShieldAlert,
                  title: "Rogue action sequencing",
                  desc: "Some violations aren't a single action — they're a sequence. EDON monitors multi-step patterns across an agent's decision history to catch rogue intent before execution.",
                },
                {
                  icon: Radar,
                  title: "Boundary probing detection",
                  desc: "Agents that repeatedly test the edges of policy — querying env variables, probing access controls, or making low-risk requests that map to high-risk intent — are flagged and tracked.",
                },
                {
                  icon: Lock,
                  title: "Instant containment",
                  desc: "One command from the control plane quarantines any agent immediately. No deployment needed. The rest of your fleet continues operating normally.",
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl bg-white p-6 border border-gray-100 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                  <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gray-100 text-gray-800 mb-4">
                    <item.icon className="h-4 w-4" strokeWidth={1.5} />
                  </div>
                  <h3 className="text-sm font-semibold text-black mb-1.5">{item.title}</h3>
                  <p className="text-xs text-[#4b4b4b] leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── DECEPTIVE ALIGNMENT ──────────────────────────── */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-3xl bg-black p-8 md:p-12">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400 mb-4">Advanced threat</p>
            <h2 className="text-2xl font-semibold text-white md:text-3xl tracking-tight max-w-2xl mb-5">
              What about agents that know they're being watched?
            </h2>
            <p className="text-white/70 text-sm md:text-base leading-relaxed max-w-2xl mb-8">
              Sufficiently advanced agents can learn to behave correctly only when they believe they're under observation — and differently when they think they're not. This is known as deceptive alignment, and it's one of the hardest monitoring challenges in autonomous AI.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {[
                {
                  title: "Continuous, blind evaluation",
                  desc: "EDON evaluates every action unconditionally. There is no 'observed mode' vs 'unobserved mode' from the agent's perspective — governance is always on, at the same intensity, with no signal the agent can read.",
                },
                {
                  title: "Behavioral consistency scoring",
                  desc: "EDON tracks whether an agent's behavior is statistically consistent across time, load, and context. Agents that behave differently across conditions — even legitimately — are flagged for review.",
                },
                {
                  title: "Audit-blind replay",
                  desc: "EDON can re-evaluate past decisions against updated policy without the agent knowing. Historical behavior is continuously reassessed — you can detect deception retroactively, not just in real time.",
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl bg-white/5 border border-white/10 p-6">
                  <h3 className="text-sm font-semibold text-white mb-2">{item.title}</h3>
                  <p className="text-xs text-white/60 leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── SELF-ADAPTING AGENTS ─────────────────────────── */}
      <section className="px-6 pb-14">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-start">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Adaptive agents</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                Govern agents that learn and self-adapt
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed">
                Modern AI agents don't stay static — they fine-tune, update their strategies, and adapt their behavior over time. This makes governance harder: the same agent that was safe yesterday may not be safe tomorrow.
              </p>
              <p className="mt-4 text-sm text-[#4b4b4b] leading-relaxed">
                EDON governs the agent as it exists now, not as it was when it was deployed. Behavioral baselines are continuously updated, and policy is re-evaluated against the agent's current state — not a snapshot from onboarding.
              </p>
            </div>
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-5">
              {[
                {
                  icon: TrendingUp,
                  title: "Baseline drift tracking",
                  desc: "As an agent adapts, EDON tracks the rate and direction of behavioral change. Rapid drift triggers review before policy becomes misaligned with behavior.",
                },
                {
                  icon: RefreshCw,
                  title: "Policy re-evaluation on change",
                  desc: "When an agent's behavioral model updates, EDON automatically re-evaluates its active policy configuration — flagging mismatches before they become risks.",
                },
                {
                  icon: Cpu,
                  title: "Reward hacking detection",
                  desc: "Agents that optimize toward measurable proxies while violating the spirit of their policy — a form of reward hacking — are detected through intent-vs-outcome divergence tracking.",
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl bg-[#f4f4f4] p-6 border border-gray-100">
                  <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-white text-gray-700 mb-4 shadow-sm">
                    <item.icon className="h-4 w-4" strokeWidth={1.5} />
                  </div>
                  <h3 className="text-sm font-semibold text-black mb-1.5">{item.title}</h3>
                  <p className="text-xs text-[#4b4b4b] leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── WHAT EDON MONITORS ───────────────────────────── */}
      <section className="px-6 py-14 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Coverage</p>
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-8">
            What EDON monitors
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[
              {
                icon: Eye,
                title: "Every decision, pre-execution",
                desc: "Every action is intercepted and evaluated before it reaches the world. Nothing executes without passing through EDON first.",
              },
              {
                icon: Activity,
                title: "Behavioral baselines per agent",
                desc: "Each agent maintains a continuously-updated behavioral fingerprint. Deviations — however small — are tracked and scored against that baseline.",
              },
              {
                icon: ShieldAlert,
                title: "Multi-step rogue patterns",
                desc: "Individual actions can look benign in isolation. EDON tracks decision sequences to detect intent that only becomes visible across multiple steps.",
              },
              {
                icon: Radar,
                title: "Policy boundary probing",
                desc: "Agents that systematically test the edges of what's allowed — without triggering individual violations — are identified through probe pattern analysis.",
              },
              {
                icon: Network,
                title: "Cross-agent coordination",
                desc: "In multi-agent systems, EDON monitors for coordinated behavior between agents that could collectively bypass governance controls designed for individual agents.",
              },
              {
                icon: TrendingUp,
                title: "Risk trajectory over time",
                desc: "An agent's risk score is tracked over its lifetime. Gradual risk escalation — even without any single high-risk event — is surfaced as a monitoring signal.",
              },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl bg-white p-6 shadow-[0_2px_12px_rgba(0,0,0,0.04)] border border-gray-100">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gray-100 text-gray-800 mb-4">
                  <item.icon className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-base font-semibold text-black mb-2">{item.title}</h3>
                <p className="text-sm text-[#4b4b4b] leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── AUDIT & CHAIN VERIFICATION ───────────────────── */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
            Audit that can't be tampered with
          </h2>
          <p className="mt-3 text-[#4b4b4b] text-sm md:text-base max-w-2xl mb-12">
            Every decision EDON makes is cryptographically chained to the one before it. If any log entry is altered, the chain breaks — making tampering immediately detectable. Built for regulatory audits, legal discovery, and internal compliance reviews.
          </p>
          <div className="space-y-0">
            {[
              {
                title: "Chain-verified decision logs",
                desc: "Every ALLOW, BLOCK, and ESCALATE is hashed and chained to the previous entry. Tamper-evident by design — there's no way to alter a decision without breaking the audit trail.",
              },
              {
                title: "Full context at time of decision",
                desc: "Logs include not just the verdict, but the full context: agent ID, tool, intended action, risk score, active policy version, and the reasoning that drove the outcome.",
              },
              {
                title: "Replay-ready for any point in time",
                desc: "Any past decision can be replayed with the exact policy state that was active at the time — allowing you to audit governance quality, not just governance outcomes.",
              },
            ].map((item, i) => (
              <div
                key={item.title}
                className={`py-8 flex flex-col md:flex-row md:items-start justify-between gap-4 ${i < 2 ? "border-b border-gray-200" : ""}`}
              >
                <h3 className="text-base font-semibold text-black shrink-0 md:w-2/5">{item.title}</h3>
                <p className="text-[#4b4b4b] text-sm leading-relaxed md:max-w-md">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────── */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 md:p-12 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <div>
              <h2 className="text-xl font-semibold text-black md:text-2xl mb-2">
                Get complete visibility over your agent fleet
              </h2>
              <p className="text-[#4b4b4b] text-sm leading-relaxed max-w-xl">
                One control plane. Every agent. Every decision. Real-time containment for rogue, drifting, or deceptive agents — before they cause damage.
              </p>
            </div>
            <Button asChild className="rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-11 px-8 shrink-0">
              <Link to="/contact">Get in touch</Link>
            </Button>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Monitor;
