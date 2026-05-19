# EDON Gateway — Operations Runbook

**Audience:** SRE / DevOps / On-call engineers
**Last updated:** 2026-02-24
**Version:** 1.0

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Starting and Stopping the Gateway](#2-starting-and-stopping-the-gateway)
3. [Health Checks](#3-health-checks)
4. [Key Environment Variables](#4-key-environment-variables)
5. [Logs](#5-logs)
6. [Metrics (Prometheus)](#6-metrics-prometheus)
7. [Database Operations](#7-database-operations)
8. [Encryption Key Rotation](#8-encryption-key-rotation)
9. [Rate Limiting](#9-rate-limiting)
10. [Alert Runbooks](#10-alert-runbooks)
11. [Scaling for 100 Robots](#11-scaling-for-100-robots)
12. [Disaster Recovery](#12-disaster-recovery)

---

## 1. Architecture Overview

```
Robot → EDON Gateway (FastAPI/uvicorn)
                 ↓
         Middleware stack:
           LatencySLO → Auth → RBAC → RateLimit → Validation → MAGValidation
                 ↓
         PolicyEngine (50ms timeout, fail-safe)
                 ↓
         SQLite (development only) / PostgreSQL (required for production)
                 ↓
         Audit trail (append-only, SHA-256 chain, optional Fernet encryption)
```

**Ports:** 8000 (HTTP)
**Database:** SQLite (development only) or PostgreSQL (required for production, set `DATABASE_URL=postgresql://...`)
**Metrics:** `/metrics` (Prometheus text format)
**Health:** `/health` or `/healthz`

---

## 2. Starting and Stopping the Gateway

### Development
```bash
cd edon_gateway
EDON_AUTH_ENABLED=false uvicorn edon_gateway.main:app --reload --port 8000
```

### Production (single process)
```bash
cd edon_gateway
EDON_API_TOKEN=<token> \
EDON_DB_ENCRYPTION_KEY=<fernet-key> \
DATABASE_URL=postgresql://user:pass@db-host:5432/edon \
uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker
```bash
docker build -f Dockerfile.gateway -t edon-gateway:latest .
docker run -d \
  -p 8000:8000 \
  -e EDON_API_TOKEN=$EDON_API_TOKEN \
  -e DATABASE_URL=$DATABASE_URL \
  -e EDON_DB_ENCRYPTION_KEY=$EDON_DB_ENCRYPTION_KEY \
  --name edon-gateway \
  edon-gateway:latest
```

### Stop
```bash
# Docker
docker stop edon-gateway

# Systemd
systemctl stop edon-gateway

# Direct PID
kill $(cat uvicorn.pid)
```

---

## 3. Health Checks

### Quick health check
```bash
curl http://localhost:8000/health
```

Expected response (all healthy):
```json
{
  "ok": true,
  "status": "healthy",
  "version": "1.0.1",
  "uptime_seconds": 3600,
  "components": {
    "database":    {"status": "healthy", "latency_ms": 0.5},
    "policy_engine": {"status": "healthy", "type": "PolicyEngine"},
    "rate_limiter": {"status": "healthy"},
    "latency_slo": {"status": "healthy", "p99_ms": 12.3, "slo_p99_target_ms": 100.0}
  },
  "overall_status": "healthy"
}
```

### Component statuses
| Status | Meaning |
|--------|---------|
| `healthy` | Component operating normally |
| `degraded` | Component present but suboptimal (p99 SLO breach, policy engine warning) |
| `unhealthy` | Component failed — immediate attention required |

### Prometheus health probe
```bash
curl http://localhost:8000/metrics | grep edon_
```

---

## 4. Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EDON_API_TOKEN` | — | Master API token for auth (required in production) |
| `EDON_AUTH_ENABLED` | `true` | Set `false` only in local dev |
| `DATABASE_URL` | — | PostgreSQL connection string; required for production |
| `EDON_DB_URL` | (see persistence) | DB connection for gateway scripts and local dev. Use SQLite only for development; use PostgreSQL in production. |
| `EDON_DATABASE_PATH` | `edon_gateway.db` | SQLite DB path (development only; legacy) |
| `EDON_DB_ENCRYPTION_KEY` | — | Fernet key for audit payload encryption |
| `EDON_AUDIT_ASYNC` | `true` | When `true`, audit writes run in a background thread (p99 latency); response returns immediately with a precomputed `decision_id`. Set `false` for synchronous audit. |
| `EDON_ENCRYPT_AUDIT_PAYLOAD` | `false` in local dev; required `true` in production | Encrypt audit payloads at rest |
| `EDON_POLICY_TIMEOUT_MS` | `50` | Policy evaluation timeout in milliseconds |
| `EDON_POLICY_FAIL_SAFE` | `block` for production | `block` or `allow_with_log` on timeout; `allow_with_log` requires explicit exception signoff |
| `EDON_SLO_P99_MS` | `100` | p99 latency SLO threshold in milliseconds |
| `EDON_RATE_LIMIT_ENABLED` | `true` (prod) | Enable/disable rate limiting |
| `EDON_CORS_ORIGINS` | (internal list) | Comma-separated allowed CORS origins |
| `EDON_ENV` / `ENVIRONMENT` | `production` | `development` disables some production checks |
| `CLERK_SECRET_KEY` | — | Clerk API secret (when using Clerk auth) |
| `CLERK_ISSUER` | — | JWT issuer (e.g. `https://...clerk.accounts.dev`) |
| `CLERK_AUDIENCE` | — | Optional JWT audience for validation |

---

## 5. Logs

### Log location
- **uvicorn stdout**: captured by systemd/Docker logging driver
- **Audit trail**: `audit.log.jsonl` in working directory (also in DB)
- **Log level**: set `--log-level debug|info|warning|error` on uvicorn

### Log scrubbing
All logs pass through `LogScrubberFilter` which redacts:
- EDON API keys (`edon_...` / `edon-...`)
- Bearer tokens
- OpenAI keys (`sk-...`)
- Password fields
- Credit card numbers

### Structured log fields
```json
{"timestamp": "2026-02-24T12:00:00Z", "level": "INFO", "logger": "edon_gateway.routes.v1_action",
 "message": "Decision: ALLOW for agent-001", "request_id": "a1b2c3d4"}
```

---

## 6. Metrics (Prometheus)

Endpoint: `GET /metrics`

| Metric | Type | Description |
|--------|------|-------------|
| `edon_decisions_total{verdict, reason_code}` | Counter | Total governance decisions |
| `edon_decision_latency_ms{endpoint}` | Histogram | Decision evaluation latency |
| `edon_rate_limit_hits_total` | Counter | Rate limit rejections |
| `edon_active_intents` | Gauge | Active intent contracts |
| `edon_uptime_seconds` | Gauge | Gateway uptime |

### Grafana dashboard
A pre-built dashboard JSON has not yet been published. To visualise metrics manually, add the EDON Gateway as a Prometheus data source in Grafana using the scrape URL `https://edon-gateway.fly.dev/metrics/prometheus` (or `http://localhost:8000/metrics/prometheus` locally) and build panels from the metrics listed above.

Key panels to create:
- Decision rate (RPM)
- p99 latency vs 100ms SLO
- BLOCK rate by agent
- Rate limit hits

---

## 7. Database Operations

### SQLite (development only)
```bash
# Inspect audit events
sqlite3 edon_gateway.db "SELECT id, agent_id, timestamp, verdict FROM audit_events LIMIT 20;"

# Check audit chain integrity
sqlite3 edon_gateway.db "SELECT id, chain_hash FROM audit_events ORDER BY id;"
```

### Audit chain validation script
Run `edon_gateway/scripts/validate_audit_chain.py` to verify the cryptographic chain. **Use the same database as the gateway** by setting `EDON_DB_URL` to the same value the gateway uses (e.g. in CI: `EDON_DB_URL=sqlite:///./ci_edon.db`; in production: your PostgreSQL URL). Example:
```bash
EDON_DB_URL=sqlite:///./edon_gateway.db python edon_gateway/scripts/validate_audit_chain.py
```
Output: `{"valid": true, "checked": N, "message": "Chain valid"}` or `{"valid": false, "broken_at_id": ...}`.

### SQLite vacuum (reclaim space, development only)
```bash
sqlite3 edon_gateway.db "VACUUM;"
```

### PostgreSQL (production)
```bash
# Connect
psql $DATABASE_URL

# Check row counts
SELECT COUNT(*) FROM audit_events;
SELECT COUNT(*) FROM api_keys;

# Recent events
SELECT id, agent_id, timestamp, verdict FROM audit_events ORDER BY id DESC LIMIT 20;

# Index health
SELECT schemaname, tablename, indexname, idx_scan FROM pg_stat_user_indexes
WHERE tablename = 'audit_events' ORDER BY idx_scan DESC;
```

### Schema migrations
Migrations run automatically on startup via `schema_version.py`. To check:
```bash
sqlite3 edon_gateway.db "SELECT * FROM schema_version;"
```

---

## 8. Encryption Key Rotation

**When to rotate:** Annually, or immediately upon suspected key compromise.

```bash
# Step 1: Generate new key
NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "New key: $NEW_KEY"

# Step 2: Dry run (verify row count, no writes)
OLD_KEY=$CURRENT_KEY NEW_KEY=$NEW_KEY DRY_RUN=true \
  python scripts/rotate_encryption_key.py

# Step 3: Execute rotation (gateway must be stopped or in maintenance mode)
OLD_KEY=$CURRENT_KEY NEW_KEY=$NEW_KEY \
  python scripts/rotate_encryption_key.py

# Step 4: Update EDON_DB_ENCRYPTION_KEY to NEW_KEY in your secrets manager

# Step 5: Restart gateway
```

**Important:**
- Stop the gateway before rotation to prevent writes with mixed keys
- Back up the database before rotating
- The old key is no longer valid after rotation

---

## 9. Rate Limiting

Default limits (per `agent_id`):
- 10,000 requests/minute
- 100,000 requests/hour
- 1,000,000 requests/day

For 100 robots at 100 req/min = 10K/min total — **at the default limit**.

To adjust for burst capacity:
```bash
# Increase to 50K/min (for high-throughput scenarios)
EDON_RATE_LIMIT_PER_MINUTE=50000 uvicorn ...
```

Rate limit headers in response:
- `Retry-After: 60` (seconds to wait after 429)

---

## 10. Alert Runbooks

### Alert: `edon_gateway_p99_latency_above_slo`
**Threshold:** p99 > 100ms
**Steps:**
1. Check `/health` for `latency_slo.p99_ms` — confirm breach
2. Check DB latency: `components.database.latency_ms`
3. If DB latency > 20ms → check PostgreSQL load, add read replicas
4. If policy_engine degraded → check `EDON_POLICY_TIMEOUT_MS` setting
5. Scale horizontal: add uvicorn workers or instances

### Alert: `edon_gateway_error_rate_above_1pct`
**Threshold:** 5xx rate > 1%
**Steps:**
1. Check uvicorn logs for exception traces
2. `curl /health` — identify unhealthy component
3. If database unhealthy → check DB connection, run `SELECT 1`
4. Restart gateway if hung: `systemctl restart edon-gateway`

### Alert: `edon_gateway_down`
**Threshold:** `/healthz` returns non-200 for 2+ minutes
**Steps:**
1. SSH to host, check process: `ps aux | grep uvicorn`
2. Check port: `netstat -tlnp | grep 8000`
3. Start: `systemctl start edon-gateway`
4. Check logs: `journalctl -u edon-gateway -n 100`

### Alert: `edon_audit_chain_broken`
**Threshold:** Any audit event fails chain_hash validation
**Steps:**
1. This indicates potential data tampering — escalate to security team immediately
2. Preserve DB snapshot: `cp edon_gateway.db edon_gateway.db.INCIDENT_$(date +%s)`
3. Run chain validation **using the same DB as the gateway**: `EDON_DB_URL=<same-as-gateway> python edon_gateway/scripts/validate_audit_chain.py` (e.g. `EDON_DB_URL=sqlite:///./ci_edon.db` or your production PostgreSQL URL). If `EDON_DB_URL` is unset, the script uses the default DB path and may validate a different database.
4. Do NOT modify the database until incident review complete

---

## 11. Scaling for 100 Robots

### Target: 100 robots × 100 req/min = 10,000 req/min

**Single-node (SQLite):**
- Supported up to ~10K req/min with WAL mode enabled
- CPU: 2+ cores, Memory: 512MB+
- Disk: SSD recommended for SQLite WAL

**Multi-node (PostgreSQL):**
```
Load Balancer (nginx/ALB)
  ├── EDON Gateway node 1 (uvicorn --workers 4)
  ├── EDON Gateway node 2 (uvicorn --workers 4)
  └── EDON Gateway node 3 (uvicorn --workers 4)
                ↓
  PostgreSQL primary + 1 read replica
  (connection pool: minconn=2, maxconn=20 per node)
```

**Load test before pilot:**
```bash
python scripts/load_test.py --url http://gateway:8000 --rps 200 --duration 60
```
Target: p99 < 100ms, error rate < 1%, RPS >= 180 (90% of 200).

---

## 12. Disaster Recovery

### RTO: 15 minutes | RPO: 1 hour (SQLite) / 5 minutes (PostgreSQL)

### SQLite backup (cron every hour)
```bash
# /etc/cron.hourly/edon-backup
python scripts/backup_gateway_db.py --mode sqlite --output-dir /backups
# Keep last 24h of SQLite snapshots
find /backups -name "edon_gateway_sqlite_*.db" -mtime +1 -delete
```

### PostgreSQL backup
```bash
python scripts/backup_gateway_db.py --mode postgres --output-dir /backups
```

### Restore SQLite
```bash
systemctl stop edon-gateway
python scripts/restore_gateway_db.py /backups/edon_gateway_sqlite_TIMESTAMP.db --mode sqlite
systemctl start edon-gateway
```

### Restore PostgreSQL
```bash
python scripts/restore_gateway_db.py /backups/edon_gateway_postgres_TIMESTAMP.sql.gz --mode postgres
```

### Full disaster recovery
1. Provision new server with Docker/Python 3.11
2. Clone repo: `git clone <repo>`
3. Restore DB backup
4. Set all env vars (from secrets manager)
5. Start gateway: `docker-compose up -d` or `systemctl start edon-gateway`
6. Verify: `curl /health`
7. Run smoke test: `python scripts/load_test.py --rps 10 --duration 5`

---

## 13. Production deployment checklist

Before going live, ensure:

- [ ] **Env vars:** `EDON_API_TOKEN`, `DATABASE_URL` (production) or `EDON_DB_URL` (development only), `EDON_DB_ENCRYPTION_KEY` (production), `EDON_AUTH_ENABLED=true`, `EDON_CORS_ORIGINS` set to your frontend origins. If using Clerk: `CLERK_SECRET_KEY`, optionally `CLERK_ISSUER` and `CLERK_AUDIENCE`. See [Key Environment Variables](#4-key-environment-variables).
- [ ] **Health:** `GET /healthz` returns 200 and `components.database.status` is healthy.
- [ ] **Auth:** Protected endpoints return 401 without a valid token; with token, 200.
- [ ] **Audit:** After a few requests, run `EDON_DB_URL=<same-as-gateway> python edon_gateway/scripts/validate_audit_chain.py` and confirm `valid: true`.
- [ ] **Latency:** p99 under SLO (default 100 ms); use `edon_gateway/scripts/load_test_v1_action.py --p99-max-ms 100` against the live URL (or a staging copy).
- [ ] **Console:** If deploying the separate console, complete its production checklist (env vars, build/publish, auth) per that repo’s docs.
