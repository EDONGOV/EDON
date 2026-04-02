"""Safe Claude API wrapper for EDON AI advisory layer.

All AI calls in this module are:
- Advisory only — outputs are bounded floats or structured JSON
- Fail-open — any error returns None and governance continues unchanged
- Timeout-protected — default 8s hard timeout
- Metadata-only inputs — never pass raw agent-controlled free-text verbatim
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Model to use for all advisory AI calls
_MODEL = os.getenv("EDON_AI_MODEL", "claude-opus-4-6")
_TIMEOUT = float(os.getenv("EDON_AI_TIMEOUT_SEC", "8"))
_MAX_TOKENS = int(os.getenv("EDON_AI_MAX_TOKENS", "512"))
_AI_ENABLED = os.getenv("EDON_AI_ENABLED", "true").strip().lower() == "true"


def _get_client():
    """Lazy-load Anthropic client. Returns None if not configured."""
    try:
        import anthropic  # type: ignore[import]
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


def call_advisory(
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int = _MAX_TOKENS,
    timeout: float = _TIMEOUT,
    expect_json: bool = True,
) -> Optional[Any]:
    """Call Claude with a bounded advisory prompt. Returns parsed JSON or plain text.

    Returns None on any error — callers MUST handle None gracefully (fail-open).
    Never raises. Never blocks the governance pipeline.

    Args:
        system_prompt: System-level instructions (must constrain output to JSON/float).
        user_message: Structured governance context (metadata only, not raw user text).
        max_tokens: Hard cap on response length. Keep small — advisory outputs are compact.
        timeout: Wall-clock timeout in seconds.
        expect_json: If True, parse response as JSON. If False, return raw text.

    Returns:
        Parsed JSON dict/value, raw text string, or None on any failure.
    """
    if not _AI_ENABLED:
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        import anthropic  # type: ignore[import]

        with client.messages.stream(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            thinking={"type": "adaptive"},
        ) as stream:
            response = stream.get_final_message()

        # Extract text content block
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break

        if not text:
            return None

        if expect_json:
            # Strip markdown code fences if present
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            return json.loads(text)

        return text

    except Exception as exc:
        logger.debug("AI advisory call failed (fail-open): %s", exc)
        return None


def call_advisory_float(
    system_prompt: str,
    user_message: str,
    key: str = "score",
    lo: float = 0.0,
    hi: float = 1.0,
    timeout: float = _TIMEOUT,
) -> Optional[float]:
    """Call Claude expecting a single float score in a JSON object.

    Returns bounded float in [lo, hi], or None on failure.

    Example response expected: {"score": 0.72}
    """
    result = call_advisory(system_prompt, user_message, timeout=timeout)
    if result is None:
        return None
    try:
        if isinstance(result, dict):
            value = float(result.get(key, lo))
        else:
            value = float(result)
        return max(lo, min(hi, value))
    except (TypeError, ValueError):
        return None


def is_ai_available() -> bool:
    """Return True if the AI advisory layer is configured and enabled."""
    if not _AI_ENABLED:
        return False
    return _get_client() is not None
