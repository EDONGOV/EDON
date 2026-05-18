"""Expansion Trigger System — system-driven account expansion signals.

EDON continuously monitors live governance telemetry against the original
GovernanceDeploymentProfile and fires expansion signals when:

  1. New agent types appear that weren't in the profile
  2. New external data sinks are observed
  3. Policy stress points detected (high block/escalation rates)
  4. Repeated human escalations on the same action pattern
  5. Fleet campaign signals touching this tenant's agents

These feed into the proposals system as EXPANSION_PROPOSAL type.
Not sales-driven — system-driven.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ExpansionSignal:
    signal_type: str        # "new_agent", "new_sink", "policy_stress", "repeated_escalation", "fleet_campaign"
    severity: str           # "high", "medium", "low"
    title: str
    description: str
    evidence: dict
    recommended_action: str
    detected_at: str

    def as_dict(self) -> dict:
        return asdict(self)


def check_expansion_signals(tenant_id: str, profile) -> list[ExpansionSignal]:
    """Check live telemetry against the profile and return expansion signals.

    Pulls from impact store, audit log, fleet campaign detector.
    Falls back gracefully when subsystems are unavailable.
    """
    signals: list[ExpansionSignal] = []
    now = datetime.now(UTC).isoformat()

    if profile is None:
        return signals

    registered_agents = {a.name for a in profile.agent_systems}
    registered_sinks  = set(profile.external_sinks)
    registered_actions = set(profile.all_actions)

    # ── 1. New agent types in execution graph ─────────────────────────────────
    try:
        from ..impact.store import get_impact_store
        impact_store = get_impact_store()
        live_agents = {a.get("agent_id", "") for a in impact_store.get_agents(tenant_id=tenant_id)}
        new_agents = live_agents - registered_agents - {""}
        if new_agents:
            signals.append(ExpansionSignal(
                signal_type="new_agent",
                severity="high",
                title=f"{len(new_agents)} unregistered agent(s) detected",
                description=(
                    f"Agents {list(new_agents)[:5]} are executing actions but were not included "
                    "in the original Governance Deployment Profile. Their actions are unclassified "
                    "and operating without intent contracts."
                ),
                evidence={"new_agents": list(new_agents)[:10], "registered_agents": list(registered_agents)},
                recommended_action="Run intake expansion wizard to classify and govern these agents",
                detected_at=now,
            ))
    except Exception as e:
        logger.debug(f"[expansion] impact store unavailable: {e}")

    # ── 2. New external sinks in execution graph ──────────────────────────────
    try:
        from ..impact.store import get_impact_store
        impact_store = get_impact_store()
        live_tools = {t.get("tool_id", "") for t in impact_store.get_tools()}
        # Heuristic: tools with "external", "api", "webhook", "email" in name are sinks
        _sink_prefixes = {"external", "api.", "webhook", "email", "http", "slack", "ftp"}
        new_sinks = {
            t for t in live_tools
            if any(t.lower().startswith(p) for p in _sink_prefixes)
            and t not in registered_sinks
        }
        if new_sinks:
            signals.append(ExpansionSignal(
                signal_type="new_sink",
                severity="high",
                title=f"{len(new_sinks)} unregistered external sink(s) detected",
                description=(
                    f"External destinations {list(new_sinks)[:5]} observed in live traffic "
                    "but not registered in the deployment profile. Data may be flowing to "
                    "unreviewed external services without governance coverage."
                ),
                evidence={"new_sinks": list(new_sinks)[:10], "registered_sinks": list(registered_sinks)},
                recommended_action="Review and register these sinks or add BLOCK policy for unrecognized destinations",
                detected_at=now,
            ))
    except Exception as e:
        logger.debug(f"[expansion] sink check failed: {e}")

    # ── 3. Policy stress: high BLOCK/ESCALATE rates ───────────────────────────
    try:
        from ..impact.store import get_impact_store
        impact_store = get_impact_store()
        failure_states = impact_store.get_failure_states(tenant_id=tenant_id, limit=50)
        critical_fs = [f for f in failure_states if f.get("severity_score", 0) >= 0.5]
        if len(critical_fs) >= 3:
            signals.append(ExpansionSignal(
                signal_type="policy_stress",
                severity="high",
                title=f"{len(critical_fs)} critical failure states detected",
                description=(
                    f"The risk intelligence engine has identified {len(critical_fs)} critical failure states. "
                    "This indicates the current policy set may be insufficient for the observed attack surface. "
                    "Policy hardening or scope expansion is recommended."
                ),
                evidence={
                    "critical_count": len(critical_fs),
                    "top_classes": list({f.get("vulnerability_class") for f in critical_fs[:5]}),
                },
                recommended_action="Review critical failure states in Impact tab and apply remediation policies",
                detected_at=now,
            ))
    except Exception as e:
        logger.debug(f"[expansion] failure state check failed: {e}")

    # ── 4. Fleet campaign signal targeting this tenant ────────────────────────
    try:
        from ..fleet.campaign_detector import get_campaign_detector
        detector = get_campaign_detector()
        stats = detector.fleet_stats(window_h=24.0)
        high_threat = [s for s in stats.get("top_patterns", [])
                       if s.get("threat_level") in ("suspected", "confirmed")
                       and tenant_id in s.get("matched_tenants", [])]
        if high_threat:
            signals.append(ExpansionSignal(
                signal_type="fleet_campaign",
                severity="high",
                title="Fleet-level attack campaign targeting your agents",
                description=(
                    f"{len(high_threat)} cross-tenant attack patterns detected that include "
                    f"your tenant's agents. The same action fingerprints are being executed "
                    "across multiple tenants — coordinated campaign behavior."
                ),
                evidence={"campaign_count": len(high_threat), "patterns": high_threat[:3]},
                recommended_action="Enable active probe mode and review fleet stats in Impact tab",
                detected_at=now,
            ))
    except Exception as e:
        logger.debug(f"[expansion] fleet check failed: {e}")

    # ── 5. New action types not in registered set ─────────────────────────────
    try:
        from ..impact.store import get_impact_store
        impact_store = get_impact_store()
        edges = impact_store.get_edges(tenant_id=tenant_id)
        live_actions = {e.get("action_type", "") for e in edges if e.get("action_type")}
        new_actions = live_actions - registered_actions - {""}
        if len(new_actions) >= 3:
            signals.append(ExpansionSignal(
                signal_type="new_agent",
                severity="medium",
                title=f"{len(new_actions)} action types outside registered scope",
                description=(
                    f"Actions {list(new_actions)[:5]} observed but not in the Governance Deployment Profile. "
                    "These actions have no intent contract and operate under default-deny-unknown policy."
                ),
                evidence={"new_actions": list(new_actions)[:10], "registered_count": len(registered_actions)},
                recommended_action="Update profile to register new action types or confirm they are blocked",
                detected_at=now,
            ))
    except Exception as e:
        logger.debug(f"[expansion] action check failed: {e}")

    if signals:
        logger.info(f"[expansion] {len(signals)} signals for tenant={tenant_id}")

    return signals
