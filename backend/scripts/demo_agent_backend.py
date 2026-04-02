#!/usr/bin/env python3
"""
Demo Agent Backend — minimal /tools/invoke endpoint for showcasing EDON plug-in.

This mimics what a customer's agent backend would expose. EDON Gateway calls
this when it ALLOWs a request (after you connect it via POST /integrations/clawdbot/connect).

Contract (same as Clawdbot / agent gateways):
  POST /tools/invoke
  Authorization: Bearer <your-token>
  Content-Type: application/json
  Body: { "tool": str, "action": str, "args": dict, optional "sessionKey": str }

Run:
  python edon_gateway/scripts/demo_agent_backend.py
  # Listens on http://127.0.0.1:18789 (or DEMO_AGENT_BACKEND_PORT)

Then in EDON:
  1. POST /integrations/clawdbot/connect with base_url=http://127.0.0.1:18789, secret=any-token
  2. (Or set CLAWDBOT_GATEWAY_URL=http://127.0.0.1:18789 CLAWDBOT_GATEWAY_TOKEN=any-token)
  3. Point your agent (or simulator) at EDON's /agent/invoke — when EDON allows, it will call this backend.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from fastapi import FastAPI, Request, Header, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:
    print("Install: pip install fastapi uvicorn", file=__import__("sys").stderr)
    raise

app = FastAPI(title="Demo Agent Backend", version="1.0", description="Minimal /tools/invoke for EDON showcase")

# Any token for demo; in production the customer would use their real backend auth.
DEMO_TOKEN = os.getenv("DEMO_AGENT_BACKEND_TOKEN", "demo-token")
PORT = int(os.getenv("DEMO_AGENT_BACKEND_PORT", "18789"))


class InvokeRequest(BaseModel):
    tool: str = "unknown"
    action: str = "json"
    args: dict = {}
    sessionKey: str | None = None


def _check_auth(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if token != DEMO_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@app.post("/tools/invoke")
async def tools_invoke(
    body: InvokeRequest,
    request: Request,
    authorization: str | None = None,
):
    """Accept the same contract EDON uses when proxying to a customer backend."""
    _check_auth(authorization)

    # Probe from EDON connect: sessions_list
    if body.tool == "sessions_list":
        return {
            "success": True,
            "sessions": [],
            "message": "Demo backend — no sessions",
        }

    # Any other tool: echo back so caller sees the full loop worked.
    return {
        "ok": True,
        "result": {
            "message": f"Demo backend received: {body.tool}.{body.action}",
            "args_keys": list((body.args or {}).keys()),
            "received_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "demo-agent-backend"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
