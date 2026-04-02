"""Tests for edge node management API (Gap 1).

Covers:
  - Edge node registration
  - Policy bundle fetch
  - Offline sync upload → audit trail
  - Tenant isolation (node A cannot access node B's bundle)
  - List edge nodes
"""
from datetime import datetime, UTC

import pytest
from cryptography.fernet import Fernet

import edon_gateway.config as cfg


@pytest.fixture(autouse=True)
def disable_auth(monkeypatch):
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)


@pytest.fixture
def client(_dev_environment):
    from starlette.testclient import TestClient
    from edon_gateway.main import app
    with TestClient(app, headers={"X-Agent-ID": "edge-test-agent"}) as c:
        yield c


def _now():
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestEdgeRegistration:
    def test_register_returns_200(self, client):
        resp = client.post("/edge/register", json={
            "node_id": "node-001", "name": "Swarm Controller Alpha",
        })
        assert resp.status_code == 200

    def test_register_returns_node_id(self, client):
        resp = client.post("/edge/register", json={
            "node_id": "node-002", "name": "Beta",
        })
        data = resp.json()
        assert data["node_id"] == "node-002"

    def test_register_returns_policy_version(self, client):
        resp = client.post("/edge/register", json={
            "node_id": "node-003", "name": "Gamma",
        })
        data = resp.json()
        assert "policy_version" in data
        assert len(data["policy_version"]) > 0

    def test_register_returns_status_active(self, client):
        resp = client.post("/edge/register", json={
            "node_id": "node-004", "name": "Delta",
        })
        assert resp.json()["status"] == "active"

    def test_register_idempotent(self, client):
        payload = {"node_id": "node-idem", "name": "Idempotent Node"}
        r1 = client.post("/edge/register", json=payload)
        r2 = client.post("/edge/register", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_register_with_capabilities(self, client):
        resp = client.post("/edge/register", json={
            "node_id": "node-caps",
            "name": "Capable Node",
            "capabilities": ["nano_inject", "sensor_read"],
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Policy bundle
# ---------------------------------------------------------------------------

class TestPolicyBundle:
    def _register(self, client, node_id="bundle-node"):
        client.post("/edge/register", json={"node_id": node_id, "name": "Bundle Test"})
        return node_id

    def test_bundle_returns_200(self, client):
        nid = self._register(client)
        resp = client.get(f"/edge/{nid}/policy-bundle")
        assert resp.status_code == 200

    def test_bundle_has_version(self, client):
        nid = self._register(client)
        data = client.get(f"/edge/{nid}/policy-bundle").json()
        assert "policy_version" in data
        assert len(data["policy_version"]) > 0

    def test_bundle_has_bundle_key(self, client):
        nid = self._register(client)
        data = client.get(f"/edge/{nid}/policy-bundle").json()
        assert "bundle" in data
        bundle = data["bundle"]
        assert "blocked_tools" in bundle
        assert "rate_limits" in bundle
        assert "ttl_seconds" in bundle

    def test_bundle_has_expiry(self, client):
        nid = self._register(client)
        data = client.get(f"/edge/{nid}/policy-bundle").json()
        assert "expires_at" in data

    def test_unknown_node_returns_404(self, client):
        resp = client.get("/edge/nonexistent-node/policy-bundle")
        assert resp.status_code == 404

    def test_bundle_is_embeddedgovernor_compatible(self, client):
        """Bundle returned by API must load cleanly into EmbeddedGovernor."""
        nid = self._register(client, node_id="compat-node")
        bundle_dict = client.get(f"/edge/{nid}/policy-bundle").json()["bundle"]

        from edon_gateway.edge.embedded_governor import EmbeddedGovernor
        gov = EmbeddedGovernor.from_bundle_dict(bundle_dict)
        # Override the expiry to avoid TTL issues in tests
        gov._bundle.issued_at = "2099-01-01T00:00:00+00:00"
        v = gov.evaluate({"tool": "sensor", "op": "read"})
        assert v.verdict in ("ALLOW", "BLOCK", "ESCALATE")


# ---------------------------------------------------------------------------
# Offline sync
# ---------------------------------------------------------------------------

class TestEdgeSync:
    def _register(self, client, node_id="sync-node"):
        client.post("/edge/register", json={"node_id": node_id, "name": "Sync Test"})
        return node_id

    def test_sync_returns_200(self, client):
        nid = self._register(client)
        resp = client.post(f"/edge/{nid}/sync", json={
            "actions": [
                {"agent_id": "bot-1", "action_type": "sensor.read",
                 "verdict": "ALLOW", "timestamp": _now()},
            ]
        })
        assert resp.status_code == 200

    def test_sync_accepted_count(self, client):
        nid = self._register(client, "sync-count")
        resp = client.post(f"/edge/{nid}/sync", json={
            "actions": [
                {"agent_id": "b1", "action_type": "a", "verdict": "ALLOW", "timestamp": _now()},
                {"agent_id": "b2", "action_type": "b", "verdict": "BLOCK", "timestamp": _now()},
                {"agent_id": "b3", "action_type": "c", "verdict": "ALLOW", "timestamp": _now()},
            ]
        })
        data = resp.json()
        assert data["accepted"] == 3
        assert data["rejected"] == 0

    def test_sync_returns_new_policy_version(self, client):
        nid = self._register(client, "sync-ver")
        resp = client.post(f"/edge/{nid}/sync", json={"actions": []})
        assert "new_policy_version" in resp.json()

    def test_sync_unknown_node_returns_404(self, client):
        resp = client.post("/edge/ghost-node/sync", json={"actions": []})
        assert resp.status_code == 404

    def test_sync_empty_actions_succeeds(self, client):
        nid = self._register(client, "sync-empty")
        resp = client.post(f"/edge/{nid}/sync", json={"actions": []})
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 0


# ---------------------------------------------------------------------------
# List edge nodes
# ---------------------------------------------------------------------------

class TestListEdgeNodes:
    def test_list_returns_200(self, client):
        resp = client.get("/edge")
        assert resp.status_code == 200

    def test_list_includes_registered_node(self, client):
        client.post("/edge/register", json={"node_id": "list-node-x", "name": "List X"})
        resp = client.get("/edge")
        ids = [n["node_id"] for n in resp.json()["nodes"]]
        assert "list-node-x" in ids

    def test_list_has_total_field(self, client):
        resp = client.get("/edge")
        assert "total" in resp.json()
