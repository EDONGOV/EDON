"""EDON Impact Value Engine.

Converts failure states, coverage data, and scan history into quantifiable
economic value — the "$ saved" layer that closes the loop between security
findings and business outcomes.

Industry benchmark sources:
  - IBM Cost of a Data Breach Report 2023: $165 / record, $4.45M average total
  - HHS/OCR HIPAA penalty tiers: $100–$50k per violation category
  - Gartner IT downtime cost: $5,600 / hour
  - Ponemon: mean time to identify breach 204 days (without tooling)
  - SOC 2 re-audit cost: $30k–$100k (average $50k)
  - GDPR maximum: 4% global revenue or €20M

Configurable via environment variables so enterprises can supply their own numbers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional


# ── Industry benchmarks (overridable per deployment) ──────────────────────────

_BREACH_COST_PER_RECORD   = float(os.getenv("EDON_BREACH_COST_PER_RECORD",   "165"))
_HIPAA_FINE_PER_VIOLATION = float(os.getenv("EDON_HIPAA_FINE_PER_VIOLATION", "50000"))
_DOWNTIME_COST_PER_HOUR   = float(os.getenv("EDON_DOWNTIME_COST_PER_HOUR",   "5600"))
_SOC2_REAUDIT_COST        = float(os.getenv("EDON_SOC2_REAUDIT_COST",        "50000"))
_GDPR_FINE_BASELINE       = float(os.getenv("EDON_GDPR_FINE_BASELINE",       "20000"))
_RECORDS_AT_RISK_DEFAULT  = int(os.getenv("EDON_RECORDS_AT_RISK_DEFAULT",    "100000"))
_ANNUAL_REVENUE           = float(os.getenv("EDON_ANNUAL_REVENUE",           "0"))  # 0 = skip GDPR % calc


@dataclass
class ImpactValue:
    """Quantified economic value produced by EDON for a given tenant snapshot."""

    # ── $ prevented ───────────────────────────────────────────────────────────
    risk_prevented_usd:       float = 0.0   # total expected loss prevented
    breach_cost_prevented:    float = 0.0   # data breach cost (records × cost_per_record)
    compliance_fine_prevented: float = 0.0  # regulatory fine exposure blocked
    downtime_prevented_usd:   float = 0.0   # operational downtime value preserved

    # ── Operational metrics ────────────────────────────────────────────────────
    uptime_preserved_hours:   float = 0.0   # hours of downtime avoided
    incidents_avoided:        int   = 0     # count of confirmed incidents blocked
    mitigated_this_cycle:     int   = 0     # states moved to mitigated in last cycle

    # ── Risk surface metrics ───────────────────────────────────────────────────
    risk_eliminated_pct:      float = 0.0   # % of original risk surface eliminated
    compliance_exposure_usd:  float = 0.0   # remaining unmitigated fine exposure
    records_protected:        int   = 0     # estimated records no longer at risk

    # ── System improvement ────────────────────────────────────────────────────
    coverage_pct:             float = 0.0   # current coverage %
    coverage_delta_pct:       float = 0.0   # coverage improvement vs last snapshot
    mean_severity_score:      float = 0.0   # average severity across open findings
    open_critical:            int   = 0
    open_high:                int   = 0

    # ── Meta ──────────────────────────────────────────────────────────────────
    tenant_id:                Optional[str] = None
    calculated_at:            str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    config_used:              dict = field(default_factory=dict)


def calculate_value(
    failure_states: list[dict],
    coverage: Optional[dict] = None,
    tenant_id: Optional[str] = None,
    records_at_risk: Optional[int] = None,
) -> ImpactValue:
    """
    Produce an ImpactValue snapshot from live failure state data.

    Args:
        failure_states:  List of failure state dicts from ImpactStore.get_failure_states()
        coverage:        Latest coverage snapshot dict (optional)
        tenant_id:       Tenant scope
        records_at_risk: Override default records count for this tenant

    Returns:
        ImpactValue dataclass
    """
    _records = records_at_risk or _RECORDS_AT_RISK_DEFAULT
    v = ImpactValue(tenant_id=tenant_id)

    v.config_used = {
        "breach_cost_per_record":   _BREACH_COST_PER_RECORD,
        "hipaa_fine_per_violation": _HIPAA_FINE_PER_VIOLATION,
        "downtime_cost_per_hour":   _DOWNTIME_COST_PER_HOUR,
        "soc2_reaudit_cost":        _SOC2_REAUDIT_COST,
        "records_at_risk":          _records,
    }

    if not failure_states:
        return v

    # Partition into open (unmitigated) vs mitigated
    mitigated   = [s for s in failure_states if s.get("mitigated_at")]
    open_states = [s for s in failure_states if not s.get("mitigated_at")]
    verified    = [s for s in open_states if s.get("verified")]

    v.mitigated_this_cycle = len(mitigated)
    v.incidents_avoided    = len([s for s in mitigated if s.get("verified")])

    # Severity buckets for open states
    critical = [s for s in open_states if s.get("severity_score", 0) >= 0.75]
    high     = [s for s in open_states if 0.50 <= s.get("severity_score", 0) < 0.75]
    v.open_critical = len(critical)
    v.open_high     = len(high)

    # Mean severity across open verified states
    if verified:
        v.mean_severity_score = round(
            sum(s.get("severity_score", 0) for s in verified) / len(verified), 3
        )

    # ── Breach cost (prevented) ────────────────────────────────────────────────
    # For each mitigated verified state: fraction of records protected × cost/record
    # We estimate records_at_risk_for_state = records × blast_radius × likelihood
    breach_prevented = 0.0
    records_protected = 0
    for s in mitigated:
        if not s.get("verified"):
            continue
        blast   = s.get("blast_radius_score", 0.5)
        likely  = s.get("likelihood_score", 0.5)
        records = int(_records * blast * likely)
        records_protected += records
        breach_prevented  += records * _BREACH_COST_PER_RECORD

    v.records_protected     = records_protected
    v.breach_cost_prevented = round(breach_prevented, 2)

    # ── Compliance fine exposure (remaining) ───────────────────────────────────
    # Each unmitigated finding with data_exfiltration / audit_gap / privilege_escalation
    # carries regulatory fine potential
    _COMPLIANCE_VULN_CLASSES = {
        "data_exfiltration",
        "audit_gap",
        "unconstrained_credential_access",
    }
    remaining_fine = 0.0
    prevented_fine = 0.0

    for s in failure_states:
        is_compliance_risk = s.get("vulnerability_class", "") in _COMPLIANCE_VULN_CLASSES
        if not is_compliance_risk:
            continue
        severity = s.get("severity_score", 0)
        fine = _HIPAA_FINE_PER_VIOLATION * severity

        # Add GDPR exposure if revenue configured
        if _ANNUAL_REVENUE > 0:
            gdpr_fine = min(_ANNUAL_REVENUE * 0.04, 20_000_000) * severity * 0.25
            fine = max(fine, gdpr_fine)

        # SOC 2 re-audit for audit gaps
        if s.get("vulnerability_class") == "audit_gap":
            fine = max(fine, _SOC2_REAUDIT_COST * severity)

        if s.get("mitigated_at"):
            prevented_fine += fine
        else:
            remaining_fine += fine

    v.compliance_fine_prevented = round(prevented_fine, 2)
    v.compliance_exposure_usd   = round(remaining_fine, 2)

    # ── Downtime (operational impact) ─────────────────────────────────────────
    # Confirmed + mitigated privilege_escalation / kill_switch_bypass scenarios
    # would have caused ~4-8h downtime each
    _DOWNTIME_VULN_CLASSES = {"privilege_escalation", "kill_switch_bypass", "confused_deputy"}
    downtime_hours = 0.0
    for s in mitigated:
        if s.get("vulnerability_class", "") in _DOWNTIME_VULN_CLASSES and s.get("verified"):
            # blast radius drives how many systems affected → downtime multiplier
            blast = s.get("blast_radius_score", 0.5)
            downtime_hours += 4.0 * blast

    v.uptime_preserved_hours  = round(downtime_hours, 1)
    v.downtime_prevented_usd  = round(downtime_hours * _DOWNTIME_COST_PER_HOUR, 2)

    # ── Total risk prevented ───────────────────────────────────────────────────
    v.risk_prevented_usd = round(
        v.breach_cost_prevented + v.compliance_fine_prevented + v.downtime_prevented_usd, 2
    )

    # ── Risk elimination % ─────────────────────────────────────────────────────
    if failure_states:
        total_severity  = sum(s.get("severity_score", 0) for s in failure_states)
        mitig_severity  = sum(s.get("severity_score", 0) for s in mitigated)
        v.risk_eliminated_pct = round(
            (mitig_severity / total_severity * 100) if total_severity > 0 else 0, 1
        )

    # ── Coverage metrics ───────────────────────────────────────────────────────
    if coverage:
        v.coverage_pct = round(float(coverage.get("coverage_pct", 0)), 1)
        v.coverage_delta_pct = round(float(coverage.get("coverage_delta_pct", 0)), 1)

    return v
