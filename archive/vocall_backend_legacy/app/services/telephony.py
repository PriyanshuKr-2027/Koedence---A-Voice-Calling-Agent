"""
VoCall Outbound Telephony Service — Twilio REST API.

initiate_outbound_call(to_number, from_number, agent_id, contact_id)
  → POSTs to Twilio /Calls to dial an outbound call.
  → Twilio will invoke the inbound webhook URL (configured as status/voice URL)
    which returns TwiML to connect the call to the VoCall voice pipeline.

The caller-ID (from_number) must be a Twilio-verified number or alphanumeric
sender ID. It is typically the assigned phone number from the phone_numbers table.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelephonyService:
    """
    Wraps the Twilio Python SDK for outbound call management.

    Usage:
        from app.services.telephony import telephony_service
        call_sid = await telephony_service.initiate_outbound_call(
            to_number="+919876543210",
            from_number="+12025551234",
            agent_id="uuid-here",
            contact_id="uuid-here",
        )
    """

    def __init__(self):
        self._account_sid = settings.TWILIO_ACCOUNT_SID
        self._auth_token = settings.TWILIO_AUTH_TOKEN
        self._backend_url = settings.BACKEND_PUBLIC_URL or ""

    def is_configured(self) -> bool:
        return bool(self._account_sid and self._auth_token)

    async def initiate_outbound_call(
        self,
        to_number: str,
        from_number: str,
        agent_id: str,
        contact_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """
        Dials an outbound call via Twilio REST API POST /Calls.

        Args:
            to_number:   E.164 number to call (e.g. "+919876543210").
            from_number: Twilio-provisioned caller ID (e.g. "+12025551234").
            agent_id:    UUID of the VoCall agent handling the call.
            contact_id:  UUID of the contact being called (optional).
            org_id:      Organisation UUID (optional, used for routing).

        Returns:
            Twilio CallSid string (e.g. "CAxxxxxxxx...").

        Raises:
            RuntimeError: If Twilio credentials are not configured.
            TwilioRestException: On Twilio API errors.
        """
        if not self.is_configured():
            raise RuntimeError(
                "Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
            )

        # The webhook URL Twilio will call when the callee picks up.
        # This triggers the same inbound voice pipeline via TwiML <Stream>.
        voice_webhook_url = f"{self._backend_url}/api/v1/webhooks/twilio/inbound"
        status_callback_url = f"{self._backend_url}/api/v1/webhooks/twilio/status"

        logger.info(
            "Initiating outbound call: to=%s from=%s agent=%s",
            to_number,
            from_number,
            agent_id,
        )

        try:
            from twilio.rest import Client as TwilioClient

            client = TwilioClient(self._account_sid, self._auth_token)
            call = client.calls.create(
                to=to_number,
                from_=from_number,
                url=voice_webhook_url,
                status_callback=status_callback_url,
                status_callback_method="POST",
                # Pass context params so the webhook handler can route correctly
                # These appear in the TwiML request as custom parameters
            )
            logger.info("Outbound call initiated: sid=%s status=%s", call.sid, call.status)
            return call.sid

        except Exception as exc:
            logger.error("Twilio outbound call failed: %s", exc)
            raise

    async def cancel_call(self, call_sid: str) -> None:
        """
        Cancels a queued or ringing outbound call.
        Has no effect on calls already in-progress (use hangup instead).
        """
        if not self.is_configured():
            raise RuntimeError("Twilio credentials not configured")

        try:
            from twilio.rest import Client as TwilioClient

            client = TwilioClient(self._account_sid, self._auth_token)
            client.calls(call_sid).update(status="canceled")
            logger.info("Cancelled Twilio call: %s", call_sid)
        except Exception as exc:
            logger.warning("Failed to cancel call %s: %s", call_sid, exc)

    async def hangup_call(self, call_sid: str) -> None:
        """
        Hangs up an in-progress call.
        """
        if not self.is_configured():
            raise RuntimeError("Twilio credentials not configured")

        try:
            from twilio.rest import Client as TwilioClient

            client = TwilioClient(self._account_sid, self._auth_token)
            client.calls(call_sid).update(status="completed")
            logger.info("Hung up Twilio call: %s", call_sid)
        except Exception as exc:
            logger.warning("Failed to hang up call %s: %s", call_sid, exc)


# Module-level singleton
telephony_service = TelephonyService()
