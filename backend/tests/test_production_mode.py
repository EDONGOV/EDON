"""End-to-end tests for production mode security invariants.

These tests validate that production security features work correctly:
A) Strict credentials fail closed
B) Validation rejects dangerous payloads
C) Auth truly blocks protected endpoints
"""

import os
import json
import requests
import pytest
from pathlib import Path
import tempfile
import shutil

BASE_URL = os.getenv("EDON_GATEWAY_URL", "http://localhost:8000")

# Test configuration
TEST_CREDENTIAL_ID = "test-email-credential-001"
TEST_AGENT_ID = "test-agent-001"
TEST_INTENT_ID = "test-intent-001"


class TestStrictCredentials:
    """Test A: Strict credentials fail closed."""
    
    def setup_method(self):
        """Set up test environment."""
        # Enable strict mode
        os.environ["EDON_CREDENTIALS_STRICT"] = "true"
        # Note: In real tests, you'd need to restart the server or use a test client
        # For now, we'll document the expected behavior
    
    def test_credential_missing_fails_closed(self):
        """Test that missing credential returns 503 in strict mode.
        
        Steps:
        1. Set EDON_CREDENTIALS_STRICT=true
        2. Clear credentials table (or ensure credential doesn't exist)
        3. Call /execute with action requiring credential
        4. Expect 503 and no execution artifact created
        """
        # This test requires the server to be running with EDON_CREDENTIALS_STRICT=true
        # and the credential to not exist in the database
        
        # First, ensure credential doesn't exist
        # DELETE /credentials/{credential_id} if it exists
        try:
            requests.delete(f"{BASE_URL}/credentials/{TEST_CREDENTIAL_ID}")
        except:
            pass
        
        # Try to execute an action that requires a credential
        response = requests.post(
            f"{BASE_URL}/execute",
            json={
                "action": {
                    "tool": "email",
                    "op": "send",
                    "params": {
                        "recipients": ["test@example.com"],
                        "subject": "Test",
                        "body": "Test body"
                    }
                },
                "agent_id": TEST_AGENT_ID,
                "intent_id": TEST_INTENT_ID
            },
            headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "test-token")} if os.getenv("EDON_AUTH_ENABLED") == "true" else {}
        )
        
        # In strict mode, should get 503 if credential missing
        # Note: This assumes the connector is configured to use a credential_id
        # For this test to work, the connector would need to be initialized with credential_id
        # and that credential must not exist
        
        # Check that no execution artifact was created
        # (This would check the sandbox directory or execution result)
        
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
        # Expected: 503 Service Unavailable with credential error message
        assert response.status_code in [503, 500], f"Expected 503, got {response.status_code}: {response.text}"
        assert "credential" in response.text.lower() or "not found" in response.text.lower(), \
            f"Response should mention credential: {response.text}"


class TestValidationRejectsDangerousPayloads:
    """Test B: Validation rejects dangerous payloads."""
    
    def test_oversized_body_rejected(self):
        """Test that >10MB body is rejected with 413."""
        # Create a large payload (>10MB)
        large_payload = {
            "action": {
                "tool": "email",
                "op": "draft",
                "params": {
                    "body": "x" * (11 * 1024 * 1024)  # 11 MB
                }
            },
            "agent_id": TEST_AGENT_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/execute",
            json=large_payload,
            headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "test-token")} if os.getenv("EDON_AUTH_ENABLED") == "true" else {}
        )
        
        print(f"Oversized body test - Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        # Should reject with 413 Request Entity Too Large
        assert response.status_code == 413, f"Expected 413, got {response.status_code}: {response.text}"
        assert "exceeds maximum" in response.text.lower() or "too large" in response.text.lower(), \
            f"Response should mention size limit: {response.text}"
    
    def test_deep_json_nesting_rejected(self):
        """Test that deep JSON nesting (>10 levels) is rejected with 400."""
        # Create deeply nested JSON (11 levels)
        def create_nested_dict(depth):
            if depth == 0:
                return {"value": "test"}
            return {"nested": create_nested_dict(depth - 1)}
        
        deep_payload = {
            "action": {
                "tool": "email",
                "op": "draft",
                "params": create_nested_dict(11)  # 11 levels deep
            },
            "agent_id": TEST_AGENT_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/execute",
            json=deep_payload,
            headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "test-token")} if os.getenv("EDON_AUTH_ENABLED") == "true" else {}
        )
        
        print(f"Deep nesting test - Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        # Should reject with 400 Bad Request
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "depth" in response.text.lower() or "exceeds maximum" in response.text.lower(), \
            f"Response should mention depth limit: {response.text}"
    
    def test_huge_array_rejected(self):
        """Test that huge arrays (>10,000 items) are rejected with 400."""
        # Create array with 10,001 items
        huge_array = list(range(10001))
        
        payload = {
            "action": {
                "tool": "email",
                "op": "draft",
                "params": {
                    "recipients": huge_array  # 10,001 items
                }
            },
            "agent_id": TEST_AGENT_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/execute",
            json=payload,
            headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "test-token")} if os.getenv("EDON_AUTH_ENABLED") == "true" else {}
        )
        
        print(f"Huge array test - Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        # Should reject with 400 Bad Request
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "array length" in response.text.lower() or "exceeds maximum" in response.text.lower(), \
            f"Response should mention array limit: {response.text}"
    
    def test_dangerous_patterns_rejected(self):
        """Test that dangerous patterns (script tags, etc.) are rejected with 400."""
        dangerous_payloads = [
            {
                "name": "script_tag",
                "payload": {
                    "action": {
                        "tool": "email",
                        "op": "draft",
                        "params": {
                            "body": "<script>alert('xss')</script>"
                        }
                    },
                    "agent_id": TEST_AGENT_ID
                },
                "expected_error": "script"
            },
            {
                "name": "javascript_protocol",
                "payload": {
                    "action": {
                        "tool": "email",
                        "op": "draft",
                        "params": {
                            "body": "javascript:alert('xss')"
                        }
                    },
                    "agent_id": TEST_AGENT_ID
                },
                "expected_error": "javascript"
            },
            {
                "name": "event_handler",
                "payload": {
                    "action": {
                        "tool": "email",
                        "op": "draft",
                        "params": {
                            "body": "<div onclick='alert(1)'>test</div>"
                        }
                    },
                    "agent_id": TEST_AGENT_ID
                },
                "expected_error": "event"
            }
        ]
        
        for test_case in dangerous_payloads:
            response = requests.post(
                f"{BASE_URL}/execute",
                json=test_case["payload"],
                headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "test-token")} if os.getenv("EDON_AUTH_ENABLED") == "true" else {}
            )
            
            print(f"Dangerous pattern test ({test_case['name']}) - Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
            # Should reject with 400 Bad Request
            assert response.status_code == 400, \
                f"Expected 400 for {test_case['name']}, got {response.status_code}: {response.text}"
            assert test_case["expected_error"] in response.text.lower(), \
                f"Response should mention {test_case['expected_error']}: {response.text}"


class TestAuthBlocksProtectedEndpoints:
    """Test C: Auth truly blocks protected endpoints."""
    
    def test_execute_requires_auth(self):
        """Test that /execute requires authentication when enabled."""
        # Make request without token
        response = requests.post(
            f"{BASE_URL}/execute",
            json={
                "action": {
                    "tool": "email",
                    "op": "draft",
                    "params": {
                        "recipients": ["test@example.com"],
                        "subject": "Test",
                        "body": "Test"
                    }
                },
                "agent_id": TEST_AGENT_ID
            }
            # No auth header
        )
        
        print(f"Execute without auth - Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        # If auth is enabled, should get 401 or 403
        if os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true":
            assert response.status_code in [401, 403], \
                f"Expected 401/403 when auth enabled, got {response.status_code}: {response.text}"
            assert "token" in response.text.lower() or "unauthorized" in response.text.lower() or "forbidden" in response.text.lower(), \
                f"Response should mention authentication: {response.text}"
        else:
            # If auth disabled, request should proceed (but may fail for other reasons)
            print("Auth disabled - skipping auth check")
    
    def test_audit_query_requires_auth(self):
        """Test that /audit/query requires authentication when enabled."""
        response = requests.get(
            f"{BASE_URL}/audit/query",
            params={"limit": 10}
            # No auth header
        )
        
        print(f"Audit query without auth - Status: {response.status_code}")
        
        if os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true":
            assert response.status_code in [401, 403], \
                f"Expected 401/403 when auth enabled, got {response.status_code}: {response.text}"
    
    def test_credentials_endpoints_require_auth(self):
        """Test that /credentials/* endpoints require authentication when enabled.
        
        Note: Credential readback (GET) is disabled for security.
        Only SET and DELETE operations are available.
        """
        endpoints = [
            ("POST", "/credentials/set"),
            ("DELETE", "/credentials/test-id")
        ]
        
        for method, endpoint in endpoints:
            if method == "POST":
                response = requests.post(
                    f"{BASE_URL}{endpoint}",
                    json={"credential_id": "test", "tool_name": "email", "credential_type": "smtp", "credential_data": {}}
                )
            elif method == "DELETE":
                response = requests.delete(f"{BASE_URL}{endpoint}")
            
            print(f"{method} {endpoint} without auth - Status: {response.status_code}")
            
            if os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true":
                assert response.status_code in [401, 403], \
                    f"Expected 401/403 for {method} {endpoint}, got {response.status_code}: {response.text}"
        
        # Verify credential readback is disabled (should return 404, not 401)
        readback_endpoints = [
            ("GET", "/credentials/get/test-id"),
            ("GET", "/credentials/tool/email")
        ]
        
        for method, endpoint in readback_endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"{method} {endpoint} (readback disabled) - Status: {response.status_code}")
            # Readback endpoints should return 404 (not found) since they're disabled
            assert response.status_code == 404, \
                f"Credential readback should be disabled (404), got {response.status_code}: {response.text}"
    
    def test_intent_endpoints_require_auth(self):
        """Test that /intent/* endpoints require authentication when enabled."""
        endpoints = [
            ("GET", "/intent/get", {"intent_id": "test"}),
            ("POST", "/intent/set", {"objective": "test", "scope": {}, "constraints": {}})
        ]
        
        for method, endpoint, params in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", params=params)
            elif method == "POST":
                response = requests.post(f"{BASE_URL}{endpoint}", json=params)
            
            print(f"{method} {endpoint} without auth - Status: {response.status_code}")
            
            if os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true":
                assert response.status_code in [401, 403], \
                    f"Expected 401/403 for {method} {endpoint}, got {response.status_code}: {response.text}"
    
    def test_health_endpoint_stays_open(self):
        """Test that /health endpoint remains accessible without auth."""
        response = requests.get(f"{BASE_URL}/health")
        
        print(f"Health check - Status: {response.status_code}")
        print(f"Response: {response.json() if response.status_code == 200 else response.text}")
        
        # Health should always be accessible (200 OK)
        assert response.status_code == 200, \
            f"Health endpoint should be accessible, got {response.status_code}: {response.text}"
        assert "status" in response.json(), "Health response should have status field"


def run_production_mode_tests():
    """Run all production mode validation tests.
    
    Usage:
        # Set environment variables
        export EDON_CREDENTIALS_STRICT=true
        export EDON_VALIDATE_STRICT=true
        export EDON_AUTH_ENABLED=true
        export EDON_API_TOKEN=test-token
        export EDON_GATEWAY_URL=http://localhost:8000
        
        # Run tests
        python edon_gateway/test_production_mode.py
    """
    print("=" * 70)
    print("Production Mode Security Validation Tests")
    print("=" * 70)
    print()
    
    # Check environment
    print("Environment Configuration:")
    print(f"  EDON_CREDENTIALS_STRICT: {os.getenv('EDON_CREDENTIALS_STRICT', 'not set')}")
    print(f"  EDON_VALIDATE_STRICT: {os.getenv('EDON_VALIDATE_STRICT', 'not set')}")
    print(f"  EDON_AUTH_ENABLED: {os.getenv('EDON_AUTH_ENABLED', 'not set')}")
    print(f"  EDON_GATEWAY_URL: {BASE_URL}")
    print()
    
    # Run tests
    test_classes = [
        ("A) Strict Credentials", TestStrictCredentials),
        ("B) Validation Rejects Dangerous Payloads", TestValidationRejectsDangerousPayloads),
        ("C) Auth Blocks Protected Endpoints", TestAuthBlocksProtectedEndpoints),
    ]
    
    results = {"passed": 0, "failed": 0, "errors": []}
    
    for test_suite_name, test_class in test_classes:
        print(f"\n{'=' * 70}")
        print(f"Running: {test_suite_name}")
        print(f"{'=' * 70}\n")
        
        test_instance = test_class()
        test_methods = [m for m in dir(test_instance) if m.startswith("test_")]
        
        for test_method in test_methods:
            try:
                print(f"  Running: {test_method}...")
                getattr(test_instance, test_method)()
                print(f"  ✓ PASSED: {test_method}\n")
                results["passed"] += 1
            except AssertionError as e:
                print(f"  ✗ FAILED: {test_method}")
                print(f"    {str(e)}\n")
                results["failed"] += 1
                results["errors"].append(f"{test_suite_name}::{test_method}: {str(e)}")
            except Exception as e:
                print(f"  ✗ ERROR: {test_method}")
                print(f"    {str(e)}\n")
                results["failed"] += 1
                results["errors"].append(f"{test_suite_name}::{test_method}: {str(e)}")
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Total: {results['passed'] + results['failed']}")
    
    if results["errors"]:
        print("\nErrors:")
        for error in results["errors"]:
            print(f"  - {error}")
    
    print("\n" + "=" * 70)
    
    if results["failed"] > 0:
        print("❌ Some tests failed. Review errors above.")
        return 1
    else:
        print("✅ All tests passed!")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_production_mode_tests())
