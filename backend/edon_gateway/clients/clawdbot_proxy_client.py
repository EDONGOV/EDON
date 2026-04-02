#!/usr/bin/env python3
"""
EDON Proxy Client - Drop-in replacement for Clawdbot Gateway client.

Usage:
    OLD:
        POST http://clawdbot-gateway:18789/tools/invoke
        Authorization: Bearer <clawdbot-token>

    NEW:
        POST http://edon-gateway:8000/clawdbot/invoke
        X-EDON-TOKEN: <edon-token>
        X-Agent-ID: <agent-id>
        X-Intent-ID: <intent-id> (optional)

    Body schema is IDENTICAL.
"""

import os
import sys
import json
import requests
from typing import Dict, Any, Optional


class EDONClawdbotProxyClient:
    """
    Drop-in replacement for Clawdbot Gateway client.

    This client is intentionally PURE:
    - No FastAPI
    - No request object
    - No hidden globals
    """

    def __init__(
        self,
        edon_gateway_url: Optional[str] = None,
        edon_token: Optional[str] = None,
        agent_id: str = "clawdbot-agent",
        intent_id: Optional[str] = None,
        timeout_seconds: int = 30,
    ):
        self.edon_gateway_url = (
            edon_gateway_url
            or os.getenv("EDON_GATEWAY_URL")
            or "http://127.0.0.1:8000"
        ).rstrip("/")

        self.edon_token = (
            edon_token
            or os.getenv("EDON_GATEWAY_TOKEN")
            or os.getenv("EDON_API_TOKEN")
        )

        if not self.edon_token:
            raise ValueError(
                "EDON token missing. Set EDON_GATEWAY_TOKEN or EDON_API_TOKEN."
            )

        self.agent_id = agent_id
        self.intent_id = intent_id
        self.timeout_seconds = timeout_seconds

    def invoke(
        self,
        tool: str,
        action: str = "json",
        args: Optional[Dict[str, Any]] = None,
        sessionKey: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a Clawdbot tool via EDON governance.

        Signature matches Clawdbot Gateway EXACTLY.
        """

        payload: Dict[str, Any] = {
            "tool": tool,
            "action": action,
            "args": args or {},
        }

        if sessionKey is not None:
            payload["sessionKey"] = sessionKey

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.edon_token}",
            "Content-Type": "application/json",
        }
        if self.agent_id:
            headers["X-Agent-ID"] = self.agent_id
        if self.intent_id:
            headers["X-Intent-ID"] = self.intent_id

        url = f"{self.edon_gateway_url}/clawdbot/invoke"

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )

            # Normalize HTTP errors into Clawdbot-style response
            if response.status_code >= 400:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text

                return {
                    "ok": False,
                    "error": detail.get("detail") if isinstance(detail, dict) else str(detail),
                    "edon_verdict": "BLOCK",
                    "edon_explanation": f"HTTP {response.status_code}",
                }

            return response.json()

        except requests.exceptions.RequestException as e:
            return {
                "ok": False,
                "error": f"Connection error: {str(e)}",
                "edon_verdict": "BLOCK",
                "edon_explanation": "EDON gateway unreachable",
            }


# ────────────────────────────────────────────────────────────────
# CLI for manual testing
# ────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser("EDON Clawdbot Proxy Client")

    parser.add_argument("--edon-url", default=os.getenv("EDON_GATEWAY_URL"))
    parser.add_argument("--edon-token", default=os.getenv("EDON_GATEWAY_TOKEN") or os.getenv("EDON_API_TOKEN"))
    parser.add_argument("--agent-id", default="clawdbot-agent")
    parser.add_argument("--intent-id", default=None)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--action", default="json")
    parser.add_argument("--args", default="{}")
    parser.add_argument("--session-key", default=None)

    args = parser.parse_args()

    try:
        args_dict = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON for --args: {e}", file=sys.stderr)
        sys.exit(1)

    client = EDONClawdbotProxyClient(
        edon_gateway_url=args.edon_url,
        edon_token=args.edon_token,
        agent_id=args.agent_id,
        intent_id=args.intent_id,
    )

    result = client.invoke(
        tool=args.tool,
        action=args.action,
        args=args_dict,
        sessionKey=args.session_key,
    )

    print(json.dumps(result, indent=2))

    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
