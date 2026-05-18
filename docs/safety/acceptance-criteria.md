# EDON Safety Acceptance Criteria — v1.0

## Document purpose

This document defines the measurable acceptance criteria for each safety property of the EDON governance gateway. Each property has a precise definition, a set of pass/fail criteria with numeric thresholds, and a designated measurement method. These criteria are used to:

- Verify that a given deployment meets the EDON governance guarantee
- Define the scope of automated invariant tests and CI regression suites
- Establish the minimum bar for GameDay exercises
- Provide auditors (HIPAA, SOC 2) with verifiable evidence of safety controls

A deployment is considered compliant with a given property only when all acceptance criteria for that property pass. Partial compliance is noted as "degraded" for High-severity properties and "non-compliant" for Critical-severity properties.

---

## Property 1: Audit completeness

**Definition:** Every governance evaluation produces exactly one immutable audit record. No evaluation produces zero records. No evaluation produces duplicate records. Audit records are written before the response is returned to the caller.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-1.1 | 100% of `evaluate()` calls produce an audit record | p95 write latency < 500ms under nominal load (500 req/min) | Implemented |
| AC-1.2 | 100% of fail-open events produce an audit record flagged with `fallback=true` | Zero fail-open events with missing `fallback` flag in test corpus | Implemented |
| AC-1.3 | Zero evaluations produce no audit record during gateway recovery window | Measured during GameDay-1: gateway is killed mid-load, restarted, and audit log is checked for gaps | Partial |
| AC-1.4 | Audit write failure causes `evaluate()` to return an error verdict | Write failure injected via fault injection; response must be BLOCK or error, not ALLOW | Implemented |
| AC-1.5 | No duplicate audit records are produced under concurrent load | 10,000 concurrent requests at 1,000 req/min; audit record count equals request count | Implemented |

**Measurement method:**
- Invariant test `INV-1` (audit completeness): automated, runs on every CI build targeting `governor.py`.
- GameDay-1 runbook: manual exercise, minimum quarterly cadence.
- Metric: `edon.audit.write.success_rate` exported to monitoring; alert threshold at < 100%.

**Known gap:** AC-1.3 is partially implemented. The GameDay-1 runbook exists but has not been executed against the current production configuration. Pre-write PENDING record (which would close the recovery window gap) is tracked as RR-3 in the fault tree.

---

## Property 2: Tenant isolation

**Definition:** No tenant's audit records, policy rules, agent data, or rate limit state are accessible to, or can influence the governance outcome of, a request from a different tenant.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-2.1 | Zero cross-tenant data leakage in randomized query corpus | 10,000 randomized cross-tenant query pairs; zero results from wrong tenant | Implemented |
| AC-2.2 | Isolation holds under concurrent multi-tenant load | 500 req/s across 50 tenants; zero cross-tenant audit records in result set | Implemented |
| AC-2.3 | `customer_id` is present and non-null on every row of every tenant-scoped table | Schema invariant checked on every migration; CI assertion on all tenant tables | Implemented |
| AC-2.4 | Cache keys include `customer_id` as a required prefix | Static analysis and runtime assertion; no cache hit served to wrong tenant | Partial |
| AC-2.5 | Tenant-scoped API endpoints return HTTP 403 for requests with a mismatched `customer_id` | Automated endpoint test matrix across all tenant-scoped routes | Implemented |

**Measurement method:**
- Invariant test `INV-3` (tenant isolation): automated, runs on every CI build.
- Schema migration review checklist: required item on all PRs touching tenant-scoped tables.
- Load test: `k6` script `tests/load/multi-tenant-isolation.js`, run on every release candidate.

**Known gap:** AC-2.4 is partial. In-memory policy rule caches may not enforce `customer_id` prefixing in all code paths (see RR-2 in fault tree). This is tracked as an open engineering item.

---

## Property 3: Fail-closed by default

**Definition:** Under all known and modeled failure conditions, with `EDON_STRICT_FAIL_CLOSED=true`, governance errors produce a BLOCK verdict. No exception path, timeout, or dependency failure produces an ALLOW verdict in strict mode.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-3.1 | Policy engine `RuntimeError` → BLOCK | Verdict is BLOCK within 50ms p99 of exception being raised | Implemented |
| AC-3.2 | Policy engine `TimeoutError` → BLOCK | Verdict is BLOCK within (configured timeout + 50ms) p99 | Implemented |
| AC-3.3 | Database connection failure during audit write → BLOCK | `evaluate()` does not return ALLOW when audit write fails | Implemented |
| AC-3.4 | Zero ALLOW verdicts produced by exception paths in strict mode | Automated fault injection across all exception paths in `governor.py`; assertion on verdict | Implemented |
| AC-3.5 | `EDON_STRICT_FAIL_CLOSED=false` is logged as WARNING at startup | Startup log contains WARNING when strict mode is disabled | Implemented |
| AC-3.6 | `EDON_STRICT_FAIL_CLOSED=false` is not the default | Default configuration file and environment template set `EDON_STRICT_FAIL_CLOSED=true` | Implemented |

**Measurement method:**
- Invariant test `INV-2` (fail-closed): automated, runs on every CI build targeting `governor.py`.
- Fault injection test suite: `tests/fault_injection/test_strict_mode.py`; covers all `except` clauses in `governor.py`.
- Manual verification: startup log reviewed as part of deployment checklist.

---

## Property 4: Ungoverned actions escalate

**Definition:** Any action for which no matching policy rule exists and no blast radius floor applies produces an ESCALATE verdict, never an ALLOW verdict. Tenant configuration can change this default only through explicit opt-in, which is itself logged and audited.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-4.1 | Action types absent from blast radius floor table and with no tenant rules → ESCALATE | 100% of test cases in ungoverned scenario group return ESCALATE | Implemented |
| AC-4.2 | `EDON_UNGOVERNED_VERDICT` defaults to `ESCALATE` | Default value asserted in configuration test; no override in default config files | Implemented |
| AC-4.3 | Overriding `EDON_UNGOVERNED_VERDICT` to `ALLOW` requires explicit opt-in | Override requires `EDON_UNGOVERNED_ALLOW_EXPLICIT=true`; absence of this flag causes override to be ignored | Implemented |
| AC-4.4 | Ungoverned ALLOW opt-in is logged as a security event at startup | Startup log contains a SECURITY-level entry when opt-in is active | Implemented |
| AC-4.5 | Ungoverned verdict is `ESCALATE` in 100% of test cases where no rules match | Policy regression suite, ungoverned scenario group; zero ALLOW verdicts without explicit opt-in | Implemented |

**Measurement method:**
- Invariant test `INV-4` (ungoverned escalation): automated, runs on every CI build.
- Policy regression suite: `tests/policy/test_ungoverned.py`; must pass 100% before any release.

---

## Property 5: Blast radius floor

**Definition:** High-blast-radius actions are subject to a minimum risk floor that cannot be overridden by tenant policy alone. Actions in the blast radius floor table are never plain ALLOW without at least one explicit tenant rule that has been reviewed and activated.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-5.1 | `database.truncate`, `database.drop` → never ALLOW without an active tenant rule | 100% of blast-radius-floor group test cases return non-ALLOW without tenant rules | Implemented |
| AC-5.2 | `shell.execute` with a dangerous command pattern → never ALLOW without an active tenant rule | Shell command patterns in dangerous list produce non-ALLOW; pattern list covers all entries in `blast_radius_floor.py` | Implemented |
| AC-5.3 | Physical actuator operations (`robot.actuate`, `vehicle.drive`, `drone.fly`) → minimum MEDIUM risk floor | Verdict risk level is never below MEDIUM for these action types regardless of tenant rules | Implemented |
| AC-5.4 | Blast radius floor table is immutable at runtime | No API endpoint or tenant configuration allows mutation of the floor table at runtime | Implemented |
| AC-5.5 | Tenant policy cannot override a blast radius floor entry to ALLOW without a code-level change | Policy engine asserts floor before applying tenant rules; tenant ALLOW rule for a floored type is rejected | Implemented |
| AC-5.6 | All 12+ blast radius floor entries are covered by automated tests | Policy regression suite blast-radius-floor group covers every entry in the floor table | Implemented |

**Measurement method:**
- Policy regression suite: `tests/policy/test_blast_radius_floor.py`; one test case per floor table entry.
- Immutability assertion: `tests/invariants/test_floor_immutable.py`; attempts runtime mutation and asserts rejection.
- Floor table entry count is asserted in CI to prevent silent removal of entries.

---

## Property 6: Escalation self-authorization

**Definition:** An agent that initiated an action requiring escalation cannot approve its own escalation. Approvals must come from a principal whose identity differs from the agent that submitted the original action.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-6.1 | `POST /compliance/review/{id}/approve` with `resolved_by` equal to original `agent_id` → HTTP 403 | 100% of self-authorization attempts return 403; zero are accepted | Implemented |
| AC-6.2 | Self-authorization attempt is logged as a security event | Audit log contains a `SECURITY` event with `event_type: self_authorization_attempt` for every 403 | Implemented |
| AC-6.3 | Self-authorization check applies regardless of agent role or permission level | Test cases cover agents with admin-equivalent roles; check is not bypassed by elevated permissions | Implemented |
| AC-6.4 | Escalation approval requires a `resolved_by` field that is a valid, distinct principal | Missing or null `resolved_by` returns HTTP 400; same-identity `resolved_by` returns HTTP 403 | Implemented |

**Measurement method:**
- Automated test: `tests/compliance/test_self_authorization.py`.
- Security regression test: included in the pre-release security regression suite.

---

## Property 7: Latency SLA

**Definition:** Governance adds bounded, predictable latency to agent pipelines. Latency is measured from the moment the request is received at the gateway boundary to the moment the verdict response is returned to the caller. Measurement excludes network transit between the caller and the gateway.

**Acceptance criteria:**

| ID | Criterion | Threshold | Status |
|----|-----------|-----------|--------|
| AC-7.1 | `evaluate()` p50 latency under sustained load | < 30ms at 1,000 req/min | Implemented |
| AC-7.2 | `evaluate()` p95 latency under sustained load | < 100ms at 1,000 req/min | Implemented |
| AC-7.3 | `evaluate()` p99 latency under sustained load | < 300ms at 1,000 req/min | Implemented |
| AC-7.4 | `scan_output()` p50 latency under sustained load | < 20ms at 1,000 req/min | Implemented |
| AC-7.5 | `scan_output()` p95 latency under sustained load | < 80ms at 1,000 req/min | Implemented |
| AC-7.6 | Cumulative latency tax per 10-step agent pipeline | < 500ms p95 | Implemented |
| AC-7.7 | Alert threshold for latency breach | Alert fires if p95 `evaluate()` latency exceeds 150ms over a 5-minute window | Implemented |

**Measurement method:**
- Load test suite: `k6` scripts in `tests/load/`; executed against staging on every release candidate and monthly against production.
- Continuous metric: `edon.evaluate.latency_ms` histogram exported to monitoring; p50/p95/p99 dimensions.
- Alert: configured in monitoring platform; evaluated monthly and after each infrastructure change.

---

## Revision history

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-06 | Initial | Seven safety properties defined with full acceptance criteria |
