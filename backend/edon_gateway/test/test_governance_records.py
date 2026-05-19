from __future__ import annotations

from backend.edon_gateway.governance_records import (
    DecisionRecord,
    build_decision_record,
    build_execution_token,
    build_policy_replay_bundle,
    verify_execution_token,
)
from backend.edon_gateway.schemas import Action, Decision, ReasonCode, RiskLevel, Tool, Verdict


def test_decision_record_and_execution_token_are_signed():
    action = Action(
        tool=Tool.EMAIL,
        op="send",
        params={"to": "user@example.com"},
        estimated_risk=RiskLevel.HIGH,
        data_class="PHI",
        connector_scope=["epic.record.writeback"],
    )
    decision = Decision(
        verdict=Verdict.ALLOW,
        reason_code=ReasonCode.APPROVED,
        explanation="Approved",
        policy_version="2.1.0",
        policy_snapshot_hash="snapshot-abc",
    )
    record = build_decision_record(
        decision_id="dec-1",
        tenant_id="tenant-a",
        actor_id="user-a",
        agent_id="agent-a",
        action_type="epic.record.writeback",
        risk_tier="high",
        verdict=decision.verdict.value,
        context={
            "data_class": "PHI",
            "connector_scope": ["epic.record.writeback"],
            "approval_chain": [{"step": "manager", "approved": True}],
            "actor_role": "governance_admin",
            "rollback_mode": "partial",
        },
        policy_version=decision.policy_version,
        reason_code=decision.reason_code.value,
        issued_at="2026-05-19T10:00:00+00:00",
        request_hash="req-abc",
    )

    assert isinstance(record, DecisionRecord)
    assert record.signature
    token = build_execution_token(record)
    assert token["token"].startswith("ey")
    assert token["payload"]["decision_id"] == "dec-1"
    verified = verify_execution_token(
        token,
        tenant_id="tenant-a",
        action_type="epic.record.writeback",
    )
    assert verified["decision_id"] == "dec-1"

    replay = build_policy_replay_bundle(
        record=record,
        decision_row={"explanation": decision.explanation},
        audit_event={"audit_id": "audit-1"},
    )
    assert replay["policy_version_at_time"] == "2.1.0"
    assert replay["policy_snapshot"]["policy_snapshot_hash"] == record.policy_snapshot_hash
    assert replay["decision_record"]["signature"]
