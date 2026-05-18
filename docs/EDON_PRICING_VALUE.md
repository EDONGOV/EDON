# EDON Pricing & Value Architecture

> Last updated: 2026-04-16

---

## The Market Reality

Large enterprises are not price-sensitive on security — they are **proof-sensitive**.

A CISO managing a $15M/year security budget is not asking "can we afford $3M for EDON?"
They are asking: **"Can I defend this purchase to the board if something goes wrong?"**

That is the only question your pricing and positioning must answer.

---

## What They're Already Spending

| Segment | Total Security Budget/Year | As % of IT Budget |
|---|---|---|
| Regional hospital system | $10M – $20M | 10–15% |
| Large bank / financial institution | $20M – $100M+ | 12–20% |
| Series C–D AI-native company | $2M – $8M | 8–15% |
| Enterprise SaaS (1000+ employees) | $5M – $15M | 8–12% |

**How that budget breaks down internally:**
- 40% → platforms and software
- 30% → security personnel
- 15% → hardware / infrastructure
- 15% → services (pentests, consulting, compliance audits)

The 15% services bucket — pentests, red teams, compliance work — is where EDON enters.
Then it expands into the 40% platforms bucket as you replace fragmented tools.

---

## The Fragmentation Problem (Your Opening)

A typical enterprise security stack looks like this:

| Tool | Annual Cost |
|---|---|
| SIEM (Splunk, Sentinel) | $30K – $500K |
| IAM platform | $5–20/user/month |
| Cloud security (Wiz, Orca) | $20K – $200K |
| Managed SOC | $120K – $600K |
| Penetration testing (periodic) | $20K – $100K per engagement |
| Compliance tooling (HIPAA, SOC2) | $50K – $300K |
| Red team / adversarial testing | $50K – $200K/year |

**Total fragmented stack: $500K – $2M+ per year**

None of these tools:
- Prove exploits against their specific system continuously
- Quantify risk in financial terms ($)
- Control or govern AI agent behavior
- Connect finding → impact → fix in a single workflow

This is not a gap they've papered over. It's a structural hole.

---

## EDON Pricing Tiers

### Tier 1 — Proof Engagement (Entry)
**$50K – $200K**

- Duration: 7–30 days
- Deliverable: signed report of real exploit paths + dollar impact
- What runs: Impact engine, Proof output
- Conversion goal: 100% → Tier 2

This is not a free trial. Charging here pre-qualifies the buyer and frames the expansion as a step up, not a cliff.

---

### Tier 2 — Continuous Risk Intelligence
**$250K – $750K / year**

- Continuous shadow monitoring
- Weekly risk reports with $ impact deltas
- Exploit path tracking (not remediation yet)
- Covers: 1 core system or product line
- Value anchor: replaces periodic pentesting + red team engagement costs

**Gross margin at this tier: ~85–90%**
(COGS: ~$30K–$60K infra + API per customer/year)

---

### Tier 3 — Governance + Prevention
**$1M – $3M / year**

- Real-time Gateway enforcement (observe → enforce)
- CREAO assisted remediation
- Audit trail + compliance layer (SOC2, HIPAA, emerging AI regs)
- AI agent behavioral controls
- Multi-system coverage

At this tier EDON is no longer a security vendor.
It is infrastructure. Switching cost becomes extremely high.

**Gross margin at this tier: ~90–95%**
(COGS scales slowly — infra adds ~$50K–$100K per customer regardless of contract size)

---

### Tier 4 — Enterprise Platform
**$3M – $10M / year**

- Full platform across all AI systems
- Dedicated governance policies per business unit
- Executive risk dashboard (CFO/CISO/CTO visibility)
- Custom SLAs + incident response integration
- Annual proof report for board / regulators

**This tier is sold to CFO and board, not security teams.**
The frame is: *operational risk management*, not cybersecurity.

**Gross margin at this tier: ~93–96%**

---

## The Buyer Math (How They Justify It Internally)

### For a bank spending $30M/year on security:

```
Current spend:     $30M/year
Known gap:         No continuous AI governance, no real-time exploit validation
Average breach:    $4M–$10M+ direct cost + regulatory fines
                   $50M–$500M reputational / stock impact for a major incident

EDON at $3M/year:
→ 10% of security budget
→ Justified by preventing ONE mid-tier incident
→ CFO math: $3M spend vs. $10M+ expected breach cost = obvious ROI
```

### For a Series C AI-native company (50–200 agents in prod):

```
Current spend:     $3M/year on security
AI risk exposure:  Unquantified — this is the lever
Regulatory trend:  EU AI Act, SEC AI disclosure requirements incoming

EDON at $500K/year:
→ 17% of security budget (high, but they're getting a new category)
→ Justified as: "We now know what our AI systems can actually do to us"
→ CTO math: one agent going rogue costs more than $500K in headlines alone
```

---

## Positioning Against the Stack

| Competitor | What they do | Why EDON wins |
|---|---|---|
| Wiz / Orca / Prisma | Cloud misconfiguration scanning | Static findings, no AI behavior, no $ impact |
| Crowdstrike / SentinelOne | Endpoint / threat detection | Reactive, not predictive, no AI governance |
| Pentesting firms (NCC, Bishop Fox) | Periodic manual testing | Expensive, slow, no continuity |
| Anthropic / OpenAI safety tools | Model-level safety | Not system-level, no financial quantification |
| **EDON** | **Continuous AI system governance + exploit validation + $ impact** | **This category does not exist yet** |

The correct frame is not "we're better than X."
It is: **"None of these tools do what we do. They are not substitutes."**

---

## Expansion Logic (Why Deals Grow)

The natural expansion path per customer:

```
Year 1:  $50K proof engagement
         ↓ (convert 100%)
Year 1:  $250K continuous monitoring contract
         ↓ (convert 70%)
Year 2:  $1M governance + prevention
         ↓ (convert 50%)
Year 3:  $3M–$5M enterprise platform
```

A single customer that enters at $50K can become a $3M–$5M account in 24 months.
You need 25 of those. Not 25 independent deals — 25 accounts in expansion motion.

---

## Revenue & Margin Model (Realistic)

| Milestone | Customers | Avg ACV | ARR | Est. Gross Margin |
|---|---|---|---|---|
| Month 3 | 3–5 pilots converted | $200K | $600K–$1M | ~85% |
| Month 9 | 10 customers | $500K | $5M | ~88% |
| Month 18 | 20 customers | $1.5M | $30M | ~91% |
| Month 30 | 30 customers | $3M+ | $90M+ | ~93% |

**Operating costs (solo founder + AI agents as team):**
- LLM API costs: $50K–$200K/year at $30M ARR scale
- Cloud infra: $100K–$400K/year
- Legal / compliance: $50K–$150K/year
- Sales / travel: $100K–$300K/year
- Tools / misc: $25K–$50K/year

**Net margin at $30M ARR: ~75–85%** (before any hiring)

This is a fundamentally different cost structure than any traditional security company.
The leverage is extreme because your "delivery team" is AI.

---

## The One Number That Matters

**Average breach cost in 2025: $4.88M** (IBM Cost of a Data Breach Report)
**For AI-specific incidents: 2–5x multiplier expected by 2027**

Every enterprise contract you close is priced below the cost of one incident.
That is your close argument. It is also your renewal argument. It never changes.

---

## What to Avoid in Pricing Conversations

1. **Never lead with features.** Lead with the dollar figure you found in their system.
2. **Never discount below Tier 1 ($50K).** Free pilots attract tire-kickers, not buyers.
3. **Never quote a flat annual price without usage-based upside.** LLM costs scale with their agent footprint — build that in.
4. **Never sell to the security team alone.** The CISO approves. The CFO and CTO write the check.
5. **Never position against specific tools.** You are a new category. Comparisons shrink you.
