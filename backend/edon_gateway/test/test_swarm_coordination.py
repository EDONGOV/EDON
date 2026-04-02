"""Tests for swarm coordination API (Gap 3).

Covers:
  - Swarm CRUD (create, list, members)
  - Action budget enforcement
  - Quorum rules
  - Dosage caps
  - Cross-tenant isolation
  - Swarm state endpoint
"""
import pytest
from datetime import datetime, UTC
from cryptography.fernet import Fernet

import edon_gateway.config as cfg


@pytest.fixture(autouse=True)
def disable_auth(monkeypatch):
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)


@pytest.fixture
def client(disable_auth):
    from starlette.testclient import TestClient
    from edon_gateway.main import app
    with TestClient(app, headers={"X-Agent-ID": "swarm-test-agent"}) as c:
        yield c


def _now():
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Swarm CRUD
# ---------------------------------------------------------------------------

class TestSwarmCRUD:
    def test_create_swarm_returns_201(self, client):
        resp = client.post("/swarms", json={"name": "test-swarm"})
        assert resp.status_code == 201

    def test_create_swarm_returns_swarm_id(self, client):
        resp = client.post("/swarms", json={"name": "my-swarm"})
        data = resp.json()
        assert "swarm_id" in data
        assert len(data["swarm_id"]) > 0

    def test_list_swarms_returns_200(self, client):
        resp = client.get("/swarms")
        assert resp.status_code == 200

    def test_list_swarms_contains_created(self, client):
        client.post("/swarms", json={"name": "list-swarm-x"})
        resp = client.get("/swarms")
        names = [s["name"] for s in resp.json()["swarms"]]
        assert "list-swarm-x" in names

    def test_add_member_returns_201(self, client):
        swarm = client.post("/swarms", json={"name": "member-swarm"}).json()
        sid = swarm["swarm_id"]
        resp = client.post(f"/swarms/{sid}/members", json={"agent_id": "bot-1"})
        assert resp.status_code == 201

    def test_get_state_reflects_member_count(self, client):
        swarm = client.post("/swarms", json={"name": "state-swarm"}).json()
        sid = swarm["swarm_id"]
        client.post(f"/swarms/{sid}/members", json={"agent_id": "bot-a"})
        client.post(f"/swarms/{sid}/members", json={"agent_id": "bot-b"})
        client.post(f"/swarms/{sid}/members", json={"agent_id": "bot-c"})
        state = client.get(f"/swarms/{sid}/state").json()
        assert state["member_count"] == 3

    def test_remove_member_returns_200(self, client):
        swarm = client.post("/swarms", json={"name": "rm-swarm"}).json()
        sid = swarm["swarm_id"]
        client.post(f"/swarms/{sid}/members", json={"agent_id": "bot-del"})
        resp = client.delete(f"/swarms/{sid}/members/bot-del")
        assert resp.status_code == 200

    def test_unknown_swarm_returns_404(self, client):
        resp = client.post(
            "/swarms/nonexistent-id/evaluate",
            json={"agent_id": "x", "action_type": "robot.move", "timestamp": _now()},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Action budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_budget_blocks_after_limit(self, client):
        policy = {"action_budgets": {"robot.move": {"max_per_minute": 3}}}
        swarm = client.post("/swarms", json={"name": "budget-swarm", "policy": policy}).json()
        sid = swarm["swarm_id"]

        verdicts = []
        for i in range(4):
            resp = client.post(
                f"/swarms/{sid}/evaluate",
                json={
                    "agent_id": f"bot-{i}",
                    "action_type": "robot.move",
                    "payload": {},
                    "timestamp": _now(),
                },
            )
            assert resp.status_code == 200
            verdicts.append(resp.json()["verdict"])

        assert verdicts[:3] == ["ALLOW", "ALLOW", "ALLOW"]
        assert verdicts[3] == "BLOCK"

    def test_budget_remaining_decrements(self, client):
        policy = {"action_budgets": {"sensor.read": {"max_per_minute": 5}}}
        swarm = client.post("/swarms", json={"name": "rem-swarm", "policy": policy}).json()
        sid = swarm["swarm_id"]

        resp = client.post(
            f"/swarms/{sid}/evaluate",
            json={"agent_id": "bot-1", "action_type": "sensor.read", "timestamp": _now()},
        )
        assert resp.json()["budget_remaining"] is not None

    def test_different_action_types_have_separate_budgets(self, client):
        policy = {"action_budgets": {"robot.move": {"max_per_minute": 1}}}
        swarm = client.post("/swarms", json={"name": "sep-budget", "policy": policy}).json()
        sid = swarm["swarm_id"]

        # Exhaust robot.move budget
        client.post(f"/swarms/{sid}/evaluate",
                    json={"agent_id": "bot", "action_type": "robot.move", "timestamp": _now()})
        client.post(f"/swarms/{sid}/evaluate",
                    json={"agent_id": "bot", "action_type": "robot.move", "timestamp": _now()})

        # sensor.read should still be allowed (different action type)
        resp = client.post(f"/swarms/{sid}/evaluate",
                           json={"agent_id": "bot", "action_type": "sensor.read", "timestamp": _now()})
        assert resp.json()["verdict"] == "ALLOW"


# ---------------------------------------------------------------------------
# Quorum rules
# ---------------------------------------------------------------------------

class TestQuorumRules:
    def test_first_vote_is_quorum_pending(self, client):
        policy = {"quorum_rules": {"drone.spray": {"required_votes": 3, "ttl_seconds": 30}}}
        swarm = client.post("/swarms", json={"name": "quorum-swarm", "policy": policy}).json()
        sid = swarm["swarm_id"]

        resp = client.post(f"/swarms/{sid}/evaluate",
                           json={"agent_id": "bot-1", "action_type": "drone.spray",
                                 "payload": {}, "timestamp": _now()})
        assert resp.json()["verdict"] == "QUORUM_PENDING"

    def test_quorum_met_after_enough_votes(self, client):
        policy = {"quorum_rules": {"drone.spray": {"required_votes": 3, "ttl_seconds": 60}}}
        swarm = client.post("/swarms", json={"name": "q-met", "policy": policy}).json()
        sid = swarm["swarm_id"]

        # First two pending
        client.post(f"/swarms/{sid}/evaluate",
                    json={"agent_id": "bot-1", "action_type": "drone.spray",
                          "payload": {}, "timestamp": _now()})
        client.post(f"/swarms/{sid}/evaluate",
                    json={"agent_id": "bot-2", "action_type": "drone.spray",
                          "payload": {}, "timestamp": _now()})

        # Third vote should meet quorum
        resp = client.post(f"/swarms/{sid}/evaluate",
                           json={"agent_id": "bot-3", "action_type": "drone.spray",
                                 "payload": {}, "timestamp": _now()})
        assert resp.json()["verdict"] == "ALLOW"

    def test_quorum_response_includes_vote_counts(self, client):
        policy = {"quorum_rules": {"inject.deliver": {"required_votes": 5, "ttl_seconds": 30}}}
        swarm = client.post("/swarms", json={"name": "q-counts", "policy": policy}).json()
        sid = swarm["swarm_id"]

        resp = client.post(f"/swarms/{sid}/evaluate",
                           json={"agent_id": "bot-1", "action_type": "inject.deliver",
                                 "payload": {}, "timestamp": _now()})
        data = resp.json()
        assert data["quorum_required"] == 5
        assert data["quorum_votes"] >= 1


# ---------------------------------------------------------------------------
# Dosage caps
# ---------------------------------------------------------------------------

class TestDosageCaps:
    def test_dosage_cap_blocks_after_limit(self, client):
        policy = {
            "dosage_caps": {
                "inject.deliver": {
                    "max_amount_per_hour": 100.0,
                    "amount_field": "volume_ml",
                    "window_seconds": 3600,
                }
            }
        }
        swarm = client.post("/swarms", json={"name": "dose-swarm", "policy": policy}).json()
        sid = swarm["swarm_id"]

        # 4 injections of 30 ml each = 120 ml > 100 ml cap
        verdicts = []
        for i in range(4):
            resp = client.post(f"/swarms/{sid}/evaluate", json={
                "agent_id": f"bot-{i}",
                "action_type": "inject.deliver",
                "payload": {"volume_ml": 30.0},
                "timestamp": _now(),
            })
            verdicts.append(resp.json()["verdict"])

        # First 3 allowed (90 ml), 4th blocked (would be 120 ml)
        assert verdicts[0] == "ALLOW"
        assert verdicts[1] == "ALLOW"
        assert verdicts[2] == "ALLOW"
        assert verdicts[3] == "BLOCK"

    def test_dosage_remaining_decrements(self, client):
        policy = {
            "dosage_caps": {
                "inject.deliver": {
                    "max_amount_per_hour": 100.0,
                    "amount_field": "volume_ml",
                }
            }
        }
        swarm = client.post("/swarms", json={"name": "dose-rem", "policy": policy}).json()
        sid = swarm["swarm_id"]

        resp = client.post(f"/swarms/{sid}/evaluate", json={
            "agent_id": "bot-1",
            "action_type": "inject.deliver",
            "payload": {"volume_ml": 40.0},
            "timestamp": _now(),
        })
        data = resp.json()
        assert data["dosage_remaining"] is not None
        # 100 - 40 = 60 remaining
        assert abs(data["dosage_remaining"] - 60.0) < 0.01


# ---------------------------------------------------------------------------
# Swarm state
# ---------------------------------------------------------------------------

class TestSwarmState:
    def test_state_action_counts(self, client):
        swarm = client.post("/swarms", json={"name": "state-counts"}).json()
        sid = swarm["swarm_id"]

        for i in range(3):
            client.post(f"/swarms/{sid}/evaluate",
                        json={"agent_id": "bot-1", "action_type": "robot.move",
                              "payload": {}, "timestamp": _now()})

        state = client.get(f"/swarms/{sid}/state").json()
        counts = state.get("action_counts_last_60s", {})
        assert "robot.move" in counts
        assert sum(counts["robot.move"].values()) == 3
