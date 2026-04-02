"""
Brave Search connector — web search via Brave Search API.
Credentials: API key (X-Subscription-Token). Env: BRAVE_SEARCH_API_KEY or DB.
"""

import os
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class BraveSearchConnector:
    """
    Connector for Brave Search API (web search).
    EDON holds the API key; agents request search via /execute.
    """

    TOOL_NAME = "brave_search"
    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        credential_id: str = "brave_search",
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
            self.api_key = (data.get("api_key") or data.get("subscription_token") or "").strip()
            if self.api_key:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "Brave Search API key missing. Set via credentials API or BRAVE_SEARCH_API_KEY in dev."
            )
        self.api_key = (os.getenv("BRAVE_SEARCH_API_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def search(
        self,
        q: str,
        count: int = 10,
        country: Optional[str] = None,
        freshness: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Web search. Params: q (query), count (1–20), country (e.g. US), freshness (pd, pw, pm, py).
        """
        if not self.configured or not self.api_key:
            return {
                "success": False,
                "error": "Brave Search connector not configured (missing API key)",
            }
        params: Dict[str, Any] = {"q": q, "count": min(20, max(1, count))}
        if country:
            params["country"] = country
        if freshness:
            params["freshness"] = freshness
        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json",
        }
        try:
            r = requests.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            results: List[Dict[str, Any]] = []
            web = data.get("web") or {}
            for item in (web.get("results") or [])[:count]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                })
            return {
                "success": True,
                "query": q,
                "results": results,
                "count": len(results),
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "query": q,
            }
