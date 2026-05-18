"""Bootstrap authentication for internal admin endpoints.

Validates the X-Bootstrap-Secret header used by Jarvis, Codex, Autonomous,
and Voice. Returns 401 if the secret is wrong; no-ops in dev mode when no
secret is configured.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request


def check_bootstrap_auth(request: Request) -> None:
    """Raise HTTP 401 if X-Bootstrap-Secret is missing or incorrect."""
    secret = os.getenv("EDON_BOOTSTRAP_SECRET", "")
    if not secret:
        return  # dev mode — no secret configured
    provided = request.headers.get("X-Bootstrap-Secret", "")
    if provided != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
