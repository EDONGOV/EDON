# EDON Impact — risk discovery & failure-mode simulation

**Audience:** product, sales, security architecture, solutions engineering  
**Status:** target product definition (implementation may be partial; aligns platform narrative)

---

## 1. What EDON Impact is (correct framing)

EDON Impact is a **pre-sale and pre-deployment risk discovery engine** for enterprise AI agent systems—not merely a **reporting** or **executive translation** layer.

**Mental model:**

| Incorrect (too narrow) | Correct |
|------------------------|---------|
| Impact = reporting layer | Impact = **proactive** risk discovery + scenario generation |
| Impact = interprets existing findings only | Impact identifies **latent failure modes** in agent behavior **before or during** deployment |
| Passive “explain governance” | **Active diagnostic**: what will **likely** break, **how**, and at **what severity** |

**Positioning shorthand (commercial):** *AI agent vulnerability scanner + governance simulator for enterprise AI systems*—complementing, not replacing, full infrastructure pentests.

---

## 2. Formal definition

**EDON Impact** is a **risk discovery and failure-mode simulation layer** that analyzes **client agent configurations**, **governance policies**, **Shadow** results, and (where available) a **system surface model** of the client stack to identify **high-impact vulnerabilities**, **control gaps**, and **operational failure scenarios** before they manifest in production.

---

## 3. Hard architectural constraint (non-negotiable)

**EDON Impact does not authorize, modify, or evaluate live decisions.**

- **Governance** (Decision Kernel / governor) is the **only** binding authority for **ALLOW / BLOCK / ESCALATE** on real traffic.
- Impact **simulates**, **analyzes**, **identifies risks**, and **generates scenarios**—it must **not** become a second governance engine or shadow policy layer.

If this line blurs, you risk **duplicate** “truth” and **audit confusion**. Impact outputs **recommendations** and **risk artifacts**; **policy changes** happen through governed admin flows.

---

## 4. Relationship to Shadow and Governance (hierarchy)

Impact is **not** simply “downstream of Shadow.”

**Flow:**

```
Governance → live decisions (execution path)
       ↓
   Shadow (stress tests governance on traces / perturbations)
       ↓
   Impact (system-wide failure reasoning = topology + governance config + Shadow + DecisionRecords)
```

- **Shadow** answers: *Does the **control** hold under attack and drift?*
- **Impact** answers: *Given **policies**, **intents**, **tool/agent topology**, and **Shadow** evidence, what **failure modes** and **vulnerability classes** exist end-to-end?*

**Impact = Shadow + system topology reasoning + risk synthesis**—not only “Shadow → summary.”

---

## 5. Inputs (what Impact consumes)

1. **Governance configuration**  
   Policies, intent definitions, tool permissions, packs, tenant rules.

2. **Shadow outputs**  
   Adversarial failures, bypass classes, drift events, chain-stress results, confirmed-bypass signals (when present).

3. **DecisionRecord lineage (SSOT)**  
   Where committed, findings and scenarios **join** to `decision_id` / policy version—see [DECISION_KERNEL.md](./DECISION_KERNEL.md) §1.1.

4. **System surface model (required for latent failure discovery)**  
   As available from the client or discovery: **tool graph**, **agent workflows**, **data-flow / integration points**, **permissions topology**.  
   *You cannot reliably find latent failure modes without modeling how the agent stack is structured—policy and Shadow alone are insufficient for full “system” risk.*

---

## 6. Outputs (what Impact produces)

**A. Vulnerability classes** (examples)  
- Prompt-injection susceptibility surfaces  
- Over-permissioned agents or intents  
- Uncontrolled tool chaining  
- Data exfiltration paths under policy  
- Privilege escalation via agent routing or multi-step chains  

**B. Failure scenarios** (concrete narratives)  
- e.g. “Policy allows export without human approval under condition X.”  
- e.g. “Shadow shows bypass under multi-step decomposition; Impact maps to business impact.”  

**C. Risk severity mapping**  
- Structured **likelihood × blast radius × recoverability** (or equivalent bands)—customer-calibrated where assumptions exist.

**D. Remediation recommendations**  
- Tighten policy / intent, restructure tool graph, add approval gates, isolate capabilities—**actionable**, not generic PDF filler.

**E. Deliverables**  
- Pre-sales / pilot **readouts**, **before–after** when policy changes, exports suitable for **CISO / procurement** (format TBD by product).

---

## 7. What Impact is not

- **Not** a full **infrastructure** vulnerability scanner (OS, network, cloud posture)—**complementary**.
- **Not** a guarantee of specific legal outcomes or exact dollar loss—**risk bands** and **scenarios**, grounded in evidence and assumptions.
- **Not** a second decision authority—see §3.

---

## 8. One-line definitions (pick by audience)

**Funding / exec:**  
**EDON Impact is a pre-deployment and pre-sale risk discovery system that analyzes agent configurations, governance policies, and Shadow simulations to identify high-impact failure modes, control gaps, and operational vulnerabilities in enterprise AI agent systems.**

**Technical:**  
**Impact synthesizes governance configuration, Shadow evidence, and (when modeled) client agent topology into vulnerability classes and failure scenarios—without authorizing live actions.**

---

## 9. Commercial alignment

Impact is positioned for:

- **CISO** buying logic (“find weaknesses before attackers / before go-live”)  
- **Procurement** justification (pilot value, measurable risk reduction)  
- **Enterprise pilot** (pre-deployment assurance)

—not only “compliance visualization” or “nicer dashboards.”

---

## Related docs

- [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md) — platform narrative  
- [DECISION_KERNEL.md](./DECISION_KERNEL.md) — `DecisionRecord` as SSOT; Impact binds for analysis  
- [EDON_FEATURES_INDEX.md](./EDON_FEATURES_INDEX.md) — where features live  

---

*Revise this doc when the Impact engine ships (APIs, topology ingestion, report templates).*
