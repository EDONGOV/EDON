import React, { useState } from "react";
import Navigation from "@/components/Navigation";
import FooterDark from "@/components/FooterDark";
import ScrollToTop from "@/components/ScrollToTop";
import SEOHead from "@/components/SEOHead";
import { Button } from "@/components/ui/button";
import edonLogo from "@/assets/edon-logo.svg";

interface Standard {
  id: string;
  title: string;
  image: string;
  date: string;
  author: string;
  excerpt: string;
  content: string;
  version: string;
  definition: string;
}

const Standards = () => {
  const [selectedStandard, setSelectedStandard] = useState<Standard | null>(null);

  const standards: Standard[] = [
    {
      id: "minimum-insurable-standard",
      title: "Minimum Insurable Physical AI Deployment Standard",
      image: "/article-standard.jpg",
      date: "JANUARY 6, 2026",
      author: "Team EDON",
      version: "Version 0.1 · Public Draft",
      definition: "This document defines the minimum requirements for the safe, insurable, and institutionally defensible deployment of physical artificial intelligence systems.",
      excerpt: "This document defines the minimum requirements for the safe, insurable, and institutionally defensible deployment of physical artificial intelligence systems, establishing a neutral, auditable baseline for responsible deployment.",
      content: `Minimum Insurable Physical AI Deployment Standard

Version 0.1 (Public Draft)

Maintained by EDON

1. Purpose and Scope

This document defines the minimum requirements for the safe, insurable, and institutionally defensible deployment of physical artificial intelligence systems.

Physical AI systems are defined here as systems that use computational intelligence to perceive their environment, make decisions, and initiate physical actions in the real world.

The purpose of this standard is to establish a neutral, auditable baseline that enables institutions, operators, insurers, and other stakeholders to determine whether a physical AI system may be responsibly deployed in real-world environments.

This standard is not a product specification and does not mandate specific hardware, software models, or vendors. It defines operational and governance conditions under which physical AI systems may be considered deployable and insurable.

2. Design Principles

This standard is guided by the following principles: Prevention of systemic harm takes precedence over optimization or performance. Governance must operate at runtime, not solely through documentation. Authority and responsibility must be clearly assigned at all times. Systems must fail safely and predictably. Behavior must be reconstructable after an incident. Deployment conditions must be enforceable and auditable.

This standard assumes that physical AI systems will fail at some point. Its purpose is to ensure failures do not propagate, repeat, or remain unexplained.

3. System Boundary Definition

Every physical AI deployment must define a clear system boundary prior to operation.

The system boundary must specify: What physical components the AI system directly controls, what components it influences but does not control, what components remain under direct human or external system control, and the environments in which the system is permitted to operate.

Operation outside the defined system boundary is considered out of scope and is not covered under this standard.

System boundaries must be documented, versioned, and available for audit.

4. Safety Envelopes

Physical AI systems must operate within enforced safety envelopes that constrain physical behavior regardless of decision logic.

Safety envelopes must define: Maximum allowable speed, force, torque, or energy output. Minimum allowable distance from humans or restricted zones. Environmental constraints such as surface conditions, visibility, or congestion. Physical behaviors that are explicitly prohibited.

Safety envelopes must be enforced at runtime and must not be overridable by autonomous decision making.

If a system cannot enforce safety envelopes independently of its intelligence layer, it does not meet this standard.

5. Autonomy Levels and State Control

Physical AI systems must operate within clearly defined autonomy levels.

Each autonomy level must specify: The actions the system is permitted to perform, the level of human supervision required, the conditions under which autonomy may increase or decrease, and the conditions under which the system must halt or degrade to a safe state.

Autonomy levels must be discrete and finite. Continuous or undefined autonomy states are not acceptable under this standard.

All transitions between autonomy levels must be logged and attributable.

6. Human Authority and Override

All physical AI systems must maintain clear and immediate human authority.

This includes: A defined role or individual responsible for operational oversight, immediate ability to halt or disable autonomous behavior, clear precedence of human commands over system actions, and access controls to prevent unauthorized overrides.

If a system cannot be reliably stopped by an authorized human, it is not eligible for deployment under this standard.

7. Runtime Monitoring and Logging

Physical AI systems must maintain continuous runtime monitoring and logging sufficient to reconstruct system behavior after an incident.

Logs must include: Time-stamped system state, relevant sensor inputs at decision time, commands issued and actions taken, active autonomy level, and override or intervention events.

Logs must be tamper-resistant and retained according to institutional and insurance requirements.

Systems that cannot produce auditable evidence of behavior do not meet this standard.

8. Incident Response and Containment

Deployments must define an incident response process that prioritizes prevention of recurrence.

This includes: Immediate containment of similar behaviors across deployed systems, suspension or restriction of autonomy modes implicated in an incident, and preservation of evidence for technical review.

Incident response under this standard focuses on system correction, not attribution of legal fault.

9. Liability Separation

Deployments must clearly define responsibility boundaries between the system provider and the operator.

This includes: Conditions under which the system is responsible for autonomous actions, conditions under which the operator assumes responsibility, and explicit exclusions for operation outside approved configurations.

Ambiguous or undefined liability allocation is not compatible with this standard.

10. Minimum Insurable Configuration

This standard defines a minimum insurable configuration under which physical AI systems may be considered deployable.

A system meets the minimum insurable configuration only when: System boundaries are defined and enforced, safety envelopes are active, autonomy levels are constrained and logged, human override authority is available, and runtime logging is active and auditable.

Operation outside this configuration is considered non-compliant with this standard.

11. Audit and Review Readiness

Deployments must be capable of demonstrating compliance with this standard at any time.

This includes: Documentation of configuration and boundaries, evidence of runtime enforcement, access to logs and monitoring data, and clear responsibility assignment.

This standard is designed to support future regulatory alignment without requiring retroactive redesign.

12. Versioning and Evolution

This standard is expected to evolve as physical AI systems and deployment environments mature.

Changes to this standard will be versioned, documented, and publicly available.

Compliance is evaluated against the version in effect at the time of deployment authorization.

Closing Statement

The purpose of this standard is to enable physical AI systems to be deployed responsibly at scale.

By defining enforceable deployment conditions, this standard supports insurability, institutional trust, and long-term viability of physical AI in real-world environments.`
    },
    {
      id: "edon-operational-authorization",
      title: "EDON Operational Authorization (EOA)",
      image: "/article-eoa.jpg",
      date: "JANUARY 6, 2026",
      author: "Team EDON",
      version: "Version 0.1 · Public Draft",
      definition: "EOA is a binary deployment authorization that determines whether a physical AI system may operate in autonomous or semi-autonomous modes within real-world environments.",
      excerpt: "EOA is a binary deployment authorization that determines whether a physical AI system may operate in autonomous or semi-autonomous modes within real-world environments, providing institutions, operators, and insurers with a clear, enforceable determination. RAO / EOA apply to agents + robots. For agents: \"EOA = tool execution boundary\". For robots: \"EOA = actuator boundary\".",
      content: `EDON Operational Authorization (EOA)

Definition and Conditions

Version 0.1 (Public Draft)

Maintained by EDON

1. Purpose

EDON Operational Authorization (EOA) is a binary deployment authorization that determines whether a physical artificial intelligence system may operate in autonomous or semi-autonomous modes within real-world environments.

EOA exists to provide institutions, operators, and insurers with a clear, enforceable determination of whether a physical AI system is operating within an insurable and institutionally defensible configuration.

EOA is not a legal judgment, certification of performance, or endorsement of a specific technology. It is an operational authorization tied to runtime governance and risk containment.

2. What EOA Represents

EOA represents confirmation that a physical AI system is operating under the Minimum Insurable Physical AI Deployment Standard maintained by EDON.

EOA answers one question only: Is this system authorized to operate under defined safety, governance, and liability conditions?

EOA is either granted or not granted. There is no partial authorization.

3. Conditions Required for EOA

EOA may be granted only when all of the following conditions are met: System boundaries are explicitly defined, documented, and enforced. Safety envelopes are active and cannot be overridden by autonomous logic. Autonomy levels are discrete, bounded, and logged. Human override authority is available and effective at all times. Runtime monitoring and logging are active and auditable. Liability boundaries between system provider and operator are defined. The system is operating within the minimum insurable configuration.

Failure to meet any condition results in denial or suspension of EOA.

4. Granting of EOA

EOA is granted at the deployment level, not the company level.

Authorization applies to: A specific system configuration, a defined operating environment, and approved autonomy modes.

EOA does not automatically transfer to other configurations, environments, or deployments.

5. Duration and Scope

EOA remains valid only while the system continues to operate within the authorized configuration.

EOA is invalidated if: Safety envelopes are disabled or modified, autonomy behavior exceeds approved boundaries, runtime logging is interrupted, unauthorized updates or changes are applied, or operation occurs outside the defined system boundary.

6. Suspension and Revocation

EOA may be suspended or revoked in response to: A safety incident indicating potential systemic risk, detection of operation outside approved conditions, loss of auditability or control, or failure to comply with incident response requirements.

Suspension of EOA requires immediate restriction or halt of affected autonomy modes.

EOA enforcement is operational and preventative, not punitive.

7. Incident Review and Enforcement Separation

EOA operates alongside a neutral incident review process.

Incident review focuses on reconstructing system behavior and identifying systemic risk factors.

EOA enforcement focuses on preventing recurrence through operational restrictions or configuration changes.

EOA does not assign legal blame or liability.

8. Relationship to Insurance and Institutional Approval

EOA is designed to support insurance underwriting and institutional risk management.

EOA may be referenced by: Insurance policies, institutional deployment approvals, and procurement and safety reviews.

Operation without EOA is outside the scope of insurable and institutionally approved deployment under this framework.

9. Transparency and Auditability

EOA status must be demonstrable at any time through: Active runtime monitoring, accessible configuration records, and verifiable logging.

EOA exists to enable trust through evidence, not assertion.

10. Versioning

This definition is versioned and subject to evolution as physical AI systems and deployment environments mature.

EOA applies according to the version in effect at the time authorization is granted.

Closing Statement

EDON Operational Authorization exists to enable physical AI systems to operate safely, responsibly, and at scale.

By defining a clear deployment authorization tied to runtime governance and insurability, EOA provides a foundation for institutional trust and market stability in physical AI deployment.`
    },
    {
      id: "runtime-autonomy-oversight",
      title: "Runtime Autonomy Oversight (RAO)",
      image: "/article-rao.jpg",
      date: "JANUARY 6, 2026",
      author: "Team EDON",
      version: "Version 0.1 · Public Draft",
      definition: "A governance framework for scalable physical autonomy that regulates autonomous behavior in real time through the Autonomy State Ledger and Risk Modulation Envelope.",
      excerpt: "RAO enables Governed Autonomy through the Autonomy State Ledger and Risk Modulation Envelope, establishing a practical foundation for safe, insurable, and scalable physical autonomy.",
      content: `Runtime Autonomy Oversight (RAO)

A Governance Framework for Scalable Physical Autonomy

Executive Summary

Autonomous physical systems, including humanoid robots, mobile robots, automated warehouses, and other forms of physical AI, are rapidly advancing in capability and deployment scale. Despite this progress, widespread adoption remains constrained by operational instability, concentrated liability, and uncertainty around insurability and accountability.

These constraints do not primarily stem from failures in perception, planning, or control. Instead, they arise from system-level behavior under uncertainty, particularly when autonomous agents interact with dynamic environments, degraded sensing, and one another.

This paper introduces Runtime Autonomy Oversight (RAO)—a governance framework designed to regulate autonomous physical systems while they are operating, rather than relying solely on design-time policies, static safety rules, or post-incident analysis.

RAO enables Governed Autonomy through two core artifacts: the Autonomy State Ledger, and the Risk Modulation Envelope. Together, these mechanisms establish a practical, auditable foundation for safe, insurable, and scalable physical autonomy.

Why Runtime Governance Is Now Required

Early autonomous deployments operated in constrained environments with limited scale, single-vendor systems, and human fallback. Today's deployments increasingly involve: multi-vendor robotic fleets, continuous operation with minimal human presence, shared physical environments, and economic pressure to maximize utilization.

At this scale, failures are rarely attributable to a single component. Instead, they emerge from interaction effects under uncertainty, including sensor degradation, congestion, partial system faults, and feedback loops across autonomous agents.

Static safety rules and binary shutdown mechanisms are insufficient in these conditions. They either fail to prevent cascading degradation or impose excessive downtime that undermines economic viability.

As a result, autonomy now faces an insurability and accountability gap: systems may function technically, but lack mechanisms to demonstrate how risk is regulated in real time.

Runtime Autonomy Oversight (RAO)

Definition

Runtime Autonomy Oversight (RAO) is the continuous, real-time oversight of autonomous physical systems that regulates how autonomy is exercised under uncertainty, independent of task planning and low-level control.

RAO answers a single operational question: Given current system state and uncertainty, what level of autonomous behavior is acceptable at this moment?

Scope and Placement

RAO operates: below mission and task planning, and above control and actuation. It does not decide what the system is trying to do, nor how individual motions are executed. Instead, it governs how aggressively, confidently, and concurrently autonomy is allowed to operate as conditions change.

Governed Autonomy

Governed Autonomy refers to autonomous behavior whose actions are continuously constrained, modulated, and auditable through an independent oversight layer.

In governed autonomy: autonomy is not binary, system behavior adapts smoothly to rising or falling risk, and decisions remain explainable after the fact.

By contrast, autonomous systems lacking runtime oversight rely on static thresholds, predefined exception handling, or emergency shutdowns. While sufficient for pilots, such systems exhibit brittle behavior at scale, concentrate liability, and undermine insurability.

Governed autonomy addresses these limitations through continuous regulation rather than episodic intervention.

Governance Artifacts

Runtime Autonomy Oversight is made operational through two concrete artifacts.

Autonomy State Ledger

The Autonomy State Ledger is a continuous system-of-record capturing: system state, assessed risk levels, oversight actions taken, and transitions between autonomy modes at runtime.

The ledger enables reconstruction of autonomous decisions, regulatory and insurance review, attribution of responsibility, and accountability without requiring human presence at the moment of action.

Without an autonomy state ledger, autonomous behavior cannot be meaningfully audited, governed, or insured.

Risk Modulation Envelope

The Risk Modulation Envelope is a dynamic boundary within which autonomous behavior is continuously adjusted to maintain acceptable system risk.

Rather than relying on binary shutdowns, the envelope regulates: speed, force, task concurrency, and autonomy confidence.

Under increasing uncertainty, governed systems contract their operational envelope rather than fail abruptly, enabling graceful degradation while preserving continuity of service.

Illustrative Scenario

Consider a fully autonomous warehouse operating without human supervision. During peak operation, partial sensor degradation and localized congestion emerge simultaneously.

In an ungoverned system, task planners continue issuing commands optimized for nominal conditions until safety thresholds are breached, triggering widespread shutdown.

Under Runtime Autonomy Oversight: rising uncertainty is detected at the system level, the risk modulation envelope contracts, robot speed and task concurrency are reduced, autonomy confidence is lowered without halting operations, and all oversight actions are recorded in the autonomy state ledger.

Operations continue at reduced capacity without catastrophic interruption, while remaining auditable and defensible.

System-Level Implications

Insurability. RAO converts autonomous operation from opaque exposure into bounded, documented risk, reducing uncertainty for underwriters and enabling coverage otherwise unavailable.

Regulatory accountability. RAO provides a clear locus of operational accountability through traceable decision records and enforceable behavioral constraints, supporting oversight without prohibiting autonomy.

Enterprise scalability. By governing system-level interactions, RAO enables multi-vendor autonomous systems to scale beyond pilots and isolated deployments.

Non-Goals and Clarifications

Runtime Autonomy Oversight: does not replace OEM safety systems, does not remove human or organizational accountability, and does not certify task intent or ethical alignment.

RAO governs execution under uncertainty, complementing existing safety, planning, and compliance mechanisms.

Conclusion

As physical AI systems proliferate, the limiting factor for deployment is no longer intelligence, but governance.

Runtime Autonomy Oversight establishes the missing layer required to regulate autonomous behavior in real time, enabling governed autonomy through auditable records and continuous risk modulation.

Autonomy that cannot be governed at runtime cannot scale responsibly.

Conceptual Placement

Mission / Task Planning (what the system is trying to do)

───────────────

Runtime Autonomy Oversight
• Governed Autonomy
• Autonomy State Ledger
• Risk Modulation Envelope

───────────────

Control & Actuation (how actions are physically executed)

Governance operates between intent and execution, regulating how autonomy is exercised under uncertainty.`
    }
  ];

  // If a standard is selected, show the detailed view
  if (selectedStandard) {
    return (
      <div className="min-h-screen bg-white font-sans">
        <SEOHead
          title={`${selectedStandard.title} | EDON Standards`}
          description={selectedStandard.excerpt}
          keywords="EDON standards, physical AI governance, deployment authorization, runtime oversight"
          canonical={`https://edoncore.com/standards/${selectedStandard.id}`}
        />
        <Navigation />
        
        <div className="pt-24 pb-24 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
              {/* Left Sidebar - Author Info */}
              <div className="lg:col-span-3">
                <div className="sticky top-24">
                  <div className="flex flex-col items-start gap-6">
                    {/* Author Icon - EDON Logo */}
                    <div className="w-16 h-16 rounded-full bg-gray-900 flex items-center justify-center p-2">
                      <img src={edonLogo} alt="EDON" className="w-full h-full object-contain" />
                    </div>
                    
                    <div className="flex flex-col gap-2">
                      <p className="font-sans text-xs tracking-widest text-gray-500 uppercase">AUTHOR</p>
                      <p className="font-sans text-lg font-medium text-black">{selectedStandard.author}</p>
                      <p className="font-sans text-xs tracking-widest text-gray-500 uppercase mt-4">{selectedStandard.date}</p>
                    </div>
                    
                    <Button
                      onClick={() => setSelectedStandard(null)}
                      className="bg-gray-900 hover:bg-gray-800 active:bg-gray-700 text-white rounded-lg px-6 py-3 font-sans text-xs tracking-widest uppercase w-full mt-2 transition-all duration-200"
                    >
                      BACK TO STANDARDS
                    </Button>
                  </div>
                </div>
              </div>

              {/* Main Content */}
              <div className="lg:col-span-9">
                <h1 className="font-sans text-4xl md:text-5xl lg:text-6xl font-bold text-black mb-12 leading-tight">
                  {selectedStandard.title}
                </h1>
                
                <div className="max-w-3xl">
                  <div className="font-sans text-base md:text-lg text-gray-800 leading-relaxed space-y-6">
                    {selectedStandard.content.split('\n\n').map((paragraph, index) => {
                      // Check if paragraph is a heading (all caps or starts with specific patterns)
                      const isHeading = paragraph.length < 100 && (
                        paragraph === paragraph.toUpperCase() || 
                        paragraph.match(/^(How|Why|What|The|If|1\.|2\.|3\.|4\.|5\.|6\.|7\.|8\.|9\.|10\.|11\.|12\.)/)
                      );
                      
                      return (
                        <p 
                          key={index} 
                          className={isHeading ? 'font-bold text-black text-xl md:text-2xl mb-4 mt-8' : 'text-gray-800'}
                        >
                          {paragraph}
                        </p>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <FooterDark />
        <ScrollToTop />
      </div>
    );
  }

  // Show standards listing
  return (
    <div className="min-h-screen bg-white font-sans">
      <SEOHead
        title="EDON Standards | Governance Framework for Agents and Physical AI"
        description="EDON is the runtime governance and control layer for autonomous agents and physical AI systems. Standards: Minimum Insurable Standard, Operational Authorization (EOA), and Runtime Autonomy Oversight (RAO)."
        keywords="EDON standards, autonomous agents, physical AI standards, deployment governance, EOA, RAO"
        canonical="https://edoncore.com/standards"
      />
      <Navigation />
      
      {/* Hero Section */}
      <section className="pt-32 pb-16 px-6 bg-[#f7f8fa]">
        <div className="max-w-7xl mx-auto">
          <h1 className="font-sans text-4xl md:text-6xl font-bold text-black mb-4">
            Standards
          </h1>
          <p className="font-sans text-xl text-gray-600 max-w-3xl mb-6">
            Deployment and governance framework for physical AI systems.
          </p>
          <p className="font-sans text-sm text-gray-500 max-w-3xl leading-[1.65]">
            These standards define deployment, governance, and insurability conditions for physical AI systems. They do not replace statutory regulation or assign legal fault.
          </p>
          <div className="mt-6 bg-gray-50 border-l-4 border-tactical-cyan p-4 max-w-3xl">
            <p className="font-sans text-sm text-gray-700 leading-relaxed">
              <strong>RAO / EOA apply to agents + robots.</strong> For agents: "EOA = tool execution boundary". For robots: "EOA = actuator boundary".
            </p>
          </div>
        </div>
      </section>

      {/* Standards List */}
      <section className="pb-16 px-6 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="grid gap-6">
            {standards.map((standard, index) => (
              <article
                key={standard.id}
                className="border border-gray-200 rounded-2xl p-6 md:p-8 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex flex-col gap-4">
                  {/* Date */}
                  <p className="font-sans text-xs text-gray-500 uppercase tracking-wider">
                    {standard.date}
                  </p>
                  
                  {/* Title */}
                  <h2 className="font-sans text-2xl md:text-3xl font-bold text-black leading-tight">
                    {standard.title}
                  </h2>
                  
                  {/* Definition */}
                  <p className="font-sans text-base text-gray-700 leading-[1.65]">
                    {standard.definition}
                  </p>
                  
                  {/* Version */}
                  <p className="font-sans text-sm text-gray-500">
                    {standard.version}
                  </p>
                  
                  {/* Read Standard Link */}
                  <div className="pt-2">
                    <a
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedStandard(standard);
                      }}
                      className="font-sans text-sm text-tactical-cyan hover:text-tactical-cyan/80 underline cursor-pointer uppercase tracking-wide transition-colors inline-block"
                    >
                      READ STANDARD →
                    </a>
                  </div>
                  
                  {/* Referenced By */}
                  <div className="pt-4 mt-2 border-t border-gray-100">
                    <p className="font-sans text-xs text-gray-400 uppercase tracking-wider mb-2">
                      Referenced by
                    </p>
                    <p className="font-sans text-sm text-gray-500 italic">
                      No public references yet.
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Footer Note */}
      <section className="pb-24 px-6 bg-white">
        <div className="max-w-4xl mx-auto">
          <p className="font-sans text-xs text-gray-400 text-center leading-[1.65]">
            Standards are versioned and updated as real-world deployment and insurance requirements evolve.
          </p>
        </div>
      </section>

      <FooterDark />
      <ScrollToTop />
    </div>
  );
};

export default Standards;

