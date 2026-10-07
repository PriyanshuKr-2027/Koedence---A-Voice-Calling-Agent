from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.services.supabase_client import supabase
from app.services.memory import short_term
from app.routers.auth import require_authenticated_user

router = APIRouter(prefix="/emotion", tags=["Emotion (VoCall Original)"])


@router.get("/events/{call_id}")
async def get_emotion_events(
    call_id: str,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Retrieves recorded emotion events for a call.
    Checks Redis short-term memory first, falling back to Supabase emotion_events table.
    """
    from app.services.supabase_client import supabase as sb_client
    if sb_client:
        call_res = sb_client.table("calls").select("org_id").eq("id", call_id).execute()
        if call_res.data and isinstance(call_res.data, list) and len(call_res.data) > 0 and isinstance(call_res.data[0], dict):
            if str(call_res.data[0].get("org_id")) != current_user["org_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: call belongs to another organization",
                )

    # 1. Check Redis short-term memory
    mem = await short_term.get_call_memory(call_id)
    if mem and "emotion_events" in mem and mem["emotion_events"]:
        return {"call_id": call_id, "events": mem["emotion_events"], "source": "redis"}

    # 2. Fall back to Supabase emotion_events table
    if sb_client:
        try:
            res = (
                sb_client.table("emotion_events")
                .select("*")
                .eq("call_id", call_id)
                .order("timestamp_ms", ascending=True)
                .execute()
            )
            events_data = res.data if isinstance(res.data, list) else []
            return {"call_id": call_id, "events": events_data, "source": "supabase"}
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve emotion events: {exc}",
            )

    return {"call_id": call_id, "events": [], "source": "none"}


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def record_emotion_event(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Manually records an emotion event to Supabase and Redis.
    """
    call_id = payload.get("call_id")
    if not call_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="call_id is required",
        )

    if supabase:
        call_res = supabase.table("calls").select("org_id").eq("id", call_id).execute()
        if call_res.data and str(call_res.data[0].get("org_id")) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: call belongs to another organization",
            )

    event_data = {
        "call_id": call_id,
        "timestamp_ms": payload.get("timestamp_ms"),
        "valence": payload.get("valence"),
        "arousal": payload.get("arousal"),
        "dominant": payload.get("dominant"),
        "confidence": payload.get("confidence"),
        "signal_source": payload.get("signal_source", "manual"),
    }

    # Store in Redis
    await short_term.append_emotion_event(call_id, event_data)

    # Store in Supabase
    if supabase:
        try:
            res = supabase.table("emotion_events").insert(event_data).execute()
            return res.data[0] if res.data else event_data
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to record emotion event: {exc}",
            )

    return event_data
