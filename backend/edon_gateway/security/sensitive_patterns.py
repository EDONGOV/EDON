"""Compiled regex patterns for scrubbing sensitive data from log output."""

import re

_EDON_API_KEY = re.compile(r'(?:\bek_[A-Za-z0-9_-]{8,}|\bedon[_-][a-f0-9]{16,})')
_OPENAI_SK_KEY = re.compile(r'sk-[a-zA-Z0-9_-]{20,}', re.IGNORECASE)
_BEARER_TOKEN = re.compile(r'(?i)bearer\s+[a-zA-Z0-9._\-]{20,}')
_JSON_PASSWORD = re.compile(r'"password"\s*:\s*"[^"]+"', re.IGNORECASE)
_JSON_SECRET = re.compile(r'"(?:secret|api_key|token|credential)"\s*:\s*"[^"]+"', re.IGNORECASE)
_JSON_X_EDON_TOKEN = re.compile(r'"X-EDON-TOKEN"\s*:\s*"[^"]+"', re.IGNORECASE)
_HEADER_X_EDON_TOKEN = re.compile(r'(?i)x-edon-token\s*[:=]\s*[^\s,;]+')
_CREDIT_CARD = re.compile(r'\b(?:\d[ \-]?){13,15}\d\b')
_EMAIL_IN_CONTEXT = re.compile(
    r'(?i)(?:email|e-mail|mail)\s*[=:]\s*[\'"]?[\w.%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}[\'"]?'
)

# OAuth / session token fields in JSON bodies
_JSON_REFRESH_TOKEN = re.compile(r'"refresh_token"\s*:\s*"[^"]+"', re.IGNORECASE)
_JSON_ACCESS_TOKEN = re.compile(r'"access_token"\s*:\s*"[^"]+"', re.IGNORECASE)

# Stripe API keys (live and test, public and secret)
_STRIPE_KEY = re.compile(r'(?:sk|pk)_(?:live|test)_[a-zA-Z0-9]{10,}')

# GitHub personal access tokens
_GITHUB_PAT = re.compile(r'(?:ghp_|github_pat_)[a-zA-Z0-9_]{10,}')

# Tokens in URL query parameters (?token=... or &token=...)
_URL_QUERY_TOKEN = re.compile(r'(?<=[?&])token=[A-Za-z0-9._-]+')

# PHI patterns (HIPAA) — redacted as [PHI-REDACTED]
_PHI_MRN = re.compile(r'MRN[\s:#-]*\d{6,10}', re.IGNORECASE)
_PHI_MRN_LONG = re.compile(r'medical[\s_-]?record[\s_-]?number[\s:#-]*\d+', re.IGNORECASE)
_PHI_DOB = re.compile(r'\b(dob|date[\s_-]?of[\s_-]?birth|birth[\s_-]?date)[\s:]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b', re.IGNORECASE)
_PHI_SSN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_PHI_NPI = re.compile(r'\b(npi)[\s:#-]*\d{10}\b', re.IGNORECASE)
_PHI_PATIENT_ID = re.compile(r'patient[\s_-]?id[\s:#-]*[a-zA-Z0-9\-]{6,}', re.IGNORECASE)
_PHI_INSURANCE_ID = re.compile(r'\b(member[\s_-]?id|insurance[\s_-]?id|policy[\s_-]?number)[\s:#-]*[a-zA-Z0-9\-]{8,}\b', re.IGNORECASE)

_PATTERNS = [
    (_EDON_API_KEY,       '[REDACTED]'),
    (_OPENAI_SK_KEY,      '[REDACTED]'),
    (_BEARER_TOKEN,       'Bearer [REDACTED]'),
    (_JSON_PASSWORD,      '"password": "[REDACTED]"'),
    (_JSON_SECRET,        '"secret": "[REDACTED]"'),
    (_JSON_X_EDON_TOKEN,  '"X-EDON-TOKEN": "[REDACTED]"'),
    (_HEADER_X_EDON_TOKEN, 'X-EDON-TOKEN: [REDACTED]'),
    (_CREDIT_CARD,        '[REDACTED]'),
    (_EMAIL_IN_CONTEXT,   '[REDACTED]'),
    (_JSON_REFRESH_TOKEN, '"refresh_token": "[REDACTED]"'),
    (_JSON_ACCESS_TOKEN,  '"access_token": "[REDACTED]"'),
    (_STRIPE_KEY,         '[REDACTED]'),
    (_GITHUB_PAT,         '[REDACTED]'),
    (_URL_QUERY_TOKEN,    'token=[REDACTED]'),
    # PHI (HIPAA)
    (_PHI_MRN,            '[PHI-REDACTED]'),
    (_PHI_MRN_LONG,       '[PHI-REDACTED]'),
    (_PHI_DOB,            '[PHI-REDACTED]'),
    (_PHI_SSN,            '[PHI-REDACTED]'),
    (_PHI_NPI,            '[PHI-REDACTED]'),
    (_PHI_PATIENT_ID,     '[PHI-REDACTED]'),
    (_PHI_INSURANCE_ID,   '[PHI-REDACTED]'),
]


def scrub_string(s: object) -> str:
    """Apply all scrubbing patterns to a string, replacing sensitive values."""
    if not isinstance(s, str):
        return str(s)
    for pattern, replacement in _PATTERNS:
        s = pattern.sub(replacement, s)
    return s
