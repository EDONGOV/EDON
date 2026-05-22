from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_fleet_reconciliation_import_hold_merge_promote(tmp_path, monkeypatch):
    from backend.edon_gateway.persistence.database import Database
    import backend.edon_gateway.routes.reconciliation as reconciliation_routes

    db = Database(Path(tmp_path) / "gateway-reconciliation.db")
    db.create_user("user-1", "ops@example.com", "clerk", "subject-1", role="admin")
    db.create_tenant("tenant-1", "user-1")

    # Existing EDON fleet that should participate in reconciliation
    db.register_agent_full(
        agent_id="epic_note_drafter_01",
        tenant_id="tenant-1",
        name="Epic note drafter",
        agent_type="service",
        description="Draft notes",
        capabilities=["cardiology.note.draft"],
        vendor_id="Epic",
        department="Cardiology",
    )
    db.register_agent_full(
        agent_id="radiology_triage_bot",
        tenant_id="tenant-1",
        name="Radiology triage bot",
        agent_type="service",
        description="Triage imaging reports",
        capabilities=["radiology.report.draft"],
        vendor_id="Vendor console",
        department="Radiology",
    )
    db.register_agent_full(
        agent_id="legacy_ehr_bridge",
        tenant_id="tenant-1",
        name="Legacy EHR bridge",
        agent_type="service",
        description="Old connector",
        capabilities=["ehr.bridge.sync"],
        vendor_id="Legacy",
        department="EHR / Records",
    )

    monkeypatch.setattr(reconciliation_routes, "get_db", lambda: db)
    monkeypatch.setattr(reconciliation_routes, "get_request_tenant_id", lambda request: "tenant-1")

    from backend.edon_gateway.main import app

    import_body = {
        "source_system": "Existing system",
        "vendor_name": "Hospital AI Vendor",
        "vendor_id": "vend-42",
        "source_type": "Vendor console",
        "department": "Cardiology",
        "cohort_mode": "purpose",
        "posture": "audit-only",
        "inventory": [
            {
                "name": "Epic note drafter",
                "vendor": "Epic",
                "vendor_id": "Epic",
                "department": "Cardiology",
                "scope": "cardiology.note.draft",
                "action": "Register audit-only",
                "runtime_type": "Service",
                "connectors": ["Epic"],
            },
            {
                "name": "Radiology triage bot",
                "vendor": "Vendor console",
                "vendor_id": "Vendor console",
                "department": "Radiology",
                "scope": "radiology.report.writeback",
                "action": "Review scope drift",
                "runtime_type": "Service",
                "connectors": ["Epic"],
            },
            {
                "name": "Pharmacy lookup",
                "vendor": "CSV export",
                "vendor_id": "CSV export",
                "department": "Pharmacy",
                "scope": "pharmacy.lookup.read",
                "action": "Hold until re-found",
                "runtime_type": "Service",
                "connectors": ["CSV"],
            },
            {
                "name": "Pharmacy lookup",
                "vendor": "CSV export",
                "vendor_id": "CSV export",
                "department": "Pharmacy",
                "scope": "pharmacy.lookup.read",
                "action": "Hold until re-found",
                "runtime_type": "Service",
                "connectors": ["CSV"],
            },
            {
                "name": "Telemetry watcher",
                "vendor": "Inventory API",
                "vendor_id": "Inventory API",
                "department": "ICU",
                "scope": "icu.escalation.notify",
                "action": "Merge duplicate IDs",
                "runtime_type": "Service",
                "connectors": ["SIEM"],
            },
        ],
    }

    with TestClient(app) as client:
        import_resp = client.post("/v1/operations/reconciliation/import", json=import_body)
        assert import_resp.status_code == 200, import_resp.text
        batch = import_resp.json()["batch"]
        batch_id = batch["batch_id"]
        assert batch["summary"]["ready"] == 1
        assert batch["summary"]["changed"] == 1
        assert batch["summary"]["new"] == 2
        assert batch["summary"]["duplicate"] == 1
        assert batch["summary"]["missing"] == 1

        list_resp = client.get("/v1/operations/reconciliation")
        assert list_resp.status_code == 200, list_resp.text
        assert list_resp.json()["count"] == 1

        duplicate_row = next(row for row in batch["rows"] if row["status"] == "duplicate")
        merge_resp = client.post(
            f"/v1/operations/reconciliation/{batch_id}/rows/{duplicate_row['row_key']}/action",
            json={"actor": "Governance admin", "action": "merge_duplicate_ids", "notes": "Merged duplicate row"},
        )
        assert merge_resp.status_code == 200, merge_resp.text
        assert merge_resp.json()["row"]["status"] == "merged"

        hold_resp = client.post(
            f"/v1/operations/reconciliation/{batch_id}/hold",
            json={"actor": "Governance admin", "action": "hold", "notes": "Hold for review"},
        )
        assert hold_resp.status_code == 200, hold_resp.text
        assert hold_resp.json()["batch"]["status"] == "held"

        promote_resp = client.post(
            f"/v1/operations/reconciliation/{batch_id}/promote",
            json={"actor": "Governance admin", "action": "promote_low_risk_batch", "notes": "Promote safe cohort"},
        )
        assert promote_resp.status_code == 200, promote_resp.text
        promoted_batch = promote_resp.json()["batch"]
        assert promoted_batch["status"] == "promoted"
        assert promote_resp.json()["promoted"] >= 1

    promoted_agent = db.get_agent("epic_note_drafter_01", tenant_id="tenant-1")
    assert promoted_agent is not None
    assert promoted_agent["vendor_id"] == "Epic"
    assert promoted_agent["department"] == "Cardiology"

    audit = db.query_audit_events(customer_id="tenant-1", limit=20)
    ops = [(event["action"]["tool"], event["action"]["op"]) for event in audit]
    assert ("reconciliation", "import_batch") in ops
    assert ("reconciliation", "hold_batch") in ops
    assert ("reconciliation", "promote_batch") in ops
