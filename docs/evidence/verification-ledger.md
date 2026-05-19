# EDON Verification Ledger

This ledger records the current signed verification artifacts that support the
governance package. It is not a substitute for live drill results or third-party
validation, but it does document the exact repo state that has been verified.

## Recorded verification

| Control | Status | Evidence | Source |
| --- | --- | --- | --- |
| Restore drill evidence | Signed CI verification record | Governance test slice passed after restore/evidence updates | `3160c78` |
| Tenant isolation evidence | Signed CI verification record | Tenant-cleanup and multitenant governance tests passed | `3160c78` |
| Audit-chain evidence | Signed CI verification record | Repeatable architecture and enforcement tests passed | `3160c78` |
| Execution-binding evidence | Signed CI verification record | Repeatable architecture test and enforcement slice passed | `3160c78` |
| Exception register | Signed review record | Intentional fail-open paths are listed in the advisory review | `3160c78` |
| Pilot package | Signed documentation record | Pilot checklist now includes wedge, SSO, RBAC, rollback, and runbook | `3160c78` |
| Enterprise boundary | Signed code verification | RBAC, edge identity, and enterprise role hardening tests passed | `3160c78` |

## Verification commands

- `python -m pytest edon_gateway/test/test_enforcement_hardening.py edon_gateway/test/test_tenant_default_cleanup.py edon_gateway/test/test_multitenant_rbac.py edon_gateway/test/test_enterprise_identity_controls.py tests/test_repeatable_architecture.py -q --basetemp C:\tmp\pytest-governance`
- `python backend/scripts/secret_audit.py`
- `python -m py_compile backend/edon_gateway/main.py backend/edon_gateway/audit.py backend/edon_gateway/middleware/rbac.py backend/edon_gateway/monitoring/prometheus_registry.py backend/edon_gateway/routes/admin.py backend/edon_gateway/routes/api_keys.py backend/edon_gateway/routes/bootstrap.py backend/edon_gateway/routes/compliance.py backend/edon_gateway/routes/edge.py backend/edon_gateway/schemas/action_result.py backend/edon_gateway/schemas/v1_action.py backend/edon_gateway/test/test_multitenant_rbac.py`

## Still pending

- Live restore drill with a signed operator record
- External pentest and retest report
- Buyer-specific pilot deployment record

