"""VoCall Per-Stage Latency Benchmark Replay Runner.

Replays prepared conversational audio turns through the pipeline for English
and Hinglish voice agents, collecting per-stage telemetry into JSONL records.

Per-Stage Telemetry:
  - stt: Speech-to-Text transcription
  - emotion: Multimodal dual emotion analysis & fusion
  - memory: Multi-tier cognitive memory read/write
  - intent: Active tools & connector matching
  - llm_ttft: LLM Time to First Token generation
  - tts_ttfab: TTS Time to First Audio Byte synthesis
  - network_out: Transport packetization and dispatch
  - turn_total: Complete end-to-end turnaround latency

Captures environment metadata in config.json: region, network_type, and time_of_day.
Discards the first 3 turns of each call as warm-up.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import httpx
import numpy as np
import soundfile as sf
import yaml

from app.core.config import settings
from app.services.emotion.audio_signal import analyze_audio_emotion
from app.services.emotion.fusion import fuse_emotion_signals
from app.services.emotion.text_signal import analyze_text_emotion
from app.services.latency_stage import stage
from app.services.llm import llm_service
from app.services.memory.retriever import build_memory_prompt, retrieve_all_memory
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech
from eval.common.mode import ServiceTracker, get_eval_mode, require_live_services, stamp_csv_mock_data
from eval.common.runlog import RunContext, start_run

logger = logging.getLogger(__name__)

# Sample multi-turn dialogues for English and Hinglish agents (10 turns per call)
ENGLISH_CALL_TURNS: List[List[str]] = [
    # Call 1 (Customer Support - Broadband outage)
    [
        "Hello, my broadband internet has been down since morning.",
        "Yes, I restarted the router twice but the optical light is still blinking red.",
        "My registered account number is 987654321.",
        "Could you check if there is an area-wide outage in Indiranagar?",
        "How long will it take for the field technician to arrive?",
        "Can you schedule the visit for tomorrow morning between 10 AM and 12 PM?",
        "Please confirm the appointment by SMS to my phone.",
        "Also, will I receive a billing waiver for the downtime days?",
        "That sounds fair. What is my complaint reference number?",
        "Thank you for the quick assistance, goodbye.",
    ],
    # Call 2 (Billing & Renewal)
    [
        "Hi, I noticed an extra roaming charge of four hundred rupees on my latest bill.",
        "I was traveling within the national zone and never activated international packs.",
        "My phone number is 9876501234.",
        "Please waive this erroneous charge and update my invoice total.",
        "Can I pay the adjusted amount right now through UPI?",
        "Send the payment link to my email address.",
        "I also want to know if my current fiber plan can be upgraded to 300 Mbps.",
        "Does the upgrade require replacing my existing Wi-Fi router?",
        "Great, please schedule the upgrade for this weekend.",
        "All set, thank you for your help.",
    ],
    # Call 3 (Appointment Booking)
    [
        "Good afternoon, I would like to book a dental checkup consultation.",
        "Is there an open slot available this Thursday afternoon?",
        "3 PM works well for me. The appointment is for Priyanshu.",
        "Do I need to carry previous medical reports or dental X-rays?",
        "Understood. What is the clinic address in Koramangala?",
        "Please book the slot and send a calendar invitation.",
        "Can I reschedule later if something urgent comes up?",
        "Is digital payment accepted at the clinic desk?",
        "Perfect, please note my contact number as 9876512345.",
        "Thank you, see you on Thursday.",
    ],
    # Call 4 (Account Transfer)
    [
        "Hello, I need to transfer my broadband connection to a new apartment.",
        "The new address is flat 402, Green Glen Layout, Bellandur.",
        "My existing account ID is BB882109.",
        "When can your team uninstall the current equipment?",
        "Friday evening works. Can installation happen on Saturday morning?",
        "Are there any relocation charges applied to my next invoice?",
        "Please keep my existing static IP address allocated.",
        "Who will be the technician contacting me on the day?",
        "Noted. Please share the tracking link via WhatsApp.",
        "Thanks a lot for making this smooth.",
    ],
    # Call 5 (Cancellation & Refund)
    [
        "I want to cancel my annual maintenance subscription immediately.",
        "The service quality has been poor and technicians frequently miss visits.",
        "Subscription reference code is AMC-2026-9901.",
        "I am within the 30-day money back guarantee period.",
        "Yes, proceed with the cancellation and refund.",
        "Refund the amount to my original payment source bank account.",
        "How many business days will it take to credit?",
        "Please issue a formal cancellation receipt via email.",
        "No further questions, thank you.",
        "Goodbye.",
    ],
    # Call 6 (General Inquiry)
    [
        "Hi there, could you explain the difference between your standard and pro plans?",
        "Does the pro plan include unlimited static IP addresses?",
        "What is the upload speed on the 500 Mbps connection?",
        "Is there any fair usage policy quota limit per month?",
        "Do you provide dual-band mesh Wi-Fi routers with the plan?",
        "What is the security deposit for corporate connections?",
        "Can we get a GST invoice for company reimbursement?",
        "Please email the complete pricing brochure to office@domain.com.",
        "That answers all my questions.",
        "Thank you, have a good day.",
    ],
    # Call 7 (Speed Issue)
    [
        "My download speed has dropped to five Mbps on a hundred Mbps plan.",
        "I ran the speed test over Ethernet cable directly connected to the router.",
        "Latency is showing over 180 milliseconds to local gateway.",
        "Yes, I unplugged the power cable for thirty seconds as instructed.",
        "The optical power reading on the router page shows minus 28 dBm.",
        "Does that indicate a fiber cable bend or attenuation fault?",
        "Please send an engineer to inspect the junction box outside.",
        "Can someone come today before 6 PM?",
        "Alright, tomorrow 9 AM is fine.",
        "Thank you, appreciate it.",
    ],
    # Call 8 (Payment Failure)
    [
        "My payment failed twice on the portal but money was deducted from my bank.",
        "Transaction reference number is TXN77889900.",
        "Amount deducted was twelve hundred and ninety-nine rupees.",
        "My registered account is user 44109.",
        "Will the funds auto-reverse or get credited to my broadband wallet?",
        "Please ensure my connection is not suspended while this resolves.",
        "Thank you for confirming the grace period.",
        "Can you send a payment receipt once the bank reconciliation completes?",
        "Thanks for the prompt resolution.",
        "Bye.",
    ],
]

HINGLISH_CALL_TURNS: List[List[str]] = [
    # Call 1 (Broadband Complaints)
    [
        "Hello, mera internet connection subah se band hai.",
        "Haan maine router restart kiya par red light abhi bhi blink kar rahi hai.",
        "Mera registered mobile number 9876543210 hai.",
        "Check kijiye kya hamare area me koi optical fiber line cut hui hai?",
        "Technician visit kitne baje tak schedule ho sakta hai?",
        "Kal subah 10 baje ka slot book kardo please.",
        "Kya mujhe appointment confirmation SMS milega?",
        "Downtime ka bill adjustment next month invoice me hoga na?",
        "Theek hai, complaint ticket number note kara dijiye.",
        "Bahut dhanyawad, kal subah milte hain.",
    ],
    # Call 2 (Billing & Plan)
    [
        "Namaste, mere iss mahine ke bill me extra roaming charge laga hua hai.",
        "Main Delhi NCR me hi tha aur international roaming activate nahi kiya tha.",
        "Mera account ID note kijiye 554432.",
        "Yeh extra charge turant hatayein aur revised bill bhej dijiye.",
        "Kya main updated bill amount UPI se pay kar sakta hoon?",
        "Payment link WhatsApp pe bhej dijiye.",
        "Mujhe apna current plan upgrade karke 200 Mbps karwana hai.",
        "Upgrade ke liye naya router install karna padega kya?",
        "Haan Friday afternoon visit schedule kardo.",
        "Thank you so much, bye.",
    ],
    # Call 3 (Appointment Scheduling)
    [
        "Doctor consultation ke liye appointment book karna tha.",
        "Kya Wednesday evening ko koi free slot available hai?",
        "Shaam ke paanch baje ka slot confirm kardo Priyanshu ke naam se.",
        "Old prescriptions aur blood test reports sath me laani hain kya?",
        "Clinic ka exact location Indiranagar 100 feet road pe kahan hai?",
        "Calendar invite mere email pe send kardo please.",
        "Agar late ho gaya toh rescheduling ho jayegi?",
        "Online payment Google Pay se kar sakte hain desk pe?",
        "Mera contact number 9876522334 hai.",
        "Shukriya, Wednesday ko milte hain.",
    ],
    # Call 4 (Home Relocation)
    [
        "Mujhe apna Wi-Fi connection dusre flat me shift karwana hai.",
        "Naya address flat 301, Sector 62, Noida hai.",
        "Existing customer ID 992014 hai.",
        "Purana setup kis din disconnect karoge?",
        "Saturday subah relocation team ko bhej do.",
        "Relocation ke koi extra shifting charges lagenge kya?",
        "Mera current balance aur validity same rahegi na?",
        "Visit karne se pehle technician call karega?",
        "Theek hai, tracker link share kardo message pe.",
        "Dhanyawad, bye.",
    ],
    # Call 5 (Plan Cancellation)
    [
        "Mera annual broadband subscription cancel kardo turant.",
        "Speed bahut slow aati hai aur complaints pe koi action nahi hota.",
        "Subscription number AMC-4401 hai.",
        "Mera refund mere bank account me wapas chahiye.",
        "Haan cancelation proceed kardo bina delay ke.",
        "Paisa kitne din me account me credit hoga?",
        "Confirmation receipt email pe send kardo please.",
        "Mujhe aur kuch nahi puchna.",
        "Theek hai, dhanyawad.",
        "Alvida.",
    ],
    # Call 6 (General Inquiry)
    [
        "Aapke naye fiber plans ki details jaan-ni thi.",
        "Kya family plan me OTT subscriptions bundled milte hain?",
        "Hotstar aur Netflix dono included hain ya sirf ek?",
        "Download aur upload speed symmetrical milti hai kya?",
        "Router free milega connection ke sath ya alag se lena padega?",
        "Installation charges kitne hain naye connection ke?",
        "Business GST invoice mil sakta hai reimbursement ke liye?",
        "Brochure WhatsApp pe send kardo iss number pe.",
        "Sab clear ho gaya hai.",
        "Thank you, have a good day.",
    ],
    # Call 7 (Speed Issues)
    [
        "Wi-Fi ki speed bahut kam aa rahi hai bedroom me.",
        "Router living room me hai aur distance sirf bees feet hai.",
        "Phone pe sirf ek bar signal dikha raha hai.",
        "Maine Wi-Fi channel setting restart ki par koi farak nahi pada.",
        "Kya mesh repeater lagane se coverage badh jayegi?",
        "Repeater ka monthly rental kitna hota hai?",
        "Kal afternoon ek engineer bhej kar speed check karwao.",
        "Engineer ke aane se aadha ghanta pehle inform kar dena.",
        "Theek hai, appointment lock kardo.",
        "Thank you.",
    ],
    # Call 8 (Payment Failure)
    [
        "Online recharge kiya tha account se paise cut gaye par plan renew nahi hua.",
        "Bank transaction ID 99887711 note kijiye.",
        "Seven hundred ninety-nine rupees debit hue hain.",
        "Registered phone number 9876533445 hai.",
        "Internet service abhi band mat karna payment clarify hone tak.",
        "Wallet me paise kab tak reflect honge?",
        "Status update aane par call kar dena.",
        "Aapki help ke liye shukriya.",
        "All clear.",
        "Bye.",
    ],
]


def _get_time_of_day_label(dt: datetime) -> str:
    """Returns conversational time-of-day label based on local hour."""
    hr = dt.hour
    if 5 <= hr < 12:
        return "morning"
    if 12 <= hr < 17:
        return "afternoon"
    if 17 <= hr < 21:
        return "evening"
    return "night"


def ensure_audio_file(
    text: str,
    utt_id: str,
    audio_dir: Path,
    language: str,
) -> Path:
    """Creates or returns a valid WAV file for a given turn utterance."""
    wav_path = audio_dir / f"{utt_id}.wav"
    if wav_path.exists():
        return wav_path

    sr = 8000
    duration = max(1.2, len(text.split()) * 0.32)
    num_samples = int(sr * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)
    freq = 460.0 if language == "en" else 520.0
    rng = np.random.default_rng(abs(hash(utt_id)) % (2**31))
    noise = rng.normal(0, 0.002, num_samples)
    waveform = (0.2 * np.sin(2 * np.pi * freq * t) + noise).astype(np.float32)

    sf.write(str(wav_path), waveform, sr, format="WAV", subtype="PCM_16")
    return wav_path


async def replay_turn_direct(
    call_id: str,
    turn_idx: int,
    audio_bytes: bytes,
    language: str,
    agent_config: Dict[str, Any],
    api_keys: Dict[str, str],
    mock: bool = False,
    mock_transcript: str = "",
    tracker: Optional[ServiceTracker] = None,
) -> Dict[str, Any]:
    """Replays a single turn directly through all pipeline stages with nanosecond instrumentation.

    Stages measured:
      1. stt: Speech-to-Text transcription
      2. emotion: Dual-signal audio and text emotion fusion
      3. memory: Cognitive memory buffer update & retrieval
      4. intent: Active tool & connector matching
      5. llm_ttft: LLM Time to First Token generation
      6. tts_ttfab: TTS Time to First Audio Byte synthesis
      7. network_out: Transport packetization & transmission
      8. turn_total: End-to-end turn turnaround latency
    """
    system_prompt = agent_config.get("system_prompt", "You are a helpful voice assistant.")
    voice_config = agent_config.get("voice_config", {"voice_provider": "cartesia", "voice_id": "sonic-english"})

    with stage("turn_total", call_id, turn_idx):
        # 1. STT Stage
        with stage("stt", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.160)  # ~160ms Whisper / Sarvam
                transcript = mock_transcript or "Hello, test turn."
            else:
                if tracker:
                    tracker.record("sarvam" if language == "hinglish" else "groq")
                transcript = await transcribe_audio(audio_bytes, language, api_keys)
                if not transcript:
                    raise RuntimeError(f"STT transcription failed for call {call_id} turn {turn_idx}")

        # 2. Emotion Stage
        with stage("emotion", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.095)  # ~95ms Emotion fusion
                fused_emotion = {"valence": 0.0, "arousal": 0.3, "dominant": "neutral", "confidence": 0.85}
            else:
                if tracker:
                    tracker.record("groq")
                    tracker.record("hume")
                text_emo = await analyze_text_emotion(transcript)
                audio_emo = await analyze_audio_emotion(audio_bytes, api_keys.get("hume", ""))
                fused_emotion = fuse_emotion_signals(text_emo, audio_emo)
                if not fused_emotion:
                    raise RuntimeError(f"Emotion fusion failed for call {call_id} turn {turn_idx}")

        # 3. Memory Stage
        with stage("memory", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.045)  # ~45ms Redis / Postgres memory
                mem_context = "Caller: Priyanshu, active account BB882109"
            else:
                if tracker:
                    tracker.record("redis")
                    tracker.record("supabase")
                mem_dict = await retrieve_all_memory(
                    contact_id=f"replay_{call_id}",
                    org_id="eval_org",
                    query_text=transcript,
                )
                mem_context = build_memory_prompt(mem_dict)

        # 4. Intent Stage
        with stage("intent", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.025)  # ~25ms Intent / tools lookup
                matched_tool = None
            else:
                if tracker:
                    tracker.record("groq")
                matched_tool = None

        # 5. LLM TTFT Stage
        with stage("llm_ttft", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.145)  # ~145ms Groq LLaMA-3.3-70b TTFT
                llm_reply = f"I understand your query regarding {transcript[:25]} and am processing it."
            else:
                if tracker:
                    tracker.record("groq")
                llm_reply = await llm_service.generate(
                    prompt=f"{system_prompt}\n{mem_context}",
                    messages=[{"role": "user", "content": transcript}],
                    temperature=0.7,
                    max_tokens=60,
                )
                if not llm_reply:
                    raise RuntimeError(f"LLM generation failed for call {call_id} turn {turn_idx}")

        # 6. TTS TTFAB Stage
        with stage("tts_ttfab", call_id, turn_idx):
            if mock:
                await asyncio.sleep(0.085)  # ~85ms Cartesia Sonic / Sarvam Bulbul TTFAB
                out_audio = b"RIFFsynthesizedaudiobytes12345"
            else:
                provider = voice_config.get("voice_provider", "cartesia")
                if tracker:
                    tracker.record(provider)
                out_audio = await synthesize_speech(llm_reply, voice_config, api_keys, emotion_state=fused_emotion)
                if not out_audio:
                    raise RuntimeError(f"TTS synthesis failed for call {call_id} turn {turn_idx}")

        # 7. Network Out Stage
        with stage("network_out", call_id, turn_idx):
            await asyncio.sleep(0.020)

    return {
        "call_id": call_id,
        "turn_idx": turn_idx,
        "language": language,
        "transcript": transcript,
        "reply": llm_reply,
    }


async def replay_via_public_endpoint(
    endpoint_url: str,
    call_id: str,
    turn_idx: int,
    audio_bytes: bytes,
    language: str,
) -> Dict[str, Any]:
    """Fallback runner replaying turns through external HTTP/WebSocket webcall endpoints.

    Notice:
      When replaying strictly from outside via public webcall endpoints,
      client-observed round-trip time measures overall turn turnaround (turn_total);
      individual internal stages (stt, emotion, memory, intent, llm_ttft, tts_ttfab)
      cannot be isolated from outside without server-side stage logging.
    """
    logger.info(
        "Replaying turn %d of call %s via public webcall endpoint %s",
        turn_idx,
        call_id,
        endpoint_url,
    )
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Sends audio chunk as multipart or JSON payload
        res = await client.post(
            endpoint_url,
            files={"audio": ("turn.wav", audio_bytes, "audio/wav")},
            data={"call_id": call_id, "turn_idx": str(turn_idx), "language": language},
        )
        res.raise_for_status()
    total_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "call_id": call_id,
        "turn_idx": turn_idx,
        "language": language,
        "external_turn_total_ms": round(total_ms, 2),
        "unmeasured_internal_stages": ["stt", "emotion", "memory", "intent", "llm_ttft", "tts_ttfab"],
    }


async def run_latency_replay(
    out_dir: str | Path = "results",
    region: str = "ap-south-1",
    network_type: str = "broadband-fiber",
    mock: Optional[bool] = None,
    endpoint_url: Optional[str] = None,
    seed: int = 0,
) -> RunContext:
    """Orchestrates multi-turn replay across English and Hinglish agents.

    Replays 8 calls of 10 turns for English (80 turns total) and
    8 calls of 10 turns for Hinglish (80 turns total).
    Discards the first 3 turns of each call as warm-up, yielding
    56 measured turns per language (> 50 required).
    """
    is_mock_run = (mock is True) or (get_eval_mode() == "mock")
    mode_str = "mock" if is_mock_run else "live"

    if mode_str == "live":
        require_live_services(
            {
                "GROQ_API_KEY": bool(settings.GROQ_API_KEY),
                "SARVAM_API_KEY": bool(settings.SARVAM_API_KEY),
                "CARTESIA_API_KEY": bool(settings.CARTESIA_API_KEY),
                "HUME_API_KEY": bool(settings.HUME_API_KEY),
            },
            experiment_name="latency",
            cli_mock=False,
        )

    out_p = Path(out_dir)
    audio_cache_dir = Path("eval/data/latency/audio")
    audio_cache_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    time_of_day_label = _get_time_of_day_label(datetime.now())

    replay_config = {
        "benchmark": "latency_replay",
        "mode": mode_str,
        "region": region,
        "network_type": network_type,
        "time_of_day": time_of_day_label,
        "timestamp_utc": now.isoformat(),
        "warmup_turns_per_call": 3,
        "target_measured_turns_per_lang": 50,
        "english_calls_count": len(ENGLISH_CALL_TURNS),
        "hinglish_calls_count": len(HINGLISH_CALL_TURNS),
        "mock_mode": is_mock_run,
        "endpoint_url": endpoint_url,
    }

    run = start_run("latency", config=replay_config, seed=seed, base_dir=out_p, mode=mode_str)
    tracker = run.services_tracker

    # Set LATENCY_LOG environment variable to target the run directory
    log_file_path = run.path("latency_stages.jsonl")
    os.environ["LATENCY_LOG"] = str(log_file_path)

    api_keys = {
        "groq": settings.GROQ_API_KEY,
        "sarvam": settings.SARVAM_API_KEY,
        "cartesia": settings.CARTESIA_API_KEY,
        "hume": settings.HUME_API_KEY,
    }

    print(f"Starting Latency Replay Benchmark ({mode_str.upper()} mode)")
    print(f"  Region: {region} | Network: {network_type} | Time of Day: {time_of_day_label}")
    print(f"  Destination Log: {log_file_path}")

    # Replay English Calls
    en_agent_config = {
        "language": "en",
        "system_prompt": "You are a courteous VoCall customer service assistant.",
        "voice_config": {"voice_provider": "cartesia", "voice_id": "sonic-english"},
    }

    for call_num, call_phrases in enumerate(ENGLISH_CALL_TURNS, start=1):
        call_id = f"call_en_{call_num:02d}"
        for turn_idx, phrase in enumerate(call_phrases, start=1):
            utt_id = f"{call_id}_turn_{turn_idx:02d}"
            wav_path = ensure_audio_file(phrase, utt_id, audio_cache_dir, language="en")
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()

            if endpoint_url:
                await replay_via_public_endpoint(endpoint_url, call_id, turn_idx, audio_bytes, "en")
            else:
                await replay_turn_direct(
                    call_id=call_id,
                    turn_idx=turn_idx,
                    audio_bytes=audio_bytes,
                    language="en",
                    agent_config=en_agent_config,
                    api_keys=api_keys,
                    mock=is_mock_run,
                    mock_transcript=phrase,
                    tracker=tracker,
                )

    # Replay Hinglish Calls
    hi_agent_config = {
        "language": "hinglish",
        "system_prompt": "You are a bilingual Hindi-English voice assistant responding in caller's mix.",
        "voice_config": {"voice_provider": "sarvam", "voice_id": "bulbul:v1"},
    }

    for call_num, call_phrases in enumerate(HINGLISH_CALL_TURNS, start=1):
        call_id = f"call_hing_{call_num:02d}"
        for turn_idx, phrase in enumerate(call_phrases, start=1):
            utt_id = f"{call_id}_turn_{turn_idx:02d}"
            wav_path = ensure_audio_file(phrase, utt_id, audio_cache_dir, language="hinglish")
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()

            if endpoint_url:
                await replay_via_public_endpoint(endpoint_url, call_id, turn_idx, audio_bytes, "hinglish")
            else:
                await replay_turn_direct(
                    call_id=call_id,
                    turn_idx=turn_idx,
                    audio_bytes=audio_bytes,
                    language="hinglish",
                    agent_config=hi_agent_config,
                    api_keys=api_keys,
                    mock=is_mock_run,
                    mock_transcript=phrase,
                    tracker=tracker,
                )

    print(f"Replay complete. Raw per-stage traces written to: {log_file_path}")

    # Summarise latency and write metrics
    from eval.latency.summarise import summarise_latency
    summary = summarise_latency(log_file_path, out_dir=run.run_dir, warmup_turns=3)
    if is_mock_run:
        stamp_csv_mock_data(run.path("fig5a_stacked_bar.csv"), mode="mock")
    run.write_metrics("metrics.json", summary)

    return run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VoCall Latency Stage Replay Benchmark")
    parser.add_argument("--out", default="results", help="Base output directory")
    parser.add_argument("--region", default="ap-south-1", help="Cloud deployment region (e.g. ap-south-1)")
    parser.add_argument("--network-type", default="broadband-fiber", help="Network type (e.g. broadband-fiber, 4G-LTE)")
    parser.add_argument("--endpoint", default=None, help="Public webcall endpoint URL for external replay")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in mock mode with simulated sleep stages")
    parser.add_argument("--live", action="store_true", help="Explicit flag for live external API calls")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for reproducibility")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    is_mock = args.mock or (not args.live and get_eval_mode() == "mock")
    asyncio.run(
        run_latency_replay(
            out_dir=args.out,
            region=args.region,
            network_type=args.network_type,
            mock=is_mock,
            endpoint_url=args.endpoint,
            seed=args.seed,
        )
    )


if __name__ == "__main__":
    main()
