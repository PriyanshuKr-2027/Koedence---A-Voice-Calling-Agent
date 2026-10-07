from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from typing import Any, Dict, List, Optional
from uuid import UUID
import time
import logging
from app.models.schemas import (
    CallCreate, CallUpdate, CallResponse, LiveKitTokenRequest, LiveKitTokenResponse
)
from app.routers.auth import require_authenticated_user
from app.core.tokens import verify_call_stream_token
from app.services.supabase_client import supabase
from app.core.config import settings
from livekit import api as livekit_api
from app.services.livekit_service import livekit_service
from app.services.telephony import telephony_service
from app.services.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["Calls"])

@router.get("", response_model=List[CallResponse])
async def list_calls(
    org_id: UUID,
    agent_id: Optional[UUID] = None,
    direction: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot access calls of another organization",
        )
    effective_org = current_user["org_id"]
    if not supabase:
        return []
    query = supabase.table("calls").select("*").eq("org_id", str(effective_org))
    if agent_id:
        query = query.eq("agent_id", str(agent_id))
    if direction and direction.lower() != "all":
        query = query.eq("direction", direction)

    res = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
    return res.data or []

@router.post("", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
async def create_call(
    call: CallCreate,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    payload = call.model_dump(mode="json")
    payload["org_id"] = current_user["org_id"]
    res = supabase.table("calls").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to record call")
    return res.data[0]

@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("calls").select("*").eq("id", str(call_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Call record not found")
    if str(res.data.get("org_id")) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: call belongs to another organization",
        )
    return res.data


@router.get("/{call_id}/memory")
async def get_call_memory_debug(
    call_id: UUID,
    org_id: Optional[UUID] = None,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Debug endpoint for inspecting active/recent call short-term memory from Redis.
    Performs org-scoped authorization check.
    """
    from app.services.memory import short_term

    if supabase:
        res = supabase.table("calls").select("org_id").eq("id", str(call_id)).execute()
        if res.data and str(res.data[0].get("org_id")) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access to call memory"
            )
        if not res.data and org_id and str(org_id) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access to call memory"
            )

    memory = await short_term.get_call_memory(str(call_id))
    if memory is None:
        return {
            "call_id": str(call_id),
            "turns": [],
            "emotion_events": [],
            "status": "empty_or_expired",
        }
    return memory

@router.post("/token", response_model=LiveKitTokenResponse)
async def generate_livekit_token(
    req: LiveKitTokenRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Generates a LiveKit JWT token for connecting to real-time voice call rooms.
    """
    api_key = settings.LIVEKIT_API_KEY
    api_secret = settings.LIVEKIT_API_SECRET
    livekit_url = settings.LIVEKIT_URL

    if not api_key or not api_secret:
        dummy_token = f"dev_token_{req.room_name}_{req.participant_name}_{int(time.time())}"
        return LiveKitTokenResponse(
            token=dummy_token,
            room_name=req.room_name,
            livekit_url=livekit_url or "wss://livekit.example.com",
        )

    try:
        grant = livekit_api.VideoGrants(
            room_join=True,
            room=req.room_name,
            can_publish=True,
            can_subscribe=True,
        )
        token = (
            livekit_api.AccessToken(api_key, api_secret)
            .with_identity(req.participant_name)
            .with_name(req.participant_name)
            .with_grants(grant)
            .to_jwt()
        )
        return LiveKitTokenResponse(
            token=token,
            room_name=req.room_name,
            livekit_url=livekit_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate LiveKit token: {str(e)}")


# ---------------------------------------------------------------------------
# WebSocket: Twilio Media Stream bridge → VoCall pipeline
# ---------------------------------------------------------------------------

@router.websocket("/stream/{call_id}")
async def call_stream(
    websocket: WebSocket,
    call_id: str,
    token: Optional[str] = None,
    exp: Optional[int] = None,
    agent_id: str = "",
    contact_id: str = "",
):
    """
    WebSocket endpoint that Twilio's <Stream> connects to.
    Requires HMAC token and exp in URL query parameters.
    """
    query_params = dict(websocket.query_params)
    token_val = token or query_params.get("token")
    exp_val = exp if exp is not None else query_params.get("exp")

    is_valid = False
    if token_val and exp_val:
        try:
            is_valid = verify_call_stream_token(str(call_id), token_val, int(exp_val))
        except (ValueError, TypeError):
            is_valid = False

    if not is_valid:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket stream opened: call_id=%s agent_id=%s", call_id, agent_id)

    try:
        from app.services.voice_pipeline import start_pipeline
        await start_pipeline(
            call_id=call_id,
            agent_id=agent_id,
            contact_id=contact_id or None,
            ws_connection=websocket,
        )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: call_id=%s", call_id)
    except Exception as exc:
        logger.error("Pipeline error for call %s: %s", call_id, exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Web Call — browser-to-LiveKit test calls
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel
from fastapi.responses import StreamingResponse
import asyncio as _asyncio
import json as _json
import uuid as _uuid_mod
import time as _time_mod


class WebCallStartRequest(_BaseModel):
    agent_id: str
    org_id: str
    participant_name: str = "tester"
    contact_name: str = "Test User"


class WebCallStartResponse(_BaseModel):
    call_id: str
    room_name: str
    token: str
    livekit_url: str


@router.post("/webcall/start", response_model=WebCallStartResponse)
async def start_webcall(
    req: WebCallStartRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    req.org_id = current_user["org_id"]
    """
    Starts a browser-to-LiveKit web call.

    Steps:
    1. Creates a LiveKit room
    2. Generates a browser participant token
    3. Spawns the webcall pipeline as a background task
    4. Inserts a call record (is_test=True) in Supabase
    5. Returns connection details to the browser
    """
    from app.services.webcall_pipeline import run_webcall_agent, register_webcall_task

    call_id = str(_uuid_mod.uuid4())
    room_name = livekit_service._room_name(call_id)

    # Create LiveKit room
    try:
        await livekit_service.create_room(call_id)
    except Exception as exc:
        logger.error("Failed to create LiveKit room for webcall: %s", exc)
        raise HTTPException(status_code=503, detail=f"LiveKit unavailable: {exc}")

    # Browser participant token
    try:
        token = livekit_service.generate_test_token(room_name, req.participant_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Token generation failed: {exc}")

    # Resolve contact: find by name in org, or create new one
    # This gives webcall access to all 4 memory tiers (short-term, long-term, episodic, graph)
    contact_id: Optional[str] = None
    if supabase and req.contact_name:
        try:
            name_clean = req.contact_name.strip()
            # Case-insensitive name lookup within the org
            existing = (
                supabase.table("contacts")
                .select("id, name")
                .eq("org_id", req.org_id)
                .ilike("name", name_clean)
                .limit(1)
                .execute()
            )
            if existing.data:
                contact_id = existing.data[0]["id"]
                logger.info("Webcall: matched existing contact %s (%s)", name_clean, contact_id)
            else:
                # Create a new contact entry for this name
                new_contact = (
                    supabase.table("contacts")
                    .insert({
                        "org_id": req.org_id,
                        "name": name_clean,
                        "phone": None,
                        "email": None,
                        "tags": ["web-call"],
                    })
                    .execute()
                )
                if new_contact.data:
                    contact_id = new_contact.data[0]["id"]
                    logger.info("Webcall: created new contact %s (%s)", name_clean, contact_id)
        except Exception as exc:
            logger.warning("Webcall contact lookup/create failed (non-fatal): %s", exc)

    # Insert call record
    if supabase:
        try:
            supabase.table("calls").insert({
                "id": call_id,
                "agent_id": req.agent_id,
                "org_id": req.org_id,
                "contact_id": contact_id,
                "direction": "web",
                "status": "in_progress",
                "is_test": True,
                "from_number": "web-browser",
                "to_number": "agent",
                "started_at": "now()",
            }).execute()
        except Exception as exc:
            logger.warning("Failed to insert webcall record: %s", exc)

    # Spawn pipeline background task (now with contact_id for memory retrieval)
    task = _asyncio.create_task(
        run_webcall_agent(
            call_id=call_id,
            agent_id=req.agent_id,
            org_id=req.org_id,
            contact_id=contact_id,
            contact_name=req.contact_name.strip(),
        )
    )
    register_webcall_task(call_id, task)

    return WebCallStartResponse(
        call_id=call_id,
        room_name=room_name,
        token=token,
        livekit_url=settings.LIVEKIT_URL or "wss://livekit.example.com",
    )


@router.get("/webcall/{call_id}/events")
async def webcall_sse_events(call_id: str):
    """
    Server-Sent Events stream delivering real-time transcript turns.

    Events pushed by webcall_pipeline.py via Redis list `webcall:{call_id}:events`.
    Closes automatically when an event of type=status state=ended is received.

    Frontend usage:
        const es = new EventSource(`/api/v1/calls/webcall/${callId}/events`);
        es.onmessage = (e) => { const ev = JSON.parse(e.data); ... };
    """
    async def event_generator():
        key = f"webcall:{call_id}:events"
        cursor = 0
        idle_ticks = 0
        MAX_IDLE = 600  # 10 min total

        yield f"data: {_json.dumps({'type': 'connected', 'call_id': call_id})}\n\n"

        while idle_ticks < MAX_IDLE:
            try:
                events = await redis_client.lrange(key, cursor, -1)
            except Exception:
                events = []

            if events:
                for raw in events:
                    try:
                        ev = _json.loads(raw)
                    except Exception:
                        continue
                    yield f"data: {_json.dumps(ev)}\n\n"
                    if ev.get("type") == "status" and ev.get("state") == "ended":
                        return
                cursor += len(events)
                idle_ticks = 0
            else:
                idle_ticks += 1

            await _asyncio.sleep(0.5)

        yield f"data: {_json.dumps({'type': 'status', 'state': 'timeout'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete("/webcall/{call_id}/end")
async def end_webcall(
    call_id: str,
    org_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Terminates a running web call.

    1. Cancels the pipeline asyncio.Task
    2. Deletes the LiveKit room
    3. Updates the call record: status=completed, duration_seconds, ended_at
    4. Returns final duration so the frontend can display it
    """
    if org_id and str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot end call of another organization",
        )
    if supabase:
        check_res = supabase.table("calls").select("org_id").eq("id", call_id).execute()
        if check_res.data and str(check_res.data[0].get("org_id")) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: call belongs to another organization",
            )

    from app.services.webcall_pipeline import cancel_webcall_task

    cancelled = cancel_webcall_task(call_id)

    # Compute duration from call record
    duration_seconds = 0
    if supabase:
        try:
            res = supabase.table("calls").select("started_at").eq("id", call_id).single().execute()
            if res.data and res.data.get("started_at"):
                import datetime
                started = datetime.datetime.fromisoformat(
                    res.data["started_at"].replace("Z", "+00:00")
                )
                delta = datetime.datetime.now(datetime.timezone.utc) - started
                duration_seconds = max(0, int(delta.total_seconds()))
        except Exception as exc:
            logger.warning("Could not compute call duration: %s", exc)

        try:
            supabase.table("calls").update({
                "status": "completed",
                "duration_seconds": duration_seconds,
            }).eq("id", call_id).execute()
        except Exception as exc:
            logger.warning("Failed to update webcall record on end: %s", exc)

    # Cleanup LiveKit room (also done by pipeline finally block, but belt-and-suspenders)
    try:
        await livekit_service.delete_room(call_id)
    except Exception:
        pass

    return {
        "call_id": call_id,
        "status": "ended",
        "duration_seconds": duration_seconds,
        "pipeline_cancelled": cancelled,
    }


# ---------------------------------------------------------------------------
# Outbound call initiation
# ---------------------------------------------------------------------------

class OutboundCallRequest(CallCreate):
    """Extends CallCreate with the Twilio from_number for outbound dialling."""
    pass

@router.post("/outbound", status_code=status.HTTP_202_ACCEPTED)
async def initiate_outbound_call(
    payload: OutboundCallRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    payload.org_id = UUID(current_user["org_id"])
    """
    Initiates an outbound call via Twilio REST API.
    Creates a calls row and returns the Twilio call SID.
    """
    if not payload.to_number or not payload.from_number:
        raise HTTPException(status_code=400, detail="to_number and from_number are required")
    if not payload.agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required for outbound calls")

    # Create calls row before dialling so pipeline can reference the ID
    call_id: Optional[str] = None
    if supabase:
        try:
            call_data = payload.model_dump(mode="json")
            call_data.update({"direction": "outbound", "status": "initiated"})
            res = supabase.table("calls").insert(call_data).execute()
            if res.data:
                call_id = res.data[0]["id"]
        except Exception as exc:
            logger.error("Failed to create outbound call record: %s", exc)

    # Dial via Twilio
    try:
        call_sid = await telephony_service.initiate_outbound_call(
            to_number=payload.to_number,
            from_number=payload.from_number,
            agent_id=str(payload.agent_id),
            contact_id=str(payload.contact_id) if payload.contact_id else None,
            org_id=str(payload.org_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Twilio error: {exc}")

    return {"call_id": call_id, "call_sid": call_sid, "status": "dialling"}
