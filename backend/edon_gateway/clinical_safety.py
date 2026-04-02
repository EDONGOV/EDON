"""Clinical Safety Mode — regulation-mapped policy rule definitions.

Each entry in CLINICAL_SAFETY_RULES maps one regulatory requirement to a concrete
policy rule that EDON enforces at action time. When Clinical Safety Mode is activated
for a tenant, all rules are seeded into policy_rules marked protected=1 and
regulation=<code>.

Protected rules cannot be silently disabled — any mutation requires admin role +
a written justification that is appended to the policy change audit log.

REQUIRED_RULES_BY_REGULATION defines which rule_codes must be present AND enabled
for a regulation to be considered compliant. Used by GET /compliance/health.
"""

from typing import List, Dict, Any

# ── Rule definitions ───────────────────────────────────────────────────────────

CLINICAL_SAFETY_RULES: List[Dict[str, Any]] = [

    # ── HIPAA (45 CFR §164) ────────────────────────────────────────────────────
    {
        "rule_code": "HIPAA-001",
        "regulation": "HIPAA",
        "name": "[HIPAA] Escalate bulk patient data export",
        "description": (
            "Any bulk export of patient records requires human review before execution. "
            "Prevents mass PHI disclosure. 45 CFR §164.312(b) — Audit controls."
        ),
        "condition_tool": "scanner",
        "condition_op": "export",
        "condition_risk_level": None,
        "condition_tags": ["phi", "bulk_export"],
        "action": "ESCALATE",
        "priority": 900,
    },
    {
        "rule_code": "HIPAA-002",
        "regulation": "HIPAA",
        "name": "[HIPAA] Block high-risk file export containing PHI",
        "description": (
            "Block high-risk file export operations that may transmit PHI to "
            "unauthorized destinations. 45 CFR §164.312(a)(2)(i) — Unique user identification."
        ),
        "condition_tool": "file",
        "condition_op": "export",
        "condition_risk_level": "high",
        "condition_tags": None,
        "action": "BLOCK",
        "priority": 900,
    },
    {
        "rule_code": "HIPAA-003",
        "regulation": "HIPAA",
        "name": "[HIPAA] Escalate high-risk email that may transmit PHI",
        "description": (
            "High-risk email actions that could transmit PHI externally require "
            "clinical review. 45 CFR §164.312(e)(1) — Transmission security."
        ),
        "condition_tool": "email",
        "condition_op": None,
        "condition_risk_level": "high",
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 850,
    },

    # ── HITECH (42 U.S.C. §17931) ─────────────────────────────────────────────
    {
        "rule_code": "HITECH-001",
        "regulation": "HITECH",
        "name": "[HITECH] Block critical-risk actions to prevent reportable breaches",
        "description": (
            "Block any critical-risk action across all tools — critical risk indicates "
            "high probability of a reportable breach event. HITECH §13402 — "
            "Notification in case of breach."
        ),
        "condition_tool": None,
        "condition_op": None,
        "condition_risk_level": "critical",
        "condition_tags": None,
        "action": "BLOCK",
        "priority": 950,
    },
    {
        "rule_code": "HITECH-002",
        "regulation": "HITECH",
        "name": "[HITECH] Escalate shell commands with critical risk",
        "description": (
            "Shell execution at critical risk level could indicate a system compromise "
            "or data exfiltration attempt. HITECH §13401 — Application of security "
            "provisions and penalties."
        ),
        "condition_tool": "shell",
        "condition_op": None,
        "condition_risk_level": "high",
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 900,
    },

    # ── FDA SaMD (21 CFR Part 820 / Part 880) ─────────────────────────────────
    {
        "rule_code": "FDA-SAMD-001",
        "regulation": "FDA_SAMD",
        "name": "[FDA SaMD] Escalate medical device configuration changes",
        "description": (
            "Device configuration changes alter clinical software behavior and require "
            "review under design control procedures. "
            "FDA 21 CFR §820.30 — Design controls."
        ),
        "condition_tool": "robot",
        "condition_op": "configure",
        "condition_risk_level": None,
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 920,
    },
    {
        "rule_code": "FDA-SAMD-002",
        "regulation": "FDA_SAMD",
        "name": "[FDA SaMD] Escalate critical-risk autonomous robot actions",
        "description": (
            "Critical-risk autonomous actions on medical devices require attending "
            "physician confirmation before execution. "
            "FDA 21 CFR §880.3860 — Robotic surgical system guidance."
        ),
        "condition_tool": "robot",
        "condition_op": None,
        "condition_risk_level": "critical",
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 920,
    },
    {
        "rule_code": "FDA-SAMD-003",
        "regulation": "FDA_SAMD",
        "name": "[FDA SaMD] Block unauthorized firmware updates to medical devices",
        "description": (
            "Firmware updates to medical devices must follow validated change control "
            "procedures. Unauthorized updates blocked. "
            "FDA 21 CFR §820.70 — Production and process controls."
        ),
        "condition_tool": "robot",
        "condition_op": "firmware_update",
        "condition_risk_level": None,
        "condition_tags": None,
        "action": "BLOCK",
        "priority": 950,
    },

    # ── DEA (21 CFR §1306) ─────────────────────────────────────────────────────
    {
        "rule_code": "DEA-001",
        "regulation": "DEA",
        "name": "[DEA] Escalate controlled substance dispensing",
        "description": (
            "All AI-initiated controlled substance dispensing requires pharmacist "
            "verification before execution. "
            "21 CFR §1306.11 — Requirement of prescription."
        ),
        "condition_tool": "robot",
        "condition_op": "dispense",
        "condition_risk_level": None,
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 980,
    },
    {
        "rule_code": "DEA-002",
        "regulation": "DEA",
        "name": "[DEA] Block high-risk medication administration without authorization",
        "description": (
            "High-risk medication administration by AI agents is blocked without "
            "explicit clinical authorization in context. "
            "21 CFR §1306.21 — Requirement of order to dispense."
        ),
        "condition_tool": "robot",
        "condition_op": "administer",
        "condition_risk_level": "high",
        "condition_tags": None,
        "action": "BLOCK",
        "priority": 980,
    },

    # ── Joint Commission (NPSG / CAMH) ─────────────────────────────────────────
    {
        "rule_code": "JCAHO-001",
        "regulation": "JOINT_COMMISSION",
        "name": "[Joint Commission] Escalate high-risk clinical robot actions",
        "description": (
            "High-risk clinical procedures performed by AI agents require attending "
            "physician confirmation. "
            "NPSG.01.01.01 — Identify patients correctly; NPSG.07.01.01 — Prevent infection."
        ),
        "condition_tool": "robot",
        "condition_op": None,
        "condition_risk_level": "high",
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 870,
    },
    {
        "rule_code": "JCAHO-002",
        "regulation": "JOINT_COMMISSION",
        "name": "[Joint Commission] Escalate drone/vehicle movement in clinical areas",
        "description": (
            "Autonomous vehicle and drone movement in clinical areas requires "
            "safety officer confirmation. "
            "CAMH EC.02.01.01 — Environment of care safety."
        ),
        "condition_tool": "vehicle",
        "condition_op": None,
        "condition_risk_level": "medium",
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 860,
    },

    # ── ISO 13485:2016 ─────────────────────────────────────────────────────────
    {
        "rule_code": "ISO13485-001",
        "regulation": "ISO_13485",
        "name": "[ISO 13485] Escalate medical device maintenance operations",
        "description": (
            "Device maintenance actions must be reviewed under the quality management "
            "system before execution. "
            "ISO 13485:2016 §7.5.1 — Control of production and service provision."
        ),
        "condition_tool": "robot",
        "condition_op": "maintenance",
        "condition_risk_level": None,
        "condition_tags": None,
        "action": "ESCALATE",
        "priority": 830,
    },
    {
        "rule_code": "ISO13485-002",
        "regulation": "ISO_13485",
        "name": "[ISO 13485] Block unauthorized calibration changes",
        "description": (
            "Calibration changes to medical devices require documented QMS approval. "
            "ISO 13485:2016 §7.6 — Control of monitoring and measuring equipment."
        ),
        "condition_tool": "robot",
        "condition_op": "calibrate",
        "condition_risk_level": None,
        "condition_tags": None,
        "action": "BLOCK",
        "priority": 900,
    },

    # ── 45 CFR 46 (Common Rule — Research Subject Protection) ──────────────────
    {
        "rule_code": "CFR46-001",
        "regulation": "CFR_46",
        "name": "[45 CFR 46] Escalate research subject data access",
        "description": (
            "Access to research subject data requires IRB protocol verification "
            "before AI agents may proceed. "
            "45 CFR §46.111 — Criteria for IRB approval of research."
        ),
        "condition_tool": "scanner",
        "condition_op": "research_scan",
        "condition_risk_level": None,
        "condition_tags": ["research"],
        "action": "ESCALATE",
        "priority": 920,
    },
    {
        "rule_code": "CFR46-002",
        "regulation": "CFR_46",
        "name": "[45 CFR 46] Block research data export without verified consent",
        "description": (
            "Export of research subject data is blocked without verified informed "
            "consent record in context. "
            "45 CFR §46.116 — General requirements for informed consent."
        ),
        "condition_tool": "file",
        "condition_op": "research_export",
        "condition_risk_level": None,
        "condition_tags": ["research"],
        "action": "BLOCK",
        "priority": 950,
    },
]


# ── Required rule codes per regulation (used by compliance health check) ───────

REQUIRED_RULES_BY_REGULATION: Dict[str, List[str]] = {
    "HIPAA":            ["HIPAA-001", "HIPAA-002", "HIPAA-003"],
    "HITECH":           ["HITECH-001", "HITECH-002"],
    "FDA_SAMD":         ["FDA-SAMD-001", "FDA-SAMD-002", "FDA-SAMD-003"],
    "DEA":              ["DEA-001", "DEA-002"],
    "JOINT_COMMISSION": ["JCAHO-001", "JCAHO-002"],
    "ISO_13485":        ["ISO13485-001", "ISO13485-002"],
    "CFR_46":           ["CFR46-001", "CFR46-002"],
}

# Human-readable labels for API responses
REGULATION_LABELS: Dict[str, str] = {
    "HIPAA":            "HIPAA — Patient Data Privacy & Security (45 CFR §164)",
    "HITECH":           "HITECH — Health IT Breach Enforcement (42 U.S.C. §17931)",
    "FDA_SAMD":         "FDA SaMD — Software as a Medical Device (21 CFR Part 820)",
    "DEA":              "DEA — Controlled Substance Controls (21 CFR §1306)",
    "JOINT_COMMISSION": "Joint Commission — Clinical Safety Standards (NPSG/CAMH)",
    "ISO_13485":        "ISO 13485 — Medical Device Quality Management (ISO 13485:2016)",
    "CFR_46":           "45 CFR 46 — Research Subject Protection (Common Rule)",
}

ALL_REGULATIONS = list(REQUIRED_RULES_BY_REGULATION.keys())
