from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_healthcare_market_pack_registry_and_aliases():
    from backend.edon_gateway.market_packs import get_market_pack, list_market_packs

    packs = list_market_packs()
    assert len(packs) == 1
    pack = packs[0]
    assert pack["slug"] == "healthcare"
    assert pack["status_tier"] == "supported"
    assert pack["certification_status"] == "certified"
    assert pack["tenant_pinned"] is True
    assert "HIPAA" in pack["default_compliance_requirements"]
    assert "PHI" in pack["default_data_classes"]
    assert "record_writeback" in {action["action"] for action in pack["governed_actions"]}

    alias = get_market_pack("hospital")
    assert alias["slug"] == "healthcare"
    assert alias["version"] == pack["version"]
    assert alias["enterprise_supported"] is True


def test_onboarding_profile_pins_healthcare_market_pack_defaults():
    from backend.edon_gateway.onboarding.profile import OnboardingStore

    store = OnboardingStore(":memory:")
    profile = store.create(
        tenant_id="tenant-1",
        org_name="Acme Health",
        agent_systems=[],
        identity_provider="entra",
        environments=["saas"],
        compliance_requirements=[],
        deployment_mode="pilot",
        market_pack="healthcare",
    )

    loaded = store.get(profile.profile_id)
    assert profile.market_pack == "healthcare"
    assert profile.market_pack_version == "2026.05"
    assert "HIPAA" in profile.compliance_requirements
    assert "PHI" in profile.all_data_classes
    assert loaded is not None
    assert loaded.market_pack == "healthcare"
    assert loaded.market_pack_version == "2026.05"
    assert "HIPAA" in loaded.compliance_requirements


def test_market_pack_routes_show_healthcare_pack(_dev_environment):
    from edon_gateway.main import app

    with TestClient(app, headers={"X-Agent-ID": "market-pack-test"}) as client:
        resp = client.get("/v1/governance/market-packs")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["tenant_pinning"] is True
    assert payload["versioned"] is True
    assert payload["count"] == 1
    assert payload["packs"][0]["slug"] == "healthcare"
    assert payload["packs"][0]["enterprise_supported"] is True

