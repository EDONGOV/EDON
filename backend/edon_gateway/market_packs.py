"""Versioned market packs for EDON deployments.

Market packs are vertical overlays on top of the invariant governance core.
They are tenant-pinned and versioned so clients can stay on a known pack while
newer pack versions are tested in shadow mode.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


MARKET_PACK_STATUS_TIERS = {"supported", "pilot", "experimental", "blocked"}
MARKET_PACK_CERTIFICATION_STATUSES = {"certified", "pilot", "experimental", "blocked"}


@dataclass(frozen=True)
class MarketPack:
    slug: str
    title: str
    market: str
    version: str
    status_tier: str
    certification_status: str
    policy_pack: str
    description: str
    default_compliance_requirements: list[str]
    default_data_classes: list[str]
    connector_categories: list[str]
    required_controls: list[str]
    governed_actions: list[dict[str, Any]]
    upgrade_policy: dict[str, Any]
    evidence_refs: list[str]
    live_change_guidance: list[str]
    deployment_modes: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


HEALTHCARE_MARKET_PACK = MarketPack(
    slug="healthcare",
    title="Healthcare / Hospital",
    market="healthcare",
    version="2026.05",
    status_tier="supported",
    certification_status="certified",
    policy_pack="hospital",
    description=(
        "Healthcare market pack for EDON hospital deployments. "
        "Pins PHI-safe defaults, hospital-approved connectors, and break-glass handling."
    ),
    default_compliance_requirements=["HIPAA", "HITRUST", "SOC2"],
    default_data_classes=["PHI", "PII", "internal", "safety-critical"],
    connector_categories=[
        "ehr_emr",
        "identity_access_management",
        "clinical_communications",
        "scheduling_staffing",
        "revenue_cycle_billing",
        "pacs_imaging",
        "laboratory_information_systems",
        "security_siem",
        "messaging_workflow",
        "llm_providers",
    ],
    required_controls=[
        "Tenant-scoped identity and audit chain",
        "DecisionRecord binding for every governed write",
        "SSO-only enterprise access with step-up MFA",
        "Break-glass review and signoff",
        "PHI export policy enforcement",
        "Rollback limits documented per governed action",
    ],
    governed_actions=[
        {
            "action": "draft_patient_note",
            "risk": "medium",
            "approval": "optional",
            "rollback": "full",
            "logged": True,
            "data_classes": ["PHI"],
        },
        {
            "action": "record_writeback",
            "risk": "high",
            "approval": "required",
            "rollback": "partial",
            "logged": True,
            "data_classes": ["PHI", "safety-critical"],
        },
        {
            "action": "medication_update",
            "risk": "critical",
            "approval": "required",
            "rollback": "limited",
            "logged": True,
            "data_classes": ["PHI", "safety-critical"],
        },
        {
            "action": "clinical_escalation_notify",
            "risk": "medium",
            "approval": "required",
            "rollback": "full",
            "logged": True,
            "data_classes": ["PHI", "internal"],
        },
        {
            "action": "claim_submission",
            "risk": "high",
            "approval": "required",
            "rollback": "partial",
            "logged": True,
            "data_classes": ["PHI", "financial"],
        },
    ],
    upgrade_policy={
        "tenant_pinned": True,
        "promotion_path": "pilot -> shadow -> signoff -> production",
        "rollback_path": "revert the tenant to the previous pack version",
        "no_in_place_mutation": True,
        "shadow_validation_required": True,
    },
    evidence_refs=[
        "docs/evidence/verification-ledger.md",
        "docs/evidence/tenant-isolation.md",
        "docs/evidence/audit-chain.md",
        "docs/evidence/restore-drill.md",
        "docs/evidence/production-advisory-review.md",
    ],
    live_change_guidance=[
        "Pin the tenant to one pack version at a time.",
        "Test upgrades in shadow mode before promotion.",
        "Keep the prior pack version available for rollback.",
        "Do not mutate a live tenant pack in place.",
    ],
    deployment_modes=["pilot", "production"],
)


_MARKET_PACKS: List[MarketPack] = [
    HEALTHCARE_MARKET_PACK,
]

_PACK_BY_SLUG: Dict[str, MarketPack] = {
    "healthcare": HEALTHCARE_MARKET_PACK,
    "hospital": HEALTHCARE_MARKET_PACK,
    "clinical": HEALTHCARE_MARKET_PACK,
    "hipaa": HEALTHCARE_MARKET_PACK,
}


def normalize_market_pack_slug(slug: str | None) -> str:
    slug = (slug or "healthcare").strip().lower()
    if not slug:
        slug = "healthcare"
    if slug not in _PACK_BY_SLUG:
        raise ValueError(
            f"Unknown market pack '{slug}'. Available: "
            f"{sorted({pack.slug for pack in _MARKET_PACKS})}"
        )
    return _PACK_BY_SLUG[slug].slug


def get_market_pack(slug: str | None) -> dict:
    canonical_slug = normalize_market_pack_slug(slug)
    pack = deepcopy(_PACK_BY_SLUG[canonical_slug])
    decorated = pack.as_dict()
    decorated["enterprise_supported"] = (
        decorated["status_tier"] == "supported"
        and decorated["certification_status"] == "certified"
    )
    decorated["tenant_pinned"] = True
    return decorated


def list_market_packs() -> list[dict]:
    return [get_market_pack(pack.slug) for pack in _MARKET_PACKS]


def get_market_pack_defaults(slug: str | None) -> dict[str, Any]:
    pack = get_market_pack(slug)
    return {
        "market_pack": pack["slug"],
        "market_pack_version": pack["version"],
        "compliance_requirements": list(pack["default_compliance_requirements"]),
        "data_classes": list(pack["default_data_classes"]),
        "connector_categories": list(pack["connector_categories"]),
        "required_controls": list(pack["required_controls"]),
        "governed_actions": list(pack["governed_actions"]),
        "upgrade_policy": dict(pack["upgrade_policy"]),
        "evidence_refs": list(pack["evidence_refs"]),
    }

