"""
Twilio webhook handlers for VoCall voice pipeline.

POST /api/v1/webhooks/twilio/inbound  — inbound call entry point
POST /api/v1/webhooks/twilio/status   — call status callback
POST /api/v1/webhooks/livekit/events  — LiveKit room lifecycle events
"""

import hashlib
import hmac
import base64
import urllib.parse
import logging
from typing import Optional

from fastapi import APIRouter, Request, Response, HTTPException, status, Form
from twilio.request_validator import RequestValidator

from app.core.config import settings
from app.services.supabase_client import supabase
from app.services.livekit_service import livekit_service
from app.trigger.post_call_pipeline import post_call_pipeline, trigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_twilio_signature(request: Request, body: bytes) -> bool:
    """
    Validates Twilio's X-Twilio-Signature HMAC-SHA1.
    Skips validation in development when TWILIO_AUTH_TOKEN is not set.
    """
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping signature validation (dev mode)")
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    validator = RequestValidator(auth_token)
    # Parse form params for POST validation
    params: dict = {}
    try:
        params = dict(urllib.parse.parse_qsl(body.decode("utf-8")))
    except Exception:
        pass

    valid = validator.validate(url, params, signature)
    if not valid:
        logger.warning("Invalid Twilio signature for request to %s", url)
    return valid


async def _lookup_or_create_contact(org_id: str, from_number: str) -> Optional[str]:
    """
    Finds an existing contact by phone number within the org, or creates a new one.
    Returns the contact UUID string, or None on failure.
    """
    if not supabase:
        return None
    try:
        res = (
            supabase.table("contacts")
            .select("id")
            .eq("org_id", org_id)
            .eq("phone", from_number)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["id"]

        # Create a new contact record for this caller
        insert_res = (
            supabase.table("contacts")
            .insert({"org_id": org_id, "phone": from_number, "name": from_number})
            .execute()
        )
        if insert_res.data:
            return insert_res.data[0]["id"]
    except Exception as exc:
        logger.error("Error looking up/creating contact: %s", exc)
    return None


async def _lookup_agent_by_number(to_number: str) -> Optional[dict]:
    """
    Resolves a dialled Twilio number to the assigned agent + org.
    Returns the phone_numbers row (joined with agent config) or None.
    """
    if not supabase:
        return None
    try:
        res = (
            supabase.table("phone_numbers")
            .select("id, org_id, agent_id, number, provider")
            .eq("number", to_number)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as exc:
        logger.error("Error looking up agent by phone number: %s", exc)
        return None


# ---------------------------------------------------------------------------
# POST /webhooks/twilio/inbound
# ---------------------------------------------------------------------------

@router.post("/twilio/inbound")
async def twilio_inbound(request: Request):
    """
    Inbound Twilio voice webhook.

    Flow:
      1. Validate Twilio HMAC signature.
      2. Look up agent by called number (To param).
      3. Look up or create contact by caller ID (From param).
      4. Create a calls row with status = 'initiated', direction = 'inbound'.
      5. Create a LiveKit room for this call.
      6. Return TwiML <Stream> pointing to VoCall's WebSocket bridge.
    """
    raw_body = await request.body()

    # 1. Signature validation
    if not _validate_twilio_signature(request, raw_body):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    # Parse form fields
    form = await request.form()
    call_sid: str = form.get("CallSid", "")
    from_number: str = form.get("From", "")
    to_number: str = form.get("To", "")

    logger.info("Inbound call: sid=%s from=%s to=%s", call_sid, from_number, to_number)

    # 2. Resolve agent from phone number
    phone_record = await _lookup_agent_by_number(to_number)
    org_id = phone_record["org_id"] if phone_record else None
    agent_id = phone_record["agent_id"] if phone_record else None

    # 3. Look up or create contact
    contact_id: Optional[str] = None
    if org_id and from_number:
        contact_id = await _lookup_or_create_contact(org_id, from_number)

    # 4. Create calls row in Supabase
    call_id: Optional[str] = None
    if supabase and org_id:
        try:
            call_data = {
                "org_id": org_id,
                "agent_id": agent_id,
                "contact_id": contact_id,
                "direction": "inbound",
                "status": "initiated",
                "from_number": from_number,
                "to_number": to_number,
                "is_test": False,
            }
            ins = supabase.table("calls").insert(call_data).execute()
            if ins.data:
                call_id = ins.data[0]["id"]
                logger.info("Created call record: id=%s", call_id)
        except Exception as exc:
            logger.error("Failed to create call record: %s", exc)

    # 5. Create LiveKit room (non-blocking; errors are logged but don't block TwiML)
    room_name = f"call-{call_id or call_sid}"
    try:
        if livekit_service.is_configured():
            await livekit_service.create_room(room_name)
    except Exception as exc:
        logger.error("LiveKit room creation failed (non-fatal): %s", exc)

    # 6. Build TwiML response — stream audio to VoCall WebSocket bridge
    # The WS URL will be routed to voice_pipeline.py start_pipeline()
    backend_host = settings.BACKEND_PUBLIC_URL or "wss://your-backend.railway.app"
    ws_url = f"{backend_host}/api/v1/calls/stream/{call_id or call_sid}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="call_id" value="{call_id or ''}"/>
            <Parameter name="agent_id" value="{agent_id or ''}"/>
            <Parameter name="contact_id" value="{contact_id or ''}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="text/xml")


# ---------------------------------------------------------------------------
# POST /webhooks/twilio/status
# ---------------------------------------------------------------------------

@router.post("/twilio/status")
async def twilio_status(request: Request):
    """
    Twilio call status callback.
    Updates calls.status and calls.duration_seconds when Twilio reports
    completed / busy / no-answer / failed.
    """
    raw_body = await request.body()

    if not _validate_twilio_signature(request, raw_body):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    form = await request.form()
    call_sid: str = form.get("CallSid", "")
    call_status: str = form.get("CallStatus", "")          # e.g. "completed", "failed"
    call_duration: str = form.get("CallDuration", "0")    # seconds as string (Twilio sends after completion)

    logger.info("Twilio status callback: sid=%s status=%s duration=%ss", call_sid, call_status, call_duration)

    # Map Twilio status strings to VoCall's call status enum
    status_map = {
        "completed": "completed",
        "busy": "failed",
        "no-answer": "failed",
        "failed": "failed",
        "canceled": "failed",
        "in-progress": "in_progress",
        "ringing": "initiated",
        "queued": "initiated",
    }
    vocall_status = status_map.get(call_status, call_status)

    # Update the calls row by matching call_sid stored in a json config column,
    # or fall back to a best-effort from_number+to_number match if needed.
    # For now we match by status update; production implementations store call_sid.
    if supabase:
        try:
            duration_int = int(call_duration) if call_duration.isdigit() else 0
            # Attempt to update by call_sid stored in the calls.analysis JSONB
            update_payload: dict = {
                "status": vocall_status,
                "duration_seconds": duration_int,
            }
            # Try matching call_sid saved in calls.analysis->>'call_sid'
            res = (
                supabase.table("calls")
                .update(update_payload)
                .eq("analysis->>call_sid", call_sid)
                .execute()
            )
            if not (res.data):
                # Fallback: also try by from/to + status=initiated (best-effort)
                from_number = form.get("From", "")
                to_number = form.get("To", "")
                if from_number and to_number:
                    supabase.table("calls").update(update_payload).eq(
                        "from_number", from_number
                    ).eq("to_number", to_number).eq("status", "initiated").execute()
        except Exception as exc:
            logger.error("Failed to update call status: %s", exc)

    # Fire Trigger.dev post-call pipeline task when call completes
    if call_status == "completed" or vocall_status == "completed":
        call_id = form.get("call_id") or call_sid
        agent_id = form.get("agent_id") or ""
        contact_id = form.get("contact_id") or ""
        org_id = form.get("org_id") or ""

        if supabase and call_id:
            try:
                call_res = supabase.table("calls").select("id, agent_id, contact_id, org_id").eq("id", call_id).execute()
                if call_res.data:
                    row = call_res.data[0]
                    agent_id = agent_id or row.get("agent_id", "")
                    contact_id = contact_id or row.get("contact_id", "")
                    org_id = org_id or row.get("org_id", "")
            except Exception as query_exc:
                logger.warning("Could not fetch call metadata for pipeline trigger: %s", query_exc)

        logger.info("Triggering post_call_pipeline for call %s", call_id)
        trigger(post_call_pipeline, {
            "call_id": call_id,
            "agent_id": agent_id,
            "contact_id": contact_id,
            "org_id": org_id,
        })

    return Response(content="", status_code=200)


# ---------------------------------------------------------------------------
# POST /webhooks/livekit/events
# ---------------------------------------------------------------------------

@router.post("/livekit/events")
async def livekit_events(request: Request):
    """
    LiveKit room lifecycle webhook.
    Handles: room_started, participant_joined, participant_left, room_finished.
    On room_finished: marks the call as 'completed'.
    """
    body = await request.json()
    event_type: str = body.get("event", "")
    room_name: str = body.get("room", {}).get("name", "")

    logger.info("LiveKit event: %s room=%s", event_type, room_name)

    if event_type == "room_finished" and room_name.startswith("call-"):
        call_id = room_name.removeprefix("call-")
        if supabase:
            try:
                supabase.table("calls").update({"status": "completed"}).eq("id", call_id).execute()
                logger.info("Marked call %s as completed via LiveKit room_finished", call_id)
            except Exception as exc:
                logger.error("Failed to mark call completed: %s", exc)

    return {"status": "received", "event": event_type}
