"""
test_config_behavior.py — Tests verifying runtime behavior obeys configurable hyperparameters.
"""

import pytest
from app.core.config import settings, Settings, settings_snapshot
from app.services.emotion.fusion import fuse_emotion_signals
from app.services.emotion.tone_adapter import get_tone_instruction
from app.services.llm import LLMService


def test_fusion_audio_weight_default_and_override(monkeypatch):
    """Verifies fuse_emotion_signals uses settings.FUSION_AUDIO_WEIGHT by default."""
    text_sig = {"valence": 0.0, "arousal": 0.5, "dominant": "neutral", "confidence": 0.8}
    audio_sig = {"valence": 1.0, "arousal": 0.5, "dominant": "happy", "confidence": 0.8}

    # Default weight 0.6 -> valence = 0.6 * 1.0 + 0.4 * 0.0 = 0.6
    res = fuse_emotion_signals(text_sig, audio_sig)
    assert pytest.approx(res["valence"], rel=1e-2) == 0.6

    # Override setting to 0.8 -> valence = 0.8 * 1.0 + 0.2 * 0.0 = 0.8
    monkeypatch.setattr(settings, "FUSION_AUDIO_WEIGHT", 0.8)
    res_custom = fuse_emotion_signals(text_sig, audio_sig)
    assert pytest.approx(res_custom["valence"], rel=1e-2) == 0.8


def test_tone_thresholds_default_and_override(monkeypatch):
    """Verifies tone_adapter respects TONE_THRESHOLD_* settings."""
    cfg = {"tone_adaptation": True}

    # Default mild threshold is 0.4, strong is 0.6
    # v = -0.5 is between -0.6 and -0.4 -> mild unhappy
    mild_state = {"valence": -0.5}
    inst = get_tone_instruction(mild_state, cfg)
    assert "caller seems unhappy" in inst

    # Change mild threshold to 0.55 -> -0.5 is no longer below -0.55
    monkeypatch.setattr(settings, "TONE_THRESHOLD_MILD", 0.55)
    inst_none = get_tone_instruction(mild_state, cfg)
    assert inst_none is None

    # Positive mood threshold default 0.6
    pos_state = {"valence": 0.7}
    inst_pos = get_tone_instruction(pos_state, cfg)
    assert "good mood" in inst_pos

    monkeypatch.setattr(settings, "TONE_THRESHOLD_POSITIVE", 0.8)
    assert get_tone_instruction(pos_state, cfg) is None


def test_llm_model_settings_payload():
    """Verifies LLMService builds payload with settings.LLM_MODEL."""
    svc = LLMService()
    payload = svc._build_payload("Prompt", [], 0.7, 512)
    assert payload["model"] == settings.LLM_MODEL


def test_settings_snapshot_reproducibility():
    """Verifies settings_snapshot captures exact environment values."""
    snap = settings_snapshot()
    assert snap["RETRIEVAL_TOP_K"] == 5
    assert snap["RETRIEVAL_TAU"] == 0.75
    assert snap["EPISODIC_LIMIT"] == 3
    assert snap["FUSION_AUDIO_WEIGHT"] == 0.6
    assert snap["TONE_THRESHOLD_MILD"] == 0.4
    assert snap["TONE_THRESHOLD_STRONG"] == 0.6
    assert snap["TONE_THRESHOLD_POSITIVE"] == 0.6
    assert snap["ALERT_THRESHOLD"] == 0.7
    assert snap["INTENT_CONFIDENCE_MIN"] == 0.70
    assert snap["SLOT_TTL_SECONDS"] == 3600
