"""Telemetry ingestion routes — operator wearable data pipeline.

POST /v1/telemetry/operator/{operator_id}
    Accepts physiological / wearable signals from an E4 (Empatica) or
    compatible device and forwards them to the CAV engine.  Authentication
    is required via the standard X-EDON-TOKEN header (enforced by
    AuthMiddleware at the app level).

Fail-open: if the CAV engine is unreachable the endpoint still returns
200 so that the client does not have to handle CAV downtime as an error.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..cav_client import cav_client
from ..logging_config import get_logger
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


# ──────────────────────────────────────────────────────────────────────────────
# Request / response models
# ──────────────────────────────────────────────────────────────────────────────


class OperatorTelemetryRequest(BaseModel):
    """Wearable telemetry payload for a single time-window batch."""

    source: str = Field(..., description="Sensor/device identifier, e.g. 'empatica_e4'")
    EDA: List[float] = Field(default_factory=list, description="Electrodermal activity samples (µS)")
    BVP: List[float] = Field(default_factory=list, description="Blood volume pulse samples")
    TEMP: List[float] = Field(default_factory=list, description="Peripheral skin temperature samples (°C)")
    ACC_x: List[float] = Field(default_factory=list, description="Accelerometer X-axis samples (g)")
    ACC_y: List[float] = Field(default_factory=list, description="Accelerometer Y-axis samples (g)")
    ACC_z: List[float] = Field(default_factory=list, description="Accelerometer Z-axis samples (g)")
    timestamp: str = Field(..., description="ISO 8601 timestamp for the start of this batch")


class OperatorTelemetryResponse(BaseModel):
    ok: bool
    operator_id: str
    forwarded: bool
    note: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/operator/{operator_id}",
    response_model=OperatorTelemetryResponse,
    summary="Ingest operator wearable telemetry",
)
async def ingest_operator_telemetry(
    operator_id: str,
    request: Request,
    body: OperatorTelemetryRequest,
) -> OperatorTelemetryResponse:
    """Accept a batch of physiological wearable samples and forward to CAV.

    Authentication is enforced by the gateway-level AuthMiddleware — a valid
    ``X-EDON-TOKEN`` header must be present on every call.

    The endpoint validates that the ``operator_id`` path parameter is non-empty
    and (when tenant context is available) checks that the operator belongs to
    the requesting tenant.

    If the CAV engine is down, the response still returns HTTP 200 with
    ``forwarded: false`` so that callers do not need to handle CAV
    availability as a hard failure.

    Args:
        operator_id: URL path segment identifying the operator.
        request: FastAPI request (carries tenant context injected by middleware).
        body: Batch of telemetry samples.

    Returns:
        OperatorTelemetryResponse with ``forwarded`` flag and optional note.

    Raises:
        HTTPException 400: operator_id is empty or invalid.
        HTTPException 403: operator_id does not belong to the requesting tenant.
    """
    # Basic validation
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(status_code=400, detail="operator_id path parameter cannot be empty")

    # Tenant ownership check
    tenant_id = get_request_tenant_id(request)
    if tenant_id:
        # operator_id convention: must start with or contain the tenant_id, OR
        # the tenant record explicitly allows this operator.  We use a lightweight
        # prefix check here; projects with a full operator registry can replace
        # this with a DB lookup.
        if not _operator_belongs_to_tenant(operator_id, tenant_id):
            logger.warning(
                "Telemetry rejected: operator_id=%s does not belong to tenant=%s",
                operator_id,
                tenant_id,
            )
            raise HTTPException(
                status_code=403,
                detail=f"operator_id '{operator_id}' is not associated with this tenant.",
            )

    # Build the payload dict for CAV
    telemetry_payload = body.model_dump()

    # Forward to CAV engine
    logger.debug("Forwarding telemetry for operator=%s to CAV engine", operator_id)
    forwarded = cav_client.ingest_operator_telemetry(operator_id, telemetry_payload)

    if forwarded:
        logger.info("Telemetry forwarded: operator=%s tenant=%s", operator_id, tenant_id)
        return OperatorTelemetryResponse(ok=True, operator_id=operator_id, forwarded=True)

    # CAV is down — fail open
    logger.warning(
        "CAV engine unavailable; telemetry NOT forwarded: operator=%s tenant=%s",
        operator_id,
        tenant_id,
    )
    return OperatorTelemetryResponse(
        ok=True,
        operator_id=operator_id,
        forwarded=False,
        note="CAV engine unavailable — telemetry accepted but not forwarded.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _operator_belongs_to_tenant(operator_id: str, tenant_id: str) -> bool:
    """Return True if this operator_id is plausibly owned by the tenant.

    Current logic (lightweight, no DB round-trip):
      - If operator_id starts with the tenant_id prefix, allow it.
      - If operator_id contains the tenant_id substring, allow it.
      - Otherwise, deny.

    Projects with a full operator registry should replace this with a DB
    lookup such as ``db.get_operator_tenant(operator_id) == tenant_id``.
    """
    if tenant_id in operator_id:
        return True
    if operator_id.startswith(tenant_id):
        return True
    return False
