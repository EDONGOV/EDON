"""Policy Bootstrap — generate 3-layer initial policy set from a deployment profile.

Layer A: Hard safety (PHI/PCI restrictions, credential access rules, kill-switch conditions)
Layer B: Operational (allowed tools per agent type, rate limits, escalation thresholds)
Layer C: Intent contracts (what each agent is allowed to do in business terms)

Output is a structured policy bundle that can be loaded directly into the policy engine.
Policies are tagged bootstrap=True and are mutable until go-live signoff.
After signoff, hard-safety policies become immutable.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Any


@dataclass
class BootstrapPolicy:
    policy_id: str
    layer: str           # "hard_safety", "operational", "intent_contract"
    agent_system: str    # agent name or "*" for all
    action_pattern: str  # e.g. "email.*", "*.delete", "credential.*"
    decision: str        # "BLOCK", "ESCALATE", "ALLOW", "HUMAN_REQUIRED"
    reason: str
    constraints: dict[str, Any]
    data_classes: list[str]
    immutable_after_signoff: bool
    priority: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PolicyBundle:
    profile_id: str
    tenant_id: str
    generated_at: str
    hard_safety: list[BootstrapPolicy]
    operational: list[BootstrapPolicy]
    intent_contracts: list[BootstrapPolicy]

    @property
    def all_policies(self) -> list[BootstrapPolicy]:
        return self.hard_safety + self.operational + self.intent_contracts

    def as_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "tenant_id": self.tenant_id,
            "generated_at": self.generated_at,
            "hard_safety": [p.as_dict() for p in self.hard_safety],
            "operational": [p.as_dict() for p in self.operational],
            "intent_contracts": [p.as_dict() for p in self.intent_contracts],
            "total_count": len(self.all_policies),
        }


def _pid() -> str:
    return f"bp-{uuid.uuid4().hex[:8]}"


def bootstrap_policies(profile) -> PolicyBundle:
    """Generate 3-layer initial policy set from a GovernanceDeploymentProfile."""
    from .profile import GovernanceDeploymentProfile
    assert isinstance(profile, GovernanceDeploymentProfile)

    now = datetime.now(UTC).isoformat()
    hard_safety: list[BootstrapPolicy] = []
    operational: list[BootstrapPolicy] = []
    intent_contracts: list[BootstrapPolicy] = []

    # ── Layer A: Hard Safety ──────────────────────────────────────────────────

    # PHI: block any external send containing PHI
    if "PHI" in profile.all_data_classes or "HIPAA" in profile.compliance_requirements:
        hard_safety.append(BootstrapPolicy(
            policy_id=_pid(), layer="hard_safety",
            agent_system="*", action_pattern="email.*",
            decision="BLOCK",
            reason="PHI must not leave the system via uncontrolled email",
            constraints={"unless_field": "user_confirmed", "unless_value": True},
            data_classes=["PHI"],
            immutable_after_signoff=True, priority=100,
        ))
        hard_safety.append(BootstrapPolicy(
            policy_id=_pid(), layer="hard_safety",
            agent_system="*", action_pattern="export.*",
            decision="HUMAN_REQUIRED",
            reason="PHI export requires explicit human approval",
            constraints={},
            data_classes=["PHI"],
            immutable_after_signoff=True, priority=100,
        ))

    # PCI: block any agent action that touches card data externally
    if "PCI" in profile.all_data_classes or "PCI_DSS" in profile.compliance_requirements:
        hard_safety.append(BootstrapPolicy(
            policy_id=_pid(), layer="hard_safety",
            agent_system="*", action_pattern="*.send",
            decision="BLOCK",
            reason="PCI data must not be transmitted by autonomous agents",
            constraints={"data_class": "PCI"},
            data_classes=["PCI"],
            immutable_after_signoff=True, priority=100,
        ))

    # Credential access rules
    hard_safety.append(BootstrapPolicy(
        policy_id=_pid(), layer="hard_safety",
        agent_system="*", action_pattern="credential.*",
        decision="ESCALATE",
        reason="Credential operations always require elevated scrutiny",
        constraints={"max_per_session": 3},
        data_classes=["credentials"],
        immutable_after_signoff=True, priority=99,
    ))
    hard_safety.append(BootstrapPolicy(
        policy_id=_pid(), layer="hard_safety",
        agent_system="*", action_pattern="*.secret",
        decision="ESCALATE",
        reason="Secret access is audited and rate-limited",
        constraints={"max_per_hour": 10},
        data_classes=["credentials"],
        immutable_after_signoff=True, priority=99,
    ))

    # Kill-switch conditions
    hard_safety.append(BootstrapPolicy(
        policy_id=_pid(), layer="hard_safety",
        agent_system="*", action_pattern="admin.*",
        decision="BLOCK",
        reason="Admin operations blocked by default; whitelist specific agent IDs to allow",
        constraints={"whitelist_agents": []},
        data_classes=[],
        immutable_after_signoff=True, priority=100,
    ))
    hard_safety.append(BootstrapPolicy(
        policy_id=_pid(), layer="hard_safety",
        agent_system="*", action_pattern="*.delete",
        decision="HUMAN_REQUIRED",
        reason="Destructive operations require human confirmation",
        constraints={},
        data_classes=[],
        immutable_after_signoff=True, priority=98,
    ))
    hard_safety.append(BootstrapPolicy(
        policy_id=_pid(), layer="hard_safety",
        agent_system="*", action_pattern="*.purge",
        decision="BLOCK",
        reason="Bulk purge always blocked; issue via break-glass procedure",
        constraints={},
        data_classes=[],
        immutable_after_signoff=True, priority=100,
    ))

    # External API restrictions: only approved sinks
    if profile.external_sinks:
        hard_safety.append(BootstrapPolicy(
            policy_id=_pid(), layer="hard_safety",
            agent_system="*", action_pattern="api.*",
            decision="ESCALATE",
            reason=f"Only approved external APIs allowed: {', '.join(profile.external_sinks[:5])}",
            constraints={"allowed_destinations": profile.external_sinks},
            data_classes=profile.all_data_classes,
            immutable_after_signoff=True, priority=95,
        ))
    else:
        hard_safety.append(BootstrapPolicy(
            policy_id=_pid(), layer="hard_safety",
            agent_system="*", action_pattern="api.*",
            decision="BLOCK",
            reason="No external API sinks registered; all external calls blocked by default",
            constraints={},
            data_classes=[],
            immutable_after_signoff=True, priority=95,
        ))

    # ── Layer B: Operational ──────────────────────────────────────────────────

    for agent_sys in profile.agent_systems:
        # Allowed tool set
        operational.append(BootstrapPolicy(
            policy_id=_pid(), layer="operational",
            agent_system=agent_sys.name,
            action_pattern="*",
            decision="ALLOW",
            reason=f"Allow registered action set for {agent_sys.name}",
            constraints={"allowed_actions": agent_sys.actions},
            data_classes=agent_sys.data_classes,
            immutable_after_signoff=False, priority=50,
        ))

        # Rate limits by risk tier
        rate_map = {"critical": 20, "high": 50, "medium": 100, "low": 200}
        rate = rate_map.get(profile.risk_tier, 100)
        operational.append(BootstrapPolicy(
            policy_id=_pid(), layer="operational",
            agent_system=agent_sys.name,
            action_pattern="*",
            decision="ESCALATE",
            reason=f"Rate limit: {rate} actions/hour for {profile.risk_tier} tier",
            constraints={"max_actions_per_hour": rate, "window_h": 1},
            data_classes=[],
            immutable_after_signoff=False, priority=60,
        ))

        # Escalation threshold by data class sensitivity
        if any(dc in ("PHI", "PCI", "credentials") for dc in agent_sys.data_classes):
            operational.append(BootstrapPolicy(
                policy_id=_pid(), layer="operational",
                agent_system=agent_sys.name,
                action_pattern="*",
                decision="ESCALATE",
                reason="Sensitive data class: escalate when risk_score > 0.4",
                constraints={"risk_score_threshold": 0.40},
                data_classes=agent_sys.data_classes,
                immutable_after_signoff=False, priority=70,
            ))

    # ── Layer C: Intent Contracts ─────────────────────────────────────────────

    for agent_sys in profile.agent_systems:
        # Describe what this agent is ALLOWED to do in business terms
        business_scope = _infer_business_scope(agent_sys)
        intent_contracts.append(BootstrapPolicy(
            policy_id=_pid(), layer="intent_contract",
            agent_system=agent_sys.name,
            action_pattern="*",
            decision="ALLOW",
            reason=business_scope["description"],
            constraints={
                "permitted_purposes": business_scope["purposes"],
                "prohibited_purposes": business_scope["prohibited"],
                "data_minimization": True,
            },
            data_classes=agent_sys.data_classes,
            immutable_after_signoff=False, priority=40,
        ))

    return PolicyBundle(
        profile_id=profile.profile_id,
        tenant_id=profile.tenant_id,
        generated_at=now,
        hard_safety=hard_safety,
        operational=operational,
        intent_contracts=intent_contracts,
    )


def _infer_business_scope(agent_sys) -> dict:
    """Infer human-readable business scope from action list and data classes."""
    actions = agent_sys.actions
    data_classes = agent_sys.data_classes

    purposes = []
    prohibited = []

    if any("email" in a for a in actions):
        purposes.append("Send email communications to approved recipients")
        prohibited.append("Send bulk email without user confirmation")

    if any("read" in a or "query" in a or "get" in a for a in actions):
        purposes.append("Read and retrieve data for analysis and reporting")

    if any("write" in a or "create" in a or "update" in a for a in actions):
        purposes.append("Create and update records within assigned scope")
        prohibited.append("Modify records outside assigned agent scope")

    if any("delete" in a or "remove" in a for a in actions):
        prohibited.append("Delete data without explicit human confirmation")

    if "PHI" in data_classes:
        purposes.append("Access patient health information for authorized clinical workflows only")
        prohibited.append("Store, export, or transmit PHI to unauthorized parties")

    if "credentials" in data_classes or any("credential" in a or "token" in a for a in actions):
        purposes.append("Access service credentials for authorized integrations")
        prohibited.append("Exfiltrate or share credentials with external systems")

    description = (
        f"{agent_sys.name} is authorized to: {'; '.join(purposes[:3]) or 'perform its configured actions'}. "
        f"Prohibited: {'; '.join(prohibited[:3]) or 'any action outside the configured action set'}."
    )

    return {"description": description, "purposes": purposes, "prohibited": prohibited}
