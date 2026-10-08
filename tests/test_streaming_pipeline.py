"""
tests/test_streaming_pipeline.py — Unit tests for token streaming (LLM),
streaming TTS (Cartesia/chunked), first-sentence triggering, latency stage renaming,
and blocking fallback execution.
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.latency_stage import stage
from app.services.llm import LLMService, RateLimitError
from app.services.tts import synthesize_speech_stream, _synthesize_cartesia_stream
from app.services.voice_pipeline import (
    _custom_turn_loop,
    _has_sentence_end,
    _split_first_sentence,
)


class TestSentenceSplitter:
    """Tests for sentence boundary detection and splitting."""

    def test_has_sentence_end(self):
        assert _has_sentence_end("Hello there! How are you?") is True
        assert _has_sentence_end("This is a complete sentence. ") is True
        assert _has_sentence_end("Line one\nLine two") is True
        assert _has_sentence_end("नमस्ते आप कैसे हैं।") is True
        assert _has_sentence_end("Just an incomplete fragment") is False

    def test_split_first_sentence(self):
        first, rem = _split_first_sentence("Hello world! How can I help you today?")
        assert first == "Hello world!"
        assert rem.strip() == "How can I help you today?"

        first_hindi, rem_hindi = _split_first_sentence("नमस्ते जी। आपका दिन शुभ हो।")
        assert first_hindi == "नमस्ते जी।"
        assert rem_hindi.strip() == "आपका दिन शुभ हो।"

        no_split, rem_empty = _split_first_sentence("Incomplete sentence")
        assert no_split == "Incomplete sentence"
        assert rem_empty == ""


class TestLLMStreaming:
    """Tests for LLMService.generate_stream()."""

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self):
        service = LLMService()
        sample_tokens = ["Hello", " ", "world", "! ", "How", " can", " I", " help?"]

        async def fake_provider_stream(*args, **kwargs):
            for token in sample_tokens:
                yield token

        with patch.object(service, "_call_provider_stream", side_effect=fake_provider_stream):
            collected = []
            async for tok in service.generate_stream(
                prompt="System prompt",
                messages=[{"role": "user", "content": "Hi"}],
                api_keys={"groq_api_key": "mock_groq_key"},
            ):
                collected.append(tok)

            assert collected == sample_tokens
            assert "".join(collected) == "Hello world! How can I help?"

    @pytest.mark.asyncio
    async def test_generate_stream_falls_back_to_cerebras_on_groq_429(self):
        service = LLMService()
        cerebras_tokens = ["Response", " from", " Cerebras", "."]

        async def fake_groq_stream(*args, **kwargs):
            raise RateLimitError("Groq 429 rate limit")
            yield "never"

        async def fake_cerebras_stream(*args, **kwargs):
            for tok in cerebras_tokens:
                yield tok

        async def fake_call_provider(base_url, api_key, payload):
            if "groq" in base_url:
                async for tok in fake_groq_stream():
                    yield tok
            else:
                async for tok in fake_cerebras_stream():
                    yield tok

        with patch.object(service, "_call_provider_stream", side_effect=fake_call_provider):
            collected = []
            async for tok in service.generate_stream(
                prompt="System prompt",
                messages=[{"role": "user", "content": "Hi"}],
                api_keys={
                    "groq_api_key": "mock_groq_key",
                    "cerebras_api_key": "mock_cerebras_key",
                },
            ):
                collected.append(tok)

            assert collected == cerebras_tokens


class TestTTSStreaming:
    """Tests for synthesize_speech_stream()."""

    @pytest.mark.asyncio
    async def test_synthesize_speech_stream_cartesia(self):
        chunks = [b"\x00\x01" * 512, b"\x02\x03" * 512, b"\x04\x05" * 512]

        async def fake_cartesia_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch(
            "app.services.tts._synthesize_cartesia_stream",
            side_effect=fake_cartesia_stream,
        ):
            received = []
            async for audio_frame in synthesize_speech_stream(
                text="Hello world!",
                voice_config={"voice_provider": "cartesia", "voice_id": "mock_voice"},
                api_keys={"cartesia": "mock_cartesia_key"},
            ):
                received.append(audio_frame)

            assert received == chunks
            assert len(b"".join(received)) == 3072

    @pytest.mark.asyncio
    async def test_synthesize_speech_stream_fallback_to_buffered(self):
        buffered_audio = b"\xaa\xbb" * 1024  # 2048 bytes

        with patch(
            "app.services.tts.synthesize_speech",
            new_callable=AsyncMock,
            return_value=buffered_audio,
        ):
            received = []
            async for audio_frame in synthesize_speech_stream(
                text="Hume speech test",
                voice_config={"voice_provider": "hume", "voice_id": "hume_voice"},
                api_keys={"hume": "mock_hume_key"},
                chunk_size=1024,
            ):
                received.append(audio_frame)

            assert b"".join(received) == buffered_audio
            assert len(received) == 2


class TestVoicePipelineStreamingAndStages:
    """Tests for voice pipeline turn loop streaming and stage timing."""

    @pytest.mark.asyncio
    async def test_turn_loop_streaming_records_llm_ttft_and_tts_ttfab(self, tmp_path):
        latency_log = tmp_path / "latency.jsonl"
        os.environ["LATENCY_LOG"] = str(latency_log)

        try:
            call_id = f"test_stream_{uuid4().hex[:6]}"
            token_list = ["Hello", " world", "! ", "This", " is", " streaming", "."]
            audio_frames = [b"frame_1_audio", b"frame_2_audio"]

            async def fake_llm_stream(*args, **kwargs):
                await asyncio.sleep(0.01)
                for tok in token_list:
                    yield tok

            async def fake_tts_stream(*args, **kwargs):
                await asyncio.sleep(0.01)
                for frame in audio_frames:
                    yield frame

            sent_ws_messages = []

            class FakeWebSocket:
                def __init__(self):
                    self.call_count = 0

                async def receive(self):
                    self.call_count += 1
                    if self.call_count == 1:
                        import base64
                        fake_mulaw = b"\xff" * 320
                        payload = {
                            "event": "media",
                            "streamSid": "stream_123",
                            "media": {"payload": base64.b64encode(fake_mulaw).decode()},
                        }
                        return {"type": "websocket.receive", "text": json.dumps(payload)}
                    elif self.call_count == 2:
                        return {"type": "websocket.receive", "text": json.dumps({"event": "stop"})}
                    return {"type": "websocket.disconnect"}

                async def send(self, msg):
                    sent_ws_messages.append(msg)

                async def send_text(self, text):
                    sent_ws_messages.append({"type": "websocket.send", "text": text})

            fake_vad_pcm = b"\x00\x00" * 320
            with patch("app.services.voice_pipeline.VoiceActivityDetector") as mock_vad_cls, \
                 patch("app.services.voice_pipeline._stt_transcribe", new_callable=AsyncMock, return_value="Hello there"), \
                 patch("app.services.voice_pipeline.execute_shared_turn_steps", new_callable=AsyncMock) as mock_shared, \
                 patch("app.services.voice_pipeline.llm_service.generate_stream", side_effect=fake_llm_stream), \
                 patch("app.services.voice_pipeline.synthesize_speech_stream", side_effect=fake_tts_stream), \
                 patch("app.services.voice_pipeline._append_turn_to_redis", new_callable=AsyncMock):

                mock_vad_inst = MagicMock()
                mock_vad_inst.process_frame.return_value = fake_vad_pcm
                mock_vad_cls.return_value = mock_vad_inst

                mock_shared.return_value = {
                    "fused_emotion": {"dominant": "neutral"},
                    "text_emotion": None,
                    "audio_emotion": None,
                    "active_tools": [],
                    "turn_prompt": "You are a helpful assistant.",
                    "tts_config": {"voice_provider": "cartesia", "voice_id": "sonic-2"},
                }

                ws = FakeWebSocket()
                await _custom_turn_loop(
                    ws_connection=ws,
                    call_id=call_id,
                    agent_id="agent_1",
                    org_id="org_1",
                    system_prompt="Assistant prompt",
                    api_keys={"groq": "test", "cartesia": "test"},
                    language="en",
                    voice_config={"voice_provider": "cartesia", "voice_id": "sonic-2"},
                )

            assert len(sent_ws_messages) > 0

            # Verify latency log stages
            assert latency_log.exists()
            records = []
            with open(latency_log, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))

            recorded_stages = [r["stage"] for r in records if r["call_id"] == call_id]
            assert "llm_ttft" in recorded_stages
            assert "tts_ttfab" in recorded_stages
            assert "llm" not in recorded_stages
            assert "tts" not in recorded_stages

        finally:
            os.environ.pop("LATENCY_LOG", None)

    @pytest.mark.asyncio
    async def test_turn_loop_fallback_to_blocking_records_llm_and_tts(self, tmp_path):
        latency_log = tmp_path / "latency_fallback.jsonl"
        os.environ["LATENCY_LOG"] = str(latency_log)

        try:
            call_id = f"test_fallback_{uuid4().hex[:6]}"

            async def failing_llm_stream(*args, **kwargs):
                raise RuntimeError("Stream broken")
                yield "never"

            sent_ws_messages = []

            class FakeWebSocket:
                def __init__(self):
                    self.call_count = 0

                async def receive(self):
                    self.call_count += 1
                    if self.call_count == 1:
                        import base64
                        fake_mulaw = b"\xff" * 320
                        payload = {
                            "event": "media",
                            "streamSid": "stream_456",
                            "media": {"payload": base64.b64encode(fake_mulaw).decode()},
                        }
                        return {"type": "websocket.receive", "text": json.dumps(payload)}
                    elif self.call_count == 2:
                        return {"type": "websocket.receive", "text": json.dumps({"event": "stop"})}
                    return {"type": "websocket.disconnect"}

                async def send(self, msg):
                    sent_ws_messages.append(msg)

                async def send_text(self, text):
                    sent_ws_messages.append({"type": "websocket.send", "text": text})

            fake_vad_pcm = b"\x00\x00" * 320
            with patch("app.services.voice_pipeline.VoiceActivityDetector") as mock_vad_cls, \
                 patch("app.services.voice_pipeline._stt_transcribe", new_callable=AsyncMock, return_value="Help me"), \
                 patch("app.services.voice_pipeline.execute_shared_turn_steps", new_callable=AsyncMock) as mock_shared, \
                 patch("app.services.voice_pipeline.llm_service.generate_stream", side_effect=failing_llm_stream), \
                 patch("app.services.voice_pipeline.llm_service.generate", new_callable=AsyncMock, return_value="Blocking fallback response."), \
                 patch("app.services.voice_pipeline._tts_synthesize", new_callable=AsyncMock, return_value=b"blocking_audio_bytes"), \
                 patch("app.services.voice_pipeline._append_turn_to_redis", new_callable=AsyncMock):

                mock_vad_inst = MagicMock()
                mock_vad_inst.process_frame.return_value = fake_vad_pcm
                mock_vad_cls.return_value = mock_vad_inst

                mock_shared.return_value = {
                    "fused_emotion": {"dominant": "neutral"},
                    "text_emotion": None,
                    "audio_emotion": None,
                    "active_tools": [],
                    "turn_prompt": "Assistant prompt",
                    "tts_config": {"voice_provider": "cartesia", "voice_id": "sonic-2"},
                }

                ws = FakeWebSocket()
                await _custom_turn_loop(
                    ws_connection=ws,
                    call_id=call_id,
                    agent_id="agent_1",
                    org_id="org_1",
                    system_prompt="Assistant prompt",
                    api_keys={"groq": "test", "cartesia": "test"},
                    language="en",
                    voice_config={"voice_provider": "cartesia", "voice_id": "sonic-2"},
                )

            assert len(sent_ws_messages) > 0

            # Verify latency log records blocking stage names 'llm' and 'tts'
            assert latency_log.exists()
            records = []
            with open(latency_log, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))

            recorded_stages = [r["stage"] for r in records if r["call_id"] == call_id]
            assert "llm" in recorded_stages
            assert "tts" in recorded_stages
            assert "network_out" in recorded_stages

        finally:
            os.environ.pop("LATENCY_LOG", None)
