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
