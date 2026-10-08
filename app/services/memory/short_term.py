"""
VoCall Short-Term Memory Service (Upstash Redis REST API via httpx).

Manages ephemeral in-call state for active voice calls:
  - Dialogue turns (role, content, emotion_state, timestamp_ms)
  - Continuous emotion events (emotion_state, timestamp_ms)

Redis Key Format: stm:{call_id}
TTL: 3600 seconds (1 hour)

CRITICAL: Never crashes the voice pipeline on Redis failure.
All operations wrap network and JSON calls in try/except blocks, log errors, and return gracefully.
"""

import json
import logging
import time
from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.services.redis_client import redis_client

logger = logging.getLogger(__name__)

KEY_PREFIX = "stm:"
DEFAULT_TTL_SECONDS = settings.SLOT_TTL_SECONDS


async def init_call_memory(call_id: str) -> bool:
    """
    Initializes short-term memory structure for a new call:
      SET stm:{call_id} JSON.stringify({turns: [], emotion_events: []}) EX 3600
    """
    try:
        key = f"{KEY_PREFIX}{call_id}"
        initial_data = {
            "call_id": call_id,
            "turns": [],
            "emotion_events": [],
            "initialized_at": int(time.time() * 1000),
        }
        success = await redis_client.set(
            key=key,
            value=json.dumps(initial_data),
            ex_seconds=DEFAULT_TTL_SECONDS,
        )
        logger.debug("Initialized short-term memory for call %s (success=%s)", call_id, success)
        return success
    except Exception as exc:
        logger.error("Failed to init_call_memory for call %s: %s", call_id, exc)
        return False


async def append_turn(
    call_id: str,
    role: str,
    content: str,
    emotion_state: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Appends a dialogue turn to stm:{call_id}.
    Turn structure: {"role": role, "content": content, "emotion_state": emotion_state, "timestamp_ms": ts}

    Never raises on Redis failure — logs and returns silently.
    """
    try:
        key = f"{KEY_PREFIX}{call_id}"
        data = await get_call_memory(call_id)
        if data is None:
            data = {
                "call_id": call_id,
                "turns": [],
                "emotion_events": [],
                "initialized_at": int(time.time() * 1000),
            }

        if "turns" not in data or not isinstance(data.get("turns"), list):
            data["turns"] = []

        turn_entry = {
            "role": role,
            "content": content,
            "emotion_state": emotion_state,
            "timestamp_ms": int(time.time() * 1000),
        }
        data["turns"].append(turn_entry)

        success = await redis_client.set(
            key=key,
            value=json.dumps(data),
            ex_seconds=DEFAULT_TTL_SECONDS,
        )
        if success:
            await redis_client.expire(key, DEFAULT_TTL_SECONDS)
        logger.debug("Appended %s turn to short-term memory for call %s (TTL refreshed to %ds)", role, call_id, DEFAULT_TTL_SECONDS)
        return success
    except Exception as exc:
        logger.error("Failed to append_turn for call %s: %s", call_id, exc)
        return False


async def write_turn(call_id: str, turn_data: Dict[str, Any]) -> bool:
    """
    Appends a turn dictionary to short-term memory and refreshes the 3600s TTL.
    """
    role = turn_data.get("role", "user")
    content = turn_data.get("content", "")
    emotion_state = turn_data.get("emotion") or turn_data.get("emotion_state")
    return await append_turn(call_id, role, content, emotion_state)


async def refresh_call_ttl(call_id: str, ttl_seconds: Optional[int] = None) -> bool:
    """
    Confirms or refreshes the TTL on stm:{call_id} (defaults to 3600s).
    """
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS
    try:
        key = f"{KEY_PREFIX}{call_id}"
        return await redis_client.expire(key, ttl)
    except Exception as exc:
        logger.error("Failed to refresh_call_ttl for call %s: %s", call_id, exc)
        return False


async def append_emotion_event(
    call_id: str,
    emotion_state: Dict[str, Any],
) -> bool:
    """
    Appends an emotion event to stm:{call_id}.
    Event structure: {"emotion_state": emotion_state, "timestamp_ms": ts}

    Never raises on Redis failure — logs and returns silently.
    """
    try:
        key = f"{KEY_PREFIX}{call_id}"
        data = await get_call_memory(call_id)
        if data is None:
            data = {
                "call_id": call_id,
                "turns": [],
                "emotion_events": [],
                "initialized_at": int(time.time() * 1000),
            }

        if "emotion_events" not in data or not isinstance(data.get("emotion_events"), list):
            data["emotion_events"] = []

        event_entry = {
            "emotion_state": emotion_state,
            "timestamp_ms": emotion_state.get("timestamp_ms") or int(time.time() * 1000),
        }
        data["emotion_events"].append(event_entry)

        success = await redis_client.set(
            key=key,
            value=json.dumps(data),
            ex_seconds=DEFAULT_TTL_SECONDS,
        )
        if success:
            await redis_client.expire(key, DEFAULT_TTL_SECONDS)
        logger.debug("Appended emotion event to short-term memory for call %s", call_id)
        return success
    except Exception as exc:
        logger.error("Failed to append_emotion_event for call %s: %s", call_id, exc)
        return False


async def get_call_memory(call_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves short-term memory JSON object from stm:{call_id}.
    Returns parsed dict or None if missing or on error.
    """
    try:
        key = f"{KEY_PREFIX}{call_id}"
        raw_val = await redis_client.get(key)
        if not raw_val:
            return None
        if isinstance(raw_val, dict):
            return raw_val
        return json.loads(raw_val)
    except Exception as exc:
        logger.error("Failed to get_call_memory for call %s: %s", call_id, exc)
        return None


async def get_slots(call_id: str, intent_slug: str) -> Dict[str, Any]:
    """
    Retrieves slots dictionary for given call_id and intent_slug from Redis:
      GET slot:{call_id}:{intent_slug}
    Returns parsed dict or {} if missing or on error.
    """
    if not call_id or not intent_slug:
        return {}
    try:
        key = f"slot:{call_id}:{intent_slug}"
        raw_val = await redis_client.get(key)
        if not raw_val:
            return {}
        if isinstance(raw_val, dict):
            return raw_val
        data = json.loads(raw_val)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as exc:
        logger.error("Failed to get_slots for call %s intent %s: %s", call_id, intent_slug, exc)
        return {}


async def get_all_slots(call_id: str) -> Dict[str, Any]:
    """
    Retrieves all slots across all intents for a given call_id:
      SCAN/KEYS slot:{call_id}:*
    Returns {intent_slug: {slot_name: value, ...}}
    """
    if not call_id:
        return {}
    try:
        pattern = f"slot:{call_id}:*"
        keys = await redis_client.keys(pattern)
        all_slots: Dict[str, Any] = {}
        if keys:
            for k in keys:
                slug = k.split(":")[-1]
                slots_dict = await get_slots(call_id, slug)
                all_slots[slug] = slots_dict
        return all_slots
    except Exception as exc:
        logger.error("Failed to get_all_slots for call %s: %s", call_id, exc)
        return {}


async def write_slot(call_id: str, intent_slug: str, slots: Dict[str, Any]) -> None:
    """
    Persists slots dictionary for given call_id and intent_slug to Redis:
      SET slot:{call_id}:{intent_slug} JSON.stringify(slots) EX 3600
    """
    if not call_id or not intent_slug:
        return None
    try:
        key = f"slot:{call_id}:{intent_slug}"
        payload = json.dumps(slots if isinstance(slots, dict) else {})
        await redis_client.set(
            key=key,
            value=payload,
            ex_seconds=DEFAULT_TTL_SECONDS,
        )
        await redis_client.expire(key, DEFAULT_TTL_SECONDS)
        logger.debug("Wrote slots for call %s intent %s (TTL refreshed)", call_id, intent_slug)
    except Exception as exc:
        logger.error("Failed to write_slot for call %s intent %s: %s", call_id, intent_slug, exc)
    return None


async def clear_slots(call_id: str) -> int:
    """
    Deletes all slot:{call_id}:* keys from Redis.
    Returns the count of deleted keys.
    """
    if not call_id:
        return 0
    try:
        pattern = f"slot:{call_id}:*"
        keys = await redis_client.keys(pattern)
        deleted_count = 0
        if keys:
            for k in keys:
                success = await redis_client.delete(k)
                if success:
                    deleted_count += 1
        logger.debug("Cleared %d slot keys for call %s", deleted_count, call_id)
        return deleted_count
    except Exception as exc:
        logger.error("Failed to clear_slots for call %s: %s", call_id, exc)
        return 0


async def clear_call_memory(call_id: str) -> bool:
    """
    Deletes stm:{call_id}, all slot:{call_id}:* keys, and webcall:{call_id}:events from Redis.
    """
    try:
        key = f"{KEY_PREFIX}{call_id}"
        success = await redis_client.delete(key)

        # Clear all slot keys and webcall stream events
        await clear_slots(call_id)
        await redis_client.delete(f"webcall:{call_id}:events")

        logger.debug("Cleared short-term memory, slots, and webcall events for call %s", call_id)
        return success
    except Exception as exc:
        logger.error("Failed to clear_call_memory for call %s: %s", call_id, exc)
        return False


async def clear_call(call_id: str) -> bool:
    """
    Deletes stm:{call_id} from Redis. Convenience alias for clear_call_memory.
    """
    return await clear_call_memory(call_id)
