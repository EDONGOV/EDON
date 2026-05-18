# Python SDK — Quickstart

## Installation

```bash
pip install edon-sdk
# Or from this repo during development:
pip install -e sdk/python/
```

## Authentication

Get an API key from the [EDON Console](https://console.edoncore.com) → Settings → API Keys,
or call `POST /auth/register` to sign up programmatically (see below).

```python
import os
from edon_sdk import EdonClient

# Reads EDON_API_KEY from environment automatically
client = EdonClient()

# Or pass explicitly
client = EdonClient(token="edon-your_key_here")
```

Set these environment variables to avoid hardcoding credentials:

| Variable | Description |
|----------|-------------|
| `EDON_API_KEY` | Your API key (starts with `edon-`) |
| `EDON_GATEWAY_URL` | Override gateway URL (default: production) |

## Basic Usage — 5 Lines

```python
from edon_sdk import EdonClient

client = EdonClient()  # reads EDON_API_KEY from env
result = client.evaluate(
    action_type="email.send",
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

client = EdonClient()  # reads EDON_API_KEY from env

def governed_send_email(recipients, subject, body, agent_id="my-agent"):
    """Send an email only if EDON allows it."""
    result = client.evaluate(
        action_type="email.send",
        agent_id=agent_id,
        payload={"recipients": recipients, "subject": subject, "body": body},
    )

    verdict = result["verdict"]
    explanation = result.get("explanation", "")

    if verdict == "ALLOW":
        _actual_send_email(recipients, subject, body)
        return {"sent": True}

    elif verdict == "BLOCK":
        raise PermissionError(f"Email blocked by EDON: {explanation}")

    elif verdict == "ESCALATE":
        question = result.get("escalation_question", "Please review this action")
        return {"sent": False, "requires_human": True, "question": question}

    elif verdict == "DEGRADE":
        alt = result.get("safe_alternative", {})
        _actual_send_email(alt.get("recipients", []), alt.get("subject", subject), body)
        return {"sent": True, "degraded": True}

    elif verdict == "PAUSE":
        time.sleep(5)
        return governed_send_email(recipients, subject, body, agent_id)

    else:
        raise RuntimeError(f"Unexpected verdict: {verdict}")


def _actual_send_email(recipients, subject, body):
    print(f"Sending to {recipients}: {subject}")
```

## Error Handling

The SDK raises typed exceptions — catch the specific error you care about:

```python
from edon_sdk import (
    EdonClient,
    AuthenticationError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    EdonError,
)
import time

client = EdonClient()

try:
    result = client.evaluate(action_type="database.query", payload={...})

except AuthenticationError:
    print("Invalid API key — check EDON_API_KEY starts with 'edon-'")

except RateLimitError as e:
    wait = e.retry_after or 5
    print(f"Rate limit hit — retrying in {wait}s")
    time.sleep(wait)

except APITimeoutError:
    print("Gateway timed out — safe to retry (governance is idempotent)")

except APIConnectionError:
    print("Cannot reach EDON gateway — check network / EDON_GATEWAY_URL")

except EdonError as e:
    print(f"SDK error: {e}")
```

The SDK automatically retries 429 and 5xx responses with exponential backoff (2 retries by default).
You only need to handle errors that persist after retries.

## Async Usage

```python
import asyncio
from edon_sdk import AsyncEdonClient

async def main():
    async with AsyncEdonClient() as client:
        result = await client.evaluate(
            action_type="database.query",
            payload={"table": "patients", "limit": 10},
        )
        print(result["verdict"])

asyncio.run(main())
```

## Self-Serve Sign-Up (No Console Required)

Sign up and get an API key entirely via the API:

```python
import httpx

resp = httpx.post(
    "https://edon-gateway-prod.fly.dev/auth/register",
    json={"email": "you@yourhospital.com", "password": "secure-password-here"},
)
data = resp.json()
print(data["api_key"])      # edon-... — copy this now, shown only once
print(data["tenant_id"])
```
