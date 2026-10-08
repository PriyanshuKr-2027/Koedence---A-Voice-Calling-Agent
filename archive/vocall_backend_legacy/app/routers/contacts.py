from fastapi import APIRouter, HTTPException, status
from typing import List
from uuid import UUID
from app.models.schemas import ContactCreate, ContactUpdate, ContactResponse
from app.services.supabase_client import supabase

router = APIRouter(prefix="/contacts", tags=["Contacts"])

@router.get("", response_model=List[ContactResponse])
async def list_contacts(org_id: UUID):
    if not supabase:
        return []
    res = supabase.table("contacts").select("*").eq("org_id", str(org_id)).execute()
    return res.data or []

@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(contact: ContactCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("contacts").insert(contact.model_dump(mode="json")).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create contact")
    return res.data[0]

@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("contacts").select("*").eq("id", str(contact_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    return res.data

@router.put("/{contact_id}", response_model=ContactResponse)
@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: UUID, contact_update: ContactUpdate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    update_data = {k: v for k, v in contact_update.model_dump(mode="json").items() if v is not None}
    res = supabase.table("contacts").update(update_data).eq("id", str(contact_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Contact not found or update failed")
    return res.data[0]

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("contacts").delete().eq("id", str(contact_id)).execute()
    return None


@router.get("/{contact_id}/memory/graph")
async def get_contact_graph(contact_id: UUID):
    """Fetch Knowledge Graph node and relationship data for visual graph rendering."""
    from app.services.memory import graph
    return graph.get_graph_data(str(contact_id))


@router.delete("/{contact_id}/memory/graph")
async def delete_contact_graph_memory(contact_id: UUID):
    """Clear all Knowledge Graph memory for a given contact."""
    from app.services.memory import graph
    success = graph.delete_contact_graph(str(contact_id))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete graph memory")
    return {"status": "success", "message": f"Graph memory cleared for contact {contact_id}"}


@router.delete("/{contact_id}/memory/long-term")
async def delete_contact_long_term_memory(contact_id: UUID):
    """Clear all long-term memory records for a given contact."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("memory_long_term").delete().eq("contact_id", str(contact_id)).execute()
    return {"status": "success", "message": f"Long-term memory cleared for contact {contact_id}"}


@router.delete("/{contact_id}/memory/episodic")
async def delete_contact_episodic_memory(contact_id: UUID):
    """Clear all episodic memory records for a given contact."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("memory_episodic").delete().eq("contact_id", str(contact_id)).execute()
    return {"status": "success", "message": f"Episodic memory cleared for contact {contact_id}"}


