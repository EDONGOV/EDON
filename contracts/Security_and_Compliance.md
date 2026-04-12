# EDON Security & Compliance Overview

**Version 1.0 — April 2026**
**Prepared for:** Prospective Enterprise Customers
**Contact:** security@edoncore.com

---

## What EDON Does

EDON is an AI governance platform that intercepts, evaluates, and logs every action taken by autonomous AI agents before it executes. EDON sits between your AI agents and the outside world — enforcing policies, blocking violations, and producing a tamper-evident audit trail of every decision.

For healthcare organizations, this means: every action your AI agent attempts (querying a patient record, sending a message, updating a system) is evaluated against your defined policies and logged before execution. Nothing passes through unexamined.

---

## Data Classification

EDON processes two categories of data:

| Category | Description | Examples |
|----------|-------------|---------|
| **Control Plane Data** | Configuration, policies, agent metadata | Policy rules, agent IDs, workspace settings |
| **Audit Data** | Runtime decision logs | Action type, verdict (ALLOW/BLOCK), timestamp, risk score, agent ID, tool name |

**EDON does not require access to your underlying data sources.** It evaluates agent *actions* (intent + parameters), not the content of medical records or patient databases directly. PHI exposure in audit logs depends entirely on what parameters your agents pass — EDON's PHI masking feature redacts sensitive fields before they are stored.

---

## Technical Security Controls

### Encryption

| Layer | Standard |
|-------|----------|
| Data at rest | AES-256 |
| Data in transit | TLS 1.2 minimum; TLS 1.3 preferred |
| Database backups | AES-256, encrypted before leaving compute boundary |
| API keys | PBKDF2-SHA256 hashed; raw key shown once, never stored |

### Access Controls

- **Authentication**: All internal system access requires MFA
- **Authorization**: Role-based access control (RBAC) with least-privilege enforcement
- **API authentication**: HMAC-signed API keys with optional IP allowlisting
- **Admin access**: Production database access restricted to ≤ 2 named engineers; access logged
- **SSO**: SAML/OIDC SSO supported on Business and Enterprise plans (Okta, Azure AD, Google Workspace)

### Network Security

- All services run in isolated VPCs with private subnets
- Public endpoints limited to API gateway (port 443 only)
- Database not publicly accessible; accessed only via private network
- WAF and DDoS protection on all public-facing endpoints
- Audit logs are append-only at the infrastructure level — no UPDATE or DELETE on log tables

### Vulnerability Management

| Activity | Frequency |
|----------|-----------|
| Dependency scanning | Continuous (automated) |
| Static code analysis | Every commit (CI pipeline) |
| Infrastructure vulnerability scan | Weekly |
| Penetration test | Annual (third-party) |
| Security review for major features | Per release |

Penetration test reports are available to Business and Enterprise customers under NDA.

---

## HIPAA Compliance

EDON is designed to operate as a HIPAA Business Associate for covered healthcare organizations.

### Technical Safeguards (45 C.F.R. § 164.312)

| Safeguard | Implementation |
|-----------|---------------|
| Access control | Unique user identification, automatic logoff, encryption/decryption |
| Audit controls | Append-only audit log of all ePHI access; immutable records |
| Integrity | Cryptographic hashing (SHA-256) of all audit records; tamper detection |
| Transmission security | TLS 1.2+ for all data in transit |

### Administrative Safeguards (45 C.F.R. § 164.308)

| Safeguard | Implementation |
|-----------|---------------|
| Security management | Written security policies; risk analysis performed annually |
| Assigned security responsibility | Designated Security Officer |
| Workforce training | Annual HIPAA training required for all employees |
| Access management | Role-based; access terminated same day upon employee departure |
| Contingency plan | Documented backup and disaster recovery procedures |
| Evaluation | Annual security review |

### Physical Safeguards (45 C.F.R. § 164.310)

- All compute infrastructure hosted in SOC 2 Type II certified data centers (via Fly.io, US regions)
- No on-site hardware for cloud-hosted deployments
- On-premise deployments run within Customer's own physical environment

### PHI Masking

EDON supports configurable PHI masking in audit logs. When enabled:
- Specified fields (e.g., patient name, DOB, MRN, SSN) are replaced with `[MASKED]` before storage
- Masking is applied at ingestion — masked values are never written to disk
- Masking patterns are configurable via the EDON policy configuration API

### BAA Availability
EDON executes Business Associate Agreements with all healthcare customers prior to any PHI transmission. Contact contracts@edoncore.com.

---

## Data Residency & Sovereignty

| Option | Availability |
|--------|-------------|
| US-only data residency | Standard (all plans) |
| EU data residency | Enterprise plan |
| Custom region | Enterprise plan (contact sales) |
| On-premise deployment | Enterprise plan |
| Air-gapped deployment | Available — contact sales |

All cloud-hosted customer data is stored in **US East (Virginia)** by default. Data does not leave the selected region.

---

## Audit Log Integrity

Every audit log record produced by EDON includes:

- `action_id` — UUID, globally unique
- `timestamp` — UTC, microsecond precision
- `agent_id` — identifier of the agent that triggered the action
- `verdict` — ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE
- `reason_code` — machine-readable reason (e.g., SCOPE_VIOLATION, DATA_EXFIL)
- `policy_snapshot_hash` — SHA-256 of the policy set active at decision time
- `record_hash` — SHA-256 of the full record, computed at write time

The `record_hash` chain allows any third party (including auditors or regulators) to verify that no log records have been modified or deleted after the fact.

**Export formats:** CSV, NDJSON, signed PDF (Business/Enterprise)

**Signed exports (Business/Enterprise):** EDON can produce exports with a digital signature that can be verified independently, suitable for regulatory submissions and legal proceedings.

---

## Availability & Reliability

| Component | Architecture |
|-----------|-------------|
| API gateway | Multi-region active-active |
| Decision engine | Stateless; horizontally scalable |
| Database | Managed PostgreSQL with automated failover |
| Backups | Continuous WAL archival; point-in-time recovery to 7 days |
| Monitoring | 24/7 automated alerting; on-call rotation |

**RTO (Recovery Time Objective):** < 1 hour for cloud-hosted
**RPO (Recovery Point Objective):** < 5 minutes

---

## Certifications & Roadmap

| Standard | Status |
|----------|--------|
| HIPAA compliance | Operational (BAA available) |
| SOC 2 Type I | In preparation — Q3 2026 |
| SOC 2 Type II | Roadmap — Q1 2027 |
| ISO 27001 | Roadmap — 2027 |
| HITRUST CSF | Roadmap — Enterprise track |

Customers requiring SOC 2 or HITRUST certifications prior to the completion of EDON's audit may request a security questionnaire response, penetration test report, and policy documentation in lieu of a certification.

---

## Vendor Risk Management

For procurement and vendor risk teams, EDON can provide:

| Document | Availability |
|----------|-------------|
| Completed security questionnaire (SIG Lite / CAIQ) | On request |
| Penetration test report (executive summary) | Business/Enterprise, under NDA |
| Security policies (summary) | On request |
| Sub-processor list | Available at edoncore.com/sub-processors |
| Business Associate Agreement | Standard template or Customer's preferred form |
| Data Processing Addendum | Available for GDPR-regulated customers |
| Cyber liability insurance certificate | On request (COI) |
| W-9 | On request |

---

## Incident Response

In the event of a security incident affecting Customer data:

1. EDON's on-call engineer is paged within **5 minutes** of automated detection
2. Initial assessment completed within **1 hour**
3. Customer notification within **10 business days** of confirmed incident (or sooner as required by law)
4. Full incident report provided within **30 days**
5. For HIPAA Breaches: EDON cooperates fully with required notifications to HHS and affected individuals

EDON maintains cyber liability insurance with minimum limits of $2,000,000 per occurrence.

---

## Contact

| Purpose | Contact |
|---------|---------|
| Security questions | security@edoncore.com |
| Compliance / BAA | contracts@edoncore.com |
| Vendor risk questionnaires | security@edoncore.com |
| General sales | hello@edoncore.com |

Response time for security inquiries: **2 business days**

---

*This document reflects EDON's security posture as of April 2026. An updated version is available upon request.*
