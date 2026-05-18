import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _dummy_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_onboarding_store_rejects_placeholder_tenants():
    from edon_gateway.onboarding.profile import OnboardingStore

    store = OnboardingStore(":memory:")

    with pytest.raises(ValueError):
        store.create(
            tenant_id="default",
            org_name="Acme",
            agent_systems=[],
            identity_provider="none",
            environments=["saas"],
            compliance_requirements=[],
        )

    with pytest.raises(ValueError):
        store.list_for_tenant("unknown")


def test_signoff_store_rejects_placeholder_tenants():
    from edon_gateway.onboarding.signoff import SignoffStore

    store = SignoffStore(":memory:")

    with pytest.raises(ValueError):
        store.create(
            profile_id="gdp-1",
            tenant_id="default",
            requested_by="approver",
            enforcement_scope=["agent-a"],
            escalation_rules_accepted=True,
            kill_switch_authority="admin",
            data_classes_governed=[],
        )

    with pytest.raises(ValueError):
        store.latest_approved("unknown")


def test_onboarding_store_requires_explicit_db_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EDON_ONBOARDING_DB", raising=False)

    from edon_gateway.onboarding.profile import OnboardingStore

    with pytest.raises(RuntimeError):
        OnboardingStore()


def test_signoff_store_requires_explicit_db_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EDON_ONBOARDING_DB", raising=False)

    from edon_gateway.onboarding.signoff import SignoffStore

    with pytest.raises(RuntimeError):
        SignoffStore()


def test_onboarding_profile_ownership_checks_require_the_right_tenant():
    from edon_gateway.onboarding.profile import OnboardingStore
    from edon_gateway.routes.onboarding import _assert_owns_profile

    store = OnboardingStore(":memory:")
    profile = store.create(
        tenant_id="tenant-a",
        org_name="Acme",
        agent_systems=[],
        identity_provider="none",
        environments=["saas"],
        compliance_requirements=[],
    )

    with pytest.raises(HTTPException) as exc:
        _assert_owns_profile(profile, None)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        _assert_owns_profile(profile, "tenant-b")
    assert exc.value.status_code == 404

    _assert_owns_profile(profile, "tenant-a")


def test_onboarding_routes_fail_closed_without_tenant(monkeypatch):
    from edon_gateway.routes import onboarding as onboarding_routes

    monkeypatch.setattr(onboarding_routes, "get_request_tenant_id", lambda request: None)

    body = onboarding_routes.IntakeRequest(
        org_name="Acme",
        agent_systems=[],
        identity_provider="none",
        environments=["saas"],
        compliance_requirements=[],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(onboarding_routes.submit_intake(_dummy_request(), body))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(onboarding_routes.list_profiles(_dummy_request()))
    assert exc.value.status_code == 400


def test_physical_routes_fail_closed_without_tenant(monkeypatch):
    from edon_gateway.routes import physical as physical_routes

    monkeypatch.setattr(physical_routes, "get_request_tenant_id", lambda request: None)

    heartbeat_body = physical_routes.HeartbeatBody(
        tenant_id=None,
        comm_loss_posture="freeze",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.heartbeat("robot-1", heartbeat_body, _dummy_request()))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.list_heartbeats(_dummy_request()))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.release_zone("zone-a", "robot-1", _dummy_request()))
    assert exc.value.status_code == 400

    telemetry_body = physical_routes.TelemetryBody(action_id="action-1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.ingest_robot_telemetry("robot-1", telemetry_body, _dummy_request()))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.complete_execution("robot-1", "action-1", _dummy_request()))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.get_execution_state("robot-1", "action-1", _dummy_request()))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        asyncio.run(physical_routes.list_executions("robot-1", _dummy_request()))
    assert exc.value.status_code == 400


def test_physical_heartbeat_accepts_explicit_tenant_bootstrap(monkeypatch):
    from edon_gateway.routes import physical as physical_routes

    monkeypatch.setattr(physical_routes, "get_request_tenant_id", lambda request: None)

    captured = {}

    class _Heartbeat:
        ttl_s = 10.0
        comm_loss_posture = "freeze"
        tenant_id = "tenant-explicit"

    def _register(robot_id, tenant_id, ttl_s, comm_loss_posture):
        captured["robot_id"] = robot_id
        captured["tenant_id"] = tenant_id
        captured["ttl_s"] = ttl_s
        captured["comm_loss_posture"] = comm_loss_posture
        return SimpleNamespace(ttl_s=ttl_s, comm_loss_posture=comm_loss_posture)

    monkeypatch.setattr(physical_routes, "register", _register)
    monkeypatch.setattr(physical_routes, "record_heartbeat", lambda robot_id: None)

    result = asyncio.run(physical_routes.heartbeat("robot-explicit", _Heartbeat(), _dummy_request()))

    assert result["status"] == "registered"
    assert captured["tenant_id"] == "tenant-explicit"
