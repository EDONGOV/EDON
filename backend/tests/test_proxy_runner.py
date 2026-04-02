#!/usr/bin/env python3
"""
Test script for EDON Proxy Runner endpoint.

Tests the drop-in replacement for Clawdbot Gateway /tools/invoke.
"""

import requests
import os
import json
import sys
import pytest

# Configuration
EDON_GATEWAY_URL = os.getenv("EDON_GATEWAY_URL", "http://127.0.0.1:8000")
EDON_GATEWAY_TOKEN = os.getenv("EDON_GATEWAY_TOKEN") or os.getenv("EDON_API_TOKEN", "your-secret-token")
AGENT_ID = "test-agent-proxy"


def test_proxy_allowed_tool():
    """Test proxy with an allowed tool."""
    print("\n[TEST 1] Testing ALLOW case (sessions_list)...")
    
    # First, set up an intent that allows sessions_list
    intent_response = requests.post(
        f"{EDON_GATEWAY_URL}/intent/set",
        headers={
            "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "objective": "Test proxy runner",
            "scope": {
                "clawdbot": ["invoke"]
            },
            "constraints": {
                "allowed_clawdbot_tools": ["sessions_list"]
            },
            "risk_level": "low",
            "approved_by_user": True
        },
        timeout=10
    )
    
    if intent_response.status_code != 200:
        pytest.skip(f"Could not set intent: {intent_response.text}")
    
    intent_id = intent_response.json().get("intent_id")
    print(f"  Intent ID: {intent_id}")
    
    # Test proxy endpoint
    proxy_response = requests.post(
        f"{EDON_GATEWAY_URL}/clawdbot/invoke",
        headers={
            "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
            "Content-Type": "application/json",
            "X-Agent-ID": AGENT_ID,
            "X-Intent-ID": intent_id
        },
        json={
            "tool": "sessions_list",
            "action": "json",
            "args": {}
        },
        timeout=30
    )
    
    assert proxy_response.status_code == 200, f"HTTP {proxy_response.status_code}: {proxy_response.text}"
    
    result = proxy_response.json()
    print(f"  Response: {json.dumps(result, indent=2)}")
    
    assert result.get("ok"), f"Tool was blocked: {result.get('error')}"
    print(f"  [OK] ALLOW test passed")
    print(f"  EDON verdict: {result.get('edon_verdict')}")


def test_proxy_blocked_tool():
    """Test proxy with a blocked tool."""
    print("\n[TEST 2] Testing BLOCK case (web_execute)...")
    
    # Use same intent as test 1 (only allows sessions_list)
    intent_response = requests.post(
        f"{EDON_GATEWAY_URL}/intent/set",
        headers={
            "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
            "Content-Type": "application/json"
        },
        json={
            "objective": "Test proxy runner - block risky",
            "scope": {
                "clawdbot": ["invoke"]
            },
            "constraints": {
                "allowed_clawdbot_tools": ["sessions_list"]
            },
            "risk_level": "low",
            "approved_by_user": True
        },
        timeout=10
    )
    
    if intent_response.status_code != 200:
        pytest.skip(f"Could not set intent: {intent_response.text}")
    
    intent_id = intent_response.json().get("intent_id")
    
    # Test proxy endpoint with blocked tool
    proxy_response = requests.post(
        f"{EDON_GATEWAY_URL}/clawdbot/invoke",
        headers={
            "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
            "Content-Type": "application/json",
            "X-Agent-ID": AGENT_ID,
            "X-Intent-ID": intent_id
        },
        json={
            "tool": "web_execute",
            "action": "json",
            "args": {"command": "rm -rf /"}
        },
        timeout=30
    )
    
    assert proxy_response.status_code == 200, f"HTTP {proxy_response.status_code}: {proxy_response.text}"
    
    result = proxy_response.json()
    print(f"  Response: {json.dumps(result, indent=2)}")
    
    assert not result.get("ok") and result.get("edon_verdict") == "BLOCK", "Tool was not blocked (should be BLOCK)"
    print(f"  [OK] BLOCK test passed")
    print(f"  Blocked reason: {result.get('error')}")


def test_proxy_schema_compatibility():
    """Test that proxy accepts exact Clawdbot schema."""
    print("\n[TEST 3] Testing schema compatibility...")
    
    # Test with all Clawdbot fields
    proxy_response = requests.post(
        f"{EDON_GATEWAY_URL}/clawdbot/invoke",
        headers={
            "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
            "Content-Type": "application/json",
            "X-Agent-ID": AGENT_ID
        },
        json={
            "tool": "sessions_list",
            "action": "json",
            "args": {"test": "value"},
            "sessionKey": "test-session-123"
        },
        timeout=30
    )
    
    assert proxy_response.status_code == 200, f"HTTP {proxy_response.status_code}: {proxy_response.text}"
    print(f"  [OK] Schema compatibility test passed")
    print(f"  Response: {json.dumps(proxy_response.json(), indent=2)}")


def main():
    """Run all proxy tests."""
    print("=" * 70)
    print("EDON Proxy Runner Tests")
    print("=" * 70)
    
    # Check gateway is accessible
    try:
        health_response = requests.get(f"{EDON_GATEWAY_URL}/health", timeout=5)
        if health_response.status_code != 200:
            print(f"[FAIL] Gateway not healthy: HTTP {health_response.status_code}")
            sys.exit(1)
        print("[OK] Gateway accessible")
    except Exception as e:
        print(f"[FAIL] Gateway not accessible: {e}")
        sys.exit(1)
    
    # Run tests
    results = []
    results.append(("Schema Compatibility", test_proxy_schema_compatibility()))
    results.append(("ALLOW Case", test_proxy_allowed_tool()))
    results.append(("BLOCK Case", test_proxy_blocked_tool()))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    for test_name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n[SUCCESS] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
