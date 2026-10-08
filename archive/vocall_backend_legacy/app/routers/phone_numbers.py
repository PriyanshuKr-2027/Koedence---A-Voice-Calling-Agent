from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from typing import List, Optional
from uuid import UUID
from app.models.schemas import PhoneNumberCreate, PhoneNumberResponse
from app.services.supabase_client import supabase

router = APIRouter(prefix="/phone-numbers", tags=["Phone Numbers"])

@router.get("", response_model=List[PhoneNumberResponse])
async def list_phone_numbers(org_id: UUID):
    if not supabase:
        return []
    res = supabase.table("phone_numbers").select("*").eq("org_id", str(org_id)).execute()
    return res.data or []

@router.post("", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
async def provision_phone_number(phone: PhoneNumberCreate):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("phone_numbers").insert(phone.model_dump(mode="json")).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to provision phone number")
    return res.data[0]

@router.get("/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(phone_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("phone_numbers").select("*").eq("id", str(phone_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Phone number record not found")
    return res.data

@router.post("/{phone_id}/kyc", response_model=PhoneNumberResponse)
async def upload_kyc_document(
    phone_id: UUID,
    doc_type: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Uploads KYC compliance document (Aadhaar / PAN / GST / Company Registration)
    to Supabase Storage private bucket and marks kyc_status as 'submitted'.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")

    filename = f"kyc_{phone_id}_{file.filename}"
    file_bytes = await file.read()

    try:
        # Upload to Supabase Storage bucket 'kyc-documents'
        supabase.storage.from_("kyc-documents").upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
    except Exception as e:
        print(f"Supabase Storage upload notice: {e}")

    # Update kyc_status to 'submitted'
    res = supabase.table("phone_numbers").update({"kyc_status": "submitted"}).eq("id", str(phone_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Phone number record not found")

    return res.data[0]

@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_phone_number(phone_id: UUID):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    supabase.table("phone_numbers").delete().eq("id", str(phone_id)).execute()
    return None
