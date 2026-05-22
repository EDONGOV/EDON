"""GovernanceDeploymentProfile — client intake and machine-readable config.

Step 1 of the EDON onboarding flow. Takes a structured intake questionnaire
and produces a GovernanceDeploymentProfile that drives every subsequent step:
topology generation, policy bootstrap, deployment package, signoff, expansion.

The profile is the single source of truth for what a tenant's environment
looks like BEFORE any agent traffic is observed. It is reconciled against
live observations as shadow mode runs.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger
from ..market_packs import get_market_pack, get_market_pack_defaults, normalize_market_pack_slug

logger = get_logger(__name__)

_DEFAULT_DB_PATH = "onboarding.db"


def _is_production_env() -> bool:
    return os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production"


def _resolve_db_path() -> str:
    db_path = (os.getenv("EDON_ONBOARDING_DB") or "").strip()
    if db_path:
        return db_path
    if _is_production_env():
        raise RuntimeError(
            "EDON_ONBOARDING_DB must be set in production. "
            "The onboarding store cannot silently fall back to the local SQLite file."
        )
    return _DEFAULT_DB_PATH

# Risk tier derivation weights
_DATA_CLASS_RISK: dict[str, int] = {
    "PHI": 3, "PCI": 3, "PII": 2, "credentials": 3,
    "financial": 2, "legal": 2, "internal": 1, "public": 0,
}
_COMPLIANCE_RISK: dict[str, int] = {
    "HIPAA": 3, "PCI_DSS": 3, "GDPR": 2, "SOC2": 2, "ISO27001": 1,
}

_DEPLOYMENT_MODES = {"pilot", "production", "experimental"}


def normalize_deployment_mode(mode: str | None) -> str:
    mode = (mode or "pilot").strip().lower()
    if mode not in _DEPLOYMENT_MODES:
        raise ValueError(
            f"Unsupported deployment mode '{mode}'. Expected one of: "
            f"{', '.join(sorted(_DEPLOYMENT_MODES))}."
        )
    return mode


def _classify_runtime_risk(requested_access: list[str], connectors: list[str], agent_count: int) -> tuple[int, str]:
    text = " ".join((requested_access or []) + (connectors or [])).lower()
    score = 0
    if any(keyword in text for keyword in ("writeback", "admin", "medication", "delete", "destroy")):
        score += 4
    if any(keyword in text for keyword in ("export", "phi", "ehr", "note", "draft")):
        score += 2
    if "siem" in text or "audit" in text:
        score += 1
    score += min(max(agent_count, 0) // 100, 3)
    score = min(score, 10)
    if score >= 7:
        tier = "critical"
    elif score >= 5:
        tier = "high"
    elif score >= 3:
        tier = "medium"
    else:
        tier = "low"
    return score, tier


def _build_policy_simulation(requested_access: list[str], risk_tier: str) -> dict:
    approvals = [
        access for access in requested_access
        if any(keyword in access.lower() for keyword in ("writeback", "export", "admin", "medication"))
    ]
    blocked = [
        access for access in requested_access
        if any(keyword in access.lower() for keyword in ("delete", "destroy"))
    ]
    return {
        "shadow": True,
        "policy_mode": "shadow",
        "allowed": [access for access in requested_access if access not in blocked],
        "blocked": blocked,
        "approval_required": approvals,
        "risk_tier": risk_tier,
        "summary": (
            "Shadow Governance active. Policy simulation is verifying access boundaries."
            if risk_tier in {"low", "medium"}
            else "Shadow Governance active. Policy simulation shows approval-bound access."
        ),
    }


@dataclass
class AgentSystemSpec:
    name: str
    agent_type: str           # "llm_agent", "rpa", "scripted", "human_in_loop"
    actions: list[str]        # ["email.send", "ehr.write", ...]
    data_classes: list[str]   # ["PHI", "PCI", ...]
    external_sinks: list[str] # domains / service names data can leave to
    description: str = ""


@dataclass
class GovernanceDeploymentProfile:
    profile_id: str
    tenant_id: str
    org_name: str
    created_at: str
    updated_at: str

    # Environment
    agent_systems: list[AgentSystemSpec]
    identity_provider: str          # "entra", "okta", "cognito", "none"
    environments: list[str]         # ["aws_vpc", "azure_vnet", "k8s", "on_prem", "saas"]
    external_sinks: list[str]       # all unique sinks across all agent systems
    compliance_requirements: list[str]

    # Derived
    all_data_classes: list[str]
    all_actions: list[str]
    risk_tier: str                  # "critical", "high", "medium", "low"
    risk_score: int                 # 0–10

    # Onboarding state machine
    stage: str = "intake"           # intake → topology → bootstrap → shadow → signoff → live → expanding
    shadow_mode_enabled: bool = False
    signed_off: bool = False
    signed_off_at: Optional[str] = None
    signed_off_by: Optional[str] = None
    deployment_mode: str = "pilot"
    market_pack: str = "healthcare"
    market_pack_version: str = "2026.05"
    policy_pack: str = "hospital"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["agent_systems"] = [asdict(a) for a in self.agent_systems]
        return d


@dataclass
class RuntimeRegistration:
    runtime_id: str
    tenant_id: str
    runtime_name: str
    vendor_name: str
    vendor_id: str
    source_type: str
    agent_count: int
    department: str
    purpose: str
    runtime_type: str
    requested_access: list[str]
    connectors: list[str]
    governance_mode: str = "shadow"
    status: str = "observing"
    review_status: str = "pending"
    risk_score: int = 0
    risk_tier: str = "low"
    policy_simulation: dict = field(default_factory=dict)
    audit_stream: list[dict] = field(default_factory=list)
    recent_actions: list[str] = field(default_factory=list)
    review_notes: str = ""
    promoted_agent_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _derive_risk(profile: GovernanceDeploymentProfile) -> tuple[int, str]:
    score = 0
    for dc in profile.all_data_classes:
        score += _DATA_CLASS_RISK.get(dc, 0)
    for cr in profile.compliance_requirements:
        score += _COMPLIANCE_RISK.get(cr, 0)
    # External sinks add risk
    score += min(len(profile.external_sinks), 3)
    # Many agents / high action count
    score += min(len(profile.agent_systems), 3)
    score = min(score, 10)
    if score >= 7:
        tier = "critical"
    elif score >= 5:
        tier = "high"
    elif score >= 3:
        tier = "medium"
    else:
        tier = "low"
    return score, tier


def _require_tenant_id(tenant_id: str, *, context: str) -> str:
    tenant_id = (tenant_id or "").strip()
    if tenant_id in ("", "default", "unknown"):
        raise ValueError(f"Tenant ID is required to {context}.")
    return tenant_id


class OnboardingStore:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = _resolve_db_path()
        self._db_path = db_path
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id   TEXT PRIMARY KEY,
                    tenant_id    TEXT NOT NULL,
                    org_name     TEXT NOT NULL,
                    data         TEXT NOT NULL,
                    stage        TEXT NOT NULL DEFAULT 'intake',
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_profiles_tenant
                    ON profiles (tenant_id);
                CREATE TABLE IF NOT EXISTS runtime_registrations (
                    runtime_id   TEXT PRIMARY KEY,
                    tenant_id    TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'observing',
                    data         TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_registrations_tenant
                    ON runtime_registrations (tenant_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_registrations_status
                    ON runtime_registrations (status);
            """)

    def create(
        self,
        tenant_id: str,
        org_name: str,
        agent_systems: list[dict],
        identity_provider: str,
        environments: list[str],
        compliance_requirements: list[str],
        deployment_mode: str = "pilot",
        market_pack: str = "healthcare",
        policy_pack: str | None = None,
        market_pack_version: str | None = None,
    ) -> GovernanceDeploymentProfile:
        tenant_id = _require_tenant_id(tenant_id, context="create an onboarding profile")
        deployment_mode = normalize_deployment_mode(deployment_mode)
        market_pack = normalize_market_pack_slug(market_pack)
        pack_defaults = get_market_pack_defaults(market_pack)
        market_pack_version = (market_pack_version or pack_defaults["market_pack_version"]).strip()
        policy_pack = (policy_pack or pack_defaults.get("policy_pack") or "hospital").strip().lower()
        profile_id = f"gdp-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()

        specs = [
            AgentSystemSpec(
                name=a.get("name", "unnamed"),
                agent_type=a.get("agent_type", "llm_agent"),
                actions=a.get("actions", []),
                data_classes=a.get("data_classes", []),
                external_sinks=a.get("external_sinks", []),
                description=a.get("description", ""),
            )
            for a in agent_systems
        ]

        all_data_classes = sorted({
            *{dc for s in specs for dc in s.data_classes},
            *pack_defaults["data_classes"],
        })
        all_actions      = sorted({ac for s in specs for ac in s.actions})
        all_sinks        = sorted({sk for s in specs for sk in s.external_sinks})
        compliance_requirements = sorted({
            *compliance_requirements,
            *pack_defaults["compliance_requirements"],
        })

        profile = GovernanceDeploymentProfile(
            profile_id=profile_id,
            tenant_id=tenant_id,
            org_name=org_name,
            created_at=now,
            updated_at=now,
            deployment_mode=deployment_mode,
            agent_systems=specs,
            identity_provider=identity_provider,
            environments=environments,
            external_sinks=all_sinks,
            compliance_requirements=compliance_requirements,
            all_data_classes=all_data_classes,
            all_actions=all_actions,
            risk_tier="low",
            risk_score=0,
            market_pack=market_pack,
            market_pack_version=market_pack_version,
            policy_pack=policy_pack,
        )
        profile.risk_score, profile.risk_tier = _derive_risk(profile)

        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO profiles (profile_id, tenant_id, org_name, data, stage, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (profile_id, tenant_id, org_name, json.dumps(profile.as_dict()), "intake", now, now),
            )
        logger.info(f"[onboarding] profile created: {profile_id} tenant={tenant_id} tier={profile.risk_tier}")
        return profile

    def get(self, profile_id: str) -> Optional[GovernanceDeploymentProfile]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM profiles WHERE profile_id=?", (profile_id,)
            ).fetchone()
        if row is None:
            return None
        return _from_dict(json.loads(row["data"]))

    def list_for_tenant(self, tenant_id: str) -> list[dict]:
        tenant_id = _require_tenant_id(tenant_id, context="list onboarding profiles")
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM profiles WHERE tenant_id=? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def update_stage(self, profile_id: str, stage: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            if row is None:
                return
            d = json.loads(row["data"])
            d["stage"] = stage
            d["updated_at"] = now
            conn.execute(
                "UPDATE profiles SET data=?, stage=?, updated_at=? WHERE profile_id=?",
                (json.dumps(d), stage, now, profile_id),
            )

    def set_shadow_mode(self, profile_id: str, enabled: bool) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            if row is None:
                return
            d = json.loads(row["data"])
            d["shadow_mode_enabled"] = enabled
            d["stage"] = "shadow" if enabled else d.get("stage", "bootstrap")
            d["updated_at"] = now
            conn.execute(
                "UPDATE profiles SET data=?, stage=?, updated_at=? WHERE profile_id=?",
                (json.dumps(d), d["stage"], now, profile_id),
            )

    def sign_off(self, profile_id: str, signed_off_by: str) -> Optional[GovernanceDeploymentProfile]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            if row is None:
                return None
            d = json.loads(row["data"])
            d["signed_off"] = True
            d["signed_off_at"] = now
            d["signed_off_by"] = signed_off_by
            d["stage"] = "live"
            d["updated_at"] = now
            conn.execute(
                "UPDATE profiles SET data=?, stage=?, updated_at=? WHERE profile_id=?",
                (json.dumps(d), "live", now, profile_id),
            )
        logger.info(f"[onboarding] signed off: {profile_id} by={signed_off_by}")
        return _from_dict(d)

    def register_runtime(
        self,
        tenant_id: str,
        runtime_name: str,
        vendor_name: str,
        vendor_id: str,
        source_type: str,
        agent_count: int,
        department: str,
        purpose: str,
        runtime_type: str,
        requested_access: list[str],
        connectors: list[str],
        *,
        governance_mode: str = "shadow",
        status: str = "observing",
        review_status: str = "pending",
        review_notes: str = "",
    ) -> RuntimeRegistration:
        tenant_id = _require_tenant_id(tenant_id, context="register an onboarding runtime")
        runtime_id = f"rtm-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        risk_score, risk_tier = _classify_runtime_risk(requested_access, connectors, agent_count)
        policy_simulation = _build_policy_simulation(requested_access, risk_tier)
        record = RuntimeRegistration(
            runtime_id=runtime_id,
            tenant_id=tenant_id,
            runtime_name=runtime_name,
            vendor_name=vendor_name,
            vendor_id=vendor_id,
            source_type=source_type,
            agent_count=max(int(agent_count), 0),
            department=department,
            purpose=purpose,
            runtime_type=runtime_type,
            requested_access=requested_access,
            connectors=connectors,
            governance_mode=governance_mode,
            status=status,
            review_status=review_status,
            risk_score=risk_score,
            risk_tier=risk_tier,
            policy_simulation=policy_simulation,
            audit_stream=[
                {
                    "action": "register_runtime",
                    "actor": "system",
                    "result": status,
                    "time": now,
                    "summary": "Registered in shadow governance",
                }
            ],
            recent_actions=["Registered in shadow governance"],
            review_notes=review_notes,
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO runtime_registrations (runtime_id, tenant_id, status, data, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (runtime_id, tenant_id, status, json.dumps(record.as_dict()), now, now),
            )
        logger.info(f"[onboarding] runtime registered: {runtime_id} tenant={tenant_id} tier={risk_tier}")
        return record

    def _load_runtime(self, runtime_id: str) -> Optional[RuntimeRegistration]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM runtime_registrations WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()
        if row is None:
            return None
        return _runtime_from_dict(json.loads(row["data"]))

    def get_runtime(self, runtime_id: str) -> Optional[RuntimeRegistration]:
        return self._load_runtime(runtime_id)

    def list_runtimes_for_tenant(self, tenant_id: str) -> list[dict]:
        tenant_id = _require_tenant_id(tenant_id, context="list onboarding runtimes")
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM runtime_registrations WHERE tenant_id=? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def _store_runtime(self, record: RuntimeRegistration) -> RuntimeRegistration:
        now = datetime.now(UTC).isoformat()
        record.updated_at = now
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE runtime_registrations SET status=?, data=?, updated_at=? WHERE runtime_id=?",
                (record.status, json.dumps(record.as_dict()), now, record.runtime_id),
            )
        return record

    def review_runtime(self, runtime_id: str, reviewed_by: str, approved: bool, notes: str = "") -> Optional[RuntimeRegistration]:
        record = self._load_runtime(runtime_id)
        if record is None:
            return None
        now = datetime.now(UTC).isoformat()
        record.review_status = "approved" if approved else "rejected"
        record.status = "reviewed" if approved else "held"
        if notes:
            record.review_notes = notes
        record.recent_actions.append(f"Review {'approved' if approved else 'rejected'} by {reviewed_by}")
        record.audit_stream.append({
            "action": "review_runtime",
            "actor": reviewed_by,
            "result": record.review_status,
            "time": now,
            "notes": notes,
        })
        return self._store_runtime(record)

    def promote_runtime(
        self,
        runtime_id: str,
        promoted_by: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[RuntimeRegistration]:
        record = self._load_runtime(runtime_id)
        if record is None:
            return None
        now = datetime.now(UTC).isoformat()
        record.status = "promoted"
        record.governance_mode = "governed"
        record.review_status = "approved"
        record.promoted_agent_id = agent_id or runtime_id
        record.recent_actions.append(f"Promoted by {promoted_by}")
        record.audit_stream.append({
            "action": "promote_runtime",
            "actor": promoted_by,
            "result": "promoted",
            "time": now,
            "agent_id": record.promoted_agent_id,
        })
        return self._store_runtime(record)


def _from_dict(d: dict) -> GovernanceDeploymentProfile:
    specs = [AgentSystemSpec(**a) for a in d.get("agent_systems", [])]
    d = dict(d)
    d["deployment_mode"] = normalize_deployment_mode(d.get("deployment_mode"))
    d["market_pack"] = normalize_market_pack_slug(d.get("market_pack"))
    d["market_pack_version"] = (d.get("market_pack_version") or get_market_pack(d["market_pack"])["version"]).strip()
    d["policy_pack"] = (d.get("policy_pack") or get_market_pack(d["market_pack"])["policy_pack"]).strip().lower()
    d["agent_systems"] = specs
    return GovernanceDeploymentProfile(**d)


def _runtime_from_dict(d: dict) -> RuntimeRegistration:
    d = dict(d)
    d["requested_access"] = list(d.get("requested_access") or [])
    d["connectors"] = list(d.get("connectors") or [])
    d["audit_stream"] = list(d.get("audit_stream") or [])
    d["recent_actions"] = list(d.get("recent_actions") or [])
    d["policy_simulation"] = dict(d.get("policy_simulation") or {})
    d["agent_count"] = int(d.get("agent_count") or 0)
    d["risk_score"] = int(d.get("risk_score") or 0)
    return RuntimeRegistration(**d)


# ── Singleton ──────────────────────────────────────────────────────────────────

_store: Optional[OnboardingStore] = None
_store_lock = threading.Lock()


def get_onboarding_store() -> OnboardingStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = OnboardingStore()
    return _store
