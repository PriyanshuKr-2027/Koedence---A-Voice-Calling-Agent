"""Tests for Dataset D1 generator and schema validation.

Runs gen_d1 with N=2 and a stubbed LLM without network calls,
validating callers.jsonl, calls.jsonl, and questions.jsonl schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch
import pytest

# Ensure repo root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.data.check_d1 import run_check_d1
from eval.data.gen_d1 import generate_d1_dataset_async


@pytest.mark.asyncio
async def test_gen_d1_schema_and_integrity(tmp_path):
    """Verifies that gen_d1 generates valid persona sheets, calls, and questions."""
    mock_turns = [
        {"role": "agent", "content": "Welcome to VoCall Support. How can I help you today?"},
        {"role": "caller", "content": "Hello, I am calling regarding my broadband account."},
        {"role": "agent", "content": "Certainly. Can you verify your registered plan?"},
        {"role": "caller", "content": "Yes, my plan is Fiber Pro 300 Mbps and my billing date is 5th of every month."},
        {"role": "agent", "content": "Thank you, I see your account. What issue are you experiencing?"},
        {"role": "caller", "content": "I have been experiencing frequent evening broadband speed drops."},
        {"role": "agent", "content": "I understand. I have created a priority technical ticket for your area."},
        {"role": "caller", "content": "Thank you, that was all I needed."},
    ]
    mock_llm_response = json.dumps(mock_turns)

    with patch("app.services.llm.llm_service.generate", new=AsyncMock(return_value=mock_llm_response)):
        manifest = await generate_d1_dataset_async(
            config_path="eval/config.yaml",
            out_dir=tmp_path,
            n_callers=2,
            seed=42,
        )

    # 1. Check generated files exist
    callers_file = tmp_path / "callers.jsonl"
    calls_file = tmp_path / "calls.jsonl"
    questions_file = tmp_path / "questions.jsonl"
    manifest_file = tmp_path / "generation_manifest.json"

    assert callers_file.exists()
    assert calls_file.exists()
    assert questions_file.exists()
    assert manifest_file.exists()

    # 2. Check callers.jsonl schema
    with open(callers_file, "r", encoding="utf-8") as f:
        callers = [json.loads(line) for line in f if line.strip()]

    assert len(callers) == 2
    for caller in callers:
        assert "caller_id" in caller
        assert "name" in caller and len(caller["name"]) > 0
        assert "phone" in caller and "+91" in caller["phone"]
        assert caller["language_style"] in ["English", "Hinglish"]

        # 4 to 6 stable facts
        facts = caller["facts"]
        assert 4 <= len(facts) <= 6
        fact_ids = set()
        for fact in facts:
            assert "fact_id" in fact
            assert "category" in fact
            assert "key" in fact
            assert "value" in fact
            fact_ids.add(fact["fact_id"])
        assert len(fact_ids) == len(facts)  # Unique fact IDs

        # 1 recurring complaint
        complaint = caller["recurring_complaint"]
        assert "fact_id" in complaint
        assert "topic" in complaint and len(complaint["topic"]) > 0

    # 3. Check calls.jsonl schema
    with open(calls_file, "r", encoding="utf-8") as f:
        calls = [json.loads(line) for line in f if line.strip()]

    calls_by_caller = {}
    for call in calls:
        cid = call["caller_id"]
        calls_by_caller.setdefault(cid, []).append(call)

        assert "call_id" in call
        assert "call_index" in call
        assert "emotion_arc" in call
        assert "complaint_present" in call
        assert isinstance(call["complaint_present"], bool)
        assert isinstance(call["mentioned_fact_ids"], list)

        # 6 to 14 turns
        turns = call["turns"]
        assert 6 <= len(turns) <= 14
        for turn in turns:
            assert turn["role"] in ["agent", "caller"]
            assert len(turn["content"]) > 0

    assert len(calls_by_caller) == 2
    for cid, caller_calls in calls_by_caller.items():
        # M calls between 5 and 8
        assert 5 <= len(caller_calls) <= 8

        # Recurring complaint appears in at least 3 calls
        complaint_calls = [c for c in caller_calls if c["complaint_present"]]
        assert len(complaint_calls) >= 3

    # 4. Check questions.jsonl schema
    with open(questions_file, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    # Exactly 8 questions per caller (total 16 for 2 callers)
    assert len(questions) == 16

    questions_by_caller = {}
    for q in questions:
        cid = q["caller_id"]
        questions_by_caller.setdefault(cid, []).append(q)

        assert "qid" in q
        assert "type" in q
        assert "question" in q and len(q["question"]) > 0
        assert "gold_answer" in q and len(q["gold_answer"]) > 0
        assert isinstance(q["gold_fact_ids"], list)

    for cid, q_list in questions_by_caller.items():
        assert len(q_list) == 8

        types = [q["type"] for q in q_list]
        assert "fact_recall" in types
        assert "preference" in types
        assert "recurring_complaint_pattern" in types
        assert "temporal" in types
        assert "adversarial" in types

        # Check adversarial properties
        adv_questions = [q for q in q_list if q["type"] == "adversarial"]
        assert len(adv_questions) >= 1
        for adv in adv_questions:
            assert adv["gold_answer"] == "unknown"
            assert adv["gold_fact_ids"] == []

        # Check recurring complaint pattern question
        pattern_q = next(q for q in q_list if q["type"] == "recurring_complaint_pattern")
        caller_meta = next(c for c in callers if c["caller_id"] == cid)
        assert pattern_q["gold_answer"] == caller_meta["recurring_complaint"]["topic"]

    # 5. Check check_d1 runner on the generated directory
    summary = run_check_d1(data_dir=tmp_path, sample_size=5)
    assert summary["n_callers"] == 2
    assert summary["total_questions"] == 16
    assert summary["question_counts"]["adversarial"] >= 2
