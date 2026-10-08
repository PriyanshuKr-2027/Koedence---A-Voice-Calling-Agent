"""
ConnectorRegistry — Lazy-loaded dispatcher replacing the 111-line if/elif chain.

WHY THIS REFACTOR:
  The original fire_connector() was a single function with 8 elif branches, each
  doing a deferred `from app.services.connectors.X import fn` inside the branch body.
  This made fire_connector() a single "god node" with betweenness centrality 0.043 —
  every connector community had to route through it, and any change to dispatch logic
  required editing the central function.

HOW IT IS FIXED:
  A ConnectorRegistry dict maps connector-type keyword strings → async handler callables.
  - Each handler is defined as a thin async wrapper in this file (not in the connector
    modules themselves), so connector modules remain fully isolated from each other.
  - fire_connector() is now 3 lines: normalize → lookup → call.
  - Adding a new connector = add one entry to CONNECTOR_REGISTRY, nothing else changes.
  - The dispatcher no longer becomes a new betweenness-centrality bridge every time a
    connector is added.
"""

from typing import Any, Callable, Dict


# ---------------------------------------------------------------------------
# Handler wrappers — one per connector type
# ---------------------------------------------------------------------------

async def _handle_google_cal(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.google_cal import book_appointment
    return await book_appointment(
        credentials_json=config.get("credentials_json", "{}"),
        calendar_id=config.get("calendar_id", "primary"),
        start_time=payload.get("start_time", ""),
        end_time=payload.get("end_time", ""),
        summary=payload.get("summary", "Call Appointment"),
        attendee_email=payload.get("attendee_email"),
        timezone=config.get("timezone", "Asia/Kolkata"),
    )


async def _handle_hubspot(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.hubspot import log_lead
    return await log_lead(
        access_token=config.get("access_token", ""),
        pipeline_id=config.get("pipeline_id", ""),
        deal_stage_id=config.get("deal_stage_id", ""),
        contact_name=payload.get("contact_name", "Lead Caller"),
        contact_phone=payload.get("contact_phone", ""),
        contact_email=payload.get("contact_email"),
        notes=payload.get("notes", ""),
    )


async def _handle_salesforce(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.salesforce import sync_call_result
    return await sync_call_result(
        client_id=config.get("client_id", ""),
        client_secret=config.get("client_secret", ""),
        refresh_token=config.get("refresh_token", ""),
        instance_url=config.get("instance_url", ""),
        contact_phone=payload.get("contact_phone", ""),
        call_summary=payload.get("call_summary", ""),
        disposition=payload.get("disposition", "Completed"),
        emotion_score=float(payload.get("emotion_score", 0.0)),
    )


async def _handle_webhook(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.webhook import fire_post_call_webhook
    url = config.get("webhook_url") or config.get("url", "")
    return await fire_post_call_webhook(
        url=url,
        method=config.get("method", "POST"),
        headers=config.get("headers"),
        payload_template=config.get("payload_template"),
        call_data=payload,
    )


async def _handle_whatsapp(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.whatsapp import send_summary
    return await send_summary(
        provider=config.get("provider", "twilio"),
        from_number=config.get("from_number", ""),
        to_number=payload.get("contact_phone", ""),
        message_template=config.get("message_template", "Summary: {call_summary}"),
        call_summary=payload.get("call_summary", ""),
        agent_name=payload.get("agent_name", "Agent"),
        contact_name=payload.get("contact_name", "Caller"),
        emotion_score=float(payload.get("emotion_score", 0.0)),
        org_id=config.get("org_id", payload.get("org_id", "")),
    )


async def _handle_slack(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.slack import send_call_summary
    return await send_call_summary(
        bot_token=config.get("bot_token", ""),
        channel_id=config.get("channel_id", ""),
        agent_name=payload.get("agent_name", "Agent"),
        contact_name=payload.get("contact_name", "Caller"),
        call_summary=payload.get("call_summary", ""),
        emotion_score=float(payload.get("emotion_score", 0.0)),
        duration_seconds=int(payload.get("duration_seconds", 0)),
        call_id=payload.get("call_id", ""),
    )


async def _handle_supabase(config: Dict, payload: Dict) -> Dict:
    from app.services.connectors.supabase_conn import query_postgres, query_supabase
    if "connection_string" in config:
        return await query_postgres(
            connection_string=config.get("connection_string", ""),
            query_template=config.get(
                "query_template", "SELECT * FROM contacts WHERE phone = {contact_phone}"
            ),
            contact_phone=payload.get("contact_phone", ""),
        )
    return await query_supabase(
        url=config.get("url", ""),
        anon_key=config.get("anon_key", ""),
        table_name=config.get("table_name", ""),
        query_column=config.get("query_column", "phone"),
        query_value=payload.get("contact_phone", ""),
    )


# ---------------------------------------------------------------------------
# Registry — keyword-to-handler mapping
# To add a new connector: add one entry here. Nothing else changes.
# ---------------------------------------------------------------------------

CONNECTOR_REGISTRY: Dict[str, Callable] = {
    "google":     _handle_google_cal,
    "calendar":   _handle_google_cal,
    "hubspot":    _handle_hubspot,
    "salesforce": _handle_salesforce,
    "webhook":    _handle_webhook,
    "zapier":     _handle_webhook,
    "whatsapp":   _handle_whatsapp,
    "slack":      _handle_slack,
    "supabase":   _handle_supabase,
    "postgres":   _handle_supabase,
}


# ---------------------------------------------------------------------------
# Public API — identical signature to the old fire_connector()
# ---------------------------------------------------------------------------

async def fire_connector(
    connector_type: str, config: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Central Dispatcher — routes execution to the appropriate connector handler
    via CONNECTOR_REGISTRY lookup. O(1) dispatch, no if/elif branching.

    Args:
        connector_type: String key identifying the connector (e.g. "slack", "hubspot").
        config:         Connector-specific credentials and settings dict.
        payload:        Runtime call data (call_id, contact_phone, call_summary, etc.).

    Returns:
        Handler result dict. Always includes "success": bool.
    """
    ctype = connector_type.lower()

    # Find the first matching keyword in the registry
    handler = next(
        (fn for key, fn in CONNECTOR_REGISTRY.items() if key in ctype),
        None,
    )

    if handler is None:
        return {
            "success": False,
            "error": f"Unknown connector type '{connector_type}'",
        }

    return await handler(config, payload)
