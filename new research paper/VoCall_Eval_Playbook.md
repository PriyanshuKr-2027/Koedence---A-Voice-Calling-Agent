# VoCall Evaluation Playbook

What to do to turn the paper draft into real results: checklist, datasets, formulas, libraries, models, and Cursor-ready prompts.

Status labels used below: **Verified** = I saw the source in a search this session. **Background** = from my own knowledge, not re-checked; confirm before relying on it.

---

## Part A. Do these in this order

1. **Freeze the system.** Pick one embedding model, fix the thresholds, write them in one config file (see Part F). Tag the git commit. Every experiment logs this commit.
2. **Fix the erasure scope first.** Your schema keeps personal data in tables the erasure endpoint does not touch (see Part F, item 1). Fix it or report it; the paper's Algorithm 1 must match what the code does.
3. **Build the evaluation harness** (Prompt 0 below), then the memory ablation on LoCoMo and LongMemEval (public data, no recording needed).
4. **Generate D1** (synthetic callers) and run the same ablation on it.
5. **Record D3 and D4** (your own role-played calls). Start this early because it needs people and consent forms.
6. **Annotate D3** with two annotators and compute agreement.
7. **Run emotion, WER, latency, erasure experiments.**
8. **Regenerate Fig. 4 and 5, fill Tables V to VIII**, rewrite every `[bracket]` in Sections IV and V, delete claims the data does not support.
9. **Move into the venue template** and ask your mentor for the target conference. I have not checked any call for papers.

Optional but strengthens the paper: run Mem0 (open-source package) and Graphiti (Zep's open-source graph engine) as baselines on the same LoCoMo subset. Background: both are public repositories; confirm current install steps.

---

## Part B. Datasets

| Dataset | Use in paper | Where | Notes | Status |
|:--|:--|:--|:--|:--|
| **LoCoMo** | D2, memory ablation | `https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json` (also on Hugging Face as `snap-research/locomo`) | 10 long conversations. Question types: single-hop, multi-hop, temporal, open-domain, adversarial. Check the repository license before use. | Verified |
| **LongMemEval** | Extra memory benchmark | Hugging Face `xiaowu0162/longmemeval-cleaned`, files `longmemeval_s_cleaned.json` and `longmemeval_m_cleaned.json` | Use the small split first. Text only. | Verified |
| **IITG-HingCoS** | D4, Hinglish WER | IIT Guwahati; described in Speech Communication vol. 110 (2019) | 9,251 utterances, about 25 h, 101 speakers, **8 kHz audio**, which matches telephone bandwidth. A 2025 data paper lists it as available, but I did not find the download link. Check the paper's data section or email the authors. | Verified (existence); access route unconfirmed |
| **HiACC** | D4 alternative | Zenodo ("HiACC: Hinglish Adult & Children Code-switched Corpus"), Data in Brief 2025 | 5.24 h, 16 kHz, adults and children, read and spontaneous speech. Downsample to 8 kHz to mimic phone audio. | Verified |
| **MC-EIU** | Possible D3 source and intent labels | arXiv:2407.02751 (already in your project files) | Emotion and intent labels on conversations. Read its data-availability section for access, language, and license. | Background |
| **MELD** (audio + text emotion) | Optional public emotion check | Public GitHub release from the authors | English TV dialogue, not phone quality, so use only as a sanity check. | Background |
| **IEMOCAP** | Optional | Needs a license request to USC | Do not plan around it unless the request is approved. | Background |
| **D1 synthetic callers** | Memory ablation on your workload | You generate it (Prompt 1) | No public benchmark has repeat-caller histories with recurring complaints. | n/a |
| **D3 role-played calls** | Emotion signals | You record it | No public Hinglish phone-call emotion data that I found. Plan 3 scenarios (billing dispute, appointment change, refund) times 3 tones (calm, irritated, angry), at least 4 speakers, 8 kHz phone-call recording. Write a consent form and anonymise names. | n/a |
| **D5 latency traces** | Latency | Your own live and scripted calls | Report region and network. | n/a |

Do not call D1 "real". The paper already states it is synthetic; keep that wording.

---

## Part C. Formulas to implement (all appear in the paper)

- **Recall@k:** `mean over questions of |retrieved_k ∩ gold| / |gold|`.
- **MRR (optional):** `mean of 1 / rank of first gold fact`.
- **Macro-F1:** average of per-class F1; use `sklearn.metrics.f1_score(average="macro")`.
- **WER:** `(S + D + I) / N`. **CER:** same on characters. Report both because of script mixing.
- **Valence MAE:** `mean |v_pred - v_gold|`; **Pearson r** with `scipy.stats.pearsonr`.
- **Cohen's kappa:** `(p_o - p_e) / (1 - p_e)`, with `p_o` observed agreement and `p_e` chance agreement. Use `sklearn.metrics.cohen_kappa_score`; for 5-point valence use `weights="quadratic"`.
- **Bootstrap 95% CI:** resample the test items 1,000 times, recompute the metric, take the 2.5th and 97.5th percentiles.
- **Paired comparison of two configurations:** paired bootstrap on the per-item score difference; report the difference and its CI. For binary correctness you can also run McNemar's test.
- **Erasure completeness:** `C = 1 - sum(n_after) / sum(n_before)` (Eq. 7).
- **Latency:** p50, p95, p99 per stage and for the full turn (Eq. 1).

---

## Part D. Libraries

| Need | Library |
|:--|:--|
| WER and CER | `jiwer` |
| Classification metrics, kappa | `scikit-learn` |
| Correlation, bootstrap | `scipy`, `numpy` |
| Plots | `matplotlib` (the placeholder chart script in the figures zip already uses it) |
| Audio resampling and 8 kHz simulation | `librosa` or `torchaudio`, plus `soundfile` |
| Devanagari and Roman conversion | `indic-transliteration` or AI4Bharat IndicXlit (Background; confirm which you prefer) |
| Data loading | `datasets` (Hugging Face), `pandas` |
| Graph | the `falkordb` Python client you already use |
| Experiment config | `pyyaml` |

---

## Part E. Models and settings to decide

- **Embedding model.** One model, one dimension, everywhere. Your pgvector column size must equal the model's output size. For Hinglish facts, prefer a multilingual embedder; `BAAI/bge-m3` (1,024 dimensions) is multilingual and was used in a LongMemEval reproduction I saw (Verified). Whatever you pick, re-embed the data after switching and update the `vector(N)` column.
- **Answer LLM.** The one VoCall uses (llama-3.3-70b on Groq). Temperature 0 for evaluation.
- **Judge LLM.** A different model family from the answer LLM, temperature 0. Hand-label 50 answers and report judge-versus-human agreement. If you reuse the answer model as judge, say so in the limitations.
- **Fusion weight w.** Sweep 0 to 1 in steps of 0.1; keep 0.6 only if the data supports it.
- **Thresholds.** Choose one tone threshold and one alert threshold (the docs currently list -0.4, -0.7 and 0.75).

---

## Part F. Issues to resolve in the project

1. **Erasure scope.** `system_design.md` lists tables that hold personal data: `call_turns` (transcripts), `call_transcripts`, `emotion_events`, `intent_events`, `memory_graph_nodes`, `calls.recording_url`, and `contacts`. The erasure description only covers `memory_long_term`, `memory_episodic`, Redis, and the graph. Either extend the endpoint to cover these or state the limit. The probe in Prompt 6 checks all of them.
2. **Third-party retention.** Audio and text sent to Groq, Hume, Sarvam, Cartesia, and Twilio is outside your control. Keep this in the limitations.
3. **Docs versus code.** Fusion weight (fixed 0.6/0.4 in code, dynamic alpha in `INTENT_EMOTION_ENGINE.md`), Hume emotion count (27 versus 43), graph edge names (`MENTIONED` versus `MENTIONED_ENTITY`, `FRUSTRATED_ABOUT` versus `EXPERIENCED_FRUSTRATION`), pipeline step count (8 versus 11), and the embedding model. Decide which is true and edit the others.
4. **Competitor table in `VoCall_Research_Diagrams.md`.** Verify the cells for Vapi, Retell, and OmniDim before reusing them anywhere.
5. **Reference placeholders.** Search every `[CONFIRM]` in the paper's reference list.
6. **Ethics.** Consent forms for D3 and D4 recordings, anonymised storage, and a note in the paper that participants agreed to recording.

---

## Part G. Cursor prompts

Paste them in order. Each one assumes the previous one is done. Tell Cursor to read the listed files first and adapt to the real function names, because the docs may differ from the code.

### Prompt 0. Evaluation scaffold

```
You are working in the VoCall repo (FastAPI backend in app/, tests in tests/). Create a new top-level folder eval/ for research experiments. Do not change existing behaviour.

First read: app/core/config.py, app/services/memory/retriever.py, app/services/emotion/fusion.py, app/services/stt.py, app/services/tts.py, app/routers/contacts.py, trigger/post_call_pipeline.py. Use the real function names you find.

Create:
- eval/config.yaml: one place for k=5, tau=0.75, episodic_limit=3, fusion_w=0.6, tone_threshold, alert_threshold, embedding_model, answer_model, judge_model, seeds=[0,1,2], paths to datasets.
- eval/common/runlog.py: start_run(experiment) creates results/<experiment>/<timestamp>/ and writes config.json containing the config, git commit SHA, python and package versions, model names, and seed. Provide append_jsonl(), write_metrics().
- eval/common/stats.py: bootstrap_ci(values, n=1000), paired_bootstrap(a, b, n=1000), mcnemar(a, b), cohen_kappa wrapper.
- eval/common/cache.py: disk cache keyed by sha256 of (provider, model, input) so paid API calls (LLM, judge, Hume, STT) are never repeated.
- eval/common/cost.py: log tokens and wall time per call.
- eval/README.md explaining how to run each experiment, and a Makefile with targets: memory, emotion, wer, latency, erasure, figures, all.
- tests/test_eval_common.py with pytest tests for stats.py using small hand-computed examples.

Rules: every random operation uses the seed from config; every script takes --config and --out; no network calls in the tests. When finished, run pytest tests/test_eval_common.py and show the output.
```

### Prompt 1. Synthetic caller histories (D1)

```
In eval/data/, create gen_d1.py that generates dataset D1: synthetic caller histories for memory evaluation.

Spec:
- N callers (default 60). Each has a persona sheet: name, phone, language style (English, Hinglish), 4 to 6 stable facts (plan type, preferred language, billing date, address area, preferred contact time, a family-related preference), and 1 recurring complaint topic.
- Each caller gets M calls (default 5 to 8) as short text transcripts (6 to 14 turns), written by an LLM from the persona sheet plus a per-call script: which facts are mentioned, whether the recurring complaint appears (at least 3 of the calls), and the caller's emotional trajectory (calm, irritated, angry).
- Questions per caller (default 8), each with a gold answer and gold fact ids, in these types: fact_recall, preference, recurring_complaint_pattern ("Which topic has this caller complained about most?"), temporal ("What did the caller ask for in the most recent call?"), and adversarial (asks about something never said; correct answer is "unknown").
- Output JSONL: callers.jsonl (persona + seeded facts with ids), calls.jsonl (caller_id, call_index, turns, emotion_arc), questions.jsonl (caller_id, qid, type, question, gold_answer, gold_fact_ids).
- Use the LLM through the repo's llm service, temperature 0.7 for generation, seed logged. Cache all calls.
- Add eval/data/check_d1.py which samples 20 conversations and prints them for manual realism review, and prints counts per question type.

Keep the generator deterministic given the seed. Add a pytest that runs the generator with N=2 and a stubbed LLM and checks the schema.
```

### Prompt 2. Memory ablation runner

```
Create eval/memory/run_ablation.py.

Goal: compare memory configurations on three datasets: D1 (eval/data output), LoCoMo (locomo10.json), and LongMemEval small split.

Configurations: no_memory, t2_only, t2_t3, t2_t3_t4, full (T1 to T4). Add an optional parameter enabled_tiers to retrieve_all_memory in app/services/memory/retriever.py, defaulting to all tiers so current behaviour is unchanged. Update the existing memory tests if needed.

Per sample:
1. Create a fresh contact id (one per caller or per LoCoMo/LongMemEval conversation). Ingest history by calling the same write functions the post-call pipeline uses (episodic summary, fact extraction and embedding, graph update). Do not use a shortcut path. For LoCoMo and LongMemEval feed the dialogue turns as text; no audio.
2. For every question, build the memory block with the configuration, call the answer LLM with temperature 0, and store the answer, retrieved items, prompt token count, and retrieval latency in raw.jsonl.
3. Score: for D1 and LongMemEval use the judge model with a strict JSON output {"correct": true|false} and cache the verdicts; for LoCoMo use the judge too, and report per question type. Compute Recall@k only where gold fact ids exist (D1).
4. After each sample, delete the contact's data from all tiers so runs do not leak into each other.

Outputs: metrics.json with mean and bootstrap 95% CI per configuration and per question type; paired-bootstrap difference between consecutive configurations; a CSV matching TABLE V columns (accuracy D1, accuracy D2, Recall@5, tokens per call, retrieval ms). Run over seeds from config and report mean.

Also write eval/memory/judge_check.py that samples 50 answers, writes them to a CSV with an empty "human_label" column, and later computes agreement between the judge and the human labels.

Add --limit for quick runs. Do not call real services in tests; provide a stub mode.
```

### Prompt 3. Emotion experiment

```
Create eval/emotion/run_emotion.py and eval/emotion/kappa.py.

Input: eval/data/d3/labels.csv with columns: clip_id, audio_path, transcript, annotator_1_label, annotator_1_valence, annotator_2_label, annotator_2_valence. Labels use a config-defined class set; valence is a 5-point scale mapped to [-1, 1].

kappa.py: compute Cohen's kappa for the categorical labels (unweighted) and for valence (quadratic weights), print both, and write the adjudicated gold label file (rows where annotators disagree are flagged for manual resolution).

run_emotion.py:
- For each clip compute three estimates: text-only (the repo's text_signal), audio-only (audio_signal using Hume), and fused using fuse_emotion_signals. First refactor fuse_emotion_signals to accept an optional audio_weight argument (default 0.6) so the output with default arguments is identical to today's. Add a test proving that.
- Cache every Hume and LLM response.
- Metrics against the adjudicated gold: macro-F1, accuracy, valence MAE, Pearson r, each with bootstrap 95% CI. Report added latency per signal.
- Weight sweep: w from 0 to 1 in steps of 0.1, macro-F1 and valence MAE at each w. Save sweep.csv.
- Error analysis: write the 20 clips where text-only and audio-only disagree the most, with transcripts, to disagreements.csv.
- Also run the 'tone adapter' trigger check: for each clip, record whether the tone instruction and the alert would fire at the configured thresholds, and report precision and recall against gold clips labelled angry or frustrated.

Write TABLE VI-ready CSV and the sweep data for Fig. 5(b).
```

### Prompt 4. Hinglish recognition (WER)

```
Create eval/speech/run_wer.py.

Input: a folder of audio (wav) with reference transcripts in a CSV (utt_id, path, text, language: hi | hinglish | en). Datasets: IITG-HingCoS subset (8 kHz) and/or our recordings.

Steps:
1. Optionally simulate telephony: --telephony resamples to 8 kHz and applies mu-law encode and decode before sending audio to the recognizers.
2. Systems: Whisper large-v3 through the repo's Groq STT path; Saarika through the repo's Sarvam STT path; and the language-routed path (use the router in app/services/stt.py with the agent language set to the row's language). Cache all outputs.
3. Normalisation (write it as a documented function in eval/speech/normalize.py): Unicode NFC, lowercase, strip punctuation, collapse spaces, map Devanagari digits to ASCII digits, expand a small configurable word list for spelling variants. Provide three scoring modes: raw (no script change), roman (transliterate all text to Roman), devanagari (transliterate all to Devanagari). Document the transliteration library used.
4. Metrics with jiwer: WER and CER per system, per language group, per utterance-length bucket (short, medium, long), each with bootstrap 95% CI over utterances. Also record latency per request.
5. Output TABLE VII CSV (rows: systems; columns: Hindi, Hinglish, English WER) and per-utterance errors for the 30 worst cases.

Add tests for normalize.py with five hand-written examples including mixed-script text.
```

### Prompt 5. Latency harness

```
Instrument and measure per-stage latency.

1. In app/services (voice_pipeline.py and webcall_pipeline.py) add a tiny context manager stage(name, call_id, turn_idx) using time.perf_counter_ns that appends {call_id, turn_idx, stage, ms} to a JSONL file when LATENCY_LOG=path is set, and does nothing otherwise. Stages: stt, emotion, memory, intent, llm_ttft, tts_ttfab, network_out, turn_total. Keep overhead negligible; do not change behaviour.
2. Create eval/latency/replay.py that replays a list of prepared WAV turns through the pipeline (English and Hinglish agents) for at least 50 turns per language, discarding the first 3 turns of each call as warm-up. Record region, network type, and time of day in config.json.
3. Create eval/latency/summarise.py that computes p50, p95, p99 per stage and for turn_total, checks Equation 1 (turn_total vs stt + max(emotion, memory, intent) + llm_ttft + tts_ttfab + network_out) and prints the gap, and writes the stacked-bar data for Fig. 5(a) plus the fraction of turns under 800 ms.

If direct pipeline replay is not possible, build the replay through the public webcall endpoints and say which stages can then not be measured.
```

### Prompt 6. Erasure probe

```
Create eval/erasure/run_probe.py and a pytest in tests/test_erasure_probe.py.

Goal: verify that after DELETE /api/v1/contacts/{id}/memory nothing about the contact can be found anywhere in our stores.

Method (canary tokens):
1. Create N test contacts (default 20). For each, generate a unique canary string (for example CANARY-<uuid4 short>). Seed every store with data that contains the canary: a Redis in-call buffer and slot keys; a long-term fact (with embedding); an episodic summary; call_turns and call_transcripts rows; emotion_events and intent_events rows; a graph with Contact, Episode, Entity, Topic and FrustrationEvent nodes whose text contains the canary; a calls row with a recording_url; and memory_graph_nodes rows. Use the real write paths where possible.
2. probe(contact): count retrievable items per store without any threshold: Redis key scan for the contact's call ids (stm:, webcall:, slot:); pgvector similarity search with threshold 0 for the contact id plus a text search for the canary across every table with personal data (ILIKE on text columns); row counts by contact_id and by call_id for each table; FalkorDB node count in the contact's graph and a global search for the canary string across graphs.
3. Run probe (n_before), call the real erasure endpoint, run probe again (n_after).
4. Report per store and per contact: before, after, residue, and completeness C = 1 - sum(after) / sum(before). Report which tables or stores had residue. Do not hide tables that the erasure endpoint does not touch; those are findings.
5. Extra scenarios: erasure while a call is in progress; erasure twice (idempotent); a graph node shared by two contacts must survive for the other contact.
6. Verify the audit log entry exists and contains no raw personal data.

Output TABLE VIII-ready CSV and a residue_report.md listing anything left. Do not modify the erasure endpoint in this task; just report. A separate task will fix the residue.
```

### Prompt 7. Tables and figures from results

```
Create eval/report/make_tables.py and eval/report/make_figures.py.

make_tables.py reads the latest results/ folders and writes TABLE V to VIII as LaTeX (booktabs) and Markdown, using the same column order as the paper. Include mean and 95% CI as "x.x [lo, hi]". If a result file is missing, write "n/a" instead of failing.

make_figures.py regenerates Fig. 4(a), 4(b), 5(a), 5(b) from the same files with matplotlib. Style: DejaVu Sans 8 pt, width 6.9 in, the colours in figs/make_charts.py, no watermark. Save PNG at 300 dpi and PDF.

Then write eval/report/claims_check.py that prints a checklist of the paper's claims against the numbers: does fused beat text-only and audio-only (CI excludes zero)? does the graph tier improve recurring-complaint accuracy? does Hinglish routing reduce WER? is p95 under 800 ms? is erasure completeness 1.0? Print "supported", "not supported", or "inconclusive" for each, so I delete or soften any claim the data does not back.
```

### Prompt 8. Reproducibility package

```
Prepare the repository for artifact release.
- Add a top-level REPRODUCE.md with exact commands (make memory, make emotion, make wer, make latency, make erasure, make figures) and expected runtimes and API costs from the logs.
- Add requirements-eval.txt with pinned versions.
- Add a results/MANIFEST.json listing every run, commit SHA, models, and dataset versions.
- Add a LICENSE check: confirm MIT for our code, and write a DATASETS.md listing each dataset, its source, license, and whether it can be redistributed (do not include datasets whose license forbids it; include download scripts instead).
- Add a scripts/anonymise_audio.md describing how participant recordings were anonymised.
```

---

## Part H. What to change in the paper once results exist

- Replace every highlighted `[bracket]` in Sections IV and V and the abstract.
- Delete or soften any sentence that Prompt 7's `claims_check.py` marks "not supported".
- In the abstract, report the headline numbers with confidence intervals.
- Regenerate Fig. 4 and Fig. 5 without the watermark and update their captions.
- Update Algorithm 1 to match the real erasure endpoint, including the extra tables if you fix the residue.
- If the graph or fusion does not help, keep the negative result in the paper; the draft is written so that it holds either way.
