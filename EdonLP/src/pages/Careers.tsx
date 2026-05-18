import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const roles = [
  {
    title: "Senior Backend Engineer (Python/Rust)",
    team: "Engineering",
    location: "Remote",
    type: "Full-time",
    desc: "Build the core governance runtime — the decision engine, audit chain, and policy evaluation layer that sits between agents and the world.",
  },
  {
    title: "Developer Advocate",
    team: "Growth",
    location: "Remote",
    type: "Full-time",
    desc: "Help developers integrate EDON into their agent stacks. Create guides, examples, and open-source tooling that make governance as easy as a decorator.",
  },
  {
    title: "Enterprise Sales Engineer",
    team: "Sales",
    location: "Remote",
    type: "Full-time",
    desc: "Work directly with enterprise customers deploying AI at scale. Understand their governance requirements and architect EDON deployments that meet them.",
  },
  {
    title: "ML / Policy Research Engineer",
    team: "Research",
    location: "Remote",
    type: "Full-time",
    desc: "Research and build the fleet learning models that make governance self-optimizing — false positive reduction, risk calibration, and policy compression.",
  },
];

const Careers = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Careers | EDON — Build AI Governance Infrastructure"
        description="Join EDON and build the infrastructure that governs autonomous AI. Remote-first, mission-critical, early-stage. See open roles."
        keywords="EDON careers, AI governance jobs, autonomous AI startup, remote engineering jobs"
        canonical="https://edoncore.com/careers"
      />
      <Navigation />

      {/* Hero Section */}
      <section className="px-6 pt-28 pb-12">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="font-sans text-xs text-[#6b6b6b] tracking-[0.2em] uppercase mb-4">
              Careers
            </p>
            <h1 className="font-sans text-4xl md:text-5xl font-semibold text-black mb-4 tracking-tight">
              Build the infrastructure that governs autonomous AI.
            </h1>
            <p className="font-sans text-base text-[#4b4b4b] max-w-2xl">
              We're a small team solving one of the most important infrastructure problems in AI. If you want your work to matter, EDON is where you build.
            </p>
          </div>
        </div>
      </section>

      {/* Why EDON */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Why EDON</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Mission-critical work</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                What you build here will govern AI agents operating in hospitals, warehouses, financial systems, and physical environments. This isn't a feature — it's infrastructure. The stakes are real.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Early-stage ownership</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                We're early. The decisions you make now shape the architecture for years. You'll own whole problem spaces, not tickets. If you want agency and accountability, you'll have both.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Remote-first</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                We hire the best people regardless of location. Remote-first means async by default, documented decisions, and trust-based work culture — not Zoom all day.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Open Roles */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Open roles</h2>
          <div className="flex flex-col gap-4">
            {roles.map((role) => (
              <div key={role.title} className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <h3 className="text-base font-semibold text-black">{role.title}</h3>
                  </div>
                  <div className="flex flex-wrap gap-2 mb-3">
                    <span className="px-3 py-1 rounded-full bg-gray-100 text-xs text-[#4b4b4b] font-medium">{role.team}</span>
                    <span className="px-3 py-1 rounded-full bg-gray-100 text-xs text-[#4b4b4b] font-medium">{role.location}</span>
                    <span className="px-3 py-1 rounded-full bg-gray-100 text-xs text-[#4b4b4b] font-medium">{role.type}</span>
                  </div>
                  <p className="text-[#4b4b4b] text-sm leading-relaxed">{role.desc}</p>
                </div>
                <div className="flex-shrink-0">
                  <a
                    href="mailto:careers@edoncore.com"
                    className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 inline-block"
                  >
                    Apply
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Our values */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Our values</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Speed with integrity</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                We move fast because the problem demands it. But we don't cut corners on security, correctness, or the trust our customers place in us. Speed and integrity aren't a tradeoff here — they're both non-negotiable.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Operate in public</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                We share what we're building, why we're building it, and what we've learned. Internally, that means decisions are documented and visible. Externally, it means we publish what we know about governing AI.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Own the outcome</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                If you built it, you own it — including what happens after it ships. We don't throw work over fences. Everyone at EDON is accountable for the full outcome of what they create.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div>
              <h2 className="text-xl font-semibold text-black mb-2">Don't see your role? Reach out anyway.</h2>
              <p className="text-[#4b4b4b] text-sm leading-relaxed max-w-xl">
                We're always interested in exceptional people, even when we don't have a specific opening. Tell us what you do and why you want to work on AI governance.
              </p>
            </div>
            <Link
              to="/contact"
              className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 whitespace-nowrap"
            >
              Get in touch
            </Link>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Careers;
