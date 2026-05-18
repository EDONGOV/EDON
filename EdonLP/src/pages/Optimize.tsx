import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Link } from "react-router-dom";

const Optimize = () => {
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Optimize | EDON — Scale Autonomy Without Adding Headcount"
        description="Fleet learning, policy compression, and risk calibration. EDON optimizes governance so your AI agents can scale autonomy without constant human review."
        keywords="AI governance optimization, fleet learning, policy automation, autonomous AI scaling, EDON optimize"
        canonical="https://edoncore.com/optimize"
      />
      <Navigation />

      {/* Hero Section */}
      <section className="px-6 pt-28 pb-12">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <p className="font-sans text-xs text-[#6b6b6b] tracking-[0.2em] uppercase mb-4">
              Optimize
            </p>
            <h1 className="font-sans text-4xl md:text-5xl font-semibold text-black mb-4 tracking-tight">
              Scale autonomy. Reduce oversight.
            </h1>
            <p className="font-sans text-base text-[#4b4b4b] max-w-2xl">
              Govern AI fleets without constant human review. EDON learns from your decision history to continuously tighten policy, eliminate false positives, and let your agents operate at full speed, safely.
            </p>
          </div>
        </div>
      </section>

      {/* Section 1: The optimization problem */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">The optimization problem</h2>
          <div className="bg-white border border-gray-200 rounded-2xl p-8">
            <p className="text-[#4b4b4b] text-sm leading-relaxed mb-4">
              At low scale, manual oversight works. A human can review flagged decisions, approve exceptions, and tune policy by hand. But at 1,000 decisions per day — let alone 100,000 — that model collapses. Human reviewers become a bottleneck. False positives accumulate. Agents slow down waiting for approval queues to clear.
            </p>
            <p className="text-[#4b4b4b] text-sm leading-relaxed mb-4">
              EDON's fleet learning engine solves this at the infrastructure level. Every decision your agents make — allow, block, escalate, or override — feeds a continuous learning loop. Patterns that consistently resolve as safe are automatically relaxed. Patterns that consistently trigger escalation are promoted to hard blocks.
            </p>
            <p className="text-[#4b4b4b] text-sm leading-relaxed">
              The result: your governance policy stays calibrated to your actual risk profile, not a static ruleset written six months ago. Autonomy scales. Oversight burden doesn't.
            </p>
          </div>
        </div>
      </section>

      {/* Section 2: Optimization features */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Optimization features</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Fleet learning</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Patterns observed across your entire agent fleet inform policy updates. High-confidence safe patterns are promoted to auto-allow. Emerging risk signals update risk thresholds before incidents occur. Learning is fleet-wide but policy updates are tenant-scoped — your data stays yours.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Policy compression</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Over time, policy packs accumulate redundant and contradictory rules. EDON's compression engine identifies rules that are never triggered, rules that always agree, and rules that conflict — then simplifies your pack without changing its effective behavior. Lower complexity means lower latency.
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h3 className="text-base font-semibold text-black mb-3">Risk calibration</h3>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                Risk thresholds that made sense at deployment often drift from reality within weeks. EDON tracks decision outcomes — did a flagged action actually cause harm? — and calibrates thresholds accordingly. Your governance stays aligned to real-world risk, not theoretical estimates.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 3: Results */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-xl font-semibold text-black mb-6">Results</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
              <p className="text-5xl font-bold text-black mb-2">93%</p>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                reduction in false positives after 30 days of fleet learning
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
              <p className="text-5xl font-bold text-black mb-2">10x</p>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                scale in agent fleet size without adding governance headcount
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
              <p className="text-5xl font-bold text-black mb-2">&lt;50ms</p>
              <p className="text-[#4b4b4b] text-sm leading-relaxed">
                average decision latency — governance at runtime, not in a review queue
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
              <h2 className="text-xl font-semibold text-black mb-2">Ready to scale your agent fleet?</h2>
              <p className="text-[#4b4b4b] text-sm leading-relaxed max-w-xl">
                See how EDON's optimization layer can reduce oversight burden while increasing governance coverage.
              </p>
            </div>
            <Link
              to="/contact"
              className="rounded-full bg-black px-6 py-2.5 text-sm font-semibold text-white hover:bg-gray-900 whitespace-nowrap"
            >
              Talk to us
            </Link>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Optimize;
