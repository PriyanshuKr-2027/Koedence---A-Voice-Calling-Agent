"""
VoCall Real-Time Audio Utilities and Voice Activity Detection (VAD).

Provides:
  - mulaw_to_pcm16: Decodes G.711 mu-law (8 kHz) to signed 16-bit PCM.
  - resample_pcm16: Resamples 16-bit mono PCM between sample rates (e.g., 8 kHz -> 16 kHz).
  - pcm16_to_wav: Wraps raw PCM16 samples in a valid RIFF/WAVE container header.
  - calculate_rms: Computes root-mean-square energy of a PCM16 frame.
  - VoiceActivityDetector: Configurable energy-based VAD for frame buffering and end-of-utterance detection.
"""

from __future__ import annotations

import io
import math
import wave
from typing import List, Optional

try:
    import audioop
except ImportError:
    audioop = None  # type: ignore

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


# ---------------------------------------------------------------------------
# G.711 Mu-law Lookup Table (used as high-speed pure Python fallback)
# ---------------------------------------------------------------------------

def _build_mulaw_table() -> List[int]:
    """Generates the 256-entry lookup table for G.711 mu-law to 16-bit linear PCM."""
    table = []
    for b in range(256):
        inverted = ~b & 0xFF
        sign = inverted & 0x80
        exponent = (inverted >> 4) & 0x07
        mantissa = inverted & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        sample -= 0x84
        table.append(-sample if sign else sample)
    return table

_MULAW_DECODE_TABLE = _build_mulaw_table()


# ---------------------------------------------------------------------------
# Core Audio Conversion Functions
# ---------------------------------------------------------------------------

def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """
    Decodes G.711 mu-law bytes to signed 16-bit linear PCM bytes.
    Returns empty bytes if input is empty.
    """
    if not mulaw_bytes:
        return b""

    if audioop is not None:
        try:
            return audioop.ulaw2lin(mulaw_bytes, 2)
        except Exception:
            pass

    # NumPy / Table fallback
    if np is not None:
        table_arr = np.array(_MULAW_DECODE_TABLE, dtype=np.int16)
        u_arr = np.frombuffer(mulaw_bytes, dtype=np.uint8)
        return table_arr[u_arr].tobytes()

    # Pure Python fallback
    import struct
    samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def resample_pcm16(pcm: bytes, src_hz: int, dst_hz: int) -> bytes:
    """
    Resamples 16-bit signed mono PCM audio from src_hz to dst_hz.
    Returns input unmodified if src_hz == dst_hz or input is empty.
    """
    if not pcm or src_hz == dst_hz:
        return pcm

    if audioop is not None:
        try:
            resampled, _ = audioop.ratecv(pcm, 2, 1, src_hz, dst_hz, None)
            return resampled
        except Exception:
            pass

    # NumPy linear interpolation fallback
    if np is not None:
        samples = np.frombuffer(pcm, dtype=np.int16)
        num_src = len(samples)
        if num_src == 0:
            return b""
        num_dst = int(round(num_src * float(dst_hz) / float(src_hz)))
        if num_dst == 0:
            return b""
        src_indices = np.linspace(0, num_src - 1, num_src)
        dst_indices = np.linspace(0, num_src - 1, num_dst)
        interp_samples = np.interp(dst_indices, src_indices, samples)
        clipped = np.clip(interp_samples, -32768, 32767).astype(np.int16)
        return clipped.tobytes()

    raise RuntimeError("Neither audioop nor numpy is available for PCM resampling")


def pcm16_to_wav(
    pcm: bytes,
    sample_rate: int = 16000,
    num_channels: int = 1,
) -> bytes:
    """
    Encapsulates raw 16-bit linear PCM audio into a standard RIFF/WAVE byte stream.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(2)  # 16-bit PCM = 2 bytes per sample
        wav_file.setframerate(sample_rate)
        if pcm:
            wav_file.writeframes(pcm)
    return buf.getvalue()


def calculate_rms(pcm: bytes) -> float:
    """
    Calculates root-mean-square (RMS) amplitude of a 16-bit PCM chunk.
    Returns 0.0 for empty input.
    """
    if not pcm or len(pcm) < 2:
        return 0.0

    if audioop is not None:
        try:
            return float(audioop.rms(pcm, 2))
        except Exception:
            pass

    if np is not None:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples ** 2)))

    # Pure Python fallback
    import struct
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm[: count * 2])
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / count)


# ---------------------------------------------------------------------------
# Voice Activity Detector (VAD) & Frame Buffer
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    """
    Energy-based Voice Activity Detector for telephone & webcall audio streaming.

    Buffers incoming 20 ms frames and detects:
      - Speech start: after N consecutive voiced frames (start_voiced_frames)
      - Speech end: after M ms of continuous silence (silence_duration_ms)
      - Maximum utterance length: forces emission if utterance exceeds max_utterance_ms

    Usage:
        vad = VoiceActivityDetector(sample_rate=8000, energy_threshold=400.0)
        for frame in audio_frames:
            utterance = vad.process_frame(frame)
            if utterance is not None:
                # Handle complete spoken utterance
    """

    def __init__(
        self,
        sample_rate: int = 8000,
        frame_duration_ms: int = 20,
        energy_threshold: float = 400.0,
        start_voiced_frames: int = 3,
        silence_duration_ms: int = 700,
        max_utterance_ms: int = 15000,
        min_utterance_ms: int = 120,
        pre_speech_frames: int = 5,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.energy_threshold = energy_threshold
        self.start_voiced_frames = start_voiced_frames
        self.silence_duration_ms = silence_duration_ms
        self.max_utterance_ms = max_utterance_ms
        self.min_utterance_ms = min_utterance_ms
        self.pre_speech_limit = pre_speech_frames

        # State
        self.is_speaking: bool = False
        self.consecutive_voiced: int = 0
        self.consecutive_silence_ms: int = 0
        self.current_utterance_ms: int = 0

        # Frame buffers
        self.pre_speech_buffer: List[bytes] = []
        self.utterance_buffer: List[bytes] = []

    def reset(self) -> None:
        """Resets detector state and internal frame buffers."""
        self.is_speaking = False
        self.consecutive_voiced = 0
        self.consecutive_silence_ms = 0
        self.current_utterance_ms = 0
        self.pre_speech_buffer.clear()
        self.utterance_buffer.clear()

    def process_frame(self, pcm_frame: bytes) -> Optional[bytes]:
        """
        Processes a single PCM16 audio frame (typically 20 ms).

        Returns:
            bytes: Complete utterance PCM audio if end-of-utterance was detected.
            None: If utterance is still continuing or caller is silent.
        """
        if not pcm_frame:
            return None

        energy = calculate_rms(pcm_frame)
        is_voiced = energy >= self.energy_threshold

        if not self.is_speaking:
            if is_voiced:
                self.consecutive_voiced += 1
                if self.consecutive_voiced >= self.start_voiced_frames:
                    # Transition to active speech
                    self.is_speaking = True
                    self.utterance_buffer = list(self.pre_speech_buffer)
                    self.utterance_buffer.append(pcm_frame)
                    self.current_utterance_ms = len(self.utterance_buffer) * self.frame_duration_ms
                    self.consecutive_silence_ms = 0
                    self.pre_speech_buffer.clear()
            else:
                self.consecutive_voiced = 0
                self.pre_speech_buffer.append(pcm_frame)
                if len(self.pre_speech_buffer) > self.pre_speech_limit:
                    self.pre_speech_buffer.pop(0)
            return None

        else:
            # Active speech mode
            self.utterance_buffer.append(pcm_frame)
            self.current_utterance_ms += self.frame_duration_ms

            if is_voiced:
                self.consecutive_silence_ms = 0
            else:
                self.consecutive_silence_ms += self.frame_duration_ms

            # Check termination criteria
            silence_timeout = self.consecutive_silence_ms >= self.silence_duration_ms
            max_duration_reached = self.current_utterance_ms >= self.max_utterance_ms

            if silence_timeout or max_duration_reached:
                # End of utterance detected
                pcm_audio = b"".join(self.utterance_buffer)
                total_duration = self.current_utterance_ms
                self.reset()

                # Filter out short transient noises below minimum threshold
                if total_duration >= self.min_utterance_ms:
                    return pcm_audio
                return None

        return None

    def flush(self) -> Optional[bytes]:
        """
        Flushes and returns any remaining buffered speech when a call ends.
        """
        if self.is_speaking and self.utterance_buffer:
            pcm_audio = b"".join(self.utterance_buffer)
            total_duration = self.current_utterance_ms
            self.reset()
            if total_duration >= self.min_utterance_ms:
                return pcm_audio
        self.reset()
        return None
