from fastapi import APIRouter, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import List, Optional
from uuid import UUID
import time
import logging
from app.models.schemas import (
    CallCreate, CallUpdate, CallResponse, LiveKitTokenRequest, LiveKitTokenResponse
)
from app.services.supabase_client import supabase
from app.core.config import settings
from livekit import api as livekit_api
from app.services.livekit_service import livekit_service
from app.services.telephony import telephony_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["Calls"])

@router.get("", response_model=List[CallResponse])
async def list_calls(
    org_id: UUID,
    agent_id: Optional[UUID] = None,
    direction: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    if not supabase:
        return []
    query = supabase.table("calls").select("*").eq("org_id", str(org_id))
    if agent_id:
        query = query.eq("agent_id", str(agent_id))
    if direction and direction.lower() != "all":
        query = query.eq("direction", direction)

    res = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
    return res.data or []

@router.post("", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
async def create_call(call: CallCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("calls").insert(call.model_dump(mode="json")).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to record call")
    return res.data[0]

@router.get("/{call_id}", response_model=CallResponse)
async def get_call(call_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("calls").select("*").eq("id", str(call_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Call record not found")
    return res.data


@router.get("/{call_id}/memory")
async def get_call_memory_debug(call_id: UUID, org_id: Optional[UUID] = None):
    """
    Debug endpoint for inspecting active/recent call short-term memory from Redis.
    Performs org-scoped authorization check if org_id is supplied.
    """
    from app.services.memory import short_term

    if supabase and org_id:
        res = supabase.table("calls").select("org_id").eq("id", str(call_id)).execute()
        if not res.data or str(res.data[0].get("org_id")) != str(org_id):
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
async def generate_livekit_token(req: LiveKitTokenRequest):
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
async def call_stream(websocket: WebSocket, call_id: str, agent_id: str = "", contact_id: str = ""):
    """
    WebSocket endpoint that Twilio's <Stream> connects to.
    Hands off the live WebSocket to voice_pipeline.start_pipeline().

    URL params (passed by TwiML <Parameter> tags):
      call_id    — UUID from calls table
      agent_id   — UUID of the agent handling the call
      contact_id — UUID of the contact (caller)
    """
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
# Outbound call initiation
# ---------------------------------------------------------------------------

class OutboundCallRequest(CallCreate):
    """Extends CallCreate with the Twilio from_number for outbound dialling."""
    pass

@router.post("/outbound", status_code=status.HTTP_202_ACCEPTED)
async def initiate_outbound_call(payload: OutboundCallRequest):
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
