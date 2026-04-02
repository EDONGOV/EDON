"""
Financial Modeling Prep (FMP) connector — market data.

Credentials: API key stored in DB or env (FMP_API_KEY).
"""

import os
from typing import Dict, Any, Optional

import requests

from ..persistence import get_db
from ..config import config


class FmpConnector:
    """
    Connector for Financial Modeling Prep API.
    """

    TOOL_NAME = "fmp"
    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(
        self,
        credential_id: str = "fmp",
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
                "FMP API key missing. Set via credentials API or FMP_API_KEY in dev."
            )
        self.api_key = (os.getenv("FMP_API_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def quote(self, symbol: str) -> Dict[str, Any]:
        """
        Quote for a symbol.
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "FMP connector not configured (missing API key)"}
        if not (symbol or "").strip():
            return {"success": False, "error": "symbol is required"}
        url = f"{self.BASE_URL}/quote/{symbol.upper()}"
        try:
            r = requests.get(url, params={"apikey": self.api_key}, timeout=20)
            r.raise_for_status()
            data = r.json()
            return {"success": True, "symbol": symbol.upper(), "results": data}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "symbol": symbol.upper()}

    def stock_news(self, tickers: str, limit: int = 10) -> Dict[str, Any]:
        """
        Stock news for tickers (comma-separated).
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "FMP connector not configured (missing API key)"}
        if not (tickers or "").strip():
            return {"success": False, "error": "tickers is required"}
        url = f"{self.BASE_URL}/stock_news"
        try:
            r = requests.get(
                url,
                params={"tickers": tickers, "limit": max(1, min(50, int(limit or 10))), "apikey": self.api_key},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return {"success": True, "tickers": tickers, "results": data}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "tickers": tickers}
