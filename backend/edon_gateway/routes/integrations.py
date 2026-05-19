"""Integration routes for EDON Gateway."""

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, UTC
from ..schemas.integrations import ClawdbotConnectRequest, ClawdbotConnectResponse
from ..persistence import get_db
from ..connectors.clawdbot_connector import ClawdbotConnector
from ..integration_catalog import get_enterprise_integration_catalog, get_enterprise_integration_target
from ..logging_config import get_logger
from ..config import config
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

VALID_CONNECT_SERVICES = {
    "gmail",
    "google_calendar",
    "brave_search",
    "github",
    "elevenlabs",
    "gemini",
    "polygon",
    "fmp",
    "newsapi",
    "home_assistant",
}
CONNECT_TTL_SECONDS = 600  # 10 minutes

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Connect services for Telegram /connect command: id, label, type (oauth vs api_key)
CONNECT_SERVICES: List[Dict[str, str]] = [
    {"id": "gmail", "label": "Gmail", "type": "oauth"},
    {"id": "google_calendar", "label": "Google Calendar", "type": "oauth"},
    {"id": "brave_search", "label": "Brave Search", "type": "api_key"},
    {"id": "github", "label": "GitHub", "type": "api_key"},
    {"id": "elevenlabs", "label": "ElevenLabs", "type": "api_key"},
    {"id": "gemini", "label": "Gemini", "type": "api_key"},
    {"id": "polygon", "label": "Polygon", "type": "api_key"},
    {"id": "fmp", "label": "FMP", "type": "api_key"},
    {"id": "newsapi", "label": "NewsAPI", "type": "api_key"},
    {"id": "home_assistant", "label": "Home Assistant", "type": "oauth"},
]

# Telegram inline keyboard: one row per service (callback_data = connect_<id>)
TELEGRAM_CONNECT_KEYBOARD: List[List[Dict[str, str]]] = [
    [{"text": "📧 Gmail", "callback_data": "connect_gmail"}],
    [{"text": "📅 Google Calendar", "callback_data": "connect_google_calendar"}],
    [{"text": "🔍 Brave Search", "callback_data": "connect_brave_search"}],
    [{"text": "🐙 GitHub", "callback_data": "connect_github"}],
    [{"text": "🔊 ElevenLabs", "callback_data": "connect_elevenlabs"}],
    [{"text": "✨ Gemini", "callback_data": "connect_gemini"}],
    [{"text": "📈 Polygon", "callback_data": "connect_polygon"}],
    [{"text": "💹 FMP", "callback_data": "connect_fmp"}],
    [{"text": "📰 NewsAPI", "callback_data": "connect_newsapi"}],
    [{"text": "🏠 Home Assistant", "callback_data": "connect_home_assistant"}],
]


class TelegramConnectCodeRequest(BaseModel):
    channel: str = "telegram"


class TelegramVerifyCodeRequest(BaseModel):
    code: str
    user_id: str
    chat_id: Optional[str] = None
    username: Optional[str] = None


class ConnectLinkRequest(BaseModel):
    service: str
    chat_id: Optional[str] = None


class ApiKeySubmitRequest(BaseModel):
    code: str
    api_key: str


class GitHubTokenSubmitRequest(BaseModel):
    code: str
    token: str


class AlertPreferencesUpdate(BaseModel):
    """Which events to alert the user about (via Telegram, Slack, or Discord)."""
    alert_on_blocked: Optional[bool] = None
    alert_on_policy_violation: Optional[bool] = None
    alert_on_drift: Optional[bool] = None
    alert_on_escalation: Optional[bool] = None


def _resolve_connect_base_url(request: Request) -> str:
    """Base URL for connect pages (config or request base)."""
    base = config.CONNECT_BASE_URL
    if base:
        return base
    return str(request.base_url).rstrip("/")


def _get_and_validate_service_code(code: str) -> Dict[str, Any]:
    """Resolve service code; raise HTTPException if invalid."""
    code = (code or "").strip().upper()
    db = get_db()
    entry = db.get_connect_service_code(code)
    if not entry:
        raise HTTPException(status_code=404, detail="Connect code not found")
    if entry.get("used_at"):
        raise HTTPException(status_code=409, detail="Connect code already used")
    try:
        expires_at = datetime.fromisoformat(entry["expires_at"])
    except Exception:
        expires_at = None
    if not expires_at or expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Connect code expired")
    return entry


@router.get("/connect/buttons")
async def get_connect_buttons() -> Dict[str, Any]:
    """Return connect service buttons for Telegram /connect command.

    Use this from the Telegram bot to show which services users can connect
    (Gmail, Google Calendar, Brave Search, GitHub, ElevenLabs).
    Returns both a list of services (id, label, type) and a ready-to-use
    Telegram inline keyboard (inline_keyboard format).
    """
    return {
        "services": CONNECT_SERVICES,
        "telegram_inline_keyboard": TELEGRAM_CONNECT_KEYBOARD,
    }


@router.get("/enterprise/catalog")
async def get_enterprise_catalog(approved_only: Optional[bool] = None) -> Dict[str, Any]:
    """Return the enterprise integration catalog.

    This is the canonical list of the hospital, enterprise, and physical-AI
    systems EDON is expected to integrate with. It records the auth and
    transport patterns the gateway is designed to govern.
    """
    enterprise_only = config.ENTERPRISE_MODE if approved_only is None else approved_only
    return get_enterprise_integration_catalog(approved_only=enterprise_only)


@router.get("/enterprise/catalog/{identifier}")
async def get_enterprise_catalog_target(identifier: str, approved_only: Optional[bool] = None) -> Dict[str, Any]:
    """Return one integration target by slug or category."""
    enterprise_only = config.ENTERPRISE_MODE if approved_only is None else approved_only
    target = get_enterprise_integration_target(identifier, approved_only=enterprise_only)
    if not target:
        raise HTTPException(status_code=404, detail="Enterprise integration target not found")
    return target


@router.post("/connect/link")
async def create_connect_link(request: Request, body: ConnectLinkRequest) -> Dict[str, Any]:
    """Create a one-time connect link for a service. Bot calls this when user taps a connect button."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    service = (body.service or "").strip().lower()
    if service not in VALID_CONNECT_SERVICES:
        raise HTTPException(status_code=400, detail=f"Invalid service. Use one of: {sorted(VALID_CONNECT_SERVICES)}")
    expires_at = (datetime.now(UTC) + timedelta(seconds=CONNECT_TTL_SECONDS)).isoformat()
    db = get_db()
    code = db.create_connect_service_code(
        tenant_id=tenant_id,
        service=service,
        expires_at=expires_at,
        chat_id=body.chat_id,
    )
    base = _resolve_connect_base_url(request)
    path = f"/integrations/connect/{service}"
    if service in ("gmail", "google_calendar"):
        path = f"/integrations/connect/{service}/start"
    url = f"{base}{path}?code={code}"
    return {"url": url, "code": code, "expires_in": CONNECT_TTL_SECONDS}


@router.get("/connect/status")
async def get_connect_status(request: Request) -> Dict[str, Any]:
    """Return which services are connected for the current tenant (for /connections in Telegram)."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        return {"services": {s: False for s in VALID_CONNECT_SERVICES}}
    db = get_db()
    connected = db.list_connected_services_for_tenant(tenant_id)
    return {"services": {s: (s in connected) for s in VALID_CONNECT_SERVICES}}


def _api_key_form_html(service: str, label: str, code: str, post_path: str, field_name: str = "api_key", field_placeholder: str = "Paste your API key") -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connect {label}</title></head>
<body style="font-family:sans-serif;max-width:400px;margin:2rem auto;padding:1rem;">
<h1>Connect {label}</h1>
<p>Paste your {label} {field_name.replace("_", " ")} below. It will be stored securely and never shown again.</p>
<form method="post" action="{post_path}">
<input type="hidden" name="code" value="{code}" />
<label>{field_name.replace("_", " ").title()}: <input type="password" name="{field_name}" placeholder="{field_placeholder}" style="width:100%;padding:0.5rem;" /></label>
<br><br><button type="submit">Connect</button>
</form>
<p style="color:#666;font-size:0.9rem;">After connecting, return to Telegram.</p>
</body></html>"""


def _home_assistant_form_html(code: str, post_path: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connect Home Assistant</title></head>
<body style="font-family:sans-serif;max-width:420px;margin:2rem auto;padding:1rem;">
<h1>Connect Home Assistant</h1>
<p>Enter your Home Assistant base URL and a long-lived access token.</p>
<form method="post" action="{post_path}">
<input type="hidden" name="code" value="{code}" />
<label>Base URL:
  <input type="url" name="base_url" placeholder="https://homeassistant.local:8123" style="width:100%;padding:0.5rem;" />
</label>
<br><br>
<label>Token:
  <input type="password" name="token" placeholder="Long-lived access token" style="width:100%;padding:0.5rem;" />
</label>
<br><br><button type="submit">Connect</button>
</form>
<p style="color:#666;font-size:0.9rem;">After connecting, return to Telegram.</p>
</body></html>"""


@router.get("/connect/brave_search", response_class=HTMLResponse)
async def connect_brave_form(request: Request, code: str = "") -> str:
    """Serve form to paste Brave Search API key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("brave_search", "Brave Search", code, f"{base}/integrations/connect/brave_search", "api_key", "Brave API key")


@router.post("/connect/brave_search")
async def connect_brave_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store Brave Search credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"brave_search_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="brave_search",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Brave%20Search", status_code=302)


@router.get("/connect/github", response_class=HTMLResponse)
async def connect_github_form(request: Request, code: str = "") -> str:
    """Serve form to paste GitHub token."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("github", "GitHub", code, f"{base}/integrations/connect/github", "token", "Personal access token")


@router.post("/connect/github")
async def connect_github_submit(request: Request, code: str = Form(""), token: str = Form("")) -> RedirectResponse:
    """Store GitHub credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    db = get_db()
    credential_id = f"github_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="github",
        credential_type="token",
        credential_data={"token": token},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=GitHub", status_code=302)


@router.get("/connect/elevenlabs", response_class=HTMLResponse)
async def connect_elevenlabs_form(request: Request, code: str = "") -> str:
    """Serve form to paste ElevenLabs API key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("elevenlabs", "ElevenLabs", code, f"{base}/integrations/connect/elevenlabs", "api_key", "ElevenLabs API key")


@router.post("/connect/elevenlabs")
async def connect_elevenlabs_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store ElevenLabs credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"elevenlabs_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="elevenlabs",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=ElevenLabs", status_code=302)


@router.get("/connect/gemini", response_class=HTMLResponse)
async def connect_gemini_form(request: Request, code: str = "") -> str:
    """Serve form to paste Gemini API key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("gemini", "Gemini", code, f"{base}/integrations/connect/gemini", "api_key", "Gemini API key")


@router.post("/connect/gemini")
async def connect_gemini_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store Gemini credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"gemini_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="gemini",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Gemini", status_code=302)


@router.get("/connect/polygon", response_class=HTMLResponse)
async def connect_polygon_form(request: Request, code: str = "") -> str:
    """Serve form to paste Polygon API key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("polygon", "Polygon", code, f"{base}/integrations/connect/polygon", "api_key", "Polygon API key")


@router.post("/connect/polygon")
async def connect_polygon_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store Polygon credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"polygon_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="polygon",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Polygon", status_code=302)


@router.get("/connect/fmp", response_class=HTMLResponse)
async def connect_fmp_form(request: Request, code: str = "") -> str:
    """Serve form to paste FMP API key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("fmp", "FMP", code, f"{base}/integrations/connect/fmp", "api_key", "FMP API key")


@router.post("/connect/fmp")
async def connect_fmp_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store FMP credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"fmp_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="fmp",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=FMP", status_code=302)


@router.get("/connect/newsapi", response_class=HTMLResponse)
async def connect_newsapi_form(request: Request, code: str = "") -> str:
    """Serve form to paste NewsAPI key."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _api_key_form_html("newsapi", "NewsAPI", code, f"{base}/integrations/connect/newsapi", "api_key", "NewsAPI key")


@router.post("/connect/newsapi")
async def connect_newsapi_submit(request: Request, code: str = Form(""), api_key: str = Form("")) -> RedirectResponse:
    """Store NewsAPI credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    db = get_db()
    credential_id = f"newsapi_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="newsapi",
        credential_type="api_key",
        credential_data={"api_key": api_key},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=NewsAPI", status_code=302)


@router.get("/connect/home_assistant", response_class=HTMLResponse)
async def connect_home_assistant_form(request: Request, code: str = "") -> str:
    """Serve form to paste Home Assistant base URL + token."""
    _get_and_validate_service_code(code)
    base = _resolve_connect_base_url(request)
    return _home_assistant_form_html(code, f"{base}/integrations/connect/home_assistant")


@router.post("/connect/home_assistant")
async def connect_home_assistant_submit(
    request: Request,
    code: str = Form(""),
    base_url: str = Form(""),
    token: str = Form(""),
) -> RedirectResponse:
    """Store Home Assistant credential for tenant from connect code."""
    entry = _get_and_validate_service_code(code)
    base_url = (base_url or "").strip().rstrip("/")
    token = (token or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url required")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    db = get_db()
    credential_id = f"home_assistant_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="home_assistant",
        credential_type="token",
        credential_data={"base_url": base_url, "token": token},
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(code)
    base = _resolve_connect_base_url(request)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Home%20Assistant", status_code=302)


@router.get("/connect/success", response_class=HTMLResponse)
async def connect_success(request: Request, service: str = "Service") -> str:
    """Shown after user completes connect (OAuth or API key)."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connected</title></head>
<body style="font-family:sans-serif;max-width:400px;margin:2rem auto;padding:1rem;text-align:center;">
<h1>✓ {service} connected</h1>
<p>You can close this page and return to Telegram.</p>
</body></html>"""


# --- Gmail OAuth ---
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify"
GOOGLE_CALENDAR_SCOPES = "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events"


@router.get("/connect/gmail/start")
async def connect_gmail_start(request: Request, code: str = "") -> RedirectResponse:
    """Redirect to Google OAuth for Gmail. state = our connect code."""
    entry = _get_and_validate_service_code(code)
    client_id = config.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=503, detail="Gmail OAuth not configured (GOOGLE_CLIENT_ID)")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/gmail/callback"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={GMAIL_SCOPES}&state={code}&access_type=offline&prompt=consent"
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/connect/gmail/callback")
async def connect_gmail_callback(request: Request, state: str = "", code: str = "", error: Optional[str] = None) -> RedirectResponse:
    """Exchange Google OAuth code for tokens and save Gmail credential."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    entry = _get_and_validate_service_code(state)
    client_id = config.GOOGLE_CLIENT_ID
    client_secret = config.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Gmail OAuth not configured")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/gmail/callback"
    import requests as req_lib
    resp = req_lib.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text[:200]}")
    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)
    expires_at_ts = int(datetime.now(UTC).timestamp()) + expires_in
    db = get_db()
    credential_id = f"gmail_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="gmail",
        credential_type="oauth2",
        credential_data={
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "client_id": client_id,
            "client_secret": client_secret,
            "token_uri": "https://oauth2.googleapis.com/token",
            "expires_at": expires_at_ts,
        },
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(state)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Gmail", status_code=302)


@router.get("/connect/google_calendar/start")
async def connect_google_calendar_start(request: Request, code: str = "") -> RedirectResponse:
    """Redirect to Google OAuth for Calendar. state = our connect code."""
    entry = _get_and_validate_service_code(code)
    client_id = config.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=503, detail="Google Calendar OAuth not configured (GOOGLE_CLIENT_ID)")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/google_calendar/callback"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={GOOGLE_CALENDAR_SCOPES}&state={code}&access_type=offline&prompt=consent"
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/connect/google_calendar/callback")
async def connect_google_calendar_callback(request: Request, state: str = "", code: str = "", error: Optional[str] = None) -> RedirectResponse:
    """Exchange Google OAuth code for tokens and save Google Calendar credential."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    entry = _get_and_validate_service_code(state)
    client_id = config.GOOGLE_CLIENT_ID
    client_secret = config.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google Calendar OAuth not configured")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/google_calendar/callback"
    import requests as req_lib
    resp = req_lib.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text[:200]}")
    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)
    expires_at_ts = int(datetime.now(UTC).timestamp()) + expires_in
    db = get_db()
    credential_id = f"google_calendar_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="google_calendar",
        credential_type="oauth2",
        credential_data={
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "client_id": client_id,
            "client_secret": client_secret,
            "token_uri": "https://oauth2.googleapis.com/token",
            "expires_at": expires_at_ts,
            "calendar_id": "primary",
        },
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(state)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Google%20Calendar", status_code=302)


@router.get("/connect/home_assistant/start")
async def connect_home_assistant_start(request: Request, code: str = "") -> RedirectResponse:
    """Redirect to Home Assistant OAuth. state = our connect code."""
    entry = _get_and_validate_service_code(code)
    base_url = config.HOME_ASSISTANT_BASE_URL
    client_id = config.HOME_ASSISTANT_CLIENT_ID
    if not base_url or not client_id:
        raise HTTPException(status_code=503, detail="Home Assistant OAuth not configured")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/home_assistant/callback"
    url = (
        f"{base_url}/auth/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&state={code}"
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/connect/home_assistant/callback")
async def connect_home_assistant_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: Optional[str] = None,
) -> RedirectResponse:
    """Exchange Home Assistant OAuth code for tokens and save credential."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    entry = _get_and_validate_service_code(state)
    base_url = config.HOME_ASSISTANT_BASE_URL
    client_id = config.HOME_ASSISTANT_CLIENT_ID
    client_secret = config.HOME_ASSISTANT_CLIENT_SECRET
    if not base_url or not client_id:
        raise HTTPException(status_code=503, detail="Home Assistant OAuth not configured")
    base = _resolve_connect_base_url(request)
    redirect_uri = f"{base}/integrations/connect/home_assistant/callback"
    token_url = f"{base_url}/auth/token"
    import requests as req_lib
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = req_lib.post(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text[:200]}")
    oauth = resp.json()
    access_token = oauth.get("access_token")
    refresh_token = oauth.get("refresh_token")
    expires_in = oauth.get("expires_in", 3600)
    expires_at_ts = int(datetime.now(UTC).timestamp()) + int(expires_in or 0)
    db = get_db()
    credential_id = f"home_assistant_{entry['tenant_id']}"
    db.save_credential(
        credential_id=credential_id,
        tool_name="home_assistant",
        credential_type="oauth2",
        credential_data={
            "base_url": base_url,
            "access_token": access_token,
            "refresh_token": refresh_token or "",
            "client_id": client_id,
            "client_secret": client_secret or "",
            "token_url": token_url,
            "expires_at": expires_at_ts,
        },
        encrypted=True,
        tenant_id=entry["tenant_id"],
    )
    db.mark_connect_service_code_used(state)
    return RedirectResponse(url=f"{base}/integrations/connect/success?service=Home%20Assistant", status_code=302)


@router.post("/clawdbot/connect", response_model=ClawdbotConnectResponse)
async def connect_clawdbot(request: Request, body: ClawdbotConnectRequest):
    """Connect Edonbot (bot gateway) integration.
    
    Validates connection by calling sessions_list (if probe=true), then stores credentials.
    
    Args:
        request: FastAPI request (auth middleware populates tenant_id)
        body: Connection details
        
    Returns:
        Connection status and credential info
    """
    tenant_id = get_request_tenant_id(request)
    
    # Optional probe before saving
    if body.probe:
        try:
            # Create an ephemeral connector instance using provided creds (not DB)
            connector = ClawdbotConnector.from_inline(
                base_url=body.base_url,
                auth_mode=body.auth_mode,
                secret=body.secret,
            )
            # Minimal probe: sessions_list
            result = connector.invoke(tool="sessions_list", action="json", args={})
            if not result.get("success"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Edonbot probe failed: {result.get('error', 'Unknown error')}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Clawdbot probe failed: {str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"Edonbot probe failed: {str(e)}")
    
    # Save credential in EDON DB (tenant-scoped if tenant_id exists)
    db = get_db()
    credential_data = {
        "base_url": body.base_url,
        "auth_mode": body.auth_mode,
        "secret": body.secret,
    }
    
    default_cred_id = config.DEFAULT_CLAWDBOT_CREDENTIAL_ID
    credential_id = (body.credential_id or "").strip() or default_cred_id
    if credential_id == "clawdbot_gateway":
        credential_id = default_cred_id
    if tenant_id and credential_id != default_cred_id:
        credential_id = f"{credential_id}_{tenant_id}"
    
    db.save_credential(
        credential_id=credential_id,
        tool_name="clawdbot",
        credential_type="gateway",
        credential_data=credential_data,
        encrypted=True,
        tenant_id=tenant_id
    )
    if body.probe:
        db.update_credential_status(credential_id, tenant_id, success=True, error_message=None)
    logger.info(f"Edonbot connected successfully. Credential ID: {credential_id}, Tenant: {tenant_id}")
    
    return ClawdbotConnectResponse(
        connected=True,
        credential_id=credential_id,
        base_url=body.base_url,
        auth_mode=body.auth_mode,
        message="Edonbot connected. Credential saved.",
    )


@router.get("/account/integrations")
async def get_integration_status(request: Request) -> Dict[str, Any]:
    """Get integration status for current tenant.
    
    Returns:
        Integration status including:
        - connected: bool
        - base_url: Optional[str]
        - auth_mode: Optional[str]
        - last_ok_at: Optional[str]
        - last_error: Optional[str]
        - active_policy_pack: Optional[str]
        - default_intent_id: Optional[str]
    """
    try:
        tenant_id = get_request_tenant_id(request)
        db = get_db()

        # Get Clawdbot integration status
        integration_status = db.get_integration_status(tenant_id, tool_name="clawdbot")

        # Get active policy pack
        active_preset = db.get_active_policy_preset()

        # Get tenant default intent
        default_intent_id = None
        if tenant_id:
            default_intent_id = db.get_tenant_default_intent(tenant_id)

        # Network gating status
        from ..security.network_gating import validate_network_gating, get_clawdbot_base_url

        base_url = integration_status.get("base_url") or get_clawdbot_base_url()
        network_gating_enabled = config.NETWORK_GATING

        is_valid, reachability, risk, recommendation = validate_network_gating(
            base_url,
            network_gating_enabled
        )

        clawdbot_status = {
            "connected": integration_status.get("connected", False),
            "base_url": integration_status.get("base_url"),
            "auth_mode": integration_status.get("auth_mode"),
            "last_ok_at": integration_status.get("last_ok_at"),
            "last_error": integration_status.get("last_error"),
            "active_policy_pack": active_preset.get("preset_name") if active_preset else None,
            "default_intent_id": default_intent_id,
            "network_gating_enabled": network_gating_enabled,
            "clawdbot_reachability": reachability,
            "bypass_risk": risk,
            "recommendation": recommendation if risk == "high" else None
        }

        # Channel status for alerts (Telegram, Slack, Discord)
        channels_connected = db.get_tenant_channel_connections(tenant_id) if tenant_id else []
        telegram = {"connected": "telegram" in channels_connected}
        slack = {"connected": "slack" in channels_connected}
        discord = {"connected": "discord" in channels_connected}

        # Alert preferences (what to notify user about)
        alert_preferences = db.get_tenant_alert_preferences(tenant_id) if tenant_id else {}

        return {
            "clawdbot": clawdbot_status,
            "telegram": telegram,
            "slack": slack,
            "discord": discord,
            "alert_preferences": alert_preferences,
        }

    except Exception as e:
        logger.error(f"Failed to get integration status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get integration status. Please try again or contact support."
        )


@router.get("/alert-preferences")
async def get_alert_preferences(request: Request) -> Dict[str, Any]:
    """Get alert preferences for the current tenant (what to notify on)."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        return {
            "alert_on_blocked": True,
            "alert_on_policy_violation": True,
            "alert_on_drift": True,
            "alert_on_escalation": True,
        }
    db = get_db()
    return db.get_tenant_alert_preferences(tenant_id)


@router.patch("/alert-preferences")
async def update_alert_preferences(request: Request, body: AlertPreferencesUpdate) -> Dict[str, Any]:
    """Update alert preferences (partial update)."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="No tenant context")
    prefs = body.model_dump(exclude_none=True)
    if not prefs:
        db = get_db()
        return db.get_tenant_alert_preferences(tenant_id)
    db = get_db()
    db.set_tenant_alert_preferences(tenant_id, prefs)
    return db.get_tenant_alert_preferences(tenant_id)


@router.post("/telegram/connect-code")
async def create_telegram_connect_code(request: Request, body: TelegramConnectCodeRequest):
    """Create a short-lived connect code for Telegram binding."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        if not config.DEMO_MODE:
            raise HTTPException(status_code=401, detail="No tenant context for connect code")
        tenant_id = config.DEMO_TENANT_ID
        # Ensure demo tenant exists
        db = get_db()
        tenant = db.get_tenant(tenant_id)
        if not tenant:
            import uuid
            demo_user = db.get_user_by_auth("demo", "demo")
            user_id = demo_user["id"] if demo_user else str(uuid.uuid4())
            if not demo_user:
                db.create_user(
                    user_id=user_id,
                    email="demo@edoncore.com",
                    auth_provider="demo",
                    auth_subject="demo",
                    role="admin",
                )
            db.create_tenant(tenant_id=tenant_id, user_id=user_id)

    ttl_minutes = config.TELEGRAM_CONNECT_TTL_MIN
    expires_at = (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).isoformat()
    db = get_db()
    code = db.create_connect_code(tenant_id=tenant_id, expires_at=expires_at, channel=body.channel)
    return {"code": code, "expires_at": expires_at, "ttl_minutes": ttl_minutes}


@router.post("/telegram/verify-code")
async def verify_telegram_connect_code(request: Request, body: TelegramVerifyCodeRequest):
    """Verify a Telegram connect code and bind the user to a tenant."""
    bot_secret = config.TELEGRAM_BOT_SECRET
    if not bot_secret:
        raise HTTPException(status_code=500, detail="Telegram bot secret not configured")

    header_secret = request.headers.get("X-EDON-BOT-SECRET") or request.headers.get("X-TELEGRAM-BOT-SECRET")
    if not header_secret or header_secret != bot_secret:
        raise HTTPException(status_code=401, detail="Invalid bot secret")

    code = (body.code or "").strip().upper()
    db = get_db()
    entry = db.get_connect_code(code)
    if not entry:
        raise HTTPException(status_code=404, detail="Connect code not found")
    if entry.get("used_at"):
        raise HTTPException(status_code=409, detail="Connect code already used")

    try:
        expires_at = datetime.fromisoformat(entry["expires_at"])
    except Exception:
        expires_at = None
    if not expires_at or expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Connect code expired")

    tenant_id = entry["tenant_id"]
    db.mark_connect_code_used(code, used_by=body.user_id)
    db.upsert_channel_binding(
        tenant_id=tenant_id,
        channel="telegram",
        external_user_id=str(body.user_id),
        external_chat_id=str(body.chat_id) if body.chat_id is not None else None,
        username=body.username,
    )
    token_info = db.create_channel_token(
        tenant_id=tenant_id,
        channel="telegram",
        external_user_id=str(body.user_id),
    )
    return {
        "tenant_id": tenant_id,
        "token": token_info["raw_token"],
        "channel": "telegram",
    }
