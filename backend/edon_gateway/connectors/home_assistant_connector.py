"""
Home Assistant connector — smart home control.

Credentials: base_url + token (preferred) or OAuth2 tokens stored in DB.
Fallback env vars: HOME_ASSISTANT_BASE_URL, HOME_ASSISTANT_TOKEN.
"""

from __future__ import annotations

import os
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class HomeAssistantConnector:
    """
    Connector for Home Assistant REST API.
    """

    TOOL_NAME = "home_assistant"

    def __init__(
        self,
        credential_id: str = "home_assistant",
        tenant_id: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.tenant_id = tenant_id
        self.base_url: Optional[str] = None
        self.token: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.token_url: Optional[str] = None
        self.expires_at: Optional[int] = None
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
            data = cred["credential_data"] or {}
            self.base_url = (data.get("base_url") or "").strip()
            self.token = (data.get("token") or "").strip()
            self.access_token = (data.get("access_token") or "").strip()
            self.refresh_token = (data.get("refresh_token") or "").strip()
            self.client_id = (data.get("client_id") or "").strip()
            self.client_secret = (data.get("client_secret") or "").strip()
            self.token_url = (data.get("token_url") or "").strip()
            self.expires_at = data.get("expires_at")
            if self.base_url:
                self.base_url = self.base_url.rstrip("/")
            self.configured = bool(self.base_url and (self.token or self.access_token or self.refresh_token))
            return

        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Home Assistant credentials missing. Set via credentials API or env vars in dev."
            )

        self.base_url = (os.getenv("HOME_ASSISTANT_BASE_URL") or "").strip().rstrip("/")
        self.token = (os.getenv("HOME_ASSISTANT_TOKEN") or "").strip()
        self.configured = bool(self.base_url and self.token)

    def _save_tokens(self) -> None:
        if not self.tenant_id:
            return
        db = get_db()
        db.save_credential(
            credential_id=self.credential_id,
            tool_name=self.TOOL_NAME,
            credential_type="oauth2",
            credential_data={
                "base_url": self.base_url or "",
                "token": self.token or "",
                "access_token": self.access_token or "",
                "refresh_token": self.refresh_token or "",
                "client_id": self.client_id or "",
                "client_secret": self.client_secret or "",
                "token_url": self.token_url or "",
                "expires_at": self.expires_at,
            },
            encrypted=True,
            tenant_id=self.tenant_id,
        )

    def _refresh_access_token(self) -> None:
        if not self.refresh_token:
            return
        if not self.token_url:
            if not self.base_url:
                return
            self.token_url = f"{self.base_url}/auth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id or "",
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        try:
            resp = requests.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            access_token = (data.get("access_token") or "").strip()
            refresh_token = (data.get("refresh_token") or "").strip()
            expires_in = int(data.get("expires_in") or 0)
            if access_token:
                self.access_token = access_token
            if refresh_token:
                self.refresh_token = refresh_token
            if expires_in:
                from datetime import datetime, UTC
                self.expires_at = int(datetime.now(UTC).timestamp()) + expires_in
            self._save_tokens()
        except requests.exceptions.RequestException:
            return

    def _auth_header(self) -> Dict[str, str]:
        if self.expires_at and self.access_token:
            from datetime import datetime, UTC
            now_ts = int(datetime.now(UTC).timestamp())
            if now_ts >= int(self.expires_at) - 60:
                self._refresh_access_token()
        token = self.token or self.access_token
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _validate_configured(self) -> Optional[str]:
        if not self.base_url:
            return "Home Assistant base_url missing"
        if not (self.token or self.access_token or self.refresh_token):
            return "Home Assistant token missing"
        return None

    def list_entities(self) -> Dict[str, Any]:
        """
        List entity states.
        """
        error = self._validate_configured()
        if error:
            return {"success": False, "error": error}
        try:
            url = f"{self.base_url}/api/states"
            resp = requests.get(url, headers=self._auth_header(), timeout=20)
            resp.raise_for_status()
            data = resp.json()
            entities: List[Dict[str, Any]] = []
            for entry in data or []:
                entity_id = entry.get("entity_id")
                attrs = entry.get("attributes") or {}
                entities.append(
                    {
                        "entity_id": entity_id,
                        "state": entry.get("state"),
                        "name": attrs.get("friendly_name") or entity_id,
                        "domain": (entity_id or "").split(".")[0] if entity_id else None,
                    }
                )
            return {"success": True, "entities": entities}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def get_state(self, entity_id: str) -> Dict[str, Any]:
        """
        Get a single entity state.
        """
        error = self._validate_configured()
        if error:
            return {"success": False, "error": error}
        if not (entity_id or "").strip():
            return {"success": False, "error": "entity_id is required"}
        try:
            url = f"{self.base_url}/api/states/{entity_id}"
            resp = requests.get(url, headers=self._auth_header(), timeout=20)
            resp.raise_for_status()
            return {"success": True, "state": resp.json()}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "entity_id": entity_id}

    def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        service_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call a Home Assistant service (e.g., light/turn_on).
        """
        error = self._validate_configured()
        if error:
            return {"success": False, "error": error}
        if not (domain or "").strip():
            return {"success": False, "error": "domain is required"}
        if not (service or "").strip():
            return {"success": False, "error": "service is required"}
        payload = dict(service_data or {})
        if entity_id:
            payload.setdefault("entity_id", entity_id)
        try:
            url = f"{self.base_url}/api/services/{domain}/{service}"
            resp = requests.post(
                url,
                headers={**self._auth_header(), "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
