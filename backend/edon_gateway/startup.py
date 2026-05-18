"""EDON Gateway startup and shutdown lifecycle.

Called from main.py via app.router.lifespan_context = lifespan.
Receives the FastAPI app instance; reads db, governor, and optional
prometheus objects from app.state so this module never imports from main.py.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from .config import config
from .logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: "FastAPI"):
    await _startup(app)
    yield
    await _shutdown(app)


async def _startup(app: "FastAPI") -> None:
    db = app.state.db
    governor = app.state.governor

    logger.info("=" * 60)
    logger.info("Starting EDON Gateway...")
    logger.info("Gateway version: %s", app.version)
    logger.info("=" * 60)

    from .persistence.schema_version import (
        check_schema_version,
        set_schema_version,
        get_current_schema_version,
        SCHEMA_VERSION,
    )
    from .security.hashing import validate_hash_security
    from .security.encryption import validate_encryption_setup

    validate_hash_security()
    validate_encryption_setup()

    if not check_schema_version(db):
        current_version = get_current_schema_version(db)
        logger.warning(
            "Database schema version mismatch. Current: %s, Expected: %s",
            current_version,
            SCHEMA_VERSION,
        )
        set_schema_version(db, SCHEMA_VERSION)
        logger.info("Schema version set to %s", SCHEMA_VERSION)
    else:
        logger.info("Database schema version OK: %s", SCHEMA_VERSION)

    logger.info(
        "Database backend: %s",
        "PostgreSQL"
        if "postgresql" in str(type(db).__name__).lower()
        else "SQLite (set DATABASE_URL=postgresql://... to switch)",
    )

    if config.METRICS_ENABLED:
        _prom_intents = getattr(app.state, "prometheus_active_intents", None)
        _prom_uptime = getattr(app.state, "prometheus_uptime_seconds", None)
        if _prom_intents is not None:
            _prom_intents.set(len(db.list_intents()))
        if _prom_uptime is not None:
            _prom_uptime.set(0)

    if config.NETWORK_GATING:
        from .security.network_gating import validate_network_gating, get_clawdbot_base_url

        base_url = get_clawdbot_base_url()
        is_valid, reachability, risk, recommendation = validate_network_gating(base_url, True)
        if not is_valid:
            error_msg = (
                f"Network gating validation failed: Clawdbot Gateway is {reachability} (risk: {risk}).\n"
                f"Recommendation:\n{recommendation}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        logger.info(
            "Network gating validation passed: Clawdbot Gateway is %s (risk: %s)",
            reachability,
            risk,
        )

    logger.debug("allow_env_token_in_prod=%s", config.ALLOW_ENV_TOKEN_IN_PROD)
    strict_fail_closed = (
        os.getenv(
            "EDON_STRICT_FAIL_CLOSED",
            "true" if config.is_production() else "false",
        )
        .strip()
        .lower()
        == "true"
    )
    if config.is_production():
        missing = []
        if not config.CLERK_SECRET_KEY:
            missing.append("CLERK_SECRET_KEY")
        if not config.STRIPE_SECRET_KEY:
            missing.append("STRIPE_SECRET_KEY")
        if strict_fail_closed and not (os.getenv("EDON_AUDIT_CHAIN_SIGNING_KEY") or "").strip():
            missing.append("EDON_AUDIT_CHAIN_SIGNING_KEY")
        if missing:
            raise RuntimeError(
                "Missing required production secrets: "
                + ", ".join(missing)
                + ". Refusing to boot in production."
            )
    elif not config.CLERK_SECRET_KEY:
        logger.warning(
            "CLERK_SECRET_KEY not set — POST /auth/signup will return 401. "
            "Set it (e.g. fly secrets set CLERK_SECRET_KEY=sk_live_...) to allow Clerk-based signup."
        )

    try:
        from .policy.defaults import seed_default_preset

        seed_default_preset(db)
    except Exception as _seed_err:
        logger.warning("Policy defaults seeding failed (non-fatal): %s", _seed_err)

    # Warn loudly in production if the signing key is ephemeral.
    # An ephemeral key means every restart breaks the audit signature chain.
    if config.is_production() and not os.getenv("EDON_SIGNING_KEY_HEX", "").strip():
        logger.error(
            "CRITICAL: EDON_SIGNING_KEY_HEX is not set. "
            "The gateway is using an ephemeral Ed25519 key that changes on every restart. "
            "This breaks audit chain integrity — previously signed decisions cannot be "
            "verified after a restart. Set EDON_SIGNING_KEY_HEX to a persistent 32-byte "
            "hex-encoded Ed25519 private key (e.g. fly secrets set EDON_SIGNING_KEY_HEX=...). "
            "Gateway will continue, but audit signatures are unreliable."
        )

    logger.info("EDON Gateway startup complete")

    try:
        from .alerts import fire_gateway_recovery_alert

        fire_gateway_recovery_alert()
    except Exception:
        pass

    async def _daily_audit_cleanup():
        await asyncio.sleep(3600)
        while True:
            try:
                from .billing.plans import get_plan_limits

                tenants = db.list_tenants() if hasattr(db, "list_tenants") else []
                _HIPAA_MIN_RETENTION_DAYS = 2190
                for t in tenants:
                    try:
                        lim = get_plan_limits(t.get("plan", "free"))
                        effective_retention = lim.audit_retention_days
                        if t.get("hipaa_mode") and effective_retention != -1:
                            effective_retention = max(effective_retention, _HIPAA_MIN_RETENTION_DAYS)
                        if effective_retention != -1:
                            deleted = db.delete_expired_audit_events(t["id"], effective_retention)
                            if deleted:
                                logger.info(
                                    "Retention cleanup: %d events deleted for tenant %s",
                                    deleted,
                                    t["id"],
                                )
                    except Exception as _te:
                        logger.warning("Retention cleanup error for tenant %s: %s", t["id"], _te)
            except Exception as _ce:
                logger.warning("Retention cleanup cycle error: %s", _ce)
            await asyncio.sleep(86400)

    asyncio.create_task(_daily_audit_cleanup())

    try:
        from .ai.audit_miner import run_audit_mining_loop
        from .ai.policy_suggester import run_policy_suggestion_loop
        from .persistence import get_db as _get_db

        asyncio.create_task(run_audit_mining_loop(_get_db))
        asyncio.create_task(run_policy_suggestion_loop(_get_db))
        logger.info("Audit mining and policy suggestion loops started")
    except Exception as _bg_err:
        logger.warning("Background analysis loops failed to start: %s", _bg_err)

    try:
        from .autonomous.loop import start_autonomous_loop

        start_autonomous_loop(governor=governor)
    except Exception as _ae:
        logger.warning("Autonomous loop startup error: %s", _ae)

    try:
        if os.getenv("EDON_PROBE_ENABLED", "true").lower() == "true":
            from .impact.active_probe import get_active_probe

            get_active_probe().start()
            logger.info("Active adversarial probe scheduler started")
    except Exception as _probe_err:
        logger.warning("Active probe startup error: %s", _probe_err)

    try:
        from .audit_queue import start_worker as start_audit_worker

        await start_audit_worker(db)
        logger.info("Audit queue worker started")
    except Exception as _aq_err:
        logger.warning("Audit queue worker failed to start: %s", _aq_err)

    try:
        from .training.auto_trainer import start_auto_trainer

        start_auto_trainer()
    except Exception as _at_err:
        logger.warning("Auto-trainer failed to start: %s", _at_err)

    # ── Background daemon threads ───────────────────���───────────────────────────
    # These were previously started at module import time in main.py.
    # Starting them here ensures they have access to a fully initialised app.

    try:
        from .impact.loop import start_background_scheduler as _start_impact_loop
        from .shadow.trace_capture import get_trace_store as _get_shadow_store

        _start_impact_loop(governor=governor, shadow_store=_get_shadow_store())
    except Exception as _impact_err:
        logger.warning("[impact] background scheduler failed to start: %s", _impact_err)

    try:
        from .agents.hardening.runner import start_background_scheduler as _start_hardening

        _start_hardening(governor=governor)
    except Exception as _hardening_err:
        logger.warning("[hardening] background scheduler failed to start: %s", _hardening_err)

    try:
        import uuid as _uuid

        _internal_tenant_id = os.getenv("EDON_SELF_GOVERN_TENANT_ID", "tenant_edon_internal")
        if not db.get_tenant(_internal_tenant_id):
            _uid = str(_uuid.uuid4())
            db.create_user(
                user_id=_uid,
                email="internal-agents@edoncore.com",
                auth_provider="internal",
                auth_subject="edon_internal_agents",
                role="admin",
            )
            db.create_tenant(tenant_id=_internal_tenant_id, user_id=_uid)
            logger.info("[self_govern] Provisioned internal governance tenant: %s", _internal_tenant_id)
        else:
            logger.debug(
                "[self_govern] Internal governance tenant already exists: %s", _internal_tenant_id
            )
    except Exception as _tenant_err:
        logger.warning("[self_govern] Internal tenant provisioning failed: %s", _tenant_err)


async def _shutdown(app: "FastAPI") -> None:
    """Graceful shutdown: drain async audit queue before process exits.

    Gives in-flight audit writes up to 10s to flush so no governance
    decisions are lost during rolling deploys or restarts.
    """
    logger.info("EDON Gateway shutting down — flushing in-flight audit events...")
    try:
        from .autonomous.loop import stop_autonomous_loop

        stop_autonomous_loop()
    except Exception as _ae:
        logger.debug("Autonomous loop stop error: %s", _ae)
    try:
        from .impact.active_probe import get_active_probe

        get_active_probe().stop()
    except Exception as _probe_err:
        logger.debug("Active probe stop error: %s", _probe_err)
    try:
        from .audit_queue import stop_worker as stop_audit_worker

        await stop_audit_worker(timeout_sec=10.0)
    except Exception as _err:
        logger.warning("Audit queue shutdown error (some events may be lost): %s", _err)
    logger.info("EDON Gateway shutdown complete")
