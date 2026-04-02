"""Unit tests for deterministic credential selection (no cross-tenant fallback)."""

import tempfile
from pathlib import Path

import pytest

from edon_gateway.persistence.database import Database


def test_get_credential_strict_tenant_match():
    """When multiple rows exist for same credential_id (different tenant_id),
    get_credential(tenant_id=X) returns only the row with tenant_id=X.
    get_credential(tenant_id=None) returns only the row with tenant_id IS NULL.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        db = Database(db_path)
        cred_data = {"base_url": "http://example.com", "secret": "s1", "auth_mode": "password"}
        # Same credential_id, two tenants
        db.save_credential(
            credential_id="clawdbot_gateway",
            tool_name="clawdbot",
            credential_type="gateway",
            credential_data={**cred_data, "secret": "global_secret"},
            tenant_id=None,
        )
        db.save_credential(
            credential_id="clawdbot_gateway",
            tool_name="clawdbot",
            credential_type="gateway",
            credential_data={**cred_data, "secret": "tenant_secret"},
            tenant_id="tenant_dev",
        )
        # tenant_id=None must return only global row
        out_none = db.get_credential("clawdbot_gateway", tool_name="clawdbot", tenant_id=None)
        assert out_none is not None
        assert out_none.get("credential_data", {}).get("secret") == "global_secret"
        assert out_none.get("tenant_id") is None
        # tenant_id="tenant_dev" must return only tenant row
        out_dev = db.get_credential("clawdbot_gateway", tool_name="clawdbot", tenant_id="tenant_dev")
        assert out_dev is not None
        assert out_dev.get("credential_data", {}).get("secret") == "tenant_secret"
        assert out_dev.get("tenant_id") == "tenant_dev"
        # Unrelated tenant gets nothing
        out_other = db.get_credential("clawdbot_gateway", tool_name="clawdbot", tenant_id="other")
        assert out_other is None
    finally:
        db_path.unlink(missing_ok=True)


def test_get_credential_order_by_rowid_desc():
    """When multiple rows exist (same credential_id, same tenant_id) we use ORDER BY rowid DESC LIMIT 1.
    SQLite PK (credential_id, tenant_id) allows only one row per pair; this test documents
    that we select by rowid for consistency if schema ever allows multiple.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        db = Database(db_path)
        db.save_credential(
            credential_id="single",
            tool_name="clawdbot",
            credential_type="gateway",
            credential_data={"base_url": "http://a.com", "secret": "only"},
            tenant_id=None,
        )
        out = db.get_credential("single", tool_name="clawdbot", tenant_id=None)
        assert out is not None
        assert out["credential_data"]["secret"] == "only"
    finally:
        db_path.unlink(missing_ok=True)
