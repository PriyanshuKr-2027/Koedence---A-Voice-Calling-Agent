### TABLE VI: Emotion Recognition Performance on D3

| Signal | Macro-F1 | Valence MAE | Pearson r | Added latency (ms) |
|:---|:---:|:---:|:---:|:---:|
| Text only (LLM) | 0.85 [0.68, 0.96] | 0.25 [0.11, 0.44] | 0.72 | 0.00 |
| Audio only (Hume) | 0.85 [0.68, 0.96] | 0.29 [0.15, 0.49] | 0.70 | 0.01 |
| Fused, w=0.6 | 0.85 [0.68, 0.96] | 0.28 [0.13, 0.47] | 0.71 | 0.00 |
| Fused, best w (0.0) | 0.85 | 0.25 | 0.72 | 0.00 |