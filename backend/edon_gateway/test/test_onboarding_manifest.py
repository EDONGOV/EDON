"""Onboarding manifest regressions."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_onboarding_manifest_pins_policy_and_market_pack(tmp_path, monkeypatch):
    from backend.edon_gateway.onboarding.profile import OnboardingStore
    import backend.edon_gateway.routes.onboarding as onboarding_routes

    store = OnboardingStore(str(Path(tmp_path) / "onboarding-manifest.db"))
    monkeypatch.setattr(onboarding_routes, "get_onboarding_store", lambda: store)
    monkeypatch.setattr(onboarding_routes, "get_request_tenant_id", lambda request: "tenant-1")

    from backend.edon_gateway.main import app

    manifest = {
        "tenant_id": "tenant-1",
        "org_name": "Acme Health",
        "deployment_mode": "pilot",
        "market_pack": "healthcare",
        "policy_pack": "hospital",
        "identity_provider": "entra",
        "environments": ["saas"],
        "compliance_requirements": ["HIPAA"],
        "agent_systems": [
            {
                "name": "epic_note_drafter_01",
                "agent_type": "llm_agent",
                "actions": ["ehr.note.draft"],
                "data_classes": ["PHI"],
                "external_sinks": ["epic"],
                "description": "Draft note workflow",
            }
        ],
        "support_contact": "support@example.com",
        "support_webhook_url": "https://support.example/webhook",
        "support_diagnostics_enabled": True,
        "production_promotion_requires_approval": True,
        "connector_writeback_requires_approval": True,
        "agent_inventory": [{"agent_id": "epic_note_drafter_01", "risk_tier": "medium"}],
        "notes": "Initial pilot manifest",
    }

    with TestClient(app) as client:
        resp = client.post("/v1/onboarding/manifest", json=manifest)

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["manifest"]["deployment_mode"] == "pilot"
    assert payload["manifest"]["market_pack"] == "healthcare"
    assert payload["manifest"]["policy_pack"] == "hospital"
    assert payload["profile"]["deployment_mode"] == "pilot"
    assert payload["profile"]["market_pack"] == "healthcare"
    assert payload["profile"]["policy_pack"] == "hospital"
    assert payload["profile"]["agent_systems"][0]["name"] == "epic_note_drafter_01"

    loaded = store.list_for_tenant("tenant-1")
    assert loaded
    assert loaded[0]["policy_pack"] == "hospital"
