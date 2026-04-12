# EDON Enterprise Readiness Checklist
## Everything needed to pass banking & healthcare vendor approval

Last updated: 2026-04-11

---

## HOW TO USE THIS FILE

Each item is either:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — done

Work left to right: **Security → Legal → Compliance → Sales**.
Do not start large bank or health system conversations without at least the Security and Legal columns complete.

---

## SECTION 1 — SECURITY ARCHITECTURE

> Required for: every enterprise deal. First thing any security team asks for.

### 1A. Documentation
- [ ] Network architecture diagram (how EDON connects to customer systems)
- [ ] Data flow diagram — what data enters EDON, where it goes, what is stored
- [ ] API integration spec (inbound vs outbound, protocols, ports)
- [ ] Encryption spec — TLS versions, at-rest encryption algorithm, key management
- [ ] Authentication spec — how customer tokens/keys are issued, rotated, revoked
- [ ] Secret management documentation (how API keys, DB credentials are stored — not in code)
- [ ] Logging and monitoring spec — what is logged, where, retention period
- [ ] Incident response plan — steps taken when a breach occurs, who is notified, in what timeframe

### 1B. Architecture answers to have ready
- [ ] Does EDON require inbound network access to customer systems? (Answer: No — gateway model)
- [ ] Does EDON store customer PII or transaction data? (Define exactly what is and is not stored)
- [ ] Can EDON be deployed in a customer's own cloud (VPC isolation)? (Yes/No + how)
- [ ] Can EDON be deployed on-premises? (Yes/No + roadmap)
- [ ] What happens if EDON goes down — does it fail open or fail closed? (Document default behavior)
- [ ] What is the blast radius if EDON is compromised? (Answer should be: governance metadata only)
- [ ] Is EDON in the critical path of transactions? (Answer: no — async governance layer)

### 1C. Certifications and tests — must have before first enterprise conversation
- [ ] **SOC 2 Type II** — hire auditor, complete 6-month observation period, receive report
  - Scope: Security, Availability, Confidentiality trust service criteria
  - Estimated cost: $15,000–$40,000
  - Timeline: 6–9 months from start
- [ ] **Penetration test** — third-party pentest of gateway API, admin console, shadow execution
  - Hire: NCC Group, Bishop Fox, Cobalt, or similar
  - Must cover: API auth, rate limiting, injection, privilege escalation, token handling
  - Estimated cost: $10,000–$25,000
  - Re-run annually
- [ ] **Vulnerability disclosure policy** — public page explaining how researchers report issues
- [ ] **ISO 27001** (optional for first deals, required for global banks / NHS in UK)

---

## SECTION 2 — VENDOR RISK MANAGEMENT (TPRM)

> Required for: all banks, all health systems > $500M revenue.
> You will receive a questionnaire. These are the answers to prepare.

### 2A. Company information package
- [ ] Company registration documents (articles of incorporation)
- [ ] Ownership structure — who owns EDON, any foreign ownership disclosure
- [ ] Financial stability documentation — last 12 months bank statements or funding evidence
- [ ] Key person risk statement — what happens to the product if founder leaves
- [ ] D&O insurance certificate
- [ ] Cyber liability insurance certificate (minimum $5M coverage — banks often require $10M)
- [ ] Errors & omissions insurance certificate

### 2B. Employee and operations
- [ ] Background check policy — confirm all employees undergo background checks
- [ ] Security training program — annual security awareness training documented
- [ ] Acceptable use policy (internal)
- [ ] Access control policy — who at EDON can access customer data and under what conditions
- [ ] Offboarding process — how access is revoked when employees leave

### 2C. Business continuity
- [ ] Business continuity plan (BCP) — how EDON continues operating if disaster strikes
- [ ] Disaster recovery plan (DRP) — RTO and RPO targets, tested annually
- [ ] Data backup policy — frequency, location, encryption, testing
- [ ] Uptime SLA documentation — 99.9% or 99.95% with penalties defined

### 2D. Subprocessors
- [ ] Complete list of all subprocessors (Fly.io, Anthropic API, Postgres provider, etc.)
- [ ] Contracts with each subprocessor confirming their data protection obligations
- [ ] Right to audit subprocessors (required by many enterprise contracts)

---

## SECTION 3 — LEGAL DOCUMENTS

> Required for: every deal. Negotiate these in advance so you are not starting from scratch.

### 3A. Core contracts to have drafted (hire a startup-specialized attorney)
- [ ] **Master Service Agreement (MSA)** — governing contract for all services
- [ ] **Data Processing Agreement (DPA)** — GDPR/CCPA compliant, covers customer data processing
- [ ] **Service Level Agreement (SLA)** — uptime guarantees, support response times, penalties
- [ ] **Order Form template** — deal-specific terms attached to the MSA

### 3B. Key clauses to pre-negotiate your position on
- [ ] **Liability cap** — standard: capped at 12 months of fees paid. Banks will push for uncapped. Hold at 12–24 months.
- [ ] **Indemnification** — you indemnify customer for IP infringement and data breaches caused by your negligence. Do not accept unlimited indemnification.
- [ ] **Data ownership** — customer owns their data. You own aggregate/anonymized insights. State this explicitly.
- [ ] **Breach notification timeline** — commit to 72 hours (GDPR standard). Banks may want 24 hours. 48 hours is reasonable.
- [ ] **Audit rights** — customer can audit EDON's security controls once per year with 30 days notice. Do not allow unlimited unannounced audits.
- [ ] **Termination for convenience** — 30–60 day notice. Avoid 90+ day lock-in demands.
- [ ] **Data return and deletion** — customer data returned or deleted within 30 days of contract end.
- [ ] **Governing law** — negotiate for your state. Banks will want NY. Healthcare will want state of incorporation.
- [ ] **Source code escrow** (large deals only) — if EDON ceases to operate, customer gets source code. Use a third-party escrow service.

### 3C. Healthcare-specific legal
- [ ] **Business Associate Agreement (BAA)** — required before any HIPAA-covered entity can use EDON
  - Must cover: permitted uses of PHI, safeguards required, breach notification, subcontractor obligations
  - Hire a HIPAA-specialized attorney to draft
  - Have it ready before any demo involving real patient workflows
- [ ] **FDA SaMD classification review** — get a legal opinion on whether EDON qualifies as Software as a Medical Device under 21 CFR Part 11
  - If EDON's decisions can influence clinical action (block, escalate), FDA may apply
  - Most likely path: argue EDON is administrative governance, not clinical decision support
  - Get written legal opinion before hospital conversations

---

## SECTION 4 — COMPLIANCE & REGULATORY

### 4A. Banking-specific compliance readiness
- [ ] **Model Risk Management (SR 11-7)** — prepare documentation showing EDON is not a "model" under Fed guidance, or if it is, provide model documentation (purpose, methodology, limitations, validation)
  - Banks' model risk management teams will classify EDON as a model if it makes risk-influencing decisions
  - Prepare: model purpose statement, input/output description, known limitations, back-testing approach
- [ ] **SOX Section 302/404 alignment** — document how EDON's audit trail supports SOX internal controls requirements
  - Immutable log, tamper-evident, accessible for auditors
  - Demonstrate 7-year retention capability (SEC requirement)
- [ ] **BSA/AML documentation** — how EDON supports AML compliance without replacing the bank's BSA officer
  - EDON governs AI agents, does not replace human compliance decisions
  - SAR and CTR decisions remain with licensed BSA officers
- [ ] **FINRA compliance statement** — if any EDON deployment touches broker-dealer operations, document Rule 17a-4 compliance (record retention)
- [ ] **OCC, Fed, FDIC examiner readiness** — prepare a one-page "EDON for Examiners" brief
  - What EDON does, what it does not do, how it supports safe AI deployment
  - Examiners will find it during third-party reviews — give banks the document they need to hand over
- [ ] **Concentration risk statement** — explain multi-tenancy isolation. One bank's governance rules cannot affect another's.

### 4B. Healthcare-specific compliance readiness
- [ ] **HIPAA Security Rule alignment** — document how EDON meets Technical Safeguards (§164.312)
  - Access controls, audit controls, integrity, transmission security
- [ ] **HIPAA Privacy Rule statement** — what EDON processes vs what it never touches (PHI vs governance metadata)
- [ ] **HITECH Act alignment** — breach notification, enhanced penalties, BAA requirements
- [ ] **21st Century Cures Act** — information blocking provisions. EDON must not create information blocking scenarios.
- [ ] **Epic/Cerner third-party policy** — check if target hospital is on Epic/Cerner. If so:
  - Epic: apply to the App Orchard program
  - Cerner: apply to the Open Developer Experience (CODE) program
  - Do not attempt to deploy alongside these EHR systems without their formal partner approval
- [ ] **Joint Commission statement** — if hospital is Joint Commission accredited, frame EDON as supporting their patient safety standards

### 4C. General privacy compliance
- [ ] **GDPR compliance** — if any EU customers or EU data subjects (required for UK/EU banks)
  - Data Processing Agreement
  - Data Subject Rights process (access, deletion, portability)
  - Privacy Impact Assessment template
- [ ] **CCPA/CPRA compliance** — if any California customers or California residents' data
- [ ] **Privacy policy** — public-facing, plain language, covers all data collected

---

## SECTION 5 — SECURITY CERTIFICATIONS TIMELINE

> Plan this now. SOC 2 alone takes 6–9 months. Start immediately.

| Certification | Priority | Timeline | Estimated Cost | Who to Hire |
|---|---|---|---|---|
| SOC 2 Type II | Critical — needed for every deal | 6–9 months | $15–40k | Drata/Vanta for prep + auditor |
| Penetration Test | Critical — needed before pilot | 4–8 weeks | $10–25k | NCC Group, Bishop Fox, Cobalt |
| ISO 27001 | High — needed for global banks | 6–12 months | $20–50k | After SOC 2 |
| HIPAA Attestation | Required for healthcare | 4–8 weeks | $5–15k | Healthcare compliance firm |
| FedRAMP (future) | If selling to government banks | 12–24 months | $500k+ | Only if government becomes a target |

**Shortcut**: Use **Vanta** or **Drata** as your compliance automation platform. They reduce SOC 2 prep from months of manual work to 6–8 weeks of automated evidence collection. Cost: ~$10–15k/year. Do this first.

---

## SECTION 6 — PILOT PROGRAM DESIGN

> Banks and hospitals will not buy without a pilot. Design it before they ask.

### 6A. Standard pilot structure to offer
- **Duration**: 60 days
- **Mode**: Shadow mode only — observe, zero enforcement, zero blast radius
- **Scope**: 1–3 AI agent systems, single business unit
- **Data access**: governance metadata only, no customer PII required
- **Success metrics defined upfront**:
  - Number of policy violations detected
  - Decision latency (target: <10ms)
  - Uptime (target: 99.9%)
  - False positive rate on blocked actions
  - Compliance events surfaced that were previously invisible

### 6B. Pilot deliverables to produce for customer
- [ ] Weekly governance report (PDF, auto-generated)
- [ ] Final pilot readout deck — what was found, what would have been blocked, ROI estimate
- [ ] Compliance gap analysis — regulations they were not meeting that EDON would enforce
- [ ] Reference architecture diagram showing full deployment path

### 6C. Pilot pricing
- [ ] Decide pilot pricing strategy: free, discounted, or cost-applied-to-contract
- [ ] Recommended: free 60-day pilot, full contract value applies if they proceed
- [ ] Have signed pilot agreement (lighter weight than full MSA) ready

---

## SECTION 7 — OPERATIONAL RISK ANSWERS

> Banks and hospitals have operational risk teams that ask "what if this breaks?"

Prepare answers to every question below:

- [ ] **What is EDON's failure mode?** — does it fail open (allow all) or fail closed (block all)?
  - Recommended answer: configurable per customer. Default: fail open with alert. Clinical safety / trading desks: fail closed option.
- [ ] **What is the RTO (Recovery Time Objective)?** — how fast do you recover from an outage?
  - Target: 15 minutes for gateway restore, 4 hours for full functionality
- [ ] **What is the RPO (Recovery Point Objective)?** — how much data can you lose?
  - Target: 1 hour maximum data loss
- [ ] **Single point of failure analysis** — what are EDON's SPOFs and how are they mitigated?
  - Database: multi-region replication
  - Gateway: multiple instances behind load balancer
  - Audit log: replicated to secondary storage
- [ ] **Runbook documentation** — step-by-step procedures for common failure scenarios
- [ ] **On-call rotation** — who is on call, what is the escalation path, what is the response SLA?
- [ ] **Change management process** — how are software updates deployed, tested, and rolled back?

---

## SECTION 8 — DATA PRIVACY ANSWERS

> Every enterprise will ask these. Have written answers ready.

- [ ] Where is customer data stored? (Region, cloud provider, specific services)
- [ ] Is data stored in the same region as the customer's operations? (Data residency)
- [ ] What data does EDON store vs what is discarded immediately?
  - EDON stores: agent ID, action type, verdict, timestamp, policy version, risk score
  - EDON does NOT store: customer PII, transaction amounts, account numbers (unless governance metadata requires it — define this precisely)
- [ ] How long is data retained? (Default retention policy)
- [ ] How is data encrypted at rest? (AES-256)
- [ ] How is data encrypted in transit? (TLS 1.2 minimum, TLS 1.3 recommended)
- [ ] Who at EDON can access customer data? (List roles and access controls)
- [ ] Under what circumstances would EDON employees access customer data? (Support investigations only, with audit trail)
- [ ] Can customers export their data? (Yes — full audit log export, JSON/CSV)
- [ ] Can customers delete their data? (Yes — define process and timeline)
- [ ] Is data used to train models? (If yes, be explicit. If no, state it plainly in writing.)

---

## SECTION 9 — TECHNOLOGY GOVERNANCE BOARD PACKAGE

> Large banks have an internal committee that decides if a vendor is allowed company-wide.
> You need a "vendor maturity" package to present to them.

- [ ] Company founding date and employee count
- [ ] Architecture overview — cloud-native, multi-tenant, API-first
- [ ] Technology stack documentation (what languages, frameworks, cloud services)
- [ ] Roadmap — 12-month product roadmap showing long-term investment
- [ ] Support tiers — what SLA does each tier get, who is the named support contact
- [ ] Escalation path — from L1 support to engineering to founder
- [ ] Long-term viability statement — funding runway, revenue, growth

---

## SECTION 10 — EXECUTIVE APPROVAL PACKAGE

> For deals > $500k, CISO, CIO, or CTO must sign off. Prepare one-pagers for each.

### For the CISO
- One-pager: "How EDON reduces AI security risk"
  - Threat: uncontrolled AI agents executing unauthorized actions
  - EDON's answer: policy enforcement layer between AI and tools
  - Evidence: SOC 2, pentest, encryption standards
  - Key stat: average decision latency < 10ms — no performance cost

### For the CIO
- One-pager: "EDON integration and deployment"
  - Single API endpoint, no infrastructure to manage
  - Deploys alongside existing AI stacks, no replacement required
  - Supported deployment models: cloud, VPC, future on-prem
  - Uptime SLA: 99.95%

### For the CFO / Procurement
- One-pager: "EDON ROI case"
  - Average regulatory fine avoided (cite real fines: $920M HSBC AML, $1B JPMorgan trader)
  - Compliance headcount saved (each escalated event handled automatically)
  - Incident response cost avoided
  - Pricing model: per-agent or per-decision, predictable and auditable

### For the Chief Compliance Officer (banks and hospitals)
- One-pager: "How EDON supports your compliance program"
  - Banking: BSA/AML, SOX, FINRA, SR 11-7
  - Healthcare: HIPAA, HITECH, Joint Commission
  - Immutable audit trail ready for regulators and examiners
  - Human review queue — compliance team is always in the loop

---

## SECTION 11 — FIRST DEAL STRATEGY (SKIP THE 9-MONTH PROCESS)

> The fastest path to a first bank or hospital contract.

### Step 1 — Target the right institution size
- **Banks**: $2–15B in assets (community/regional banks). Examples: Glacier Bancorp, S&T Bancorp, Renasant Bank.
  - Their procurement is 60–70% lighter than JPM
  - CISO and CIO are often the same conversation
  - Timeline: 6–10 weeks instead of 6–9 months
- **Healthcare**: $500M–$2B revenue health systems. Examples: regional hospital systems, not Mayo Clinic or HCA.
  - CMIO often makes the decision with limited committee overhead
  - No Epic App Orchard required at this scale

### Step 2 — Enter through the CISO or Chief Compliance Officer, not IT
- IT says "not now, we have a backlog"
- CISO says "show me what you found" (shadow mode pitch)
- CCO says "can you help me answer the examiners?" (regulatory pitch)

### Step 3 — Offer shadow mode as the entry point
- No enforcement, no blast radius, no change management
- "Let us watch your AI systems for 60 days and tell you what we find"
- Frame it: you are giving them free intelligence, not asking for trust

### Step 4 — Use the pilot readout to sell the full contract
- Show them specific events EDON would have caught
- Show the regulatory exposure they currently have
- Make the ROI undeniable before the full procurement process starts

### Step 5 — Use first customer to unlock second tier
- Pursue JPM, Goldman, BofA, HCA, or similar only after:
  - SOC 2 Type II in hand
  - One live reference customer
  - Pentest completed
  - Legal templates battle-tested
- The first customer's name opens every door. Protect that relationship.

---

## MASTER CHECKLIST SUMMARY

| Category | Status | Blocker? |
|---|---|---|
| SOC 2 Type II | [ ] Not started | YES — required for every deal |
| Penetration test | [ ] Not started | YES — required before pilot |
| MSA + DPA drafted | [ ] Not started | YES — needed before LOI |
| BAA drafted (healthcare) | [ ] Not started | YES — healthcare only |
| Cyber liability insurance | [ ] Not started | YES — required for TPRM |
| Data flow diagram | [ ] Not started | YES — security review |
| Network architecture diagram | [ ] Not started | YES — security review |
| Incident response plan | [ ] Not started | YES — security review |
| Business continuity plan | [ ] Not started | YES — TPRM |
| Subprocessor list | [ ] Not started | YES — TPRM |
| CISO one-pager | [ ] Not started | High |
| CIO one-pager | [ ] Not started | High |
| CCO one-pager | [ ] Not started | High |
| Pilot program design | [ ] Not started | High |
| SR 11-7 model documentation | [ ] Not started | Banking only |
| Epic/Cerner partner application | [ ] Not started | Healthcare only |
| FDA SaMD legal opinion | [ ] Not started | Healthcare only |
| GDPR DPA | [ ] Not started | EU deals only |
| ISO 27001 | [ ] Not started | Global banks only |
| Examiner brief ("EDON for Regulators") | [ ] Not started | Banking priority |

---

*This file lives at the root of the EDON repo. Update status as items complete.*
*Owner: review quarterly or before each new enterprise conversation.*
