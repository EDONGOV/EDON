"""
Gmail connector — read/send email via Gmail API (REST).
Credentials: OAuth2 access_token (or refresh_token + client_id/secret). Env: GMAIL_ACCESS_TOKEN or DB.
"""

import os
import base64
import time
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class GmailConnector:
    """
    Connector for Gmail API. EDON holds the token; agents request list/send via /execute.
    Uses Gmail REST API (https://gmail.googleapis.com/gmail/v1/).
    """

    TOOL_NAME = "gmail"
    BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(
        self,
        credential_id: str = "gmail",
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
            self.refresh_token = (data.get("refresh_token") or "").strip() or None
            self.client_id = (data.get("client_id") or "").strip() or None
            self.client_secret = (data.get("client_secret") or "").strip() or None
            self.token_uri = (data.get("token_uri") or self.token_uri).strip() or self.token_uri
            self.expires_at = int(data.get("expires_at")) if data.get("expires_at") else None
            self._credential_type = cred.get("credential_type") or "oauth"
            if self.access_token:
                self.configured = True
            # Try refresh if token is missing/expired but refresh token is present
            self._ensure_token()
            if self.access_token:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Gmail credentials missing. Set via credentials API or GMAIL_ACCESS_TOKEN in dev."
            )
        self.access_token = (os.getenv("GMAIL_ACCESS_TOKEN") or "").strip()
        self.refresh_token = (os.getenv("GMAIL_REFRESH_TOKEN") or "").strip() or None
        self.client_id = (os.getenv("GMAIL_CLIENT_ID") or "").strip() or None
        self.client_secret = (os.getenv("GMAIL_CLIENT_SECRET") or "").strip() or None
        self.token_uri = (os.getenv("GMAIL_TOKEN_URI") or self.token_uri).strip() or self.token_uri
        _expires_at_str = os.getenv("GMAIL_EXPIRES_AT")
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

    def list_messages(
        self,
        max_results: int = 10,
        q: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """List message IDs (and thread IDs). Optional q (Gmail query) and label_ids (e.g. INBOX)."""
        if not self.configured:
            return {"success": False, "error": "Gmail connector not configured"}
        params: Dict[str, Any] = {"maxResults": min(50, max(1, max_results))}
        if q:
            params["q"] = q
        if label_ids:
            params["labelIds"] = label_ids
        try:
            r = requests.get(
                f"{self.BASE}/messages",
                params=params,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            messages = data.get("messages") or []
            return {
                "success": True,
                "messages": [{"id": m["id"], "threadId": m.get("threadId")} for m in messages],
                "resultSizeEstimate": data.get("resultSizeEstimate", 0),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def get_message(self, message_id: str, format: str = "metadata") -> Dict[str, Any]:
        """Get one message. format: metadata, full, raw, minimal."""
        if not self.configured:
            return {"success": False, "error": "Gmail connector not configured"}
        try:
            r = requests.get(
                f"{self.BASE}/messages/{message_id}",
                params={"format": format},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            msg = r.json()
            snippet = msg.get("snippet", "")
            subject = ""
            from_addr = ""
            for h in msg.get("payload", {}).get("headers", []):
                if h.get("name", "").lower() == "subject":
                    subject = h.get("value", "")
                if h.get("name", "").lower() == "from":
                    from_addr = h.get("value", "")
            return {
                "success": True,
                "id": msg.get("id"),
                "threadId": msg.get("threadId"),
                "snippet": snippet,
                "subject": subject,
                "from": from_addr,
                "labelIds": msg.get("labelIds", []),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def send_message(
        self,
        to: Optional[str] = None,
        recipients: Optional[List[str]] = None,
        subject: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send an email. to or recipients, subject, body (plain text)."""
        if not self.configured:
            return {"success": False, "error": "Gmail connector not configured"}
        to_list = recipients or ([to] if to else [])
        if not to_list:
            return {"success": False, "error": "No recipients"}
        raw_to = ", ".join(to_list)
        raw_message = (
            f"To: {raw_to}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            f"{body}"
        )
        raw_b64 = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("ascii")
        try:
            r = requests.post(
                f"{self.BASE}/messages/send",
                json={"raw": raw_b64},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            out = r.json()
            return {
                "success": True,
                "id": out.get("id"),
                "threadId": out.get("threadId"),
                "labelIds": out.get("labelIds", []),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
