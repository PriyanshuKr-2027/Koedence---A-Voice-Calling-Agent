"""
tests/test_turn_flow.py — Verification for Fig. 2 / Eq. 1 per-turn pipeline flow and memory loading.

Verifies:
1. Concurrency timing: 3 branches sleeping 100, 80, 60 ms finish in ~100 ms total, not 240 ms.
2. Call start: Both pipelines call retrieve_all_memory at start with tiers t3 and t4, without T2.
3. Per-turn T2 retrieval: T2 is queried per turn with transcript; skipped when MEMORY_PER_TURN=False.
4. Fault isolation: One branch raising an exception does not abort the turn (falls back to neutral emotion or empty memory).
5. Prompt assembly: Assembled prompt contains base + call-start block + per-turn T2 facts + tone instruction + slots.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.latency_stage import stage
from app.services.voice_pipeline import (
    _minimal_echo_loop,
    _format_t2_facts,
    start_pipeline,
)
from app.services.webcall_pipeline import (
    run_webcall_agent,
    _format_t2_facts as webcall_format_t2,
)


# ---------------------------------------------------------------------------
# Test 1: Concurrency Timing (Fig. 2 parallel fan-out)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_fanout_timing():
    """
    With fake branches sleeping 100, 80, and 60 ms, the parallel gather
    must complete in approximately 100 ms (max time), not ~240 ms (sequential sum).
    """
    async def fake_emotion():
        async with stage("emotion", "call_bench", 1):
            await asyncio.sleep(0.100)
            return {"dominant": "neutral"}, None, None

    async def fake_intent():
        async with stage("intent", "call_bench", 1):
            await asyncio.sleep(0.080)
            return "general_inquiry", {}, []

    async def fake_memory():
        async with stage("memory", "call_bench", 1):
            await asyncio.sleep(0.060)
            return ["fact 1"]

    t0 = time.perf_counter()
    emotion_res, intent_res, memory_res = await asyncio.gather(
        fake_emotion(),
        fake_intent(),
        fake_memory(),
    )
    duration_s = time.perf_counter() - t0

    assert emotion_res[0]["dominant"] == "neutral"
    assert intent_res[0] == "general_inquiry"
    assert memory_res == ["fact 1"]

    # Concurrency verification: must be well below sequential 240 ms
    assert duration_s < 0.170, f"Expected concurrency under 170 ms, got {duration_s * 1000:.1f} ms"
    assert duration_s >= 0.090, f"Expected at least 90 ms duration, got {duration_s * 1000:.1f} ms"


# ---------------------------------------------------------------------------
# Test 2: Call Start loads T3 & T4 in both pipelines
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_start_loads_t3_and_t4_both_pipelines():
    """
    Both pipelines (start_pipeline in voice_pipeline and run_webcall_agent in webcall_pipeline)
    must call retrieve_all_memory at call start with enabled_tiers=['t3', 't4'] and query_text=''.
    """
    call_id = "test_call_start_id"
    agent_id = "test_agent_start"
    contact_id = "test_contact_start"
    org_id = "test_org_start"

    agent_data = {
        "id": agent_id,
        "org_id": org_id,
        "system_prompt": "You are a customer support agent.",
        "language": "en",
        "voice_id": "v1",
        "voice_provider": "cartesia",
    }

    mock_retrieve = AsyncMock(return_value={
        "short_term": None,
        "long_term": [],
        "episodic": [{"summary": "Previous call about order #123"}],
        "graph": {"recent_entities": []},
    })

    # 1. Test voice_pipeline.start_pipeline
    with patch("app.services.voice_pipeline._load_agent_config", AsyncMock(return_value=agent_data)), \
         patch("app.services.voice_pipeline._load_org_api_keys", AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline.short_term.init_call_memory", AsyncMock()), \
         patch("app.services.voice_pipeline.retrieve_all_memory", mock_retrieve), \
         patch("app.services.voice_pipeline.livekit_service.is_configured", return_value=False), \
         patch("app.services.voice_pipeline.supabase", None), \
         patch("app.services.voice_pipeline._minimal_echo_loop", AsyncMock()), \
         patch("app.services.voice_pipeline._finalize_call", AsyncMock()):

        mock_ws = AsyncMock()
        await start_pipeline(call_id, agent_id, contact_id, mock_ws)

        mock_retrieve.assert_called_once_with(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=agent_id,
            query_text="",
            config={"call_id": call_id, "episodic_limit": 3},
            enabled_tiers=["t3", "t4"],
        )

    # 2. Test webcall_pipeline.run_webcall_agent
    mock_retrieve_web = AsyncMock(return_value={
        "short_term": None,
        "long_term": [],
        "episodic": [{"summary": "Web user past interaction"}],
        "graph": {},
    })

    with patch("app.services.webcall_pipeline._load_agent_config", AsyncMock(return_value=agent_data)), \
         patch("app.services.webcall_pipeline._load_org_api_keys", AsyncMock(return_value={})), \
         patch("app.services.webcall_pipeline.short_term.init_call_memory", AsyncMock()), \
         patch("app.services.webcall_pipeline.retrieve_all_memory", mock_retrieve_web), \
         patch("app.services.webcall_pipeline._push_sse_event", AsyncMock()), \
         patch("app.services.webcall_pipeline._run_minimal_webcall_loop", AsyncMock()), \
         patch("app.services.webcall_pipeline._finalize_webcall", AsyncMock()):

        await run_webcall_agent(
            call_id=call_id,
            agent_id=agent_id,
            org_id=org_id,
            contact_id=contact_id,
            contact_name="Alice",
        )

        mock_retrieve_web.assert_called_once_with(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=agent_id,
            query_text="",
            config={"call_id": call_id, "episodic_limit": 3},
            enabled_tiers=["t3", "t4"],
        )


# ---------------------------------------------------------------------------
# Test 3: Per-Turn T2 Memory Query with Transcript
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_turn_t2_memory_query():
    """
    On each turn, retrieve_all_memory must be queried with query_text=transcript and enabled_tiers=['t2'].
    When MEMORY_PER_TURN is False, per-turn T2 retrieval must be skipped.
    """
    call_id = "call_t2_test"
    contact_id = "contact_t2_test"
    org_id = "org_t2_test"
    transcript = "Where is my refund?"

    retrieved_facts = [{"content": "Customer requested refund yesterday", "emotion_state": {"dominant": "frustration"}}]
    mock_retrieve = AsyncMock(return_value={"long_term": retrieved_facts})

    class FakeWS:
        def __init__(self):
            # Send single frame of audio then disconnect
            import base64
            fake_payload = base64.b64encode(bytes([128] * 160)).decode()
            self.msgs = [
                {"type": "websocket.receive", "text": json.dumps({"event": "media", "media": {"payload": fake_payload}})},
                {"type": "websocket.disconnect"},
            ]

        async def receive(self):
            if self.msgs:
                return self.msgs.pop(0)
            return {"type": "websocket.disconnect"}

        async def send(self, data):
            pass

    # A. With MEMORY_PER_TURN = True (default)
    with patch("app.services.voice_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.voice_pipeline._stt_transcribe", AsyncMock(return_value=transcript)), \
         patch("app.services.voice_pipeline.retrieve_all_memory", mock_retrieve), \
         patch("app.services.intent.detector.detect", AsyncMock(return_value={"intent": "request_refund", "slot_data": {}})), \
         patch("app.services.intent.slot_manager.merge_slots", AsyncMock(return_value={"order_id": "999"})), \
         patch("app.services.llm.llm_service.generate", AsyncMock(return_value="Your refund is being processed.")), \
         patch("app.services.voice_pipeline.analyze_text_emotion", AsyncMock(return_value={"dominant": "neutral"})), \
         patch("app.services.voice_pipeline.analyze_audio_emotion", AsyncMock(return_value=None)), \
         patch("app.services.voice_pipeline.synthesize_speech", AsyncMock(return_value=b"wav")), \
         patch("app.services.voice_pipeline.short_term.append_turn", AsyncMock()), \
         patch("app.services.voice_pipeline.short_term.append_emotion_event", AsyncMock()), \
         patch.object(settings, "MEMORY_PER_TURN", True):

        ws = FakeWS()
        await _minimal_echo_loop(
            ws_connection=ws,
            call_id=call_id,
            agent_id="agent_1",
            org_id=org_id,
            system_prompt="Base prompt",
            api_keys={},
            language="en",
            voice_config={},
            contact_id=contact_id,
        )

        mock_retrieve.assert_called_once_with(
            contact_id=contact_id,
            org_id=org_id,
            agent_id="agent_1",
            query_text=transcript,
            config={"call_id": call_id},
            enabled_tiers=["t2"],
        )

    # B. With MEMORY_PER_TURN = False
    mock_retrieve_disabled = AsyncMock()
    with patch("app.services.voice_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.voice_pipeline._stt_transcribe", AsyncMock(return_value=transcript)), \
         patch("app.services.voice_pipeline.retrieve_all_memory", mock_retrieve_disabled), \
         patch("app.services.intent.detector.detect", AsyncMock(return_value={"intent": "request_refund", "slot_data": {}})), \
         patch("app.services.intent.slot_manager.merge_slots", AsyncMock(return_value={})), \
         patch("app.services.llm.llm_service.generate", AsyncMock(return_value="Response")), \
         patch("app.services.voice_pipeline.analyze_text_emotion", AsyncMock(return_value={"dominant": "neutral"})), \
         patch("app.services.voice_pipeline.analyze_audio_emotion", AsyncMock(return_value=None)), \
         patch("app.services.voice_pipeline.synthesize_speech", AsyncMock(return_value=b"wav")), \
         patch("app.services.voice_pipeline.short_term.append_turn", AsyncMock()), \
         patch("app.services.voice_pipeline.short_term.append_emotion_event", AsyncMock()), \
         patch.object(settings, "MEMORY_PER_TURN", False):

        ws = FakeWS()
        await _minimal_echo_loop(
            ws_connection=ws,
            call_id=call_id,
            agent_id="agent_1",
            org_id=org_id,
            system_prompt="Base prompt",
            api_keys={},
            language="en",
            voice_config={},
            contact_id=contact_id,
        )

        mock_retrieve_disabled.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Fault Isolation (One branch raising does not abort turn)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fault_isolation_branch_raising():
    """
    If any of the parallel branches (emotion, intent, or memory) raises an exception,
    the turn must NOT abort. It should fall back cleanly (neutral emotion, empty memory, default intent).
    """
    call_id = "call_fault_test"
    contact_id = "contact_fault_test"
    org_id = "org_fault_test"

    class FakeWS:
        def __init__(self):
            import base64
            fake_payload = base64.b64encode(bytes([128] * 160)).decode()
            self.msgs = [
                {"type": "websocket.receive", "text": json.dumps({"event": "media", "media": {"payload": fake_payload}})},
                {"type": "websocket.disconnect"},
            ]

        async def receive(self):
            if self.msgs:
                return self.msgs.pop(0)
            return {"type": "websocket.disconnect"}

        async def send(self, data):
            pass

    llm_mock = AsyncMock(return_value="Still works smoothly.")

    # Emotion and Memory raise RuntimeError, Intent raises ValueError
    with patch("app.services.voice_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.voice_pipeline._stt_transcribe", AsyncMock(return_value="Hello there")), \
         patch("app.services.voice_pipeline.analyze_text_emotion", AsyncMock(side_effect=RuntimeError("Emotion API Down"))), \
         patch("app.services.voice_pipeline.analyze_audio_emotion", AsyncMock(side_effect=RuntimeError("Hume audio down"))), \
         patch("app.services.voice_pipeline.retrieve_all_memory", AsyncMock(side_effect=RuntimeError("PgVector timeout"))), \
         patch("app.services.intent.detector.detect", AsyncMock(side_effect=ValueError("LLM parse failure"))), \
         patch("app.services.llm.llm_service.generate", llm_mock), \
         patch("app.services.voice_pipeline.synthesize_speech", AsyncMock(return_value=b"wav")), \
         patch("app.services.voice_pipeline.short_term.append_turn", AsyncMock()), \
         patch("app.services.voice_pipeline.short_term.append_emotion_event", AsyncMock()), \
         patch.object(settings, "MEMORY_PER_TURN", True):

        ws = FakeWS()
        await _minimal_echo_loop(
            ws_connection=ws,
            call_id=call_id,
            agent_id="agent_1",
            org_id=org_id,
            system_prompt="Base prompt",
            api_keys={},
            language="en",
            voice_config={},
            contact_id=contact_id,
        )

        # Verification: LLM was invoked despite all branches failing
        assert llm_mock.call_count == 1
        call_prompt = llm_mock.call_args.kwargs.get("prompt", "")
        # Base prompt is present
        assert "Base prompt" in call_prompt


# ---------------------------------------------------------------------------
# Test 5: Prompt Assembly Structure (base + call-start + T2 + tone + slots)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_assembly_structure():
    """
    Verify prompt assembly contains:
    base + call-start block (T3/T4) + per-turn T2 facts + tone instruction + slots.
    """
    call_id = "call_prompt_assembly"
    contact_id = "contact_prompt_assembly"
    org_id = "org_prompt_assembly"

    class FakeWS:
        def __init__(self):
            import base64
            fake_payload = base64.b64encode(bytes([128] * 160)).decode()
            self.msgs = [
                {"type": "websocket.receive", "text": json.dumps({"event": "media", "media": {"payload": fake_payload}})},
                {"type": "websocket.disconnect"},
            ]

        async def receive(self):
            if self.msgs:
                return self.msgs.pop(0)
            return {"type": "websocket.disconnect"}

        async def send(self, data):
            pass

    llm_mock = AsyncMock(return_value="Appointment booked.")

    with patch("app.services.voice_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.voice_pipeline._stt_transcribe", AsyncMock(return_value="I want to book an appointment for tomorrow")), \
         patch("app.services.voice_pipeline.retrieve_all_memory", AsyncMock(return_value={"long_term": [{"content": "Prefers morning slots", "emotion_state": {"dominant": "neutral"}}]})), \
         patch("app.services.intent.detector.detect", AsyncMock(return_value={"intent": "book_appointment", "slot_data": {"date": "tomorrow"}})), \
         patch("app.services.intent.slot_manager.merge_slots", AsyncMock(return_value={"date": "tomorrow"})), \
         patch("app.services.llm.llm_service.generate", llm_mock), \
         patch("app.services.voice_pipeline.analyze_text_emotion", AsyncMock(return_value={"dominant": "anxiety", "valence": -0.7, "arousal": 0.8})), \
         patch("app.services.voice_pipeline.analyze_audio_emotion", AsyncMock(return_value=None)), \
         patch("app.services.voice_pipeline.synthesize_speech", AsyncMock(return_value=b"wav")), \
         patch("app.services.voice_pipeline.short_term.append_turn", AsyncMock()), \
         patch("app.services.voice_pipeline.short_term.append_emotion_event", AsyncMock()), \
         patch.object(settings, "MEMORY_PER_TURN", True):

        ws = FakeWS()
        call_start_block = "[CONTACT MEMORY]\nPrevious conversations:\n- Customer called about pricing"
        agent_config = {
            "config": {
                "emotion": {
                    "tone_adaptation": True,
                }
            }
        }
        await _minimal_echo_loop(
            ws_connection=ws,
            call_id=call_id,
            agent_id="agent_1",
            org_id=org_id,
            system_prompt="You are a scheduling assistant.",
            api_keys={},
            language="en",
            voice_config={},
            agent=agent_config,
            contact_id=contact_id,
            call_start_block=call_start_block,
        )

        assert llm_mock.call_count == 1
        prompt = llm_mock.call_args.kwargs.get("prompt", "")

        # 1. Base prompt
        assert "You are a scheduling assistant." in prompt
        # 2. Call-start block
        assert "[CONTACT MEMORY]" in prompt
        assert "Customer called about pricing" in prompt
        # 3. Per-turn T2 facts
        assert "[RELEVANT FACTS]" in prompt
        assert "Prefers morning slots" in prompt
        # 4. Tone instruction (triggered by valence < -0.6)
        assert "The caller is very frustrated." in prompt
        # 5. Slots block
        assert "[SLOTS FILLED THIS CALL]" in prompt
        assert "date: tomorrow" in prompt
