"""Tests for Emotion Fusion Evaluation, Weight Refactor, and Kappa Adjudication.

Verifies:
  1. fuse_emotion_signals default audio_weight=0.6 produces identical output to legacy call.
  2. audio_weight sweep behavior (w=0.0 vs w=1.0).
  3. kappa.py inter-annotator agreement and gold adjudication.
  4. run_emotion.py produces TABLE VI, sweep.csv, disagreements.csv, and tone trigger metrics offline.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import pytest

# Ensure repo root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.emotion.fusion import fuse_emotion_signals
from eval.data.gen_d3 import create_d3_dataset
from eval.emotion.kappa import compute_inter_annotator_agreement, map_valence_5point_to_unit
from eval.emotion.run_emotion import run_emotion_experiment


def test_fuse_emotion_signals_audio_weight_default_identical():
    """
    Proves that fuse_emotion_signals(text, audio) with default arguments
    yields output identical to fuse_emotion_signals(text, audio, audio_weight=0.6).
    """
    text_signal = {
        "valence": -0.4,
        "arousal": 0.6,
        "dominant": "frustrated",
        "confidence": 0.75,
    }
    audio_signal = {
        "valence": -0.8,
        "arousal": 0.8,
        "dominant": "angry",
        "confidence": 0.85,
    }

    # Default call without audio_weight
    res_default = fuse_emotion_signals(text_signal, audio_signal)

    # Explicit call with audio_weight=0.6
    res_explicit = fuse_emotion_signals(text_signal, audio_signal, audio_weight=0.6)

    # Hand-computed baseline checks:
    # valence = 0.6 * (-0.8) + 0.4 * (-0.4) = -0.48 - 0.16 = -0.64
    # arousal = 0.6 * 0.8 + 0.4 * 0.6 = 0.48 + 0.24 = 0.72
    # dominant = audio_dom ('angry') because audio_conf (0.85) > 0.6
    assert res_default["valence"] == res_explicit["valence"] == -0.64
    assert res_default["arousal"] == res_explicit["arousal"] == 0.72
    assert res_default["dominant"] == res_explicit["dominant"] == "angry"
    assert res_default["confidence"] == res_explicit["confidence"] == 0.85


def test_fuse_emotion_signals_weight_boundaries():
    """Verifies boundary weights: w=0.0 (text-only) and w=1.0 (audio-only)."""
    text_sig = {"valence": 0.5, "arousal": 0.4, "dominant": "happy", "confidence": 0.8}
    audio_sig = {"valence": -0.5, "arousal": 0.7, "dominant": "sad", "confidence": 0.9}

    res_w0 = fuse_emotion_signals(text_sig, audio_sig, audio_weight=0.0)
    assert res_w0["valence"] == 0.5
    assert res_w0["arousal"] == 0.4
    assert res_w0["dominant"] == "happy"

    res_w1 = fuse_emotion_signals(text_sig, audio_sig, audio_weight=1.0)
    assert res_w1["valence"] == -0.5
    assert res_w1["arousal"] == 0.7
    assert res_w1["dominant"] == "sad"


def test_kappa_inter_annotator_and_adjudication(tmp_path):
    """Verifies Cohen's Kappa calculations and gold label adjudication file emission."""
    labels_csv = tmp_path / "labels.csv"
    gold_csv = tmp_path / "gold_labels.csv"

    # Create test labels with known agreement and minor disagreements
    rows = [
        ["clip_01", "a1.wav", "sample 1", "angry", 1, "angry", 1],
        ["clip_02", "a2.wav", "sample 2", "frustrated", 2, "frustrated", 2],
        ["clip_03", "a3.wav", "sample 3", "neutral", 3, "neutral", 3],
        ["clip_04", "a4.wav", "sample 4", "calm", 4, "calm", 4],
        ["clip_05", "a5.wav", "sample 5", "happy", 5, "happy", 5],
        ["clip_06", "a6.wav", "sample 6", "angry", 1, "frustrated", 2],  # disagreement
    ]
    with open(labels_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["clip_id", "audio_path", "transcript", "annotator_1_label", "annotator_1_valence", "annotator_2_label", "annotator_2_valence"])
        writer.writerows(rows)

    metrics = compute_inter_annotator_agreement(labels_csv, gold_csv)
    assert metrics["total_clips"] == 6
    assert metrics["disagreements"] == 1
    assert metrics["cohen_kappa_categorical"] > 0.6
    assert metrics["cohen_kappa_valence_quadratic"] > 0.8
    assert gold_csv.exists()

    with open(gold_csv, "r", encoding="utf-8") as f:
        adjudicated = list(csv.DictReader(f))
    assert len(adjudicated) == 6
    # Verify disagreement row was flagged
    disagreed_row = adjudicated[5]
    assert disagreed_row["needs_adjudication"] == "True"
    assert disagreed_row["agreement"] == "False"


@pytest.mark.asyncio
async def test_run_emotion_experiment_stub_mode(tmp_path):
    """Verifies that run_emotion outputs TABLE VI, sweep.csv, and disagreements.csv offline."""
    out_dir = tmp_path / "emotion_results"
    labels_csv = tmp_path / "labels.csv"
    create_d3_dataset(str(labels_csv))

    summary = await run_emotion_experiment(
        config_path="eval/config.yaml",
        out_dir=str(out_dir),
        labels_csv_path=str(labels_csv),
        stub_mode=True,
    )

    # 1. Output files exist
    table_vi = out_dir / "table_vi.csv"
    sweep_csv = out_dir / "sweep.csv"
    disagreements_csv = out_dir / "disagreements.csv"
    metrics_json = out_dir / "metrics.json"

    assert table_vi.exists()
    assert sweep_csv.exists()
    assert disagreements_csv.exists()
    assert metrics_json.exists()

    # 2. Check TABLE VI columns and signal rows
    with open(table_vi, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    assert reader[0][:6] == ["Signal", "Macro-F1", "Accuracy", "Valence MAE", "Pearson r", "Added Latency ms"]
    assert "MOCK DATA" in reader[0]
    signals = [r[0] for r in reader[1:]]
    assert "Text-Only" in signals
    assert "Audio-Only" in signals
    assert any("Fused" in s for s in signals)

    # 3. Check sweep.csv (11 rows for w=0.0..1.0 in 0.1 steps)
    with open(sweep_csv, "r", encoding="utf-8") as f:
        sweep_rows = list(csv.DictReader(f))
    assert len(sweep_rows) == 11
    weights = [float(r["audio_weight"]) for r in sweep_rows]
    assert weights == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

    # 4. Check disagreements.csv has top 20 or all available
    with open(disagreements_csv, "r", encoding="utf-8") as f:
        disagreements = list(csv.DictReader(f))
    assert 1 <= len(disagreements) <= 20
    assert "valence_difference" in disagreements[0]

    # 5. Check tone adapter trigger metrics
    assert "tone_adapter_trigger" in summary
    assert "precision" in summary["tone_adapter_trigger"]
    assert "recall" in summary["tone_adapter_trigger"]
    assert "frustration_alert_trigger" in summary
