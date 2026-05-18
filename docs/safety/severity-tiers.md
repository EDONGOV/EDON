# EDON Severity Tier Definitions — v1.0

## Document purpose

This document defines the four severity tiers used throughout EDON's safety documentation, incident response procedures, and monitoring configuration. Every fault tree branch, acceptance criterion failure, and operational alert is assigned one of these tiers. Tier assignments drive the response requirements and SLA obligations described below.

This document is referenced by:
- `fault-tree.md` — severity assignments for each fault tree branch
- `acceptance-criteria.md` — severity of each acceptance criterion failure
- Monitoring alert configuration — alert priority and escalation routing
- Incident response runbooks — response time obligations

---

## Tier definitions

---

### Critical

**Definition:** An unsafe agent action may execute without a governance decision having been made or recorded. The core governance guarantee — that every action is evaluated and every evaluation is recorded — is broken or circumvented.

A Critical event is distinguished from High by the absence of an audit trail, the absence of a governance decision, or both. A system that is "governing wrong" is High. A system that is "not governing at all, silently" is Critical.

**Examples:**
- Audit write silently fails and no error is returned to the caller; the action proceeds
- Tenant isolation is bypassed; a tenant's request is evaluated against a different tenant's policy
- A BLOCK verdict is converted to ALLOW by an exception handler in strict fail-closed mode
- Escalation queue overflow permits an unreviewed action to proceed
- An agent action executes in a window where the gateway was unreachable and the integration failed open without logging

**Response requirements:**
- Immediate halt of the affected component or code path
- Human review and sign-off required before the affected component is restarted or re-enabled
- Incident report filed within 1 hour of detection
- Root cause analysis completed within 72 hours
- Mitigation or remediation deployed within 7 days; exception requires written risk acceptance from an authorized principal

**SLA impact:** Breach of the core governance guarantee. Constitutes a reportable event under HIPAA Business Associate Agreements where applicable. Must be disclosed to affected tenants within the contractually specified window.

---

### High

**Definition:** Governance is degraded but the failure is visible. Actions may proceed under non-standard conditions (e.g., fail-open), but audit records are written and the degradation is flagged. Alternatively, the integrity or completeness of governance is reduced in a detectable way (e.g., signing key absent, escalation queue approaching capacity).

A High event does not constitute a silent governance failure. The system is operating outside its normal parameters in a way that is observable through logs, metrics, or alerts.

**Examples:**
- Fail-open mode is activated: an action proceeds, the audit record is written with `fallback=true`, and an alert fires
- Escalation queue depth exceeds 80% of capacity; new escalations are at risk of being blocked
- Signing key is absent in a production environment; audit chain verification is not possible
- Session trust scoring is degraded due to a dependency failure; trust decisions are less accurate
- An agent's self-authorization attempt is blocked and logged (the control worked, but the attempt is a security signal)

**Response requirements:**
- Alert fires within 60 seconds of detection
- On-call engineer acknowledges within 15 minutes
- Investigation begins within 4 hours
- Remediation deployed or risk acceptance documented within 24 hours

**SLA impact:** Governance operating in degraded mode. Audit trail is intact. Tenant notification is required if degraded mode persists beyond the 24-hour remediation window.

---

### Medium

**Definition:** Performance or observability is impaired. Governance correctness is not affected: verdicts are correct, audit records are complete, and tenant isolation is maintained. The impairment affects how quickly or reliably the system can be monitored or how efficiently it operates.

**Examples:**
- `evaluate()` p95 latency exceeds 150ms for a sustained period
- Redis is unavailable; the gateway falls back to in-memory rate limiting
- Audit chain verification endpoint (`GET /verify-chain`) is slow or returns partial results
- Policy rule compilation is slower than expected due to a large rule set
- Metric export to the monitoring platform is delayed or missing

**Response requirements:**
- Alert fires within 5 minutes of detection
- Investigation begins within 24 hours
- Remediation deployed within the next scheduled release cycle, or sooner if root cause indicates a regression

**SLA impact:** No governance correctness impact. Operational monitoring is impaired; teams may have reduced visibility into the system's state during the impairment window.

---

### Low

**Definition:** Non-safety functionality is affected. Governance core operations (evaluation, audit writing, tenant isolation) are unaffected. The impairment is in peripheral features: reporting, notifications, UI, or tooling.

**Examples:**
- Compliance report generation fails or produces malformed output
- Console UI returns an error or renders incorrectly for a subset of users
- Telegram or webhook notification for an escalation fails to deliver
- API documentation endpoint returns stale content
- A scheduled maintenance task (e.g., audit log compaction) fails to run

**Response requirements:**
- Logged in the application error tracker
- Tracked as an issue in the project issue tracker
- Remediated in the next scheduled release
- No on-call pager alert required

**SLA impact:** None. No governance, audit, or isolation functionality is affected.

---

## Severity classification table

This table maps each fault tree branch (from `fault-tree.md`) to its severity tier, current mitigation status, and the acceptance criteria it is tested by.

| Branch | Description (abbreviated) | Severity | Mitigation status | Tested by |
|--------|---------------------------|----------|-------------------|-----------|
| B-1 | Gateway unavailable + fail-open + audit write failure → silent unrecorded action | Critical | Partial | AC-1.2, AC-1.3, INV-1 |
| B-2 | Signing key absent or rotated mid-session → audit chain integrity break | High | Partial | Startup check, verify-chain endpoint |
| B-3 | Tenant isolation bug → wrong policy applied → wrong verdict | Critical | Partial | AC-2.1, AC-2.4, INV-3 |
| B-4 | Policy engine exception → fail-open configured → action allowed | Critical | Implemented | AC-3.1, AC-3.4, INV-2 |
| B-5 | Agent spoofs action_type → wrong rules evaluated → policy bypass | High | Partial | AC-5.1, blast-radius-floor suite |
| B-6 | Rate limit key excludes tenant_id → per-tenant limit not enforced | Medium | Implemented | Rate limit integration tests |
| B-7 | Escalation queue overflow → action proceeds without review | Critical | Implemented | AC-1.4, escalation overflow test |
| B-8 | Ephemeral signing key → audit chain unverifiable after restart | High | Implemented | Startup check, deployment checklist |

### Classification rationale

**B-1 is Critical** because the combination produces an action that executes with no audit record and no governance decision. The audit trail is broken silently.

**B-2 is High (not Critical)** because audit records are still written; only chain integrity verification is compromised. The failure is detectable via the `verify-chain` endpoint.

**B-3 is Critical** because the wrong policy being applied produces a verdict that is not the correct governance outcome for the requesting tenant. The audit record exists but records a wrong decision.

**B-4 is Critical** because an exception in the policy engine, combined with a non-default fail-open configuration, can produce an ALLOW verdict with no actual policy evaluation having occurred. In strict mode (the default), this degrades to High.

**B-5 is High** because the blast radius floor provides a defense-in-depth backstop. A spoofed action_type alone is insufficient to bypass governance for high-blast-radius actions; the attacker must also evade payload inspection.

**B-6 is Medium** because rate limit bypass degrades governance quality (an agent can exceed its configured throughput limit) but does not change the correctness of individual verdicts.

**B-7 is Critical** because the top-level event is that an escalatable action proceeds without human review. The mitigation (fail-closed overflow) converts this to a block rather than a silent pass, which is why the current mitigation status is Implemented.

**B-8 is High** because the failure is detectable (the `verify-chain` endpoint returns failures), and the startup hard-exit in production mode prevents the scenario from occurring if deployment configuration is correct.

---

## Severity tier assignment criteria

When assigning a severity tier to a new fault tree branch, alert, or acceptance criterion failure, use the following decision criteria in order:

1. **Is the governance guarantee broken silently?** — If yes, Critical.
2. **Is a governance decision absent or incorrect, with an audit record present?** — If yes, Critical.
3. **Is governance degraded but visible, with an intact audit trail?** — If yes, High.
4. **Is performance, latency, or observability impaired, with correct governance?** — If yes, Medium.
5. **Is only peripheral functionality affected?** — If yes, Low.

When in doubt, assign the higher severity tier. Downgrading from a higher tier requires a written rationale.

---

## Revision history

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-06 | Initial | Four tiers defined; fault tree branch classification table added |
