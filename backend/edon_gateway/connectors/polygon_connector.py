"""
Polygon.io connector — market data.

Credentials: API key stored in DB or env (POLYGON_API_KEY).
"""

import os
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class PolygonConnector:
    """
    Connector for Polygon.io market data.
    """

    TOOL_NAME = "polygon"
    BASE_URL = "https://api.polygon.io"

    def __init__(
        self,
        credential_id: str = "polygon",
        tenant_id: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.tenant_id = tenant_id
        self.api_key: Optional[str] = None
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
            self.api_key = (data.get("api_key") or data.get("key") or "").strip()
            if self.api_key:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Polygon API key missing. Set via credentials API or POLYGON_API_KEY in dev."
            )
        self.api_key = (os.getenv("POLYGON_API_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def prev_close(self, ticker: str, adjusted: bool = True) -> Dict[str, Any]:
        """
        Previous close aggregate for a ticker.
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "Polygon connector not configured (missing API key)"}
        if not (ticker or "").strip():
            return {"success": False, "error": "ticker is required"}
        url = f"{self.BASE_URL}/v2/aggs/ticker/{ticker.upper()}/prev"
        try:
            r = requests.get(
                url,
                params={"adjusted": "true" if adjusted else "false", "apiKey": self.api_key},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "success": True,
                "ticker": ticker.upper(),
                "results": data.get("results", []),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "ticker": ticker.upper()}

    def ticker_details(self, ticker: str) -> Dict[str, Any]:
        """
        Reference details for a ticker.
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "Polygon connector not configured (missing API key)"}
        if not (ticker or "").strip():
            return {"success": False, "error": "ticker is required"}
        url = f"{self.BASE_URL}/v3/reference/tickers/{ticker.upper()}"
        try:
            r = requests.get(
                url,
                params={"apiKey": self.api_key},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "success": True,
                "ticker": ticker.upper(),
                "result": data.get("results", {}),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "ticker": ticker.upper()}
