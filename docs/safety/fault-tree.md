# EDON Fault Tree Analysis — v1.0

## Document purpose

This document enumerates the combinations of failures that can produce the top-level unsafe event for the EDON governance gateway. It is intended for use by:

- Security teams conducting vendor risk assessments
- HIPAA and SOC 2 auditors evaluating control completeness
- Engineering teams triaging incidents and planning mitigations
- Procurement reviewers requiring evidence of systematic safety analysis

This is a living document. Each branch is assigned a severity tier (defined in `severity-tiers.md`) and a current mitigation status. Branches with status "Partial" or "Not implemented" represent open engineering obligations tracked in the project issue tracker.

---

## Scope and methodology

**In scope:** All failure paths reachable from the `evaluate()` and `scan_output()` entry points under normal and degraded operating conditions, including dependency failures (database, Redis, signing subsystem, escalation queue).

**Out of scope:** Physical infrastructure failures below the hypervisor layer; client-side failures in agent code not governed by EDON; failures in downstream systems that execute actions after EDON issues an ALLOW verdict.

**Methodology:** Deductive fault tree analysis (FTA) per IEC 61025. Each branch is a minimal cut set — the smallest combination of component failures sufficient to produce the top event. Branches are independent unless explicitly noted. Mitigations are classified as controls that reduce either the probability of the branch occurring or the severity of the outcome. Residual risk is what remains with all listed mitigations implemented.

**Tier definitions:** See `severity-tiers.md`.

---

## Top-level unsafe event

> **TE-1: An unsafe agent action executes without a governance decision being made or recorded.**

This event has two sufficient conditions:
1. The action proceeds without any governance evaluation having been invoked (bypass), or
2. A governance evaluation was invoked but its outcome was not recorded in the immutable audit log (silent evaluation).

Either condition alone is sufficient to constitute the top-level unsafe event.

---

## Fault tree branches

---

### Branch 1: Gateway unavailable + fail-open + audit write failure → silent unrecorded action

**Description:**
The EDON gateway is unreachable or returns a non-2xx response. The calling agent or integration layer is configured with `fail_open=true`. Because the gateway did not process the request, no audit record is written. The action proceeds with no governance decision and no audit trail.

**Minimal cut set:**
- C1-1: Gateway process unavailable (crash, OOM, network partition)
- C1-2: Integration configured with `fail_open=true`
- C1-3: Fail-open event not written to audit log

**Severity:** Critical

**Current mitigation status:** Partial

**Mitigations:**
- Audit write is attempted before the gateway returns any response; a write failure causes the gateway to return an error verdict rather than silently proceed.
- Fail-open events are logged with `fallback=true` flag when the gateway itself initiates a graceful degradation.
- Alert fires on the first fail-open event within a rolling 5-minute window.
- `EDON_FAIL_OPEN=false` is the default; `fail_open=true` requires explicit configuration and is flagged in the startup log.

**Gap:** When the gateway is fully unreachable (C1-1), the integration layer must enforce the fail-open/fail-closed policy locally. EDON cannot control behavior in unreachable gateway scenarios through gateway-side code alone. SDK documentation and integration guidance must enforce fail-closed as the default for production deployments.

**Residual risk:** Integrations that override the SDK default to `fail_open=true` and operate with no local fallback policy will proceed without governance under a gateway outage. This residual risk requires contractual and operational controls in addition to technical ones.

---

### Branch 2: Signing key absent or rotated mid-session → audit chain integrity break (silent)

**Description:**
The HMAC signing key (`EDON_SIGNING_KEY`) is not set, is set to a placeholder value, or is rotated while active sessions have in-flight audit records. Audit records are written, but their chain signatures are invalid or unverifiable. An adversary who compromises the audit log cannot be detected via chain verification.

**Minimal cut set:**
- C2-1: `EDON_SIGNING_KEY` not set or set to a non-secret default value
- C2-2: Mid-session key rotation with no re-signing of in-flight records
- C2-3: Audit chain verification not run (silently broken chain goes undetected)

**Severity:** High

**Current mitigation status:** Partial

**Mitigations:**
- Gateway logs an `ERROR`-level message at startup if `EDON_SIGNING_KEY` is absent in a production environment (`EDON_ENV=production`).
- The `GET /verify-chain` endpoint re-derives signatures for a configurable time range and reports any gaps.
- Startup check fails hard (process exits) if `EDON_SIGNING_KEY` is absent and `EDON_ENV=production`. In non-production environments, a warning is emitted and a deterministic test key is used.

**Gap:** Key rotation procedure is not yet automated. Manual rotation requires a maintenance window and a `verify-chain` run immediately after. This is documented in the operational runbook but is not enforced by the system.

**Residual risk:** A key that is present but was generated insecurely (e.g., low entropy, committed to source control) passes the startup check but provides no meaningful chain integrity guarantee. Secret management hygiene is a prerequisite control not enforced by EDON.

---

### Branch 3: Tenant isolation bug → wrong policy applied → wrong verdict

**Description:**
A bug in query construction, ORM usage, or caching logic causes the policy engine to evaluate a request against the wrong tenant's rules. The resulting verdict (ALLOW, BLOCK, ESCALATE) is correct for a different tenant but incorrect for the requesting tenant. The incorrect verdict is recorded under the requesting tenant's audit log, obscuring the error.

**Minimal cut set:**
- C3-1: `customer_id` filter missing or incorrect in a policy query
- C3-2: Cache key does not include `customer_id` (cross-tenant cache hit)
- C3-3: No runtime assertion that returned policy rows belong to the requesting tenant

**Severity:** Critical

**Current mitigation status:** Partial

**Mitigations:**
- All tenant-scoped database queries require `customer_id` as a non-nullable parameter. Queries without it are rejected at the query builder layer.
- No query uses `OR customer_id IS NULL`; nullable tenant rows are disallowed by schema constraint.
- Automated invariant test INV-3 runs 10,000 randomized cross-tenant query pairs on every CI run and asserts zero cross-tenant results.
- Schema migrations that add tenant-scoped tables require a reviewer checklist item confirming `customer_id` NOT NULL constraint is present.

**Gap:** In-memory caches (e.g., compiled policy rule sets) do not yet enforce a `customer_id`-keyed cache namespace in all code paths. A cache key collision under high concurrency could serve a stale rule set from a different tenant.

**Residual risk:** Cache key collisions under extreme load or following a cache flush. Mitigation: cache keys must include `customer_id` as a required prefix. This is tracked as an open engineering item.

---

### Branch 4: Policy engine exception → default verdict applied → fail-open configured → action allowed

**Description:**
The policy engine raises an unhandled exception (e.g., `RuntimeError`, malformed rule, database timeout) during evaluation. The exception handler applies a default verdict. If `EDON_STRICT_FAIL_CLOSED=false`, the default verdict may be ALLOW, permitting the action without a policy decision having been made.

**Minimal cut set:**
- C4-1: Policy engine raises an unhandled exception during `evaluate()`
- C4-2: `EDON_STRICT_FAIL_CLOSED=false` (non-default configuration)
- C4-3: Default verdict resolves to ALLOW

**Severity:** Critical

**Current mitigation status:** Implemented

**Mitigations:**
- `EDON_STRICT_FAIL_CLOSED=true` is the hard default. Setting it to `false` requires an explicit environment variable override and is logged as a `WARNING` at startup.
- All exceptions in `governor.py` are caught at the outermost handler, logged with full context (tenant, action_type, exception traceback), and the verdict is set to BLOCK before the response is returned.
- Exception paths are covered by invariant test INV-2, which injects synthetic exceptions and asserts the verdict is always BLOCK in strict mode.
- The audit record for an exception-derived verdict includes a `reason` field set to `"policy_engine_exception"` for observability.

**Residual risk:** An exception that crashes the Python process before the audit write completes would produce no audit record for that evaluation. This overlaps with Branch 1 (gateway unavailable). Process supervisors (systemd, Fly.io restart policy) restart the process, but the in-flight evaluation is lost. Mitigation: pre-write the audit record as PENDING before evaluation begins, then update to the final verdict on completion.

---

### Branch 5: Agent spoofs action_type field → wrong rules evaluated → policy bypass

**Description:**
An agent under adversarial control (or a misconfigured agent) sends a request with a forged or downgraded `action_type` value (e.g., sends `"database.read"` instead of `"database.truncate"`). The policy engine evaluates rules for the spoofed type, which may be less restrictive, and returns an ALLOW verdict for an action that would otherwise be blocked.

**Minimal cut set:**
- C5-1: Governance evaluation relies exclusively on the client-supplied `action_type` field
- C5-2: No payload-level content inspection to detect mismatch between declared type and actual payload
- C5-3: Blast radius floor not applied based on payload content analysis

**Severity:** High

**Current mitigation status:** Partial

**Mitigations:**
- Payload-level content inspection (`security/output_filter.py` and governor pre-processing) scans the action payload for patterns inconsistent with the declared `action_type` (e.g., a `database.read` payload containing `DROP TABLE` or `TRUNCATE`).
- The blast radius floor table provides a defense-in-depth layer: high-blast-radius actions are subject to minimum risk floors regardless of the declared `action_type`, based on payload signatures.
- Anomaly scoring in `state/sequence_scorer.py` penalizes sessions where declared action types are inconsistent with payload content patterns.

**Gap:** Payload-level content inspection is signature-based and can be evaded by obfuscation (e.g., base64-encoded payloads, non-standard SQL dialects). Semantic analysis for all action types is not yet implemented.

**Residual risk:** Novel obfuscation techniques may evade signature-based payload inspection. This is an inherent limitation of pattern-matching defenses. Defense-in-depth (blast radius floor, session trust scoring) reduces but does not eliminate this risk.

---

### Branch 6: Rate limit key excludes tenant_id → tenant rotates agent IDs → per-tenant limit not enforced

**Description:**
If the rate limit key is derived from `agent_id` alone, a tenant that frequently rotates agent identifiers can generate a new `agent_id` to reset their rate limit counter, bypassing per-tenant throughput constraints. Under high load this can exhaust gateway resources and degrade governance for other tenants.

**Minimal cut set:**
- C6-1: Rate limit key does not include `tenant_id`
- C6-2: Tenant rotates `agent_id` values to reset counters
- C6-3: In-memory fallback does not evict stale keys, causing unbounded key growth

**Severity:** Medium

**Current mitigation status:** Implemented

**Mitigations:**
- Rate limit keys are composite: `{tenant_id}:{agent_id}`. Rotating `agent_id` does not reset the per-tenant aggregate counter because tenant-level limits are enforced independently of agent-level limits.
- In-memory rate limit fallback (active when Redis is unavailable) uses an LRU eviction policy with a configurable maximum key count to prevent unbounded memory growth from stale agent ID keys.
- Redis key TTL is set equal to the rate limit window, so expired agent IDs are evicted automatically.

**Residual risk:** A tenant that operates many concurrent agent IDs may distribute load across per-agent limits while remaining under the per-agent threshold, effectively multiplying their effective rate limit by the number of active agent IDs. Mitigation: enforce a per-tenant aggregate limit at the Redis layer that is independent of agent count.

---

### Branch 7: Escalation queue overflow → new escalations silently dropped → action proceeds without review

**Description:**
The escalation queue (storing actions pending human review) reaches its configured capacity. New escalation entries cannot be written. If the overflow handling returns ALLOW rather than BLOCK, the action proceeds without the required human review, bypassing the escalation control.

**Minimal cut set:**
- C7-1: Escalation queue at capacity
- C7-2: Queue overflow handler does not fail-closed
- C7-3: No alert on queue depth threshold

**Severity:** Critical

**Current mitigation status:** Implemented

**Mitigations:**
- Queue overflow fails-closed: if the queue cannot accept a new entry, the governance verdict is set to BLOCK. The action does not proceed.
- Queue depth is monitored; an alert fires when depth exceeds 80% of configured capacity.
- Overflow events are written to the audit log with `reason: "queue_overflow_block"` for post-incident review.
- Queue capacity is configurable per tenant, allowing high-escalation-rate tenants to be isolated from affecting global queue capacity.

**Residual risk:** If the monitoring alert fires but is not acted upon promptly, the queue may reach 100% capacity, causing all escalatable actions to be blocked until the queue is drained. This is operationally disruptive but does not produce the unsafe top-level event (actions are blocked, not permitted silently). The alert SLA is defined in `severity-tiers.md` (High tier: investigation within 4 hours).

---

### Branch 8: Ephemeral signing key across process restarts → audit chain appears valid but is unverifiable

**Description:**
If `EDON_SIGNING_KEY` is not set and the gateway falls back to a process-generated ephemeral key, the key is lost on every process restart. Audit records written before the restart have signatures that cannot be re-verified after the restart. The chain appears contiguous but verification always fails for pre-restart records, making it impossible to distinguish a tampered record from a legitimately signed one.

**Minimal cut set:**
- C8-1: `EDON_SIGNING_KEY` not set in production
- C8-2: Gateway falls back to ephemeral in-memory key
- C8-3: Process restarts (scheduled, crash, deployment) destroy the ephemeral key

**Severity:** High

**Current mitigation status:** Implemented

**Mitigations:**
- In `EDON_ENV=production`, the gateway exits at startup if `EDON_SIGNING_KEY` is absent. No ephemeral fallback is used in production mode.
- In non-production environments, the startup log emits a `WARNING` that audit chain verification will not be possible across restarts. Records are written with a `ephemeral_key=true` flag.
- HIPAA deployment documentation specifies `EDON_SIGNING_KEY` as a required configuration item with instructions for secret manager injection.

**Residual risk:** An operator who incorrectly sets `EDON_ENV=development` in a production deployment will receive a warning but the gateway will start with an ephemeral key. This is a misconfiguration risk, not a code defect. Mitigation: deployment checklists and infrastructure-as-code templates must set `EDON_ENV=production` explicitly and fail deployment if `EDON_SIGNING_KEY` is absent.

---

## Known residual risks

The following risks remain after all currently-implemented mitigations. Each is an acknowledged open item.

| ID | Description | Severity | Status |
|----|-------------|----------|--------|
| RR-1 | Integrations with `fail_open=true` and an unreachable gateway proceed without governance. Contractual and operational controls required. | Critical | Open |
| RR-2 | In-memory policy rule caches may not be keyed by `customer_id` in all code paths. Cache key collision under concurrent load possible. | Critical | In progress |
| RR-3 | In-flight evaluation is lost if the process crashes between evaluation start and audit write completion. Pre-write PENDING record not yet implemented. | High | Open |
| RR-4 | Payload-level content inspection is signature-based and may be evaded by novel obfuscation techniques. | High | Accepted (defense-in-depth) |
| RR-5 | Tenants with many agent IDs can distribute load across per-agent rate limits, effectively bypassing per-tenant aggregate limits. | Medium | Open |
| RR-6 | Misconfigured `EDON_ENV=development` in production bypasses hard startup key check. | High | Accepted (deployment control) |

---

## Revision history

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-06 | Initial | Initial fault tree — 8 branches enumerated |
