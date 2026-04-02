"""Integration schemas for EDON Gateway."""

from pydantic import BaseModel, Field
from typing import Literal, Optional

AuthMode = Literal["password", "token"]


class ClawdbotConnectRequest(BaseModel):
    """Request to connect Clawdbot Gateway integration."""
    base_url: str = Field(..., description="Clawdbot Gateway base URL, e.g. http://127.0.0.1:18789")
    auth_mode: AuthMode = Field("password", description="Authentication mode: password or token")
    secret: str = Field(..., description="Gateway password or token depending on auth_mode")
    credential_id: str = Field("clawdbot_gateway", description="Credential id to store under")
    probe: bool = Field(True, description="If true, validate by calling /tools/invoke before saving")


class ClawdbotConnectResponse(BaseModel):
    """Response from Clawdbot connection."""
    connected: bool
    credential_id: str
    base_url: str
    auth_mode: AuthMode
    message: str
