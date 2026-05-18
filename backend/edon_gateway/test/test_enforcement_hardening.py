from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.edon_gateway.schemas import Action, Decision, IntentContract, ReasonCode, RiskLevel, Tool, Verdict


class _DummyDb:
    def get_tenant(self, _tenant_id: str):
        return {"plan": "pro"}

    def get_agent_count(self, _tenant_id: str) -> int:
        return 0

    def register_agent(self, _tenant_id: str, _agent_id: str) -> bool:
        return False

    def update_agent_stats(self, *_args, **_kwargs) -> None:
        return None

    def check_device_binding_valid(self, *_args, **_kwargs):
        return {"allowed": True, "requires_supervision": False}

    def get_device(self, *_args, **_kwargs):
        return {"status": "available"}

    def acquire_device_lock(self, *_args, **_kwargs):
        return None


class _AllowGovernor:
    def evaluate(self, *args, **kwargs):
        return Decision(
            verdict=Verdict.ALLOW,
            reason_code=ReasonCode.APPROVED,
            explanation="ok",
        )


class _DummyLearningEngine:
    def record_feedback(self, **_kwargs):
        return None

    def record_sequence_feedback(self, **_kwargs):
        return None


def _intent() -> IntentContract:
    return IntentContract(
        objective="operate robot",
        scope={"robot": ["actuate"]},
        constraints={},
        risk_level=RiskLevel.LOW,
        approved_by_user=True,
    )


def _action() -> Action:
    return Action(
        tool=Tool.ROBOT,
        op="actuate",
        params={"device": "robot-1"},
        estimated_risk=RiskLevel.LOW,
    )


def test_v1_action_fails_closed_when_audit_persistence_fails(monkeypatch):
    import backend.edon_gateway.audit_queue as audit_queue
    import backend.edon_gateway.routes.v1_action as v1_action_route

    app = FastAPI()
    app.state.governor = _AllowGovernor()
    app.include_router(v1_action_route.router)

    db = _DummyDb()
    monkeypatch.setattr(v1_action_route, "get_db", lambda: db)
    monkeypatch.setattr(v1_action_route, "get_request_tenant_id", lambda _request: "tenant-a")
    monkeypatch.setattr(v1_action_route, "run_preflight", lambda ctx: None)
    monkeypatch.setattr(v1_action_route, "load_intent", lambda _db, _intent_id, _tenant_id: (_intent(), "intent-1"))
    monkeypatch.setattr(v1_action_route, "get_fleet_learning_engine", lambda: _DummyLearningEngine())
    async def _audit_fail(*_args, **_kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(audit_queue, "enqueue_audit", _audit_fail)

    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "agent-1",
            "action_type": "robot.actuate",
            "action_payload": {"device": "robot-1"},
            "timestamp": "2026-02-26T10:30:00Z",
            "context": {"intent_id": "intent-1"},
            "device_id": "robot-1",
        },
    )

    assert resp.status_code == 503
    assert "audit" in resp.json()["detail"].lower()


def test_v1_action_fails_closed_when_device_lock_cannot_be_acquired(monkeypatch):
    import backend.edon_gateway.audit_queue as audit_queue
    import backend.edon_gateway.routes.v1_action as v1_action_route

    class _Db(_DummyDb):
        def acquire_device_lock(self, *_args, **_kwargs):
            return None

    app = FastAPI()
    app.state.governor = _AllowGovernor()
    app.include_router(v1_action_route.router)

    db = _Db()
    monkeypatch.setattr(v1_action_route, "get_db", lambda: db)
    monkeypatch.setattr(v1_action_route, "get_request_tenant_id", lambda _request: "tenant-a")
    monkeypatch.setattr(v1_action_route, "run_preflight", lambda ctx: None)
    monkeypatch.setattr(v1_action_route, "load_intent", lambda _db, _intent_id, _tenant_id: (_intent(), "intent-1"))
    monkeypatch.setattr(v1_action_route, "get_fleet_learning_engine", lambda: _DummyLearningEngine())
    async def _audit_ok(*_args, **_kwargs):
        return "dec-1"

    monkeypatch.setattr(audit_queue, "enqueue_audit", _audit_ok)

    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "agent-1",
            "action_type": "robot.actuate",
            "action_payload": {"device": "robot-1"},
            "timestamp": "2026-02-26T10:30:00Z",
            "context": {"intent_id": "intent-1"},
            "device_id": "robot-1",
        },
    )

    assert resp.status_code == 409
    assert "mutex" in resp.json()["detail"].lower() or "available" in resp.json()["detail"].lower()


def test_v1_action_fails_closed_when_preflight_audit_persistence_fails(monkeypatch):
    import backend.edon_gateway.audit_queue as audit_queue
    import backend.edon_gateway.routes.v1_action as v1_action_route

    class _PreflightResponse:
        action_id = "pf-1"
        decision = "BLOCK"
        reason_code = "POLICY_ENGINE_ERROR"
        decision_reason = "preflight blocked"

    app = FastAPI()
    app.state.governor = _AllowGovernor()
    app.include_router(v1_action_route.router)

    db = _DummyDb()
    monkeypatch.setattr(v1_action_route, "get_db", lambda: db)
    monkeypatch.setattr(v1_action_route, "get_request_tenant_id", lambda _request: "tenant-a")
    monkeypatch.setattr(v1_action_route, "run_preflight", lambda ctx: _PreflightResponse())
    monkeypatch.setattr(v1_action_route, "load_intent", lambda _db, _intent_id, _tenant_id: (_intent(), "intent-1"))
    monkeypatch.setattr(v1_action_route, "get_fleet_learning_engine", lambda: _DummyLearningEngine())

    async def _audit_fail(*_args, **_kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(audit_queue, "enqueue_audit", _audit_fail)

    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "agent-1",
            "action_type": "robot.actuate",
            "action_payload": {"device": "robot-1"},
            "timestamp": "2026-02-26T10:30:00Z",
            "context": {"intent_id": "intent-1"},
            "device_id": "robot-1",
        },
    )

    assert resp.status_code == 503
    assert "preflight" in resp.json()["detail"].lower()


def test_v1_action_fails_closed_when_agent_limit_check_fails_in_production(monkeypatch):
    import backend.edon_gateway.routes.v1_action as v1_action_route

    class _ProdConfig:
        @staticmethod
        def is_production():
            return True

    class _Db(_DummyDb):
        def get_tenant(self, _tenant_id: str):
            raise RuntimeError("billing unavailable")

    app = FastAPI()
    app.state.governor = _AllowGovernor()
    app.include_router(v1_action_route.router)

    db = _Db()
    monkeypatch.setattr(v1_action_route, "config", _ProdConfig())
    monkeypatch.setattr(v1_action_route, "get_db", lambda: db)
    monkeypatch.setattr(v1_action_route, "get_request_tenant_id", lambda _request: "tenant-a")
    monkeypatch.setattr(v1_action_route, "run_preflight", lambda ctx: None)
    monkeypatch.setattr(v1_action_route, "load_intent", lambda _db, _intent_id, _tenant_id: (_intent(), "intent-1"))
    monkeypatch.setattr(v1_action_route, "get_fleet_learning_engine", lambda: _DummyLearningEngine())

    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "agent-1",
            "action_type": "robot.actuate",
            "action_payload": {"device": "robot-1"},
            "timestamp": "2026-02-26T10:30:00Z",
            "context": {"intent_id": "intent-1"},
            "device_id": "robot-1",
        },
    )

    assert resp.status_code == 503
    assert "agent limit" in resp.json()["detail"].lower()


def test_governor_blocks_mag_enabled_action_without_binding(monkeypatch):
    import backend.edon_gateway.governor as governor_module

    governor = governor_module.EDONGovernor()
    intent = _intent()
    action = _action()

    monkeypatch.setattr(governor_module, "mag_enabled_for_tenant", lambda _tenant_id: True)
    monkeypatch.setattr(governor_module, "authorize_action", lambda *args, **kwargs: {"verdict": "allow"})

    decision = governor.evaluate(
        action=action,
        intent=intent,
        context={"tenant_id": "tenant-mag", "agent_id": "agent-1"},
        tenant_id="tenant-mag",
    )

    assert decision.verdict == Verdict.BLOCK
    assert decision.reason_code == ReasonCode.POLICY_ENGINE_ERROR
    assert any(
        r["id"] == "INV-005-MAG-AUTH" and r["status"] == "fail"
        for r in decision.invariant_results
    )


def test_governor_blocks_policy_engine_exceptions_in_production(monkeypatch):
    import backend.edon_gateway.governor as governor_module

    governor = governor_module.EDONGovernor()
    intent = _intent()
    action = _action()

    monkeypatch.setattr(governor_module, "_IS_PRODUCTION", True)
    monkeypatch.setattr(governor_module, "_STRICT_FAIL_CLOSED", False)
    monkeypatch.setattr(governor_module, "POLICY_FAIL_SAFE", "allow_with_log")
    monkeypatch.setattr(governor_module, "mag_enabled_for_tenant", lambda _tenant_id: True)
    monkeypatch.setattr(governor_module, "authorize_action", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("policy engine down")))

    decision = governor.evaluate(
        action=action,
        intent=intent,
        context={
            "tenant_id": "tenant-prod",
            "agent_id": "agent-1",
            "mag_decision_id": "decision-1",
            "mag_decision_bundle": {"decision_id": "decision-1"},
        },
        tenant_id="tenant-prod",
    )

    assert decision.verdict == Verdict.BLOCK
    assert decision.reason_code == ReasonCode.POLICY_ENGINE_ERROR


def test_kill_switch_activation_fails_closed_when_estop_propagation_fails(monkeypatch):
    import backend.edon_gateway.routes.kill_switch as kill_switch_route
    import backend.edon_gateway.persistence as persistence
    import backend.edon_gateway.estop as estop_module

    class _Db:
        def set_kill_switch(self, *_args, **_kwargs):
            return None

        def get_kill_switch(self, tenant_id: str):
            return {"active": False, "tenant_id": tenant_id}

    app = FastAPI()
    app.include_router(kill_switch_route.router)

    db = _Db()
    monkeypatch.setattr(persistence, "get_db", lambda: db)
    monkeypatch.setattr(kill_switch_route, "get_request_tenant_id", lambda _request: "tenant-a")
    monkeypatch.setattr(estop_module, "trigger_tenant_estop", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("estop down")))

    client = TestClient(app)
    resp = client.post(
        "/settings/kill-switch",
        json={"reason": "incident", "activated_by": "ops"},
    )

    assert resp.status_code == 503
    assert "safety controls" in resp.json()["detail"].lower()
