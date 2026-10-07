"""
test_livekit_service.py — Tests for app/services/livekit_service.py
"""
import pytest
import time
from unittest.mock import patch, MagicMock


class TestLiveKitServiceIsConfigured:
    """TC-LIVEKIT-CONFIG-*"""

    def test_not_configured_when_no_keys(self):
        """TC-LIVEKIT-CONFIG-01: is_configured returns False when keys are missing."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            assert svc.is_configured() is False

    def test_configured_when_keys_present(self):
        """TC-LIVEKIT-CONFIG-02: is_configured returns True when all keys are set."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = "key"
            mock_s.LIVEKIT_API_SECRET = "secret"
            mock_s.LIVEKIT_URL = "wss://test.livekit.io"
            svc = LiveKitService()
            assert svc.is_configured() is True


class TestRoomNaming:
    """TC-LIVEKIT-ROOM-NAME-*"""

    def test_room_name_prefixes_call_id(self):
        """TC-LIVEKIT-ROOM-01: _room_name adds 'call-' prefix."""
        from app.services.livekit_service import LiveKitService
        assert LiveKitService._room_name("abc-123") == "call-abc-123"

    def test_room_name_no_double_prefix(self):
        """TC-LIVEKIT-ROOM-02: _room_name doesn't double-prefix."""
        from app.services.livekit_service import LiveKitService
        assert LiveKitService._room_name("call-abc-123") == "call-abc-123"


class TestDevPlaceholderToken:
    """TC-LIVEKIT-TOKEN-*"""

    def test_unconfigured_service_returns_dev_token(self):
        """
        TC-LIVEKIT-TOKEN-01: Without credentials, generate_test_token returns
        a dev placeholder token starting with 'dev_token_'. This is a fallback
        for local development only.
        """
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            token = svc.generate_test_token("test-room", "user1")
        assert token.startswith("dev_token_")
        assert "test-room" in token
        assert "user1" in token

    def test_agent_token_dev_fallback(self):
        """TC-LIVEKIT-TOKEN-02: generate_agent_token returns dev token when unconfigured."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            token = svc.generate_agent_token("room-1", "agent-uuid-123")
        assert token.startswith("dev_token_")

    def test_caller_token_dev_fallback(self):
        """TC-LIVEKIT-TOKEN-03: generate_caller_token returns dev token when unconfigured."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            token = svc.generate_caller_token("room-1", "caller-id")
        assert token.startswith("dev_token_")


class TestCreateRoomUnconfigured:
    """TC-LIVEKIT-CREATE-ROOM-*"""

    @pytest.mark.asyncio
    async def test_create_room_raises_when_unconfigured(self):
        """TC-LIVEKIT-CREATE-ROOM-01: create_room raises RuntimeError if not configured."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            with pytest.raises(RuntimeError, match="not configured"):
                await svc.create_room("test-call-id")

    @pytest.mark.asyncio
    async def test_delete_room_is_no_op_when_unconfigured(self):
        """TC-LIVEKIT-DELETE-ROOM-01: delete_room returns None silently if not configured."""
        from app.services.livekit_service import LiveKitService
        with patch("app.services.livekit_service.settings") as mock_s:
            mock_s.LIVEKIT_API_KEY = ""
            mock_s.LIVEKIT_API_SECRET = ""
            mock_s.LIVEKIT_URL = ""
            svc = LiveKitService()
            result = await svc.delete_room("test-call-id")
            assert result is None
