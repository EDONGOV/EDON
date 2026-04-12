# EDON Agent Upgrade Plan

Last audited: 2026-04-09  
Total agents: 19  
Purpose: Track what needs upgrading across the internal AI team, why, and what done looks like.

---

## Priority Legend
- 🔴 **CRITICAL** — Broken, risky, or blocking top-of-funnel work
- 🟠 **HIGH** — Working but missing key capability; noticeable pain weekly
- 🟡 **MEDIUM** — Functional but leaves value on the table
- 🟢 **LOW** — Nice to have, non-urgent

---

## 🔴 CRITICAL

### 1. Onboarding Agent (`onboarding_agent.py`)
**Problem:** Silent failures everywhere. If SMTP isn't configured, it fails silently. If tenant provisioning fails, it continues anyway. No audit trail of who was onboarded or when.

**Upgrades needed:**
- [ ] Validate SMTP config at startup, fail loudly if missing
- [ ] Add rollback: if provisioning fails mid-way, undo partial state
- [ ] Write every onboarding to `am_memory/{tenant_id}.json` automatically (feeds account_manager)
- [ ] Require review of Claude-generated welcome email before SMTP send (use `--auto-send` flag to opt in)
- [ ] Add `--list` command to see all onboarded tenants and status

**Why it matters:** First touchpoint with every customer. A silent failure here means the customer gets no API key, no welcome email, and doesn't know what happened.

---

### 2. Docs Agent (`docs_agent.py`)
**Problem:** Replaces the *entire* `docs/api-reference.md` file with Claude's output. One bad generation wipes all docs.

**Upgrades needed:**
- [ ] Switch from `file.write_text(claude_output)` to section-by-section patching (find the section header, replace only that block)
- [ ] Always create a backup of the file before writing
- [ ] Validate output has minimum expected headings before writing
- [ ] Add `--dry-run` flag that prints the diff without writing
- [ ] PR should include a before/after diff in the body

**Why it matters:** A bad LLM output currently deletes your entire API documentation. This is a data-loss risk.

---

### 3. Code Agent (`code_agent.py`)
**Problem:** Uses `str.replace()` to patch files — no codebase navigation, can only change one file, fails if search string isn't found exactly. Test execution is a subprocess call with no result parsing.

**Upgrades needed:**
- [ ] Replace `apply_change()` with Claude Code CLI: `claude --print --allowedTools "Edit,Bash,Read,Glob,Grep" -p "$(cat task.md)"`
- [ ] Install `@anthropic-ai/claude-code` in the GitHub Actions workflow
- [ ] Expand `ALLOWED_PATHS` to include `routes/`, `agents/`, `persistence/` (not just clinical safety)
- [ ] Parse pytest output to extract actual failure count, not just exit code
- [ ] Add `--max-risk medium` guard so it never attempts high-risk changes without manual trigger
- [ ] Save last 5 PRs to `code_agent_history.json` so it doesn't re-propose the same change

**Why it matters:** The harness upgrade turns this from a fragile string-patcher into an agent that can actually understand the codebase, navigate multiple files, and make real changes.

---

## 🟠 HIGH

### 4. Incident Agent (`incident_agent.py`)
**Problem:** All detection thresholds are hardcoded constants. No memory across incidents — can't detect "this is the third latency spike this week."

**Upgrades needed:**
- [ ] Store incident history in `incident_log.json` (append-only, last 90 days)
- [ ] Make thresholds configurable via `incident_config.json` (no code change needed to tune)
- [ ] Add pattern detection: if same issue fires 3x in 7 days, escalate severity
- [ ] Deduplicate GitHub issues — check open issues before filing a duplicate
- [ ] Add "resolved" comment when the same metric returns to baseline

**Why it matters:** Runs every 5 minutes. Without memory, it opens duplicate issues for the same outage, and you can't tune thresholds without editing Python.

---

### 5. Regulatory Watcher (`regulatory_watcher.py`)
**Problem:** Detects compliance gaps but has no way to fix them. Findings sit as GitHub issues and nothing happens.

**Upgrades needed:**
- [ ] After filing a gap issue, also write a task file that `code_agent.py` picks up next Sunday
- [ ] Track which regulations have been checked in `regulatory_baseline.json` to avoid duplicate alerts
- [ ] Expand feed sources (currently only HHS/FDA/DEA/NIST; add OCR, CMS, ONC)
- [ ] Upgrade from `claude-haiku-4-5-20251001` → `claude-sonnet-4-6` for better gap analysis
- [ ] Add `--check-rule "HIPAA-001"` for manual targeted checks

**Why it matters:** Regulatory gaps are the #1 risk for healthtech buyers. The watcher sees them but can't act — fixing the closed loop turns it from an alerting system into a compliance engine.

---

### 6. QA Agent (`qa_agent.py`)
**Problem:** Tests are synthetic payloads with hardcoded expected verdicts. Uses `claude-haiku` for failure analysis (lower quality). No tracking of test pass rate over time.

**Upgrades needed:**
- [ ] Load test payloads from a fixture file (`qa_fixtures.json`) not hardcoded — easier to expand
- [ ] Record pass/fail history in `qa_baseline.json` to track regression trends
- [ ] Upgrade from `claude-haiku-4-5-20251001` → `claude-sonnet-4-6` for root cause analysis
- [ ] Add test for policy interactions (two rules that could conflict)
- [ ] Report pass rate % in the GitHub Actions summary, not just pass/fail

**Why it matters:** Nightly QA is your safety net. Haiku-level analysis and synthetic-only payloads mean you can miss real-world regressions.

---

### 7. Follow-up Agent (`followup_agent.py`)
**Problem:** Generates follow-up drafts but never sends them. No integration with the actual email flow. Manual tracking only.

**Upgrades needed:**
- [ ] Add SMTP send with `--auto-send` flag (same pattern as onboarding_agent upgrade)
- [ ] When `outbound_agent.py` saves a draft, auto-register the prospect in `followup_tracker.json`
- [ ] Track "reply received" by checking a designated inbox (IMAP) or webhook
- [ ] Integrate with account_manager: when a prospect converts, promote their record

**Why it matters:** You lose deals from slow follow-up. This is the agent most directly tied to revenue for a solo founder.

---

## 🟡 MEDIUM

### 8. Account Manager (`account_manager.py`)
**Problem:** Weekly health reports generated but no auto-send. SMTP is optional config. No connection to other agents' outputs.

**Upgrades needed:**
- [ ] Auto-send emails when health score drops below 60 (not just weekly)
- [ ] Pull `onboarding_record.json` to auto-register clients — no manual `--new` needed
- [ ] Feed account health data to chief_of_staff brief automatically
- [ ] Add `--dashboard` command to print all client health scores in one table

---

### 9. Ops Agent (`ops_agent.py`)
**Problem:** Code health check greps for TODO/FIXME (too noisy). Pain point issues are filed with no priority signal. No memory of previous issues.

**Upgrades needed:**
- [ ] Track filed issues in `ops_issue_log.json` — don't re-file if issue is still open
- [ ] Add gateway-level checks for slow routes (>500ms p95 over the last 24h from timeseries)
- [ ] Replace TODO/FIXME scan with a smarter code debt signal (cyclomatic complexity via `radon`, or just files over 500 lines)
- [ ] Add a "resolved this week" section to show what got fixed

---

### 10. Integration Agent (`integration_agent.py`)
**Problem:** Generates SDK examples but never tests them. Files are saved without PR. No tracking of which integrations were actually built.

**Upgrades needed:**
- [ ] Run generated examples through a syntax check (`python -m py_compile`) before saving
- [ ] Auto-PR generated examples to `examples/integrations/` branch for review
- [ ] Keep `integration_backlog.json` — ideas that were generated but not yet PRed

---

### 11. Security Monitor Agent (`security_monitor_agent.py`)
**Problem:** Prompt injection detection is basic string matching (many false positives). No response automation — just fires GitHub issues.

**Upgrades needed:**
- [ ] Use semantic similarity for injection detection, not keyword matching
- [ ] Add quarantine action: if CRITICAL severity, call `/admin/agents/{agent_id}/status` to set `paused`
- [ ] Track threat patterns over time in state file (build threat baseline)
- [ ] Deduplication: don't open a new issue if the same threat fired in the last 24h

---

### 12. Chief of Staff (`chief_of_staff.py`)
**Problem:** High dependency on all other agents running successfully. No state persistence. If an upstream file is missing, brief is incomplete with no warning.

**Upgrades needed:**
- [ ] Add fallback for each missing agent output file (show "unavailable" instead of crashing)
- [ ] Track brief history in `brief_archive/YYYY-MM-DD.json` for lookback
- [ ] Add a "What changed since yesterday" section using diff between today's and yesterday's brief
- [ ] Fix wrong `GITHUB_REPO` default — currently `GHOSTCODERRRRAHAHA/edongov`, should be `EDONGOV/EDON`

---

### 13. Outbound Agent (`outbound_agent.py`)
**Problem:** Saves drafts but no tracking, no integration with follow-up, no way to see what was sent.

**Upgrades needed:**
- [ ] After saving draft, auto-register prospect in `followup_tracker.json` with status `draft_ready`
- [ ] Add `--sent <company>` command to mark a draft as sent (kicks off follow-up countdown)
- [ ] Keep a `outbound_log.json` of all companies researched (avoid duplicates)

---

### 14. Content Agent (`content_agent.py`)
**Problem:** Posts are saved to repo but no git integration, no PR automation.

**Upgrades needed:**
- [ ] Auto-commit new posts to `content-agent/post-YYYY-MM-DD` branch and open a PR
- [ ] Add `--topic-add` command to append to the topic queue from CLI
- [ ] Track which posts performed well (by checking GitHub merge + view count if GA is available)

---

### 15. Product Intelligence Agent (`product_intelligence_agent.py`)
**Problem:** Findings filed as issues but no integration with roadmap or sales.

**Upgrades needed:**
- [ ] When finding upsell signal, also write to `account_manager` memory for that tenant
- [ ] Track insight history in `product_intel_log.json` to spot recurring themes
- [ ] Add a "top friction points" summary to the chief_of_staff brief

---

## 🟢 LOW

### 16. Competitor Monitor (`competitor_monitor.py`)
**Upgrades needed:**
- [ ] Add `competitor_history.json` — track key metrics (pricing, features) over time
- [ ] When major competitor change detected, file a GitHub issue + notify via Telegram

---

### 17. Customer Agent (`customer_agent.py`)
**Upgrades needed:**
- [ ] Log questions + answers to `customer_qa_log.json` for training data
- [ ] Expose as webhook endpoint (e.g. via Telegram command `/ask <question>`)

---

### 18. Demo Agent (`demo_agent.py`)
**Upgrades needed:**
- [ ] Auto-register demo tenant in followup_tracker after provisioning
- [ ] Add cleanup command: `--expire <tenant_id>` to delete demo tenants after 14 days

---

### 19. Security Questionnaire Agent (`security_questionnaire_agent.py`)
**Upgrades needed:**
- [ ] Log completed questionnaires to `questionnaire_log.json` (date, company, output path)
- [ ] Add `--company-profile` command to update hardcoded company facts without editing code

---

## Cross-Agent Issues (affect all agents)

| Issue | Impact | Fix |
|-------|--------|-----|
| No unified audit trail | Can't see what agent did what, when | Add `agents/agent_activity_log.jsonl` — each agent appends one line per run |
| Wrong GitHub repo default in ops_agent | ops_agent.py defaults to `GHOSTCODERRRRAHAHA/edongov` on local runs | Fix line 33 in ops_agent.py to `EDONGOV/EDON` |
| No error propagation to chief-of-staff | Brief incomplete, no warning | Each agent writes a `{name}_status.json` with last_run, success, error |
| Manual review bottleneck | Most agents produce drafts, not actions | Add `--auto-send` / `--auto-pr` flags per agent, default off |
| No feedback loops | Insights pile up without being acted on | Code agent picks up tagged JSON files from other agents as task inputs |

---

## Quick Wins (do in one session)

These are small, high-ROI changes that take <1 hour each:

1. **Fix wrong GITHUB_REPO default in ops_agent** → `ops_agent.py` line 33 defaults to `GHOSTCODERRRRAHAHA/edongov`, should be `EDONGOV/EDON`
2. ~~**Add `--dry-run` to docs_agent**~~ ✅ Done — `python -m agents.docs_agent --dry-run` prints unified diff, no file written
3. ~~**Add `am_memory/` auto-registration to onboarding_agent**~~ ✅ Done — writes `am_memory/{tenant_id}.json` on every new onboarding
4. ~~**Upgrade regulatory_watcher + qa_agent to `claude-sonnet-4-6`**~~ ✅ Done — both upgraded from haiku
5. ~~**Add deduplication to incident_agent**~~ ✅ Done — checks open "incident" issues before filing; adds comment on recurrence instead

---

## Done Checklist

Track completions here as upgrades are implemented.

- [ ] Onboarding Agent — silent failure fix
- [ ] Docs Agent — safe section patching
- [ ] Code Agent — Claude Code harness
- [ ] Incident Agent — memory + dedup
- [ ] Regulatory Watcher — closed loop with code_agent
- [ ] QA Agent — fixture file + sonnet upgrade
- [ ] Follow-up Agent — SMTP integration
- [ ] Account Manager — trigger-based sends
- [ ] Ops Agent — issue dedup + smarter code debt
- [ ] Integration Agent — syntax check + auto-PR
- [ ] Security Monitor — quarantine action
- [ ] Chief of Staff — fallbacks + daily diff
- [ ] Outbound Agent — followup integration
- [ ] Content Agent — auto-PR
- [ ] Product Intelligence — upsell → AM feed
- [ ] Competitor Monitor — trend tracking
- [ ] Customer Agent — Q&A logging
- [ ] Demo Agent — followup registration + cleanup
- [ ] Security Questionnaire — audit log
