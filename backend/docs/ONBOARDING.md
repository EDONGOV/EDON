# EDON Gateway — Customer Onboarding Guide

> Every action your AI agents take passes through EDON first.
> EDON decides: **Allow, Block, Escalate, or Degrade** — in under 100ms.
> Every decision is cryptographically logged. Nothing is lost. Nothing can be faked.

---

## How It Works (30 seconds)

```
Your Agent  ──►  POST /v1/action  ──►  EDON decides  ──►  Your Agent acts (or stops)
                       │
                       ▼
               SHA-256 audit log
               (tamper-evident, forever)
```

1. Your agent wants to do something (move a robot, send an email, query a database)
2. Before doing it, your agent asks EDON: *"Is this allowed?"*
3. EDON checks the action against your intent, your custom rules, and built-in safety policies
4. EDON responds: `ALLOW`, `BLOCK`, `HUMAN_REQUIRED`, or `DEGRADE`
5. Your agent obeys the decision

That's it. EDON is not in the data path — it's in the **decision** path.

---

## Step 1 — Get Your API Key

Every request to EDON requires an API key tied to your account (tenant).

You'll receive a key in the format:
```
edon-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Send it on every request as a header:
```
X-EDON-TOKEN: edon-your-key-here
```

**Keep this key secret.** It identifies your organization and all agents under it.

---

## Step 2 — Create an Intent

An **Intent** is the contract that defines what your agents are allowed to do.
Think of it as a mission briefing: *"Here is the objective and here are the boundaries."*

```bash
curl -X POST https://edon-gatewaybk.fly.dev/intents \
  -H "X-EDON-TOKEN: edon-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "intent_id": "warehouse-ops-v1",
    "objective": "Manage warehouse floor operations: move robots, scan packages, assign dock doors",
    "scope": {
      "robot":    ["move_to", "pick", "place", "home"],
      "scanner":  ["scan", "verify"],
      "dock":     ["assign", "release"],
      "forklift": ["move_to", "lift", "lower"]
    },
    "constraints": {
      "work_hours_only": false,
      "no_external_sharing": true
    },
    "risk_level": "medium",
    "approved_by_user": true
  }'
```

### Scope rules
- Only the `tool.operation` pairs listed in `scope` are allowed
- Anything not listed is automatically **BLOCKED**
- You can have multiple intents for different agent teams

### Common constraints
| Constraint | Type | Effect |
|---|---|---|
| `work_hours_only` | boolean | Blocks all actions outside 9–5 Monday–Friday |
| `no_external_sharing` | boolean | Blocks any operation that sends data externally |
| `drafts_only` | boolean | Degrades `email.send` → `email.draft` automatically |
| `max_recipients` | integer | Escalates bulk emails above this threshold |

---

## Step 3 — Wire Your First Agent

Every time your agent wants to take an action, it sends a single POST request first.

### Python
```python
import httpx
from datetime import datetime, UTC

EDON_URL = "https://edon-gatewaybk.fly.dev"
EDON_TOKEN = "edon-your-key"

def ask_edon(agent_id: str, action_type: str, payload: dict, intent_id: str = "warehouse-ops-v1") -> dict:
    """Ask EDON if this action is allowed. Returns the decision."""
    response = httpx.post(
        f"{EDON_URL}/v1/action",
        headers={"X-EDON-TOKEN": EDON_TOKEN},
        json={
            "agent_id": agent_id,
            "action_type": action_type,          # format: "tool.operation"
            "action_payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
            "context": {"intent_id": intent_id}
        },
        timeout=5.0
    )
    response.raise_for_status()
    return response.json()


# Example: Robot wants to move to shelf A-12
decision = ask_edon(
    agent_id="robot-unit-42",
    action_type="robot.move_to",
    payload={"destination": "shelf-A12", "speed": "normal"}
)

if decision["decision"] == "ALLOW":
    robot.move_to("shelf-A12")
elif decision["decision"] == "BLOCK":
    print(f"Blocked: {decision['decision_reason']}")
elif decision["decision"] == "HUMAN_REQUIRED":
    queue_for_human_review(decision)
```

### Node.js / TypeScript
```typescript
const EDON_URL = "https://edon-gatewaybk.fly.dev";
const EDON_TOKEN = "edon-your-key";

async function askEdon(agentId: string, actionType: string, payload: object, intentId = "warehouse-ops-v1") {
  const res = await fetch(`${EDON_URL}/v1/action`, {
    method: "POST",
    headers: {
      "X-EDON-TOKEN": EDON_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      agent_id: agentId,
      action_type: actionType,
      action_payload: payload,
      timestamp: new Date().toISOString(),
      context: { intent_id: intentId },
    }),
  });
  if (!res.ok) throw new Error(`EDON error: ${res.status}`);
  return res.json();
}

// Example usage
const decision = await askEdon("forklift-7", "forklift.lift", { pallet_id: "PLT-0042", height_mm: 1200 });

switch (decision.decision) {
  case "ALLOW":    forklift.lift(palletId, heightMm); break;
  case "BLOCK":    console.error("Blocked:", decision.decision_reason); break;
  case "HUMAN_REQUIRED": await notifyOperator(decision); break;
}
```

### Plain cURL (for testing)
```bash
curl -X POST https://edon-gatewaybk.fly.dev/v1/action \
  -H "X-EDON-TOKEN: edon-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test-agent-1",
    "action_type": "robot.move_to",
    "action_payload": {"destination": "dock-3"},
    "timestamp": "2026-02-25T12:00:00Z",
    "context": {"intent_id": "warehouse-ops-v1"}
  }'
```

---

## Step 4 — Understand the Response

Every `/v1/action` call returns:

```json
{
  "action_id": "dec-abc123",
  "decision": "ALLOW",
  "decision_reason": "Action approved: within scope, constraints satisfied, risk acceptable",
  "reason_code": "APPROVED",
  "policy_version": "1.0.0",
  "processing_latency_ms": 4
}
```

### Decision types

| Decision | Meaning | What your agent should do |
|---|---|---|
| `ALLOW` | Approved — proceed | Execute the action |
| `BLOCK` | Denied — do not proceed | Log it, notify if needed, do NOT execute |
| `HUMAN_REQUIRED` | Needs a human to approve | Queue it for operator review, pause the agent |
| `DEGRADE` | Safe alternative available | Use `safe_alternative` in the response instead |
| `PAUSE` | Loop or rate limit detected | Wait before retrying |

### When you get `DEGRADE`
The response includes a `safe_alternative` field:
```json
{
  "decision": "DEGRADE",
  "decision_reason": "Intent requires drafts_only, degrading send to draft",
  "safe_alternative": {
    "action_type": "email.draft",
    "action_payload": { "...": "..." }
  }
}
```
Execute the `safe_alternative` instead of the original action.

### When you get `HUMAN_REQUIRED`
The response includes the question to show to your operator:
```json
{
  "decision": "HUMAN_REQUIRED",
  "escalation_question": "Send email to 47 recipients? (max allowed: 10)",
  "escalation_options": [
    {"id": "allow_once", "label": "Allow once"},
    {"id": "draft_only", "label": "Save as draft only"},
    {"id": "keep_blocking", "label": "Keep blocking"}
  ]
}
```

---

## Step 5 — Multiple Agents

All agents at your organization share the same API key and tenant. They are differentiated by `agent_id`.

```
Your Tenant (API Key)
├── robot-unit-01     agent_id="robot-unit-01"
├── robot-unit-02     agent_id="robot-unit-02"
├── forklift-north-1  agent_id="forklift-north-1"
├── drone-fleet-A     agent_id="drone-fleet-A"
└── scanner-dock-7    agent_id="scanner-dock-7"
```

**Each agent uses the same API key** but a different `agent_id`. EDON tracks:
- Rate limits per `agent_id`
- Loop detection per `agent_id`
- Audit trail per `agent_id`

### Multiple teams / environments

Use **different intents** for different teams or environments:

```python
# Production warehouse floor
decision = ask_edon(agent_id, action_type, payload, intent_id="warehouse-floor-prod")

# Staging / testing
decision = ask_edon(agent_id, action_type, payload, intent_id="warehouse-floor-staging")

# Night-shift autonomous mode (wider scope, no human escalation)
decision = ask_edon(agent_id, action_type, payload, intent_id="autonomous-night-v1")
```

### Recommended agent_id format

Use a consistent naming scheme so your audit logs are easy to read:
```
{team}-{unit-type}-{id}
# Examples:
warehouse-robot-042
fulfillment-drone-A7
receiving-forklift-north-1
dispatch-scanner-dock-3
```

---

## Step 6 — Custom Policy Rules (Optional)

Beyond the intent scope, you can add your own rules that apply to all agents on your account.

Rules are evaluated **before** any standard governance check, in priority order.

### Example: Block all emergency stops without escalation
```bash
curl -X POST https://edon-gatewaybk.fly.dev/policy/rules \
  -H "X-EDON-TOKEN: edon-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Forklift emergency stops require operator approval",
    "condition_tool": "forklift",
    "condition_op": "emergency_stop",
    "action": "ESCALATE",
    "priority": 100
  }'
```

### Example: Always allow health-check pings
```bash
curl -X POST https://edon-gatewaybk.fly.dev/policy/rules \
  -H "X-EDON-TOKEN: edon-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Allow health check pings",
    "condition_tool": "sensor",
    "condition_op": "ping",
    "action": "ALLOW",
    "priority": 200
  }'
```

### Rule conditions (all optional — omit = match anything)

| Field | Example | Matches |
|---|---|---|
| `condition_tool` | `"forklift"` | Only forklift actions |
| `condition_op` | `"emergency_stop"` | Only that specific operation |
| `condition_risk_level` | `"high"` | Only high-risk actions |
| `condition_tags` | `["urgent", "after-hours"]` | Actions tagged with ALL listed tags |

### Manage your rules
```bash
# List all rules
GET /policy/rules

# Disable a rule (keep it, just turn it off)
POST /policy/rules/{rule_id}/disable

# Re-enable
POST /policy/rules/{rule_id}/enable

# Delete permanently
DELETE /policy/rules/{rule_id}
```

---

## Step 7 — Audit Trail

Every decision EDON makes is logged forever and can be exported or verified.

```bash
# Query recent decisions for a specific agent
GET /audit/query?agent_id=robot-unit-42&limit=50

# Export full audit trail as JSON
GET /audit/export?format=json

# Export as CSV (for Excel / compliance teams)
GET /audit/export?format=csv

# Cryptographically verify nothing was tampered with
GET /audit/verify-chain
```

The audit chain is SHA-256 hash-chained — if anyone modifies, deletes, or reorders even one record, the verification will fail and you'll know exactly which record was affected.

---

## Step 8 — Rotate Your API Key (Zero Downtime)

When you need to rotate credentials (security policy, key compromise, etc.):

```bash
# 1. Rotate: creates new key, old key still works for 24 hours
curl -X POST https://edon-gatewaybk.fly.dev/api-keys/{your-key-id}/rotate \
  -H "X-EDON-TOKEN: edon-your-key" \
  -H "Content-Type: application/json" \
  -d '{"overlap_hours": 24}'

# Response:
# {
#   "new_key": "edon-NEW-KEY-HERE",    ← store this immediately
#   "new_key_id": "key_abc123",
#   "old_key_expires_at": "2026-02-26T12:00:00Z"
# }

# 2. Update all your agents with the new key
# 3. Old key expires automatically — no manual cleanup needed
```

---

## Rate Limits

| Window | Default limit |
|---|---|
| Per minute (per `agent_id`) | 10,000 requests |
| Per hour | 300,000 requests |
| Per day | 20,000,000 requests |

If you exceed a limit you receive `429 Too Many Requests` with a `Retry-After` header telling you exactly when to retry.

For **100 systems at 20M decisions/day**, the defaults are pre-configured to handle your load.

---

## Health Check

```bash
curl https://edon-gatewaybk.fly.dev/health
# {"status": "healthy", "db": "connected", "version": "..."}
```

---

## Quick Reference — All Endpoints

| Method | Path | What it does |
|---|---|---|
| `POST` | `/v1/action` | **Main endpoint** — evaluate an agent action |
| `POST` | `/intents` | Create an intent contract |
| `GET` | `/intents/{id}` | Get an intent |
| `GET` | `/policy/rules` | List your custom rules |
| `POST` | `/policy/rules` | Create a custom rule |
| `PUT` | `/policy/rules/{id}` | Update a rule |
| `DELETE` | `/policy/rules/{id}` | Delete a rule |
| `POST` | `/policy/rules/{id}/enable` | Enable a rule |
| `POST` | `/policy/rules/{id}/disable` | Disable a rule |
| `GET` | `/audit/query` | Query audit log |
| `GET` | `/audit/export` | Export audit trail (JSON/CSV/Parquet) |
| `GET` | `/audit/verify-chain` | Cryptographic integrity check |
| `POST` | `/api-keys/{id}/rotate` | Rotate an API key (zero downtime) |
| `GET` | `/compliance/report` | Generate compliance report |
| `GET` | `/health` | Health check |

---

## Supported Tool Types

### Physical / Robotics
`robot` · `vehicle` · `forklift` · `conveyor` · `drone` · `scanner` · `sorter` · `dock` · `gate` · `sensor`

### Digital / AI Agents
`email` · `shell` · `calendar` · `file` · `browser` · `gmail` · `google_calendar` · `github` · `memory` · `agent` · `database` · `http`

### Communication & Productivity
`slack` · `discord` · `twitter` · `notion`

### Data / Finance
`brave_search` · `polygon` · `fmp` · `newsapi` · `gemini`

### Communication
`elevenlabs` · `home_assistant` · `clawdbot`

---

## Common Mistakes

**❌ Don't call `/v1/action` after taking the action**
EDON must be called BEFORE the action is taken. It's a pre-authorization gate, not a logging endpoint.

**❌ Don't ignore `BLOCK` responses**
If EDON returns `BLOCK`, your agent must not proceed. The audit log records both the decision and whether it was respected.

**❌ Don't hardcode the intent_id**
Pass it in context so you can swap intents (staging vs prod, day vs night) without redeploying agents.

**❌ Don't share `agent_id` across different machines**
Each physical machine or agent instance should have a unique `agent_id`. Rate limiting and loop detection are per-`agent_id`.

---

## Getting Help

- **Audit anything**: `GET /audit/query?agent_id=your-agent`
- **Check policy**: `GET /policy/rules`
- **Verify integrity**: `GET /audit/verify-chain`
- **Check health**: `GET /health`
- **API reference**: `GET /docs` (interactive Swagger UI)

---

*EDON Gateway — Built for 100 systems. Designed for 20 million decisions a day.*
