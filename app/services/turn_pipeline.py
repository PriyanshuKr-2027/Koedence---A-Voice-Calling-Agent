"""
turn_pipeline.py — Shared per-turn processing for VoCall custom voice & webcall loops.

Consolidates the multi-modal turn flow (Fig. 2 and Eq. 1):
  1. Parallel fan-out:
     - Emotion: text and acoustic analysis fused with fuse_emotion_signals
     - Intent: intent classification, slot extraction & merge, active tools
     - Memory: per-turn T2 pgvector long-term fact retrieval
  2. Tone adaptation based on fused emotional valence & arousal
  3. Prompt assembly (system prompt + call-start T3/T4 + T2 facts + tone + slots)
  4. Frustration threshold connector background dispatch
  5. TTS voice selection
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.latency_stage import stage
from app.services.emotion import (
    analyze_audio_emotion,
    analyze_text_emotion,
    fire_threshold_connectors,
    fuse_emotion_signals,
    get_tone_instruction,
)
from app.services.intent import detector, slot_manager
from app.services.memory.retriever import retrieve_all_memory
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)


def format_t2_facts(facts: list) -> str:
    """Formats retrieved T2 facts for prompt injection."""
    if not facts:
        return ""
    lines = []
    for fact in facts:
        if isinstance(fact, dict):
            c = fact.get("content", "").strip()
            em = fact.get("emotion_state", {}).get("dominant")
            if c:
                lines.append(f"- {c} (emotion: {em})" if em else f"- {c}")
        elif isinstance(fact, str) and fact.strip():
            lines.append(f"- {fact.strip()}")
    if not lines:
        return ""
    return "[RELEVANT FACTS]\n" + "\n".join(lines)


def select_tts_config(agent: Dict[str, Any], language: str = "en") -> Dict[str, Any]:
    """
    Selects TTS provider and voice parameters from agent configuration.
    """
    agent_dict = agent or {}
    voice_provider = agent_dict.get("voice_provider") or agent_dict.get("tts_provider") or "cartesia"
    voice_id = agent_dict.get("voice_id")
    if not voice_id:
        if voice_provider == "sarvam":
            voice_id = "meera"
        elif voice_provider == "cartesia":
            voice_id = "a0e99841-438c-4a64-b679-ae501e7d6091"
        else:
            voice_id = "default"

    agent_cfg = agent_dict.get("config") or {}
    voice_sub = agent_cfg.get("voice") or {}

    return {
        "voice_id": voice_id,
        "voice_provider": voice_provider,
        "language": language or agent_dict.get("language") or "en",
        "speed": voice_sub.get("speed", 1.0),
    }


def assemble_turn_prompt(
    system_prompt: str,
    call_start_block: str = "",
    t2_block: str = "",
    tone_instruction: str = "",
    slot_block: str = "",
) -> str:
    """Assembles prompt parts: base + call-start block + T2 facts + tone + slots."""
    parts = [system_prompt]
    if call_start_block:
        parts.append(call_start_block)
    if t2_block:
        parts.append(t2_block)
    if tone_instruction:
        parts.append(tone_instruction)
    if slot_block:
        parts.append(slot_block)
    return "\n\n".join(p for p in parts if p.strip())


async def get_active_tools(org_id: str, agent_id: str) -> List[Dict[str, Any]]:
    """
    Fetches enabled connector schemas for the agent from connector_configs.
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
            from app.services.connectors.google_cal import (
                TOOL_SCHEMA_BOOK_APPOINTMENT,
                TOOL_SCHEMA_CHECK_AVAILABILITY,
            )
            tools.extend([TOOL_SCHEMA_CHECK_AVAILABILITY, TOOL_SCHEMA_BOOK_APPOINTMENT])
        if "supabase" in enabled_types:
            from app.services.connectors.supabase_conn import TOOL_SCHEMA_QUERY_SUPABASE
            tools.append(TOOL_SCHEMA_QUERY_SUPABASE)
        if "postgres" in enabled_types:
            from app.services.connectors.supabase_conn import TOOL_SCHEMA_QUERY_POSTGRES
            tools.append(TOOL_SCHEMA_QUERY_POSTGRES)
        if "custom_webhook" in enabled_types:
            from app.services.connectors.webhook import TOOL_SCHEMA_FIRE_WEBHOOK
            tools.append(TOOL_SCHEMA_FIRE_WEBHOOK)
        return tools
    except Exception as exc:
        logger.warning("Error fetching active tools for agent %s: %s", agent_id, exc)
        return []


async def handle_tool_call(
    tool_name: str,
    tool_args: Dict[str, Any],
    org_id: str,
    agent_id: str,
) -> str:
    """Dispatches a tool call from LLM output to connector implementations."""
    connector_type = None
    if tool_name in ("check_availability", "book_appointment"):
        connector_type = "google_calendar"
    elif tool_name in ("query_supabase", "query_postgres"):
        connector_type = "supabase" if tool_name == "query_supabase" else "postgres"
    elif tool_name == "fire_webhook":
        connector_type = "custom_webhook"

    if not connector_type:
        return json.dumps({"success": False, "error": f"Unknown tool name '{tool_name}'"})

    config: Dict[str, Any] = {}
    if supabase and org_id:
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


async def execute_shared_turn_steps(
    call_id: str,
    turn_idx: int,
    transcript: str,
    wav_bytes: Optional[bytes],
    agent: Dict[str, Any],
    org_id: str,
    agent_id: str,
    contact_id: Optional[str],
    api_keys: Dict[str, str],
    system_prompt: str,
    call_start_block: str = "",
    contact_name: str = "Caller",
    language: str = "en",
    _retrieve_all_memory=None,
    _analyze_text_emotion=None,
    _analyze_audio_emotion=None,
) -> Dict[str, Any]:
    """
    Executes shared per-turn pipeline steps used by both custom turn loops:
      1. Parallel fan-out:
         - Emotion: text and acoustic analysis fused with fuse_emotion_signals
         - Intent: intent classification, slot extraction & merge, active tools
         - Memory: per-turn T2 pgvector long-term fact retrieval
      2. Tone adaptation based on fused emotional state
      3. Prompt assembly (system + call-start + T2 facts + tone + slots)
      4. Frustration threshold connector background dispatch
      5. TTS voice selection
    """
    groq_key = api_keys.get("groq") or api_keys.get("groq_api_key") or settings.GROQ_API_KEY
    hume_key = api_keys.get("hume") or api_keys.get("hume_api_key")

    retriever_fn = _retrieve_all_memory or retrieve_all_memory
    text_emotion_fn = _analyze_text_emotion or analyze_text_emotion
    audio_emotion_fn = _analyze_audio_emotion or analyze_audio_emotion

    # 1. Parallel fan-out
    async def _run_emotion_branch():
        async with stage("emotion", call_id, turn_idx):
            audio_fut = audio_emotion_fn(wav_bytes, hume_key) if wav_bytes else asyncio.sleep(0, result=None)
            t_em, a_em = await asyncio.gather(
                text_emotion_fn(transcript, groq_key),
                audio_fut,
                return_exceptions=True,
            )
            if isinstance(t_em, Exception):
                t_em = None
            if isinstance(a_em, Exception):
                a_em = None
            fused = fuse_emotion_signals(t_em, a_em)
            return fused, t_em, a_em

    async def _run_intent_branch():
        async with stage("intent", call_id, turn_idx):
            try:
                detected = await detector.detect(
                    transcript_turn=transcript,
                    emotion_state={},
                    agent_intents=(agent or {}).get("intents"),
                )
            except Exception as e_det:
                logger.warning("Intent detection error: %s", e_det)
                detected = {"intent": "unknown", "confidence": 0.0}

            intent_slug = detected.get("intent", "unknown") if isinstance(detected, dict) else "unknown"
            slot_data = detected.get("slot_data") if isinstance(detected, dict) else {}
            slots: Dict[str, Any] = {}
            if intent_slug and intent_slug != "unknown":
                try:
                    slots = await slot_manager.merge_slots(call_id, intent_slug, slot_data or {})
                except Exception as e_slots:
                    logger.warning("Slot merge error: %s", e_slots)
                    slots = {}
            tools = await get_active_tools(org_id, agent_id)
            return intent_slug, slots, tools

    async def _run_memory_branch():
        async with stage("memory", call_id, turn_idx):
            if not getattr(settings, "MEMORY_PER_TURN", True):
                return []
            mem = await retriever_fn(
                contact_id=contact_id,
                org_id=org_id,
                agent_id=agent_id,
                query_text=transcript,
                config={"call_id": call_id},
                enabled_tiers=["t2"],
            )
            return mem.get("long_term", []) if isinstance(mem, dict) else []

    emotion_res, intent_res, memory_res = await asyncio.gather(
        _run_emotion_branch(),
        _run_intent_branch(),
        _run_memory_branch(),
        return_exceptions=True,
    )

    if isinstance(emotion_res, Exception):
        logger.warning("Emotion branch failed: %s", emotion_res)
        fused_emotion = {"dominant": "neutral", "valence": 0.0, "arousal": 0.0}
        text_emotion, audio_emotion = None, None
    else:
        fused_emotion, text_emotion, audio_emotion = emotion_res

    if isinstance(intent_res, Exception):
        logger.warning("Intent branch failed: %s", intent_res)
        intent_slug, slots, active_tools = "unknown", {}, []
    else:
        intent_slug, slots, active_tools = intent_res

    if isinstance(memory_res, Exception):
        logger.warning("Memory branch failed: %s", memory_res)
        t2_facts = []
    else:
        t2_facts = memory_res or []

    # 2. Tone instruction
    agent_dict = agent or {}
    emotion_config = (agent_dict.get("config") or {}).get("emotion") or agent_dict.get("emotion_config") or {}
    instruction = get_tone_instruction(fused_emotion, emotion_config)

    # 3. Prompt assembly
    t2_block = format_t2_facts(t2_facts)
    slot_block = ""
    if intent_slug and intent_slug != "unknown" and slots:
        slot_block = slot_manager.build_slot_status_block(call_id, {intent_slug: slots})

    turn_prompt = assemble_turn_prompt(
        system_prompt=system_prompt,
        call_start_block=call_start_block,
        t2_block=t2_block,
        tone_instruction=instruction,
        slot_block=slot_block,
    )

    # 4. Background frustration connector dispatch
    asyncio.create_task(
        fire_threshold_connectors(
            org_id=org_id,
            agent_id=agent_id,
            call_id=call_id,
            emotion_state=fused_emotion,
            contact={"name": contact_name, "phone": "call"},
            agent=agent,
            last_transcript_line=transcript,
        )
    )

    # 5. TTS voice configuration selection
    tts_config = select_tts_config(agent, language=language)

    return {
        "fused_emotion": fused_emotion,
        "text_emotion": text_emotion,
        "audio_emotion": audio_emotion,
        "intent_slug": intent_slug,
        "slots": slots,
        "active_tools": active_tools,
        "t2_facts": t2_facts,
        "tone_instruction": instruction,
        "turn_prompt": turn_prompt,
        "tts_config": tts_config,
    }
