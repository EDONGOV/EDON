from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_onboarding_runtime_register_review_promote(tmp_path, monkeypatch):
    from backend.edon_gateway.onboarding.profile import OnboardingStore
    import backend.edon_gateway.routes.onboarding as onboarding_routes
    import backend.edon_gateway.routes.audit as audit_routes
    from backend.edon_gateway.persistence.database import Database

    onboarding_store = OnboardingStore(str(Path(tmp_path) / "onboarding-runtime.db"))
    db = Database(Path(tmp_path) / "gateway-runtime.db")
    db.create_user("user-1", "tenant@example.com", "clerk", "subject-1", role="admin")
    db.create_tenant("tenant-1", "user-1")

    monkeypatch.setattr(onboarding_routes, "get_onboarding_store", lambda: onboarding_store)
    monkeypatch.setattr(onboarding_routes, "get_db", lambda: db)
    monkeypatch.setattr(onboarding_routes, "get_request_tenant_id", lambda request: "tenant-1")
    monkeypatch.setattr(audit_routes, "get_db", lambda: db)
    monkeypatch.setattr(audit_routes, "get_request_tenant_id", lambda request: "tenant-1")

    from backend.edon_gateway.main import app

    register_body = {
        "runtime_name": "Cardiology Note Helper",
        "vendor_name": "VendorOne",
        "vendor_id": "vendor-001",
        "source_type": "Vendor console",
        "agent_count": 12,
        "department": "Cardiology",
        "purpose": "Draft clinical notes",
        "runtime_type": "Service",
        "requested_access": ["Epic.note.draft", "Teams.escalation.notify", "SIEM.audit.export"],
        "connectors": ["Epic", "Teams", "SIEM"],
    }

    with TestClient(app) as client:
        register_resp = client.post("/v1/onboarding/runtimes", json=register_body)
        assert register_resp.status_code == 200, register_resp.text
        runtime = register_resp.json()["runtime"]
        runtime_id = runtime["runtime_id"]

        assert runtime["tenant_id"] == "tenant-1"
        assert runtime["status"] == "observing"
        assert runtime["governance_mode"] == "shadow"
        assert runtime["vendor_name"] == "VendorOne"
        assert runtime["vendor_id"] == "vendor-001"
        assert runtime["risk_tier"] in {"medium", "high", "critical"}

        list_resp = client.get("/v1/onboarding/runtimes")
        assert list_resp.status_code == 200, list_resp.text
        assert list_resp.json()["count"] == 1

        review_resp = client.post(
            f"/v1/onboarding/runtimes/{runtime_id}/review",
            json={"reviewed_by": "Governance admin", "approved": True, "notes": "Looks good"},
        )
        assert review_resp.status_code == 200, review_resp.text
        reviewed = review_resp.json()["runtime"]
        assert reviewed["review_status"] == "approved"
        assert reviewed["status"] == "reviewed"

        promote_resp = client.post(
            f"/v1/onboarding/runtimes/{runtime_id}/promote",
            json={"promoted_by": "Governance admin"},
        )
        assert promote_resp.status_code == 200, promote_resp.text
        promoted = promote_resp.json()["runtime"]
        agent = promote_resp.json()["agent"]
        assert promoted["status"] == "promoted"
        assert promoted["governance_mode"] == "governed"
        assert agent["agent_id"] == runtime_id
        assert agent["vendor_id"] == "vendor-001"
        assert agent["department"] == "Cardiology"

        report_resp = client.get("/audit/report/export?format=json&limit=20")
        assert report_resp.status_code == 200, report_resp.text
        report = report_resp.json()
        assert report["tenant_id"] == "tenant-1"
        assert report["summary"]["total_decisions"] >= 3
        assert report["export_proof"]["algorithm"] == "sha256"
        assert report["export_proof"]["event_count"] >= 3
        assert report["export_proof"]["payload_hash"]

    events = db.query_audit_events(customer_id="tenant-1", limit=20)
    event_ops = [(event["action"]["tool"], event["action"]["op"]) for event in events]
    assert ("onboarding", "register_runtime") in event_ops
    assert ("onboarding", "review_runtime") in event_ops
    assert ("onboarding", "promote_runtime") in event_ops

    stored_agent = db.get_agent(runtime_id, tenant_id="tenant-1")
    assert stored_agent is not None
    assert stored_agent["name"] == "Cardiology Note Helper"
    assert stored_agent["metadata"]["vendor_name"] == "VendorOne"
