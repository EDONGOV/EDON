# EDON Architecture

## Overview

EDON is an enterprise AI governance platform. Every action an AI agent attempts
passes through the EDON Gateway, which evaluates it against active policies and
returns a verdict before the action executes.

```text
AI Agent -> EDON Gateway (/v1/action) -> Verdict (ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE)
                |
                +-- Policy Engine
                +-- Risk Classifier
                +-- Prompt Injection Detector
                +-- Behavioral CAV (anomaly detection)
                +-- Audit Logger (tamper-proof)
```

## Repos (Monorepo: edongov/)

| Folder | What it is |
|--------|------------|
| `backend/` | FastAPI gateway - governance engine |
| `console/` | React console for governance, clinical, research, and assurance views |
| `docs/` | Platform and product documentation |
| `sdk/` | Python + JS client SDKs |
| `shared/` | Shared types and UI helpers |
| `demos/` | Offline demo environments (healthcare, law, logistics) |

## Deployment

- **Backend**: Fly.io (`edon-gateway` app, `iad` region)
- **Console**: local dev host or static deployment
- **Auth**: Clerk (JWT, JWKS at `clerk.edoncore.com`)
- **Database**: SQLite (development only) -> PostgreSQL (required for production, attach via fly postgres)
- **CAV Engine**: `edon-cav-api.fly.dev` (behavioral scoring, separate service)

## Repeatable architecture standard

EDON deployments should repeat the same invariant runtime across tenants while allowing customer-specific policy, market, integration, workflow, permission, and scale packs to vary. This is the platform contract: same kernel, same decision record, same audit proof, same enforcement semantics.

Market packs are tenant-pinned and versioned. For example, the healthcare pack
keeps hospital defaults, connector scope, and governance evidence together so
an existing client can stay on a known version while newer versions are tested
in shadow mode.

The invariant runtime includes the Decision Kernel as the causal core. Every
governed action becomes one typed `DecisionCandidate`, is committed once as one
immutable `DecisionRecord`, and downstream execution must bind to that record.

See [repeatable-architecture-standard.md](./repeatable-architecture-standard.md)
for the contract and proof requirements.

## Enterprise integration catalog

The gateway now exposes a canonical integration catalog at
`GET /integrations/enterprise/catalog`. It makes the supported enterprise and
hospital integration surfaces explicit and classifies each target by
deployment tier:

| Tier | Meaning |
|------|---------|
| supported | Approved for enterprise use in the current runtime contract |
| pilot | Allowed only in controlled pilot deployments |
| experimental | Not approved for production use |
| blocked | Explicitly disallowed |

| Category | Example systems |
|----------|-----------------|
| EHR / EMR | Epic, Oracle Health (Cerner), MEDITECH |
| IAM | Microsoft Entra ID, Okta, Ping Identity, Google Workspace |
| Clinical communications | TigerConnect, Vocera |
| Scheduling / staffing | UKG / Kronos, nurse staffing systems |
| Revenue cycle / billing | Epic billing, RCM vendors, claims systems |
| PACS / imaging | Radiology PACS, imaging AI tools |
| Laboratory systems | Labcorp, pathology systems, LIS platforms |
| ERP / procurement | SAP, Oracle ERP |
| Security / SIEM | Microsoft Sentinel, Splunk, CrowdStrike |
| AI / LLM providers | OpenAI, Anthropic, Ollama/Qwen, healthcare AI vendors |
| Robotics / physical AI | Logistics robots, humanoids, autonomous carts, pharmacy robotics |
| Messaging / workflow | Teams, Slack, ServiceNow, ticketing systems |

Each category carries a connector contract with auth modes, tenant scoping,
allowed actions, audit requirements, rollback behavior, tested versions, and
execution-binding requirements. In enterprise mode, the catalog defaults to the
`supported` tier only unless a deployment explicitly opts into pilot targets.
The catalog is a contract for integration readiness, not a claim that every
vendor connector is already custom-built.

## Governance Domains

| Domain | Systems Governed |
|--------|------------------|
| AI Agents | LLM agents, copilots, API bots |
| Industrial | Robots, PLCs, factory automation |
| Drones / UAVs | Swarm coordination, payload control |
| Humanoids | Physical robot human-in-the-loop |
| Medical / Nanobots | Dosage caps, acoustic transport |
| Edge Nodes | Offline / embedded governors |
| Swarm | Multi-agent quorum rules |

## Decision Flow

```text
1. Agent calls POST /v1/action
2. Auth middleware validates X-EDON-TOKEN (Clerk JWT or API key)
3. Rate limiter checks per-tenant quotas
4. Governor runs pipeline:
   a. Prompt injection scan
   b. Policy engine evaluates against active pack
   c. Risk classifier scores the action
   d. Behavioral CAV checks for anomalies
5. Verdict returned (< 200ms p95 target)
6. Audit log written (tamper-proof hash chain)
7. Webhooks fired if configured
```
