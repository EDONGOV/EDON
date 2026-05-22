"""Platform operations endpoints: health, version, metrics, websocket.

These are infrastructure/ops concerns — not governance business logic.
They live here so main.py contains only composition and lifecycle wiring.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..config import config
from ..integration_catalog import get_enterprise_integration_catalog
from ..market_packs import get_market_pack
from ..logging_config import get_logger
from ..middleware.latency_slo import get_slo_stats
from ..security.vault import get_vault_status
from ..tenant_knowledge import build_tenant_knowledge_snapshot

logger = get_logger(__name__)

router = APIRouter(tags=["ops"])

# Active WebSocket connections for /ws/events
_ws_connections: list = []


# ── Models ─────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    ok: bool = True
    status: str
    version: str
    uptime_seconds: int
    governor: Dict[str, Any]
    components: Dict[str, Any] = {}
    overall_status: str = "healthy"


class VersionResponse(BaseModel):
    version: str
    git_sha: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_cav_dependency_status() -> Dict[str, Any]:
    import time as _time
    import requests as _requests

    if not config.CAV_ENABLED or not config.CAV_URL:
        return {"status": "not_configured", "url": config.CAV_URL}
    try:
        t0 = _time.perf_counter()
        cav_res = _requests.get(f"{config.CAV_URL.rstrip('/')}/health", timeout=2.0)
        return {
            "status": "healthy" if cav_res.ok else "unreachable",
            "url": config.CAV_URL,
            "latency_ms": round((_time.perf_counter() - t0) * 1000, 2),
            "http_status": cav_res.status_code,
        }
    except Exception as _exc:
        return {"status": "unreachable", "url": config.CAV_URL, "error": str(_exc)[:200]}


def _get_database_dependency_status(app) -> Dict[str, Any]:
    from ..persistence.schema_version import get_current_schema_version, SCHEMA_VERSION

    db = app.state.db
    backend = type(db).__name__
    url = os.getenv("DATABASE_URL", "").strip()
    scheme = "postgresql" if url.startswith(("postgresql://", "postgres://")) else "sqlite"
    try:
        schema_version = get_current_schema_version(db)
    except Exception as exc:
        schema_version = None
        schema_error = str(exc)[:200]
    else:
        schema_error = None
    return {
        "status": "healthy",
        "backend": backend,
        "scheme": scheme,
        "schema_version": schema_version,
        "expected_schema_version": SCHEMA_VERSION,
        "schema_error": schema_error,
    }


def _get_procurement_evidence_status() -> Dict[str, Any]:
    evidence_dir = Path("docs/evidence")
    backend_docs = Path("backend/docs")
    verification_ledger = evidence_dir / "verification-ledger.md"
    advisory_review = evidence_dir / "production-advisory-review.md"
    compliance_pack = evidence_dir / "compliance-pack.md"
    restore_drill = backend_docs / "ROLLBACK_DRILL.md"
    backup_procedures = backend_docs / "BACKUP_PROCEDURES.md"
    audit_chain = evidence_dir / "audit-chain.md"
    return {
        "verification_ledger": verification_ledger.exists(),
        "advisory_review": advisory_review.exists(),
        "compliance_pack": compliance_pack.exists(),
        "restore_drill": restore_drill.exists(),
        "backup_procedures": backup_procedures.exists(),
        "audit_chain": audit_chain.exists(),
        "dependency_graph_submission": Path(".github/workflows/dependency_graph_submission.yml").exists(),
    }


def _get_governance_drift_status() -> Dict[str, Any]:
    catalog = get_enterprise_integration_catalog(approved_only=False)
    approved_targets = [t for t in catalog.get("targets", []) if t.get("enterprise_supported")]
    connector_version_drift = any(
        not t.get("last_verified") or t.get("certification_status") != "certified"
        for t in approved_targets
    )
    idp_claim_drift = not (config.ENTERPRISE_SSO_ONLY and bool(config.ENTERPRISE_IDENTITY_PROVIDERS))
    policy_pack_drift = not config.AUTH_ENABLED or not config.ENCRYPT_AUDIT_PAYLOAD
    permissions_drift = not (config.is_production() and config.ENTERPRISE_DEFAULT_USER_ROLE == "viewer")
    edge_config_drift = not (
        config.EDGE_REQUIRE_NODE_CERTIFICATE
        and config.EDGE_REQUIRE_ATTESTATION
        and bool(config.EDGE_BUNDLE_SIGNING_KEY)
    )
    return {
        "connector_version_drift": connector_version_drift,
        "idp_claim_drift": idp_claim_drift,
        "policy_pack_drift": policy_pack_drift,
        "permissions_drift": permissions_drift,
        "edge_config_drift": edge_config_drift,
        "status": "healthy"
        if not any([connector_version_drift, idp_claim_drift, policy_pack_drift, permissions_drift, edge_config_drift])
        else "degraded",
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Real-time stream of governed action events."""
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)
    except Exception:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse)
async def health(request: Request):
    import time as _time

    db = request.app.state.db
    governor = request.app.state.governor
    uptime_seconds = int(_time.time() - request.app.state.start_time)

    db_component: Dict[str, Any] = {"status": "unhealthy", "latency_ms": None}
    try:
        t0 = _time.perf_counter()
        with db._get_connection() as _conn:
            _cur = _conn.cursor()
            _cur.execute("SELECT 1")
            _cur.fetchone()
        db_component = {
            "status": "healthy",
            "latency_ms": round((_time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as _exc:
        db_component = {"status": "unhealthy", "latency_ms": None, "error": str(_exc)[:200]}

    pe_component: Dict[str, Any] = {"status": "unhealthy"}
    try:
        _pe = getattr(governor, "policy_engine", None)
        if _pe is not None:
            pe_component = {"status": "healthy", "type": type(_pe).__name__}
        else:
            pe_component = {"status": "degraded", "note": "PolicyEngine not attached to governor"}
    except Exception as _exc:
        pe_component = {"status": "unhealthy", "error": str(_exc)[:200]}

    slo_stats = get_slo_stats()
    p99 = slo_stats.get("p99_ms")
    slo_target = slo_stats.get("slo_p99_target_ms", 100)
    slo_status = "healthy" if p99 is None or p99 <= slo_target else "degraded"
    slo_component = {"status": slo_status, **slo_stats}

    components = {
        "database": db_component,
        "policy_engine": pe_component,
        "rate_limiter": {"status": "healthy"},
        "latency_slo": slo_component,
        "cav_dependency": _get_cav_dependency_status(),
    }
    all_healthy = all(c.get("status") == "healthy" for c in components.values())
    overall_status = "healthy" if all_healthy else "degraded"

    active_preset = db.get_active_policy_preset()
    preset_info = None
    active_intent_id = None
    if active_preset:
        preset_name = active_preset["preset_name"]
        preset_info = {"preset_name": preset_name, "applied_at": active_preset["applied_at"]}
        try:
            all_intents = db.list_intents()
            matching = [
                i for i in all_intents if preset_name.lower() in i.get("intent_id", "").lower()
            ]
            active_intent_id = (matching or all_intents or [{}])[0].get("intent_id")
        except Exception:
            pass

    return HealthResponse(
        ok=all_healthy,
        status=overall_status,
        version=request.app.version,
        uptime_seconds=uptime_seconds,
        governor={
            "policy_version": "1.0.0",
            "active_intents": len(db.list_intents()),
            "active_preset": preset_info,
            "active_intent_id": active_intent_id,
        },
        components=components,
        overall_status=overall_status,
    )


@router.get("/health/dependencies")
async def health_dependencies(request: Request):
    db_status = _get_database_dependency_status(request.app)
    return {
        "ok": db_status.get("schema_error") is None,
        "service": "gateway",
        "dependencies": {
            "database": db_status,
            "cav": _get_cav_dependency_status(),
        },
        "enterprise": {
            "production_mode": config.is_production(),
            "auth_enabled": config.AUTH_ENABLED,
            "rate_limit_enabled": config.RATE_LIMIT_ENABLED,
            "cors_strict": "*" not in config.CORS_ORIGINS,
            "postgres_required": config.is_production(),
        },
    }


@router.get("/ops/production-readiness")
async def production_readiness(request: Request):
    """Return deployment hardening checks for a first production client."""
    db_status = _get_database_dependency_status(request.app)
    violations = config.enterprise_violations()
    smtp_configured = bool((os.getenv("EDON_SMTP_HOST") or os.getenv("SMTP_HOST") or "").strip())
    idp_configured = bool(config.ENTERPRISE_IDENTITY_PROVIDERS) or bool((os.getenv("CLERK_ISSUER") or "").strip())
    vault_status = get_vault_status()
    vault_configured = vault_status.configured
    kms_configured = vault_status.kms_configured
    backup_configured = any(
        (os.getenv(name) or "").strip()
        for name in ("EDON_BACKUP_BUCKET", "EDON_BACKUP_SCHEDULE", "PG_BACKUP_BUCKET")
    )
    monitoring_configured = config.METRICS_ENABLED and bool((os.getenv("EDON_ALERT_WEBHOOK") or "").strip())
    cloud_provider = (os.getenv("EDON_CLOUD_PROVIDER") or "").strip().lower()
    cloud_profile = {
        "provider": cloud_provider or "not_configured",
        "baa_signed": (os.getenv("EDON_BAA_SIGNED") or "").strip().lower() in {"1", "true", "yes"},
        "hipaa_profile": (os.getenv("EDON_HIPAA_DEPLOYMENT_PROFILE") or "").strip().lower() in {"1", "true", "yes"},
        "private_network": (os.getenv("EDON_PRIVATE_NETWORK_ENABLED") or "").strip().lower() in {"1", "true", "yes"},
        "waf": (os.getenv("EDON_WAF_ENABLED") or "").strip().lower() in {"1", "true", "yes"},
        "managed_postgres": (os.getenv("EDON_MANAGED_POSTGRES") or "").strip().lower() in {"1", "true", "yes"},
    }
    cloud_ready = (
        cloud_profile["provider"] in {"aws", "azure", "gcp"}
        and cloud_profile["baa_signed"]
        and cloud_profile["hipaa_profile"]
        and cloud_profile["private_network"]
        and cloud_profile["waf"]
        and cloud_profile["managed_postgres"]
    )
    try:
        log_retention_days = int((os.getenv("EDON_LOG_RETENTION_DAYS") or "0").strip())
    except ValueError:
        log_retention_days = 0
    checks = [
        {
            "id": "sso_email_invites",
            "label": "SSO/email invite delivery",
            "status": "pass" if idp_configured and smtp_configured and os.getenv("EDON_SSO_ROLE_CLAIM") and os.getenv("EDON_SSO_DEPARTMENT_CLAIM") else "needs_config",
            "detail": "Configure enterprise identity provider, role/department claims, and SMTP/email connector.",
        },
        {
            "id": "production_hardening",
            "label": "Production environment hardening",
            "status": "pass" if not violations and cloud_ready and backup_configured and monitoring_configured else "needs_config",
            "detail": "BAA, HIPAA profile, private networking, WAF, managed Postgres, backups, metrics, and alerting must be locked before go-live.",
            "violations": violations,
        },
        {
            "id": "runtime_credentials",
            "label": "Real credential handling",
            "status": "pass" if vault_configured and kms_configured and config.TOKEN_BINDING_ENABLED else "needs_config",
            "detail": "Runtime credentials should use vault/KMS storage, rotation, and short-lived token exchange.",
        },
        {
            "id": "monitoring_alerting",
            "label": "Monitoring and alerting",
            "status": "pass" if monitoring_configured and log_retention_days >= 365 and any((os.getenv(name) or "").strip() for name in ("EDON_SIEM_ENDPOINT", "EDON_SENTINEL_WORKSPACE_ID", "EDON_SPLUNK_HEC_URL", "EDON_LOG_ARCHIVE_BUCKET")) else "needs_config",
            "detail": "Metrics, alert routing, SIEM export, and 365+ day log retention must be configured.",
        },
        {
            "id": "backup_restore",
            "label": "Backup and restore readiness",
            "status": "pass" if backup_configured and bool((os.getenv("EDON_RESTORE_DRILL_LAST_RUN_AT") or "").strip()) else "needs_config",
            "detail": "Managed database backups and a documented restore drill timestamp are required.",
        },
        {
            "id": "client_e2e",
            "label": "End-to-end client test",
            "status": "manual_required",
            "detail": "Run onboard runtime -> shadow audit -> review -> promote -> logged action -> report export.",
        },
        {
            "id": "permission_enforcement",
            "label": "Permission enforcement validation",
            "status": "pass" if config.ENTERPRISE_DEFAULT_USER_ROLE == "viewer" and idp_configured else "needs_config",
            "detail": "Validate SSO role claims and department-scoped access before client go-live.",
        },
    ]
    return {
        "ready": all(check["status"] == "pass" for check in checks),
        "environment": "production" if config.is_production() else "non-production",
        "database": db_status,
        "cloud_profile": cloud_profile,
        "vault": {
            "provider": vault_status.provider,
            "configured": vault_configured,
            "kms_configured": kms_configured,
            "secret_reference": vault_status.secret_reference,
            "kms_reference": vault_status.kms_reference,
        },
        "observability": {
            "metrics_enabled": config.METRICS_ENABLED,
            "alerting_configured": monitoring_configured,
            "log_retention_days": log_retention_days,
        },
        "checks": checks,
        "next_required_action": next((check for check in checks if check["status"] != "pass"), None),
    }


@router.get("/governance/procurement-dashboard")
async def procurement_dashboard(request: Request, tenant_id: str | None = None):
    db_status = _get_database_dependency_status(request.app)
    catalog = get_enterprise_integration_catalog(approved_only=False)
    approved_catalog = get_enterprise_integration_catalog(approved_only=True)
    approved_targets = approved_catalog.get("targets", [])
    latest_signoff = None
    deployment_mode = None
    market_pack = None
    resolved_tenant = tenant_id
    if resolved_tenant is None:
        try:
            from ..tenancy import get_request_tenant_id
            resolved_tenant = get_request_tenant_id(request)
        except Exception:
            resolved_tenant = None
    if resolved_tenant:
        try:
            from ..onboarding.signoff import get_signoff_store
            latest_signoff = get_signoff_store().latest_approved(resolved_tenant)
        except Exception:
            latest_signoff = None
        try:
            from ..onboarding.profile import get_onboarding_store
            profile_store = get_onboarding_store()
            profiles = profile_store.list_for_tenant(resolved_tenant)
            if profiles:
                deployment_mode = (profiles[0].get("deployment_mode") or "pilot").strip().lower()
                market_pack = get_market_pack(profiles[0].get("market_pack"))
        except Exception:
            deployment_mode = None
            market_pack = None
        try:
            tenant_snapshot = build_tenant_knowledge_snapshot(resolved_tenant).as_dict()
        except Exception:
            tenant_snapshot = None
    else:
        tenant_snapshot = None

    controls = {
        "sso_only": config.ENTERPRISE_SSO_ONLY or (config.is_production() and config.AUTH_ENABLED),
        "mfa": {
            "admin": config.REQUIRE_ADMIN_MFA,
            "phishing_resistant": config.REQUIRE_PHISHING_RESISTANT_MFA,
        },
        "postgres": db_status.get("scheme") == "postgresql" or config.is_production(),
        "audit_encryption": config.ENCRYPT_AUDIT_PAYLOAD,
        "token_binding": config.TOKEN_BINDING_ENABLED,
        "edge_identity": {
            "node_certificate": config.EDGE_REQUIRE_NODE_CERTIFICATE,
            "attestation": config.EDGE_REQUIRE_ATTESTATION,
            "bundle_signing_key": bool(config.EDGE_BUNDLE_SIGNING_KEY),
        },
        "backup_restore": _get_procurement_evidence_status(),
        "dependency_audit": {
            "graph_submission": Path(".github/workflows/dependency_graph_submission.yml").exists(),
            "active_catalog_targets": len(approved_targets),
        },
        "connector_certification": {
            "approved_only_targets": len(approved_targets),
            "supported_targets": len(catalog.get("targets", [])),
        },
        "latest_signoff": latest_signoff,
    }
    return {
        "tenant_id": resolved_tenant,
        "deployment_mode": deployment_mode,
        "market_pack": market_pack,
        "controls": controls,
        "catalog": {
            "version": catalog.get("version"),
            "approved_only_count": len(approved_targets),
            "total_count": len(catalog.get("targets", [])),
            "approved_categories": approved_catalog.get("approved_categories", []),
        },
        "tenant_knowledge": tenant_snapshot,
        "drift": _get_governance_drift_status(),
    }


@router.get("/version", response_model=VersionResponse)
def version(request: Request):
    git_sha = os.getenv("GIT_SHA", os.getenv("EDON_GIT_SHA", "unknown"))
    return VersionResponse(version=request.app.version, git_sha=git_sha)


@router.get("/security/anti-bypass")
async def get_anti_bypass_status():
    from ..security.anti_bypass import validate_anti_bypass_setup, get_bypass_resistance_score

    status_info = validate_anti_bypass_setup()
    score = get_bypass_resistance_score()
    return {
        "status": status_info,
        "bypass_resistance": score,
        "secure": status_info.get("validation", {}).get("secure", False),
    }


@router.get("/metrics")
def metrics_endpoint():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    if not config.METRICS_ENABLED:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Metrics collection is disabled")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
