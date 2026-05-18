"""Safety invariant test suite for the EDON governance engine.

These tests verify properties that must hold under ALL conditions, including
failure conditions. Fault injection is used to prove EDON fails safely.

Each test is labelled with the invariant ID it exercises and a brief rationale.
Run with:
    pytest backend/edon_gateway/tests/invariants/ -v
"""

from __future__ import annotations

import concurrent.futures
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC

from ...governor import EDONGovernor, FAIL_SAFE_ALLOW
from ...schemas import (
    Action,
    Tool,
    IntentContract,
    RiskLevel,
    ActionSource,
    Verdict,
    Decision,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_action(
    tool_str: str,
    op: str,
    risk: str = "low",
    params: dict | None = None,
) -> Action:
    """Build a minimal Action for testing.

    Args:
        tool_str: Tool enum value string (e.g. "database", "shell").
        op:       Operation name (e.g. "truncate", "execute").
        risk:     RiskLevel value string (default "low").
        params:   Optional extra params dict.
    """
    tool_enum = Tool(tool_str) if tool_str in Tool._value2member_map_ else Tool.CUSTOM
    return Action(
        tool=tool_enum,
        op=op,
        params=params or {},
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=[],
        estimated_risk=RiskLevel(risk),
    )


def make_intent(
    risk: str = "low",
    scope: dict | None = None,
    objective: str = "test objective for governance evaluation",
    approved_by_user: bool = True,
    constraints: dict | None = None,
) -> IntentContract:
    """Build a minimal IntentContract for testing.

    Args:
        risk:           RiskLevel value string (default "low").
        scope:          Tool→ops scope dict (default permissive for all tools).
        objective:      Human-readable objective string.
        approved_by_user: Whether the user has approved.
        constraints:    Optional extra constraints.
    """
    if scope is None:
        scope = {
            "email": ["send", "draft", "read"],
            "shell": ["execute", "run"],
            "database": ["query", "truncate", "drop", "delete"],
            "file": ["read", "write", "delete"],
            "calendar": ["create", "read", "update"],
            "custom": ["unknown_operation_xyz"],
        }
    return IntentContract(
        objective=objective,
        scope=scope,
        constraints=constraints or {},
        risk_level=RiskLevel(risk),
        approved_by_user=approved_by_user,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def governor() -> EDONGovernor:
    """Fresh governor with no DB and default policy config."""
    return EDONGovernor()


# ── INV-1: BLOCK verdict cannot be upgraded to ALLOW through retry ────────────


def test_inv1_block_verdict_stable_across_retries(governor: EDONGovernor):
    """INV-1: Retrying a BLOCK decision must never produce ALLOW.

    Rationale: retrying should never flip a governance decision. If an action
    is blocked on the first call it must stay blocked on every subsequent call
    with identical inputs.  A flip to ALLOW would let an adversary loop-retry
    until a race or transient state opens the gate.
    """
    # database.truncate has CRITICAL blast-radius floor — will be BLOCK/ESCALATE
    action = make_action("database", "truncate", risk="critical")
    intent = make_intent(
        risk="critical",
        scope={"database": ["truncate"]},
        objective="truncate database table",
    )

    verdicts = []
    for _ in range(5):
        result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])
        verdicts.append(str(result.verdict).upper())

    for v in verdicts:
        assert v in ("BLOCK", "ESCALATE"), (
            f"INV-1 VIOLATED: retry produced {v} — expected BLOCK or ESCALATE only. "
            f"Full verdict sequence: {verdicts}"
        )


# ── INV-2: Policy engine error produces BLOCK (fail-closed by default) ────────


@pytest.mark.skipif(
    FAIL_SAFE_ALLOW,
    reason="INV-2 only applies when EDON_STRICT_FAIL_CLOSED=true (not FAIL_SAFE_ALLOW)",
)
def test_inv2_policy_engine_error_produces_block(governor: EDONGovernor):
    """INV-2: An exception inside _evaluate_impl must produce Verdict.BLOCK.

    Rationale: EDON_STRICT_FAIL_CLOSED=true is the default. When the policy
    engine throws, governance must default to BLOCK rather than silently
    allowing the action through.  Any other behavior lets a fault-injection
    attack bypass governance.
    """
    action = make_action("email", "send", risk="low")
    intent = make_intent()

    with patch.object(
        governor,
        "_evaluate_impl",
        side_effect=RuntimeError("injected failure"),
    ):
        result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])

    assert str(result.verdict).upper() == "BLOCK", (
        f"INV-2 VIOLATED: policy engine error produced {result.verdict} — "
        "expected BLOCK when EDON_STRICT_FAIL_CLOSED=true"
    )
    assert isinstance(result, Decision), "evaluate() must always return a Decision"


# ── INV-3: CRITICAL blast-radius actions are never plain ALLOW ────────────────


@pytest.mark.parametrize("tool_str,op,risk,params", [
    ("database", "truncate", "critical", {}),
    ("database", "drop",     "critical", {}),
    ("shell",    "execute",  "high",     {"command": "rm -rf /important/data"}),
])
def test_inv3_critical_blast_radius_never_allow(
    governor: EDONGovernor,
    tool_str: str,
    op: str,
    risk: str,
    params: dict,
):
    """INV-3: Actions with CRITICAL blast radius must never produce plain ALLOW.

    Rationale: the blast-radius floor in the governor means these operations
    carry minimum CRITICAL/HIGH risk regardless of what a tenant configures.
    Absence of explicit allow rules must not silently permit them.
    """
    action = make_action(tool_str, op, risk=risk, params=params)
    # Fresh intent with wide scope but no tenant rules — tests the default floor
    intent = make_intent(
        risk=risk,
        scope={tool_str: [op]},
        objective=f"{tool_str} {op} operation",
    )

    result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])

    assert str(result.verdict).upper() != "ALLOW", (
        f"INV-3 VIOLATED: {tool_str}.{op} produced Verdict.ALLOW — "
        "critical blast-radius actions must never be plain ALLOW without explicit rules"
    )


# ── INV-4: Unknown action type produces ESCALATE, not ALLOW ──────────────────


def test_inv4_unknown_action_produces_escalate_not_allow(governor: EDONGovernor):
    """INV-4: An unknown/ungoverned action must produce ESCALATE, not ALLOW.

    Rationale: _UNGOVERNED_VERDICT = "ESCALATE" in the policy engine.
    Ungoverned is not the same as permitted — it means a human reviewer must
    inspect the action before it proceeds.  ALLOW on an ungoverned action
    would create a silent bypass for novel tool types.
    """
    action = make_action("custom", "unknown_operation_xyz", risk="low")
    # Intent has no policy rules configured — governor and policy engine see
    # a completely unknown action type.
    intent = make_intent(
        risk="low",
        scope={"custom": ["unknown_operation_xyz"]},
        objective="custom operation",
    )

    result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])

    assert str(result.verdict).upper() != "ALLOW", (
        f"INV-4 VIOLATED: unknown action produced Verdict.ALLOW — "
        "ungoverned actions must reach ESCALATE, not be silently permitted. "
        f"Got: {result.verdict}"
    )


# ── INV-5: High/critical risk actions never plain ALLOW without policy rules ──


@pytest.mark.parametrize("tool_str,op", [
    ("email",    "send"),
    ("file",     "read"),
    ("calendar", "create"),
])
def test_inv5_high_critical_risk_never_plain_allow(
    governor: EDONGovernor,
    tool_str: str,
    op: str,
):
    """INV-5: High/critical risk level actions must not produce plain ALLOW.

    Rationale: the governor's escalate_risk_levels gate is {"high", "critical"}.
    Any action submitted with CRITICAL risk must reach a human reviewer
    (ESCALATE) or be blocked (BLOCK) — never silently allowed through.
    """
    action = make_action(tool_str, op, risk="critical")
    intent = make_intent(
        risk="critical",
        scope={tool_str: [op]},
        objective=f"high risk {tool_str} {op} task",
        approved_by_user=False,  # no pre-approval — forces escalation gate
    )

    result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])

    assert str(result.verdict).upper() in ("ESCALATE", "BLOCK"), (
        f"INV-5 VIOLATED: {tool_str}.{op} at CRITICAL risk produced {result.verdict} — "
        "must be ESCALATE or BLOCK, never ALLOW, without explicit policy rules"
    )


# ── INV-6: Governor evaluate() never raises — always returns a Decision ───────


@pytest.mark.parametrize("exc_type,exc_args", [
    (RuntimeError,                    ("simulated runtime error",)),
    (MemoryError,                     ("simulated memory error",)),
    (KeyError,                        ("missing field",)),
    (concurrent.futures.TimeoutError, ()),
])
def test_inv6_governor_never_raises_always_returns_decision(
    governor: EDONGovernor,
    exc_type: type,
    exc_args: tuple,
):
    """INV-6: governor.evaluate() must never propagate exceptions to the caller.

    Rationale: governance must never crash an agent's execution.  Whatever
    internal failure occurs, evaluate() must catch it, apply fail-closed
    semantics, and return a well-formed Decision.  An unhandled exception
    here would bypass all downstream safety checks.

    Tested exception types:
      - RuntimeError     — generic logic failure
      - MemoryError      — resource exhaustion
      - KeyError         — missing field / schema mismatch
      - TimeoutError     — policy engine timeout (concurrent.futures)
    """
    action = make_action("email", "send", risk="low")
    intent = make_intent()

    # Patch PolicyEngine.evaluate (the inner engine call) to raise the injected error.
    # We target the PolicyEngine instance on the governor so other governor
    # methods (invariant recording, _attach_provenance) remain functional.
    with patch.object(
        governor.policy_engine,
        "evaluate",
        side_effect=exc_type(*exc_args),
    ):
        raised = None
        result = None
        try:
            result = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])
        except Exception as e:
            raised = e

    assert raised is None, (
        f"INV-6 VIOLATED: governor.evaluate() raised {type(raised).__name__}({raised}) "
        f"when PolicyEngine raised {exc_type.__name__} — must never propagate"
    )
    assert result is not None, "INV-6: evaluate() returned None instead of a Decision"
    assert isinstance(result, Decision), (
        f"INV-6: evaluate() returned {type(result)} — must return a Decision instance"
    )
    # Fail-closed: when strict mode is on, the error verdict must be BLOCK
    if not FAIL_SAFE_ALLOW:
        assert str(result.verdict).upper() == "BLOCK", (
            f"INV-6 VIOLATED: exception produced verdict {result.verdict} — "
            "expected BLOCK under EDON_STRICT_FAIL_CLOSED=true"
        )
