# EDON Gateway — Data Dictionary

**Version:** 1.0
**Last updated:** 2026-02-24

This document defines all persistent data structures, their fields, types, constraints, and purpose.

---

## Tables

### `audit_events`

Primary record of every governance decision made by EDON Gateway. **Append-only** (backed by SQLite triggers). Cryptographically chained via `chain_hash`.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER (PK, autoincrement) | No | Monotonically increasing row ID |
| `action_id` | TEXT | No | UUID of the action request |
| `agent_id` | TEXT | No | Identifier of the robot/agent making the request |
| `customer_id` | TEXT | No | Tenant identifier (multi-tenant isolation key) |
| `action_payload` | TEXT (JSON) | No | Full action details. May be Fernet-encrypted if `is_payload_encrypted=1` |
| `decision_payload` | TEXT (JSON) | No | Full decision details: verdict, reason_code, explanation |
| `context` | TEXT (JSON) | Yes | Context snapshot at decision time (CAV score, environment, etc.) |
| `intent_id` | TEXT | Yes | Associated intent contract ID, if any |
| `timestamp` | TEXT (ISO-8601) | No | UTC timestamp of the decision |
| `verdict` | TEXT | No | Decision outcome: `ALLOW`, `BLOCK`, `DEGRADE`, `ESCALATE` |
| `chain_hash` | TEXT | No | SHA-256 hash of (previous_chain_hash + this_row_content). Enables tamper detection |
| `is_payload_encrypted` | INTEGER (0/1) | No | 1 if `action_payload` is Fernet-encrypted, 0 otherwise |

**Indexes:**
- `idx_audit_agent_id` — fast lookup by `agent_id`
- `idx_audit_customer_id` — fast tenant-scoped queries
- `idx_audit_timestamp` — time-range queries
- `idx_audit_agent_timestamp` — compound: `(agent_id, timestamp)` for per-robot timelines
- `idx_audit_customer_timestamp` — compound: `(customer_id, timestamp)` for tenant audit views
- `idx_audit_chain` — `chain_hash` for integrity validation

**Constraints:**
- No UPDATE or DELETE (enforced by SQLite trigger `prevent_audit_update` / `prevent_audit_delete`)
- `chain_hash` validated on read by `validate_audit_chain()`
- `is_payload_encrypted` defaults to 0

---

### `api_keys`

Hashed API credentials for tenant authentication.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER (PK, autoincrement) | No | Row ID |
| `customer_id` | TEXT (FK→customers) | No | Owning tenant |
| `key_hash` | TEXT (UNIQUE) | No | bcrypt hash of the raw API key |
| `name` | TEXT | Yes | Human-readable label (e.g., "robot-fleet-prod") |
| `role` | TEXT | No | RBAC role: `admin`, `operator`, `agent`, `read_only`. Default: `agent` |
| `created_at` | TEXT (ISO-8601) | No | Creation timestamp |
| `revoked_at` | TEXT (ISO-8601) | Yes | Revocation timestamp; NULL means active |

**Notes:**
- Raw API key is NEVER stored. Only the bcrypt hash.
- Key format: `ek_<environment>_<random>` (e.g., `ek_live_abc123`)

---

### `customers`

Tenant registry.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `customer_id` | TEXT (PK) | No | Unique tenant identifier (e.g., `customer_acme_123`) |
| `customer_name` | TEXT | No | Display name |
| `email` | TEXT | No | Primary contact email |
| `plan` | TEXT | No | Billing plan: `free`, `starter`, `pro`, `enterprise`. Default: `free` |
| `created_at` | TEXT (ISO-8601) | No | Registration timestamp |
| `metadata` | TEXT (JSON) | Yes | Arbitrary key-value tenant config |

---

### `intents`

Active intent contracts that scope what an agent is permitted to do.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `intent_id` | TEXT (PK) | No | UUID |
| `objective` | TEXT | No | Human-readable goal (e.g., "Move pallet A to bay 3") |
| `scope` | TEXT (JSON) | No | Allowed tools and operations: `{"memory": ["get", "set"], "email": []}` |
| `constraints` | TEXT (JSON) | No | Risk constraints: `{"max_risk": "medium", "no_external_comms": true}` |
| `risk_level` | TEXT | No | `low`, `medium`, `high`, `critical` |
| `approved_by_user` | INTEGER (0/1) | No | 1 if a human operator approved this intent |
| `created_at` | TEXT (ISO-8601) | No | Creation timestamp |
| `updated_at` | TEXT (ISO-8601) | No | Last modification timestamp |

---

### `policy_rules`

Individual governance rules evaluated by `PolicyEngine`.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER (PK, autoincrement) | No | Row ID |
| `customer_id` | TEXT | Yes | NULL = global rule, non-NULL = tenant-specific |
| `rule_id` | TEXT (UNIQUE) | No | Stable rule identifier (e.g., `rule_cav_threshold`) |
| `name` | TEXT | No | Human label |
| `description` | TEXT | Yes | Rule purpose |
| `condition` | TEXT (JSON) | No | Condition spec: `{"type": "threshold", "field": "context.cav_score", "operator": "gte", "value": 0.7}` |
| `action` | TEXT | No | `BLOCK`, `ALLOW`, `DEGRADE`, `ESCALATE` |
| `priority` | INTEGER | No | Evaluation order (lower = higher priority). Default: 100 |
| `enabled` | INTEGER (0/1) | No | 1 = active. Default: 1 |
| `created_at` | TEXT (ISO-8601) | No | Creation timestamp |

**Condition types:**
- `threshold` — numeric comparison (`gte`, `lte`, `gt`, `lt`, `eq`)
- `range` — `{"min": 0.0, "max": 0.5}` (inclusive)
- `equals` — exact string/value match
- `contains` — substring or list membership

**Field path:** dot-notation into the evaluation context, e.g., `context.cav_score`, `action.type`

---

### `schema_version`

Single-row table tracking DB schema version.

| Column | Type | Description |
|--------|------|-------------|
| `version` | TEXT | Schema version string (e.g., `"1"`) |
| `updated_at` | TEXT | Last migration timestamp |

---

### `counters`

General-purpose atomic counters (used for rate limiting, usage tracking).

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT (PK) | Counter key, e.g., `rate_limit:agent-001:minute:202602241200` |
| `value` | INTEGER | Current count |
| `expires_at` | TEXT | ISO-8601 expiry; NULL = never expires |

---

## REST API Request/Response Schemas

### `POST /v1/action` — Request

```json
{
  "agent_id":       "string (required, non-empty)",
  "action_type":    "string (required): tool_call | state_report | intent_update | ...",
  "action_payload": {
    "tool":   "string (required for tool_call)",
    "op":     "string (required for tool_call)",
    "params": "object (optional)"
  },
  "timestamp":  "ISO-8601 string (optional, defaults to now)",
  "context":    "object (optional): {cav_score, environment, ...}"
}
```

Extra top-level fields → HTTP 422 (strict schema).

### `POST /v1/action` — Response

```json
{
  "verdict":     "ALLOW | BLOCK | DEGRADE | ESCALATE",
  "decision_id": "uuid string",
  "reason_code": "string: OK | POLICY_BLOCK | RATE_LIMIT | ...",
  "explanation": "human-readable string",
  "timestamp":   "ISO-8601 string"
}
```

---

## Audit Chain Integrity

The `chain_hash` forms a linked list:
```
chain_hash[0] = SHA256("" + row_0_content)
chain_hash[1] = SHA256(chain_hash[0] + row_1_content)
chain_hash[N] = SHA256(chain_hash[N-1] + row_N_content)
```

`row_content` = `f"{action_id}|{agent_id}|{customer_id}|{timestamp}|{verdict}"`

Any tampering with a row breaks the chain from that point forward. Validated by `validate_audit_chain()` in `persistence/database.py`.

---

## Data Retention

| Data | Retention | Notes |
|------|-----------|-------|
| Audit events | Forever (append-only) | Archive to cold storage after 90 days in production |
| Rate limit counters | Auto-expire by key name (minute/hour/day rolling window) | |
| API keys | Until revoked | Soft-delete via `revoked_at` |
| Intents | Until explicitly deleted | |

---

## Sensitive Fields

| Field | Classification | Handling |
|-------|---------------|----------|
| `api_keys.key_hash` | Secret | bcrypt hash only; raw key never stored |
| `audit_events.action_payload` | Confidential | Optional Fernet encryption at rest |
| `audit_events.context` | Sensitive | Not encrypted by default; avoid storing raw PII |
| `customers.email` | PII | Stored plaintext; encrypt at DB-level in regulated deployments |
