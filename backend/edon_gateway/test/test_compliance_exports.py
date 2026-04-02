from fastapi import FastAPI
from fastapi.testclient import TestClient

from edon_gateway.routes import compliance as compliance_module


class _FakeDB:
    def query_audit_events(self, **_kwargs):
        return [
            {
                "timestamp": "2026-03-01T00:00:00Z",
                "created_at": "2026-03-01T00:00:00Z",
                "decision": {"verdict": "ALLOW", "reason_code": "APPROVED", "explanation": "ok"},
                "action": {"id": "act-1"},
                "anomaly_score": 0,
                "human_override": False,
            }
        ]

    def verify_audit_chain(self, **_kwargs):
        return {"valid": True, "checked": 1, "message": "Chain valid"}


def _make_client(monkeypatch):
    monkeypatch.setattr(compliance_module, "get_db", lambda: _FakeDB())
    monkeypatch.setattr(compliance_module, "get_request_tenant_id", lambda _request: "tenant_test")
    app = FastAPI()
    app.include_router(compliance_module.router)
    return TestClient(app)


def test_compliance_report_csv_export(monkeypatch):
    client = _make_client(monkeypatch)
    res = client.get("/compliance/report?format=csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "section,metric,value" in res.text


def test_compliance_evidence_export(monkeypatch):
    client = _make_client(monkeypatch)
    res = client.get("/compliance/evidence/export")
    assert res.status_code == 200
    body = res.json()
    assert body["tenant_id"] == "tenant_test"
    assert body["audit_chain_verification"]["valid"] is True
    assert body["event_count"] == 1
