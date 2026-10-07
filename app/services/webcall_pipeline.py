"""
VoCall Web Call Pipeline — Browser-to-LiveKit voice session.

run_webcall_agent(call_id, agent_config, api_keys):
  Joins a LiveKit room as the AI agent participant (no Twilio).
  Waits for the human browser participant to publish an audio track,
  then runs the same STT → LLM → TTS → LiveKit audio publish loop
  used by the phone pipeline.

  Transcript turns are stored in Redis (short_term memory) AND appended
  to a Redis list keyed `webcall:{call_id}:events` so the SSE endpoint
  can stream them to the browser.

  The pipeline is cancelled when:
    - The DELETE /calls/webcall/{call_id}/end endpoint is called, OR
    - The LiveKit room becomes empty (all participants leave)
"""

import asyncio
import base64
import json
import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx

from app.services.audio import (
    mulaw_to_pcm16,
    resample_pcm16,
    pcm16_to_wav,
    VoiceActivityDetector,
)
from app.services.latency_stage import stage

from app.core.config import settings
from app.services.emotion import (
    analyze_text_emotion,
    analyze_audio_emotion,
    fire_threshold_connectors,
    fuse_emotion_signals,
    get_tone_instruction,
)
from app.services.intent import detector, slot_manager
from app.services.livekit_service import livekit_service
from app.services.llm import llm_service
from app.services.memory import short_term
from app.services.memory.retriever import retrieve_all_memory, build_memory_prompt
from app.services.redis_client import redis_client
from app.services.stt import transcribe_audio
from app.services.supabase_client import supabase
from app.services.tts import synthesize_speech
from app.services.voice_pipeline import (
    _load_agent_config,
    _load_org_api_keys,
    get_active_pipeline_path,
    get_active_tools,
    handle_tool_call,
)
from app.services.turn_pipeline import (
    assemble_turn_prompt,
    execute_shared_turn_steps,
    format_t2_facts,
    select_tts_config,
)

logger = logging.getLogger(__name__)

_format_t2_facts = format_t2_facts


# Active webcall tasks: call_id -> asyncio.Task
_active_webcall_tasks: Dict[str, asyncio.Task] = {}

# ---------------------------------------------------------------------------
# Redis event helpers — SSE feed per call_id
# ---------------------------------------------------------------------------

WEBCALL_EVENT_TTL = 3600  # 1 hour


async def _push_sse_event(call_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """
    Appends a JSON event to the Redis list `webcall:{call_id}:events`.
    The SSE endpoint reads from this list and streams to the browser.
    """
    payload = json.dumps({"type": event_type, "ts": int(time.time() * 1000), **data})
    key = f"webcall:{call_id}:events"
    try:
        await redis_client.rpush(key, payload)
    except Exception as exc:
        logger.warning("Failed to push SSE event for call %s: %s", call_id, exc)


# ---------------------------------------------------------------------------
# LiveKit audio helpers (no Pipecat dependency — direct SDK usage)
# ---------------------------------------------------------------------------

async def _pull_audio_from_livekit(
    room_name: str,
    call_id: str,
    timeout: float = 300.0,
) -> Optional[bytes]:
    """
    Polls LiveKit for the most recent audio frame from the human participant.
    Returns raw PCM/opus bytes or None if no audio/timeout.

    NOTE: This is a simplified polling approach using LiveKit REST API.
    For production deployments with Pipecat, swap this for LiveKitTransport.
    """
    if not livekit_service.is_configured():
        return None

    try:
        from livekit import api as lk_api

        room_service = lk_api.RoomServiceClient(
            livekit_service._url,
            livekit_service._api_key,
            livekit_service._api_secret,
        )
        participants = await room_service.list_participants(
            lk_api.ListParticipantsRequest(room=room_name)
        )
        # Human participant will have identity NOT starting with "agent-"
        human = next(
            (p for p in participants.participants if not p.identity.startswith("agent-")),
            None,
        )
        if not human:
            return None

        logger.debug(
            "Web call %s: human participant %s found", call_id, human.identity
        )
        return None  # Polling approach; Pipecat LiveKitTransport handles audio frames
    except Exception as exc:
        logger.warning("LiveKit participant check failed: %s", exc)
        return None


async def _publish_audio_to_livekit(
    room_name: str,
    audio_bytes: bytes,
    call_id: str,
) -> None:
    """
    Publishes synthesised TTS audio back to the LiveKit room.
    In a Pipecat-based deployment this is handled by LiveKitTransport.output().
    For the minimal loop, we use LiveKit's DataPacket as a fallback signal.
    """
    if not livekit_service.is_configured():
        logger.debug("LiveKit not configured — skipping audio publish")
        return

    try:
        from livekit import api as lk_api

        room_service = lk_api.RoomServiceClient(
            livekit_service._url,
            livekit_service._api_key,
            livekit_service._api_secret,
        )
        audio_b64 = base64.b64encode(audio_bytes).decode()
        await room_service.send_data(
            lk_api.SendDataRequest(
                room=room_name,
                data=json.dumps({"type": "audio", "payload": audio_b64}).encode(),
                kind=lk_api.DataPacketKind.RELIABLE,
            )
        )
        logger.debug("Published TTS audio to LiveKit room %s", room_name)
    except Exception as exc:
        logger.warning("Failed to publish audio to LiveKit: %s", exc)


# ---------------------------------------------------------------------------
# Main webcall pipeline (Pipecat-first with minimal fallback)
# ---------------------------------------------------------------------------

async def run_webcall_agent(
    call_id: str,
    agent_id: str,
    org_id: str,
    contact_id: Optional[str] = None,
    contact_name: str = "Caller",
) -> None:
    """
    Entry point for the background webcall pipeline task.

    Loads all 4 memory tiers when contact_id is present:
      - Short-term  : active call turns in Redis
      - Long-term   : pgvector semantic facts about this contact
      - Episodic    : summaries of past calls with this contact
      - Graph       : FalkorDB entity/frustration graph context

    Tries Pipecat LiveKitTransport first. Falls back to a minimal STT→LLM→TTS
    loop that communicates through LiveKit DataPackets when Pipecat is not available.
    """
    logger.info(
        "Starting webcall agent: call_id=%s agent_id=%s contact_id=%s contact_name=%s",
        call_id, agent_id, contact_id, contact_name,
    )
    room_name = livekit_service._room_name(call_id)

    agent = await _load_agent_config(agent_id)
    system_prompt: str = agent.get("system_prompt") or "You are a helpful AI voice assistant."
    language: str = agent.get("language") or "en"
    voice_config: Dict[str, Any] = {
        "voice_id": agent.get("voice_id"),
        "voice_provider": agent.get("voice_provider", "cartesia"),
    }
    emotion_config: Dict[str, Any] = (agent.get("config") or {}).get("emotion") or {}

    api_keys = await _load_org_api_keys(org_id)
    await short_term.init_call_memory(call_id)

    # ── Call-Start Memory Retrieval (T3 Episodic, T4 Graph) ───────────────────
    call_start_block = ""
    try:
        memory_dict = await retrieve_all_memory(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=agent_id,
            query_text="",  # no query text at call start; do not run T2
            config={"call_id": call_id, "episodic_limit": 3},
            enabled_tiers=["t3", "t4"],
        )
        call_start_block = build_memory_prompt(memory_dict)
        if call_start_block:
            logger.info(
                "Webcall %s: injected contact memory (T3/T4) for %s (%s)",
                call_id, contact_name, contact_id,
            )
        else:
            logger.info(
                "Webcall %s: no prior episodic/graph memory found for %s — fresh start",
                call_id, contact_name,
            )
    except Exception as exc:
        logger.warning("Webcall memory retrieval failed: %s", exc)
        call_start_block = ""
    # ────────────────────────────────────────────────────────────────────────

    # Signal connecting
    await _push_sse_event(call_id, "status", {"state": "connecting"})

    active_path = get_active_pipeline_path()
    logger.info("Starting webcall pipeline: call_id=%s agent_id=%s path=%s", call_id, agent_id, active_path)
    if supabase:
        try:
            supabase.table("calls").update({
                "status": "in_progress",
                "analysis": {"pipeline_path": active_path},
            }).eq("id", call_id).execute()
        except Exception as exc:
            logger.warning("Failed to update webcall status to in_progress: %s", exc)

    try:
        if active_path == "pipecat":
            logger.info("Starting Pipecat webcall path (experimental: no emotion, intent, or memory steps)")
            try:
                await _run_pipecat_webcall(
                    call_id=call_id,
                    room_name=room_name,
                    agent_id=agent_id,
                    org_id=org_id,
                    system_prompt=system_prompt,
                    language=language,
                    voice_config=voice_config,
                    emotion_config=emotion_config,
                    api_keys=api_keys,
                    agent=agent,
                    contact_id=contact_id,
                    contact_name=contact_name,
                    call_start_block=call_start_block,
                )
            except Exception as pipecat_exc:
                logger.warning(
                    "Pipecat webcall raised error (%s) — falling back to custom webcall loop",
                    pipecat_exc,
                )
                await _custom_webcall_loop(
                    call_id=call_id,
                    room_name=room_name,
                    agent_id=agent_id,
                    org_id=org_id,
                    system_prompt=system_prompt,
                    language=language,
                    voice_config=voice_config,
                    emotion_config=emotion_config,
                    api_keys=api_keys,
                    agent=agent,
                    contact_id=contact_id,
                    contact_name=contact_name,
                    call_start_block=call_start_block,
                )
        else:
            logger.info("Running custom webcall loop (production multi-modal loop with emotion, intent, memory)")
            await _custom_webcall_loop(
                call_id=call_id,
                room_name=room_name,
                agent_id=agent_id,
                org_id=org_id,
                system_prompt=system_prompt,
                language=language,
                voice_config=voice_config,
                emotion_config=emotion_config,
                api_keys=api_keys,
                agent=agent,
                contact_id=contact_id,
                contact_name=contact_name,
                call_start_block=call_start_block,
            )
    except asyncio.CancelledError:
        logger.info("Webcall pipeline cancelled: call_id=%s", call_id)
    except Exception as exc:
        logger.error("Webcall pipeline error call_id=%s: %s", call_id, exc)
    finally:
        await _finalize_webcall(call_id)


# ---------------------------------------------------------------------------
# Pipecat LiveKitTransport path
# ---------------------------------------------------------------------------

async def _run_pipecat_webcall(
    call_id: str,
    room_name: str,
    agent_id: str,
    org_id: str,
    system_prompt: str,
    language: str,
    voice_config: Dict[str, Any],
    emotion_config: Dict[str, Any],
    api_keys: Dict[str, str],
    agent: Dict[str, Any],
    contact_id: Optional[str] = None,
    contact_name: str = "Caller",
    call_start_block: str = "",
) -> None:
    """
    Uses Pipecat's LiveKitTransport for full-duplex audio with the browser.
    Raises ImportError if Pipecat is not installed (triggers fallback).
    """
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask
    from pipecat.processors.aggregators.llm_response import (
        LLMUserResponseAggregator,
        LLMAssistantResponseAggregator,
    )
    from pipecat.services.openai import OpenAILLMService
    from pipecat.transports.services.livekit import LiveKitParams, LiveKitTransport

    agent_token = livekit_service.generate_agent_token(room_name, agent_id)

    transport = LiveKitTransport(
        url=livekit_service._url,
        token=agent_token,
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
        ),
    )

    groq_key = api_keys.get("groq") or settings.GROQ_API_KEY
    llm = OpenAILLMService(
        api_key=groq_key or "placeholder",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )

    initial_prompt = f"{call_start_block}\n\n{system_prompt}" if call_start_block else system_prompt

    user_aggregator = LLMUserResponseAggregator(
        messages=[{"role": "system", "content": initial_prompt}]
    )
    assistant_aggregator = LLMAssistantResponseAggregator(
        messages=[{"role": "system", "content": initial_prompt}]
    )

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            assistant_aggregator,
            transport.output(),
        ]
    )

    # Register event hooks for transcript streaming
    @transport.event_handler("on_transcription_message")
    async def on_transcript(transport, message):
        speaker = "agent" if message.get("is_final") else "user"
        text = message.get("text", "")
        if text:
            await _push_sse_event(call_id, "transcript", {
                "speaker": speaker,
                "text": text,
                "timestamp": int(time.time() * 1000),
            })
            await short_term.append_turn(call_id=call_id, role=speaker, content=text)

    await _push_sse_event(call_id, "status", {"state": "active"})

    task = PipelineTask(pipeline)
    runner = PipelineRunner()
    await runner.run(task)


# ---------------------------------------------------------------------------
# Custom webcall loop (production multi-modal loop)
# ---------------------------------------------------------------------------

async def _custom_webcall_loop(
    call_id: str,
    room_name: str,
    agent_id: str,
    org_id: str,
    system_prompt: str,
    language: str,
    voice_config: Dict[str, Any],
    emotion_config: Dict[str, Any],
    api_keys: Dict[str, str],
    agent: Dict[str, Any],
    contact_id: Optional[str] = None,
    contact_name: str = "Caller",
    call_start_block: str = "",
) -> None:
    """
    Custom LiveKit audio loop with multi-modal parallel fan-out
    (emotion, intent, memory), tone adaptation, and active tool execution.
    """
    if not livekit_service.is_configured():
        logger.warning("LiveKit not configured — webcall custom loop cannot run")
        return

    await _push_sse_event(call_id, "status", {"state": "active"})

    initial_prompt = f"{call_start_block}\n\n{system_prompt}" if call_start_block else system_prompt
    conversation: List[Dict[str, Any]] = [{"role": "system", "content": initial_prompt}]
    groq_key = api_keys.get("groq") or settings.GROQ_API_KEY
    hume_key = api_keys.get("hume") or api_keys.get("hume_api_key")

    try:
        from livekit import api as lk_api, rtc as lk_rtc

        lk_room = lk_rtc.Room()
        agent_token = livekit_service.generate_agent_token(room_name, agent_id)
        turn_idx = 0
        vad = VoiceActivityDetector(
            sample_rate=16000,
            frame_duration_ms=20,
            energy_threshold=getattr(settings, "VAD_ENERGY_THRESHOLD", 400.0),
            silence_duration_ms=getattr(settings, "VAD_SILENCE_MS", 700),
        )

        async def on_data_received(data: bytes, participant):
            nonlocal conversation, turn_idx
            try:
                msg = json.loads(data.decode())
            except Exception:
                return

            if msg.get("type") == "audio_end":
                utterance_pcm = vad.flush()
            elif msg.get("type") == "audio_chunk":
                audio_b64 = msg.get("payload", "")
                if not audio_b64:
                    return
                raw_chunk = base64.b64decode(audio_b64)
                pcm_chunk = raw_chunk[44:] if (len(raw_chunk) >= 44 and raw_chunk[:4] == b"RIFF") else raw_chunk
                utterance_pcm = vad.process_frame(pcm_chunk)
            else:
                return

            if not utterance_pcm:
                return

            turn_idx += 1

            with stage("turn_total", call_id, turn_idx):
                wav_bytes = pcm16_to_wav(utterance_pcm, sample_rate=16000, num_channels=1)

                # 1. STT Stage
                with stage("stt", call_id, turn_idx):
                    transcript = await transcribe_audio(wav_bytes, language, api_keys)
                if not transcript:
                    return

                # 2. Shared Multi-Modal Turn Steps (Emotion, Intent, Memory, Tone, Prompt, TTS config)
                shared = await execute_shared_turn_steps(
                    call_id=call_id,
                    turn_idx=turn_idx,
                    transcript=transcript,
                    wav_bytes=wav_bytes,
                    agent=agent or {},
                    org_id=org_id,
                    agent_id=agent_id,
                    contact_id=contact_id,
                    api_keys=api_keys,
                    system_prompt=system_prompt,
                    call_start_block=call_start_block,
                    contact_name=contact_name,
                    language=language,
                    _retrieve_all_memory=retrieve_all_memory,
                    _analyze_text_emotion=analyze_text_emotion,
                    _analyze_audio_emotion=analyze_audio_emotion,
                )
                fused_emotion = shared["fused_emotion"]
                text_emotion = shared["text_emotion"]
                audio_emotion = shared["audio_emotion"]
                active_tools = shared["active_tools"]
                turn_prompt = shared["turn_prompt"]
                tts_config = shared["tts_config"]

                # Emit transcript SSE event
                ts = int(time.time() * 1000)
                conversation.append({"role": "user", "content": transcript})
                await _push_sse_event(call_id, "transcript", {
                    "speaker": "user",
                    "text": transcript,
                    "timestamp": ts,
                })

                # 4. LLM Generation Stage
                llm_kwargs = {"tools": active_tools} if active_tools else {}
                with stage("llm", call_id, turn_idx):
                    try:
                        llm_res = await llm_service.generate(
                            prompt=turn_prompt,
                            messages=conversation[1:],
                            api_keys=api_keys,
                            **llm_kwargs,
                        )
                    except Exception as llm_exc:
                        logger.error("LLM error in webcall: %s", llm_exc)
                        llm_res = "I'm sorry, I'm having trouble responding right now."

                reply = ""
                tool_calls = None
                if isinstance(llm_res, dict):
                    reply = llm_res.get("content") or ""
                    tool_calls = llm_res.get("tool_calls")
                else:
                    reply = str(llm_res or "")

                # Tool execution
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        t_name = func.get("name", "")
                        t_args_raw = func.get("arguments", {})
                        t_args = json.loads(t_args_raw) if isinstance(t_args_raw, str) else (t_args_raw or {})
                        conversation.append({"role": "assistant", "content": reply, "tool_calls": [tc]})
                        tool_result_str = await handle_tool_call(t_name, t_args, org_id, agent_id)
                        conversation.append({"role": "tool", "tool_call_id": tc.get("id", "call_1"), "name": t_name, "content": tool_result_str})
                        try:
                            final_res = await llm_service.generate(prompt=turn_prompt, messages=conversation[1:], api_keys=api_keys)
                            reply = final_res.get("content") or "" if isinstance(final_res, dict) else str(final_res or "")
                        except Exception:
                            reply = reply or "I completed the action."

                conversation.append({"role": "assistant", "content": reply})
                ts2 = int(time.time() * 1000)

                # 5. Turn Append Stage (Redis)
                with stage("append_turn", call_id, turn_idx):
                    if text_emotion:
                        text_emotion["signal_source"] = "text"
                        text_emotion["timestamp_ms"] = ts
                        await short_term.append_emotion_event(call_id, text_emotion)

                    if audio_emotion:
                        audio_emotion["signal_source"] = "audio"
                        audio_emotion["timestamp_ms"] = ts
                        await short_term.append_emotion_event(call_id, audio_emotion)

                    await short_term.append_turn(call_id=call_id, role="user", content=transcript, emotion_state=fused_emotion)
                    await short_term.append_turn(call_id=call_id, role="assistant", content=reply)

                # Emit agent transcript SSE event
                await _push_sse_event(call_id, "transcript", {
                    "speaker": "agent",
                    "text": reply,
                    "timestamp": ts2,
                })

                # 6. TTS Speech Synthesis Stage
                tts_emotion = fused_emotion if emotion_config.get("emotion_conditioned_voice") and hume_key else None
                with stage("tts", call_id, turn_idx):
                    audio_out = await synthesize_speech(reply, tts_config or voice_config, api_keys, emotion_state=tts_emotion)

                # 7. Network Out Stage
                with stage("network_out", call_id, turn_idx):
                    if audio_out:
                        await _publish_audio_to_livekit(room_name, audio_out, call_id)

        lk_room.on("data_received", on_data_received)

        await lk_room.connect(livekit_service._url, agent_token)
        logger.info("Webcall agent connected to LiveKit room: %s", room_name)

        # Keep alive until cancelled or room disconnects
        stop_event = asyncio.Event()

        @lk_room.on("disconnected")
        def on_disconnected():
            stop_event.set()

        await stop_event.wait()

    except ImportError:
        logger.error("livekit-agents SDK not available for webcall custom loop")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Custom webcall loop error: %s", exc)


# Backward compatibility alias
_run_minimal_webcall_loop = _custom_webcall_loop


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------

async def _finalize_webcall(call_id: str) -> None:
    """Saves transcript, deletes LiveKit room, emits ended SSE event."""
    logger.info("Finalizing webcall: %s", call_id)

    try:
        mem = await short_term.get_call_memory(call_id)
        transcript_data = mem.get("turns", []) if mem else []
        transcript_json = json.dumps(transcript_data)

        if supabase:
            supabase.table("calls").update(
                {"transcript": transcript_json}
            ).eq("id", call_id).execute()
    except Exception as exc:
        logger.error("Failed to finalize webcall transcript: %s", exc)

    try:
        await _push_sse_event(call_id, "status", {"state": "ended"})
    except Exception:
        pass

    try:
        if livekit_service.is_configured():
            await livekit_service.delete_room(call_id)
    except Exception as exc:
        logger.warning("LiveKit room cleanup failed for webcall %s: %s", call_id, exc)

    _active_webcall_tasks.pop(call_id, None)


# ---------------------------------------------------------------------------
# Task registry helpers (called by the router)
# ---------------------------------------------------------------------------

def register_webcall_task(call_id: str, task: asyncio.Task) -> None:
    """Stores the asyncio.Task so DELETE /end can cancel it."""
    _active_webcall_tasks[call_id] = task


def cancel_webcall_task(call_id: str) -> bool:
    """Cancels the running pipeline task. Returns True if a task was found."""
    task = _active_webcall_tasks.pop(call_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False
