"""
test_canonical_emotion.py — Tests for canonical emotion labeling, Hume mappings, and combined rules triggers.
"""

import pytest
from app.services.emotion.mapping import (
    CANONICAL_EMOTIONS,
    HUME_TO_CANONICAL_EMOTION_MAP,
    map_to_canonical_emotion,
)
from app.services.emotion.fusion import fuse_emotion_signals
from app.services.intent import combined_rules


def test_canonical_emotions_tuple_contents():
    """Verifies fixed 9-label emotion list."""
    expected = {"angry", "frustrated", "sad", "anxious", "confused", "neutral", "calm", "happy", "other"}
    assert set(CANONICAL_EMOTIONS) == expected
    assert len(CANONICAL_EMOTIONS) == 9


def test_hume_mapping_to_canonical():
    """Tests that Hume paralinguistic emotion names map correctly to canonical labels."""
    assert map_to_canonical_emotion("anger") == "angry"
    assert map_to_canonical_emotion("frustration") == "frustrated"
    assert map_to_canonical_emotion("sadness") == "sad"
    assert map_to_canonical_emotion("distress") == "sad"
    assert map_to_canonical_emotion("anxiety") == "anxious"
    assert map_to_canonical_emotion("fear") == "anxious"
    assert map_to_canonical_emotion("confusion") == "confused"
    assert map_to_canonical_emotion("calmness") == "calm"
    assert map_to_canonical_emotion("relief") == "calm"
    assert map_to_canonical_emotion("joy") == "happy"
    assert map_to_canonical_emotion("amusement") == "happy"
    assert map_to_canonical_emotion("neutral") == "neutral"


def test_unknown_labels_map_to_other():
    """Verifies unknown/arbitrary labels and invalid types map safely to 'other'."""
    assert map_to_canonical_emotion("unknown_emotion_xyz") == "other"
    assert map_to_canonical_emotion("random_noise") == "other"
    assert map_to_canonical_emotion("") == "other"
    assert map_to_canonical_emotion(None) == "other"
    assert map_to_canonical_emotion(123) == "other"


def test_fuse_emotion_signals_maps_dominant_to_canonical():
    """Verifies fuse_emotion_signals normalizes dominant labels from audio or text."""
    # Audio with raw Hume name "anger"
    audio_anger = {"valence": -0.8, "arousal": 0.8, "dominant": "anger", "confidence": 0.9}
    res_audio = fuse_emotion_signals(text=None, audio=audio_anger)
    assert res_audio["dominant"] == "angry"

    # Text with raw name "frustration"
    text_frust = {"valence": -0.7, "arousal": 0.6, "dominant": "frustration", "confidence": 0.85}
    res_text = fuse_emotion_signals(text=text_frust, audio=None)
    assert res_text["dominant"] == "frustrated"

    # Audio unknown label
    audio_unknown = {"valence": 0.1, "arousal": 0.3, "dominant": "unrecognized_state", "confidence": 0.8}
    res_unknown = fuse_emotion_signals(text=None, audio=audio_unknown)
    assert res_unknown["dominant"] == "other"


def test_combined_rules_trigger_speak_to_human_angry_from_audio_anger():
    """Proves audio 'anger' triggers speak_to_human_angry rule."""
    emotion_state = {
        "valence": -0.8,
        "arousal": 0.8,
        "dominant": "anger",
        "confidence": 0.9,
    }
    intent_state = {
        "intent": "speak_to_human",
        "confidence": 0.95,
    }

    matched = combined_rules.evaluate(emotion_state, intent_state)
    assert matched is not None
    assert matched["rule_matched"] == "speak_to_human_angry"
    assert matched["action"] == "human_handoff"
    assert matched["skip_llm_response"] is True


def test_combined_rules_trigger_speak_to_human_angry_from_text_frustrated():
    """Proves text 'frustrated' triggers speak_to_human_angry rule."""
    emotion_state = {
        "valence": -0.7,
        "arousal": 0.6,
        "dominant": "frustrated",
        "confidence": 0.85,
    }
    intent_state = {
        "intent": "speak_to_human",
        "confidence": 0.90,
    }

    matched = combined_rules.evaluate(emotion_state, intent_state)
    assert matched is not None
    assert matched["rule_matched"] == "speak_to_human_angry"
    assert matched["action"] == "human_handoff"
    assert matched["skip_llm_response"] is True


def test_combined_rules_unknown_label_does_not_trigger_speak_to_human_angry():
    """Proves unknown labels map to 'other' and do not falsely trigger anger rules."""
    emotion_state = {
        "valence": 0.0,
        "arousal": 0.5,
        "dominant": "extraterrestrial_bliss",
        "confidence": 0.85,
    }
    intent_state = {
        "intent": "speak_to_human",
        "confidence": 0.90,
    }

    matched = combined_rules.evaluate(emotion_state, intent_state)
    assert matched is None
