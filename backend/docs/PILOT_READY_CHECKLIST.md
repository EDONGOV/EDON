# Pilot-ready checklist (e.g. FedEx)

**Goal:** Get edon-gatewaybk (or edon-gateway) live with Postgres, verify p99, then onboard the pilot customer (e.g. FedEx) in ~1 hour + 15 min.

---

## Step 1: Set DATABASE_URL + add Postgres driver (~5 min)

**1.1** Add Postgres URL to Fly secrets (use your real RDS URL and password):

```powershell
fly secrets set DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@database-1.c2r6emwsal3n.us-east-1.rds.amazonaws.com:5432/postgres?sslmode=require" --app edon-gatewaybk
```

**1.2** `psycopg2-binary` is already in `edon_gateway/requirements.txt`. No change needed if you have it; if not, add:

```
psycopg2-binary>=2.9.0
```

---

## Step 2: Deploy (~10 min)

From the repo folder that contains the Dockerfile and fly config:

```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
fly deploy --app edon-gatewaybk -c fly.edon-gatewaybk.toml
```

Wait for the release to complete. Check logs: you should see "Database schema version OK" and "Using PostgreSQL database" (if DATABASE_URL is set).

---

## Step 3: Load test (~15 min)

Set your gateway URL and token, then run the load test:

```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
$env:EDON_GATEWAY_URL = "https://edon-gatewaybk.fly.dev"
$env:EDON_API_TOKEN = "fedex-pilot-68cee4d633955320720b8a39"
python scripts/load_test_v1_action.py --requests 200 --concurrent 20 --p99-max-ms 8000
```

**Note:** When you run from your laptop, client-measured p99 includes network RTT and queueing, so use a relaxed threshold (e.g. `--p99-max-ms 8000`). Server-side latency is ~100–200 ms per request (see Fly logs). For strict p99 &lt; 150 ms, run the load test from a machine in the same region as Fly (e.g. a Fly job in dfw).

---

## Step 4: Create pilot tenant + API key (~10 min)

**Option A – Bootstrap endpoint (one tenant + one key)**  
If you have `EDON_BOOTSTRAP_SECRET` set in Fly secrets:

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "X-Bootstrap-Secret" = "YOUR_EDON_BOOTSTRAP_SECRET"
}
$body = '{"token":"fedex-pilot-key-CHOOSE-A-LONG-SECRET","tenant_id":"fedex-pilot","name":"FedEx Pilot"}'
Invoke-WebRequest -Uri "https://edon-gatewaybk.fly.dev/admin/bootstrap-api-key" -Method POST -Headers $headers -Body $body -UseBasicParsing
```

Then give FedEx:
- **URL:** `https://edon-gatewaybk.fly.dev`
- **API key (token):** the value you put in `token` (e.g. `fedex-pilot-key-CHOOSE-A-LONG-SECRET`).

**Option B – Create tenant + key via DB or existing admin**  
If you use Stripe/signup or an admin UI, create a tenant (e.g. `fedex-pilot`) and generate an API key; give FedEx that key and the gateway URL.

---

## Step 5: Handoff to pilot (~5 min)

Send the pilot:

1. **Base URL:** `https://edon-gatewaybk.fly.dev` (or your chosen gateway URL).
2. **Auth:** Header `X-EDON-TOKEN: <their API key>` (or `Authorization: Bearer <their API key>`).
3. **Endpoints:**
   - **GET /health** – Check gateway is up.
   - **POST /v1/action** – Submit an action for governance; body must include `agent_id`, `action_type`, `action_payload` (see API spec). Response: allow / block / degrade + `decision_id`.

They should call **POST /v1/action** before executing each governed action; use the response to allow, block, or degrade.

---

## Summary

| Step | What | Time |
|------|------|------|
| 1 | `fly secrets set DATABASE_URL=...` + psycopg2 in requirements | ~5 min |
| 2 | `fly deploy --app edon-gatewaybk -c fly.edon-gatewaybk.toml` | ~10 min |
| 3 | Run load test, confirm p99 < 100 ms | ~15 min |
| 4 | Create FedEx tenant + API key (bootstrap or admin) | ~10 min |
| 5 | Send URL, key, GET /health, POST /v1/action | ~5 min |

**Total:** ~1 hour (steps 1–3) + ~15 min (steps 4–5). Pilot-ready the same day.
