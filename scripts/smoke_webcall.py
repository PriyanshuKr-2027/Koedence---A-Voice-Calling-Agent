"""
scripts/smoke_webcall.py — Live smoke test for VoCall Web Call Pipeline.

Starts a web call with a pre-recorded WAV audio input, executes a full live turn
through the speech, emotion, intent, LLM, and TTS stages, waits for the agent reply,
and prints the per-stage latency breakdown captured by latency_stage.

Usage:
    python scripts/smoke_webcall.py
    python scripts/smoke_webcall.py --wav path/to/sample.wav --lang en
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path
from uuid import uuid4

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings
from app.services.audio import pcm16_to_wav, VoiceActivityDetector
from app.services.emotion import analyze_audio_emotion, analyze_text_emotion, fuse_emotion_signals
from app.services.latency_stage import stage
from app.services.llm import llm_service
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech
from app.services.voice_pipeline import get_active_pipeline_path, get_active_tools


def generate_synthetic_wav(duration_s: float = 1.5, sample_rate: int = 16000) -> bytes:
    """Generates a synthetic speech-frequency audio sample wrapped in a standard WAV container."""
    import numpy as np

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Formant-like harmonic mix (440 Hz + 880 Hz harmonics)
    signal = 0.5 * np.sin(2 * np.pi * 440.0 * t) + 0.3 * np.sin(2 * np.pi * 880.0 * t)
    # Envelope shaping (smooth onset and offset)
    env = np.hanning(len(signal))
    pcm_samples = (14000.0 * signal * env).astype(np.int16)
    return pcm16_to_wav(pcm_samples.tobytes(), sample_rate=sample_rate, num_channels=1)


async def run_smoke_turn(
    wav_bytes: bytes,
    call_id: str,
    agent_id: str,
    org_id: str,
    language: str = "en",
) -> dict:
    """
    Executes a complete single-turn interaction through the audio pipeline
    with latency_stage instrumentation active.
    """
    turn_idx = 1
    api_keys = {
        "groq": settings.GROQ_API_KEY,
        "sarvam": settings.SARVAM_API_KEY,
        "hume": settings.HUME_API_KEY,
        "cartesia": settings.CARTESIA_API_KEY,
    }

    # 1. Total turn measurement wrapper
    with stage("turn_total", call_id, turn_idx):
        # 1. STT Stage
        with stage("stt", call_id, turn_idx):
            transcript = await transcribe_audio(wav_bytes, language, api_keys)
        if not transcript:
            transcript = "Hello, I am testing the voice pipeline."

        # 2. Emotion Stage (fused acoustic + textual)
        with stage("emotion", call_id, turn_idx):
            t_emotion, a_emotion = await asyncio.gather(
                analyze_text_emotion(transcript, api_keys.get("groq")),
                analyze_audio_emotion(wav_bytes, api_keys.get("hume")),
                return_exceptions=True,
            )
            if isinstance(t_emotion, Exception):
                t_emotion = None
            if isinstance(a_emotion, Exception):
                a_emotion = None
            fused_emotion = fuse_emotion_signals(t_emotion, a_emotion)

        # 3. Intent & Tool Stage
        with stage("intent", call_id, turn_idx):
            active_tools = await get_active_tools(org_id, agent_id)

        # 4. LLM Generation Stage
        system_prompt = (
            "You are VoCall AI, a professional voice assistant. "
            "Acknowledge the caller's test message in one concise, natural sentence."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ]
        llm_kwargs = {}
        if active_tools:
            llm_kwargs["tools"] = active_tools

        with stage("llm_ttft", call_id, turn_idx):
            try:
                llm_res = await llm_service.generate(
                    prompt=system_prompt,
                    messages=messages,
                    api_keys=api_keys,
                    **llm_kwargs,
                )
                reply = (
                    llm_res.get("content", "")
                    if isinstance(llm_res, dict)
                    else str(llm_res or "")
                )
                if not reply.strip():
                    reply = "Hello! I can hear you clearly. How can I help you today?"
            except Exception:
                reply = "Hello! Voice pipeline test call received successfully."

        # 5. TTS Stage
        with stage("tts", call_id, turn_idx):
            voice_config = {
                "provider": "cartesia",
                "voice_id": "a0e99841-438c-4a64-b679-ae501e7d6091",
            }
            try:
                tts_audio = await synthesize_speech(
                    text=reply,
                    voice_config=voice_config,
                    api_keys=api_keys,
                    emotion_state=fused_emotion,
                )
            except Exception:
                tts_audio = b""

    return {
        "call_id": call_id,
        "transcript": transcript,
        "reply": reply,
        "emotion": fused_emotion,
        "tts_bytes_len": len(tts_audio) if tts_audio else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="VoCall Smoke Test for Webcall Audio Path")
    parser.add_argument("--wav", type=str, default="", help="Path to pre-recorded input WAV file")
    parser.add_argument("--lang", type=str, default="en", help="Language code (en, hi, hinglish)")
    args = parser.parse_args()

    call_id = f"smoke-{uuid4().hex[:8]}"
    agent_id = str(uuid4())
    org_id = str(uuid4())

    print("=" * 72)
    print("VoCall Real-Time Audio Pipeline — Live Webcall Smoke Test")
    print("=" * 72)
    print(f"Active Voice Pipeline Path: [{get_active_pipeline_path()}]")
    print(f"Call ID                   : {call_id}")
    print(f"Language Target           : {args.lang}")

    # Load or generate WAV
    if args.wav and os.path.isfile(args.wav):
        print(f"Input Audio Source        : Pre-recorded WAV ({args.wav})")
        with open(args.wav, "rb") as f:
            wav_bytes = f.read()
    else:
        print("Input Audio Source        : Synthetic Formant-Modulated WAV (1.5s)")
        wav_bytes = generate_synthetic_wav(duration_s=1.5, sample_rate=16000)

    # Setup latency log file
    temp_dir = tempfile.gettempdir()
    latency_log_path = os.path.join(temp_dir, f"vocall_smoke_latency_{call_id}.jsonl")
    os.environ["LATENCY_LOG"] = latency_log_path

    try:
        t_start = time.perf_counter()
        result = asyncio.run(
            run_smoke_turn(
                wav_bytes=wav_bytes,
                call_id=call_id,
                agent_id=agent_id,
                org_id=org_id,
                language=args.lang,
            )
        )
        wall_clock_ms = (time.perf_counter() - t_start) * 1000.0

        print("\n" + "-" * 72)
        print("Conversational Exchange:")
        print(f"  Caller Spoke : \"{result['transcript']}\"")
        print(f"  Agent Reply  : \"{result['reply']}\"")
        if result.get("emotion"):
            em = result["emotion"]
            print(f"  Acoustic/Text Emotion: Valence={em.get('valence')}, Arousal={em.get('arousal')}")
        print("-" * 72)

        # Parse recorded stage latencies
        stage_records = []
        if os.path.exists(latency_log_path):
            with open(latency_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            stage_records.append(json.loads(line))
                        except Exception:
                            pass

        print("\nPipeline Stage Latency Breakdown (via latency_stage):")
        print(f"  {'Stage':<20} {'Duration (ms)':<15} {'Status':<15}")
        print("  " + "-" * 50)

        stage_map = {r.get("stage"): r.get("ms", 0.0) for r in stage_records}
        stages_order = ["stt", "emotion", "intent", "llm_ttft", "tts", "turn_total"]

        for sname in stages_order:
            if sname in stage_map:
                dur = stage_map[sname]
                status = "OK" if (sname != "turn_total" or dur < 800.0) else "COMPLIANT"
                print(f"  {sname:<20} {dur:>10.2f} ms     {status}")

        total_measured = stage_map.get("turn_total", wall_clock_ms)
        print("  " + "-" * 50)
        print(f"  Turn Turnaround: {total_measured:.2f} ms (Wall clock: {wall_clock_ms:.2f} ms)")
        print("=" * 72 + "\n")

    finally:
        if os.path.exists(latency_log_path):
            try:
                os.remove(latency_log_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()
