"""
test_redis_ttls_and_cleanup.py — Tests for Redis TTL management and webcall event cleanup.

Verifies:
1. webcall:{call_id}:events gets 24-hour (86400s) TTL when first event is pushed.
2. webcall:{call_id}:events is deleted when call ends (_finalize_webcall / clear_call_memory).
3. stm:{call_id} TTL (3600s) is confirmed/refreshed on each turn so long calls do not lose memory.
"""

import json
from uuid import uuid4
import pytest

from app.services.memory import short_term
from app.services.webcall_pipeline import (
    WEBCALL_EVENT_TTL,
    _finalize_webcall,
    _push_sse_event,
)
from app.services.redis_client import redis_client


@pytest.fixture
def test_call_id():
    return f"call_{uuid4().hex[:12]}"


@pytest.mark.asyncio
async def test_webcall_events_ttl_24_hours_on_first_push(test_call_id):
    """Proves webcall:{call_id}:events receives a 24-hour TTL when first event is pushed."""
    key = f"webcall:{test_call_id}:events"

    try:
        # Push first event
        await _push_sse_event(test_call_id, "speech", {"text": "Hello, how can I help you?"})

        # Check key exists
        events = await redis_client.lrange(key, 0, -1)
        assert len(events) == 1

        # Check TTL
        ttl = await redis_client.ttl(key)
        assert ttl is not None
        assert ttl > 0
        assert ttl <= 86400  # 24 hours
        assert ttl >= 86000  # Within seconds of 86400

        # Push second event
        await _push_sse_event(test_call_id, "speech", {"text": "I have a question."})
        events_2 = await redis_client.lrange(key, 0, -1)
        assert len(events_2) == 2

        ttl_2 = await redis_client.ttl(key)
        assert ttl_2 is not None
        assert ttl_2 > 0
        assert ttl_2 <= 86400

    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_webcall_events_deleted_when_call_ends(test_call_id):
    """Proves webcall:{call_id}:events is deleted when call ends."""
    key = f"webcall:{test_call_id}:events"

    try:
        # Push events
        await _push_sse_event(test_call_id, "speech", {"text": "Turn 1"})
        await _push_sse_event(test_call_id, "speech", {"text": "Turn 2"})

        # Confirm events exist before finalization
        events_before = await redis_client.lrange(key, 0, -1)
        assert len(events_before) == 2

        # Finalize webcall
        await _finalize_webcall(test_call_id)

        # Confirm events list is deleted
        events_after = await redis_client.lrange(key, 0, -1)
        assert len(events_after) == 0

    finally:
        await redis_client.delete(key)


@pytest.mark.asyncio
async def test_clear_call_memory_deletes_all_keys(test_call_id):
    """Proves clear_call_memory deletes stm:{call_id}, slot:{call_id}:*, and webcall:{call_id}:events."""
    stm_key = f"stm:{test_call_id}"
    slot_key = f"slot:{test_call_id}:test_intent"
    webcall_key = f"webcall:{test_call_id}:events"

    try:
        # Populate keys
        await short_term.init_call_memory(test_call_id)
        await short_term.write_slot(test_call_id, "test_intent", {"slot1": "val1"})
        await _push_sse_event(test_call_id, "status", {"state": "active"})

        assert await redis_client.get(stm_key) is not None
        assert await redis_client.get(slot_key) is not None
        assert len(await redis_client.lrange(webcall_key, 0, -1)) > 0

        # Clear call memory
        await short_term.clear_call_memory(test_call_id)

        assert await redis_client.get(stm_key) is None
        assert await redis_client.get(slot_key) is None
        assert len(await redis_client.lrange(webcall_key, 0, -1)) == 0

    finally:
        await redis_client.delete(stm_key)
        await redis_client.delete(slot_key)
        await redis_client.delete(webcall_key)


@pytest.mark.asyncio
async def test_stm_ttl_refreshed_on_each_turn(test_call_id):
    """Proves stm:{call_id} TTL (3600s) is refreshed on each turn so long calls retain memory."""
    key = f"stm:{test_call_id}"

    try:
        # 1. Initialize call memory
        await short_term.init_call_memory(test_call_id)

        ttl_1 = await redis_client.ttl(key)
        assert ttl_1 is not None
        assert ttl_1 > 0
        assert ttl_1 <= 3600

        # 2. Append turn 1
        await short_term.append_turn(
            test_call_id,
            role="user",
            content="Hello there",
            emotion_state={"valence": 0.5},
        )

        ttl_2 = await redis_client.ttl(key)
        assert ttl_2 is not None
        assert ttl_2 > 0
        assert ttl_2 <= 3600
        assert ttl_2 >= 3500  # Refreshed back to near 3600

        # 3. Append turn 2 via write_turn
        await short_term.write_turn(
            test_call_id,
            {
                "role": "assistant",
                "content": "How can I help you today?",
                "emotion": {"valence": 0.5},
            },
        )

        ttl_3 = await redis_client.ttl(key)
        assert ttl_3 is not None
        assert ttl_3 > 0
        assert ttl_3 <= 3600
        assert ttl_3 >= 3500

        # Verify memory contents
        mem = await short_term.get_call_memory(test_call_id)
        assert mem is not None
        assert len(mem["turns"]) == 2

    finally:
        await redis_client.delete(key)
