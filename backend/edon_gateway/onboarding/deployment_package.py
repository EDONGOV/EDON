"""Deployment Package Generator.

Produces a concrete, IT-approvable deployment package from a GovernanceDeploymentProfile
and its EnforcementTopology. Output is structured JSON that maps directly to:

  - Helm chart values  (k8s deployments)
  - VPC/ECS task defs (AWS)
  - env var blocks     (connector mode)
  - network rules      (firewall / security groups)
  - rollback plan      (step-by-step)

This is what the customer's IT/infra team actually reviews and approves.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Any


@dataclass
class DeploymentPackage:
    profile_id: str
    tenant_id: str
    generated_at: str
    deployment_mode: str          # primary mode: "helm_sidecar" | "http_proxy" | "sdk" | "webhook"
    helm_values: dict[str, Any]   # directly usable as values.yaml override
    env_vars: dict[str, str]      # env block for connector / gateway process
    connector_configs: list[dict] # one entry per enforcement point
    network_requirements: dict    # ingress/egress rules
    identity_setup: dict          # OIDC / service account requirements
    audit_pipeline: dict          # where audit events should go
    rollback_plan: list[str]      # ordered steps to undo EDON
    estimated_setup_h: float      # realistic install estimate

    def as_dict(self) -> dict:
        return asdict(self)


def generate_deployment_package(profile, topology) -> DeploymentPackage:
    """Build the deployment package from profile + topology."""
    from .profile import GovernanceDeploymentProfile
    from .topology import EnforcementTopology
    from ..market_packs import get_market_pack
    assert isinstance(profile, GovernanceDeploymentProfile)
    assert isinstance(topology, EnforcementTopology)

    now = datetime.now(UTC).isoformat()
    mode = topology.deployment_modes[0] if topology.deployment_modes else "http_proxy"
    market_pack = get_market_pack(getattr(profile, "market_pack", "healthcare"))

    # ── Helm values ───────────────────────────────────────────────────────────
    helm_values = {
        "edon": {
            "tenantId": profile.tenant_id,
            "orgName": profile.org_name,
            "mode": "shadow",          # always start in shadow; flip to 'active' post-signoff
            "riskTier": profile.risk_tier,
            "gateway": {
                "replicas": 2 if profile.risk_tier in ("critical", "high") else 1,
                "resources": {
                    "requests": {"cpu": "250m", "memory": "256Mi"},
                    "limits":   {"cpu": "1000m", "memory": "512Mi"},
                },
                "image": "edoncore/gateway:latest",
            },
            "audit": {
                "enabled": True,
                "retentionDays": 90 if "HIPAA" in profile.compliance_requirements else 30,
            },
            "shadowMode": {
                "enabled": True,
                "logAllDecisions": True,
            },
            "marketPack": market_pack["slug"],
            "marketPackVersion": market_pack["version"],
            "marketPackPolicyPack": market_pack["policy_pack"],
            "identityProvider": profile.identity_provider,
            "compliance": profile.compliance_requirements,
        }
    }

    # ── Environment variables ────────────────────────────────────────────────
    env_vars = {
        "EDON_TENANT_ID": profile.tenant_id,
        "EDON_MODE": "shadow",
        "EDON_RISK_TIER": profile.risk_tier,
        "EDON_SHADOW_MODE": "true",
        "EDON_AUDIT_RETENTION_DAYS": "90" if "HIPAA" in profile.compliance_requirements else "30",
        "EDON_LOG_LEVEL": "INFO",
        "EDON_IDENTITY_PROVIDER": profile.identity_provider,
        "EDON_MARKET_PACK": market_pack["slug"],
        "EDON_MARKET_PACK_VERSION": market_pack["version"],
    }
    if profile.compliance_requirements:
        env_vars["EDON_COMPLIANCE_REQUIREMENTS"] = ",".join(profile.compliance_requirements)
    if "PHI" in profile.all_data_classes:
        env_vars["EDON_PHI_PROTECTION"] = "strict"
    if "PCI" in profile.all_data_classes:
        env_vars["EDON_PCI_PROTECTION"] = "strict"
    if "credentials" in profile.all_data_classes:
        env_vars["EDON_CREDENTIALS_STRICT"] = "true"

    # ── Connector configs (one per enforcement point) ─────────────────────────
    connector_configs = []
    for ep in topology.enforcement_points:
        connector_configs.append({
            "point_id": ep.point_id,
            "label": ep.label,
            "connector_type": ep.connector_type,
            "agent_system": ep.agent_system,
            "intercepts": ep.intercepts,
            "config": _connector_config(ep.connector_type, profile),
        })

    # ── Network requirements ─────────────────────────────────────────────────
    network_requirements = {
        "inbound": [
            {"port": 8000, "protocol": "HTTPS", "source": "agent_runtime", "purpose": "action interception"},
            {"port": 8001, "protocol": "HTTPS", "source": "admin_network", "purpose": "management API"},
        ],
        "outbound": [],
        "dns_required": ["edon-gateway.internal"],
        "tls_required": True,
        "mtls_recommended": profile.risk_tier in ("critical", "high"),
    }
    for sink in profile.external_sinks[:10]:
        network_requirements["outbound"].append({
            "destination": sink, "port": 443, "protocol": "HTTPS",
            "purpose": "approved external sink — must be whitelisted",
        })

    # ── Identity setup ───────────────────────────────────────────────────────
    idp = profile.identity_provider
    identity_setup: dict[str, Any] = {
        "provider": idp,
        "service_account": {
            "name": f"edon-gateway-{profile.tenant_id[:8]}",
            "permissions": ["read:audit_logs", "write:governance_events"],
        },
    }
    if idp == "entra":
        identity_setup["oidc"] = {
            "issuer": "https://login.microsoftonline.com/{tenant_id}/v2.0",
            "client_id": "REPLACE_WITH_APP_REGISTRATION_CLIENT_ID",
            "scope": "openid profile email",
        }
    elif idp == "okta":
        identity_setup["oidc"] = {
            "issuer": "https://{your-okta-domain}/oauth2/default",
            "client_id": "REPLACE_WITH_OKTA_CLIENT_ID",
            "scope": "openid profile email",
        }

    # ── Audit pipeline ───────────────────────────────────────────────────────
    audit_pipeline = {
        "mode": "append_only",
        "destinations": ["edon_audit_db"],
        "siem_export": {
            "enabled": profile.risk_tier in ("critical", "high"),
            "format": "CEF",
            "endpoint": "REPLACE_WITH_SIEM_ENDPOINT",
        },
        "retention_days": 90 if "HIPAA" in profile.compliance_requirements else 30,
        "immutable": True,
        "encryption_at_rest": "AES-256",
    }

    # ── Rollback plan ────────────────────────────────────────────────────────
    rollback_plan = [
        "1. Set EDON_MODE=disabled in all connector env vars — agents bypass EDON immediately",
        "2. Scale EDON gateway replicas to 0 (kubectl scale deploy/edon-gateway --replicas=0)",
        "3. Remove EDON sidecar annotations from agent deployments",
        "4. Restore original agent service endpoints (DNS / k8s service selectors)",
        "5. Verify agent traffic flows without EDON interception (smoke test)",
        "6. Retain audit logs — do NOT delete; required for compliance review",
        "7. Notify EDON support at support@edoncore.com with tenant ID",
    ]

    # ── Setup time estimate ──────────────────────────────────────────────────
    base_h = 2.0
    base_h += len(profile.agent_systems) * 0.5
    base_h += 1.0 if profile.identity_provider != "none" else 0.0
    base_h += 1.0 if profile.risk_tier in ("critical", "high") else 0.0
    base_h += 0.5 * len(profile.compliance_requirements)

    return DeploymentPackage(
        profile_id=profile.profile_id,
        tenant_id=profile.tenant_id,
        generated_at=now,
        deployment_mode=mode,
        helm_values=helm_values,
        env_vars=env_vars,
        connector_configs=connector_configs,
        network_requirements=network_requirements,
        identity_setup=identity_setup,
        audit_pipeline=audit_pipeline,
        rollback_plan=rollback_plan,
        estimated_setup_h=round(base_h, 1),
    )


def _connector_config(connector_type: str, profile) -> dict:
    base = {
        "shadow_mode": True,
        "tenant_id": profile.tenant_id,
        "gateway_url": "https://REPLACE_WITH_EDON_GATEWAY_URL",
        "api_key": "REPLACE_WITH_EDON_API_KEY",
        "timeout_ms": 200,
        "fail_open": False,
    }
    if connector_type == "http_proxy":
        base.update({
            "proxy_port": 8000,
            "intercept_headers": ["X-Agent-ID", "X-Action-Type", "Authorization"],
        })
    elif connector_type == "sidecar":
        base.update({
            "sidecar_image": "edoncore/sidecar:latest",
            "intercept_syscalls": False,
            "intercept_http": True,
        })
    elif connector_type == "sdk_wrapper":
        base.update({
            "sdk_language": "python",
            "wrap_tool_calls": True,
            "async_mode": True,
        })
    elif connector_type == "webhook":
        base.update({
            "webhook_url": "https://REPLACE_WITH_EDON_GATEWAY_URL/v1/action",
            "retry_policy": {"max_retries": 3, "backoff_ms": 100},
        })
    return base
