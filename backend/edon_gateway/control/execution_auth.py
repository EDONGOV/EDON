"""EDON Execution Authorization Layer.

Enforces a strict hierarchy of execution stages for all CREAO actions.
No stage can be skipped. Higher stages require progressively stronger
authorization.

Stage hierarchy (lowest → highest privilege):
  READ              — read system state, pull metrics, query graphs
  SIMULATE          — run Impact cycles, generate scenarios, dry-run analysis
  PROPOSE           — generate fix proposals, create PRs, suggest rules (no execution)
  APPLY_STAGING     — apply rule to staging environment, requires human approval
  DEPLOY_PRODUCTION — apply rule to production, requires multi-factor authorization

Used as a decorator on route handlers and called explicitly inside
CREAO's healing runner and fix pipeline.

Usage:
    from ..control.execution_auth import require_stage, ExecutionStage

    @require_stage(ExecutionStage.APPLY_STAGING)
    async def my_endpoint(request: Request): ...

    # Or inline:
    auth = ExecutionAuthLayer()
    auth.check(ExecutionStage.DEPLOY_PRODUCTION, tenant_id=tid, actor=actor_id)
"""

from __future__ import annotations

import os
from enum import IntEnum
from functools import wraps
from typing import Optional

from fastapi import HTTPException, Request

from ..logging_config import get_logger

logger = get_logger(__name__)

# ── Environment overrides ─────────────────────────────────────────────────────

_ALLOW_STAGING_AUTO  = os.getenv("EDON_EXEC_ALLOW_STAGING_AUTO",  "false").lower() == "true"
_ALLOW_PROD_AUTO     = os.getenv("EDON_EXEC_ALLOW_PROD_AUTO",     "false").lower() == "true"
_REQUIRE_MFA_PROD    = os.getenv("EDON_EXEC_REQUIRE_MFA_PROD",    "true").lower()  == "true"


class ExecutionStage(IntEnum):
    """Ordered execution stages — higher value = more privileged."""
    READ              = 0
    SIMULATE          = 1
    PROPOSE           = 2
    APPLY_STAGING     = 3
    DEPLOY_PRODUCTION = 4


_STAGE_LABELS = {
    ExecutionStage.READ:              "Read",
    ExecutionStage.SIMULATE:          "Simulate",
    ExecutionStage.PROPOSE:           "Propose",
    ExecutionStage.APPLY_STAGING:     "Apply (staging)",
    ExecutionStage.DEPLOY_PRODUCTION: "Deploy (production)",
}


class ExecutionAuthError(Exception):
    """Raised when an action is blocked by the execution authorization layer."""
    def __init__(self, stage: ExecutionStage, reason: str):
        self.stage = stage
        self.reason = reason
        super().__init__(f"ExecutionAuth blocked stage={stage.name}: {reason}")


class ExecutionAuthLayer:
    """
    Stateless authorization checker for execution stage gates.

    Instantiate once or use the module-level `check()` function.
    """

    def check(
        self,
        stage: ExecutionStage,
        *,
        tenant_id: Optional[str] = None,
        actor: Optional[str] = None,
        mfa_verified: bool = False,
        approval_token: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """
        Verify that the requested execution stage is authorized.

        Returns a dict with authorization metadata on success.
        Raises ExecutionAuthError on rejection.
        """
        label = _STAGE_LABELS[stage]

        match stage:
            case ExecutionStage.READ | ExecutionStage.SIMULATE | ExecutionStage.PROPOSE:
                # Always allowed — these are read/analysis operations only
                pass

            case ExecutionStage.APPLY_STAGING:
                # Requires either explicit human approval token OR env opt-in
                if not _ALLOW_STAGING_AUTO and not approval_token:
                    raise ExecutionAuthError(
                        stage,
                        f"staging apply requires human approval token. "
                        f"Set EDON_EXEC_ALLOW_STAGING_AUTO=true to enable autonomous staging deploys.",
                    )

            case ExecutionStage.DEPLOY_PRODUCTION:
                # Production deployment: never fully autonomous without explicit opt-in
                if not _ALLOW_PROD_AUTO:
                    raise ExecutionAuthError(
                        stage,
                        "production deployment requires explicit operator authorization. "
                        "EDON does not autonomously deploy to production by default. "
                        "Set EDON_EXEC_ALLOW_PROD_AUTO=true and provide an approval_token.",
                    )
                if _REQUIRE_MFA_PROD and not mfa_verified:
                    raise ExecutionAuthError(
                        stage,
                        "production deployment requires MFA verification. "
                        "Pass mfa_verified=True after validating the operator's second factor.",
                    )
                if not approval_token:
                    raise ExecutionAuthError(
                        stage,
                        "production deployment requires a signed approval token.",
                    )

        result = {
            "authorized": True,
            "stage": stage.name,
            "label": label,
            "tenant_id": tenant_id,
            "actor": actor,
        }
        logger.info(
            "[exec_auth] AUTHORIZED stage=%s tenant=%s actor=%s",
            stage.name, tenant_id, actor,
        )
        return result

    def as_http_check(
        self,
        stage: ExecutionStage,
        request: Request,
        approval_token: Optional[str] = None,
        mfa_verified: bool = False,
    ) -> dict:
        """
        FastAPI-friendly wrapper. Raises HTTPException(403) on rejection.
        Extracts tenant_id from the request object.
        """
        from ..tenancy import get_request_tenant_id
        tenant_id = get_request_tenant_id(request)
        actor = request.headers.get("X-Agent-ID") or request.headers.get("X-User-ID") or "unknown"
        try:
            return self.check(
                stage,
                tenant_id=tenant_id,
                actor=actor,
                approval_token=approval_token,
                mfa_verified=mfa_verified,
            )
        except ExecutionAuthError as exc:
            logger.warning(
                "[exec_auth] BLOCKED stage=%s tenant=%s actor=%s reason=%s",
                stage.name, tenant_id, actor, exc.reason,
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "execution_stage_blocked",
                    "stage": stage.name,
                    "reason": exc.reason,
                    "allowed_stages": [
                        s.name for s in ExecutionStage if s < stage
                    ],
                },
            )


# ── Decorator ─────────────────────────────────────────────────────────────────

_auth_layer = ExecutionAuthLayer()


def require_stage(stage: ExecutionStage):
    """
    FastAPI route decorator that enforces an execution stage gate.

    Example:
        @router.post("/deploy")
        @require_stage(ExecutionStage.APPLY_STAGING)
        async def deploy_rule(request: Request): ...
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            # Find the Request object in args/kwargs
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break

            approval_token = None
            if request:
                approval_token = (
                    request.headers.get("X-Approval-Token") or
                    request.headers.get("X-EDON-Approval")
                )

            if request:
                _auth_layer.as_http_check(stage, request, approval_token=approval_token)
            else:
                _auth_layer.check(stage)

            return await fn(*args, **kwargs)
        return wrapper
    return decorator
