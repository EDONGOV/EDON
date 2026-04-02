"""
Policy Packs - Pre-configured policy modes for Edonbot users.

Users don't want to design policies. They want presets.

Preset modes:
1. Casual User - Ultra-safe everyday use
2. Market Analyst - Financial research focus
3. Ops Commander - Workflow automation with confirmations
4. Founder Mode - Power user with conservative limits
5. Helpdesk - Customer support focus
6. Autonomy Mode - High-risk full co-pilot
"""

from typing import Dict, Any, List, Optional
from .schemas import RiskLevel


class PolicyPack:
    """Pre-configured policy pack."""

    def __init__(
        self,
        name: str,
        description: str,
        scope: Dict[str, List[str]],
        constraints: Dict[str, Any],
        risk_level: RiskLevel,
        approved_by_user: bool = True
    ):
        self.name = name
        self.description = description
        self.scope = scope
        self.constraints = constraints
        self.risk_level = risk_level
        self.approved_by_user = approved_by_user

    def to_intent_dict(self, objective: Optional[str] = None) -> Dict[str, Any]:
        """Convert to intent contract dictionary."""
        return {
            "objective": objective or self.description,
            "scope": self.scope,
            "constraints": self.constraints,
            "risk_level": self.risk_level.value,
            "approved_by_user": self.approved_by_user
        }


# Mode 1: Casual User (Ultra-Safe / Everyday Use)
CASUAL_USER = PolicyPack(
    name="casual_user",
    description="Casual User - Ultra-safe everyday use",
    scope={
        "clawdbot": ["invoke"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "message",
            "web_read",
            "web_summarize",
            "web_draft",
            "web_search"
        ],
        "blocked_clawdbot_tools": [
            "web_send",
            "web_delete",
            "web_execute",
            "shell_execute",
            "file_write",
            "mass_outbound",
            "credential_operations"
        ],
        "confirm_irreversible": True,
        "max_recipients": 1,
        "no_external_sharing": True
    },
    risk_level=RiskLevel.LOW,
    approved_by_user=True
)


# Mode 2: Market Analyst (Financial + Research Focus)
MARKET_ANALYST = PolicyPack(
    name="market_analyst",
    description="Market Analyst - Financial research focus",
    scope={
        "clawdbot": ["invoke"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "web_read",
            "web_search",
            "web_summarize",
            "web_draft"
        ],
        "blocked_clawdbot_tools": [
            "message",
            "web_send",
            "web_execute",
            "shell_execute",
            "file_write",
            "mass_outbound",
            "credential_operations"
        ],
        "confirm_irreversible": True,
        "max_recipients": 1,
        "no_external_sharing": True
    },
    risk_level=RiskLevel.LOW,
    approved_by_user=True
)


# Mode 3: Ops Commander (Productivity / Workflow Focus)
OPS_COMMANDER = PolicyPack(
    name="ops_commander",
    description="Ops Commander - Workflow automation with confirmations",
    scope={
        "clawdbot": ["invoke"],
        "email": ["draft", "read"],
        "calendar": ["view", "propose"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "message",
            "web_read",
            "web_search",
            "web_summarize",
            "web_draft",
            "calendar_view",
            "calendar_create"
        ],
        "confirm_on": [
            "web_send",
            "calendar_create",
            "file_write",
            "message"
        ],
        "blocked_clawdbot_tools": [
            "web_execute",
            "shell_execute",
            "mass_outbound",
            "credential_operations"
        ],
        "max_recipients": 10,
        "work_hours_only": True,
        "no_external_sharing": True
    },
    risk_level=RiskLevel.MEDIUM,
    approved_by_user=True
)


# Mode 4: Founder Mode (Power User / Flexible Ops)
FOUNDER_MODE = PolicyPack(
    name="founder_mode",
    description="Founder Mode - Power user with conservative limits",
    scope={
        "clawdbot": ["invoke"],
        "email": ["draft", "read"],
        "file": ["read"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "message",
            "web_read",
            "web_search",
            "web_summarize",
            "web_draft",
            "sessions_list"
        ],
        "confirm_on": [
            "web_send",
            "file_write",
            "message"
        ],
        "blocked_clawdbot_tools": [
            "web_execute",
            "shell_execute",
            "mass_outbound",
            "credential_operations"
        ],
        "max_recipients": 5,
        "no_external_sharing": True
    },
    risk_level=RiskLevel.MEDIUM,
    approved_by_user=True
)


# Mode 5: Helpdesk (Customer Support Focus)
HELPDESK = PolicyPack(
    name="helpdesk",
    description="Helpdesk - Customer support focus",
    scope={
        "clawdbot": ["invoke"],
        "email": ["draft", "read"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "message",
            "web_read",
            "web_search",
            "web_summarize",
            "web_draft",
            "sessions_list"
        ],
        "confirm_on": [
            "web_send",
            "message"
        ],
        "blocked_clawdbot_tools": [
            "web_execute",
            "shell_execute",
            "file_write",
            "mass_outbound",
            "credential_operations"
        ],
        "max_recipients": 3,
        "no_external_sharing": True
    },
    risk_level=RiskLevel.LOW,
    approved_by_user=True
)


# Mode 6: Autonomy Mode (High-Risk / Full Co-Pilot)
AUTONOMY_MODE = PolicyPack(
    name="autonomy_mode",
    description="Autonomy Mode - High-risk full co-pilot",
    scope={
        "clawdbot": ["invoke"],
        "email": ["draft", "send", "read"],
        "file": ["read", "write"]
    },
    constraints={
        "allowed_clawdbot_tools": [
            "message",
            "web_read",
            "web_search",
            "web_summarize",
            "web_draft",
            "web_send",
            "sessions_list",
            "calendar_view",
            "calendar_create"
        ],
        "confirm_on": [
            "web_send",
            "file_write",
            "message"
        ],
        "blocked_clawdbot_tools": [
            "shell_execute",
            "mass_outbound",
            "credential_operations"
        ],
        "max_recipients": 50,
        "audit_level": "detailed",
        "work_hours_only": False
    },
    risk_level=RiskLevel.HIGH,
    approved_by_user=True
)


HOSPITAL = PolicyPack(
    name="hospital",
    description="HIPAA-compliant clinical policy pack for hospital AI deployments. Enforces PHI access controls, medication safety, clinical role enforcement, and HIPAA audit requirements.",
    risk_level=RiskLevel.CRITICAL,
    approved_by_user=True,
    scope={
        "allowed_tools": ["read_file", "write_file", "http_request", "database_query", "agent_invoke"],
        "allowed_operations": ["read", "write", "execute", "query"],
    },
    constraints={
        # Rule 1: PHI Access Control
        "require_clinical_purpose": True,
        "phi_access_blocked_without_purpose": True,
        # Rule 2: Minimum Necessary
        "max_records_per_action": 100,
        "bulk_export_requires_admin_approval": True,
        # Rule 3: Clinical Role Enforcement
        "allowed_clinical_roles": ["physician", "nurse", "admin", "radiologist", "pharmacist"],
        "enforce_clinical_role_context": True,
        # Rule 4: PHI Audit Escalation
        "phi_fields": ["patient_id", "mrn", "dob", "ssn", "npi", "phi"],
        "phi_anomaly_escalate_threshold": 40,
        # Rule 5: Medication Safety
        "medication_ops": ["prescribe", "dispense", "order_medication", "change_dosage", "cancel_prescription"],
        "medication_ops_always_escalate": True,
        # Rule 6: De-identification for External Transmission
        "external_transmission_requires_deidentification": True,
        "deidentification_required_ops": ["export", "transmit", "send", "share"],
        # Rule 7: Break-glass Emergency Override
        "allow_emergency_override": True,
        "emergency_override_always_escalate": True,
        "emergency_override_anomaly_boost": 40,
        # Rule 8: Off-hours Alert
        "off_hours_start_utc": 22,
        "off_hours_end_utc": 6,
        "off_hours_anomaly_boost": 20,
        # Rule 9: No Mass Delete
        "max_delete_records": 1,
        "mass_delete_blocked": True,
        # Rule 10: Breach Detection
        "patient_record_access_limit_per_hour": 50,
        "breach_detection_auto_escalate": True,
        "breach_detection_reason": "RATE_LIMIT_EXCEEDED",
    },
)


# Registry of all policy packs
POLICY_PACKS = {
    "casual_user": CASUAL_USER,
    "market_analyst": MARKET_ANALYST,
    "ops_commander": OPS_COMMANDER,
    "founder_mode": FOUNDER_MODE,
    "helpdesk": HELPDESK,
    "autonomy_mode": AUTONOMY_MODE,
    # Backwards-compat alias used by regression tests / older clients
    "clawdbot_safe": AUTONOMY_MODE,
    # Console/API aliases (docs and UI use these names)
    "personal_safe": CASUAL_USER,
    "work_safe": OPS_COMMANDER,
    "research_mode": MARKET_ANALYST,
    "ops_admin": OPS_COMMANDER,
    # Additional slugs the console may send (match by intent)
    "casual": CASUAL_USER,
    "market": MARKET_ANALYST,
    "ops": OPS_COMMANDER,
    "founder": FOUNDER_MODE,
    "help_desk": HELPDESK,
    "autonomy": AUTONOMY_MODE,
    # Hospital / healthcare HIPAA pack
    "hospital": HOSPITAL,
    "clinical": HOSPITAL,
    "hipaa": HOSPITAL,
    "healthcare": HOSPITAL,
}


def get_policy_pack(name: str) -> PolicyPack:
    """Get a policy pack by name."""
    if name not in POLICY_PACKS:
        raise ValueError(
            f"Unknown policy pack: {name}. "
            f"Available: {list(POLICY_PACKS.keys())}"
        )
    return POLICY_PACKS[name]


def list_policy_packs() -> List[Dict[str, Any]]:
    """List all available policy packs (unique by pack name; aliases not duplicated)."""
    seen_names: set = set()
    result: List[Dict[str, Any]] = []
    for pack in POLICY_PACKS.values():
        if pack.name in seen_names:
            continue
        seen_names.add(pack.name)
        result.append({
            "name": pack.name,
            "description": pack.description,
            "risk_level": pack.risk_level.value,
            "scope_summary": {
                tool: len(ops) for tool, ops in pack.scope.items()
            },
            "constraints_summary": {
                "allowed_tools": len(pack.constraints.get("allowed_clawdbot_tools", [])),
                "blocked_tools": len(pack.constraints.get("blocked_clawdbot_tools", [])),
                "confirm_required": "confirm_on" in pack.constraints
            }
        })
    return result


def apply_policy_pack(pack_name: str, objective: Optional[str] = None) -> Dict[str, Any]:
    """Apply a policy pack and return intent contract dictionary."""
    pack = get_policy_pack(pack_name)
    return pack.to_intent_dict(objective)
