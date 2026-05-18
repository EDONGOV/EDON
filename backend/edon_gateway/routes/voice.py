"""EDON Voice Agent — ask Jarvis by voice.

POST /v1/voice/ask   — text/voice question → grounded answer + optional TTS audio
WS   /v1/voice/stream — WebSocket: send question, receive text then audio chunks

Auth: X-Bootstrap-Secret header (REST) or ?secret= query param (WebSocket).
TTS:  ElevenLabs (requires ELEVENLABS_API_KEY). Audio returned as base64 audio/mpeg.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..logging_config import get_logger
from ..security.bootstrap_auth import check_bootstrap_auth as _check_auth
from ..routes.jarvis import _run_jarvis  # jarvis AI engine — intentional dependency

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/voice", tags=["voice"])

_DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel


def _tts_sync(text: str) -> Optional[str]:
    """Blocking TTS call — run in a thread pool."""
    try:
        from ..connectors.elevenlabs_connector import ElevenLabsConnector
        tts = ElevenLabsConnector()
        result = tts.text_to_speech(text, voice_id=_DEFAULT_VOICE)
        if result.get("success") and result.get("audio_b64"):
            return result["audio_b64"]
    except Exception as exc:
        logger.warning("[voice] TTS failed: %s", exc)
    return None


async def _answer_to_audio(text: str) -> Optional[str]:
    """Run TTS in thread pool, return base64 audio/mpeg or None."""
    return await asyncio.to_thread(_tts_sync, text)


# ── REST endpoint ─────────────────────────────────────────────────────────────

class VoiceAskRequest(BaseModel):
    question: str
    return_audio: bool = True
    conversation: list[dict] | None = None


@router.post("/ask")
async def voice_ask(req: VoiceAskRequest, request: Request):
    """Ask EDON Jarvis a question. Returns grounded text answer + optional TTS audio.

    Set `return_audio: false` for text-only (faster). When audio is returned it is
    base64-encoded audio/mpeg — decode and play in any audio element.
    """
    _check_auth(request)

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    try:
        answer = await _run_jarvis(req.question, req.conversation)
        audio_b64: Optional[str] = None
        if req.return_audio:
            audio_b64 = await _answer_to_audio(answer)

        return {
            "answer": answer,
            "audio_b64": audio_b64,
            "audio_mime": "audio/mpeg" if audio_b64 else None,
        }
    except Exception as exc:
        logger.error("[voice] ask error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── WebSocket stream ──────────────────────────────────────────────────────────

@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    """WebSocket voice stream.

    Send: {"question": str, "return_audio": bool, "conversation": [...] | null}
    Receive sequence per question:
      {"type": "text",  "content": "<full answer>"}
      {"type": "audio", "content": "<base64 audio/mpeg>", "mime": "audio/mpeg"}  (if return_audio)
      {"type": "done"}
    Errors: {"type": "error", "content": "<message>"}
    """
    secret = os.getenv("EDON_BOOTSTRAP_SECRET", "")
    provided = websocket.query_params.get("secret", "")
    if secret and provided != secret:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    logger.info("[voice] WebSocket connected from %s", websocket.client)

    try:
        while True:
            data = await websocket.receive_json()
            question = (data.get("question") or "").strip()
            return_audio = data.get("return_audio", True)
            conversation = data.get("conversation")

            if not question:
                await websocket.send_json({"type": "error", "content": "question is empty"})
                continue

            try:
                answer = await _run_jarvis(question, conversation)
            except Exception as exc:
                await websocket.send_json({"type": "error", "content": str(exc)})
                continue

            await websocket.send_json({"type": "text", "content": answer})

            if return_audio:
                audio_b64 = await _answer_to_audio(answer)
                if audio_b64:
                    await websocket.send_json({
                        "type": "audio",
                        "content": audio_b64,
                        "mime": "audio/mpeg",
                    })

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("[voice] WebSocket disconnected")
    except Exception as exc:
        logger.error("[voice] WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "content": str(exc)})
        except Exception:
            pass
