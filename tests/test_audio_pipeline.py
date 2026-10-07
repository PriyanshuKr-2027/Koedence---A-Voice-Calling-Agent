"""
tests/test_audio_pipeline.py — Tests for audio conversion, VAD, and real-time frame buffering.

Verifies:
1. A 440 Hz tone encoded as mu-law at 8 kHz decodes to ~440 Hz at 16 kHz (FFT peak detection).
2. WAV header is valid, structurally standard, and parseable by standard wave reader.
3. Empty input handled gracefully across all converters without throwing exceptions.
4. VAD splits two spoken bursts separated by silence into exactly two utterances.
5. A 3-second synthetic utterance produces exactly one STT call, not 150.
6. Pipeline startup logs the active pipeline path.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.audio import (
    calculate_rms,
    mulaw_to_pcm16,
    pcm16_to_wav,
    resample_pcm16,
    VoiceActivityDetector,
)
from app.services.voice_pipeline import get_active_pipeline_path, _minimal_echo_loop


# ---------------------------------------------------------------------------
# Test 1: 440 Hz tone G.711 mu-law decode + resample + FFT
# ---------------------------------------------------------------------------

def test_mulaw_decode_resample_fft():
    """
    Generate a 440 Hz sine wave at 8 kHz, encode to G.711 mu-law, decode to PCM16,
    resample to 16 kHz, and verify dominant frequency is ~440 Hz using FFT.
    """
    src_rate = 8000
    dst_rate = 16000
    duration_s = 1.0
    freq_target = 440.0

    t = np.linspace(0, duration_s, int(src_rate * duration_s), endpoint=False)
    # Generate 16-bit linear PCM sine wave
    amplitude = 16000  # half full-scale
    pcm_samples = (amplitude * np.sin(2 * np.pi * freq_target * t)).astype(np.int16)
    pcm_bytes = pcm_samples.tobytes()

    # Encode to G.711 mu-law
    try:
        import audioop
        mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
    except Exception:
        # Software fallback encoding
        BIAS = 0x84
        CLIP = 32635
        mulaw_list = []
        for s in pcm_samples:
            sign = 0x80 if s < 0 else 0x00
            val = min(abs(int(s)), CLIP) + BIAS
            exponent = 7
            for exp in range(7, -1, -1):
                if val >= (1 << (exp + 7)):
                    exponent = exp
                    break
            mantissa = (val >> (exponent + 3)) & 0x0F
            mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
            mulaw_list.append(mulaw_byte)
        mulaw_bytes = bytes(mulaw_list)

    # 1. Decode mu-law to PCM16 at 8 kHz
    decoded_pcm8k = mulaw_to_pcm16(mulaw_bytes)
    assert len(decoded_pcm8k) == len(pcm_bytes)

    # 2. Resample 8 kHz to 16 kHz (allows 1-sample filter edge variance)
    resampled_pcm16k = resample_pcm16(decoded_pcm8k, src_hz=src_rate, dst_hz=dst_rate)
    assert abs(len(resampled_pcm16k) - len(pcm_bytes) * 2) <= 4

    # 3. FFT on 16 kHz resampled audio
    samples_16k = np.frombuffer(resampled_pcm16k, dtype=np.int16).astype(np.float64)
    fft_vals = np.abs(np.fft.rfft(samples_16k))
    freqs = np.fft.rfftfreq(len(samples_16k), 1.0 / dst_rate)

    peak_freq = freqs[np.argmax(fft_vals)]
    # FFT resolution with 16000 points is 1 Hz; verify within 3 Hz
    assert abs(peak_freq - freq_target) < 3.0, f"Expected ~440 Hz, got {peak_freq} Hz"


# ---------------------------------------------------------------------------
# Test 2: Valid WAV header structure
# ---------------------------------------------------------------------------

def test_wav_header_valid():
    """Verify pcm16_to_wav generates a standard, valid RIFF/WAVE header."""
    pcm = b"\x00\x00\x10\x00\x20\x00" * 100  # 600 bytes = 300 samples
    wav_bytes = pcm16_to_wav(pcm, sample_rate=16000, num_channels=1)

    assert wav_bytes.startswith(b"RIFF")
    assert wav_bytes[8:12] == b"WAVE"
    assert len(wav_bytes) == len(pcm) + 44

    # Verify standard wave reader can parse header parameters cleanly
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == len(pcm) // 2


# ---------------------------------------------------------------------------
# Test 3: Empty input handling
# ---------------------------------------------------------------------------

def test_empty_input_handled():
    """Verify converters and VAD handle empty byte arrays safely."""
    assert mulaw_to_pcm16(b"") == b""
    assert resample_pcm16(b"", 8000, 16000) == b""

    empty_wav = pcm16_to_wav(b"", 16000, 1)
    assert len(empty_wav) == 44  # Valid empty WAV container header
    with wave.open(io.BytesIO(empty_wav), "rb") as wf:
        assert wf.getnframes() == 0

    assert calculate_rms(b"") == 0.0

    vad = VoiceActivityDetector()
    assert vad.process_frame(b"") is None
    assert vad.flush() is None


# ---------------------------------------------------------------------------
# Test 4: VAD splits two spoken bursts separated by silence
# ---------------------------------------------------------------------------

def test_vad_splits_two_spoken_bursts():
    """
    Simulate two spoken bursts separated by silence.
    The VAD must emit exactly two distinct utterances.
    """
    vad = VoiceActivityDetector(
        sample_rate=8000,
        frame_duration_ms=20,
        energy_threshold=400.0,
        start_voiced_frames=3,
        silence_duration_ms=600,   # 600 ms = 30 silent frames
        min_utterance_ms=100,
    )

    # 20 ms at 8000 Hz = 160 samples = 320 bytes of PCM16
    t = np.linspace(0, 0.02, 160, endpoint=False)
    voiced_sample = (10000.0 * np.sin(2 * np.pi * 440.0 * t)).astype(np.int16).tobytes()
    silent_sample = np.zeros(160, dtype=np.int16).tobytes()

    utterances = []

    # Burst 1: 20 voiced frames (400 ms)
    for _ in range(20):
        out = vad.process_frame(voiced_sample)
        if out is not None:
            utterances.append(out)

    # Silence 1: 35 silent frames (700 ms > 600 ms timeout) -> should emit burst 1
    for _ in range(35):
        out = vad.process_frame(silent_sample)
        if out is not None:
            utterances.append(out)

    assert len(utterances) == 1, "First utterance should be emitted after silence"

    # Burst 2: 25 voiced frames (500 ms)
    for _ in range(25):
        out = vad.process_frame(voiced_sample)
        if out is not None:
            utterances.append(out)

    # Silence 2: 35 silent frames (700 ms > 600 ms timeout) -> should emit burst 2
    for _ in range(35):
        out = vad.process_frame(silent_sample)
        if out is not None:
            utterances.append(out)

    assert len(utterances) == 2, "Second utterance should be emitted after second silence"


# ---------------------------------------------------------------------------
# Test 5: 3-second synthetic utterance produces one STT call, not 150
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_second_synthetic_utterance_produces_one_stt_call():
    """
    A 3-second utterance sent as 150 20ms frames must be buffered by VAD
    and result in exactly ONE STT call, not 150.
    """
    # 1. First test VAD directly
    vad = VoiceActivityDetector(
        sample_rate=8000,
        frame_duration_ms=20,
        energy_threshold=400.0,
        silence_duration_ms=600,
    )

    t = np.linspace(0, 0.02, 160, endpoint=False)
    voiced_pcm = (12000.0 * np.sin(2 * np.pi * 440.0 * t)).astype(np.int16).tobytes()
    silent_pcm = np.zeros(160, dtype=np.int16).tobytes()

    try:
        import audioop
        voiced_mulaw = audioop.lin2ulaw(voiced_pcm, 2)
        silent_mulaw = audioop.lin2ulaw(silent_pcm, 2)
    except Exception:
        voiced_mulaw = bytes([128] * 160)
        silent_mulaw = bytes([255] * 160)

    emitted_utterances = []
    # 150 voiced frames = 3000 ms
    for _ in range(150):
        out = vad.process_frame(voiced_pcm)
        if out is not None:
            emitted_utterances.append(out)

    assert len(emitted_utterances) == 0, "Should not emit while speech is actively ongoing"

    # Now 35 silent frames (700 ms > 600 ms silence timeout)
    for _ in range(35):
        out = vad.process_frame(silent_pcm)
        if out is not None:
            emitted_utterances.append(out)

    assert len(emitted_utterances) == 1, "Must emit exactly ONE utterance at the end of speech"

    # 2. Test through _minimal_echo_loop with WebSocket stream
    # Construct sequence of WebSocket messages:
    # 150 media events of voiced audio, followed by 35 media events of silence, then disconnect
    voiced_b64 = base64.b64encode(voiced_mulaw).decode()
    silent_b64 = base64.b64encode(silent_mulaw).decode()

    ws_messages = []
    for _ in range(150):
        ws_messages.append({
            "type": "websocket.receive",
            "text": json.dumps({"event": "media", "media": {"payload": voiced_b64}}),
        })
    for _ in range(35):
        ws_messages.append({
            "type": "websocket.receive",
            "text": json.dumps({"event": "media", "media": {"payload": silent_b64}}),
        })
    ws_messages.append({"type": "websocket.disconnect"})

    class MockWebSocket:
        def __init__(self, msgs):
            self.msgs = list(msgs)

        async def receive(self):
            if self.msgs:
                return self.msgs.pop(0)
            return {"type": "websocket.disconnect"}

        async def send_text(self, text):
            pass

    mock_ws = MockWebSocket(ws_messages)
    stt_mock = AsyncMock(return_value="Hello VoCall testing")
    llm_mock = AsyncMock(return_value="Hi there, I heard you clearly.")

    with patch("app.services.voice_pipeline._stt_transcribe", stt_mock), \
         patch("app.services.llm.llm_service.generate", llm_mock), \
         patch("app.services.intent.detector.detect", AsyncMock(return_value={"intent": "unknown", "confidence": 0.0})), \
         patch("app.services.intent.slot_manager.merge_slots", AsyncMock(return_value={})), \
         patch("app.services.voice_pipeline.short_term.append_turn", AsyncMock()), \
         patch("app.services.voice_pipeline.short_term.append_emotion_event", AsyncMock()), \
         patch("app.services.voice_pipeline.analyze_text_emotion", AsyncMock(return_value={"valence": 0.5})), \
         patch("app.services.voice_pipeline.analyze_audio_emotion", AsyncMock(return_value={"valence": 0.5})), \
         patch("app.services.voice_pipeline.synthesize_speech", AsyncMock(return_value=b"fake_audio")):

        await _minimal_echo_loop(
            ws_connection=mock_ws,
            call_id="test_vad_call",
            agent_id="test_agent",
            org_id="test_org",
            system_prompt="Test assistant",
            api_keys={},
            language="en",
            voice_config={},
        )

    # Key assertion: STT was called EXACTLY ONCE, not 150 times!
    assert stt_mock.call_count == 1, f"Expected 1 STT call, got {stt_mock.call_count}"
    assert llm_mock.call_count == 1


# ---------------------------------------------------------------------------
# Test 6: Startup pipeline path reporter
# ---------------------------------------------------------------------------

def test_pipeline_path_reporter():
    """Verify get_active_pipeline_path returns expected category ('custom' or 'pipecat')."""
    path = get_active_pipeline_path()
    assert path in ("custom", "pipecat")
