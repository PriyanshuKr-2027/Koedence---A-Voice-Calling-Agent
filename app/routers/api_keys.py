from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, List, Optional
from uuid import UUID
from app.models.schemas import APIKeyCreate, APIKeyResponse
from app.routers.auth import require_authenticated_user
from app.services.supabase_client import supabase

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    org_id: Optional[UUID] = Query(None),
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if org_id and str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot access API keys of another organization",
        )
    effective_org = current_user["org_id"]
    if not supabase:
        return []
    res = supabase.table("api_keys").select("*").eq("org_id", str(effective_org)).execute()
    return res.data or []

@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key: APIKeyCreate,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    payload = key.model_dump(mode="json")
    payload["org_id"] = current_user["org_id"]
    res = supabase.table("api_keys").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to store API key")
    return res.data[0]

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    existing = supabase.table("api_keys").select("org_id").eq("id", str(key_id)).single().execute()
    if existing.data and str(existing.data.get("org_id")) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: API key belongs to another organization",
        )
    supabase.table("api_keys").delete().eq("id", str(key_id)).execute()
    return None
