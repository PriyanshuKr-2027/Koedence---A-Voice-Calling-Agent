from fastapi import APIRouter, HTTPException, status
from typing import List
from uuid import UUID
from app.models.schemas import APIKeyCreate, APIKeyResponse
from app.services.supabase_client import supabase

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(org_id: UUID):
    if not supabase:
        return []
    res = supabase.table("api_keys").select("*").eq("org_id", str(org_id)).execute()
    return res.data or []

@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(key: APIKeyCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("api_keys").insert(key.model_dump(mode="json")).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to store API key")
    return res.data[0]

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("api_keys").delete().eq("id", str(key_id)).execute()
    return None
