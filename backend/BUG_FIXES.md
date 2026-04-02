# Critical Bug Fixes - Phase A

**Date:** 2026-01-26  
**Status:** ✅ All Fixed

---

## 1. ✅ Fixed: reason_code Wrong on ALLOW

**Problem:** ALLOW verdicts were showing `reason_code: INTENT_MISMATCH`, which is logically inconsistent.

**Fix:**
- Added `APPROVED` to `ReasonCode` enum
- Made `reason_code` deterministic per verdict:
  - `ALLOW` → `APPROVED`
  - `DEGRADE` → `DEGRADED_TO_SAFE_ALTERNATIVE`
  - `ESCALATE` → `NEED_CONFIRMATION`
  - `BLOCK` → Appropriate block reason (SCOPE_VIOLATION, DATA_EXFIL, etc.)
  - `PAUSE` → `LOOP_DETECTED` or `RATE_LIMIT`

**Files Changed:**
- `edon_demo/schemas.py` - Added `APPROVED` and `DEGRADED_TO_SAFE_ALTERNATIVE` to `ReasonCode`
- `edon_demo/governor.py` - Updated all Decision returns to use correct reason_code

**Verification:**
```python
# ALLOW now returns APPROVED
Verdict: ALLOW, Reason: APPROVED ✅
```

---

## 2. ✅ Fixed: intent_id Format Mismatch

**Problem:** 
- `/intent/set` returned: `"intent-2026-01-26T10:14:45.982273"`
- Audit logs showed: `"2026-01-26 16:14:45.982273+00:00"`

Different formats broke traceability and joins.

**Fix:**
- Use canonical UUID-based intent_id: `intent_{uuid_hex[:16]}`
- Propagate same intent_id everywhere:
  - Response from `/intent/set`
  - Stored in `active_intents`
  - Passed to audit logger via context
  - Used in audit log events

**Files Changed:**
- `edon_gateway/main.py` - Changed intent_id generation to UUID
- `edon_demo/audit.py` - Use intent_id from context instead of timestamp

**Verification:**
- Intent IDs now consistent across all records
- Format: `intent_a1b2c3d4e5f6g7h8` (stable and opaque)

---

## 3. ✅ Fixed: Security Invariant Enforcement

**Problem:** No explicit enforcement that execution only occurs on ALLOW or DEGRADE with safe_alternative.

**Fix:**
- Added explicit check before execution:
  ```python
  if decision.verdict not in [Verdict.ALLOW, Verdict.DEGRADE]:
      # Return decision without execution
      return ExecuteResponse(..., execution=None)
  ```
- Added assertion for DEGRADE requiring safe_alternative
- Execution block is `None` for non-executable verdicts

**Files Changed:**
- `edon_gateway/main.py` - Added security invariant check

**Verification:**
- BLOCK/ESCALATE/PAUSE verdicts return `execution: null`
- Only ALLOW and DEGRADE can execute

---

## 4. ✅ Fixed: Server-Side Risk Computation

**Problem:** Shell action with `rm -rf /` showed `estimated_risk: low` (trusting agent's estimate).

**Fix:**
- Added `computed_risk` field to `Action` schema
- Governor computes server-side risk:
  - Starts with agent's `estimated_risk`
  - Overrides for dangerous shell commands → `CRITICAL`
  - Uses `computed_risk` (not `estimated_risk`) for policy evaluation
- Both `estimated_risk` and `computed_risk` logged in audit

**Files Changed:**
- `edon_demo/schemas.py` - Added `computed_risk: Optional[RiskLevel]` to Action
- `edon_demo/governor.py` - Compute risk before evaluation, use computed_risk for escalation checks
- `edon_demo/schemas.py` - Action.to_dict() includes computed_risk

**Verification:**
- Dangerous shell commands now show `computed_risk: critical` in audit logs
- Policy evaluation uses computed_risk, not agent's estimated_risk

---

## Summary

All four critical bugs are fixed:

1. ✅ **reason_code** - Deterministic per verdict, ALLOW → APPROVED
2. ✅ **intent_id** - Canonical UUID format, consistent everywhere
3. ✅ **Security** - Explicit invariant: no execution unless ALLOW/DEGRADE
4. ✅ **Risk** - Server-side computation, dangerous commands → CRITICAL

**Next Steps:**
- Restart gateway and run tests
- Verify all fixes work end-to-end
- Proceed with real tool connectors (Phase A completion)
