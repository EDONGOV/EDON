import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  FileText,
  Wrench,
  ShieldCheck,
  Database,
  Settings,
  Code2,
  Play,
  ClipboardCheck,
  MessageSquare,
  Mail,
  Globe,
  Cpu,
  Bot,
  Smartphone,
} from "lucide-react";

const Build = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Build | EDON — Govern Production-Ready Agents"
        description="Everything you need to create and deploy production-ready agents with runtime governance. Policy, guardrails, knowledge, and one integration for any agent or channel."
        keywords="AI agent builder, governance API, agent deployment, runtime policy, EDON build, production agents"
        canonical="https://edoncore.com/build"
      />
      <Navigation />

      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="relative px-6 pt-28 pb-16 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-gray-100 via-white to-white pointer-events-none" />
        <div className="absolute inset-0 opacity-30 pointer-events-none" style={{ backgroundImage: "radial-gradient(circle at 20% 50%, rgba(120,80,180,0.08) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(100,100,200,0.06) 0%, transparent 40%)" }} />
        <div className="relative mx-auto w-full max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-4">Build</p>
          <h1 className="text-4xl font-semibold text-black tracking-tight md:text-5xl lg:text-6xl max-w-4xl">
            Everything you need to create production-ready agents
          </h1>
          <p className="mt-5 text-lg text-[#4b4b4b] max-w-2xl leading-relaxed">
            Deploy production-ready agents with runtime governance designed for enterprise and physical AI operations.
          </p>
          <p className="mt-5 text-base font-medium text-black">Build agents grounded in your business reality</p>
        </div>
      </section>

      {/* ── FOUR PILLARS: Policy, Tools, Guardrails, Knowledge ─ */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: FileText, title: "Policy", desc: "Use natural language or code to define how agents respond and what they're allowed to do. Policy packs define allow, block, and escalate rules — per agent and environment." },
              { icon: Wrench, title: "Tools & capabilities", desc: "Equip agents with specialized, reusable capabilities. EDON evaluates every tool call before it runs, so only governed actions execute." },
              { icon: ShieldCheck, title: "Guardrails", desc: "Set boundaries so agents operate safely and compliantly. Block, allow, or escalate at runtime — in under 50ms, every time." },
              { icon: Database, title: "Knowledge & context", desc: "Connect agents securely to your sources of truth and data. Governance sees intent and data access in one place, audit-ready." },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl bg-[#f4f4f4] border border-gray-100 p-6 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white text-gray-800 mb-4 shadow-sm">
                  <item.icon className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-base font-semibold text-black mb-2">{item.title}</h3>
                <p className="text-sm text-[#4b4b4b] leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── ONE BUILDER FOR ENGINEERS AND BUSINESS TEAMS ───── */}
      <section className="px-6 py-16 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-10">
            One builder for engineers and business teams
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="rounded-2xl bg-white p-8 border border-gray-100 shadow-[0_4px_20px_rgba(0,0,0,0.06)]">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#f4f4f4] text-gray-800">
                  <Settings className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-semibold text-black">Governance config</h3>
              </div>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Create and configure policy using natural language or structured rules, with clear visibility into what's allowed, blocked, and escalated. Change policy without changing agent code.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-8 border border-gray-100 shadow-[0_4px_20px_rgba(0,0,0,0.06)]">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#f4f4f4] text-gray-800">
                  <Code2 className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-semibold text-black">Low code & API</h3>
              </div>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Extend and customize with a REST API and SDKs for Python, Node, and Go. One integration for any agent framework — LangChain, CrewAI, OpenAI, Openclaw, or custom runtimes. Full control when you need it.
              </p>
            </div>
          </div>
          <div className="mt-8 rounded-2xl h-32 bg-gradient-to-r from-gray-200/80 via-gray-100/60 to-gray-200/80 flex items-center justify-center border border-gray-100">
            <span className="text-[#6b6b6b] text-xs font-medium uppercase tracking-wider">Abstract</span>
          </div>
        </div>
      </section>

      {/* ── TEST WITH CONFIDENCE BEFORE YOU DEPLOY ─────────── */}
      <section className="px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-4">
            Test with confidence before you deploy
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-8">
            <div className="rounded-2xl bg-white p-8 border border-gray-200 shadow-[0_4px_20px_rgba(0,0,0,0.06)]">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#f4f4f4] text-gray-800">
                  <Play className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-semibold text-black">Testing</h3>
              </div>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Interact with agents in a live preview as you build. See every action, decision, and system call in real time — before it hits production. Governance runs in the loop from the first request.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-8 border border-gray-200 shadow-[0_4px_20px_rgba(0,0,0,0.06)]">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#f4f4f4] text-gray-800">
                  <ClipboardCheck className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-semibold text-black">Evals</h3>
              </div>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Automatically validate agent behavior with scripted scenarios. Define expected outcomes, simulate at scale, and catch regressions across edge cases — so governance stays reliable as you ship.
              </p>
            </div>
          </div>
          <div className="mt-8 rounded-2xl h-32 bg-gradient-to-r from-gray-200/80 via-gray-100/60 to-gray-200/80 flex items-center justify-center border border-gray-100">
            <span className="text-[#6b6b6b] text-xs font-medium uppercase tracking-wider">Abstract</span>
          </div>
        </div>
      </section>

      {/* ── CHANNEL-AGNOSTIC DEPLOYMENT ──────────────────── */}
      <section className="px-6 py-16 bg-[#f4f4f4]">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-2xl font-semibold text-black md:text-3xl tracking-tight mb-3">
            Channel-agnostic agent deployment
          </h2>
          <p className="text-[#4b4b4b] text-base max-w-2xl mb-10">
            Deploy your agents across any channel with a unified governance interface. One policy layer — voice, chat, API, physical systems, or custom integrations.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {[
              { icon: MessageSquare, label: "Voice" },
              { icon: Mail, label: "Email" },
              { icon: MessageSquare, label: "Chat" },
              { icon: Cpu, label: "API" },
              { icon: Globe, label: "Social" },
              { icon: Bot, label: "ChatGPT" },
              { icon: MessageSquare, label: "Slack" },
              { icon: MessageSquare, label: "WhatsApp" },
              { icon: Smartphone, label: "App" },
              { icon: Cpu, label: "Robots" },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl bg-white border border-gray-100 p-4 flex flex-col items-center justify-center gap-2 shadow-[0_2px_8px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.06)] transition-shadow"
              >
                <item.icon className="h-6 w-6 text-gray-600" strokeWidth={1.5} />
                <span className="text-sm font-medium text-[#4b4b4b]">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────── */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 md:p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <div>
              <h2 className="text-xl font-semibold text-black mb-2">Get your API key</h2>
              <p className="text-[#4b4b4b] text-sm leading-relaxed max-w-xl">
                Start governing your agents today. One integration, any agent — software or physical. Integration takes minutes, not weeks.
              </p>
            </div>
            <Button asChild className="rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-11 px-7 shrink-0">
              <Link to="/contact">Request API access</Link>
            </Button>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Build;
