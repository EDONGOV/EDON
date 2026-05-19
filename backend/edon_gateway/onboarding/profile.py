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

    def as_dict(self) -> dict:
        d = asdict(self)
        d["agent_systems"] = [asdict(a) for a in self.agent_systems]
        return d


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
        market_pack_version: str | None = None,
    ) -> GovernanceDeploymentProfile:
        tenant_id = _require_tenant_id(tenant_id, context="create an onboarding profile")
        deployment_mode = normalize_deployment_mode(deployment_mode)
        market_pack = normalize_market_pack_slug(market_pack)
        pack_defaults = get_market_pack_defaults(market_pack)
        market_pack_version = (market_pack_version or pack_defaults["market_pack_version"]).strip()
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


def _from_dict(d: dict) -> GovernanceDeploymentProfile:
    specs = [AgentSystemSpec(**a) for a in d.get("agent_systems", [])]
    d = dict(d)
    d["deployment_mode"] = normalize_deployment_mode(d.get("deployment_mode"))
    d["market_pack"] = normalize_market_pack_slug(d.get("market_pack"))
    d["market_pack_version"] = (d.get("market_pack_version") or get_market_pack(d["market_pack"])["version"]).strip()
    d["agent_systems"] = specs
    return GovernanceDeploymentProfile(**d)


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
