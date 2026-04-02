#!/usr/bin/env python3
"""
Example: Migrating from Clawdbot Gateway to EDON Proxy.

This script shows how to migrate your code in 5 minutes.
"""

import requests

# ============================================================================
# BEFORE: Direct Clawdbot Gateway Call
# ============================================================================

def old_clawdbot_call():
    """Old way - calling Clawdbot Gateway directly."""
    response = requests.post(
        "http://clawdbot-gateway:18789/tools/invoke",
        headers={
            "Authorization": "Bearer your-clawdbot-token",
            "Content-Type": "application/json"
        },
        json={
            "tool": "sessions_list",
            "action": "json",
            "args": {}
        }
    )
    return response.json()


# ============================================================================
# AFTER: EDON Proxy Call (Drop-in Replacement)
# ============================================================================

def new_edon_proxy_call():
    """New way - calling EDON Proxy (drop-in replacement)."""
    response = requests.post(
        "http://edon-gateway:8000/clawdbot/invoke",  # Changed URL
        headers={
            "X-EDON-TOKEN": "your-edon-token",  # Changed header
            "Content-Type": "application/json",
            "X-Agent-ID": "your-agent-id"  # Optional but recommended
        },
        json={
            "tool": "sessions_list",  # Same body!
            "action": "json",
            "args": {}
        }
    )
    return response.json()


# ============================================================================
# Using the Client Library (Recommended)
# ============================================================================

from edon_gateway.clients.clawdbot_proxy_client import EDONClawdbotProxyClient

def using_client_library():
    """Best way - use the client library."""
    client = EDONClawdbotProxyClient(
        edon_gateway_url="http://edon-gateway:8000",
        edon_token="your-edon-token",
        agent_id="your-agent-id"
    )
    
    # Same API as Clawdbot client!
    result = client.invoke(
        tool="sessions_list",
        action="json",
        args={}
    )
    
    if result["ok"]:
        print("Success:", result["result"])
        print("EDON verdict:", result["edon_verdict"])
    else:
        print("Blocked:", result["error"])
        print("EDON explanation:", result["edon_explanation"])
    
    return result


# ============================================================================
# Migration Checklist
# ============================================================================

"""
Migration Checklist (5 minutes):

1. Set up EDON Gateway
   - Start gateway: python -m edon_gateway.main
   - Or use: ./edon_gateway/start_production_gateway.ps1

2. Configure Clawdbot credentials
   - POST /credentials/set with Clawdbot Gateway URL and token

3. Set up intent/policy
   - POST /intent/set with allowed_clawdbot_tools constraint

4. Change your code:
   - URL: clawdbot-gateway:18789/tools/invoke → edon-gateway:8000/clawdbot/invoke
   - Header: Authorization: Bearer <token> → X-EDON-TOKEN: <token>
   - Add: X-Agent-ID: <your-agent-id> (optional)

5. Test:
   - Try a benign tool (sessions_list)
   - Verify blocked tools return proper errors

That's it! Zero code changes except URL and headers.
"""

if __name__ == "__main__":
    print("This is an example migration script.")
    print("See PROXY_RUNNER_GUIDE.md for full documentation.")
