import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const Platforms = () => {
  const platforms = [
    {
      title: "Human Proximity Systems",
      riskDomain: "Humanoids",
      status: "Fully supported",
      governanceStatus: "EOA Available",
      insurabilityReadiness: "Ready",
      runtime: "gRPC + streaming",
      outputs: "State vectors, torque scaling, motion gating, safety flags",
      useCases: [
        "Factory robots",
        "Human-assist robotics",
        "Field deployment"
      ],
      description: "Systems operating in close proximity to humans. Highest governance requirements for safety envelopes and human override authority."
    },
    {
      title: "Airspace and Kinetic Systems",
      riskDomain: "Drones / UAV",
      status: "Framework available",
      governanceStatus: "Framework in evaluation",
      insurabilityReadiness: "Under assessment",
      runtime: "v2 batch + mission state routing",
      outputs: "Navigation stress + payload risk modulation",
      useCases: [
        "Autonomous navigation",
        "Payload management",
        "Mission-critical operations"
      ],
      description: "Aerial systems with kinetic energy and airspace constraints. Requires strict boundary definition and incident containment protocols."
    },
    {
      title: "Human State Interfaces",
      riskDomain: "Wearables",
      status: "Supported via embedded profiles",
      governanceStatus: "EOA Available",
      insurabilityReadiness: "Ready",
      runtime: "Local ML",
      outputs: "Edge inference, real-time physiological state, safety nudges",
      useCases: [
        "Edge inference",
        "Real-time physiological state",
        "Safety nudges"
      ],
      description: "Systems directly interfacing with human physiology. Governance focuses on data boundaries and operator state classification."
    },
    {
      title: "Distributed Physical Control",
      riskDomain: "Smart Environments",
      status: "Framework available",
      governanceStatus: "Framework in evaluation",
      insurabilityReadiness: "Under assessment",
      runtime: "Mixed",
      outputs: "Adaptive lighting, environmental stress regulation, multi-device sync",
      useCases: [
        "Adaptive lighting",
        "Environmental stress regulation",
        "Multi-device sync with human physiology"
      ],
      description: "Building-scale autonomous control systems. Governance addresses multi-device coordination and system boundary enforcement."
    },
    {
      title: "Autonomous Agents",
      riskDomain: "Autonomous Agents",
      status: "Fully supported",
      governanceStatus: "EOA Available",
      insurabilityReadiness: "Ready",
      runtime: "REST API",
      outputs: "Policy enforcement, audit logs, risk scoring, execution traces",
      useCases: [
        "Tool allowlists + scope constraints",
        "Risk scoring + policy presets",
        "Decision stream + audit log",
        "Webhook-driven enforcement"
      ],
      description: "Policy enforcement for tool calls. Audit logs and approvals. Scope and risk gating. Safe execution with traces."
    },
    {
      title: "Pre-Deployment Validation",
      riskDomain: "Simulation & Digital Twins",
      status: "Testing & research mode",
      governanceStatus: "Not Applicable",
      insurabilityReadiness: "N/A",
      runtime: "Local CPU",
      outputs: "System validation, model refinement",
      useCases: [
        "System validation",
        "Model refinement",
        "Research & development"
      ],
      description: "Validation environments for testing governance frameworks before real-world deployment. Not subject to EOA requirements."
    }
  ];

  const compatibilityTable = [
    { platform: "Humanoids", transport: "gRPC Stream", cpuGpu: "CPU", mode: "Real-time", status: "Prod" },
    { platform: "UAV/Drones", transport: "REST Batch", cpuGpu: "Edge ARM", mode: "Episodic", status: "Beta" },
    { platform: "Wearables", transport: "Local ML", cpuGpu: "ARM/Micro", mode: "On-device", status: "In Dev" },
    { platform: "Smart Home", transport: "Cloud → Local", cpuGpu: "Mixed", mode: "Hybrid", status: "Alpha" },
    { platform: "Simulation", transport: "Local CPU", cpuGpu: "HPC/Cluster", mode: "Offline", status: "Active" },
  ];

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Platforms | EDON Governance for Agents and Physical AI"
        description="EDON is the runtime governance and control layer for autonomous agents and physical AI systems. Governance frameworks for humanoids, drones, wearables, environments, and autonomous agents."
        keywords="EDON platforms, autonomous agents, physical AI governance, deployment authorization by system type, insurability readiness"
        canonical="https://edoncore.com/platforms"
      />
      {/* Header */}
      <Navigation />
      <section className="px-6 pt-28" id="platforms">
        <div className="mx-auto w-full max-w-6xl">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h1 className="font-sans text-4xl md:text-5xl font-semibold text-black mb-4">
              Platforms
            </h1>
            <p className="font-sans text-lg text-gray-600 max-w-3xl mb-4">
              EDON is the runtime governance and control layer for autonomous agents and physical AI systems.
            </p>
            <p className="font-sans text-base text-gray-500 max-w-3xl mb-6">
              Governance frameworks organized by risk class and system type.
            </p>
            <div className="bg-white border border-gray-200 rounded-2xl p-6 max-w-4xl shadow-sm">
              <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-4">Institutional Summary</p>
              <div className="grid gap-3 text-sm text-gray-700">
                <p><strong>Governance Status:</strong> Indicates whether Operational Authorization (EOA) is available for deployment in this risk domain.</p>
                <p><strong>Insurability Readiness:</strong> Indicates whether systems in this domain meet standards suitable for insurance underwriting.</p>
                <p><strong>Risk Classification:</strong> Systems are organized by proximity to humans, kinetic energy, and operational scale.</p>
                <p><strong>Deployment Authorization:</strong> Each domain has specific governance requirements that must be met before operational authorization is granted.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Platform Tiers */}
      <section className="py-16 px-6 bg-white">
        <div className="max-w-6xl mx-auto">
          <div className="space-y-16">
            {platforms.map((platform, index) => (
              <div 
                key={index} 
                id={platform.riskDomain === "Autonomous Agents" ? "agents" : undefined}
                className="border border-gray-200 rounded-3xl p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)] scroll-mt-32"
              >
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                  <div className="lg:col-span-2">
                    <div className="flex flex-wrap items-center gap-3 mb-4">
                      <h2 className="font-sans text-2xl md:text-3xl font-bold text-black">
                        {platform.title}
                      </h2>
                      <span className={`px-3 py-1 rounded-full text-xs font-sans uppercase tracking-widest ${
                        platform.status.includes("Fully") ? "bg-green-100 text-green-800" :
                        platform.status.includes("Framework available") ? "bg-blue-100 text-blue-800" :
                        platform.status.includes("Supported") ? "bg-blue-100 text-blue-800" :
                        "bg-gray-100 text-gray-800"
                      }`}>
                        {platform.status}
                      </span>
                    </div>
                    {platform.riskDomain && (
                      <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-2">
                        Risk Domain: {platform.riskDomain}
                      </p>
                    )}
                    <p className="font-sans text-base text-gray-700 mb-6 leading-relaxed">
                      {platform.description}
                    </p>
                    <div className="flex flex-wrap gap-2 mb-6">
                      <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
                        {platform.governanceStatus}
                      </span>
                      <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
                        {platform.insurabilityReadiness}
                      </span>
                    </div>
                    <div>
                      <span className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-2 block">Use Cases</span>
                      <div className="flex flex-wrap gap-2">
                        {platform.useCases.map((useCase, i) => (
                          <span key={i} className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
                            {useCase}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="bg-[#f4f4f4] border border-gray-200 rounded-2xl p-6">
                    <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-4">Runtime + Outputs</p>
                    <div className="space-y-3 text-sm text-gray-700">
                      <p><strong>Runtime:</strong> {platform.runtime}</p>
                      <p><strong>Outputs:</strong> {platform.outputs}</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Governance Status Summary */}
      <section className="bg-white py-16 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="font-sans text-3xl font-bold text-black mb-8">
            Governance Status by Risk Domain
          </h2>
          <div className="bg-white border border-gray-200 rounded-3xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-4 text-left font-sans text-sm font-semibold text-black uppercase tracking-widest">Risk Domain</th>
                  <th className="px-6 py-4 text-left font-sans text-sm font-semibold text-black uppercase tracking-widest">Governance Status</th>
                  <th className="px-6 py-4 text-left font-sans text-sm font-semibold text-black uppercase tracking-widest">Insurability Readiness</th>
                  <th className="px-6 py-4 text-left font-sans text-sm font-semibold text-black uppercase tracking-widest">Framework Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {platforms.filter(p => p.riskDomain).map((platform, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-sans text-gray-900 font-medium">{platform.riskDomain}</td>
                    <td className="px-6 py-4 font-sans text-gray-700">{platform.governanceStatus}</td>
                    <td className="px-6 py-4 font-sans text-gray-700">{platform.insurabilityReadiness}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs font-sans uppercase tracking-widest ${
                        platform.status.includes("Fully") ? "bg-green-100 text-green-800" :
                        platform.status.includes("Framework available") ? "bg-blue-100 text-blue-800" :
                        platform.status.includes("Supported") ? "bg-blue-100 text-blue-800" :
                        "bg-gray-100 text-gray-800"
                      }`}>
                        {platform.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-8">
            <p className="font-sans text-sm text-gray-600">
              Technical implementation details and evaluation access are available for approved OEM partners. <Link to="/contact" className="text-tactical-cyan hover:underline">Contact us</Link> for more information.
            </p>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Platforms;

