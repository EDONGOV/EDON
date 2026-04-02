"""
GitHub connector — repos, files, issues via GitHub REST API.
Credentials: Personal Access Token (PAT). Env: GITHUB_TOKEN or DB.
"""

import os
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class GitHubConnector:
    """
    Connector for GitHub API. EDON holds the token; agents request list/get/create via /execute.
    """

    TOOL_NAME = "github"
    BASE = "https://api.github.com"

    def __init__(
        self,
        credential_id: str = "github",
        tenant_id: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.tenant_id = tenant_id
        self.token: Optional[str] = None
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
            self.token = (data.get("token") or data.get("access_token") or "").strip()
            if self.token:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "GitHub token missing. Set via credentials API or GITHUB_TOKEN in dev."
            )
        self.token = (os.getenv("GITHUB_TOKEN") or "").strip()
        self.configured = bool(self.token)

    def _headers(self) -> Dict[str, str]:
        if not self.token:
            return {"Accept": "application/vnd.github.v3+json"}
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def list_repos(self, visibility: str = "all", per_page: int = 30) -> Dict[str, Any]:
        """List repositories for the authenticated user."""
        if not self.configured:
            return {"success": False, "error": "GitHub connector not configured"}
        try:
            r = requests.get(
                f"{self.BASE}/user/repos",
                params={"visibility": visibility, "per_page": min(100, per_page)},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            repos = [{"name": x.get("name"), "full_name": x.get("full_name"), "private": x.get("private")} for x in data]
            return {"success": True, "repos": repos, "count": len(repos)}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def get_file(self, owner: str, repo: str, path: str) -> Dict[str, Any]:
        """Get file contents (decoded). path e.g. README.md."""
        if not self.configured:
            return {"success": False, "error": "GitHub connector not configured"}
        try:
            r = requests.get(
                f"{self.BASE}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            import base64
            content_b64 = data.get("content", "")
            content = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""
            return {"success": True, "content": content, "sha": data.get("sha"), "path": path}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an issue."""
        if not self.configured:
            return {"success": False, "error": "GitHub connector not configured"}
        payload: Dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        try:
            r = requests.post(
                f"{self.BASE}/repos/{owner}/{repo}/issues",
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            out = r.json()
            return {
                "success": True,
                "number": out.get("number"),
                "html_url": out.get("html_url"),
                "state": out.get("state"),
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
