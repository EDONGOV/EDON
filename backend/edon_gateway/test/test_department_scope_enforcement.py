from __future__ import annotations

import asyncio

import pytest

import backend.edon_gateway.routes.agents as agents_routes
from backend.edon_gateway.department_scope import filter_events_for_department


class _Request:
    def __init__(self, role="operator", department="Cardiology"):
        self.state = type("State", (), {"tenant_info": {
            "tenant_id": "tenant-1",
            "role": role,
            "department": department,
        }})()


class _DB:
    def list_agents(self, tenant_id):
        return [
            {
                "agent_id": "cardiology-note",
                "tenant_id": "tenant-1",
                "name": "Cardiology Note Helper",
                "agent_type": "service",
                "description": "",
                "capabilities": [],
                "policy_pack": "Healthcare v17",
                "mag_enabled": False,
                "status": "active",
                "metadata": {},
                "vendor_id": "Epic",
                "department": "Cardiology",
                "created_at": "2026-05-21T00:00:00+00:00",
                "updated_at": "2026-05-21T00:00:00+00:00",
            },
            {
                "agent_id": "radiology-triage",
                "tenant_id": "tenant-1",
                "name": "Radiology Triage",
                "agent_type": "service",
                "description": "",
                "capabilities": [],
                "policy_pack": "Healthcare v17",
                "mag_enabled": False,
                "status": "active",
                "metadata": {},
                "vendor_id": "Vendor console",
                "department": "Radiology",
                "created_at": "2026-05-21T00:00:00+00:00",
                "updated_at": "2026-05-21T00:00:00+00:00",
            },
        ]

    def get_tenant_agents(self, tenant_id):
        return []

    def get_agent(self, agent_id, tenant_id=None):
        return next((agent for agent in self.list_agents(tenant_id) if agent["agent_id"] == agent_id), None)


@pytest.fixture(autouse=True)
def _patch_agents(monkeypatch):
    monkeypatch.setattr(agents_routes, "get_request_tenant_id", lambda request: "tenant-1")
    monkeypatch.setattr(agents_routes, "get_db", lambda: _DB())
    monkeypatch.setattr(agents_routes, "_get_lifetime_stats", lambda db, tenant_id, agent_id: {
        "total_actions": 0,
        "allow_count": 0,
        "block_count": 0,
        "escalate_count": 0,
        "degrade_count": 0,
        "pause_count": 0,
        "error_count": 0,
        "allow_rate": 0,
        "block_rate": 0,
        "escalate_rate": 0,
        "last_action_at": None,
    })


def test_department_scoped_agent_list_filters_other_departments():
    result = asyncio.run(agents_routes.list_agents(_Request(), status=None, agent_type=None, department=None))

    assert result["total"] == 1
    assert result["agents"][0]["department"] == "Cardiology"


def test_department_scoped_agent_list_rejects_other_department_query():
    with pytest.raises(agents_routes.HTTPException) as exc:
        asyncio.run(agents_routes.list_agents(_Request(), department="Radiology"))

    assert exc.value.status_code == 403


def test_department_scoped_audit_filter_removes_other_departments():
    events = [
        {"agent_id": "a1", "context": {"department": "Cardiology"}},
        {"agent_id": "a2", "context": {"department": "Radiology"}},
    ]

    filtered = filter_events_for_department(events, department="Cardiology")

    assert filtered == [{"agent_id": "a1", "context": {"department": "Cardiology"}}]
