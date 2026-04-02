# EDON Gateway — Backup and Recovery Procedures

**Version:** 1.0
**Last updated:** 2026-02-24
**RTO (Recovery Time Objective):** 15 minutes
**RPO (Recovery Point Objective):** 1 hour (SQLite) / 5 minutes (PostgreSQL)

---

## 1. What to Back Up

| Asset | Criticality | Location |
|-------|------------|----------|
| SQLite database | Critical | `$EDON_DATABASE_PATH` (default: `edon_gateway.db`) |
| Environment variables / secrets | Critical | Secrets manager (Vault, AWS SSM, Render env) |
| Policy rules (DB) | High | Contained in DB backup |
| API keys (DB) | High | Contained in DB backup (bcrypt hashes only) |
| Application code | Medium | Git repository |
| Encryption key | Critical | Secrets manager — **never in backups** |

---

## 2. SQLite Backup

### Manual backup
```bash
# Safe online backup (SQLite backup API — consistent snapshot even under WAL)
sqlite3 /app/edon_gateway.db ".backup '/backups/edon_gateway_$(date +%Y%m%d_%H%M%S).db'"

# Or simple copy (safe when gateway is stopped)
cp /app/edon_gateway.db /backups/edon_gateway_$(date +%Y%m%d_%H%M%S).db
```

### Automated hourly cron
```bash
# /etc/cron.d/edon-backup
0 * * * * app /usr/bin/sqlite3 /app/edon_gateway.db ".backup '/backups/edon_$(date +\%Y\%m\%d_\%H\%M\%S).db'" && find /backups -name 'edon_*.db' -mtime +2 -delete
```

### Verify backup integrity
```bash
sqlite3 /backups/edon_gateway_TIMESTAMP.db "PRAGMA integrity_check;"
# Expected output: ok
```

---

## 3. PostgreSQL Backup

### On-demand dump
```bash
# Full dump (compressed)
pg_dump $DATABASE_URL | gzip > /backups/edon_pg_$(date +%Y%m%d_%H%M%S).sql.gz

# Schema only
pg_dump --schema-only $DATABASE_URL > /backups/edon_schema_$(date +%Y%m%d).sql
```

### Automated with pg_basebackup (continuous archiving)
```bash
# Enable WAL archiving in postgresql.conf:
# wal_level = replica
# archive_mode = on
# archive_command = 'cp %p /backups/wal/%f'
```

### Managed database (Render, Supabase, RDS)
Enable the platform's automatic backup feature:
- **Render:** Enable "Automatic Backups" in database settings (daily, 7-day retention)
- **RDS:** Enable automated backups with 7-day retention
- **Supabase:** Point-in-time recovery enabled by default on Pro plan

### Verify PostgreSQL backup
```bash
# Create test restore DB
createdb edon_restore_test
gunzip < /backups/edon_pg_TIMESTAMP.sql.gz | psql edon_restore_test

# Check row counts match
psql $DATABASE_URL -c "SELECT COUNT(*) FROM audit_events;"
psql edon_restore_test -c "SELECT COUNT(*) FROM audit_events;"

# Drop test DB
dropdb edon_restore_test
```

---

## 4. Secrets Backup

**NEVER include secrets in DB backups or Git.**

Backup strategy for `EDON_DB_ENCRYPTION_KEY`:
1. Store in hardware security module (HSM) or managed secrets service
2. Split key escrow: two authorized personnel required for recovery
3. Test recovery procedure quarterly

For cloud deployments:
- **AWS:** Store in AWS Secrets Manager; enable cross-region replication
- **Render:** Note env vars in Render dashboard; export to offline secure storage
- **Docker:** Use Docker Secrets or external vault

---

## 5. Recovery Procedures

### 5.1 Restore SQLite from backup

```bash
# 1. Stop gateway
systemctl stop edon-gateway  # or: kill $(cat uvicorn.pid)

# 2. Verify backup integrity
sqlite3 /backups/edon_gateway_TIMESTAMP.db "PRAGMA integrity_check;"

# 3. Replace current DB
cp /app/edon_gateway.db /app/edon_gateway.db.pre_restore_$(date +%s)
cp /backups/edon_gateway_TIMESTAMP.db /app/edon_gateway.db

# 4. Start gateway
systemctl start edon-gateway

# 5. Verify
curl http://localhost:8000/health
```

### 5.2 Restore PostgreSQL from dump

```bash
# 1. Stop gateway
systemctl stop edon-gateway

# 2. Drop and recreate DB (if on self-managed Postgres)
psql postgres -c "DROP DATABASE edon;"
psql postgres -c "CREATE DATABASE edon;"

# 3. Restore
gunzip < /backups/edon_pg_TIMESTAMP.sql.gz | psql $DATABASE_URL

# 4. Verify row counts
psql $DATABASE_URL -c "SELECT COUNT(*) FROM audit_events;"

# 5. Start gateway
systemctl start edon-gateway
curl http://localhost:8000/health
```

### 5.3 Restore from full disaster (new server)

```bash
# 1. Provision server with Python 3.11
# 2. Clone repository
git clone <repo-url> /app
cd /app/edon_gateway

# 3. Install dependencies
pip install -r requirements.gateway.txt

# 4. Restore DB (SQLite or PostgreSQL — see 5.1/5.2 above)

# 5. Configure environment
export EDON_API_TOKEN="<from secrets manager>"
export EDON_DB_ENCRYPTION_KEY="<from secrets manager>"
export DATABASE_URL="<postgres connection string>"
# ... other env vars from OPERATIONS_RUNBOOK.md

# 6. Start gateway
uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000 --workers 4

# 7. Smoke test
curl http://localhost:8000/health
python scripts/load_test.py --rps 10 --duration 5
```

---

## 6. Audit Chain Validation After Restore

After any restore, validate the audit chain is intact:

```python
# Run from edon_gateway/ directory
python - <<'EOF'
from edon_gateway.persistence.database import Database
from pathlib import Path

db = Database(Path("edon_gateway.db"))
events = db.query_audit_events(limit=10000)

prev_hash = ""
ok = True
for i, event in enumerate(events):
    import hashlib
    content = f"{event['action']['id']}|{event.get('agent_id', '')}|{event.get('customer_id', '')}|{event.get('timestamp', '')}|{event.get('decision', {}).get('verdict', '')}"
    expected = hashlib.sha256((prev_hash + content).encode()).hexdigest()
    actual = event.get("chain_hash", "")
    if actual and actual != expected:
        print(f"CHAIN BROKEN at row {i} (id={event.get('id')})")
        ok = False
    prev_hash = actual or expected

print("Audit chain: OK" if ok else "Audit chain: BROKEN — investigate before proceeding")
EOF
```

---

## 7. Backup Test Schedule

| Test | Frequency | Responsible |
|------|-----------|-------------|
| Verify backup file exists and is non-empty | Daily (automated) | Monitoring alert |
| SQLite integrity check on backup | Daily (cron) | Ops team |
| Full restore drill to staging | Monthly | Lead engineer |
| Secrets recovery drill | Quarterly | Security + Ops |
| Full DR drill (new server) | Semi-annually | Ops team |

---

## 8. Backup Retention Policy

| Backup Type | Retention |
|------------|-----------|
| Hourly SQLite snapshots | 48 hours |
| Daily SQLite snapshots | 30 days |
| Weekly SQLite snapshots | 1 year |
| PostgreSQL WAL archives | 7 days |
| PostgreSQL weekly dumps | 3 months |
| Pre-incident DB snapshots | 1 year (manual) |
