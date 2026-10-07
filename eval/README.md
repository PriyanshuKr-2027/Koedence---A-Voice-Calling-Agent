# VoCall Evaluation Suite

Benchmark suite for VoCall's voice pipelines, multi-tier memory retrieval, multimodal emotion fusion, and DPDP compliance.

All scripts accept `--config` and `--out`. Random seeds come directly from `eval/config.yaml` to ensure experiments reproduce cleanly.

---

## Quickstart

Run individual benchmarks or trigger the full battery using `make`:

```bash
# Run everything
make all

# Run specific experiments
make memory
make emotion
make wer
make latency
make erasure
make figures
```

If `make` isn't installed on your machine, run the Python modules directly:

```bash
python -m eval.experiments.memory --config eval/config.yaml --out results
python -m eval.experiments.emotion --config eval/config.yaml --out results
python -m eval.experiments.wer --config eval/config.yaml --out results
python -m eval.experiments.latency --config eval/config.yaml --out results
python -m eval.experiments.erasure --config eval/config.yaml --out results
python -m eval.experiments.figures --config eval/config.yaml --out results
```

---

## Configuration (`eval/config.yaml`)

All parameters live in `eval/config.yaml`. The values match VoCall's production settings:

| Parameter | Value | Source File | Purpose |
|---|---|---|---|
| `k` | `5` | `app/services/memory/long_term.py` | Top facts retrieved from pgvector |
| `tau` | `0.75` | `app/services/memory/long_term.py` | Cosine similarity threshold |
| `episodic_limit` | `3` | `app/services/memory/retriever.py` | Prior call episodes loaded per contact |
| `fusion_w` | `0.6` | `app/services/emotion/fusion.py` | Audio weight in audio-text fusion |
| `tone_threshold` | `0.6` | `app/services/emotion/fusion.py` | Audio confidence cutoff for dominant tone |
| `alert_threshold` | `0.7` | `app/services/emotion/fusion.py` | Frustration trigger (`valence < -0.7`) |
| `embedding_model` | `nomic-embed-text-v1_5` | `app/services/memory/long_term.py` | pgvector 1536-dim embeddings |
| `answer_model` | `llama-3.3-70b-versatile` | `trigger/post_call_pipeline.py` | Main conversational agent |
| `judge_model` | `llama-3.3-70b-versatile` | Evaluation judge | LLM judge for qualitative checks |
| `seeds` | `[0, 1, 2]` | Config root | Seeds for runs and bootstrap resampling |

---

## Experiments

### 1. Memory Retrieval & Tier Ablation (`make memory` / `make ablation`)
Evaluates `retrieve_all_memory` and `build_memory_prompt` from `app/services/memory/retriever.py`.
- **Retrieval Baseline**: Sweeps similarity threshold $\tau = 0.75$ and top-$k = 5$ against unconstrained baseline retrieval.
- **Tier Ablation (`eval/memory/run_ablation.py`)**: Evaluates 5 memory configurations (`no_memory`, `t2_only`, `t2_t3`, `t2_t3_t4`, `full`) on D1, LoCoMo, and LongMemEval.
  - Ingests call turns through pipeline write calls (`episodic.create_episode`, `long_term.store_fact`, and `graph.add_entities`).
  - Evaluates questions with temperature 0 and scores answers with the judge model.
  - Emits `raw.jsonl`, `metrics.json` with 95% bootstrap CIs and consecutive paired differences, and `table_v.csv` (matching TABLE V columns).
  - Clears all contact state after each sample.

```bash
# Run ablation (use --limit 5 for quick trials, --stub for offline execution)
python -m eval.memory.run_ablation --config eval/config.yaml --out results/ablation --stub

# Export 50 items for human review
python -m eval.memory.judge_check --raw results/ablation/raw.jsonl --out results/ablation/judge_review.csv

# Score agreement after filling human labels
python -m eval.memory.judge_check --evaluate results/ablation/judge_review.csv
```

### 2. Emotion Fusion & Annotator Reliability (`make emotion`)
Evaluates multimodal emotion fusion from `app/services/emotion/fusion.py` against dataset D3 (`eval/data/d3/labels.csv`):
- **Inter-Annotator Reliability (`eval/emotion/kappa.py`)**: Computes unweighted Cohen's Kappa for categorical emotion classes and quadratic-weighted Kappa for ordinal valence ratings. Writes adjudicated gold labels to `eval/data/d3/gold_labels.csv`, flagging disagreement rows.
- **Multimodal Evaluation (`eval/emotion/run_emotion.py`)**: Compares text-only (Groq NLP), audio-only (Hume AI), and fused signals (`fuse_emotion_signals`) with configurable `audio_weight`.
  - Caches Hume and LLM inferences in `.eval_cache/`.
  - Emits `table_vi.csv` (TABLE VI) with Macro-F1, Accuracy, Valence MAE, Pearson $r$, and signal latency.
  - Generates `sweep.csv` sweeping $w \in [0.0, 1.0]$ in steps of 0.1 for Fig. 5(b).
  - Extracts the 20 clips with largest text-vs-audio valence divergence into `disagreements.csv`.
  - Computes precision and recall for prompt tone modification and frustration alert triggers on angry/frustrated clips.

```bash
# Inter-annotator agreement and gold label adjudication
python -m eval.emotion.kappa --input eval/data/d3/labels.csv --out eval/data/d3/gold_labels.csv

# Run emotion evaluation experiment (use --stub for offline mock mode)
python -m eval.emotion.run_emotion --config eval/config.yaml --out results/emotion --stub
```


### 3. Hinglish STT WER (`make wer`)
Compares Sarvam AI's Saarika v2 with Groq Whisper large-v3 using Levenshtein Word Error Rate on code-switched Hindi-English dialogue phrases from `app/services/stt.py`. Reports paired bootstrap confidence intervals.

### 4. Turn Latency (`make latency`)
Benchmarks turn duration across:
1. Speech recognition (`transcribe_audio` in `app/services/stt.py`)
2. Context assembly and generation (`retrieve_all_memory` in `app/services/memory/retriever.py`)
3. Speech synthesis time-to-first-byte (`synthesize_speech` in `app/services/tts.py`)

Outputs mean, p50, p90, and p99 percentiles in milliseconds.

### 5. Memory Erasure (`make erasure`)
Audits DPDP Act 2023 "Forget Me" cascade deletion from `app/routers/contacts.py#cascade_delete_contact_memory`. Verifies zero residual state across all 5 tiers:
- Tier 1: Upstash Redis short-term memory keys
- Tier 2: Supabase pgvector long-term facts
- Tier 3: Postgres episodic call records
- Tier 4: FalkorDB knowledge graph nodes and edges
- Tier 5: Supabase intent events and audit entries

### 6. Figures and Aggregation (`make figures`)
Scans `results/` for the latest runs and compiles summary metrics into `results/figures/<timestamp>/aggregated_experiment_summary.json`.

---

## Reproducibility and Run Logging

Every run invokes `start_run(experiment)` from `eval/common/runlog.py`, creating `results/<experiment>/<timestamp>/` with a `config.json` manifest:

```json
{
  "experiment": "memory",
  "timestamp": "20261005_054238",
  "seed": 0,
  "git_commit": "34175756cf365a1c8a31fb234283ba3b74ae2e53",
  "python_version": "3.12.3 ...",
  "package_versions": {
    "fastapi": "0.111.1",
    "pydantic": "2.11.7",
    "numpy": "1.26.4",
    "scipy": "1.17.0",
    "scikit-learn": "1.8.0"
  },
  "model_names": {
    "embedding_model": "nomic-embed-text-v1_5",
    "answer_model": "llama-3.3-70b-versatile"
  },
  "config": { ... }
}
```

### Disk Cache (`eval/common/cache.py`)
Paid API calls to Groq, Hume, and Sarvam are saved in `.eval_cache/` using SHA-256 keys derived from `(provider, model, input)`. If an exact prompt or audio buffer was run before, it returns immediately from disk without hitting external network endpoints.

### Cost and Token Accounting (`eval/common/cost.py`)
Tracks prompt tokens, completion tokens, wall time, and estimated dollar costs per call. Saves totals alongside the run metrics in `cost_summary.json`.

---

## Tests

Test statistical routines with pytest:

```bash
pytest tests/test_eval_common.py
```

Tests run offline without network access, verifying bootstrap confidence intervals, paired tests, McNemar's exact binomial test, and Cohen's Kappa against hand-calculated analytical values.
