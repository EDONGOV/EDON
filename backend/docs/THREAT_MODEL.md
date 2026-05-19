# EDON Gateway — Threat Model

**Version:** 1.0
**Last updated:** 2026-02-24
**Methodology:** STRIDE
**Scope:** EDON Gateway v1.0.1, 100-robot enterprise pilot deployment

---

## 1. System Description

EDON Gateway is an AI governance layer that sits between physical autonomous robots and their backend systems. It evaluates every robot action request against policy rules and records tamper-evident audit trails. A breach could result in: unauthorized robot movement, data exfiltration, physical harm, regulatory violation.

### Trust Boundary Diagram
```
[Robot Fleet] ──HTTP──→ [EDON Gateway] ──SQL──→ [Database]
                                ↓
                         [Policy Engine]
                                ↓
                        [Audit Trail]
```

**Assets:**
- Robot command authorization (primary)
- Audit trail integrity (regulatory/legal)
- Tenant isolation (multi-tenant data)
- API keys / credentials
- Policy rules (configurable governance)

---

## 2. Threat Analysis (STRIDE)

### S — Spoofing

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| S-01 | Robot impersonates another robot | Stolen `agent_id` in request | API key auth scoped to tenant; rate limiting per `agent_id` |
| S-02 | Attacker impersonates legitimate API key | Brute force or key theft | bcrypt hashing (cost factor ≥ 12); rate limiting on auth failures |
| S-03 | JWT / Bearer token replay | Token theft via MitM | TLS required in production; `X-EDON-TOKEN` single-use not enforced (limitation — see mitigations) |
| S-04 | Privileged role escalation | Low-privilege key claims governance or admin role | Role stored in DB, not in token; RBAC checks server-side only; enterprise roles default narrow |

**Mitigations in place:** bcrypt API key hashing (`security/hashing.py`), `AuthMiddleware`, `RBACMiddleware`

**Open risks:**
- S-03: No token expiry or single-use enforcement. Mitigation: rotate API keys regularly; use short-lived tokens in future.

---

### T — Tampering

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| T-01 | Audit record modification | Direct DB access | Append-only triggers (no UPDATE/DELETE on `audit_events`); SHA-256 chain_hash |
| T-02 | Policy rule manipulation | API endpoint abuse | RBAC: only `governance_admin` / `super_admin` can modify policy rules |
| T-03 | Encrypted payload swap | DB access + known plaintext | Fernet HMAC-SHA256 covers authenticity — tampered ciphertext decrypts to error |
| T-04 | Race condition in chain hash | Concurrent inserts | SQLite serialized writes (WAL mode); PostgreSQL `SERIALIZABLE` recommended |
| T-05 | Config injection via env var | Server config access | Env vars controlled by deployment pipeline; secrets manager recommended |

**Mitigations in place:** `prevent_audit_update`, `prevent_audit_delete` triggers; `chain_hash`; Fernet encryption

---

### R — Repudiation

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| R-01 | Robot denies issuing command | Log manipulation | Append-only audit trail with chain hash; `decision_id` returned to caller |
| R-02 | Operator denies approving intent | No audit of intent creation | Intent creation logged with `approved_by_user` flag; operator `customer_id` recorded |
| R-03 | Admin denies changing policy | No policy change audit | Policy rule changes should log to audit table (enhancement: currently not audited) |

**Open risks:**
- R-03: Policy rule changes are not currently written to `audit_events`. Mitigation: add policy change audit logging in next version.

---

### I — Information Disclosure

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| I-01 | Cross-tenant data leakage | API query without `customer_id` filter | All DB queries filter by `customer_id`; enforced in `Database.query_audit_events()` |
| I-02 | Secrets in log output | Verbose logging of request bodies | `LogScrubberFilter` redacts API keys, tokens, passwords |
| I-03 | Audit payload exposes PII | Payload stored in plaintext | Optional Fernet encryption; advise customers not to include PII in context |
| I-04 | Error messages reveal DB schema | 500 error passthrough | FastAPI exception handlers return generic messages; SQL errors not surfaced to caller |
| I-05 | Metrics endpoint exposes tenant info | Unauthenticated `/metrics` | Metrics use aggregate counters only; no per-tenant breakdown in Prometheus export |

**Mitigations in place:** `customer_id` isolation at DB level; `LogScrubberFilter`; Fernet encryption (optional)

**Open risks:**
- I-03: Encryption is opt-in. For regulated deployments, enforce `EDON_ENCRYPT_AUDIT_PAYLOAD=true`.
- I-05: `/metrics` is unauthenticated. Restrict access via network policy (VPN/internal only).

---

### D — Denial of Service

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| D-01 | Request flood from single robot | High-frequency POST /v1/action | Rate limiting: 10,000 req/min per `agent_id` |
| D-02 | Policy evaluation timeout | Complex rule or slow DB | 50ms policy evaluation timeout with fail-safe (`EDON_POLICY_FAIL_SAFE`) |
| D-03 | Large payload body bomb | Oversized JSON body | FastAPI default body size limit (1MB); `ValidationMiddleware` strips extra fields |
| D-04 | DB lock contention | Many concurrent writes | SQLite WAL mode; PostgreSQL connection pool (maxconn=20) |
| D-05 | Slow client holds connections | Clients that never close | uvicorn `--timeout-keep-alive 30` recommended |

**Mitigations in place:** `RateLimitMiddleware` (10K/min); policy timeout; WAL mode

---

### E — Elevation of Privilege

| ID | Threat | Attack Vector | Controls |
|----|--------|--------------|----------|
| E-01 | Agent role accesses admin endpoints | Crafted HTTP request | `RBACMiddleware` checks role on every request; legacy agent alias is read/action only |
| E-02 | SQL injection → DB admin | Malicious input in query params | Parameterized queries throughout (no string interpolation in SQL) |
| E-03 | Path traversal → config files | URL manipulation | No file serving from user-controlled paths |
| E-04 | Command injection via subprocess | No subprocess usage | No shell execution in gateway code |
| E-05 | Malicious policy rule → unrestricted access | Policy API abuse | Policy API requires `admin` role; rules validated on write |

**Mitigations in place:** `RBACMiddleware`; parameterized SQL; bandit SAST in CI

---

## 3. Risk Register

| ID | Threat | Likelihood | Impact | Risk Level | Mitigation Status |
|----|--------|-----------|--------|------------|-------------------|
| S-01 | Robot spoofing | Medium | High | **High** | Mitigated (bcrypt + RBAC) |
| S-03 | Token replay | Low | High | **Medium** | Open (no expiry) |
| T-01 | Audit tampering | Low | Critical | **High** | Mitigated (append-only + chain) |
| T-02 | Policy manipulation | Low | Critical | **High** | Mitigated (admin-only RBAC) |
| I-01 | Cross-tenant leakage | Low | Critical | **High** | Mitigated (DB-level isolation) |
| I-03 | PII in audit payloads | Medium | High | **High** | Partial (opt-in encryption) |
| D-01 | Request flood | Medium | Medium | **Medium** | Mitigated (rate limiting) |
| D-02 | Policy DoS | Low | Medium | **Low** | Mitigated (timeout + fail-safe) |
| E-02 | SQL injection | Low | Critical | **High** | Mitigated (parameterized SQL) |
| R-03 | Policy change repudiation | Low | Medium | **Low** | Open (no policy audit log) |

---

## 4. Security Controls Summary

| Layer | Control |
|-------|---------|
| Authentication | bcrypt-hashed API keys; `AuthMiddleware` |
| Authorization | `RBACMiddleware` (super_admin/governance_admin/security_admin/operator/auditor/developer/viewer; legacy aliases narrow) |
| Rate limiting | 10K req/min per agent via `RateLimitMiddleware` |
| Input validation | `ValidationMiddleware`; Pydantic strict schema |
| Audit integrity | Append-only triggers; SHA-256 chain hash |
| Encryption at rest | Fernet AES-128-CBC + HMAC-SHA256 (optional) |
| Secret scrubbing | `LogScrubberFilter` on all log handlers |
| Policy enforcement | Timeout + fail-safe; RBAC-protected mutation |
| Transport | TLS required in production (handled by reverse proxy/LB) |
| SAST | bandit in CI (`security/` and `middleware/` critical paths) |
| Dependency audit | pip-audit in CI |

---

## 5. Out-of-Scope

The following are not in scope for this threat model:
- Physical security of robot hardware
- Network infrastructure between robots and gateway
- Upstream AI model safety (EDON governs outputs, not model internals)
- Billing system (Stripe handles payment security)
- CI/CD pipeline compromise

---

## 6. Review Schedule

This threat model should be reviewed:
- At each major version release
- When adding new data flows or external integrations
- After any security incident
- Annually as a minimum

**Next review:** 2027-02-24
**Owner:** EDON Security Team
