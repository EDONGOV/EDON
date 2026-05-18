# EDON — Project Map

This file is the authoritative directory guide for all agents (Claude Code, sub-agents, CI agents).
Read this before touching any code.

## Monorepo layout

```
edongov/
├── console/          ← Tenant-facing web app (React + Vite)  "edon-console"
│   ├── src/          ← App.tsx, api.ts, main.tsx
│   └── package.json
│
├── admin/            ← Internal admin panel (React + Vite)   "edon-admin"
│   ├── src/          ← App.tsx + component tree
│   └── package.json
│
├── backend/          ← Python monolith (FastAPI)
│   ├── edon_gateway/ ← Core gateway: governor, policy engine, routes, agents
│   └── agents/       ← Autonomous agent definitions
│
├── EdonLP/           ← Marketing site (submodule — do NOT edit files directly)
│
├── frontend/         ← LEGACY — being migrated into console/. Do not add features here.
│
├── sdk/              ← Python + JS SDKs for external integrations
├── infrastructure/   ← Fly.io / deployment config
├── demos/            ← Standalone demo apps
└── docs/             ← Documentation
```

## Rules for agents

1. **console/** is the tenant console. All user-facing governance UI work goes here.
2. **admin/** is the internal admin panel. Ops/internal tooling goes here.
3. **backend/edon_gateway/** is the gateway. API routes, governor, policy engine, agents all live here.
4. **Never edit frontend/** for new features — it is being phased out in favour of console/.
5. **Never edit EdonLP/** directly — it is a git submodule.
6. When adding a new API route, register it in `backend/edon_gateway/main.py`.
7. When adding a new frontend page to console, add it in `console/src/`.

## Dev servers

| App | Command | Default port |
|-----|---------|--------------|
| console | `cd console && npm run dev` | 5173 |
| admin | `cd admin && npm run dev` | 5174 |
| backend gateway | `cd backend && uvicorn edon_gateway.main:app --reload` | 8000 |

## Key backend files

| File | Purpose |
|------|---------|
| `backend/edon_gateway/governor.py` | Core governance evaluation (12-step pipeline) |
| `backend/edon_gateway/policy/engine.py` | Policy rule evaluation |
| `backend/edon_gateway/routes/v1_action.py` | Input governance endpoint |
| `backend/edon_gateway/routes/v1_output.py` | Output governance endpoint |
| `backend/edon_gateway/security/output_filter.py` | PHI/credential/bulk-data scanner |
| `backend/edon_gateway/state/sequence_scorer.py` | Multi-step attack detection |
| `backend/edon_gateway/state/session_trust.py` | Adaptive session trust scoring |
| `backend/edon_gateway/degradation_registry.py` | BLOCK→DEGRADE safe alternatives |
| `backend/edon_gateway/control/meta_governance.py` | Self-audit / meta-governance |

---

## Coding Principles (Karpathy-Inspired)

### 1. Think Before Coding
- State assumptions explicitly — if uncertain, ask rather than guess
- Present multiple interpretations when ambiguity exists — don't pick silently
- Push back when a simpler approach exists
- Stop when confused — name what's unclear and ask for clarification

### 2. Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked
- No abstractions for single-use code
- No "flexibility" or "configurability" that wasn't requested
- No error handling for impossible scenarios
- If 200 lines could be 50, rewrite it

### 3. Surgical Changes
- Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting unprompted
- Don't refactor things that aren't broken
- Match existing style, even if you'd do it differently
- If you notice unrelated dead code, mention it — don't delete it
- Remove imports/variables/functions that YOUR changes made unused; leave pre-existing dead code alone

### 4. Goal-Driven Execution
- Define success criteria before starting. Loop until verified.
- For multi-step tasks, state a brief plan with a verify step for each stage
- Write tests for the failure case first, then make them pass
- Weak criteria ("make it work") require clarification before proceeding
