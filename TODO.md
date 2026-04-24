# EDON — Master Build List & Operating Costs
_Last updated: 2026-04-17_

---

## LEGEND
- ✅ Done
- 🔧 Needs wiring / partial
- ⬜ Not started

---

## 1. CORE GATEWAY (edon-gateway.fly.dev)

### Engine
- ✅ Governance decision engine (ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE)
- ✅ Policy rules (db-backed, per-tenant, priority-ordered)
- ✅ Risk classifier (anomaly scores, action_estimated_risk)
- ✅ Prompt injection detector
- ✅ Intent alignment checker
- ✅ Audit event logging (full chain of custody)
- ✅ Multi-tenant RBAC + Clerk JWT auth
- ✅ Rate limiting + quota enforcement
- ✅ Kill switch (per-tenant, per-agent, global)
- ✅ Shadow mode (capture → replay → perturb → compare verdicts)
- ✅ Fleet learning (Bayesian risk from feedback_labels across all tenants)
- ✅ Anomaly detector (per-agent behavioral baseline)

### Impact Engine (A → B → C → D loop)
- ✅ Engine A: failure state generation (vulnerability graph builder)
- ✅ Engine B: red team scenario generation (attack narratives)
- ✅ Engine C: validation (reachability + policy violation confirmation)
- ✅ Engine D: CREAO self-healing (autonomous rule deployment)
- 🔧 Engine D wiring to hardening runner (healing runner exists, verify D fires after each C cycle)

### Hardening Agents (every 10 min, per tenant)
- ✅ Coverage agent (probes failure states → shadow findings)
- ✅ Policy agent (proposes governance rules from findings)
- ✅ Regression agent (tests proposed rules against recent traces)
- ✅ Self-healing runner (deploys rules, calls healing deployer)
- ✅ Multi-tenant scheduler (iterates all active tenants per cycle)

### Self-Healing
- ✅ CREAO engine (suggest_only / assisted / autonomous modes)
- ✅ Healing deployer (deploy_rule → fire_healing_alert)
- ✅ EDON_CREAO_MODE=autonomous in production (fly.gateway.toml)
- ✅ Alert on deploy (Telegram + webhook)

---

## 2. INTERNAL EDON AGENTS (backend/agents/ via GitHub Actions)

### Governance wired (gov_check before external actions)
- ✅ onboarding_agent — gov_check before send_email, notify_telegram
- ✅ outbound_agent — gov_check before save_draft
- ✅ chief_of_staff — wired
- ✅ code_agent — wired
- ✅ content_agent — wired
- ✅ followup_agent — wired
- ✅ incident_agent — wired
- ✅ integration_agent — wired
- ✅ product_intelligence_agent — wired
- ✅ regulatory_watcher — wired
- ✅ security_monitor_agent — wired

### NOT YET governed (add gov_check before any external action)
- ⬜ customer_agent — needs gov_check before email / CRM writes
- ⬜ docs_agent — needs gov_check before GitHub commit / PR
- ⬜ demo_agent — needs gov_check before external API calls
- ⬜ qa_agent — needs gov_check before test result writes / notifications
- ⬜ competitor_monitor — needs gov_check before web scrape / storage write
- ⬜ account_manager — needs gov_check before CRM / email / contract writes
- ⬜ security_questionnaire_agent — needs gov_check before sending questionnaire

### GitHub Actions workflows
- ✅ chief_of_staff.yml
- ✅ followup_agent.yml
- ✅ content_agent.yml
- ✅ competitor_monitor.yml
- ✅ account_manager.yml
- ✅ security_monitor.yml
- ✅ regulatory_watcher.yml
- ✅ product_intelligence.yml
- ✅ docs_agent.yml
- ✅ code_agent.yml
- ✅ incident_agent.yml
- ✅ nightly_qa.yml
- ✅ integration_agent.yml
- ⬜ customer_agent.yml
- ⬜ demo_agent.yml
- ⬜ security_questionnaire_agent.yml

---

## 3. TRAINING PIPELINE (backend/edon_gateway/training/)

- ✅ extractors.py — pulls from audit_events, shadow_traces, feedback_labels, impact_failure_states, policy_rules
- ✅ formatters.py — converts to Anthropic fine-tuning JSONL (4 system prompts: governance, vuln, risk, fix)
- ✅ synthetic.py — 530 bootstrap examples (activates when real data < 50 per dataset)
- ✅ pipeline.py — extract → format → merge → write JSONL → upload to Anthropic Files API → create fine-tuning job
- ✅ routes/training.py — API endpoints (export, upload, start, status, jobs, run, datasets)
- ✅ Registered in main.py

### Still to do
- ⬜ Run first training export once 1 real client is active (POST /v1/training/run)
- ⬜ Set ANTHROPIC_API_KEY fly secret (needed for pipeline + Jarvis)
- ⬜ Schedule monthly re-training cron once data accumulates
- ⬜ Swap fine-tuned model ID into gateway config (EDON_AI_MODEL env var) when first job completes

---

## 4. JARVIS (voice + text AI assistant)

- ✅ Backend orchestrator: /v1/jarvis/ask (Claude tool_use loop, 9 live data tools)
  - get_system_health, get_governance_stats, get_client_health
  - get_active_findings, get_healing_history, get_shadow_findings
  - get_fleet_risk, get_training_status, get_hardening_status
- ✅ Registered in main.py
- ✅ Admin page upgraded — CommandTab now calls backend Jarvis (live data mode)
- ✅ Multi-turn conversation memory (last 10 turns)
- ✅ Voice input — Whisper transcription (OpenAI)
- ✅ Voice output — OpenAI TTS (onyx voice)
- ✅ Telegram /jarvis command — text questions with live EDON data
- ✅ Telegram voice messages — auto-transcribed via Whisper → Jarvis
- ✅ Unknown Telegram messages → auto-routed to Jarvis (no slash needed)

### Still to do
- ⬜ Add OPENAI_API_KEY to Fly.io secrets (fly secrets set OPENAI_API_KEY=sk-...) — needed for Telegram voice
- ⬜ Add get_results() to shadow TraceStore (Pyright flagged missing)
- ⬜ Add Jarvis tab to client-facing console frontend (console.edoncore.com)
- ⬜ Add training dashboard to admin (show dataset sizes, last job status, fire pipeline)
- ⬜ ElevenLabs voice option (higher quality than OpenAI TTS) — connector exists in connectors/elevenlabs_connector.py

---

## 5. PROOF REPORT (client sales artifact)

- ✅ proof/report.py — assembles FailureState + LogicalProof + RedTeamScenario + ImpactValue
- ✅ GET /v1/proof/report — API endpoint
- ✅ frontend/src/pages/Report.tsx — animated browser report with PDF export
- ✅ Wired into App.tsx routes

### Still to do
- ⬜ Verify report renders correctly with real client data (currently only tested with synthetic)
- ⬜ Add report link to console nav under "Impact" tab
- ⬜ White-label client logo + company name in report header
- ⬜ Email report delivery (send PDF link via account_manager after proof run)

---

## 6. INFRASTRUCTURE

- ✅ Fly.io deployment (edon-gateway, 1 machine, 1GB RAM, 2 vCPU)
- ✅ SQLite on persistent Fly volume (edon_gateway_data → /app/data)
- ✅ CORS configured for all production domains
- ✅ Clerk JWT auth (clerk.edoncore.com)
- ✅ HTTPS forced
- ✅ CAV integration (edon-cav-api.fly.dev)

### Critical: Data safety before first real client
- ⬜ Migrate to PostgreSQL BEFORE real clients (fly postgres create → attach → remove EDON_DATABASE_PATH)
  - Instructions already in fly.gateway.toml comments
  - Scale min_machines_running to 2 for HA
- ⬜ Set up automated DB backups (pg_dump daily → S3 or Fly snapshots)
- ⬜ Run POST /v1/training/export weekly as data backup (JSONL = distilled training value)

### Fly.io secrets to set
- ⬜ ANTHROPIC_API_KEY — Jarvis + training pipeline (critical)
- ⬜ OPENAI_API_KEY — Telegram voice transcription
- ⬜ EDON_BOOTSTRAP_SECRET — protects Jarvis + admin API (set if not already)
- ✅ TELEGRAM_BOT_TOKEN
- ✅ TELEGRAM_OWNER_CHAT_ID
- ✅ TELEGRAM_WEBHOOK_SECRET
- ✅ CLERK_JWKS_URL

---

## 7. BILLING & CLIENTS

- ✅ Stripe integration (billing/stripe_client.py)
- ✅ Usage metering (billing/metering.py)
- ✅ Plans defined (billing/plans.py): starter / growth / enterprise
- ✅ Bootstrap onboarding flow
- ✅ Admin page: contract management, ACV tracking, tenant lifecycle

### Still to do
- ⬜ Activate Stripe live keys (currently test mode assumed)
- ⬜ First client onboard — run bootstrap, verify decisions flowing
- ⬜ Set up renewal alerts via account_manager
- ⬜ Proof report delivery workflow (run impact → generate report → email to prospect)

---

## 8. API CREDITS — WHAT POWERS EDON

### A. Internal Agent Loop (GitHub Actions, monthly estimate)
These are EDON's own background agents running on your behalf.

| Agent | Frequency | Model | Est. $/month |
|---|---|---|---|
| chief_of_staff | Daily | claude-sonnet-4-6 | $5–8 |
| followup_agent | Daily | claude-haiku-4-5 | $3–5 |
| content_agent | Daily | claude-sonnet-4-6 | $4–7 |
| competitor_monitor | 3×/week | claude-haiku-4-5 | $2–4 |
| account_manager | Daily | claude-haiku-4-5 | $2–4 |
| security_monitor_agent | Daily | claude-haiku-4-5 | $1–3 |
| regulatory_watcher | Weekly | claude-haiku-4-5 | $1–2 |
| product_intelligence_agent | Weekly | claude-sonnet-4-6 | $2–4 |
| docs_agent | Per PR | claude-haiku-4-5 | $1–3 |
| code_agent | On demand | claude-sonnet-4-6 | $3–6 |
| qa_agent | Nightly | claude-haiku-4-5 | $2–4 |
| incident_agent | On demand | claude-sonnet-4-6 | $1–3 |
| integration_agent | On demand | claude-haiku-4-5 | $1–2 |
| **Total internal** | | | **~$28–55/month** |

### B. Gateway per client (governance decisions + AI layers)
Every client action flowing through the EDON gateway costs:

| Component | Volume assumption | Model | Est. $/month/client |
|---|---|---|---|
| Governance decisions | 10,000/day | claude-haiku-4-5 | $25–40 |
| Risk classifier | Per decision (batched) | claude-haiku-4-5 | included above |
| Impact engine (A–D cycle) | Weekly per tenant | claude-sonnet-4-6 | $15–25 |
| CREAO self-healing | 3–5 proposals/cycle | claude-sonnet-4-6 | $5–10 |
| Hardening agents | Every 10 min | claude-haiku-4-5 | $5–10 |
| Shadow mode replay | Async background | claude-haiku-4-5 | $3–5 |
| Proof report generation | On demand | claude-sonnet-4-6 | $1–3/run |
| **Total per client/month** | | | **~$53–90/month** |

At 10,000 decisions/day that's ~300K decisions/month.
At 100K decisions/day (large enterprise): multiply by ~10 → ~$300–600/month/client.
Still ~93–97% gross margin at $5K–10K/month contract.

### C. Jarvis (your personal AI command interface)
| Component | Volume | Model | Est. $/month |
|---|---|---|---|
| Jarvis queries (admin + Telegram) | ~50/day | claude-sonnet-4-6 | $12–30 |
| Telegram voice transcription | ~20 voice msgs/day | OpenAI Whisper | $1–2 |
| Voice output (TTS) | Optional, ~20/day | OpenAI TTS-1 | $1–3 |
| **Total Jarvis** | | | **~$14–35/month** |

### D. Training pipeline (periodic, not continuous)
| Component | When | Cost |
|---|---|---|
| Export JSONL | Weekly | $0 (no API call) |
| Upload to Anthropic Files API | Per training run | $0 (file storage) |
| Fine-tune claude-haiku-4-5 | Monthly | $2–8/run |
| Fine-tune claude-sonnet-4-6 | Quarterly | $15–40/run |
| **Total training** | | **~$5–15/month** |

### E. OpenAI (Whisper only — everything else is Anthropic)
| Component | Est. $/month |
|---|---|
| Whisper voice transcription (Telegram + admin) | $2–5 |

---

## 9. TOTAL MONTHLY COST SCENARIOS

### Solo founder, 0 clients (now)
| | Low | High |
|---|---|---|
| Internal agents | $28 | $55 |
| Jarvis | $14 | $35 |
| Training | $5 | $15 |
| Infrastructure (Fly.io) | $20 | $30 |
| OpenAI | $2 | $5 |
| **Total** | **~$69** | **~$140** |

### 1 client (e.g., $5,000 ACV / $417/month)
| | Low | High |
|---|---|---|
| Above baseline | $69 | $140 |
| +1 client gateway | $53 | $90 |
| **Total operating** | **~$122** | **~$230** |
| Revenue | $417 | $417 |
| **Gross margin** | **~71%** | **~45%** |

### 5 clients ($25,000/month revenue)
| | Est. |
|---|---|
| Baseline operating | ~$100 |
| 5× client gateway | ~$350 |
| Infrastructure (Postgres, 2 machines) | ~$80 |
| **Total operating** | **~$530** |
| Revenue | $25,000 |
| **Gross margin** | **~98%** |

### 20 clients ($100,000/month revenue)
| | Est. |
|---|---|
| Baseline | ~$100 |
| 20× client gateway | ~$1,400 |
| Infrastructure | ~$200 |
| **Total operating** | **~$1,700** |
| Revenue | $100,000 |
| **Gross margin** | **~98.3%** |

---

## 10. RECOMMENDED FIRST ACTIONS (IN ORDER)

1. **Set Fly.io secrets** — `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` unlock Jarvis + training + Telegram voice
2. **Wire remaining 7 agents** with gov_check (customer_agent, docs_agent, demo_agent, qa_agent, competitor_monitor, account_manager, security_questionnaire_agent)
3. **Migrate to PostgreSQL** — before first real client. Instructions in fly.gateway.toml. One command.
4. **Onboard first client** — run bootstrap, verify governance decisions flowing, run impact engine
5. **Generate proof report** — run POST /v1/proof/report, verify it renders with real data, use in next sales call
6. **Run first training export** — POST /v1/training/run once first client has 2-3 weeks of data
7. **Test Jarvis end-to-end** — voice message on Telegram, check it queries live data and responds
8. **Add Jarvis to console frontend** — so clients can ask questions about their own agent health
9. **Set up Stripe live keys** — move from test to production billing
10. **Schedule weekly training exports** — cron or manual, keeps JSONL backup as data grows

---

## 11. WHAT EDON DOES AUTONOMOUSLY (ZERO MANUAL WORK)

Once `ANTHROPIC_API_KEY` is set and a client is active, this runs 24/7 with no input from you:

- Every action every client agent takes → governance decision in <50ms
- Every 10 minutes → hardening agents scan for new vulnerabilities, propose rules, test them, deploy the good ones
- Continuously → fleet learning updates risk scores across all tenants
- Weekly → impact engine full cycle (A→B→C→D): finds vulnerabilities, generates attack narratives, validates them, auto-deploys fixes
- On every deployment → shadow mode replays historical traces against new rules, catches regressions
- On critical findings → Telegram alert fires immediately
- On rule deployment → Telegram alert fires immediately
- Daily → chief_of_staff agent brief lands in Telegram
- On follow-up due → Telegram alert from followup_agent

The only thing you manually touch: sales calls, client conversations, and reading Jarvis briefings on your phone.
