# EDON Gateway – How to Test “How Good” It Is

This doc lists the kinds of tests you can run against the EDON gateway and how to run them.

---

## 1. **Smoke / health**

**What it checks:** Gateway is up and basic endpoints respond.

**How to run:**

```powershell
# From repo root
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

Or with a deployed URL:

```powershell
Invoke-WebRequest -Uri "https://edon-gatewaybk.fly.dev/health" -UseBasicParsing
```

**Good result:** `200` and JSON with `status: "ok"`, `uptime_seconds`, etc.

---

## 2. **Unit tests (pytest)**

**What they check:** Auth, RBAC, credential selection, v1/action and tenant logic, Clerk auth, Clawdbot proxy behavior (no request NameError), etc.

**Location:** `edon_gateway/edon_gateway/test/`

**How to run:**

```powershell
cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
$env:PYTHONPATH = (Get-Location).Path
python -m pytest edon_gateway/test/ -v --tb=short
```

(On Windows, setting `PYTHONPATH` to the `edon_gateway` directory ensures imports resolve.)

Or use the shell script (from repo root, WSL/Git Bash):

```bash
./edon_gateway/run_tests.sh
```

**Good result:** All tests pass (no failures).

---

## 3. **Quick gateway script (health + intents + execute)**

**What it checks:** Health, setting an intent, and an allow/block on `/execute`.

**Script:** `edon_gateway/test_gateway.py`

**How to run:** Start the gateway first, then:

```powershell
cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
python test_gateway.py
```

**Good result:** Health 200, intent set, one ALLOW and one BLOCK as expected.

---

## 4. **Upstream / Clawdbot smoketest (full flow)**

**What it checks:** Health, stats, policy-pack apply, credentials set, Clawdbot invoke (allow + block), decisions and audit query. End-to-end “is the gateway good” for the Clawdbot flow.

**Script:** `scripts/test_upstream_gateway.ps1`

**How to run (gateway running locally with valid tokens):**

```powershell
cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_upstream_gateway.ps1 `
  -EdonToken "YOUR_EDON_GATEWAY_TOKEN" `
  -UpstreamToken "YOUR_CLAWDBOT_TOKEN" `
  -PolicyPack "clawdbot_safe"
```

Optional: `-GatewayUrl "http://localhost:8000"`, `-OutFile ".\scripts\last_gateway_smoketest.log.jsonl"`.

**Good result:** All sections (health, stats, policy apply, credentials, invoke allow, invoke block, decisions, audit) complete without FATAL; log file written.

---

## 5. **Load / performance (p99 latency)**

**What it checks:** Throughput and latency of `POST /v1/action` under load (e.g. 200 requests, 20 concurrent). Can enforce a p99 SLO (e.g. &lt; 100 ms for CI).

**Script:** `edon_gateway/scripts/load_test_v1_action.py`

**How to run:**

```powershell
cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
$env:EDON_GATEWAY_URL = "http://localhost:8000"
$env:EDON_API_TOKEN = "your-token"
python scripts/load_test_v1_action.py
```

Stricter (fail if p99 ≥ 100 ms):

```powershell
python scripts/load_test_v1_action.py --p99-max-ms 100
```

Heavier load (e.g. 2000 requests, 50 concurrent):

```powershell
python scripts/load_test_v1_action.py --requests 2000 --concurrent 50
```

**Good result:** Completed requests, p50/p95/p99 printed; with `--p99-max-ms 100`, exit 0 only if p99 &lt; 100 ms.

---

## 6. **Production-mode security tests**

**What they check:** Strict credentials (e.g. 503 when credential missing), validation (reject oversized/dangerous payloads), auth (401/403 on protected endpoints without token).

**Script:** `edon_gateway/test_production_mode.py`

**How to run:** Start the gateway with production env vars (see `edon_gateway/TEST_RESULTS.md`), then in another terminal:

```powershell
$env:EDON_CREDENTIALS_STRICT = "true"
$env:EDON_VALIDATE_STRICT = "true"
$env:EDON_AUTH_ENABLED = "true"
$env:EDON_API_TOKEN = "<unique-test-token>"
$env:EDON_GATEWAY_URL = "http://localhost:8000"
python edon_gateway/test_production_mode.py
```

**Good result:** All 10 tests pass (correct 503/400/413/401/403 where expected).

---

## 7. **Root-level integration / regression tests**

**What they check:** Broader repo behavior: rate limit, feature ingest validation, v2 APIs, governor, audit, network gating, etc. Some hit the gateway or depend on it.

**Location:** `tests/` at repo root (e.g. `tests/test_rate_limit.py`, `tests/test_audit_log.py`, `tests/test_network_gating.py`, etc.)

**How to run:**

```powershell
cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine
python -m pytest tests/ -v --tb=short -x
```

(`-x` stops on first failure.) Run with gateway (and any required env) if the test expects it.

---

## Summary – “How good is the gateway?”

| Goal | Test to run |
|------|-------------|
| Is it up? | Health: `GET /health` |
| Is code correct? | Unit: `pytest edon_gateway/edon_gateway/test/` |
| Does the main flow work? | `test_gateway.py` or `test_upstream_gateway.ps1` |
| Is it fast enough? | `load_test_v1_action.py` (optionally `--p99-max-ms 100`) |
| Is it secure in prod? | `test_production_mode.py` (with prod env) |
| Full system behavior? | Root `tests/` (pytest) |

For a single “is the gateway good?” check: run **health** + **unit tests** + **load test** (and, if you use Clawdbot, **upstream smoketest**).
