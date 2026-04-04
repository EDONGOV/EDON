# API Reference

Base URL: `https://edon-gateway.fly.dev`  
Auth header: `X-EDON-TOKEN: <your-api-key>`

Interactive docs: https://edon-gateway.fly.dev/docs

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
  "estimated_risk": "low",
  "context": {
    "intent_id": "intent-uuid-optional",
    "session_id": "sess-abc123"
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
      "name": "Research Agent",
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

## GET /policy-packs

List available policy packs.

**Response:**
```json
{
  "packs": [
    {"name": "casual_user", "description": "Low-stakes agents and demos"},
    {"name": "market_analyst", "description": "Read-only research"},
    {"name": "ops_commander", "description": "DevOps automation"},
    {"name": "founder_mode", "description": "Trusted agents, broad permissions"},
    {"name": "helpdesk", "description": "Customer support bots"},
    {"name": "autonomy_mode", "description": "Fully autonomous agents"}
  ]
}
```

---

## POST /policy-packs/{name}/apply

Apply a policy pack for the current tenant.

**Response:**
```json
{
  "applied": "ops_commander",
  "applied_at": "2026-04-02T12:00:00Z"
}
```

---

## Error Codes

| HTTP Status | Meaning |
|------------|---------|
| 200 | Success |
| 400 | Bad request (invalid payload) |
| 401 | Unauthorized (invalid or missing token) |
| 403 | Forbidden (RBAC violation) |
| 404 | Not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable (gateway degraded) |
