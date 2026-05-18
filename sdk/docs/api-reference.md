# API Reference

Base URL: `https://edon-gateway-prod.fly.dev`
Auth header: `X-EDON-TOKEN: <your-api-key>`

Interactive docs: https://edon-gateway-prod.fly.dev/docs

---

## Authentication

All endpoints (except `/auth/register` and `/auth/login`) require your API key
in the `X-EDON-TOKEN` header. Keys start with `edon-` and are issued from the
[EDON Console](https://console.edoncore.com) or via `POST /auth/register`.

---

## POST /auth/register

Create an account and receive an API key in one step. No Console access required.

**Request:**
```json
{
  "email": "engineer@yourhospital.com",
  "password": "your-secure-password"
}
```

**Response:**
```json
{
  "tenant_id": "tenant_abc123",
  "api_key": "edon-...",
  "api_key_notice": "This is the only time your API key will be shown. Copy it now.",
  "user": { "id": "...", "email": "engineer@yourhospital.com", "tenant_id": "tenant_abc123" }
}
```

---

## POST /auth/login

Log in with email + password. Returns tenant context. Does not re-issue the plaintext
API key (use `/api-keys` to rotate if lost).

---

## POST /v1/action

Evaluate a governance decision for an agent action. The primary endpoint.

**Request:**
```json
{
  "agent_id": "my-agent-1",
  "action_type": "email.send",
  "action_payload": {
    "recipients": ["user@example.com"],
    "subject": "Weekly report",
    "body": "Here is your update."
  },
  "timestamp": "2026-04-02T12:00:00Z",
  "context": {
    "stated_intent": "Send weekly summary to care team",
    "intent_id": "intent-uuid-optional"
  }
}
```

**Response:**
```json
{
  "action_id": "uuid",
  "verdict": "ALLOW",
  "reason_code": "APPROVED",
  "explanation": "Action is within scope and risk tolerance.",
  "safe_alternative": null,
  "escalation_question": null,
  "escalation_options": [],
  "policy_snapshot_hash": "sha256:abc123..."
}
```

**Verdict values:** `ALLOW` | `BLOCK` | `ESCALATE` | `DEGRADE` | `PAUSE` | `ERROR`

**Reason codes:** `APPROVED` | `SCOPE_VIOLATION` | `RISK_TOO_HIGH` | `DATA_EXFIL` |
`OUT_OF_HOURS` | `NEED_CONFIRMATION` | `LOOP_DETECTED` | `RATE_LIMIT` |
`PROMPT_INJECTION` | `ANOMALY_DETECTED`

---

## POST /v1/output

Scan a tool response for PHI/PII, credential leakage, and bulk data before the
agent uses it. Always call after executing a tool.

**Request:**
```json
{
  "agent_id": "my-agent-1",
  "action_type": "database.query",
  "action_id": "uuid-from-evaluate",
  "response": { "rows": [...], "count": 5 }
}
```

**Response:**
```json
{
  "verdict": "REDACT",
  "payload": { "rows": [...], "count": 5 },
  "findings": [
    { "category": "phi", "pattern": "ssn", "count": 2 },
    { "category": "phi", "pattern": "dob", "count": 2 }
  ],
  "redacted": true
}
```

**Verdict values:** `PASS` | `REDACT` | `BLOCK`

---

## POST /intent/set

Register an intent contract before a multi-step agent session. Enables sequence
drift detection and shared rate budgets across all evaluate() calls.

**Request:**
```json
{
  "intent_id": "intent_abc123",
  "objective": "Summarise daily patient roster for care team",
  "scope": { "database": ["query"], "email": ["send"] },
  "constraints": { "max_risk_level": "MEDIUM", "ttl_seconds": 3600 },
  "risk_level": "medium",
  "approved_by_user": false
}
```

---

## GET /health

Returns gateway health and component status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.1",
  "components": {
    "database": "healthy",
    "ai_advisory": "available",
    "metrics": "enabled"
  }
}
```

---

## GET /stats

Returns decision statistics (counts, latency, verdicts).

**Response:**
```json
{
  "total_decisions": 12450,
  "allow_count": 10200,
  "block_count": 1800,
  "escalate_count": 450,
  "avg_latency_ms": 45,
  "p95_latency_ms": 120
}
```

---

## GET /audit/query

Query the tamper-proof audit log.

**Query parameters:**
- `agent_id` — filter by agent
- `verdict` — filter by verdict (ALLOW, BLOCK, ESCALATE, etc.)
- `start_date` — ISO-8601 start datetime
- `end_date` — ISO-8601 end datetime
- `limit` — max results (default 50, max 1000)
- `offset` — pagination offset

**Response:**
```json
{
  "events": [
    {
      "id": 1234,
      "timestamp": "2026-04-02T12:00:00Z",
      "agent_id": "my-agent-1",
      "action_tool": "email",
      "action_op": "send",
      "decision_verdict": "ALLOW",
      "decision_reason_code": "APPROVED",
      "chain_hash": "sha256:abc..."
    }
  ],
  "total": 100,
  "offset": 0
}
```

---

## GET /audit/verify-chain

Verifies the integrity of the audit chain (tamper detection).

**Response:**
```json
{
  "valid": true,
  "checked_events": 12450,
  "broken_at": null
}
```

---

## GET /agents

List registered agents for the tenant.

**Response:**
```json
{
  "agents": [
    {
      "agent_id": "my-agent-1",
      "name": "Clinical Summary Agent",
      "department": "Cardiology",
      "status": "active",
      "total_actions": 450,
      "total_allowed": 420,
      "total_blocked": 30,
      "registered_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

---

## GET /policy/templates

List available compliance policy templates.

**Response:**
```json
[
  { "id": "hipaa", "name": "HIPAA", "description": "HIPAA-compliant AI governance baseline", "rule_count": 5 },
  { "id": "joint_commission", "name": "Joint Commission", "description": "Joint Commission AI governance standards", "rule_count": 5 },
  { "id": "clinical_governance", "name": "Clinical AI Governance", "description": "PHI minimization and clinical AI guardrails", "rule_count": 4 },
  { "id": "hitrust", "name": "HITRUST CSF", "description": "HITRUST Common Security Framework", "rule_count": 5 },
  { "id": "soc2", "name": "SOC 2 Type II", "description": "SOC 2 security and availability controls", "rule_count": 5 }
]
```

## POST /policy/templates/{template_id}/apply

Apply a compliance template to your tenant. Creates policy rules immediately.
Available templates: `hipaa`, `joint_commission`, `clinical_governance`, `hitrust`, `soc2`.

---

## GET /policy/rules

List all policy rules for the tenant.

## POST /policy/rules

Create a custom policy rule.

**Request:**
```json
{
  "name": "Block bulk EHR export",
  "description": "Block mass patient record exports",
  "condition_tool": "ehr",
  "condition_op": "export",
  "action": "BLOCK",
  "priority": 900,
  "enabled": true
}
```

---

## Error Codes

| HTTP Status | Meaning |
|------------|---------|
| 200 | Success |
| 400 | Bad request (invalid payload) |
| 401 | Unauthorized (invalid or missing API key) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable (gateway degraded) |
