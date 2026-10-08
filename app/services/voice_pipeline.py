"""
VoCall Real-Time Voice Pipeline using Pipecat.

start_pipeline(call_id, agent_id, contact_id, ws_connection):
  Assembles and runs a Pipecat pipeline:

  LiveKitTransport (audio input)
    → STT stage
    → LLMUserResponseAggregator
    → LLM stage  (Groq → Cerebras fallback via llm.py with tools support)
    → TTS stage
    → LiveKitTransport (audio output)

  Each completed turn is written to Redis via short_term.append_turn()
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.services.audio import (
    mulaw_to_pcm16,
    resample_pcm16,
    pcm16_to_wav,
    VoiceActivityDetector,
)
from app.services.latency_stage import stage

from app.core.config import settings
from app.services.emotion import (
    analyze_audio_emotion,
    analyze_text_emotion,
    fire_frustration_connector,
    fire_threshold_connectors,
    fuse_emotion_signals,
    get_tone_instruction,
)
from app.services.turn_pipeline import (
    assemble_turn_prompt,
    execute_shared_turn_steps,
    format_t2_facts,
    get_active_tools,
    handle_tool_call,
    select_tts_config,
)
from app.services.intent import detector, slot_manager
from app.services.livekit_service import livekit_service
from app.services.llm import llm_service
from app.services.memory import short_term
from app.services.memory.retriever import build_memory_prompt, retrieve_all_memory
from app.services.redis_client import redis_client
from app.services.stt import transcribe_audio
from app.services.supabase_client import supabase
from app.services.tts import synthesize_speech, synthesize_speech_stream
import re

logger = logging.getLogger(__name__)

SENTENCE_END_RE = re.compile(r'([.!?|।]+(?:\s+|$)|[\r\n]+)')


def _has_sentence_end(text: str) -> bool:
    return bool(SENTENCE_END_RE.search(text))


def _split_first_sentence(text: str) -> tuple[str, str]:
    match = SENTENCE_END_RE.search(text)
    if not match:
        return text, ""
    end_idx = match.end()
    first_sent = text[:end_idx].strip()
    remainder = text[end_idx:]
    return first_sent, remainder


async def _send_media_to_ws(ws_connection, stream_sid: str, audio_bytes: bytes) -> None:
    if not audio_bytes:
        return
    import base64
    audio_b64_out = base64.b64encode(audio_bytes).decode()
    response_payload = json.dumps(
        {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": audio_b64_out},
        }
    )
    if hasattr(ws_connection, "send"):
        await ws_connection.send({"type": "websocket.send", "text": response_payload})
    elif hasattr(ws_connection, "send_text"):
        await ws_connection.send_text(response_payload)


def get_active_pipeline_path() -> str:
    """
    Returns the active voice pipeline path: 'custom' (default) or 'pipecat'.
    With PIPELINE_MODE='custom', Pipecat is never imported or used.
    """
    mode = getattr(settings, "PIPELINE_MODE", "custom").lower()
    if mode == "pipecat":
        return "pipecat"
    return "custom"


# ---------------------------------------------------------------------------
# Connector & Active Tools Loader
# ---------------------------------------------------------------------------

async def get_active_tools(org_id: str, agent_id: str) -> List[Dict[str, Any]]:
    """
    1. Fetches all connector_configs for org/agent where is_enabled = True and connector_type
       IN ("google_calendar", "supabase", "postgres", "custom_webhook").
    2. Imports corresponding TOOL_SCHEMA from connector services.
    3. Returns the list of tool schemas.
    """
    if not supabase or not org_id:
        return []

    try:
        res = (
            supabase.table("connector_configs")
            .select("connector_type, config, agent_id, is_enabled")
            .eq("org_id", str(org_id))
            .eq("is_enabled", True)
            .in_("connector_type", ["google_calendar", "supabase", "postgres", "custom_webhook"])
            .execute()
        )

        rows = res.data or []
        enabled_types = set()
        for row in rows:
            row_agent = row.get("agent_id")
            if not row_agent or str(row_agent) == str(agent_id):
                enabled_types.add(row.get("connector_type"))

        tools = []
        if "google_calendar" in enabled_types:
            try:
                from app.services.connectors.google_cal import TOOL_SCHEMA as cal_tools
                tools.extend(cal_tools)
            except Exception as e:
                logger.warning("Failed to load google_calendar TOOL_SCHEMA: %s", e)

        if "supabase" in enabled_types or "postgres" in enabled_types:
            try:
                from app.services.connectors.supabase_conn import TOOL_SCHEMA as db_tools
                for t in db_tools:
                    fname = t.get("function", {}).get("name")
                    if fname == "query_supabase" and "supabase" in enabled_types:
                        tools.append(t)
                    elif fname == "query_postgres" and "postgres" in enabled_types:
                        tools.append(t)
            except Exception as e:
                logger.warning("Failed to load supabase/postgres TOOL_SCHEMA: %s", e)

        if "custom_webhook" in enabled_types:
            try:
                from app.services.connectors.webhook import DURING_CALL_TOOL_SCHEMA as wh_tools
                tools.extend(wh_tools)
            except Exception as e:
                logger.warning("Failed to load webhook TOOL_SCHEMA: %s", e)

        return tools

    except Exception as exc:
        logger.error("Error fetching active tools for org %s: %s", org_id, exc)
        return []


async def handle_tool_call(tool_name: str, tool_args: dict, org_id: str, agent_id: str) -> str:
    """
    Dispatches tool call to correct connector service using stored config.
    Returns string result to be read back into conversation.
    """
    if not supabase or not org_id:
        return json.dumps({"success": False, "error": "Database unavailable"})

    connector_type = None
    if tool_name in ("check_availability", "book_appointment"):
        connector_type = "google_calendar"
    elif tool_name == "query_supabase":
        connector_type = "supabase"
    elif tool_name == "query_postgres":
        connector_type = "postgres"
    elif tool_name == "fire_webhook":
        connector_type = "custom_webhook"

    if not connector_type:
        return json.dumps({"success": False, "error": f"Unknown tool name '{tool_name}'"})

    config = {}
    try:
        res = (
            supabase.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("connector_type", connector_type)
            .execute()
        )
        rows = res.data or []
        if rows:
            agent_rows = [r for r in rows if r.get("agent_id") and str(r.get("agent_id")) == str(agent_id)]
            target_row = agent_rows[0] if agent_rows else rows[0]
            from app.utils.encryption import decrypt_dict
            config = decrypt_dict(target_row.get("config", {}))
    except Exception as e:
        logger.warning("Error fetching connector config for tool %s: %s", tool_name, e)

    try:
        if tool_name == "check_availability":
            from app.services.connectors.google_cal import check_availability
            creds_json = tool_args.get("credentials_json") or config.get("credentials_json", "{}")
            cal_id = tool_args.get("calendar_id") or config.get("calendar_id", "primary")
            tz = tool_args.get("timezone") or config.get("timezone", "Asia/Kolkata")
            slots = await check_availability(creds_json, cal_id, tool_args.get("date_str", ""), tz)
            return json.dumps({"success": True, "free_slots": slots})

        elif tool_name == "book_appointment":
            from app.services.connectors.google_cal import book_appointment
            creds_json = tool_args.get("credentials_json") or config.get("credentials_json", "{}")
            cal_id = tool_args.get("calendar_id") or config.get("calendar_id", "primary")
            tz = tool_args.get("timezone") or config.get("timezone", "Asia/Kolkata")
            res_dict = await book_appointment(
                creds_json,
                cal_id,
                tool_args.get("start_time", ""),
                tool_args.get("end_time", ""),
                tool_args.get("summary", "Appointment"),
                tool_args.get("attendee_email"),
                tz,
            )
            return json.dumps(res_dict)

        elif tool_name == "query_supabase":
            from app.services.connectors.supabase_conn import query_supabase
            url = tool_args.get("url") or config.get("url", "")
            anon_key = tool_args.get("anon_key") or config.get("anon_key", "")
            res_dict = await query_supabase(
                url,
                anon_key,
                tool_args.get("table_name", ""),
                tool_args.get("query_column", ""),
                tool_args.get("query_value", ""),
            )
            return json.dumps(res_dict)

        elif tool_name == "query_postgres":
            from app.services.connectors.supabase_conn import query_postgres
            conn_str = tool_args.get("connection_string") or config.get("connection_string", "")
            q_tmpl = tool_args.get("query_template") or config.get("query_template", "")
            res_dict = await query_postgres(conn_str, q_tmpl, tool_args.get("contact_phone", ""))
            return json.dumps(res_dict)

        elif tool_name == "fire_webhook":
            from app.services.connectors.webhook import fire_webhook
            url = tool_args.get("url") or config.get("webhook_url") or config.get("url", "")
            payload = tool_args.get("payload") or {}
            headers = config.get("headers", {})
            res_dict = await fire_webhook(url=url, method="POST", headers=headers, payload=payload)
            return json.dumps(res_dict)

        else:
            return json.dumps({"success": False, "error": f"Unhandled tool '{tool_name}'"})

    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# STT & TTS Routing Wrappers
# ---------------------------------------------------------------------------

async def _stt_transcribe(
    audio_bytes: bytes,
    language: str,
    api_keys: Dict[str, str],
) -> str:
    return await transcribe_audio(audio_bytes, language, api_keys)


async def _tts_synthesize(
    text: str,
    voice_config: Dict[str, Any],
    api_keys: Dict[str, str],
    emotion_state: Optional[Dict[str, Any]] = None,
) -> bytes:
    return await synthesize_speech(text, voice_config, api_keys, emotion_state)


async def _append_turn_to_redis(
    call_id: str,
    role: str,
    content: str,
    timestamp_ms: int,
    emotion_state: Optional[Dict[str, Any]] = None,
) -> None:
    await short_term.append_turn(
        call_id=call_id,
        role=role,
        content=content,
        emotion_state=emotion_state,
    )


async def _load_agent_config(agent_id: str) -> Dict[str, Any]:
    if not supabase or not agent_id:
        return {}
    try:
        res = supabase.table("agents").select("*").eq("id", agent_id).single().execute()
        return res.data or {}
    except Exception as exc:
        logger.error("Failed to load agent config for %s: %s", agent_id, exc)
        return {}


async def _load_org_api_keys(org_id: str) -> Dict[str, str]:
    if not supabase or not org_id:
        return {}
    try:
        res = supabase.table("api_keys").select("provider, encrypted_key").eq("org_id", org_id).execute()
        return {row["provider"]: row["encrypted_key"] for row in (res.data or [])}
    except Exception as exc:
        logger.error("Failed to load org API keys: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Pipecat Pipeline
# ---------------------------------------------------------------------------

async def start_pipeline(
    call_id: str,
    agent_id: str,
    contact_id: Optional[str],
    ws_connection,
) -> None:
    """
    Builds and runs the VoCall real-time voice pipeline for a single call.
    """
    active_path = get_active_pipeline_path()
    logger.info("Starting voice pipeline: call_id=%s agent_id=%s path=%s", call_id, agent_id, active_path)

    agent = await _load_agent_config(agent_id)
    org_id: str = agent.get("org_id", "")
    system_prompt: str = agent.get("system_prompt") or "You are a helpful AI voice assistant."
    language: str = agent.get("language") or "en"
    final_prompt: str = system_prompt
    if language in ["hi", "hinglish"]:
        final_prompt += (
            "\n\nLANGUAGE INSTRUCTION: Respond in the same language mix the "
            "caller uses — Hindi, English, or Hinglish code-switching."
        )
    voice_config: Dict[str, Any] = {
        "voice_id": agent.get("voice_id"),
        "voice_provider": agent.get("voice_provider", "cartesia"),
    }

    api_keys = await _load_org_api_keys(org_id)
    await short_term.init_call_memory(call_id)

    call_start_block = ""
    try:
        mem_dict = await retrieve_all_memory(
            contact_id=contact_id,
            org_id=org_id,
            agent_id=agent_id,
            query_text="",
            config={"call_id": call_id, "episodic_limit": 3},
            enabled_tiers=["t3", "t4"],
        )
        call_start_block = build_memory_prompt(mem_dict)
    except Exception as exc:
        logger.warning("Failed call-start memory retrieval: %s", exc)
        call_start_block = ""

    pipecat_prompt = f"{call_start_block}\n\n{final_prompt}" if call_start_block else final_prompt

    if livekit_service.is_configured():
        try:
            await livekit_service.create_room(call_id)
        except Exception as exc:
            logger.warning("LiveKit room pre-creation skipped: %s", exc)

    if supabase:
        try:
            supabase.table("calls").update({
                "status": "in_progress",
                "analysis": {"pipeline_path": active_path},
            }).eq("id", call_id).execute()
        except Exception as exc:
            logger.warning("Failed to update call status to in_progress: %s", exc)

    try:
        if active_path == "pipecat":
            logger.info("Starting Pipecat path (experimental: no emotion, intent, or memory steps)")
            try:
                from pipecat.pipeline.pipeline import Pipeline
                from pipecat.pipeline.runner import PipelineRunner
                from pipecat.pipeline.task import PipelineTask
                from pipecat.processors.aggregators.llm_response import (
                    LLMUserResponseAggregator,
                    LLMAssistantResponseAggregator,
                )
                from pipecat.transports.network.websocket_server import (
                    WebsocketServerParams,
                    WebsocketServerTransport,
                )
                from pipecat.services.openai import OpenAILLMService

                transport = WebsocketServerTransport(
                    params=WebsocketServerParams(
                        audio_out_enabled=True,
                        add_wav_header=False,
                        vad_enabled=True,
                        vad_audio_passthrough=True,
                    )
                )

                groq_key = api_keys.get("groq") or settings.GROQ_API_KEY
                llm = OpenAILLMService(
                    api_key=groq_key or "placeholder",
                    base_url="https://api.groq.com/openai/v1",
                    model="llama-3.3-70b-versatile",
                )

                user_aggregator = LLMUserResponseAggregator(
                    messages=[{"role": "system", "content": pipecat_prompt}]
                )
                assistant_aggregator = LLMAssistantResponseAggregator(
                    messages=[{"role": "system", "content": pipecat_prompt}]
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

                task = PipelineTask(pipeline)
                runner = PipelineRunner()
                await runner.run(task)
            except Exception as pipecat_exc:
                logger.warning(
                    "Pipecat run raised error (%s) — falling back to custom turn loop to continue call",
                    pipecat_exc,
                )
                await _custom_turn_loop(
                    ws_connection=ws_connection,
                    call_id=call_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    system_prompt=final_prompt,
                    api_keys=api_keys,
                    language=language,
                    voice_config=voice_config,
                    agent=agent,
                    contact_id=contact_id,
                    call_start_block=call_start_block,
                )
        else:
            logger.info("Running custom turn loop (production multi-modal loop with emotion, intent, memory)")
            await _custom_turn_loop(
                ws_connection=ws_connection,
                call_id=call_id,
                agent_id=agent_id,
                org_id=org_id,
                system_prompt=final_prompt,
                api_keys=api_keys,
                language=language,
                voice_config=voice_config,
                agent=agent,
                contact_id=contact_id,
                call_start_block=call_start_block,
            )

    except Exception as exc:
        logger.error("Pipeline error for call %s: %s", call_id, exc)

    finally:
        await _finalize_call(call_id)


# ---------------------------------------------------------------------------
# Custom turn loop (production multi-modal loop)
# ---------------------------------------------------------------------------

_format_t2_facts = format_t2_facts


async def _custom_turn_loop(
    ws_connection,
    call_id: str,
    agent_id: str,
    org_id: str,
    system_prompt: str,
    api_keys: Dict[str, str],
    language: str,
    voice_config: Dict[str, Any],
    agent: Optional[Dict[str, Any]] = None,
    contact_id: Optional[str] = None,
    call_start_block: str = "",
) -> None:
    """
    Custom WebSocket turn loop with multi-modal parallel fan-out
    (emotion, intent, memory), tone adaptation, and active tool execution.
    """
    logger.info("Running custom turn loop for call %s (org_id=%s, agent_id=%s)", call_id, org_id, agent_id)
    initial_prompt = f"{call_start_block}\n\n{system_prompt}" if call_start_block else system_prompt
    conversation: list = [{"role": "system", "content": initial_prompt}]
    turn_idx = 0
    emotion_config: Dict[str, Any] = (agent or {}).get("emotion_config") or {}
    hume_key = api_keys.get("hume") or api_keys.get("hume_api_key")
    vad = VoiceActivityDetector(
        sample_rate=8000,
        frame_duration_ms=settings.VAD_FRAME_MS,
        energy_threshold=settings.VAD_ENERGY_THRESHOLD,
        silence_duration_ms=settings.VAD_SILENCE_MS,
        min_utterance_ms=settings.VAD_MIN_MS,
        max_utterance_ms=settings.VAD_MAX_MS,
    )

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws_connection.receive(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.info("Call %s timed out after 5 minutes of silence", call_id)
                break

            if data.get("type") == "websocket.disconnect":
                logger.info("WebSocket disconnected for call %s", call_id)
                break

            if data.get("type") == "websocket.receive":
                raw = data.get("text") or data.get("bytes", "")
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else {}
                except Exception:
                    continue

                if payload.get("event") == "media":
                    audio_b64 = payload.get("media", {}).get("payload", "")
                    if not audio_b64:
                        continue

                    import base64
                    mulaw_bytes = base64.b64decode(audio_b64)
                    pcm8k = mulaw_to_pcm16(mulaw_bytes)
                    utterance_pcm = vad.process_frame(pcm8k)
                    if not utterance_pcm:
                        continue

                    turn_idx += 1

                    with stage("turn_total", call_id, turn_idx):
                        # Resample 8 kHz to 16 kHz and encapsulate in valid WAV container
                        pcm16k = resample_pcm16(utterance_pcm, 8000, 16000)
                        wav_bytes = pcm16_to_wav(pcm16k, sample_rate=16000, num_channels=1)

                        # 1. STT Transcription Stage
                        with stage("stt", call_id, turn_idx):
                            transcript = await _stt_transcribe(wav_bytes, language, api_keys)
                        if not transcript:
                            continue

                        # 2. Shared Multi-Modal Turn Steps (Emotion, Intent, Memory, Tone, Prompt, TTS)
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
                            contact_name="Caller",
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

                        conversation.append({"role": "user", "content": transcript})
                        ts = int(time.time() * 1000)

                        # 3. LLM Generation & TTS Synthesis Stage (Streaming with fallback)
                        llm_kwargs = {}
                        if active_tools:
                            llm_kwargs["tools"] = active_tools

                        stream_sid = payload.get("streamSid", "")
                        tts_emotion_state = (
                            fused_emotion
                            if emotion_config.get("emotion_conditioned_voice") and hume_key
                            else None
                        )
                        streaming_succeeded = False
                        reply = ""
                        tool_calls = None

                        # Only attempt token-level streaming if tools are not required
                        if not active_tools:
                            try:
                                t_llm = stage("llm_ttft", call_id, turn_idx)
                                t_llm.__enter__()
                                first_token_seen = False
                                tokens_accumulated: List[str] = []
                                sentence_buffer = ""
                                first_sentence = None
                                remaining_sentences: List[str] = []

                                stream_iter = llm_service.generate_stream(
                                    prompt=turn_prompt,
                                    messages=conversation[1:],
                                    api_keys=api_keys,
                                )

                                async for token in stream_iter:
                                    if not first_token_seen:
                                        first_token_seen = True
                                        t_llm.__exit__(None, None, None)
                                    tokens_accumulated.append(token)
                                    sentence_buffer += token

                                    if first_sentence is None and _has_sentence_end(sentence_buffer):
                                        first_sentence, sentence_buffer = _split_first_sentence(sentence_buffer)

                                if not first_token_seen:
                                    t_llm.__exit__(None, None, None)

                                if first_token_seen:
                                    if first_sentence is None:
                                        first_sentence = sentence_buffer.strip()
                                        sentence_buffer = ""
                                    elif sentence_buffer.strip():
                                        remaining_sentences.append(sentence_buffer.strip())

                                    reply = "".join(tokens_accumulated).strip()

                                    # Trigger streaming TTS starting at first complete sentence
                                    if first_sentence:
                                        t_tts = stage("tts_ttfab", call_id, turn_idx)
                                        t_tts.__enter__()
                                        first_audio_seen = False

                                        # Synthesize first sentence
                                        async for chunk in synthesize_speech_stream(
                                            first_sentence,
                                            tts_config or voice_config,
                                            api_keys,
                                            emotion_state=tts_emotion_state,
                                        ):
                                            if not first_audio_seen:
                                                first_audio_seen = True
                                                t_tts.__exit__(None, None, None)
                                            await _send_media_to_ws(ws_connection, stream_sid, chunk)

                                        if not first_audio_seen:
                                            t_tts.__exit__(None, None, None)

                                        # Synthesize any remaining sentences
                                        for rem_sent in remaining_sentences:
                                            async for chunk in synthesize_speech_stream(
                                                rem_sent,
                                                tts_config or voice_config,
                                                api_keys,
                                                emotion_state=tts_emotion_state,
                                            ):
                                                await _send_media_to_ws(ws_connection, stream_sid, chunk)

                                        if first_audio_seen:
                                            streaming_succeeded = True

                            except Exception as stream_exc:
                                logger.warning("Streaming pipeline error: %s — falling back to blocking path", stream_exc)
                                streaming_succeeded = False

                        # 4. Fallback: Blocking LLM + Blocking TTS path
                        if not streaming_succeeded:
                            with stage("llm", call_id, turn_idx):
                                try:
                                    llm_res = await llm_service.generate(
                                        prompt=turn_prompt,
                                        messages=conversation[1:],
                                        api_keys=api_keys,
                                        **llm_kwargs,
                                    )
                                except Exception as llm_exc:
                                    logger.error("LLM error: %s", llm_exc)
                                    llm_res = "I'm sorry, I'm having trouble responding right now."

                            if isinstance(llm_res, dict):
                                reply = llm_res.get("content") or ""
                                tool_calls = llm_res.get("tool_calls")
                            else:
                                reply = str(llm_res or "")

                            # Handle Tool Calls if generated by LLM
                            if tool_calls:
                                for tc in tool_calls:
                                    func = tc.get("function", {})
                                    t_name = func.get("name", "")
                                    t_args_raw = func.get("arguments", {})
                                    if isinstance(t_args_raw, str):
                                        try:
                                            t_args = json.loads(t_args_raw)
                                        except Exception:
                                            t_args = {}
                                    else:
                                        t_args = t_args_raw or {}

                                    conversation.append({
                                        "role": "assistant",
                                        "content": reply,
                                        "tool_calls": [tc],
                                    })

                                    # Execute tool call
                                    tool_result_str = await handle_tool_call(t_name, t_args, org_id, agent_id)

                                    conversation.append({
                                        "role": "tool",
                                        "tool_call_id": tc.get("id", "call_1"),
                                        "name": t_name,
                                        "content": tool_result_str,
                                    })

                                    # Make one more LLM call to get final spoken response
                                    try:
                                        final_llm_res = await llm_service.generate(
                                            prompt=turn_prompt,
                                            messages=conversation[1:],
                                            api_keys=api_keys,
                                        )
                                        if isinstance(final_llm_res, dict):
                                            reply = final_llm_res.get("content") or ""
                                        else:
                                            reply = str(final_llm_res or "")
                                    except Exception as exc2:
                                        logger.error("Error in post-tool LLM response: %s", exc2)
                                        reply = reply or "I completed the action."

                            # Blocking TTS Speech Synthesis Stage
                            with stage("tts", call_id, turn_idx):
                                audio_out = await _tts_synthesize(
                                    reply, tts_config or voice_config, api_keys, emotion_state=tts_emotion_state
                                )

                            # Network Out Stage
                            with stage("network_out", call_id, turn_idx):
                                if audio_out:
                                    await _send_media_to_ws(ws_connection, stream_sid, audio_out)

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

                            await _append_turn_to_redis(call_id, "user", transcript, ts, emotion_state=fused_emotion)
                            await _append_turn_to_redis(call_id, "assistant", reply, ts2)

                elif payload.get("event") == "stop":
                    logger.info("Twilio stream stopped for call %s", call_id)
                    break

    except Exception as exc:
        logger.error("Fallback loop error for call %s: %s", call_id, exc)


# Backward compatibility alias
_minimal_echo_loop = _custom_turn_loop


# ---------------------------------------------------------------------------
# Call finalization
# ---------------------------------------------------------------------------

async def _finalize_call(call_id: str) -> None:
    logger.info("Finalizing call: %s", call_id)

    try:
        mem = await short_term.get_call_memory(call_id)
        transcript_json = json.dumps(mem["turns"]) if mem and "turns" in mem else "[]"

        if supabase:
            supabase.table("calls").update(
                {"status": "completed", "transcript": transcript_json}
            ).eq("id", call_id).execute()

    except Exception as exc:
        logger.error("Failed to finalize call transcript: %s", exc)

    try:
        if livekit_service.is_configured():
            await livekit_service.delete_room(call_id)
    except Exception as exc:
        logger.warning("LiveKit room cleanup failed: %s", exc)
