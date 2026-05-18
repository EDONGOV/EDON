# EDON — Platform overview (one page)

**Full feature index (Impact, Shadow, Decision Kernel, shipped vs soon):** [EDON_FEATURES_INDEX.md](./EDON_FEATURES_INDEX.md)

**For:** sales, customer success, security review kickoff  
**What EDON is:** the governance layer between your AI agents and the outside world—every action is evaluated, enforced, and recorded before execution.

---

## Executive summary

Organizations are deploying agents that can move money, touch regulated data, and control operations. EDON makes that safe to scale: **policy and intent** define what agents may do; **tamper-evident auditing** proves what was decided; **Shadow** continuously stress-tests those decisions on real traffic; **EDON Impact** is a **pre-sale and pre-deployment risk discovery engine**—it combines **governance configuration**, **Shadow** evidence, and (where modeled) **client agent topology** to surface **vulnerability classes, failure scenarios, and severity** before production—not merely executive summaries of what already happened.

---

## The problem EDON solves

- Agents can take **high-impact actions** (payments, bulk export, messaging, physical systems, internal tools).
- **Prompt injection, credential abuse, and policy drift** can turn “helpful automation” into **unauthorized or harmful behavior**.
- Boards and regulators expect **control, evidence, and accountability**—not “we trust the model.”

---

## What EDON does (four layers)

| Layer | Outcome for the customer |
|--------|---------------------------|
| **Govern** | Every proposed action is checked against **intent** (scope + constraints) and **policy** (packs + custom rules) → **allow, block, escalate, degrade, pause**. |
| **Audit** | Decisions are written to an **append-only, integrity-checked** trail suitable for **risk, audit, and operations** review. |
| **Assure (Shadow)** | Real decisions are **replayed** with adversarial mutations and multi-step **chain stress** to find **bypasses, drift, and fragile policy**—without blocking production traffic. |
| **Discover (EDON Impact)** | **Proactive** risk discovery: vulnerability classes, **failure-mode scenarios**, and **severity** (likelihood × blast radius × recoverability) from **policies, intents, permissions**, **Shadow** findings, and **system surface** (tool graph, workflows, data flows)—**pre-deployment / pilot** assurance. Does **not** authorize live decisions. |

**EDON Impact (full definition, inputs/outputs, non-authorization constraint):** [EDON_IMPACT.md](./EDON_IMPACT.md).

---

## Causal control model (target architecture)

Beyond policy packs and logs, EDON’s **north star** is a **single causal substrate**: a **Decision Kernel** with **one write path**—**`DecisionCandidate`** (typed input only, policy evaluated here) → **commit barrier** → **immutable `DecisionAtom` / `DecisionRecord`** with a stable **`decision_id`**. Wire JSON may be messy on ingress; after **normalization**, raw structures must be **causally inert** for execution logic (forensic/debug only)—so **opacity cannot accumulate** through parallel interpreters of the same payload.

**Control system, not only a governance map:** the committed **`DecisionRecord`** must be the **single source of truth across every layer**—audit, Shadow, EDON Impact, execution receipts, observability—so no parallel “official” story exists outside that record. See §1.1 in [DECISION_KERNEL.md](./DECISION_KERNEL.md).

**Full invariants, state machine, forbidden patterns, and reference record shape:** [DECISION_KERNEL.md](./DECISION_KERNEL.md).

---

## How customers connect

- **Primary path:** agents call EDON **before** acting (e.g. `POST /v1/action`).
- **Proxy path:** agents point tool invocation at EDON; allowed calls are **forwarded** to the customer’s existing gateway (**governance-only** integration).
- **Identity & scale:** tenant-scoped **API keys**, **RBAC**, **rate limits**, and observability for enterprise rollout.

---

## What EDON is not (set expectations, build trust)

- EDON is **not** a replacement for your full **infrastructure penetration test**, **EDR**, or **cloud security posture** program. It **complements** them by **owning the agent control plane**.
- EDON Impact **does not** authorize, modify, or re-evaluate **live** governance verdicts—it **simulates and analyzes** risk. It **does not** guarantee specific legal outcomes or dollar losses; it provides **structured scenarios and bands** grounded in **governance evidence**, **Shadow**, **topology** (when modeled), and **customer assumptions**. Full spec: [EDON_IMPACT.md](./EDON_IMPACT.md).

---

## Who cares inside the buyer

- **CISO / security:** defensible controls, continuous assurance, exportable evidence.
- **Risk / compliance:** intent boundaries, auditability, mapping to regulatory narratives (implementation varies by vertical).
- **COO / business owner:** blast radius visibility, prioritization of “what could go wrong,” alignment with operational risk.
- **Engineering:** one integration surface, clear verdicts, SDKs and docs.

---

## One-sentence positioning

**EDON governs every agent action with policy and proof; Shadow validates that those controls hold under attack; EDON Impact discovers what can break across policy, topology, and adversarial evidence—before it hits production.**

---

## Suggested next step with a prospect

1. **Scope** agents, environments, and regulated data classes.  
2. **Connect** traffic (observation or enforcement, as appropriate).  
3. **Deliver** baseline **Impact** readout + **Shadow** findings with remediation priorities.  
4. **Tighten** intents and rules; **re-run** assurance to show **before/after** exposure.

---

## What “real enforcement” looks like in practice

Governance logic in EDON is necessary but not sufficient: **if execution can bypass the gateway, causality breaks.** When EDON is treated as **real infrastructure**, the customer deployment should aim for the following (exact mechanisms vary by cloud and network layout).

### Network level

- **Execution services** (tool backends, internal APIs, payment rails, robotics gateways) are **not** broadly internet-exposed.
- Only the **EDON gateway** (or an explicitly approved broker) has **routing** to those services for agent-driven traffic, where technically feasible.

### Identity level

- **Execution requests** are **cryptographically bound** to governance (e.g. signed or HMAC’d payloads, short-lived capability tokens).
- **Keys** that can invoke privileged execution are **issued or mediated through EDON** (or a tightly coupled secret broker), not duplicated as long-lived god-keys on agents.

### Runtime level

- **Execution services** validate **linkage to a committed decision** (e.g. `decision_id` / **DecisionAtom** ID issued only after policy commit).
- Requests **without** a valid, unexpired binding are **rejected**—no “silent” tool execution.

### Observability level

- **No committed decision → no authorized effect**; correlatively, **system-of-record** logs and operational truth should align: **no DecisionAtom (or equivalent canonical decision record) → no durable “official” record of that action** in the governed pipeline.
- Ad-hoc logs may exist for debugging, but **audit and compliance** trace to the **same causal ID** as execution.

**Compressed rule:** every externally consequential effect should be traceable to **exactly one** immutable governance commitment—**network, identity, runtime, and logs** all agree.

---

*Internal reference — align with legal for customer-facing PDFs and contractual scope.*
