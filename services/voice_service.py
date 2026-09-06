"""
Voice service.

Speech-to-text via Hugging Face Whisper.
  * Web: browser sends recorded audio blob → POST /api/voice → we transcribe.
  * WhatsApp: user sends a voice note → Meta gives us a media_id → we
    download + transcribe.
  * SMS: not applicable (SMS is text only).

Model:  openai/whisper-large-v3  — multilingual, handles Indian English
        + Hindi + code-mixed (very common in India).

For hosted inference we use the HF Inference API (audio endpoint).
"""
from __future__ import annotations

import base64
from typing import Any

import httpx
from loguru import logger

from config import settings

HF_AUDIO_URL = "https://api-inference.huggingface.co/models/{model}"

# Default to Whisper large-v3 for quality; switch to whisper-small for cost.
STT_MODEL = "openai/whisper-large-v3"

# Language hint helps a lot for Hindi / code-mixed audio.
SUPPORTED_LANGS = {"en", "hi", "auto"}


class VoiceService:
    def __init__(self) -> None:
        self.token = settings.HF_API_TOKEN
        self.enabled = bool(self.token)
        if not self.enabled:
            logger.warning("Voice STT disabled — set HF_API_TOKEN.")

    # ------------------------------------------------------------------
    # Speech-to-text
    # ------------------------------------------------------------------
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "auto",
        mime: str = "audio/webm",
    ) -> dict[str, Any]:
        """Return {'text': '...', 'language': '...'} or {'error': ...}."""
        if not self.enabled:
            return {"error": "STT disabled, no HF_API_TOKEN"}
        if len(audio_bytes) < 500:
            return {"error": "audio too short"}
        if len(audio_bytes) > 20 * 1024 * 1024:            # 20 MB cap
            return {"error": "audio too large"}

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": mime,
        }
        params = {}
        if language in {"en", "hi"}:
            params["language"] = language

        url = HF_AUDIO_URL.format(model=STT_MODEL)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    url, headers=headers, content=audio_bytes, params=params
                )
                if r.status_code == 503:
                    return {"error": "model warming up, retry in 20s"}
                r.raise_for_status()
                data = r.json()
                text = data.get("text", "").strip() if isinstance(data, dict) else ""
                return {"text": text, "language": language, "model": STT_MODEL}
        except Exception as e:
            logger.error(f"Whisper STT error: {e}")
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # WhatsApp voice-note flow
    # Meta sends media_id; we resolve URL then download the audio.
    # ------------------------------------------------------------------
    async def download_whatsapp_media(self, media_id: str) -> tuple[bytes, str] | None:
        """Fetch audio bytes from Meta by media_id."""
        wa_token = settings.META_WHATSAPP_TOKEN
        if not wa_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: get the media URL
                meta = await client.get(
                    f"https://graph.facebook.com/v20.0/{media_id}",
                    headers={"Authorization": f"Bearer {wa_token}"},
                )
                meta.raise_for_status()
                media_url = meta.json().get("url")
                mime = meta.json().get("mime_type", "audio/ogg")
                if not media_url:
                    return None
                # Step 2: download the file
                r = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {wa_token}"},
                )
                r.raise_for_status()
                return r.content, mime
        except Exception as e:
            logger.error(f"WA media download error: {e}")
            return None


voice_service = VoiceService()
