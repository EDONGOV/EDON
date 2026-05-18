# JavaScript / TypeScript SDK — Quickstart

## Installation

```bash
npm install @edon/sdk
# Or from this repo during development:
npm install ./sdk/javascript
```

## Authentication

Get an API key from the [EDON Console](https://console.edoncore.com) → Settings → API Keys,
or call `POST /auth/register` to sign up programmatically (see below).

```typescript
import { EdonClient } from "@edon/sdk";

const client = new EdonClient({ token: process.env.EDON_API_KEY! });
```

## Basic Usage — 5 Lines

```typescript
import { EdonClient } from "@edon/sdk";

const client = new EdonClient({ token: process.env.EDON_API_KEY! });
const result = await client.evaluate({
  actionType: "email.send",
  payload: { recipients: ["user@co.com"], subject: "Hello" },
});

console.log(result.verdict); // ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE, or ERROR
```

## Verdict Types

| Verdict | Meaning | What to do |
|---------|---------|------------|
| `ALLOW` | Action approved | Proceed with the action |
| `BLOCK` | Action denied | Do not execute. Log and inform user |
| `ESCALATE` | Needs human review | Queue for human approval; show `escalationQuestion` |
| `DEGRADE` | Proceed with restrictions | Use `safeAlternative` instead of original params |
| `PAUSE` | Temporary hold | Retry after a delay |
| `ERROR` | Governance error | Fail safely |

## Complete Example

```typescript
import { EdonClient } from "@edon/sdk";

const edon = new EdonClient({ token: process.env.EDON_API_KEY! });

async function governedAction(
  actionType: string,
  payload: Record<string, unknown>,
  agentId = "my-agent",
) {
  const result = await edon.evaluate({ actionType, agentId, payload });

  switch (result.verdict) {
    case "ALLOW":
      return await executeAction(actionType, payload);

    case "BLOCK":
      throw new Error(`Action blocked: ${result.explanation} (${result.reasonCode})`);

    case "ESCALATE":
      return { escalated: true, question: result.escalationQuestion };

    case "DEGRADE":
      return await executeAction(actionType, result.safeAlternative ?? payload);

    case "PAUSE":
      await sleep(5_000);
      return governedAction(actionType, payload, agentId);

    default:
      throw new Error(`Governance error: verdict=${result.verdict}`);
  }
}

async function executeAction(type: string, payload: unknown) {
  console.log(`Executing ${type}`, payload);
  return { executed: true };
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

## Error Handling

The SDK throws typed errors — catch the specific class you care about:

```typescript
import {
  EdonClient,
  AuthenticationError,
  RateLimitError,
  APITimeoutError,
  APIConnectionError,
  EdonError,
} from "@edon/sdk";

const client = new EdonClient({ token: process.env.EDON_API_KEY! });

try {
  const result = await client.evaluate({ actionType: "database.query", payload: {} });
} catch (err) {
  if (err instanceof AuthenticationError) {
    console.error("Invalid API key — check EDON_API_KEY starts with 'edon-'");

  } else if (err instanceof RateLimitError) {
    const wait = (err.retryAfter ?? 5) * 1_000;
    console.error(`Rate limit — retrying in ${wait}ms`);
    await sleep(wait);

  } else if (err instanceof APITimeoutError) {
    console.error("Gateway timed out — safe to retry");

  } else if (err instanceof APIConnectionError) {
    console.error("Cannot reach EDON gateway — check network / EDON_GATEWAY_URL");

  } else if (err instanceof EdonError) {
    console.error("SDK error:", err.message);
  }
}
```

The SDK automatically retries 429 and 5xx responses with exponential backoff (2 retries by default).

## TypeScript Types

```typescript
import type {
  EvaluateOptions,
  EvaluateResult,
  ScanOutputOptions,
  ScanOutputResult,
  BeginIntentOptions,
} from "@edon/sdk";

// EvaluateResult fields (all camelCase):
// result.verdict           — 'ALLOW' | 'BLOCK' | 'ESCALATE' | 'DEGRADE' | 'PAUSE' | 'ERROR'
// result.reasonCode        — machine-readable reason string
// result.explanation       — human-readable explanation
// result.actionId          — audit trail ID; pass to scanOutput()
// result.safeAlternative   — (DEGRADE only) modified params
// result.escalationQuestion — (ESCALATE only) question to show a human
// result.fallback          — true if gateway was unreachable (fail-open applied)
```

## Browser Usage

```typescript
// Never expose API keys in client-side bundles.
// For browser demos, use a backend proxy that injects the key server-side.
const client = new EdonClient({ token: "edon-..." }); // from your backend session
```

## Self-Serve Sign-Up (No Console Required)

```typescript
const resp = await fetch("https://edon-gateway-prod.fly.dev/auth/register", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "you@yourhospital.com", password: "secure-password" }),
});
const data = await resp.json();
console.log(data.api_key);   // edon-... — copy this now, shown only once
console.log(data.tenant_id);
```
