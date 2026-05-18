"""Extract durable tenant memories from completed AI conversations.

After each conversation ends, this module calls Claude to distill the
exchange into structured facts — agent issues, preferences, compliance
concerns, applied changes — that are injected into every future session.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import httpx

from ..logging_config import get_logger
from ..persistence import get_db

logger = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap for extraction
_ANTHROPIC_API = "https://api.anthropic.com/v1"

_CATEGORIES = {
    "agent_behavior":   "Patterns in how specific agents behave — what they do, what gets blocked, recurring issues",
    "preference":       "How this tenant wants things handled — tone, escalation thresholds, preferred actions",
    "compliance_focus": "Which regulations they care about most and why",
    "recurring_issue":  "Problems that come up repeatedly across conversations",
    "applied_change":   "Policy rules or settings that were actually applied through the assistant",
    "open_question":    "Something the user asked about but wasn't fully resolved — follow up next time",
}

_EXTRACT_PROMPT = """You are a memory extraction system for an AI governance assistant.

Read the following conversation between a tenant and their governance AI. Extract durable facts that would help the AI serve this tenant better in future conversations.

Focus ONLY on facts that:
- Are specific to this tenant (not generic governance knowledge)
- Would still be relevant weeks from now
- Would change how the AI responds to future questions

Categories to extract (use exactly these category keys):
{categories}

Return a JSON object with a single key "memories" containing an array. Each memory:
{{
  "category": "<one of the category keys above>",
  "fact": "<one clear sentence, max 120 chars, specific enough to be actionable>",
  "confidence": <0.5–1.0, higher = more certain this is durable>
}}

Extract 0–8 memories. If the conversation has no durable facts worth remembering, return {{"memories": []}}.
Do NOT extract: generic questions, one-off lookups, anything the AI already knows from live data.

Conversation:
{conversation}"""


async def extract_memories(
    conversation_id: str,
    tenant_id: str,
    messages: list[dict],
) -> list[dict[str, Any]]:
    """Call Claude to extract memories from a completed conversation.

    Returns list of memory dicts with category/fact/confidence.
    Saves extracted memories to DB. Safe to call multiple times (upserts by deterministic ID).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []

    # Only extract from conversations with actual exchanges (at least one user + one AI turn)
    user_turns = [m for m in messages if m.get("role") == "user"]
    assistant_turns = [m for m in messages if m.get("role") == "assistant"]
    if len(user_turns) < 1 or len(assistant_turns) < 1:
        return []

    # Build readable transcript (skip greeting message)
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            # Strip tool call blocks, keep only text
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        if not content or content.startswith("[PAGE CONTEXT"):
            continue
        lines.append(f"{role.upper()}: {content[:400]}")

    if not lines:
        return []

    transcript = "\n".join(lines[:60])  # cap at 60 turns
    categories_text = "\n".join(f'  "{k}": {v}' for k, v in _CATEGORIES.items())
    prompt = _EXTRACT_PROMPT.format(categories=categories_text, conversation=transcript)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_ANTHROPIC_API}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            logger.warning("[memory] extraction API error %s", resp.status_code)
            return []

        data = resp.json()
        raw = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                raw = block["text"]
                break

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        extracted = json.loads(raw).get("memories", [])
    except Exception as exc:
        logger.warning("[memory] extraction failed for conversation %s: %s", conversation_id, exc)
        return []

    if not extracted:
        return []

    db = get_db()
    saved = []
    for mem in extracted:
        category = mem.get("category", "").strip()
        fact = (mem.get("fact") or "").strip()[:200]
        confidence = float(mem.get("confidence", 1.0))
        if not category or not fact or category not in _CATEGORIES:
            continue

        # Deterministic ID: hash of tenant + category + fact so duplicates upsert cleanly
        mem_id = "mem_" + hashlib.sha1(f"{tenant_id}:{category}:{fact}".encode()).hexdigest()[:16]
        try:
            db.upsert_memory(
                memory_id=mem_id,
                tenant_id=tenant_id,
                category=category,
                fact=fact,
                confidence=confidence,
                source_conversation_id=conversation_id,
            )
            saved.append({"id": mem_id, "category": category, "fact": fact, "confidence": confidence})
        except Exception as exc:
            logger.warning("[memory] DB upsert failed: %s", exc)

    if saved:
        logger.info("[memory] extracted %d memories for tenant %s from conversation %s",
                    len(saved), tenant_id, conversation_id)
    return saved
