# Meta-Capabilities — Memory, Planning, Observation, Human-in-the-Loop

Beyond tool integrations, the gateway adds **memory**, **planning**, **observation**, and **human-in-the-loop escalation** so the agent can learn, plan, verify, and ask when needed.

---

## 1. Memory (first-class)

Two layers: **preferences** (long-term) and **episodes** (task history). Writes are **intentional** and governor-approved; no automatic writes.

### A. Long-term preference memory

- **Examples:** “I like concise emails”, “Never schedule before 10am”, “Always CC my cofounder on investor emails”.
- **Implementation:** KV store per tenant (`preference_memory` table). Write/read via tool `memory`.
- **Ops:** `write_preference`, `read_preferences`.

**Execute (write):**
```json
{
  "action": {
    "tool": "memory",
    "op": "write_preference",
    "params": {
      "key": "email_style",
      "value": "concise",
      "tenant_id": "tenant_xxx"
    }
  },
  "agent_id": "edonbot-001"
}
```

**Execute (read):**
```json
{
  "action": {
    "tool": "memory",
    "op": "read_preferences",
    "params": { "keys": ["email_style", "meeting_after"] }
  }
}
```

Intent scope must include `"memory": ["write_preference", "read_preferences", "append_episode", "query_episodes"]`.

### B. Episodic task memory

- **Examples:** “Last time we deployed, it failed because X”, “This repo uses staging branch”, “We already emailed this person last week”.
- **Implementation:** Append-only episodes per tenant (`episodic_memory` table). Query by time or tool.
- **Ops:** `append_episode`, `query_episodes`.

**Append:**
```json
{
  "action": {
    "tool": "memory",
    "op": "append_episode",
    "params": {
      "episode_id": "ep_abc",
      "task_summary": "Deployed frontend to staging",
      "outcome": "failed",
      "tool": "github",
      "op": "create_issue",
      "context": { "reason": "missing env var" }
    }
  }
}
```

**Query:**
```json
{
  "action": {
    "tool": "memory",
    "op": "query_episodes",
    "params": { "limit": 20, "since": "2025-01-01T00:00:00Z", "tool": "gmail" }
  }
}
```

---

## 2. Planning + decomposition (non-executing)

Planning **does not execute**; execution still goes through `POST /execute` and the governor.

- **Endpoint:** `POST /plan`
- **Body:** `{ "objective": "Search for X and email the summary to Y", "context": {} }`
- **Response:** `{ "objective": "...", "steps": [ { "id", "tool", "op", "step_type", "params" }, ... ], "count": N }`

**Step types:**

- **read** — no side effects (e.g. search, list messages, list events).
- **draft** — preview/safe (e.g. draft email).
- **execute** — side effects; may require confirmation (e.g. send email, create event, create issue).

Rules are keyword-based (e.g. “search” → brave_search read; “email” → gmail list then send). The agent or client can refine steps and then call `POST /execute` for each step.

---

## 3. Observation hooks (feedback loops)

After a successful tool run, the gateway runs a lightweight **“did this work?”** check and attaches it to the execution result.

- **Gmail send** → `observation`: `{ "verified": true, "message_id": "...", "thread_id": "..." }`.
- **Google Calendar create_event** → `observation`: `{ "verified": true, "event_id": "...", "html_link": "..." }`.
- **GitHub create_issue** → `observation`: `{ "verified": true, "issue_number": ..., "html_url": "..." }`.

So the client can use `execution.result` and `execution.observation` for retries, confidence, or logging.

---

## 4. Human-in-the-loop escalation

When the governor escalates (e.g. high risk, too many recipients, ambiguous intent), the response includes:

- **escalation_question** — one precise question (e.g. “Send email to 15 recipients?”).
- **escalation_options** — list of `{ "id", "label" }` (e.g. “Allow once”, “Save as draft only”, “Keep blocking”).

**Triggers:**

- **High-impact:** e.g. recipient count &gt; `max_recipients` in intent constraints.
- **Risk:** action in `escalate_risk_levels` (high/critical) without prior approval.
- **Ambiguous intent:** optional, when intent objective is very short and constraint `escalate_on_ambiguous_intent` is true; then we escalate instead of hard block.

**Example response (ESCALATE):**
```json
{
  "verdict": "ESCALATE",
  "reason_code": "NEED_CONFIRMATION",
  "explanation": "Recipient count (15) exceeds max (10). Requires confirmation.",
  "escalation_question": "Send email to 15 recipients? (max allowed: 10)",
  "escalation_options": [
    { "id": "allow_once", "label": "Allow once" },
    { "id": "draft_only", "label": "Save as draft only" },
    { "id": "keep_blocking", "label": "Keep blocking" }
  ]
}
```

The client (e.g. Edonbot/Telegram) shows the question and options, collects the user’s choice, and can re-call with confirmation or a different action.

---

## Quick reference

| Capability   | How                                                     |
|-------------|----------------------------------------------------------|
| Preferences | `tool: "memory", op: "write_preference" / "read_preferences"` |
| Episodes    | `tool: "memory", op: "append_episode" / "query_episodes"`     |
| Planning    | `POST /plan` with `objective` (returns steps only)           |
| Observation | Automatic after execute; see `execution.observation`           |
| HITL        | On ESCALATE, use `escalation_question` + `escalation_options` |

All memory writes and tool executions still go through the governor; planning is non-executing; observation is read-only verification; escalation keeps one question and clear options so the agent feels smart, not noisy.
