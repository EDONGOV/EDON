# EDON Agent Team

AI agents that handle ongoing team responsibilities. Each agent runs through the EDON gateway — dogfooding governance on the team that builds it.

## Agents

### QA Agent (`qa_agent.py`)
**Schedule:** Nightly, 3am UTC  
**Workflow:** `nightly_qa.yml`

Fires a test payload for every rule in `CLINICAL_SAFETY_RULES`, verifies the expected verdict (BLOCK/ESCALATE) comes back from the live gateway, then uses Claude Haiku to write a plain-English analysis. Opens a GitHub issue automatically if any rules regress.

```bash
EDON_API_TOKEN=xxx EDON_GATEWAY_URL=https://edon-gateway.fly.dev \
ANTHROPIC_API_KEY=xxx python -m agents.qa_agent
```

---

### Docs Agent (`docs_agent.py`)
**Trigger:** Push to master touching `backend/edon_gateway/**`  
**Workflow:** `docs_agent.yml`

Reads the git diff, identifies route or rule changes, and rewrites the stale sections of `docs/api-reference.md`. Opens a PR with the changes — you review and merge.

```bash
git diff HEAD~1 HEAD -- 'backend/edon_gateway/**' | \
ANTHROPIC_API_KEY=xxx python -m agents.docs_agent
```

---

### Customer Agent (`customer_agent.py`)
**Trigger:** Manual (pipe a question in, get a draft back)

Loads the full API reference, clinical safety rules, governance model, and onboarding guide as context. Drafts a precise answer to a prospect or customer question. You review and send.

```bash
echo '{"question": "Does EDON cover 21 CFR Part 11?", "context": "We build LIMS software"}' \
  | ANTHROPIC_API_KEY=xxx python -m agents.customer_agent

# Or directly:
ANTHROPIC_API_KEY=xxx python -m agents.customer_agent --ask "How does HIPAA-001 work?"
```

---

### Regulatory Watcher (`regulatory_watcher.py`)
**Schedule:** Weekly, Monday 6am UTC  
**Workflow:** `regulatory_watcher.yml`

Fetches recent Federal Register publications from HHS, FDA, and DEA. Uses Claude Haiku to check whether any updates affect EDON's current rule coverage. Opens a GitHub issue if a potential gap is found.

```bash
ANTHROPIC_API_KEY=xxx GITHUB_TOKEN=xxx python -m agents.regulatory_watcher
```

---

### Onboarding Agent (`onboarding_agent.py`)
**Trigger:** Manual (run when a new customer is ready to provision)

Provisions a new tenant (API key, clinical safety rules, compliance health check), then generates a personalised welcome brief. You review the brief and send it to the customer.

```bash
echo '{
  "name": "Acme Health",
  "email": "cto@acme.com",
  "regulations": ["HIPAA", "HITECH"],
  "use_case": "Clinical AI assistant for EHR workflows",
  "plan": "enterprise"
}' | ANTHROPIC_API_TOKEN=xxx EDON_API_TOKEN=xxx \
    EDON_BOOTSTRAP_SECRET=xxx python -m agents.onboarding_agent
```

---

---

### Ops Agent (`ops_agent.py`)
**Schedule:** Daily, 7am UTC — ready when you start work  
**Workflow:** `ops_agent.yml`

Your CTO-in-residence. Monitors everything in one pass: gateway health (latency SLO, DB, policy engine, CAV), security posture, compliance gaps, CI pass/fail, open GitHub issues, code debt (TODOs/FIXMEs, large files, unpinned deps), and business metrics (decision volume trends, block rates, agent fleet health). Uses Claude Opus to reason about what actually matters vs noise, prioritises by business impact, and suggests a specific fix for each pain point. Automatically opens GitHub issues for anything critical or high severity. Exits with code 1 if critical issues are found (so CI can alert you).

```bash
ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx GITHUB_TOKEN=xxx python -m agents.ops_agent
```

---

### Account Manager (`account_manager.py`)
**Schedule:** Weekly, Monday 8am UTC  
**Workflow:** `account_manager.yml`

One AM per client. Each client has a memory file in `agents/am_memory/{tenant_id}.json` that persists observations week-over-week — health scores, open items, relationship notes. Every Monday the AM pulls live data (decision volume trend, compliance health, agent fleet), assesses health, and drafts a proactive email if something needs attention. You get a single weekly report with all draft emails ready to review and send.

```bash
# Add a new client after onboarding
python -m agents.account_manager --new '{
  "tenant_id": "tenant_acme",
  "company_name": "Acme Health",
  "contact_name": "John Smith",
  "contact_email": "cto@acme.com",
  "regulations": ["HIPAA", "HITECH"],
  "use_case": "Clinical AI assistant"
}'

# Run review for all clients
ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.account_manager --all

# Run for one client
ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.account_manager --tenant tenant_acme

# See all clients and their health scores
python -m agents.account_manager --list
```

**Memory files** live in `agents/am_memory/` — commit them to the repo so history persists across CI runs. They contain no secrets, just usage observations and relationship notes.

---

---

### Security Questionnaire Agent (`security_questionnaire_agent.py`)
**Trigger:** Manual — run when a prospect sends a vendor assessment  
Loads your full security posture (threat model, auth methods, network isolation, backup procedures, HIPAA compliance, architecture) and answers every question with Claude Opus. Handles .txt, .json, and .csv formats. Outputs a completed markdown document ready to send. Each questionnaire takes seconds instead of 8-40 hours.

```bash
ANTHROPIC_API_KEY=xxx python -m agents.security_questionnaire_agent \
  --input questionnaire.txt --company "Acme Health" --output completed.md
```

---

### Outbound Agent (`outbound_agent.py`)
**Trigger:** Manual — run when you want to work a prospect list  
Takes a list of target companies, researches each one using web search (recent AI initiatives, HIPAA incidents, funding, job postings), then drafts a cold email so specific it could only have been written for that company. Drafts saved to `agents/outbound_drafts/`. You review and send.

```bash
# Single company
ANTHROPIC_API_KEY=xxx python -m agents.outbound_agent \
  --company "Memorial Health System" --website "memorialhealth.com"

# From a list
ANTHROPIC_API_KEY=xxx python -m agents.outbound_agent --input prospects.json
```

---

### Demo Environment Agent (`demo_agent.py`)
**Trigger:** Manual — run when a prospect wants a POC  
Provisions a demo tenant, applies the right policy pack (hospital/clinical_saas/medical_device), activates clinical safety mode, seeds realistic sample decisions, and generates a personalised demo guide. Turns a 2-week POC setup into same-day credentials.

```bash
echo '{"company": "Acme Health", "use_case": "Clinical AI for EHR", "regulations": ["HIPAA"], "industry": "hospital"}' \
  | ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx EDON_BOOTSTRAP_SECRET=xxx python -m agents.demo_agent
```

---

### Content Agent (`content_agent.py`)
**Schedule:** Weekly, Tuesday 9am UTC  
**Workflow:** `content_agent.yml`  
Picks the next topic from a curated queue in `agents/content_topics.json`, researches using web search, and writes a 1000-1500 word technical blog post targeting healthtech AI compliance keywords. Opens a PR to `content/blog/`. You review regulation citations and merge.

```bash
# Write next post in queue
ANTHROPIC_API_KEY=xxx python -m agents.content_agent

# Write on a specific topic
ANTHROPIC_API_KEY=xxx python -m agents.content_agent \
  --topic "How HIPAA-001 protects against bulk PHI export by AI agents"

# See what's in the queue
python -m agents.content_agent --list
```

---

## Required Secrets (GitHub Actions)

| Secret | Used by |
|--------|---------|
| `ANTHROPIC_API_KEY` | All agents |
| `EDON_API_TOKEN` | QA, Onboarding |
| `EDON_GATEWAY_URL` | QA, Onboarding |
| `EDON_BOOTSTRAP_SECRET` | Onboarding |
| `EDON_QA_TENANT_ID` | QA (optional, defaults to `tenant_dev`) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions.
