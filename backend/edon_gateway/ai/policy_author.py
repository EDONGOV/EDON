"""AI-powered natural language policy authoring.

Converts plain-English policy descriptions into structured policy rule JSON
that can be submitted to the tenant rules API.

The AI drafts the rule; a human MUST review and explicitly submit it via
the standard policy rules API before it takes effect.

Fail-open: returns None on any error.
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

# All valid tool names from schemas.py Tool enum
_KNOWN_TOOLS = (
    "email", "shell", "calendar", "file", "clawdbot", "brave_search", "gmail",
    "google_calendar", "elevenlabs", "github", "gemini", "polygon", "fmp",
    "newsapi", "home_assistant", "memory", "agent", "browser", "slack",
    "discord", "twitter", "notion", "database", "http", "robot", "vehicle",
    "conveyor", "forklift", "drone", "scanner", "sorter", "dock", "gate",
    "sensor", "custom", "filesystem",
)

_SYSTEM_PROMPT = f"""\
You are a governance policy author for an AI agent platform.

You receive a JSON object with:
- "description": plain-English description of the desired policy rule
- "examples": optional list of example actions this should affect

Convert this into a structured governance policy rule. The rule must have:
- "name": short descriptive name (snake_case, max 64 chars)
- "description": human-readable description (max 200 chars)
- "action": one of "BLOCK", "ESCALATE", or "ALLOW"
- "condition_tool": one of these tool names or null for any: {", ".join(_KNOWN_TOOLS[:20])}...
- "condition_op": operation name to match (e.g. "send", "exec", "delete") or null
- "condition_risk_level": one of "low", "medium", "high", "critical" or null
- "enabled": true

Return ONLY a JSON object: {{"rule": {{...}}, "warnings": ["optional warnings about ambiguity"]}}

If the description is too ambiguous to create a safe rule, return:
{{"rule": null, "warnings": ["<explanation why rule cannot be safely generated>"]}}

Always err on the side of caution — if unsure whether action should be BLOCK
or ESCALATE, use ESCALATE.
"""


def author_policy_rule(
    description: str,
    examples: Optional[list] = None,
) -> dict:
    """Convert a plain-English description into a draft policy rule.

    The returned rule is a DRAFT — it must be reviewed and submitted via the
    standard policy rules API before it takes effect.

    Args:
        description: Plain-English policy description.
        examples: Optional list of example action strings.

    Returns:
        Dict with "rule" (dict or None) and "warnings" (list).
        Never raises.
    """
    import json as _json

    safe_desc = str(description)[:500]
    safe_examples = [str(e)[:100] for e in (examples or [])[:5]]

    payload = _json.dumps({
        "description": safe_desc,
        "examples": safe_examples,
    }, separators=(",", ":"))

    result = call_advisory(_SYSTEM_PROMPT, payload, max_tokens=512)

    if result is None:
        return {
            "rule": None,
            "warnings": ["AI policy author unavailable. Please write the rule manually."],
        }

    try:
        rule = result.get("rule")
        warnings = result.get("warnings", [])

        if rule is not None:
            # Validate and sanitize the rule
            action = str(rule.get("action", "")).upper()
            if action not in ("BLOCK", "ESCALATE", "ALLOW"):
                return {
                    "rule": None,
                    "warnings": [f"AI generated invalid action '{action}'. Please specify BLOCK, ESCALATE, or ALLOW."],
                }

            # Validate tool if specified
            condition_tool = rule.get("condition_tool")
            if condition_tool and str(condition_tool).lower() not in _KNOWN_TOOLS:
                warnings.append(f"Warning: unknown tool '{condition_tool}'. Verify before submitting.")

            return {
                "rule": {
                    "name": str(rule.get("name", "ai_generated_rule"))[:64],
                    "description": str(rule.get("description", safe_desc[:200]))[:200],
                    "action": action,
                    "condition_tool": str(condition_tool).lower() if condition_tool else None,
                    "condition_op": str(rule.get("condition_op", ""))[:64] or None,
                    "condition_risk_level": rule.get("condition_risk_level"),
                    "enabled": True,
                    "source": "ai_policy_author",
                    "status": "draft_pending_review",
                },
                "warnings": [str(w)[:200] for w in (warnings or [])[:5]],
            }

        return {
            "rule": None,
            "warnings": [str(w)[:200] for w in (warnings or ["AI could not generate a safe rule."])[:5]],
        }

    except Exception as exc:
        logger.debug("Policy author result parsing failed: %s", exc)
        return {"rule": None, "warnings": [f"Result parsing failed: {str(exc)[:100]}"]}
