"""Regression tests for stricter self-serve privilege defaults."""

from __future__ import annotations

import asyncio

import backend.edon_gateway.config as cfg
import backend.edon_gateway.middleware.auth as auth_module
import backend.edon_gateway.persistence as persistence_pkg
import backend.edon_gateway.routes.auth as auth_routes


class _DummyClient:
    host = "127.0.0.1"


class _DummyRequest:
    client = _DummyClient()


class _FakeDB:
    def __init__(self):
        self.users: dict[tuple[str, str], dict] = {}
        self.users_by_id: dict[str, dict] = {}
        self.tenants: dict[str, dict] = {}
        self.api_keys: list[dict] = []

    def get_user_by_auth(self, provider: str, subject: str):
        row = self.users.get((provider, subject))
        if row is not None:
            return row
        if provider == "email":
            return next((user for user in self.users_by_id.values() if user.get("email") == subject), None)
        return None

    def create_user(self, user_id: str, email: str, auth_provider: str, auth_subject: str, role: str = "user") -> str:
        row = {
            "id": user_id,
            "email": email,
            "auth_provider": auth_provider,
            "auth_subject": auth_subject,
            "role": role,
        }
        self.users[(auth_provider, auth_subject)] = row
        self.users_by_id[user_id] = row
        return user_id

    def update_user_email(self, user_id: str, email: str):
        if user_id in self.users_by_id:
            self.users_by_id[user_id]["email"] = email

    def create_tenant(self, tenant_id: str, user_id: str, stripe_customer_id=None) -> str:
        row = {
            "id": tenant_id,
            "user_id": user_id,
            "status": "active",
            "plan": "free",
        }
        self.tenants[tenant_id] = row
        return tenant_id

    def get_tenant_by_user(self, user_id: str):
        return next((tenant for tenant in self.tenants.values() if tenant["user_id"] == user_id), None)

    def get_tenant_by_user_id(self, user_id: str):
        return self.get_tenant_by_user(user_id)

    def get_tenant(self, tenant_id: str):
        return self.tenants.get(tenant_id)

    def list_tenants(self):
        return list(self.tenants.values())

    def list_api_keys(self, tenant_id: str):
        return [key for key in self.api_keys if key["tenant_id"] == tenant_id]

    def create_api_key(self, tenant_id: str, key_hash: str, name=None, role: str = "viewer", is_sandbox: bool = False):
        key_id = f"key-{len(self.api_keys) + 1}"
        row = {
            "id": key_id,
            "tenant_id": tenant_id,
            "key_hash": key_hash,
            "name": name,
            "role": role,
            "status": "active",
            "is_sandbox": is_sandbox,
        }
        self.api_keys.append(row)
        return key_id


def _configure_self_serve(monkeypatch, db: _FakeDB):
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_MODE", False)
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_SSO_ONLY", False)
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(auth_routes, "get_db", lambda: db)
    monkeypatch.setattr(persistence_pkg, "get_db", lambda: db)
    monkeypatch.setattr(auth_routes, "check_rate_limit", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(auth_routes, "increment_rate_limit", lambda *args, **kwargs: None)


def test_self_serve_register_defaults_to_viewer_role(monkeypatch):
    db = _FakeDB()
    _configure_self_serve(monkeypatch, db)

    result = asyncio.run(
        auth_routes.register(
            _DummyRequest(),
            auth_routes.RegisterRequest(email="solo@example.com", password="TestPass123!"),
        )
    )

    assert result["tenant_id"]
    assert db.users_by_id[result["user"]["id"]]["role"] == "viewer"
    assert db.api_keys[0]["role"] == "viewer"


def test_self_serve_login_provisions_viewer_key(monkeypatch):
    db = _FakeDB()
    _configure_self_serve(monkeypatch, db)
    monkeypatch.setattr(auth_routes, "_verify_password", lambda _password, _hashed: True)

    user_id = "user-1"
    tenant_id = "tenant-1"
    db.create_user(
        user_id=user_id,
        email="solo@example.com",
        auth_provider="email",
        auth_subject="solo@example.com",
        role="viewer",
    )
    db.create_tenant(tenant_id=tenant_id, user_id=user_id)

    result = asyncio.run(
        auth_routes.login(
            _DummyRequest(),
            auth_routes.RegisterRequest(email="solo@example.com", password="TestPass123!"),
        )
    )

    assert result["tenant_id"] == tenant_id
    assert result["api_key"]
    assert db.api_keys[0]["role"] == "viewer"


def test_clerk_resolution_defaults_to_viewer_role(monkeypatch):
    db = _FakeDB()
    _configure_self_serve(monkeypatch, db)

    claims = {"sub": "clerk-subject-1", "email": "admin@example.com"}
    tenant_info = auth_module.resolve_tenant_for_clerk(claims)

    assert tenant_info["tenant_id"]
    assert db.users[("clerk", "clerk-subject-1")]["role"] == "viewer"
    assert len(db.tenants) == 1
