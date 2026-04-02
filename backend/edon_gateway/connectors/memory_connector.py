"""
Memory connector — long-term preferences and episodic task memory.
Writes are intentional and governor-approved; no automatic writes.
"""

from typing import Dict, Any, Optional, List

from ..persistence import get_db


class MemoryConnector:
    """
    Connector for agent memory: preferences (KV) and episodic (task history).
    EDON owns storage; agents read/write only via /execute with governor approval.
    """

    TOOL_NAME = "memory"

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id or "default"

    def write_preference(self, key: str, value: str) -> Dict[str, Any]:
        """Write one preference. Intentional only."""
        try:
            get_db().write_preference(self.tenant_id, key, value)
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_preferences(self, keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """Read preferences. keys=None returns all for tenant."""
        try:
            prefs = get_db().read_preferences(self.tenant_id, keys=keys)
            return {"success": True, "preferences": prefs}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_episode(
        self,
        episode_id: str,
        task_summary: str,
        outcome: Optional[str] = None,
        tool: Optional[str] = None,
        op: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append one episode. Intentional only."""
        try:
            get_db().append_episode(
                tenant_id=self.tenant_id,
                episode_id=episode_id,
                task_summary=task_summary,
                outcome=outcome,
                tool=tool,
                op=op,
                context=context,
            )
            return {"success": True, "episode_id": episode_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def query_episodes(
        self,
        limit: int = 50,
        since: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query episodic memory (most recent first)."""
        try:
            episodes = get_db().query_episodes(
                tenant_id=self.tenant_id,
                limit=limit,
                since=since,
                tool=tool,
            )
            return {"success": True, "episodes": episodes, "count": len(episodes)}
        except Exception as e:
            return {"success": False, "error": str(e)}
