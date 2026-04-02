"""
NewsAPI connector — news search and headlines.

Credentials: API key stored in DB or env (NEWSAPI_KEY).
"""

import os
from typing import Dict, Any, Optional

import requests

from ..persistence import get_db
from ..config import config


class NewsApiConnector:
    """
    Connector for NewsAPI.
    """

    TOOL_NAME = "newsapi"
    BASE_URL = "https://newsapi.org/v2"

    def __init__(
        self,
        credential_id: str = "newsapi",
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
                "NewsAPI key missing. Set via credentials API or NEWSAPI_KEY in dev."
            )
        self.api_key = (os.getenv("NEWSAPI_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def search(
        self,
        q: str,
        language: str = "en",
        sort_by: str = "publishedAt",
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Search all news with a query.
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "NewsAPI connector not configured (missing API key)"}
        if not (q or "").strip():
            return {"success": False, "error": "q is required"}
        url = f"{self.BASE_URL}/everything"
        try:
            r = requests.get(
                url,
                params={
                    "q": q,
                    "language": language,
                    "sortBy": sort_by,
                    "pageSize": max(1, min(100, int(page_size or 20))),
                    "apiKey": self.api_key,
                },
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return {"success": True, "query": q, "results": data.get("articles", [])}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "query": q}

    def top_headlines(
        self,
        country: str = "us",
        category: Optional[str] = None,
        q: Optional[str] = None,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Get top headlines.
        """
        if not self.configured or not self.api_key:
            return {"success": False, "error": "NewsAPI connector not configured (missing API key)"}
        url = f"{self.BASE_URL}/top-headlines"
        params = {
            "country": country,
            "pageSize": max(1, min(100, int(page_size or 20))),
            "apiKey": self.api_key,
        }
        if category:
            params["category"] = category
        if q:
            params["q"] = q
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            return {"success": True, "results": data.get("articles", [])}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
