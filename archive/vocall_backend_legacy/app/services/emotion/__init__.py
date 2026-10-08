from app.services.emotion.audio_signal import analyze_audio_emotion
from app.services.emotion.fusion import fire_threshold_connectors, fuse_emotion_signals
from app.services.emotion.text_signal import analyze_text_emotion
from app.services.emotion.tone_adapter import (
    fire_frustration_connector,
    get_tone_instruction,
)

__all__ = [
    "analyze_text_emotion",
    "analyze_audio_emotion",
    "fuse_emotion_signals",
    "fire_threshold_connectors",
    "get_tone_instruction",
    "fire_frustration_connector",
]
