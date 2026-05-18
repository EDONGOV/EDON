# EDON Decision Kernel — causal control architecture

**Audience:** engineering, security architecture, compliance engineering  
**Status:** target architecture / north-star invariants (implementation may be partial until migrated)

---

## 1. Purpose

This document defines **how EDON represents “truth”** for governed agent actions. The goal is a **control system**, not only a **governance rule set**:

- **One** authoritative causal record per governed action.
- **One** code path that may **create or mutate** causal state before commit.
- **No** silent semantic drift from **untyped** or **multi-path** interpretation of the same request.

### 1.1 Control system: `DecisionRecord` as single source of truth (every layer)

A **strong governance platform map**—intents, policy packs, Shadow, EDON Impact, enforcement playbooks—is necessary but **not sufficient**. EDON becomes a **true control system** only when **`DecisionRecord`** (the committed, immutable record keyed by **`decision_id`**) is declared the **single source of truth across every layer**, **not** only inside the Decision Kernel.

**Layers must project onto the same record**, not maintain parallel “official” truths:

| Layer | How it binds to `DecisionRecord` |
|-------|-----------------------------------|
| **Kernel** | Creates and commits the record. |
| **Audit / system of record** | Persists and chains integrity to **`decision_id`**. |
| **Shadow** | Findings reference the **same causal lineage** (e.g. trace → committed decision identity); replay diffs are **about** that record’s policy context. |
| **EDON Impact** | Risk findings, scenario rows, and severity **join** to **`decision_id`** / policy version on the record—not a separate impact-only ID as primary truth. Impact **analyzes and synthesizes**; it does **not** authorize or re-evaluate live verdicts (see [EDON_IMPACT.md](./EDON_IMPACT.md) §3). |
| **Execution receipts** | Outcomes **append** under **`decision_id`** (or are rejected if unbound). |
| **Observability & metering** | Where decisions are counted, labels tie to **`decision_id`** (or an explicit **ungoverned** bucket). |

**Rule:** Secondary artifacts (dashboards, narrative PDFs, SIEM copies) may exist, but they are **derivatives**. If **audit, Shadow, and Impact** disagree on “what happened” without reconciling through **`DecisionRecord`**, the system is still a **governance map**, not a **closed control loop**.

---

## 2. Problem being solved

Opacity in production systems often comes **less** from “bad JSON” and **more** from:

- **Multiple code paths** interpreting or enriching the same payload independently.
- **Distributed causality:** agent builds partial intent, policy mutates, tool layer mutates, logging infers fields afterward.
- **Post-hoc reasoning:** primary “why” reconstructed from logs instead of recorded at commit time.

**Result:** audit becomes **interpretation**, not **verification**.

---

## 3. Core invariants

### 3.1 Single Decision Kernel (non-negotiable)

**Only the Decision Kernel** may **create or modify** causal state leading to a committed decision.

| Allowed | Forbidden |
|---------|-----------|
| Input **normalization** (wire → typed input) | Agents or services **deriving policy meaning** from raw request JSON ad hoc |
| **Execution** (after commit, bound to `decision_id`) | Multiple independent **“decision builders”** across services |
| **Logging** (observational, forensic, hashed raw copy) | **Policy verdict** or **primary reason** invented only in logs after the fact |

### 3.2 Single write path

All routes that produce a governed outcome (`/v1/action`, proxy/invoke paths, etc.) must **converge** on the same pipeline:

`normalized input → Decision Kernel → commit → immutable record`.

### 3.3 Typed state only in the kernel

**Untyped state must not influence control flow** after parsing.

- **Wire layer:** HTTP/JSON may be free-form as received.
- **Normalization boundary:** exactly one layer converts **raw → typed `DecisionInput`** (or equivalent).
- **Kernel:** only **typed** structures enter **policy evaluation**.

`Dict[str, Any]` may still exist **only** in **quarantined** storage: forensic blobs, debug echoes, **non-causal** attachments. It must be **causally inert** for execution logic—**observable but not active** in branching.

### 3.4 Enforcement-level specificity for normalization

“Normalization” must be **enforceable**, not a loose convention.

- **Per route / per tool (or versioned schema)** rules: what is valid, what is **rejected**, what **escalates** to human review—no silent coercion of ambiguous JSON into policy meaning.
- **Versioned** contracts (schema id + revision) so audits can answer **what shape** was legal at commit time.
- **Tests** on the normalizer: invalid payloads **fail closed** (or ESCALATE) per product policy—**not** undefined behavior.

Without this, `Dict[str, Any]` survives as a **hidden** control channel.

### 3.5 Elimination of multi-path semantic construction

**Governance-relevant meaning** (what action is requested, under which intent, which tool/op) must be built **exactly once** on the path into the kernel—typically at **normalization → `DecisionCandidate`**.

**Forbidden:** constructing or mutating that meaning again in **parallel** (e.g. different semantics in a proxy adapter vs `/v1/action` vs a background worker). That is **multi-path semantic construction** and reproduces **distributed causality**.

**Allowed:** format adapters that parse wire formats into **the same** normalized constructor inputs—**one** semantic pipeline, multiple **syntax** entrypoints.

### 3.6 Advisory outputs: non-causal channel only

Advisory systems (ML/LLM **scores**, “suggested risk,” semantic classifiers) must be **strictly non-causal** with respect to **binding** verdict unless the product explicitly defines a **single** kernel rule that consumes them.

- **May:** attach scores to the **record**, drive **dashboards**, **escalation suggestions**, **human queue ordering**, **Shadow** prioritization.
- **Must not:** silently **override** intent, **flip** ALLOW/BLOCK, or **inject** new policy meaning **without** the same deterministic kernel path that any other signal uses.

**Binding policy** stays **auditable and non-learned** in the default posture; learned layers are **observable metadata**, not a second brain inside the commit path.

---

## 4. State machine: Candidate → commit → immutable record

Conceptually there is **one** object family with a **commit barrier**, not two unrelated “pre/post” systems.

### Phase 1 — `DecisionCandidate` (mutable until commit)

- Constructed **only** from typed input.
- Policy evaluation runs **here**.
- Proposed tool intent / action shape is fixed **before** commit.

### Commit barrier (governance lives here)

At commit:

- Causal intent is **frozen**.
- System issues **`decision_id`** (and/or **DecisionAtom** ID) as the **only** token that may authorize **externally consequential** effects (subject to deployment enforcement).

### Phase 2 — immutable record (`DecisionAtom` / `DecisionRecord`)

- **DecisionCandidate** + **verdict** + **kernel-produced factors** + **policy version hashes**.
- **Append-only** extension with **execution outcomes** (e.g. tool `result_hash`, success/failure) when reported—**never** rewriting the committed causal core.

**Note:** If execution runs **outside** the gateway process, **tool results** may arrive **asynchronously**; the invariant is **no authorized side effect without a prior committed `decision_id`**, not “same HTTP response contains everything.”

---

## 5. Minimum shape (reference): Decision Atom

Exact fields evolve; this is a **logical** minimum for discussion and APIs:

```json
{
  "decision_id": "uuid",
  "timestamp": "ISO-8601",

  "input_state_hash": "hash",
  "intent_ref": "typed enum or schema id",
  "context": "strict schema or null",

  "decision_vector": {
    "features": [],
    "weights": [],
    "thresholds": []
  },

  "policy_version": "hash-or-version",
  "verdict": "ALLOW | BLOCK | ESCALATE | …",

  "tool_calls": [
    {
      "tool": "string",
      "arguments": "strict schema",
      "result_hash": "hash or null"
    }
  ],

  "output_action": "typed schema or null",
  "final_state_hash": "hash"
}
```

Naming in code may use `DecisionRecord` / `DecisionAtom` interchangeably until a single term is standardized.

---

## 6. Failure modes to avoid

| Failure mode | Symptom |
|--------------|---------|
| **A — Multiple decision builders** | Same request yields **different** “truth shapes” per route. |
| **B — Post-hoc reasoning injection** | Authoritative **reason** or **verdict** appears only in logs after execution. |
| **C — Dual truth** | Logs describe X; execution followed Y. |
| **D — Advisory AI as hidden branch** | Model scores **mutate** intent or verdict without going through the kernel. |

**Rule:** advisory models supply **signals** or **metadata** on the record; they do **not** replace the kernel’s **binding** decision path.

---

## 7. Relationship to deployment (“real enforcement”)

The Decision Kernel defines **causal truth inside EDON**. **Bypass** of EDON (agents calling tools directly) is a **deployment and network** problem. See **“What real enforcement looks like in practice”** in [EDON_PLATFORM_OVERVIEW.md](./EDON_PLATFORM_OVERVIEW.md): network choke points, signed execution, runtime validation of `decision_id`, aligned observability.

**Compressed invariant:** **every side effect** should trace to **exactly one** immutable **`decision_id`** in the governed pipeline—**and** execution endpoints should **reject** unbound requests where customers adopt tight integration.

---

## 8. Engineering migration (reality)

Rolling this out is a **migration**, not a one-day flip:

1. Introduce **typed `DecisionInput`** + **single kernel entrypoint**.
2. Route all governed endpoints through it; deprecate parallel paths.
3. Persist **one** canonical record schema in the audit store.
4. Quarantine raw JSON to **forensic** fields only.
5. Document **customer** choke-point requirements alongside the kernel.

---

## 9. Summary (one paragraph)

EDON’s **Decision Kernel** is the **only** component that may create or evolve **causal** state before commit. **Raw JSON is allowed on the wire** but must become **typed** before policy runs; unstructured data must remain **causally inert** for execution logic. After **commit**, the **DecisionAtom / DecisionRecord** is **immutable**; effects and outcomes **append** under the same **`decision_id`**. Together with **deployment enforcement**, this is the path from **strong governance** to **control-system architecture**.

---

*Internal engineering reference — align naming and fields with implementation as the kernel lands.*
