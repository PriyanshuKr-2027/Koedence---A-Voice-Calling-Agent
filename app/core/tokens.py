"""
Token security utilities:
- HMAC-SHA256 call stream tokens for WebSocket authentication.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Tuple

from app.core.config import settings


def generate_call_stream_token(call_id: str, ttl_seconds: int = 3600) -> Tuple[str, int]:
    """
    Generates an HMAC-SHA256 signature for a specific call_id and expiration timestamp.
    Used by inbound webhooks to authorize WebSocket audio streams.
    """
    exp = int(time.time()) + ttl_seconds
    secret = (settings.SUPABASE_JWT_SECRET or settings.TWILIO_AUTH_TOKEN or "vocall-stream-token-secret").encode("utf-8")
    payload = f"{call_id}:{exp}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return sig, exp


def verify_call_stream_token(call_id: str, token: str, exp: int) -> bool:
    """
    Verifies that the HMAC token for call_id is valid and unexpired.
    """
    if not token or not exp:
        return False
    try:
        if int(exp) < int(time.time()):
            return False
    except (ValueError, TypeError):
        return False

    secret = (settings.SUPABASE_JWT_SECRET or settings.TWILIO_AUTH_TOKEN or "vocall-stream-token-secret").encode("utf-8")
    payload = f"{call_id}:{exp}".encode("utf-8")
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, token)
