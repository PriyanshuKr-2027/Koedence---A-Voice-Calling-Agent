"""
FalkorDB Knowledge Graph Service for VoCall (Cypher Query Language).

Nodes:
  Contact {id, name, phone}
  Entity {name}
  Topic {name}
  Episode {id, call_id, date, summary}

Edges:
  MENTIONED: Contact -> Entity
  FRUSTRATED_ABOUT: Contact -> Entity/Topic (count, last_emotion_state, last_seen)
  OCCURRED_IN: Entity -> Episode
  LEADS_TO: Episode -> Episode (causal chain)
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

try:
    import falkordb
except ImportError:
    falkordb = None

from app.core.config import settings

logger = logging.getLogger(__name__)


def connect_falkor(contact_id: str):
    """
    Connect to FalkorDB instance and select contact-specific graph context.
    Returns Graph object or None on connection failure.
    """
    if falkordb is None:
        logger.warning("falkordb module is not installed. Graph memory disabled.")
        return None

    try:
        host = settings.FALKORDB_HOST
        port = settings.FALKORDB_PORT
        client = falkordb.FalkorDB(host=host, port=port)
        graph_name = f"contact_{contact_id.replace('-', '_')}"
        return client.select_graph(graph_name)
    except Exception as e:
        logger.warning(f"Failed to connect to FalkorDB graph for contact {contact_id}: {e}")
        return None


def add_entities(
    contact_id: str,
    entities: List[str],
    episode_id: str,
    call_id: str,
    date: Optional[str] = None,
    summary: str = "",
    contact_name: str = "Caller",
    contact_phone: str = "",
) -> bool:
    """
    MERGE Contact node, Episode node, Entity nodes, MENTIONED edges, and OCCURRED_IN edges.
    """
    g = connect_falkor(contact_id)
    if not g:
        return False

    date_str = date or datetime.now(timezone.utc).isoformat()

    try:
        # Merge Contact Node
        g.query(
            "MERGE (c:Contact {id: $contact_id}) "
            "ON CREATE SET c.name = $contact_name, c.phone = $contact_phone",
            {"contact_id": contact_id, "contact_name": contact_name, "contact_phone": contact_phone},
        )

        # Merge Episode Node
        g.query(
            "MERGE (ep:Episode {id: $episode_id}) "
            "ON CREATE SET ep.call_id = $call_id, ep.date = $date, ep.summary = $summary "
            "ON MATCH SET ep.summary = CASE WHEN $summary <> '' THEN $summary ELSE ep.summary END",
            {"episode_id": episode_id, "call_id": call_id, "date": date_str, "summary": summary},
        )

        for ent in entities:
            if not ent or not ent.strip():
                continue
            ent_clean = ent.strip()
            # Merge Entity, MENTIONED edge, and OCCURRED_IN edge
            g.query(
                "MATCH (c:Contact {id: $contact_id}) "
                "MATCH (ep:Episode {id: $episode_id}) "
                "MERGE (e:Entity {name: $ent_name}) "
                "MERGE (c)-[:MENTIONED]->(e) "
                "MERGE (e)-[:OCCURRED_IN]->(ep)",
                {"contact_id": contact_id, "episode_id": episode_id, "ent_name": ent_clean},
            )
        return True
    except Exception as e:
        logger.error(f"Error in add_entities for contact {contact_id}: {e}")
        return False


def add_frustration_edges(
    contact_id: str,
    topics: List[str],
    episode_id: str,
    emotion_state: Optional[Dict[str, Any]] = None,
    call_id: Optional[str] = None,
) -> bool:
    """
    MERGE Topic nodes and FRUSTRATED_ABOUT edges.
    ON MATCH: increment count once per call_id, update last_seen + last_emotion_state.
    """
    g = connect_falkor(contact_id)
    if not g:
        return False

    emotion_json = json.dumps(emotion_state or {})
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        # Merge Contact Node first
        g.query(
            "MERGE (c:Contact {id: $contact_id})",
            {"contact_id": contact_id},
        )

        for topic in topics:
            if not topic or not topic.strip():
                continue
            topic_clean = topic.strip()

            if call_id:
                query = (
                    "MATCH (c:Contact {id: $contact_id}) "
                    "MERGE (t:Topic {name: $topic_name}) "
                    "MERGE (c)-[r:FRUSTRATED_ABOUT]->(t) "
                    "ON CREATE SET r.count = 1, r.last_call_id = $call_id, r.last_emotion_state = $emotion_json, r.last_seen = $now_str "
                    "ON MATCH SET r.count = CASE WHEN r.last_call_id = $call_id THEN coalesce(r.count, 1) ELSE coalesce(r.count, 0) + 1 END, "
                    "r.last_call_id = $call_id, r.last_emotion_state = $emotion_json, r.last_seen = $now_str"
                )
                params = {
                    "contact_id": contact_id,
                    "topic_name": topic_clean,
                    "emotion_json": emotion_json,
                    "now_str": now_str,
                    "call_id": call_id,
                }
            else:
                query = (
                    "MATCH (c:Contact {id: $contact_id}) "
                    "MERGE (t:Topic {name: $topic_name}) "
                    "MERGE (c)-[r:FRUSTRATED_ABOUT]->(t) "
                    "ON CREATE SET r.count = 1, r.last_emotion_state = $emotion_json, r.last_seen = $now_str "
                    "ON MATCH SET r.count = coalesce(r.count, 0) + 1, r.last_emotion_state = $emotion_json, r.last_seen = $now_str"
                )
                params = {
                    "contact_id": contact_id,
                    "topic_name": topic_clean,
                    "emotion_json": emotion_json,
                    "now_str": now_str,
                }

            g.query(query, params)
        return True
    except Exception as e:
        logger.error(f"Error in add_frustration_edges for contact {contact_id}: {e}")
        return False


def link_episodes(contact_id: str, from_episode_id: str, to_episode_id: str) -> bool:
    """
    MATCH both Episode nodes, MERGE (from)-[:LEADS_TO]->(to).
    """
    g = connect_falkor(contact_id)
    if not g:
        return False

    try:
        query = (
            "MATCH (e1:Episode {id: $from_id}) "
            "MATCH (e2:Episode {id: $to_id}) "
            "MERGE (e1)-[:LEADS_TO]->(e2)"
        )
        g.query(query, {"from_id": from_episode_id, "to_id": to_episode_id})
        return True
    except Exception as e:
        logger.error(f"Error linking episodes {from_episode_id} -> {to_episode_id}: {e}")
        return False


def get_contact_graph_context(contact_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Retrieves knowledge graph context for a contact.
      Query 1: recent entity/episode associations
      Query 2: top frustration topics by frequency
      Query 3: episode causal chains (LEADS_TO)

    Returns:
      {
        "recent_entities": [ { "episode_summary": str, "entities": list[str], "date": str } ],
        "frustration_topics": [ { "topic": str, "frequency": int, "last_emotion_state": dict, "last_seen": str } ],
        "episode_chain": [ { "from_id": str, "to_id": str, "from_summary": str, "to_summary": str } ]
      }
    """
    g = connect_falkor(contact_id)
    if not g:
        return {"recent_entities": [], "frustration_topics": [], "episode_chain": []}

    try:
        # Query 1: Recent entity/episode associations
        q1 = (
            "MATCH (e:Entity)-[:OCCURRED_IN]->(ep:Episode) "
            "RETURN ep.id as ep_id, ep.summary as summary, ep.date as date, collect(e.name) as entities "
            "ORDER BY ep.date DESC LIMIT 10"
        )
        res1 = g.query(q1)
        recent_entities = []
        if res1 and res1.result_set:
            for row in res1.result_set:
                summary = row[1] if len(row) > 1 and row[1] else ""
                date_val = row[2] if len(row) > 2 and row[2] else ""
                ents = row[3] if len(row) > 3 and isinstance(row[3], list) else []
                recent_entities.append({
                    "episode_summary": summary,
                    "entities": ents,
                    "date": date_val,
                })

        # Query 2: Top frustration topics by frequency
        q2 = (
            "MATCH (c:Contact {id: $contact_id})-[r:FRUSTRATED_ABOUT]->(t:Topic) "
            "RETURN t.name as topic, r.count as frequency, r.last_emotion_state as last_emotion, r.last_seen as last_seen "
            "ORDER BY r.count DESC LIMIT 10"
        )
        res2 = g.query(q2, {"contact_id": contact_id})
        frustration_topics = []
        if res2 and res2.result_set:
            for row in res2.result_set:
                topic_name = row[0] if len(row) > 0 else ""
                freq = row[1] if len(row) > 1 and row[1] is not None else 1
                raw_emo = row[2] if len(row) > 2 else "{}"
                last_seen = row[3] if len(row) > 3 else ""

                parsed_emo = {}
                if isinstance(raw_emo, str) and raw_emo.strip():
                    try:
                        parsed_emo = json.loads(raw_emo)
                    except Exception:
                        parsed_emo = {}
                elif isinstance(raw_emo, dict):
                    parsed_emo = raw_emo

                frustration_topics.append({
                    "topic": topic_name,
                    "frequency": freq,
                    "last_emotion_state": parsed_emo,
                    "last_seen": last_seen,
                })

        # Query 3: Episode causal chain
        q3 = (
            "MATCH (ep1:Episode)-[:LEADS_TO]->(ep2:Episode) "
            "RETURN ep1.id as from_id, ep1.summary as from_summary, ep2.id as to_id, ep2.summary as to_summary"
        )
        res3 = g.query(q3)
        episode_chain = []
        if res3 and res3.result_set:
            for row in res3.result_set:
                episode_chain.append({
                    "from_id": row[0] if len(row) > 0 else "",
                    "from_summary": row[1] if len(row) > 1 else "",
                    "to_id": row[2] if len(row) > 2 else "",
                    "to_summary": row[3] if len(row) > 3 else "",
                })

        return {
            "recent_entities": recent_entities,
            "frustration_topics": frustration_topics,
            "episode_chain": episode_chain,
        }

    except Exception as e:
        logger.error(f"Error querying graph context for contact {contact_id}: {e}")
        return {"recent_entities": [], "frustration_topics": [], "episode_chain": []}


def get_graph_data(contact_id: str) -> Dict[str, Any]:
    """
    Returns full node and edge list for visual graph rendering.
    Format: { "nodes": [{id, label, type, ...}], "links": [{source, target, label, ...}] }
    """
    g = connect_falkor(contact_id)
    if not g:
        return {"nodes": [], "links": []}

    try:
        nodes_dict = {}
        links = []

        # Get all nodes
        q_nodes = "MATCH (n) RETURN id(n), labels(n), n"
        res_nodes = g.query(q_nodes)
        if res_nodes and res_nodes.result_set:
            for row in res_nodes.result_set:
                node_id = str(row[0])
                labels = row[1] if len(row) > 1 and row[1] else ["Node"]
                node_obj = row[2]
                props = node_obj.properties if hasattr(node_obj, "properties") else {}

                node_type = labels[0] if labels else "Entity"
                name = props.get("name") or props.get("summary") or props.get("id") or f"Node-{node_id}"

                nodes_dict[node_id] = {
                    "id": node_id,
                    "name": name,
                    "type": node_type,
                    "label": name,
                    "properties": props,
                }

        # Get all relationships
        q_rels = "MATCH (src)-[r]->(tgt) RETURN id(src), type(r), id(tgt), properties(r)"
        res_rels = g.query(q_rels)
        if res_rels and res_rels.result_set:
            for row in res_rels.result_set:
                src_id = str(row[0])
                rel_type = row[1]
                tgt_id = str(row[2])
                r_props = row[3] if len(row) > 3 else {}

                links.append({
                    "source": src_id,
                    "target": tgt_id,
                    "label": rel_type,
                    "properties": r_props,
                })

        return {
            "nodes": list(nodes_dict.values()),
            "links": links,
        }

    except Exception as e:
        logger.error(f"Error fetching raw graph data for contact {contact_id}: {e}")
        return {"nodes": [], "links": []}


def delete_contact_graph(contact_id: str) -> bool:
    """
    Deletes all nodes in the contact-specific graph and drops the graph instance.
    Confirms the graph is completely gone (count(n) == 0).
    """
    g = connect_falkor(contact_id)
    if not g:
        return True

    try:
        # 1. Detach and delete all nodes
        query = "MATCH (n) DETACH DELETE n"
        g.query(query)

        # 2. Attempt to drop graph instance completely
        if hasattr(g, "delete"):
            try:
                g.delete()
            except Exception:
                pass

        # 3. Confirm graph is gone / empty
        try:
            res = g.query("MATCH (n) RETURN count(n)")
            if res and res.result_set:
                cnt = res.result_set[0][0]
                if cnt > 0:
                    logger.error("FalkorDB graph contact_%s still has %d nodes after deletion", contact_id, cnt)
                    return False
        except Exception:
            # Query on non-existent/dropped graph confirms deletion
            pass

        return True
    except Exception as e:
        logger.error(f"Error deleting contact graph for {contact_id}: {e}")
        return False
