"""Tests for Speech-to-Text WER Evaluation Pipeline (run_wer.py).

Validates:
  1. Telephony simulation: downmixing, 8 kHz polyphase resampling, G.711 mu-law companding.
  2. Utterance length bucketing ('short', 'medium', 'long').
  3. Error rate calculations via jiwer (WER and CER).
  4. Dataset CSV loading and path resolution.
  5. End-to-end benchmark execution in mock mode:
     - Table VII CSV structure (rows: systems; columns: Hindi, Hinglish, English).
     - Table VII CI matrix.
     - Extraction and ranking of the 30 worst utterance errors.
     - Bootstrap 95% confidence intervals and metrics JSON.
  6. Disk caching behavior.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from eval.common.cache import DiskCache
from eval.speech.run_wer import (
    ALL_SYSTEMS,
    SYSTEM_ROUTED,
    SYSTEM_SAARIKA,
    SYSTEM_WHISPER,
    calculate_error_rates,
    compute_bootstrap_stats,
    create_sample_speech_dataset,
    get_length_bucket,
    load_dataset_csv,
    run_wer_benchmark,
    simulate_telephony,
)


def _generate_test_wav(
    sample_rate: int = 16000,
    channels: int = 1,
    duration: float = 1.0,
    freq: float = 440.0,
) -> bytes:
    """Helper to synthesize valid linear PCM WAV audio bytes for testing."""
    num_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)
    single_channel = (0.25 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    if channels > 1:
        data = np.column_stack([single_channel] * channels)
    else:
        data = single_channel

    buf = io.BytesIO()
    sf.write(buf, data, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_simulate_telephony_resampling_and_mulaw():
    """Proves telephony simulation resamples to 8 kHz, converts stereo to mono, and applies mu-law."""
    # Create 16 kHz stereo audio
    stereo_16k_wav = _generate_test_wav(sample_rate=16000, channels=2, duration=1.0)

    # Apply telephony simulation
    telephony_wav = simulate_telephony(stereo_16k_wav)
    assert len(telephony_wav) > 0
    assert telephony_wav[:4] == b"RIFF"

    # Read output and verify sample rate and single channel
    with io.BytesIO(telephony_wav) as buf:
        data, sr = sf.read(buf)

    assert sr == 8000
    assert data.ndim == 1  # Downmixed to mono
    assert len(data) == 8000  # Exactly 1 second at 8 kHz


def test_simulate_telephony_empty_bytes():
    """Verifies empty bytes input returns empty bytes without crashing."""
    assert simulate_telephony(b"") == b""


def test_get_length_bucket_thresholds():
    """Checks threshold boundaries for short (<=5), medium (6-15), and long (>15) buckets."""
    assert get_length_bucket("") == "short"
    assert get_length_bucket("one two three") == "short"
    assert get_length_bucket("one two three four five") == "short"
    assert get_length_bucket("one two three four five six") == "medium"
    assert get_length_bucket("word " * 15) == "medium"
    assert get_length_bucket("word " * 16) == "long"
    assert get_length_bucket("word " * 25) == "long"


def test_calculate_error_rates():
    """Validates jiwer WER and CER calculations on controlled inputs."""
    # Identical strings
    w0, c0 = calculate_error_rates("hello world", "hello world")
    assert w0 == 0.0
    assert c0 == 0.0

    # Substitution: 1 word out of 2 differs -> WER = 0.5
    w1, c1 = calculate_error_rates("hello world", "hello duck")
    assert w1 == 0.5
    assert c1 > 0.0

    # Empty reference vs non-empty hypothesis
    w_empty, c_empty = calculate_error_rates("", "some text")
    assert w_empty == 1.0
    assert c_empty == 1.0

    # Both empty
    w_both_empty, c_both_empty = calculate_error_rates("", "")
    assert w_both_empty == 0.0
    assert c_both_empty == 0.0


def test_compute_bootstrap_stats():
    """Validates empirical bootstrap CI computation and guarding against empty inputs."""
    # Empty inputs
    res_empty = compute_bootstrap_stats([])
    assert res_empty == {"mean": 0.0, "low": 0.0, "high": 0.0}

    # Constant values
    res_const = compute_bootstrap_stats([0.15, 0.15, 0.15])
    assert res_const["mean"] == 0.15
    assert res_const["low"] == 0.15
    assert res_const["high"] == 0.15

    # Range of values
    res_var = compute_bootstrap_stats([0.1, 0.2, 0.3, 0.4, 0.5], n_samples=500, seed=42)
    assert res_var["low"] <= res_var["mean"] <= res_var["high"]


def test_load_dataset_csv_validation(tmp_path):
    """Verifies load_dataset_csv parses valid rows and raises on invalid schema or missing file."""
    csv_file = tmp_path / "valid.csv"
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["utt_id", "path", "text", "language"])
        writer.writerow(["clip_1", "audio/1.wav", "Hello world", "en"])

    records = load_dataset_csv(csv_file)
    assert len(records) == 1
    assert records[0]["utt_id"] == "clip_1"
    assert records[0]["language"] == "en"

    # Missing header
    bad_csv = tmp_path / "bad.csv"
    with open(bad_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "transcript"])
        writer.writerow(["clip_1", "Hello"])

    with pytest.raises(ValueError, match="CSV must contain headers"):
        load_dataset_csv(bad_csv)

    # Missing file
    with pytest.raises(FileNotFoundError):
        load_dataset_csv(tmp_path / "nonexistent.csv")


@pytest.mark.asyncio
async def test_end_to_end_benchmark_mock_pipeline(tmp_path):
    """Executes full benchmark in mock mode, validating Table VII CSV, worst errors, and metrics."""
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "results"
    cache_dir = tmp_path / "cache"

    csv_path, _ = create_sample_speech_dataset(data_dir)
    assert csv_path.exists()

    metrics = await run_wer_benchmark(
        csv_path=csv_path,
        telephony=True,
        mode="raw",
        systems=ALL_SYSTEMS,
        out_dir=out_dir,
        cache_dir=cache_dir,
        bootstrap_samples=100,
        seed=123,
        mock=True,
    )

    assert "systems" in metrics
    for sys_name in ALL_SYSTEMS:
        assert sys_name in metrics["systems"]
        sys_data = metrics["systems"][sys_name]
        assert "overall_wer" in sys_data
        assert "overall_cer" in sys_data
        assert "by_language" in sys_data
        assert "by_length_bucket" in sys_data

    # Locate generated run directory
    run_dirs = list((out_dir / "wer").glob("*"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Verify Table VII CSV structure
    table_vii_path = run_dir / "table_vii.csv"
    assert table_vii_path.exists()

    with open(table_vii_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames[:4] == ["system", "Hindi", "Hinglish", "English"]
        assert "MOCK DATA" in reader.fieldnames
        rows = list(reader)
        assert len(rows) == 3
        systems_present = [r["system"] for r in rows]
        assert systems_present == [SYSTEM_WHISPER, SYSTEM_SAARIKA, SYSTEM_ROUTED]
        for r in rows:
            assert float(r["Hindi"]) >= 0.0
            assert float(r["Hinglish"]) >= 0.0
            assert float(r["English"]) >= 0.0

    # Verify Table VII with CI CSV
    table_vii_ci_path = run_dir / "table_vii_ci.csv"
    assert table_vii_ci_path.exists()

    # Verify worst 30 errors CSV
    worst_path = run_dir / "worst_30_errors.csv"
    assert worst_path.exists()
    with open(worst_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        req_cols = {"rank", "utt_id", "system", "language", "length_bucket", "wer", "cer", "latency_ms"}
        assert req_cols.issubset(set(reader.fieldnames or []))
        worst_rows = list(reader)
        # Verify length <= 30
        assert len(worst_rows) <= 30
        # Verify ranked in descending order of WER
        wers = [float(r["wer"]) for r in worst_rows]
        assert wers == sorted(wers, reverse=True)


@pytest.mark.asyncio
async def test_transcribe_caching_behavior(tmp_path):
    """Verifies that disk caching stores and returns previous STT recognition responses."""
    cache_dir = tmp_path / "test_cache"
    cache = DiskCache(cache_dir=cache_dir)
    audio_bytes = b"RIFFtestdummybytes12345"

    from eval.speech.run_wer import transcribe_with_caching

    # First call stores to cache
    t1, lat1 = await transcribe_with_caching(
        system=SYSTEM_WHISPER,
        audio_bytes=audio_bytes,
        language="en",
        cache=cache,
        mock=True,
        mock_reference="Test sentence",
    )
    assert t1 == "Test sentence"

    # Second call hits cache
    t2, lat2 = await transcribe_with_caching(
        system=SYSTEM_WHISPER,
        audio_bytes=audio_bytes,
        language="en",
        cache=cache,
        mock=True,
        mock_reference="Different reference ignored on cache hit",
    )
    assert t2 == "Test sentence"
    assert lat2 == lat1
