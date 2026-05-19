"""Repeatable architecture standard for EDON deployments.

This module turns the onboarding primitives into a single machine-readable
deployment contract:

* invariant layers that must not vary across customers
* customer-variable packs that may vary by tenant
* proof requirements for enterprise readiness

The goal is to keep the runtime architecture stable while allowing policy,
integrations, workflows, permissions, and scale to differ per tenant.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Any, Optional


@dataclass(frozen=True)
class InvariantLayer:
    name: str
    responsibility: str
    must_remain_constant: list[str]
    proof_required: list[str]


@dataclass(frozen=True)
class CustomerVariablePack:
    name: str
    allowed_variation: list[str]
    validation_rules: list[str]
    examples: list[str]


@dataclass(frozen=True)
class GovernedActionMatrixEntry:
    action: str
    risk_tier: str
    approval: str
    rollback: str
    logged: bool


@dataclass(frozen=True)
class OperationalGuarantee:
    metric: str
    target: str
    scope: str
    notes: str


@dataclass(frozen=True)
class DeploymentClassification:
    classification: str
    meaning: str
    enforcement_notes: list[str]


@dataclass(frozen=True)
class RepeatableArchitectureStandard:
    standard_id: str
    version: str
    tenant_id: str
    org_name: str
    generated_at: str
    invariant_layers: list[InvariantLayer]
    customer_variable_packs: list[CustomerVariablePack]
    control_primitives: list[str]
    proof_requirements: list[str]
    release_gates: list[str]
    forbidden_variation: list[str]
    deployment_modes: list[str]
    required_connectors: list[str]
    governed_action_matrix: list[GovernedActionMatrixEntry]
    pilot_safety_mode: dict[str, Any]
    operational_guarantees: list[OperationalGuarantee]
    deployment_classification: list[DeploymentClassification]
    edge_runtime_boundary: list[str]
    policy_shape: dict[str, Any]
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_repeatable_architecture_standard(profile, topology, deployment_package, policy_bundle: Optional[Any] = None) -> RepeatableArchitectureStandard:
    """Build the repeatable architecture contract for a customer profile."""
    from .profile import GovernanceDeploymentProfile
    from .topology import EnforcementTopology
    from .deployment_package import DeploymentPackage

    assert isinstance(profile, GovernanceDeploymentProfile)
    assert isinstance(topology, EnforcementTopology)
    assert isinstance(deployment_package, DeploymentPackage)

    now = datetime.now(UTC).isoformat()
    standard_id = f"ras-{profile.tenant_id[:8]}-{profile.profile_id[-6:]}"

    invariant_layers = [
        InvariantLayer(
            name="runtime_governance_engine",
            responsibility="Every externally consequential action is evaluated before execution.",
            must_remain_constant=[
                "single enforcement entrypoint",
                "fail-closed governance verdicts on governed actions",
                "immutable audit trail with decision identity",
                "decision kernel is the only causal write path",
            ],
            proof_required=[
                "governed action test passes through the gateway",
                "audit chain validation remains intact",
            ],
        ),
        InvariantLayer(
            name="decision_kernel",
            responsibility="Typed DecisionCandidate input is committed once as an immutable DecisionRecord.",
            must_remain_constant=[
                "one DecisionCandidate per governed action",
                "one DecisionRecord per commit",
                "no parallel decision paths",
                "execution may only bind to a committed decision record",
            ],
            proof_required=[
                "decision record is emitted for governed actions",
                "execution binding references the committed decision id",
            ],
        ),
        InvariantLayer(
            name="agent_communication_layer",
            responsibility="All agent handoffs use explicit identity and permission checks.",
            must_remain_constant=[
                "authenticated handoff semantics",
                "tenant-scoped identity binding",
                "no direct tool execution outside the control plane",
            ],
            proof_required=[
                "tenant isolation test passes",
                "handoff identity is visible in audit records",
            ],
        ),
        InvariantLayer(
            name="operational_intelligence_layer",
            responsibility="Observe, score, and replay decisions without becoming a second source of truth.",
            must_remain_constant=[
                "shadow replay uses committed decisions",
                "anomaly detection is advisory to enforcement",
                "Impact analysis never authorizes live execution",
            ],
            proof_required=[
                "shadow replay produces a stable finding record",
                "Impact output references the committed decision record",
            ],
        ),
        InvariantLayer(
            name="edge_runtime",
            responsibility="Provide low-latency local execution while preserving governance semantics.",
            must_remain_constant=[
                "local runtime still enforces the same policy contract",
                "edge failure cannot bypass governance",
                "rollback path disables the edge cleanly",
            ],
            proof_required=[
                "deployment rollback drill documented",
                "edge/offline path tested against the same policy set",
            ],
        ),
        InvariantLayer(
            name="integration_layer",
            responsibility="Connect customer systems through versioned connectors and allowlists.",
            must_remain_constant=[
                "integrations are explicit and enumerated",
                "external sinks are registered before use",
                "connector versions are declared and reviewable",
            ],
            proof_required=[
                "connector inventory matches the onboarding profile",
                "external sink allowlist is present in the deployment package",
            ],
        ),
        InvariantLayer(
            name="command_console",
            responsibility="Expose the control plane, not a hidden admin bypass.",
            must_remain_constant=[
                "role-based views only",
                "governance status is visible alongside actions",
                "administrative operations are auditable and scoped",
            ],
            proof_required=[
                "role-based navigation is present",
                "admin actions leave an audit trail",
            ],
        ),
    ]

    customer_variable_packs = [
        CustomerVariablePack(
            name="policy_pack",
            allowed_variation=[
                "hard safety thresholds",
                "escalation thresholds",
                "domain-specific blocklists and allowlists",
                "compliance-specific overlays",
            ],
            validation_rules=[
                "policy changes must not alter invariant layers",
                "policy pack version must be recorded",
                "high-risk policy edits require review or signoff",
            ],
            examples=[
                "healthcare-core-v12",
                "ambient-clinical-v5",
                "research-shadow-v7",
            ],
        ),
        CustomerVariablePack(
            name="integration_pack",
            allowed_variation=[
                "customer tools",
                "external sinks",
                "identity provider",
                "connector mode",
            ],
            validation_rules=[
                "every external sink must be listed",
                "connector mode must match the customer environment",
                "identity provider must be documented in the deployment package",
            ],
            examples=[
                "FHIR EHR",
                "Okta",
                "k8s sidecar",
                "webhook broker",
            ],
        ),
        CustomerVariablePack(
            name="workflow_pack",
            allowed_variation=[
                "department-specific actions",
                "escalation routing",
                "approval chains",
                "shadow-to-enforced rollout cadence",
            ],
            validation_rules=[
                "workflow changes must preserve auditability",
                "high-impact workflows require explicit approval",
            ],
            examples=[
                "clinical review workflow",
                "research cohort review",
                "ops approval path",
            ],
        ),
        CustomerVariablePack(
            name="permission_pack",
            allowed_variation=[
                "role mapping",
                "tenant scope",
                "approval authority",
                "rate limits",
            ],
            validation_rules=[
                "least-privilege role mappings are required",
                "permissions must be tenant-scoped",
            ],
            examples=[
                "admin",
                "research",
                "clinical",
            ],
        ),
        CustomerVariablePack(
            name="scale_pack",
            allowed_variation=[
                "replica count",
                "retention horizon",
                "traffic volume",
                "site count",
            ],
            validation_rules=[
                "scale changes cannot lower safety guarantees",
                "production scale must remain observable and recoverable",
            ],
            examples=[
                "single tenant pilot",
                "multi-site enterprise rollout",
            ],
        ),
        CustomerVariablePack(
            name="environment_pack",
            allowed_variation=[
                "cloud provider",
                "network layout",
                "deployment mode",
                "regional constraints",
            ],
            validation_rules=[
                "the same governance contract must apply across environments",
                "environment-specific settings must be enumerated in the deployment package",
            ],
            examples=[
                "aws_vpc",
                "azure_vnet",
                "on_prem",
            ],
        ),
    ]

    control_primitives = [
        "policy packs",
        "decision kernel",
        "audit chain",
        "shadow replay",
        "impact analysis",
        "kill switch",
        "tenant isolation",
        "role-based console",
        "deployment package",
        "rollback plan",
    ]

    governed_action_matrix = [
        GovernedActionMatrixEntry(
            action="draft_patient_note",
            risk_tier="medium",
            approval="optional",
            rollback="yes",
            logged=True,
        ),
        GovernedActionMatrixEntry(
            action="record_writeback",
            risk_tier="high",
            approval="required",
            rollback="partial",
            logged=True,
        ),
        GovernedActionMatrixEntry(
            action="medication_update",
            risk_tier="critical",
            approval="required",
            rollback="limited",
            logged=True,
        ),
        GovernedActionMatrixEntry(
            action="billing_claim_submission",
            risk_tier="high",
            approval="required",
            rollback="partial",
            logged=True,
        ),
        GovernedActionMatrixEntry(
            action="robot_motion_command",
            risk_tier="critical",
            approval="required",
            rollback="limited",
            logged=True,
        ),
    ]

    pilot_safety_mode = {
        "name": "constrained_pilot_mode",
        "enabled": True,
        "rules": [
            "no autonomous clinical authority",
            "all high-risk actions require human approval",
            "no medication execution without explicit policy exception",
            "rollback required on governed writebacks where supported",
            "fail-closed on connector uncertainty",
        ],
    }

    operational_guarantees = [
        OperationalGuarantee(
            metric="policy_evaluation_latency",
            target="< 500 ms",
            scope="governed actions",
            notes="Policy verdicts should be fast enough for live workflow use.",
        ),
        OperationalGuarantee(
            metric="audit_persistence",
            target="100%",
            scope="governed actions",
            notes="Every governed action must persist an audit record.",
        ),
        OperationalGuarantee(
            metric="rollback_execution",
            target="documented and testable",
            scope="pilot writebacks",
            notes="Rollback plan must exist for every supported deployment path.",
        ),
        OperationalGuarantee(
            metric="tenant_isolation",
            target="strict",
            scope="all tenants",
            notes="No cross-tenant access unless explicitly approved.",
        ),
        OperationalGuarantee(
            metric="pilot_uptime",
            target="best-effort with incident response",
            scope="pilot environment",
            notes="Pilot SLAs should be explicit and conservative.",
        ),
    ]

    deployment_classification = [
        DeploymentClassification(
            classification="advisory",
            meaning="No execution authority; outputs are informational only.",
            enforcement_notes=[
                "never invoke downstream execution",
                "audit and replay remain enabled",
            ],
        ),
        DeploymentClassification(
            classification="governed",
            meaning="Approval-bound execution with EDON decision binding.",
            enforcement_notes=[
                "execution requires a signed decision token",
                "human approval may be required by risk tier",
            ],
        ),
        DeploymentClassification(
            classification="autonomous",
            meaning="Policy-scoped autonomous execution with strict bounds.",
            enforcement_notes=[
                "still requires EDON decision semantics",
                "may be disallowed in pilot safety mode",
            ],
        ),
    ]

    edge_runtime_boundary = [
        "local policy evaluation is allowed",
        "cloud escalation is optional",
        "same governance semantics apply at the edge",
        "no edge bypass around the decision kernel",
        "edge node identity is required",
    ]

    proof_requirements = [
        "tenant isolation evidence",
        "restore drill evidence",
        "audit chain validation",
        "shadow replay evidence",
        "signoff evidence",
        "dependency audit evidence",
        "execution binding evidence",
    ]

    release_gates = [
        "profile intake complete",
        "topology generated",
        "policy bootstrap generated",
        "deployment package generated",
        "shadow mode exercised",
        "signoff approved",
    ]

    forbidden_variation = [
        "alternate enforcement path outside the gateway",
        "unscoped tenant access",
        "unlogged governance decisions",
        "policy bypass through direct tool execution",
        "execution without a valid decision token",
        "silent fail-open for high-risk actions",
        "shadow result authorizing live execution",
        "customer pack overriding kernel safety invariants",
    ]

    policy_shape = {
        "policy_bundle_present": policy_bundle is not None,
        "policy_layers": {
            "hard_safety": len(getattr(policy_bundle, "hard_safety", [])),
            "operational": len(getattr(policy_bundle, "operational", [])),
            "intent_contracts": len(getattr(policy_bundle, "intent_contracts", [])),
        },
        "deployment_mode": deployment_package.deployment_mode,
        "estimated_setup_h": deployment_package.estimated_setup_h,
        "required_connectors": topology.required_connectors,
    }

    notes = (
        "The invariant architecture is stable across tenants. "
        "Only policy, integrations, workflows, permissions, and scale change per customer. "
        "The Decision Kernel is the causal core and execution must bind to a committed decision record. "
        "Pilot deployments should use constrained pilot mode with explicit governed-action tiers and operational guarantees."
    )

    return RepeatableArchitectureStandard(
        standard_id=standard_id,
        version="v1",
        tenant_id=profile.tenant_id,
        org_name=profile.org_name,
        generated_at=now,
        invariant_layers=invariant_layers,
        customer_variable_packs=customer_variable_packs,
        control_primitives=control_primitives,
        proof_requirements=proof_requirements,
        release_gates=release_gates,
        forbidden_variation=forbidden_variation,
        deployment_modes=sorted(set(topology.deployment_modes)),
        required_connectors=sorted(set(topology.required_connectors)),
        governed_action_matrix=governed_action_matrix,
        pilot_safety_mode=pilot_safety_mode,
        operational_guarantees=operational_guarantees,
        deployment_classification=deployment_classification,
        edge_runtime_boundary=edge_runtime_boundary,
        policy_shape=policy_shape,
        notes=notes,
    )
