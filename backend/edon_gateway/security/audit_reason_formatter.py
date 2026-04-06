"""Audit-ready reason formatter.

Converts internal verdict + reason_code into human-readable, regulation-mapped
language suitable for Joint Commission, HIPAA, and FDA audits.

Rule: never mention internal implementation details (threshold values, field names).
Always include: what was blocked/escalated, which policy, which regulation, audit ref.
"""

from __future__ import annotations

from typing import Optional

# Maps internal reason codes to audit-ready templates.
# {decision_id} and {agent_id} are injected at call time.
_REASON_TEMPLATES = {
    # BLOCK reasons
    "POLICY_VIOLATION": (
        "Agent action blocked — policy violation detected. "
        "The requested action exceeded the boundaries defined in your active governance policy. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.308(a)(1) (Administrative Safeguards — Security Management Process)."
    ),
    "RISK_TOO_HIGH": (
        "Agent action blocked — risk assessment exceeded acceptable threshold. "
        "The AI governance engine classified this action as high-risk based on "
        "tool type, operation, and contextual signals. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: FDA SaMD Guidance (Pre-Specified Clinical Intended Use); "
        "Joint Commission NPSG.15.01.01 (Safety Risk Reduction)."
    ),
    "INJECTION_DETECTED": (
        "Agent action blocked — prompt injection attempt detected. "
        "The action payload contained patterns consistent with an attempt to override "
        "AI governance controls or hijack agent behavior. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.312(a)(1) (Technical Safeguards — Access Control); "
        "HITECH §13402 (Breach Notification)."
    ),
    "RATE_LIMIT": (
        "Agent action blocked — rate limit exceeded. "
        "This agent has exceeded the maximum permitted action frequency. "
        "This may indicate runaway automation or a control loop failure. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.308(a)(1)(ii)(D) (Information System Activity Review)."
    ),
    "LOOP_DETECTED": (
        "Agent action blocked — repetitive action loop detected. "
        "The same action was repeated beyond the permitted threshold within a short window, "
        "indicating a possible control failure or adversarial loop. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: FDA SaMD Guidance (Performance Monitoring); ISO 13485 §8.2.3."
    ),
    "OUT_OF_SCOPE": (
        "Agent action blocked — action is outside the agent's declared scope. "
        "The requested tool or operation is not permitted under this agent's active intent contract. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.308(a)(4) (Access Management — Minimum Necessary)."
    ),
    "PHI_EXFIL": (
        "Agent action blocked — unauthorized data endpoint detected. "
        "The action attempted to send data to a URL not in the PHI-approved endpoint allowlist. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.312(e)(1) (Transmission Security); "
        "HITECH §13402 (Breach Notification)."
    ),
    "ANOMALY_DETECTED": (
        "Agent action escalated — behavioral anomaly detected. "
        "The AI anomaly engine identified a suspicious action sequence "
        "(e.g. reconnaissance followed by data send, or rapid sequential shell commands). "
        "Human review required before proceeding. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: HIPAA §164.308(a)(1)(ii)(D) (Information System Activity Review); "
        "FDA SaMD Guidance (Anomaly Handling)."
    ),
    "NEED_CONFIRMATION": (
        "Agent action escalated — human confirmation required. "
        "The governance engine determined that this action requires human approval "
        "before execution based on risk level, predicted behavior, or policy configuration. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: FDA SaMD Guidance (Human Oversight); "
        "Joint Commission NPSG.15.01.01; ISO 14971 §6 (Risk Control)."
    ),
    "HIGH_RISK_SCORE": (
        "Agent action escalated — AI risk classifier returned a high-risk score. "
        "An independent AI model assessed this action as high-risk based on structural metadata. "
        "Human review required. "
        "Audit reference: {decision_id}. Agent: {agent_id}. "
        "Regulation: FDA SaMD Guidance; ISO 14971."
    ),
}

def format_reason(
    verdict: str,
    reason_code: Optional[str],
    decision_id: str,
    agent_id: str,
    original_explanation: str = "",
) -> str:
    """Return an audit-ready reason string.

    Falls back to the original_explanation if no template matches,
    but always appends audit reference and regulation mapping.
    """
    code = (reason_code or "").upper().replace("-", "_")
    template = _REASON_TEMPLATES.get(code)

    if template:
        return template.format(decision_id=decision_id, agent_id=agent_id)

    # No template — enrich the original explanation
    verdict_upper = verdict.upper()
    if verdict_upper in ("BLOCK", "ERROR"):
        base = original_explanation or "Action blocked by governance policy."
        return (
            f"{base.rstrip('.')}. "
            f"Audit reference: {decision_id}. Agent: {agent_id}. "
            f"Regulation: HIPAA §164.308(a)(1) (Security Management Process)."
        )
    elif verdict_upper in ("ESCALATE", "HUMAN_REQUIRED", "PAUSE"):
        base = original_explanation or "Action requires human review."
        return (
            f"{base.rstrip('.')}. "
            f"Audit reference: {decision_id}. Agent: {agent_id}. "
            f"Review at https://console.edoncore.com."
        )

    return original_explanation
