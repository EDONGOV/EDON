"""Training data formatters — convert raw records to Anthropic fine-tuning JSONL.

Each formatter takes a list of raw dicts (from extractors.py) and returns
a list of fine-tuning message dicts:

    {"messages": [
        {"role": "system",    "content": "..."},
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."}
    ]}

Quality rules applied in every formatter:
- Skip examples with empty or near-empty assistant turns
- Skip examples where key fields are None/empty
- Truncate oversized params to keep context windows reasonable
"""

from __future__ import annotations

import json
from typing import Any

# ── System prompts ─────────────────────────────────────────────────────────────

_GOVERNANCE_SYSTEM = (
    "You are EDON, an AI governance engine. Your job is to evaluate agent actions "
    "and decide whether to ALLOW, BLOCK, ESCALATE, DEGRADE, or PAUSE them. "
    "Base your decision on: the action's tool and operation, the agent's stated intent, "
    "the applicable policy rules, the data classes involved, and any anomaly signals. "
    "Respond with the verdict followed by a clear, specific explanation. "
    "Format: VERDICT — explanation."
)

_VULNERABILITY_SYSTEM = (
    "You are EDON's vulnerability analysis engine. You analyze AI agent execution graphs "
    "to identify security vulnerabilities and governance gaps. "
    "Given a description of agent behavior, tools used, and data flows, identify "
    "the vulnerability class, the exploit path, the severity, and what governance "
    "constraint is missing. Be precise and evidence-based."
)

_RISK_SYSTEM = (
    "You are EDON's risk prediction engine. Given an agent, tool, and operation, "
    "predict whether this action represents normal behavior or an out-of-bounds risk. "
    "Consider: whether this tool/op combination has historically caused incidents, "
    "whether the agent has performed this before, and the sensitivity of the data involved. "
    "Respond with the risk label (safe / blocked / oob / incident) and your reasoning."
)

_FIX_SYSTEM = (
    "You are EDON's governance rule generator. Given a vulnerability finding, "
    "generate a precise governance rule that would block or constrain the exploit path. "
    "Output the rule as: action (BLOCK/ESCALATE), condition_tool, condition_op, "
    "and a clear rule description explaining what it prevents and why."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _truncate(v: Any, max_len: int = 300) -> str:
    s = str(v) if not isinstance(v, str) else v
    return s[:max_len] + "…" if len(s) > max_len else s


def _params_summary(params: Any, max_len: int = 200) -> str:
    if not params:
        return "none"
    if isinstance(params, dict):
        # Redact credential-like keys
        safe = {k: ("***" if any(x in k.lower() for x in ("key", "token", "secret", "password", "credential")) else v)
                for k, v in params.items()}
        return _truncate(json.dumps(safe, default=str), max_len)
    return _truncate(str(params), max_len)


def _path_summary(path: list) -> str:
    if not path:
        return "unknown"
    return " → ".join(str(p) for p in path[:8])


def _data_classes_str(dc: Any) -> str:
    if isinstance(dc, list):
        return ", ".join(dc) if dc else "none"
    if isinstance(dc, str):
        try:
            parsed = json.loads(dc)
            return ", ".join(parsed) if parsed else "none"
        except Exception:
            return dc or "none"
    return "none"


# ── Formatter 1: Governance decisions ─────────────────────────────────────────

def format_governance_decisions(records: list[dict]) -> list[dict]:
    """Convert audit_event records to governance decision training examples."""
    examples = []
    for r in records:
        verdict = (r.get("decision_verdict") or "").strip().upper()
        explanation = (r.get("decision_explanation") or "").strip()
        agent_id = (r.get("agent_id") or "").strip()
        tool = (r.get("action_tool") or "unknown").strip()
        op = (r.get("action_op") or "unknown").strip()

        if not verdict or not explanation or not agent_id:
            continue
        if len(explanation) < 15:
            continue

        params = r.get("action_params") or {}
        context = r.get("context") or {}
        stated_intent = (r.get("stated_intent") or "not specified").strip()
        risk_level = (r.get("action_estimated_risk") or "unknown").strip()
        anomaly = r.get("anomaly_score")
        rule_id = r.get("policy_rule_id") or "none"
        reason_code = (r.get("decision_reason_code") or "").strip()

        # Build user prompt
        user_parts = [
            f"Agent: {agent_id}",
            f"Action: {tool}.{op}",
            f"Params: {_params_summary(params)}",
            f"Stated intent: {stated_intent}",
            f"Estimated risk: {risk_level}",
        ]
        if anomaly is not None:
            user_parts.append(f"Anomaly score: {round(float(anomaly), 3)}")
        if rule_id != "none":
            user_parts.append(f"Matched policy rule: {rule_id}")
        if isinstance(context, dict):
            dc = context.get("data_classes") or context.get("detected_data_classes")
            if dc:
                user_parts.append(f"Data classes: {_data_classes_str(dc)}")

        # Human override gets flagged — highest quality signal
        human_override = r.get("human_override")
        human_reason = r.get("human_override_reason") or ""
        if human_override:
            user_parts.append(f"[Human override applied: {human_reason}]")

        assistant = f"{verdict} — {explanation}"
        if reason_code:
            assistant = f"{verdict} ({reason_code}) — {explanation}"

        examples.append({"messages": [
            {"role": "system",    "content": _GOVERNANCE_SYSTEM},
            {"role": "user",      "content": "\n".join(user_parts)},
            {"role": "assistant", "content": assistant},
        ]})

    return examples


# ── Formatter 2: Shadow bypass findings ───────────────────────────────────────

def format_shadow_findings(records: list[dict]) -> list[dict]:
    """Convert shadow replay results to governance robustness training examples.

    The model learns: given an original ALLOW decision + a perturbation,
    should the verdict change? Answer: yes when the perturbation exploits a gap.
    """
    examples = []
    for r in records:
        agent_id = r.get("agent_id") or "unknown"
        action_type = r.get("action_type") or "unknown"
        original_verdict = (r.get("original_verdict") or "ALLOW").upper()
        shadow_verdict = (r.get("shadow_verdict") or "BLOCK").upper()
        perturbation = r.get("perturbation_name") or r.get("perturbation_type") or "unknown"
        perturbed_field = r.get("perturbed_field") or "unknown"
        severity = r.get("severity") or "advisory"
        original_reason = r.get("original_reason") or ""
        shadow_reason = r.get("shadow_reason") or ""

        payload = r.get("action_payload") or {}
        context = r.get("context") or {}

        if not shadow_verdict or shadow_verdict == original_verdict:
            continue

        user_parts = [
            f"Agent: {agent_id}",
            f"Action: {action_type}",
            f"Original verdict: {original_verdict}",
            f"Perturbation applied: {perturbation} (field: {perturbed_field})",
            f"Params: {_params_summary(payload)}",
        ]
        if isinstance(context, dict):
            stated = context.get("stated_intent") or ""
            if stated:
                user_parts.append(f"Stated intent: {stated}")

        user_parts.append(
            f"\nGiven this perturbation to the original action, should the verdict change? "
            f"Explain whether '{perturbation}' creates a governance gap."
        )

        assistant_parts = [
            f"Yes — verdict should change from {original_verdict} to {shadow_verdict}.",
            f"Severity: {severity}.",
        ]
        if shadow_reason:
            assistant_parts.append(f"Reason: {shadow_reason}")
        if original_reason:
            assistant_parts.append(f"Original decision was: {original_reason}")
        assistant_parts.append(
            f"The perturbation '{perturbation}' on field '{perturbed_field}' "
            "bypasses the original governance check, requiring a stricter rule on this path."
        )

        examples.append({"messages": [
            {"role": "system",    "content": _GOVERNANCE_SYSTEM},
            {"role": "user",      "content": "\n".join(user_parts)},
            {"role": "assistant", "content": " ".join(assistant_parts)},
        ]})

    return examples


# ── Formatter 3: Risk labels ───────────────────────────────────────────────────

def format_risk_labels(records: list[dict]) -> list[dict]:
    """Convert fleet_learning feedback_labels to risk prediction examples."""
    _label_explanation = {
        "incident":
            "This tool/operation combination has caused a confirmed security incident. "
            "It should be blocked or require explicit approval.",
        "oob":
            "This action is out-of-bounds for this agent — it exceeds the agent's declared "
            "operational scope or has never appeared in its behavioral baseline.",
        "blocked":
            "The governance engine blocked this action. Historical block rate for this "
            "tool/op combination is elevated, indicating it regularly violates policy.",
        "safe":
            "This action falls within normal operational parameters. The tool/op combination "
            "has a low historical incident rate and matches the agent's typical behavior.",
    }

    examples = []
    for r in records:
        tool = r.get("action_tool") or "unknown"
        op = r.get("action_op") or "unknown"
        label = (r.get("label") or "").strip().lower()
        agent_id = r.get("agent_id") or "unknown_agent"
        oob_type = r.get("oob_type") or ""
        notes = r.get("notes") or ""
        predicted_risk = r.get("predicted_risk")
        source = r.get("source") or "auto"

        if label not in _label_explanation:
            continue

        user_parts = [
            f"Agent: {agent_id}",
            f"Tool: {tool}",
            f"Operation: {op}",
            f"Source: {source}",
        ]
        if predicted_risk is not None:
            user_parts.append(f"Predicted risk score: {round(float(predicted_risk), 3)}")
        if notes:
            user_parts.append(f"Context: {_truncate(notes, 150)}")

        explanation = _label_explanation[label]
        if oob_type:
            explanation += f" OOB type: {oob_type}."

        examples.append({"messages": [
            {"role": "system",    "content": _RISK_SYSTEM},
            {"role": "user",      "content": "\n".join(user_parts)},
            {"role": "assistant", "content": f"Risk label: {label}. {explanation}"},
        ]})

    return examples


# ── Formatter 4: Vulnerability findings ───────────────────────────────────────

def format_vulnerabilities(records: list[dict]) -> list[dict]:
    """Convert impact store failure states to vulnerability discovery examples."""
    examples = []
    for r in records:
        vuln_class = r.get("vulnerability_class") or "unknown"
        description = r.get("description") or ""
        path = r.get("path") or []
        constraint = r.get("constraint_violation") or ""
        data_classes = r.get("data_classes") or []
        severity = round(float(r.get("severity_score") or 0), 3)
        blast = round(float(r.get("blast_radius_score") or 0), 3)
        likelihood = round(float(r.get("likelihood_score") or 0), 3)
        window = r.get("exploitability_window") or "session"
        narrative = r.get("attack_narrative") or ""
        impact_desc = r.get("impact_description") or ""
        remediation = r.get("remediation_steps") or []

        if not vuln_class or not path:
            continue

        path_str = _path_summary(path)
        dc_str = _data_classes_str(data_classes)

        user_parts = [
            "Analyze the following AI agent execution path for security vulnerabilities:",
            f"Path: {path_str}",
            f"Data classes in flow: {dc_str}",
        ]
        if constraint:
            user_parts.append(f"Governance constraint status: {constraint}")

        assistant_parts = [
            f"Vulnerability: {vuln_class.replace('_', ' ').title()}",
            f"Severity: {severity} (blast radius: {blast}, likelihood: {likelihood})",
            f"Exploitability window: {window}",
        ]
        if description:
            assistant_parts.append(f"Description: {_truncate(description, 300)}")
        if constraint:
            assistant_parts.append(f"Missing constraint: {constraint}")
        if narrative:
            assistant_parts.append(f"Attack scenario: {_truncate(narrative, 300)}")
        if impact_desc:
            assistant_parts.append(f"Impact if exploited: {_truncate(impact_desc, 200)}")
        if remediation:
            steps = remediation if isinstance(remediation, list) else []
            if steps:
                assistant_parts.append(f"Fix: {steps[0]}")

        examples.append({"messages": [
            {"role": "system",    "content": _VULNERABILITY_SYSTEM},
            {"role": "user",      "content": "\n".join(user_parts)},
            {"role": "assistant", "content": "\n".join(assistant_parts)},
        ]})

    return examples


# ── Formatter 5: Fix generation (deployed rules) ──────────────────────────────

def format_deployed_rules(records: list[dict]) -> list[dict]:
    """Convert auto-deployed governance rules to fix generation training examples."""
    examples = []
    for r in records:
        name = r.get("name") or ""
        description = r.get("description") or ""
        action = r.get("action") or "BLOCK"
        tool = r.get("condition_tool") or "any"
        op = r.get("condition_op") or "any"
        tags = r.get("condition_tags") or []

        if not name and not description:
            continue

        tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        context_str = tag_str or "auto-hardening"

        user = (
            f"An AI governance scan identified the following issue:\n"
            f"{description or name}\n"
            f"Context: {context_str}\n"
            f"Generate a governance rule to mitigate this."
        )

        assistant = (
            f"Action: {action}\n"
            f"Condition: tool={tool}, operation={op}\n"
            f"Rule name: {name}\n"
            f"Description: {description or name}\n"
            f"This rule {'blocks' if action == 'BLOCK' else 'escalates'} "
            f"the {tool}.{op} operation to prevent the identified governance gap."
        )

        examples.append({"messages": [
            {"role": "system",    "content": _FIX_SYSTEM},
            {"role": "user",      "content": user},
            {"role": "assistant", "content": assistant},
        ]})

    return examples


# ── Formatter 6: Review queue feedback (human approval/rejection) ─────────────

def format_review_feedback(records: list[dict]) -> list[dict]:
    """Convert resolved review-queue escalations to preference training examples.

    Approved escalations → ALLOW (human confirmed the action was acceptable).
    Rejected escalations → BLOCK (human confirmed the action should be blocked).
    These are the highest-quality signal: real humans labelling real agent actions.
    """
    examples = []
    for r in records:
        resolution = (r.get("resolution") or "").lower()
        if resolution not in ("approved", "rejected"):
            continue

        agent_id  = (r.get("agent_id") or "unknown").strip()
        action    = (r.get("action_type") or "unknown").strip()
        question  = (r.get("escalation_question") or "").strip()
        explanation = (r.get("explanation") or "").strip()
        note      = (r.get("resolution_note") or "").strip()
        payload   = r.get("action_payload") or {}

        if not explanation and not question:
            continue

        user_parts = [
            f"Agent: {agent_id}",
            f"Action: {action}",
            f"Params: {_params_summary(payload)}",
        ]
        if question:
            user_parts.append(f"Escalation question: {question}")

        if resolution == "approved":
            verdict = "ALLOW"
            reason_code = "HUMAN_APPROVED"
            body = explanation or question
            if note:
                body += f" Reviewer note: {note}"
        else:
            verdict = "BLOCK"
            reason_code = "HUMAN_REJECTED"
            body = explanation or question
            if note:
                body += f" Reviewer note: {note}"

        examples.append({"messages": [
            {"role": "system",    "content": _GOVERNANCE_SYSTEM},
            {"role": "user",      "content": "\n".join(user_parts)},
            {"role": "assistant", "content": f"{verdict} ({reason_code}) — {body}"},
        ]})

    return examples


# ── Dispatch ───────────────────────────────────────────────────────────────────

def format_all(raw: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Format all extracted datasets. Returns keyed dict of example lists."""
    return {
        "governance_decisions": format_governance_decisions(raw.get("governance_decisions", [])),
        "shadow_findings":      format_shadow_findings(raw.get("shadow_findings", [])),
        "risk_labels":          format_risk_labels(raw.get("risk_labels", [])),
        "vulnerabilities":      format_vulnerabilities(raw.get("vulnerabilities", [])),
        "deployed_rules":       format_deployed_rules(raw.get("deployed_rules", [])),
        "review_feedback":      format_review_feedback(raw.get("review_feedback", [])),
    }
