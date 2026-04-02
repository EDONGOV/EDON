"""EDON Gateway Tool Connectors. Optional connectors are imported only if present."""

import importlib

from .email_connector import EmailConnector
from .filesystem_connector import FilesystemConnector

__all__ = ["EmailConnector", "FilesystemConnector"]

# Optional connectors (may not be in repo in minimal/CI installs)
_optional = [
    ("brave_search_connector", "BraveSearchConnector"),
    ("gmail_connector", "GmailConnector"),
    ("google_calendar_connector", "GoogleCalendarConnector"),
    ("elevenlabs_connector", "ElevenLabsConnector"),
    ("github_connector", "GitHubConnector"),
    ("gemini_connector", "GeminiConnector"),
    ("polygon_connector", "PolygonConnector"),
    ("fmp_connector", "FmpConnector"),
    ("newsapi_connector", "NewsApiConnector"),
    ("home_assistant_connector", "HomeAssistantConnector"),
    ("memory_connector", "MemoryConnector"),
]
for _mod_name, _attr in _optional:
    try:
        _mod = importlib.import_module("." + _mod_name, package=__name__)
        _cls = getattr(_mod, _attr)
        globals()[_attr] = _cls
        __all__.append(_attr)
    except (ImportError, AttributeError):
        pass
