"""Policy rules and configurations."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from .schemas import Tool, RiskLevel


@dataclass
class PolicyConfig:
    """Policy configuration."""
    # Rate limiting
    max_actions_per_minute: int = 30
    
    # Loop detection
    loop_detection_window_seconds: int = 60
    loop_detection_threshold: int = 5  # Same action N times in window
    
    # Work hours (24-hour format)
    work_hours_start: int = 8  # 8 AM
    work_hours_end: int = 18  # 6 PM
    
    # Risk thresholds
    auto_allow_risk_levels: Optional[Set[RiskLevel]] = None  # Risk levels that auto-allow
    escalate_risk_levels: Optional[Set[RiskLevel]] = None  # Risk levels that require escalation

    # Dangerous operations (always block)
    dangerous_shell_commands: Optional[Set[str]] = None

    # Data exfiltration patterns
    external_sharing_patterns: Optional[List[str]] = None  # Patterns that indicate external sharing

    def __post_init__(self):
        """Initialize default sets."""
        # Env overrides for production tuning
        try:
            if os.getenv("EDON_MAX_ACTIONS_PER_MINUTE"):
                self.max_actions_per_minute = int(os.getenv("EDON_MAX_ACTIONS_PER_MINUTE") or 30)
            if os.getenv("EDON_LOOP_DETECTION_WINDOW_SECONDS"):
                self.loop_detection_window_seconds = int(os.getenv("EDON_LOOP_DETECTION_WINDOW_SECONDS") or 60)
            if os.getenv("EDON_LOOP_DETECTION_THRESHOLD"):
                self.loop_detection_threshold = int(os.getenv("EDON_LOOP_DETECTION_THRESHOLD") or 5)
        except ValueError:
            # Ignore invalid overrides; keep defaults
            pass
        if self.auto_allow_risk_levels is None:
            self.auto_allow_risk_levels = {RiskLevel.LOW}
        
        if self.escalate_risk_levels is None:
            self.escalate_risk_levels = {RiskLevel.HIGH, RiskLevel.CRITICAL}
        
        if self.dangerous_shell_commands is None:
            self.dangerous_shell_commands = {
                "rm -rf",
                "format",
                "del /f /s /q",
                "shutdown",
                "reboot",
            }
        
        if self.external_sharing_patterns is None:
            self.external_sharing_patterns = [
                "export",
                "upload",
                "share",
                "send_to",
                "external",
            ]


class PolicyEngine:
    """Policy evaluation engine."""
    
    def __init__(self, config: Optional["PolicyConfig"] = None):
        """Initialize policy engine."""
        self.config = config or PolicyConfig()
        self.action_history: List[tuple] = []  # (timestamp, tool, op, params_hash)
    
    def is_work_hours(self, timestamp) -> bool:
        """Check if timestamp is within work hours."""
        hour = timestamp.hour
        return self.config.work_hours_start <= hour < self.config.work_hours_end
    
    def check_rate_limit(self, current_time) -> bool:
        """Check if rate limit is exceeded."""
        cutoff_time = current_time.timestamp() - 60  # Last minute
        recent_actions = [
            ts for ts, _, _, _ in self.action_history
            if ts >= cutoff_time
        ]
        return len(recent_actions) >= self.config.max_actions_per_minute
    
    def detect_loop(self, tool: Tool, op: str, params_hash: str, current_time) -> bool:
        """Detect if action is part of a loop."""
        window_start = current_time.timestamp() - self.config.loop_detection_window_seconds
        
        matching_actions = [
            (ts, t, o, p) for ts, t, o, p in self.action_history
            if ts >= window_start and t == tool and o == op and p == params_hash
        ]
        
        return len(matching_actions) >= self.config.loop_detection_threshold
    
    def is_dangerous_command(self, command: str) -> bool:
        """Check if shell command is dangerous."""
        command_lower = command.lower()
        return any(
            dangerous in command_lower
            for dangerous in (self.config.dangerous_shell_commands or set())
        )
    
    def is_external_sharing(self, op: str, params: dict) -> bool:
        """Check if action involves external sharing."""
        op_lower = op.lower()
        patterns = self.config.external_sharing_patterns or []
        if any(pattern in op_lower for pattern in patterns):
            return True

        # Check params for external indicators
        params_str = str(params).lower()
        return any(pattern in params_str for pattern in patterns)
    
    def record_action(self, action, current_time):
        """Record action in history for loop detection."""
        # Create a simple hash of params for comparison
        params_hash = str(sorted(action.params.items()))
        self.action_history.append((
            current_time.timestamp(),
            action.tool,
            action.op,
            params_hash
        ))
        
        # Clean old history (keep last hour)
        cutoff = current_time.timestamp() - 3600
        self.action_history = [
            item for item in self.action_history
            if item[0] >= cutoff
        ]
