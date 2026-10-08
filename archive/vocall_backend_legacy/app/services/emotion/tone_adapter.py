import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_tone_instruction(
    emotion_state: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Generates real-time prompt instruction modifier based on caller's detected emotion.

    Args:
        emotion_state: Fused emotion dict containing 'valence', 'arousal', etc.
        config: Agent emotion config dictionary (agent.config.emotion).

    Returns:
        str: Specific tone adaptation prompt instruction to prepend to LLM prompt.
        None: If tone_adaptation is disabled or valence doesn't trigger adaptation.
    """
    if not config or not isinstance(config, dict):
        return None

    if not config.get("tone_adaptation"):
        return None

    if not emotion_state or not isinstance(emotion_state, dict):
        return None

    v = float(emotion_state.get("valence", 0.0))

    if v < -0.6:
        return (
            "The caller is very frustrated. Be extremely empathetic. "
            "Acknowledge their frustration explicitly before responding. "
            "Slow down. Use shorter sentences."
        )
    elif v < -0.4:
        return "The caller seems unhappy. Be extra empathetic and patient."
    elif v > 0.6:
        return "The caller is in a good mood. Be warm and conversational."

    return None


async def fire_frustration_connector(
    agent: Dict[str, Any],
    call_id: str,
    emotion_state: Dict[str, Any],
) -> None:
    """
    Triggers the configured on_frustration_connector asynchronously when caller frustration is detected.

    Executes safely in background task. Never raises or interrupts voice pipeline.
    """
    try:
        if not agent or not isinstance(agent, dict):
            return

        agent_config = agent.get("config") or {}
        emotion_config = agent_config.get("emotion") or {}
        connector_target = emotion_config.get("on_frustration_connector")

        if not connector_target:
            logger.debug("No on_frustration_connector configured for agent %s", agent.get("id"))
            return

        logger.info(
            "Frustration threshold exceeded for call %s (valence=%.2f) — triggering connector %s",
            call_id,
            emotion_state.get("valence", 0.0),
            connector_target,
        )

        from app.services.supabase_client import supabase
        from app.services.connectors.dispatcher import fire_connector

        connector_type = str(connector_target)
        connector_config = {}

        if supabase:
            try:
                # Query connector by ID if a UUID is provided
                res = supabase.table("connectors").select("*").eq("id", connector_target).execute()
                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    connector_type = row.get("type", connector_target)
                    connector_config = row.get("config", {})
            except Exception as db_exc:
                logger.warning("Supabase connector lookup error for %s: %s", connector_target, db_exc)

        payload = {
            "event": "frustration_threshold_exceeded",
            "call_id": call_id,
            "agent_id": agent.get("id"),
            "agent_name": agent.get("name"),
            "emotion_state": emotion_state,
        }

        res = await fire_connector(connector_type, connector_config, payload)
        logger.info("Frustration connector executed for call %s: %s", call_id, res)

    except Exception as exc:
        logger.error("fire_frustration_connector failed for call %s: %s", call_id, exc)
