from __future__ import annotations

from backend.edon_gateway.onboarding.profile import OnboardingStore


def test_onboarding_profile_persists_deployment_mode():
    store = OnboardingStore(":memory:")
    profile = store.create(
        tenant_id="tenant-1",
        org_name="Acme",
        agent_systems=[],
        identity_provider="none",
        environments=["saas"],
        compliance_requirements=[],
        deployment_mode="production",
    )

    loaded = store.get(profile.profile_id)

    assert profile.deployment_mode == "production"
    assert loaded is not None
    assert loaded.deployment_mode == "production"
    assert loaded.as_dict()["deployment_mode"] == "production"
