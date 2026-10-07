"""
test_telephony.py — Tests for app/services/telephony.py (TwilioService).
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestTelephonyServiceConfigured:
    """TC-TELEPHONY-CONFIG-*"""

    def test_not_configured_when_no_credentials(self):
        """TC-TELEPHONY-CONFIG-01: is_configured returns False when credentials missing."""
        from app.services.telephony import TelephonyService
        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = ""
            mock_s.TWILIO_AUTH_TOKEN = ""
            mock_s.BACKEND_PUBLIC_URL = ""
            svc = TelephonyService()
            assert svc.is_configured() is False

    def test_configured_when_credentials_present(self):
        """TC-TELEPHONY-CONFIG-02: is_configured returns True with credentials."""
        from app.services.telephony import TelephonyService
        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = "ACtest123"
            mock_s.TWILIO_AUTH_TOKEN = "auth_token_test"
            mock_s.BACKEND_PUBLIC_URL = "https://backend.example.com"
            svc = TelephonyService()
            assert svc.is_configured() is True


class TestInitiateOutboundCall:
    """TC-TELEPHONY-OUTBOUND-*"""

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_unconfigured(self):
        """TC-TELEPHONY-OUTBOUND-01: RuntimeError raised when Twilio not configured."""
        from app.services.telephony import TelephonyService
        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = ""
            mock_s.TWILIO_AUTH_TOKEN = ""
            mock_s.BACKEND_PUBLIC_URL = ""
            svc = TelephonyService()
            with pytest.raises(RuntimeError, match="credentials not configured"):
                await svc.initiate_outbound_call(
                    to_number="+919876543210",
                    from_number="+12025551234",
                    agent_id="agent-uuid",
                )

    @pytest.mark.asyncio
    async def test_calls_twilio_when_configured(self):
        """TC-TELEPHONY-OUTBOUND-02: With credentials, calls Twilio SDK and returns SID."""
        from app.services.telephony import TelephonyService
        mock_call = MagicMock()
        mock_call.sid = "CA1234567890abcdef"
        mock_call.status = "queued"

        mock_twilio_client = MagicMock()
        mock_twilio_client.calls.create.return_value = mock_call

        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = "ACtest123"
            mock_s.TWILIO_AUTH_TOKEN = "auth_token_test"
            mock_s.BACKEND_PUBLIC_URL = "https://backend.example.com"
            svc = TelephonyService()

            with patch("twilio.rest.Client", return_value=mock_twilio_client):
                sid = await svc.initiate_outbound_call(
                    to_number="+919876543210",
                    from_number="+12025551234",
                    agent_id="agent-uuid",
                )

        assert sid == "CA1234567890abcdef"
        assert mock_twilio_client.calls.create.called


class TestCancelCall:
    """TC-TELEPHONY-CANCEL-*"""

    @pytest.mark.asyncio
    async def test_cancel_raises_when_unconfigured(self):
        """TC-TELEPHONY-CANCEL-01: cancel_call raises RuntimeError when unconfigured."""
        from app.services.telephony import TelephonyService
        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = ""
            mock_s.TWILIO_AUTH_TOKEN = ""
            mock_s.BACKEND_PUBLIC_URL = ""
            svc = TelephonyService()
            with pytest.raises(RuntimeError):
                await svc.cancel_call("CA_test_sid")


class TestHangupCall:
    """TC-TELEPHONY-HANGUP-*"""

    @pytest.mark.asyncio
    async def test_hangup_raises_when_unconfigured(self):
        """TC-TELEPHONY-HANGUP-01: hangup_call raises RuntimeError when unconfigured."""
        from app.services.telephony import TelephonyService
        with patch("app.services.telephony.settings") as mock_s:
            mock_s.TWILIO_ACCOUNT_SID = ""
            mock_s.TWILIO_AUTH_TOKEN = ""
            mock_s.BACKEND_PUBLIC_URL = ""
            svc = TelephonyService()
            with pytest.raises(RuntimeError):
                await svc.hangup_call("CA_test_sid")
