"""Physical systems routes — telemetry, heartbeat, trajectory validation.

POST /v1/robots/{robot_id}/heartbeat                        — heartbeat ping + registration
DELETE /v1/robots/{robot_id}/heartbeat                      — deregister
GET  /v1/robots/heartbeats                                  — list all registered robots
POST /v1/robots/{robot_id}/telemetry                        — ingest execution telemetry (HTTP)
WS   /v1/robots/{robot_id}/telemetry/stream                 — streaming telemetry (WebSocket)
POST /v1/robots/{robot_id}/execution/{action_id}/complete   — mark action done
GET  /v1/robots/{robot_id}/execution/{action_id}            — get execution state
GET  /v1/robots/{robot_id}/execution                        — list active executions
POST /v1/trajectory/validate                                — standalone trajectory validation
GET  /v1/workspace/zones                                    — list active zone claims
DELETE /v1/workspace/zones/{zone_name}                      — release a zone claim
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..physical.execution_monitor import (
    ExecutionStatus,
    TelemetryReading,
    get_active_executions,
    get_execution,
    ingest_telemetry,
    mark_completed,
    register_execution,
)
from ..physical.heartbeat import (
    VALID_POSTURES,
    deregister,
    get_posture,
    list_registrations,
    record_heartbeat,
    register,
)
from ..physical.trajectory import TrajectoryViolation, validate_trajectory
from ..physical.workspace_registry import list_claims, release_claim
from ..estop import trigger_estop
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["physical"])


def _require_request_tenant(request: Request, purpose: str) -> str:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(400, f"Tenant context is required to {purpose}.")
    return tenant_id


def _require_websocket_tenant(websocket: WebSocket, purpose: str) -> Optional[str]:
    tenant_id = getattr(websocket.state, "tenant_id", None)
    if not tenant_id:
        logger.warning("tenant_context_missing: websocket path=%s purpose=%s", websocket.url.path, purpose)
        return None
    return tenant_id


# ── Heartbeat ──────────────────────────────────────────────────────────────────

class HeartbeatBody(BaseModel):
    ttl_s: float = Field(default=10.0, ge=1.0, le=300.0,
                         description="Seconds before comm-loss watchdog triggers if no heartbeat received")
    comm_loss_posture: str = Field(
        default="freeze",
        description="What the robot should do if it loses contact: freeze | complete_and_halt | controlled_descent | safe_home",
    )
    tenant_id: Optional[str] = None


@router.post("/robots/{robot_id}/heartbeat")
async def heartbeat(robot_id: str, body: HeartbeatBody, request: Request):
    """Register or renew heartbeat monitoring for a robot.

    Call this once at startup to register (with ttl_s and comm_loss_posture),
    then call it periodically (at least every ttl_s seconds) to keep the watchdog satisfied.

    If no heartbeat is received within ttl_s seconds, the gateway will:
      1. Trigger an e-stop for this robot_id
      2. Release all workspace zone claims
      3. Fire a physical.comm_loss alert

    The comm_loss_posture is embedded in every governance ALLOW response so
    the robot knows its fallback behavior before a connection drop.
    """
    tenant_id = (body.tenant_id or "").strip() or _require_request_tenant(
        request,
        "register a robot heartbeat",
    )
    if body.comm_loss_posture not in VALID_POSTURES:
        raise HTTPException(
            status_code=422,
            detail=f"comm_loss_posture must be one of: {sorted(VALID_POSTURES)}",
        )
    hb = register(robot_id, tenant_id, ttl_s=body.ttl_s, comm_loss_posture=body.comm_loss_posture)
    record_heartbeat(robot_id)
    return {
        "robot_id": robot_id,
        "ttl_s": hb.ttl_s,
        "comm_loss_posture": hb.comm_loss_posture,
        "status": "registered",
        "message": f"Heartbeat registered. Send POST /v1/robots/{robot_id}/heartbeat every {hb.ttl_s:.0f}s.",
    }


@router.delete("/robots/{robot_id}/heartbeat")
async def deregister_heartbeat(robot_id: str):
    """Deregister a robot from heartbeat monitoring (e.g. planned shutdown)."""
    removed = deregister(robot_id)
    return {"robot_id": robot_id, "deregistered": removed}


@router.get("/robots/heartbeats")
async def list_heartbeats(request: Request):
    """List all registered robots and their heartbeat status for this tenant."""
    tenant_id = _require_request_tenant(request, "list robot heartbeats")
    return {"robots": list_registrations(tenant_id=tenant_id)}


# ── Execution telemetry ────────────────────────────────────────────────────────

class TelemetryBody(BaseModel):
    action_id: str
    joint_torques: dict[str, float] = Field(default_factory=dict)
    contact_forces: dict[str, float] = Field(default_factory=dict)
    position_deviation_m: Optional[float] = None
    velocity_ms: Optional[float] = None
    fault_code: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


@router.post("/robots/{robot_id}/telemetry")
async def ingest_robot_telemetry(robot_id: str, body: TelemetryBody, request: Request):
    """Stream execution telemetry for an in-progress action.

    Call this continuously (e.g. every 100ms) while the robot is executing.
    The monitor checks joint torques, ISO 15066 contact forces, position
    deviation, and velocity against the intent constraints registered at
    governance time.

    If an anomaly is detected, the monitor triggers an e-stop and returns
    anomaly=true with the reason. The robot should halt immediately.
    """
    tenant_id = _require_request_tenant(request, "record physical telemetry")
    import time
    reading = TelemetryReading(
        timestamp=time.monotonic(),
        joint_torques=body.joint_torques,
        contact_forces=body.contact_forces,
        position_deviation_m=body.position_deviation_m,
        velocity_ms=body.velocity_ms,
        fault_code=body.fault_code,
        raw=body.extra,
    )

    anomaly = ingest_telemetry(robot_id, body.action_id, reading)
    if anomaly:
        trigger_estop(
            robot_id=robot_id,
            reason=anomaly,
            triggered_by="execution_monitor",
            tenant_id=tenant_id,
        )
        try:
            from ..alerts.dispatcher import _dispatch
            _dispatch("physical.execution_anomaly", {
                "robot_id": robot_id,
                "action_id": body.action_id,
                "tenant_id": tenant_id,
                "reason": anomaly,
            })
        except Exception:
            pass
        return {
            "robot_id": robot_id,
            "action_id": body.action_id,
            "anomaly": True,
            "reason": anomaly,
            "action_required": "HALT IMMEDIATELY. E-stop triggered. Clear at DELETE /v1/estop/{robot_id} when safe.",
        }

    return {
        "robot_id": robot_id,
        "action_id": body.action_id,
        "anomaly": False,
    }


@router.websocket("/robots/{robot_id}/telemetry/stream")
async def telemetry_websocket(robot_id: str, websocket: WebSocket):
    """WebSocket streaming telemetry for high-frequency physical robots.

    Replaces the HTTP POST endpoint for robots that stream at >= 5 Hz.
    One persistent connection per robot per action, instead of thousands
    of individual HTTP requests.

    Frame format (JSON, client → server):
        {
            "action_id": "...",
            "joint_torques": {"shoulder": 45.2, "elbow": 12.1},
            "contact_forces": {"chest": 18.0},
            "position_deviation_m": 0.002,
            "velocity_ms": 0.8,
            "fault_code": null
        }

    Response frame (server → client):
        {"anomaly": false}                    — normal reading accepted
        {"anomaly": true, "reason": "...",    — anomaly detected
         "action_required": "HALT IMMEDIATELY. E-stop triggered."}

    On anomaly the server sends the halt frame and closes the connection.
    The robot must treat a closed connection as an implicit e-stop signal.
    """
    tenant_id = _require_websocket_tenant(websocket, "stream telemetry")
    if not tenant_id:
        await websocket.close(code=1008, reason="tenant_required")
        return
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            action_id = str(data.get("action_id", ""))
            reading = TelemetryReading(
                timestamp=time.monotonic(),
                joint_torques=data.get("joint_torques") or {},
                contact_forces=data.get("contact_forces") or {},
                position_deviation_m=data.get("position_deviation_m"),
                velocity_ms=data.get("velocity_ms"),
                fault_code=data.get("fault_code"),
                raw={k: v for k, v in data.items()
                     if k not in ("action_id", "joint_torques", "contact_forces",
                                  "position_deviation_m", "velocity_ms", "fault_code")},
            )
            record_heartbeat(robot_id)

            anomaly = ingest_telemetry(robot_id, action_id, reading)
            if anomaly:
                trigger_estop(
                    robot_id=robot_id,
                    reason=anomaly,
                    triggered_by="execution_monitor_ws",
                    tenant_id=tenant_id,
                )
                try:
                    from ..alerts.dispatcher import _dispatch
                    _dispatch("physical.execution_anomaly", {
                        "robot_id": robot_id,
                        "action_id": action_id,
                        "tenant_id": tenant_id,
                        "reason": anomaly,
                    })
                except Exception:
                    pass
                await websocket.send_json({
                    "anomaly": True,
                    "reason": anomaly,
                    "action_required": "HALT IMMEDIATELY. E-stop triggered. Clear at DELETE /v1/estop/{robot_id}.",
                })
                await websocket.close(code=1011, reason="execution_anomaly")
                return

            await websocket.send_json({"anomaly": False})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("[physical/ws] robot=%s error: %s", robot_id, exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@router.post("/robots/{robot_id}/execution/{action_id}/complete")
async def complete_execution(robot_id: str, action_id: str, request: Request):
    """Mark an action as completed (releases workspace zone claims)."""
    tenant_id = _require_request_tenant(request, "complete a physical execution")
    state = get_execution(robot_id, action_id)
    if state is None or state.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Execution not found")
    mark_completed(robot_id, action_id)
    # Release workspace zones claimed by this action
    try:
        from ..physical.workspace_registry import _claims, _lock
        with _lock:
            to_release = [k for k, c in _claims.items() if c.robot_id == robot_id and c.action_id == action_id]
            for k in to_release:
                del _claims[k]
    except Exception:
        pass
    return {"robot_id": robot_id, "action_id": action_id, "status": "completed"}


@router.get("/robots/{robot_id}/execution/{action_id}")
async def get_execution_state(robot_id: str, action_id: str, request: Request):
    """Get the current governance execution state for a specific action."""
    tenant_id = _require_request_tenant(request, "view a physical execution state")
    state = get_execution(robot_id, action_id)
    if state is None or state.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {
        "robot_id": state.robot_id,
        "action_id": state.action_id,
        "status": state.status.value,
        "duration_s": round(state.duration_s, 2),
        "anomaly_reason": state.anomaly_reason,
        "telemetry_readings": len(state.telemetry_buffer),
    }


@router.get("/robots/{robot_id}/execution")
async def list_executions(robot_id: str, request: Request):
    """List active (running) executions for a robot."""
    tenant_id = _require_request_tenant(request, "list physical executions")
    states = [s for s in get_active_executions(robot_id) if s.tenant_id == tenant_id]
    return {
        "robot_id": robot_id,
        "active_count": len(states),
        "executions": [
            {
                "action_id": s.action_id,
                "status": s.status.value,
                "duration_s": round(s.duration_s, 2),
            }
            for s in states
        ],
    }


# ── Standalone trajectory validation ──────────────────────────────────────────

class TrajectoryValidateBody(BaseModel):
    trajectory: list[dict[str, Any]]
    constraints: dict[str, Any] = Field(default_factory=dict)
    robot_id: str = ""
    action_id: str = ""
    human_proximity_m: Optional[float] = None


@router.post("/trajectory/validate")
async def validate_trajectory_endpoint(body: TrajectoryValidateBody):
    """Validate a trajectory before issuing it to a robot.

    This is the same check the governor runs internally when an action includes
    a `trajectory` param. Call it standalone to pre-validate motion plans.

    Returns valid=true if all waypoints pass, or a list of violations with
    waypoint indices and reasons.
    """
    report = validate_trajectory(
        trajectory=body.trajectory,
        constraints=body.constraints,
        action_id=body.action_id,
        robot_id=body.robot_id,
        human_proximity_m=body.human_proximity_m,
    )
    return {
        "valid": report.valid,
        "waypoint_count": report.waypoint_count,
        "checked_by": report.checked_by,
        "violations": [
            {
                "waypoint_index": v.waypoint_index,
                "reason": v.reason,
                "severity": v.severity,
            }
            for v in report.violations
        ],
        "summary": report.first_violation_summary() if not report.valid else "All waypoints pass.",
    }


# ── Workspace zones ────────────────────────────────────────────────────────────

@router.get("/workspace/zones")
async def get_workspace_zones(request: Request):
    """List all active workspace zone claims for this tenant."""
    tenant_id = _require_request_tenant(request, "list workspace zones")
    return {"zones": list_claims(tenant_id=tenant_id)}


@router.delete("/workspace/zones/{zone_name}")
async def release_zone(zone_name: str, robot_id: str, request: Request):
    """Manually release a workspace zone claim."""
    tenant_id = _require_request_tenant(request, "release a workspace zone")
    released = release_claim(tenant_id, zone_name, robot_id)
    return {"zone_name": zone_name, "robot_id": robot_id, "released": released}
