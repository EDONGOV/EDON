"""Agent Profiles, Timeline, and Cross-Agent Anomaly Detection API.

Endpoints:
  POST /agents/register            - Register a new agent profile
  GET  /agents                     - List all agents for the tenant
  GET  /agents/anomalies           - Cross-agent anomaly detection (must be before /{agent_id})
  GET  /agents/{agent_id}          - Full agent profile with stats and trends
  GET  /agents/{agent_id}/timeline - Paginated action history
  GET  /agents/{agent_id}/stats    - Time-series stats (30d)
  PUT  /agents/{agent_id}/status   - Update agent status

The agents table (schema in database.py _init_schema) is the primary registry.
Timeline and stats are derived from audit_events (always tenant-scoped via customer_id).
"""

import json
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(tags=["agents"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    agent_type: str = Field(default="general", max_length=100)
    description: str = Field(default="", max_length=2000)
    capabilities: List[str] = Field(default_factory=list)
    policy_pack: str = Field(default="", max_length=100)
    mag_enabled: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    vendor_id: Optional[str] = Field(
        None, max_length=100,
        description="Vendor that owns/operates this agent, e.g. 'vendor-a-surgical'",
    )


class AgentStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(active|paused|retired)$")


# ---------------------------------------------------------------------------
# Stats / timeline helpers (all data from audit_events)
# ---------------------------------------------------------------------------

def _ensure_agent_stats_table(db) -> None:
    """Ensure agent_stats table exists.  Called lazily — safe to call each request."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_stats (
                tenant_id      TEXT NOT NULL,
                agent_id       TEXT NOT NULL,
                total_actions  INTEGER NOT NULL DEFAULT 0,
                allow_count    INTEGER NOT NULL DEFAULT 0,
                block_count    INTEGER NOT NULL DEFAULT 0,
                escalate_count INTEGER NOT NULL DEFAULT 0,
                degrade_count  INTEGER NOT NULL DEFAULT 0,
                pause_count    INTEGER NOT NULL DEFAULT 0,
                error_count    INTEGER NOT NULL DEFAULT 0,
                last_action_at TEXT,
                PRIMARY KEY (tenant_id, agent_id)
            )
        """)
        conn.commit()


def _get_lifetime_stats(db, tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """Read lifetime verdict counts from agent_stats + agents tables."""
    _ensure_agent_stats_table(db)

    # First try agent_stats (has full breakdown)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT total_actions, allow_count, block_count, escalate_count,
                   degrade_count, pause_count, error_count, last_action_at
            FROM agent_stats
            WHERE tenant_id = ? AND agent_id = ?
        """, (tenant_id, agent_id))
        row = cursor.fetchone()

    if row:
        total = row["total_actions"] or 0
        allow = row["allow_count"] or 0
        block = row["block_count"] or 0
        escalate = row["escalate_count"] or 0
        degrade = row["degrade_count"] or 0
        pause = row["pause_count"] or 0
        error = row["error_count"] or 0
        last_action_at = row["last_action_at"]
    else:
        # Fallback: read from agents table (coarser, no degrade/pause/error)
        agent = db.get_agent(agent_id, tenant_id=tenant_id)
        if agent:
            total = agent.get("total_actions", 0) or 0
            allow = agent.get("total_allowed", 0) or 0
            block = agent.get("total_blocked", 0) or 0
            escalate = agent.get("total_escalated", 0) or 0
            degrade = pause = error = 0
            last_action_at = agent.get("last_seen_at")
        else:
            total = allow = block = escalate = degrade = pause = error = 0
            last_action_at = None

    def rate(n):
        return round(n / total, 4) if total > 0 else 0.0

    return {
        "total_actions": total,
        "allow_count": allow,
        "block_count": block,
        "escalate_count": escalate,
        "degrade_count": degrade,
        "pause_count": pause,
        "error_count": error,
        "allow_rate": rate(allow),
        "block_rate": rate(block),
        "escalate_rate": rate(escalate),
        "last_action_at": last_action_at,
    }


def _profile_from_agent_row(agent: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    """Shape an agent DB row + stats dict into the API response format."""
    return {
        "agent_id": agent["agent_id"],
        "tenant_id": agent["tenant_id"],
        "name": agent.get("name", agent["agent_id"]),
        "agent_type": agent.get("agent_type", "general"),
        "description": agent.get("description") or "",
        "capabilities": agent.get("capabilities") or [],
        "policy_pack": agent.get("policy_pack") or "",
        "mag_enabled": bool(agent.get("mag_enabled", False)),
        "cav_enabled": bool(agent.get("cav_enabled", True)),
        "metadata": agent.get("metadata") or {},
        "status": agent.get("status", "active"),
        "registered_at": agent.get("registered_at"),
        "last_seen_at": agent.get("last_seen_at"),
        "stats": stats,
    }


def _legacy_profile(agent_id: str, tenant_id: str, display_name: str, first_seen: Optional[str]) -> Dict[str, Any]:
    """Build a minimal profile dict for agents that are in tenant_agents but not in agents."""
    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "name": display_name,
        "agent_type": "auto-registered",
        "description": "",
        "capabilities": [],
        "policy_pack": "",
        "mag_enabled": False,
        "cav_enabled": False,
        "metadata": {},
        "status": "active",
        "registered_at": first_seen,
        "last_seen_at": None,
        "stats": {
            "total_actions": 0, "allow_count": 0, "block_count": 0,
            "escalate_count": 0, "degrade_count": 0, "pause_count": 0,
            "error_count": 0, "allow_rate": 0.0, "block_rate": 0.0,
            "escalate_rate": 0.0, "last_action_at": None,
        },
    }


def _get_agent_timeline(
    db,
    tenant_id: str,
    agent_id: str,
    limit: int = 50,
    offset: int = 0,
    verdict: Optional[str] = None,
    days: int = 7,
) -> Dict[str, Any]:
    """Return paginated timeline entries from audit_events for a specific agent."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        if verdict:
            v = verdict.upper()
            cursor.execute(
                "SELECT COUNT(*) FROM audit_events"
                " WHERE agent_id = ? AND (customer_id = ? OR customer_id IS NULL)"
                " AND timestamp >= ? AND decision_verdict = ?",
                [agent_id, tenant_id, since, v],
            )
            row = cursor.fetchone()
            total = row[0] if row else 0
            cursor.execute(
                "SELECT timestamp, action_tool, action_op, decision_verdict,"
                " decision_reason_code, decision_explanation, action_computed_risk,"
                " action_estimated_risk, context, processing_latency_ms"
                " FROM audit_events"
                " WHERE agent_id = ? AND (customer_id = ? OR customer_id IS NULL)"
                " AND timestamp >= ? AND decision_verdict = ?"
                " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                [agent_id, tenant_id, since, v, limit, offset],
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM audit_events"
                " WHERE agent_id = ? AND (customer_id = ? OR customer_id IS NULL)"
                " AND timestamp >= ?",
                [agent_id, tenant_id, since],
            )
            row = cursor.fetchone()
            total = row[0] if row else 0
            cursor.execute(
                "SELECT timestamp, action_tool, action_op, decision_verdict,"
                " decision_reason_code, decision_explanation, action_computed_risk,"
                " action_estimated_risk, context, processing_latency_ms"
                " FROM audit_events"
                " WHERE agent_id = ? AND (customer_id = ? OR customer_id IS NULL)"
                " AND timestamp >= ?"
                " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                [agent_id, tenant_id, since, limit, offset],
            )

        entries = []
        for r in cursor.fetchall():
            ctx = {}
            if r["context"]:
                try:
                    ctx = json.loads(r["context"])
                except Exception:
                    pass
            entries.append({
                "timestamp": r["timestamp"],
                "action_type": f"{r['action_tool']}.{r['action_op']}",
                "verdict": r["decision_verdict"],
                "reason_code": r["decision_reason_code"],
                "explanation": r["decision_explanation"],
                "risk_level": r["action_computed_risk"] or r["action_estimated_risk"],
                "latency_ms": r["processing_latency_ms"],
                "context": ctx,
            })

    return {"total": total, "limit": limit, "offset": offset, "entries": entries}


def _get_agent_stats_30d(db, tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """Return 30-day time-series stats + breakdown for an agent."""
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        # Daily verdict counts (last 30 days)
        cursor.execute("""
            SELECT
                substr(timestamp, 1, 10) AS day,
                decision_verdict,
                COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY day, decision_verdict
            ORDER BY day ASC
        """, (agent_id, tenant_id, since))
        daily_rows = cursor.fetchall()

        daily: Dict[str, Dict[str, Any]] = {}
        for r in daily_rows:
            day = r["day"]
            if day not in daily:
                daily[day] = {"date": day, "total": 0, "allow": 0, "block": 0,
                              "escalate": 0, "degrade": 0, "pause": 0}
            vkey = (r["decision_verdict"] or "unknown").lower()
            if vkey in daily[day]:
                daily[day][vkey] += r["cnt"]
            daily[day]["total"] += r["cnt"]

        # Verdict totals (30d)
        cursor.execute("""
            SELECT decision_verdict, COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY decision_verdict
        """, (agent_id, tenant_id, since))
        verdict_breakdown = {
            (r["decision_verdict"] or "UNKNOWN").upper(): r["cnt"]
            for r in cursor.fetchall()
        }

        # Risk level breakdown (30d)
        cursor.execute("""
            SELECT
                COALESCE(action_computed_risk, action_estimated_risk, 'unknown') AS risk,
                COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY risk
        """, (agent_id, tenant_id, since))
        risk_breakdown = {r["risk"]: r["cnt"] for r in cursor.fetchall()}

        # Top 5 block reasons (30d)
        cursor.execute("""
            SELECT decision_reason_code, COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
              AND decision_verdict = 'BLOCK'
            GROUP BY decision_reason_code
            ORDER BY cnt DESC
            LIMIT 5
        """, (agent_id, tenant_id, since))
        top_block_reasons = [
            {"reason_code": r["decision_reason_code"], "count": r["cnt"]}
            for r in cursor.fetchall()
        ]

        # Top 5 most-used tools (30d)
        cursor.execute("""
            SELECT action_tool, COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY action_tool
            ORDER BY cnt DESC
            LIMIT 5
        """, (agent_id, tenant_id, since))
        top_tools = [
            {"tool": r["action_tool"], "count": r["cnt"]}
            for r in cursor.fetchall()
        ]

        # 7-day trend: actions per day
        since_7d = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        cursor.execute("""
            SELECT substr(timestamp, 1, 10) AS day, COUNT(*) AS cnt
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY day
            ORDER BY day ASC
        """, (agent_id, tenant_id, since_7d))
        trend_7d = [{"date": r["day"], "count": r["cnt"]} for r in cursor.fetchall()]

        # Behavioral CAV history: last 24h, one row per hour
        cursor.execute("""
            SELECT
                substr(timestamp, 1, 13) AS hour,
                COUNT(*) AS total,
                SUM(CASE WHEN decision_verdict = 'BLOCK' THEN 1 ELSE 0 END) AS blocks,
                SUM(CASE WHEN decision_verdict = 'ALLOW' THEN 1 ELSE 0 END) AS allows
            FROM audit_events
            WHERE agent_id = ?
              AND (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY hour
            ORDER BY hour ASC
        """, (agent_id, tenant_id, since_24h))
        cav_history_24h = [
            {
                "hour": r["hour"],
                "total": r["total"],
                "blocks": r["blocks"],
                "allows": r["allows"],
                "block_rate": round(r["blocks"] / r["total"], 4) if r["total"] > 0 else 0.0,
            }
            for r in cursor.fetchall()
        ]

    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "period_days": 30,
        "daily_series": list(daily.values()),
        "verdict_breakdown": verdict_breakdown,
        "risk_breakdown": risk_breakdown,
        "top_block_reasons": top_block_reasons,
        "top_tools": top_tools,
        "trend_7d": trend_7d,
        "cav_history_24h": cav_history_24h,
    }


def _detect_anomalies(db, tenant_id: str) -> List[Dict[str, Any]]:
    """Cross-agent anomaly detection.

    Scans every agent for this tenant that has >10 actions in the last hour.
    Compares current-hour metrics against each agent's 30-day baseline.
    Flags agents where:
      - error_rate  > 2x baseline (or >=3 errors with no baseline)
      - action_rate > 3x baseline hourly average (or >50 with no baseline)
      - block_rate spike: current > baseline + 0.15 and > 25%
      - new tool usage: tool not seen in last 30d before this hour
    """
    now = datetime.now(UTC)
    since_1h = (now - timedelta(hours=1)).isoformat()
    since_30d = (now - timedelta(days=30)).isoformat()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        # Agents active in the last hour with >10 actions
        cursor.execute("""
            SELECT agent_id, COUNT(*) AS cnt
            FROM audit_events
            WHERE (customer_id = ? OR customer_id IS NULL)
              AND timestamp >= ?
            GROUP BY agent_id
            HAVING cnt > 10
        """, (tenant_id, since_1h))
        active_agents = {r["agent_id"]: r["cnt"] for r in cursor.fetchall() if r["agent_id"]}

        if not active_agents:
            return []

        flagged: List[Dict[str, Any]] = []

        for agent_id, _ in active_agents.items():
            anomalies: List[str] = []

            # ── Current-hour stats ───────────────────────────────────────────
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN decision_verdict = 'BLOCK'  THEN 1 ELSE 0 END) AS blocks,
                    SUM(CASE WHEN decision_verdict = 'ERROR'  THEN 1 ELSE 0 END) AS errors
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
            """, (agent_id, tenant_id, since_1h))
            cur = cursor.fetchone()
            cur_total  = cur["total"]  or 0
            cur_blocks = cur["blocks"] or 0
            cur_errors = cur["errors"] or 0
            cur_block_rate = cur_blocks / cur_total if cur_total > 0 else 0.0
            cur_error_rate = cur_errors / cur_total if cur_total > 0 else 0.0

            # Current-hour tools
            cursor.execute("""
                SELECT DISTINCT action_tool FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
            """, (agent_id, tenant_id, since_1h))
            cur_tools = {r["action_tool"] for r in cursor.fetchall() if r["action_tool"]}

            # ── 30-day baseline (excludes the current hour) ──────────────────
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN decision_verdict = 'BLOCK'  THEN 1 ELSE 0 END) AS blocks,
                    SUM(CASE WHEN decision_verdict = 'ERROR'  THEN 1 ELSE 0 END) AS errors
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                  AND timestamp < ?
            """, (agent_id, tenant_id, since_30d, since_1h))
            base = cursor.fetchone()
            base_total  = base["total"]  or 0
            base_hourly = base_total / 720.0 if base_total > 0 else 0.0  # 30d * 24h
            base_blocks = base["blocks"] or 0
            base_errors = base["errors"] or 0
            base_block_rate = base_blocks / base_total if base_total > 0 else 0.0
            base_error_rate = base_errors / base_total if base_total > 0 else 0.0

            # Baseline tools
            cursor.execute("""
                SELECT DISTINCT action_tool FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                  AND timestamp < ?
            """, (agent_id, tenant_id, since_30d, since_1h))
            base_tools = {r["action_tool"] for r in cursor.fetchall() if r["action_tool"]}

            # ── Detection rules ──────────────────────────────────────────────

            # Rule 1: Error rate spike
            if cur_error_rate > 0 and (
                (base_error_rate == 0 and cur_errors >= 3)
                or (base_error_rate > 0 and cur_error_rate > 2 * base_error_rate)
            ):
                anomalies.append(
                    f"error_rate_spike: current={cur_error_rate:.2%} "
                    f"vs baseline={base_error_rate:.2%}"
                )

            # Rule 2: Action rate spike
            if base_hourly > 0 and cur_total > 3 * base_hourly:
                anomalies.append(
                    f"action_rate_spike: {cur_total} actions/hr "
                    f"vs baseline={base_hourly:.1f} actions/hr"
                )
            elif base_hourly == 0 and cur_total > 50:
                anomalies.append(
                    f"action_rate_spike: {cur_total} actions/hr with no 30d baseline"
                )

            # Rule 3: Block rate spike
            if cur_block_rate > 0.25 and cur_block_rate > base_block_rate + 0.15:
                anomalies.append(
                    f"block_rate_spike: current={cur_block_rate:.2%} "
                    f"vs baseline={base_block_rate:.2%}"
                )

            # Rule 4: New tool usage
            new_tools = cur_tools - base_tools
            if new_tools:
                anomalies.append(f"new_tool_usage: {', '.join(sorted(new_tools))}")

            if anomalies:
                flagged.append({
                    "agent_id": agent_id,
                    "anomalies": anomalies,
                    "current_hour_actions": cur_total,
                    "current_block_rate": round(cur_block_rate, 4),
                    "current_error_rate": round(cur_error_rate, 4),
                    "baseline_block_rate": round(base_block_rate, 4),
                    "baseline_hourly_avg": round(base_hourly, 2),
                    "detected_at": now.isoformat(),
                })

    return flagged


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register_agent(request: Request, body: AgentRegisterRequest):
    """Register or update a full agent profile for the authenticated tenant.

    Uses db.register_agent_full (upsert) — idempotent for the same agent_id.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    try:
        agent = db.register_agent_full(
            agent_id=body.agent_id,
            tenant_id=tenant_id,
            name=body.name,
            agent_type=body.agent_type,
            description=body.description,
            capabilities=body.capabilities,
            policy_pack=body.policy_pack or None,
            mag_enabled=body.mag_enabled,
            metadata=body.metadata,
            vendor_id=body.vendor_id,
        )
    except Exception as e:
        logger.exception("Failed to register agent: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to register agent: {e}")

    # Ensure also registered in tenant_agents for plan enforcement
    try:
        db.register_agent(tenant_id, body.agent_id)
    except Exception:
        pass

    stats = _get_lifetime_stats(db, tenant_id, body.agent_id)
    return _profile_from_agent_row(agent, stats)


@router.get("")
async def list_agents(
    request: Request,
    status: Optional[str] = Query(None, pattern="^(active|paused|retired)$"),
    agent_type: Optional[str] = Query(None),
):
    """List all agents registered for the authenticated tenant."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()

    # Primary: agents table
    try:
        all_agents = db.list_agents(tenant_id)
    except Exception as e:
        logger.warning("list_agents DB error: %s", e)
        all_agents = []

    # Apply filters
    if status:
        all_agents = [a for a in all_agents if a.get("status") == status]
    if agent_type:
        all_agents = [a for a in all_agents if a.get("agent_type") == agent_type]

    profiles = []
    for agent in all_agents:
        stats = _get_lifetime_stats(db, tenant_id, agent["agent_id"])
        profiles.append(_profile_from_agent_row(agent, stats))

    # Fallback: add auto-registered agents from tenant_agents not in agents table
    if not status or status == "active":
        try:
            registered_ids = {p["agent_id"] for p in profiles}
            for la in db.get_tenant_agents(tenant_id):
                if la["agent_id"] not in registered_ids:
                    profiles.append(_legacy_profile(
                        la["agent_id"], tenant_id,
                        la.get("display_name", la["agent_id"]),
                        la.get("first_seen"),
                    ))
        except Exception as e:
            logger.warning("Failed to merge legacy agents: %s", e)

    return {"agents": profiles, "total": len(profiles), "tenant_id": tenant_id}


@router.get("/anomalies")
async def get_anomalies(request: Request):
    """Cross-agent anomaly detection for the authenticated tenant.

    Scans all agents with >10 actions in the last hour and flags those
    showing statistically anomalous behaviour compared to their 30-day
    baseline (error rate spike, action rate spike, block rate spike, new tool).
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    try:
        flagged = _detect_anomalies(db, tenant_id)
    except Exception as e:
        logger.exception("Anomaly detection error: %s", e)
        raise HTTPException(status_code=500, detail="Anomaly detection failed")

    return {
        "tenant_id": tenant_id,
        "flagged_agents": flagged,
        "total_flagged": len(flagged),
        "scanned_at": datetime.now(UTC).isoformat(),
    }


@router.get("/{agent_id}")
async def get_agent(request: Request, agent_id: str):
    """Return full agent profile with 7-day trend, top tools, and top block reasons."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()

    agent = db.get_agent(agent_id, tenant_id=tenant_id)
    if not agent:
        # Try legacy auto-registered
        legacy = db.get_tenant_agents(tenant_id)
        match = next((a for a in legacy if a["agent_id"] == agent_id), None)
        if not match:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        profile = _legacy_profile(
            match["agent_id"], tenant_id,
            match.get("display_name", match["agent_id"]),
            match.get("first_seen"),
        )
    else:
        stats = _get_lifetime_stats(db, tenant_id, agent_id)
        profile = _profile_from_agent_row(agent, stats)

    # Enrich with 7-day trend, top tools, top block reasons, behavioral CAV state
    since_7d = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()

            # 7-day trend
            cursor.execute("""
                SELECT substr(timestamp, 1, 10) AS day, COUNT(*) AS cnt
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                GROUP BY day ORDER BY day ASC
            """, (agent_id, tenant_id, since_7d))
            profile["trend_7d"] = [
                {"date": r["day"], "count": r["cnt"]} for r in cursor.fetchall()
            ]

            # Top 5 tools (7d)
            cursor.execute("""
                SELECT action_tool, COUNT(*) AS cnt
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                GROUP BY action_tool ORDER BY cnt DESC LIMIT 5
            """, (agent_id, tenant_id, since_7d))
            profile["top_tools"] = [
                {"tool": r["action_tool"], "count": r["cnt"]} for r in cursor.fetchall()
            ]

            # Top 5 block reasons (7d)
            cursor.execute("""
                SELECT decision_reason_code, COUNT(*) AS cnt
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                  AND decision_verdict = 'BLOCK'
                GROUP BY decision_reason_code ORDER BY cnt DESC LIMIT 5
            """, (agent_id, tenant_id, since_7d))
            profile["top_block_reasons"] = [
                {"reason_code": r["decision_reason_code"], "count": r["cnt"]}
                for r in cursor.fetchall()
            ]

            # Behavioral CAV state (7d)
            cursor.execute("""
                SELECT decision_verdict, COUNT(*) AS cnt
                FROM audit_events
                WHERE agent_id = ?
                  AND (customer_id = ? OR customer_id IS NULL)
                  AND timestamp >= ?
                GROUP BY decision_verdict
            """, (agent_id, tenant_id, since_7d))
            cav = {r["decision_verdict"]: r["cnt"] for r in cursor.fetchall()}
            total_cav = sum(cav.values()) or 1
            profile["behavioral_cav_state"] = {
                "verdicts": cav,
                "block_rate_7d": round(cav.get("BLOCK", 0) / total_cav, 4),
                "allow_rate_7d": round(cav.get("ALLOW", 0) / total_cav, 4),
            }
    except Exception as e:
        logger.warning("Failed to enrich profile for agent %s: %s", agent_id, e)
        profile.setdefault("trend_7d", [])
        profile.setdefault("top_tools", [])
        profile.setdefault("top_block_reasons", [])
        profile.setdefault("behavioral_cav_state", {})

    return profile


@router.get("/{agent_id}/timeline")
async def get_agent_timeline(
    request: Request,
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    verdict: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
):
    """Return paginated action history for a specific agent from audit_events."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    try:
        result = _get_agent_timeline(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            limit=limit,
            offset=offset,
            verdict=verdict,
            days=days,
        )
    except Exception as e:
        logger.exception("Failed to fetch timeline for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch timeline")

    return result


@router.get("/{agent_id}/stats")
async def get_agent_stats(request: Request, agent_id: str):
    """Return 30-day time-series stats for a specific agent.

    Includes daily action counts by verdict, verdict breakdown totals,
    risk level breakdown, top block reasons, 7-day trend, and 24h
    behavioral CAV history (hourly buckets).
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    try:
        stats = _get_agent_stats_30d(db, tenant_id, agent_id)
    except Exception as e:
        logger.exception("Failed to fetch stats for agent %s: %s", agent_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

    return stats


@router.put("/{agent_id}/status")
async def update_agent_status(
    request: Request,
    agent_id: str,
    body: AgentStatusUpdateRequest,
):
    """Update the operational status of an agent (active, paused, retired).

    Only updates agents registered to the authenticated tenant.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()

    # Verify agent belongs to this tenant
    agent = db.get_agent(agent_id, tenant_id=tenant_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Use POST /agents/register first.",
        )

    updated = db.update_agent_status(agent_id, tenant_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    logger.info(
        "agent_status_updated: tenant=%s agent=%s status=%s",
        tenant_id, agent_id, body.status,
    )

    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "status": body.status,
        "updated_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Per-agent resource quota management
# ---------------------------------------------------------------------------

class AgentQuotaRequest(BaseModel):
    max_calls_per_minute: Optional[int] = Field(None, ge=1, le=1_000_000)
    max_calls_per_hour: Optional[int] = Field(None, ge=1, le=10_000_000)
    max_calls_per_day: Optional[int] = Field(None, ge=1, le=100_000_000)
    max_payload_bytes: Optional[int] = Field(None, ge=1, le=100 * 1024 * 1024)  # 100 MB cap
    enabled: bool = True


@router.get("/{agent_id}/quota")
async def get_agent_quota(request: Request, agent_id: str):
    """Get the resource quota configuration for an agent.

    Returns the custom quota if set, otherwise the system defaults.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    from ..security.agent_quotas import get_quota_store
    quota = get_quota_store().get(db=db, tenant_id=tenant_id, agent_id=agent_id)
    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "quota": quota.to_dict(),
    }


@router.put("/{agent_id}/quota")
async def set_agent_quota(request: Request, agent_id: str, body: AgentQuotaRequest):
    """Set custom resource quotas for an agent.

    Overrides the global defaults for this specific agent.
    Set enabled=false to disable quota enforcement for the agent.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()

    from ..security.agent_quotas import get_quota_store, AgentQuotaConfig
    from ..middleware.rate_limit import DEFAULT_LIMITS
    import os as _os

    _default_payload = int(_os.getenv("EDON_DEFAULT_MAX_PAYLOAD_BYTES", str(1024 * 1024)))
    existing = get_quota_store().get(db=db, tenant_id=tenant_id, agent_id=agent_id)

    new_quota = AgentQuotaConfig(
        max_calls_per_minute=body.max_calls_per_minute or existing.max_calls_per_minute,
        max_calls_per_hour=body.max_calls_per_hour or existing.max_calls_per_hour,
        max_calls_per_day=body.max_calls_per_day or existing.max_calls_per_day,
        max_payload_bytes=body.max_payload_bytes or existing.max_payload_bytes,
        enabled=body.enabled,
    )
    get_quota_store().set(db=db, tenant_id=tenant_id, agent_id=agent_id, quota=new_quota)

    logger.info("agent_quota_updated: tenant=%s agent=%s quota=%s", tenant_id, agent_id, new_quota.to_dict())

    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "quota": new_quota.to_dict(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@router.delete("/{agent_id}/quota")
async def delete_agent_quota(request: Request, agent_id: str):
    """Remove custom quota config for an agent (reverts to system defaults)."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    from ..security.agent_quotas import get_quota_store
    get_quota_store().delete(db=db, tenant_id=tenant_id, agent_id=agent_id)

    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "quota": "reset to defaults",
        "updated_at": datetime.now(UTC).isoformat(),
    }
