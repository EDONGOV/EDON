"""Prompt injection detection for AI agent inputs and tool outputs.

Scans action parameters (and tool outputs) for injection patterns:
instructions embedded in data that attempt to hijack agent behavior.
"""

import re
import base64
from typing import Any, Dict, List, Optional, Tuple


# Each entry: (name, compiled_regex_or_None, description)
# None regex means handled by a custom function.
_INJECTION_PATTERNS: List[Tuple[str, Optional[re.Pattern], str]] = [
    (
        "instruction_override",
        re.compile(
            r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|earlier|your)\s+"
            r"(?:instructions?|rules?|guidelines?|constraints?|system\s+prompt|context)",
            re.IGNORECASE,
        ),
        "Instruction override attempt",
    ),
    (
        "role_hijack",
        re.compile(
            r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|roleplay\s+as|"
            r"your\s+(?:new\s+)?(?:role|persona|identity|name)\s+is|from\s+now\s+on\s+you\s+are)",
            re.IGNORECASE,
        ),
        "Role/persona hijack attempt",
    ),
    (
        "system_prompt_inject",
        re.compile(
            r"(?:\[SYSTEM\]|\[INST\]|<\|system\|>|<system>|###\s*System\s*:|"
            r"SYSTEM\s*PROMPT\s*:|<\|im_start\|>\s*system)",
            re.IGNORECASE,
        ),
        "System prompt injection marker",
    ),
    (
        "jailbreak_dan",
        re.compile(
            r"(?:do\s+anything\s+now|DAN\s+mode|jailbreak(?:ed)?|"
            r"developer\s+mode\s+enabled|unrestricted\s+(?:mode|ai|access)|"
            r"safety\s+(?:filters?\s+)?(?:disabled|bypassed|removed|off))",
            re.IGNORECASE,
        ),
        "DAN/jailbreak pattern",
    ),
    (
        "prompt_exfil",
        re.compile(
            r"(?:repeat\s+(?:everything|all|the\s+(?:full|entire|above|previous))\s+"
            r"(?:back|after|verbatim|word\s+for\s+word)|"
            r"(?:print|output|display|reveal|expose|leak|share)\s+"
            r"(?:your\s+)?(?:system\s+prompt|instructions?|context|initial\s+prompt|"
            r"configuration|api\s+key|secret|password|token))",
            re.IGNORECASE,
        ),
        "Prompt/config exfiltration attempt",
    ),
    (
        "governance_bypass",
        re.compile(
            r"(?:bypass(?:ing)?\s+(?:governance|edon|policy|safety|guardrails?)|"
            r"(?:disable|skip|ignore)\s+(?:governance|edon|policy|safety|guardrails?)|"
            r"governance\s+(?:off|disabled|bypassed))",
            re.IGNORECASE,
        ),
        "EDON governance bypass attempt",
    ),
    (
        "indirect_injection",
        re.compile(
            r"(?:<!-{2,}\s*injection|<!--\s*ai\s+(?:instruction|command)|"
            r"\[ai\s*:\s*(?:instruction|command|override)\]|"
            r"(?:human|assistant|user)\s*:\s*(?:ignore|disregard|act\s+as))",
            re.IGNORECASE,
        ),
        "Indirect/hidden injection marker",
    ),
    # Base64-encoded injection: handled separately via _check_base64
    (
        "encoded_injection",
        None,
        "Base64-encoded injection",
    ),
]

# Compiled patterns for quick text check (excludes the None-regex entry)
_TEXT_PATTERNS = [(n, p, d) for n, p, d in _INJECTION_PATTERNS if p is not None]

_B64_BLOB = re.compile(r'[A-Za-z0-9+/]{24,}={0,2}')


class InjectionResult:
    __slots__ = ("detected", "pattern_name", "description", "field", "snippet")

    def __init__(
        self,
        detected: bool,
        pattern_name: str,
        description: str,
        field: str,
        snippet: str,
    ) -> None:
        self.detected = detected
        self.pattern_name = pattern_name
        self.description = description
        self.field = field
        self.snippet = snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "field": self.field,
            "snippet": self.snippet[:200] if self.snippet else "",
        }


def _check_base64(value: str) -> Optional[str]:
    """Decode base64 blobs and check decoded content for injection patterns."""
    for match in _B64_BLOB.finditer(value):
        blob = match.group(0)
        try:
            decoded = base64.b64decode(blob + "==").decode("utf-8", errors="ignore")
            for name, pattern, _ in _TEXT_PATTERNS:
                if pattern.search(decoded):
                    return name
        except Exception:
            pass
    return None


def _extract_strings(obj: Any, path: str = "", depth: int = 0) -> List[Tuple[str, str]]:
    """Recursively extract (field_path, string_value) from a params dict."""
    if depth > 4:
        return []
    results: List[Tuple[str, str]] = []
    if isinstance(obj, str):
        results.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            results.extend(_extract_strings(v, f"{path}.{k}" if path else str(k), depth + 1))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:30]):
            results.extend(_extract_strings(item, f"{path}[{i}]", depth + 1))
    return results


def scan_params(params: Dict[str, Any]) -> Optional[InjectionResult]:
    """Scan action params for prompt injection. Returns InjectionResult if detected, None if clean."""
    for field_path, text in _extract_strings(params):
        if not text or len(text) < 12:
            continue

        # Text pattern scan
        for name, pattern, description in _TEXT_PATTERNS:
            m = pattern.search(text)
            if m:
                start = max(0, m.start() - 30)
                snippet = text[start : m.end() + 30]
                return InjectionResult(
                    detected=True,
                    pattern_name=name,
                    description=description,
                    field=field_path,
                    snippet=snippet,
                )

        # Base64 scan (only on longer strings to avoid false positives)
        if len(text) >= 24:
            b64_match = _check_base64(text)
            if b64_match:
                return InjectionResult(
                    detected=True,
                    pattern_name="encoded_injection",
                    description=f"Base64-encoded content matches pattern '{b64_match}'",
                    field=field_path,
                    snippet=text[:150],
                )

    return None


def scan_output(output: Any) -> Optional[InjectionResult]:
    """Scan tool output for injected instructions (indirect injection detection).

    Call this after receiving a tool response to detect attacker-controlled
    content trying to hijack the agent via retrieved data.
    """
    if isinstance(output, str):
        return scan_params({"output": output})
    if isinstance(output, dict):
        return scan_params(output)
    return None
