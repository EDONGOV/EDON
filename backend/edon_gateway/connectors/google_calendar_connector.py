"""
Google Calendar connector — list/create events via Google Calendar API (REST).
Credentials: OAuth2 access_token. Env: GOOGLE_CALENDAR_ACCESS_TOKEN or DB.
"""

import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC

import requests

from ..persistence import get_db
from ..config import config


class GoogleCalendarConnector:
    """
    Connector for Google Calendar API. EDON holds the token; agents request list/create via /execute.
    """

    TOOL_NAME = "google_calendar"
    BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        credential_id: str = "google_calendar",
        tenant_id: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.tenant_id = tenant_id
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.token_uri: str = "https://oauth2.googleapis.com/token"
        self.expires_at: Optional[int] = None
        self._credential_type: str = "oauth"
        self.default_calendar_id: str = "primary"
        self.configured = False
        self._load_credentials()

    def _load_credentials(self) -> None:
        db = get_db()
        cred = db.get_credential(
            credential_id=self.credential_id,
            tool_name=self.TOOL_NAME,
            tenant_id=self.tenant_id,
        )
        if cred and cred.get("credential_data"):
            data = cred["credential_data"]
            self.access_token = (data.get("access_token") or data.get("token") or "").strip()
            self.default_calendar_id = (data.get("calendar_id") or "primary").strip() or "primary"
            self.refresh_token = (data.get("refresh_token") or "").strip() or None
            self.client_id = (data.get("client_id") or "").strip() or None
            self.client_secret = (data.get("client_secret") or "").strip() or None
            self.token_uri = (data.get("token_uri") or self.token_uri).strip() or self.token_uri
            self.expires_at = int(data.get("expires_at")) if data.get("expires_at") else None
            self._credential_type = cred.get("credential_type") or "oauth"
            if self.access_token:
                self.configured = True
            self._ensure_token()
            if self.access_token:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Google Calendar credentials missing. Set via credentials API or GOOGLE_CALENDAR_ACCESS_TOKEN in dev."
            )
        self.access_token = (os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN") or "").strip()
        self.refresh_token = (os.getenv("GOOGLE_CALENDAR_REFRESH_TOKEN") or "").strip() or None
        self.client_id = (os.getenv("GOOGLE_CALENDAR_CLIENT_ID") or "").strip() or None
        self.client_secret = (os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET") or "").strip() or None
        self.token_uri = (os.getenv("GOOGLE_CALENDAR_TOKEN_URI") or self.token_uri).strip() or self.token_uri
        _expires_at_str = os.getenv("GOOGLE_CALENDAR_EXPIRES_AT")
        self.expires_at = int(_expires_at_str) if _expires_at_str else None
        self.configured = bool(self.access_token)
        if not self.access_token and self.refresh_token and self.client_id and self.client_secret:
            self._ensure_token()
            self.configured = bool(self.access_token)

    def _token_expired(self) -> bool:
        if not self.expires_at:
            return False
        return int(time.time()) >= int(self.expires_at) - 60

    def _refresh_access_token(self) -> bool:
        if not (self.refresh_token and self.client_id and self.client_secret):
            return False
        try:
            resp = requests.post(
                self.token_uri,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
            )
            if resp.status_code >= 400:
                return False
            payload = resp.json()
            token = payload.get("access_token")
            if not token:
                return False
            self.access_token = token
            expires_in = int(payload.get("expires_in", 3600))
            self.expires_at = int(time.time()) + max(60, expires_in - 60)
            # Persist updated access_token/expires_at when DB credential exists
            try:
                data = {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "token_uri": self.token_uri,
                    "expires_at": self.expires_at,
                    "calendar_id": self.default_calendar_id,
                }
                get_db().save_credential(
                    credential_id=self.credential_id,
                    tool_name=self.TOOL_NAME,
                    credential_type=self._credential_type,
                    credential_data=data,
                    encrypted=True,
                    tenant_id=self.tenant_id,
                )
            except Exception:
                pass
            return True
        except requests.exceptions.RequestException:
            return False

    def _ensure_token(self) -> None:
        if not self.access_token:
            self._refresh_access_token()
            return
        if self._token_expired():
            self._refresh_access_token()

    def _headers(self) -> Dict[str, str]:
        self._ensure_token()
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def list_events(
        self,
        calendar_id: Optional[str] = None,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        single_events: bool = True,
    ) -> Dict[str, Any]:
        """List events. time_min/time_max in RFC3339 (e.g. 2025-02-01T00:00:00Z)."""
        if not self.configured:
            return {"success": False, "error": "Google Calendar connector not configured"}
        cal = calendar_id or self.default_calendar_id
        params: Dict[str, Any] = {
            "maxResults": min(100, max(1, max_results)),
            "singleEvents": single_events,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        try:
            r = requests.get(
                f"{self.BASE}/calendars/{cal}/events",
                params=params,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            events = []
            for item in data.get("items", []):
                start = item.get("start") or {}
                end = item.get("end") or {}
                events.append({
                    "id": item.get("id"),
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "location": item.get("location", ""),
                    "status": item.get("status", ""),
                })
            return {"success": True, "events": events, "count": len(events)}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def create_event(
        self,
        calendar_id: Optional[str] = None,
        summary: str = "",
        description: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an event. start/end in RFC3339 or date (YYYY-MM-DD)."""
        if not self.configured:
            return {"success": False, "error": "Google Calendar connector not configured"}
        cal = calendar_id or self.default_calendar_id
        # Default to now + 1 hour if not provided
        now = datetime.now(UTC)
        start_str = start or now.isoformat().replace("+00:00", "Z")
        end_str = end or (now.replace(hour=now.hour + 1).isoformat().replace("+00:00", "Z"))
        body: Dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_str, "timeZone": "UTC"},
            "end": {"dateTime": end_str, "timeZone": "UTC"},
        }
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        try:
            r = requests.post(
                f"{self.BASE}/calendars/{cal}/events",
                json=body,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            out = r.json()
            return {
                "success": True,
                "id": out.get("id"),
                "htmlLink": out.get("htmlLink"),
                "summary": out.get("summary"),
                "start": out.get("start", {}).get("dateTime"),
                "end": out.get("end", {}).get("dateTime"),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
