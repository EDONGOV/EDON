---
title: "What Is AI Governance and Why Every Health System Deploying AI Agents Needs It"
date: 2026-04-21
topic: What is AI governance and why every health system deploying AI agents needs it
status: draft
---

# What Is AI Governance and Why Every Health System Deploying AI Agents Needs It

In February 2025, a federal court allowed a class action to proceed against UnitedHealth Group after its AI model, "nH Predict," was shown to have a 90% error rate when denying post-acute care coverage to elderly Medicare Advantage patients — with no meaningful human review in the loop (*Lokken v. UnitedHealth Group Inc.*, Case 0:23-cv-03514-JRT-SGE). Over 80% of those denials were reversed on appeal, but not before patients were harmed.

That case is the cost of deploying AI without governance. This post defines what AI governance actually means at the infrastructure level, explains the regulatory landscape forcing the issue in 2025–2026, and describes what a governance layer looks like in practice.

## AI Governance Is Not a Committee — It's a Runtime Control Plane

When most health systems hear "AI governance," they think of a committee that meets quarterly, reviews model cards, and produces a PDF policy document. That model is already inadequate.

AI agents in clinical and operational workflows don't wait for quarterly review. They send messages to patients, query protected health information, trigger device commands, generate prior authorization decisions, and export data — continuously, at scale, across multiple systems. Governance must operate at the same speed and granularity as the agents themselves.

**AI governance, defined technically:** a policy-enforcement layer that intercepts every action an AI agent attempts, evaluates it against a codified set of regulatory and organizational rules, and returns an allow/deny/escalate verdict — with a tamper-proof audit trail.

This is the difference between governance-as-documentation and governance-as-infrastructure.

## The Regulatory Landscape Has Moved Faster Than Most Teams Realize

### Federal Rules Still Apply — and They're Specific

HIPAA and HITECH didn't anticipate AI agents, but their requirements apply directly:

- **45 CFR §164.312(b)** — Audit controls. Covered entities must implement hardware, software, and procedural mechanisms to record and examine activity in information systems that contain or use ePHI. An AI agent querying a clinical database is an information system activity. If you can't produce a complete, tamper-proof log of every query that agent made, you have a compliance gap.
- **45 CFR §164.312(d)** — Person or entity authentication. When an AI agent acts on behalf of a clinician or administrator, the chain of authorization must be verifiable. Which human authorized this agent's access? Under what scope?
- **45 CFR §164.308(a)(1)(ii)(D)** — Information system activity review. Organizations must regularly review records of information system activity, including audit logs and access reports. This review must cover AI agent activity, not just human user activity.
- **21 CFR Part 820 (FDA QSR) / FDA SaMD guidance** — If your AI agent's output influences clinical decisions (diagnosis, treatment recommendations, triage), it likely qualifies as Software as a Medical Device. FDA expects documented risk management processes, version-controlled algorithms, and traceable decision logs.
- **21 CFR §1306 (DEA)** — AI agents involved in any part of the controlled substance prescribing or dispensing workflow face strict requirements around authentication and authorization that predate AI but bind it absolutely.

### States Are Not Waiting for Congress

With no federal AI legislation enacted, 43 states introduced over 240 AI-related bills in early 2026. Two are immediately relevant:

**Texas TRAIGA** (effective January 1, 2026) establishes governance requirements for AI systems including risk assessments, disclosure obligations, and accountability mechanisms. If your health system operates in Texas or serves Texas patients, this applies.

**California AB 489** (effective January 1, 2026) prohibits AI systems from using terms, design elements, or interaction patterns that imply the system holds a healthcare license. This directly affects any patient-facing AI agent — chatbots, symptom checkers, care navigation tools. An AI agent that introduces itself as "your care team" without proper disclosure is now in violation.

These laws carry enforcement teeth and create private rights of action. The DOJ's AI Litigation Task Force, established in late 2025 to challenge "onerous" state AI laws, has not slowed this legislative activity.

### The Joint Commission–CHAI Framework Signals Accreditation Requirements

In September 2025, the Joint Commission and the Coalition for Health AI (CHAI) released the first comprehensive U.S. health system AI governance framework, covering over 23,000 accredited healthcare organizations. It establishes seven governance areas: leadership oversight, regulatory compliance, IT and cybersecurity integration, clinical department involvement, safety monitoring, ethical review, and ongoing performance evaluation.

The framework is currently non-binding. But if you've worked in healthcare IT for any length of time, you know that Joint Commission guidance has a reliable habit of becoming accreditation criteria. The organizations building governance infrastructure now will be ready. The ones treating this as optional will be retrofitting under pressure.

## What Runtime Governance Looks Like in Practice

A governance layer must sit in the execution path of every AI agent action — not as a logging sidecar, but as a synchronous policy checkpoint. Here's a concrete example.

An AI agent in a care management platform attempts to send a coverage determination letter to a patient via email. Before that email leaves the system, the governance layer must evaluate:

1. Does the email contain ePHI? If so, is the transmission channel encrypted per 45 CFR §164.312(e)(1)?
2. Does the content include language that implies a licensed professional authored it (California AB 489)?
3. Has a human clinician reviewed and approved this determination, or is this an autonomous denial (the nH Predict failure mode)?
4. Is the action logged with the agent identity, policy version, human authorizer, timestamp, and full payload hash?

Here's what that looks like as an API call through EDON's governance layer:

```python
import edon

client = edon.Client(api_key="sk-hlth-...")

verdict = client.evaluate(
    agent_id="care-mgmt-agent-04",
    action={
        "type": "email.send",
        "recipient": "patient:mrn-88421",
        "contains_phi": True,
        "content_hash": "sha256:a3f1c9...",
        "clinical_determination": True,
        "human_reviewer": None  # No human reviewed this action
    },
    rule_packs=["hipaa", "california_ab489", "cms_interoperability"],
    context={
        "patient_state": "CA",
        "care_setting": "post_acute",
        "agent_fleet": "care-management-v2"
    }
)

# verdict.decision  => "ESCALATE"
# verdict.reasons   => [
#   "HIPAA §164.312(e)(1): PHI transmission requires encryption verification",
#   "CA AB 489: Clinical determination language requires licensed-professional disclosure",
#   "ORG-POLICY-017: Coverage determinations require human-in-the-loop approval"
# ]
# verdict.escalation => {"route": "clinical_reviewer_queue", "sla_minutes": 30}
# verdict.audit_id  => "aud_7f3a...c821" (tamper-proof, immutable)
```

The response returns in under 100ms. The agent doesn't send the email. Instead, the action is routed to a human reviewer with full context. The audit record is written to an append-only, tamper-proof log that satisfies 45 CFR §164.312(b) requirements and is ready for Joint Commission survey or litigation discovery.

This is what governance-as-infrastructure means: not a policy PDF, but a programmatic control that prevents the nH Predict pattern — autonomous AI decisions affecting patient care with no human checkpoint and no audit trail.

## The nH Predict Pattern Is the Default Without Governance

It's worth being explicit about why the UnitedHealth case matters architecturally, not just legally. The nH Predict failure had three compounding factors:

1. **No runtime policy enforcement.** The model could issue denials without hitting any compliance checkpoint.
2. **No human-in-the-loop gate.** Physician determinations were overridden autonomously by the algorithm.
3. **No auditable decision trail.** When patients appealed, reconstructing why the model denied coverage was difficult — and the reversal rate (80%+) suggests the decisions were indefensible.

Any health system deploying AI agents for utilization management, prior authorization, clinical documentation, patient communication, or care coordination is building the same architecture unless it has a governance layer that prevents it.

## What to Do Now

If you're a CTO or engineering lead at a health system or clinical SaaS company, here's the minimum viable governance checklist for 2026:

1. **Inventory every AI agent action type** — emails, database queries, file exports, API calls, device commands. You can't govern what you can't enumerate.
2. **Map each action to its regulatory surface** — HIPAA, FDA SaMD, DEA, state-specific laws, Joint Commission–CHAI framework areas.
3. **Implement synchronous policy enforcement** — not async logging, not post-hoc review. The governance check must happen before the action executes.
4. **Require human-in-the-loop for clinical determinations** — this is the single highest-liability gap in health AI today.
5. **Produce tamper-proof audit logs** — if you can't hand a regulator or plaintiff's attorney a complete, immutable record of every AI decision, you are exposed.

EDON provides this as a platform: rule packs for HIPAA/HITECH, FDA SaMD, DEA, Joint Commission, and state-specific regulations; policy-as-code that version-controls your governance rules alongside your application code; sub-100ms verdicts; and fleet-wide management for organizations running multiple AI agents across departments.

**[Request a technical demo →](https://edon.ai/demo)**

If you're deploying AI agents in healthcare and don't yet have a runtime governance layer, the regulatory and legal exposure is real, it's growing, and the nH Predict precedent shows exactly how it plays out. Build the control plane before you need it in discovery.