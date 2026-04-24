"""Schemas for /v1/action/result endpoint."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

OutcomeType = Literal["success", "failure", "partial", "timeout"]


class ActionResultRequest(BaseModel):
    """Posted by an agent after executing a tool action.

    The action_id field must match the action_id returned by the preceding
    /v1/action call. This closes the loop so EDON can correlate governance
    decisions with real execution outcomes.
    """

    action_id: str = Field(
        ...,
        description="The action_id returned by the /v1/action response for this execution",
        example="dec-abc123",
    )
    agent_id: str = Field(
        ...,
        description="Agent that executed the action",
        example="agent_crm_sync",
    )
    action_type: str = Field(
        ...,
        description="The action type that was executed (e.g. 'email.send')",
        example="email.send",
    )
    outcome: OutcomeType = Field(
        ...,
        description="Execution outcome: success | failure | partial | timeout",
        example="success",
    )
    latency_ms: int = Field(
        ...,
        description="Tool execution time in milliseconds (not governance latency)",
        ge=0,
        example=340,
    )
    executed_at: str = Field(
        ...,
        description="ISO-8601 timestamp when tool execution completed",
        example="2026-04-11T12:00:00Z",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if outcome is failure or timeout (max 1000 chars, enforced server-side)",
    )
    result_summary: Optional[str] = Field(
        None,
        description=(
            "Optional sanitized one-line description of what happened. "
            "Do NOT include PII, credentials, or full response bodies. "
            "Max 500 chars, enforced server-side."
        ),
    )
    result_payload: Optional[dict] = Field(
        None,
        description=(
            "Optional structured tool response for observation verification "
            "(e.g. {\"id\": \"msg_123\"} for email.send). Omit PII and large blobs."
        ),
    )
    goal_context: Optional[str] = Field(
        None,
        description=(
            "Optional description of what success looks like for this action, "
            "used to score goal achievement. E.g. 'summarise cardiology patients for care team'. "
            "Max 300 chars."
        ),
        max_length=300,
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "action_id": "dec-abc123",
            "agent_id": "agent_crm_sync",
            "action_type": "email.send",
            "outcome": "success",
            "latency_ms": 340,
            "executed_at": "2026-04-11T12:00:00Z",
            "error": None,
            "result_summary": "Email delivered to 3 recipients",
        }
    })


class ActionResultResponse(BaseModel):
    """Confirmation returned after recording an action result."""

    result_id: str = Field(..., description="Unique ID assigned to this result record")
    action_id: str = Field(..., description="The action_id that was correlated")
    recorded: bool = Field(..., description="Whether the result was persisted")
    outcome: OutcomeType = Field(..., description="Echo of the recorded outcome")
