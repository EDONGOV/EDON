"""
Observation hooks — lightweight "did this work?" checks after tool execution.
Enables self-correction, retry logic, confidence scoring.
"""

from typing import Dict, Any, Optional

def observe(
    tool: str,
    op: str,
    execution_result: Dict[str, Any],
    params: Dict[str, Any],
    tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Run a lightweight verification after successful execution. Returns observation dict or None.
    """
    if not execution_result or execution_result.get("error"):
        return None
    result_inner = execution_result.get("result") or execution_result

    # Gmail send: confirm message ID (we already have it in result; just structure as observation)
    if tool == "gmail" and op == "send":
        if result_inner.get("success") and result_inner.get("id"):
            return {
                "verified": True,
                "message_id": result_inner.get("id"),
                "thread_id": result_inner.get("threadId"),
                "note": "Message created; ID confirmed.",
            }
        return {"verified": False, "note": "No message_id in result."}

    # Google Calendar create: confirm event ID and link
    if tool == "google_calendar" and op == "create_event":
        if result_inner.get("success") and result_inner.get("id"):
            return {
                "verified": True,
                "event_id": result_inner.get("id"),
                "html_link": result_inner.get("htmlLink"),
                "summary": result_inner.get("summary"),
                "note": "Event created; ID and link confirmed.",
            }
        return {"verified": bool(result_inner.get("success")), "note": "Create result only."}

    # GitHub create_issue: we have html_url; optional re-fetch for full state
    if tool == "github" and op == "create_issue":
        if result_inner.get("success") and result_inner.get("number"):
            return {
                "verified": True,
                "issue_number": result_inner.get("number"),
                "html_url": result_inner.get("html_url"),
                "state": result_inner.get("state"),
                "note": "Issue created; link confirmed.",
            }
        return {"verified": False, "note": "No issue number in result."}

    return None
