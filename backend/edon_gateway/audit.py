"""Audit logging for EDON Guard."""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from .schemas import Action, Decision, AuditEvent, IntentContract


class AuditLogger:
    """Audit logger with in-memory storage and JSONL persistence."""
    
    def __init__(self, log_file: Optional[Path] = None):
        """Initialize audit logger.
        
        Args:
            log_file: Path to JSONL log file. If None, only in-memory.
        """
        self.log_file = log_file
        self.events: List[AuditEvent] = []
        self.log_handle = None
        
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            # Open in append mode
            self.log_handle = open(self.log_file, 'a')
    
    def log(
        self,
        action: Action,
        decision: Decision,
        intent: Optional[IntentContract] = None,
        context: dict = None
    ):
        """Log an audit event.
        
        Args:
            action: Action that was evaluated
            decision: Governance decision
            intent: Intent contract (optional)
            context: Additional context (optional)
        """
        if context is None:
            context = {}
        
        # Use canonical intent_id from context if provided, otherwise fallback
        intent_id = context.get("intent_id") if context else None
        if not intent_id and intent:
            # Fallback: use created_at as identifier (will be replaced with proper ID in Phase B)
            intent_id = f"intent_{intent.created_at.isoformat()}"
        
        # Clean context: remove intent_id (it's top-level), keep agent_id, session_id, etc.
        clean_context = {k: v for k, v in (context or {}).items() if k != "intent_id"}
        
        event = AuditEvent(
            action=action,
            decision=decision,
            intent_id=intent_id,
            context=clean_context
        )
        
        self.events.append(event)
        
        if self.log_handle:
            self.log_handle.write(json.dumps(event.to_dict()) + '\n')
            self.log_handle.flush()
    
    def get_events(
        self,
        verdict: Optional[str] = None,
        reason_code: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[AuditEvent]:
        """Query audit events.
        
        Args:
            verdict: Filter by verdict
            reason_code: Filter by reason code
            limit: Maximum number of events to return
            
        Returns:
            List of matching audit events
        """
        filtered = self.events
        
        if verdict:
            filtered = [e for e in filtered if e.decision and e.decision.verdict.value == verdict]
        
        if reason_code:
            filtered = [e for e in filtered if e.decision and e.decision.reason_code.value == reason_code]
        
        if limit:
            filtered = filtered[-limit:]
        
        return filtered
    
    def get_incidents(self) -> List[AuditEvent]:
        """Get all incidents (BLOCK, ESCALATE, PAUSE decisions).
        
        Returns:
            List of incident events
        """
        incidents = []
        for event in self.events:
            if event.decision:
                verdict = event.decision.verdict.value
                if verdict in ["BLOCK", "ESCALATE", "PAUSE"]:
                    incidents.append(event)
        return incidents
    
    def replay_incident(self, incident_index: int) -> Optional[dict]:
        """Replay an incident for analysis.
        
        Args:
            incident_index: Index of incident in incidents list
            
        Returns:
            Replay data dictionary
        """
        incidents = self.get_incidents()
        if incident_index >= len(incidents):
            return None
        
        incident = incidents[incident_index]
        
        # Get context leading up to incident
        event_index = self.events.index(incident)
        preceding_events = self.events[max(0, event_index - 10):event_index]
        
        return {
            "incident": incident.to_dict(),
            "preceding_events": [e.to_dict() for e in preceding_events],
            "timeline": {
                "incident_time": incident.timestamp.isoformat(),
                "events_before": len(preceding_events)
            }
        }
    
    def close(self):
        """Close audit log file."""
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None
    
    def load_from_file(self, log_file: Path) -> List[AuditEvent]:
        """Load audit events from JSONL file.
        
        Args:
            log_file: Path to JSONL file
            
        Returns:
            List of audit events
        """
        events = []
        if not log_file.exists():
            return events
        
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    # Reconstruct event (simplified - would need full reconstruction)
                    events.append(AuditEvent(
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        context=data.get("context", {})
                    ))
        
        return events
