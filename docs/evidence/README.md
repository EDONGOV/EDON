# EDON Evidence Pack

This folder collects the operational evidence that procurement, security review,
and audit teams usually ask for.

## Included artifacts

- [restore-drill.md](./restore-drill.md) - restore drill record template and checklist
- [tenant-isolation.md](./tenant-isolation.md) - tenant isolation verification record
- [audit-chain.md](./audit-chain.md) - audit chain validation record
- [execution-binding.md](./execution-binding.md) - decision binding and execution-token record
- [exception-register.md](./exception-register.md) - intentional fail-open exception register
- [pentest-register.md](./pentest-register.md) - external pentest and retest register
- [compliance-pack.md](./compliance-pack.md) - compliance evidence index
- [verification-ledger.md](./verification-ledger.md) - signed verification record ledger
- [production-advisory-review.md](./production-advisory-review.md) - advisory-only path classification

## Source evidence already in the repo

- [docs/runbooks/disaster-recovery.md](../runbooks/disaster-recovery.md)
- [backend/docs/BACKUP_PROCEDURES.md](../../backend/docs/BACKUP_PROCEDURES.md)
- [docs/safety/acceptance-criteria.md](../safety/acceptance-criteria.md)
- [docs/safety/authority-chain.md](../safety/authority-chain.md)
- [docs/safety/fault-tree.md](../safety/fault-tree.md)
- [docs/safety/severity-tiers.md](../safety/severity-tiers.md)
- [backend/edon_gateway/test/test_multitenant_isolation.py](../../backend/edon_gateway/test/test_multitenant_isolation.py)
- [backend/edon_gateway/test/test_compliance_exports.py](../../backend/edon_gateway/test/test_compliance_exports.py)
- [backend/edon_gateway/test/test_repeatable_architecture.py](../../backend/tests/test_repeatable_architecture.py)
- [backend/edon_gateway/routes/audit.py](../../backend/edon_gateway/routes/audit.py)

## Status

- Restore drill evidence: template ready for a signed live drill record
- Tenant isolation evidence: template ready for a signed staging record
- Audit-chain evidence: template ready for a signed validation record
- Execution-binding evidence: template ready for a signed validation record
- Exception register: template ready for review and signoff
- Verification ledger: signed CI-backed records attached
- Advisory review: completed for remaining non-blocking production paths
- Pentest evidence: pending external assessment and retest
- Compliance pack: in progress
