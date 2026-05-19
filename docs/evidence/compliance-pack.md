# Compliance Evidence Pack

This document is the index for the evidence pack used in enterprise diligence.

## Control references

- [docs/safety/acceptance-criteria.md](../safety/acceptance-criteria.md)
- [docs/safety/authority-chain.md](../safety/authority-chain.md)
- [docs/safety/fault-tree.md](../safety/fault-tree.md)
- [docs/safety/severity-tiers.md](../safety/severity-tiers.md)
- [docs/DECISION_KERNEL.md](../DECISION_KERNEL.md)
- [docs/runbooks/disaster-recovery.md](../runbooks/disaster-recovery.md)
- [backend/docs/BACKUP_PROCEDURES.md](../../backend/docs/BACKUP_PROCEDURES.md)
- [backend/edon_gateway/routes/audit.py](../../backend/edon_gateway/routes/audit.py)
- [backend/edon_gateway/test/test_multitenant_isolation.py](../../backend/edon_gateway/test/test_multitenant_isolation.py)
- [docs/evidence/verification-ledger.md](./verification-ledger.md)
- [docs/evidence/production-advisory-review.md](./production-advisory-review.md)

## Pack contents

- Restore drill record: [restore-drill.md](./restore-drill.md)
- Tenant isolation record: [tenant-isolation.md](./tenant-isolation.md)
- Audit chain record: [audit-chain.md](./audit-chain.md)
- Execution binding record: [execution-binding.md](./execution-binding.md)
- Exception register: [exception-register.md](./exception-register.md)
- Pentest register: [pentest-register.md](./pentest-register.md)

## Open gaps

- External pentest report not yet attached
- Recorded restore drill not yet signed and attached
- Recorded tenant-isolation run not yet signed and attached
- Audit-chain validation not yet signed and attached
- Execution-binding validation not yet signed and attached
- Exception register not yet reviewed and signed
- Verification ledger now records the current signed CI-backed evidence set
- Production advisory review documents all remaining non-blocking paths
