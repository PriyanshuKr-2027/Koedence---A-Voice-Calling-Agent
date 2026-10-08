"""
Speech-to-Text (STT) Service with Hinglish Provider Routing.

Routes transcription requests based on language:
  - 'hi' or 'hinglish' -> Sarvam AI Saarika v2 (preserves Hindi-English code-switching)
  - default / 'en'     -> Groq Whisper large-v3 audio endpoint
"""

import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _extract_key(api_keys: Any, key_name: str, fallback_value: str = "") -> str:
    """Extracts an API key from a dict or object with fallback to settings."""
    if isinstance(api_keys, dict):
        val = api_keys.get(key_name) or api_keys.get(f"{key_name}_api_key")
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    elif hasattr(api_keys, key_name):
        val = getattr(api_keys, key_name)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return fallback_value or ""


async def transcribe_audio(
    audio_bytes: bytes,
    language: str,
    api_keys: Any,
) -> str:
    """
    Transcribes audio bytes to text using provider-specific routing.

    Args:
        audio_bytes: Raw audio byte stream (e.g. PCM / WAV / MP3 / Mu-law).
        language: Language code ('hi', 'hinglish', 'en', etc.).
        api_keys: Dictionary or object containing provider API keys.

    Returns:
        Transcribed text string, preserving code-switching for Hinglish.
    """
    if not audio_bytes:
        return ""

    lang = (language or "en").lower().strip()

    if lang in ["hi", "hinglish"]:
        sarvam_key = _extract_key(api_keys, "sarvam", settings.SARVAM_API_KEY)
        if not sarvam_key:
            logger.warning("Sarvam API key missing for Hinglish STT; falling back to Groq Whisper")
            return await _transcribe_groq_whisper(audio_bytes, api_keys)

        try:
            url = "https://api.sarvam.ai/speech-to-text"
            headers = {"api-subscription-key": sarvam_key}
            files = {
                "file": ("audio.wav", audio_bytes, "audio/wav")
            }
            data = {
                "model": "saarika:v2",
                "language_code": "hi-IN",
                "with_timings": "false",
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                res_data = response.json()

                transcript = (
                    res_data.get("transcript")
                    or res_data.get("text")
                    or (res_data.get("results", [{}])[0].get("transcript") if res_data.get("results") else "")
                    or ""
                )
                logger.debug("Sarvam STT success — transcript length: %d", len(transcript))
                return transcript.strip()

        except Exception as exc:
            logger.error("Sarvam AI STT error: %s. Falling back to Groq Whisper.", exc)
            return await _transcribe_groq_whisper(audio_bytes, api_keys)

    else:
        return await _transcribe_groq_whisper(audio_bytes, api_keys)


async def _transcribe_groq_whisper(audio_bytes: bytes, api_keys: Any) -> str:
    """Helper function to POST audio to Groq Whisper large-v3 endpoint."""
    groq_key = _extract_key(api_keys, "groq", settings.GROQ_API_KEY)
    if not groq_key:
        logger.error("Groq API key not provided for STT transcription")
        return ""

    try:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {groq_key}"}
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav")
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            res_data = response.json()

            transcript = res_data.get("text", "") or ""
            logger.debug("Groq Whisper STT success — transcript length: %d", len(transcript))
            return transcript.strip()

    except Exception as exc:
        logger.error("Groq Whisper STT error: %s", exc)
        return ""
