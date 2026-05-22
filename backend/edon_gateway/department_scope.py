"""Department-scoped access helpers for console/API routes."""

from __future__ import annotations

import json
from typing import Any, Optional

GLOBAL_ROLES = {"admin", "super_admin", "governance_admin", "security_admin", "auditor"}


def get_department_scope(request) -> Optional[str]:
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    role = tenant_info.get("role", "viewer")
    department = (tenant_info.get("department") or "").strip()
    if role in GLOBAL_ROLES or not department:
        return None
    return department


def event_department(event: dict[str, Any], *, db=None, tenant_id: Optional[str] = None) -> Optional[str]:
    context = event.get("context") or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            context = {}
    if isinstance(context, dict):
        dept = context.get("department") or context.get("actor_department")
        if dept:
            return str(dept)

    action = event.get("action") or {}
    if isinstance(action, str):
        try:
            action = json.loads(action)
        except Exception:
            action = {}
    if isinstance(action, dict):
        params = action.get("params") or {}
        if isinstance(params, dict) and params.get("department"):
            return str(params["department"])

    agent_id = event.get("agent_id")
    if db is not None and tenant_id and agent_id and hasattr(db, "get_agent"):
        try:
            agent = db.get_agent(agent_id, tenant_id=tenant_id)
            if agent and agent.get("department"):
                return str(agent["department"])
        except Exception:
            return None
    return None


def filter_events_for_department(events: list[dict[str, Any]], *, department: Optional[str], db=None, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    if not department:
        return events
    return [
        event
        for event in events
        if event_department(event, db=db, tenant_id=tenant_id) == department
    ]


def record_department(record: dict[str, Any]) -> Optional[str]:
    for key in ("department", "actor_department"):
        value = record.get(key)
        if value:
            return str(value)
    meta = record.get("meta") or record.get("metadata") or {}
    if isinstance(meta, dict):
        for key in ("department", "actor_department"):
            value = meta.get(key)
            if value:
                return str(value)
    action = record.get("action") or {}
    if isinstance(action, dict):
        params = action.get("params") or {}
        if isinstance(params, dict) and params.get("department"):
            return str(params["department"])
    return None


def department_allowed(request, record_department_value: Optional[str]) -> bool:
    department = get_department_scope(request)
    return not department or record_department_value == department
