"""
Gemini connector — image generation + voice (TTS) via Google APIs.

Credentials: API key stored in DB or env (GEMINI_API_KEY).
"""

import os
from typing import Dict, Any, Optional, List

import requests

from ..persistence import get_db
from ..config import config


class GeminiConnector:
    """
    Connector for Gemini image generation and Google TTS.
    EDON holds the API key; agents call via /execute.
    """

    TOOL_NAME = "gemini"
    GENERATIVE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    IMAGE_MODEL = "imagen-3.0-generate-001"
    TTS_BASE_URL = "https://texttospeech.googleapis.com/v1"

    def __init__(
        self,
        credential_id: str = "gemini",
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
                "Gemini API key missing. Set via credentials API or GEMINI_API_KEY in dev."
            )
        self.api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        self.configured = bool(self.api_key)

    def generate_image(
        self,
        prompt: str,
        sample_count: int = 1,
        output_mime_type: str = "image/png",
    ) -> Dict[str, Any]:
        """
        Generate images from a prompt.
        Returns base64-encoded image bytes.
        """
        if not self.configured or not self.api_key:
            return {
                "success": False,
                "error": "Gemini connector not configured (missing API key)",
            }
        if not (prompt or "").strip():
            return {"success": False, "error": "prompt is required"}
        sample_count = min(4, max(1, int(sample_count or 1)))
        url = f"{self.GENERATIVE_BASE_URL}/models/{self.IMAGE_MODEL}:generateImages"
        payload: Dict[str, Any] = {
            "prompt": {"text": prompt},
            "imageParameters": {
                "sampleCount": sample_count,
                "outputMimeType": output_mime_type,
            },
        }
        try:
            r = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            images: List[str] = []
            for item in data.get("generatedImages", []) or []:
                b64 = item.get("bytesBase64Encoded")
                if b64:
                    images.append(b64)
            return {
                "success": True,
                "prompt": prompt,
                "images": images,
                "count": len(images),
                "output_mime_type": output_mime_type,
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def text_to_speech(
        self,
        text: str,
        language_code: str = "en-US",
        voice_name: str = "en-US-Standard-A",
        audio_encoding: str = "MP3",
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Convert text to speech using Google TTS (API key).
        Returns base64 audio content.
        """
        if not self.configured or not self.api_key:
            return {
                "success": False,
                "error": "Gemini connector not configured (missing API key)",
            }
        if not (text or "").strip():
            return {"success": False, "error": "text is required"}
        url = f"{self.TTS_BASE_URL}/text:synthesize"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": language_code, "name": voice_name},
            "audioConfig": {
                "audioEncoding": audio_encoding,
                "speakingRate": float(speaking_rate),
                "pitch": float(pitch),
            },
        }
        try:
            r = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "success": True,
                "audio_content": data.get("audioContent"),
                "audio_encoding": audio_encoding,
                "voice_name": voice_name,
                "language_code": language_code,
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}
