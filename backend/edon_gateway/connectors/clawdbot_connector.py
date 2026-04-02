"""
Clawdbot connector - calls Clawdbot Gateway /tools/invoke endpoint.
"""

import os
from typing import Dict, Any, Optional

import requests

from ..persistence import get_db
from ..config import config


class ClawdbotConnector:
    """
    Clawdbot connector that calls Clawdbot Gateway /tools/invoke endpoint.

    This proves "EDON is the only path to side effects" — agents cannot
    call Clawdbot tools directly because they do not have credentials.
    Only EDON can execute Clawdbot operations.
    """

    def __init__(
        self,
        credential_id: str = "clawdbot_gateway",
        tenant_id: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.tenant_id = tenant_id

        self.base_url: Optional[str] = None
        self.auth_mode: str = "password"  # "password" | "token"
        self.secret: Optional[str] = None

        # Runtime state
        self.configured: bool = False
        self.last_credential_error: Optional[str] = None

        # Attempt credential load, but NEVER crash process
        try:
            self._load_credentials()
            self.configured = True
        except RuntimeError as e:
            self.configured = False
            self.last_credential_error = str(e)

    @classmethod
    def from_inline(cls, base_url: str, auth_mode: str, secret: str):
        """
        Create connector from inline credentials (testing / probing only).
        """
        obj = cls.__new__(cls)
        obj.credential_id = "inline"
        obj.tenant_id = None
        obj.base_url = (base_url or "").rstrip("/")
        obj.auth_mode = auth_mode
        obj.secret = secret
        obj.configured = True
        obj.last_credential_error = None
        return obj

    def _fetch_credential(self, db, credential_id: str):
        return db.get_credential(
            credential_id=credential_id,
            tool_name="clawdbot",
            tenant_id=self.tenant_id,
        )

    def _load_credentials(self):
        """
        Load credentials from database or environment variables.

        Raises:
            RuntimeError if credentials not found and strict mode enabled.
        """

        db = get_db()

        # --- Database first: strict match (credential_id + tenant_id), no fallback to other tenant ---
        cred = self._fetch_credential(db, self.credential_id)

        if cred:
            data = cred.get("credential_data", {}) or {}

            base_url = (
                data.get("base_url")
                or data.get("gateway_url")
                or data.get("url")
                or ""
            )
            auth_mode = (data.get("auth_mode") or "password").strip().lower()

            # Normalize secret across various historical shapes
            secret = (
                data.get("secret")
                or data.get("token")
                or data.get("password")
                or data.get("gateway_token")
            )

            base_url = (base_url or "").rstrip("/")

            if base_url and secret:
                self.base_url = base_url
                self.auth_mode = auth_mode if auth_mode in ("password", "token") else "password"
                self.secret = str(secret)
                self.configured = True
                self.last_credential_error = None
                return

        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Clawdbot Gateway credentials missing. EDON_CREDENTIALS_STRICT=true disables env fallback. "
                "Configure via POST /integrations/clawdbot/connect."
            )
        env_secret = config.CLAWDBOT_GATEWAY_TOKEN
        env_url = config.CLAWDBOT_GATEWAY_URL or "http://127.0.0.1:18789"
        if env_secret:
            self.base_url = (env_url or "").rstrip("/")
            self.auth_mode = "token"
            self.secret = str(env_secret)
            self.configured = True
            self.last_credential_error = None
            return
        raise RuntimeError(
            "Clawdbot Gateway credentials missing. "
            "Configure via /integrations/clawdbot/connect."
        )

    def _build_headers(self) -> Dict[str, str]:
        """
        IMPORTANT: Your Clawdbot Gateway is clearly accepting Authorization: Bearer <secret>.
        In your logs/tests, X-CLAWDBOT-PASSWORD returned 401 while Authorization worked.

        Therefore:
        - auth_mode == token    -> Authorization: Bearer
        - auth_mode == password -> Authorization: Bearer  (same wire format)
        """
        if not self.secret:
            return {"Content-Type": "application/json"}

        return {
            "Authorization": f"Bearer {self.secret}",
            "Content-Type": "application/json",
        }

    def _record_invoke_success(self) -> None:
        """Record successful Clawdbot invoke for this credential (for integration status)."""
        if self.credential_id == "inline":
            return
        try:
            get_db().update_credential_status(
                self.credential_id, self.tenant_id, success=True, error_message=None
            )
        except Exception:
            pass

    def _record_invoke_failure(self, error_message: str) -> None:
        """Record failed Clawdbot invoke for this credential (for integration status)."""
        if self.credential_id == "inline":
            return
        try:
            get_db().update_credential_status(
                self.credential_id, self.tenant_id, success=False, error_message=error_message
            )
        except Exception:
            pass

    @staticmethod
    def _safe_json(resp: requests.Response) -> Any:
        """
        Parse JSON when possible; otherwise return text.
        """
        try:
            return resp.json()
        except Exception:
            return resp.text

    def invoke(
        self,
        tool: str,
        action: str = "json",
        args: Optional[Dict[str, Any]] = None,
        sessionKey: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a Clawdbot tool via Gateway /tools/invoke endpoint.
        """

        if not self.base_url or not self.secret:
            raise RuntimeError(
                "Clawdbot connector not configured. "
                "Credentials must be set before invoking tools."
            )

        payload: Dict[str, Any] = {
            "tool": tool,
            "action": action,
            "args": args or {},
        }
        if sessionKey:
            payload["sessionKey"] = sessionKey

        url = f"{self.base_url}/tools/invoke"
        headers = self._build_headers()

        try:
            r = requests.post(
                url,
                json=payload,     # correct: send object, not a JSON string
                headers=headers,
                timeout=30,
            )

            if r.status_code >= 400:
                detail = self._safe_json(r)
                self._record_invoke_failure(str(detail))
                raise RuntimeError(
                    f"Clawdbot Gateway HTTP error {r.status_code}: {detail}"
                )

            result = self._safe_json(r)
            if isinstance(result, dict) and result.get("ok"):
                self._record_invoke_success()
                return {
                    "success": True,
                    "tool": tool,
                    "action": action,
                    "result": result.get("result", {}),
                    "clawdbot_response": result,
                }

            # Non-ok but not HTTP error
            if isinstance(result, dict):
                err = result.get("error", "Unknown Clawdbot error")
            else:
                err = str(result)
            self._record_invoke_failure(err)
            return {
                "success": False,
                "tool": tool,
                "action": action,
                "error": err,
                "clawdbot_response": result if isinstance(result, dict) else None,
            }

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            self._record_invoke_failure(f"Clawdbot Gateway request failed: {str(e)}")
            return {
                "success": False,
                "tool": tool,
                "action": action,
                "error": f"Clawdbot Gateway request failed: {str(e)}",
                "downstream_unavailable": True,
            }
        except requests.exceptions.RequestException as e:
            self._record_invoke_failure(f"Clawdbot Gateway request failed: {str(e)}")
            return {
                "success": False,
                "tool": tool,
                "action": action,
                "error": f"Clawdbot Gateway request failed: {str(e)}",
                "downstream_unavailable": True,
            }


# ────────────────────────────────────────────────────────────────
# Connector factory (NO CACHE)
# ────────────────────────────────────────────────────────────────

from typing import Optional

def get_clawdbot_connector(
    *,
    credential_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> "ClawdbotConnector":
    """
    Return a fresh ClawdbotConnector each call.
    This ensures DB-updated credentials take effect immediately.
    """
    from ..config import config
    cred_id = credential_id or config.DEFAULT_CLAWDBOT_CREDENTIAL_ID
    return ClawdbotConnector(credential_id=cred_id, tenant_id=tenant_id)
