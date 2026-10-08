"""
VoCall Multi-Tier Memory Retriever.

Retrieves and merges memory across all 4 tiers:
  1. Short-Term Memory (Upstash Redis active call state)
  2. Long-Term Memory (pgvector semantic facts)
  3. Episodic Memory (past call summaries — stubbed until P2-M4)
  4. Knowledge Graph Context (FalkorDB graph — stubbed until P2-M8)

Runs retrieval queries in parallel using asyncio.gather.
Formats retrieved memory into LLM prompt sections.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List

from app.services.memory import short_term, long_term, episodic, graph

logger = logging.getLogger(__name__)


async def _fetch_graph_context(contact_id: str) -> Dict[str, Any]:
    """Retrieves knowledge graph context from FalkorDB for a given contact."""
    try:
        return await asyncio.to_thread(graph.get_contact_graph_context, contact_id)
    except Exception as e:
        logger.error(f"Error fetching graph context for contact {contact_id}: {e}")
        return {"recent_entities": [], "frustration_topics": [], "episode_chain": []}


async def retrieve_all_memory(
    contact_id: Optional[str],
    org_id: str,
    agent_id: Optional[str] = None,
    query_text: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Parallel retrieval across all memory tiers using asyncio.gather.

    Args:
        contact_id: UUID of caller contact.
        org_id:     UUID of organization.
        agent_id:   UUID of agent.
        query_text: Current user input or topic for semantic search.
        config:     Dict containing runtime settings (e.g. call_id).

    Returns:
        Dict: {"short_term": dict|None, "long_term": list, "episodic": list, "graph": dict}
    """
    config = config or {}
    call_id = config.get("call_id")

    # Define tasks for parallel execution
    short_term_task = (
        short_term.get_call_memory(call_id)
        if call_id
        else asyncio.sleep(0, result=None)
    )

    long_term_task = (
        long_term.retrieve_relevant_facts(contact_id, org_id, query_text)
        if contact_id and org_id
        else asyncio.sleep(0, result=[])
    )

    episodic_limit = config.get("episodic_limit", 3)
    episodic_task = (
        episodic.get_recent_episodes(contact_id, org_id, limit=episodic_limit)
        if contact_id and org_id
        else asyncio.sleep(0, result=[])
    )
    graph_task = (
        _fetch_graph_context(contact_id)
        if contact_id
        else asyncio.sleep(0, result={})
    )

    # Execute all retrievers concurrently
    st_res, lt_res, ep_res, gr_res = await asyncio.gather(
        short_term_task,
        long_term_task,
        episodic_task,
        graph_task,
        return_exceptions=True,
    )

    # Safely handle results (defaults on exception)
    return {
        "short_term": st_res if not isinstance(st_res, Exception) else None,
        "long_term": lt_res if isinstance(lt_res, list) else [],
        "episodic": ep_res if isinstance(ep_res, list) else [],
        "graph": gr_res if isinstance(gr_res, dict) else {},
    }


def build_memory_prompt(
    memory_dict: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Formats multi-tier memory dictionary into a structured system prompt section.

    Output format:
    [CONTACT MEMORY]
    Previous conversations:
    - {episodic summary}

    Known facts:
    - {fact content} (emotion: {dominant})

    Graph context:
    - {entity/frustration context}

    Returns empty string "" if all memory tiers are empty.
    """
    if not memory_dict or not isinstance(memory_dict, dict):
        return ""

    sections = []

    # 1. Episodic Summaries
    episodic = memory_dict.get("episodic") or []
    if episodic:
        lines = []
        for ep in episodic:
            summary = ep.get("summary") if isinstance(ep, dict) else str(ep)
            if summary:
                lines.append(f"- {summary}")
        if lines:
            sections.append("Previous conversations:\n" + "\n".join(lines))

    # 2. Long-Term Facts
    long_term_facts = memory_dict.get("long_term") or []
    if long_term_facts:
        lines = []
        for fact in long_term_facts:
            if isinstance(fact, dict):
                content = fact.get("content", "").strip()
                emotion = fact.get("emotion_state", {}).get("dominant")
                if content:
                    tag = f" (emotion: {emotion})" if emotion else ""
                    lines.append(f"- {content}{tag}")
            elif isinstance(fact, str) and fact.strip():
                lines.append(f"- {fact.strip()}")
        if lines:
            sections.append("Known facts:\n" + "\n".join(lines))

    # 3. Knowledge Graph Context
    graph_ctx = memory_dict.get("graph") or {}
    if graph_ctx and isinstance(graph_ctx, dict):
        graph_lines = []

        recent_entities = graph_ctx.get("recent_entities") or []
        for item in recent_entities:
            summary = item.get("episode_summary", "")
            ents = ", ".join(item.get("entities", []))
            if summary or ents:
                graph_lines.append(f"- Mentioned Entities: {ents}" + (f" (Episode: {summary})" if summary else ""))

        frustration_topics = graph_ctx.get("frustration_topics") or []
        for item in frustration_topics:
            topic = item.get("topic", "")
            freq = item.get("frequency", 1)
            if topic:
                graph_lines.append(f"- Frustration Topic: '{topic}' (Count: {freq})")

        episode_chain = graph_ctx.get("episode_chain") or []
        for item in episode_chain:
            from_sum = item.get("from_summary") or item.get("from_id")
            to_sum = item.get("to_summary") or item.get("to_id")
            if from_sum and to_sum:
                graph_lines.append(f"- Causal Chain: {from_sum} -> {to_sum}")

        if graph_lines:
            sections.append("Graph context:\n" + "\n".join(graph_lines))
    elif isinstance(graph_ctx, list) and graph_ctx:
        lines = [f"- {item}" for item in graph_ctx]
        sections.append("Graph context:\n" + "\n".join(lines))

    if not sections:
        return ""

    return "[CONTACT MEMORY]\n" + "\n\n".join(sections)

