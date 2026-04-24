"""Schema definitions for EDON Guard."""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tool(str, Enum):
    """Tool enumeration."""
    EMAIL = "email"
    SHELL = "shell"
    CALENDAR = "calendar"
    FILE = "file"
    CLAWDBOT = "clawdbot"
    # Super-agent integrations (Clawdbot/Telegram)
    BRAVE_SEARCH = "brave_search"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"
    ELEVENLABS = "elevenlabs"
    GITHUB = "github"
    GEMINI = "gemini"
    POLYGON = "polygon"
    FMP = "fmp"
    NEWSAPI = "newsapi"
    HOME_ASSISTANT = "home_assistant"
    MEMORY = "memory"
    AGENT = "agent"
    # Consumer / productivity agents
    BROWSER = "browser"
    SLACK = "slack"
    DISCORD = "discord"
    TWITTER = "twitter"
    NOTION = "notion"
    DATABASE = "database"
    HTTP = "http"
    # Physical autonomous systems (FedEx / logistics)
    ROBOT = "robot"
    VEHICLE = "vehicle"
    CONVEYOR = "conveyor"
    FORKLIFT = "forklift"
    DRONE = "drone"
    SCANNER = "scanner"
    SORTER = "sorter"
    DOCK = "dock"
    GATE = "gate"
    SENSOR = "sensor"
    # Catch-all for tenant-defined custom tools
    CUSTOM = "custom"


class ActionSource(str, Enum):
    """Action source enumeration."""
    AGENT = "agent"
    USER = "user"
    CLAWDBOT = "clawdbot"


class Verdict(str, Enum):
    """Governance verdict."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    DEGRADE = "DEGRADE"
    PAUSE = "PAUSE"
    ERROR = "ERROR"



class ReasonCode(str, Enum):
    """Decision reason code."""
    # Approval reasons
    APPROVED = "APPROVED"
    
    # Block reasons
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    DATA_EXFIL = "DATA_EXFIL"
    OUT_OF_HOURS = "OUT_OF_HOURS"
    INTENT_MISMATCH = "INTENT_MISMATCH"  # For blocking due to intent mismatch
    
    # Escalation reasons
    NEED_CONFIRMATION = "NEED_CONFIRMATION"
    
    # Degrade reasons
    DEGRADED_TO_SAFE_ALTERNATIVE = "DEGRADED_TO_SAFE_ALTERNATIVE"
    
    # Pause reasons
    LOOP_DETECTED = "LOOP_DETECTED"
    RATE_LIMIT = "RATE_LIMIT"

    # Fail-safe / internal policy errors
    POLICY_ENGINE_ERROR = "POLICY_ENGINE_ERROR"


@dataclass
class IntentContract:
    """Intent contract defining objective, scope, and constraints."""
    objective: str
    scope: Dict[str, List[str]]  # tool -> allowed_ops
    constraints: Dict[str, Any]  # e.g., work_hours_only, no_external_sharing, etc.
    risk_level: RiskLevel
    approved_by_user: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # TTL and revocation — checked on every evaluate call (INV-006-INTENT-FRESH)
    expires_at: Optional[datetime] = None
    revoked: bool = False

    def allows_tool_op(self, tool: str, op: str) -> bool:
        """Check if tool+op is allowed in scope."""
        if tool not in self.scope:
            return False
        return op in self.scope[tool]


@dataclass
class Action:
    """Agent action proposal."""
    tool: Tool
    op: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    params: Dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: ActionSource = ActionSource.AGENT
    tags: List[str] = field(default_factory=list)
    estimated_blast_radius: int = 0
    estimated_risk: RiskLevel = RiskLevel.LOW
    computed_risk: Optional[RiskLevel] = None  # Server-side computed risk
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "tool": self.tool.value,
            "op": self.op,
            "params": self.params,
            "requested_at": self.requested_at.isoformat(),
            "source": self.source.value,
            "tags": self.tags,
            "estimated_blast_radius": self.estimated_blast_radius,
            "estimated_risk": self.estimated_risk.value,
            "computed_risk": self.computed_risk.value if self.computed_risk else None,
        }


@dataclass
class Decision:
    """Governance decision."""
    verdict: Verdict
    reason_code: ReasonCode
    explanation: str
    safe_alternative: Optional[Action] = None
    required_confirmation: bool = False
    policy_version: str = "1.0.0"
    escalation_question: Optional[str] = None
    escalation_options: Optional[List[Dict[str, str]]] = None
    policy_snapshot_hash: Optional[str] = None
    invariant_results: List[Dict[str, Any]] = field(default_factory=list)
    policy_rule_id: Optional[str] = None
    # Internal metadata (e.g. MAG signal). Not part of the public API response
    # but available to routes for enriching audit context.
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "verdict": self.verdict.value,
            "reason_code": self.reason_code.value,
            "explanation": self.explanation,
            "safe_alternative": self.safe_alternative.to_dict() if self.safe_alternative else None,
            "required_confirmation": self.required_confirmation,
            "policy_version": self.policy_version,
            "escalation_question": self.escalation_question,
            "escalation_options": self.escalation_options,
            "policy_snapshot_hash": self.policy_snapshot_hash,
            "invariant_results": self.invariant_results,
            "policy_rule_id": self.policy_rule_id,
            "meta": self.meta,
        }


@dataclass
class AuditEvent:
    """Audit log event."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    action: Optional[Action] = None
    decision: Optional[Decision] = None
    intent_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.to_dict() if self.action else None,
            "decision": self.decision.to_dict() if self.decision else None,
            "intent_id": self.intent_id,
            "context": self.context,
        }
