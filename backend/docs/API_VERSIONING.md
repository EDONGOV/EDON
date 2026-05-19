# EDON Gateway — API Versioning Policy

**Version:** 1.0
**Last updated:** 2026-02-24

---

## 1. Versioning Scheme

EDON Gateway uses **URL-path versioning** for stability and clarity:

```
/v1/action       ← stable, production
/v2/action       ← future (not yet released)
```

Internal version format: `MAJOR.MINOR.PATCH` (SemVer).

| Change type | Version bump | Policy |
|-------------|-------------|--------|
| Breaking change to request/response schema | MAJOR (v1 → v2) | Old version kept for 6 months |
| New optional field in response | MINOR | Backwards-compatible; no version bump |
| Bug fix, security patch | PATCH | Deploy immediately |
| New endpoint added | MINOR | No break to existing clients |
| Endpoint deprecated | MINOR | 3-month deprecation notice |
| Endpoint removed | MAJOR | Only after 6-month grace period |

---

## 2. Current API Version

**Gateway version:** `1.0.1`
**API version:** `v1`
**Stability:** Production

Check version:
```bash
curl http://localhost:8000/version
# {"version": "1.0.1", "git_sha": "abc123"}
```

---

## 3. Endpoint Inventory

### v1 Endpoints (Stable)

| Method | Path | Purpose | Auth Required |
|--------|------|---------|---------------|
| `POST` | `/v1/action` | Primary governance decision | Yes |
| `POST` | `/execute` | Legacy action execution | Yes |
| `POST` | `/intent/set` | Register intent contract | Yes |
| `GET` | `/intent/get` | Retrieve intent | Yes |
| `GET` | `/decisions/query` | Query audit events | Yes |
| `GET` | `/audit/query` | Query audit trail | Yes |
| `GET` | `/health` | Health check | No |
| `GET` | `/healthz` | Health check (alias) | No |
| `GET` | `/metrics` | Prometheus metrics | No (restrict via network) |
| `GET` | `/version` | Version info | No |
| `GET` | `/docs` | OpenAPI UI | No |
| `GET` | `/openapi.json` | OpenAPI spec | No |

### Policy Management Endpoints (Stable)

| Method | Path | Purpose | Required Role |
|--------|------|---------|--------------|
| `GET` | `/policy/rules` | List policy rules | `viewer`+ |
| `POST` | `/policy/rules` | Create rule | `governance_admin` |
| `PUT` | `/policy/rules/{id}` | Update rule | `governance_admin` |
| `DELETE` | `/policy/rules/{id}` | Delete rule | `governance_admin` |
| `POST` | `/policy/evaluate` | Test rule evaluation | `operator`+ |
| `GET` | `/policy/packs` | List available policy packs | `viewer`+ |
| `POST` | `/policy/packs/{name}/apply` | Apply policy pack | `governance_admin` |

### Auth Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/keys` | Create API key |
| `GET` | `/auth/keys` | List API keys |
| `DELETE` | `/auth/keys/{id}` | Revoke API key |

Enterprise deployments should use SSO-only identity flows and create
`super_admin`, `governance_admin`, `security_admin`, `operator`, `auditor`,
`developer`, or `viewer` keys by default. Legacy roles exist only for
compatibility with older tenants.

---

## 4. Breaking Changes Policy

### What constitutes a breaking change

- Removing a required field from a request schema
- Renaming an existing field
- Changing a field type (e.g., string → object)
- Changing HTTP status codes for existing scenarios
- Removing a response field that clients depend on
- Changing authentication requirements

### What is NOT a breaking change

- Adding a new **optional** request field (ignored if extra fields forbidden, returned as 422 only if strict)
- Adding a new response field (clients should ignore unknown fields)
- Adding a new endpoint
- Tightening validation (e.g., min length) with 3+ months notice
- Changing error message text (not `code`)

---

## 5. Deprecation Process

1. **Announce** in CHANGELOG and via API header: `Deprecation: true` + `Sunset: <date>`
2. **3-month notice** minimum before removing non-critical endpoints
3. **6-month notice** for breaking changes to `/v1/action` or `/execute`
4. **Keep old version** running in parallel during deprecation window
5. **Remove** only after sunset date

Example deprecation header:
```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Mon, 01 Sep 2026 00:00:00 GMT
Link: <https://docs.edoncore.com/migration/v2>; rel="successor-version"
```

---

## 6. `/v1/action` Schema (Canonical)

### Request (strict — extra fields rejected with HTTP 422)

```typescript
{
  agent_id:       string;   // required, non-empty
  action_type:    string;   // required: "tool_call" | "state_report" | "intent_update" | "navigation" | "manipulation" | "sensor_read"
  action_payload: {
    tool?:   string;        // required when action_type = "tool_call"
    op?:     string;        // required when action_type = "tool_call"
    params?: object;        // optional
    [key: string]: unknown; // other fields allowed in payload
  };
  timestamp?:  string;      // ISO-8601, defaults to server time
  context?:    object;      // optional: { cav_score?: number, environment?: string, ... }
}
```

### Response

```typescript
{
  verdict:     "ALLOW" | "BLOCK" | "DEGRADE" | "ESCALATE";
  decision_id: string;       // UUID
  reason_code: string;       // "OK" | "POLICY_BLOCK" | "RATE_LIMIT" | "VALIDATION_ERROR" | ...
  explanation: string;       // Human-readable
  timestamp:   string;       // ISO-8601
}
```

### Error responses

| HTTP Status | Condition |
|-------------|-----------|
| 400 | Missing required field or semantic validation failure |
| 401 | Missing or invalid API token |
| 403 | Valid token but insufficient role (RBAC) |
| 422 | Extra unknown field in request body |
| 429 | Rate limit exceeded (`Retry-After` header set) |
| 500 | Internal server error (gateway bug) |
| 503 | Downstream dependency unavailable |

---

## 7. Client Integration Guide

### Minimal integration (Python)

```python
import requests

GATEWAY_URL = "https://your-gateway.edoncore.com"
API_KEY = "ek_live_your_api_key"

response = requests.post(
    f"{GATEWAY_URL}/v1/action",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "X-EDON-TOKEN": API_KEY,
        "Content-Type": "application/json",
    },
    json={
        "agent_id": "robot-001",
        "action_type": "tool_call",
        "action_payload": {
            "tool": "navigation",
            "op": "move_to",
            "params": {"x": 10.5, "y": 3.2, "speed": 0.5},
        },
        "context": {"cav_score": 0.15},
    },
    timeout=2,  # 2s timeout — SLO is 100ms p99
)

decision = response.json()
if decision["verdict"] == "ALLOW":
    execute_movement()
elif decision["verdict"] == "BLOCK":
    log_blocked(decision["reason_code"], decision["explanation"])
```

### Retry policy

```python
import time

MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds

for attempt in range(MAX_RETRIES):
    resp = requests.post(...)
    if resp.status_code == 200:
        break
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        time.sleep(retry_after)
    elif resp.status_code >= 500:
        time.sleep(RETRY_DELAY * (attempt + 1))
    else:
        # 4xx — don't retry
        break
```

---

## 8. Changelog

### v1.0.1 (2026-02-24)
- Added `POST /v1/action` endpoint (primary governance API)
- Added RBAC middleware (enterprise roles with narrow legacy compatibility aliases)
- Added field-level Fernet encryption for audit payloads
- Added PostgreSQL backend support via `DATABASE_URL`
- Added latency SLO tracking (`X-Response-Time-Ms` header)
- Added policy evaluation timeout (50ms, configurable)
- Added log scrubbing filter (secrets redacted from all log output)
- Added compound indexes on audit_events for 100-agent scale

### v1.0.0 (2025-Q4)
- Initial release
- Core governance engine (`/execute`)
- Intent contracts
- Rate limiting (10K req/min)
- Cryptographic audit chain
- Prometheus metrics
