# Python SDK — Quickstart

## Installation

```bash
pip install httpx  # only dependency (until edon-sdk is on PyPI)
# Or install from this repo:
pip install -e sdk/python/
```

## Authentication

Get an API key from the [EDON Console](https://agent.edoncore.com) → Settings → API Keys.

```python
from edon_sdk import EdonClient

client = EdonClient(
    token="eak_your_key_here",
    base_url="https://edon-gateway.fly.dev",  # default
)
```

## Basic Usage — 5 Lines

```python
from edon_sdk import EdonClient

client = EdonClient(token="eak_your_key_here")
result = client.evaluate(
    action_type="email.send",
    agent_id="my-agent-v1",
    payload={"recipients": ["boss@company.com"], "subject": "Quarterly report"},
)
print(result["verdict"])  # ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE, or ERROR
```

## Verdict Types

| Verdict | Meaning | What to do |
|---------|---------|------------|
| `ALLOW` | Action approved | Proceed with the action |
| `BLOCK` | Action denied | Do not execute. Log and inform user |
| `ESCALATE` | Needs human review | Queue for human approval; show `escalation_question` |
| `DEGRADE` | Proceed with restrictions | Use `safe_alternative` instead of original params |
| `PAUSE` | Temporary hold | Retry after a delay; check for loop detection |
| `ERROR` | Governance error | Fail safely (fail-closed by default) |

## Complete Example — Governed Agent

```python
import time
from edon_sdk import EdonClient

client = EdonClient(token="eak_your_key_here")

def governed_send_email(recipients, subject, body, agent_id="my-agent"):
    """Send an email only if EDON allows it."""
    result = client.evaluate(
        action_type="email.send",
        agent_id=agent_id,
        payload={"recipients": recipients, "subject": subject, "body": body},
    )

    verdict = result["verdict"]
    reason = result.get("reason_code", "")
    explanation = result.get("explanation", "")

    if verdict == "ALLOW":
        # Proceed — action is approved
        _actual_send_email(recipients, subject, body)
        return {"sent": True}

    elif verdict == "BLOCK":
        raise PermissionError(f"Email blocked by EDON: {explanation} ({reason})")

    elif verdict == "ESCALATE":
        # Queue for human review
        question = result.get("escalation_question", "Please review this action")
        return {"sent": False, "requires_human": True, "question": question}

    elif verdict == "DEGRADE":
        # Use the safe alternative parameters
        alt = result.get("safe_alternative", {})
        _actual_send_email(alt.get("recipients", []), alt.get("subject", subject), body)
        return {"sent": True, "degraded": True}

    elif verdict == "PAUSE":
        time.sleep(5)
        return governed_send_email(recipients, subject, body, agent_id)  # retry

    else:
        raise RuntimeError(f"Unexpected verdict: {verdict}")


def _actual_send_email(recipients, subject, body):
    print(f"Sending to {recipients}: {subject}")
```

## Error Handling Best Practices

```python
import httpx

try:
    result = client.evaluate(action_type="http.request", agent_id="agent-1", payload={...})
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        print("Invalid API key")
    elif e.response.status_code == 429:
        print("Rate limit exceeded — slow down")
    else:
        print(f"Gateway error: {e.response.text}")
    # Fail closed — don't proceed with the action
except httpx.TimeoutException:
    print("Gateway timeout — fail closed")
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `EDON_API_KEY` | API key (alternative to passing `token=` to constructor) |
| `EDON_GATEWAY_URL` | Gateway base URL (default: `https://edon-gateway.fly.dev`) |

```python
import os
from edon_sdk import EdonClient

client = EdonClient(
    token=os.environ["EDON_API_KEY"],
    base_url=os.getenv("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev"),
)
```
