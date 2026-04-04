# JavaScript / TypeScript SDK — Quickstart

## Installation

```bash
npm install @edon/sdk
# or from this repo:
npm install ./sdk/javascript
```

## Authentication

Get an API key from the [EDON Console](https://agent.edoncore.com) → Settings → API Keys.

## Basic Usage — Node.js (5 lines)

```typescript
import { EdonClient } from "@edon/sdk";

const client = new EdonClient({ token: "eak_your_key_here" });
const result = await client.evaluate({
  actionType: "email.send",
  agentId: "my-node-agent",
  payload: { recipients: ["user@co.com"], subject: "Hello" },
});

console.log(result.verdict); // ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE, or ERROR
```

## Complete Node.js Example

```typescript
import { EdonClient } from "@edon/sdk";

const edon = new EdonClient({
  token: process.env.EDON_API_KEY!,
  baseUrl: process.env.EDON_GATEWAY_URL ?? "https://edon-gateway.fly.dev",
});

async function governedAction(
  actionType: string,
  payload: Record<string, unknown>,
  agentId: string
) {
  const result = await edon.evaluate({ actionType, agentId, payload });

  switch (result.verdict) {
    case "ALLOW":
      return await executeAction(actionType, payload);

    case "BLOCK":
      throw new Error(`Action blocked: ${result.explanation} (${result.reason_code})`);

    case "ESCALATE":
      return { escalated: true, question: result.escalation_question };

    case "DEGRADE":
      return await executeAction(actionType, result.safe_alternative ?? payload);

    case "PAUSE":
      await sleep(5000);
      return governedAction(actionType, payload, agentId); // retry

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

## Browser Usage

```typescript
// Store token securely — never expose in client-side code in production
// Use URL hash params so the token never reaches the server:
// https://your-app.com/#token=eak_...
const token = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";

const client = new EdonClient({ token });
```

## TypeScript Types

```typescript
interface EvaluateRequest {
  actionType: string;
  agentId: string;
  payload?: Record<string, unknown>;
  estimatedRisk?: "low" | "medium" | "high" | "critical";
  context?: Record<string, unknown>;
}

interface EvaluateResponse {
  action_id: string;
  verdict: "ALLOW" | "BLOCK" | "ESCALATE" | "DEGRADE" | "PAUSE" | "ERROR";
  reason_code: string;
  explanation: string;
  safe_alternative?: Record<string, unknown> | null;
  escalation_question?: string | null;
  escalation_options?: Array<{ id: string; label: string }>;
  policy_snapshot_hash: string;
}
```

## Error Handling

```typescript
try {
  const result = await client.evaluate({ actionType: "http.request", agentId: "agent-1" });
} catch (error) {
  if (error instanceof Response && error.status === 401) {
    console.error("Invalid API key");
  } else if (error instanceof Response && error.status === 429) {
    console.error("Rate limit exceeded");
  } else {
    // Fail closed — do not proceed with the action
    console.error("Governance error:", error);
  }
}
```
