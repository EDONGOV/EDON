# EDON Gateway — Disaster Recovery Runbook

**Last reviewed:** 2026-04-02  
**RTO target:** 30 minutes  
**RPO target:** 24 hours (SQLite) / 1 hour (PostgreSQL with WAL archiving)

---

## 1. Overview

EDON Gateway is deployed on:

| Component | Platform | URL |
|-----------|----------|-----|
| Backend API | Fly.io (`edon-gateway` app, `iad` region) | https://edon-gateway.fly.dev |
| Frontend SPA | Render.com | https://agent.edoncore.com |
| Database | SQLite on Fly.io volume `/app/data` or PostgreSQL (if `DATABASE_URL` set) |

---

## 2. Backup Procedures

### 2a. SQLite Backup (default)

The SQLite database lives at `/app/data/edon_gateway.db` on the Fly.io machine.

**Daily backup (manual):**
```bash
# SSH into the machine
fly ssh console -a edon-gateway

# Inside the container:
cp /app/data/edon_gateway.db /app/data/edon_gateway_$(date +%Y%m%d).db
exit

# Download to local machine
fly sftp get /app/data/edon_gateway_$(date +%Y%m%d).db ./backups/
```

**Recommended:** Set up a daily cron job that dumps the SQLite file to S3/Backblaze B2:
```bash
# Run from a separate machine with access to Fly.io SSH
fly ssh console -a edon-gateway --command \
  "sqlite3 /app/data/edon_gateway.db .dump" \
  > backup_$(date +%Y%m%d).sql
# Then upload to S3:
aws s3 cp backup_$(date +%Y%m%d).sql s3://your-bucket/edon-backups/
```

**Backup frequency:** Daily minimum. Before any schema migration.

### 2b. PostgreSQL Backup

If `DATABASE_URL=postgresql://...` is configured (recommended for production):

```bash
# List available backups
fly postgres backup list -a edon-gateway-db

# Create a manual backup before deployments
fly postgres backup create -a edon-gateway-db

# Download a backup
fly postgres backup download <backup-id> -a edon-gateway-db
```

Fly.io automatically takes daily snapshots of Postgres instances on paid plans.

---

## 3. Recovery Scenarios

### Scenario A: Backend pod crash / restart loop

Fly.io automatically restarts crashed VMs. Typical recovery time: < 2 minutes.

**Verify:**
```bash
fly status -a edon-gateway          # Check machine state
fly logs -a edon-gateway            # Check recent logs for error
curl https://edon-gateway.fly.dev/health  # Confirm healthy
```

**If auto-restart fails:**
```bash
fly machine restart <machine-id> -a edon-gateway
# Or redeploy from last known-good image:
fly deploy --image <registry/image:tag> -a edon-gateway
```

### Scenario B: Database corruption (SQLite)

```bash
# 1. SSH in and check integrity
fly ssh console -a edon-gateway
sqlite3 /app/data/edon_gateway.db "PRAGMA integrity_check;"

# 2. If corrupt, restore from latest backup
cp /app/data/edon_gateway_YYYYMMDD.db /app/data/edon_gateway.db

# 3. Or restore from S3 dump
sqlite3 /app/data/edon_gateway.db < backup_YYYYMMDD.sql

# 4. Restart the app
fly machine restart -a edon-gateway
```

### Scenario C: Full region outage (Fly.io IAD down)

```bash
# Deploy to a different region
fly scale count 1 --region lhr -a edon-gateway
# Or redeploy to a new region
fly deploy -a edon-gateway --region lhr

# Update DNS/CNAME to point to new region endpoint if needed
```

Note: SQLite volumes are region-specific. If the region is unavailable, restore from the last off-site backup to the new region's volume.

### Scenario D: Accidental data deletion

```bash
# 1. Stop writes immediately (scale to 0 machines)
fly scale count 0 -a edon-gateway

# 2. Restore from the most recent backup before the deletion
fly ssh console -a edon-gateway
cp /app/data/edon_gateway.db /app/data/edon_gateway_corrupted_$(date +%Y%m%d%H%M).db
sqlite3 /app/data/edon_gateway.db < backup_before_deletion.sql

# 3. Resume service
fly scale count 1 -a edon-gateway

# 4. Audit what was deleted using the tamper-proof audit chain
curl -H "X-EDON-TOKEN: $ADMIN_TOKEN" \
  "https://edon-gateway.fly.dev/audit/verify-chain"
```

### Scenario E: Security breach — token rotation

```bash
# 1. Immediately revoke all API keys for affected tenants
# Via API:
curl -X DELETE -H "X-EDON-TOKEN: $ADMIN_TOKEN" \
  "https://edon-gateway.fly.dev/api-keys/<key-id>"

# 2. Rotate the EDON_API_TOKEN secret
fly secrets set EDON_API_TOKEN=$(openssl rand -hex 32) -a edon-gateway

# 3. Rotate Clerk signing keys (if Clerk auth was compromised)
# Log into Clerk dashboard → API Keys → Rotate

# 4. Review audit log for suspicious activity
curl -H "X-EDON-TOKEN: $NEW_ADMIN_TOKEN" \
  "https://edon-gateway.fly.dev/audit/query?limit=1000&start_date=<incident_date>"

# 5. Export evidence package
curl -H "X-EDON-TOKEN: $NEW_ADMIN_TOKEN" \
  "https://edon-gateway.fly.dev/compliance/export?format=json" \
  > evidence_$(date +%Y%m%d).json
```

---

## 4. Rollback Procedure

See [`deployment-rollback.md`](./deployment-rollback.md) for the full code rollback procedure.

---

## 5. RTO / RPO Targets

| Database | RPO | RTO |
|----------|-----|-----|
| SQLite + daily backup | 24 hours | 30 minutes |
| SQLite + hourly backup | 1 hour | 30 minutes |
| PostgreSQL (Fly) | 1 hour (WAL) | 15 minutes |

**After restoration, always verify:**
1. `GET /health` returns `{"status": "healthy"}`
2. `GET /audit/verify-chain` returns `{"valid": true}`
3. A test `POST /v1/action` returns a valid verdict

---

## 6. Contacts & Escalation

| Role | Name | Contact |
|------|------|---------|
| On-call engineer | _fill in_ | _fill in_ |
| Fly.io support | — | https://fly.io/docs/support/ |
| Incident channel | — | _fill in Slack/Discord channel_ |

---

## 7. DR Drill Schedule

Run a DR drill quarterly:

1. **Backup test:** restore SQLite to a test instance, verify data integrity
2. **Failover test:** deploy to a secondary region, verify health endpoint
3. **Rollback test:** deploy a known-bad image, then roll back to previous
4. **Token rotation:** rotate all secrets in staging, verify auth still works

Document drill results and update this runbook with findings.
