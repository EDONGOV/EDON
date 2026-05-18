import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Activity, ScrollText, Shield } from "lucide-react";

const pillars = [
  {
    icon: Shield,
    title: "Policy at runtime",
    body: "Intercept tool calls before they execute — allow, block, escalate, or degrade with your rules.",
  },
  {
    icon: ScrollText,
    title: "Audit-grade logs",
    body: "Every decision hashed and traceable — demonstrate control without bolting on logging after the fact.",
  },
  {
    icon: Activity,
    title: "Fleet-wide visibility",
    body: "Baselines, drift, and anomalies across agents — one control plane as autonomy scales.",
  },
] as const;

const Index = () => {
  return (
    <div className="min-h-screen bg-[#f5f5f3] font-sans antialiased">
      <SEOHead
        title="EDON | Runtime Governance for Autonomous Agents and Physical AI"
        description="EDON is the runtime governance and control layer for autonomous agents and physical AI systems. Enforce policy, manage risk, learn from every decision, and produce audit-grade logs."
        keywords="EDON, runtime governance, autonomous agents, physical AI, fleet learning, adaptive AI, audit logs, policy enforcement, per-agent memory"
        canonical="https://edoncore.com"
      />
      <Navigation />

      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="relative w-full min-h-[88vh] flex flex-col justify-end overflow-hidden">
        <video
          className="absolute inset-0 w-full h-full object-cover scale-[1.01]"
          autoPlay
          muted
          loop
          playsInline
          controls={false}
          aria-hidden
        >
          <source src="/1.mp4" type="video/mp4" />
        </video>
        {/* Layered readablity: vignette + bottom weight + subtle top cool wash */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_100%,rgba(0,0,0,0.75)_0%,transparent_55%)]" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black via-black/45 to-black/15" />
        <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/[0.06]" />
        <div className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-16 pt-28 md:px-6 md:pb-24 lg:px-8">
          <div className="flex w-full flex-col gap-10 md:flex-row md:items-end md:justify-between md:gap-12">
            <div className="max-w-2xl">
              <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-white/90 backdrop-blur-md">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-tactical-cyan shadow-[0_0_12px_hsl(var(--tactical-cyan))]" aria-hidden />
                Runtime governance
              </p>
              <h1 className="font-space text-4xl font-semibold tracking-tight text-white md:text-5xl lg:text-[3.25rem] lg:leading-[1.08]">
                Govern autonomy{" "}
                <span className="text-white/95">while it runs.</span>
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-white/80 md:text-lg">
                The control layer for autonomous agents and physical AI — every decision evaluated, logged, and learned from{" "}
                <span className="font-medium text-tactical-cyan">in real time</span>.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-3 md:justify-end md:pb-1">
              <Button
                asChild
                className="h-12 rounded-full border-0 bg-white px-8 text-sm font-semibold text-gray-900 shadow-[0_8px_30px_rgba(0,0,0,0.2)] transition-all hover:bg-gray-50 hover:shadow-[0_12px_40px_rgba(0,0,0,0.25)]"
              >
                <Link to="/contact">Get in touch</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <main className="border-t border-gray-200/80 bg-[#f5f5f3] px-4 pb-28 pt-20 md:px-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-20">
          {/* ── WHAT WE DO ────────────────── */}
          <section className="relative overflow-hidden rounded-[2rem] border border-gray-200/90 bg-white p-10 text-center shadow-[0_4px_40px_rgba(0,0,0,0.04)] md:p-14">
            <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-tactical-cyan/[0.06] blur-3xl" />
            <div className="pointer-events-none absolute -bottom-32 -left-20 h-56 w-56 rounded-full bg-black/[0.03] blur-3xl" />
            <div className="relative">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">
                What we do
              </p>
              <h2 className="font-space mx-auto mt-3 max-w-2xl text-2xl font-semibold tracking-tight text-black md:text-3xl md:leading-snug">
                The runtime governance layer for autonomous agents and physical AI
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-[#4b4b4b] md:text-lg md:leading-relaxed">
                Every decision evaluated, every action logged — so you can scale autonomy without losing control.
              </p>
            </div>
          </section>

          {/* ── PILLARS ──────────────────────── */}
          <section aria-labelledby="pillars-heading">
            <div className="mb-10 text-center md:mb-12">
              <h2 id="pillars-heading" className="font-space text-xl font-semibold tracking-tight text-black md:text-2xl">
                Control that scales with your fleet
              </h2>
              <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600 md:text-base">
                Keep intelligence internal, agents auditable, and oversight uncompromised.
              </p>
            </div>
            <ul className="grid gap-5 md:grid-cols-3 md:gap-6">
              {pillars.map(({ icon: Icon, title, body }) => (
                <li
                  key={title}
                  className="flex flex-col rounded-2xl border border-gray-200/90 bg-white p-6 shadow-[0_2px_20px_rgba(0,0,0,0.03)] transition-shadow duration-300 hover:shadow-[0_8px_32px_rgba(0,0,0,0.06)] md:p-7"
                >
                  <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-gray-100 bg-[#f0f0ed] text-gray-900">
                    <Icon className="h-5 w-5" strokeWidth={1.5} aria-hidden />
                  </div>
                  <h3 className="font-space text-base font-semibold text-black">{title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-gray-600">{body}</p>
                </li>
              ))}
            </ul>
          </section>

          {/* ── CTA ───────────────────────────────────────── */}
          <section className="relative overflow-hidden rounded-[2rem] border border-gray-800 bg-gradient-to-b from-neutral-900 to-black p-10 text-center shadow-[0_24px_80px_rgba(0,0,0,0.2)] md:p-14">
            <div className="pointer-events-none absolute -right-20 top-1/2 h-72 w-72 -translate-y-1/2 rounded-full bg-tactical-cyan/10 blur-[100px]" />
            <div className="pointer-events-none absolute inset-0 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)]" />
            <div className="relative">
              <h2 className="font-space text-2xl font-semibold tracking-tight text-white md:text-3xl">
                Ready to govern your agents?
              </h2>
              <p className="mx-auto mt-3 max-w-md text-sm text-white/65 md:text-base">
                Start with one agent. Scale to your entire fleet.
              </p>
              <Button
                asChild
                className="mt-9 h-12 rounded-full bg-white px-8 text-sm font-semibold text-black transition-all hover:bg-gray-100"
              >
                <Link to="/contact">Get in touch</Link>
              </Button>
            </div>
          </section>
        </div>
      </main>
      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Index;
