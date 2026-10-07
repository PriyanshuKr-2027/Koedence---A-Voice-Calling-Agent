"""
test_slot_memory.py — Tests for Redis slot memory and multi-turn slot filling.

Verifies:
1. write then read merges slots correctly.
2. unknown call returns an empty dictionary.
3. clear_slots removes all intent namespaces for a call.
4. clear_call_memory removes stm:, slot:, and webcall: keys.
5. two-turn slot filling through slot_manager reaches complete=True.
"""

import fnmatch
import json
from typing import Any, Dict, List, Optional
import pytest

from app.services.intent import slot_manager
from app.services.memory import short_term


class FakeRedisClient:
    """In-memory Redis fake implementing the subset used by VoCall services."""

    def __init__(self):
        self.kv: Dict[str, str] = {}
        self.lists: Dict[str, List[str]] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.kv.get(key)

    async def set(self, key: str, value: Any, ex_seconds: Optional[int] = None) -> bool:
        self.kv[key] = str(value)
        return True

    async def delete(self, key: str) -> bool:
        existed = False
        if key in self.kv:
            del self.kv[key]
            existed = True
        if key in self.lists:
            del self.lists[key]
            existed = True
        return existed

    async def keys(self, pattern: str) -> List[str]:
        matched = [k for k in self.kv if fnmatch.fnmatch(k, pattern)]
        matched_lists = [k for k in self.lists if fnmatch.fnmatch(k, pattern)]
        return list(set(matched + matched_lists))

    async def rpush(self, key: str, value: str) -> bool:
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].append(value)
        return True

    async def lrange(self, key: str, start: int, stop: int) -> List[str]:
        items = self.lists.get(key, [])
        if stop == -1:
            return items[start:]
        return items[start : stop + 1]


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Installs FakeRedisClient into short_term and redis_client modules."""
    fake = FakeRedisClient()
    monkeypatch.setattr("app.services.memory.short_term.redis_client", fake)
    monkeypatch.setattr("app.services.redis_client.redis_client", fake)
    return fake


@pytest.mark.asyncio
async def test_write_then_read_merges_slots(fake_redis):
    """Writing initial slots and merging additional slots preserves all non-empty fields."""
    call_id = "call-merge-01"
    intent = "book_appointment"

    # Direct initial write
    initial_slots = {"date": "2026-10-15"}
    await short_term.write_slot(call_id, intent, initial_slots)

    # Read back directly
    stored = await short_term.get_slots(call_id, intent)
    assert stored == {"date": "2026-10-15"}

    # Merge second turn values using slot_manager
    merged = await slot_manager.merge_slots(
        call_id=call_id,
        intent_slug=intent,
        new_slots={"time": "14:00", "purpose": "Billing inquiry"},
    )
    assert merged == {
        "date": "2026-10-15",
        "time": "14:00",
        "purpose": "Billing inquiry",
    }

    # Verify read via short_term matches merged state
    retrieved = await short_term.get_slots(call_id, intent)
    assert retrieved == merged


@pytest.mark.asyncio
async def test_unknown_call_returns_empty_dict(fake_redis):
    """Unknown call IDs or missing intent slots return an empty dictionary."""
    # Never stored call
    res1 = await short_term.get_slots("unknown-call-xyz", "book_appointment")
    assert res1 == {}

    # slot_manager wrapper also returns empty dict
    res2 = await slot_manager.get_slots("unknown-call-xyz", "book_appointment")
    assert res2 == {}

    # Empty inputs guard
    assert await short_term.get_slots("", "book_appointment") == {}
    assert await short_term.get_slots("some-call", "") == {}


@pytest.mark.asyncio
async def test_clear_slots_removes_all_intents(fake_redis):
    """clear_slots purges all slot keys for the target call without touching other calls."""
    target_call = "call-target-123"
    other_call = "call-other-456"

    # Seed multiple intents for target call
    await short_term.write_slot(target_call, "book_appointment", {"date": "2026-10-15", "time": "10:00"})
    await short_term.write_slot(target_call, "request_refund", {"order_id": "ORD-99"})

    # Seed intent for other call
    await short_term.write_slot(other_call, "book_appointment", {"date": "2026-10-18"})

    # Clear target call slots
    deleted = await short_term.clear_slots(target_call)
    assert deleted == 2

    # Target call slots are gone
    assert await short_term.get_slots(target_call, "book_appointment") == {}
    assert await short_term.get_slots(target_call, "request_refund") == {}

    # Other call remains intact
    other_slots = await short_term.get_slots(other_call, "book_appointment")
    assert other_slots == {"date": "2026-10-18"}


@pytest.mark.asyncio
async def test_clear_call_memory_removes_stm_slot_and_webcall(fake_redis):
    """clear_call_memory clears stm:{call_id}, slot:{call_id}:*, and webcall:{call_id}:events."""
    call_id = "call-full-clear-789"
    other_call = "call-keep-001"

    # Seed keys for target call
    await fake_redis.set(f"stm:{call_id}", json.dumps({"turns": [{"role": "user", "text": "hello"}]}))
    await fake_redis.set(f"slot:{call_id}:book_appointment", json.dumps({"date": "2026-10-15"}))
    await fake_redis.set(f"slot:{call_id}:request_refund", json.dumps({"order_id": "ORD-1"}))
    await fake_redis.rpush(f"webcall:{call_id}:events", json.dumps({"type": "transcript", "text": "hi"}))

    # Seed keys for another call
    await fake_redis.set(f"stm:{other_call}", json.dumps({"turns": []}))
    await fake_redis.set(f"slot:{other_call}:book_appointment", json.dumps({"date": "2026-11-01"}))
    await fake_redis.rpush(f"webcall:{other_call}:events", json.dumps({"type": "start"}))

    # Execute clear_call_memory
    cleared = await short_term.clear_call_memory(call_id)
    assert cleared is True

    # Verify no target keys remain
    assert await fake_redis.get(f"stm:{call_id}") is None
    assert await fake_redis.get(f"slot:{call_id}:book_appointment") is None
    assert await fake_redis.get(f"slot:{call_id}:request_refund") is None
    assert await fake_redis.lrange(f"webcall:{call_id}:events", 0, -1) == []

    # Other call keys remain
    assert await fake_redis.get(f"stm:{other_call}") is not None
    assert await fake_redis.get(f"slot:{other_call}:book_appointment") is not None
    assert len(await fake_redis.lrange(f"webcall:{other_call}:events", 0, -1)) == 1

    # Verify alias clear_call delegates properly
    alias_call = "call-alias-test"
    await fake_redis.set(f"stm:{alias_call}", "data")
    await fake_redis.set(f"slot:{alias_call}:test", "{}")
    await short_term.clear_call(alias_call)
    assert await fake_redis.get(f"stm:{alias_call}") is None
    assert await fake_redis.get(f"slot:{alias_call}:test") is None


@pytest.mark.asyncio
async def test_two_turn_slot_filling_reaches_complete(fake_redis):
    """Two-turn slot filling via slot_manager updates slot state from incomplete to complete."""
    call_id = "call-dialogue-turn-555"
    intent = "book_appointment"

    # Turn 1: user provides date only
    turn1_input = {"date": "2026-10-20"}
    turn1_merged = await slot_manager.merge_slots(call_id, intent, turn1_input)
    status_t1 = slot_manager.get_slot_status(intent, turn1_merged)

    assert status_t1["complete"] is False
    assert status_t1["filled"] == ["date"]
    assert status_t1["missing_required"] == ["time"]

    # Turn 2: user provides time
    turn2_input = {"time": "15:30"}
    turn2_merged = await slot_manager.merge_slots(call_id, intent, turn2_input)
    status_t2 = slot_manager.get_slot_status(intent, turn2_merged)

    assert status_t2["complete"] is True
    assert set(status_t2["filled"]) == {"date", "time"}
    assert status_t2["missing_required"] == []

    # Final persisted memory state has both slots
    final_slots = await slot_manager.get_slots(call_id, intent)
    assert final_slots == {"date": "2026-10-20", "time": "15:30"}


@pytest.mark.asyncio
async def test_empty_and_whitespace_values_do_not_overwrite(fake_redis):
    """Empty strings or whitespace do not overwrite previously collected slots."""
    call_id = "call-whitespace-01"
    intent = "book_appointment"

    await slot_manager.merge_slots(call_id, intent, {"date": "2026-10-20", "time": "11:00"})
    # Overwrite attempt with empty string and spaces
    merged = await slot_manager.merge_slots(call_id, intent, {"date": "   ", "time": None})

    assert merged["date"] == "2026-10-20"
    assert merged["time"] == "11:00"
