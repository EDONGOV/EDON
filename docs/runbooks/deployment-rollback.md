# EDON Gateway — Deployment Rollback Runbook

Use this runbook when a deploy introduces a regression and must be reverted.

---

## 1. Identify the bad deploy

```bash
# List recent releases
fly releases -a edon-gateway

# Output example:
# VERSION  STATUS   DESCRIPTION           USER        DATE
# v42      active   Deploy image sha-abc  you@co.com  2026-04-02T10:00:00Z
# v41      complete Deploy image sha-xyz  you@co.com  2026-04-01T15:00:00Z
```

## 2. Roll back to the previous image

```bash
# Deploy the previous version by its image
fly deploy --image registry.fly.io/edon-gateway:deployment-<previous-sha> -a edon-gateway

# Or specify the release version number directly
fly deploy -a edon-gateway --image $(fly releases -a edon-gateway --json | jq -r '.[1].ImageRef')
```

## 3. Verify the rollback succeeded

```bash
fly status -a edon-gateway                          # Confirm machine is running
curl https://edon-gateway.fly.dev/health           # Should return {"status":"healthy"}
fly logs -a edon-gateway --tail                    # Check for errors in last 100 lines
```

## 4. Roll back a database migration (Alembic)

If the bad deploy included a schema migration, roll it back **before** restarting the app:

```bash
# SSH into the running instance
fly ssh console -a edon-gateway

# Inside the container — check current migration
cd /app && alembic current

# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision-id>

# Verify
alembic current
exit
```

Then redeploy the previous application image (step 2).

## 5. Confirm rollback in logs

```bash
fly logs -a edon-gateway | grep -E "(startup|schema|error)"
```

Expected: `EDON Gateway startup complete` with no schema version errors.

## 6. Notify the team

Post in the incident channel:
```
🔄 Rolled back edon-gateway to v<N-1> at <time>.
Reason: <brief description>
Status: Health check passing ✅
Next steps: Investigate root cause in separate PR.
```

---

## Quick Reference

| Task | Command |
|------|---------|
| List releases | `fly releases -a edon-gateway` |
| Deploy previous image | `fly deploy --image <image-ref> -a edon-gateway` |
| Check health | `curl https://edon-gateway.fly.dev/health` |
| View logs | `fly logs -a edon-gateway` |
| SSH in | `fly ssh console -a edon-gateway` |
| Rollback migration | `alembic downgrade -1` (inside container) |
| Check migration state | `alembic current` (inside container) |
