import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def fuse_emotion_signals(
    text: Optional[Dict[str, Any]],
    audio: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Fuses text-based (Groq NLP) and audio-based (Hume AI) emotion signals
    into a single unified emotion state.

    Fusion weighting rules:
      - If audio is available and text is available:
          valence = 0.6 * audio['valence'] + 0.4 * text['valence']
          arousal = 0.6 * audio['arousal'] + 0.4 * text['arousal']
          dominant = audio['dominant'] if audio['confidence'] > 0.6 else text['dominant']
          confidence = max(audio['confidence'], text['confidence'])
      - If audio is available and text is None:
          uses audio signal values directly.
      - If audio is None and text is available:
          uses text signal values directly (text-only mode).
      - If both are None:
          returns fallback neutral state.
    """
    now_ms = int(time.time() * 1000)

    if audio is not None and isinstance(audio, dict):
        audio_val = float(audio.get("valence", 0.0))
        audio_aro = float(audio.get("arousal", 0.5))
        audio_dom = str(audio.get("dominant", "neutral"))
        audio_conf = float(audio.get("confidence", 0.5))

        if text is not None and isinstance(text, dict):
            text_val = float(text.get("valence", 0.0))
            text_aro = float(text.get("arousal", 0.5))
            text_dom = str(text.get("dominant", "neutral"))
            text_conf = float(text.get("confidence", 0.5))

            valence = 0.6 * audio_val + 0.4 * text_val
            arousal = 0.6 * audio_aro + 0.4 * text_aro
            dominant = audio_dom if audio_conf > 0.6 else text_dom
            confidence = max(audio_conf, text_conf)
        else:
            valence = audio_val
            arousal = audio_aro
            dominant = audio_dom
            confidence = audio_conf

    elif text is not None and isinstance(text, dict):
        valence = float(text.get("valence", 0.0))
        arousal = float(text.get("arousal", 0.5))
        dominant = str(text.get("dominant", "neutral"))
        confidence = float(text.get("confidence", 0.5))

    else:
        valence = 0.0
        arousal = 0.5
        dominant = "neutral"
        confidence = 0.0

    valence = round(max(-1.0, min(1.0, valence)), 3)
    arousal = round(max(0.0, min(1.0, arousal)), 3)
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    return {
        "valence": valence,
        "arousal": arousal,
        "dominant": dominant,
        "confidence": confidence,
        "timestamp": now_ms,
    }


async def fire_threshold_connectors(
    org_id: str,
    agent_id: str,
    call_id: str,
    emotion_state: Dict[str, Any],
    contact: Dict[str, Any],
    agent: Dict[str, Any],
    last_transcript_line: str,
) -> None:
    """
    Checks the frustration threshold and fires configured Slack alert or custom webhook.
    1. Fetches connector_configs where connector_type = "slack" and is_enabled = True for this org.
    2. If found and emotion_state["valence"] < -threshold (default 0.7): decrypts config and sends alert.
    3. Checks for custom_webhook connector with notify_on = "frustration" and fires payload.
    """
    if not emotion_state or not isinstance(emotion_state, dict):
        return

    valence = float(emotion_state.get("valence", 0.0))
    agent_config = (agent.get("config") or {}) if isinstance(agent, dict) else {}
    emotion_config = agent_config.get("emotion") or {}
    frustration_threshold = float(emotion_config.get("frustration_threshold", 0.7))

    # Trigger if valence is more negative than -frustration_threshold (e.g. valence < -0.7)
    if valence >= -frustration_threshold:
        return

    frustration_score = abs(valence)
    contact_name = (contact.get("name") if isinstance(contact, dict) else None) or "Caller"
    contact_phone = (
        (contact.get("phone") or contact.get("number")) if isinstance(contact, dict) else None
    ) or "Unknown"
    agent_name = (agent.get("name") if isinstance(agent, dict) else None) or "Voice Agent"

    try:
        from app.services.supabase_client import get_supabase_client
        sb = get_supabase_client() if get_supabase_client else None
    except Exception:
        sb = None

    if not sb or not org_id:
        return

    try:
        from app.utils.encryption import decrypt_dict

        # 1. Slack connector threshold alert
        slack_res = (
            sb.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("connector_type", "slack")
            .eq("is_enabled", True)
            .execute()
        )
        slack_rows = slack_res.data or []
        if slack_rows:
            target_row = slack_rows[0]
            slack_cfg = decrypt_dict(target_row.get("config", {}))
            notify_on = slack_cfg.get("notify_on", "frustration")
            if notify_on in ("frustration", "both"):
                from app.services.connectors.slack import send_frustration_alert

                bot_token = slack_cfg.get("bot_token", "")
                channel_id = slack_cfg.get("channel_id", "")
                if bot_token and channel_id:
                    alert_res = await send_frustration_alert(
                        bot_token=bot_token,
                        channel_id=channel_id,
                        agent_name=agent_name,
                        contact_name=contact_name,
                        contact_phone=contact_phone,
                        call_id=call_id,
                        frustration_score=frustration_score,
                        last_transcript_line=last_transcript_line,
                    )
                    logger.info("Slack frustration alert sent for call %s: %s", call_id, alert_res)

        # 2. Custom webhook connector threshold alert
        wh_res = (
            sb.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .in_("connector_type", ["custom_webhook", "zapier"])
            .eq("is_enabled", True)
            .execute()
        )
        wh_rows = wh_res.data or []
        for row in wh_rows:
            wh_cfg = decrypt_dict(row.get("config", {}))
            if (
                wh_cfg.get("notify_on") == "frustration"
                or wh_cfg.get("notify_on_frustration")
                or wh_cfg.get("include_emotion")
            ):
                from app.services.connectors.webhook import fire_webhook

                url = wh_cfg.get("webhook_url") or wh_cfg.get("url", "")
                if url:
                    payload = {
                        "event": "high_frustration_alert",
                        "call_id": call_id,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "contact_name": contact_name,
                        "contact_phone": contact_phone,
                        "frustration_score": frustration_score,
                        "last_transcript_line": last_transcript_line,
                        "emotion_state": emotion_state,
                    }
                    wh_result = await fire_webhook(
                        url=url,
                        method="POST",
                        headers=wh_cfg.get("headers", {}),
                        payload=payload,
                    )
                    logger.info(
                        "Custom webhook frustration alert fired for call %s: %s",
                        call_id,
                        wh_result,
                    )

    except Exception as exc:
        logger.error("fire_threshold_connectors failed for call %s: %s", call_id, exc)
