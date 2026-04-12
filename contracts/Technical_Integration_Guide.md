# EDON Technical Integration Guide

**For Engineering Teams**
**Version 1.0 — April 2026**

---

## Overview

EDON is a runtime governance layer for AI agents. You wrap your existing agent client with EDON — no agent rewrite, no model change, no architecture overhaul.

Every action your agent attempts passes through EDON before executing. EDON evaluates it against your policies in **< 2ms** and returns one of five verdicts:

| Verdict | Meaning |
|---------|---------|
| `ALLOW` | Action is within policy — proceed |
| `BLOCK` | Action violates policy — do not execute |
| `ESCALATE` | Action is high-risk — pause and queue for human approval |
| `DEGRADE` | Allow a limited/safe version of the action instead |
| `PAUSE` | Agent is suspended pending review |

---

## What Leaves Your Environment

Understanding data flow is critical for healthcare environments.

```
Your Agent → EDON API → Your Systems
                ↓
          Audit Log (stored by EDON)
```

**EDON receives:**
- The action type (e.g., `query_database`, `send_message`, `write_file`)
- The parameters of the action (the "intent")
- The agent ID
- A session/request ID you provide

**EDON does NOT receive:**
- The response from your systems
- Raw patient records or EHR data (unless your agent explicitly passes it as a parameter)
- Authentication credentials to your internal systems
- Model weights or prompts

**PHI exposure in audit logs:**
PHI only appears in EDON's audit logs if your agent passes PHI as an action parameter (e.g., a query string containing a patient name). This is mitigated by:
1. **PHI masking** — configure EDON to redact specific fields before storage (see Section 5)
2. **Parameter sanitization** — strip PHI from action parameters before calling EDON (recommended for highest-assurance environments)

---

## Integration: 3 Steps

### Step 1 — Install the SDK

**Python**
```bash
pip install edon-sdk
```

**Node.js**
```bash
npm install @edon/sdk
```

**Go**
```bash
go get github.com/EDONGOV/edon-go
```

Or use the **REST API directly** (no SDK required) — see Section 4.

---

### Step 2 — Wrap Your Agent Client

**Python (OpenAI example)**
```python
from openai import OpenAI
from edon import EdonGateway

# Your existing client
llm = OpenAI(api_key="sk-...")

# Wrap it — one line
client = EdonGateway(llm, api_key="edon_sk_your_key_here")

# Use exactly as before — EDON intercepts tool calls automatically
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Schedule a follow-up for patient 1042"}],
    tools=your_tool_definitions,
)
```

**Python (Anthropic example)**
```python
from anthropic import Anthropic
from edon import EdonGateway

client = EdonGateway(Anthropic(), api_key="edon_sk_your_key_here")
```

**Python (LangChain example)**
```python
from langchain_openai import ChatOpenAI
from edon.langchain import EdonCallbackHandler

llm = ChatOpenAI(
    model="gpt-4o",
    callbacks=[EdonCallbackHandler(api_key="edon_sk_your_key_here")]
)
```

**Node.js**
```typescript
import OpenAI from 'openai'
import { EdonGateway } from '@edon/sdk'

const client = new EdonGateway(
  new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
  { apiKey: process.env.EDON_API_KEY }
)

// Use identically to the standard OpenAI client
```

---

### Step 3 — Apply a Policy Pack

Choose a policy pack that fits your use case, or write custom rules.

**Via API**
```bash
curl -X POST https://api.edoncore.com/policy-packs/clinical_assistant/apply \
  -H "X-EDON-TOKEN: edon_sk_your_key_here" \
  -H "Content-Type: application/json"
```

**Via Dashboard**
Log in at `console.edoncore.com` → Policies → Apply Pack

**Available Healthcare Policy Packs**

| Pack | Use Case | Default Behavior |
|------|----------|-----------------|
| `clinical_assistant` | Patient-facing or clinical support agents | Blocks external data writes; escalates PHI access outside business hours |
| `ops_commander` | Internal ops automation | Allows broad internal access; blocks external communications |
| `helpdesk` | IT and support agents | Restricts to read-only operations; blocks system config changes |
| `audit_only` | Passive monitoring mode | All actions allowed; full audit logging with no blocking |

---

## REST API Reference

If you prefer direct integration without the SDK:

### Evaluate an Action

```
POST https://api.edoncore.com/v1/action
X-EDON-TOKEN: edon_sk_your_key_here
Content-Type: application/json
```

**Request body**
```json
{
  "agent_id": "discharge-summary-agent",
  "action": {
    "type": "query_ehr",
    "parameters": {
      "patient_id": "12345",
      "data_type": "medications",
      "date_range": "last_30_days"
    }
  },
  "context": {
    "session_id": "sess_abc123",
    "user_id": "clinician_007",
    "intent": "Generate discharge summary"
  }
}
```

**Response**
```json
{
  "action_id": "act_01JXYZ...",
  "verdict": "ALLOW",
  "reason_code": "APPROVED",
  "explanation": "Query is within policy scope for clinical assistant agent.",
  "policy_snapshot_hash": "sha256:a3f8...",
  "latency_ms": 1.4
}
```

**BLOCK response example**
```json
{
  "action_id": "act_01JABC...",
  "verdict": "BLOCK",
  "reason_code": "SCOPE_VIOLATION",
  "explanation": "Agent attempted to write to external system. Policy: clinical_assistant restricts external writes.",
  "safe_alternative": {
    "type": "flag_for_review",
    "parameters": { "reason": "External write attempted" }
  }
}
```

**ESCALATE response example**
```json
{
  "action_id": "act_01JDEF...",
  "verdict": "ESCALATE",
  "reason_code": "HIGH_RISK_ACTION",
  "explanation": "Mass record export requires human approval.",
  "escalation_question": "Do you authorize exporting records for 847 patients?",
  "escalation_options": [
    { "id": "approve_once", "label": "Approve this action" },
    { "id": "deny", "label": "Deny" },
    { "id": "approve_always", "label": "Always allow for this agent" }
  ]
}
```

### Handling Escalations in Your Agent

```python
result = edon.evaluate(action)

if result.verdict == "ESCALATE":
    # Pause your agent and wait for human decision
    # EDON will POST to your webhook when a decision is made
    agent.pause(reason=result.explanation)

elif result.verdict == "BLOCK":
    # Log the block; optionally use safe_alternative
    if result.safe_alternative:
        agent.execute(result.safe_alternative)
    else:
        agent.respond("I'm unable to perform that action.")

elif result.verdict == "ALLOW":
    agent.execute(action)
```

---

## PHI Masking Configuration

Configure PHI masking to prevent sensitive fields from being stored in audit logs.

**Via API**
```bash
curl -X PUT https://api.edoncore.com/config/masking \
  -H "X-EDON-TOKEN: edon_sk_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "fields": [
      "patient_id",
      "patient_name",
      "date_of_birth",
      "ssn",
      "mrn",
      "phone",
      "email",
      "address"
    ],
    "strategy": "redact"
  }'
```

**Masking strategies**

| Strategy | Behavior | Example |
|----------|----------|---------|
| `redact` | Replace with `[MASKED]` | `"name": "[MASKED]"` |
| `hash` | SHA-256 one-way hash | `"name": "a3f8bc..."` |
| `tokenize` | Consistent pseudonym per value | `"name": "PATIENT-7841"` |

**Important:** Masking is applied at ingestion before any storage. Masked values cannot be recovered from EDON's systems.

---

## Agent Registration

Register your agents to enable per-agent analytics, policies, and monitoring.

```bash
curl -X POST https://api.edoncore.com/agents \
  -H "X-EDON-TOKEN: edon_sk_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "discharge-summary-agent",
    "name": "Discharge Summary Agent",
    "description": "Generates patient discharge summaries from EHR data",
    "risk_level": "medium",
    "tags": ["clinical", "ehr-read", "document-generation"]
  }'
```

Registered agents appear in your EDON dashboard with individual analytics, policy assignments, and audit logs.

---

## Audit Log Format

Every decision EDON makes is recorded. You can query, export, and verify the full audit trail.

**Query audit logs**
```bash
curl "https://api.edoncore.com/audit/query?agent_id=discharge-summary-agent&verdict=BLOCK&limit=50" \
  -H "X-EDON-TOKEN: edon_sk_your_key_here"
```

**Export (CSV)**
```bash
curl "https://api.edoncore.com/audit/export?format=csv&from=2026-01-01&to=2026-03-31" \
  -H "X-EDON-TOKEN: edon_sk_your_key_here" \
  -o audit_q1_2026.csv
```

**Audit record fields**

| Field | Type | Description |
|-------|------|-------------|
| `action_id` | UUID | Globally unique decision ID |
| `timestamp` | ISO 8601 UTC | Decision time, microsecond precision |
| `agent_id` | string | Agent that triggered the action |
| `action_type` | string | Type of action evaluated |
| `verdict` | enum | ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE |
| `reason_code` | enum | Machine-readable reason |
| `explanation` | string | Human-readable explanation |
| `policy_snapshot_hash` | SHA-256 | Hash of active policy set at decision time |
| `record_hash` | SHA-256 | Hash of this record — enables tamper detection |
| `latency_ms` | float | EDON evaluation latency |

---

## Webhook Configuration

Receive real-time notifications for ESCALATE decisions, BLOCK events, or anomalies.

```bash
curl -X POST https://api.edoncore.com/webhooks \
  -H "X-EDON-TOKEN: edon_sk_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-system.com/edon-webhook",
    "events": ["escalation.created", "block.high_risk", "anomaly.detected"],
    "secret": "your_webhook_secret"
  }'
```

**Webhook payload**
```json
{
  "event": "escalation.created",
  "action_id": "act_01JXYZ...",
  "agent_id": "discharge-summary-agent",
  "timestamp": "2026-04-09T14:30:00.000Z",
  "escalation_question": "Agent is requesting access to 847 patient records. Approve?",
  "review_url": "https://console.edoncore.com/account/review/act_01JXYZ"
}
```

Webhook payloads are signed with HMAC-SHA256 using your webhook secret. Verify the `X-EDON-Signature` header before processing.

---

## Network Requirements

For cloud-hosted deployments, your agents need outbound HTTPS access to:

| Endpoint | Port | Purpose |
|----------|------|---------|
| `api.edoncore.com` | 443 | Action evaluation + audit logging |

No inbound connections from EDON to your network are required.

**On-premise deployments:** EDON runs entirely within your network. No external connections required. Configuration is managed via a local admin interface.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EDON_API_KEY` | Yes | Your EDON API key |
| `EDON_BASE_URL` | No | Override for on-premise deployments (default: `https://api.edoncore.com`) |
| `EDON_AGENT_ID` | No | Default agent ID (can be overridden per call) |
| `EDON_TIMEOUT_MS` | No | Evaluation timeout in ms (default: 5000) |
| `EDON_FAIL_OPEN` | No | If `true`, allow action if EDON is unreachable (default: `false`) |

**`EDON_FAIL_OPEN`:** For healthcare environments, we strongly recommend keeping this `false` (the default). If EDON is unreachable, actions are blocked. This is the safer default for regulated environments.

---

## Latency

EDON adds **< 2ms** to each agent action in the normal path. This is below the threshold for any meaningful user experience impact.

| Path | P50 | P95 | P99 |
|------|-----|-----|-----|
| Cloud-hosted (same region) | 0.8ms | 1.6ms | 2.1ms |
| Cloud-hosted (cross-region) | 3–8ms | 12ms | 18ms |
| On-premise | 0.2ms | 0.5ms | 0.8ms |

Escalation decisions (which require human input) are asynchronous — your agent is paused; there is no synchronous timeout waiting for a human response.

---

## Support

| Channel | Availability | Use For |
|---------|-------------|---------|
| `support@edoncore.com` | Business hours | General questions, integration help |
| Dedicated Slack channel | Business/Enterprise | Real-time technical support |
| `console.edoncore.com` | 24/7 | Dashboard, audit logs, policy management |
| Documentation | Always | `docs.edoncore.com` |

For urgent production issues (Severity 1): contact your dedicated Slack channel or email `oncall@edoncore.com`.

---

*EDON Technical Integration Guide v1.0 — April 2026*
*For the latest version: docs.edoncore.com/integration*
