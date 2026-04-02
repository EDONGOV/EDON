"""Tests for /learning routes and predictive /v1/action escalation."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _DummyPrediction:
    def __init__(self, score: float, reasons: list[str], signal_breakdown: Dict[str, float]) -> None:
        self.score = score
        self.reasons = reasons
        self.signal_breakdown = signal_breakdown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "reasons": self.reasons,
            "signal_breakdown": self.signal_breakdown,
        }


class _DummyLearningEngine:
    def __init__(self) -> None:
        self.feedback_events: list[Dict[str, Any]] = []
        self.federated_opt_in_calls: list[Dict[str, Any]] = []

    def predict_action(self, **_kwargs) -> _DummyPrediction:
        return _DummyPrediction(
            score=0.91,
            reasons=["synthetic high-risk test signal"],
            signal_breakdown={"fleet_prior": 0.5, "novelty": 0.41},
        )

    def record_feedback(self, **kwargs) -> None:
        self.feedback_events.append(kwargs)

    def set_federated_opt_in(self, **kwargs) -> None:
        self.federated_opt_in_calls.append(kwargs)

    def model_summary(self, tenant_id: str | None = None) -> Dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "feedback_samples": len(self.feedback_events),
            "negative_labels": 0,
            "negative_rate": 0.0,
            "top_labeled_tool_ops": [],
        }


class _DummyDb:
    def get_tenant(self, _tenant_id: str) -> Dict[str, Any]:
        return {"plan": "pro"}

    def get_agent_count(self, _tenant_id: str) -> int:
        return 0

    def register_agent(self, _tenant_id: str, _agent_id: str) -> bool:
        return False

    def get_active_policy_preset(self):
        return None

    def get_policy_rules(self, _tenant_id: str, enabled_only: bool = True):
        return []

    def save_audit_event(self, **_kwargs) -> str:
        return "dec_test_123"

    def update_agent_stats(self, _agent_id: str, _verdict: str, tenant_id: str | None = None) -> None:
        return None


def _setup_test_client(monkeypatch):
    import edon_gateway.routes.learning as learning_route
    import edon_gateway.routes.v1_action as v1_action_route

    app = FastAPI()
    engine = _DummyLearningEngine()
    db = _DummyDb()

    monkeypatch.setattr(learning_route, "get_fleet_learning_engine", lambda: engine)
    monkeypatch.setattr(v1_action_route, "get_fleet_learning_engine", lambda: engine)
    monkeypatch.setattr(learning_route, "get_db", lambda: db)
    monkeypatch.setattr(v1_action_route, "get_db", lambda: db)
    monkeypatch.setattr(learning_route, "get_request_tenant_id", lambda _request: "tenant_test")
    monkeypatch.setattr(v1_action_route, "get_request_tenant_id", lambda _request: "tenant_test")

    app.include_router(learning_route.router)
    app.include_router(v1_action_route.router)
    return TestClient(app), engine


def test_learning_endpoints_predict_feedback_federated_summary(monkeypatch):
    client, engine = _setup_test_client(monkeypatch)

    predict_resp = client.post(
        "/learning/predict",
        json={"agent_id": "agent-1", "action_type": "email.send", "estimated_risk": "high"},
    )
    assert predict_resp.status_code == 200, predict_resp.text
    predict_body = predict_resp.json()
    assert predict_body["tenant_id"] == "tenant_test"
    assert predict_body["prediction"]["score"] == 0.91

    feedback_resp = client.post(
        "/learning/feedback",
        json={
            "agent_id": "agent-1",
            "action_type": "email.send",
            "label": "safe",
            "predicted_risk": 0.42,
            "source": "operator",
        },
    )
    assert feedback_resp.status_code == 200, feedback_resp.text
    assert feedback_resp.json()["ok"] is True
    assert len(engine.feedback_events) >= 1

    opt_in_resp = client.post("/learning/federated-opt-in", json={"opt_in": True})
    assert opt_in_resp.status_code == 200, opt_in_resp.text
    assert opt_in_resp.json()["tenant_id"] == "tenant_test"
    assert opt_in_resp.json()["federated_opt_in"] is True
    assert len(engine.federated_opt_in_calls) == 1

    summary_resp = client.get("/learning/model/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary["tenant_id"] == "tenant_test"
    assert "feedback_samples" in summary


def test_v1_action_predictive_escalation_exposes_prediction_fields(monkeypatch):
    client, _engine = _setup_test_client(monkeypatch)

    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "agent-risky",
            "action_type": "email.send",
            "action_payload": {"to": "ops@example.com"},
            "timestamp": "2026-02-26T10:30:00Z",
            "context": {"risk_estimate": "high"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "HUMAN_REQUIRED"
    assert "predicted_oob_risk" in body
    assert body["predicted_oob_risk"] >= 0.82
    assert body["predicted_oob_reasons"] == ["synthetic high-risk test signal"]
    assert "predictive_oob_risk" not in body
