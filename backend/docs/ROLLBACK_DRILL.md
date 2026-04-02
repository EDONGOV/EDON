# EDON Gateway Rollback Drill

## Goal

Prove we can roll back a bad release quickly with preserved audit integrity.

## Frequency

- Weekly in staging
- Monthly in production-like environment

## Drill Procedure

1. **Create pre-drill backup**
   - `python scripts/backup_gateway_db.py --mode auto --output-dir backups`

2. **Deploy canary change**
   - Deploy a known test version or intentionally bad config in staging.

3. **Trigger failure condition**
   - Validate degraded behavior (health, latency, or error increase).

4. **Execute rollback**
   - Re-deploy previous known-good image/version.
   - If data corruption is simulated, restore DB:
     - `python scripts/restore_gateway_db.py <backup-file> --mode auto`

5. **Validate rollback**
   - `curl http://127.0.0.1:8000/health`
   - `python scripts/validate_audit_chain.py`
   - `/v1/action` authenticated smoke call

6. **Record metrics**
   - Recovery time (RTO)
   - Data loss window (RPO)
   - Any manual intervention required

## Pass Criteria

- Service healthy within target RTO.
- Audit chain verification passes after rollback.
- No secret leakage in logs during incident/rollback steps.
- Team can execute without ad-hoc undocumented steps.
