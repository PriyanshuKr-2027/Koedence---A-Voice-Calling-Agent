from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional, Dict, Any
from uuid import UUID
from app.models.schemas import MemoryLongTermCreate, MemoryLongTermResponse, MemoryEpisodicResponse
from app.services.memory import long_term, episodic
from app.routers.auth import require_authenticated_user

router = APIRouter(prefix="/memory", tags=["Memory (VoCall Original)"])


@router.get("/long-term")
async def get_long_term_memory(
    contact_id: UUID,
    org_id: Optional[UUID] = Query(None),
    query_text: Optional[str] = Query(None, description="Semantic search query text"),
    limit: int = Query(5, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Retrieves long-term memory facts for a contact using pgvector semantic search or recency.
    """
    if org_id and str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot access memory of another organization",
        )
    effective_org = current_user["org_id"]
    from app.services.supabase_client import supabase
    if supabase:
        c_res = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).execute()
        if c_res.data and str(c_res.data[0].get("org_id")) != effective_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: contact belongs to another organization",
            )
    facts = await long_term.retrieve_relevant_facts(
        contact_id=str(contact_id),
        org_id=effective_org,
        query_text=query_text or "",
        limit=limit,
    )
    return {"contact_id": str(contact_id), "org_id": effective_org, "facts": facts}


@router.post("/long-term", status_code=status.HTTP_201_CREATED)
async def store_long_term_memory(
    payload: MemoryLongTermCreate,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Generates embedding vector and stores a new persistent long-term fact.
    """
    if not payload.contact_id:
        raise HTTPException(status_code=400, detail="contact_id is required")

    effective_org = current_user["org_id"]
    from app.services.supabase_client import supabase
    if supabase:
        c_res = supabase.table("contacts").select("org_id").eq("id", str(payload.contact_id)).execute()
        if c_res.data and str(c_res.data[0].get("org_id")) != effective_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: contact belongs to another organization",
            )

    result = await long_term.store_fact(
        contact_id=str(payload.contact_id),
        org_id=effective_org,
        agent_id=str(payload.agent_id) if payload.agent_id else None,
        content=payload.content,
        emotion_state=payload.emotion_state,
        call_id=str(payload.call_id) if payload.call_id else None,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to store long-term memory fact")

    return result


@router.get("/episodic")
async def get_episodic_memory(
    contact_id: UUID,
    org_id: Optional[UUID] = Query(None),
    limit: int = Query(5, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """
    Retrieves recent call episode summaries for a contact.
    """
    if org_id and str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot access memory of another organization",
        )
    effective_org = current_user["org_id"]
    from app.services.supabase_client import supabase
    if supabase:
        c_res = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).execute()
        if c_res.data and str(c_res.data[0].get("org_id")) != effective_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: contact belongs to another organization",
            )
    episodes = await episodic.get_recent_episodes(
        contact_id=str(contact_id),
        org_id=effective_org,
        limit=limit,
    )
    return {"contact_id": str(contact_id), "org_id": effective_org, "episodes": episodes}
