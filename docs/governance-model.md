# EDON Governance Model

## Policy Packs

| Pack | Key | Description | Best For |
|------|-----|-------------|----------|
| Safe Mode | `casual_user` | Read-only by default; blocks writes/sends | New deployments, consumer agents |
| Market Analyst | `market_analyst` | Research + read; blocks trading actions | Finance research agents |
| Ops Commander | `ops_commander` | Full workflow automation; escalates high-stakes | Enterprise ops teams |
| Founder Mode | `founder_mode` | Broad access with minimal friction | Trusted internal agents |
| Helpdesk | `helpdesk` | Customer comms allowed; blocks sensitive data access | Support agents |
| Autonomy Mode | `autonomy_mode` | Near-full autonomy; only true safety violations blocked | High-trust robotics, physical AI |

## Verdicts

| Verdict | Meaning |
|---------|---------|
| `ALLOW` | Action approved, proceed |
| `BLOCK` | Action denied, do not execute |
| `ESCALATE` | Requires human confirmation before proceeding |
| `DEGRADE` | Allow a limited/safe version of the action |
| `PAUSE` | Suspend agent pending review |
| `ERROR` | Evaluation failed (fail-open or fail-closed per config) |

## Reason Codes

| Code | Trigger |
|------|---------|
| `APPROVED` | Passed all checks |
| `SCOPE_VIOLATION` | Action outside declared intent scope |
| `RISK_TOO_HIGH` | Risk score exceeds policy threshold |
| `DATA_EXFIL` | Potential data exfiltration detected |
| `OUT_OF_HOURS` | Action attempted outside allowed time window |
| `NEED_CONFIRMATION` | High-stakes action requires human sign-off |
| `LOOP_DETECTED` | Agent repeating same action (loop guard) |
| `RATE_LIMIT` | Per-tenant or per-agent quota exceeded |
| `PROMPT_INJECTION` | Injection attack detected in payload |
| `ANOMALY_DETECTED` | Behavioral deviation from agent baseline |

## Behavioral CAV (Continuous Anomaly Validation)

EDON tracks per-agent behavior over time. If an agent's block rate spikes, its action pattern deviates from baseline, or cross-agent collusion is detected, the CAV flags it for review and optionally auto-pauses the agent.

## Audit Chain Integrity

Every decision is written to an append-only log with a SHA-256 hash chaining each entry to the previous. Tampering with any entry invalidates the chain. The `/scripts/validate_audit_chain.py` script verifies integrity.
