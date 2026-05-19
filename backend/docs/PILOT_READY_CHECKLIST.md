# Pilot-ready checklist (e.g. FedEx)

**Goal:** Get edon-gatewaybk (or edon-gateway) live with Postgres, verify p99, then onboard the pilot customer (e.g. FedEx) in ~1 hour + 15 min.

---

## 0: Pilot wedge

Pick one workflow and freeze scope:

- **Wedge:** hospital AI governance for record writeback and escalations
- **Buyer:** clinical ops, IT security, informatics
- **Systems:** SSO IdP, EHR/EMR, SIEM, Teams/Slack
- **Pilot mode:** advisory first, governed for high-risk writebacks, no autonomous clinical authority

---

## Step 1: Set DATABASE_URL + add Postgres driver (~5 min)

**1.1** Add Postgres URL to Fly secrets (use your real RDS URL and password):

```powershell
fly secrets set DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@database-1.c2r6emwsal3n.us-east-1.rds.amazonaws.com:5432/postgres?sslmode=require" --app edon-gatewaybk
```

**1.2** `psycopg2-binary` is already in `edon_gateway/requirements.gateway.txt`. No change needed if you have it; if not, add:

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

## 5.1 One deployment path

Use one path for the pilot and nothing else:

1. Enable the dependency graph, Dependabot alerts, and automatic dependency submission in GitHub.
2. Deploy the gateway with Postgres and the enterprise identity settings enabled.
3. Create one tenant and one pilot API key.
4. Configure one IdP and one RBAC map.
5. Validate one governed action loop end to end.

---

## 5.2 SSO setup

Use one identity provider for the pilot:

- **Preferred:** Microsoft Entra ID, Okta, or Ping Identity
- **Fallback for smaller orgs:** Google Workspace
- **Required controls:** SAML or OIDC, admin MFA, phishing-resistant MFA for privileged roles

---

## 5.3 RBAC map

Use the enterprise role split:

| Role | Access |
|------|--------|
| super_admin | tenant setup, identity, billing, emergency controls |
| governance_admin | policies, approvals, risk settings |
| security_admin | logs, incidents, keys, integrations |
| operator | live decisions, escalations |
| auditor | read-only audit/replay |
| developer | SDK/API sandbox access |
| viewer | dashboard only |

---

## 5.4 Rollback path

Keep the rollback path simple:

- disable the tenant or kill switch
- revert the connector registration
- restore the last known-good policy pack
- verify audit continuity after rollback
- record the rollback in the restore-drill evidence file

---

## 5.5 Buyer-facing runbook

Give the buyer a short operational runbook:

1. Sign in through SSO.
2. Open the tenant-scoped console.
3. Submit one governed action.
4. Review the decision record and audit trail.
5. Export the evidence pack.
6. Use the rollback path if the pilot exceeds scope.

---

## 2.1 Governed Action Matrix

Use this in the pilot pack so procurement and security can see which actions are governed, how risky they are, and what happens if rollback is needed.

| Action | Risk | Approval | Rollback | Logged |
|--------|------|----------|----------|--------|
| Draft patient note | Medium | Optional | Yes | Yes |
| Record writeback | High | Required | Partial | Yes |
| Medication update | Critical | Required | Limited | Yes |
| Billing claim submission | High | Required | Partial | Yes |
| Robot motion command | Critical | Required | Limited | Yes |

---

## 2.2 Pilot Safety Mode

Start the pilot in constrained mode:

- no autonomous clinical authority
- all high-risk actions require human approval
- no medication execution without explicit policy exception
- rollback required on governed writebacks where supported
- fail-closed on connector uncertainty

---

## 2.3 Operational Guarantees

The pilot should advertise simple operational targets:

- policy evaluation latency target: `< 500 ms`
- audit persistence: `100%` for governed actions
- rollback execution: documented and testable
- tenant isolation: strict
- pilot uptime: explicit and conservative

---

## 2.4 Deployment Classification

Use a maturity ladder so everyone knows what mode the deployment is in:

| Classification | Meaning |
|----------------|---------|
| Advisory | No execution authority |
| Governed | Approval-bound execution with EDON decision binding |
| Autonomous | Policy-scoped autonomous execution with strict bounds |

---

## 2.5 Edge Runtime Boundary

If edge nodes are part of the deployment, keep the boundary explicit:

- local policy evaluation is allowed
- cloud escalation is optional
- same governance semantics apply at the edge
- no edge bypass around the decision kernel
- edge node identity is required

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
