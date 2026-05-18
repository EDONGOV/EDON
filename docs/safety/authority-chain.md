# EDON Authority Chain — v1.0

## Document purpose

This document defines the explicit conflict resolution ordering used by the EDON governor when multiple subsystems produce conflicting signals. It is the authoritative reference for:

- Engineers modifying `backend/edon_gateway/authority_chain.py` or `governor.py` (any such change is safety-significant and must be reflected here)
- Security reviewers and auditors evaluating how partial failures are resolved
- Incident responders diagnosing unexpected verdicts under degraded conditions
- Test engineers verifying that invariant tests cover each precedence level

The authority chain is a total ordering: when two subsystems disagree, the lower priority number wins unconditionally. There are no weighted combinations, no probability-weighted overrides, and no tenant-configurable exceptions to any level 0–2 rule.

---

## Scope

**In scope:** All conflict resolution logic that executes inside `governor.evaluate()` from the moment a request is accepted to the moment a verdict is returned, including partial failure scenarios where one or more subsystems are unavailable or return an error.

**Out of scope:** Conflict resolution within a single subsystem (e.g., how the policy engine orders multiple matching rules from the same tenant); network-layer routing decisions before the request reaches `governor.evaluate()`; downstream system behaviour after EDON issues a verdict.

**Source of truth in code:** `backend/edon_gateway/authority_chain.py` — `AUTHORITY_PRECEDENCE`. Any discrepancy between that file and this document is a defect in this document. The code governs.

---

## Authority chain

The table below lists all seven levels in ascending priority order. Priority 0 is the highest and is evaluated last — the governor applies checks from lowest priority (6) to highest (0) and the highest-priority applicable rule that produces a non-DEFAULT outcome is the final verdict. If no override fires, the DEFAULT (priority 6) verdict is ALLOW.

| Priority | Name | Trigger condition | Resolution |
|----------|------|-------------------|------------|
| 0 | AUDIT_WRITE | Audit write failure for an action in the fail-closed registry (e.g., `payment.wire_transfer`, `database.truncate`) | BLOCK — a governance decision without a durable record is indistinguishable from no governance at all |
| 1 | ESTOP | Emergency stop active for a physical tool at the time of evaluation | BLOCK — no exceptions; hardware safety invariants supersede all policy logic |
| 2 | BLAST_RADIUS_FLOOR | Requested action falls within the governor's minimum risk floor table | Upgrade verdict — the policy engine's ALLOW does not survive a CRITICAL floor classification; verdict is set to at least the floor level |
| 3 | SESSION_BLOCK | Cumulative session risk score exceeds the configured block threshold | BLOCK or ESCALATE — session history overrides the single-action assessment; a clean individual action in a compromised session is still blocked |
| 4 | TENANT_POLICY | A tenant-defined rule matches the action at the highest tenant priority | Rule verdict is applied (ALLOW, BLOCK, ESCALATE, or DEGRADE) as the tenant rule specifies |
| 5 | INTENT_CONTRACT | Action falls outside the declared scope or constraints of the current intent contract | BLOCK or DEGRADE — out-of-scope actions are not governed by the active contract |
| 6 | DEFAULT | All checks pass; no override fired | ALLOW |

**Note on ESTOP (priority 1):** The ESTOP check is a hard gate. It does not consult the policy engine. The governor queries the ESTOP registry directly. Even if the policy engine was never invoked, or raised an exception, or returned ALLOW for any reason, a live ESTOP signal for the relevant tool causes the governor to return BLOCK. This is the only level where no policy engine involvement is required at all.

**Note on BLAST_RADIUS_FLOOR (priority 2):** The floor does not unconditionally produce BLOCK. It produces an upgrade: if the floor classification is MEDIUM, a policy engine ALLOW becomes at least ESCALATE; if the floor classification is CRITICAL, the verdict is BLOCK regardless of the policy engine outcome. The floor table is immutable at runtime (see acceptance criterion AC-5.4).

---

## Partial failure scenarios

The following scenarios document how the authority chain behaves when subsystems fail in specific combinations. Each scenario reflects a condition that is explicitly handled in `governor.py` and tested by an invariant suite.

---

### Scenario A: Policy says ALLOW + audit write fails + action is fail-closed

**Preconditions:**
- Policy engine evaluates the request and returns ALLOW (no error, no exception)
- The audit write for the ALLOW decision raises an exception (e.g., database connection failure, queue full)
- The action type is in `_AUDIT_REQUIRED_PATTERNS` in `authority_chain.py` (e.g., `payment.wire_transfer`)

**Resolution:** AUDIT_WRITE at priority 0 fires. The governor returns BLOCK.

**Rationale:** The ALLOW verdict was computed correctly, but it was not durably recorded. An unrecorded ALLOW for a fail-closed action is operationally equivalent to no governance having occurred: there is no audit evidence that the action was reviewed, no chain signature, and no way to reconstruct whether the action was authorised. The audit record is not a post-hoc log entry — it is a prerequisite for the action being permitted.

**Affected registry entries (current):** `payment.wire_transfer`, `payment.transfer`, `finance.transfer`, `database.truncate`, `database.drop`.

---

### Scenario B: Policy engine exception + governor exception handler fires

**Preconditions:**
- Policy engine raises `RuntimeError`, `TimeoutError`, or any unhandled exception during `evaluate()`
- Governor exception handler fires before any verdict is returned to the caller
- BLAST_RADIUS_FLOOR and SESSION_BLOCK checks may not have run (exception may have occurred before them)

**Resolution:** `_resolve_failure_mode()` is called. It checks the per-rule failure mode, then the `_FAILURE_MODE_REGISTRY`, then the global `EDON_STRICT_FAIL_CLOSED` environment variable. With `EDON_STRICT_FAIL_CLOSED=true` (the default), the verdict is BLOCK.

**Rationale:** The blast-radius floor (priority 2) and session block (priority 3) never ran — neither check can confirm it is safe to allow the action. Issuing ALLOW when the safety checks were never completed would violate the governance contract. The exception itself is logged with full context (tenant, action type, traceback) and the audit record reason is set to `"policy_engine_exception"`.

**Configuration dependency:** This resolution requires `EDON_STRICT_FAIL_CLOSED=true`, which is the default. A deployment with `EDON_STRICT_FAIL_CLOSED=false` would resolve to whatever `_resolve_failure_mode()` returns for the global fallback, which may be ALLOW. Setting `EDON_STRICT_FAIL_CLOSED=false` is logged as a WARNING at startup (see AC-3.5 and AC-3.6).

---

### Scenario C: Policy engine exception + audit write also fails (double failure)

**Preconditions:**
- Policy engine raises an exception → governor exception handler fires → verdict is set to BLOCK (as in Scenario B)
- Audit write for the BLOCK decision then also fails (second independent failure)

**Resolution:** The BLOCK verdict stands. The audit write failure is logged but does not change the verdict.

**Rationale:** The AUDIT_WRITE rule at priority 0 applies specifically to fail-closed actions where an unrecorded *ALLOW* would constitute ungoverned execution. A BLOCK verdict means the action does not execute — there is no unsafe consequence. Escalating a double failure from BLOCK to something more permissive would introduce a race condition where sufficiently many coincident failures could produce ALLOW. The BLOCK verdict is therefore unconditional once issued, regardless of whether it can be recorded.

**Observability:** The failed audit write is written to the process log at ERROR level with the original BLOCK reason preserved. A separate metric, `edon.audit.write.failure`, is incremented. Monitoring alerts on this metric per acceptance criterion AC-1.4.

---

### Scenario D: Hard gate fires + policy engine says ALLOW (contradictory signals)

**Preconditions:**
- A hard gate invariant fires and records a "fail" result (e.g., ESTOP signal is active for the target tool, or an ISO 15066 force threshold violation is detected)
- The policy engine was invoked independently and returned ALLOW (e.g., the tenant has an explicit ALLOW rule for this action type)

**Resolution:** ESTOP at priority 1 — the governor post-processes the decision after all checks have been collected and overrides to BLOCK.

**Rationale:** Hard gates encode physical safety invariants. The policy engine evaluates logical rules authored by the tenant. The policy engine's ALLOW is authoritative only within the space of situations that the hard gate has not already excluded as unsafe. Any ALLOW produced by the policy layer while a hard gate is active reflects either a rule that was written without anticipating the failure condition, or a latency window between when the ESTOP fired and when the policy cache was updated. Neither case should produce execution. The governor does not ask the policy engine to re-evaluate once a hard gate result is known; it applies the priority override directly.

---

## Conflict resolution algorithm

The following pseudocode describes the governor's decision procedure for the authority chain. It is illustrative of the logic in `governor.py`; the Python source is authoritative in case of discrepancy.

```
function evaluate(request) -> Verdict:
    # Collect signals from all subsystems
    estop_active    = estop_registry.is_active(request.tool)
    floor_result    = blast_radius_floor.classify(request)
    session_result  = session_trust.evaluate(request.session)
    policy_verdict  = policy_engine.evaluate(request)   # may raise
    intent_ok       = intent_contract.check(request)

    # Apply authority chain: highest priority (lowest number) wins
    # Level 0 — checked after audit write attempt, below
    # Level 1 — ESTOP
    if estop_active:
        return write_audit_and_return(BLOCK, reason="ESTOP")

    # Level 2 — BLAST_RADIUS_FLOOR
    if floor_result.classification == CRITICAL:
        return write_audit_and_return(BLOCK, reason="BLAST_RADIUS_FLOOR")
    if floor_result.classification == MEDIUM and policy_verdict == ALLOW:
        policy_verdict = ESCALATE   # floor upgrade

    # Level 3 — SESSION_BLOCK
    if session_result.risk >= SESSION_BLOCK_THRESHOLD:
        return write_audit_and_return(BLOCK, reason="SESSION_BLOCK")

    # Level 4 — TENANT_POLICY
    # policy_verdict is already set from policy_engine.evaluate() above

    # Level 5 — INTENT_CONTRACT
    if not intent_ok:
        policy_verdict = BLOCK   # or DEGRADE per contract configuration

    # Level 6 — DEFAULT
    # policy_verdict at this point is the final verdict (ALLOW if nothing overrode)

    # Level 0 — AUDIT_WRITE (evaluated after verdict is determined, before returning)
    audit_ok = audit_log.write(request, policy_verdict)
    if not audit_ok and audit_write_required(request.tool, request.op):
        return BLOCK   # priority 0 override: cannot issue unrecorded fail-closed verdict

    return policy_verdict


on exception during evaluate():
    _resolve_failure_mode(exception)
    # With EDON_STRICT_FAIL_CLOSED=true → BLOCK
    # Audit write is attempted for the BLOCK; audit write failure for a BLOCK does not change verdict
```

**Key ordering note:** AUDIT_WRITE (priority 0) is checked *after* the verdict is determined but *before* returning. This is the only level that is applied in post-processing rather than pre-processing. Levels 1–6 are evaluated in order, and higher-priority results short-circuit. The session block (level 3) and intent contract (level 5) can both demote a policy ALLOW; neither can override ESTOP (level 1) or BLAST_RADIUS_FLOOR (level 2).

---

## Verification

The table below maps each authority chain level to the invariant tests and test files that verify it.

| Level | Name | Invariant test(s) | Test file(s) | Status |
|-------|------|-------------------|--------------|--------|
| 0 | AUDIT_WRITE | INV-1, AC-1.4 | `tests/invariants/test_audit_completeness.py`, `tests/fault_injection/test_strict_mode.py` | Implemented |
| 1 | ESTOP | INV-ESTOP (hard gate suite) | `tests/invariants/test_hard_gates.py` | Implemented |
| 2 | BLAST_RADIUS_FLOOR | INV-5, AC-5.1–AC-5.6 | `tests/policy/test_blast_radius_floor.py`, `tests/invariants/test_floor_immutable.py` | Implemented |
| 3 | SESSION_BLOCK | INV-SESSION | `tests/state/test_session_trust.py` | Partial (see Gap Register) |
| 4 | TENANT_POLICY | INV-3, AC-2.1–AC-2.5 | `tests/policy/`, `tests/invariants/test_tenant_isolation.py` | Implemented |
| 5 | INTENT_CONTRACT | INV-INTENT | `tests/policy/test_intent_contract.py` | Implemented |
| 6 | DEFAULT | INV-4, AC-4.1–AC-4.5 | `tests/policy/test_ungoverned.py` | Implemented |

**Scenario coverage:**

| Scenario | Test(s) |
|----------|---------|
| A (ALLOW + audit write fails + fail-closed) | `tests/fault_injection/test_audit_write_failure.py` — `test_fail_closed_audit_write_exception` |
| B (Policy exception + strict mode) | `tests/fault_injection/test_strict_mode.py` — `test_policy_exception_strict_block` |
| C (Double failure: policy exception + audit write fails) | `tests/fault_injection/test_strict_mode.py` — `test_double_failure_block_unchanged` |
| D (ESTOP active + policy returns ALLOW) | `tests/invariants/test_hard_gates.py` — `test_estop_overrides_policy_allow` |

---

## Gap register

The following gaps are known open items as of v1.0. Each gap is an acknowledged limitation in either coverage or implementation completeness.

| ID | Level | Description | Severity | Status |
|----|-------|-------------|----------|--------|
| GAP-AC-1 | SESSION_BLOCK (3) | Session block detection is not fully tested under concurrent load. The unit test suite covers single-threaded session accumulation. Concurrent sessions that race on the same session ID may produce inconsistent risk scores if the Redis update is non-atomic. | High | Open |
| GAP-AC-2 | AUDIT_WRITE (0) | Cross-replica audit consistency under partition has not been tested. When multiple gateway replicas are running and the shared audit store becomes partially unreachable, it is possible for one replica to successfully write an audit record while another replica for the same action cannot. The authority chain correctly produces BLOCK on the replica that fails the write, but the record on the successful replica is not automatically reconciled. | High | Open |
| GAP-AC-3 | BLAST_RADIUS_FLOOR (2) | The floor table currently covers 12+ explicitly enumerated action types. Novel action types not yet in the registry fall through to TENANT_POLICY (level 4) and DEFAULT (level 6). The ungoverned escalation path (Property 4 in `acceptance-criteria.md`) provides a backstop, but the floor table is not yet auto-populated from action type registrations. | Medium | Open |
| GAP-AC-4 | SESSION_BLOCK (3) | The session block threshold is currently a global constant. Per-tenant threshold configuration is not yet implemented. A session that would be blocked under a stricter tenant configuration may not be blocked under the global default. | Medium | Open |
| GAP-AC-5 | AUDIT_WRITE (0) | Pre-write PENDING record is not yet implemented (tracked as RR-3 in `fault-tree.md`). If the gateway process crashes between evaluation completion and audit write, the in-flight evaluation is lost with no audit record. The AUDIT_WRITE authority chain level cannot fire in this case because the exception occurs outside `evaluate()`. | High | Open |

---

## Revision history

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-06 | Initial | Authority chain defined from `authority_chain.py`; seven levels, four partial failure scenarios, full verification table |
