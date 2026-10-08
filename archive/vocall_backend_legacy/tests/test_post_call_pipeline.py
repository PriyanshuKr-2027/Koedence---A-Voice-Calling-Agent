import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from trigger.post_call_pipeline import (
    post_call_pipeline,
    compute_avg_emotion,
    format_transcript,
    extract_entities_and_topics,
    run_analysis,
    trigger,
)


def test_compute_avg_emotion():
    emotion_events = [
        {"emotion_state": {"valence": 0.6, "arousal": 0.4}},
        {"emotion_state": {"valence": 0.2, "arousal": 0.8}},
    ]
    res = compute_avg_emotion(emotion_events)
    assert res["valence"] == 0.4
    assert res["arousal"] == 0.6


def test_format_transcript():
    turns = [
        {"role": "user", "content": "Hello, I need help with my account."},
        {"role": "assistant", "content": "Sure, main aapki help kar sakta hoon."},
    ]
    formatted = format_transcript(turns)
    assert "User: Hello, I need help with my account." in formatted
    assert "Assistant: Sure, main aapki help kar sakta hoon." in formatted


@pytest.mark.asyncio
async def test_extract_entities_and_topics():
    turns = [
        {"role": "user", "content": "I'm having an issue with my iPhone order in Mumbai."}
    ]
    with patch("app.services.llm.llm_service.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '{"entities": ["iPhone", "Mumbai"], "frustration_topics": ["order issue"]}'
        entities, topics = await extract_entities_and_topics(turns)
        assert "iPhone" in entities
        assert "Mumbai" in entities
        assert "order issue" in topics


@pytest.mark.asyncio
async def test_run_analysis():
    turns = [
        {"role": "user", "content": "Cancel my subscription please."}
    ]
    with patch("app.services.llm.llm_service.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '''{
            "summary": "Customer requested subscription cancellation.",
            "sentiment": "Neutral",
            "action_items": ["Cancel subscription"],
            "user_intent": "Account cancellation",
            "resolution_status": "resolved"
        }'''
        analysis = await run_analysis(turns, [], {})
        assert analysis["summary"] == "Customer requested subscription cancellation."
        assert analysis["sentiment"] == "Neutral"
        assert "Cancel subscription" in analysis["action_items"]


@pytest.mark.asyncio
async def test_post_call_pipeline_full_execution():
    """Verify all 11 steps of post_call_pipeline execute without errors."""
    call_id = "test-call-123"
    agent_id = "test-agent-456"
    contact_id = "test-contact-789"
    org_id = "test-org-000"

    mock_memory = {
        "turns": [
            {"role": "user", "content": "Main samajh gaya, thank you!"},
            {"role": "assistant", "content": "You are welcome!"},
        ],
        "emotion_events": [
            {"emotion_state": {"valence": 0.5, "arousal": 0.3}}
        ],
    }

    mock_episode = {
        "id": "episode-111",
        "summary": "Successful conversation in Hinglish.",
        "key_facts": {"facts": ["Customer spoke Hinglish"]},
    }

    with patch("app.services.memory.short_term.get_call_memory", new_callable=AsyncMock) as mock_get_mem, \
         patch("app.services.memory.episodic.create_episode", new_callable=AsyncMock) as mock_create_ep, \
         patch("trigger.post_call_pipeline.extract_entities_and_topics", new_callable=AsyncMock) as mock_ext, \
         patch("app.services.memory.long_term.store_fact", new_callable=AsyncMock) as mock_store_fact, \
         patch("app.services.memory.graph.add_entities") as mock_graph_ent, \
         patch("app.services.memory.graph.add_frustration_edges") as mock_graph_frust, \
         patch("app.services.memory.episodic.get_previous_episode_id", new_callable=AsyncMock) as mock_prev_ep, \
         patch("app.services.memory.graph.link_episodes") as mock_graph_link, \
         patch("trigger.post_call_pipeline.get_agent", new_callable=AsyncMock) as mock_get_ag, \
         patch("trigger.post_call_pipeline.run_analysis", new_callable=AsyncMock) as mock_analysis, \
         patch("trigger.post_call_pipeline.fire_post_call_connectors", new_callable=AsyncMock) as mock_get_conn, \
         patch("app.services.connectors.dispatcher.fire_connector", new_callable=AsyncMock) as mock_fire_conn, \
         patch("app.services.email.send_post_call_email", new_callable=AsyncMock) as mock_send_email, \
         patch("app.services.supabase_client.supabase") as mock_sb, \
         patch("app.services.memory.short_term.clear_call_memory", new_callable=AsyncMock) as mock_clear_mem:

        mock_get_mem.return_value = mock_memory
        mock_create_ep.return_value = mock_episode
        mock_ext.return_value = (["Hinglish"], ["None"])
        mock_prev_ep.return_value = "prev-ep-000"
        mock_get_ag.return_value = {"id": agent_id, "name": "Support Agent", "config": {}}
        mock_analysis.return_value = {"summary": "Call resolved", "sentiment": "Positive", "action_items": []}
        mock_get_conn.return_value = [{"success": True, "connector": "webhook"}]

        result = await post_call_pipeline(call_id, agent_id, contact_id, org_id)

        assert result["status"] == "success"
        assert result["call_id"] == call_id
        assert result["episode_id"] == "episode-111"
        assert result["emotion_score"] == 0.5

        # Verify steps triggered
        mock_get_mem.assert_called_once_with(call_id)
        mock_create_ep.assert_called_once()
        mock_store_fact.assert_called_once()
        mock_graph_ent.assert_called_once()
        mock_graph_frust.assert_called_once()
        mock_graph_link.assert_called_once()
        mock_get_conn.assert_called_once()
        mock_send_email.assert_called_once()
        mock_clear_mem.assert_called_once_with(call_id)
