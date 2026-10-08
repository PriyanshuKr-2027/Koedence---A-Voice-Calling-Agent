"""
VoCall Episodic Memory Service.

Summarizes completed call transcripts and tracks emotional trajectories:
  - Generates JSON structured call summaries via Groq llama-3.3-70b
  - Extracts key facts and automatically persists them to long-term memory
  - Fetches recent call episodes for contact history
  - Identifies previous episode IDs for knowledge graph LEADS_TO temporal linkage

Database Table: memory_episodic
"""

import json
import logging
from typing import Optional, Dict, Any, List

from app.services.supabase_client import supabase
from app.services.llm import llm_service
from app.services.memory import long_term

logger = logging.getLogger(__name__)


async def create_episode(
    call_id: str,
    contact_id: Optional[str],
    org_id: str,
    transcript: Any,
    emotion_events: Optional[List[Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Summarizes a call transcript via Groq llama-3.3-70b in JSON mode and stores the episode record.

    Schema:
    {
      "summary": "2-3 sentence call summary",
      "key_facts": ["fact 1", "fact 2", "fact 3"],
      "emotion_arc": "brief description of emotional trajectory"
    }

    Also automatically populates long-term memory with key_facts if contact_id is provided.
    """
    if not supabase or not transcript:
        return None

    if contact_id:
        try:
            from app.services.redis_client import redis_client
            if await redis_client.get(f"erasure:{contact_id}"):
                logger.info("Contact %s has erasure flag set; skipping create_episode", contact_id)
                return None
        except Exception:
            pass

    # Check for existing episodic record for this call_id
    if call_id and supabase:
        try:
            existing = (
                supabase.table("memory_episodic")
                .select("*")
                .eq("call_id", call_id)
                .limit(1)
                .execute()
            )
            if existing.data and len(existing.data) > 0:
                logger.info("Episodic memory record already exists for call %s; returning existing", call_id)
                return existing.data[0]
        except Exception as exc:
            logger.warning("Could not check existing episodic memory for call %s: %s", call_id, exc)

    # Format transcript text if passed as list of turn dicts
    if isinstance(transcript, list):
        formatted_lines = []
        for turn in transcript:
            if isinstance(turn, dict):
                role = turn.get("role", "speaker").upper()
                content = turn.get("content", "").strip()
                formatted_lines.append(f"{role}: {content}")
            else:
                formatted_lines.append(str(turn))
        transcript_text = "\n".join(formatted_lines)
    else:
        transcript_text = str(transcript)

    prompt = (
        "Analyze this call transcript and return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "summary": "2-3 sentence call summary",\n'
        '  "key_facts": ["fact 1", "fact 2", "fact 3"],\n'
        '  "emotion_arc": "brief description of emotional trajectory"\n'
        "}\n\n"
        "Do not include Markdown formatting or commentary outside the JSON object.\n\n"
        f"Transcript:\n{transcript_text}"
    )

    try:
        raw_response = await llm_service.generate(
            prompt="You are an expert AI speech analyst summarizing customer phone calls.",
            messages=[{"role": "user", "content": prompt}],
        )

        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        data = json.loads(cleaned)
        summary = data.get("summary", "")
        key_facts = data.get("key_facts", [])
        emotion_arc = data.get("emotion_arc", "")

        insert_payload = {
            "call_id": call_id,
            "contact_id": contact_id,
            "org_id": org_id,
            "summary": summary,
            "key_facts": {"facts": key_facts} if isinstance(key_facts, list) else key_facts,
            "emotion_arc": {"description": emotion_arc} if isinstance(emotion_arc, str) else emotion_arc,
        }

        try:
            res = supabase.table("memory_episodic").upsert(insert_payload, on_conflict="call_id").execute()
        except Exception:
            res = supabase.table("memory_episodic").insert(insert_payload).execute()

        if res.data:
            created_episode = res.data[0]
            logger.info("Created or upserted episodic memory record for call %s", call_id)
            return created_episode
    except Exception as exc:
        logger.error("Failed to create_episode for call %s: %s", call_id, exc)

    return None


async def get_recent_episodes(
    contact_id: str,
    org_id: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Retrieves the most recent episodic call summaries for a contact.
    """
    if not supabase or not contact_id or not org_id:
        return []

    try:
        res = (
            supabase.table("memory_episodic")
            .select("*")
            .eq("contact_id", contact_id)
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.error("Failed to get_recent_episodes for contact %s: %s", contact_id, exc)
        return []


async def get_previous_episode_id(
    contact_id: str,
    org_id: str,
) -> Optional[str]:
    """
    Returns the ID of the second-most-recent episode for the given contact
    (ORDER BY created_at DESC LIMIT 1 OFFSET 1).

    Used for connecting LEADS_TO temporal edges in knowledge graph (P2-M8).
    """
    if not supabase or not contact_id or not org_id:
        return None

    try:
        res = (
            supabase.table("memory_episodic")
            .select("id")
            .eq("contact_id", contact_id)
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .range(1, 1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0].get("id")
    except Exception as exc:
        logger.error("Failed to get_previous_episode_id for contact %s: %s", contact_id, exc)

    return None


async def delete_contact_episodes(contact_id: str, org_id: str) -> bool:
    """
    Deletes all episodic memory records for a specified contact.
    """
    if not supabase or not contact_id or not org_id:
        return False

    try:
        supabase.table("memory_episodic").delete().eq("contact_id", contact_id).eq("org_id", org_id).execute()
        logger.info("Deleted episodic memory for contact %s in org %s", contact_id, org_id)
        return True
    except Exception as exc:
        logger.error("Failed to delete_contact_episodes for contact %s: %s", contact_id, exc)
        return False
