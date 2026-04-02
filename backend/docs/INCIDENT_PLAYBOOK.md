# EDON Gateway Incident Playbook

## Severity Levels

- `SEV-1`: Gateway down, auth bypass suspected, audit chain invalid.
- `SEV-2`: Elevated 5xx/error rate, latency SLO breach, webhook failures.
- `SEV-3`: Partial degradation, non-critical connector failures.

## First 10 Minutes

1. Declare incident in on-call channel and assign commander.
2. Capture baseline evidence:
   - `curl http://127.0.0.1:8000/health`
   - `curl http://127.0.0.1:8000/health/dependencies`
   - `python scripts/validate_audit_chain.py`
3. Snapshot DB before any remediation:
   - `python scripts/backup_gateway_db.py --mode auto`
4. Freeze non-emergency deploys until incident is resolved.

## Standard Response Paths

- **Auth failures spike**
  - Verify `EDON_AUTH_ENABLED=true`.
  - Check token issuer/JWKS env (`CLERK_*`) and `X-EDON-TOKEN` usage.
  - Confirm no accidental env token fallback in prod (`EDON_ALLOW_ENV_TOKEN_IN_PROD=false`).

- **Audit chain invalid**
  - Treat as security event (SEV-1).
  - Preserve backup and logs.
  - Block writes if needed; keep system in read-only mode.
  - Escalate to security lead and legal/compliance owner.

- **Latency SLO breached**
  - Inspect `/health` `latency_slo` component and DB latency.
  - Scale gateway workers/instances.
  - If DB contention, move to PostgreSQL or increase pool capacity.

## Recovery Validation Checklist

1. `/health` overall status healthy.
2. `scripts/validate_audit_chain.py` returns `valid=true`.
3. `/v1/action` smoke call succeeds with valid token.
4. Alert volume returns to baseline.
5. Incident timeline and root cause documented.

## Post-Incident

1. Run rollback drill if incident involved deployment.
2. Create action items with owners and due dates.
3. Update this playbook if any step was missing or ambiguous.
