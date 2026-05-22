"""Regression tests for strict API key role creation."""

from __future__ import annotations

import asyncio

import pytest

import backend.edon_gateway.config as cfg
import backend.edon_gateway.routes.api_keys as api_keys


class _DummyRequest:
    def __init__(self, role: str, **tenant_info):
        info = {"tenant_id": "tenant-1", "role": role}
        info.update(tenant_info)
        self.state = type("State", (), {"tenant_info": info})()


class _FakeDB:
    def __init__(self):
        self.created: list[dict] = []

    def create_api_key(
        self,
        tenant_id: str,
        key_hash: str,
        name=None,
        role: str = "viewer",
        department=None,
        scope_group=None,
        purpose=None,
        scope=None,
        environment=None,
        expires_at=None,
    ):
        key_id = f"key-{len(self.created) + 1}"
        self.created.append({
            "id": key_id,
            "tenant_id": tenant_id,
            "key_hash": key_hash,
            "name": name,
            "role": role,
            "department": department,
            "scope": scope,
            "expires_at": expires_at,
        })
        return key_id


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch):
    monkeypatch.setattr(api_keys, "get_request_tenant_id", lambda request: request.state.tenant_info["tenant_id"])
    monkeypatch.setattr(api_keys, "hash_api_key_fast", lambda plaintext: f"hash:{plaintext}")


def _set_enterprise(monkeypatch, value: bool):
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_MODE", value)


def test_viewer_can_only_create_viewer_keys(monkeypatch):
    db = _FakeDB()
    _set_enterprise(monkeypatch, False)
    monkeypatch.setattr(api_keys, "get_db", lambda: db)

    result = asyncio.run(api_keys.create_api_key(_DummyRequest("viewer"), api_keys.CreateKeyRequest(name="solo")))

    assert result["role"] == "viewer"
    assert db.created[0]["role"] == "viewer"


def test_non_admin_cannot_create_elevated_keys(monkeypatch):
    db = _FakeDB()
    _set_enterprise(monkeypatch, False)
    monkeypatch.setattr(api_keys, "get_db", lambda: db)

    with pytest.raises(api_keys.HTTPException) as exc:
        asyncio.run(api_keys.create_api_key(_DummyRequest("viewer"), api_keys.CreateKeyRequest(name="elevated", role="operator")))

    assert exc.value.status_code == 403


def test_admin_can_create_elevated_keys(monkeypatch):
    db = _FakeDB()
    _set_enterprise(monkeypatch, False)
    monkeypatch.setattr(api_keys, "get_db", lambda: db)

    result = asyncio.run(api_keys.create_api_key(
        _DummyRequest("governance_admin"),
        api_keys.CreateKeyRequest(name="ops", role="operator", department="Cardiology", scope="cardiology.note.draft"),
    ))

    assert result["role"] == "operator"
    assert db.created[0]["role"] == "operator"
    assert db.created[0]["expires_at"]


def test_enterprise_viewer_cannot_create_any_key(monkeypatch):
    db = _FakeDB()
    _set_enterprise(monkeypatch, True)
    monkeypatch.setattr(api_keys, "get_db", lambda: db)

    with pytest.raises(api_keys.HTTPException) as exc:
        asyncio.run(api_keys.create_api_key(_DummyRequest("viewer"), api_keys.CreateKeyRequest(name="solo")))

    assert exc.value.status_code == 403


def test_enterprise_admin_can_create_viewer_key(monkeypatch):
    db = _FakeDB()
    _set_enterprise(monkeypatch, True)
    monkeypatch.setattr(api_keys, "get_db", lambda: db)

    result = asyncio.run(api_keys.create_api_key(_DummyRequest("governance_admin"), api_keys.CreateKeyRequest(name="invitee")))

    assert result["role"] == "viewer"
    assert db.created[0]["role"] == "viewer"


def test_runtime_credential_exchanges_short_lived_session(monkeypatch):
    monkeypatch.setattr(api_keys, "get_key_id", lambda: "kid-test")
    monkeypatch.setattr(api_keys, "sign_canonical_payload", lambda payload: "sig-test")

    result = asyncio.run(api_keys.exchange_runtime_session(
        _DummyRequest(
            "operator",
            api_key_id="key-runtime",
            department="Cardiology",
            scope_group="clinical",
            purpose="Note drafting",
            scope="cardiology.note.draft",
            environment="Sandbox",
        ),
        api_keys.RuntimeSessionRequest(ttl_minutes=10),
    ))

    assert result["token_type"] == "edon.runtime_session"
    assert result["ttl_minutes"] == 10
    assert result["payload"]["department"] == "Cardiology"
    assert result["payload"]["scope"] == "cardiology.note.draft"
    assert result["token"].endswith(".sig-test")


def test_viewer_cannot_exchange_runtime_session():
    with pytest.raises(api_keys.HTTPException) as exc:
        asyncio.run(api_keys.exchange_runtime_session(
            _DummyRequest("viewer", api_key_id="key-viewer"),
            api_keys.RuntimeSessionRequest(),
        ))

    assert exc.value.status_code == 403
