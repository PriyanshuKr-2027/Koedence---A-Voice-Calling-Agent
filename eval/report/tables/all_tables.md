### TABLE V: Memory-Tier Ablation on D1 and D2

| Configuration | Accuracy D1 (%) | Accuracy D2 (%) | Recall@5 | Tokens / call | Retrieval ms |
|:---|:---:|:---:|:---:|:---:|:---:|
| No memory | n/a | n/a | n/a | n/a | n/a |
| T2 vector only | n/a | n/a | n/a | n/a | n/a |
| T2 + T3 | n/a | n/a | n/a | n/a | n/a |
| T2 + T3 + T4 (graph) | n/a | n/a | n/a | n/a | n/a |
| Full (T1 to T4) | n/a | n/a | n/a | n/a | n/a |

---

### TABLE VI: Emotion Recognition Performance on D3

| Signal | Macro-F1 | Valence MAE | Pearson r | Added latency (ms) |
|:---|:---:|:---:|:---:|:---:|
| Text only (LLM) | n/a | n/a | n/a | n/a |
| Audio only (Hume) | n/a | n/a | n/a | n/a |
| Fused, w=0.6 | n/a | n/a | n/a | n/a |
| Fused, best w from sweep | n/a | n/a | n/a | n/a |

---

### TABLE VII: Speech Recognition Word Error Rate (WER) across Languages

| System | Hindi | Hinglish | English | Latency (ms) |
|:---|:---:|:---:|:---:|:---:|
| Whisper large-v3 (Groq) | n/a | n/a | n/a | n/a |
| Saarika v2 (Sarvam) | n/a | n/a | n/a | n/a |
| Language-routed (VoCall) | n/a | n/a | n/a | n/a |

---

### TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit

| Tier | Items before (mean) | Items after (mean) | Contacts with residue |
|:---|:---:|:---:|:---:|
| T1 Redis | n/a | n/a | n/a |
| T2 pgvector | n/a | n/a | n/a |
| T3 Postgres | n/a | n/a | n/a |
| T4 FalkorDB | n/a | n/a | n/a |
| Completeness C | n/a | n/a | n/a |