# EDON Gateway API Reference

Base URL: `https://edon-gateway.fly.dev`

All requests require: `X-EDON-TOKEN: <token>`

---

## Core

### `GET /health`
Gateway status, version, uptime, active policy preset.

### `GET /metrics`
Prometheus-format metrics.

### `GET /stats`
JSON stats: decision counts, latency percentiles.

---

## Action Evaluation

### `POST /v1/action`
Evaluate an agent action against active policy.

**Request:**
```json
{
  "action_type": "send_email",
  "agent_id": "agent-123",
  "payload": { "to": "...", "subject": "..." },
  "intent_id": "optional-intent-uuid"
}
```

**Response:**
```json
{
  "action_id": "uuid",
  "verdict": "ALLOW",
  "reason_code": "APPROVED",
  "explanation": "Action is within policy scope.",
  "safe_alternative": {},
  "escalation_question": null,
  "escalation_options": [],
  "policy_snapshot_hash": "sha256...",
  "latency_ms": 45
}
```

**Verdicts:** `ALLOW` · `BLOCK` · `ESCALATE` · `DEGRADE` · `PAUSE` · `ERROR`

**Reason codes:** `APPROVED` · `SCOPE_VIOLATION` · `RISK_TOO_HIGH` · `DATA_EXFIL` · `OUT_OF_HOURS` · `NEED_CONFIRMATION` · `LOOP_DETECTED` · `RATE_LIMIT` · `PROMPT_INJECTION` · `ANOMALY_DETECTED`

---

## Decisions & Audit

### `GET /audit/query`
Query decision history. Role-restricted (requires `audit` permission).

| Param | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Filter by agent |
| `verdict` | string | Filter by verdict |
| `from` | ISO date | Start range |
| `to` | ISO date | End range |
| `limit` | int | Max results (default 50) |

### `GET /decisions/query`
Same as audit but available to all roles.

---

## Policy

### `GET /policy-packs`
List available policy packs.

### `POST /policy-packs/{name}/apply`
Activate a policy pack.

**Pack names:** `casual_user` · `market_analyst` · `ops_commander` · `founder_mode` · `helpdesk` · `autonomy_mode`

### `GET /intent/get`
Active intent contract (scope, constraints, risk_level).

---

## Agents

### `GET /agents`
List registered agent fleet.

### `POST /agents`
Register a new agent.

### `GET /agents/{id}`
Agent profile + metadata.

### `GET /agents/{id}/stats`
Per-agent time-series stats (30d).

### `PATCH /agents/{id}/status`
Update agent status: `active` · `paused` · `retired`

---

## Settings

Tenant self-service configuration. All endpoints are scoped to the authenticated tenant.

### `GET /settings/ip-allowlist`
Return the tenant's current IP allowlist.

**Response:**
```json
{
  "cidrs": ["203.0.113.0/24", "198.51.100.5/32"],
  "enabled": true
}
```

`enabled` is `true` when at least one CIDR entry exists. When enabled, requests from IPs outside the allowlist are rejected with `403`.

### `POST /settings/ip-allowlist`
Add a CIDR block to the tenant's IP allowlist.

> **Warning:** Once any entry is added, ALL requests from IPs outside the allowlist will be rejected with 403. Add your own IP before enabling.

**Request:**
```json
{
  "cidr": "203.0.113.0/24"
}
```

`cidr` accepts IPv4/IPv6 CIDR notation (e.g. `203.0.113.0/24`) or a bare IP (e.g. `1.2.3.4`, automatically normalized to `/32` or `/128`).

**Response (`201`):**
```json
{
  "ok": true,
  "cidr": "203.0.113.0/24",
  "message": "CIDR added to allowlist"
}
```

If the CIDR already exists, returns `200` with `"message": "Already in allowlist"`.

**Errors:**

| Status | Detail |
|--------|--------|
| `401` | Tenant context required |
| `422` | Invalid CIDR |
| `501` | IP allowlist not supported by this backend |

### `DELETE /settings/ip-allowlist`
Remove a CIDR block from the tenant's IP allowlist.

**Request:**
```json
{
  "cidr": "203.0.113.0/24"
}
```

**Response (`200`):**
```json
{
  "ok": true,
  "cidr": "203.0.113.0/24"
}
```

`ok` is `false` if the CIDR was not found in the allowlist.

**Errors:**

| Status | Detail |
|--------|--------|
| `401` | Tenant context required |
| `422` | Invalid CIDR |
| `501` | IP allowlist not supported by this backend |

---

## Admin

### `POST /admin/provision`
Bootstrap a new tenant. Requires `X-Bootstrap-Secret` header.