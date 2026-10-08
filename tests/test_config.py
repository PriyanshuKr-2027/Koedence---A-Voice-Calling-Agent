"""
test_config.py — Tests for app/core/config.py Settings.
"""
import pytest
import os


class TestSettings:
    """TC-CONFIG-*: Settings/config validation tests."""

    def test_settings_has_project_name(self):
        """TC-CONFIG-01: Settings.PROJECT_NAME is set."""
        from app.core.config import settings
        assert settings.PROJECT_NAME == "VoCall API"

    def test_settings_has_version(self):
        """TC-CONFIG-02: Settings.VERSION is set."""
        from app.core.config import settings
        assert settings.VERSION == "0.1.0"

    def test_api_v1_str(self):
        """TC-CONFIG-03: API_V1_STR is /api/v1."""
        from app.core.config import settings
        assert settings.API_V1_STR == "/api/v1"

    def test_falkordb_port_defaults_to_6379(self):
        """TC-CONFIG-04: FALKORDB_PORT defaults to 6379."""
        from app.core.config import settings
        assert settings.FALKORDB_PORT == 6379

    def test_backend_public_url_defaults(self):
        """TC-CONFIG-05: BACKEND_PUBLIC_URL defaults to localhost:8000."""
        from app.core.config import settings
        assert "localhost" in settings.BACKEND_PUBLIC_URL or settings.BACKEND_PUBLIC_URL == ""

    def test_supabase_env_defaults_empty(self):
        """TC-CONFIG-06: Supabase keys default to empty string (not None)."""
        from app.core.config import settings
        assert isinstance(settings.NEXT_PUBLIC_SUPABASE_URL, str)
        assert isinstance(settings.SUPABASE_SERVICE_ROLE_KEY, str)

    def test_groq_api_key_defaults_empty(self):
        """TC-CONFIG-07: GROQ_API_KEY defaults to empty string."""
        from app.core.config import settings
        assert isinstance(settings.GROQ_API_KEY, str)

    def test_livekit_settings_defaults_empty(self):
        """TC-CONFIG-08: LiveKit settings default to empty string."""
        from app.core.config import settings
        assert isinstance(settings.LIVEKIT_URL, str)
        assert isinstance(settings.LIVEKIT_API_KEY, str)
        assert isinstance(settings.LIVEKIT_API_SECRET, str)

    def test_hyperparameter_defaults_reproduce_expected_values(self):
        """TC-CONFIG-09: Verifies all hyperparameter defaults match required baseline values."""
        from app.core.config import settings
        assert settings.RETRIEVAL_TOP_K == 5
        assert settings.RETRIEVAL_TAU == 0.75
        assert settings.EPISODIC_LIMIT == 3
        assert settings.FUSION_AUDIO_WEIGHT == 0.6
        assert settings.TONE_THRESHOLD_MILD == 0.4
        assert settings.TONE_THRESHOLD_STRONG == 0.6
        assert settings.TONE_THRESHOLD_POSITIVE == 0.6
        assert settings.ALERT_THRESHOLD == 0.7
        assert settings.LLM_MODEL == "llama-3.3-70b-versatile"
        assert settings.LLM_FALLBACK_MODEL == "llama3-70b-8192"
        assert settings.EMBEDDING_PROVIDER == "sentence_transformers"
        assert settings.EMBEDDING_MODEL == "BAAI/bge-m3"
        assert settings.EMBEDDING_DIM == 1024
        assert settings.INTENT_CONFIDENCE_MIN == 0.70
        assert settings.SLOT_TTL_SECONDS == 3600
        assert settings.VAD_ENERGY_THRESHOLD == 400.0
        assert settings.VAD_FRAME_MS == 20
        assert settings.VAD_SILENCE_MS == 700
        assert settings.VAD_MIN_MS == 120
        assert settings.VAD_MAX_MS == 15000

    def test_settings_snapshot_structure_and_values(self):
        """TC-CONFIG-10: settings_snapshot returns complete dictionary of hyperparameters."""
        from app.core.config import settings_snapshot
        snapshot = settings_snapshot()
        assert isinstance(snapshot, dict)
        assert snapshot["RETRIEVAL_TOP_K"] == 5
        assert snapshot["RETRIEVAL_TAU"] == 0.75
        assert snapshot["EPISODIC_LIMIT"] == 3
        assert snapshot["FUSION_AUDIO_WEIGHT"] == 0.6
        assert snapshot["TONE_THRESHOLD_MILD"] == 0.4
        assert snapshot["TONE_THRESHOLD_STRONG"] == 0.6
        assert snapshot["TONE_THRESHOLD_POSITIVE"] == 0.6
        assert snapshot["ALERT_THRESHOLD"] == 0.7
        assert snapshot["LLM_MODEL"] == "llama-3.3-70b-versatile"
        assert snapshot["LLM_FALLBACK_MODEL"] == "llama3-70b-8192"
        assert snapshot["EMBEDDING_PROVIDER"] == "sentence_transformers"
        assert snapshot["EMBEDDING_MODEL"] == "BAAI/bge-m3"
        assert snapshot["EMBEDDING_DIM"] == 1024
        assert snapshot["INTENT_CONFIDENCE_MIN"] == 0.70
        assert snapshot["SLOT_TTL_SECONDS"] == 3600
        assert snapshot["VAD_ENERGY_THRESHOLD"] == 400.0
        assert snapshot["VAD_FRAME_MS"] == 20
        assert snapshot["VAD_SILENCE_MS"] == 700
        assert snapshot["VAD_MIN_MS"] == 120
        assert snapshot["VAD_MAX_MS"] == 15000

    def test_settings_env_overrides(self, monkeypatch):
        """TC-CONFIG-11: Environment variables override defaults in Settings instantiation."""
        from app.core.config import Settings
        monkeypatch.setenv("RETRIEVAL_TOP_K", "10")
        monkeypatch.setenv("RETRIEVAL_TAU", "0.85")
        monkeypatch.setenv("EPISODIC_LIMIT", "7")
        monkeypatch.setenv("FUSION_AUDIO_WEIGHT", "0.4")
        monkeypatch.setenv("TONE_THRESHOLD_MILD", "0.3")
        monkeypatch.setenv("TONE_THRESHOLD_STRONG", "0.8")
        monkeypatch.setenv("TONE_THRESHOLD_POSITIVE", "0.75")
        monkeypatch.setenv("ALERT_THRESHOLD", "0.9")
        monkeypatch.setenv("LLM_MODEL", "custom-llm-model")
        monkeypatch.setenv("LLM_FALLBACK_MODEL", "custom-fallback-model")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
        monkeypatch.setenv("EMBEDDING_DIM", "1536")
        monkeypatch.setenv("INTENT_CONFIDENCE_MIN", "0.85")
        monkeypatch.setenv("SLOT_TTL_SECONDS", "7200")
        monkeypatch.setenv("VAD_ENERGY_THRESHOLD", "550.0")
        monkeypatch.setenv("VAD_FRAME_MS", "30")
        monkeypatch.setenv("VAD_SILENCE_MS", "800")
        monkeypatch.setenv("VAD_MIN_MS", "150")
        monkeypatch.setenv("VAD_MAX_MS", "20000")

        custom_settings = Settings()
        assert custom_settings.RETRIEVAL_TOP_K == 10
        assert custom_settings.RETRIEVAL_TAU == 0.85
        assert custom_settings.EPISODIC_LIMIT == 7
        assert custom_settings.FUSION_AUDIO_WEIGHT == 0.4
        assert custom_settings.TONE_THRESHOLD_MILD == 0.3
        assert custom_settings.TONE_THRESHOLD_STRONG == 0.8
        assert custom_settings.TONE_THRESHOLD_POSITIVE == 0.75
        assert custom_settings.ALERT_THRESHOLD == 0.9
        assert custom_settings.LLM_MODEL == "custom-llm-model"
        assert custom_settings.LLM_FALLBACK_MODEL == "custom-fallback-model"
        assert custom_settings.EMBEDDING_PROVIDER == "openai"
        assert custom_settings.EMBEDDING_MODEL == "text-embedding-3-small"
        assert custom_settings.EMBEDDING_DIM == 1536
        assert custom_settings.INTENT_CONFIDENCE_MIN == 0.85
        assert custom_settings.SLOT_TTL_SECONDS == 7200
        assert custom_settings.VAD_ENERGY_THRESHOLD == 550.0
        assert custom_settings.VAD_FRAME_MS == 30
        assert custom_settings.VAD_SILENCE_MS == 800
        assert custom_settings.VAD_MIN_MS == 150
        assert custom_settings.VAD_MAX_MS == 20000

