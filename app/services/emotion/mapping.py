"""
Canonical emotion mapping utilities.

Defines the fixed 9-label emotion set:
  angry, frustrated, sad, anxious, confused, neutral, calm, happy, other
and provides bidirectional/normalizing maps from Hume paralinguistic and text model outputs.
"""

from typing import Dict, Optional, Tuple

CANONICAL_EMOTIONS: Tuple[str, ...] = (
    "angry",
    "frustrated",
    "sad",
    "anxious",
    "confused",
    "neutral",
    "calm",
    "happy",
    "other",
)

HUME_TO_CANONICAL_EMOTION_MAP: Dict[str, str] = {
    # Direct canonical identities
    "angry": "angry",
    "frustrated": "frustrated",
    "sad": "sad",
    "anxious": "anxious",
    "confused": "confused",
    "neutral": "neutral",
    "calm": "calm",
    "happy": "happy",
    "other": "other",

    # Hume paralinguistic emotion mappings
    "anger": "angry",
    "frustration": "frustrated",
    "annoyance": "frustrated",
    "irritation": "frustrated",
    "rage": "angry",
    "fury": "angry",
    "disgust": "angry",
    "contempt": "angry",

    # Sadness / Grief
    "sadness": "sad",
    "distress": "sad",
    "pain": "sad",
    "grief": "sad",
    "disappointment": "sad",
    "guilt": "sad",
    "shame": "sad",
    "embarrassment": "sad",
    "empathic pain": "sad",

    # Anxiety / Fear
    "anxiety": "anxious",
    "fear": "anxious",
    "horror": "anxious",
    "worry": "anxious",
    "nervousness": "anxious",
    "panic": "anxious",

    # Confusion / Uncertainty
    "confusion": "confused",
    "doubt": "confused",
    "awkwardness": "confused",

    # Calmness / Serenity
    "calmness": "calm",
    "relief": "calm",
    "contentment": "calm",
    "serenity": "calm",
    "peaceful": "calm",

    # Joy / Happiness
    "joy": "happy",
    "amusement": "happy",
    "enthusiasm": "happy",
    "excitement": "happy",
    "ecstasy": "happy",
    "satisfaction": "happy",
    "triumph": "happy",
    "gratitude": "happy",
    "love": "happy",
    "romance": "happy",
    "admiration": "happy",
    "adoration": "happy",
    "awe": "happy",
    "pride": "happy",
    "interest": "happy",
    "enthrallment": "happy",

    # Neutral / Passive
    "neutral": "neutral",
    "concentration": "neutral",
    "boredom": "neutral",
    "tiredness": "neutral",
}


def map_to_canonical_emotion(name: Optional[str]) -> str:
    """
    Maps an emotion label (e.g., Hume AI name, LLM output, or arbitrary string)
    to one of the 9 canonical labels:
    ['angry', 'frustrated', 'sad', 'anxious', 'confused', 'neutral', 'calm', 'happy', 'other'].
    Any unrecognized or empty label maps to 'other'.
    """
    if not name or not isinstance(name, str):
        return "other"
    clean = name.strip().lower()
    return HUME_TO_CANONICAL_EMOTION_MAP.get(clean, "other")
