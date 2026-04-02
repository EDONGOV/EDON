"""EDON Python SDK — lightweight client for the EDON Governance Gateway."""
from __future__ import annotations
import httpx
from typing import Any


class EdonClient:
    """Client for the EDON Governance Gateway.

    Usage:
        client = EdonClient(token="your-token", base_url="https://edon-gateway.fly.dev")
        result = client.evaluate(action_type="send_email", agent_id="agent-1", payload={...})
    """

    def __init__(self, token: str, base_url: str = "https://edon-gateway.fly.dev"):
        self.base_url = base_url.rstrip("/")
        self._headers = {"X-EDON-TOKEN": token, "Content-Type": "application/json"}

    def evaluate(self, action_type: str, agent_id: str, payload: dict[str, Any] = {}, intent_id: str | None = None) -> dict:
        """Evaluate an agent action. Returns verdict + reason_code + explanation."""
        body: dict[str, Any] = {"action_type": action_type, "agent_id": agent_id, "payload": payload}
        if intent_id:
            body["intent_id"] = intent_id
        return self._post("/v1/action", body)

    def health(self) -> dict:
        return self._get("/health")

    def stats(self) -> dict:
        return self._get("/stats")

    def list_agents(self) -> list[dict]:
        return self._get("/agents")

    def get_agent(self, agent_id: str) -> dict:
        return self._get(f"/agents/{agent_id}")

    def list_decisions(self, agent_id: str | None = None, verdict: str | None = None, limit: int = 50) -> list[dict]:
        params = {"limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        if verdict:
            params["verdict"] = verdict
        return self._get("/audit/query", params=params)

    def apply_policy(self, pack_name: str, objective: str | None = None) -> dict:
        body = {}
        if objective:
            body["objective"] = objective
        return self._post(f"/policy-packs/{pack_name}/apply", body)

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = httpx.get(f"{self.base_url}{path}", headers=self._headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> Any:
        r = httpx.post(f"{self.base_url}{path}", headers=self._headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json()
