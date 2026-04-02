"""Schema definitions for /v1/action REST API endpoint.

This module defines the request and response schemas for the /v1/action endpoint,
which is the primary interface for agent action evaluation and governance.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, Optional, Literal, List


class V1ActionRequest(BaseModel):
    """Request schema for /v1/action endpoint.

    This is the primary request format for agents to submit actions for evaluation.
    All fields are required for proper governance and audit trail.
    """
    agent_id: str = Field(
        ...,
        description="Unique identifier for the agent making the request",
        min_length=1,
        example="agent_123"
    )
    action_type: str = Field(
        ...,
        description="Type of action being requested (e.g., 'email.send', 'file.read')",
        min_length=1,
        example="email.send"
    )
    action_payload: Dict[str, Any] = Field(
        ...,
        description="Action-specific parameters and data",
        example={
            "recipients": ["user@example.com"],
            "subject": "Test email",
            "body": "This is a test"
        }
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp when action was requested",
        example="2026-02-24T10:30:00Z"
    )
    device_id: Optional[str] = Field(
        None,
        description="Physical device ID being commanded (e.g. 'sr-001'). "
                    "When present, EDON enforces agent-device binding and mutex lock.",
        example="sr-001",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context about the action (optional)",
        example={
            "intent_id": "intent_xyz",
            "user_confirmed": False,
            "risk_estimate": "low"
        }
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "agent_id": "agent_123",
            "action_type": "email.send",
            "action_payload": {
                "recipients": ["user@example.com"],
                "subject": "Monthly Report",
                "body": "Please find the report attached."
            },
            "timestamp": "2026-02-24T10:30:00Z",
            "context": {
                "intent_id": "intent_monthly_reports",
                "user_confirmed": False
            }
        }
    })


DecisionType = Literal["ALLOW", "BLOCK", "DEGRADE", "HUMAN_REQUIRED", "ESCALATE", "PAUSE"]


class V1ActionResponse(BaseModel):
    """Response schema for /v1/action endpoint.

    Returns the governance decision and metadata about the evaluation.
    """
    action_id: str = Field(
        ...,
        description="Unique identifier for this action (for audit trail)",
        example="act_abc123def456"
    )
    decision: DecisionType = Field(
        ...,
        description="Governance decision: ALLOW, BLOCK, DEGRADE, HUMAN_REQUIRED, ESCALATE, or PAUSE"
    )
    decision_reason: str = Field(
        ...,
        description="Human-readable explanation of the decision",
        example="Action approved: within scope, constraints satisfied, risk acceptable"
    )
    policy_version: Optional[str] = Field(
        None,
        description="Version of the policy used for evaluation",
        example="1.0.0"
    )
    processing_latency_ms: int = Field(
        ...,
        description="Time taken to evaluate the action in milliseconds",
        ge=0,
        example=45
    )
    # Additional fields for richer responses
    reason_code: Optional[str] = Field(
        None,
        description="Machine-readable reason code for the decision",
        example="APPROVED"
    )
    safe_alternative: Optional[Dict[str, Any]] = Field(
        None,
        description="Alternative action if decision is DEGRADE",
        example={
            "action_type": "email.draft",
            "action_payload": {
                "recipients": ["user@example.com"],
                "subject": "Monthly Report",
                "body": "Please find the report attached."
            }
        }
    )
    escalation_question: Optional[str] = Field(
        None,
        description="Question to ask user if decision is ESCALATE or HUMAN_REQUIRED",
        example="Send email to 50 recipients? (max allowed: 10)"
    )
    escalation_options: Optional[list] = Field(
        None,
        description="Options for user to choose from if decision is ESCALATE",
        example=[
            {"id": "allow_once", "label": "Allow once"},
            {"id": "draft_only", "label": "Save as draft only"}
        ]
    )
    predicted_oob_risk: Optional[float] = Field(
        None,
        description="Predicted out-of-bounds risk score (0.0-1.0) when available",
        ge=0.0,
        le=1.0,
        example=0.87,
    )
    predicted_oob_reasons: Optional[List[str]] = Field(
        None,
        description="Human-readable reasons that contributed to predicted_oob_risk",
        example=["tool/op not seen in agent 30-day baseline", "agent action-rate spike vs 30-day baseline"],
    )
    predicted_oob_breakdown: Optional[Dict[str, float]] = Field(
        None,
        description="Signal-level weighted contributions used to compute predicted_oob_risk",
        example={"fleet_prior": 0.12, "estimated_risk": 0.08, "novelty": 0.2},
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "action_id": "act_abc123def456",
            "decision": "ALLOW",
            "decision_reason": "Action approved: within scope, constraints satisfied, risk acceptable",
            "policy_version": "1.0.0",
            "processing_latency_ms": 45,
            "reason_code": "APPROVED"
        }
    })
