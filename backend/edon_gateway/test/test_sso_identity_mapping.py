from __future__ import annotations

import backend.edon_gateway.middleware.auth as auth
import backend.edon_gateway.persistence as persistence


class _DB:
    def __init__(self):
        self.users = {}
        self.tenant = None

    def get_user_by_auth(self, provider, subject):
        return self.users.get((provider, subject))

    def create_user(self, user_id, email, auth_provider, auth_subject, role="viewer"):
        self.users[(auth_provider, auth_subject)] = {
            "id": user_id,
            "email": email,
            "role": role,
        }

    def update_user_email(self, user_id, email):
        pass

    def get_tenant_by_user_id(self, user_id):
        return self.tenant

    def create_tenant(self, tenant_id, user_id):
        self.tenant = {
            "id": tenant_id,
            "user_id": user_id,
            "status": "trial",
            "plan": "enterprise",
        }

    def get_tenant(self, tenant_id):
        return self.tenant


def test_sso_claims_map_to_edon_role_department_and_session_policy(monkeypatch):
    db = _DB()
    monkeypatch.setattr(persistence, "get_db", lambda: db)

    tenant_info = auth.resolve_tenant_for_clerk({
        "sub": "clerk-user-1",
        "email": "cardiology.admin@stmercy.org",
        "edon_role": "operator",
        "edon_department": "Cardiology",
    })

    assert tenant_info["role"] == "operator"
    assert tenant_info["department"] == "Cardiology"
    assert tenant_info["session_policy"] == "department_scoped"


def test_sso_non_admin_without_department_falls_back_to_viewer(monkeypatch):
    db = _DB()
    monkeypatch.setattr(persistence, "get_db", lambda: db)

    tenant_info = auth.resolve_tenant_for_clerk({
        "sub": "clerk-user-2",
        "email": "unknown@stmercy.org",
        "edon_role": "operator",
    })

    assert tenant_info["role"] == "viewer"
    assert tenant_info["department"] is None
