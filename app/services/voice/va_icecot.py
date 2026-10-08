"""
Voice-Adapted Intention-Centric Chain-of-Thought (VA-ICECoT) Service (M41)
Real-time per-turn reasoning loop: Emotion -> Intent -> Combined Rules -> Resolution -> LLM Assembly.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.emotion import fusion as emotion_fusion
from app.services.intent import combined_rules, detector as intent_detector, resolver, slot_manager
from app.services.llm import llm_service
from app.services.memory import short_term
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)


async def process_turn(
    transcript_turn: str,
    audio_bytes: Optional[bytes],
    call_id: str,
    contact_id: Optional[str],
    agent: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    memory_block: str = "",
) -> Dict[str, Any]:
    """
    VA-ICECoT full per-turn reasoning chain for real-time voice calls.

    Returns:
        {
          "response_text": str,
          "emotion_state": dict,
          "intent_state": dict,
          "connector_result": dict or None
        }
    """
    agent_config = agent.get("config", {}) if isinstance(agent, dict) else {}
    custom_intents = agent_config.get("intents", [])
    custom_rules = agent_config.get("combined_rules", [])

    # ── STEP 1: Parallel Emotion & Intent Analysis ─────────────────────
    filled_slots = await short_term.get_all_slots(call_id)

    emotion_task = emotion_fusion.fuse(
        transcript_turn=transcript_turn,
        audio_bytes=audio_bytes,
        conversation_history=conversation_history,
    )
    intent_task = intent_detector.detect(
        transcript_turn=transcript_turn,
        emotion_state={},
        conversation_history=conversation_history,
        agent_intents=custom_intents,
        filled_slots=filled_slots,
    )

    emotion_state, intent_state_prelim = await asyncio.gather(
        emotion_task, intent_task, return_exceptions=True
    )

    if isinstance(emotion_state, Exception):
        logger.error("Emotion fusion error in VA-ICECoT: %s", emotion_state)
        emotion_state = {"valence_fused": 0.0, "dominant_fused": "neutral", "confidence": 0.5}

    if isinstance(intent_state_prelim, Exception):
        logger.error("Preliminary intent error in VA-ICECoT: %s", intent_state_prelim)
        intent_state_prelim = {"intent": "general_inquiry", "confidence": 0.5, "slot_data": {}}

    # Re-run intent with emotion context now available (caller_need, issue_category)
    intent_state = await intent_detector.detect(
        transcript_turn=transcript_turn,
        emotion_state=emotion_state,
        conversation_history=conversation_history,
        agent_intents=custom_intents,
        filled_slots=filled_slots,
    )

    # ── STEP 2: Combined Rules Evaluation ──────────────────────────────
    rule_matched = combined_rules.evaluate(
        emotion_state=emotion_state,
        intent_state=intent_state,
        agent_combined_rules=custom_rules,
    )

    connector_result = None
    combined_instruction = None

    if rule_matched:
        combined_instruction = rule_matched.get("instruction")
        rule_action = rule_matched.get("action", "none")

        if rule_action != "none":
            # Fire connector specified by rule
            configured_connectors = get_configured_connectors(agent)
            connector_result = await resolver.resolve(
                intent_state={"intent": rule_action, "confidence": 1.0},
                filled_slots=filled_slots.get(rule_action, {}),
                agent_config=agent_config,
                configured_connectors=configured_connectors,
                contact={"id": contact_id},
                agent=agent,
                call_id=call_id,
            )

        if rule_matched.get("skip_llm_response"):
            response_text = combined_instruction or "Connecting you to a representative now."
            await persist_events(call_id, contact_id, emotion_state, intent_state, connector_result)
            return {
                "response_text": response_text,
                "emotion_state": emotion_state,
                "intent_state": intent_state,
                "connector_result": connector_result,
            }

    # ── STEP 3: Intent Connector Resolution (if slots complete) ──────
    elif intent_state.get("intent") and intent_state.get("confidence", 0) >= float(settings.INTENT_CONFIDENCE_MIN):
        intent_slug = intent_state["intent"]
        new_slots = intent_state.get("slot_data", {})

        # Merge slots
        await slot_manager.merge_slots(call_id, intent_slug, new_slots)
        filled_slots = await short_term.get_all_slots(call_id)
        intent_slots = filled_slots.get(intent_slug, {})

        slot_status = slot_manager.get_slot_status(intent_slug, intent_slots)

        if slot_status["complete"]:
            configured_connectors = get_configured_connectors(agent)
            connector_result = await resolver.resolve(
                intent_state=intent_state,
                filled_slots=intent_slots,
                agent_config=agent_config,
                configured_connectors=configured_connectors,
                contact={"id": contact_id},
                agent=agent,
                call_id=call_id,
            )

    # ── STEP 4: LLM System Prompt Assembly & Response Generation ───────
    tone_instruction = emotion_fusion.get_tone_instruction(emotion_state)
    slot_status_block = slot_manager.build_slot_status_block(call_id, filled_slots)

    system_prompt = build_system_prompt(
        base_prompt=agent.get("system_prompt", "You are a professional voice agent."),
        memory_block=memory_block,
        tone_instruction=tone_instruction,
        combined_instruction=combined_instruction,
        intent_articulation=intent_state.get("intent_articulation"),
        slot_status_block=slot_status_block,
        connector_result=connector_result,
        use_swi=True,
    )

    llm_messages = list(conversation_history or [])
    llm_messages.append({"role": "user", "content": transcript_turn})

    response_text = await llm_service.generate(
        prompt=system_prompt,
        messages=llm_messages,
    )

    # Clean SWI <INTENT> tag from final TTS audio prompt if preferred, but log intent
    await short_term.write_turn(
        call_id,
        {
            "role": "user",
            "content": transcript_turn,
            "emotion": emotion_state,
            "intent": intent_state,
        },
    )
    await short_term.write_turn(
        call_id,
        {
            "role": "assistant",
            "content": response_text,
        },
    )

    await persist_events(call_id, contact_id, emotion_state, intent_state, connector_result)

    return {
        "response_text": response_text,
        "emotion_state": emotion_state,
        "intent_state": intent_state,
        "connector_result": connector_result,
    }


def build_system_prompt(
    base_prompt: str,
    memory_block: str,
    tone_instruction: Optional[str],
    combined_instruction: Optional[str],
    intent_articulation: Optional[str],
    slot_status_block: str,
    connector_result: Optional[Dict[str, Any]],
    use_swi: bool = True,
) -> str:
    """Assembles final system prompt with all injected VA-ICECoT context blocks."""
    blocks = [base_prompt]

    if memory_block and memory_block.strip():
        blocks.append(f"\n{memory_block}")

    if tone_instruction and tone_instruction.strip():
        blocks.append(f"\n{tone_instruction}")

    if combined_instruction and combined_instruction.strip():
        blocks.append(f"\n[COMBINED RULE INSTRUCTION]\n{combined_instruction}")

    if intent_articulation and intent_articulation.strip():
        blocks.append(f"\n[DETECTED INTENT ARTICULATION]\n{intent_articulation}")

    if slot_status_block and slot_status_block.strip():
        blocks.append(f"\n{slot_status_block}")

    if connector_result and connector_result.get("success"):
        blocks.append(
            f"\n[CONNECTOR EXECUTED SUCCESS]\n"
            f"Connector: {connector_result.get('connector_used')}\n"
            f"Message: {connector_result.get('success_message')}"
        )

    if use_swi:
        blocks.append(
            "\n[SWI INSTRUCTION]\n"
            "State an explicit <INTENT>...</INTENT> tag at the very beginning of your response "
            "summarizing your action before speaking naturally to the caller."
        )

    return "\n".join(blocks)


def get_configured_connectors(agent: Dict[str, Any]) -> List[str]:
    """Helper to extract active connector names for an agent."""
    connectors = ["google_calendar", "supabase", "hubspot", "webhook"]
    config = agent.get("config", {}) if isinstance(agent, dict) else {}
    if "configured_connectors" in config and isinstance(config["configured_connectors"], list):
        return config["configured_connectors"]
    return connectors


async def persist_events(
    call_id: str,
    contact_id: Optional[str],
    emotion_state: Dict[str, Any],
    intent_state: Dict[str, Any],
    connector_result: Optional[Dict[str, Any]],
) -> None:
    """Persists emotion and intent events to database tables."""
    if not supabase:
        return

    try:
        # Write emotion event
        if emotion_state:
            supabase.table("emotion_events").insert({
                "call_id": call_id,
                "valence": emotion_state.get("valence_fused", 0.0),
                "arousal": emotion_state.get("arousal_fused", 0.5),
                "dominant": emotion_state.get("dominant_fused", "neutral"),
                "confidence": emotion_state.get("confidence", 0.8),
                "signal_source": emotion_state.get("source", "fused"),
            }).execute()

        # Write intent event
        if intent_state and intent_state.get("intent"):
            supabase.table("intent_events").insert({
                "call_id": call_id,
                "contact_id": contact_id,
                "intent": intent_state.get("intent", "general_inquiry"),
                "confidence": intent_state.get("confidence", 0.0),
                "entities": intent_state.get("entities", []),
                "slot_data": intent_state.get("slot_data", {}),
                "connector_used": connector_result.get("connector_used") if connector_result else None,
                "connector_result": connector_result,
                "emotion_state_at_detection": emotion_state,
                "resolved": bool(connector_result and connector_result.get("success")),
            }).execute()
    except Exception as exc:
        logger.error("Failed to persist turn events for call %s: %s", call_id, exc)
