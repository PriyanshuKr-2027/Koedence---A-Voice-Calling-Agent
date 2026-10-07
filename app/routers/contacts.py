from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.models.schemas import ContactCreate, ContactResponse, ContactUpdate
from app.routers.auth import require_authenticated_user
from app.services.memory import episodic, graph, long_term, short_term
from app.services.redis_client import redis_client
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def compute_contact_hash(contact_id: str) -> str:
    """Computes HMAC-SHA256 hash of contact_id using a server-side secret key."""
    secret = (
        os.environ.get("COMPLIANCE_HMAC_KEY")
        or "vocall-audit-compliance-secret-key-2026"
    ).encode("utf-8")
    return hmac.new(secret, contact_id.encode("utf-8"), hashlib.sha256).hexdigest()


@router.get("", response_model=List[ContactResponse])
async def list_contacts(
    org_id: UUID,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if str(org_id) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: cannot access contacts of another organization",
        )
    effective_org = current_user["org_id"]
    if not supabase:
        return []
    res = (
        supabase.table("contacts")
        .select("*")
        .eq("org_id", str(effective_org))
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    return res.data or []


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact: ContactCreate,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    payload = contact.model_dump(mode="json")
    payload["org_id"] = current_user["org_id"]
    res = supabase.table("contacts").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create contact")
    return res.data[0]


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    res = supabase.table("contacts").select("*").eq("id", str(contact_id)).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    if str(res.data.get("org_id")) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: contact belongs to another organization",
        )
    return res.data


@router.put("/{contact_id}", response_model=ContactResponse)
@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    contact_update: ContactUpdate,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    existing = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    if str(existing.data.get("org_id")) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: contact belongs to another organization",
        )
    update_data = {k: v for k, v in contact_update.model_dump(mode="json").items() if v is not None}
    res = supabase.table("contacts").update(update_data).eq("id", str(contact_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Contact not found or update failed")
    return res.data[0]


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client unavailable")
    existing = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).single().execute()
    if existing.data and str(existing.data.get("org_id")) != current_user["org_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: contact belongs to another organization",
        )
    supabase.table("contacts").delete().eq("id", str(contact_id)).execute()
    return None


@router.get("/{contact_id}/memory/graph")
async def get_contact_graph(
    contact_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """Fetches Knowledge Graph node and relationship data for visual graph rendering."""
    if supabase:
        existing = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).single().execute()
        if existing.data and str(existing.data.get("org_id")) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: contact belongs to another organization",
            )
    return graph.get_graph_data(str(contact_id))


@router.delete("/{contact_id}/memory/graph")
async def delete_contact_graph_memory(
    contact_id: UUID,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
):
    """Clears all Knowledge Graph memory for a given contact."""
    if supabase:
        existing = supabase.table("contacts").select("org_id").eq("id", str(contact_id)).single().execute()
        if existing.data and str(existing.data.get("org_id")) != current_user["org_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: contact belongs to another organization",
            )
    success = graph.delete_contact_graph(str(contact_id))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete graph memory")
    return {"status": "success", "message": f"Graph memory cleared for contact {contact_id}"}


async def verify_store_residue(contact_id: str, call_ids: List[str]) -> Dict[str, int]:
    """Runs residue count queries across storage tiers without thresholding."""
    residue: Dict[str, int] = {
        "redis_stm": 0,
        "redis_webcall": 0,
        "redis_slot": 0,
        "redis_extra_keys": 0,
        "contacts": 0,
        "calls": 0,
        "emotion_events": 0,
        "intent_events": 0,
        "memory_long_term": 0,
        "memory_episodic": 0,
        "falkordb_nodes": 0,
    }

    # Redis in-call buffer, webcall, slot, and extra keys
    stm_hits = 0
    webcall_hits = 0
    slot_hits = 0
    try:
        for c_id in call_ids:
            val = await redis_client.get(f"stm:{c_id}")
            if val:
                stm_hits += 1
            wb = await redis_client.lrange(f"webcall:{c_id}:events", 0, -1)
            if wb:
                webcall_hits += len(wb)
            sv = await redis_client.get(f"slot:{c_id}")
            if sv:
                slot_hits += 1
            sk = await redis_client.keys(f"slot:{c_id}:*")
            slot_hits += len(sk)

        residue["redis_stm"] = stm_hits
        residue["redis_webcall"] = webcall_hits
        residue["redis_slot"] = slot_hits

        extra = await redis_client.keys(f"*{contact_id}*")
        residue["redis_extra_keys"] = len([k for k in extra if k != f"erasure:{contact_id}"])
    except Exception as exc:
        logger.warning("Redis residue check error for %s: %s", contact_id, exc)

    if supabase:
        c_res = supabase.table("contacts").select("id").eq("id", contact_id).execute()
        residue["contacts"] = len(c_res.data or [])

        # Calls retaining transcript or raw metadata for this contact
        calls_res = supabase.table("calls").select("id, transcript, from_number").eq("contact_id", contact_id).execute()
        residue["calls"] = len(calls_res.data or [])

        ee_hits = 0
        for c_id in call_ids:
            ee_res = supabase.table("emotion_events").select("id").eq("call_id", c_id).execute()
            ee_hits += len(ee_res.data or [])
        residue["emotion_events"] = ee_hits

        ie_res = supabase.table("intent_events").select("id").eq("contact_id", contact_id).execute()
        residue["intent_events"] = len(ie_res.data or [])

        lt_res = supabase.table("memory_long_term").select("id").eq("contact_id", contact_id).execute()
        residue["memory_long_term"] = len(lt_res.data or [])

        ep_res = supabase.table("memory_episodic").select("id").eq("contact_id", contact_id).execute()
        residue["memory_episodic"] = len(ep_res.data or [])

    g = graph.connect_falkor(contact_id)
    if g:
        try:
            r = g.query("MATCH (n) RETURN count(n)")
            if r and r.result_set:
                residue["falkordb_nodes"] = int(r.result_set[0][0])
        except Exception:
            residue["falkordb_nodes"] = 0

    return residue


@router.delete("/{contact_id}/memory")
async def cascade_delete_contact_memory(
    contact_id: UUID,
    delete_contact: bool = True,
    verify: bool = False,
    response: Response = None,
    current_user: Optional[Dict[str, Any]] = Depends(require_authenticated_user),
):
    """
    DPDP Act 2023 Section 12 'Forget Me' Cascade Erasure.

    Clears personal identity and conversational residue across all tiers:
      1. Authentication & tenant isolation check
      2. Call ID pre-fetch before deletions begin
      3. 1-hour Redis erasure suppression flag
      4. Redis buffer and slot key removal
      5. Postgres pgvector, episodic, intent, emotion events, and calls sanitization
      6. FalkorDB contact graph deletion and confirmation
      7. Contact row deletion (when delete_contact=True)
      8. Isolated per-tier execution and multi-status reporting
      9. Pseudonymized audit log entry using HMAC-SHA256
      10. Fully idempotent on repeat execution
      11. Optional zero-residue verification
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cid = str(contact_id)
    user_org_id = str(current_user.get("org_id")) if current_user.get("org_id") else None

    # 1. Tenant Verification & Contact Lookup
    contact_row = None
    if supabase:
        try:
            res = supabase.table("contacts").select("id, org_id").eq("id", cid).execute()
            if res.data and len(res.data) > 0:
                contact_row = res.data[0]
        except Exception as exc:
            logger.warning("Error fetching contact row %s: %s", cid, exc)

    contact_hash = compute_contact_hash(cid)
    is_idempotent_repeat = False

    if contact_row:
        contact_org_id = str(contact_row.get("org_id"))
        if user_org_id and contact_org_id != user_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Contact does not belong to your organization",
            )
    else:
        # Check if this contact was already erased by checking compliance_log or Redis flag
        prev_org_id = None
        if supabase:
            try:
                log_res = supabase.table("compliance_log").select("org_id").eq("contact_hash", contact_hash).execute()
                if log_res.data and len(log_res.data) > 0:
                    prev_org_id = str(log_res.data[0].get("org_id"))
            except Exception as exc:
                logger.warning("Error checking compliance log for hash %s: %s", contact_hash, exc)

        if prev_org_id is not None:
            if user_org_id and prev_org_id != user_org_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Contact does not belong to your organization",
                )
            is_idempotent_repeat = True
        else:
            # Check redis erasure flag
            erasure_flag = await redis_client.get(f"erasure:{cid}")
            if erasure_flag:
                is_idempotent_repeat = True
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contact not found",
                )

    # 2. Pre-fetch call_ids BEFORE any deletions
    call_ids: List[str] = []
    if supabase:
        try:
            calls_res = supabase.table("calls").select("id").eq("contact_id", cid).execute()
            call_ids = [str(r["id"]) for r in (calls_res.data or []) if r.get("id")]
        except Exception as exc:
            logger.warning("Failed pre-fetching call IDs for contact %s: %s", cid, exc)

    # 3. Set Redis erasure flag (1 hour TTL) to suppress concurrent writes
    try:
        await redis_client.set(f"erasure:{cid}", "1", ex_seconds=3600)
    except Exception as exc:
        logger.warning("Failed setting erasure flag for %s: %s", cid, exc)

    tier_results: List[Dict[str, Any]] = []

    # 4. Tier: Redis Deletion
    redis_deleted_count = 0
    try:
        for c_id in call_ids:
            if await redis_client.delete(f"stm:{c_id}"):
                redis_deleted_count += 1
            if await redis_client.delete(f"webcall:{c_id}:events"):
                redis_deleted_count += 1
            slots_deleted = await short_term.clear_slots(c_id)
            redis_deleted_count += slots_deleted
            if await redis_client.delete(f"slot:{c_id}"):
                redis_deleted_count += 1

        # Delete any key matching *cid* except the active erasure flag
        cid_keys = await redis_client.keys(f"*{cid}*")
        for k in cid_keys:
            if k != f"erasure:{cid}":
                if await redis_client.delete(k):
                    redis_deleted_count += 1

        tier_results.append({
            "tier": "redis",
            "status": "ok",
            "deleted_count": redis_deleted_count,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "redis",
            "status": "failed",
            "deleted_count": redis_deleted_count,
            "error": str(exc),
        })

    # 5. Tier: Postgres pgvector (memory_long_term)
    lt_deleted_count = 0
    try:
        if supabase:
            before_res = supabase.table("memory_long_term").select("id").eq("contact_id", cid).execute()
            lt_deleted_count += len(before_res.data or [])
            supabase.table("memory_long_term").delete().eq("contact_id", cid).execute()
            for c_id in call_ids:
                cb_res = supabase.table("memory_long_term").select("id").eq("call_id", c_id).execute()
                lt_deleted_count += len(cb_res.data or [])
                supabase.table("memory_long_term").delete().eq("call_id", c_id).execute()

        tier_results.append({
            "tier": "pgvector",
            "status": "ok",
            "deleted_count": lt_deleted_count,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "pgvector",
            "status": "failed",
            "deleted_count": 0,
            "error": str(exc),
        })

    # 6. Tier: Postgres Episodic (memory_episodic)
    ep_deleted_count = 0
    try:
        if supabase:
            before_res = supabase.table("memory_episodic").select("id").eq("contact_id", cid).execute()
            ep_deleted_count += len(before_res.data or [])
            supabase.table("memory_episodic").delete().eq("contact_id", cid).execute()
            for c_id in call_ids:
                cb_res = supabase.table("memory_episodic").select("id").eq("call_id", c_id).execute()
                ep_deleted_count += len(cb_res.data or [])
                supabase.table("memory_episodic").delete().eq("call_id", c_id).execute()

        tier_results.append({
            "tier": "episodic",
            "status": "ok",
            "deleted_count": ep_deleted_count,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "episodic",
            "status": "failed",
            "deleted_count": 0,
            "error": str(exc),
        })

    # 7. Tier: FalkorDB Contact Graph
    try:
        falkor_ok = await asyncio.to_thread(graph.delete_contact_graph, cid)
        if not falkor_ok:
            raise RuntimeError(f"FalkorDB graph contact_{cid} confirmed not empty after deletion")

        tier_results.append({
            "tier": "falkordb",
            "status": "ok",
            "deleted_count": 1 if not is_idempotent_repeat else 0,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "falkordb",
            "status": "failed",
            "deleted_count": 0,
            "error": str(exc),
        })

    # 8. Tier: Intent & Emotion Events
    events_deleted_count = 0
    try:
        if supabase:
            ie_before = supabase.table("intent_events").select("id").eq("contact_id", cid).execute()
            events_deleted_count += len(ie_before.data or [])
            supabase.table("intent_events").delete().eq("contact_id", cid).execute()

            for c_id in call_ids:
                ie_c = supabase.table("intent_events").select("id").eq("call_id", c_id).execute()
                events_deleted_count += len(ie_c.data or [])
                supabase.table("intent_events").delete().eq("call_id", c_id).execute()

                ee_c = supabase.table("emotion_events").select("id").eq("call_id", c_id).execute()
                events_deleted_count += len(ee_c.data or [])
                supabase.table("emotion_events").delete().eq("call_id", c_id).execute()

        tier_results.append({
            "tier": "events",
            "status": "ok",
            "deleted_count": events_deleted_count,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "events",
            "status": "failed",
            "deleted_count": 0,
            "error": str(exc),
        })

    # 9. Tier: Calls Sanitization
    calls_scrubbed_count = 0
    try:
        if supabase and call_ids:
            for c_id in call_ids:
                call_update = {
                    "transcript": None,
                    "analysis": None,
                    "from_number": None,
                    "to_number": None,
                    "emotion_score": None,
                    "contact_id": None,
                }
                try:
                    supabase.table("calls").update({**call_update, "recording_url": None}).eq("id", c_id).execute()
                except Exception:
                    supabase.table("calls").update(call_update).eq("id", c_id).execute()
                calls_scrubbed_count += 1

                # Clean optional turn/transcript tables if present
                try:
                    supabase.table("call_turns").delete().eq("call_id", c_id).execute()
                except Exception:
                    pass
                try:
                    supabase.table("call_transcripts").delete().eq("call_id", c_id).execute()
                except Exception:
                    pass

        if supabase:
            try:
                supabase.table("memory_graph_nodes").delete().eq("contact_id", cid).execute()
            except Exception:
                pass

        tier_results.append({
            "tier": "calls",
            "status": "ok",
            "deleted_count": calls_scrubbed_count,
            "error": None,
        })
    except Exception as exc:
        tier_results.append({
            "tier": "calls",
            "status": "failed",
            "deleted_count": 0,
            "error": str(exc),
        })

    # 10. Tier: Contact Row (deleted last if requested)
    contacts_deleted_count = 0
    if delete_contact:
        try:
            if supabase and contact_row:
                supabase.table("contacts").delete().eq("id", cid).execute()
                contacts_deleted_count = 1

            tier_results.append({
                "tier": "contacts",
                "status": "ok",
                "deleted_count": contacts_deleted_count,
                "error": None,
            })
        except Exception as exc:
            tier_results.append({
                "tier": "contacts",
                "status": "failed",
                "deleted_count": 0,
                "error": str(exc),
            })

    # Evaluate per-tier success
    all_succeeded = all(t["status"] == "ok" for t in tier_results)
    if response is not None:
        response.status_code = status.HTTP_200_OK if all_succeeded else status.HTTP_207_MULTI_STATUS

    # 11. Pseudonymized Audit Logging
    audit_status = "ok"
    try:
        if supabase:
            supabase.table("compliance_log").insert({
                "action": "forget_me",
                "contact_hash": contact_hash,
                "contact_id": None,
                "org_id": user_org_id,
                "tiers_cleared": [t["tier"] for t in tier_results if t["status"] == "ok"],
                "tier_details": tier_results,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as audit_exc:
        logger.error("Audit log insert failed: %s", audit_exc)
        audit_status = f"failed: {audit_exc}"

    result_payload: Dict[str, Any] = {
        "deleted": all_succeeded,
        "contact_id": cid,
        "tiers_cleared": sum(1 for t in tier_results if t["status"] == "ok"),
        "tiers": tier_results,
        "audit_status": audit_status,
        "message": (
            "All personal identity and memory records erased under DPDP Act 2023"
            if all_succeeded
            else "Partial deletion completed; review per-tier status for failed tiers"
        ),
    }

    if verify:
        result_payload["residue"] = await verify_store_residue(cid, call_ids)

    return result_payload
