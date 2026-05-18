import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { useLocation, Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";

const Docs = () => {
  const location = useLocation();
  const [activeSection, setActiveSection] = useState("overview");
  const { isSignedIn } = useAuth();

  useEffect(() => {
    // If on /docs/api route, set active section to API
    if (location.pathname === "/docs/api") {
      setActiveSection("api");
    }
  }, [location.pathname]);

  const publicSections = [
    { id: "overview", label: "Governance Overview" },
    { id: "eoa", label: "Authorization Model" },
    { id: "rao", label: "Runtime Oversight" },
    { id: "autonomy-state", label: "Autonomy State Machine" },
    { id: "enforcement", label: "Enforcement Logic" },
    { id: "incident", label: "Incident Handling" },
    { id: "audit", label: "Audit & Evidence" },
  ];

  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="Governance & Standards Documentation | EDON"
        description="EDON governance and standards documentation: deployment authorization, runtime oversight, incident handling, and audit requirements for physical AI systems."
        keywords="EDON governance, deployment authorization, runtime oversight, physical AI standards, EOA, RAO"
        canonical="https://edoncore.com/docs"
      />
      <Navigation />
      
      {/* Header */}
      <section className="px-6 pt-28 pb-10">
        <div className="max-w-6xl mx-auto">
          <div className="rounded-3xl bg-[#f4f4f4] p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            <h1 className="font-sans text-3xl md:text-4xl font-semibold text-black mb-4">
              Governance & Standards Documentation
            </h1>
            <div className="bg-white border-l-[3px] border-tactical-cyan pl-4 py-3 mb-4">
              <p className="font-sans text-sm text-[#555] leading-relaxed">
                This documentation describes the governance, authorization, and technical enforcement mechanisms of EDON for approved evaluators and integration partners.
              </p>
            </div>
            <p className="font-sans text-sm text-gray-500 italic">
              Technical integration documentation is available to approved evaluators and OEM partners.
            </p>
          </div>
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-6 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-10">
          {/* Sidebar Navigation */}
          <aside className="lg:col-span-1">
            <nav className="sticky top-24 space-y-1 bg-white border border-gray-200 rounded-3xl p-4 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
              {/* Public Sections */}
              <div className="mb-6">
                <p className="px-4 py-2 text-[0.7rem] font-sans font-semibold text-gray-500 uppercase tracking-[0.08em] mb-2">
                  PUBLIC
                </p>
                {publicSections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full text-left px-4 py-2 text-xs font-sans transition-colors ${
                      activeSection === section.id
                        ? "bg-gray-100 text-black font-semibold border-l-2 border-tactical-cyan"
                        : "text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    {section.label}
                  </button>
                ))}
              </div>

            </nav>
          </aside>

          {/* Main Content */}
          <main className="lg:col-span-3 max-w-[760px] bg-white border border-gray-200 rounded-3xl p-6 md:p-8 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
            {activeSection === "overview" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    What EDON is
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    EDON is the deployment and governance layer for physical AI systems. It enforces runtime governance, safety boundaries, and insurability requirements through operational authorization and continuous oversight.
                  </p>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    EDON answers three questions: Can this system be deployed? Can it be insured? Can it be governed after failure?
                  </p>
                  <div className="border-t border-gray-200 my-8"></div>
                  <p className="font-sans text-base text-gray-600 leading-[1.65]">
                    Technical capabilities exist solely to enforce governance outcomes and are documented as implementation details.
                  </p>
                </div>

                <div className="mt-12 mb-12">
                  <h3 className="font-sans text-2xl font-semibold text-black mb-6">
                    Core Concepts
                  </h3>
                  <div className="space-y-4">
                    <div className="bg-[#fafafa] border-l-4 border-tactical-cyan rounded-md p-5">
                      <h4 className="font-sans font-semibold text-black mb-2">CAV (Contextual Awareness Vector)</h4>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Internal state representation used to enforce autonomy boundaries and detect unsafe deviation.
                      </p>
                    </div>
                    <div className="bg-[#fafafa] border-l-4 border-tactical-cyan rounded-md p-5">
                      <h4 className="font-sans font-semibold text-black mb-2">State Engine</h4>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Governance computation pipeline that evaluates state and enforces runtime constraints.
                      </p>
                    </div>
                    <div className="bg-[#fafafa] border-l-4 border-tactical-cyan rounded-md p-5">
                      <h4 className="font-sans font-semibold text-black mb-2">Baseline Memory</h4>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Adaptive reference model used to identify abnormal behavior requiring intervention.
                      </p>
                    </div>
                  </div>
                  <p className="font-sans text-sm text-gray-500 italic mt-6 leading-[1.65]">
                    These mechanisms exist to support authorization, oversight, and post-incident control.
                  </p>
                </div>

                <div>
                  <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                    Integration
                  </h3>
                  <p className="font-sans text-base text-gray-700 leading-[1.65]">
                    Integration instructions and SDKs are available to approved partners in the Integration section.
                  </p>
                </div>
              </div>
            )}

            {activeSection === "governance" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Runtime Governance Model
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    EDON's governance model operates independently of task planning and control, regulating how autonomy is exercised under uncertainty.
                  </p>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    The governance layer answers: <strong>Given current system state and uncertainty, what level of autonomous behavior is acceptable at this moment?</strong>
                  </p>
                  <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6 mb-6">
                    <h3 className="font-sans font-semibold text-black mb-3">Governance Placement</h3>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">Mission / Task Planning (what the system is trying to do)</p>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">───────────────</p>
                    <p className="font-sans text-black font-semibold mb-2">Runtime Autonomy Oversight (RAO)</p>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">• Governed Autonomy</p>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">• Autonomy State Ledger</p>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">• Risk Modulation Envelope</p>
                    <p className="font-sans text-gray-700 leading-[1.65] mb-2">───────────────</p>
                    <p className="font-sans text-gray-700 leading-[1.65]">Control & Actuation (how actions are physically executed)</p>
                  </div>
                  <p className="font-sans text-base text-gray-700 leading-[1.65]">
                    Governance operates between intent and execution, regulating how autonomy is exercised under uncertainty.
                  </p>
                </div>
              </div>
            )}

            {activeSection === "eoa" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    EDON Operational Authorization (EOA)
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    EOA is a binary deployment authorization that determines whether a physical AI system may operate in autonomous or semi-autonomous modes within real-world environments.
                  </p>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    EOA exists to provide institutions, operators, and insurers with a clear, enforceable determination of whether a physical AI system is operating within an insurable and institutionally defensible configuration.
                  </p>
                  <div className="space-y-6">
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Conditions Required for EOA</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        EOA may be granted only when all of the following conditions are met:
                      </p>
                      <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                        <li>• System boundaries are explicitly defined, documented, and enforced</li>
                        <li>• Safety envelopes are active and cannot be overridden by autonomous logic</li>
                        <li>• Autonomy levels are discrete, bounded, and logged</li>
                        <li>• Human override authority is available and effective at all times</li>
                        <li>• Runtime monitoring and logging are active and auditable</li>
                        <li>• Liability boundaries between system provider and operator are defined</li>
                        <li>• The system is operating within the minimum insurable configuration</li>
                      </ul>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Granting and Scope</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        EOA is granted at the deployment level, not the company level. Authorization applies to a specific system configuration, a defined operating environment, and approved autonomy modes.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        EOA does not automatically transfer to other configurations, environments, or deployments. Authorization remains valid only while the system continues to operate within the authorized configuration.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Suspension and Revocation</h3>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        EOA may be suspended or revoked in response to safety incidents indicating potential systemic risk, detection of operation outside approved conditions, loss of auditability or control, or failure to comply with incident response requirements. Suspension requires immediate restriction or halt of affected autonomy modes.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "rao" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Runtime Autonomy Oversight (RAO)
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    RAO is the continuous, real-time oversight of autonomous physical systems that regulates how autonomy is exercised under uncertainty, independent of task planning and low-level control.
                  </p>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    RAO answers a single operational question: Given current system state and uncertainty, what level of autonomous behavior is acceptable at this moment?
                  </p>
                  <div className="space-y-6">
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Autonomy State Ledger</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        A continuous system-of-record capturing system state, assessed risk levels, oversight actions taken, and transitions between autonomy modes at runtime.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        The ledger enables reconstruction of autonomous decisions, regulatory and insurance review, attribution of responsibility, and accountability without requiring human presence at the moment of action.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Risk Modulation Envelope</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        A dynamic boundary within which autonomous behavior is continuously adjusted to maintain acceptable system risk. Rather than relying on binary shutdowns, the envelope regulates speed, force, task concurrency, and autonomy confidence.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Under increasing uncertainty, governed systems contract their operational envelope rather than fail abruptly, enabling graceful degradation while preserving continuity of service.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">System-Level Implications</h3>
                      <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                        <li>• <strong>Insurability:</strong> RAO converts autonomous operation from opaque exposure into bounded, documented risk, reducing uncertainty for underwriters</li>
                        <li>• <strong>Regulatory accountability:</strong> RAO provides a clear locus of operational accountability through traceable decision records and enforceable behavioral constraints</li>
                        <li>• <strong>Enterprise scalability:</strong> By governing system-level interactions, RAO enables multi-vendor autonomous systems to scale beyond pilots and isolated deployments</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "autonomy-state" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Autonomy State Machine
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    EDON enforces discrete, bounded autonomy levels. Each level specifies permitted actions, required human supervision, and conditions for transitions.
                  </p>
                  <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm mb-6">
                    <h3 className="font-sans font-semibold text-black mb-4">State Transitions</h3>
                    <ul className="space-y-2 font-sans text-gray-700">
                      <li>• All transitions between autonomy levels are logged and attributable</li>
                      <li>• States are discrete and finite—continuous or undefined states are not acceptable</li>
                      <li>• Each state defines conditions under which the system must halt or degrade to a safe state</li>
                      <li>• Human override authority is available and effective at all times</li>
                    </ul>
                  </div>
                  <p className="font-sans text-base text-gray-700 leading-[1.65]">
                    The autonomy state machine ensures systems operate within approved boundaries and provides clear audit trails for all mode changes.
                  </p>
                </div>
              </div>
            )}

            {activeSection === "enforcement" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Enforcement Logic
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    How does EDON actually stop something from happening?
                  </p>
                  <div className="space-y-6">
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Safety Envelope Enforcement</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        Safety envelopes define maximum allowable speed, force, torque, or energy output. These are enforced at runtime and cannot be overridden by autonomous decision making.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        If a system cannot enforce safety envelopes independently of its intelligence layer, it does not meet deployment standards.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Risk Modulation</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        Under increasing uncertainty, governed systems contract their operational envelope rather than fail abruptly. This regulates speed, force, task concurrency, and autonomy confidence.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Graceful degradation preserves continuity of service while maintaining safety boundaries.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Boundary Enforcement</h3>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        System boundaries are explicitly defined, documented, and enforced. Operation outside the defined boundary is considered out of scope and invalidates operational authorization.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "incident" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Incident Freeze and Rollback
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    When an incident is detected, EDON provides immediate containment and evidence preservation.
                  </p>
                  <div className="space-y-4">
                    <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm">
                      <h3 className="font-sans font-semibold text-black mb-3">Immediate Containment</h3>
                      <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                        <li>• Similar behaviors are immediately contained across all deployed systems</li>
                        <li>• Autonomy modes implicated in an incident are suspended or restricted</li>
                        <li>• System state is frozen for evidence capture</li>
                      </ul>
                    </div>
                    <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm">
                      <h3 className="font-sans font-semibold text-black mb-3">Evidence Preservation</h3>
                      <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                        <li>• Time-stamped system state at decision points</li>
                        <li>• Relevant sensor inputs at decision time</li>
                        <li>• Commands issued and actions taken</li>
                        <li>• Active autonomy level and transitions</li>
                        <li>• Override or intervention events</li>
                      </ul>
                    </div>
                    <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm">
                      <h3 className="font-sans font-semibold text-black mb-3">Prevention of Recurrence</h3>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Incident response focuses on system correction, not attribution of legal fault. The goal is preventing recurrence through operational restrictions or configuration changes.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "audit" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Audit and Evidence Capture
                  </h2>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    EDON maintains continuous runtime monitoring and logging sufficient to reconstruct system behavior after an incident.
                  </p>
                  <div className="space-y-6">
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Autonomy State Ledger</h3>
                      <p className="font-sans text-gray-700 leading-[1.65] mb-2">
                        A continuous system-of-record capturing system state, assessed risk levels, oversight actions taken, and transitions between autonomy modes at runtime.
                      </p>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        The ledger enables reconstruction of autonomous decisions, regulatory and insurance review, attribution of responsibility, and accountability without requiring human presence at the moment of action.
                      </p>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Log Requirements</h3>
                      <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                        <li>• Logs must be tamper-resistant and retained according to institutional and insurance requirements</li>
                        <li>• Systems that cannot produce auditable evidence of behavior do not meet deployment standards</li>
                        <li>• Logs must enable reconstruction of system behavior after an incident</li>
                      </ul>
                    </div>
                    <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6">
                      <h3 className="font-sans font-semibold text-black mb-3">Audit Readiness</h3>
                      <p className="font-sans text-gray-700 leading-[1.65]">
                        Deployments must be capable of demonstrating compliance with governance standards at any time through documentation of configuration, evidence of runtime enforcement, access to logs and monitoring data, and clear responsibility assignment.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "api" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-2">
                    API Reference
                  </h2>
                  <p className="font-sans text-base text-gray-600 mb-8">
                    Implementation of EDON governance and authorization decisions
                  </p>
                  
                  <div className="bg-yellow-50 border-l-4 border-yellow-500 p-4 mb-8">
                    <p className="font-sans text-sm text-gray-700 leading-[1.65]">
                      This API implements EDON's authorization and runtime governance decisions. It does not grant permission to operate independently.
                    </p>
                  </div>

                  {!isSignedIn ? (
                    <div className="space-y-6">
                      <p className="font-sans text-base text-gray-700 leading-[1.65]">
                        Full API reference documentation is available to approved partners after authentication.
                      </p>
                      <div className="flex gap-4">
                        <Link to="/login">
                          <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                            Log In
                          </Button>
                        </Link>
                        <Link to="/contact">
                          <Button variant="tactical-outline" size="lg" className="font-sans tracking-wider">
                            Request Access
                          </Button>
                        </Link>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-8">
                      <div>
                        <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                          REST v2
                        </h3>
                        <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm mb-4">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="bg-tactical-cyan text-white px-2 py-1 text-xs font-mono">POST</span>
                            <code className="font-mono text-sm text-black">/v2/oem/cav/batch</code>
                          </div>
                          <p className="font-sans text-sm text-gray-600 mb-4">Compute CAV from batch sensor data</p>
                          <div className="space-y-3">
                            <div>
                              <p className="font-sans text-xs text-gray-500 uppercase mb-1">Request Schema</p>
                              <pre className="bg-black text-green-400 p-3 rounded-sm overflow-x-auto text-xs font-mono">
{`{
  "signals": {
    "physio": [float],
    "motion": [float],
    "environment": [float]
  }
}`}
                              </pre>
                            </div>
                            <div>
                              <p className="font-sans text-xs text-gray-500 uppercase mb-1">Response</p>
                              <pre className="bg-black text-green-400 p-3 rounded-sm overflow-x-auto text-xs font-mono">
{`{
  "cav_vector": [float],
  "state_classification": "authorized|constrained|restricted|suspended",
  "regulation_outputs": {
    "speed_scale": 0.0-1.0,
    "torque_limit": 0.0-1.0,
    "alert_level": 0.0-1.0
  },
  "timestamp": "ISO8601"
}`}
                              </pre>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                          gRPC Service
                        </h3>
                        <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm">
                          <code className="font-mono text-sm text-black">ComputeCavBatchV2()</code>
                          <p className="font-sans text-sm text-gray-600 mt-2 leading-[1.65]">
                            Streaming gRPC service for real-time CAV computation. Supports bidirectional streaming for continuous state updates.
                          </p>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                          WebSocket Streams
                        </h3>
                        <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm">
                          <code className="font-mono text-sm text-black">/v2/stream/cav</code>
                          <p className="font-sans text-sm text-gray-600 mt-2 leading-[1.65]">
                            Real-time streaming endpoint for continuous CAV updates. Maintains persistent connection for high-frequency state monitoring.
                          </p>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                          Telemetry + Health Endpoints
                        </h3>
                        <div className="space-y-2 font-mono text-sm">
                          <div className="flex items-center gap-2">
                            <span className="bg-gray-200 text-black px-2 py-1 text-xs">GET</span>
                            <code className="text-black">/v2/health</code>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="bg-gray-200 text-black px-2 py-1 text-xs">GET</span>
                            <code className="text-black">/v2/telemetry</code>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="bg-gray-200 text-black px-2 py-1 text-xs">GET</span>
                            <code className="text-black">/v2/metrics</code>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeSection === "sdks" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-2">
                    SDKs
                  </h2>
                  <p className="font-sans text-base text-gray-600 mb-8">
                    Governance Enforcement Libraries
                  </p>
                  
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-6">
                    EDON SDKs are used to embed runtime governance, authorization enforcement, and audit capture into physical AI systems.
                  </p>

                  <div className="bg-[#f6f7f9] border-l-[3px] border-tactical-cyan pl-4 py-3 mb-8">
                    <p className="font-sans text-sm text-[#555] leading-[1.65]">
                      SDKs are provided only to approved partners to preserve deployment integrity and insurability.
                    </p>
                  </div>

                  <div className="flex gap-4">
                    {!isSignedIn ? (
                      <Link to="/login">
                        <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                          Log In
                        </Button>
                      </Link>
                    ) : (
                      <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                        Access SDKs
                      </Button>
                    )}
                    <Link to="/contact">
                      <Button variant="tactical-outline" size="lg" className="font-sans tracking-wider">
                        Request Access
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "architecture" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-2">
                    Model Architecture
                  </h2>
                  <p className="font-sans text-base text-gray-600 mb-8">
                    Governance Enforcement Overview
                  </p>
                  
                  <div className="bg-gray-50 border border-gray-200 p-8 rounded-sm mb-8">
                    <h3 className="font-sans font-semibold text-black mb-6">High-Level Architecture</h3>
                    <div className="space-y-4">
                      <div className="flex items-center gap-4">
                        <div className="bg-white border-2 border-gray-300 px-6 py-4 rounded-sm min-w-[200px] text-center">
                          <p className="font-sans text-sm font-semibold text-black">Sensor Inputs</p>
                        </div>
                        <div className="text-gray-400 text-xl">→</div>
                        <div className="bg-white border-2 border-gray-300 px-6 py-4 rounded-sm min-w-[200px] text-center">
                          <p className="font-sans text-sm font-semibold text-black">State Assessment</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="bg-white border-2 border-gray-300 px-6 py-4 rounded-sm min-w-[200px] text-center">
                          <p className="font-sans text-sm font-semibold text-black">Authorization Gate</p>
                        </div>
                        <div className="text-gray-400 text-xl">→</div>
                        <div className="bg-white border-2 border-gray-300 px-6 py-4 rounded-sm min-w-[200px] text-center">
                          <p className="font-sans text-sm font-semibold text-black">Enforcement Outputs</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="bg-white border-2 border-gray-300 px-6 py-4 rounded-sm min-w-[200px] text-center">
                          <p className="font-sans text-sm font-semibold text-black">Audit Ledger</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-[#f6f7f9] border-l-[3px] border-tactical-cyan pl-4 py-3 mb-8">
                    <p className="font-sans text-sm text-[#555] leading-[1.65]">
                      Detailed fusion methods, state transition logic, and internal parameters are restricted to approved partners.
                    </p>
                  </div>

                  <Link to="/contact">
                    <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                      Request Access for Full Architecture
                    </Button>
                  </Link>
                </div>
              </div>
            )}

            {activeSection === "deployment" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-2">
                    Integration Documentation
                  </h2>
                  <p className="font-sans text-sm text-gray-500 uppercase tracking-widest mb-8">
                    Restricted to approved evaluators and OEM partners
                  </p>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-8">
                    These documents describe how EDON governance and authorization are integrated into physical AI systems during approved deployments and evaluations.
                  </p>
                  
                  <div className="bg-gray-50 border border-gray-200 p-6 rounded-sm mb-8">
                    <h3 className="font-sans font-semibold text-black mb-4">What's inside</h3>
                    <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                      <li>• Authorized deployment flows</li>
                      <li>• Runtime enforcement integration</li>
                      <li>• Incident handling hooks</li>
                      <li>• Audit signal wiring</li>
                    </ul>
                  </div>

                  <div className="bg-[#f6f7f9] border-l-[3px] border-tactical-cyan pl-4 py-3 mb-8">
                    <p className="font-sans text-sm text-[#555] leading-[1.65]">
                      Access is granted to organizations participating in an approved evaluation or deployment.
                    </p>
                  </div>

                  <Link to="/contact">
                    <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                      Request Access
                    </Button>
                  </Link>
                </div>
              </div>
            )}

            {activeSection === "security" && (
              <div className="space-y-12">
                <div className="mt-12 mb-12">
                  <h2 className="font-sans text-3xl font-semibold text-black mb-6">
                    Security & Licensing
                  </h2>
                </div>

                <div>
                  <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                    License-Enforced Authorization Model
                  </h3>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    EDON uses a license-enforced deployment model. Evaluation licenses are available for qualified OEMs and research partners. Enterprise licensing includes additional security features and deployment options.
                  </p>
                  <p className="font-sans text-base text-gray-700 leading-[1.65] mb-6">
                    License enforcement mechanisms are proprietary and designed to protect both EDON's intellectual property and OEM deployment security.
                  </p>
                </div>

                <div>
                  <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                    Authorization and Insurability
                  </h3>
                  <p className="font-sans text-lg text-gray-700 leading-[1.65] mb-4">
                    Operation without a valid EDON authorization places the system outside supported and insurable deployment. EDON licensing enforces governance integrity and cannot be bypassed without detection.
                  </p>
                  <div className="bg-gray-50 border-l-4 border-tactical-cyan p-6 mb-4">
                    <h4 className="font-sans font-semibold text-black mb-3">What Invalidates Authorization</h4>
                    <ul className="space-y-2 font-sans text-gray-700 leading-[1.65]">
                      <li>• Safety envelopes are disabled or modified</li>
                      <li>• Autonomy behavior exceeds approved boundaries</li>
                      <li>• Runtime logging is interrupted</li>
                      <li>• Unauthorized updates or changes are applied</li>
                      <li>• Operation occurs outside the defined system boundary</li>
                      <li>• License tampering or bypass attempts are detected</li>
                    </ul>
                  </div>
                  <p className="font-sans text-base text-gray-700 leading-[1.65]">
                    When authorization is invalidated, the system must immediately restrict or halt affected autonomy modes. Continued operation without valid authorization is outside the scope of insurable and institutionally approved deployment.
                  </p>
                </div>

                <div className="opacity-50 pointer-events-none">
                  <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                    Key Rotation Mechanisms
                  </h3>
                  <p className="font-sans text-base text-gray-700 leading-[1.65] mb-4">
                    [Restricted content: Key rotation mechanisms and cryptographic key management procedures are available to approved partners.]
                  </p>
                </div>

                <div className="opacity-50 pointer-events-none">
                  <h3 className="font-sans text-2xl font-semibold text-black mb-4">
                    Tamper Detection and Enforcement
                  </h3>
                  <p className="font-sans text-base text-gray-700 leading-[1.65] mb-4">
                    [Restricted content: Detailed tamper detection methods, enforcement failover behavior, and security audit procedures are available to approved partners.]
                  </p>
                </div>

                <div className="bg-[#f6f7f9] border-l-[3px] border-tactical-cyan pl-4 py-3 mb-6">
                  <p className="font-sans text-sm text-[#555] leading-[1.65]">
                    Detailed enforcement and key management documentation is available to approved partners.
                  </p>
                </div>

                <Link to="/contact">
                  <Button variant="tactical" size="lg" className="font-sans tracking-wider">
                    Request Access
                  </Button>
                </Link>
              </div>
            )}
          </main>
        </div>
      </div>

      <Footer />
      <ScrollToTop />
    </div>
  );
};

export default Docs;

