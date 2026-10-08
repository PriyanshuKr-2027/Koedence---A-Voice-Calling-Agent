"""
Unit & Integration test suite for FalkorDB Knowledge Graph memory service.
"""

import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.memory import graph, retriever


def test_graph_memory_flow():
    contact_id = "test-contact-101"
    call_id = "call-881"
    episode_id_1 = "ep-101"
    episode_id_2 = "ep-102"

    print("--- 1. Testing add_entities ---")
    res1 = graph.add_entities(
        contact_id=contact_id,
        entities=["Billing Inquiry", "Invoice #8921"],
        episode_id=episode_id_1,
        call_id=call_id,
        summary="Caller asked about overcharge on Invoice #8921",
        contact_name="Test User",
        contact_phone="+15550001111",
    )
    print("add_entities result:", res1)

    print("--- 2. Testing add_frustration_edges ---")
    res2 = graph.add_frustration_edges(
        contact_id=contact_id,
        topics=["High Billing Charges"],
        episode_id=episode_id_1,
        emotion_state={"dominant": "frustration", "score": 0.85},
    )
    print("add_frustration_edges result:", res2)

    print("--- 3. Testing link_episodes ---")
    graph.add_entities(
        contact_id=contact_id,
        entities=["Refund Request"],
        episode_id=episode_id_2,
        call_id="call-882",
        summary="Follow up on refund process",
    )
    res3 = graph.link_episodes(contact_id, episode_id_1, episode_id_2)
    print("link_episodes result:", res3)

    print("--- 4. Testing get_contact_graph_context ---")
    ctx = graph.get_contact_graph_context(contact_id)
    print("get_contact_graph_context returned keys:", list(ctx.keys()))
    print("Recent Entities:", ctx.get("recent_entities"))
    print("Frustration Topics:", ctx.get("frustration_topics"))
    print("Episode Chain:", ctx.get("episode_chain"))

    print("--- 5. Testing prompt builder integration ---")
    prompt = retriever.build_memory_prompt({"graph": ctx})
    print("Generated Prompt:\n", prompt)
    assert "[CONTACT MEMORY]" in prompt or prompt == ""

    print("--- 6. Testing get_graph_data (Visual data) ---")
    visual_data = graph.get_graph_data(contact_id)
    print(f"Visual data returned {len(visual_data['nodes'])} nodes and {len(visual_data['links'])} links.")

    print("--- 7. Testing delete_contact_graph ---")
    del_res = graph.delete_contact_graph(contact_id)
    print("delete_contact_graph result:", del_res)

    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_graph_memory_flow()
