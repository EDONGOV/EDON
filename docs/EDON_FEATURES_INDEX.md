# EDON Features Index

**Purpose:** one place to find EDON's governance, audit, Shadow, Decision Kernel,
repeatable architecture standard, and deployment readiness docs.

The repeatable architecture standard is the platform contract: same kernel,
same decision record, same execution binding, same audit proof, different
customer packs.

## Platform pillars

| Pillar | What it is | Status | Documented in |
|--------|------------|--------|----------------|
| Governance | Intents, policy packs, custom rules, governor verdicts | Shipped | [governance-model.md](./governance-model.md), [architecture.md](./architecture.md) |
| Audit | Tamper-evident decisions, query/export | Shipped | [governance-model.md](./governance-model.md) |
| Shadow | Adversarial replay, perturbations, drift, chain stress | Shipped | [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md), `backend/edon_gateway/shadow/` |
| EDON Impact | Pre-sale / pre-deployment risk discovery | Product / roadmap | [EDON_IMPACT.md](./EDON_IMPACT.md) |
| Decision Kernel | Single write path and immutable decision record | Target architecture | [DECISION_KERNEL.md](./DECISION_KERNEL.md) |
| Real enforcement | Network / identity / runtime / observability choke points | Documented requirements | [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) |
| Repeatable architecture standard | Invariant runtime + Decision Kernel + execution binding + customer-variable packs + proof requirements | Shipped | [repeatable-architecture-standard.md](./repeatable-architecture-standard.md), [architecture.md](./architecture.md) |

## Where each named concept lives

### EDON Impact

- Product / architecture spec: [EDON_IMPACT.md](./EDON_IMPACT.md)
- Platform story: [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md)

### Shadow

- Product positioning: [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md)
- Code: `backend/edon_gateway/shadow/`, `backend/edon_gateway/routes/shadow_findings.py`

### Decision Kernel

- Full invariant spec: [DECISION_KERNEL.md](./DECISION_KERNEL.md)
- Short pointer in overview: [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md)

### Audit chain & verdict vocabulary

- Reason codes, packs, CAV, audit chain: [governance-model.md](./governance-model.md)

### Repeatable architecture standard

- Contract and proof requirements: [repeatable-architecture-standard.md](./repeatable-architecture-standard.md)
- Machine-readable generator: `backend/edon_gateway/onboarding/repeatable_architecture.py`
- API endpoint: `GET /v1/onboarding/profiles/{profile_id}/architecture-standard`

## Repo map

| Path | Contents |
|------|----------|
| `docs/` | Platform overview, Decision Kernel, governance model, architecture, feature index, runbooks |
| `backend/docs/` | Gateway-specific how-tos, threat model, billing, integrations, ops |
| `backend/edon_gateway/` | Gateway implementation (routes, governor, shadow, middleware) |
| `console/` | Governance console and shared UI surfaces |
| `sdk/` | Client SDKs |

## Related root docs

- [README.md](../README.md)
- [ENTERPRISE_READINESS.md](../ENTERPRISE_READINESS.md)
- [DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md)
