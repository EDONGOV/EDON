"""PHI endpoint allowlist — prevents AI agents from sending data to unauthorized URLs.

Stores a per-tenant list of approved URL patterns on disk (same volume as the DB).
Any action whose params contain a URL not matching the allowlist is BLOCKED with
an audit-ready reason before the governor even runs.

Pattern matching:
- Exact match:  "https://ehr.acmehospital.com"
- Prefix match: "https://ehr.acmehospital.com/*"  (trailing * = any suffix)
- Domain match: "*.acmehospital.com"               (* prefix = any subdomain)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

# URL extraction: find anything that looks like http(s):// in string values
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def _data_dir() -> Path:
    """Resolve the same data directory the DB lives in."""
    url = os.getenv("EDON_DB_URL", "").strip()
    if url.startswith("sqlite:///"):
        p = Path(url.replace("sqlite:///", "", 1)).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path("/data")
    if p.exists():
        return p
    p = Path("/tmp/edon_data")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _allowlist_path(tenant_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", tenant_id)
    return _data_dir() / f"phi_allowlist_{safe}.json"


def load_allowlist(tenant_id: str) -> List[Dict[str, Any]]:
    """Return the list of allowlist entries for a tenant. Empty list = not configured."""
    path = _allowlist_path(tenant_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("phi_allowlist: failed to load for tenant=%s: %s", tenant_id, exc)
        return []


def save_allowlist(tenant_id: str, entries: List[Dict[str, Any]]) -> None:
    path = _allowlist_path(tenant_id)
    path.write_text(json.dumps(entries, indent=2))


def add_entry(tenant_id: str, pattern: str, label: str = "", added_by: str = "") -> Dict[str, Any]:
    """Add a URL pattern to the allowlist. Returns the new entry."""
    entries = load_allowlist(tenant_id)
    # Deduplicate
    if any(e["pattern"] == pattern for e in entries):
        raise ValueError(f"Pattern '{pattern}' already in allowlist")
    entry: Dict[str, Any] = {
        "id": f"phi_{len(entries)+1}_{abs(hash(pattern)) % 100000}",
        "pattern": pattern,
        "label": label or pattern,
        "added_by": added_by,
        "added_at": datetime.now(UTC).isoformat(),
    }
    entries.append(entry)
    save_allowlist(tenant_id, entries)
    return entry


def remove_entry(tenant_id: str, entry_id: str) -> bool:
    entries = load_allowlist(tenant_id)
    new_entries = [e for e in entries if e["id"] != entry_id]
    if len(new_entries) == len(entries):
        return False
    save_allowlist(tenant_id, new_entries)
    return True


def _matches_pattern(url: str, pattern: str) -> bool:
    """Check if a URL matches a pattern (exact, prefix *, or domain *)."""
    if pattern.endswith("/*"):
        return url.startswith(pattern[:-1])
    if pattern.startswith("*."):
        domain_suffix = pattern[1:]  # e.g. ".acmehospital.com"
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower()
            return host.endswith(domain_suffix) or host == domain_suffix.lstrip(".")
        except Exception:
            return False
    return url.lower().rstrip("/") == pattern.lower().rstrip("/")


def _extract_urls(obj: Any, depth: int = 0) -> List[str]:
    """Recursively find all URL strings in a params dict."""
    if depth > 5:
        return []
    urls: List[str] = []
    if isinstance(obj, str):
        urls.extend(_URL_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            urls.extend(_extract_urls(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj[:20]:
            urls.extend(_extract_urls(item, depth + 1))
    return urls


def check_params(
    tenant_id: str,
    params: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check action params for unauthorized URLs.

    Returns:
        (allowed, blocked_url, audit_reason)
        allowed=True means no violation found.
    """
    entries = load_allowlist(tenant_id)
    # If no allowlist configured, pass through (opt-in enforcement)
    if not entries:
        return True, None, None

    urls = _extract_urls(params)
    if not urls:
        return True, None, None

    patterns = [e["pattern"] for e in entries]
    for url in urls:
        if not any(_matches_pattern(url, p) for p in patterns):
            reason = (
                f"Action blocked — agent attempted to send data to unauthorized endpoint: {url[:120]}. "
                f"This endpoint is not in your PHI-approved URL allowlist. "
                f"Add it via POST /compliance/phi-allowlist if this is intentional. "
                f"Policy: PHI-EXFIL-001 (HIPAA §164.312 Transmission Security)"
            )
            return False, url, reason

    return True, None, None
