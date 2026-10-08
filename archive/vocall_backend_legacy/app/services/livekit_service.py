"""
VoCall LiveKit Service.

Provides:
  create_room(call_id)             → creates an audio-only LiveKit room
  generate_agent_token(room, id)   → JWT with publish+subscribe grants
  generate_caller_token(room, id)  → JWT for the Twilio SIP/stream participant
  delete_room(call_id)             → removes the room when call ends

Audio-only: VideoGrants are set with can_publish_data=True but NO video tracks
are enabled. The transport is used purely for real-time audio streaming between
Twilio's media stream and Pipecat's LiveKitTransport.
"""

import logging
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class LiveKitService:
    """
    Thin wrapper around the LiveKit server-side SDK.

    Room/token management configured for audio-only VoCall use-case:
      - No video track grants
      - Room metadata encodes call_id for downstream pipeline routing
      - Tokens have a 4-hour TTL (covers maximum realistic call duration)
    """

    ROOM_TTL_EMPTY_TIMEOUT = 300    # seconds — room closes if empty for 5 min
    ROOM_TTL_DEPARTURE_TIMEOUT = 10 # seconds — room closes 10s after last participant leaves
    TOKEN_TTL_SECONDS = 4 * 60 * 60  # 4 hours

    def __init__(self):
        self._api_key = settings.LIVEKIT_API_KEY
        self._api_secret = settings.LIVEKIT_API_SECRET
        self._url = settings.LIVEKIT_URL

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_secret and self._url)

    # ------------------------------------------------------------------
    # Room management
    # ------------------------------------------------------------------

    async def create_room(self, call_id: str) -> dict:
        """
        Creates a LiveKit room for the given call_id.

        Returns the created room metadata dict.
        Raises RuntimeError if LiveKit is not configured.
        """
        if not self.is_configured():
            raise RuntimeError("LiveKit is not configured (missing API key/secret/URL)")

        room_name = self._room_name(call_id)
        logger.info("Creating LiveKit room: %s", room_name)

        try:
            from livekit import api as livekit_api

            room_service = livekit_api.RoomServiceClient(
                self._url, self._api_key, self._api_secret
            )
            room = await room_service.create_room(
                livekit_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=self.ROOM_TTL_EMPTY_TIMEOUT,
                    departure_timeout=self.ROOM_TTL_DEPARTURE_TIMEOUT,
                    metadata=f'{{"call_id":"{call_id}"}}',
                )
            )
            logger.info("LiveKit room created: name=%s sid=%s", room.name, room.sid)
            return {"name": room.name, "sid": room.sid}

        except Exception as exc:
            logger.error("Failed to create LiveKit room %s: %s", room_name, exc)
            raise

    async def delete_room(self, call_id: str) -> None:
        """
        Deletes the LiveKit room associated with call_id.
        Typically called after call ends or pipeline shuts down.
        """
        if not self.is_configured():
            return

        room_name = self._room_name(call_id)
        logger.info("Deleting LiveKit room: %s", room_name)

        try:
            from livekit import api as livekit_api

            room_service = livekit_api.RoomServiceClient(
                self._url, self._api_key, self._api_secret
            )
            await room_service.delete_room(
                livekit_api.DeleteRoomRequest(room=room_name)
            )
            logger.info("LiveKit room deleted: %s", room_name)
        except Exception as exc:
            logger.warning("Failed to delete LiveKit room %s (non-fatal): %s", room_name, exc)

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------

    def generate_agent_token(self, room_name: str, agent_id: str) -> str:
        """
        Generates a JWT for the VoCall AI agent participant.

        Grants:
          - room_join: True
          - can_publish: True (agent pushes synthesised TTS audio)
          - can_subscribe: True (agent receives caller audio)
          - can_publish_data: True (agent can send data channel messages)

        This is an audio-only token — no video track grant is included.
        """
        return self._build_token(
            room_name=room_name,
            identity=f"agent-{agent_id}",
            display_name=f"VoCall Agent {agent_id}",
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )

    def generate_caller_token(self, room_name: str, caller_identity: str) -> str:
        """
        Generates a JWT for the caller/Twilio SIP participant.

        Grants:
          - room_join: True
          - can_publish: True (caller's audio track)
          - can_subscribe: True (caller receives agent audio)
        """
        return self._build_token(
            room_name=room_name,
            identity=caller_identity,
            display_name="Caller",
            can_publish=True,
            can_subscribe=True,
            can_publish_data=False,
        )

    def generate_test_token(self, room_name: str, participant_name: str) -> str:
        """
        Generates a token for test-call participants (e.g. dashboard "Talk To Agent" button).
        """
        return self._build_token(
            room_name=room_name,
            identity=participant_name,
            display_name=participant_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_token(
        self,
        room_name: str,
        identity: str,
        display_name: str,
        can_publish: bool,
        can_subscribe: bool,
        can_publish_data: bool,
    ) -> str:
        """
        Low-level token builder using livekit-server-sdk AccessToken.
        Falls back to a dev-mode placeholder token if SDK is unavailable.
        """
        if not self.is_configured():
            # Dev mode placeholder — allows frontend to bootstrap without LiveKit
            logger.warning("LiveKit not configured — returning dev placeholder token")
            return f"dev_token_{room_name}_{identity}_{int(time.time())}"

        try:
            from livekit import api as livekit_api

            grant = livekit_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
                can_publish_data=can_publish_data,
                # Explicitly NO video track — audio-only pipeline
            )
            token = (
                livekit_api.AccessToken(self._api_key, self._api_secret)
                .with_identity(identity)
                .with_name(display_name)
                .with_grants(grant)
                .with_ttl(self.TOKEN_TTL_SECONDS)
                .to_jwt()
            )
            logger.debug("Generated LiveKit token for identity=%s room=%s", identity, room_name)
            return token

        except Exception as exc:
            logger.error("LiveKit token generation failed: %s", exc)
            raise

    @staticmethod
    def _room_name(call_id: str) -> str:
        """Consistent room naming: prefixes call_id with 'call-'."""
        if call_id.startswith("call-"):
            return call_id
        return f"call-{call_id}"


# Module-level singleton — import and use directly
livekit_service = LiveKitService()
