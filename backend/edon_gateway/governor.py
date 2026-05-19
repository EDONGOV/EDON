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

# Ã¢â€â‚¬Ã¢â€â‚¬ Blast-radius risk table Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# Maps (tool_value, op) Ã¢â€ â€™ minimum RiskLevel the governor will assign, regardless
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
    # Physical systems Ã¢â‚¬â€ any actuator op is at least HIGH
    ("robot", "execute"): RiskLevel.HIGH,
    ("robot", "actuate"): RiskLevel.HIGH,
    ("humanoid", "execute"): RiskLevel.HIGH,
    ("humanoid", "actuate"): RiskLevel.HIGH,
    ("humanoid", "grasp"): RiskLevel.HIGH,
    ("humanoid", "walk"): RiskLevel.MEDIUM,
    ("humanoid", "navigate"): RiskLevel.MEDIUM,
    ("vehicle", "drive"): RiskLevel.HIGH,
    ("drone", "fly"): RiskLevel.HIGH,
    ("forklift", "lift"): RiskLevel.HIGH,
    ("gate", "open"): RiskLevel.HIGH,
    ("gate", "unlock"): RiskLevel.HIGH,
    # Deployments
    ("agent", "deploy"): RiskLevel.HIGH,
}

_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

# Per-action-type failure mode registry.
# Overrides the global FAIL_SAFE_ALLOW when the policy engine raises an exception.
# Wire transfers and financial ops must always fail-closed; emergency clinical access
# should fail-open (blocking is more dangerous than allowing in a break-glass scenario).
_FAILURE_MODE_REGISTRY: Dict[Tuple[str, str], str] = {
    # Wire transfers and financial operations Ã¢â‚¬â€ always fail-closed
    ("payment", "wire_transfer"): "fail_closed",
    ("payment", "transfer"): "fail_closed",
    ("finance", "transfer"): "fail_closed",
    # Destructive database ops Ã¢â‚¬â€ always fail-closed
    ("database", "truncate"): "fail_closed",
    ("database", "drop"): "fail_closed",
    # Emergency clinical access Ã¢â‚¬â€ fail-open (blocking is more dangerous than allowing)
    ("ehr", "emergency_access"): "fail_open",
    ("ehr", "break_glass"): "fail_open",
}

FAIL_OPEN_EXCEPTION_REGISTRY: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("ehr", "emergency_access"): {
        "requires_signoff": True,
        "signoff_field": "exception_signoff_id",
        "reason": "break_glass_emergency_access",
    },
    ("ehr", "break_glass"): {
        "requires_signoff": True,
        "signoff_field": "exception_signoff_id",
        "reason": "break_glass_emergency_access",
    },
}

# Tools that govern physical actuators Ã¢â‚¬â€ e-stop and safety envelope checks apply to these
_PHYSICAL_TOOLS = frozenset({
    Tool.ROBOT, Tool.VEHICLE, Tool.DRONE,
    Tool.FORKLIFT, Tool.CONVEYOR, Tool.GATE, Tool.DOCK,
})


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two RiskLevel values."""
    ia = _RISK_ORDER.index(a) if a in _RISK_ORDER else 0
    ib = _RISK_ORDER.index(b) if b in _RISK_ORDER else 0
    return _RISK_ORDER[max(ia, ib)]

logger = logging.getLogger(__name__)

# Fail-safe when policy engine throws: "block" (default) or "allow_with_log"
POLICY_FAIL_SAFE = os.getenv("EDON_POLICY_FAIL_SAFE", "block").strip().lower()
_IS_PRODUCTION = (os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production")
# Strict fail-closed defaults ON regardless of environment. Must be explicitly opted out via
# EDON_STRICT_FAIL_CLOSED=false Ã¢â‚¬â€ only appropriate in test harnesses, never in production.
_STRICT_FAIL_CLOSED = os.getenv("EDON_STRICT_FAIL_CLOSED", "true").strip().lower() == "true"
def _global_fail_safe_allow() -> bool:
    return (not _STRICT_FAIL_CLOSED) and (not _IS_PRODUCTION) and POLICY_FAIL_SAFE in ("allow", "allow_with_log")


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
    
    def _resolve_failure_mode(self, action: Action, context: dict) -> Optional[str]:
        """Return the effective failure mode for this action: 'fail_open', 'fail_closed', or None (Ã¢â€ â€™ global)."""
        # Per-rule takes precedence (stored by _evaluate_impl after policy engine returns)
        rule_mode = (context or {}).get("_last_failure_mode")
        if rule_mode:
            return rule_mode
        # Fall back to static registry keyed by (tool, op)
        tool_str = action.tool.value if hasattr(action.tool, "value") else str(action.tool)
        return _FAILURE_MODE_REGISTRY.get((tool_str, action.op))

    def evaluate(
        self,
        action: Action,
        intent: IntentContract,
        context: Optional[dict] = None,
        tenant_rules: Optional[List[Dict[str, Any]]] = None,
        tenant_id: Optional[str] = None,
    ) -> Decision:
        """Evaluate action against intent and policies.

        Args:
            action: Proposed action
            intent: Active intent contract
            context: Additional context dict (agent_id, session_id, etc.)
            tenant_rules: Tenant-specific policy rules
            tenant_id: Explicit tenant identifier. Takes precedence over context["tenant_id"].
                       Absence triggers a warning Ã¢â‚¬â€ audit records will lack customer_id.

        Returns:
            Decision with verdict and reasoning. Fail-safe is always BLOCK unless
            EDON_STRICT_FAIL_CLOSED=false is explicitly set.
        """
        if context is None:
            context = {}
        if tenant_rules is None:
            tenant_rules = []
        # Explicit tenant_id is authoritative; seed context so all downstream
        # invariant recording and rate-limiting share a consistent value.
        if tenant_id is not None:
            context["tenant_id"] = tenant_id
        elif "tenant_id" not in context:
            logger.warning("[governor] evaluate() called without tenant_id Ã¢â‚¬â€ audit records will lack customer_id")
        policy_snapshot_hash = self._compute_policy_snapshot_hash(intent, tenant_rules)
        context["_policy_snapshot_hash"] = policy_snapshot_hash
        context.setdefault("_invariant_results", [])
        # Hard gate invariants Ã¢â‚¬â€ any "fail" here must produce a non-ALLOW verdict.
        # Hard gates return early from _evaluate_impl so this check should always
        # pass; it is a defensive guard against future regressions or custom paths.
        _HARD_GATE_INVARIANTS = frozenset({
            "INV-000-ESTOP", "INV-006-INTENT-FRESH", "INV-005-MAG-AUTH",
            "INV-010-ISO15066", "INV-008-ROBOT-STABILITY",
        })

        try:
            decision = self._evaluate_impl(action, intent, context, tenant_rules)
            # ML invariant: hard gate failure must never produce ALLOW.
            _inv_results = context.get("_invariant_results", [])
            _hard_failures = [
                r for r in _inv_results
                if r.get("id") in _HARD_GATE_INVARIANTS and r.get("status") == "fail"
            ]
            if _hard_failures and decision.verdict == Verdict.ALLOW:
                logger.error(
                    "[governor] ML invariant violation: hard gate(s) %s failed but verdict is ALLOW Ã¢â‚¬â€ reverting to BLOCK",
                    [r["id"] for r in _hard_failures],
                )
                self._record_invariant(
                    context, "INV-ML-AUTHORIZE-GUARD", "fail",
                    f"Hard gate override blocked: {[r['id'] for r in _hard_failures]}",
                )
                decision = Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                    explanation="Safety invariant: learned signal cannot override a hard gate failure",
                )
            reason_code_str = decision.reason_code.value if hasattr(decision.reason_code, "value") else str(decision.reason_code or "")
            verdict_str = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
            self._record_trust_outcome(verdict_str, reason_code_str, context)
            return self._attach_provenance(decision, context, policy_snapshot_hash)
        except Exception as e:
            logger.exception("Policy engine error during evaluate: %s", e)
            # Resolve per-action failure mode: per-rule Ã¢â€ â€™ static registry Ã¢â€ â€™ global setting
            _eff_mode = self._resolve_failure_mode(action, context)
            _fail_open = (_eff_mode == "fail_open") or (_eff_mode is None and _global_fail_safe_allow())
            if _fail_open and _IS_PRODUCTION:
                tool_str = action.tool.value if hasattr(action.tool, "value") else str(action.tool)
                op_str = action.op
                _exception_meta = FAIL_OPEN_EXCEPTION_REGISTRY.get((tool_str, op_str))
                if _exception_meta and _exception_meta.get("requires_signoff"):
                    signoff_field = str(_exception_meta.get("signoff_field") or "exception_signoff_id")
                    signoff_id = (context or {}).get(signoff_field) or (context or {}).get("break_glass_approval_id")
                    if not signoff_id:
                        logger.warning(
                            "Fail-open exception blocked in production: tool=%s op=%s missing %s",
                            tool_str,
                            op_str,
                            signoff_field,
                        )
                        _fail_open = False
            if _fail_open:
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

        # Ed25519 signature Ã¢â‚¬â€ allows customers to verify decisions offline
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

    def _apply_tenant_rules(self, tenant_rules: list, action: Action, context: Optional[dict] = None) -> Optional[Decision]:
        """Evaluate tenant-defined rules (priority-ordered). Return Decision or None."""
        for rule in tenant_rules:
            if not rule.get("enabled", True):
                continue
            rule_id = rule.get("id", rule.get("name", "custom"))
            # Canary check: if this rule is in canary mode, only apply to the
            # configured fraction of requests. Record the outcome either way.
            is_canary = False
            try:
                from .healing.canary import should_apply_canary, record_canary_outcome, get_canary
                canary_state = get_canary(rule_id)
                if canary_state and canary_state.is_active:
                    is_canary = True
                    if not should_apply_canary(rule_id):
                        continue  # skip this rule for this request
            except Exception:
                pass

            if not self._match_tenant_rule(rule, action):
                if is_canary:
                    try:
                        from .healing.canary import record_canary_outcome
                        record_canary_outcome(rule_id, False)
                    except Exception:
                        pass
                continue
            rule_action = rule.get("action", "").upper()
            rule_name = rule.get("name", rule_id)
            would_block = rule_action in ("BLOCK", "ESCALATE")
            if is_canary:
                try:
                    from .healing.canary import record_canary_outcome
                    record_canary_outcome(rule_id, would_block)
                except Exception:
                    pass
            # Propagate per-rule failure_mode into context so the exception handler can use it
            rule_failure_mode = rule.get("failure_mode")
            if rule_failure_mode and isinstance(context, dict):
                context["_last_failure_mode"] = rule_failure_mode
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

        # -2. E-stop check Ã¢â‚¬â€ physical tools only, checked before all other governance.
        #     If an e-stop is active for this robot, no command gets through.
        if action.tool in _PHYSICAL_TOOLS:
            robot_id = (context or {}).get("robot_id")
            try:
                from .estop import is_estop_active
                if is_estop_active(robot_id):
                    self._record_invariant(context, "INV-000-ESTOP", "fail", f"E-stop active for robot {robot_id}")
                    return Decision(
                        verdict=Verdict.BLOCK,
                        reason_code=ReasonCode.ESTOP_ACTIVE,
                        explanation=f"E-stop is active for robot '{robot_id}'. Clear the e-stop before issuing commands.",
                    )
            except Exception:
                pass
            self._record_invariant(context, "INV-000-ESTOP", "pass", "No active e-stop")

        # -1. Intent freshness Ã¢â‚¬â€ check before anything else (INV-006-INTENT-FRESH)
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
            tenant_decision = self._apply_tenant_rules(tenant_rules, action, context)
            if tenant_decision is not None:
                self._record_invariant(context, "INV-001-TENANT-RULES", "pass", "Tenant rule override applied")
                return tenant_decision
        self._record_invariant(context, "INV-001-TENANT-RULES", "pass", "No tenant rule override")

        # 0. Compute server-side risk using blast-radius floor table + dangerous-command check.
        #    The governor always takes max(agent_estimate, table_floor) Ã¢â‚¬â€ agents cannot
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

        # â”€â”€ MAG Authorization Signal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Fail-closed on MAG-enabled tenants: execution must be bound to a
        # validated decision bundle and MAG must return an explicit verdict.
        mag_result = None
        _mag_constraints: list = []
        tenant_id = context.get("tenant_id") if context else None
        if mag_enabled_for_tenant(tenant_id):
            mag_binding_id = None
            mag_binding_bundle = None
            if isinstance(context, dict):
                mag_binding_id = context.get("mag_decision_id") or context.get("decision_id")
                mag_binding_bundle = context.get("mag_decision_bundle") or context.get("decision_bundle")
            if isinstance(mag_binding_bundle, dict) and not mag_binding_id:
                mag_binding_id = mag_binding_bundle.get("decision_id") or mag_binding_bundle.get("id")
            if not mag_binding_id or not mag_binding_bundle:
                self._record_invariant(
                    context, "INV-005-MAG-AUTH", "fail",
                    "MAG enabled but execution binding is missing decision_id/decision_bundle",
                )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                    explanation="MAG-enabled execution requires a validated decision_id and decision_bundle",
                )
            mag_result = authorize_action(action, intent, tenant_id, context)
            if not mag_result:
                self._record_invariant(
                    context, "INV-005-MAG-AUTH", "fail",
                    "MAG authorization unavailable for a MAG-enabled tenant",
                )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                    explanation="MAG authorization is required but unavailable for this tenant",
                )
            mag_verdict = (mag_result.get("verdict") or "").lower()
            if mag_verdict == "deny":
                self._record_invariant(context, "INV-005-MAG-AUTH", "fail", "MAG denied action")
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.SCOPE_VIOLATION,
                    explanation=f"MAG authorization denied: {mag_result.get('reason', 'policy violation')}",
                    meta={"mag_verdict": mag_result.get("verdict")},
                )
            if mag_verdict == "degrade":
                # Apply MAG constraints â€” continue but flag for degrade after standard checks
                _mag_constraints = mag_result.get("constraints", [])
                self._record_invariant(context, "INV-005-MAG-AUTH", "pass", "MAG degraded action")
            elif mag_verdict == "allow":
                self._record_invariant(context, "INV-005-MAG-AUTH", "pass", "MAG allowed action")
            else:
                self._record_invariant(
                    context, "INV-005-MAG-AUTH", "fail",
                    f"MAG returned unsupported verdict: {mag_result.get('verdict')}",
                )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.POLICY_ENGINE_ERROR,
                    explanation="MAG authorization returned an unsupported verdict",
                )
        else:
            self._record_invariant(context, "INV-005-MAG-AUTH", "skip", "MAG disabled for tenant")
        # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

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
                    explanation=expl or f"Action degraded: {action.tool.value}.{action.op} Ã¢â€ â€™ {degraded.op}",
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
                intent_key = RateStore.intent_rate_key(context.get("tenant_id") if context else None, intent_id)
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
        
        # 9.5. Physical safety envelope Ã¢â‚¬â€ applies to all physical tool actions.
        #      Checks intent constraints: max_joint_torque_nm, max_velocity_ms,
        #      no_go_zones, require_clearance.  Blocks or escalates on violation.
        if action.tool in _PHYSICAL_TOOLS:
            phys_decision = self._check_physical_safety_envelope(action, intent, context)
            if phys_decision is not None:
                return phys_decision

        # 9.55. ISO/TS 15066 contact force limits (per body region).
        #       Applied to all physical tools when iso15066_enabled is set in the intent,
        #       or when the action explicitly carries contact_force_n / contact_forces.
        if action.tool in _PHYSICAL_TOOLS:
            cf_n = action.params.get("contact_force_n")
            cf_region = action.params.get("target_body_region")
            cf_dict = action.params.get("contact_forces")
            if cf_n is not None or cf_dict or intent.constraints.get("iso15066_enabled"):
                try:
                    from .physical.iso15066 import check_contact_forces
                    contact_type = intent.constraints.get("contact_type", "transient")
                    violations = check_contact_forces(
                        contact_force_n=cf_n,
                        target_body_region=cf_region,
                        contact_forces=cf_dict,
                        contact_type=contact_type,
                    )
                    if violations:
                        v = violations[0]
                        self._record_invariant(
                            context, "INV-010-ISO15066", "fail", str(v)
                        )
                        # Fire alert
                        try:
                            from .alerts.dispatcher import _dispatch
                            _dispatch("physical.force_violation", {
                                "robot_id": (context or {}).get("robot_id", "?"),
                                "tenant_id": (context or {}).get("tenant_id", "global"),
                                "violation": str(v),
                            })
                        except Exception:
                            pass
                        return Decision(
                            verdict=Verdict.BLOCK,
                            reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                            explanation=(
                                f"ISO/TS 15066 contact force violation: {v}. "
                                "Action blocked to prevent human injury."
                            ),
                        )
                    self._record_invariant(context, "INV-010-ISO15066", "pass", "Contact forces within ISO limits")
                except Exception as _iso_err:
                    logger.debug("ISO 15066 check failed (fail-open): %s", _iso_err)

        # 9.60. HRI three-zone safety check.
        #       If human_proximity_m is in params or context, determine the zone and
        #       enforce stop / collaborative constraints.
        if action.tool in _PHYSICAL_TOOLS:
            human_prox = (
                action.params.get("human_proximity_m")
                or (context or {}).get("human_proximity_m")
            )
            if human_prox is not None:
                try:
                    from .physical.hri_zones import zone_from_intent, HRIZone
                    zone_result = zone_from_intent(intent.constraints, float(human_prox))
                    if zone_result is not None:
                        if context is not None:
                            context["hri_zone"] = zone_result.zone.value
                        if zone_result.zone == HRIZone.STOP:
                            self._record_invariant(
                                context, "INV-011-HRI-ZONE", "fail",
                                f"STOP zone: human at {human_prox:.2f}m"
                            )
                            degraded = get_degraded_action(action, reason_tags=["hri_stop_zone"])
                            if degraded is not None:
                                return Decision(
                                    verdict=Verdict.DEGRADE,
                                    reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                                    explanation=zone_result.explanation,
                                    safe_alternative=degraded,
                                )
                            return Decision(
                                verdict=Verdict.BLOCK,
                                reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                                explanation=zone_result.explanation,
                            )
                        if zone_result.zone == HRIZone.COLLABORATIVE:
                            # Enforce speed cap if velocity requested exceeds collaborative limit
                            req_vel = action.params.get("velocity_ms")
                            max_vel = intent.constraints.get("max_velocity_ms")
                            if req_vel is not None and max_vel is not None:
                                collab_max = max_vel * zone_result.speed_factor
                                if float(req_vel) > collab_max:
                                    self._record_invariant(
                                        context, "INV-011-HRI-ZONE", "fail",
                                        f"COLLAB zone: velocity {req_vel}m/s > collab limit {collab_max:.2f}m/s"
                                    )
                                    return Decision(
                                        verdict=Verdict.ESCALATE,
                                        reason_code=ReasonCode.NEED_CONFIRMATION,
                                        explanation=(
                                            f"{zone_result.explanation} "
                                            f"Requested velocity {req_vel}m/s exceeds collaborative-zone limit {collab_max:.2f}m/s."
                                        ),
                                        required_confirmation=True,
                                        escalation_question="Reduce speed to collaborative-zone limit and proceed?",
                                        escalation_options=[
                                            {"id": "approve_reduced", "label": f"Proceed at {collab_max:.2f}m/s"},
                                            {"id": "cancel", "label": "Cancel"},
                                        ],
                                    )
                            self._record_invariant(
                                context, "INV-011-HRI-ZONE", "pass",
                                f"COLLAB zone: speed/force limits applied ({zone_result.explanation})"
                            )
                            if context is not None:
                                context["hri_speed_factor"] = zone_result.speed_factor
                                context["hri_force_factor"] = zone_result.force_factor
                        else:
                            self._record_invariant(context, "INV-011-HRI-ZONE", "pass", "FREE zone")
                except Exception as _hri_err:
                    logger.debug("HRI zone check failed (fail-open): %s", _hri_err)

        # 9.65. Trajectory validation.
        #       If the action carries a trajectory param, validate all waypoints
        #       before issuing ALLOW.
        if action.tool in _PHYSICAL_TOOLS:
            traj = action.params.get("trajectory")
            if traj and isinstance(traj, list):
                try:
                    from .physical.trajectory import validate_trajectory
                    human_prox_ctx = (
                        action.params.get("human_proximity_m")
                        or (context or {}).get("human_proximity_m")
                    )
                    traj_report = validate_trajectory(
                        trajectory=traj,
                        constraints=intent.constraints,
                        action_id=action.id,
                        robot_id=(context or {}).get("robot_id", ""),
                        human_proximity_m=float(human_prox_ctx) if human_prox_ctx is not None else None,
                    )
                    if not traj_report.valid:
                        self._record_invariant(
                            context, "INV-012-TRAJECTORY", "fail",
                            traj_report.first_violation_summary()
                        )
                        block_violations = [v for v in traj_report.violations if v.severity == "block"]
                        esc_violations   = [v for v in traj_report.violations if v.severity == "escalate"]
                        if block_violations:
                            return Decision(
                                verdict=Verdict.BLOCK,
                                reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                                explanation=(
                                    f"Trajectory validation failed ({traj_report.checked_by}): "
                                    f"{traj_report.first_violation_summary()}"
                                ),
                            )
                        if esc_violations:
                            return Decision(
                                verdict=Verdict.ESCALATE,
                                reason_code=ReasonCode.NEED_CONFIRMATION,
                                explanation=(
                                    f"Trajectory has safety warnings ({traj_report.checked_by}): "
                                    f"{traj_report.first_violation_summary()}"
                                ),
                                required_confirmation=True,
                                escalation_question="Trajectory has warnings. Proceed anyway?",
                                escalation_options=[
                                    {"id": "approve", "label": "Approve with warnings"},
                                    {"id": "cancel", "label": "Cancel"},
                                ],
                            )
                    self._record_invariant(
                        context, "INV-012-TRAJECTORY", "pass",
                        f"Trajectory valid ({traj_report.waypoint_count} waypoints, checked by {traj_report.checked_by})"
                    )
                except Exception as _traj_err:
                    logger.debug("Trajectory validation failed (fail-open): %s", _traj_err)

        # 9.70. Multi-robot workspace conflict detection.
        #       If the action declares a workspace_zone, check if another robot holds it.
        if action.tool in _PHYSICAL_TOOLS:
            workspace_zone = action.params.get("workspace_zone")
            if workspace_zone:
                try:
                    from .physical.workspace_registry import try_claim, ConflictResult
                    tenant_id_ctx = (context or {}).get("tenant_id") or "unknown"
                    robot_id_ctx = (context or {}).get("robot_id") or action.id
                    duration_s = action.params.get("estimated_duration_s", 60.0)
                    max_ttl = float(intent.constraints.get("max_workspace_claim_ttl_s", 300.0))
                    priority = int(action.params.get("workspace_priority", 0))
                    conflict_action = intent.constraints.get("workspace_conflict_action", "escalate")
                    result: ConflictResult = try_claim(
                        robot_id=robot_id_ctx,
                        action_id=action.id,
                        tenant_id=tenant_id_ctx,
                        zone_name=workspace_zone,
                        estimated_duration_s=float(duration_s),
                        max_ttl_s=max_ttl,
                        priority=priority,
                    )
                    if result.conflict and result.holder:
                        h = result.holder
                        self._record_invariant(
                            context, "INV-013-WORKSPACE", "fail",
                            f"Zone '{workspace_zone}' held by robot '{h.robot_id}' for ~{h.to_dict().get('expires_in_s', '?')}s"
                        )
                        if conflict_action == "block":
                            return Decision(
                                verdict=Verdict.BLOCK,
                                reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                                explanation=(
                                    f"Workspace zone '{workspace_zone}' is currently occupied by robot '{h.robot_id}'. "
                                    "Action blocked to prevent collision."
                                ),
                            )
                        return Decision(
                            verdict=Verdict.ESCALATE,
                            reason_code=ReasonCode.NEED_CONFIRMATION,
                            explanation=(
                                f"Workspace zone '{workspace_zone}' is currently occupied by robot '{h.robot_id}' "
                                f"(expires in ~{h.to_dict().get('expires_in_s', '?')}s). "
                                "Human coordination required."
                            ),
                            required_confirmation=True,
                            escalation_question=f"Zone '{workspace_zone}' is occupied by '{h.robot_id}'. Proceed anyway?",
                            escalation_options=[
                                {"id": "wait", "label": "Wait Ã¢â‚¬â€ retry after zone is free"},
                                {"id": "proceed", "label": "Proceed Ã¢â‚¬â€ I confirm no collision risk"},
                                {"id": "cancel", "label": "Cancel"},
                            ],
                        )
                    self._record_invariant(context, "INV-013-WORKSPACE", "pass", f"Zone '{workspace_zone}' claimed")
                except Exception as _ws_err:
                    logger.debug("Workspace conflict check failed (fail-open): %s", _ws_err)

        # 9.6. Humanoid / robot real-time stability (richer CAV signal).
        #      Replace the end-of-pipeline CAV robot stability check with this
        #      earlier, richer version for humanoid and robot tools.
        if action.tool in (Tool.ROBOT,) or (hasattr(action.tool, "value") and action.tool.value == "humanoid"):
            robot_id = (context or {}).get("robot_id")
            if robot_id:
                try:
                    from .cav_client import cav_client
                    if hasattr(action.tool, "value") and action.tool.value == "humanoid":
                        stability = cav_client.get_humanoid_stability(robot_id)
                    else:
                        stability = cav_client.get_robot_stability(robot_id)
                    if stability:
                        # Hard block if not stable
                        if not stability.get("stable", True):
                            self._record_invariant(
                                context, "INV-008-ROBOT-STABILITY", "fail",
                                f"Robot unstable: {stability.get('warning', 'stability check failed')}"
                            )
                            return Decision(
                                verdict=Verdict.BLOCK,
                                reason_code=ReasonCode.ROBOT_UNSTABLE,
                                explanation=f"Robot '{robot_id}' stability check failed: {stability.get('warning', 'unstable state detected')}",
                            )
                        # Escalate if balance margin is tight (humanoid-specific)
                        balance_margin = stability.get("balance_margin")
                        if balance_margin is not None and balance_margin < 0.05:
                            self._record_invariant(
                                context, "INV-008-ROBOT-STABILITY", "fail",
                                f"Low balance margin: {balance_margin:.3f}m"
                            )
                            return Decision(
                                verdict=Verdict.ESCALATE,
                                reason_code=ReasonCode.NEED_CONFIRMATION,
                                explanation=f"Humanoid balance margin is {balance_margin:.3f}m (threshold: 0.05m). Human confirmation required.",
                                required_confirmation=True,
                                escalation_question=f"Robot '{robot_id}' has low balance margin ({balance_margin:.3f}m). Proceed with action?",
                                escalation_options=[
                                    {"id": "approve", "label": "Approve Ã¢â‚¬â€ I confirm the robot is stable"},
                                    {"id": "cancel", "label": "Cancel"},
                                ],
                            )
                        # Escalate if payload exceeds limit
                        payload_kg = stability.get("payload_kg")
                        payload_limit = stability.get("payload_limit_kg")
                        if payload_kg is not None and payload_limit is not None and payload_kg > payload_limit:
                            self._record_invariant(
                                context, "INV-008-ROBOT-STABILITY", "fail",
                                f"Payload {payload_kg}kg exceeds limit {payload_limit}kg"
                            )
                            return Decision(
                                verdict=Verdict.BLOCK,
                                reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                                explanation=f"Robot '{robot_id}' payload {payload_kg}kg exceeds limit {payload_limit}kg.",
                            )
                        self._record_invariant(context, "INV-008-ROBOT-STABILITY", "pass",
                                              f"Stability OK (score={stability.get('stability_score', '?')})")
                except Exception as _stab_err:
                    logger.debug("Humanoid stability check failed (fail-open): %s", _stab_err)

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
        # Below full trust, promote MEDIUM risk to HIGH for escalation check.
        # ML contract: session trust may only raise effective risk, never lower it.
        effective_risk = computed_risk
        if trust_multiplier < 1.0 and computed_risk == RiskLevel.MEDIUM:
            effective_risk = RiskLevel.HIGH
        self._record_invariant(
            context, "INV-ML-TIGHTEN-ONLY", "pass",
            f"Session trust: multiplier={trust_multiplier:.3f} "
            f"computed_risk={computed_risk.value} effective_risk={effective_risk.value} (ML may only raise)",
        )
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

        # 11.5. Multi-step sequence drift Ã¢â‚¬â€ session-level attack chain detection.
        #       Each action may pass individually; this catches accumulation patterns
        #       like read_config Ã¢â€ â€™ read_secret Ã¢â€ â€™ send_email (exfil chain).
        try:
            from .state.sequence_scorer import get_scorer as _get_scorer, _DRIFT_THRESHOLD, _CROSS_INTENT_THRESHOLD
            _scorer = _get_scorer()
            _t_id = context.get("tenant_id") if context else None
            _a_id = context.get("agent_id") if context else None
            _i_id = context.get("intent_id") if context else None

            # Per-intent check (fast, sensitive Ã¢â‚¬â€ catches same-session chains)
            drift_score, chain_name = _scorer.record_and_score(_t_id, _a_id, _i_id, tool_val, action.op)

            # Cross-intent check (conservative Ã¢â‚¬â€ catches slow-burn across intent boundaries)
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

        # Ã¢â€â‚¬Ã¢â€â‚¬ CAV State Signal Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
                    # Overload + HIGH/CRITICAL risk Ã¢â€ â€™ escalate
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

        # All checks passed Ã¢â‚¬â€ ALLOW
        # For physical tools: register execution state and embed comm_loss_posture
        if action.tool in _PHYSICAL_TOOLS:
            robot_id_ctx = (context or {}).get("robot_id")
            tenant_id_ctx = (context or {}).get("tenant_id") or "unknown"
            if robot_id_ctx:
                # Register execution state for in-flight telemetry monitoring
                try:
                    from .physical.execution_monitor import register_execution
                    register_execution(
                        robot_id=robot_id_ctx,
                        action_id=action.id,
                        tenant_id=tenant_id_ctx,
                        constraints=intent.constraints,
                    )
                except Exception:
                    pass
                # Embed the robot's declared comm_loss_posture in the response meta
                # so the robot always knows its fallback even if connectivity drops after ALLOW
                try:
                    from .physical.heartbeat import get_posture
                    posture = get_posture(robot_id_ctx)
                    mag_meta["comm_loss_posture"] = posture
                    mag_meta["robot_id"] = robot_id_ctx
                except Exception:
                    pass

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

    # Ã¢â€â‚¬Ã¢â€â‚¬ Semantic alignment thresholds Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
                intent_id=(context or {}).get("intent_id"),
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
            Tool.ROBOT: ["move", "navigate", "pick", "place", "execute", "actuate", "robot", "walk", "grasp", "arm", "hand", "humanoid"],
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

    # Ã¢â€â‚¬Ã¢â€â‚¬ Physical safety envelope Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _check_physical_safety_envelope(
        self,
        action: Action,
        intent: IntentContract,
        context: Optional[dict],
    ) -> Optional[Decision]:
        """Enforce physical safety constraints declared in the intent.

        Supported constraints:
          max_joint_torque_nm (float)  Ã¢â‚¬â€ block if action param joint_torque_nm exceeds this
          max_velocity_ms (float)      Ã¢â‚¬â€ block if action param velocity_ms exceeds this
          no_go_zones (list[str])      Ã¢â‚¬â€ block/escalate if action param target_zone matches
          require_clearance (bool)     Ã¢â‚¬â€ escalate if context does not contain clearance_granted=True

        Returns a Decision to block/escalate, or None to continue.
        All violations record an INV-009-PHYS-SAFETY invariant.
        """
        c = intent.constraints

        # max_joint_torque_nm
        max_torque = c.get("max_joint_torque_nm")
        if max_torque is not None:
            requested_torque = action.params.get("joint_torque_nm")
            if isinstance(requested_torque, (int, float)) and requested_torque > max_torque:
                self._record_invariant(
                    context, "INV-009-PHYS-SAFETY", "fail",
                    f"Joint torque {requested_torque}Nm exceeds limit {max_torque}Nm"
                )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                    explanation=(
                        f"Requested joint torque {requested_torque}Nm exceeds safety limit {max_torque}Nm. "
                        "Action blocked to prevent mechanical damage or injury."
                    ),
                )
            # Also check per-joint dict: {"shoulder": 45.0, "elbow": 30.0, ...}
            joint_torques = action.params.get("joint_torques")
            if isinstance(joint_torques, dict):
                for joint, torque in joint_torques.items():
                    if isinstance(torque, (int, float)) and torque > max_torque:
                        self._record_invariant(
                            context, "INV-009-PHYS-SAFETY", "fail",
                            f"Joint '{joint}' torque {torque}Nm exceeds limit {max_torque}Nm"
                        )
                        return Decision(
                            verdict=Verdict.BLOCK,
                            reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                            explanation=(
                                f"Joint '{joint}' torque {torque}Nm exceeds safety limit {max_torque}Nm."
                            ),
                        )

        # max_velocity_ms
        max_velocity = c.get("max_velocity_ms")
        if max_velocity is not None:
            requested_velocity = action.params.get("velocity_ms")
            if isinstance(requested_velocity, (int, float)) and requested_velocity > max_velocity:
                self._record_invariant(
                    context, "INV-009-PHYS-SAFETY", "fail",
                    f"Velocity {requested_velocity}m/s exceeds limit {max_velocity}m/s"
                )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                    explanation=(
                        f"Requested velocity {requested_velocity}m/s exceeds safety limit {max_velocity}m/s. "
                        "Action blocked."
                    ),
                )

        # no_go_zones
        no_go_zones = c.get("no_go_zones")
        if no_go_zones and isinstance(no_go_zones, list):
            target_zone = action.params.get("target_zone") or action.params.get("zone")
            if target_zone and target_zone in no_go_zones:
                self._record_invariant(
                    context, "INV-009-PHYS-SAFETY", "fail",
                    f"Target zone '{target_zone}' is a no-go zone"
                )
                degraded = get_degraded_action(action, reason_tags=["no_go_zone"])
                if degraded is not None:
                    return Decision(
                        verdict=Verdict.DEGRADE,
                        reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                        explanation=f"Target zone '{target_zone}' is designated no-go. Action degraded.",
                        safe_alternative=degraded,
                    )
                return Decision(
                    verdict=Verdict.BLOCK,
                    reason_code=ReasonCode.PHYSICAL_SAFETY_VIOLATION,
                    explanation=f"Target zone '{target_zone}' is designated no-go. Action blocked.",
                )

        # require_clearance Ã¢â‚¬â€ a human operator must have explicitly granted clearance
        if c.get("require_clearance", False):
            clearance_granted = (context or {}).get("clearance_granted", False)
            if not clearance_granted:
                self._record_invariant(
                    context, "INV-009-PHYS-SAFETY", "fail",
                    "Physical clearance not granted"
                )
                return Decision(
                    verdict=Verdict.ESCALATE,
                    reason_code=ReasonCode.NEED_CONFIRMATION,
                    explanation="This physical action requires explicit human clearance before execution.",
                    required_confirmation=True,
                    escalation_question="Grant physical clearance for this action?",
                    escalation_options=[
                        {"id": "grant_clearance", "label": "Grant clearance Ã¢â‚¬â€ I confirm the area is safe"},
                        {"id": "cancel", "label": "Cancel"},
                    ],
                )

        self._record_invariant(context, "INV-009-PHYS-SAFETY", "pass", "Physical safety envelope OK")
        return None

    # Ã¢â€â‚¬Ã¢â€â‚¬ Contextual blast-radius upgrade Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    _SENSITIVE_PARAM_PATTERNS = frozenset([
        "password", "passwd",
        "secret",
        "token",        # substring Ã¢â‚¬â€ matches access_token, auth_token, bearer_token, etc.
        "api_key",
        "_key",         # substring Ã¢â‚¬â€ matches signing_key, encryption_key, private_key, etc.
        "private_key",
        "ssn", "dob", "phi", "pii", "hipaa", "credit_card", "cvv",
    ])

    _DANGEROUS_PATH_PATTERNS = frozenset([
        "/etc/", "id_rsa", ".env", "passwd", "shadow",
        "/.ssh/", "authorized_keys",
        "/.aws/", ".aws/credentials",
        "/.gcloud/", "gcloud/credentials",
        "/proc/", "/sys/class",
        "auth.log",
        "/root/",
        "system32",     # Windows SAM / system hive paths
    ])

    _DANGEROUS_SQL_PATTERNS = frozenset([
        "; drop", "; delete", "; truncate", "; update", "; insert",
        "'; --", "\"; --", "or 1=1", "or '1'='1",
    ])

    def _contextual_risk_upgrade(self, action: Action, current_risk: RiskLevel) -> RiskLevel:
        """Upgrade risk based on runtime context: entity count and sensitive param patterns."""
        risk = current_risk

        # Many recipients or bulk target entities Ã¢â€ â€™ at least MEDIUM
        for count_key in ("recipients", "targets", "users", "files", "records"):
            val = action.params.get(count_key)
            if isinstance(val, list) and len(val) > 10:
                risk = _max_risk(risk, RiskLevel.MEDIUM)
            if isinstance(val, list) and len(val) > 50:
                risk = _max_risk(risk, RiskLevel.HIGH)

        # Sensitive param names (keys only Ã¢â‚¬â€ never inspect values to avoid exfil)
        # Substring matching: "token" matches "access_token", "_key" matches "signing_key"
        param_keys_lower = {k.lower() for k in action.params}
        if any(pat in k for k in param_keys_lower for pat in self._SENSITIVE_PARAM_PATTERNS):
            risk = _max_risk(risk, RiskLevel.HIGH)

        # Sensitive path patterns in string param values
        for v in action.params.values():
            if isinstance(v, str):
                v_lower = v.lower()
                if any(pat in v_lower for pat in self._DANGEROUS_PATH_PATTERNS):
                    risk = RiskLevel.CRITICAL
                    break

        # SQL injection patterns in database query params
        if action.tool == Tool.DATABASE:
            for v in action.params.values():
                if isinstance(v, str):
                    v_lower = v.lower()
                    if any(pat in v_lower for pat in self._DANGEROUS_SQL_PATTERNS):
                        risk = _max_risk(risk, RiskLevel.HIGH)
                        break

        return risk
