import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  ShieldCheck,
  Gauge,
  Eye,
  Brain,
  TrendingUp,
  Plug,
  RefreshCw,
  AlertTriangle,
  BookOpen,
  Layers,
  Cpu,
  Network,
  Activity,
  LineChart,
} from "lucide-react";

const Overview = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Overview | EDON — Runtime Governance for Autonomous Agents"
        description="EDON is the runtime governance layer for autonomous agents and physical AI. Adaptive learning, per-agent memory, fleet intelligence, and audit-driven prediction — at any scale."
        keywords="EDON, runtime governance, autonomous agents, physical AI, fleet learning, per-agent memory, adaptive governance, predictive audit, scale agents"
        canonical="https://edoncore.com/overview"
      />
      <Navigation />

      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="px-6 pt-28 pb-14">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 md:p-12 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-4">Product overview</p>
            <h1 className="text-4xl font-semibold text-black tracking-tight md:text-5xl max-w-3xl">
              The runtime governance layer for autonomous agents and physical AI
            </h1>
            <p className="mt-5 text-base text-[#4b4b4b] max-w-2xl leading-relaxed md:text-lg">
              EDON sits between your agents and the world, enforcing policy, logging every decision, and learning from every action. It gets smarter with your fleet, not just alongside it.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild className="rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-11 px-7">
                <Link to="/contact">Get in touch</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ── CORE CAPABILITIES ────────────────────────────── */}
      <section className="px-6 pb-14">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Capabilities</p>
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-8">
            Everything you need to govern AI at scale
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[
              {
                icon: ShieldCheck,
                title: "Runtime policy enforcement",
                desc: "Every agent action is evaluated against your policy before it executes. Allow, block, or escalate — in under 50ms, every time.",
              },
              {
                icon: Brain,
                title: "Per-agent memory",
                desc: "EDON maintains persistent context for each agent — intent history, past decisions, and behavioral baseline — so governance is always fully informed.",
              },
              {
                icon: TrendingUp,
                title: "Adaptive fleet learning",
                desc: "Decisions across your entire fleet feed a shared intelligence layer. EDON continuously improves its risk predictions with every action logged.",
              },
              {
                icon: Plug,
                title: "Plug in any agent",
                desc: "One API call. Works with any agent framework — LangChain, CrewAI, OpenAI, Openclaw, custom runtimes, or physical systems — no rearchitecting required.",
              },
              {
                icon: Gauge,
                title: "Scale from 1 to 1,000+",
                desc: "Add agents at will. Remove or replace any agent independently without touching the rest of your fleet or reconfiguring governance rules.",
              },
              {
                icon: Eye,
                title: "Audit-grade visibility",
                desc: "Every decision logged with agent ID, tool, reason, and policy version. Chain-verified and replay-ready for compliance and regulators.",
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
      </section>

      {/* ── GETS SMARTER WITH EVERY DECISION ─────────────── */}
      <section className="px-6 py-14 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-start">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Adaptive intelligence</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                EDON gets better with every decision
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed">
                Unlike static policy engines, EDON learns continuously. Every governed action feeds a shared intelligence layer that refines risk scoring, tightens behavioral baselines, and improves prediction accuracy across your entire fleet — automatically, without manual tuning.
              </p>
              <p className="mt-4 text-sm text-[#4b4b4b] leading-relaxed">
                Over time, EDON builds a comprehensive picture of how each agent behaves, what normal looks like, and where rogue patterns tend to emerge — before they become violations.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                {["Fleet learning", "Per-agent context", "Behavioral baselines", "Risk scoring", "Anomaly detection"].map((tag) => (
                  <span key={tag} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-[#4b4b4b] border border-gray-200">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-5">
              {[
                {
                  icon: Network,
                  title: "Fleet-wide learning",
                  desc: "A decision made by one agent informs governance across all agents. Shared learning means your entire fleet gets smarter from a single event.",
                },
                {
                  icon: BookOpen,
                  title: "Per-agent memory",
                  desc: "Each agent carries persistent context — past actions, intent history, escalation patterns. EDON governs with full situational awareness, not just the current request.",
                },
                {
                  icon: AlertTriangle,
                  title: "Predictive rogue detection",
                  desc: "EDON analyzes audit history to identify pre-rogue behavioral signatures. Anomalies are flagged and blocked before they become violations.",
                },
                {
                  icon: RefreshCw,
                  title: "Continuous improvement",
                  desc: "Every allow, block, and escalate decision trains the model. Governance accuracy compounds over time without any manual intervention.",
                },
              ].map((item) => (
                <div key={item.title} className="rounded-2xl bg-white p-6 border border-gray-100 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                  <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-[#f4f4f4] text-gray-800 mb-4">
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

      {/* ── PLUG IN AND SCALE ─────────────────────────────── */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Scale</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                Plug in one agent. Scale to thousands.
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed max-w-md">
                EDON is modular by design. Every agent is independent — you can add, remove, or swap any agent in your fleet without touching the others. No downtime, no reconfiguration, no cascading changes.
              </p>
              <p className="mt-4 text-sm text-[#4b4b4b] leading-relaxed max-w-md">
                Start with a single agent in an afternoon. Scale to a full enterprise fleet without changing a line of governance code.
              </p>
            </div>
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                {
                  icon: Plug,
                  title: "One-line integration",
                  desc: "Any agent, any framework. Plug in with a single API call — governance is live from the first request.",
                },
                {
                  icon: Layers,
                  title: "Hot-swap agents",
                  desc: "Replace or remove any agent independently. The rest of your fleet keeps running without interruption.",
                },
                {
                  icon: Cpu,
                  title: "1 → 1,000+",
                  desc: "Architecture built for concurrency. Enterprise-grade performance from day one, no refactoring as you scale.",
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

      {/* ── OBSERVABILITY ─────────────────────────────────── */}
      <section className="px-6 py-14 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Observability</p>
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-3">
            Built-in audit and real-time monitoring
          </h2>
          <p className="mt-1 text-sm text-[#4b4b4b] md:text-base max-w-2xl mb-10">
            Full visibility into every agent in production. Measure, trust, and continuously improve your governance as your fleet grows.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: LineChart,
                title: "Real-time monitoring",
                desc: "Live dashboards tracking decisions, latency, policy outcomes, and risk — sliced by agent, tool, tenant, or time.",
              },
              {
                icon: Activity,
                title: "Full traceability",
                desc: "Reasoning traces for every action. See not just what your agents did — but why, with full context and policy state at time of decision.",
              },
              {
                icon: ShieldCheck,
                title: "Audit-ready logs",
                desc: "Chain-verified decision logs that meet regulatory and internal audit requirements. No retrofitting. No guesswork at review time.",
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

      {/* ── HOW IT WORKS ──────────────────────────────────── */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-3">Architecture</p>
              <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
                The layer between intent and action
              </h2>
              <p className="mt-4 text-sm text-[#4b4b4b] md:text-base leading-relaxed">
                EDON intercepts every agent decision before it executes. It evaluates intent, current state, and risk against your policy — logs the outcome — and feeds the result back into the fleet intelligence layer.
              </p>
              <p className="mt-3 text-sm text-[#4b4b4b] leading-relaxed">
                The loop closes with every decision: govern, log, learn, improve.
              </p>
            </div>
            <div className="lg:col-span-7">
              <div className="rounded-2xl bg-[#f4f4f4] p-6 border border-gray-200">
                <div className="flex flex-col gap-0">
                  {[
                    { label: "Agent Decision / Planning", sub: null, highlight: false },
                    { arrow: true },
                    { label: "EDON Runtime", sub: "Intent · State · Risk · Per-Agent Memory", highlight: true },
                    { arrow: true },
                    { label: "Allow / Block / Escalate", sub: null, highlight: false },
                    { arrow: true },
                    { label: "Execution / Actuation", sub: null, highlight: false },
                    { arrow: true },
                    { label: "Audit Log + Fleet Learning", sub: "Every decision improves the next one", highlight: false },
                  ].map((row, i) =>
                    (row as { arrow?: boolean }).arrow ? (
                      <div key={i} className="text-center text-[#8a8a8a] py-1 text-lg leading-none">↓</div>
                    ) : (
                      <div
                        key={i}
                        className={`rounded-xl px-5 py-3 text-center ${
                          (row as { highlight?: boolean }).highlight
                            ? "bg-black text-white"
                            : "bg-white border border-gray-200"
                        }`}
                      >
                        <span className={`font-semibold text-sm ${(row as { highlight?: boolean }).highlight ? "text-white" : "text-black"}`}>
                          {(row as { label?: string }).label}
                        </span>
                        {(row as { sub?: string | null }).sub && (
                          <p className={`text-xs mt-0.5 ${(row as { highlight?: boolean }).highlight ? "text-white/70" : "text-[#6b6b6b]"}`}>
                            {(row as { sub?: string | null }).sub}
                          </p>
                        )}
                      </div>
                    )
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── VALUE COMPOUNDS ───────────────────────────────── */}
      <section className="px-6 py-14 bg-[#f4f4f4]">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight">
            Governance that compounds
          </h2>
          <p className="mt-3 text-[#4b4b4b] text-sm md:text-base max-w-2xl mb-12">
            Every agent you add strengthens the whole. Shared policy, shared audit, shared intelligence — EDON becomes more accurate and more valuable the more you use it.
          </p>
          <div className="space-y-0">
            {[
              {
                title: "More agents, smarter governance",
                desc: "Each new agent contributes behavioral data to the fleet intelligence layer. The more agents EDON governs, the more accurate its risk predictions become.",
              },
              {
                title: "Audit history predicts future violations",
                desc: "EDON doesn't just log what happened — it learns from it. Patterns in your audit trail surface pre-rogue behavioral signatures before violations occur.",
              },
              {
                title: "Control stays uncompromised at scale",
                desc: "Whether you're running ten agents or ten thousand, the governance layer stays consistent, auditable, and in your control — no matter how fast your fleet grows.",
              },
            ].map((item, i) => (
              <div
                key={item.title}
                className={`py-8 flex flex-col md:flex-row md:items-start md:justify-between gap-4 ${i < 2 ? "border-b border-gray-300" : ""}`}
              >
                <h3 className="text-base font-semibold text-black shrink-0 md:w-2/5">{item.title}</h3>
                <p className="text-[#4b4b4b] text-sm leading-relaxed md:max-w-md">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRODUCT LINKS + CTA ───────────────────────────── */}
      <section className="px-6 py-14">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-lg font-semibold text-black mb-6">Explore the platform</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              { title: "Monitor", desc: "Control and audit for every agent. Every decision logged, chain-verified, and ready for replay." },
              { title: "Build", desc: "Plug in any agent. Intent, state, risk — evaluated at runtime. One API call to governed." },
              { title: "Optimize", desc: "Govern autonomy while it runs. Fleet learning and predictive governance built in." },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-2xl bg-white border border-gray-200 p-6"
              >
                <h3 className="text-base font-semibold text-black mb-2">{item.title}</h3>
                <p className="text-[#4b4b4b] text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 rounded-3xl bg-black p-8 md:p-12 flex flex-col md:flex-row md:items-center md:justify-between gap-6 shadow-[0_12px_40px_rgba(0,0,0,0.15)]">
            <div>
              <h2 className="text-xl font-semibold text-white md:text-2xl">
                Start governing your agents today
              </h2>
              <p className="mt-2 text-white/70 text-sm md:text-base max-w-xl">
                One agent or a thousand — EDON gets smarter with every decision you make together.
              </p>
            </div>
            <Button asChild className="rounded-full bg-white text-black hover:bg-gray-100 font-semibold text-sm h-12 px-8 shrink-0">
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

export default Overview;
