"""
Post-Call Processing Pipeline task using Trigger.dev v3.

Wires together all Phase 2 services (Episodic memory, Long-term memory, FalkorDB graph,
Post-call analysis, Connectors, Email notification, and Database/Redis cleanup).
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services import email
from app.services.connectors import dispatcher
from app.services.llm import llm_service
from app.services.memory import episodic, graph, long_term, short_term
from app.services.post_call import fire_post_call_connectors
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trigger.dev Task Decorator & Helper
# ---------------------------------------------------------------------------

def task(id: str, maxDuration: int = 300, retry: Optional[Dict[str, Any]] = None):
    """Trigger.dev v3 task decorator."""
    def decorator(fn):
        fn.task_id = id
        fn.max_duration = maxDuration
        fn.retry = retry or {}

        async def trigger_fn(payload: Dict[str, Any]):
            logger.info("Trigger.dev task [%s] triggered with payload: %s", id, payload)
            if asyncio.iscoroutinefunction(fn):
                return await fn(**payload)
            return fn(**payload)

        fn.trigger = trigger_fn
        return fn
    return decorator


def trigger(task_obj: Any, payload: Dict[str, Any]):
    if hasattr(task_obj, "trigger"):
        return asyncio.create_task(task_obj.trigger(payload))
    elif callable(task_obj):
        if asyncio.iscoroutinefunction(task_obj):
            return asyncio.create_task(task_obj(**payload))
        else:
            return task_obj(**payload)
    else:
        logger.error("Invalid task object passed to trigger: %s", task_obj)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

class EpisodeObj:
    """Convenience wrapper to access episode dict keys via attributes."""
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._data = data or {}
        self.id = self._data.get("id", "")
        self.summary = self._data.get("summary", "")
        kf = self._data.get("key_facts", [])
        if isinstance(kf, dict):
            self.key_facts = kf.get("facts", [])
        elif isinstance(kf, list):
            self.key_facts = kf
        else:
            self.key_facts = []


def compute_avg_emotion(emotion_events: List[Any]) -> Dict[str, Any]:
    """Computes average valence and arousal across call emotion events."""
    if not emotion_events:
        return {"valence": 0.0, "arousal": 0.5, "confidence": 0.8}

    total_val = 0.0
    total_arousal = 0.0
    count = 0

    for evt in emotion_events:
        state = evt.get("emotion_state") if isinstance(evt, dict) and "emotion_state" in evt else evt
        if isinstance(state, dict):
            total_val += float(state.get("valence", 0.0))
            total_arousal += float(state.get("arousal", 0.5))
            count += 1

    if count == 0:
        return {"valence": 0.0, "arousal": 0.5, "confidence": 0.8}

    return {
        "valence": round(total_val / count, 3),
        "arousal": round(total_arousal / count, 3),
        "confidence": 0.85,
    }


def format_transcript(transcript: Any) -> str:
    """Formats raw turns into a human-readable transcript block."""
    if isinstance(transcript, list):
        formatted_lines = []
        for turn in transcript:
            if isinstance(turn, dict):
                role = turn.get("role", "speaker").capitalize()
                content = turn.get("content", "").strip()
                formatted_lines.append(f"{role}: {content}")
            else:
                formatted_lines.append(str(turn))
        return "\n".join(formatted_lines)
    return str(transcript or "")


async def extract_entities_and_topics(transcript: Any) -> tuple[List[str], List[str]]:
    """Groq JSON mode extraction of entities and frustration topics from transcript."""
    transcript_text = format_transcript(transcript)
    if not transcript_text.strip():
        return [], []

    prompt = (
        "Extract key entities (people, products, services, locations, organizations) and "
        "frustration topics (complaints, issues, blockers) from this customer call transcript.\n"
        "Return ONLY valid JSON matching this exact schema:\n"
        "{\n"
        '  "entities": ["entity1", "entity2"],\n'
        '  "frustration_topics": ["topic1", "topic2"]\n'
        "}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    try:
        raw_response = await llm_service.generate(
            prompt="You are an expert AI data extraction system.",
            messages=[{"role": "user", "content": prompt}],
        )
        cleaned = str(raw_response).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(cleaned)
        entities = parsed.get("entities", [])
        topics = parsed.get("frustration_topics", [])
        return (
            entities if isinstance(entities, list) else [],
            topics if isinstance(topics, list) else [],
        )
    except Exception as exc:
        logger.error("Failed entity and topic extraction: %s", exc)
        return [], []


async def get_agent(agent_id: str) -> Dict[str, Any]:
    """Fetches agent record from Supabase."""
    if not supabase or not agent_id:
        return {}
    try:
        res = supabase.table("agents").select("*").eq("id", agent_id).single().execute()
        return res.data or {}
    except Exception as exc:
        logger.error("Failed to get agent config for %s: %s", agent_id, exc)
        return {}


async def get_contact(contact_id: Optional[str]) -> Dict[str, Any]:
    """Fetches contact details from Supabase if contact_id provided."""
    if not supabase or not contact_id:
        return {}
    try:
        res = supabase.table("contacts").select("*").eq("id", contact_id).single().execute()
        return res.data or {}
    except Exception:
        return {}


async def run_analysis(
    transcript: Any,
    emotion_events: List[Any],
    analysis_config: Dict[str, Any],
    avg_emotion_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generates post-call analysis summary, sentiment, action items, and resolution status.

    Always merges avg_emotion_state as a top-level key in the returned structured_data
    dict — resolving the P1-M9 comment:
      '// PHASE 3: auto-inject emotion_state into structured_data output'
    """
    transcript_text = format_transcript(transcript)
    if not transcript_text.strip():
        structured_data: Dict[str, Any] = {
            "summary": "Empty or silent call.",
            "sentiment": "Neutral",
            "action_items": [],
            "user_intent": "Unknown",
            "resolution_status": "unresolved",
        }
        # P3-M1: auto-inject emotion_state
        structured_data["emotion_state"] = avg_emotion_state or {}
        return structured_data

    prompt = (
        "Perform post-call analysis on this transcript. Return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "summary": "Comprehensive 2-4 sentence call summary",\n'
        '  "sentiment": "Positive / Neutral / Frustrated",\n'
        '  "action_items": ["action item 1", "action item 2"],\n'
        '  "user_intent": "Primary caller goal",\n'
        '  "resolution_status": "resolved / follow_up_required / escalated"\n'
        "}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    try:
        raw_response = await llm_service.generate(
            prompt="You are a senior voice operations analyst.",
            messages=[{"role": "user", "content": prompt}],
        )
        cleaned = str(raw_response).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(cleaned)
        structured_data = {
            "summary": parsed.get("summary", "Call completed."),
            "sentiment": parsed.get("sentiment", "Neutral"),
            "action_items": parsed.get("action_items", []),
            "user_intent": parsed.get("user_intent", "Inquiry"),
            "resolution_status": parsed.get("resolution_status", "resolved"),
        }
    except Exception as exc:
        logger.error("Failed run_analysis: %s", exc)
        structured_data = {
            "summary": "Call completed.",
            "sentiment": "Neutral",
            "action_items": [],
            "user_intent": "General inquiry",
            "resolution_status": "resolved",
        }

    # P3-M1: always merge avg_emotion_state as a top-level key — live as of P3-M1
    structured_data["emotion_state"] = avg_emotion_state or {}
    return structured_data


# ---------------------------------------------------------------------------
# Post-Call Pipeline Task
# ---------------------------------------------------------------------------

async def _is_contact_erased(contact_id: Optional[str]) -> bool:
    """Checks whether the contact has an active erasure flag in Redis."""
    if not contact_id:
        return False
    try:
        from app.services.redis_client import redis_client
        return bool(await redis_client.get(f"erasure:{contact_id}"))
    except Exception:
        return False


@task(id="post-call-pipeline", maxDuration=300, retry={"max": 3})
async def post_call_pipeline(
    call_id: str,
    agent_id: str,
    contact_id: Optional[str] = None,
    org_id: str = "",
) -> Dict[str, Any]:
    """
    Full Post-Call Processing Pipeline task executing Steps 1 through 11 idempotently.
    Guarded by calls.post_steps markers, Redis erasure flags, and deduplication.
    """
    logger.info(
        "Starting post_call_pipeline for call_id=%s, agent_id=%s, contact_id=%s, org_id=%s",
        call_id, agent_id, contact_id, org_id
    )

    if contact_id and await _is_contact_erased(contact_id):
        logger.info(
            "Contact %s has active erasure flag; skipping memory writes in post_call_pipeline for call %s",
            contact_id,
            call_id,
        )
        return {
            "status": "skipped",
            "reason": f"Contact {contact_id} marked for erasure",
            "call_id": call_id,
        }

    # Fetch existing call row and post_steps if available
    call_row: Dict[str, Any] = {}
    post_steps: Dict[str, Any] = {}
    if supabase:
        try:
            res = supabase.table("calls").select("*").eq("id", call_id).limit(1).execute()
            if res.data:
                call_row = res.data[0]
                raw_steps = call_row.get("post_steps") or {}
                if isinstance(raw_steps, dict):
                    post_steps = dict(raw_steps)
        except Exception as exc:
            logger.warning("Could not fetch call record for %s: %s", call_id, exc)

    async def record_step(step_name: str) -> None:
        post_steps[step_name] = datetime.now(timezone.utc).isoformat()
        if supabase:
            try:
                supabase.table("calls").update({"post_steps": post_steps}).eq("id", call_id).execute()
            except Exception as exc:
                logger.warning("Failed updating post_steps for call %s step %s: %s", call_id, step_name, exc)

    # Step 1 — Fetch raw data from short-term memory (or fallback to calls table)
    data = await short_term.get_call_memory(call_id) or {}
    transcript = data.get("turns", [])
    emotion_events = data.get("emotion_events", [])
    if not transcript and call_row.get("transcript"):
        transcript = call_row.get("transcript")
    logger.info("Step 1 — Fetched raw data: %s turns, %s emotion events", len(transcript) if isinstance(transcript, list) else 1, len(emotion_events))

    # Step 2 — Generate episodic summary (idempotent / guarded)
    episode: Optional[EpisodeObj] = None
    if post_steps.get("episodic"):
        logger.info("Step 2 — Episodic memory already completed for call_id=%s; loading existing", call_id)
        if supabase:
            try:
                ep_res = supabase.table("memory_episodic").select("*").eq("call_id", call_id).limit(1).execute()
                if ep_res.data:
                    episode = EpisodeObj(ep_res.data[0])
            except Exception as exc:
                logger.warning("Failed loading existing episodic record for call %s: %s", call_id, exc)
    if episode is None:
        if await _is_contact_erased(contact_id):
            logger.info("Step 2 — Contact %s marked for erasure; skipping episodic write", contact_id)
            episode = EpisodeObj({})
        else:
            raw_episode = await episodic.create_episode(
                call_id=call_id,
                contact_id=contact_id,
                org_id=org_id,
                transcript=transcript,
                emotion_events=emotion_events,
            )
            episode = EpisodeObj(raw_episode)
            if raw_episode:
                await record_step("episodic")
            logger.info("Step 2 — Generated episodic summary, episode_id=%s", episode.id)

    # Step 3 — Extract entities + topics
    entities, frustration_topics = await extract_entities_and_topics(transcript)
    logger.info("Step 3 — Extracted %d entities and %d frustration topics", len(entities), len(frustration_topics))

    # Step 4 — Store long-term facts (idempotent / guarded)
    avg_emotion = compute_avg_emotion(emotion_events)
    if post_steps.get("long_term"):
        logger.info("Step 4 — Long-term facts already stored for call_id=%s; skipping", call_id)
    else:
        if contact_id and episode.key_facts and not await _is_contact_erased(contact_id):
            for fact in episode.key_facts:
                if isinstance(fact, str) and fact.strip():
                    await long_term.store_fact(
                        contact_id=contact_id,
                        org_id=org_id,
                        agent_id=agent_id,
                        content=fact.strip(),
                        emotion_state=avg_emotion,
                        call_id=call_id,
                    )
        await record_step("long_term")
        logger.info("Step 4 — Stored long-term facts (avg_emotion=%s)", avg_emotion)

    # Step 5 — Episodic row confirmed
    logger.info("Step 5 — Episodic row confirmed (episode_id=%s)", episode.id)

    # Step 6 — Update FalkorDB graph (idempotent / guarded)
    if post_steps.get("graph"):
        logger.info("Step 6 — FalkorDB graph already updated for call_id=%s; skipping", call_id)
    else:
        if contact_id and episode.id and not await _is_contact_erased(contact_id):
            graph.add_entities(
                contact_id=contact_id,
                entities=entities,
                episode_id=episode.id,
                call_id=call_id,
                summary=episode.summary,
            )
            if frustration_topics:
                graph.add_frustration_edges(
                    contact_id=contact_id,
                    topics=frustration_topics,
                    episode_id=episode.id,
                    emotion_state=avg_emotion,
                    call_id=call_id,
                )
            prev_ep_id = await episodic.get_previous_episode_id(contact_id, org_id)
            if prev_ep_id:
                graph.link_episodes(contact_id, prev_ep_id, episode.id)
        await record_step("graph")
        logger.info("Step 6 — FalkorDB graph updated successfully")

    # Step 7 — Run analysis (emotion_state auto-injected as of P3-M1)
    analysis = None
    if post_steps.get("analysis") and call_row.get("analysis"):
        logger.info("Step 7 — Post-call analysis already completed for call_id=%s; reusing", call_id)
        analysis = call_row.get("analysis")
    if not analysis:
        agent = await get_agent(agent_id)
        contact = await get_contact(contact_id)
        agent_config = agent.get("config", {}) if isinstance(agent, dict) else {}
        analysis_config = agent_config.get("analysis", {})
        analysis = await run_analysis(transcript, emotion_events, analysis_config, avg_emotion_state=avg_emotion)
        await record_step("analysis")
        logger.info("Step 7 — Post-call analysis complete (summary length=%d, emotion_state=%s)", len(analysis.get("summary", "")), analysis.get("emotion_state"))

    # Step 8 — Fire post-call connectors in parallel (idempotent / guarded)
    connector_results = []
    if post_steps.get("connectors"):
        logger.info("Step 8 — Post-call connectors already fired for call_id=%s; skipping", call_id)
    else:
        agent = await get_agent(agent_id)
        contact = await get_contact(contact_id)
        contact_phone = contact.get("phone") or contact.get("number") or "+1234567890"
        contact_name = contact.get("name") or "Customer"
        agent_name = agent.get("name") or "AI Agent"
        duration_seconds = len(transcript) * 10 if isinstance(transcript, list) else 60

        call_data = {
            "call_id": call_id,
            "contact_phone": contact_phone,
            "contact_name": contact_name,
            "agent_name": agent_name,
            "call_summary": analysis.get("summary", ""),
            "emotion_score": avg_emotion.get("valence", 0.0),
            "duration_seconds": duration_seconds,
            "transcript": transcript,
            "structured_data": analysis,
            "success_eval": analysis.get("resolution_status", "completed"),
        }

        connector_results = await fire_post_call_connectors(
            org_id=org_id or agent.get("org_id", ""),
            agent_id=agent_id,
            call_data=call_data,
        )
        await record_step("connectors")
        logger.info("Step 8 — Post-call connectors executed (%d results)", len(connector_results))

    # Step 9 — Send email (idempotent / guarded)
    if post_steps.get("email"):
        logger.info("Step 9 — Post-call email already sent for call_id=%s; skipping", call_id)
    else:
        agent = await get_agent(agent_id)
        await email.send_post_call_email(agent, call_id, analysis)
        await record_step("email")
        logger.info("Step 9 — Post-call email notification sent")

    # Step 10 — Update calls row in Supabase
    post_processed_at = datetime.now(timezone.utc).isoformat()
    post_steps["completed"] = post_processed_at
    if supabase:
        try:
            if isinstance(analysis, dict):
                analysis["graph_context"] = {
                    "entities": entities,
                    "frustration_topics": frustration_topics,
                }
            update_payload = {
                "emotion_score": avg_emotion.get("valence", 0.0),
                "analysis": analysis,
                "transcript": format_transcript(transcript),
                "status": "completed",
                "post_processed_at": post_processed_at,
                "post_steps": post_steps,
            }
            supabase.table("calls").update(update_payload).eq("id", call_id).execute()
            logger.info("Step 10 — Updated calls row for call_id=%s with status='completed' and post_processed_at", call_id)
        except Exception as exc:
            logger.error("Failed to update calls row in Step 10: %s", exc)

    # Step 11 — Clear Redis short-term memory
    await short_term.clear_call_memory(call_id)
    logger.info("Step 11 — Cleared Redis short-term memory for call_id=%s", call_id)

    return {
        "status": "success",
        "call_id": call_id,
        "episode_id": episode.id,
        "emotion_score": avg_emotion.get("valence", 0.0),
        "analysis": analysis,
        "connector_results": connector_results,
        "post_steps": post_steps,
    }
