"""
Tests for PIPELINE_MODE configuration, pipeline path visibility,
Pipecat error fallback, and shared multi-modal turn execution.
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.config import settings
from app.services import voice_pipeline, webcall_pipeline
from app.services.turn_pipeline import execute_shared_turn_steps, format_t2_facts


def test_pipeline_aliases_exist():
    """Verify backward-compatibility aliases exist and reference the custom loops."""
    assert hasattr(voice_pipeline, "_minimal_echo_loop")
    assert voice_pipeline._minimal_echo_loop is voice_pipeline._custom_turn_loop

    assert hasattr(webcall_pipeline, "_run_minimal_webcall_loop")
    assert webcall_pipeline._run_minimal_webcall_loop is webcall_pipeline._custom_webcall_loop

    assert hasattr(voice_pipeline, "_format_t2_facts")
    assert voice_pipeline._format_t2_facts is format_t2_facts

    assert hasattr(webcall_pipeline, "_format_t2_facts")
    assert webcall_pipeline._format_t2_facts is format_t2_facts


def test_get_active_pipeline_path():
    """Verify get_active_pipeline_path returns 'custom' by default and 'pipecat' when configured."""
    with patch.object(settings, "PIPELINE_MODE", "custom"):
        assert voice_pipeline.get_active_pipeline_path() == "custom"

    with patch.object(settings, "PIPELINE_MODE", "pipecat"):
        assert voice_pipeline.get_active_pipeline_path() == "pipecat"

    with patch.object(settings, "PIPELINE_MODE", "unknown_val"):
        assert voice_pipeline.get_active_pipeline_path() == "custom"


@pytest.mark.asyncio
async def test_custom_mode_never_imports_pipecat():
    """In PIPELINE_MODE='custom', pipecat should never be imported or called."""
    # Ensure any previous import is removed for this test
    sys.modules.pop("pipecat", None)

    with patch.object(settings, "PIPELINE_MODE", "custom"), \
         patch("app.services.voice_pipeline._load_agent_config", new=AsyncMock(return_value={"org_id": "test_org"})), \
         patch("app.services.voice_pipeline._load_org_api_keys", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline.short_term.init_call_memory", new=AsyncMock()), \
         patch("app.services.voice_pipeline.retrieve_all_memory", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline._finalize_call", new=AsyncMock()), \
         patch("app.services.voice_pipeline._custom_turn_loop", new=AsyncMock()) as mock_custom_loop:

        ws_mock = MagicMock()
        await voice_pipeline.start_pipeline(
            call_id="call-custom-1",
            agent_id="agent-1",
            contact_id="contact-1",
            ws_connection=ws_mock,
        )

        assert mock_custom_loop.called
        assert "pipecat" not in sys.modules


@pytest.mark.asyncio
async def test_start_pipeline_records_pipeline_path_in_supabase():
    """Verify that start_pipeline records pipeline_path in calls.analysis."""
    with patch.object(settings, "PIPELINE_MODE", "custom"), \
         patch("app.services.voice_pipeline._load_agent_config", new=AsyncMock(return_value={"org_id": "test_org"})), \
         patch("app.services.voice_pipeline._load_org_api_keys", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline.short_term.init_call_memory", new=AsyncMock()), \
         patch("app.services.voice_pipeline.retrieve_all_memory", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline._finalize_call", new=AsyncMock()), \
         patch("app.services.voice_pipeline._custom_turn_loop", new=AsyncMock()):

        mock_supabase = MagicMock()
        table_mock = MagicMock()
        update_mock = MagicMock()
        eq_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        table_mock.update.return_value = update_mock
        update_mock.eq.return_value = eq_mock
        eq_mock.execute.return_value = MagicMock(data=[])

        with patch("app.services.voice_pipeline.supabase", mock_supabase):
            ws_mock = MagicMock()
            await voice_pipeline.start_pipeline(
                call_id="call-path-check",
                agent_id="agent-1",
                contact_id="contact-1",
                ws_connection=ws_mock,
            )

            # Check that analysis was updated with pipeline_path: custom
            update_mock.eq.assert_called_with("id", "call-path-check")
            update_call_args = table_mock.update.call_args[0][0]
            assert update_call_args["analysis"] == {"pipeline_path": "custom"}


@pytest.mark.asyncio
async def test_pipecat_failure_falls_back_to_custom_turn_loop():
    """When PIPELINE_MODE='pipecat' and Pipecat raises an error, fallback to _custom_turn_loop."""
    with patch.object(settings, "PIPELINE_MODE", "pipecat"), \
         patch("app.services.voice_pipeline._load_agent_config", new=AsyncMock(return_value={"org_id": "test_org"})), \
         patch("app.services.voice_pipeline._load_org_api_keys", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline.short_term.init_call_memory", new=AsyncMock()), \
         patch("app.services.voice_pipeline.retrieve_all_memory", new=AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline._finalize_call", new=AsyncMock()), \
         patch("app.services.voice_pipeline._custom_turn_loop", new=AsyncMock()) as mock_custom_loop:

        # Mocking pipecat import failure
        with patch.dict(sys.modules, {"pipecat.pipeline.pipeline": None}):
            ws_mock = MagicMock()
            await voice_pipeline.start_pipeline(
                call_id="call-fallback-1",
                agent_id="agent-1",
                contact_id="contact-1",
                ws_connection=ws_mock,
            )

            assert mock_custom_loop.called
            call_kwargs = mock_custom_loop.call_args[1]
            assert call_kwargs["call_id"] == "call-fallback-1"


@pytest.mark.asyncio
async def test_webcall_pipecat_failure_falls_back_to_custom_webcall_loop():
    """When webcall pipeline is in pipecat mode and raises, it falls back to _custom_webcall_loop."""
    with patch("app.services.webcall_pipeline.get_active_pipeline_path", return_value="pipecat"), \
         patch("app.services.webcall_pipeline._load_agent_config", new=AsyncMock(return_value={"org_id": "test_org"})), \
         patch("app.services.webcall_pipeline._load_org_api_keys", new=AsyncMock(return_value={})), \
         patch("app.services.webcall_pipeline.short_term.init_call_memory", new=AsyncMock()), \
         patch("app.services.webcall_pipeline.retrieve_all_memory", new=AsyncMock(return_value={})), \
         patch("app.services.webcall_pipeline._finalize_webcall", new=AsyncMock()), \
         patch("app.services.webcall_pipeline._push_sse_event", new=AsyncMock()), \
         patch("app.services.webcall_pipeline._run_pipecat_webcall", side_effect=RuntimeError("Pipecat transport failure")), \
         patch("app.services.webcall_pipeline._custom_webcall_loop", new=AsyncMock()) as mock_custom_webcall:

        await webcall_pipeline.run_webcall_agent(
            call_id="webcall-fallback-1",
            agent_id="agent-1",
            org_id="test_org",
            contact_id="contact-1",
        )

        assert mock_custom_webcall.called
        assert mock_custom_webcall.call_args[1]["call_id"] == "webcall-fallback-1"


@pytest.mark.asyncio
async def test_custom_loops_invoke_shared_turn_steps():
    """Verify that both custom loops use execute_shared_turn_steps."""
    assert voice_pipeline.execute_shared_turn_steps is execute_shared_turn_steps
    assert webcall_pipeline.execute_shared_turn_steps is execute_shared_turn_steps

    shared_result = {
        "fused_emotion": {"dominant": "neutral", "valence": 0.0, "arousal": 0.0},
        "text_emotion": None,
        "audio_emotion": None,
        "active_tools": [],
        "turn_prompt": "Test Prompt",
        "tts_config": {"voice_id": "v1", "voice_provider": "cartesia"},
    }

    # 1. Verify _custom_turn_loop calls execute_shared_turn_steps
    mock_ws = AsyncMock()
    media_event = json.dumps({"event": "media", "media": {"payload": "AP//AP//"}, "streamSid": "s1"})
    mock_ws.receive.side_effect = [
        {"type": "websocket.receive", "text": media_event},
        {"type": "websocket.disconnect"},
    ]

    with patch("app.services.voice_pipeline.execute_shared_turn_steps", new=AsyncMock(return_value=shared_result)) as mock_voice_shared, \
         patch("app.services.voice_pipeline._stt_transcribe", new=AsyncMock(return_value="test speech")), \
         patch("app.services.voice_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.voice_pipeline.llm_service.generate", new=AsyncMock(return_value="test reply")), \
         patch("app.services.voice_pipeline._append_turn_to_redis", new=AsyncMock()), \
         patch("app.services.voice_pipeline._tts_synthesize", new=AsyncMock(return_value=b"audio")):

        await voice_pipeline._custom_turn_loop(
            ws_connection=mock_ws,
            call_id="call-turn-shared-1",
            agent_id="agent-1",
            org_id="org-1",
            system_prompt="prompt",
            api_keys={},
            language="en",
            voice_config={},
        )

        assert mock_voice_shared.called
        assert mock_voice_shared.call_args[1]["call_id"] == "call-turn-shared-1"

    # 2. Verify _custom_webcall_loop calls execute_shared_turn_steps
    mock_room = MagicMock()
    registered_callbacks = {}
    def mock_on(event, cb):
        registered_callbacks[event] = cb
    mock_room.on.side_effect = mock_on
    mock_room.connect = AsyncMock()

    mock_livekit = MagicMock()
    mock_rtc = MagicMock()
    mock_api = MagicMock()
    mock_livekit.rtc = mock_rtc
    mock_livekit.api = mock_api
    mock_rtc.Room.return_value = mock_room

    with patch("app.services.webcall_pipeline.execute_shared_turn_steps", new=AsyncMock(return_value=shared_result)) as mock_web_shared, \
         patch("app.services.webcall_pipeline.livekit_service.is_configured", return_value=True), \
         patch("app.services.webcall_pipeline.livekit_service.generate_agent_token", return_value="token"), \
         patch("app.services.webcall_pipeline.transcribe_audio", new=AsyncMock(return_value="web speech")), \
         patch("app.services.webcall_pipeline.VoiceActivityDetector.process_frame", return_value=b"\x00" * 320), \
         patch("app.services.webcall_pipeline.llm_service.generate", new=AsyncMock(return_value="web reply")), \
         patch("app.services.webcall_pipeline.short_term.append_turn", new=AsyncMock()), \
         patch("app.services.webcall_pipeline._push_sse_event", new=AsyncMock()), \
         patch("app.services.webcall_pipeline.synthesize_speech", new=AsyncMock(return_value=b"web audio")), \
         patch("app.services.webcall_pipeline._publish_audio_to_livekit", new=AsyncMock()), \
         patch.dict(sys.modules, {"livekit": mock_livekit, "livekit.rtc": mock_rtc, "livekit.api": mock_api}):

        task = asyncio.create_task(
            webcall_pipeline._custom_webcall_loop(
                call_id="webcall-shared-1",
                room_name="room-1",
                agent_id="agent-1",
                org_id="org-1",
                system_prompt="prompt",
                language="en",
                voice_config={},
                emotion_config={},
                api_keys={},
                agent={},
            )
        )
        await asyncio.sleep(0.01)

        data_cb = registered_callbacks.get("data_received")
        assert data_cb is not None
        chunk_data = json.dumps({"type": "audio_chunk", "payload": "AP//AP//"}).encode()
        await data_cb(chunk_data, participant=MagicMock())

        assert mock_web_shared.called
        assert mock_web_shared.call_args[1]["call_id"] == "webcall-shared-1"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_eval_config_json_includes_pipeline_path(tmp_path):
    """Verify that eval/common/runlog.py includes pipeline_path in config.json manifest."""
    from eval.common.runlog import start_run

    with patch("app.services.voice_pipeline.get_active_pipeline_path", return_value="custom"):
        run_ctx = start_run(
            experiment="pipeline_test",
            config={"paths": {"results_dir": str(tmp_path)}},
            seed=42,
            mode="mock",
        )
        config_file = run_ctx.run_dir / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert "pipeline_path" in data
        assert data["pipeline_path"] == "custom"
