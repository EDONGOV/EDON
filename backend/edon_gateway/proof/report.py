"""EDON Proof Report Assembler.

Assembles the full client-facing risk report payload from:
  - FailureStates (Engine A)
  - LogicalProofs (Level 1 proof engine)
  - RedTeamScenarios (Engine B)
  - ImpactValue (value engine)

The resulting ReportPayload is a single JSON object consumed by the
frontend report renderer (/report/:tenantId).

Three audiences. One payload.
  CFO   → headline numbers, executive summary, close slide
  CISO  → per-finding summaries, severity, remediation
  CTO   → exploit chains, trace IDs, governance gaps

The report renderer decides what to show each audience — the backend
just assembles all available data cleanly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from .logical import generate_logical_proof
from ..impact.value import calculate_value
from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Dollar impact per finding ──────────────────────────────────────────────────

_VULN_DOLLAR_MAP: dict[str, dict] = {
    "data_exfiltration": {
        "label": "Data breach — regulatory fines + notification cost",
        "floor": 250_000,
        "ceiling": 4_500_000,
    },
    "privilege_escalation": {
        "label": "Unauthorized access — incident response + operational damage",
        "floor": 150_000,
        "ceiling": 2_000_000,
    },
    "confused_deputy": {
        "label": "Cross-tenant data exposure — GDPR/HIPAA violation",
        "floor": 300_000,
        "ceiling": 5_000_000,
    },
    "prompt_injection_propagation": {
        "label": "Attacker-controlled tool call — data theft or fraud",
        "floor": 200_000,
        "ceiling": 3_000_000,
    },
    "policy_bypass_via_chaining": {
        "label": "Policy circumvention — complete governance failure",
        "floor": 100_000,
        "ceiling": 2_500_000,
    },
    "unconstrained_tool_fanout": {
        "label": "Uncontrolled agent execution — runaway operations",
        "floor": 75_000,
        "ceiling": 1_500_000,
    },
    "audit_gap": {
        "label": "Invisible operations — breach dwell time + forensic failure",
        "floor": 50_000,
        "ceiling": 1_000_000,
    },
    "kill_switch_bypass": {
        "label": "Kill switch failure — incident containment impossible",
        "floor": 200_000,
        "ceiling": 4_000_000,
    },
    "unconstrained_credential_access": {
        "label": "Shadow credential access — full system compromise path",
        "floor": 300_000,
        "ceiling": 3_500_000,
    },
}

# Plain-English titles for each vulnerability class (no jargon)
_PLAIN_TITLES: dict[str, str] = {
    "data_exfiltration":             "Your AI is sending sensitive data outside the system",
    "privilege_escalation":          "An AI agent can exceed its authorized permissions",
    "confused_deputy":               "An AI agent can access another user's data",
    "prompt_injection_propagation":  "Attackers can hijack your AI agents through user input",
    "policy_bypass_via_chaining":    "Your governance rules can be bypassed in two steps",
    "unconstrained_tool_fanout":     "AI agents can spawn sub-agents with no oversight",
    "audit_gap":                     "Critical AI actions leave no record in your audit log",
    "kill_switch_bypass":            "Your kill switch cannot stop all agent actions in time",
    "unconstrained_credential_access": "AI agents can read credentials they were never meant to access",
}


def _finding_dollar_impact(fs: dict) -> int:
    """Estimate dollar impact for a single finding."""
    vuln = fs.get("vulnerability_class", "")
    sev  = float(fs.get("severity_score", 0.5))
    blast = float(fs.get("blast_radius_score", 0.5))
    likely = float(fs.get("likelihood_score", 0.5))

    bounds = _VULN_DOLLAR_MAP.get(vuln, {"floor": 50_000, "ceiling": 1_000_000})
    floor   = bounds["floor"]
    ceiling = bounds["ceiling"]

    # Scale linearly between floor and ceiling using combined risk signal
    risk_factor = (sev + blast + likely) / 3.0
    impact = int(floor + (ceiling - floor) * risk_factor)

    # Boost for PHI or PCI data — regulatory multiplier
    data_classes = fs.get("data_classes", [])
    if "PHI" in data_classes or "PCI" in data_classes:
        impact = int(impact * 1.4)

    return impact


def _plain_title(fs: dict) -> str:
    vuln = fs.get("vulnerability_class", "")
    return _PLAIN_TITLES.get(vuln, "A governance gap in your AI system")


def _executive_summary(fs: dict, dollar_impact: int) -> str:
    """One sentence a CFO can read in 5 seconds."""
    title = _plain_title(fs)
    verified = fs.get("verified", False)
    confirmed = "confirmed in live traffic" if verified else "identified in your execution graph"
    return (
        f"{title}. This path was {confirmed} and carries an estimated "
        f"${dollar_impact:,.0f} in exposure. No policy currently blocks it."
    )


def _primary_fix(fs: dict) -> str:
    """One actionable remediation sentence."""
    vuln = fs.get("vulnerability_class", "")
    fixes = {
        "data_exfiltration":
            "Add a deidentification gate before any external tool call that carries PHI/PCI/PII data.",
        "privilege_escalation":
            "Add an intent contract that locks the agent's scope to declared operations only.",
        "confused_deputy":
            "Enforce tenant isolation — each agent call must validate the requesting principal before execution.",
        "prompt_injection_propagation":
            "Add an input sanitization node between every user-controlled input field and agent context.",
        "policy_bypass_via_chaining":
            "Link multi-step operation intent — a read-intent lock must propagate to downstream write operations.",
        "unconstrained_tool_fanout":
            "Require independent governance evaluation before each spawned sub-agent receives capabilities.",
        "audit_gap":
            "Add a mandatory audit checkpoint on every governance ALLOW verdict that involves external tools.",
        "kill_switch_bypass":
            "Synchronize kill-switch state to all pre-queued execution paths before confirmation.",
        "unconstrained_credential_access":
            "Add credential scope enforcement — agents can only access secrets declared in their intent contract.",
    }
    return fixes.get(vuln, "Add a governance policy rule to block or constrain this execution path.")


# ── Report data models ─────────────────────────────────────────────────────────

@dataclass
class ReportFinding:
    """One finding in the report — all three audience layers."""
    # Identification
    finding_id: str                   # failure_state_id
    finding_number: int               # 1-indexed display number
    severity: str                     # "critical" | "high" | "medium"
    severity_score: float

    # CFO layer
    plain_title: str                  # no jargon
    executive_summary: str            # 1 sentence
    dollar_impact: int                # estimated $ exposure
    dollar_label: str                 # "Data breach — regulatory fines + notification cost"
    primary_fix: str                  # 1 actionable sentence

    # CISO layer
    vulnerability_class: str
    data_classes: list[str]
    is_external_sink: bool
    verified: bool
    exploitability_window: str

    # CTO layer
    proof_chain: list[dict]           # LogicalProof.steps serialized
    proof_summary: str                # LogicalProof narrative
    rules_violated: list[str]
    entry_point: str
    final_outcome: str
    evidence_trace_ids: list[str]

    # Red team narrative (if available)
    attack_narrative: str = ""
    attacker_type: str = ""
    indicators_of_compromise: list[str] = field(default_factory=list)
    remediation_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReportHeadline:
    """The cover page numbers."""
    total_risk_usd: int
    findings_count: int
    critical_count: int
    high_count: int
    confirmed_exploits: int           # verified=True findings
    data_classes_at_risk: list[str]   # unique across all findings
    engagement_days: int = 7

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReportClose:
    """The last page — the ask."""
    total_risk_usd: int
    edon_annual_est: int              # suggested contract value
    roi_multiple: float               # total_risk / edon_annual
    roi_label: str                    # "For every $1 you spend on EDON, you protect $X"
    next_step: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReportPayload:
    """The full report — everything the renderer needs."""
    report_id: str
    tenant_id: Optional[str]
    generated_at: str
    engagement_label: str             # "7-Day AI Risk Assessment"

    headline: ReportHeadline
    impact: dict                      # ImpactValue.to_dict() equivalent
    findings: list[ReportFinding]
    close: ReportClose

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── Assembler ──────────────────────────────────────────────────────────────────

def assemble_report(
    tenant_id: Optional[str] = None,
    top_n: int = 10,
    include_mitigated: bool = False,
    records_at_risk: Optional[int] = None,
    edon_contract_override: Optional[int] = None,
) -> ReportPayload:
    """Assemble the full report payload from live store data.

    Args:
        tenant_id:              Tenant scope (None = all tenants / demo mode)
        top_n:                  Max findings to include (sorted by severity DESC)
        include_mitigated:      Include already-mitigated findings (shows historical value)
        records_at_risk:        Override default records count for dollar calculations
        edon_contract_override: Override the suggested EDON contract value in the close slide

    Returns:
        ReportPayload — ready for JSON serialization and frontend rendering.
    """
    from ..impact.store import get_impact_store

    store = get_impact_store()

    # Load failure states — unmitigated only unless caller wants historical view
    all_states = store.get_failure_states(tenant_id=tenant_id, limit=500)
    if not include_mitigated:
        states = [s for s in all_states if not s.get("mitigated_at")]
    else:
        states = all_states

    # Sort by severity DESC, cap at top_n
    states = sorted(states, key=lambda s: s.get("severity_score", 0), reverse=True)[:top_n]

    # Load red team scenarios for all findings in one pass
    scenario_map: dict[str, dict] = {}
    for s in states:
        fsid = s.get("failure_state_id", "")
        scenarios = store.get_scenarios(failure_state_id=fsid, limit=1)
        # Take the first valid scenario if available
        valid = [sc for sc in scenarios if sc.get("validation_status") in ("valid", "pending")]
        if valid:
            scenario_map[fsid] = valid[0]

    # Calculate aggregate impact value
    impact_val = calculate_value(
        failure_states=all_states,  # use all states for value calc
        tenant_id=tenant_id,
        records_at_risk=records_at_risk,
    )

    # Build per-finding report objects
    findings: list[ReportFinding] = []
    total_dollar_impact = 0

    for idx, fs in enumerate(states, start=1):
        dollar_impact = _finding_dollar_impact(fs)
        total_dollar_impact += dollar_impact

        # Generate logical proof (fast, deterministic)
        try:
            proof = generate_logical_proof(fs)
            proof_steps = [
                {
                    "step": step.step_number,
                    "actor": step.actor,
                    "action": step.action,
                    "target": step.target,
                    "rule_violated": step.rule_violated,
                    "consequence": step.consequence,
                    "is_critical": step.is_critical,
                }
                for step in proof.steps
            ]
            proof_summary = proof.to_narrative()
            rules_violated = proof.rules_violated
            entry_point = proof.entry_point
            final_outcome = proof.final_outcome
        except Exception as exc:
            logger.warning("[report] proof generation failed for %s: %s", fs.get("failure_state_id"), exc)
            proof_steps = []
            proof_summary = ""
            rules_violated = []
            entry_point = ""
            final_outcome = ""

        # Severity label
        score = float(fs.get("severity_score", 0))
        if score >= 0.75:
            severity = "critical"
        elif score >= 0.50:
            severity = "high"
        else:
            severity = "medium"

        # Red team narrative (if available)
        sc = scenario_map.get(fs.get("failure_state_id", ""), {})
        attack_narrative = sc.get("attack_narrative", "")
        attacker_type    = sc.get("attacker_type", "")
        ioc              = sc.get("indicators_of_compromise", [])
        remediation      = sc.get("remediation_steps", [])

        vuln = fs.get("vulnerability_class", "")
        dollar_bounds = _VULN_DOLLAR_MAP.get(vuln, {"label": "Estimated financial exposure"})

        findings.append(ReportFinding(
            finding_id=fs.get("failure_state_id", f"F-{idx:03d}"),
            finding_number=idx,
            severity=severity,
            severity_score=score,

            plain_title=_plain_title(fs),
            executive_summary=_executive_summary(fs, dollar_impact),
            dollar_impact=dollar_impact,
            dollar_label=dollar_bounds.get("label", "Estimated financial exposure"),
            primary_fix=_primary_fix(fs),

            vulnerability_class=vuln,
            data_classes=fs.get("data_classes", []),
            is_external_sink=bool(fs.get("is_external_sink", False)),
            verified=bool(fs.get("verified", False)),
            exploitability_window=fs.get("exploitability_window", "session"),

            proof_chain=proof_steps,
            proof_summary=proof_summary,
            rules_violated=rules_violated,
            entry_point=entry_point,
            final_outcome=final_outcome,
            evidence_trace_ids=fs.get("evidence_trace_ids", []),

            attack_narrative=attack_narrative,
            attacker_type=attacker_type,
            indicators_of_compromise=ioc if isinstance(ioc, list) else [],
            remediation_steps=remediation if isinstance(remediation, list) else [],
        ))

    # Headline numbers
    critical_count = sum(1 for f in findings if f.severity == "critical")
    high_count     = sum(1 for f in findings if f.severity == "high")
    confirmed      = sum(1 for f in findings if f.verified)
    all_dc         = sorted(set(dc for f in findings for dc in f.data_classes))

    headline = ReportHeadline(
        total_risk_usd=total_dollar_impact,
        findings_count=len(findings),
        critical_count=critical_count,
        high_count=high_count,
        confirmed_exploits=confirmed,
        data_classes_at_risk=all_dc,
    )

    # Close slide — the ask
    # Suggested contract: 10–20% of identified risk, floor $150K, ceiling $5M
    if edon_contract_override:
        contract_est = edon_contract_override
    else:
        contract_est = max(150_000, min(5_000_000, int(total_dollar_impact * 0.15)))

    roi_multiple = round(total_dollar_impact / contract_est, 1) if contract_est > 0 else 0.0
    roi_label = f"For every $1 you spend on EDON, you protect ${roi_multiple:.1f} in exposure"

    close = ReportClose(
        total_risk_usd=total_dollar_impact,
        edon_annual_est=contract_est,
        roi_multiple=roi_multiple,
        roi_label=roi_label,
        next_step=(
            "We can begin continuous monitoring of these paths immediately. "
            "The 7-day engagement findings become the baseline for your first governance policy set."
        ),
    )

    return ReportPayload(
        report_id=f"EDON-{datetime.now(UTC).strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        tenant_id=tenant_id,
        generated_at=datetime.now(UTC).isoformat(),
        engagement_label="7-Day AI Risk Assessment",
        headline=headline,
        impact=asdict(impact_val),
        findings=findings,
        close=close,
    )
