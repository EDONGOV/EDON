"""EDON Governor - Main governance engine."""

import os
import logging
import hashlib
import json
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, Tuple
from .schemas import (
    Action, Decision, IntentContract, Verdict, ReasonCode,
    RiskLevel, Tool, ActionSource
)
from .policy.engine import PolicyEngine, PolicyConfig
from .mag_client import mag_enabled_for_tenant, authorize_action
from .degradation_registry import get_degraded_action, get_degradation_explanation

# ── Blast-radius risk table ───────────────────────────────────────────────────
# Maps (tool_value, op) → minimum RiskLevel the governor will assign, regardless
# of the agent's self-estimate.  Add entries whenever a new high-impact tool/op
# is onboarded.  The governor takes max(agent_estimate, table_floor).
_BLAST_RADIUS_FLOOR: Dict[Tuple[str, str], RiskLevel] = {
    # Email
    ("email", "send"): RiskLevel.MEDIUM,
    ("gmail", "send"): RiskLevel.MEDIUM,
    # Database
    ("database", "drop"): RiskLevel.CRITICAL,
    ("database", "delete"): RiskLevel.HIGH,
    ("database", "truncate"): RiskLevel.CRITICAL,
    # File
    ("file", "delete"): RiskLevel.HIGH,
    # Shell (any execute is at least HIGH; dangerous-command check may upgrade to CRITICAL)
    ("shell", "execute"): RiskLevel.HIGH,
    ("shell", "run"): RiskLevel.HIGH,
    # Physical systems — any actuator op is at least HIGH
    ("robot", "execute"): RiskLevel.HIGH,
    ("robot", "actuate"): RiskLevel.HIGH,
    ("vehicle", "drive"): RiskLevel.HIGH,
    ("drone", "fly"): RiskLevel.HIGH,
    ("forklift", "lift"): RiskLevel.HIGH,
    ("gate", "open"): RiskLevel.HIGH,
    ("gate", "unlock"): RiskLevel.HIGH,
    # Deployments
    ("agent", "deploy"): RiskLevel.HIGH,
}

_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two RiskLevel values."""
    ia = _RISK_ORDER.index(a) if a in _RISK_ORDER else 0
    ib = _RISK_ORDER.index(b) if b in _RISK_ORDER else 0
    return _RISK_ORDER[max(ia, ib)]

logger = logging.getLogger(__name__)

# Fail-safe when policy engine throws: "block" (default) or "allow_with_log"
POLICY_FAIL_SAFE = os.getenv("EDON_POLICY_FAIL_SAFE", "block").strip().lower()
_IS_PRODUCTION = (os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production")
_STRICT_FAIL_CLOSED = (os.getenv("EDON_STRICT_FAIL_CLOSED", "true" if _IS_PRODUCTION else "false").strip().lower() == "true")
FAIL_SAFE_ALLOW = (not _STRICT_FAIL_CLOSED) and POLICY_FAIL_SAFE in ("allow", "allow_with_log")


class EDONGovernor:
    """EDON Governance engine."""

    def __init__(self, policy_config: Optional[PolicyConfig] = None, db=None):
        """Initialize governor."""
        from .state.rate_store import RateStore
        rate_store = RateStore()
        self.policy_engine = PolicyEngine(config=policy_config, rate_store=rate_store)
        self.db = db
    
    def get_intent(self, intent_id: str) -> IntentContract:
        """Fetch intent contract from storage.
        
        Args:
            intent_id: Intent identifier
            
        Returns:
            IntentContract object
            
        Raises:
            ValueError: If intent not found
        """
        if not self.db:
            raise ValueError("Database not configured")
        
        intent_dict = self.db.get_intent(intent_id)
        if not intent_dict:
            raise ValueError(f"Intent not found: {intent_id}")
        
        # Convert dict to IntentContract (dataclass)
        # Filter to only fields that IntentContract accepts
        return IntentContract(
            objective=intent_dict["objective"],
            scope=intent_dict["scope"],
            constraints=intent_dict.get("constraints", {}),
            risk_level=RiskLevel(intent_dict.get("risk_level", "LOW")),
            approved_by_user=intent_dict.get("approved_by_user", False)
        )
    
    def evaluate(
        self,
        action: Action,
        intent: IntentContract,
        context: Optional[dict] = None,
        tenant_rules: Optional[List[Dict[str, Any]]] = None
    ) -> Decision:
        """Evaluate action against intent and policies.
        
        On policy engine error, applies fail-safe: block (default) or allow_with_log.
        Never silently drops or undefined behavior (Tier 1).
        
        Args:
            action: Proposed action
            intent: Active intent contract
            context: Additional context (optional)
            
        Returns:
            Decision with verdict and reasoning
        """
        if context is None:
            context = {}
        if tenant_rules is None:
            tenant_rules = []
        policy_snapshot_hash = self._compute_policy_snapshot_hash(intent, tenant_rules)
        context["_policy_snapshot_hash"] = policy_snapshot_hash
        context.setdefault("_invariant_results", [])
        try:
            decision = self._evaluate_impl(action, intent, context, tenant_rules)
            reason_code_str = decision.reason_code.value if hasattr(decision.reason_code, "value") else str(decision.reason_code or "")
            verdict_str = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
            self._record_trust_outcome(verdict_str, reason_code_str, context)
            return self._attach_provenance(decision, context, policy_snapshot_hash)
        except Exception as e:
            logger.exception("Policy engine error during evaluate: %s", e)
            if FAIL_SAFE_ALLOW:
                decision = Decision(
                    verdict=Verdict.ALLOW,
                    reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                    explanation=f"Policy engine error; fail-safe allow_with_log applied. Error: {str(e)[:200]}"
                )
                self._record_invariant(context, "INV-090-POLICY-ENGINE", "fail", "Policy engine error: fail-open applied")
                return self._attach_provenance(decision, context, policy_snapshot_hash)
            decision = Decision(
                verdict=Verdict.BLOCK,
                reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                explanation=f"Policy engine error; fail-safe block applied. Error: {str(e)[:200]}"
            )
            self._record_invariant(context, "INV-090-POLICY-ENGINE", "fail", "Policy engine error: fail-closed applied")
            return self._attach_provenance(decision, context, policy_snapshot_hash)

    def _compute_policy_snapshot_hash(self, intent: IntentContract, tenant_rules: Optional[List[Dict[str, Any]]]) -> str:
        payload = {
            "objective": intent.objective,
            "scope": intent.scope,
            "constraints": intent.constraints,
            "risk_level": intent.risk_level.value if hasattr(intent.risk_level, "value") else str(intent.risk_level),
            "approved_by_user": bool(intent.approved_by_user),
            "tenant_rules": tenant_rules or [],
            "policy_fail_safe": POLICY_FAIL_SAFE,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _record_invariant(self, context: Optional[dict], invariant_id: str, status: str, details: str) -> None:
        if not isinstance(context, dict):
            return
        bucket = context.setdefault("_invariant_results", [])
        if isinstance(bucket, list):
            bucket.append(
                {
                    "id": invariant_id,
                    "status": status,
                    "details": details,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    def _attach_provenance(self, decision: Decision, context: Optional[dict], policy_snapshot_hash: str) -> Decision:
        if isinstance(context, dict):
            invariant_results = context.get("_invariant_results", [])
        else:
            invariant_results = []
        decision.policy_snapshot_hash = policy_snapshot_hash
        decision.invariant_results = invariant_results if isinstance(invariant_results, list) else []
        if not decision.policy_rule_id:
            decision.policy_rule_id = (decision.meta or {}).get("policy_rule_id")
        if isinstance(decision.meta, dict):
            decision.meta.setdefault("policy_snapshot_hash", policy_snapshot_hash)
            decision.meta.setdefault("invariant_results", decision.invariant_results)

        # Ed25519 signature — allows customers to verify decisions offline
        try:
            from .security.signing import sign_decision, get_key_id
            decision_dict = decision.to_dict()
            sig = sign_decision(decision_dict)
            if isinstance(decision.meta, dict):
                decision.meta["sig"] = sig
                decision.meta["kid"] = get_key_id()
        except Exception as _sig_err:
            logger.warning("Decision signing failed (non-fatal): %s", _sig_err)

        return decision

    def _match_tenant_rule(self, rule: dict, action: Action) -> bool:
        """Return True if a tenant rule matches this action."""
        if rule.get("condition_tool") and rule["condition_tool"] != action.tool.value:
            return False
        if rule.get("condition_op") and rule["condition_op"] != action.op:
            return False
        if rule.get("condition_risk_level") and rule["condition_risk_level"] != action.estimated_risk.value:
            return False
        required_tags = rule.get("condition_tags") or []
        if required_tags:
            action_tags = set(action.tags or [])
            if not all(t in action_tags for t in required_tags):
                return False
        return True

    def _apply_tenant_rules(self, tenant_rules: list, action: Action) -> Optional[Decision]:
        """Evaluate tenant-defined rules (priority-ordered). Return Decision or None."""
        for rule in tenant_rules:
            if not rule.get("enabled", True):
                continue
            if not self._match_tenant_rule(rule, action):
                continue
            rule_action = rule.get("action", "").upper()
            rule_name = rule.get("name", rule.get("id", "custom"))
            rule_id = rule.get("id", rule_name)
            if rule_action == "BLOCK":
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.SCOPE_VIOLATION,
                    explanation=f"Blocked by custom policy rule: {rule_name}",
                    policy_rule_id=rule_id,
                    meta={"policy_rule_id": rule_id, "rule_eval_trace": [rule_id]},
                )
            elif rule_action == "ALLOW":
                return Decision(
                    verdict=Verdict.ALLOW,
                    reason_code=ReasonCode.APPROVED,
                    explanation=f"Allowed by custom policy rule: {rule_name}",
                    policy_rule_id=rule_id,
                    meta={"policy_rule_id": rule_id, "rule_eval_trace": [rule_id]},
                )
            elif rule_action == "ESCALATE":
                return Decision(
                    verdict=Verdict.ESCALATE,
                    reason_code=ReasonCode.NEED_CONFIRMATION,
                    explanation=f"Escalated by custom policy rule: {rule_name}",
                    required_confirmation=True,
                    policy_rule_id=rule_id,
                    meta={"policy_rule_id": rule_id, "rule_eval_trace": [rule_id]},
                )
        return None

    def _evaluate_impl(
        self,
        action: Action,
        intent: IntentContract,
        context: Optional[dict],
        tenant_rules: Optional[list] = None
    ) -> Decision:
        """Internal evaluation logic (called by evaluate with try/except)."""
        current_time = action.requested_at

        # -1. Intent freshness — check before anything else (INV-006-INTENT-FRESH)
        now_utc = datetime.now(UTC)
        if intent.revoked:
            self._record_invariant(context, "INV-006-INTENT-FRESH", "fail", "Intent revoked")
            return Decision(
                verdict=Verdict.BLOCK,
                reason_code=ReasonCode.INTENT_MISMATCH,
                explanation="Intent contract has been revoked",
            )
        if intent.expires_at is not None and now_utc > intent.expires_at:
            self._record_invariant(
                context, "INV-006-INTENT-FRESH", "fail",
                f"Intent expired at {intent.expires_at.isoformat()}",
            )
            return Decision(
                verdict=Verdict.BLOCK,
                reason_code=ReasonCode.INTENT_MISMATCH,
                explanation=f"Intent contract expired at {intent.expires_at.isoformat()}",
            )
        self._record_invariant(context, "INV-006-INTENT-FRESH", "pass", "Intent is current")

        # 0a. Apply tenant-defined custom rules first (highest priority)
        if tenant_rules:
            tenant_decision = self._apply_tenant_rules(tenant_rules, action)
            if tenant_decision is not None:
                self._record_invariant(context, "INV-001-TENANT-RULES", "pass", "Tenant rule override applied")
                return tenant_decision
        self._record_invariant(context, "INV-001-TENANT-RULES", "pass", "No tenant rule override")

        # 0. Compute server-side risk using blast-radius floor table + dangerous-command check.
        #    The governor always takes max(agent_estimate, table_floor) — agents cannot
        #    self-report a lower risk than the operation warrants.
        tool_val = action.tool.value if hasattr(action.tool, "value") else str(action.tool)
        floor = _BLAST_RADIUS_FLOOR.get((tool_val, action.op))
        computed_risk = _max_risk(action.estimated_risk, floor) if floor else action.estimated_risk

        # 0a. Forward blast-radius propagation: upgrade risk if this action enables a
        #     higher-risk downstream action in the dependency graph.
        try:
            from .ai.action_graph import propagate_blast_radius
            computed_risk = propagate_blast_radius(tool_val, action.op, computed_risk)
        except Exception:
            pass

        # 0b. Contextual blast radius: entity count and sensitive param patterns.
        computed_risk = self._contextual_risk_upgrade(action, computed_risk)

        # Further upgrade to CRITICAL for dangerous shell commands
        if action.tool == Tool.SHELL:
            command = action.params.get("command", "")
            if self.policy_engine.is_dangerous_command(command):
                computed_risk = RiskLevel.CRITICAL

        # Store computed risk in action for audit
        action.computed_risk = computed_risk

        # ── MAG Authorization Signal ─────────────────────────────────────────
        # Fail-open: if MAG is unreachable or errors, governance continues normally.
        mag_result = None
        _mag_constraints: list = []
        tenant_id = context.get("tenant_id") if context else None
        if mag_enabled_for_tenant(tenant_id):
            mag_result = authorize_action(action, intent, tenant_id, context)
            if mag_result:
                mag_verdict = (mag_result.get("verdict") or "").lower()
                if mag_verdict == "deny":
                    self._record_invariant(context, "INV-005-MAG-AUTH", "fail", "MAG denied action")
                    return Decision(
                        verdict=Verdict.BLOCK,
                        reason_code=ReasonCode.SCOPE_VIOLATION,
                        explanation=f"MAG authorization denied: {mag_result.get('reason', 'policy violation')}",
                        meta={"mag_verdict": mag_result.get("verdict")},
                    )
                elif mag_verdict == "degrade":
                    # Apply MAG constraints — continue but flag for degrade after standard checks
                    _mag_constraints = mag_result.get("constraints", [])
                    self._record_invariant(context, "INV-005-MAG-AUTH", "pass", "MAG degraded action")
                else:
                    self._record_invariant(context, "INV-005-MAG-AUTH", "pass", "MAG allowed action")
        else:
            self._record_invariant(context, "INV-005-MAG-AUTH", "skip", "MAG disabled for tenant")
                # "allow" → fall through to normal governance flow
        # ─────────────────────────────────────────────────────────────────────

        # 1. Check drafts_only constraint FIRST (before scope, so we can degrade send->draft)
        if intent.constraints.get("drafts_only", False):
            if action.tool in (Tool.EMAIL, Tool.GMAIL) and action.op == "send":
                degraded = get_degraded_action(action, reason_tags=["drafts_only"])
                if degraded is not None:
                    return Decision(
                        verdict=Verdict.DEGRADE,
                        reason_code=ReasonCode.DEGRADED_TO_SAFE_ALTERNATIVE,
                        explanation="Intent requires drafts_only, degrading send to draft",
                        safe_alternative=degraded,
                    )
        
        # 2. Check scope boundaries (after drafts_only check)
        # But prioritize risk if computed_risk is critical
        scope_violation = not intent.allows_tool_op(action.tool.value, action.op)
        
        if scope_violation:
            self._record_invariant(context, "INV-002-SCOPE-BOUNDARY", "fail", "Action outside declared scope")
            # If also dangerous, prioritize risk reason
            if computed_risk == RiskLevel.CRITICAL:
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.RISK_TOO_HIGH,
                    explanation=f"Dangerous operation blocked: {action.tool.value}.{action.op} (also out of scope)"
                )
            # Before hard-blocking a scope violation, check degradation registry
            degraded = get_degraded_action(action, reason_tags=["scope_violation"])
            if degraded is not None:
                expl = get_degradation_explanation(action.tool.value if hasattr(action.tool, "value") else str(action.tool), action.op)
                return Decision(
                    verdict=Verdict.DEGRADE,
                    reason_code=ReasonCode.DEGRADED_TO_SAFE_ALTERNATIVE,
                    explanation=expl or f"Action degraded: {action.tool.value}.{action.op} → {degraded.op}",
                    safe_alternative=degraded,
                )
            return Decision(
                verdict=Verdict.BLOCK,
                reason_code=ReasonCode.SCOPE_VIOLATION,
                explanation=f"Action {action.tool.value}.{action.op} not in scope. Allowed: {intent.scope.get(action.tool.value, [])}"
            )
        self._record_invariant(context, "INV-002-SCOPE-BOUNDARY", "pass", "Action within declared scope")
        
        # 2.5. Check allowed_clawdbot_tools constraint (for Clawdbot tool)
        if action.tool == Tool.CLAWDBOT and action.op == "invoke":
            allowed_tools = intent.constraints.get("allowed_clawdbot_tools", [])
            if allowed_tools:  # Only check if constraint is set
                underlying_tool = action.params.get("tool", "")
                if underlying_tool not in allowed_tools:
                    return Decision(
                        verdict=Verdict.BLOCK,
                        reason_code=ReasonCode.SCOPE_VIOLATION,
                        explanation=f"Clawdbot tool '{underlying_tool}' not in allowed list. Allowed: {allowed_tools}"
                    )
        
        # 3. Check work hours constraint
        if intent.constraints.get("work_hours_only", False):
            if not self.policy_engine.is_work_hours(current_time):
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.OUT_OF_HOURS,
                    explanation=f"Action requested outside work hours (current: {current_time.hour}:00, work hours: {self.policy_engine.config.work_hours_start}-{self.policy_engine.config.work_hours_end})"
                )
        
        # 4. Record action for loop detection (before other checks that might block)
        params_hash = str(sorted(action.params.items()))
        tenant_id = context.get("tenant_id") if context else None
        agent_id = context.get("agent_id") if context else None
        self.policy_engine.record_action(action, current_time, tenant_id=tenant_id, agent_id=agent_id)

        # 5. Loop detection (check after recording)
        if self.policy_engine.detect_loop(
            action.tool, action.op, params_hash, current_time,
            tenant_id=tenant_id, agent_id=agent_id,
        ):
            return Decision(
                verdict=Verdict.PAUSE,
                reason_code=ReasonCode.LOOP_DETECTED,
                explanation=f"Loop detected: {action.tool.value}.{action.op} repeated {self.policy_engine.config.loop_detection_threshold}+ times in {self.policy_engine.config.loop_detection_window_seconds}s"
            )

        # 6. Check rate limiting (per-agent + shared cross-agent intent budget)
        if self.policy_engine.check_rate_limit(current_time, tenant_id=tenant_id, agent_id=agent_id):
            return Decision(
                verdict=Verdict.PAUSE,
                reason_code=ReasonCode.RATE_LIMIT,
                explanation=f"Rate limit exceeded: {self.policy_engine.config.max_actions_per_minute} actions per minute"
            )
        intent_id = context.get("intent_id") if context else None
        if intent_id and self.policy_engine._rate_store is not None:
            try:
                from .state.rate_store import RateStore
                intent_key = RateStore.intent_rate_key(intent_id)
                intent_count = self.policy_engine._rate_store.add_and_count(
                    intent_key, 60.0
                )
                intent_cap = int(os.getenv("EDON_INTENT_MAX_ACTIONS_PER_MINUTE", "100"))
                if intent_count > intent_cap:
                    return Decision(
                        verdict=Verdict.PAUSE,
                        reason_code=ReasonCode.RATE_LIMIT,
                        explanation=f"Intent-level action budget exceeded: {intent_cap} actions/min across all agents"
                    )
            except Exception:
                pass
        
        # 7. Check for dangerous shell commands (computed_risk already set above)
        if action.tool == Tool.SHELL:
            command = action.params.get("command", "")
            if self.policy_engine.is_dangerous_command(command):
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.RISK_TOO_HIGH,
                    explanation=f"Dangerous shell command detected: {command[:50]}"
                )
        
        # 8. Check for data exfiltration
        if intent.constraints.get("no_external_sharing", False):
            if self.policy_engine.is_external_sharing(action.op, action.params):
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.DATA_EXFIL,
                    explanation=f"External sharing detected in {action.op} operation"
                )
        
        # 9. Check max_recipients constraint
        if "max_recipients" in intent.constraints:
            max_recipients = intent.constraints["max_recipients"]
            recipients = action.params.get("recipients", [])
            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(",")]
            recipient_count = len(recipients) if isinstance(recipients, list) else 1
            
            if recipient_count > max_recipients:
                if action.op == "send":
                    # Escalate: high-impact public action (many recipients)
                    draft_action = Action(
                        tool=action.tool,
                        op="draft",
                        params=action.params.copy(),
                        requested_at=action.requested_at,
                        source=action.source,
                        tags=action.tags + ["degraded", "too_many_recipients"],
                        computed_risk=computed_risk
                    )
                    return Decision(
                        verdict=Verdict.ESCALATE,
                        reason_code=ReasonCode.NEED_CONFIRMATION,
                        explanation=f"Recipient count ({recipient_count}) exceeds max ({max_recipients}). Requires confirmation.",
                        safe_alternative=draft_action,
                        required_confirmation=True,
                        escalation_question=f"Send email to {recipient_count} recipients? (max allowed: {max_recipients})",
                        escalation_options=[
                            {"id": "allow_once", "label": "Allow once"},
                            {"id": "draft_only", "label": "Save as draft only"},
                            {"id": "keep_blocking", "label": "Keep blocking"},
                        ],
                    )
        
        # 10. Check risk level and escalation requirements (use computed_risk, not estimated_risk).
        #     Apply session trust multiplier: a drifting agent gets tighter risk gates.
        trust_multiplier = 1.0
        try:
            from .state.session_trust import get_store as _get_trust_store
            _trust_store = _get_trust_store()
            trust_multiplier = _trust_store.get_trust_multiplier(
                context.get("tenant_id") if context else None,
                context.get("agent_id") if context else None,
                context.get("intent_id") if context else None,
            )
            if context is not None:
                context["trust_multiplier"] = trust_multiplier
        except Exception:
            pass
        # Below full trust, promote MEDIUM risk to HIGH for escalation check
        effective_risk = computed_risk
        if trust_multiplier < 1.0 and computed_risk == RiskLevel.MEDIUM:
            effective_risk = RiskLevel.HIGH
        if effective_risk in (self.policy_engine.config.escalate_risk_levels or set()):
            if not (intent.approved_by_user and effective_risk == RiskLevel.HIGH):
                self._record_invariant(context, "INV-003-RISK-GATE", "fail", f"Risk escalated ({computed_risk.value})")
                try:
                    from .main import prometheus_anomalies_detected_total
                    from .config import config as _cfg
                    if _cfg.METRICS_ENABLED and prometheus_anomalies_detected_total is not None:
                        _sev = "critical" if computed_risk == RiskLevel.CRITICAL else "elevated"
                        prometheus_anomalies_detected_total.labels(severity=_sev).inc()
                except Exception:
                    pass
                return Decision(
                    verdict=Verdict.ESCALATE,
                    reason_code=ReasonCode.NEED_CONFIRMATION,
                    explanation=f"High/critical risk action requires user confirmation (risk: {computed_risk.value})",
                    required_confirmation=True
                )
        self._record_invariant(context, "INV-003-RISK-GATE", "pass", f"Risk acceptable ({computed_risk.value})")
        
        # 11. Check intent objective alignment (basic keyword matching)
        # Ambiguous intent: short objective + no scope match -> escalate with one precise question
        if not self._check_intent_alignment(action, intent):
            self._record_invariant(context, "INV-004-INTENT-ALIGNMENT", "fail", "Action does not align with objective")
            # Optional: if objective is very short, treat as ambiguous and escalate instead of hard block
            objective_short = len((intent.objective or "").strip()) < 15
            if objective_short and intent.constraints.get("escalate_on_ambiguous_intent", False):
                return Decision(
                    verdict=Verdict.ESCALATE,
                    reason_code=ReasonCode.NEED_CONFIRMATION,
                    explanation="Intent is ambiguous; please clarify.",
                    required_confirmation=True,
                    escalation_question="What would you like to do? (e.g. search, send email, create calendar event)",
                    escalation_options=[
                        {"id": "clarify", "label": "I'll clarify"},
                        {"id": "keep_blocking", "label": "Cancel"},
                    ],
                )
            return Decision(
                verdict=Verdict.BLOCK,
                reason_code=ReasonCode.INTENT_MISMATCH,
                explanation=f"Action does not align with intent objective: {intent.objective}"
            )
        self._record_invariant(context, "INV-004-INTENT-ALIGNMENT", "pass", "Action aligns with objective")

        # 11.5. Multi-step sequence drift — session-level attack chain detection.
        #       Each action may pass individually; this catches accumulation patterns
        #       like read_config → read_secret → send_email (exfil chain).
        try:
            from .state.sequence_scorer import get_scorer as _get_scorer, _DRIFT_THRESHOLD, _CROSS_INTENT_THRESHOLD
            _scorer = _get_scorer()
            _t_id = context.get("tenant_id") if context else None
            _a_id = context.get("agent_id") if context else None
            _i_id = context.get("intent_id") if context else None

            # Per-intent check (fast, sensitive — catches same-session chains)
            drift_score, chain_name = _scorer.record_and_score(_t_id, _a_id, _i_id, tool_val, action.op)

            # Cross-intent check (conservative — catches slow-burn across intent boundaries)
            xi_score, xi_chain = _scorer.record_cross_intent(_t_id, _a_id, tool_val, action.op)
            if xi_score >= _CROSS_INTENT_THRESHOLD and xi_score > drift_score:
                drift_score, chain_name = xi_score, f"cross_intent:{xi_chain}"

            if context is not None:
                context["seq_drift_score"] = drift_score
                context["seq_chain"] = chain_name
            if drift_score >= _DRIFT_THRESHOLD:
                self._record_invariant(
                    context, "INV-007-SEQ-DRIFT", "fail",
                    f"Multi-step drift detected: chain={chain_name} score={drift_score:.2f}"
                )
                return Decision(
                    verdict=Verdict.ESCALATE,
                    reason_code=ReasonCode.NEED_CONFIRMATION,
                    explanation=(
                        f"Session action sequence matches '{chain_name}' attack pattern "
                        f"(drift score {drift_score:.0%}). Human confirmation required."
                    ),
                    required_confirmation=True,
                    escalation_question=f"The agent's recent actions match a '{chain_name}' pattern. Continue?",
                    escalation_options=[
                        {"id": "approve", "label": "Approve and continue"},
                        {"id": "reset", "label": "Reset session"},
                        {"id": "cancel", "label": "Cancel"},
                    ],
                )
            self._record_invariant(context, "INV-007-SEQ-DRIFT", "pass", f"Sequence drift acceptable ({drift_score:.2f})")
        except Exception as _seq_err:
            logger.debug("Sequence drift check failed (fail-open): %s", _seq_err)

        # ── CAV State Signal ──────────────────────────────────────────────────
        cav_state = None
        operator_id = (context or {}).get("operator_id") if context else None
        if operator_id:
            try:
                from .cav_client import cav_client
                cav_data = cav_client.get_operator_state(operator_id)
                if cav_data:
                    cav_state = cav_data.get("cav_state", "balanced")
                    # Surface CAV state into context so route handlers persist it in audit
                    if isinstance(context, dict):
                        context["cav_state"] = cav_state
                        context["cav_score"] = cav_data.get("cav_score")
                        context["cav_z_score"] = cav_data.get("z_score")
                    # Overload + HIGH/CRITICAL risk → escalate
                    if cav_state == "overload" and action.computed_risk and action.computed_risk.value in ("high", "critical"):
                        try:
                            from .main import prometheus_anomalies_detected_total
                            from .config import config as _cfg
                            if _cfg.METRICS_ENABLED and prometheus_anomalies_detected_total is not None:
                                _sev = "critical" if action.computed_risk.value == "critical" else "elevated"
                                prometheus_anomalies_detected_total.labels(severity=_sev).inc()
                        except Exception:
                            pass
                        return Decision(
                            verdict=Verdict.ESCALATE,
                            reason_code=ReasonCode.NEED_CONFIRMATION,
                            explanation="Operator cognitive load is elevated. Human confirmation required for high-risk actions.",
                            escalation_question="Operator is in overload state. Confirm this action?",
                            escalation_options=[{"id": "approve", "label": "Approve"}, {"id": "defer", "label": "Defer"}, {"id": "cancel", "label": "Cancel"}],
                        )
            except Exception as _cav_err:
                logger.debug("CAV operator state check failed (fail-open): %s", _cav_err)

        # ── CAV Robot Stability Signal ────────────────────────────────────────
        robot_id = (context or {}).get("robot_id") if context else None
        if robot_id:
            try:
                from .cav_client import cav_client
                stability = cav_client.get_robot_stability(robot_id)
                if stability and not stability.get("stable", True):
                    return Decision(
                        verdict=Verdict.BLOCK,
                        reason_code=ReasonCode.SCOPE_VIOLATION,
                        explanation=f"Robot stability check failed: {stability.get('warning', 'unstable state detected')}",
                    )
            except Exception as _cav_rob_err:
                logger.debug("CAV robot stability check failed (fail-open): %s", _cav_rob_err)

        # Build the MAG signal metadata to attach to the final decision
        mag_meta: Dict[str, Any] = {
            "mag_verdict": mag_result.get("verdict") if mag_result else None
        }
        if context is not None:
            context["mag_verdict"] = mag_meta["mag_verdict"]

        # If MAG signalled degrade (with constraints), apply degrade verdict
        if _mag_constraints:
            return Decision(
                verdict=Verdict.DEGRADE,
                reason_code=ReasonCode.DEGRADED_TO_SAFE_ALTERNATIVE,
                explanation=f"MAG authorization: action degraded by policy constraints ({', '.join(str(c) for c in _mag_constraints[:3])})",
                meta=mag_meta,
            )

        # All checks passed - ALLOW
        return Decision(
            verdict=Verdict.ALLOW,
            reason_code=ReasonCode.APPROVED,
            explanation="Action approved: within scope, constraints satisfied, risk acceptable",
            meta=mag_meta,
        )
    
    def _record_trust_outcome(self, verdict_str: str, reason_code_str: str, context: Optional[dict]) -> None:
        """Update session trust score based on the final governance verdict and reason code."""
        try:
            from .state.session_trust import get_store as _get_trust_store
            _get_trust_store().record_verdict(
                context.get("tenant_id") if context else None,
                context.get("agent_id") if context else None,
                context.get("intent_id") if context else None,
                verdict_str,
                reason_code=reason_code_str,
            )
        except Exception:
            pass

    # ── Semantic alignment thresholds ────────────────────────────────────────
    _AI_ALIGN_BLOCK_THRESHOLD: float = float(
        __import__("os").getenv("EDON_AI_ALIGN_BLOCK_THRESHOLD", "0.15")
    )

    def _check_intent_alignment(self, action: Action, intent: IntentContract) -> bool:
        """Intent alignment check: semantic scoring (AI) with keyword fallback.

        Returns False only when the action is clearly misaligned.  Fail-open:
        if the AI scorer is unavailable, falls back to deterministic keywords.
        """
        tool_val = action.tool.value if hasattr(action.tool, "value") else str(action.tool)
        scope_tools = list(intent.scope.keys())

        # Primary: semantic score from Claude
        try:
            from .ai.intent_alignment import score_intent_alignment
            score = score_intent_alignment(
                intent_objective=intent.objective,
                intent_scope_tools=scope_tools,
                action_tool=tool_val,
                action_op=action.op,
            )
            if score is not None:
                return score > self._AI_ALIGN_BLOCK_THRESHOLD
        except Exception:
            pass

        # Fallback: deterministic keyword matching
        objective_lower = intent.objective.lower()
        scope_lower = " ".join(scope_tools).lower()
        action_keywords = {
            Tool.EMAIL: ["email", "inbox", "message", "mail"],
            Tool.CALENDAR: ["calendar", "meeting", "schedule", "event"],
            Tool.FILE: ["file", "document", "folder"],
            Tool.SHELL: ["command", "system", "terminal"],
            Tool.BRAVE_SEARCH: ["search", "web", "research", "look up", "find"],
            Tool.GMAIL: ["gmail", "inbox", "email", "mail"],
            Tool.GOOGLE_CALENDAR: ["calendar", "event", "schedule", "meeting"],
            Tool.ELEVENLABS: ["voice", "speech", "tts", "read aloud", "storytelling"],
            Tool.GITHUB: ["github", "repo", "issue", "code", "pr"],
            Tool.MEMORY: ["memory", "preference", "remember", "episode", "past task"],
            Tool.ROBOT: ["move", "navigate", "pick", "place", "execute", "actuate", "robot"],
            Tool.VEHICLE: ["drive", "navigate", "move", "transport", "vehicle"],
            Tool.DRONE: ["fly", "navigate", "move", "drone", "aerial"],
            Tool.CONVEYOR: ["start", "stop", "move", "conveyor", "belt"],
            Tool.FORKLIFT: ["lift", "lower", "move", "forklift"],
            Tool.SCANNER: ["scan", "read", "capture", "scanner"],
            Tool.SENSOR: ["read", "measure", "detect", "sensor"],
            Tool.SORTER: ["sort", "classify", "route", "sorter"],
            Tool.DOCK: ["dock", "undock", "attach", "detach"],
            Tool.GATE: ["open", "close", "lock", "unlock", "gate"],
            Tool.CUSTOM: [],
        }
        if action.tool not in action_keywords:
            return True
        keywords = action_keywords[action.tool]
        if not keywords:
            return True
        return any(kw in objective_lower or kw in scope_lower for kw in keywords)

    # ── Contextual blast-radius upgrade ──────────────────────────────────────

    _SENSITIVE_PARAM_PATTERNS = frozenset([
        "password", "secret", "token", "api_key", "private_key",
        "ssn", "dob", "phi", "pii", "hipaa", "credit_card", "cvv",
    ])

    def _contextual_risk_upgrade(self, action: Action, current_risk: RiskLevel) -> RiskLevel:
        """Upgrade risk based on runtime context: entity count and sensitive param patterns."""
        risk = current_risk

        # Many recipients or bulk target entities → at least MEDIUM
        for count_key in ("recipients", "targets", "users", "files", "records"):
            val = action.params.get(count_key)
            if isinstance(val, list) and len(val) > 10:
                risk = _max_risk(risk, RiskLevel.MEDIUM)
            if isinstance(val, list) and len(val) > 50:
                risk = _max_risk(risk, RiskLevel.HIGH)

        # Sensitive param names (keys only — never inspect values to avoid exfil)
        param_keys_lower = {k.lower() for k in action.params}
        if param_keys_lower & self._SENSITIVE_PARAM_PATTERNS:
            risk = _max_risk(risk, RiskLevel.HIGH)

        # Sensitive path patterns in string param values (file paths, domains)
        for v in action.params.values():
            if isinstance(v, str):
                v_lower = v.lower()
                if any(pat in v_lower for pat in ("/etc/", "id_rsa", ".env", "passwd", "shadow")):
                    risk = RiskLevel.CRITICAL
                    break

        return risk
