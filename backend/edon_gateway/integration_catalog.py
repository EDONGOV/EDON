"""Enterprise integration catalog for EDON Gateway.

This catalog names the major external systems EDON is expected to integrate
with and records the supported auth, transport, and governance patterns.
The goal is to keep the integration surface explicit and reviewable.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


ENTERPRISE_INTEGRATION_TARGETS: List[Dict[str, Any]] = [
    {
        "slug": "ehr-emr",
        "category": "ehr_emr",
        "title": "EHR / EMR Systems",
        "priority": "highest",
        "examples": ["Epic Systems", "Oracle Health (Cerner)", "MEDITECH"],
        "integration_patterns": [
            "SMART on FHIR / OAuth 2.0",
            "FHIR R4 / HL7 API gateway",
            "Vendor API proxy",
            "Event/webhook relay",
            "File or batch exchange where required",
        ],
        "edon_role": [
            "Govern AI interactions with records",
            "Enforce approval policies before writes",
            "Audit agent actions against PHI/clinical records",
            "Monitor AI-generated clinical and administrative outputs",
        ],
        "required_controls": [
            "Tenant-scoped identity and audit chain",
            "Decision record binding for all writes",
            "Step-up auth for privileged write paths",
            "PHI export destination policy checks",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "iam",
        "category": "identity_access_management",
        "title": "Identity & Access Management",
        "examples": ["Microsoft Entra ID", "Okta", "Ping Identity", "Google Workspace"],
        "integration_patterns": [
            "SAML 2.0",
            "OIDC / OAuth 2.0",
            "SCIM provisioning",
            "Federated group claims",
        ],
        "edon_role": [
            "Inherit enterprise identity",
            "Apply governance policies from the identity context",
            "Enforce RBAC and approvals",
            "Bind admins and operators to verified identity providers",
        ],
        "required_controls": [
            "SSO-only mode for enterprise tenants",
            "Mandatory MFA for privileged roles",
            "Tenant-bound role mapping",
            "Short-lived tokens and rotation for service identities",
        ],
        "status": "native_and_required",
    },
    {
        "slug": "clinical-communications",
        "category": "clinical_communications",
        "title": "Clinical Communication Systems",
        "examples": ["TigerConnect", "Vocera Communications"],
        "integration_patterns": [
            "Webhook delivery",
            "REST API / outbound message API",
            "Message bus or relay service",
            "Escalation routing integration",
        ],
        "edon_role": [
            "Govern AI-generated escalations",
            "Audit agent-to-human communication",
            "Policy-check alerts and workflows",
        ],
        "required_controls": [
            "Message content policy checks",
            "Audit log of all outbound messages",
            "Delivery retry and dead-letter handling",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "scheduling-staffing",
        "category": "scheduling_staffing",
        "title": "Scheduling / Staffing Systems",
        "examples": ["UKG / Kronos", "Nurse staffing tools"],
        "integration_patterns": [
            "REST API",
            "Batch export/import",
            "Webhook events",
        ],
        "edon_role": [
            "Govern automated scheduling agents",
            "Prevent unsafe staffing recommendations",
            "Audit optimization decisions",
        ],
        "required_controls": [
            "Human approval for staffing changes in high-risk wards",
            "Reason capture for optimization decisions",
            "Tenant and department scoping",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "revenue-cycle",
        "category": "revenue_cycle_billing",
        "title": "Revenue Cycle / Billing Systems",
        "examples": ["Epic billing modules", "RCM vendors", "Claims systems"],
        "integration_patterns": [
            "REST API",
            "EDI / batch exchange",
            "Claims workflows",
            "Vendor portal integration",
        ],
        "edon_role": [
            "Govern billing automation",
            "Validate AI-generated coding suggestions",
            "Audit claim-related workflows",
        ],
        "required_controls": [
            "Coding and claim approval workflow",
            "Audit trail for every billing mutation",
            "Policy checks for downstream payer submissions",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "pacs-imaging",
        "category": "pacs_imaging",
        "title": "PACS / Imaging Systems",
        "examples": ["Radiology PACS", "Imaging AI tools"],
        "integration_patterns": [
            "DICOM",
            "HL7 / FHIR metadata exchange",
            "Vendor API",
        ],
        "edon_role": [
            "Govern AI-assisted analysis pipelines",
            "Track model outputs and provenance",
            "Route escalations for human review",
        ],
        "required_controls": [
            "Model-output provenance capture",
            "Human approval for clinical escalations",
            "Imaging destination allowlists",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "laboratory",
        "category": "laboratory_information_systems",
        "title": "Laboratory Systems",
        "examples": ["Labcorp integrations", "Pathology systems", "LIS platforms"],
        "integration_patterns": [
            "HL7",
            "FHIR",
            "REST API",
            "Batch result pipeline",
        ],
        "edon_role": [
            "Audit automated workflows",
            "Enforce routing policies",
            "Validate escalation handling",
        ],
        "required_controls": [
            "Tenant-scoped lab routing",
            "Result delivery audit log",
            "Escalation and exception capture",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "erp-procurement",
        "category": "erp_procurement",
        "title": "ERP / Procurement Systems",
        "examples": ["SAP", "Oracle ERP"],
        "integration_patterns": [
            "REST API",
            "SOAP where legacy systems require it",
            "Batch imports",
            "Procurement workflow APIs",
        ],
        "edon_role": [
            "Govern supply-chain automation",
            "Audit purchasing workflows",
            "Monitor autonomous procurement agents",
        ],
        "required_controls": [
            "Spend threshold approval",
            "Vendor and PO policy checks",
            "Purchase audit chain",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "security-siem",
        "category": "security_siem",
        "title": "Security / SIEM Systems",
        "examples": ["Microsoft Sentinel", "Splunk", "CrowdStrike"],
        "integration_patterns": [
            "Syslog / event forwarding",
            "REST API",
            "Webhook relay",
            "Streaming event sink",
        ],
        "edon_role": [
            "Stream governance events",
            "Provide audit evidence",
            "Integrate with incident response",
        ],
        "required_controls": [
            "Tamper-evident event payloads",
            "Tenant-scoped event routing",
            "IR escalation mapping",
        ],
        "status": "native_and_required",
    },
    {
        "slug": "llm-providers",
        "category": "llm_providers",
        "title": "AI / LLM Providers",
        "examples": ["OpenAI", "Anthropic", "Ollama / Qwen runtime", "Healthcare AI vendors"],
        "integration_patterns": [
            "Provider API gateway",
            "Prompt routing and policy enforcement",
            "Local runtime proxy",
            "Signed model/output exchange",
        ],
        "edon_role": [
            "Model routing",
            "Policy enforcement on prompts and outputs",
            "Action authorization",
        ],
        "required_controls": [
            "Decision record binding for actions",
            "Prompt and output audit logs",
            "Tenant and model allowlists",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "robotics-physical-ai",
        "category": "robotics_physical_ai",
        "title": "Robotics / Physical AI Systems",
        "examples": ["Logistics robots", "Humanoids", "Autonomous carts", "Pharmacy robotics"],
        "integration_patterns": [
            "Robot gateway API",
            "mTLS or device certificates",
            "Heartbeat / telemetry stream",
            "Emergency-stop channel",
        ],
        "edon_role": [
            "Runtime governance",
            "Safety boundaries",
            "Execution authorization",
            "Emergency stop policy enforcement",
        ],
        "required_controls": [
            "Edge-node identity",
            "Signed config bundle",
            "Attestation and heartbeat enforcement",
            "Fail-closed e-stop propagation",
        ],
        "status": "governed_proxy_ready",
    },
    {
        "slug": "messaging-workflow",
        "category": "messaging_workflow",
        "title": "Messaging / Workflow Systems",
        "examples": ["Microsoft Teams", "Slack", "ServiceNow", "Ticketing systems"],
        "integration_patterns": [
            "Webhook",
            "Bot API",
            "Ticketing API",
            "Approval routing",
        ],
        "edon_role": [
            "Approval routing",
            "Escalation chains",
            "Operational coordination",
        ],
        "required_controls": [
            "Message approval policy for sensitive data",
            "Tenant-scoped workflow routing",
            "Audit log of outbound workflow actions",
        ],
        "status": "governed_proxy_ready",
    },
]

_TARGET_BY_SLUG = {target["slug"]: target for target in ENTERPRISE_INTEGRATION_TARGETS}
_TARGET_BY_CATEGORY = {target["category"]: target for target in ENTERPRISE_INTEGRATION_TARGETS}


def get_enterprise_integration_catalog() -> Dict[str, Any]:
    """Return the full enterprise integration catalog."""
    return {
        "version": "1.0",
        "targets": deepcopy(ENTERPRISE_INTEGRATION_TARGETS),
        "supported_categories": sorted(_TARGET_BY_CATEGORY.keys()),
    }


def get_enterprise_integration_target(identifier: str) -> Optional[Dict[str, Any]]:
    """Return one integration target by slug or category."""
    key = (identifier or "").strip().lower()
    if not key:
        return None
    target = _TARGET_BY_SLUG.get(key) or _TARGET_BY_CATEGORY.get(key)
    return deepcopy(target) if target else None
