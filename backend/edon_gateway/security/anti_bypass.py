"""
Anti-Bypass Security Module

Prevents agents/users from bypassing EDON Gateway and calling Clawdbot Gateway directly.

Two approaches:
1. Network Gating: Clawdbot Gateway on private network, only EDON can reach it
2. Token Hardening: Clawdbot tokens stored only in EDON, never exposed to agents
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class AntiBypassConfig:
    """Configuration for anti-bypass measures."""
    
    def __init__(self):
        # Network gating: If enabled, Clawdbot Gateway should only be accessible
        # from EDON Gateway's network (not from public internet)
        self.network_gating_enabled = os.getenv("EDON_NETWORK_GATING", "false").lower() == "true"
        
        # Token hardening: If enabled, Clawdbot tokens are NEVER exposed to agents
        # They're only stored in EDON database and used internally
        self.token_hardening_enabled = os.getenv("EDON_TOKEN_HARDENING", "true").lower() == "true"
        
        # Credential strict mode: Requires all credentials in database
        # This is a prerequisite for token hardening
        self.credentials_strict = os.getenv("EDON_CREDENTIALS_STRICT", "false").lower() == "true"
        
        # Validation: Token hardening requires credentials strict mode
        if self.token_hardening_enabled and not self.credentials_strict:
            logger.warning(
                "EDON_TOKEN_HARDENING=true but EDON_CREDENTIALS_STRICT=false. "
                "Token hardening requires strict credential mode. "
                "Setting EDON_CREDENTIALS_STRICT=true is recommended."
            )
    
    def is_bypass_resistant(self) -> bool:
        """Check if anti-bypass measures are active."""
        return self.network_gating_enabled or self.token_hardening_enabled
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current security configuration status."""
        return {
            "network_gating": {
                "enabled": self.network_gating_enabled,
                "description": "Clawdbot Gateway on private network, only EDON can access"
            },
            "token_hardening": {
                "enabled": self.token_hardening_enabled,
                "description": "Clawdbot tokens stored only in EDON, never exposed to agents"
            },
            "credentials_strict": {
                "enabled": self.credentials_strict,
                "description": "All credentials must be in database (required for token hardening)"
            },
            "bypass_resistant": self.is_bypass_resistant(),
            "recommendations": self._get_recommendations()
        }
    
    def _get_recommendations(self) -> list:
        """Get security recommendations based on current config."""
        recommendations = []
        
        if not self.is_bypass_resistant():
            recommendations.append(
                "Enable anti-bypass: Set EDON_NETWORK_GATING=true or EDON_TOKEN_HARDENING=true"
            )
        
        if self.token_hardening_enabled and not self.credentials_strict:
            recommendations.append(
                "Enable EDON_CREDENTIALS_STRICT=true for full token hardening protection"
            )
        
        if not self.network_gating_enabled:
            recommendations.append(
                "Consider network gating: Place Clawdbot Gateway on private network, "
                "only accessible from EDON Gateway"
            )
        
        return recommendations


def validate_anti_bypass_setup() -> Dict[str, Any]:
    """Validate that anti-bypass measures are properly configured.
    
    Returns:
        Validation result with status and recommendations
    """
    config = AntiBypassConfig()
    status = config.get_security_status()
    
    # Check if credentials are in database (for token hardening)
    credentials_ok = True
    if config.token_hardening_enabled:
        try:
            from ..persistence import get_db
            db = get_db()
            clawdbot_creds = db.get_credentials_by_tool("clawdbot")
            if not clawdbot_creds:
                credentials_ok = False
                status["warnings"] = [
                    "Token hardening enabled but no Clawdbot credentials found in database. "
                    "Set credentials via POST /credentials/set"
                ]
        except Exception as e:
            logger.error(f"Error checking credentials: {e}")
            credentials_ok = False
    
    status["validation"] = {
        "credentials_configured": credentials_ok,
        "secure": config.is_bypass_resistant() and credentials_ok
    }
    
    return status


def get_bypass_resistance_score() -> Dict[str, Any]:
    """Calculate a bypass resistance score (0-100).
    
    Higher score = more resistant to bypass attempts.
    """
    config = AntiBypassConfig()
    score = 0
    factors = []
    
    # Network gating: 50 points
    if config.network_gating_enabled:
        score += 50
        factors.append("Network gating enabled (+50)")
    else:
        factors.append("Network gating disabled (0)")
    
    # Token hardening: 40 points
    if config.token_hardening_enabled:
        score += 40
        factors.append("Token hardening enabled (+40)")
    else:
        factors.append("Token hardening disabled (0)")
    
    # Credentials strict: 10 points
    if config.credentials_strict:
        score += 10
        factors.append("Credentials strict mode enabled (+10)")
    else:
        factors.append("Credentials strict mode disabled (0)")
    
    # Check if credentials actually exist
    try:
        from ..persistence import get_db
        db = get_db()
        clawdbot_creds = db.get_credentials_by_tool("clawdbot")
        if clawdbot_creds:
            factors.append("Clawdbot credentials configured in database")
        else:
            factors.append("WARNING: No Clawdbot credentials in database")
    except:
        pass
    
    return {
        "score": score,
        "max_score": 100,
        "factors": factors,
        "level": _get_security_level(score)
    }


def _get_security_level(score: int) -> str:
    """Get security level description based on score."""
    if score >= 90:
        return "Excellent - Highly resistant to bypass"
    elif score >= 70:
        return "Good - Resistant to bypass"
    elif score >= 50:
        return "Moderate - Some bypass protection"
    elif score >= 20:
        return "Weak - Minimal bypass protection"
    else:
        return "Critical - No bypass protection"


# Network gating validation (for deployment documentation)
NETWORK_GATING_GUIDE = """
Network Gating Setup Guide
==========================

To prevent agents from bypassing EDON Gateway and calling Clawdbot Gateway directly:

1. Place Clawdbot Gateway on private network
   - Clawdbot Gateway should NOT be accessible from public internet
   - Only EDON Gateway should be able to reach it
   - Use firewall rules or network segmentation

2. Configure EDON Gateway network access
   - EDON Gateway must be able to reach Clawdbot Gateway
   - Use internal DNS or IP addresses
   - Example: http://clawdbot-gateway.internal:18789

3. Verify network isolation
   - Test: Try to reach Clawdbot Gateway from agent's network
   - Should fail with connection refused/timeout
   - Only EDON Gateway should succeed

4. Enable network gating flag
   - Set EDON_NETWORK_GATING=true
   - This enables additional validation and logging

Example Docker Compose network setup:
  networks:
    public:
      # Agents connect here
    private:
      # Clawdbot Gateway here, not accessible from public
      internal: true
"""


# Token hardening validation
TOKEN_HARDENING_GUIDE = """
Token Hardening Setup Guide
===========================

To prevent agents from obtaining Clawdbot tokens:

1. Enable credentials strict mode
   - Set EDON_CREDENTIALS_STRICT=true
   - All credentials must be in database
   - No fallback to environment variables

2. Store Clawdbot token in EDON database
   - Use POST /credentials/set
   - Never expose token to agents/users
   - Token only used internally by EDON Gateway

3. Enable token hardening
   - Set EDON_TOKEN_HARDENING=true
   - Additional validation and logging enabled

4. Verify token security
   - Check: No Clawdbot tokens in environment variables
   - Check: No tokens in agent code/config
   - Check: Tokens only in EDON database

Security Properties:
  - Agents cannot see Clawdbot tokens
  - Even if agent code is compromised, tokens are safe
  - Tokens are rotated/changed in EDON, not in agent configs
"""
