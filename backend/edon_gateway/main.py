# THIS IS THE EDON GATEWAY ENTRYPOINT. Do not start app.main:app for gateway traffic.
"""EDON Gateway — application shell.

Responsibilities of this file:
  - FastAPI app creation
  - Middleware registration (order matters — see inline comments)
  - Route registration via _register_routes()
  - Static UI mounting
  - Shared app-state initialisation (db, governor, prometheus gauges)
  - Lifecycle wiring (lifespan from startup.py)

Everything else lives in a dedicated module.
"""
# NOTE: dotenv loading is handled in config.py. Do NOT call load_dotenv() here.

import os
import time

from fastapi import FastAPI

from .audit import AuditLogger
from .config import config
from .governor import EDONGovernor
from .logging_config import get_logger, setup_logging
from .middleware import AuthMiddleware, MagValidationMiddleware, RateLimitMiddleware, ValidationMiddleware
from .middleware.cors import setup_cors
from .middleware.latency_slo import LatencySLOMiddleware
from .middleware.rbac import RBACMiddleware
from .middleware.security_headers import add_security_headers_middleware
from .monitoring.metrics import metrics as metrics_collector  # noqa: F401 (imported by route modules)
from .monitoring.prometheus_registry import (  # re-exported: governor.py + routes import from here
    prometheus_active_intents,
    prometheus_anomalies_detected_total,
    prometheus_decision_latency_ms,
    prometheus_decisions_total,
    prometheus_policy_eval_time_ms,
    prometheus_rate_limit_hits_total,
    prometheus_uptime_seconds,
)
from .persistence import get_db
from .routes.integrations import get_integration_status as integrations_account_handler  # noqa: F401
from .startup import lifespan
from .ui_mount import mount_static_ui

setup_logging()
logger = get_logger(__name__)

for _w in config.validate():
    logger.warning("Configuration warning: %s", _w)

if config.is_production():
    config.assert_enterprise_ready()


# ── Route registration ─────────────────────────────────────────────────────────

def _register_routes(app: FastAPI) -> None:
    """Import and mount all route modules grouped by domain."""
    from .routes.integrations import router as integrations_router
    from .routes.analytics import router as analytics_router
    from .routes.auth import router as auth_router
    from .routes.v1_action import router as v1_action_router
    from .routes.v1_output import router as v1_output_router
    from .routes.v1_llm import router as v1_llm_router
    from .routes.audit import router as audit_router, router_review as review_router, router_auditors as auditors_router
    from .routes.compliance import router as compliance_router
    from .routes.policy import router as policy_router, router_packs as policy_packs_router, router_signing as signing_router
    from .routes.api_keys import router as api_keys_router
    from .routes.admin import router as admin_router
    from .routes.agents import router as agents_router
    from .routes.telemetry import router as telemetry_router
    from .routes.learning import router as learning_router
    from .routes.intents import router as intents_router
    from .routes.execute import router as execute_router
    from .routes.invoke import router as invoke_router
    from .routes.sandbox import router as sandbox_router
    from .routes.alerts import router as alerts_router
    from .routes.privacy import router as privacy_router
    from .routes.devices import router as devices_router
    from .routes.settings import router as settings_router
    from .routes.live_key import router as live_key_router
    from .routes.webhooks import router as webhooks_router
    from .routes.swarm import router as swarm_router
    from .routes.edge import router as edge_router
    from .routes.telegram_bot import router as telegram_bot_router
    from .routes.review_queue import router as review_queue_router
    from .routes.shadow_findings import router as shadow_findings_router
    from .routes.action_result import router as action_result_router
    from .routes.kill_switch import router as kill_switch_router
    from .routes.impact import router as impact_router
    from .routes.hardening import router as hardening_router
    from .routes.healing import router as healing_router
    from .routes.cicd import router as cicd_router
    from .routes.creao import router as creao_router
    from .routes.bootstrap import router as bootstrap_router
    from .routes.proof import router as proof_router
    from .routes.training import router as training_router
    from .routes.jarvis import router as jarvis_router
    from .routes.assistant import router as assistant_router
    from .routes.voice import router as voice_router
    from .routes.autonomous import router as autonomous_router
    from .routes.codex import router as codex_router
    from .routes.proposals import router as proposals_router
    from .routes.onboarding import router as onboarding_router
    from .routes.estop import router as estop_router
    from .routes.physical import router as physical_router
    from .routes.ops import router as ops_router
    from .routes.decisions import router as decisions_router
    from .routes.clawdbot_proxy import router as clawdbot_proxy_router

    # Core governance
    app.include_router(v1_action_router)
    app.include_router(v1_output_router)
    app.include_router(v1_llm_router)
    app.include_router(execute_router)
    app.include_router(invoke_router)
    app.include_router(intents_router)
    # Audit & compliance
    app.include_router(audit_router)
    app.include_router(review_router)
    app.include_router(auditors_router)
    app.include_router(compliance_router)
    app.include_router(review_queue_router)
    app.include_router(privacy_router)
    # Policy
    app.include_router(policy_router)
    app.include_router(policy_packs_router)
    app.include_router(signing_router)
    app.include_router(proposals_router)
    # Auth & tenancy
    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(admin_router)
    app.include_router(live_key_router)
    app.include_router(bootstrap_router)
    # Agents & devices
    app.include_router(agents_router, prefix="/agents", tags=["agents"])
    app.include_router(devices_router)
    app.include_router(swarm_router)
    app.include_router(edge_router)
    # Security & hardening
    app.include_router(kill_switch_router)
    app.include_router(shadow_findings_router)
    app.include_router(impact_router)
    app.include_router(hardening_router)
    app.include_router(healing_router)
    app.include_router(cicd_router)
    app.include_router(proof_router)
    # Autonomy
    app.include_router(autonomous_router)
    app.include_router(creao_router)
    # Copilots & assistant
    app.include_router(jarvis_router)
    app.include_router(assistant_router)
    app.include_router(codex_router)
    app.include_router(onboarding_router)
    app.include_router(voice_router)
    # Infrastructure & integrations
    app.include_router(integrations_router)
    app.include_router(analytics_router)
    app.include_router(telemetry_router)
    app.include_router(learning_router)
    app.include_router(sandbox_router)
    app.include_router(alerts_router)
    app.include_router(settings_router)
    app.include_router(webhooks_router)
    app.include_router(action_result_router)
    app.include_router(training_router)
    app.include_router(telegram_bot_router)
    app.include_router(estop_router)
    app.include_router(physical_router)
    # Platform ops, decision query, connector proxies
    app.include_router(ops_router)
    app.include_router(decisions_router)
    app.include_router(clawdbot_proxy_router)


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="EDON Gateway",
    version="1.0.1",
    description="AI Agent Safety Layer with Governance and Policy Enforcement",
    docs_url=None if config.is_production() else "/docs",
    redoc_url=None if config.is_production() else "/redoc",
    openapi_url=None if config.is_production() else "/openapi.json",
)

# Billing router must be attached before middleware is finalised
if os.getenv("EDON_ENABLE_BILLING", "true").lower() == "true":
    from .billing.bootstrap import router as billing_router
    app.include_router(billing_router)

# Middleware — added in reverse execution order (last added = outermost).
# Execution order (innermost → outermost):
#   security_headers → LatencySLO → Validation → RateLimit → MAG → RBAC → Auth → CORS
add_security_headers_middleware(app)
app.add_middleware(LatencySLOMiddleware)
app.add_middleware(ValidationMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MagValidationMiddleware)
app.add_middleware(RBACMiddleware)
app.add_middleware(AuthMiddleware)

_register_routes(app)
setup_cors(app)          # CORSMiddleware + CORSEnsureMiddleware (outermost pair)
mount_static_ui(app)     # React console UI + voice interface


# ── Shared state ───────────────────────────────────────────────────────────────

db = get_db()
governor = EDONGovernor(db=db)
# Backward-compat placeholder; keep the symbol without opening a process-global file handle.
audit_logger = AuditLogger()

app.state.governor = governor           # type: ignore[attr-defined]
app.state.db = db                       # type: ignore[attr-defined]
app.state.start_time = time.time()      # type: ignore[attr-defined]

# startup.py reads these to set initial gauge values after the event loop starts
app.state.prometheus_active_intents = prometheus_active_intents   # type: ignore[attr-defined]
app.state.prometheus_uptime_seconds = prometheus_uptime_seconds   # type: ignore[attr-defined]


# ── Lifespan ───────────────────────────────────────────────────────────────────

app.router.lifespan_context = lifespan
