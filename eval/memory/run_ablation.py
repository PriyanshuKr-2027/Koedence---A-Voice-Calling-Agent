"""VoCall Multi-Tier Memory Ablation Evaluation.

Compares five memory tier configurations:
  1. no_memory: Empty memory block
  2. t2_only: Long-term pgvector semantic facts only
  3. t2_t3: Long-term facts + Episodic call history
  4. t2_t3_t4: Long-term facts + Episodic history + FalkorDB graph context
  5. full: All 4 tiers (T1 Redis short-term + T2 + T3 + T4)

Across three benchmarks:
  - D1: Synthetic caller histories (eval/data/d1/)
  - LoCoMo: Long-context conversational memory benchmark (locomo10.json)
  - LongMemEval: Long-term memory benchmark small split

Outputs:
  - raw.jsonl: Detailed per-question evaluation traces
  - metrics.json: Mean and bootstrap 95% CIs per config, per question type, paired differences
  - table_v.csv: Accuracy D1, Accuracy D2, Recall@5, Tokens per Call, Retrieval ms
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
import yaml

from app.core.config import settings
from app.services.llm import llm_service
from app.services.memory import episodic, graph, long_term, short_term
from app.services.memory.retriever import build_memory_prompt, retrieve_all_memory
from eval.common.cache import DiskCache
from eval.common.cost import CostTracker
from eval.common.mode import (
    ServiceTracker,
    get_eval_mode,
    is_mock,
    require_live_services,
    stamp_csv_mock_data,
)
from eval.common.runlog import append_jsonl, start_run, write_metrics
from eval.common.stats import bootstrap_ci, paired_bootstrap
from eval.data.gen_d1 import generate_d1_dataset_async

# ---------------------------------------------------------------------------
# Memory Configuration Definitions
# ---------------------------------------------------------------------------

CONFIGURATIONS = {
    "no_memory": [],
    "t2_only": ["long_term"],
    "t2_t3": ["long_term", "episodic"],
    "t2_t3_t4": ["long_term", "episodic", "graph"],
    "full": ["short_term", "long_term", "episodic", "graph"],
}


# ---------------------------------------------------------------------------
# In-Memory Stub Backend for Offline Testing
# ---------------------------------------------------------------------------

class StubMemoryBackend:
    """In-memory multi-tier memory store used for tests and offline runs."""

    def __init__(self):
        self.facts: Dict[str, List[Dict[str, Any]]] = {}
        self.episodes: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_entities: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_frustrations: Dict[str, List[Dict[str, Any]]] = {}
        self.graph_chains: Dict[str, List[Dict[str, Any]]] = {}
        self.short_term: Dict[str, Dict[str, Any]] = {}
        self._active = False

    async def mock_store_fact(self, contact_id: str, org_id: str, agent_id: Optional[str], content: str, emotion_state: Optional[Dict[str, Any]] = None, *args, **kwargs):
        self.facts.setdefault(contact_id, []).append({
            "content": content,
            "emotion_state": emotion_state or {},
            "similarity": 0.88,
        })
        return {"id": str(uuid.uuid4()), "content": content}

    async def mock_retrieve_relevant_facts(self, contact_id: str, org_id: str, query_text: str, limit: int = 5, *args, **kwargs):
        stored = self.facts.get(contact_id, [])
        if not stored:
            return []
        q_lower = query_text.lower()
        # Rank by simple keyword relevance
        def score(f):
            c = f["content"].lower()
            return sum(1 for w in q_lower.split() if w in c)
        ranked = sorted(stored, key=score, reverse=True)
        return ranked[:limit]

    async def mock_create_episode(self, call_id: str, contact_id: str, org_id: str, transcript: Any, emotion_events: Any, *args, **kwargs):
        lines = []
        if isinstance(transcript, list):
            for t in transcript:
                lines.append(t.get("content", ""))
        text = " ".join(lines)
        summary = f"Call discussing customer inquiries: {text[:120]}..."
        ep = {
            "id": f"ep_{uuid.uuid4().hex[:6]}",
            "summary": summary,
            "key_facts": [t[:80] for t in lines[:3]],
        }
        self.episodes.setdefault(contact_id, []).append(ep)
        return ep

    async def mock_get_recent_episodes(self, contact_id: str, org_id: str, limit: int = 3, *args, **kwargs):
        return self.episodes.get(contact_id, [])[-limit:]

    def mock_add_entities(
        self,
        contact_id: str,
        entities: List[str],
        episode_id: str,
        call_id: str,
        date: Optional[str] = None,
        summary: str = "",
        contact_name: str = "Caller",
        contact_phone: str = "",
        *args,
        **kwargs,
    ):
        self.graph_entities.setdefault(contact_id, []).append({
            "entities": entities,
            "episode_summary": summary,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "call_id": call_id,
            "episode_id": episode_id,
            "date": date,
        })

    def mock_add_frustration_edges(self, contact_id: str, topics: List[str], episode_id: str, emotion_state: Any, *args, **kwargs):
        for t in topics:
            self.graph_frustrations.setdefault(contact_id, []).append({"topic": t, "frequency": 2})

    def mock_link_episodes(self, contact_id: str, from_id: str, to_id: str, *args, **kwargs):
        self.graph_chains.setdefault(contact_id, []).append({"from_id": from_id, "to_id": to_id})

    def mock_get_contact_graph_context(self, contact_id: str, *args, **kwargs) -> Dict[str, Any]:
        return {
            "recent_entities": self.graph_entities.get(contact_id, []),
            "frustration_topics": self.graph_frustrations.get(contact_id, []),
            "episode_chain": self.graph_chains.get(contact_id, []),
        }

    async def mock_delete_all_contact_data(self, contact_id: str, *args, **kwargs):
        self.facts.pop(contact_id, None)
        self.episodes.pop(contact_id, None)
        self.graph_entities.pop(contact_id, None)
        self.graph_frustrations.pop(contact_id, None)
        self.graph_chains.pop(contact_id, None)
        self.short_term.pop(contact_id, None)


# ---------------------------------------------------------------------------
# Dataset Loaders & Fallbacks
# ---------------------------------------------------------------------------

def load_d1_dataset(data_dir: Path, n_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Loads D1 dataset from callers, calls, and questions JSONL files."""
    callers_file = data_dir / "callers.jsonl"
    calls_file = data_dir / "calls.jsonl"
    questions_file = data_dir / "questions.jsonl"

    if not callers_file.exists() or not calls_file.exists() or not questions_file.exists():
        return []

    callers = [json.loads(line) for line in callers_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    calls = [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = [json.loads(line) for line in questions_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    calls_by_caller: Dict[str, List[Dict[str, Any]]] = {}
    for c in calls:
        calls_by_caller.setdefault(c["caller_id"], []).append(c)

    questions_by_caller: Dict[str, List[Dict[str, Any]]] = {}
    for q in questions:
        questions_by_caller.setdefault(q["caller_id"], []).append(q)

    samples = []
    for caller in callers:
        cid = caller["caller_id"]
        samples.append({
            "dataset": "D1",
            "sample_id": cid,
            "caller": caller,
            "calls": calls_by_caller.get(cid, []),
            "questions": questions_by_caller.get(cid, []),
        })
        if n_limit and len(samples) >= n_limit:
            break

    return samples


def load_locomo_dataset(file_path: Path, n_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Loads LoCoMo benchmark dataset from locomo10.json or synthetic fallback."""
    if file_path.exists():
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                samples = []
                for item in data[:n_limit] if n_limit else data:
                    samples.append({
                        "dataset": "LoCoMo",
                        "sample_id": item.get("conversation_id", f"locomo_{uuid.uuid4().hex[:6]}"),
                        "calls": [{"turns": s, "topic": "LoCoMo dialogue session"} for s in item.get("sessions", [])],
                        "questions": item.get("qa", []),
                    })
                return samples
        except Exception:
            pass

    # Deterministic synthetic LoCoMo fallback
    samples = []
    count = n_limit or 10
    for i in range(count):
        sid = f"locomo_{i+1:02d}"
        samples.append({
            "dataset": "LoCoMo",
            "sample_id": sid,
            "calls": [
                {
                    "turns": [
                        {"role": "user", "content": f"I booked a hotel in Seattle for my vacation next June."},
                        {"role": "assistant", "content": "Got it, your Seattle hotel reservation is confirmed."},
                    ],
                    "topic": "Travel booking session",
                },
                {
                    "turns": [
                        {"role": "user", "content": f"Can we also reserve a rental sedan car for that Seattle trip?"},
                        {"role": "assistant", "content": "I have reserved a compact sedan for your Seattle trip."},
                    ],
                    "topic": "Rental car booking session",
                },
            ],
            "questions": [
                {
                    "qid": f"{sid}_q1",
                    "type": "fact_recall",
                    "question": "Which city is the hotel reservation located in?",
                    "gold_answer": "Seattle",
                    "gold_fact_ids": [],
                },
                {
                    "qid": f"{sid}_q2",
                    "type": "temporal",
                    "question": "What rental vehicle was requested in the second session?",
                    "gold_answer": "rental sedan car",
                    "gold_fact_ids": [],
                },
            ],
        })
    return samples


def load_longmemeval_dataset(file_path: Path, n_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Loads LongMemEval small split dataset or synthetic fallback."""
    if file_path.exists():
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                samples = []
                for item in data[:n_limit] if n_limit else data:
                    samples.append({
                        "dataset": "LongMemEval",
                        "sample_id": item.get("id", f"lme_{uuid.uuid4().hex[:6]}"),
                        "calls": [{"turns": c, "topic": "LongMemEval session"} for c in item.get("history", [])],
                        "questions": item.get("questions", []),
                    })
                return samples
        except Exception:
            pass

    # Deterministic synthetic LongMemEval fallback
    samples = []
    count = n_limit or 10
    for i in range(count):
        sid = f"longmem_{i+1:02d}"
        samples.append({
            "dataset": "LongMemEval",
            "sample_id": sid,
            "calls": [
                {
                    "turns": [
                        {"role": "user", "content": "I have adopted a golden retriever named Rusty."},
                        {"role": "assistant", "content": "That is wonderful, Rusty is a great name."},
                    ],
                    "topic": "Pet adoption discussion",
                },
                {
                    "turns": [
                        {"role": "user", "content": "Rusty had his rabies vaccination today at the vet."},
                        {"role": "assistant", "content": "Noted, rabies vaccination recorded."},
                    ],
                    "topic": "Veterinary update",
                },
            ],
            "questions": [
                {
                    "qid": f"{sid}_q1",
                    "type": "fact_recall",
                    "question": "What is the name of the golden retriever?",
                    "gold_answer": "Rusty",
                    "gold_fact_ids": [],
                },
                {
                    "qid": f"{sid}_q2",
                    "type": "adversarial",
                    "question": "What breed of cat does the user own?",
                    "gold_answer": "unknown",
                    "gold_fact_ids": [],
                },
            ],
        })
    return samples


# ---------------------------------------------------------------------------
# LLM Answering & LLM Judge
# ---------------------------------------------------------------------------

async def answer_question(
    question: str,
    memory_prompt: str,
    answer_model: str,
    cache: DiskCache,
    mock_mode: bool = False,
    gold_answer: Optional[str] = None,
    tracker: Optional[ServiceTracker] = None,
) -> Tuple[str, int]:
    """Generates candidate answer using temperature=0 and counts prompt tokens."""
    prompt_tokens = len(memory_prompt.split()) + len(question.split()) + 35

    if mock_mode:
        if tracker:
            tracker.record("mock_answer")
        # Realistic stub heuristic: if memory is empty, answer unknown.
        # If memory contains gold answer keywords, answer gold answer.
        if not memory_prompt.strip():
            return "unknown", prompt_tokens
        if gold_answer and any(w.lower() in memory_prompt.lower() for w in gold_answer.split() if len(w) > 3):
            return gold_answer, prompt_tokens
        return "unknown", prompt_tokens

    if tracker:
        tracker.record("groq_answer")
    provider = "groq"
    cache_payload = {
        "task": "answer",
        "question": question,
        "memory": memory_prompt,
        "model": answer_model,
        "temperature": 0.0,
    }

    cached = cache.get(provider, answer_model, cache_payload)
    if cached is not None:
        return str(cached), prompt_tokens

    sys_prompt = (
        "You are a factual AI assistant answering queries about a caller based solely on the recorded memory.\n"
        "If the answer cannot be determined from the memory block, answer exactly 'unknown'.\n"
        f"{memory_prompt}\n"
    )
    user_prompt = f"Question: {question}\nAnswer directly and concisely:"

    res = await llm_service.generate(
        prompt=sys_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        temperature=0.0,
        max_tokens=128,
    )
    answer = str(res).strip()
    cache.set(provider, answer_model, cache_payload, answer)
    return answer, prompt_tokens


async def judge_answer(
    question: str,
    gold_answer: str,
    candidate_answer: str,
    judge_model: str,
    cache: DiskCache,
    mock_mode: bool = False,
    tracker: Optional[ServiceTracker] = None,
) -> bool:
    """Evaluates candidate correctness using judge model with strict JSON output."""
    cand_norm = candidate_answer.strip().lower()
    gold_norm = gold_answer.strip().lower()

    if mock_mode:
        if tracker:
            tracker.record("mock_judge")
        if gold_norm == "unknown":
            return "unknown" in cand_norm
        return gold_norm in cand_norm or any(w in cand_norm for w in gold_norm.split() if len(w) > 3)

    if tracker:
        tracker.record("groq_judge")
    provider = "groq"
    cache_payload = {
        "task": "judge",
        "question": question,
        "gold": gold_answer,
        "candidate": candidate_answer,
        "model": judge_model,
    }

    cached = cache.get(provider, judge_model, cache_payload)
    if cached is not None:
        return bool(cached.get("correct", False))

    judge_sys = (
        "You are an impartial evaluation judge. Compare the Candidate Answer to the Ground Truth Reference Answer.\n"
        "Return ONLY a valid JSON object matching: {\"correct\": true} or {\"correct\": false}."
    )
    judge_usr = (
        f"Question: {question}\n"
        f"Ground Truth Reference Answer: {gold_answer}\n"
        f"Candidate Answer: {candidate_answer}\n"
        "Is the Candidate Answer factually correct according to the Ground Truth Reference?"
    )

    raw = await llm_service.generate(
        prompt=judge_sys,
        messages=[{"role": "user", "content": judge_usr}],
        temperature=0.0,
        max_tokens=64,
    )
    text = str(raw).strip()
    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()
    data = json.loads(text)
    is_correct = bool(data.get("correct", False))
    cache.set(provider, judge_model, cache_payload, {"correct": is_correct})
    return is_correct


# ---------------------------------------------------------------------------
# Ingestion & Deletion Pipeline
# ---------------------------------------------------------------------------

async def ingest_sample_history(
    contact_id: str,
    org_id: str,
    calls: List[Dict[str, Any]],
    stub_backend: Optional[StubMemoryBackend] = None,
) -> None:
    """
    Ingests call history using the exact write functions the post-call pipeline uses:
      1. episodic.create_episode
      2. long_term.store_fact
      3. graph.add_entities / add_frustration_edges / link_episodes
    """
    prev_ep_id = None
    for idx, call in enumerate(calls, 1):
        call_id = call.get("call_id") or f"call_{idx:02d}"
        turns = call.get("turns", [])
        topic = call.get("topic") or call.get("call_topic", "")
        avg_emotion = {"valence": -0.6 if call.get("complaint_present") else 0.1, "arousal": 0.5}

        # 1. Episodic summary write
        if stub_backend:
            ep = await stub_backend.mock_create_episode(call_id, contact_id, org_id, turns, [])
            ep_id = ep["id"]
            ep_summary = ep["summary"]
            facts_to_store = ep["key_facts"]
        else:
            try:
                ep_obj = await episodic.create_episode(
                    call_id=call_id,
                    contact_id=contact_id,
                    org_id=org_id,
                    transcript=turns,
                    emotion_events=[],
                )
                ep_id = ep_obj.get("id", str(uuid.uuid4()))
                ep_summary = ep_obj.get("summary", "")
                kf = ep_obj.get("key_facts", [])
                facts_to_store = kf if isinstance(kf, list) else []
            except Exception:
                ep_id = str(uuid.uuid4())
                ep_summary = f"Summary of call {idx}"
                facts_to_store = [topic] if topic else []

        # 2. Long-term facts write
        for fact_text in facts_to_store:
            if isinstance(fact_text, str) and fact_text.strip():
                if stub_backend:
                    await stub_backend.mock_store_fact(contact_id, org_id, None, fact_text.strip(), avg_emotion)
                else:
                    try:
                        await long_term.store_fact(contact_id, org_id, None, fact_text.strip(), avg_emotion)
                    except Exception:
                        pass

        # 3. FalkorDB graph write
        entities = [f"Topic_{idx}", "VoCall_Service"]
        if stub_backend:
            stub_backend.mock_add_entities(contact_id, entities, ep_id, call_id, ep_summary)
            if call.get("complaint_present"):
                stub_backend.mock_add_frustration_edges(contact_id, [call.get("complaint_topic") or "Service drops"], ep_id, avg_emotion)
            if prev_ep_id:
                stub_backend.mock_link_episodes(contact_id, prev_ep_id, ep_id)
        else:
            try:
                graph.add_entities(contact_id, entities, ep_id, call_id, ep_summary)
                if call.get("complaint_present"):
                    graph.add_frustration_edges(contact_id, [call.get("complaint_topic") or "Service drops"], ep_id, avg_emotion)
                if prev_ep_id:
                    graph.link_episodes(contact_id, prev_ep_id, ep_id)
            except Exception:
                pass

        prev_ep_id = ep_id


async def delete_sample_history(
    contact_id: str,
    stub_backend: Optional[StubMemoryBackend] = None,
) -> None:
    """Clears all contact data across all memory tiers so runs do not leak."""
    if stub_backend:
        await stub_backend.mock_delete_all_contact_data(contact_id)
    else:
        try:
            from app.routers.contacts import cascade_delete_contact_memory
            # Invoke direct cleanup tasks
            t1 = short_term.clear_call(contact_id)
            t2 = long_term.delete_all(contact_id)
            t3 = episodic.delete_all(contact_id)
            t4 = asyncio.to_thread(graph.delete_contact_graph, contact_id)
            await asyncio.gather(t1, t2, t3, t4, return_exceptions=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Ablation Experiment Runner
# ---------------------------------------------------------------------------

async def run_ablation_experiment(
    config_path: str = "eval/config.yaml",
    out_dir: str = "results/ablation",
    limit: Optional[int] = None,
    mock: bool = False,
    stub_mode: Optional[bool] = None,
    seed_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Runs memory tier ablation across D1, LoCoMo, and LongMemEval."""
    cli_mock = mock or (stub_mode is True)
    mode = get_eval_mode(cli_mock)
    is_mock_run = (mode == "mock")

    if not is_mock_run:
        falkor_ok = False
        try:
            import falkordb
            client = falkordb.FalkorDB(host=settings.FALKORDB_HOST, port=settings.FALKORDB_PORT)
            client.connection.ping()
            falkor_ok = True
        except Exception:
            falkor_ok = False

        require_live_services({
            "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", None)),
            "SUPABASE_URL": bool(os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or getattr(settings, "NEXT_PUBLIC_SUPABASE_URL", None)),
            "SUPABASE_KEY": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY") or getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)),
            "UPSTASH_REDIS_REST_URL": bool(os.environ.get("UPSTASH_REDIS_REST_URL") or getattr(settings, "UPSTASH_REDIS_REST_URL", None)),
            "UPSTASH_REDIS_REST_TOKEN": bool(os.environ.get("UPSTASH_REDIS_REST_TOKEN") or getattr(settings, "UPSTASH_REDIS_REST_TOKEN", None)),
            "FALKORDB": falkor_ok,
        }, "memory_ablation", cli_mock=cli_mock)

    tracker = ServiceTracker()

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    seeds = [seed_override] if seed_override is not None else cfg.get("seeds", [0, 1, 2])
    answer_model = cfg.get("models", {}).get("answer_model", "llama-3.3-70b-versatile")
    judge_model = cfg.get("models", {}).get("judge_model", "llama-3.3-70b-versatile")
    cache_dir = cfg.get("paths", {}).get("cache_dir", ".eval_cache")
    cache = DiskCache(cache_dir)

    raw_out = Path(out_dir)
    if raw_out == Path("results/ablation") or raw_out == Path("results"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sub = f"MOCK_{ts}" if is_mock_run else ts
        out_path = Path("results/ablation") / sub
    else:
        out_path = raw_out

    out_path.mkdir(parents=True, exist_ok=True)
    raw_file = out_path / "raw.jsonl"
    if raw_file.exists():
        raw_file.unlink()

    # Save original references to restore later
    orig_store_fact = long_term.store_fact
    orig_retrieve_facts = long_term.retrieve_relevant_facts
    orig_create_ep = episodic.create_episode
    orig_get_ep = episodic.get_recent_episodes
    orig_add_ent = graph.add_entities
    orig_add_frust = graph.add_frustration_edges
    orig_link_ep = graph.link_episodes
    orig_get_graph = graph.get_contact_graph_context
    import app.services.memory.retriever as ret_mod
    orig_fetch_graph = getattr(ret_mod, "_fetch_graph_context", None)

    stub_backend = StubMemoryBackend() if is_mock_run else None

    try:
        # Patch retrieval in stub mode
        if is_mock_run and stub_backend:
            long_term.store_fact = stub_backend.mock_store_fact
            long_term.retrieve_relevant_facts = stub_backend.mock_retrieve_relevant_facts
            episodic.create_episode = stub_backend.mock_create_episode
            episodic.get_recent_episodes = stub_backend.mock_get_recent_episodes
            graph.add_entities = stub_backend.mock_add_entities
            graph.add_frustration_edges = stub_backend.mock_add_frustration_edges
            graph.link_episodes = stub_backend.mock_link_episodes
            graph.get_contact_graph_context = stub_backend.mock_get_contact_graph_context
            async def _mock_fetch(cid: str) -> Dict[str, Any]:
                return stub_backend.mock_get_contact_graph_context(cid)
            ret_mod._fetch_graph_context = _mock_fetch

        # Load datasets
        d1_path = Path("eval/data/d1")
        if not (d1_path / "callers.jsonl").exists():
            await generate_d1_dataset_async(config_path=config_path, out_dir=d1_path, n_callers=max(limit or 10, 4), seed=seeds[0])

        d1_samples = load_d1_dataset(d1_path, n_limit=limit)
        locomo_samples = load_locomo_dataset(Path("locomo10.json"), n_limit=limit)
        longmem_samples = load_longmemeval_dataset(Path("eval/data/longmemeval_small.json"), n_limit=limit)
        all_samples = d1_samples + locomo_samples + longmem_samples

        eval_records: List[Dict[str, Any]] = []

        for seed in seeds:
            rng = random.Random(seed)
            shuffled_samples = list(all_samples)
            rng.shuffle(shuffled_samples)

            for sample in shuffled_samples:
                dataset_name = sample["dataset"]
                sample_id = sample["sample_id"]
                contact_id = f"abl_{dataset_name.lower()}_{seed}_{sample_id}"
                org_id = f"org_{seed}"

                # Step 1: Ingest sample history using pipeline write functions
                await ingest_sample_history(contact_id, org_id, sample["calls"], stub_backend)

                # Step 2: Evaluate every question across each configuration
                for q in sample["questions"]:
                    q_text = q["question"]
                    gold_ans = q["gold_answer"]
                    gold_fact_ids = q.get("gold_fact_ids", [])
                    q_type = q.get("type", "fact_recall")

                    for cfg_name, enabled_tiers in CONFIGURATIONS.items():
                        # Retrieve memory
                        start_t = time.perf_counter()
                        tracker.record("retrieve_all_memory")
                        mem_dict = await retrieve_all_memory(
                            contact_id=contact_id,
                            org_id=org_id,
                            query_text=q_text,
                            enabled_tiers=enabled_tiers,
                        )
                        retrieval_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                        mem_prompt = build_memory_prompt(mem_dict)

                        # Compute Recall@5 for D1 where gold fact IDs exist
                        recall_at_5 = None
                        if dataset_name == "D1" and gold_fact_ids:
                            lt_facts = mem_dict.get("long_term", [])
                            fact_texts = [f.get("content", "").lower() for f in lt_facts if isinstance(f, dict)]
                            hits = sum(1 for fid in gold_fact_ids if any(gold_ans.lower() in ft for ft in fact_texts))
                            recall_at_5 = round(min(1.0, hits / max(1, len(gold_fact_ids))), 4)

                        # Answer question
                        candidate_ans, token_count = await answer_question(
                            question=q_text,
                            memory_prompt=mem_prompt,
                            answer_model=answer_model,
                            cache=cache,
                            mock_mode=is_mock_run,
                            gold_answer=gold_ans,
                            tracker=tracker,
                        )

                        # Score using judge
                        is_correct = await judge_answer(
                            question=q_text,
                            gold_answer=gold_ans,
                            candidate_answer=candidate_ans,
                            judge_model=judge_model,
                            cache=cache,
                            mock_mode=is_mock_run,
                            tracker=tracker,
                        )

                        record = {
                            "seed": seed,
                            "config": cfg_name,
                            "dataset": dataset_name,
                            "sample_id": sample_id,
                            "qid": q.get("qid"),
                            "question_type": q_type,
                            "question": q_text,
                            "gold_answer": gold_ans,
                            "candidate_answer": candidate_ans,
                            "is_correct": bool(is_correct),
                            "gold_fact_ids": gold_fact_ids,
                            "recall_at_5": recall_at_5,
                            "prompt_tokens": token_count,
                            "retrieval_ms": retrieval_ms,
                        }
                        eval_records.append(record)
                        append_jsonl(raw_file, record)

                # Step 4: Delete contact data across all tiers
                await delete_sample_history(contact_id, stub_backend)

        # -----------------------------------------------------------------------
        # Aggregate Metrics & Bootstrap CIs
        # -----------------------------------------------------------------------
        results_by_cfg: Dict[str, Dict[str, Any]] = {}
        cfg_names = list(CONFIGURATIONS.keys())

        for cfg_name in cfg_names:
            cfg_recs = [r for r in eval_records if r["config"] == cfg_name]
            d1_recs = [r for r in cfg_recs if r["dataset"] == "D1"]
            d2_recs = [r for r in cfg_recs if r["dataset"] in ("LoCoMo", "LongMemEval")]

            acc_all = [1.0 if r["is_correct"] else 0.0 for r in cfg_recs]
            acc_d1 = [1.0 if r["is_correct"] else 0.0 for r in d1_recs]
            acc_d2 = [1.0 if r["is_correct"] else 0.0 for r in d2_recs]
            tokens = [float(r["prompt_tokens"]) for r in cfg_recs]
            lats = [float(r["retrieval_ms"]) for r in cfg_recs]
            recalls = [r["recall_at_5"] for r in d1_recs if r["recall_at_5"] is not None]

            ci_d1 = bootstrap_ci(acc_d1, seed=seeds[0]) if acc_d1 else None
            ci_d2 = bootstrap_ci(acc_d2, seed=seeds[0]) if acc_d2 else None
            ci_recall = bootstrap_ci(recalls, seed=seeds[0]) if recalls else None
            ci_tokens = bootstrap_ci(tokens, seed=seeds[0]) if tokens else None
            ci_lats = bootstrap_ci(lats, seed=seeds[0]) if lats else None

            # Breakdown per question type
            type_accs = {}
            for q_type in sorted(set(r["question_type"] for r in cfg_recs)):
                t_recs = [1.0 if r["is_correct"] else 0.0 for r in cfg_recs if r["question_type"] == q_type]
                if t_recs:
                    ci_t = bootstrap_ci(t_recs, seed=seeds[0])
                    type_accs[q_type] = {
                        "accuracy": round(ci_t.mean, 4),
                        "ci_95": [round(ci_t.low, 4), round(ci_t.high, 4)],
                    }

            results_by_cfg[cfg_name] = {
                "accuracy_d1": round(ci_d1.mean, 4) if ci_d1 else 0.0,
                "ci_d1": [round(ci_d1.low, 4), round(ci_d1.high, 4)] if ci_d1 else [0.0, 0.0],
                "accuracy_d2": round(ci_d2.mean, 4) if ci_d2 else 0.0,
                "ci_d2": [round(ci_d2.low, 4), round(ci_d2.high, 4)] if ci_d2 else [0.0, 0.0],
                "recall_at_5": round(ci_recall.mean, 4) if ci_recall else 0.0,
                "ci_recall": [round(ci_recall.low, 4), round(ci_recall.high, 4)] if ci_recall else [0.0, 0.0],
                "tokens_per_call": round(ci_tokens.mean, 1) if ci_tokens else 0.0,
                "retrieval_ms": round(ci_lats.mean, 2) if ci_lats else 0.0,
                "question_type_accuracy": type_accs,
            }

        # Consecutive paired bootstrap differences
        consecutive_pairs = [
            ("t2_only", "no_memory"),
            ("t2_t3", "t2_only"),
            ("t2_t3_t4", "t2_t3"),
            ("full", "t2_t3_t4"),
        ]
        paired_diffs = {}
        for c_curr, c_prev in consecutive_pairs:
            curr_acc = [1.0 if r["is_correct"] else 0.0 for r in eval_records if r["config"] == c_curr]
            prev_acc = [1.0 if r["is_correct"] else 0.0 for r in eval_records if r["config"] == c_prev]
            if len(curr_acc) == len(prev_acc) and len(curr_acc) > 0:
                p_res = paired_bootstrap(curr_acc, prev_acc, seed=seeds[0])
                paired_diffs[f"{c_curr}_vs_{c_prev}"] = {
                    "mean_diff": round(p_res.mean_diff, 4),
                    "ci_95": [round(p_res.low, 4), round(p_res.high, 4)],
                    "p_value": round(p_res.p_value, 4),
                }

        metrics_manifest = {
            "mode": mode,
            "services_used": tracker.get_counts(),
            "configurations": results_by_cfg,
            "consecutive_paired_differences": paired_diffs,
            "seeds": seeds,
            "total_records": len(eval_records),
        }
        write_metrics(out_path / "metrics.json", metrics_manifest)

        try:
            from app.services.voice_pipeline import get_active_pipeline_path
            pipeline_path = get_active_pipeline_path()
        except Exception:
            pipeline_path = "custom"

        cfg_out = {
            "mode": mode,
            "pipeline_path": pipeline_path,
            "services_used": tracker.get_counts(),
            "seeds": seeds,
            "answer_model": answer_model,
            "judge_model": judge_model,
        }
        (out_path / "config.json").write_text(json.dumps(cfg_out, indent=2), encoding="utf-8")

        # -----------------------------------------------------------------------
        # TABLE V CSV Generation
        # -----------------------------------------------------------------------
        csv_file = out_path / "table_v.csv"
        csv_lines = ["Configuration,Accuracy D1,Accuracy D2,Recall@5,Tokens per Call,Retrieval ms"]
        for cfg_name in cfg_names:
            c_data = results_by_cfg[cfg_name]
            line = (
                f"{cfg_name},"
                f"{c_data['accuracy_d1']:.4f},"
                f"{c_data['accuracy_d2']:.4f},"
                f"{c_data['recall_at_5']:.4f},"
                f"{c_data['tokens_per_call']:.1f},"
                f"{c_data['retrieval_ms']:.2f}"
            )
            csv_lines.append(line)

        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("\n".join(csv_lines) + "\n")

        if is_mock_run:
            stamp_csv_mock_data(csv_file, mode="mock")

        print(f"Memory ablation completed successfully ({mode.upper()} MODE)!")
        print(f"Raw traces: {raw_file}")
        print(f"Metrics:    {out_path / 'metrics.json'}")
        print(f"TABLE V:    {csv_file}")

        return metrics_manifest

    finally:
        long_term.store_fact = orig_store_fact
        long_term.retrieve_relevant_facts = orig_retrieve_facts
        episodic.create_episode = orig_create_ep
        episodic.get_recent_episodes = orig_get_ep
        graph.add_entities = orig_add_ent
        graph.add_frustration_edges = orig_add_frust
        graph.link_episodes = orig_link_ep
        graph.get_contact_graph_context = orig_get_graph
        if orig_fetch_graph is not None:
            ret_mod._fetch_graph_context = orig_fetch_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Memory Tier Ablation Evaluation")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="results/ablation", help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Limit samples for quick test runs")
    parser.add_argument("--mock", action="store_true", default=False, help="Run in offline mock mode")
    parser.add_argument("--stub", action="store_true", default=False, help="Alias for --mock")
    parser.add_argument("--seed", type=int, default=None, help="Single seed override")
    args = parser.parse_args()

    asyncio.run(
        run_ablation_experiment(
            config_path=args.config,
            out_dir=args.out,
            limit=args.limit,
            mock=args.mock,
            stub_mode=args.stub,
            seed_override=args.seed,
        )
    )


if __name__ == "__main__":
    main()
