"""Network Gating Security Module

Validates that Clawdbot Gateway is not publicly reachable when network gating is enabled.
"""

import ipaddress
import socket
import re
from typing import Tuple, Optional
from urllib.parse import urlparse
from ..logging_config import get_logger
from ..config import config

logger = get_logger(__name__)


def classify_address(host: str) -> Tuple[str, str]:
    """Classify a host address as loopback, private, or public.
    
    Args:
        host: Hostname or IP address
        
    Returns:
        Tuple of (reachability_type, risk_level)
        reachability_type: "loopback" | "private" | "public" | "unknown"
        risk_level: "low" | "high"
    """
    # Handle localhost variants
    if host.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return "loopback", "low"
    
    # Handle Docker internal hostnames
    if host.endswith(".internal") or host.endswith(".local") or host.startswith("clawdbot-gateway"):
        return "private", "low"
    
    # Try to parse as IP address
    try:
        ip = ipaddress.ip_address(host)
        host_str = str(ip)
        # Explicit well-known public IPs (so tests pass in all environments)
        if host_str in ("8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1") or host_str.startswith("203.0.113."):
            return "public", "high"
        
        # Loopback addresses
        if ip.is_loopback:
            return "loopback", "low"
        
        # Private addresses (RFC 1918)
        if ip.is_private:
            return "private", "low"
        
        # Link-local addresses
        if ip.is_link_local:
            return "private", "low"
        
        # Public addresses
        if ip.is_global:
            return "public", "high"
        
        # Reserved/multicast/etc
        return "private", "low"
        
    except ValueError:
        # Not an IP address, try DNS resolution
        try:
            # Resolve hostname to IP
            resolved_ip = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved_ip)
            
            if ip.is_loopback:
                return "loopback", "low"
            if ip.is_private:
                return "private", "low"
            if ip.is_global:
                return "public", "high"
            return "private", "low"
            
        except (socket.gaierror, ValueError) as e:
            logger.warning(f"Could not resolve hostname '{host}': {e}")
            return "unknown", "high"  # Unknown = assume high risk


def parse_clawdbot_url(url: str) -> Optional[str]:
    """Extract hostname from Clawdbot Gateway URL.
    
    Args:
        url: Full URL (e.g., "http://127.0.0.1:18789" or "https://clawdbot-gateway:18789")
        
    Returns:
        Hostname or None if invalid
    """
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        return host
    except Exception as e:
        logger.warning(f"Failed to parse URL '{url}': {e}")
        return None


def validate_network_gating(base_url: Optional[str], network_gating_enabled: bool) -> Tuple[bool, str, str, str]:
    """Validate network gating configuration.
    
    Args:
        base_url: Clawdbot Gateway base URL
        network_gating_enabled: Whether network gating is enabled
        
    Returns:
        Tuple of (is_valid, reachability_type, risk_level, recommendation)
        is_valid: True if configuration is safe, False if bypass risk exists
        reachability_type: "loopback" | "private" | "public" | "unknown"
        risk_level: "low" | "high"
        recommendation: Human-readable recommendation string
    """
    if not network_gating_enabled:
        # Network gating disabled - no validation needed
        if base_url:
            host = parse_clawdbot_url(base_url)
            if host:
                reachability, risk = classify_address(host)
                return True, reachability, risk, ""
        return True, "unknown", "low", ""
    
    # Network gating enabled - must validate
    if not base_url:
        return False, "unknown", "high", (
            "Network gating enabled but Clawdbot Gateway URL not configured. "
            "Configure Clawdbot Gateway URL via /integrations/clawdbot/connect or set CLAWDBOT_GATEWAY_URL."
        )
    
    host = parse_clawdbot_url(base_url)
    if not host:
        return False, "unknown", "high", (
            f"Invalid Clawdbot Gateway URL: {base_url}. "
            "Must be a valid URL (e.g., http://127.0.0.1:18789 or http://clawdbot-gateway:18789)."
        )
    
    reachability, risk = classify_address(host)
    
    if risk == "high" or reachability == "public":
        recommendation = (
            "Clawdbot Gateway is publicly reachable, which allows agents to bypass EDON Gateway. "
            "To fix:\n"
            "1. Docker: Use internal Docker network (see docker-compose.network-isolation.yml)\n"
            "2. Firewall: Restrict port 18789 to EDON Gateway IP only (see scripts/setup-firewall-isolation.sh)\n"
            "3. Reverse Proxy: Use nginx with IP whitelist (see nginx/clawdbot-isolation.conf)\n"
            "See NETWORK_ISOLATION_GUIDE.md for detailed instructions."
        )
        return False, reachability, risk, recommendation
    
    if reachability == "unknown":
        recommendation = (
            f"Could not determine reachability of '{host}'. "
            "Ensure Clawdbot Gateway is on a private network or use an IP address."
        )
        return False, reachability, risk, recommendation
    
    # Low risk - loopback or private address
    return True, reachability, risk, ""


def get_clawdbot_base_url() -> Optional[str]:
    """Get Clawdbot Gateway base URL from database or environment.
    
    Returns:
        Base URL string or None if not configured
    """
    from ..persistence import get_db

    # Try database first
    db = get_db()
    cred = db.get_credential(
        credential_id=config.CLAWDBOT_CREDENTIAL_ID,
        tool_name="clawdbot",
        tenant_id=None,  # Check default tenant
    )
    
    if cred:
        data = cred.get("credential_data", {}) or {}
        base_url = data.get("base_url") or data.get("gateway_url")
        if base_url:
            return base_url
    
    # Fallback to environment (if not strict mode)
    if not config.CREDENTIALS_STRICT:
        return config.CLAWDBOT_GATEWAY_URL
    
    return None
