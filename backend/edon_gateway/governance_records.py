"""Canonical governed decision records and execution tokens.

This module centralizes the technical artifact we treat as the source of truth
for governed actions:

- DecisionRecord: the immutable record emitted for every governed action.
- execution token: a signed downstream authorization token derived from the
  DecisionRecord.
- replay bundle: a stable reconstruction payload for auditors and support.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .security.signing import get_key_id, get_public_key_hex, sign_canonical_payload, verify_canonical_payload


def _iso(dt: Optional[datetime]) -> str:
    return (dt or datetime.now(UTC)).isoformat()


def _normalize_scope(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    if isinstance(values, dict):
        return [str(k) for k in values.keys()]
    if isinstance(values, Iterable):
        out: List[str] = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                out.append(text)
        return out
    text = str(values).strip()
    return [text] if text else []


def _normalize_chain(values: Any) -> List[Dict[str, Any]]:
    if not values:
        return []
    if isinstance(values, dict):
        return [values]
    if isinstance(values, list):
        chain: List[Dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict):
                chain.append(item)
            else:
                chain.append({"step": str(item)})
        return chain
    return [{"step": str(values)}]


def _policy_snapshot_material(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_policy_snapshot_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_policy_snapshot_material(payload).encode("utf-8")).hexdigest()


@dataclass
class DecisionRecord:
    """Canonical governance artifact for a governed action."""

    decision_id: str
    tenant_id: str
    actor_id: str
    agent_id: str
    action_type: str
    risk_tier: str
    policy_snapshot_hash: str
    connector_scope: List[str]
    verdict: str
    approval_state: str
    rollback_mode: str
    issued_at: str
    expires_at: str
    signature: str = ""
    data_class: str = "internal"
    policy_version: Optional[str] = None
    reason_code: Optional[str] = None
    actor_role: Optional[str] = None
    approval_chain: List[Dict[str, Any]] = field(default_factory=list)
    break_glass: bool = False
    break_glass_reason: Optional[str] = None
    kill_switch_scope: Optional[str] = None
    kill_switch_target: Optional[str] = None
    connector_capabilities: List[str] = field(default_factory=list)
    request_hash: Optional[str] = None
    audit_id: Optional[str] = None
    key_id: Optional[str] = None

    def canonical_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("signature", None)
        return payload

    def sign(self) -> "DecisionRecord":
        payload = self.canonical_dict()
        self.signature = sign_canonical_payload(payload)
        self.key_id = get_key_id()
        return self

    def to_dict(self, *, include_signature: bool = True) -> Dict[str, Any]:
        payload = asdict(self)
        if not include_signature:
            payload.pop("signature", None)
        return payload


def infer_approval_state(verdict: str, context: Dict[str, Any]) -> str:
    explicit = (context.get("approval_state") or context.get("approval_status") or "").strip().lower()
    if explicit:
        return explicit
    if verdict in {"ALLOW", "DEGRADE"}:
        return "approved"
    if verdict in {"ESCALATE", "PAUSE"}:
        return "pending_review"
    if verdict == "BLOCK":
        return "blocked"
    return "unknown"


def infer_rollback_mode(context: Dict[str, Any], verdict: str) -> str:
    rollback_mode = (context.get("rollback_mode") or context.get("rollback") or "").strip()
    if rollback_mode:
        return rollback_mode
    if verdict == "ALLOW":
        return "standard"
    if verdict in {"DEGRADE", "ESCALATE"}:
        return "partial"
    return "manual"


def build_decision_record(
    *,
    decision_id: str,
    tenant_id: str,
    actor_id: str,
    agent_id: str,
    action_type: str,
    risk_tier: str,
    verdict: str,
    context: Dict[str, Any],
    policy_version: Optional[str] = None,
    reason_code: Optional[str] = None,
    issued_at: Optional[str] = None,
    expires_at: Optional[str] = None,
    request_hash: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> DecisionRecord:
    connector_scope = _normalize_scope(
        context.get("connector_scope") or context.get("connector_capabilities") or []
    )
    data_class = str(context.get("data_class") or context.get("data_classification") or "internal")
    approval_chain = _normalize_chain(context.get("approval_chain") or context.get("approvals"))
    policy_snapshot_hash = (
        context.get("policy_snapshot_hash")
        or context.get("policy_hash")
        or compute_policy_snapshot_hash(
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "agent_id": agent_id,
                "action_type": action_type,
                "risk_tier": risk_tier,
                "verdict": verdict,
                "approval_state": infer_approval_state(verdict, context),
                "rollback_mode": infer_rollback_mode(context, verdict),
                "connector_scope": connector_scope,
                "data_class": data_class,
                "policy_version": policy_version or "",
                "reason_code": reason_code or "",
                "break_glass": bool(context.get("break_glass")),
                "kill_switch_scope": context.get("kill_switch_scope"),
                "kill_switch_target": context.get("kill_switch_target"),
            }
        )
    )
    record = DecisionRecord(
        decision_id=decision_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        agent_id=agent_id,
        action_type=action_type,
        risk_tier=risk_tier,
        policy_snapshot_hash=policy_snapshot_hash,
        connector_scope=connector_scope,
        verdict=verdict,
        approval_state=infer_approval_state(verdict, context),
        rollback_mode=infer_rollback_mode(context, verdict),
        issued_at=issued_at or _iso(None),
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        data_class=data_class,
        policy_version=policy_version,
        reason_code=reason_code,
        actor_role=context.get("actor_role"),
        approval_chain=approval_chain,
        break_glass=bool(context.get("break_glass")),
        break_glass_reason=context.get("break_glass_reason"),
        kill_switch_scope=context.get("kill_switch_scope"),
        kill_switch_target=context.get("kill_switch_target"),
        connector_capabilities=_normalize_scope(context.get("connector_capabilities") or connector_scope),
        request_hash=request_hash or context.get("request_hash"),
        audit_id=audit_id,
    )
    return record.sign()


def build_execution_token(record: DecisionRecord) -> Dict[str, Any]:
    payload = {
        "token_type": "edon.execution",
        "decision_id": record.decision_id,
        "tenant_id": record.tenant_id,
        "actor_id": record.actor_id,
        "agent_id": record.agent_id,
        "action_type": record.action_type,
        "risk_tier": record.risk_tier,
        "policy_snapshot_hash": record.policy_snapshot_hash,
        "connector_scope": record.connector_scope,
        "verdict": record.verdict,
        "approval_state": record.approval_state,
        "rollback_mode": record.rollback_mode,
        "data_class": record.data_class,
        "issued_at": record.issued_at,
        "expires_at": record.expires_at,
        "break_glass": record.break_glass,
        "key_id": record.key_id or get_key_id(),
    }
    signature = sign_canonical_payload(payload)
    token_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = f"{base64.urlsafe_b64encode(token_bytes).decode('ascii').rstrip('=')}.{signature}"
    return {
        "token": token,
        "signature": signature,
        "key_id": payload["key_id"],
        "payload": payload,
    }


def verify_execution_token(
    token: str | Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
    action_type: Optional[str] = None,
    require_allow: bool = True,
) -> Dict[str, Any]:
    """Verify a signed EDON execution token and return its payload.

    Connectors and legacy execution paths use this as the commit barrier:
    no valid token, no downstream execution.
    """
    if isinstance(token, dict):
        token_text = str(token.get("token") or "")
        signature = str(token.get("signature") or "")
        payload = token.get("payload")
    else:
        token_text = str(token or "")
        signature = ""
        payload = None

    if not payload:
        try:
            encoded_payload, signature = token_text.rsplit(".", 1)
            padding = "=" * (-len(encoded_payload) % 4)
            payload = json.loads(base64.urlsafe_b64decode((encoded_payload + padding).encode("ascii")))
        except Exception as exc:
            raise ValueError(f"Invalid execution token format: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid execution token payload")

    if payload.get("token_type") != "edon.execution":
        raise ValueError("Invalid execution token type")
    if tenant_id and payload.get("tenant_id") != tenant_id:
        raise ValueError("Execution token tenant mismatch")
    if action_type and payload.get("action_type") != action_type:
        raise ValueError("Execution token action mismatch")
    if require_allow and payload.get("verdict") != "ALLOW":
        raise ValueError("Execution token does not authorize execution")

    expires_at = payload.get("expires_at")
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError(f"Invalid execution token expiry: {exc}") from exc
        if expires_dt < datetime.now(UTC):
            raise ValueError("Execution token has expired")

    if not verify_canonical_payload(payload, signature, get_public_key_hex()):
        raise ValueError("Execution token signature is invalid")

    return payload


def build_policy_replay_bundle(
    *,
    record: DecisionRecord,
    decision_row: Optional[Dict[str, Any]] = None,
    audit_event: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bundle = {
        "decision_record": record.to_dict(),
        "policy_version_at_time": record.policy_version,
        "actor_role_at_time": record.actor_role,
        "connector_scope_at_time": record.connector_scope,
        "reason_for_verdict": decision_row.get("explanation") if decision_row else None,
        "approval_chain": record.approval_chain,
        "audit_reference": {
            "decision_id": record.decision_id,
            "audit_id": record.audit_id,
            "request_hash": record.request_hash,
        },
        "policy_snapshot": {
            "policy_snapshot_hash": record.policy_snapshot_hash,
            "risk_tier": record.risk_tier,
            "data_class": record.data_class,
            "rollback_mode": record.rollback_mode,
            "approval_state": record.approval_state,
        },
    }
    if decision_row:
        bundle["decision_row"] = decision_row
    if audit_event:
        bundle["audit_event"] = audit_event
    return bundle
