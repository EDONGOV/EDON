"""Support case intake regressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.edon_gateway.config as cfg
import backend.edon_gateway.routes.support as support


@pytest.fixture(autouse=True)
def _support_env(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_SUPPORT_WEBHOOK_URL", "")
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_SUPPORT_WEBHOOK_URL", "")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.edon_gateway.persistence.database import Database

    db = Database(Path(tmp_path) / "support-cases.db")
    db.create_user("user-1", "ops@example.com", "clerk", "subject-1", role="admin")
    db.create_tenant("tenant-1", "user-1")

    monkeypatch.setattr(support, "get_db", lambda: db)
    monkeypatch.setattr(support, "get_request_tenant_id", lambda request: "tenant-1")

    from backend.edon_gateway.main import app

    with TestClient(app) as c:
        yield c


def test_support_ticket_create_list_and_detail(client: TestClient):
    payload = {
        "summary": "Epic writeback blocked for tenant",
        "severity": "sev2",
        "tab": "settings",
        "reviewer_name": "ops-admin",
        "department": "informatics",
        "issue_type": "incident",
        "chat_history": [],
        "notes": "Need tenant-specific review",
        "diagnostics": {
            "support_code": "SUP-ABCD1234",
            "tenant_id": "tenant-1",
            "role": "admin",
            "plan": "enterprise",
            "vertical": "healthcare",
            "gateway_version": "1.0.1",
            "request_id": "req-123",
            "decision_id": "dec-123",
            "action_id": "act-123",
            "trace_id": "trace-123",
            "conversation_id": "conv-123",
            "problem_description": "Epic writeback blocked",
            "affected_system": "Epic",
            "workflow_id": "wf-123",
            "connector": "epic",
        },
    }

    created = client.post("/support/ticket", json=payload)
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["status"] == "open"
    assert created_body["severity"] == "sev2"
    assert created_body["support_code"] == "SUP-ABCD1234"

    case_id = created_body["case_id"]

    listed = client.get("/support/cases")
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["count"] == 1
    assert listed_body["cases"][0]["case_id"] == case_id
    assert listed_body["cases"][0]["evidence_bundle"]["connector"] == "epic"

    detail = client.get(f"/support/cases/{case_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["case_id"] == case_id
    assert detail_body["support_code"] == "SUP-ABCD1234"
    assert detail_body["timeline"][0]["event"] == "created"
