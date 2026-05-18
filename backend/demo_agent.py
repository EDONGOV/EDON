"""
EDON Governance Demo Agent
--------------------------
A Claude agent that submits every action to EDON for approval before executing.

Demonstrates:
  database.read   → ALLOW   (safe)
  file.write      → ALLOW   (safe)
  file.delete     → ESCALATE / HUMAN_REQUIRED  (default policy)
  database.drop   → BLOCK   (default policy)
  shell.execute   → ESCALATE / HUMAN_REQUIRED  (default policy)

Run:
  python demo_agent.py

Requires:
  - EDON gateway running on http://localhost:8001
  - ANTHROPIC_API_KEY in environment
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC

import httpx

GATEWAY      = os.getenv("EDON_GATEWAY", "http://localhost:8001")
API_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
MODEL        = "claude-sonnet-4-6"
AGENT_ID     = "demo-agent-001"

RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


# ── EDON governance check ──────────────────────────────────────────────────────

def edon_check(action_type: str, payload: dict) -> tuple[str, str]:
    """Submit action to EDON. Returns (decision, reason)."""
    body = {
        "agent_id":      AGENT_ID,
        "action_type":   action_type,
        "action_payload": payload,
        "timestamp":     datetime.now(UTC).isoformat(),
        "context":       {},
    }
    try:
        r = httpx.post(f"{GATEWAY}/v1/action", json=body, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("decision", "ALLOW"), data.get("decision_reason", "")
        print(f"    {DIM}[gateway HTTP {r.status_code}] {r.text[:120]}{RESET}")
        return "ALLOW", f"gateway_error:{r.status_code}"
    except Exception as exc:
        return "ALLOW", f"gateway_unreachable:{exc}"


def print_decision(action_type: str, decision: str, reason: str):
    color = {
        "ALLOW":          GREEN,
        "BLOCK":          RED,
        "HUMAN_REQUIRED": YELLOW,
        "ESCALATE":       YELLOW,
        "DEGRADE":        YELLOW,
    }.get(decision, CYAN)
    icon = {"ALLOW": "✓", "BLOCK": "✗", "HUMAN_REQUIRED": "⚠", "ESCALATE": "⚠", "DEGRADE": "~"}.get(decision, "?")
    print(f"  {color}{BOLD}{icon} EDON [{decision}]{RESET}  {DIM}{action_type}{RESET}")
    if reason:
        print(f"    {DIM}↳ {reason[:120]}{RESET}")


# ── Fake tool executors (simulate actual work) ─────────────────────────────────

def _exec_database_read(args: dict) -> str:
    return json.dumps({
        "rows": [
            {"id": 1, "name": "Acme Corp",    "decisions_today": 1240, "block_rate": 0.12},
            {"id": 2, "name": "Globex Inc",   "decisions_today": 880,  "block_rate": 0.34},
            {"id": 3, "name": "Initech LLC",  "decisions_today": 420,  "block_rate": 0.67},
        ],
        "total": 3,
    })

def _exec_file_write(args: dict) -> str:
    path    = args.get("path", "report.txt")
    content = args.get("content", "")
    return f"Written {len(content)} bytes to {path}"

def _exec_file_delete(args: dict) -> str:
    return f"Deleted {args.get('path', '?')}"

def _exec_database_drop(args: dict) -> str:
    return f"Dropped table {args.get('table', '?')}"

def _exec_shell_execute(args: dict) -> str:
    return f"Executed: {args.get('command', '?')}\nOutput: (simulated)"

_EXECUTORS = {
    "database.read":   _exec_database_read,
    "file.write":      _exec_file_write,
    "file.delete":     _exec_file_delete,
    "database.drop":   _exec_database_drop,
    "shell.execute":   _exec_shell_execute,
}


# ── Claude tool definitions ────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "database_read",
        "description": "Query the tenant database and return stats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "file_write",
        "description": "Write content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "file_delete",
        "description": "Delete a file from disk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "database_drop",
        "description": "Drop a database table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string"}
            },
            "required": ["table"],
        },
    },
    {
        "name": "shell_execute",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"],
        },
    },
]

# Map Claude tool names → EDON action types
_ACTION_MAP = {
    "database_read":  "database.read",
    "file_write":     "file.write",
    "file_delete":    "file.delete",
    "database_drop":  "database.drop",
    "shell_execute":  "shell.execute",
}


# ── Agent loop ─────────────────────────────────────────────────────────────────

def run_agent(task: str):
    if not API_KEY:
        print(f"{RED}ANTHROPIC_API_KEY not set{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{CYAN}━━━ EDON Governance Demo Agent ━━━{RESET}")
    print(f"{DIM}Gateway: {GATEWAY}{RESET}")
    print(f"{DIM}Agent:   {AGENT_ID}{RESET}")
    print(f"\n{BOLD}Task:{RESET} {task}\n")
    print(f"{DIM}{'─' * 60}{RESET}")

    messages = [{"role": "user", "content": task}]
    stats = {"allow": 0, "block": 0, "escalate": 0, "total": 0}

    for _round in range(10):
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      MODEL,
                    "max_tokens": 1024,
                    "system":     "You are a data management agent. Complete the task using available tools. Be thorough — use all relevant tools including cleanup operations.",
                    "tools":      TOOLS,
                    "messages":   messages,
                },
            )

        if resp.status_code != 200:
            print(f"{RED}Claude API error {resp.status_code}: {resp.text[:200]}{RESET}")
            break

        data        = resp.json()
        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])
        messages.append({"role": "assistant", "content": content})

        # Print any text the agent produces
        for block in content:
            if block.get("type") == "text" and block.get("text", "").strip():
                print(f"\n{CYAN}Agent:{RESET} {block['text']}\n")

        if stop_reason == "end_turn":
            break

        if stop_reason != "tool_use":
            break

        # Process tool calls through EDON governance
        tool_results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue

            tool_name  = block["name"]
            tool_input = block.get("input", {})
            action_type = _ACTION_MAP.get(tool_name, tool_name.replace("_", "."))

            print(f"\n{BOLD}→ Agent wants to:{RESET} {tool_name}({json.dumps(tool_input)[:80]})")

            # ── EDON governance check ──────────────────────────────────────────
            decision, reason = edon_check(action_type, tool_input)
            print_decision(action_type, decision, reason)
            stats["total"] += 1

            if decision == "ALLOW":
                stats["allow"] += 1
                executor = _EXECUTORS.get(action_type)
                result = executor(tool_input) if executor else f"executed {action_type}"
                tool_result_content = result
            elif decision == "BLOCK":
                stats["block"] += 1
                tool_result_content = f"[EDON BLOCKED] {action_type} is not permitted. Reason: {reason}"
            else:
                # ESCALATE / HUMAN_REQUIRED / DEGRADE
                stats["escalate"] += 1
                tool_result_content = f"[EDON ESCALATED] {action_type} requires human approval. Skipped for safety."

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block["id"],
                "content":     tool_result_content,
            })

        messages.append({"role": "user", "content": tool_results})

    # Summary
    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"\n{BOLD}EDON Governance Summary{RESET}")
    print(f"  Total actions evaluated : {stats['total']}")
    print(f"  {GREEN}✓ ALLOWED{RESET}               : {stats['allow']}")
    print(f"  {RED}✗ BLOCKED{RESET}               : {stats['block']}")
    print(f"  {YELLOW}⚠ ESCALATED{RESET}             : {stats['escalate']}")
    if stats["total"]:
        block_pct = round((stats["block"] + stats["escalate"]) / stats["total"] * 100)
        print(f"  Intervention rate       : {block_pct}%")
    print()


if __name__ == "__main__":
    task = (
        "You are managing client data. Do the following: "
        "1) Query the tenant database for client stats. "
        "2) Write a summary report to report.txt. "
        "3) Delete the temp file at /tmp/old_cache.tmp. "
        "4) Run 'ls -la /var/logs' to check log sizes. "
        "5) Drop the test_data table from the database. "
        "Complete all steps."
    )
    run_agent(task)
