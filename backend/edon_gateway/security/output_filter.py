"""Output governance — filter and assess tool execution responses.

EDON governs what agents try to DO (input governance) and what comes BACK
(output governance). This module scans tool execution results for:

  1. PHI/PII patterns  — SSN, DOB, MRN, phone, email, credit card
  2. Credential leakage — API keys, tokens, private keys in response text
  3. Bulk data signals  — suspiciously large record counts (potential mass exfil)
  4. Sensitive path      — file paths that indicate system/credential access

Verdicts:
  PASS   — response is safe to forward to the agent
  REDACT — response contains sensitive data; redacted copy provided
  BLOCK  — response should not be forwarded (bulk exfil or credential leak)

All findings are advisory by default. Tenants can set
EDON_OUTPUT_FILTER_STRICT=true to turn REDACT → BLOCK.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_STRICT = os.getenv("EDON_OUTPUT_FILTER_STRICT", "false").strip().lower() == "true"

# ── Pattern library ───────────────────────────────────────────────────────────

_PHI_PATTERNS: list[tuple[str, re.Pattern]] = [
    # SSN dashed — highly specific, minimal false positives
    ("ssn",         re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # SSN plain — require SSN/social security keyword to avoid matching any 9-digit number
    ("ssn_context", re.compile(r"\b(?:ssn|social[\s_\-]?security)\b[\s:=#\-]*\d{9}\b", re.I)),
    # SSN in JSON value — "ssn": "123456789"
    ("ssn_json",    re.compile(r'"ssn"\s*:\s*"?\d{9}\b', re.I)),
    ("mrn",         re.compile(r"\bMRN[:\s#]*\d{5,12}\b", re.I)),
    ("dob",         re.compile(r"\b(?:DOB|date.of.birth)[:\s]*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b", re.I)),
    ("dob_json",    re.compile(r'"(?:dob|birth_?date|date_?of_?birth|born|birthday)"\s*:\s*"?\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', re.I)),
    ("phone",       re.compile(r"\b(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")),
    # Fax requires context word — otherwise identical to phone and creates duplicate findings
    ("fax",         re.compile(r"\b(?:fax|facsimile)[\s:]*(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b", re.I)),
    ("credit_card", re.compile(r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6011\d{12})\b")),
    ("email",       re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("npi",         re.compile(r"\bNPI[:\s]*\d{10}\b", re.I)),
]

_CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_key",      re.compile(r"AKIA[0-9A-Z]{16}")),
    ("jwt",          re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private_key",  re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("api_key_kv",   re.compile(r"(?:api[_\-]?key|secret[_\-]?key|auth[_\-]?token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?", re.I)),
    ("gh_token",     re.compile(r"ghp_[A-Za-z0-9]{30,42}")),
]

_SENSITIVE_PATHS = re.compile(
    r"(?:/etc/passwd|/etc/shadow|id_rsa|\.env|\.aws/credentials|/proc/|/sys/)", re.I
)

_BULK_RECORD_THRESHOLD = int(os.getenv("EDON_OUTPUT_BULK_THRESHOLD", "500"))


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class OutputFinding:
    category: str        # "phi", "credential", "bulk_data", "sensitive_path"
    pattern_name: str
    count: int = 1
    sample: str = ""     # Redacted sample, never the full match


@dataclass
class OutputFilterResult:
    verdict: str                            # "PASS", "REDACT", "BLOCK"
    findings: list[OutputFinding] = field(default_factory=list)
    redacted_text: str | None = None        # Set when verdict is REDACT
    record_count: int | None = None
    original_size_bytes: int = 0


# ── Core filter ───────────────────────────────────────────────────────────────

def _redact(text: str, pattern: re.Pattern, replacement: str) -> tuple[str, int]:
    """Replace all matches with replacement. Returns (new_text, match_count)."""
    count = len(pattern.findall(text))
    return pattern.sub(replacement, text), count


def filter_output(
    response_payload: Any,
    action_tool: str = "",
    action_op: str = "",
) -> OutputFilterResult:
    """Scan a tool execution response and return a verdict with findings.

    Args:
        response_payload: The raw response from the tool (any JSON-serialisable type).
        action_tool: Tool name (for context in findings).
        action_op: Operation name (for context in findings).

    Returns:
        OutputFilterResult with verdict, findings, and optionally a redacted copy.
    """
    import json as _json

    # Serialise to string for scanning
    try:
        if isinstance(response_payload, str):
            text = response_payload
        else:
            text = _json.dumps(response_payload, default=str)
    except Exception:
        text = str(response_payload)

    original_size = len(text.encode("utf-8"))
    findings: list[OutputFinding] = []
    redacted = text
    verdict = "PASS"

    # 1. Credential leak — always BLOCK (strict or not)
    for name, pattern in _CREDENTIAL_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(OutputFinding(
                category="credential",
                pattern_name=name,
                count=len(matches),
                sample=f"[{name.upper()}_REDACTED]",
            ))
            redacted, _ = _redact(redacted, pattern, f"[{name.upper()}_REDACTED]")
            verdict = "BLOCK"

    # 2. PHI patterns — REDACT (or BLOCK in strict mode)
    for name, pattern in _PHI_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(OutputFinding(
                category="phi",
                pattern_name=name,
                count=len(matches),
                sample=f"[{name.upper()}_REDACTED]",
            ))
            redacted, _ = _redact(redacted, pattern, f"[{name.upper()}_REDACTED]")
            if verdict != "BLOCK":
                verdict = "BLOCK" if _STRICT else "REDACT"

    # 3. Sensitive path exposure
    if _SENSITIVE_PATHS.search(text):
        findings.append(OutputFinding(
            category="sensitive_path",
            pattern_name="system_path",
            sample="[PATH_REDACTED]",
        ))
        redacted = _SENSITIVE_PATHS.sub("[PATH_REDACTED]", redacted)
        if verdict not in ("BLOCK",):
            verdict = "BLOCK" if _STRICT else "REDACT"

    # 4. Bulk data heuristic — count JSON array elements or newline-delimited records
    record_count: int | None = None
    try:
        parsed = _json.loads(text)
        if isinstance(parsed, list):
            record_count = len(parsed)
        elif isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list) and len(v) > record_count if record_count else True:
                    record_count = len(v)
        if record_count and record_count >= _BULK_RECORD_THRESHOLD:
            findings.append(OutputFinding(
                category="bulk_data",
                pattern_name="record_count",
                count=record_count,
                sample=f"{record_count} records",
            ))
            if verdict != "BLOCK":
                verdict = "BLOCK" if _STRICT else "REDACT"
    except Exception:
        pass

    if not findings:
        return OutputFilterResult(
            verdict="PASS",
            original_size_bytes=original_size,
            record_count=record_count,
        )

    logger.info(
        "output_filter: verdict=%s tool=%s.%s findings=%d size=%db",
        verdict, action_tool, action_op, len(findings), original_size,
    )

    return OutputFilterResult(
        verdict=verdict,
        findings=findings,
        redacted_text=redacted if verdict in ("REDACT", "BLOCK") else None,
        record_count=record_count,
        original_size_bytes=original_size,
    )
