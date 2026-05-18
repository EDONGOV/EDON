import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import SEOHead from "@/components/SEOHead";

const Product = () => {
  const softwareSchema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "EDON Engine",
    "applicationCategory": "AI system",
    "operatingSystem": "Linux, Embedded Linux, Docker",
    "description": "EDON is the runtime governance and control layer for autonomous agents and physical AI systems. Enforce policy, manage risk, and produce audit-grade logs.",
    "creator": {
      "@type": "Organization",
      "name": "EDON",
      "url": "https://edoncore.com"
    }
  };
  const provisionCards = [
    {
      title: "Deployment Authorization",
      description:
        "Binary determination of whether a physical AI system may operate in autonomous modes, suitable for insurance underwriting and institutional approval.",
    },
    {
      title: "Runtime Governance",
      description:
        "Continuous oversight that regulates autonomy levels and operational boundaries during operation, independent of the system's decision logic.",
    },
    {
      title: "Incident Containment",
      description:
        "Immediate system freeze and evidence capture when incidents occur, preventing recurrence across deployed systems.",
    },
    {
      title: "Audit and Accountability",
      description:
        "Complete operational records that enable reconstruction of system behavior after events, supporting regulatory review and liability determination.",
    },
    {
      title: "Insurability Framework",
      description:
        "Standards and governance mechanisms that enable insurance coverage for physical AI deployments at scale.",
    },
  ];

  const agentCapabilities = [
    "Tool allowlists + scope constraints",
    "Risk scoring + policy presets (Personal / Work / Ops)",
    "Decision stream + audit log",
    "Webhook-driven enforcement (Stripe, GitHub, web, internal APIs)",
  ];

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="EDON | Runtime Governance for Autonomous Agents and Physical AI"
        description="EDON is the runtime governance and control layer for autonomous agents and physical AI systems. Enforce policy, manage risk, and produce audit-grade logs."
        keywords="EDON, runtime governance, autonomous agents, physical AI, tool enforcement, audit logs, policy enforcement"
        canonical="https://edoncore.com/product"
        jsonLd={softwareSchema}
      />
      <Navigation />
      
      <main className="px-6 pb-16 pt-28">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-10 text-center">
          <p className="text-center text-sm font-medium uppercase tracking-[0.2em] text-[#6b6b6b]">
            Runtime Governance Framework
          </p>
          <div className="w-full max-w-6xl rounded-[28px] bg-[#f4f4f4] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.12)]">
            <div className="relative overflow-hidden rounded-[22px] bg-white">
              <div className="absolute left-1/2 top-6 z-10 -translate-x-1/2 rounded-full bg-white/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-black shadow">
                Framework
              </div>
              <video
                className="h-[360px] w-full object-cover md:h-[460px]"
                autoPlay
                muted
                loop
                playsInline
                controls={false}
              >
                <source src="/1.mp4" type="video/mp4" />
              </video>
            </div>
          </div>
          <div className="max-w-4xl">
            <h1 className="font-sans text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-semibold text-black mb-6 tracking-tight leading-tight">
              EDON — Runtime Governance for Autonomous Agents and Physical AI
            </h1>
            <p className="font-sans text-base sm:text-lg md:text-xl text-gray-600 leading-relaxed">
              Enforce policy, manage risk, and produce audit-grade logs across tool-using AI and real-world systems.
            </p>
          </div>
        </div>
      </main>

      {/* Institutional Summary */}
      <section className="bg-white py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="mb-12 sm:mb-16">
            <p className="font-sans text-xs sm:text-sm text-gray-600 tracking-widest uppercase mb-4 sm:mb-6">
              Institutional Summary
            </p>
            <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-6 sm:mb-8 leading-tight">
              What EDON Provides
            </h2>
            <p className="font-sans text-lg sm:text-xl text-gray-700 mb-6 leading-relaxed">
              EDON is the runtime governance and control layer for autonomous agents and physical AI systems.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {provisionCards.map((card) => (
                <div key={card.title} className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
                  <h3 className="font-sans text-base font-semibold text-black mb-2">{card.title}</h3>
                  <p className="font-sans text-sm text-gray-600 leading-relaxed">{card.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* What EDON Actually Does */}
      <section className="bg-[#f7f8fa] py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="mb-12 sm:mb-16">
            <p className="font-sans text-xs sm:text-sm text-gray-600 tracking-widest uppercase mb-4 sm:mb-6">
              What EDON Controls
            </p>
            <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-4 sm:mb-6 leading-tight">
              EDON enforces what machines are allowed to do, when they must stop, and how failures are contained.
            </h2>
            <p className="font-sans text-lg sm:text-xl text-gray-700 leading-relaxed mb-8">
              Three core controls govern physical AI deployment:
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8 mb-12">
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-4 sm:mb-6">
                Deployment Authorization (EOA)
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed mb-4">
                Binary determination of whether a system may operate in autonomous modes. Required for insurable deployment.
              </p>
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm">
                View documentation →
              </Link>
            </div>
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-4 sm:mb-6">
                Runtime Governance
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed mb-4">
                Continuous oversight regulating autonomy levels, risk modulation, and operational boundaries in real time.
              </p>
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm">
                View documentation →
              </Link>
            </div>
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-4 sm:mb-6">
                Incident Containment
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed mb-4">
                Immediate system freeze, evidence capture, and prevention of recurrence across deployed systems.
              </p>
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm">
                View Documentation →
              </Link>
            </div>
          </div>

          <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
            <h3 className="font-sans text-lg sm:text-xl font-semibold text-black mb-4">
              What breaks without EDON
            </h3>
            <ul className="space-y-3 font-sans text-gray-700 text-sm sm:text-base leading-relaxed">
              <li>• <strong>Lawsuits:</strong> Unclear liability boundaries and lack of auditable evidence</li>
              <li>• <strong>Insurance withdrawal:</strong> Inability to demonstrate risk containment</li>
              <li>• <strong>Pilot stagnation:</strong> Systems remain in testing, unable to scale to production</li>
              <li>• <strong>Regulatory uncertainty:</strong> No framework for demonstrating compliance</li>
            </ul>
          </div>
        </div>
      </section>

      {/* EDON for Agents */}
      <section className="bg-white py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-6xl mx-auto">
          <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-6 sm:mb-8 leading-tight">
            EDON for Agents
          </h2>
          <p className="font-sans text-lg sm:text-xl text-gray-700 mb-6 leading-relaxed">
            EDON sits between your agent and its tools. It enforces allowed actions, blocks risky operations, and produces audit-grade logs so teams can ship agents safely.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agentCapabilities.map((capability) => (
              <div key={capability} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <p className="font-sans text-sm text-gray-700">{capability}</p>
              </div>
            ))}
          </div>
          <div className="mt-8">
            <Link to="/contact" className="text-tactical-cyan hover:underline text-sm font-semibold">
              Learn more about Agents →
            </Link>
          </div>
        </div>
      </section>

      {/* Governance Framework */}
      <section className="bg-[#f7f8fa] py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-7xl mx-auto">
          <p className="font-sans text-xs sm:text-sm text-gray-600 tracking-widest uppercase mb-4 sm:mb-6">
            Governance Framework
          </p>
          <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-8 sm:mb-12 leading-tight">
            How EDON Enforces Governance
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:gap-8 mb-12 sm:mb-16">
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-3 sm:mb-4">
                Safety Envelope Enforcement
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed">
                Physical behavior constraints enforced at runtime, independent of autonomous decision logic. Maximum speed, force, and operational boundaries cannot be overridden by the system.
              </p>
            </div>
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-3 sm:mb-4">
                Autonomy State Control
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed">
                Discrete, bounded autonomy levels with logged transitions. Each level specifies permitted actions, required supervision, and conditions for safe degradation.
              </p>
            </div>
            <div className="bg-white border border-gray-200 p-6 sm:p-8 rounded-2xl shadow-sm">
              <h3 className="font-sans text-base sm:text-lg font-semibold text-black mb-3 sm:mb-4">
                Risk Modulation
              </h3>
              <p className="font-sans text-sm sm:text-base text-gray-700 leading-relaxed">
                Continuous adjustment of operational boundaries based on system state and uncertainty. Enables graceful degradation rather than abrupt shutdown.
              </p>
            </div>
          </div>

          <div className="bg-white border border-gray-200 p-6 sm:p-8 md:p-12 rounded-2xl shadow-sm">
            <h3 className="font-sans text-xl sm:text-2xl font-bold text-black mb-4 sm:mb-6 leading-tight">
              Operational Authorization Process
            </h3>
            <p className="font-sans text-base sm:text-lg text-gray-700 mb-4 leading-relaxed">
              EDON Operational Authorization (EOA) is granted when systems meet all governance requirements: defined system boundaries, active safety envelopes, discrete autonomy levels, human override authority, and continuous audit logging.
            </p>
            <p className="font-sans text-base sm:text-lg text-gray-700 leading-relaxed">
              Authorization is deployment-specific and remains valid only while the system operates within approved configurations. EOA status is demonstrable at any time through active monitoring and verifiable logs.
            </p>
            <div className="mt-6">
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm font-semibold">
                View documentation →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Deployment Authorization */}
      <section className="bg-white py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-7xl mx-auto">
          <p className="font-sans text-xs sm:text-sm text-gray-600 tracking-widest uppercase mb-4 sm:mb-6">
            Deployment Authorization
          </p>
          <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-8 sm:mb-12 leading-tight">
            Authorization for Institutional Deployment
          </h2>
          
          <div className="bg-white border border-gray-200 rounded-2xl p-6 sm:p-8 md:p-12 shadow-sm">
            <p className="font-sans text-base sm:text-lg text-gray-700 mb-6 leading-relaxed">
              EDON Operational Authorization (EOA) provides a binary determination of whether a physical AI system may operate in autonomous modes. Authorization is granted at the deployment level when systems meet governance standards.
            </p>
            <div className="space-y-4">
              <div className="border-l-4 border-tactical-cyan pl-4">
                <h3 className="font-sans font-semibold text-black mb-2">Evaluation Framework</h3>
                <p className="font-sans text-sm sm:text-base text-gray-700">
                  Framework available for organizations evaluating physical AI deployment under governance and insurability constraints.
                </p>
              </div>
              <div className="border-l-4 border-tactical-cyan pl-4">
                <h3 className="font-sans font-semibold text-black mb-2">Production Authorization</h3>
                <p className="font-sans text-sm sm:text-base text-gray-700">
                  Authorization framework available for insured, large-scale deployment of physical AI systems.
                </p>
              </div>
              <div className="border-l-4 border-tactical-cyan pl-4">
                <h3 className="font-sans font-semibold text-black mb-2">Enterprise Deployment</h3>
                <p className="font-sans text-sm sm:text-base text-gray-700">
                  Framework in evaluation for mission-critical and defense applications requiring enhanced security and auditability.
                </p>
              </div>
            </div>
            <div className="mt-8">
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm font-semibold">
                View documentation →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Supported Platforms */}
      <section className="bg-[#f7f8fa] py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-7xl mx-auto">
          <p className="font-sans text-xs sm:text-sm text-gray-600 tracking-widest uppercase mb-4 sm:mb-6">
            Platforms
          </p>
          <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-black mb-8 sm:mb-12 leading-tight">
            Supported Platforms
          </h2>
          
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 sm:gap-4">
            {["Humanoids", "UAVs", "Wearables", "Smart Environments", "Autonomous Agents"].map((platform) => (
              <Link
                key={platform}
                to="/contact"
                className="bg-white border border-gray-200 rounded-2xl p-4 sm:p-6 text-center hover:border-tactical-cyan hover:bg-gray-50 transition-colors shadow-sm"
              >
                <p className="font-sans text-xs sm:text-sm font-semibold text-black uppercase tracking-widest leading-relaxed">
                  {platform}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Technical Implementation */}
      <section className="bg-white py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white border border-gray-200 p-6 sm:p-8 md:p-12 rounded-2xl shadow-sm">
            <h2 className="font-sans text-2xl sm:text-3xl font-bold text-black mb-4 sm:mb-6 leading-tight">
              Technical Implementation Details
            </h2>
            <p className="font-sans text-base sm:text-lg text-gray-700 mb-6 leading-relaxed">
              Technical implementation details, integration guides, and API specifications are available in documentation for approved evaluators and OEM partners.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <Link to="/docs" className="text-tactical-cyan hover:underline text-sm font-semibold">
                View Documentation →
              </Link>
              <Link to="/oem/apply" className="text-tactical-cyan hover:underline text-sm font-semibold">
                Request Technical Access →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-black py-12 sm:py-16 md:py-24 px-4 sm:px-6 md:px-8 safe-area-bottom">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="font-sans text-2xl sm:text-3xl md:text-4xl font-bold text-white mb-6 sm:mb-8 leading-tight">
            Request Integration Access
          </h2>
          <p className="font-sans text-base sm:text-lg text-gray-300 mb-8 sm:mb-12 leading-relaxed px-4">
            EDON provides governance frameworks suitable for institutional deployment of physical AI systems.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 justify-center mb-8">
            <Link to="/contact" className="w-full sm:w-auto">
              <Button variant="tactical" size="lg" className="font-sans tracking-wider w-full sm:w-auto">
                Request Information
              </Button>
            </Link>
            <Link to="/docs" className="w-full sm:w-auto">
              <Button variant="tactical-outline" size="lg" className="font-sans tracking-wider w-full sm:w-auto">
                View documentation
              </Button>
            </Link>
            <Link to="/contact" className="w-full sm:w-auto">
              <Button variant="tactical-outline" size="lg" className="font-sans tracking-wider w-full sm:w-auto">
                Contact us
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Product;

