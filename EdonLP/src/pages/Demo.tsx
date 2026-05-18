import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { sendFormSubmission } from "@/lib/emailService";
import { toast } from "sonner";
import { CheckCircle2, Clock, Users, Zap } from "lucide-react";

const inputBase =
  "w-full bg-gray-50 border border-gray-200 text-gray-900 px-4 py-3 rounded-xl focus:outline-none focus:border-gray-400 focus:ring-2 focus:ring-gray-200 transition-colors placeholder:text-gray-400 text-sm";

const AGENT_TYPES = [
  "Autonomous software agents",
  "Physical AI / robotics",
  "LLM-powered assistants",
  "Data pipeline agents",
  "Customer-facing bots",
  "Trading / financial agents",
  "Logistics & supply chain agents",
  "Healthcare AI",
  "Multi-agent systems",
  "Other",
];

const FLEET_SIZES = [
  "1–5 agents",
  "6–20 agents",
  "21–100 agents",
  "100–500 agents",
  "500+ agents",
  "Not sure yet",
];

const PRIMARY_CHALLENGES = [
  "No visibility into what my agents are doing",
  "Agents taking actions they shouldn't",
  "Compliance and audit requirements",
  "Scaling agent governance as fleet grows",
  "Detecting rogue or drifting agent behavior",
  "Needing human oversight without blocking agents",
  "Multi-agent coordination governance",
  "Regulated deployment requirements",
  "Other",
];

const Demo = () => {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    company: "",
    role: "",
    agentType: "",
    fleetSize: "",
    challenge: "",
    successCriteria: "",
    preferredTime: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await sendFormSubmission("contact", {
        ...formData,
        inquiryType: "Demo Request",
        message: `Agent type: ${formData.agentType}\nFleet size: ${formData.fleetSize}\nPrimary challenge: ${formData.challenge}\nWhat success looks like: ${formData.successCriteria}\nPreferred time: ${formData.preferredTime}`,
        organization: formData.company,
      });
      setSubmitted(true);
    } catch {
      toast.error("Something went wrong. Email charlie@edoncore.com directly.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-white font-sans">
        <Navigation />
        <div className="flex items-center justify-center min-h-[80vh] px-6">
          <div className="text-center max-w-md">
            <div className="w-14 h-14 rounded-full bg-black flex items-center justify-center mx-auto mb-6">
              <CheckCircle2 className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-2xl font-semibold text-black mb-3">You're on the list</h1>
            <p className="text-[#4b4b4b] text-sm leading-relaxed mb-6">
              We'll review your details and reach out within 24 hours to schedule your tailored demo. Check your inbox — it'll come from charlie@edoncore.com.
            </p>
            <p className="text-xs text-[#6b6b6b]">
              Questions in the meantime?{" "}
              <a href="mailto:charlie@edoncore.com" className="underline hover:text-black">
                charlie@edoncore.com
              </a>
            </p>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Book a Demo | EDON — See Runtime Governance in Action"
        description="See EDON govern your specific agents live on a tailored Zoom demo. Fill in your use case and we'll build the demo around you."
        keywords="EDON demo, book demo, AI governance demo, autonomous agent governance, runtime policy demo"
        canonical="https://edoncore.com/demo"
      />
      <Navigation />

      {/* ── HERO ─────────────────────────────────────────── */}
      <section className="px-6 pt-28 pb-12">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 md:p-12 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#6b6b6b] mb-4">Book a demo</p>
            <h1 className="text-4xl md:text-5xl font-semibold text-black tracking-tight max-w-3xl mb-5">
              See EDON govern your agents — live.
            </h1>
            <p className="text-base text-[#4b4b4b] max-w-2xl leading-relaxed">
              Every demo is built around your specific use case and agent types. You'll see EDON evaluate real decisions, enforce real policy, and surface real governance insights — tailored to what you actually deploy.
            </p>

            {/* Process steps */}
            <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-5">
              {[
                {
                  icon: Users,
                  step: "1",
                  title: "Tell us about your agents",
                  desc: "Fill in the form below. We use your answers to build a demo that matches your deployment — not a generic walkthrough.",
                },
                {
                  icon: Zap,
                  step: "2",
                  title: "We build your tailored demo",
                  desc: "Within 24 hours, we'll schedule a 45-minute Zoom and configure a live governance environment around your use case.",
                },
                {
                  icon: Clock,
                  step: "3",
                  title: "See governance in action",
                  desc: "Watch EDON govern agents that look like yours — real decisions, real policy enforcement, real audit trail.",
                },
              ].map((item) => (
                <div key={item.step} className="rounded-2xl bg-white p-5 border border-gray-100 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-7 h-7 rounded-full bg-black text-white text-xs font-semibold flex items-center justify-center shrink-0">
                      {item.step}
                    </div>
                    <item.icon className="h-4 w-4 text-gray-500" strokeWidth={1.5} />
                  </div>
                  <h3 className="text-sm font-semibold text-black mb-1">{item.title}</h3>
                  <p className="text-xs text-[#4b4b4b] leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── FORM ─────────────────────────────────────────── */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-start">

            {/* Left: what you'll see */}
            <div className="lg:col-span-4">
              <h2 className="text-lg font-semibold text-black mb-5">What you'll see in the demo</h2>
              <div className="space-y-4">
                {[
                  "EDON governing live agent decisions in real time — allow, block, escalate",
                  "Policy enforcement tailored to your agent type and policies",
                  "The full audit trail — every decision logged, chain-verified, and replayable",
                  "Fleet monitoring: behavioral baselines, rogue detection, drift alerts",
                  "The control plane: how you manage, update, and contain agents from one place",
                  "Fleet learning in action — how EDON improves with every decision",
                  "Integration walkthrough: how quickly you can be live",
                ].map((item, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <CheckCircle2 className="h-4 w-4 text-black mt-0.5 shrink-0" strokeWidth={1.5} />
                    <p className="text-sm text-[#4b4b4b] leading-relaxed">{item}</p>
                  </div>
                ))}
              </div>

              <div className="mt-8 rounded-2xl bg-[#f4f4f4] p-5 border border-gray-100">
                <p className="text-xs font-semibold uppercase tracking-wider text-[#6b6b6b] mb-2">Format</p>
                <p className="text-sm font-semibold text-black">45-minute Zoom</p>
                <p className="text-xs text-[#4b4b4b] mt-1">Tailored to your use case. Scheduled within 24 hours of your submission.</p>
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <p className="text-xs text-[#6b6b6b]">
                    Questions before booking?{" "}
                    <a href="mailto:charlie@edoncore.com" className="underline hover:text-black">
                      charlie@edoncore.com
                    </a>
                  </p>
                </div>
              </div>
            </div>

            {/* Right: form */}
            <div className="lg:col-span-8">
              <div className="rounded-3xl bg-white border border-gray-100 p-8 shadow-[0_12px_40px_rgba(0,0,0,0.06)]">
                <h2 className="text-xl font-semibold text-black mb-1">Request your tailored demo</h2>
                <p className="text-sm text-[#6b6b6b] mb-7">
                  The more you tell us, the more relevant your demo will be.
                </p>

                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* Name + Email */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Full name *
                      </label>
                      <input
                        type="text"
                        required
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className={inputBase}
                        placeholder="Your name"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Work email *
                      </label>
                      <input
                        type="email"
                        required
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className={inputBase}
                        placeholder="you@company.com"
                      />
                    </div>
                  </div>

                  {/* Company + Role */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Company *
                      </label>
                      <input
                        type="text"
                        required
                        value={formData.company}
                        onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                        className={inputBase}
                        placeholder="Company name"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                        Your role *
                      </label>
                      <input
                        type="text"
                        required
                        value={formData.role}
                        onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                        className={inputBase}
                        placeholder="e.g. CTO, Head of AI, VP Eng"
                      />
                    </div>
                  </div>

                  {/* Agent type */}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      What type of agents are you deploying? *
                    </label>
                    <select
                      required
                      value={formData.agentType}
                      onChange={(e) => setFormData({ ...formData, agentType: e.target.value })}
                      className={inputBase}
                    >
                      <option value="">Select agent type…</option>
                      {AGENT_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>

                  {/* Fleet size */}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      How many agents in your fleet?
                    </label>
                    <select
                      value={formData.fleetSize}
                      onChange={(e) => setFormData({ ...formData, fleetSize: e.target.value })}
                      className={inputBase}
                    >
                      <option value="">Select fleet size…</option>
                      {FLEET_SIZES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>

                  {/* Primary challenge */}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      What's your primary governance challenge? *
                    </label>
                    <select
                      required
                      value={formData.challenge}
                      onChange={(e) => setFormData({ ...formData, challenge: e.target.value })}
                      className={inputBase}
                    >
                      <option value="">Select your challenge…</option>
                      {PRIMARY_CHALLENGES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  {/* Success criteria */}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      What would make this demo a success for you?
                    </label>
                    <textarea
                      rows={3}
                      value={formData.successCriteria}
                      onChange={(e) => setFormData({ ...formData, successCriteria: e.target.value })}
                      className={`${inputBase} resize-none`}
                      placeholder="e.g. I want to see how EDON would handle an agent that tries to export customer data…"
                    />
                  </div>

                  {/* Preferred time */}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                      Preferred time / timezone
                    </label>
                    <input
                      type="text"
                      value={formData.preferredTime}
                      onChange={(e) => setFormData({ ...formData, preferredTime: e.target.value })}
                      className={inputBase}
                      placeholder="e.g. Weekday afternoons EST, or anytime"
                    />
                  </div>

                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full rounded-full bg-black text-white hover:bg-gray-900 font-semibold text-sm h-12 px-8 mt-2"
                  >
                    {isSubmitting ? "Submitting…" : "Request my tailored demo →"}
                  </Button>

                  <p className="text-xs text-gray-400 text-center">
                    We'll respond within 24 hours to confirm your Zoom.
                  </p>
                </form>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Demo;
