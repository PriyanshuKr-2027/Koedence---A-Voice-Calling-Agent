import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# Emotion mapping dictionary based on Circumplex Model of Affect (Valence [-1.0..1.0], Arousal [0.0..1.0])
EMOTION_CIRCUMPLEX_MAP: Dict[str, tuple] = {
    "admiration": (0.7, 0.5),
    "adoration": (0.8, 0.4),
    "aesthetic appreciation": (0.6, 0.3),
    "amusement": (0.8, 0.7),
    "anger": (-0.8, 0.8),
    "anxiety": (-0.7, 0.7),
    "awe": (0.6, 0.8),
    "awkwardness": (-0.3, 0.4),
    "boredom": (-0.4, 0.1),
    "calmness": (0.7, 0.1),
    "concentration": (0.2, 0.5),
    "confusion": (-0.2, 0.5),
    "contempt": (-0.7, 0.5),
    "contentment": (0.8, 0.2),
    "craving": (0.2, 0.6),
    "desire": (0.5, 0.6),
    "disgust": (-0.8, 0.4),
    "distress": (-0.8, 0.8),
    "doubt": (-0.3, 0.4),
    "ecstasy": (0.9, 0.9),
    "embarrassment": (-0.5, 0.5),
    "empathic pain": (-0.7, 0.5),
    "enthrallment": (0.7, 0.6),
    "enthusiasm": (0.8, 0.8),
    "envy": (-0.6, 0.5),
    "excitement": (0.8, 0.9),
    "fear": (-0.8, 0.8),
    "frustration": (-0.7, 0.7),
    "gratitude": (0.8, 0.3),
    "guilt": (-0.7, 0.3),
    "horror": (-0.9, 0.9),
    "interest": (0.6, 0.6),
    "joy": (0.9, 0.7),
    "love": (0.9, 0.4),
    "nostalgia": (0.3, 0.3),
    "pain": (-0.8, 0.7),
    "pride": (0.7, 0.6),
    "realization": (0.3, 0.6),
    "relief": (0.7, 0.2),
    "romance": (0.8, 0.4),
    "sadness": (-0.8, 0.2),
    "satisfaction": (0.8, 0.3),
    "shame": (-0.7, 0.3),
    "surprise": (0.3, 0.8),
    "sympathy": (0.5, 0.3),
    "tiredness": (-0.4, 0.1),
    "triumph": (0.8, 0.8),
    "neutral": (0.0, 0.3),
}


async def analyze_audio_emotion(
    audio_bytes: bytes,
    hume_api_key: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Analyzes paralinguistic audio emotion directly from caller's voice using Hume AI.

    Args:
        audio_bytes: Raw audio chunk bytes.
        hume_api_key: Hume AI API key string. Returns None immediately if key is None or empty.

    Returns:
        dict: {"valence": float, "arousal": float, "dominant": str, "confidence": float}
        None: If hume_api_key is None/empty or on any network/parsing error.
    """
    # If hume_api_key is None or empty: return None (no crash)
    if not hume_api_key or not isinstance(hume_api_key, str) or not hume_api_key.strip():
        logger.debug("Hume API key is None or empty — skipping audio emotion analysis")
        return None

    if not audio_bytes or len(audio_bytes) < 64:
        return None

    headers = {
        "X-Hume-Api-Key": hume_api_key.strip(),
    }

    try:
        url = "https://api.hume.ai/v0/batch/jobs"
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, files=files)
            if resp.status_code not in (200, 201, 202):
                # Try fallback Expression Measurement API endpoint
                alt_url = "https://api.hume.ai/v0/evm/models"
                resp = await client.post(alt_url, headers=headers, files=files)

        if resp.status_code not in (200, 201, 202):
            logger.warning("Hume AI API returned non-200 status code: %d", resp.status_code)
            return None

        data = resp.json()
        emotions_list = _extract_emotions(data)
        if not emotions_list:
            return None

        # Map response emotions to {valence, arousal, dominant, confidence}
        dominant_emotion = "neutral"
        max_score = 0.0
        total_score = 0.0
        weighted_valence = 0.0
        weighted_arousal = 0.0

        for item in emotions_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).lower()
            score = float(item.get("score", 0.0))

            if score > max_score:
                max_score = score
                dominant_emotion = str(item.get("name", "neutral"))

            val, aro = EMOTION_CIRCUMPLEX_MAP.get(name, (0.0, 0.5))
            weighted_valence += val * score
            weighted_arousal += aro * score
            total_score += score

        if total_score > 0:
            valence = weighted_valence / total_score
            arousal = weighted_arousal / total_score
        else:
            valence = 0.0
            arousal = 0.5

        confidence = max_score if max_score > 0 else 0.5

        return {
            "valence": round(max(-1.0, min(1.0, valence)), 3),
            "arousal": round(max(0.0, min(1.0, arousal)), 3),
            "dominant": dominant_emotion,
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
        }

    except Exception as exc:
        logger.warning("analyze_audio_emotion error: %s", exc)
        return None


def _extract_emotions(data: Any) -> list:
    """Recursively searches response JSON for list of emotion score objects."""
    if not isinstance(data, (dict, list)):
        return []

    if isinstance(data, list):
        for sub in data:
            res = _extract_emotions(sub)
            if res:
                return res

    if isinstance(data, dict):
        if "emotions" in data and isinstance(data["emotions"], list):
            return data["emotions"]
        for key in ("predictions", "results", "models", "prosody", "grouped_predictions"):
            if key in data:
                res = _extract_emotions(data[key])
                if res:
                    return res

    return []
