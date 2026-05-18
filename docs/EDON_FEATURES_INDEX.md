# EDON — Features index (now + soon)

**Purpose:** One place to find **EDON Impact**, **Shadow**, **Decision Kernel**, and the rest—what exists **today**, what’s **documented as target**, and **where to read more**.

---

## Platform pillars (high level)

| Pillar | What it is | Status | Documented in |
|--------|------------|--------|----------------|
| **Governance** | Intents, policy packs, custom rules, governor verdicts | **Shipped** (evolving) | [governance-model.md](./governance-model.md), [architecture.md](./architecture.md), [api-reference.md](./api-reference.md) |
| **Audit** | Tamper-evident decisions, query/export | **Shipped** | [governance-model.md](./governance-model.md) (audit chain); `backend/docs/` audit/compliance topics |
| **Shadow** | Adversarial replay, perturbations, drift, chain stress, findings API | **Shipped** | [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) § four layers + enforcement context; implementation: `backend/edon_gateway/shadow/`, `routes/shadow_findings.py` |
| **EDON Impact** | Pre-sale / pre-deployment **risk discovery**: vulnerability classes, failure scenarios, severity mapping; consumes governance config, **Shadow**, **DecisionRecord** lineage, and **system surface model** (tool graph, workflows, flows) | **Product / roadmap** — *not a separate shipped module named “Impact” in repo yet* | [EDON_IMPACT.md](./EDON_IMPACT.md); [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) |
| **Decision Kernel** | Single write path, `DecisionCandidate` → commit → immutable **`DecisionRecord`**; typed-only causal input; advisory non-causal; **`DecisionRecord` as SSOT across audit, Shadow, Impact, execution** (see kernel §1.1) | **Target architecture** — *implementation in progress / partial* | [DECISION_KERNEL.md](./DECISION_KERNEL.md) |
| **Real enforcement** | Network / identity / runtime / observability choke points | **Documented requirements** — *customer deployment* | [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) § “What real enforcement looks like” |

---

## Where each named concept lives

### EDON Impact

- **Product / architecture spec:** [EDON_IMPACT.md](./EDON_IMPACT.md) — risk discovery vs reporting, inputs (governance + Shadow + topology), outputs (vulnerability classes, scenarios, severity), **not** a second decision system.
- **Platform story:** [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) — fourth layer (“Discover”) and executive summary.
- **Implementation detail (when shipped):** PDF wizard, assumption DB, report templates—extend `EDON_IMPACT.md` or add engineering spec.

### Shadow (continuous adversarial assurance)

- **Product positioning:** [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md).
- **How to test the gateway (includes shadow-adjacent testing):** `backend/docs/GATEWAY_TESTING_OPTIONS.md`.
- **Code:** `backend/edon_gateway/shadow/` (perturbations, replay, diff, trace store), `backend/edon_gateway/routes/shadow_findings.py` (`/v1/shadow/*`).

### Decision Kernel

- **Full invariant spec:** [DECISION_KERNEL.md](./DECISION_KERNEL.md) (single kernel, normalization enforcement, multi-path elimination, advisory channel rules).
- **Short pointer in overview:** [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) — “Causal control model (target architecture)”.

### Audit chain & verdict vocabulary

- **Reason codes, packs, CAV, audit chain:** [governance-model.md](./governance-model.md).

### Deployment & “real infra” enforcement

- **Choke point narrative:** [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md).
- **Pilot / production readiness:** `backend/docs/DEPLOYMENT_READINESS.md`, `backend/docs/PILOT_READY_CHECKLIST.md`, `backend/docs/FLY_DEPLOY.md`.

---

## Features shipped today (backend gateway — representative)

*For exhaustive routes, use `/docs` and `/openapi.json` on a running gateway.*

| Area | Docs | Notes |
|------|------|--------|
| **`POST /v1/action`** | `backend/docs/ONBOARDING.md`, [api-reference.md](./api-reference.md) | Primary governance API |
| **Auth** | `backend/docs/AUTHENTICATION_METHODS.md`, `backend/docs/GET_YOUR_TOKEN.md` | Tokens, Clerk, etc. |
| **Policy packs & custom rules** | [governance-model.md](./governance-model.md), `backend/docs/` policy-related | Packs + `/policy/*` |
| **Intents** | `backend/docs/ONBOARDING.md` | Intent contracts |
| **Shadow API** | This index + platform overview | `/v1/shadow/*` |
| **Action results (close the loop)** | — | `/v1/action/result` — code: `routes/action_result.py` |
| **Billing / Stripe** | `backend/docs/STRIPE_LIVE_SETUP.md`, `backend/docs/BILLING_PER_DECISION.md` | When enabled |
| **Clawdbot / governance-only proxy** | `backend/docs/OPENCLAW_GOVERNANCE_ONLY.md`, `CLAWDBOT_INTEGRATION.md`, `QUICK_START_CLAWDBOT.md` | Invoke/proxy flows |
| **Threat model & security** | `backend/docs/THREAT_MODEL.md`, `ENTERPRISE_SAFETY.md` | STRIDE, controls |
| **Ops / runbooks** | `backend/docs/OPERATIONS_RUNBOOK.md`, `CONFIGURATION.md`, root `docs/runbooks/*` | SRE |
| **Telegram** | `backend/docs/TELEGRAM_*.md`, `CONNECT_TELEGRAM_BOT.md` | Bot integration |
| **Network isolation / gating** | `backend/docs/NETWORK_ISOLATION_GUIDE.md`, `NETWORK_GATING_IMPLEMENTATION.md` | Defense in depth |
| **Testing** | `backend/docs/GATEWAY_TESTING_OPTIONS.md` | Pytest, load tests, smoketests |

---

## Soon to come (from product/architecture direction)

| Item | Where it’s defined | Implementation |
|------|-------------------|----------------|
| **Decision Kernel in code** | [DECISION_KERNEL.md](./DECISION_KERNEL.md) | Single pipeline; typed-only causal input; one canonical record |
| **Enforcement-grade normalization** | [DECISION_KERNEL.md](./DECISION_KERNEL.md) § 3.4–3.6 | Per-tool schemas; reject/escalate ambiguous payloads |
| **EDON Impact (full product)** | [EDON_IMPACT.md](./EDON_IMPACT.md) | Topology ingestion, scenario engine, severity model, readouts/PDFs; **Shadow + topology + risk synthesis** (not Shadow-only summary) |
| **Choke-point patterns in customer guides** | [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) | Playbooks, reference architectures |

---

## Repo map (quick)

| Path | Contents |
|------|----------|
| `docs/` | Platform overview, Decision Kernel, governance model, architecture, API ref, runbooks |
| `backend/docs/` | Gateway-specific how-tos, threat model, billing, integrations, ops |
| `backend/edon_gateway/` | Gateway implementation (routes, governor, shadow, middleware) |
| `frontend/` | Dashboard / agent UI |
| `sdk/` | Client SDKs |
| `contracts/` | Legal/commercial templates (as present) |

---

## Related root docs

- [README.md](../README.md) — clone, run backend/frontend, tests
- [ENTERPRISE_READINESS.md](../ENTERPRISE_READINESS.md) — enterprise checklist (org/process, not feature code)
- [DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md) — launch checklist (repo root)

---

*Keep this file updated when Impact ships in code or Decision Kernel milestones land.*
