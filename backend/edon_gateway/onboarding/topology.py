"""EDON Enforcement Topology — where EDON plugs in.

Takes a GovernanceDeploymentProfile and generates the EDON Enforcement Topology:
exactly which interception points, connector types, trust boundaries, and
data-class crossing points are required to govern this client's environment.

This is machine-readable config, not documentation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class EnforcementPoint:
    point_id: str
    label: str
    agent_system: str
    connector_type: str          # "http_proxy", "sdk_wrapper", "sidecar", "webhook"
    intercepts: list[str]        # action types covered
    data_classes_at_risk: list[str]
    is_external_boundary: bool   # data crosses outside the org at this point
    priority: str                # "required", "recommended", "optional"
    notes: str = ""


@dataclass
class TrustBoundary:
    boundary_id: str
    label: str
    from_zone: str               # e.g. "internal_vpc", "agent_runtime"
    to_zone: str                 # e.g. "external_api", "ehr_system"
    data_classes: list[str]
    crossing_points: list[str]   # point_ids that cross this boundary
    enforcement: str             # "block_by_default", "escalate_by_default", "allow_with_audit"


@dataclass
class EnforcementTopology:
    profile_id: str
    tenant_id: str
    enforcement_points: list[EnforcementPoint]
    trust_boundaries: list[TrustBoundary]
    required_connectors: list[str]
    deployment_modes: list[str]  # ["helm_sidecar", "http_proxy", "sdk", "webhook"]
    summary: dict

    def as_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "tenant_id": self.tenant_id,
            "enforcement_points": [asdict(p) for p in self.enforcement_points],
            "trust_boundaries": [asdict(b) for b in self.trust_boundaries],
            "required_connectors": self.required_connectors,
            "deployment_modes": self.deployment_modes,
            "summary": self.summary,
        }


# Connector type heuristics
_CONNECTOR_MAP: dict[str, str] = {
    "aws_vpc":    "http_proxy",
    "azure_vnet": "http_proxy",
    "k8s":        "sidecar",
    "on_prem":    "sdk_wrapper",
    "saas":       "webhook",
}

_EXTERNAL_ACTION_PREFIXES = {
    "email", "slack", "webhook", "api", "http", "ftp",
    "sms", "voice", "external", "export", "upload",
}

_HIGH_RISK_ACTIONS = {
    "credential", "secret", "token", "auth", "admin",
    "delete", "drop", "purge", "impersonate", "sudo",
    "bulk", "export", "exfil",
}


def generate_topology(profile) -> EnforcementTopology:
    """Build the EDON Enforcement Topology from a GovernanceDeploymentProfile."""
    from .profile import GovernanceDeploymentProfile
    assert isinstance(profile, GovernanceDeploymentProfile)

    enforcement_points: list[EnforcementPoint] = []
    trust_boundaries: list[TrustBoundary] = []
    required_connectors: set[str] = set()
    deployment_modes: set[str] = set()

    for env in profile.environments:
        mode = _CONNECTOR_MAP.get(env, "sdk_wrapper")
        deployment_modes.add(mode)

    for i, agent_sys in enumerate(profile.agent_systems):
        # Determine connector type from environments
        env = profile.environments[0] if profile.environments else "saas"
        connector_type = _CONNECTOR_MAP.get(env, "sdk_wrapper")
        required_connectors.add(connector_type)

        external_actions = [
            a for a in agent_sys.actions
            if any(a.lower().startswith(p) for p in _EXTERNAL_ACTION_PREFIXES)
        ]
        high_risk_actions = [
            a for a in agent_sys.actions
            if any(p in a.lower() for p in _HIGH_RISK_ACTIONS)
        ]

        # Main interception point for this agent
        ep = EnforcementPoint(
            point_id=f"ep-{i+1:03d}",
            label=f"{agent_sys.name} — action intercept",
            agent_system=agent_sys.name,
            connector_type=connector_type,
            intercepts=agent_sys.actions,
            data_classes_at_risk=agent_sys.data_classes,
            is_external_boundary=bool(agent_sys.external_sinks),
            priority="required",
        )
        enforcement_points.append(ep)

        # External sink boundary point if agent sends data out
        if agent_sys.external_sinks or external_actions:
            ep_ext = EnforcementPoint(
                point_id=f"ep-{i+1:03d}-ext",
                label=f"{agent_sys.name} — external sink boundary",
                agent_system=agent_sys.name,
                connector_type="webhook" if connector_type == "webhook" else "http_proxy",
                intercepts=external_actions or agent_sys.actions,
                data_classes_at_risk=agent_sys.data_classes,
                is_external_boundary=True,
                priority="required",
                notes=f"Sinks: {', '.join(agent_sys.external_sinks)}",
            )
            enforcement_points.append(ep_ext)

        # Credential/high-risk boundary
        if high_risk_actions or any(dc in ("credentials", "PHI", "PCI") for dc in agent_sys.data_classes):
            ep_hr = EnforcementPoint(
                point_id=f"ep-{i+1:03d}-hr",
                label=f"{agent_sys.name} — high-risk action gate",
                agent_system=agent_sys.name,
                connector_type=connector_type,
                intercepts=high_risk_actions or agent_sys.actions,
                data_classes_at_risk=agent_sys.data_classes,
                is_external_boundary=False,
                priority="required",
                notes="Hard-block zone for credential and destructive actions",
            )
            enforcement_points.append(ep_hr)

    # Trust boundaries: internal → external per data class
    if profile.external_sinks:
        tb = TrustBoundary(
            boundary_id="tb-ext-001",
            label="Internal agent runtime → External services",
            from_zone="agent_runtime",
            to_zone="external_internet",
            data_classes=profile.all_data_classes,
            crossing_points=[ep.point_id for ep in enforcement_points if ep.is_external_boundary],
            enforcement="block_by_default" if profile.risk_tier in ("critical", "high") else "escalate_by_default",
        )
        trust_boundaries.append(tb)

    # Identity boundary if IdP configured
    if profile.identity_provider and profile.identity_provider != "none":
        tb_id = TrustBoundary(
            boundary_id="tb-identity-001",
            label=f"Agent identity → {profile.identity_provider.upper()} trust boundary",
            from_zone="agent_runtime",
            to_zone=f"idp_{profile.identity_provider}",
            data_classes=["credentials"],
            crossing_points=[ep.point_id for ep in enforcement_points],
            enforcement="escalate_by_default",
        )
        trust_boundaries.append(tb_id)

    # PHI boundary (HIPAA)
    if "PHI" in profile.all_data_classes or "HIPAA" in profile.compliance_requirements:
        phi_eps = [ep.point_id for ep in enforcement_points
                   if "PHI" in ep.data_classes_at_risk]
        tb_phi = TrustBoundary(
            boundary_id="tb-phi-001",
            label="PHI data boundary (HIPAA)",
            from_zone="ehr_system",
            to_zone="agent_runtime",
            data_classes=["PHI"],
            crossing_points=phi_eps,
            enforcement="block_by_default",
        )
        trust_boundaries.append(tb_phi)

    summary = {
        "enforcement_point_count": len(enforcement_points),
        "required_count": sum(1 for e in enforcement_points if e.priority == "required"),
        "trust_boundary_count": len(trust_boundaries),
        "external_boundary_count": sum(1 for e in enforcement_points if e.is_external_boundary),
        "required_connectors": sorted(required_connectors),
        "deployment_modes": sorted(deployment_modes),
        "estimated_interception_coverage_pct": min(
            100, 100 * len(enforcement_points) // max(len(profile.all_actions), 1)
        ),
    }

    return EnforcementTopology(
        profile_id=profile.profile_id,
        tenant_id=profile.tenant_id,
        enforcement_points=enforcement_points,
        trust_boundaries=trust_boundaries,
        required_connectors=sorted(required_connectors),
        deployment_modes=sorted(deployment_modes),
        summary=summary,
    )
