"""Tenant Governance Assistant — per-tenant AI chat.

Mode 1: Read/Explain — query own audit log, agents, policies, compliance health.
Mode 2: Suggest     — propose policy changes; tenant clicks Apply to execute.

POST /v1/assistant/chat   — send a message, get an answer or a suggestion card
POST /v1/assistant/apply  — apply a pending suggestion
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, UTC, timedelta
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..logging_config import get_logger
from ..persistence import get_db
from ..tenant_knowledge import build_tenant_knowledge_snapshot, render_tenant_knowledge_snapshot
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/assistant", tags=["assistant"])

_MODEL         = "claude-sonnet-4-6"
_MAX_TOKENS    = 2048
_MAX_TOOL_ROUNDS = 8
_ANTHROPIC_API = "https://api.anthropic.com/v1"


# ── Read tools ─────────────────────────────────────────────────────────────────

def _tool_get_governance_stats(args: dict, tenant_id: str) -> dict:
    hours = int(args.get("hours", 24))
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    try:
        db = get_db()
        with db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT decision_verdict, COUNT(*) as cnt
                FROM audit_events
                WHERE timestamp >= ? AND customer_id = ?
                GROUP BY decision_verdict
                """,
                (since, tenant_id),
            ).fetchall()
            total_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM audit_events WHERE timestamp >= ? AND customer_id = ?",
                (since, tenant_id),
            ).fetchone()
            top_agents = conn.execute(
                """
                SELECT agent_id, COUNT(*) as cnt,
                       SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks
                FROM audit_events
                WHERE timestamp >= ? AND customer_id = ?
                GROUP BY agent_id ORDER BY cnt DESC LIMIT 5
                """,
                (since, tenant_id),
            ).fetchall()

        verdict_counts = {r["decision_verdict"]: r["cnt"] for r in rows}
        total  = total_row["cnt"] if total_row else 0
        blocks = verdict_counts.get("BLOCK", 0)

        return {
            "period_hours":    hours,
            "total_decisions": total,
            "verdict_breakdown": verdict_counts,
            "block_rate_pct":  round(blocks / total * 100, 1) if total else 0,
            "top_agents":      [
                {"agent_id": r["agent_id"], "decisions": r["cnt"], "blocks": r["blocks"]}
                for r in top_agents
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_query_audit_events(args: dict, tenant_id: str) -> dict:
    hours     = int(args.get("hours", 24))
    agent_id  = args.get("agent_id")
    verdict   = args.get("verdict")
    limit     = min(int(args.get("limit", 20)), 50)
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    try:
        db = get_db()
        events = db.query_audit_events(
            agent_id=agent_id,
            verdict=verdict,
            customer_id=tenant_id,
            limit=limit,
        )
        events = [e for e in events if (e.get("timestamp") or "") >= since]
        simplified = []
        for e in events[:limit]:
            action   = e.get("action", {})
            decision = e.get("decision", {})
            simplified.append({
                "action_id":   action.get("id") or e.get("id"),
                "agent_id":    action.get("agent_id") or e.get("agent_id"),
                "tool":        action.get("tool") or e.get("action_tool"),
                "op":          action.get("op") or e.get("action_op"),
                "verdict":     decision.get("verdict") or e.get("decision_verdict"),
                "reason_code": decision.get("reason_code") or e.get("decision_reason_code"),
                "explanation": decision.get("explanation") or e.get("decision_explanation"),
                "timestamp":   e.get("timestamp") or e.get("created_at"),
            })
        return {"events": simplified, "count": len(simplified)}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_agents(args: dict, tenant_id: str) -> dict:
    department = args.get("department")
    status = args.get("status")
    try:
        db = get_db()
        agents = db.list_agents(tenant_id)
        if department:
            agents = [a for a in agents if a.get("department") == department]
        if status:
            agents = [a for a in agents if a.get("status") == status]
        simplified = [
            {
                "agent_id":    a.get("agent_id"),
                "name":        a.get("name"),
                "agent_type":  a.get("agent_type"),
                "department":  a.get("department"),
                "status":      a.get("status"),
                "total_actions": a.get("total_actions", 0),
                "total_blocked": a.get("total_blocked", 0),
                "block_rate":  round(a.get("total_blocked", 0) / a.get("total_actions", 1) * 100, 1) if a.get("total_actions") else 0,
                "policy_pack": a.get("policy_pack"),
                "description": a.get("description"),
                "last_seen_at": a.get("last_seen_at"),
            }
            for a in agents
        ]
        return {"agents": simplified, "count": len(simplified)}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_policy_rules(args: dict, tenant_id: str) -> dict:
    try:
        db = get_db()
        rules = db.get_policy_rules(tenant_id, enabled_only=False)
        simplified = [
            {
                "rule_id":        r.get("rule_id") or r.get("id"),
                "name":           r.get("name"),
                "action":         r.get("action"),
                "enabled":        r.get("enabled"),
                "condition_tool": r.get("condition_tool"),
                "condition_op":   r.get("condition_op"),
                "description":    r.get("description"),
            }
            for r in (rules or [])
        ]
        return {"rules": simplified, "count": len(simplified)}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_compliance_health(args: dict, tenant_id: str) -> dict:
    try:
        db = get_db()
        rules = db.get_policy_rules(tenant_id, enabled_only=True)
        rule_count = len(rules or [])
        with db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks,
                  SUM(CASE WHEN decision_verdict='ESCALATE' THEN 1 ELSE 0 END) as escalations
                FROM audit_events
                WHERE customer_id = ? AND timestamp >= datetime('now','-7 days')
                """,
                (tenant_id,),
            ).fetchone()
        total      = row["total"]      if row else 0
        blocks     = row["blocks"]     if row else 0
        escalations = row["escalations"] if row else 0
        compliance_rate = round((total - blocks) / total * 100, 1) if total else 100.0
        return {
            "active_policy_rules": rule_count,
            "decisions_7d":        total,
            "blocks_7d":           blocks,
            "escalations_7d":      escalations,
            "compliance_rate_pct": compliance_rate,
            "status": "healthy" if compliance_rate >= 90 and rule_count >= 3 else "needs_attention",
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_pending_reviews(args: dict, tenant_id: str) -> dict:
    """Return items waiting for human review/approval."""
    limit = min(int(args.get("limit", 15)), 25)
    try:
        db = get_db()
        pending = db.get_review_queue(tenant_id=tenant_id, status="pending", limit=limit)
        resolved = db.get_review_queue(tenant_id=tenant_id, status="resolved", limit=5)
        return {
            "pending_count": len(pending),
            "pending": [
                {
                    "review_id":   r.get("id"),
                    "agent_id":    r.get("agent_id"),
                    "action_type": r.get("action_type"),
                    "reason":      r.get("reason"),
                    "created_at":  r.get("created_at"),
                }
                for r in pending
            ],
            "recently_resolved": [
                {
                    "review_id":  r.get("id"),
                    "agent_id":   r.get("agent_id"),
                    "decision":   r.get("decision"),
                    "resolved_at": r.get("resolved_at"),
                }
                for r in resolved
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_explain_agent(args: dict, tenant_id: str) -> dict:
    """Summarise what an agent has been doing based on its audit trail."""
    agent_id = args.get("agent_id", "").strip()
    hours    = int(args.get("hours", 24))
    if not agent_id:
        return {"error": "agent_id is required"}
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    try:
        db = get_db()

        # Agent metadata
        agent_meta = {}
        try:
            agent_meta = db.get_agent(agent_id, tenant_id) or {}
        except Exception:
            pass

        with db._get_connection() as conn:
            # Verdict breakdown
            verdict_rows = conn.execute(
                """
                SELECT decision_verdict, COUNT(*) as cnt
                FROM audit_events
                WHERE agent_id = ? AND customer_id = ? AND timestamp >= ?
                GROUP BY decision_verdict
                """,
                (agent_id, tenant_id, since),
            ).fetchall()

            # Most frequent actions
            action_rows = conn.execute(
                """
                SELECT action_tool, action_op, COUNT(*) as cnt,
                       SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks
                FROM audit_events
                WHERE agent_id = ? AND customer_id = ? AND timestamp >= ?
                GROUP BY action_tool, action_op
                ORDER BY cnt DESC LIMIT 8
                """,
                (agent_id, tenant_id, since),
            ).fetchall()

            # Recent blocks with reasons
            block_rows = conn.execute(
                """
                SELECT action_tool, action_op, decision_reason_code,
                       decision_explanation, timestamp
                FROM audit_events
                WHERE agent_id = ? AND customer_id = ? AND timestamp >= ?
                  AND decision_verdict = 'BLOCK'
                ORDER BY timestamp DESC LIMIT 5
                """,
                (agent_id, tenant_id, since),
            ).fetchall()

            # Recent escalations
            escalation_rows = conn.execute(
                """
                SELECT action_tool, action_op, decision_explanation, timestamp
                FROM audit_events
                WHERE agent_id = ? AND customer_id = ? AND timestamp >= ?
                  AND decision_verdict IN ('ESCALATE', 'PAUSE')
                ORDER BY timestamp DESC LIMIT 5
                """,
                (agent_id, tenant_id, since),
            ).fetchall()

            # Last seen
            last_row = conn.execute(
                """
                SELECT MAX(timestamp) as last_seen, COUNT(*) as total
                FROM audit_events
                WHERE agent_id = ? AND customer_id = ? AND timestamp >= ?
                """,
                (agent_id, tenant_id, since),
            ).fetchone()

        verdict_counts = {r["decision_verdict"]: r["cnt"] for r in verdict_rows}
        total  = last_row["total"]    if last_row else 0
        blocks = verdict_counts.get("BLOCK", 0)

        return {
            "agent_id":       agent_id,
            "display_name":   agent_meta.get("display_name") or agent_meta.get("name"),
            "agent_type":     agent_meta.get("agent_type"),
            "status":         agent_meta.get("status"),
            "period_hours":   hours,
            "total_actions":  total,
            "last_seen":      last_row["last_seen"] if last_row else None,
            "verdict_breakdown": verdict_counts,
            "block_rate_pct": round(blocks / total * 100, 1) if total else 0,
            "most_frequent_actions": [
                {
                    "tool":   r["action_tool"],
                    "op":     r["action_op"],
                    "count":  r["cnt"],
                    "blocks": r["blocks"],
                }
                for r in action_rows
            ],
            "recent_blocks": [
                {
                    "tool":        r["action_tool"],
                    "op":          r["action_op"],
                    "reason":      r["decision_reason_code"],
                    "explanation": r["decision_explanation"],
                    "timestamp":   r["timestamp"],
                }
                for r in block_rows
            ],
            "recent_escalations": [
                {
                    "tool":        r["action_tool"],
                    "op":          r["action_op"],
                    "explanation": r["decision_explanation"],
                    "timestamp":   r["timestamp"],
                }
                for r in escalation_rows
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_explain_decision(args: dict, tenant_id: str) -> dict:
    action_id = args.get("action_id", "").strip()
    if not action_id:
        return {"error": "action_id is required"}
    try:
        db = get_db()
        with db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM audit_events
                WHERE (action_id = ? OR id = ?) AND customer_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (action_id, action_id, tenant_id),
            ).fetchone()
        if not row:
            return {"error": f"Decision not found: {action_id}"}

        ctx = {}
        try:
            ctx = json.loads(row["context"] or "{}")
        except Exception:
            pass

        inv_checks = ctx.get("invariant_results", [])
        inv_summary = [
            {"check": i.get("id"), "status": i.get("status"), "details": i.get("details")}
            for i in inv_checks
        ]

        return {
            "action_id":   row["action_id"],
            "agent_id":    row["agent_id"],
            "tool":        row["action_tool"],
            "op":          row["action_op"],
            "verdict":     row["decision_verdict"],
            "reason_code": row["decision_reason_code"],
            "explanation": row["decision_explanation"],
            "computed_risk": row.get("action_computed_risk"),
            "timestamp":   row["timestamp"],
            "invariant_checks": inv_summary,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Suggest tool ───────────────────────────────────────────────────────────────

_PENDING_PROPOSALS: dict[str, dict] = {}  # write-through cache; keyed by proposal_id


def _tool_propose_change(args: dict, tenant_id: str) -> dict:
    """Claude calls this when it wants to suggest a governance change."""
    proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
    proposal = {
        "proposal_id":  proposal_id,
        "tenant_id":    tenant_id,
        "type":         args.get("type", ""),
        "description":  args.get("description", ""),
        "impact":       args.get("impact", ""),
        "regulation":   args.get("regulation", ""),
        "payload":      args.get("payload", {}),
        "created_at":   datetime.now(UTC).isoformat(),
        "status":       "pending",
    }
    _PENDING_PROPOSALS[proposal_id] = proposal
    try:
        get_db().save_assistant_proposal(tenant_id, proposal_id, proposal)
    except Exception as _e:
        logger.warning("[assistant] proposal DB persist failed (in-memory only): %s", _e)
    return {"proposal_id": proposal_id, "status": "pending_review"}


# ── Tool registry ──────────────────────────────────────────────────────────────

def _get_tool_handlers(tenant_id: str) -> dict:
    return {
        "get_governance_stats":  lambda a: _tool_get_governance_stats(a, tenant_id),
        "query_audit_events":    lambda a: _tool_query_audit_events(a, tenant_id),
        "get_agents":            lambda a: _tool_get_agents(a, tenant_id),
        "get_policy_rules":      lambda a: _tool_get_policy_rules(a, tenant_id),
        "get_compliance_health": lambda a: _tool_get_compliance_health(a, tenant_id),
        "get_pending_reviews":   lambda a: _tool_get_pending_reviews(a, tenant_id),
        "explain_agent":         lambda a: _tool_explain_agent(a, tenant_id),
        "explain_decision":      lambda a: _tool_explain_decision(a, tenant_id),
        "propose_change":        lambda a: _tool_propose_change(a, tenant_id),
    }


_TOOL_DEFS = [
    {
        "name": "get_governance_stats",
        "description": "Get this tenant's governance statistics: total decisions, block rate, verdict breakdown, and top agents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Look-back window in hours (default 24)"},
            },
            "required": [],
        },
    },
    {
        "name": "query_audit_events",
        "description": "Query this tenant's recent audit events. Filter by agent, verdict, or time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours":    {"type": "integer",  "description": "Look-back hours (default 24)"},
                "agent_id": {"type": "string",   "description": "Filter by specific agent ID"},
                "verdict":  {"type": "string",   "description": "Filter: ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE"},
                "limit":    {"type": "integer",  "description": "Max events (default 20, max 50)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_agents",
        "description": "List all agents registered under this tenant with their stats, department, and block rates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "Filter by department name"},
                "status":     {"type": "string", "description": "Filter by status: active, paused, retired"},
            },
            "required": [],
        },
    },
    {
        "name": "get_policy_rules",
        "description": "List this tenant's custom policy rules (both enabled and disabled).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_compliance_health",
        "description": "Get this tenant's current compliance health status and regulatory coverage.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pending_reviews",
        "description": (
            "Get items currently waiting for human review/approval. "
            "Use this when the user asks what needs attention, what's pending, or what requires their review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max pending items to return (default 15)"},
            },
            "required": [],
        },
    },
    {
        "name": "explain_agent",
        "description": (
            "Explain what a specific agent has been doing based on its governance audit trail. "
            "Returns action frequency, block rate, recent blocks with reasons, and escalations. "
            "Use this when the user asks what an agent is doing, why it keeps getting blocked, "
            "or wants a summary of an agent's behaviour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The agent ID to explain"},
                "hours":    {"type": "integer", "description": "Look-back window in hours (default 24)"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "explain_decision",
        "description": "Explain exactly why a specific governance decision was made (looks up the full decision record).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "The action_id or decision_id to look up"},
            },
            "required": ["action_id"],
        },
    },
    {
        "name": "propose_change",
        "description": (
            "Suggest a governance change for the tenant to review and optionally apply. "
            "Use this when the user asks you to change, add, or update something. "
            "NEVER apply changes directly — always use this tool so the human can approve."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["add_policy_rule", "enable_rule", "disable_rule", "set_shadow_mode"],
                    "description": "The type of change to propose",
                },
                "description": {
                    "type": "string",
                    "description": "Plain-English description of what this change does",
                },
                "impact": {
                    "type": "string",
                    "description": "What will happen after the change is applied",
                },
                "regulation": {
                    "type": "string",
                    "description": "Relevant regulation (e.g. HIPAA §164.308(a)(4), SOC2 CC6.1)",
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "The data needed to apply the change. "
                        "For add_policy_rule: {name, action (ALLOW|BLOCK|ESCALATE), condition_tool, condition_op, description}. "
                        "For enable_rule / disable_rule: {rule_id}. "
                        "For set_shadow_mode: {enabled: true|false}."
                    ),
                },
            },
            "required": ["type", "description", "impact", "payload"],
        },
    },
]

_SYSTEM_BASE = """You are the EDON Governance Assistant — a per-tenant AI that helps teams understand and manage their AI governance setup.

You have two modes:
1. READ / EXPLAIN: Answer questions about audit events, agent behaviour, policy rules, compliance health, and governance decisions. Always call the relevant tool first — never guess numbers.
2. SUGGEST: When the user asks you to make a change (add a rule, block something, enable shadow mode, etc.), use the propose_change tool to submit a structured proposal. The human will review and click Apply — you must never modify data directly.

Key rules:
- Scope: You only see data for this tenant. Never reference other tenants.
- Accuracy: Always fetch data with tools before answering stats questions. Never invent numbers from memory.
- Suggestions: When proposing a rule, be specific about tool, operation, and action. Include the relevant regulation.
- Tone: Clear, direct, non-technical language. Avoid jargon. The user may be a compliance officer, not an engineer.
- If asked to do something you can't (e.g. delete an agent, change billing), say so clearly.
- Use the agent names and departments you know about this tenant — refer to agents by name, not just ID.

INLINE CITATIONS: When your answer references a specific decision, agent, or policy rule that you fetched from a tool, embed a citation tag inline so users can click to highlight it in the console. Format exactly: [ref:TYPE:ID]
- Decisions / audit events: [ref:DECISION:action_id_here]
- Agents: [ref:AGENT:agent_id_here]
- Policy rules: [ref:RULE:rule_id_here]
Example: "Agent acme-bot [ref:AGENT:acme-bot] was blocked [ref:DECISION:act-abc123] for scope violation."
Only cite items you actually retrieved via tools — never invent IDs.

Common reason codes (explain these in plain English when asked):
- SCOPE_VIOLATION: agent tried something outside its declared job
- RISK_TOO_HIGH: action was flagged as too dangerous
- LOOP_DETECTED: agent repeated the same action too many times
- NEED_CONFIRMATION: action needs a human to approve it
- DATA_EXFIL: agent tried to send data somewhere unauthorized
- OUT_OF_HOURS: action attempted outside permitted hours

RESPONSE STYLE — follow exactly:
- No markdown. No asterisks, no bold, no bullet-point stars, no # headers. Plain prose only.
- Never open with "As a governance assistant..." or any disclaimer about what you can or cannot do. Answer directly.
- Simple questions (a number, a status, a yes/no): 1-2 sentences maximum.
- Analysis or "why/what should I do" questions: 3-5 sentences maximum. No lists, no headers.
- When stating a number always name the time period (e.g. "in the last 24 hours", "over the past 7 days")."""


def _build_system(tenant_id: str) -> str:
    """Build a personalised system prompt from live tenant data + long-term memories."""
    try:
        snapshot = build_tenant_knowledge_snapshot(tenant_id)
    except Exception:
        snapshot = None

    if not snapshot:
        return _SYSTEM_BASE + "\n\n" + f"TENANT CONTEXT (tenant_id={tenant_id}):\n  No tenant snapshot available."

    return _SYSTEM_BASE + "\n\n" + render_tenant_knowledge_snapshot(snapshot)

_CITE_RE = re.compile(r'\[ref:(DECISION|AGENT|RULE):([^\]]+)\]')


def _extract_citations(text: str) -> list[dict]:
    return [{"type": t.lower(), "id": i} for t, i in _CITE_RE.findall(text)]


# ── Claude loop ────────────────────────────────────────────────────────────────

async def _run_assistant(
    question: str,
    tenant_id: str,
    conversation: list[dict],
    page_context: Optional[dict] = None,
) -> tuple[str, dict | None, list[dict]]:
    """Run Claude tool_use loop. Returns (answer_text, proposal | None, citations)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "ANTHROPIC_API_KEY is not configured on this server.", None, []

    handlers = _get_tool_handlers(tenant_id)
    messages = list(conversation)

    if page_context:
        ctx_json = json.dumps(page_context, default=str)[:2000]
        messages.append({"role": "user", "content": f"[PAGE CONTEXT — data currently visible to the user in the console]\n{ctx_json}"})
        messages.append({"role": "assistant", "content": "Understood. I'll use this page context to give more targeted answers."})

    messages.append({"role": "user", "content": question})

    pending_proposal: dict | None = None

    for _round in range(_MAX_TOOL_ROUNDS):
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_ANTHROPIC_API}/messages",
                headers={
                    "x-api-key":         api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      _MODEL,
                    "max_tokens": _MAX_TOKENS,
                    "system":     _build_system(tenant_id),
                    "tools":      _TOOL_DEFS,
                    "messages":   messages,
                },
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:300]}")

        data        = resp.json()
        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])

        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            for block in content:
                if block.get("type") == "text":
                    answer = block["text"]
                    return answer, pending_proposal, _extract_citations(answer)
            return "(no response)", pending_proposal, []

        if stop_reason != "tool_use":
            break

        tool_results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            tool_name   = block["name"]
            tool_input  = block.get("input", {})
            tool_use_id = block["id"]

            handler = handlers.get(tool_name)
            if handler:
                try:
                    result = handler(tool_input)
                except Exception as exc:
                    result = {"error": str(exc)}
                if tool_name == "propose_change" and isinstance(result, dict) and "proposal_id" in result:
                    prop_id = result["proposal_id"]
                    pending_proposal = _PENDING_PROPOSALS.get(prop_id)
            else:
                result = {"error": f"unknown tool: {tool_name}"}

            logger.info("[assistant] tenant=%s tool=%s", tenant_id, tool_name)

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return "I hit the tool call limit — please ask a more specific question.", pending_proposal, []


# ── Apply logic ────────────────────────────────────────────────────────────────

def _apply_proposal(proposal: dict, tenant_id: str) -> dict:
    change_type = proposal.get("type", "")
    payload     = proposal.get("payload", {})

    if change_type == "add_policy_rule":
        name   = payload.get("name", "Assistant-suggested rule")
        action = (payload.get("action") or "BLOCK").upper()
        if action not in ("ALLOW", "BLOCK", "ESCALATE"):
            action = "BLOCK"
        db = get_db()
        rule_id = db.create_policy_rule(
            tenant_id       = tenant_id,
            name            = name,
            action          = action,
            priority        = int(payload.get("priority", 50)),
            description     = payload.get("description") or proposal.get("description"),
            condition_tool  = payload.get("condition_tool") or None,
            condition_op    = payload.get("condition_op") or None,
            condition_risk_level = payload.get("condition_risk_level") or None,
            condition_tags  = payload.get("condition_tags") or None,
            enabled         = True,
        )
        return {"applied": True, "rule_id": rule_id, "name": name}

    if change_type in ("enable_rule", "disable_rule"):
        rule_id = payload.get("rule_id", "")
        if not rule_id:
            raise ValueError("rule_id required for enable_rule / disable_rule")
        db      = get_db()
        enabled = change_type == "enable_rule"
        db.update_policy_rule(rule_id, tenant_id, enabled=enabled)
        return {"applied": True, "rule_id": rule_id, "enabled": enabled}

    if change_type == "set_shadow_mode":
        enabled = bool(payload.get("enabled", False))
        db = get_db()
        if hasattr(db, "set_shadow_mode"):
            db.set_shadow_mode(tenant_id, enabled)
        return {"applied": True, "shadow_mode": enabled}

    raise ValueError(f"Unsupported proposal type: {change_type}")


# ── Routes ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation: list[dict] = []
    page_context: Optional[dict] = None
    conversation_id: Optional[str] = None  # client-generated; persists across messages


class ApplyRequest(BaseModel):
    proposal: dict


class ExplainRequest(BaseModel):
    type: str  # "decision" | "agent" | "rule"
    id: str


class MemoryReviewRequest(BaseModel):
    reviewed_by: str
    review_status: str = "approved"


class MemoryExpiryRequest(BaseModel):
    updated_by: str
    expires_at: Optional[str] = None


class MemoryPinRequest(BaseModel):
    updated_by: str
    pinned: bool = True


class MemoryForgetRequest(BaseModel):
    requested_by: str
    reason: Optional[str] = None


async def _run_assistant_stream(
    question: str,
    tenant_id: str,
    conversation: list[dict],
    page_context: Optional[dict] = None,
):
    """Streaming generator. Yields dicts serialised as SSE data lines.

    Events:
      {"delta": "text chunk"}          — incremental text token
      {"done": true, "suggestion": …, "citations": […]}  — final metadata
      {"error": "message"}             — fatal error
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield {"delta": "ANTHROPIC_API_KEY is not configured on this server."}
        yield {"done": True, "suggestion": None, "citations": []}
        return

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    handlers = _get_tool_handlers(tenant_id)
    messages = list(conversation)

    if page_context:
        ctx_json = json.dumps(page_context, default=str)[:2000]
        messages.append({"role": "user", "content": f"[PAGE CONTEXT — data currently visible to the user in the console]\n{ctx_json}"})
        messages.append({"role": "assistant", "content": "Understood. I'll use this page context to give more targeted answers."})

    messages.append({"role": "user", "content": question})

    pending_proposal: dict | None = None
    full_answer = ""

    for _round in range(_MAX_TOOL_ROUNDS):
        content_blocks: list[dict] = []
        current_block: dict | None = None
        stop_reason: str | None = None

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{_ANTHROPIC_API}/messages",
                headers=headers,
                json={
                    "model":      _MODEL,
                    "max_tokens": _MAX_TOKENS,
                    "system":     _build_system(tenant_id),
                    "tools":      _TOOL_DEFS,
                    "messages":   messages,
                    "stream":     True,
                },
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {"error": f"Claude API error {resp.status_code}: {body[:200].decode(errors='replace')}"}
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except Exception:
                        continue

                    etype = event.get("type")

                    if etype == "content_block_start":
                        block = event.get("content_block", {})
                        current_block = {
                            "type":       block.get("type"),
                            "text":       "",
                            "id":         block.get("id", ""),
                            "name":       block.get("name", ""),
                            "input_json": "",
                        }
                        content_blocks.append(current_block)

                    elif etype == "content_block_delta" and current_block:
                        delta = event.get("delta", {})
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            chunk = delta.get("text", "")
                            current_block["text"] += chunk
                            full_answer += chunk
                            if chunk:
                                yield {"delta": chunk}
                        elif dtype == "input_json_delta":
                            current_block["input_json"] += delta.get("partial_json", "")

                    elif etype == "content_block_stop":
                        if current_block and current_block["type"] == "tool_use":
                            try:
                                current_block["input"] = json.loads(current_block["input_json"] or "{}")
                            except Exception:
                                current_block["input"] = {}
                        current_block = None

                    elif etype == "message_delta":
                        stop_reason = event.get("delta", {}).get("stop_reason")

        # Rebuild content list for conversation history
        api_content = []
        for block in content_blocks:
            if block["type"] == "text":
                api_content.append({"type": "text", "text": block["text"]})
            elif block["type"] == "tool_use":
                api_content.append({
                    "type":  "tool_use",
                    "id":    block["id"],
                    "name":  block["name"],
                    "input": block.get("input", {}),
                })
        messages.append({"role": "assistant", "content": api_content})

        if stop_reason == "end_turn":
            yield {"done": True, "suggestion": pending_proposal, "citations": _extract_citations(full_answer)}
            return

        if stop_reason != "tool_use":
            break

        # Execute tool calls
        _TOOL_LABELS = {
            "get_governance_stats":  "Fetching governance stats",
            "query_audit_events":    "Querying audit events",
            "get_agents":            "Loading agents",
            "get_policy_rules":      "Loading policy rules",
            "get_compliance_health": "Checking compliance health",
            "get_pending_reviews":   "Fetching pending reviews",
            "explain_agent":         "Analysing agent activity",
            "explain_decision":      "Looking up decision",
            "propose_change":        "Drafting proposal",
        }
        tool_names_called = [b["name"] for b in content_blocks if b.get("type") == "tool_use"]
        if tool_names_called:
            label = _TOOL_LABELS.get(tool_names_called[0], "Looking up data")
            yield {"thinking": label}

        tool_results = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_name   = block["name"]
            tool_input  = block.get("input", {})
            tool_use_id = block["id"]
            handler = handlers.get(tool_name)
            if handler:
                try:
                    result = handler(tool_input)
                except Exception as exc:
                    result = {"error": str(exc)}
                if tool_name == "propose_change" and isinstance(result, dict) and "proposal_id" in result:
                    pending_proposal = _PENDING_PROPOSALS.get(result["proposal_id"])
            else:
                result = {"error": f"unknown tool: {tool_name}"}
            logger.info("[assistant/stream] tenant=%s tool=%s", tenant_id, tool_name)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    yield {"done": True, "suggestion": pending_proposal, "citations": _extract_citations(full_answer)}


@router.post("/chat/stream")
async def assistant_chat_stream(req: ChatRequest, request: Request):
    """Streaming version of /chat. Returns Server-Sent Events.

    Events: {"delta": "text"} incremental tokens, then {"done": true, ...} metadata.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is empty")

    conv_id = req.conversation_id or f"conv_{uuid.uuid4().hex}"
    # Build updated message list (prior history + this user turn; AI turn appended after)
    updated_messages = list(req.conversation) + [{"role": "user", "content": req.message}]

    async def generate():
        full_answer = ""
        try:
            async for event in _run_assistant_stream(
                req.message, tenant_id, req.conversation, req.page_context
            ):
                if event.get("delta"):
                    full_answer += event["delta"]
                if event.get("done"):
                    # Persist conversation + fire memory extraction in background
                    final_messages = updated_messages + [{"role": "assistant", "content": full_answer}]
                    _title = req.message[:60] if not req.conversation else None
                    try:
                        get_db().save_conversation(conv_id, tenant_id, final_messages, title=_title)
                    except Exception as _se:
                        logger.warning("[assistant] save_conversation failed: %s", _se)
                    if len(final_messages) >= 4:
                        asyncio.create_task(_background_extract(conv_id, tenant_id, final_messages))
                    yield f"data: {json.dumps({**event, 'conversation_id': conv_id})}\n\n"
                    return
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.error("[assistant/stream] error tenant=%s: %s", tenant_id, exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _background_extract(conversation_id: str, tenant_id: str, messages: list) -> None:
    try:
        from ..ai.memory_extractor import extract_memories
        await extract_memories(conversation_id, tenant_id, messages)
    except Exception as exc:
        logger.warning("[assistant] background memory extraction failed: %s", exc)


@router.post("/chat")
async def assistant_chat(req: ChatRequest, request: Request):
    """Send a message to your Governance Assistant.

    Returns an answer (Mode 1) or an answer + suggestion card (Mode 2).
    Pass prior turns in `conversation` for multi-turn context.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is empty")

    try:
        answer, proposal, citations = await _run_assistant(
            req.message, tenant_id, req.conversation, req.page_context
        )
    except Exception as exc:
        logger.error("[assistant] chat error tenant=%s: %s", tenant_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"answer": answer, "suggestion": proposal, "citations": citations}


@router.get("/conversations")
async def list_conversations(request: Request):
    """List this tenant's past AI conversations (metadata only, no messages)."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    try:
        convs = get_db().get_conversations(tenant_id, limit=30)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"conversations": convs}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request):
    """Load a specific past conversation including its messages."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    conv = get_db().get_conversation(conversation_id, tenant_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/memories")
async def list_memories(request: Request):
    """Return all durable memories extracted for this tenant."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    try:
        memories = get_db().get_memories(tenant_id, limit=60)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"memories": memories, "count": len(memories)}


@router.get("/tenant-context")
async def get_tenant_context(request: Request):
    """Return the canonical tenant knowledge snapshot used by the assistant."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    try:
        snapshot = build_tenant_knowledge_snapshot(tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return snapshot.as_dict()


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    memory = get_db().get_memory(memory_id, tenant_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("/memories/{memory_id}/pin")
async def pin_memory(memory_id: str, request: Request, body: MemoryPinRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    updated = get_db().pin_memory(memory_id, tenant_id, pinned=body.pinned)
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory_id": memory_id, "pinned": body.pinned, "updated_by": body.updated_by}


@router.post("/memories/{memory_id}/review")
async def review_memory(memory_id: str, request: Request, body: MemoryReviewRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    try:
        updated = get_db().review_memory(memory_id, tenant_id, body.review_status, body.reviewed_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "ok": True,
        "memory_id": memory_id,
        "review_status": body.review_status,
        "reviewed_by": body.reviewed_by,
    }


@router.post("/memories/{memory_id}/expire")
async def expire_memory(memory_id: str, request: Request, body: MemoryExpiryRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    updated = get_db().expire_memory(memory_id, tenant_id, expires_at=body.expires_at)
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory_id": memory_id, "expires_at": body.expires_at, "updated_by": body.updated_by}


@router.post("/memories/{memory_id}/forget")
async def forget_memory(memory_id: str, request: Request, body: MemoryForgetRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    removed = get_db().forget_memory(memory_id, tenant_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "ok": True,
        "memory_id": memory_id,
        "requested_by": body.requested_by,
        "reason": body.reason,
    }


@router.post("/apply")
async def assistant_apply(req: ApplyRequest, request: Request):
    """Apply a suggestion that the assistant proposed.

    The tenant must explicitly call this — the assistant never applies changes directly.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    proposal = req.proposal
    if not proposal or not proposal.get("type"):
        # Try loading from DB by proposal_id if the caller sent only an ID
        pid = (req.proposal or {}).get("proposal_id", "")
        if pid:
            try:
                proposal = get_db().get_assistant_proposal(pid, tenant_id) or {}
            except Exception:
                proposal = {}
    if not proposal or not proposal.get("type"):
        raise HTTPException(status_code=400, detail="proposal.type is required")

    # Guard: proposal must belong to this tenant
    if proposal.get("tenant_id") and proposal["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Proposal tenant mismatch")

    try:
        result = _apply_proposal(proposal, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[assistant] apply error tenant=%s: %s", tenant_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    logger.info("[assistant] applied proposal type=%s tenant=%s", proposal.get("type"), tenant_id)
    return result


@router.post("/explain")
async def assistant_explain(req: ExplainRequest, request: Request):
    """Return AI reasoning for a specific governance item (decision, agent, rule).

    Called when a user clicks a citation badge in the console to open the aside panel.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    item_type = req.type.lower()
    if item_type not in ("decision", "agent", "rule"):
        raise HTTPException(status_code=400, detail=f"Unknown type: {req.type}")

    handlers = _get_tool_handlers(tenant_id)

    if item_type == "decision":
        raw = handlers["explain_decision"]({"action_id": req.id})
        prompt = (
            f"A user clicked on a specific governance decision to understand it better. "
            f"Explain in 3-5 clear sentences what happened and why, using plain English. "
            f"Decision data: {json.dumps(raw, default=str)}"
        )
    elif item_type == "agent":
        raw = handlers["explain_agent"]({"agent_id": req.id, "hours": 48})
        prompt = (
            f"A user clicked on an agent to understand what it's been doing. "
            f"Give a 3-5 sentence plain-English summary covering its activity, block rate, and any issues. "
            f"Agent data: {json.dumps(raw, default=str)}"
        )
    else:  # rule
        raw = handlers["get_policy_rules"]({})
        rules = raw.get("rules", [])
        rule = next((r for r in rules if r.get("rule_id") == req.id), {})
        prompt = (
            f"A user clicked on a policy rule to understand it. "
            f"Explain in 2-3 sentences what this rule does and why it matters. "
            f"Rule data: {json.dumps(rule or {'rule_id': req.id}, default=str)}"
        )

    try:
        answer, _, _ = await _run_assistant(prompt, tenant_id, [])
    except Exception as exc:
        logger.error("[assistant] explain error tenant=%s type=%s id=%s: %s", tenant_id, item_type, req.id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"type": item_type, "id": req.id, "explanation": answer}
