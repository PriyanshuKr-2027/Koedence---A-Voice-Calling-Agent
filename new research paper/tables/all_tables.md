### TABLE V: Memory-Tier Ablation on D1 and D2

| Configuration | Accuracy D1 (%) | Accuracy D2 (%) | Recall@5 | Tokens / call | Retrieval ms |
|:---|:---:|:---:|:---:|:---:|:---:|
| No memory | 25.0 [6.2, 43.8] | 25.0 [0.0, 50.0] | n/a | 44.3 | 0.07 |
| T2 vector only | 25.0 [6.2, 43.8] | 100.0 [100.0, 100.0] | 0.00 [0.00, 0.00] | 92.1 | 0.09 |
| T2 + T3 | 25.0 [6.2, 43.8] | 100.0 [100.0, 100.0] | 0.00 [0.00, 0.00] | 161.1 | 0.08 |
| T2 + T3 + T4 (graph) | 37.5 [18.8, 62.5] | 100.0 [100.0, 100.0] | 0.00 [0.00, 0.00] | 341.4 | 0.08 |
| Full (T1 to T4) | 37.5 [18.8, 62.5] | 100.0 [100.0, 100.0] | 0.00 [0.00, 0.00] | 341.4 | 0.08 |

---

### TABLE VI: Emotion Recognition Performance on D3

| Signal | Macro-F1 | Valence MAE | Pearson r | Added latency (ms) |
|:---|:---:|:---:|:---:|:---:|
| Text only (LLM) | 0.85 [0.68, 0.96] | 0.25 [0.11, 0.44] | 0.72 | 0.00 |
| Audio only (Hume) | 0.85 [0.68, 0.96] | 0.29 [0.15, 0.49] | 0.70 | 0.01 |
| Fused, w=0.6 | 0.85 [0.68, 0.96] | 0.28 [0.13, 0.47] | 0.71 | 0.00 |
| Fused, best w (0.0) | 0.85 | 0.25 | 0.72 | 0.00 |

---

### TABLE VII: Speech Recognition Word Error Rate (WER) across Languages

| System | Hindi | Hinglish | English | Latency (ms) |
|:---|:---:|:---:|:---:|:---:|
| Whisper large-v3 (Groq) | 0.0 [0.0, 0.0] | 4.0 [0.8, 7.9] | 0.0 [0.0, 0.0] | 13.3 [12.1, 14.8] |
| Saarika v2 (Sarvam) | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 18.4 [15.7, 20.9] |
| Language-routed (VoCall) | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 19.1 [16.5, 21.7] |

---

### TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit

| Tier | Items before (mean) | Items after (mean) | Contacts with residue |
|:---|:---:|:---:|:---:|
| T1 Redis | 4.0 | 4.0 | 20 / 20 (100%) |
| T2 pgvector | 1.0 | 0.0 | 0 / 20 (0%) |
| T3 Postgres | 1.0 | 0.0 | 0 / 20 (0%) |
| T4 FalkorDB | 5.0 | 0.0 | 0 / 20 (0%) |
| Completeness C | n/a | n/a | 0.57 |