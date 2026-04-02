# EDON Architecture

## Overview

EDON is an enterprise AI governance platform. Every action an AI agent attempts passes through the EDON Gateway, which evaluates it against active policies and returns a verdict before the action executes.

```
AI Agent → EDON Gateway (/v1/action) → Verdict (ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE)
                │
                ├── Policy Engine
                ├── Risk Classifier
                ├── Prompt Injection Detector
                ├── Behavioral CAV (anomaly detection)
                └── Audit Logger (tamper-proof)
```

## Repos (Monorepo: edongov/)

| Folder | What it is |
|--------|-----------|
| `frontend/` | React SPA — customer dashboard (agent.edoncore.com) |
| `backend/` | FastAPI gateway — governance engine (edon-gateway.fly.dev) |
| `infrastructure/` | Fly.io configs, Docker, local dev compose |
| `docs/` | This folder |
| `sdk/` | Python + JS client SDKs |
| `shared/` | TypeScript types shared across frontend/backend |
| `demos/` | Offline demo environments (healthcare, law, logistics) |

## Deployment

- **Backend**: Fly.io (`edon-gateway` app, `iad` region)
- **Frontend**: Fly.io / static host (`agent.edoncore.com`)
- **Auth**: Clerk (JWT, JWKS at `clerk.edoncore.com`)
- **Database**: SQLite (single machine) → PostgreSQL (multi-machine, attach via fly postgres)
- **CAV Engine**: `edon-cav-api.fly.dev` (behavioral scoring, separate service)

## Governance Domains

| Domain | Systems Governed |
|--------|-----------------|
| AI Agents | LLM agents, copilots, API bots |
| Industrial | Robots, PLCs, factory automation |
| Drones / UAVs | Swarm coordination, payload control |
| Humanoids | Physical robot human-in-the-loop |
| Medical / Nanobots | Dosage caps, acoustic transport |
| Edge Nodes | Offline / embedded governors |
| Swarm | Multi-agent quorum rules |

## Decision Flow

```
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
