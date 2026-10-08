"""
Text-to-Speech (TTS) Service with Multi-Provider Routing.

Routes speech synthesis requests based on voice_config:
  - provider == 'hume' and emotion_state -> Hume Octave 2 (emotion-conditioned)
  - provider == 'sarvam'                 -> Sarvam AI Bulbul v2
  - default / provider == 'cartesia'     -> Cartesia Sonic-2
"""

import base64
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


def _extract_provider_and_voice(voice_config: Any) -> tuple[str, str]:
    """Extracts provider and voice_id from dict or object."""
    provider = ""
    voice_id = ""

    if isinstance(voice_config, dict):
        provider = (
            voice_config.get("provider")
            or voice_config.get("voice_provider")
            or voice_config.get("voice_provider_name")
            or ""
        )
        voice_id = voice_config.get("voice_id") or voice_config.get("id") or ""
    elif hasattr(voice_config, "provider"):
        provider = getattr(voice_config, "provider", "") or ""
        voice_id = getattr(voice_config, "voice_id", "") or getattr(voice_config, "id", "") or ""

    provider_str = (provider or "cartesia").lower().strip()
    voice_id_str = voice_id if (voice_id and voice_id != "default") else ""
    return provider_str, voice_id_str


async def synthesize_speech(
    text: str,
    voice_config: Any,
    api_keys: Any,
    emotion_state: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Synthesizes text into raw audio bytes using provider routing.

    Args:
        text: The transcript / prompt text to speak.
        voice_config: Dict or object specifying provider and voice_id.
        api_keys: Dictionary or object containing provider API keys.
        emotion_state: Optional dict with valence, arousal, dominant emotion, etc.

    Returns:
        Raw audio bytes (PCM / WAV).
    """
    if not text or not text.strip():
        return b""

    provider, voice_id = _extract_provider_and_voice(voice_config)

    # 1. Hume Octave 2 (if provider is hume and emotion_state is supplied)
    if provider == "hume" and emotion_state:
        hume_key = _extract_key(api_keys, "hume", settings.HUME_API_KEY)
        if hume_key:
            try:
                url = "https://api.hume.ai/v0/tts"
                headers = {
                    "X-Hume-Api-Key": hume_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "text": text,
                    "voice": {"name": voice_id or "default"},
                    "generation_parameters": {
                        "emotion_state": emotion_state,
                        "valence": emotion_state.get("valence", 0.0),
                        "arousal": emotion_state.get("arousal", 0.5),
                        "dominant_emotion": emotion_state.get("dominant", "neutral"),
                    },
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    logger.debug("Hume Octave 2 TTS success — audio bytes len: %d", len(response.content))
                    return response.content
            except Exception as exc:
                logger.error("Hume TTS error: %s. Falling back to Cartesia Sonic-2.", exc)
        else:
            logger.warning("Hume API key missing; falling back to Cartesia Sonic-2")

    # 2. Sarvam AI Bulbul v2
    elif provider == "sarvam":
        sarvam_key = _extract_key(api_keys, "sarvam", settings.SARVAM_API_KEY)
        if sarvam_key:
            try:
                url = "https://api.sarvam.ai/text-to-speech"
                headers = {
                    "api-subscription-key": sarvam_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": voice_id or "meera",
                    "pitch": 0,
                    "pace": 1.05,
                    "loudness": 1.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v1",
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    res_data = response.json()

                    audios = res_data.get("audios", [])
                    if audios and isinstance(audios, list) and len(audios) > 0:
                        audio_b64 = audios[0]
                        audio_bytes = base64.b64decode(audio_b64)
                        logger.debug("Sarvam AI Bulbul TTS success — audio bytes len: %d", len(audio_bytes))
                        return audio_bytes

                    logger.warning("Sarvam TTS returned empty audio list")
            except Exception as exc:
                logger.error("Sarvam AI Bulbul TTS error: %s. Falling back to Cartesia Sonic-2.", exc)
        else:
            logger.warning("Sarvam API key missing for TTS; falling back to Cartesia Sonic-2")

    # 3. Default: Cartesia Sonic-2
    return await _synthesize_cartesia(text, voice_id, api_keys)


async def _synthesize_cartesia(text: str, voice_id: str, api_keys: Any) -> bytes:
    """Helper function to POST text synthesis request to Cartesia Sonic-2."""
    cartesia_key = _extract_key(api_keys, "cartesia", settings.CARTESIA_API_KEY)
    if not cartesia_key:
        logger.error("Cartesia API key not provided for TTS synthesis")
        return b""

    try:
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": cartesia_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        }
        payload = {
            "model_id": "sonic-2",
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice_id or "79a125e8-cd45-4c13-8a25-89665a53543c",
            },
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.debug("Cartesia Sonic-2 TTS success — audio bytes len: %d", len(response.content))
            return response.content

    except Exception as exc:
        logger.error("Cartesia Sonic-2 TTS error: %s", exc)
        return b""
