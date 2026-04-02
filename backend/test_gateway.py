"""Quick test script for EDON Gateway."""

import requests
import json

BASE_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint."""
    print("Testing /health...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_set_intent():
    """Test setting an intent."""
    print("Testing POST /intent/set...")
    response = requests.post(
        f"{BASE_URL}/intent/set",
        json={
            "objective": "Manage inbox. Drafts only.",
            "scope": {
                "email": ["draft"],
                "calendar": ["view", "propose"]
            },
            "constraints": {
                "drafts_only": True,
                "max_recipients": 3
            },
            "risk_level": "low",
            "approved_by_user": True
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    intent_id = response.json()["intent_id"]
    print()
    return intent_id


def test_execute_allow(intent_id):
    """Test executing an allowed action."""
    print("Testing POST /execute (ALLOW)...")
    response = requests.post(
        f"{BASE_URL}/execute",
        json={
            "action": {
                "tool": "email",
                "op": "draft",
                "params": {
                    "recipients": ["user@example.com"],
                    "subject": "Test",
                    "body": "Body"
                }
            },
            "intent_id": intent_id,
            "agent_id": "clawdbot-001"
        }
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    
    # Verify execution happened (real connector)
    if result.get("execution"):
        exec_result = result["execution"]["result"]
        if exec_result.get("success"):
            print(f"  ✓ Real execution: {exec_result.get('message', 'Success')}")
            if "file_path" in exec_result:
                print(f"  ✓ File created: {exec_result['file_path']}")
    print()


def test_execute_block(intent_id):
    """Test executing a blocked action."""
    print("Testing POST /execute (BLOCK)...")
    response = requests.post(
        f"{BASE_URL}/execute",
        json={
            "action": {
                "tool": "shell",
                "op": "run",
                "params": {
                    "command": "rm -rf /"
                }
            },
            "intent_id": intent_id,
            "agent_id": "clawdbot-001"
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()


def test_audit_query():
    """Test querying audit logs."""
    print("Testing GET /audit/query...")
    response = requests.get(
        f"{BASE_URL}/audit/query",
        params={"agent_id": "clawdbot-001", "limit": 10}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    print()


def test_decisions_query():
    """Test querying decisions."""
    print("Testing GET /decisions/query...")
    response = requests.get(
        f"{BASE_URL}/decisions/query",
        params={"agent_id": "clawdbot-001", "limit": 10}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Found {result['total']} decisions")
        if result['decisions']:
            print(f"Latest decision: {json.dumps(result['decisions'][0], indent=2)}")
    else:
        print(f"Error: {response.text}")
    print()


def test_get_intent(intent_id):
    """Test getting an intent."""
    print("Testing GET /intent/get...")
    response = requests.get(
        f"{BASE_URL}/intent/get",
        params={"intent_id": intent_id}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    print()


if __name__ == "__main__":
    print("=" * 70)
    print("EDON Gateway Test Suite")
    print("=" * 70)
    print()
    
    try:
        test_health()
        intent_id = test_set_intent()
        test_get_intent(intent_id)
        test_execute_allow(intent_id)
        test_execute_block(intent_id)
        test_audit_query()
        test_decisions_query()
        
        print("=" * 70)
        print("All tests completed!")
        print("=" * 70)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
