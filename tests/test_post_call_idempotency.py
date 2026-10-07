"""
tests/test_post_call_idempotency.py — Tests for idempotent post-call pipeline execution.

Verifies:
1. Pipeline run twice for one call:
   - exactly one episode in memory_episodic
   - exactly one copy of each fact in memory_long_term (no duplicate writes)
   - frustration count in FalkorDB graph incremented once
   - connectors and email dispatched once
2. Failure at graph step followed by retry completes only the remaining steps
3. Erasure flag (erasure:{contact_id}) stops all memory writes
4. episodic.create_episode upserts on call_id and does not duplicate long-term facts
5. long_term.store_fact deduplicates by (contact_id, call_id, content)
6. graph.add_frustration_edges increments count once per call_id
"""

import asyncio
from datetime import datetime, timezone
import fnmatch
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest

from app.core.config import settings
from app.services.memory import episodic, graph, long_term, short_term
from trigger.post_call_pipeline import post_call_pipeline, EpisodeObj


# ---------------------------------------------------------------------------
# In-Memory Fakes
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.kv: Dict[str, str] = {}
        self.lists: Dict[str, List[str]] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.kv.get(key)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
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
        all_keys = list(self.kv.keys()) + list(self.lists.keys())
        return [k for k in set(all_keys) if fnmatch.fnmatch(k, pattern)]

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


class FakeQueryBuilder:
    def __init__(self, table_name: str, db: "FakeSupabase"):
        self.table_name = table_name
        self.db = db
        self.filters = []
        self.limit_val = None
        self.is_single = False
        self._action = "select"
        self._payload = None
        self._on_conflict = None

    def select(self, columns: str = "*"):
        self._action = "select"
        return self

    def insert(self, payload: Any):
        self._action = "insert"
        self._payload = payload
        return self

    def upsert(self, payload: Any, on_conflict: Optional[str] = None):
        self._action = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def update(self, payload: Any):
        self._action = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value: Any):
        self.filters.append((column, "eq", value))
        return self

    def in_(self, column: str, values: List[Any]):
        self.filters.append((column, "in", values))
        return self

    def limit(self, n: int):
        self.limit_val = n
        return self

    def single(self):
        self.is_single = True
        return self

    def execute(self):
        table_rows = self.db.tables.setdefault(self.table_name, [])

        if self._action == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for item in payloads:
                row = dict(item)
                if "id" not in row:
                    row["id"] = str(uuid4())
                if "created_at" not in row:
                    row["created_at"] = datetime.now(timezone.utc).isoformat()
                table_rows.append(row)
                inserted.append(row)
            res = MagicMock()
            res.data = inserted
            return res

        elif self._action == "upsert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            upserted = []
            conflict_col = self._on_conflict or "call_id"
            for item in payloads:
                row = dict(item)
                match_idx = None
                if conflict_col in row and row[conflict_col] is not None:
                    for idx, existing in enumerate(table_rows):
                        if existing.get(conflict_col) == row[conflict_col]:
                            match_idx = idx
                            break
                if match_idx is not None:
                    table_rows[match_idx].update(row)
                    upserted.append(table_rows[match_idx])
                else:
                    if "id" not in row:
                        row["id"] = str(uuid4())
                    if "created_at" not in row:
                        row["created_at"] = datetime.now(timezone.utc).isoformat()
                    table_rows.append(row)
                    upserted.append(row)
            res = MagicMock()
            res.data = upserted
            return res

        elif self._action == "update":
            matching = self._filter_rows(table_rows)
            for row in matching:
                row.update(self._payload)
            res = MagicMock()
            res.data = matching
            return res

        elif self._action == "select":
            matching = self._filter_rows(table_rows)
            if self.limit_val is not None:
                matching = matching[: self.limit_val]
            res = MagicMock()
            if self.is_single:
                res.data = matching[0] if matching else None
            else:
                res.data = matching
            return res

        res = MagicMock()
        res.data = []
        return res

    def _filter_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for row in rows:
            matches = True
            for col, op, val in self.filters:
                row_val = row.get(col)
                if op == "eq":
                    if str(row_val) != str(val):
                        matches = False
                        break
                elif op == "in":
                    if row_val not in val:
                        matches = False
                        break
            if matches:
                result.append(row)
        return result


class FakeSupabase:
    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {}

    def table(self, name: str):
        return FakeQueryBuilder(name, self)


class FakeFalkorGraph:
    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, Dict[str, Any]] = {}

    def query(self, cypher: str, params: Optional[Dict[str, Any]] = None):
        params = params or {}
        # Simulate MERGE (c:Contact {id: $contact_id})
        cid = params.get("contact_id")
        if cid:
            self.nodes[f"Contact:{cid}"] = {"id": cid}

        # Simulate Topic & FRUSTRATED_ABOUT edge
        tname = params.get("topic_name")
        if tname and cid:
            self.nodes[f"Topic:{tname}"] = {"name": tname}
            edge_key = f"{cid}->{tname}"
            call_id = params.get("call_id")
            if edge_key not in self.edges:
                self.edges[edge_key] = {
                    "count": 1,
                    "last_call_id": call_id,
                    "last_seen": params.get("now_str"),
                }
            else:
                current = self.edges[edge_key]
                if call_id and current.get("last_call_id") == call_id:
                    # Do not increment if call_id is identical
                    pass
                else:
                    current["count"] = current.get("count", 0) + 1
                    current["last_call_id"] = call_id
                current["last_seen"] = params.get("now_str")

        # Simulate Entity & MENTIONED edge
        ename = params.get("ent_name")
        if ename and cid:
            self.nodes[f"Entity:{ename}"] = {"name": ename}
            self.edges[f"{cid}->{ename}"] = {"type": "MENTIONED"}

        res = MagicMock()
        res.result_set = []
        return res


# ---------------------------------------------------------------------------
# Test Fixtures & Shared State
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_db():
    db = FakeSupabase()
    return db


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_graph():
    return FakeFalkorGraph("test_contact_graph")


# ---------------------------------------------------------------------------
# Test 1: Full Pipeline Idempotency on Double Run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_call_pipeline_idempotency_double_run(fake_db, fake_redis, fake_graph):
    """
    Running post_call_pipeline twice on the same call must:
    - Produce exactly one episode in memory_episodic
    - Produce exactly one copy of each fact in memory_long_term
    - Increment frustration edge count once in FalkorDB
    - Fire connectors and email exactly once
    - Mark all completed steps in calls.post_steps
    """
    call_id = str(uuid4())
    contact_id = str(uuid4())
    org_id = str(uuid4())
    agent_id = str(uuid4())

    # Pre-populate call in calls table
    fake_db.tables["calls"] = [{
        "id": call_id,
        "contact_id": contact_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "status": "in_progress",
        "post_steps": {},
        "post_processed_at": None,
    }]

    # Pre-populate contact & agent
    fake_db.tables["contacts"] = [{
        "id": contact_id,
        "org_id": org_id,
        "name": "Alice Smith",
        "phone": "+15551234567",
    }]
    fake_db.tables["agents"] = [{
        "id": agent_id,
        "org_id": org_id,
        "name": "Billing Assistant",
        "config": {"analysis": {}},
        "notification_email": "ops@example.com",
    }]

    # Pre-populate short term memory
    turns = [
        {"role": "assistant", "content": "Hello, how can I help you today?"},
        {"role": "user", "content": "My billing invoice is wrong for March, please refund me."},
        {"role": "assistant", "content": "I understand. I am processing your refund request."},
    ]
    emotion_events = [
        {"valence": -0.6, "arousal": 0.8},
        {"valence": 0.2, "arousal": 0.4},
    ]
    await fake_redis.set(f"stm:{call_id}", json.dumps({"turns": turns, "emotion_events": emotion_events}))

    # LLM responses mock
    async def fake_llm_generate(*args, **kwargs):
        prompt_content = str(kwargs.get("messages", []))
        if "key_facts" in prompt_content or "summarizing customer" in str(kwargs.get("prompt", "")):
            return json.dumps({
                "summary": "Customer reported billing invoice error and requested refund.",
                "key_facts": ["Billing invoice error for March", "Requested refund"],
                "emotion_arc": "Frustrated to relieved",
            })
        elif "frustration_topics" in prompt_content:
            return json.dumps({
                "entities": ["Billing Department", "Invoice #101"],
                "frustration_topics": ["billing error", "wrong invoice"],
            })
        else:
            return json.dumps({
                "summary": "Call resolved with refund initiation.",
                "sentiment": "Neutral",
                "action_items": ["Issue refund for March"],
                "user_intent": "Refund inquiry",
                "resolution_status": "resolved",
            })

    connector_mock = AsyncMock(return_value=[{"hubspot": "synced"}])
    email_mock = AsyncMock(return_value=True)

    with patch("trigger.post_call_pipeline.supabase", fake_db), \
         patch("app.services.memory.episodic.supabase", fake_db), \
         patch("app.services.memory.long_term.supabase", fake_db), \
         patch("app.services.post_call.supabase", fake_db), \
         patch("app.services.redis_client.redis_client", fake_redis), \
         patch("app.services.memory.short_term.redis_client", fake_redis), \
         patch("app.services.memory.graph.connect_falkor", return_value=fake_graph), \
         patch("app.services.llm.llm_service.generate", side_effect=fake_llm_generate), \
         patch("app.services.memory.long_term.generate_embedding", return_value=[0.1] * 1024), \
         patch("trigger.post_call_pipeline.fire_post_call_connectors", connector_mock), \
         patch("trigger.post_call_pipeline.email.send_post_call_email", email_mock):

        # --- First Pipeline Execution ---
        res1 = await post_call_pipeline(call_id=call_id, agent_id=agent_id, contact_id=contact_id, org_id=org_id)
        assert res1["status"] == "success"

        # Assertions after first run:
        episodes = fake_db.tables.get("memory_episodic", [])
        assert len(episodes) == 1
        assert episodes[0]["call_id"] == call_id

        facts = fake_db.tables.get("memory_long_term", [])
        assert len(facts) == 2  # exactly 2 facts stored
        for f in facts:
            assert f["call_id"] == call_id

        assert connector_mock.call_count == 1
        assert email_mock.call_count == 1

        call_row = fake_db.tables["calls"][0]
        assert call_row["status"] == "completed"
        assert call_row["post_processed_at"] is not None
        steps = call_row["post_steps"]
        assert "episodic" in steps
        assert "long_term" in steps
        assert "graph" in steps
        assert "analysis" in steps
        assert "connectors" in steps
        assert "email" in steps
        assert "completed" in steps

        # Check FalkorDB frustration edge count
        assert fake_graph.edges["{}->billing error".format(contact_id)]["count"] == 1

        # --- Second Pipeline Execution (Retry / Duplicate run) ---
        res2 = await post_call_pipeline(call_id=call_id, agent_id=agent_id, contact_id=contact_id, org_id=org_id)
        assert res2["status"] == "success"

        # Assertions after second run:
        episodes_after = fake_db.tables.get("memory_episodic", [])
        assert len(episodes_after) == 1  # exactly one episode still

        facts_after = fake_db.tables.get("memory_long_term", [])
        assert len(facts_after) == 2  # still exactly one copy of each fact!

        # Connectors and email must NOT have been called a second time
        assert connector_mock.call_count == 1
        assert email_mock.call_count == 1

        # FalkorDB frustration edge count must remain 1
        assert fake_graph.edges["{}->billing error".format(contact_id)]["count"] == 1


# ---------------------------------------------------------------------------
# Test 2: Failure Recovery at Graph Step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_call_pipeline_retry_after_graph_failure(fake_db, fake_redis, fake_graph):
    """
    When pipeline fails during the graph step, a retry should skip already completed
    steps (episodic and long_term) and complete only the remaining steps.
    """
    call_id = str(uuid4())
    contact_id = str(uuid4())
    org_id = str(uuid4())
    agent_id = str(uuid4())

    fake_db.tables["calls"] = [{
        "id": call_id,
        "contact_id": contact_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "status": "in_progress",
        "post_steps": {},
        "post_processed_at": None,
    }]
    fake_db.tables["contacts"] = [{"id": contact_id, "org_id": org_id, "name": "Bob", "phone": "+1555"}]
    fake_db.tables["agents"] = [{"id": agent_id, "org_id": org_id, "name": "Support", "config": {}}]

    turns = [{"role": "user", "content": "My service is down."}]
    await fake_redis.set(f"stm:{call_id}", json.dumps({"turns": turns, "emotion_events": []}))

    async def fake_llm(*args, **kwargs):
        prompt_content = str(kwargs.get("messages", []))
        if "key_facts" in prompt_content or "summarizing" in str(kwargs.get("prompt", "")):
            return json.dumps({
                "summary": "Service outage reported.",
                "key_facts": ["Outage at 2 PM"],
                "emotion_arc": "Neutral",
            })
        elif "frustration_topics" in prompt_content:
            return json.dumps({"entities": ["Server"], "frustration_topics": ["outage"]})
        else:
            return json.dumps({
                "summary": "Reported outage",
                "sentiment": "Neutral",
                "action_items": [],
                "user_intent": "Outage",
                "resolution_status": "in_progress",
            })

    connector_mock = AsyncMock(return_value=[])
    email_mock = AsyncMock(return_value=True)

    with patch("trigger.post_call_pipeline.supabase", fake_db), \
         patch("app.services.memory.episodic.supabase", fake_db), \
         patch("app.services.memory.long_term.supabase", fake_db), \
         patch("app.services.post_call.supabase", fake_db), \
         patch("app.services.redis_client.redis_client", fake_redis), \
         patch("app.services.memory.short_term.redis_client", fake_redis), \
         patch("app.services.llm.llm_service.generate", side_effect=fake_llm), \
         patch("app.services.memory.long_term.generate_embedding", return_value=[0.1] * 1024), \
         patch("trigger.post_call_pipeline.fire_post_call_connectors", connector_mock), \
         patch("trigger.post_call_pipeline.email.send_post_call_email", email_mock):

        # First run: graph step raises an exception
        with patch("app.services.memory.graph.add_entities", side_effect=RuntimeError("FalkorDB connection timeout")):
            with pytest.raises(RuntimeError, match="FalkorDB connection timeout"):
                await post_call_pipeline(call_id=call_id, agent_id=agent_id, contact_id=contact_id, org_id=org_id)

        # Confirm state after failure:
        call_row = fake_db.tables["calls"][0]
        steps = call_row["post_steps"]
        assert "episodic" in steps
        assert "long_term" in steps
        assert "graph" not in steps
        assert "connectors" not in steps
        assert "email" not in steps
        assert len(fake_db.tables.get("memory_episodic", [])) == 1
        assert len(fake_db.tables.get("memory_long_term", [])) == 1

        # Second run (retry): graph step succeeds
        with patch("app.services.memory.graph.connect_falkor", return_value=fake_graph), \
             patch("app.services.memory.episodic.create_episode") as spy_create_episode, \
             patch("app.services.memory.long_term.store_fact") as spy_store_fact:

            res_retry = await post_call_pipeline(call_id=call_id, agent_id=agent_id, contact_id=contact_id, org_id=org_id)
            assert res_retry["status"] == "success"

            # create_episode and store_fact should NOT have been called on retry!
            spy_create_episode.assert_not_called()
            spy_store_fact.assert_not_called()

            # FalkorDB, connectors, email should have run
            assert connector_mock.call_count == 1
            assert email_mock.call_count == 1

            # All steps now marked
            steps_final = fake_db.tables["calls"][0]["post_steps"]
            assert "graph" in steps_final
            assert "analysis" in steps_final
            assert "connectors" in steps_final
            assert "email" in steps_final
            assert "completed" in steps_final


# ---------------------------------------------------------------------------
# Test 3: Erasure Flag Stops Memory Writes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_call_pipeline_erasure_flag_stops_writes(fake_db, fake_redis, fake_graph):
    """
    If erasure:{contact_id} flag is active in Redis, post_call_pipeline skips memory writes.
    """
    call_id = str(uuid4())
    contact_id = str(uuid4())
    org_id = str(uuid4())
    agent_id = str(uuid4())

    fake_db.tables["calls"] = [{
        "id": call_id,
        "contact_id": contact_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "status": "in_progress",
        "post_steps": {},
    }]

    # Set erasure flag in Redis
    await fake_redis.set(f"erasure:{contact_id}", "true")

    with patch("trigger.post_call_pipeline.supabase", fake_db), \
         patch("app.services.redis_client.redis_client", fake_redis):

        result = await post_call_pipeline(call_id=call_id, agent_id=agent_id, contact_id=contact_id, org_id=org_id)
        assert result["status"] == "skipped"
        assert f"Contact {contact_id} marked for erasure" in result["reason"]

        # No episodic memories written
        assert len(fake_db.tables.get("memory_episodic", [])) == 0
        # No long term facts written
        assert len(fake_db.tables.get("memory_long_term", [])) == 0
        # No graph nodes/edges created
        assert len(fake_graph.nodes) == 0


# ---------------------------------------------------------------------------
# Test 4: episodic.create_episode Upserts on call_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_episodic_upsert_on_call_id(fake_db, fake_redis):
    """
    Calling create_episode twice with the same call_id returns existing record without duplicates,
    and does not write duplicate facts to memory_long_term.
    """
    call_id = str(uuid4())
    contact_id = str(uuid4())
    org_id = str(uuid4())

    async def fake_llm(*args, **kwargs):
        return json.dumps({
            "summary": "Caller asked about renewal date.",
            "key_facts": ["Renewal date is Oct 15"],
            "emotion_arc": "Neutral",
        })

    with patch("app.services.memory.episodic.supabase", fake_db), \
         patch("app.services.memory.long_term.supabase", fake_db), \
         patch("app.services.redis_client.redis_client", fake_redis), \
         patch("app.services.llm.llm_service.generate", side_effect=fake_llm):

        ep1 = await episodic.create_episode(
            call_id=call_id,
            contact_id=contact_id,
            org_id=org_id,
            transcript=[{"role": "user", "content": "When is my renewal date?"}],
        )
        assert ep1 is not None
        assert ep1["call_id"] == call_id

        # Second call with the same call_id
        ep2 = await episodic.create_episode(
            call_id=call_id,
            contact_id=contact_id,
            org_id=org_id,
            transcript=[{"role": "user", "content": "When is my renewal date?"}],
        )
        assert ep2 is not None
        assert ep2["id"] == ep1["id"]

        # Only one row exists in table
        assert len(fake_db.tables["memory_episodic"]) == 1

        # Verify create_episode does NOT write to memory_long_term (preventing duplicate fact writes)
        assert len(fake_db.tables.get("memory_long_term", [])) == 0


# ---------------------------------------------------------------------------
# Test 5: long_term.store_fact Deduplication with call_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_long_term_store_fact_deduplication_with_call_id(fake_db, fake_redis):
    """
    Calling store_fact twice with the same (contact_id, call_id, content) creates only one row.
    """
    contact_id = str(uuid4())
    org_id = str(uuid4())
    call_id = str(uuid4())

    with patch("app.services.memory.long_term.supabase", fake_db), \
         patch("app.services.redis_client.redis_client", fake_redis), \
         patch("app.services.memory.long_term.generate_embedding", return_value=[0.1] * 1024):

        f1 = await long_term.store_fact(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=str(uuid4()),
            content="Customer preferred email communication",
            call_id=call_id,
        )
        assert f1 is not None

        # Repeat with same call_id and content
        f2 = await long_term.store_fact(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=str(uuid4()),
            content="Customer preferred email communication",
            call_id=call_id,
        )
        assert f2 is not None

        # Only 1 row stored
        rows = fake_db.tables.get("memory_long_term", [])
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Test 6: graph.add_frustration_edges Idempotent with call_id
# ---------------------------------------------------------------------------

def test_graph_add_frustration_edges_idempotent_with_call_id(fake_graph):
    """
    Calling add_frustration_edges with the same call_id does not increment edge count twice.
    """
    contact_id = str(uuid4())
    call_id = str(uuid4())
    episode_id = str(uuid4())

    with patch("app.services.memory.graph.connect_falkor", return_value=fake_graph):
        res1 = graph.add_frustration_edges(
            contact_id=contact_id,
            topics=["billing error"],
            episode_id=episode_id,
            call_id=call_id,
        )
        assert res1 is True
        edge_key = f"{contact_id}->billing error"
        assert fake_graph.edges[edge_key]["count"] == 1

        # Second call with the exact same call_id
        res2 = graph.add_frustration_edges(
            contact_id=contact_id,
            topics=["billing error"],
            episode_id=episode_id,
            call_id=call_id,
        )
        assert res2 is True
        assert fake_graph.edges[edge_key]["count"] == 1
