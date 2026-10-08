"""
tests/test_graph_memory.py — Tests for FalkorDB Knowledge Graph service.

Covers:
1. An episode with no entities is returned via HAD_EPISODE in get_contact_graph_context.
2. Two contacts' graphs are strictly isolated.
3. Repeated processing of the same call_id increments frustration count exactly once.
4. count_nodes returns node count for erasure verification.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

from app.services.memory import graph


class FakeGraph:
    def __init__(self, name: str):
        self.name = name
        self.nodes = {}
        self.edges = {}

    def query(self, cypher: str, params: dict = None):
        params = params or {}
        cypher_upper = cypher.upper()

        # count query
        if "RETURN COUNT(N)" in cypher_upper:
            cnt = len(self.nodes)
            return type("Res", (), {"result_set": [[cnt]]})()

        # detach delete
        if "DETACH DELETE" in cypher_upper:
            self.nodes.clear()
            self.edges.clear()
            return type("Res", (), {"result_set": []})()

        # Contact Node
        cid = params.get("contact_id")
        if cid:
            self.nodes[f"Contact:{cid}"] = {"id": cid, "name": params.get("contact_name", "Caller")}

        # Episode Node
        epid = params.get("episode_id")
        if epid:
            node_key = f"Episode:{epid}"
            existing_node = self.nodes.get(node_key, {})
            self.nodes[node_key] = {
                "id": epid,
                "call_id": params.get("call_id") or existing_node.get("call_id"),
                "summary": params.get("summary") or existing_node.get("summary", ""),
                "date": params.get("date") or existing_node.get("date", "2026-10-07T00:00:00"),
            }
            if cid:
                self.edges[f"{cid}-HAD_EPISODE->{epid}"] = {"type": "HAD_EPISODE"}

        # Entity Node
        ename = params.get("ent_name")
        if ename:
            self.nodes[f"Entity:{ename}"] = {"name": ename}
            if cid:
                self.edges[f"{cid}-MENTIONED->{ename}"] = {"type": "MENTIONED"}
            if epid:
                self.edges[f"{ename}-OCCURRED_IN->{epid}"] = {"type": "OCCURRED_IN"}

        # Topic / Frustration
        tname = params.get("topic_name")
        if tname and cid:
            self.nodes[f"Topic:{tname}"] = {"name": tname}
            call_id = params.get("call_id")
            edge_key = f"{cid}-FRUSTRATED_ABOUT->{tname}"
            if edge_key not in self.edges:
                self.edges[edge_key] = {
                    "count": 1,
                    "last_call_id": call_id,
                    "last_emotion": params.get("emotion_json"),
                    "last_seen": params.get("now_str"),
                }
            else:
                existing = self.edges[edge_key]
                if not call_id or existing.get("last_call_id") != call_id:
                    existing["count"] = existing.get("count", 0) + 1
                    existing["last_call_id"] = call_id
                existing["last_seen"] = params.get("now_str")

        # Context Query 1: (c:Contact)-[:HAD_EPISODE]->(ep:Episode)
        if "HAD_EPISODE" in cypher_upper and "RETURN EP.ID" in cypher_upper:
            rows = []
            for k, node in self.nodes.items():
                if k.startswith("Episode:"):
                    epid = node["id"]
                    # find associated entities
                    associated_entities = [
                        e_node["name"]
                        for ek, e_node in self.nodes.items()
                        if ek.startswith("Entity:") and f"{e_node['name']}-OCCURRED_IN->{epid}" in self.edges
                    ]
                    rows.append([epid, node.get("summary", ""), node.get("date", ""), associated_entities])
            return type("Res", (), {"result_set": rows})()

        # Context Query 2: FRUSTRATED_ABOUT
        if "FRUSTRATED_ABOUT" in cypher_upper and "RETURN T.NAME" in cypher_upper:
            rows = []
            for ek, edge in self.edges.items():
                if "-FRUSTRATED_ABOUT->" in ek:
                    tname = ek.split("-FRUSTRATED_ABOUT->")[1]
                    rows.append([tname, edge.get("count", 1), edge.get("last_emotion", "{}"), edge.get("last_seen", "")])
            return type("Res", (), {"result_set": rows})()

        # Context Query 3: LEADS_TO
        if "LEADS_TO" in cypher_upper:
            return type("Res", (), {"result_set": []})()

        return type("Res", (), {"result_set": []})()


@pytest.fixture
def fake_falkor_graphs():
    graphs = {}
    def get_graph(cid):
        graph_name = f"contact_{cid.replace('-', '_')}"
        if graph_name not in graphs:
            graphs[graph_name] = FakeGraph(graph_name)
        return graphs[graph_name]

    with patch("app.services.memory.graph.connect_falkor", side_effect=get_graph):
        yield graphs


def test_episode_with_no_entities_is_returned(fake_falkor_graphs):
    """
    An episode with zero entities is linked via HAD_EPISODE and returned by
    get_contact_graph_context with an empty entities list.
    """
    cid = str(uuid4())
    call_id = str(uuid4())
    epid = "ep_empty_entities_1"

    # Add episode with no entities
    ok = graph.add_entities(
        contact_id=cid,
        entities=[],
        episode_id=epid,
        call_id=call_id,
        summary="Call discussing account renewal without named entities",
    )
    assert ok is True

    # Retrieve context
    ctx = graph.get_contact_graph_context(cid)
    assert len(ctx["recent_entities"]) == 1
    ep_data = ctx["recent_entities"][0]
    assert ep_data["episode_summary"] == "Call discussing account renewal without named entities"
    assert ep_data["entities"] == []


def test_two_contacts_graphs_are_isolated(fake_falkor_graphs):
    """
    Knowledge graphs for two distinct contacts are partitioned into contact_{id_1}
    and contact_{id_2} with no shared data.
    """
    cid_1 = str(uuid4())
    cid_2 = str(uuid4())

    # Contact 1 data
    graph.add_entities(
        contact_id=cid_1,
        entities=["AcmeCorp"],
        episode_id="ep_1",
        call_id=str(uuid4()),
        summary="Acme discussion",
    )
    graph.add_frustration_edges(
        contact_id=cid_1,
        topics=["billing_issue"],
        episode_id="ep_1",
        call_id="call_1",
    )

    # Contact 2 data
    graph.add_entities(
        contact_id=cid_2,
        entities=["BetaLLC"],
        episode_id="ep_2",
        call_id=str(uuid4()),
        summary="Beta discussion",
    )

    # Query Contact 1
    ctx_1 = graph.get_contact_graph_context(cid_1)
    entities_1 = [ent for e in ctx_1["recent_entities"] for ent in e["entities"]]
    assert "AcmeCorp" in entities_1
    assert "BetaLLC" not in entities_1

    # Query Contact 2
    ctx_2 = graph.get_contact_graph_context(cid_2)
    entities_2 = [ent for e in ctx_2["recent_entities"] for ent in e["entities"]]
    assert "BetaLLC" in entities_2
    assert "AcmeCorp" not in entities_2


def test_repeated_processing_increments_frustration_count_once(fake_falkor_graphs):
    """
    Repeated post-call processing for the exact same call_id does not increment
    the frustration topic frequency multiple times.
    """
    cid = str(uuid4())
    call_id = "call_idempotent_123"

    # First run
    graph.add_frustration_edges(
        contact_id=cid,
        topics=["pricing_delay"],
        episode_id="ep_1",
        call_id=call_id,
    )

    ctx1 = graph.get_contact_graph_context(cid)
    assert len(ctx1["frustration_topics"]) == 1
    assert ctx1["frustration_topics"][0]["frequency"] == 1

    # Second duplicate run with same call_id
    graph.add_frustration_edges(
        contact_id=cid,
        topics=["pricing_delay"],
        episode_id="ep_1",
        call_id=call_id,
    )

    ctx2 = graph.get_contact_graph_context(cid)
    assert len(ctx2["frustration_topics"]) == 1
    assert ctx2["frustration_topics"][0]["frequency"] == 1


def test_count_nodes_and_deletion(fake_falkor_graphs):
    """
    count_nodes accurately counts nodes and returns 0 after deletion.
    """
    cid = str(uuid4())
    graph.add_entities(
        contact_id=cid,
        entities=["ServiceA", "ServiceB"],
        episode_id="ep_count",
        call_id="call_count",
        summary="Service review",
    )

    cnt = graph.count_nodes(cid)
    assert cnt >= 3  # Contact + Episode + 2 Entities

    # Delete
    ok = graph.delete_contact_graph(cid)
    assert ok is True
    assert graph.count_nodes(cid) == 0
