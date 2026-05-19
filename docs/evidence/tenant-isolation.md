# Tenant Isolation Evidence

Use this file to capture the results of a real tenant-isolation run against a
staging or production-like environment.

## Scope

- Tenants tested:
- Request types:
- Isolation controls verified:
- Reviewer:
- Signed by:
- Signature reference:

## Expected evidence

- No cross-tenant audit reads
- No cross-tenant policy influence
- No cross-tenant rate-limit bleed-through
- No cross-tenant data leakage in exports or reports
- No cross-tenant execution binding leakage

## Related automated tests

- [backend/edon_gateway/test/test_multitenant_isolation.py](../../backend/edon_gateway/test/test_multitenant_isolation.py)
- [docs/safety/acceptance-criteria.md](../safety/acceptance-criteria.md)

## Notes

- Record timestamps, sample requests, and the exact outputs from the staging run.
- Attach any exported CSV/JSON evidence from the audit endpoint here or in the
  compliance pack.
- Add links to raw request/response captures and any signed approval artifact.
