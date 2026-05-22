from __future__ import annotations

import asyncio

import pytest

import backend.edon_gateway.routes.access as access


class _State:
    tenant_info = {
        "tenant_id": "tenant-1",
        "role": "governance_admin",
        "key_name": "Governance Admin",
        "api_key_id": "key-admin",
    }


class _Request:
    state = _State()
    base_url = "http://testserver/"


class _FakeDB:
    def __init__(self):
        self.invites: dict[str, dict] = {}
        self.audit_events: list[dict] = []

    def create_console_user_invite(self, **kwargs):
        invite_id = f"inv-{len(self.invites) + 1}"
        invite = {
            "invite_id": invite_id,
            "tenant_id": kwargs["tenant_id"],
            "email": kwargs["email"],
            "role": kwargs["role"],
            "department": kwargs["department"],
            "scope": kwargs["scope"],
            "status": "pending",
            "invited_by": kwargs["invited_by"],
            "invite_url": kwargs["invite_url"],
            "expires_at": kwargs["expires_at"],
            "accepted_at": None,
            "revoked_at": None,
            "created_at": "2026-05-21T00:00:00+00:00",
            "updated_at": "2026-05-21T00:00:00+00:00",
        }
        self.invites[invite_id] = invite
        return invite

    def list_console_user_invites(self, tenant_id):
        return [invite for invite in self.invites.values() if invite["tenant_id"] == tenant_id]

    def revoke_console_user_invite(self, *, invite_id, tenant_id):
        invite = self.invites.get(invite_id)
        if not invite or invite["tenant_id"] != tenant_id:
            return None
        invite["status"] = "revoked"
        invite["revoked_at"] = "2026-05-21T00:01:00+00:00"
        return invite

    def save_audit_event(self, *args, **kwargs):
        self.audit_events.append({"args": args, "kwargs": kwargs})
        return f"audit-{len(self.audit_events)}"

    def list_console_department_owners(self, tenant_id):
        return [
            {
                "id": "dept-owner-1",
                "tenant_id": tenant_id,
                "department": "Cardiology",
                "owner_email": "cardiology.owner@stmercy.org",
                "updated_by": "Governance Admin",
                "created_at": "2026-05-21T00:00:00+00:00",
                "updated_at": "2026-05-21T00:00:00+00:00",
            }
        ]

    def upsert_console_department_owner(self, *, tenant_id, department, owner_email, updated_by):
        return {
            "id": "dept-owner-1",
            "tenant_id": tenant_id,
            "department": department,
            "owner_email": owner_email,
            "updated_by": updated_by,
            "created_at": "2026-05-21T00:00:00+00:00",
            "updated_at": "2026-05-21T00:00:00+00:00",
        }


@pytest.fixture()
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(access, "get_db", lambda: db)
    monkeypatch.setattr(access, "get_request_tenant_id", lambda request: request.state.tenant_info["tenant_id"])
    return db


def test_admin_can_create_and_list_console_user_invite(fake_db):
    result = asyncio.run(access.create_user_invite(
        _Request(),
        access.CreateUserInviteRequest(
            email="cardiology.ops@stmercy.org",
            role="operator",
            department="Cardiology",
        ),
    ))

    assert result["invite"]["email"] == "cardiology.ops@stmercy.org"
    assert result["invite"]["scope"] == "Cardiology only"
    assert result["invite"]["status"] == "pending"
    assert result["invite"]["invite_url"].startswith("http://testserver/console/invite?token=")

    listed = asyncio.run(access.list_user_invites(_Request()))
    assert listed["count"] == 1
    assert listed["invites"][0]["role"] == "operator"
    assert result["delivery"]["status"] == "ready"
    assert result["delivery"]["channel"] == "identity_provider_or_email"


def test_department_scoped_role_requires_department(fake_db):
    with pytest.raises(access.HTTPException) as exc:
        asyncio.run(access.create_user_invite(
            _Request(),
            access.CreateUserInviteRequest(email="ops@stmercy.org", role="operator"),
        ))

    assert exc.value.status_code == 400


def test_admin_can_revoke_pending_console_user_invite(fake_db):
    result = asyncio.run(access.create_user_invite(
        _Request(),
        access.CreateUserInviteRequest(
            email="cardiology.ops@stmercy.org",
            role="operator",
            department="Cardiology",
        ),
    ))

    revoked = asyncio.run(access.revoke_user_invite(result["invite"]["invite_id"], _Request()))

    assert revoked["status"] == "revoked"
    assert revoked["invite"]["status"] == "revoked"


def test_admin_can_manage_department_owner(fake_db):
    saved = asyncio.run(access.set_department_owner(
        "Cardiology",
        _Request(),
        access.DepartmentOwnerRequest(owner_email="cardiology.owner@stmercy.org"),
    ))

    assert saved["status"] == "saved"
    assert saved["owner"]["department"] == "Cardiology"
    assert saved["owner"]["owner_email"] == "cardiology.owner@stmercy.org"

    listed = asyncio.run(access.list_department_owners(_Request()))
    assert listed["count"] == 1
    assert listed["owners"][0]["department"] == "Cardiology"
