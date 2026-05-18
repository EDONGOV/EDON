# EDON Client Onboarding — Everything We Need

Use this to run a new client from first call to fully governed in one session.
Fill out each section before or during the kickoff call.

---

## 1. The Client (5 min)

| Question | Answer |
|----------|--------|
| Company name | |
| Industry / vertical | |
| Primary contact name + email | |
| Who reviews escalations (could be same person) | |
| Who is the technical owner (engineer who'll integrate the SDK) | |

**Why this matters:** Determines which regulations apply, who gets compliance reports, and who approves escalated agent actions.

---

## 2. Their Agents (this is the core — spend the most time here)

For each AI agent they run, we need:

| Field | Example | Their Answer |
|-------|---------|--------------|
| Agent name | `billing-processor` | |
| What it does (one sentence) | Reads invoices and submits payments | |
| What data does it touch | Customer PII, bank account numbers | |
| What tools/APIs does it call | Stripe API, internal DB, email | |
| Risk level (their gut feel) | High / Medium / Low | |
| Department | Finance / Clinical / Engineering | |
| Is it a vendor agent or built in-house | Vendor: OpenAI Assistants / In-house | |

**Ask them:** "Walk me through a typical thing this agent does from start to finish." That usually surfaces the risky operations they haven't thought about.

**Red flags to probe:**
- Agent touches financial data → ask about amount thresholds
- Agent sends emails or messages → ask about who it can contact
- Agent reads patient / health records → HIPAA is mandatory
- Agent writes to production databases → needs shadow mode first
- Agent can call external APIs → scope violation risk is high

---

## 3. Compliance Requirements

| Question | Answer |
|----------|--------|
| HIPAA — do any agents touch patient data? | Yes / No |
| SOC 2 — are you SOC 2 certified or pursuing it? | Yes / No / In progress |
| GDPR — do you have EU customers? | Yes / No |
| PCI-DSS — do agents handle card numbers? | Yes / No |
| Internal SLAs — are there hours agents must NOT run? | e.g. no production writes 11pm–6am |
| Audit log retention requirement | e.g. 7 years for HIPAA |
| Who gets the compliance report | CISO / Legal / CTO |

**If HIPAA:** Apply the `hipaa` compliance template on their tenant — this creates PHI access control, breach detection, and minimum necessary access rules automatically.

---

## 4. Risk Tolerance

These answers determine which policy pack to start them on and how aggressive governance should be.

| Question | Answer |
|----------|--------|
| If an agent tries something risky, do you want it **blocked** outright, or **degraded** to a safer version? | Block / Degrade |
| Do you want high-risk actions sent for human review before they execute? | Yes / No |
| What dollar amount of financial action needs human approval? | e.g. > $500 |
| Are there any tools or operations that should ALWAYS be blocked? | e.g. `exec_shell`, `bulk_delete` |
| Are there any that should ALWAYS be allowed regardless of risk? | e.g. `read_public_docs` |
| Shadow mode first (observe without blocking) or enforcement from day one? | Shadow / Enforce |

**Recommendation for new clients:** Start in shadow mode for 48–72 hours so the AI learns their agents' normal behaviour before enforcing. Then flip to enforcement with a policy review.

---

## 5. Technical Integration

| Question | Answer |
|----------|--------|
| SDK language | Python / JavaScript / Both |
| Where does their AI run | Cloud (AWS/GCP/Azure) / On-prem / Fly.io |
| How do agents authenticate to external systems | API keys / OAuth / IAM roles |
| Do they use an AI gateway already (e.g. LiteLLM, Portkey) | Yes / No |
| Preferred environment for install | Dev first / Staging / Prod directly |
| Can they set environment variables in their deployment | Yes / No |

**Minimum to get started:**
```
EDON_API_KEY=<from console.edoncore.com or POST /auth/register>
EDON_GATEWAY_URL=https://edon-gateway-prod.fly.dev   # optional — defaults to production
```

---

## 6. Policy Pack Selection

Based on their answers above, recommend one of these starting packs:

| Template ID | Best for | What it creates |
|-------------|----------|-----------------|
| `hipaa` | Any agent touching patient data | PHI access control, breach detection, minimum necessary access, audit logging |
| `clinical_governance` | Clinical AI (diagnosis, notes, alerts) | PHI minimisation, patient consent checks, clinical scope enforcement |
| `joint_commission` | Accredited hospitals | Clinical decision support oversight, medication order review, patient safety blocks |
| `hitrust` | HITRUST CSF certification | Access control, risk management, incident response, configuration management |
| `soc2` | SaaS / general compliance | Access control, change management, continuous monitoring |

Apply via console or one API call per template:
```
POST /policy/templates/{template_id}/apply
```

For most hospitals: start with `hipaa` + `clinical_governance`. Add `joint_commission` if they are Joint Commission accredited.

---

## 7. First Week Checklist

Walk them through this in order — do not skip steps:

- [ ] **Day 0:** Create tenant in console, assign policy pack
- [ ] **Day 0:** Install SDK (`pip install edon-sdk` or `npm install @edon/sdk`)
- [ ] **Day 0:** Wrap one agent (lowest-risk first) and run in shadow mode
- [ ] **Day 1:** Review the shadow mode audit log together — what would have been blocked?
- [ ] **Day 1:** Register all agents in the console (name, type, department)
- [ ] **Day 2:** Tune any rules that are too aggressive (false positives) or too loose
- [ ] **Day 2:** Set up escalation reviewer in console
- [ ] **Day 3:** Enable enforcement mode on the first agent
- [ ] **Day 5:** Roll out to all agents
- [ ] **Day 7:** First compliance report — review with client

---

## 8. Questions That Always Surface on the Call

**"Do we have to change our agent code?"**
Minimal. Add two calls around each action their agent takes — `client.evaluate()` before it acts, `client.scan_output()` after it gets a result. That's it. EDON never touches their agent or their data directly.

**"What happens if EDON goes down?"**
Fail-open or fail-closed — configurable. Default is fail-open (agent proceeds) with an audit entry flagged for review. Enterprise plans get fail-closed with automatic fallback.

**"Can we see exactly why an action was blocked?"**
Yes — every block has a reason code, plain-English explanation, and the full context in the audit log. The copilot can explain any decision on demand.

**"What about false positives — our agents do unusual things legitimately?"**
Shadow mode first always solves this. After 48 hours of shadow data, we can see the real pattern and tune the rules before any agent gets blocked in production.

**"Can different agents have different rules?"**
Yes — each agent can have a `policy_pack` override. The billing agent can have stricter financial rules while the research agent runs more permissively.

**"Who owns this integration — us or EDON?"**
They own the agents and the data. EDON provides the governance layer. They can export their entire audit log and memories at any time.

---

## Notes from this client's call

_Fill in during/after the call:_

```
Date:
Attended:
Key concerns raised:
Agreed policy pack:
Shadow mode duration:
Go-live target:
Open action items:
```
