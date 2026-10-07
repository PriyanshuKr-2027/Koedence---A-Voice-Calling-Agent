import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.services.connectors import (
    google_cal,
    hubspot,
    salesforce,
    slack,
    supabase_conn,
    webhook,
    whatsapp,
)
from app.services.supabase_client import supabase
from app.utils.encryption import decrypt_dict

logger = logging.getLogger(__name__)


def decrypt_config(raw_config: Any) -> Dict[str, Any]:
    """Decrypts AES-256 JSONB configuration data."""
    return decrypt_dict(raw_config)


async def get_enabled_connectors(org_id: str, types: List[str]) -> List[Dict[str, Any]]:
    """
    Fetches all enabled connector_configs for an organization matching the requested connector types.
    """
    if not supabase or not org_id:
        return []
    try:
        res = (
            supabase.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("is_enabled", True)
            .in_("connector_type", types)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.error("Failed to fetch enabled connectors for org %s: %s", org_id, exc)
        return []


async def fire_post_call_connectors(org_id: str, agent_id: str, call_data: Dict[str, Any]) -> List[Any]:
    """
    Step 8: Fire post-call connectors in parallel using asyncio.gather.

    call_data keys:
      call_id, contact_phone, contact_name, agent_name, call_summary,
      emotion_score, duration_seconds, transcript, structured_data, success_eval
    """
    call_id = call_data.get("call_id")
    if call_id and supabase:
        try:
            call_res = supabase.table("calls").select("post_steps").eq("id", str(call_id)).limit(1).execute()
            if call_res.data and len(call_res.data) > 0:
                steps = call_res.data[0].get("post_steps") or {}
                if isinstance(steps, dict) and steps.get("connectors"):
                    logger.info("Connectors already executed for call_id=%s; skipping duplicate dispatch", call_id)
                    return []
        except Exception as exc:
            logger.warning("Failed checking connector step marker for call %s: %s", call_id, exc)
    target_types = ["hubspot", "salesforce", "postgres", "whatsapp", "zapier", "custom_webhook", "slack"]
    configs = await get_enabled_connectors(org_id, target_types)

    tasks = []
    executed_configs = []

    for config in configs:
        ctype = config.get("connector_type")
        cfg = decrypt_config(config.get("config"))

        if ctype == "hubspot":
            tasks.append(
                hubspot.sync_call_summary(
                    access_token=cfg.get("access_token", ""),
                    contact_phone=call_data.get("contact_phone", ""),
                    call_summary=call_data.get("call_summary", ""),
                    success_eval=call_data.get("success_eval", "completed"),
                    emotion_score=float(call_data.get("emotion_score", 0.0)),
                    call_duration_seconds=int(call_data.get("duration_seconds", 0)),
                )
            )
            executed_configs.append(config)

        elif ctype == "salesforce":
            tasks.append(
                salesforce.sync_call_result(
                    client_id=cfg.get("client_id", ""),
                    client_secret=cfg.get("client_secret", ""),
                    refresh_token=cfg.get("refresh_token", ""),
                    instance_url=cfg.get("instance_url", ""),
                    contact_phone=call_data.get("contact_phone", ""),
                    call_summary=call_data.get("call_summary", ""),
                    disposition=call_data.get("success_eval", "Completed"),
                    emotion_score=float(call_data.get("emotion_score", 0.0)),
                )
            )
            executed_configs.append(config)

        elif ctype == "whatsapp":
            tasks.append(
                whatsapp.send_summary(
                    provider=cfg.get("provider", "twilio"),
                    from_number=cfg.get("from_number", ""),
                    to_number=call_data.get("contact_phone", ""),
                    message_template=cfg.get(
                        "message_template", "Call summary: {call_summary}"
                    ),
                    call_summary=call_data.get("call_summary", ""),
                    agent_name=call_data.get("agent_name", "Agent"),
                    contact_name=call_data.get("contact_name", "Customer"),
                    emotion_score=float(call_data.get("emotion_score", 0.0)),
                    org_id=org_id,
                )
            )
            executed_configs.append(config)

        elif ctype in ("zapier", "custom_webhook"):
            url = cfg.get("webhook_url") or cfg.get("url", "")
            tasks.append(
                webhook.fire_post_call_webhook(
                    url=url,
                    method=cfg.get("method", "POST"),
                    headers=cfg.get("headers", {}),
                    payload_template=cfg.get("payload_template"),
                    call_data=call_data,
                )
            )
            executed_configs.append(config)

        elif ctype == "slack" and cfg.get("notify_on") in ("call_end", "both"):
            tasks.append(
                slack.send_call_summary(
                    bot_token=cfg.get("bot_token", ""),
                    channel_id=cfg.get("channel_id", ""),
                    agent_name=call_data.get("agent_name", "Agent"),
                    contact_name=call_data.get("contact_name", "Customer"),
                    call_summary=call_data.get("call_summary", ""),
                    emotion_score=float(call_data.get("emotion_score", 0.0)),
                    duration_seconds=int(call_data.get("duration_seconds", 0)),
                    call_id=call_data.get("call_id", ""),
                )
            )
            executed_configs.append(config)

    if not tasks:
        logger.info("No active post-call connectors found for org %s", org_id)
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log each result
    for config, result in zip(executed_configs, results):
        ctype_name = config.get("connector_type")
        if isinstance(result, Exception):
            logger.error("Connector %s failed: %s", ctype_name, result)
        else:
            logger.info("Connector %s result: %s", ctype_name, result)

    if call_id and supabase:
        try:
            call_res = supabase.table("calls").select("post_steps").eq("id", str(call_id)).limit(1).execute()
            current_steps = {}
            if call_res.data and len(call_res.data) > 0:
                current_steps = call_res.data[0].get("post_steps") or {}
                if not isinstance(current_steps, dict):
                    current_steps = {}
            current_steps["connectors"] = datetime.now(timezone.utc).isoformat()
            supabase.table("calls").update({"post_steps": current_steps}).eq("id", str(call_id)).execute()
        except Exception as exc:
            logger.warning("Failed recording connector step marker for call %s: %s", call_id, exc)

    return list(results)
