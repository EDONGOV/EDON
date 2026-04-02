"""
ElevenLabs connector — text-to-speech via ElevenLabs API.
Credentials: API key. Env: ELEVENLABS_API_KEY or DB.
"""

import os
from typing import Dict, Any, Optional

import requests

from ..persistence import get_db
from ..config import config


class ElevenLabsConnector:
    """
    Connector for ElevenLabs TTS. EDON holds the API key; agents request speech via /execute.
    """

    TOOL_NAME = "elevenlabs"
    BASE = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        credential_id: str = "elevenlabs",
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
            self.api_key = (data.get("api_key") or data.get("xi_api_key") or "").strip()
            if self.api_key:
                self.configured = True
                return
        if config.CREDENTIALS_STRICT:
            raise RuntimeError(
                "ElevenLabs API key missing. Set via credentials API or ELEVENLABS_API_KEY in dev."
            )
        self.api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {"Content-Type": "application/json"}
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

    def text_to_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_monolingual_v1",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Convert text to speech. Returns audio URL or base64 (or error).
        voice_id: default is Rachel; use /v1/voices to list.
        """
        if not self.configured:
            return {"success": False, "error": "ElevenLabs connector not configured"}
        payload: Dict[str, Any] = {
            "text": text,
            "model_id": model_id,
            "voice_settings": kwargs.get("voice_settings", {}),
        }
        try:
            r = requests.post(
                f"{self.BASE}/text-to-speech/{voice_id}",
                json=payload,
                headers={**self._headers(), "Accept": "application/json"},
                timeout=30,
            )
            # Some plans return audio directly; API returns JSON with audio or redirect
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "")
                if "application/json" in ct:
                    data = r.json()
                    return {"success": True, "response": data}
                # Raw audio
                return {"success": True, "audio_size_bytes": len(r.content), "content_type": ct}
            return {
                "success": False,
                "error": r.text or str(r.status_code),
                "status_code": r.status_code,
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def list_voices(self) -> Dict[str, Any]:
        """List available voices."""
        if not self.configured:
            return {"success": False, "error": "ElevenLabs connector not configured"}
        try:
            r = requests.get(
                f"{self.BASE}/voices",
                headers={"xi-api-key": self.api_key or "", "Content-Type": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            voices = data.get("voices", [])
            return {
                "success": True,
                "voices": [{"voice_id": v.get("voice_id"), "name": v.get("name")} for v in voices],
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
