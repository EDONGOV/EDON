"""Integration tests for Clawdbot Gateway integration.

This test suite validates the end-to-end integration between EDON Gateway
and Clawdbot Gateway, including ALLOW and BLOCK scenarios.
"""

import os
import pytest
import requests
from typing import Dict, Any


# Test configuration
EDON_GATEWAY_URL = os.getenv("EDON_GATEWAY_URL", "http://127.0.0.1:8000")
# Use EDON_API_TOKEN if set, otherwise try EDON_GATEWAY_TOKEN, otherwise use default
EDON_API_TOKEN = os.getenv("EDON_API_TOKEN", "")
EDON_AUTH_ENABLED = os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true"
# Priority: EDON_API_TOKEN > EDON_GATEWAY_TOKEN > default test token
# Default matches common production token from start_production_gateway.ps1
EDON_GATEWAY_TOKEN = (
    EDON_API_TOKEN if EDON_API_TOKEN 
    else os.getenv("EDON_GATEWAY_TOKEN", "your-secret-token")  # Default matches production script
)
CLAWDBOT_GATEWAY_URL = os.getenv("CLAWDBOT_GATEWAY_URL", "http://127.0.0.1:18789")
CLAWDBOT_GATEWAY_TOKEN = os.getenv("CLAWDBOT_GATEWAY_TOKEN", "")


class TestClawdbotIntegration:
    """Integration tests for Clawdbot Gateway."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures."""
        # Verify Clawdbot Gateway is running
        try:
            response = requests.get(
                f"{CLAWDBOT_GATEWAY_URL}/health",
                timeout=5
            )
            if response.status_code != 200:
                pytest.skip("Clawdbot Gateway not running or not healthy")
        except requests.exceptions.RequestException:
            pytest.skip("Clawdbot Gateway not accessible")
        
        # Verify EDON Gateway is running
        try:
            response = requests.get(
                f"{EDON_GATEWAY_URL}/health",
                timeout=5
            )
            if response.status_code != 200:
                pytest.skip("EDON Gateway not running or not healthy")
        except requests.exceptions.RequestException:
            pytest.skip("EDON Gateway not accessible")
    
    def test_clawdbot_gateway_sanity_check(self):
        """Step 1: Sanity check - verify Clawdbot Gateway is accessible."""
        if not CLAWDBOT_GATEWAY_TOKEN:
            pytest.skip("CLAWDBOT_GATEWAY_TOKEN not set")
        
        response = requests.post(
            f"{CLAWDBOT_GATEWAY_URL}/tools/invoke",
            headers={
                "Authorization": f"Bearer {CLAWDBOT_GATEWAY_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "tool": "sessions_list",
                "action": "json",
                "args": {}
            },
            timeout=10
        )
        
        # Clawdbot returns 200 { ok: true, result } or 404 if tool not allowlisted
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "ok" in data, "Response missing 'ok' field"
            print(f"[OK] Clawdbot Gateway sanity check passed: {data.get('ok')}")
    
    def test_edon_allows_clawdbot_sessions_list(self):
        """Step 4: ALLOW case - benign tool invocation (sessions_list)."""
        # First, set an intent that allows clawdbot.invoke
        intent_response = requests.post(
            f"{EDON_GATEWAY_URL}/intent/set",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "objective": "List Clawdbot sessions",
                "scope": {
                    "clawdbot": ["invoke"]
                },
                "constraints": {},
                "risk_level": "low",
                "approved_by_user": True
            },
            timeout=10
        )
        
        assert intent_response.status_code == 200, f"Failed to set intent: {intent_response.text}"
        intent_data = intent_response.json()
        intent_id = intent_data["intent_id"]
        
        # Now execute the action
        execute_response = requests.post(
            f"{EDON_GATEWAY_URL}/execute",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "action": {
                    "tool": "clawdbot",
                    "op": "invoke",
                    "params": {
                        "tool": "sessions_list",
                        "action": "json",
                        "args": {}
                    }
                },
                "intent_id": intent_id,
                "agent_id": "test-agent-001"
            },
            timeout=30
        )
        
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        result = execute_response.json()
        
        # Should be ALLOW
        assert result["verdict"] == "ALLOW", f"Expected ALLOW, got {result['verdict']}: {result.get('explanation')}"
        
        # Should have execution result
        assert "execution" in result, "Missing execution result"
        execution = result["execution"]
        assert execution["tool"] == "clawdbot", "Wrong tool in execution"
        assert execution["op"] == "invoke", "Wrong op in execution"
        
        # Check Clawdbot response
        exec_result = execution.get("result", {})
        if exec_result.get("success"):
            print(f"[OK] ALLOW test passed: {exec_result.get('tool')} -> {exec_result.get('result', {}).get('ok', False)}")
        else:
            # Clawdbot may have blocked it (404 if not allowlisted), but EDON allowed it
            print(f"[OK] ALLOW test passed (EDON allowed, Clawdbot returned: {exec_result.get('error', 'unknown')})")
    
    def test_edon_blocks_risky_clawdbot_tool(self):
        """Step 4: BLOCK case - risky tool outside scope."""
        # Set an intent that only allows sessions_list
        intent_response = requests.post(
            f"{EDON_GATEWAY_URL}/intent/set",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "objective": "Limited Clawdbot access",
                "scope": {
                    "clawdbot": ["invoke"]
                },
                "constraints": {
                    "allowed_clawdbot_tools": ["sessions_list"]  # Only allow sessions_list
                },
                "risk_level": "low",
                "approved_by_user": True
            },
            timeout=10
        )
        
        assert intent_response.status_code == 200, f"Failed to set intent: {intent_response.text}"
        intent_data = intent_response.json()
        intent_id = intent_data["intent_id"]
        
        # Try to execute a risky tool (e.g., shell-like tool)
        # Note: This depends on what Clawdbot tools are available
        # For now, we'll test with a tool that's not in the allowed list
        execute_response = requests.post(
            f"{EDON_GATEWAY_URL}/execute",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "action": {
                    "tool": "clawdbot",
                    "op": "invoke",
                    "params": {
                        "tool": "web_execute",  # Risky tool (if it exists)
                        "action": "json",
                        "args": {"command": "rm -rf /"}
                    }
                },
                "intent_id": intent_id,
                "agent_id": "test-agent-001"
            },
            timeout=30
        )
        
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        result = execute_response.json()
        
        # Should be BLOCK (either by scope or by risk assessment)
        # Note: The governor may need to be updated to check allowed_clawdbot_tools constraint
        assert result["verdict"] in ["BLOCK", "ESCALATE"], \
            f"Expected BLOCK or ESCALATE, got {result['verdict']}: {result.get('explanation')}"
        
        # Should NOT have execution result (Clawdbot never receives the call)
        assert result.get("execution") is None, "Execution should not occur for BLOCK verdict"
        
        print(f"[OK] BLOCK test passed: {result['verdict']} - {result.get('explanation', '')}")
    
    def test_edon_blocks_out_of_scope_clawdbot_tool(self):
        """BLOCK case - tool not in scope."""
        # Set an intent that doesn't include clawdbot
        intent_response = requests.post(
            f"{EDON_GATEWAY_URL}/intent/set",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "objective": "Email only intent",
                "scope": {
                    "email": ["send", "draft"]
                },
                "constraints": {},
                "risk_level": "low",
                "approved_by_user": True
            },
            timeout=10
        )
        
        assert intent_response.status_code == 200, f"Failed to set intent: {intent_response.text}"
        intent_data = intent_response.json()
        intent_id = intent_data["intent_id"]
        
        # Try to execute clawdbot (not in scope)
        execute_response = requests.post(
            f"{EDON_GATEWAY_URL}/execute",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "action": {
                    "tool": "clawdbot",
                    "op": "invoke",
                    "params": {
                        "tool": "sessions_list",
                        "action": "json",
                        "args": {}
                    }
                },
                "intent_id": intent_id,
                "agent_id": "test-agent-001"
            },
            timeout=30
        )
        
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        result = execute_response.json()
        
        # Should be BLOCK due to scope violation
        assert result["verdict"] == "BLOCK", f"Expected BLOCK, got {result['verdict']}"
        assert result.get("reason_code") == "SCOPE_VIOLATION", \
            f"Expected SCOPE_VIOLATION, got {result.get('reason_code')}"
        
        # Should NOT have execution result
        assert result.get("execution") is None, "Execution should not occur for BLOCK verdict"
        
        print(f"[OK] BLOCK (scope violation) test passed: {result.get('explanation', '')}")


if __name__ == "__main__":
    # Run tests manually (without pytest)
    import sys
    
    # Create test instance
    test = TestClawdbotIntegration()
    
    # Manually run setup checks (not as pytest fixture)
    print("=" * 70)
    print("Clawdbot Integration Tests")
    print("=" * 70)
    print("")
    
    # Verify services are running
    print("Checking services...")
    try:
        # Check Clawdbot Gateway
        try:
            response = requests.get(
                f"{CLAWDBOT_GATEWAY_URL}/health",
                timeout=5
            )
            if response.status_code != 200:
                print(f"[WARNING] Clawdbot Gateway not healthy (HTTP {response.status_code})")
            else:
                print("[OK] Clawdbot Gateway accessible")
        except requests.exceptions.RequestException as e:
            print(f"[WARNING] Clawdbot Gateway not accessible: {e}")
            print("  (Some tests may be skipped)")
        
        # Check EDON Gateway
        try:
            response = requests.get(
                f"{EDON_GATEWAY_URL}/health",
                timeout=5
            )
            if response.status_code != 200:
                print(f"[FAIL] EDON Gateway not healthy (HTTP {response.status_code})")
                sys.exit(1)
            else:
                print("[OK] EDON Gateway accessible")
        except requests.exceptions.RequestException as e:
            print(f"[FAIL] EDON Gateway not accessible: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Setup failed: {e}")
        sys.exit(1)
    
    print("")
    
    # Setup credentials for clawdbot (required in production mode)
    print("Setting up Clawdbot credentials...")
    try:
        # Set credentials for clawdbot tool
        # Use environment variables if available, otherwise use placeholders
        clawdbot_url = CLAWDBOT_GATEWAY_URL
        clawdbot_token = CLAWDBOT_GATEWAY_TOKEN if CLAWDBOT_GATEWAY_TOKEN else "test-token-placeholder"
        
        cred_set_response = requests.post(
            f"{EDON_GATEWAY_URL}/credentials/set",
            headers={
                "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "credential_id": "clawdbot-gateway-test",
                "tool_name": "clawdbot",
                "credential_type": "gateway",
                "credential_data": {
                    "gateway_url": clawdbot_url,
                    "gateway_token": clawdbot_token
                }
            },
            timeout=10
        )
        
        if cred_set_response.status_code == 200:
            print("[OK] Clawdbot credentials configured")
            print(f"  URL: {clawdbot_url}")
            print(f"  Token: {'*' * 10} (hidden)")
        else:
            print(f"[WARNING] Could not set credentials: HTTP {cred_set_response.status_code}")
            if cred_set_response.status_code == 401:
                print("  Authentication failed - check your token")
            elif cred_set_response.status_code == 400:
                print(f"  Bad request: {cred_set_response.text}")
            else:
                print(f"  Response: {cred_set_response.text}")
            print("  Tests may fail if EDON_CREDENTIALS_STRICT=true")
    except Exception as e:
        print(f"[WARNING] Could not set credentials: {e}")
        print("  Tests may fail if EDON_CREDENTIALS_STRICT=true")
        import traceback
        traceback.print_exc()
    
    print("")
    
    # Check authentication configuration
    print("Checking authentication...")
    # Try to detect if gateway has auth enabled by checking a protected endpoint
    try:
        test_response = requests.post(
            f"{EDON_GATEWAY_URL}/intent/set",
            headers={"X-EDON-TOKEN": "test-invalid-token", "Content-Type": "application/json"},
            json={"objective": "test", "scope": {}, "risk_level": "low"},
            timeout=5
        )
        if test_response.status_code == 403:
            print("[OK] Authentication is enabled on gateway")
            print(f"  Using token: {EDON_GATEWAY_TOKEN[:20]}..." if len(EDON_GATEWAY_TOKEN) > 20 else f"  Using token: {EDON_GATEWAY_TOKEN}")
            if EDON_GATEWAY_TOKEN in ["test-token-123", "your-secret-token", "production-token-change-me"]:
                print("  [WARNING] Warning: Using default/placeholder token!")
                print("  If tests fail with 'Invalid authentication token', set:")
                print("    $env:EDON_API_TOKEN='your-actual-token' (PowerShell)")
        elif test_response.status_code == 401:
            print("[OK] Authentication is enabled on gateway (401 = missing token)")
            print(f"  Using token: {EDON_GATEWAY_TOKEN[:20]}..." if len(EDON_GATEWAY_TOKEN) > 20 else f"  Using token: {EDON_GATEWAY_TOKEN}")
        else:
            print("[WARNING] Authentication may be disabled (gateway accepted invalid token)")
            print(f"  Using token: {EDON_GATEWAY_TOKEN[:20]}..." if len(EDON_GATEWAY_TOKEN) > 20 else f"  Using token: {EDON_GATEWAY_TOKEN}")
    except Exception as e:
        print(f"[WARNING] Could not detect auth status: {e}")
        print(f"  Using token: {EDON_GATEWAY_TOKEN[:20]}..." if len(EDON_GATEWAY_TOKEN) > 20 else f"  Using token: {EDON_GATEWAY_TOKEN}")
    
    print("")
    
    # Check if credentials are needed (production mode)
    print("Checking credentials...")
    try:
        # Try to get credentials for clawdbot
        creds_response = requests.get(
            f"{EDON_GATEWAY_URL}/credentials/tool/clawdbot",
            headers={"X-EDON-TOKEN": EDON_GATEWAY_TOKEN},
            timeout=5
        )
        if creds_response.status_code == 404:
            # Credentials don't exist - try to set them up
            print("[WARNING] Clawdbot credentials not found in database")
            print("  Attempting to set up credentials...")
            
            # Use environment variables if available
            clawdbot_url = CLAWDBOT_GATEWAY_URL
            clawdbot_token = CLAWDBOT_GATEWAY_TOKEN or "test-token-placeholder"
            
            cred_set_response = requests.post(
                f"{EDON_GATEWAY_URL}/credentials/set",
                headers={
                    "X-EDON-TOKEN": EDON_GATEWAY_TOKEN,
                    "Content-Type": "application/json"
                },
                json={
                    "credential_id": "clawdbot-gateway-test",
                    "tool_name": "clawdbot",
                    "credential_type": "gateway",
                    "credential_data": {
                        "gateway_url": clawdbot_url,
                        "gateway_token": clawdbot_token
                    }
                },
                timeout=10
            )
            
            if cred_set_response.status_code == 200:
                print("[OK] Clawdbot credentials set up successfully")
            else:
                print(f"[WARNING] Failed to set credentials: {cred_set_response.status_code}")
                print(f"  Response: {cred_set_response.text}")
                print("  Tests may fail if EDON_CREDENTIALS_STRICT=true")
        elif creds_response.status_code == 200:
            print("[OK] Clawdbot credentials found in database")
        else:
            print(f"[WARNING] Could not check credentials: HTTP {creds_response.status_code}")
    except Exception as e:
        print(f"[WARNING] Could not check/set credentials: {e}")
        print("  Tests may fail if EDON_CREDENTIALS_STRICT=true")
    
    print("")
    print("=" * 70)
    print("")
    
    # Run tests (skip pytest fixture, run directly)
    print("1. Testing Clawdbot Gateway sanity check...")
    try:
        # Skip the pytest.skip() calls by directly calling the test logic
        if not CLAWDBOT_GATEWAY_TOKEN:
            print("[WARNING] Skipped (no token)")
        else:
            response = requests.post(
                f"{CLAWDBOT_GATEWAY_URL}/tools/invoke",
                headers={
                    "Authorization": f"Bearer {CLAWDBOT_GATEWAY_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "tool": "sessions_list",
                    "action": "json",
                    "args": {}
                },
                timeout=10
            )
            assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
            if response.status_code == 200:
                data = response.json()
                assert "ok" in data, "Response missing 'ok' field"
                print("[OK] Sanity check passed\n")
            else:
                print("[WARNING] Tool not allowlisted (404)\n")
    except Exception as e:
        print(f"[FAIL] Sanity check failed: {e}\n")
    
    print("2. Testing EDON ALLOW case...")
    try:
        test.test_edon_allows_clawdbot_sessions_list()
        print("[OK] ALLOW test passed\n")
    except AssertionError as e:
        error_msg = str(e)
        if "Invalid authentication token" in error_msg:
            print(f"[FAIL] ALLOW test failed: Authentication error")
            print(f"  If EDON_AUTH_ENABLED=true, set EDON_API_TOKEN to match your gateway token")
            print(f"  Current token: {EDON_GATEWAY_TOKEN[:20]}..." if len(EDON_GATEWAY_TOKEN) > 20 else f"  Current token: {EDON_GATEWAY_TOKEN}")
            print(f"  Set with: $env:EDON_API_TOKEN='your-actual-token' (PowerShell)")
        else:
            print(f"[FAIL] ALLOW test failed: {e}\n")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"[FAIL] ALLOW test failed: {e}\n")
        import traceback
        traceback.print_exc()
    
    print("3. Testing EDON BLOCK case (out of scope)...")
    try:
        test.test_edon_blocks_out_of_scope_clawdbot_tool()
        print("[OK] BLOCK (scope) test passed\n")
    except AssertionError as e:
        error_msg = str(e)
        if "Invalid authentication token" in error_msg:
            print(f"[FAIL] BLOCK (scope) test failed: Authentication error")
            print(f"  Set EDON_API_TOKEN to match your gateway token")
        else:
            print(f"[FAIL] BLOCK (scope) test failed: {e}\n")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"[FAIL] BLOCK (scope) test failed: {e}\n")
        import traceback
        traceback.print_exc()
    
    print("4. Testing EDON BLOCK case (risky tool)...")
    try:
        test.test_edon_blocks_risky_clawdbot_tool()
        print("[OK] BLOCK (risky) test passed\n")
    except AssertionError as e:
        error_msg = str(e)
        if "Invalid authentication token" in error_msg:
            print(f"[FAIL] BLOCK (risky) test failed: Authentication error")
            print(f"  Set EDON_API_TOKEN to match your gateway token")
        else:
            print(f"[FAIL] BLOCK (risky) test failed: {e}\n")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"[FAIL] BLOCK (risky) test failed: {e}\n")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)
    print("Integration tests complete!")
    print("=" * 70)
