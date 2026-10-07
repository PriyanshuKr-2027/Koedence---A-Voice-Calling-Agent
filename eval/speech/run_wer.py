"""VoCall Speech-to-Text WER & CER Evaluation Benchmark (Table VII).

Evaluates Automatic Speech Recognition across Hindi, Hinglish, and English audio:
  1. Groq Whisper large-v3 endpoint
  2. Sarvam AI Saarika v2 endpoint
  3. Language-routed pipeline from app/services/stt.py

Features:
  - Telephony channel simulation (--telephony): resamples to 8 kHz and applies
    ITU-T G.711 mu-law encode/decode companding before sending to recognizers.
  - Persistent disk caching of audio bytes and STT responses to .eval_cache.
  - Text normalisation via eval/speech/normalize.py (raw, roman, devanagari).
  - Word Error Rate (WER) and Character Error Rate (CER) via jiwer.
  - Bootstrapped 95% confidence intervals per system, language, and utterance length.
  - Wall-clock request latency profiling.
  - Exports Table VII CSV and detailed reports for the 30 worst-case recognition errors.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ensure repository root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import jiwer
import numpy as np
import scipy.signal
import soundfile as sf
import yaml

from app.core.config import settings
from app.services.stt import (
    _transcribe_groq_whisper,
    _transcribe_sarvam_saarika,
    transcribe_audio,
)
from eval.common.cache import DiskCache
from eval.common.mode import ServiceTracker, get_eval_mode, require_live_services, stamp_csv_mock_data
from eval.common.runlog import RunContext, start_run
from eval.common.stats import BootstrapResult, bootstrap_ci
from eval.speech.normalize import normalize_text

logger = logging.getLogger(__name__)

# System identifiers
SYSTEM_WHISPER = "Whisper large-v3"
SYSTEM_SAARIKA = "Saarika"
SYSTEM_ROUTED = "Language-routed"
ALL_SYSTEMS = [SYSTEM_WHISPER, SYSTEM_SAARIKA, SYSTEM_ROUTED]

# Supported language codes
LANG_HI = "hi"
LANG_HINGLISH = "hinglish"
LANG_EN = "en"
SUPPORTED_LANGUAGES = [LANG_HI, LANG_HINGLISH, LANG_EN]


def simulate_telephony(audio_bytes: bytes) -> bytes:
    """Simulates an 8 kHz PSTN telephony channel on linear PCM audio.

    Steps:
      1. Decodes WAV audio bytes into a floating-point numpy array.
      2. Downmixes multi-channel audio to mono.
      3. Resamples to 8,000 Hz if the input sampling rate differs.
      4. Compands through ITU-T G.711 mu-law quantization (8-bit, mu=255).
      5. Expands back to 16-bit linear PCM at 8 kHz.
      6. Encodes and returns valid WAV format bytes.

    Args:
        audio_bytes: Input audio file content (WAV).

    Returns:
        bytes: 8 kHz 16-bit mono WAV audio bytes.
    """
    if not audio_bytes:
        return b""

    with io.BytesIO(audio_bytes) as in_buf:
        data, sample_rate = sf.read(in_buf, dtype="float32")

    # Downmix multi-channel to mono
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    target_sr = 8000
    if sample_rate != target_sr:
        gcd = math.gcd(int(sample_rate), target_sr)
        up = target_sr // gcd
        down = int(sample_rate) // gcd
        data = scipy.signal.resample_poly(data, up, down).astype(np.float32)

    # G.711 mu-law companding (mu = 255)
    mu = 255.0
    x_clip = np.clip(data, -1.0, 1.0)
    fx = np.sign(x_clip) * (np.log(1.0 + mu * np.abs(x_clip)) / np.log(1.0 + mu))
    quantized_8bit = np.round((fx + 1.0) / 2.0 * mu).astype(np.uint8)

    # Decompress back to linear scale [-1.0, 1.0]
    y = (quantized_8bit.astype(np.float32) / mu) * 2.0 - 1.0
    decompressed = np.sign(y) * ((1.0 + mu) ** np.abs(y) - 1.0) / mu

    out_buf = io.BytesIO()
    sf.write(out_buf, decompressed, target_sr, format="WAV", subtype="PCM_16")
    return out_buf.getvalue()


def get_length_bucket(text: str) -> str:
    """Categorizes reference transcript into utterance length buckets.

    Buckets:
      - 'short': <= 5 words
      - 'medium': 6 to 15 words
      - 'long': > 15 words
    """
    word_count = len((text or "").strip().split())
    if word_count <= 5:
        return "short"
    if word_count <= 15:
        return "medium"
    return "long"


def _mock_transcription(reference: str, system: str, language: str) -> str:
    """Generates synthetic transcription outputs for offline testing without paid API keys."""
    lang = (language or "en").lower().strip()
    words = reference.strip().split()
    if not words:
        return ""

    # Whisper tends to write Hinglish phonetically in Latin or transcribe Hindi into Devanagari
    if system == SYSTEM_WHISPER:
        if lang == "hinglish":
            # Simulate occasional English homophone confusion on Hinglish terms
            return reference.replace("kardo", "car do").replace("bot", "board").replace("dus", "10")
        if lang == "hi":
            # Whisper transcribes Hindi accurately or with minor suffix drops
            return reference
        return reference

    # Saarika is tailored for Indian languages and Hinglish code-switching
    if system == SYSTEM_SAARIKA:
        if lang in ("hi", "hinglish"):
            return reference.replace("kardo", "kar do").replace("nahin", "nahi")
        # Saarika on pure English might add occasional phonetic alterations
        return reference

    # Language routed path: matches Saarika on hi/hinglish and Whisper on en
    if lang in ("hi", "hinglish"):
        return _mock_transcription(reference, SYSTEM_SAARIKA, lang)
    return _mock_transcription(reference, SYSTEM_WHISPER, lang)


async def transcribe_with_caching(
    system: str,
    audio_bytes: bytes,
    language: str,
    cache: DiskCache,
    mock: bool = False,
    mock_reference: str = "",
    tracker: Optional[ServiceTracker] = None,
    error_sink: Optional[List[str]] = None,
) -> Tuple[str, float]:
    """Runs speech recognition through designated system with persistent disk caching.

    Returns:
        Tuple[str, float]: (transcribed_text, latency_in_ms)
    """
    lang = (language or "en").lower().strip()
    provider_map = {
        SYSTEM_WHISPER: ("groq", "whisper-large-v3"),
        SYSTEM_SAARIKA: ("sarvam", "saarika:v2"),
        SYSTEM_ROUTED: ("routed", f"routed_{lang}"),
    }
    provider, model = provider_map.get(system, ("generic", system))

    # Check cache
    cached_val = cache.get(provider, model, audio_bytes)
    if cached_val is not None:
        if isinstance(cached_val, dict):
            return cached_val.get("transcript", ""), float(cached_val.get("latency_ms", 0.0))
        return str(cached_val), 0.0

    if mock:
        t0 = time.perf_counter()
        await asyncio.sleep(0.01)
        transcript = _mock_transcription(mock_reference, system, lang)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        cache.set(provider, model, audio_bytes, {"transcript": transcript, "latency_ms": latency_ms})
        return transcript, latency_ms

    # Live recognizer invocation - never fallback to mock transcription
    t0 = time.perf_counter()
    transcript = ""
    api_keys = {
        "groq": settings.GROQ_API_KEY,
        "sarvam": settings.SARVAM_API_KEY,
    }

    try:
        if system == SYSTEM_WHISPER:
            if tracker:
                tracker.record("groq")
            transcript = await _transcribe_groq_whisper(audio_bytes, api_keys)
        elif system == SYSTEM_SAARIKA:
            if tracker:
                tracker.record("sarvam")
            transcript = await _transcribe_sarvam_saarika(audio_bytes, api_keys)
        elif system == SYSTEM_ROUTED:
            if tracker:
                if lang in ("hi", "hinglish"):
                    tracker.record("sarvam")
                else:
                    tracker.record("groq")
            transcript = await transcribe_audio(audio_bytes, lang, api_keys)
        else:
            raise ValueError(f"Unknown system: {system}")
    except Exception as exc:
        logger.error("STT error for system %s on language %s: %s", system, lang, exc)
        transcript = ""
        if error_sink is not None:
            error_sink.append(str(exc))

    latency_ms = (time.perf_counter() - t0) * 1000.0
    cache.set(provider, model, audio_bytes, {"transcript": transcript, "latency_ms": latency_ms})
    return transcript, latency_ms


def load_dataset_csv(
    csv_path: str | Path,
    audio_dir: Optional[str | Path] = None,
) -> List[Dict[str, str]]:
    """Loads utterance records from CSV file.

    Expected headers: utt_id, path, text, language
    """
    csv_p = Path(csv_path)
    if not csv_p.exists():
        raise FileNotFoundError(f"Transcript CSV not found at: {csv_p}")

    base_audio = Path(audio_dir) if audio_dir else csv_p.parent

    records: List[Dict[str, str]] = []
    with open(csv_p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        req_fields = {"utt_id", "path", "text", "language"}
        if not req_fields.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"CSV must contain headers {req_fields}, found: {reader.fieldnames}"
            )

        for row in reader:
            raw_path = row["path"].strip()
            resolved_path = Path(raw_path)
            if not resolved_path.is_absolute():
                candidate = base_audio / raw_path
                if candidate.exists():
                    resolved_path = candidate
                elif (Path.cwd() / raw_path).exists():
                    resolved_path = Path.cwd() / raw_path

            records.append({
                "utt_id": row["utt_id"].strip(),
                "path": str(resolved_path),
                "text": row["text"].strip(),
                "language": row["language"].strip().lower(),
            })

    return records


def calculate_error_rates(
    ref_norm: str,
    hyp_norm: str,
) -> Tuple[float, float]:
    """Computes Word Error Rate and Character Error Rate via jiwer."""
    if not ref_norm:
        if not hyp_norm:
            return 0.0, 0.0
        return 1.0, 1.0

    w_val = float(jiwer.wer(ref_norm, hyp_norm))
    c_val = float(jiwer.cer(ref_norm, hyp_norm))
    return w_val, c_val


def compute_bootstrap_stats(
    values: Sequence[float],
    n_samples: int = 1000,
    seed: int = 0,
) -> Dict[str, float]:
    """Wraps bootstrap_ci with empty value guarding."""
    if not values:
        return {"mean": 0.0, "low": 0.0, "high": 0.0}
    res = bootstrap_ci(values, n=n_samples, seed=seed)
    return {
        "mean": round(res.mean, 4),
        "low": round(res.low, 4),
        "high": round(res.high, 4),
    }


def create_sample_speech_dataset(
    dest_dir: str | Path = "eval/data/speech",
) -> Tuple[Path, Path]:
    """Generates a reference speech evaluation corpus and synthetic 8 kHz audio files.

    Includes representative utterances for Hindi, Hinglish, and English
    across short, medium, and long sentence buckets.
    """
    root_p = Path(dest_dir)
    audio_p = root_p / "audio"
    audio_p.mkdir(parents=True, exist_ok=True)
    csv_p = root_p / "transcripts.csv"

    sample_dialogues = [
        # Hindi (Short, Medium, Long)
        ("hi_001", "हाँ ठीक है।", "hi"),
        ("hi_002", "कल सुबह 10 बजे कॉल शेड्यूल करदो।", "hi"),
        ("hi_003", "कृपया मेरा नया खाता विवरण चेक करके मुझे तुरंत कन्फर्म कर दीजिए।", "hi"),
        ("hi_004", "मुझे अपने पुराने लोन अकाउंट का स्टेटस चेक करना है और स्टेटमेंट चाहिए।", "hi"),
        ("hi_005", "हमारे इंटरनेट कनेक्शन में बार बार रुकावट आ रही है और स्पीड बहुत कम मिल रही है।", "hi"),
        ("hi_006", "नमस्ते आपका स्वागत है।", "hi"),
        ("hi_007", "टिकट नंबर दर्ज हो गया है।", "hi"),
        ("hi_008", "क्या आप मेरी समस्या का समाधान कर सकते हैं कृपया सहायता करें?", "hi"),
        # Hinglish (Short, Medium, Long)
        ("hing_001", "Mera refund status check kardo please.", "hinglish"),
        ("hing_002", "Haan kal subah dus baje call schedule kar do.", "hinglish"),
        ("hing_003", "Wi-Fi router restart kiya par connection abhi bhi drop ho raha hai.", "hinglish"),
        ("hing_004", "Mujhe apne home loan application ke required documents upload karne hain portal par.", "hinglish"),
        ("hing_005", "Aapka voice bot kaafi fast answer de raha hai ticket do minute me raise ho gaya.", "hinglish"),
        ("hing_006", "Technician visit cancel karke Monday afternoon re-schedule kar dena.", "hinglish"),
        ("hing_007", "Agent se turant baat karwao please.", "hinglish"),
        ("hing_008", "Bill payment debited from account but invoice showing pending status update.", "hinglish"),
        # English (Short, Medium, Long)
        ("en_001", "Please cancel my subscription immediately.", "en"),
        ("en_002", "I need to change my registered billing address.", "en"),
        ("en_003", "Could you verify if fiber optic broadband coverage is accessible in Indiranagar?", "en"),
        ("en_004", "The technical engineer resolved the hardware failure quickly and my service is restored.", "en"),
        ("en_005", "I have been waiting for over thirty minutes on hold and need immediate supervisor escalation.", "en"),
        ("en_006", "Thank you very much.", "en"),
        ("en_007", "Check my monthly account statement.", "en"),
        ("en_008", "Transfer ownership of my commercial broadband line to another business account.", "en"),
    ]

    rows = []
    sr = 8000
    for idx, (utt_id, text, lang) in enumerate(sample_dialogues):
        wav_name = f"{utt_id}.wav"
        wav_file = audio_p / wav_name

        # Synthesize a distinct mono 8 kHz audio carrier for each utterance
        duration = max(1.2, len(text.split()) * 0.35)
        num_samples = int(sr * duration)
        t = np.linspace(0, duration, num_samples, endpoint=False)
        base_freq = 300.0 + (idx * 27.0) % 350.0
        rng = np.random.default_rng(idx + 42)
        noise = rng.normal(0, 0.002, num_samples)
        audio_wave = (0.2 * np.sin(2 * np.pi * base_freq * t) + noise).astype(np.float32)
        sf.write(str(wav_file), audio_wave, sr, format="WAV", subtype="PCM_16")

        rel_path = f"audio/{wav_name}"
        rows.append([utt_id, rel_path, text, lang])

    with open(csv_p, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["utt_id", "path", "text", "language"])
        writer.writerows(rows)

    return csv_p, audio_p


async def run_wer_benchmark(
    csv_path: str | Path,
    audio_dir: Optional[str | Path] = None,
    telephony: bool = False,
    mode: str = "raw",
    systems: Optional[List[str]] = None,
    out_dir: str | Path = "results",
    cache_dir: str | Path = ".eval_cache",
    bootstrap_samples: int = 1000,
    seed: int = 0,
    mock: bool = False,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Runs speech recognition evaluation across systems, language groups, and length buckets.

    Emits Table VII CSV, detailed metrics JSON, and worst-case errors.
    """
    eval_systems = systems or ALL_SYSTEMS
    cache = DiskCache(cache_dir=cache_dir)

    is_mock_run = (mock is True) or (get_eval_mode() == "mock")
    mode_str = "mock" if is_mock_run else "live"

    if mode_str == "live":
        require_live_services(
            {
                "GROQ_API_KEY": bool(settings.GROQ_API_KEY),
                "SARVAM_API_KEY": bool(settings.SARVAM_API_KEY),
            },
            experiment_name="wer",
            cli_mock=False,
        )

    dataset_records = load_dataset_csv(csv_path, audio_dir=audio_dir)
    if not dataset_records:
        raise ValueError(f"No records found in dataset CSV: {csv_path}")

    run_cfg = config or {}
    run = start_run("wer", config=run_cfg, seed=seed, base_dir=out_dir, mode=mode_str)
    tracker = run.services_tracker
    stt_errors_count: Dict[str, int] = {sys_name: 0 for sys_name in eval_systems}

    all_utterance_results: List[Dict[str, Any]] = []

    print(f"Starting Speech Benchmark ({mode_str.upper()} mode): {len(dataset_records)} utterances, systems={eval_systems}, telephony={telephony}, mode={mode}")

    for rec in dataset_records:
        utt_id = rec["utt_id"]
        audio_file = Path(rec["path"])
        ref_text = rec["text"]
        lang = rec["language"]
        length_bucket = get_length_bucket(ref_text)

        if not audio_file.exists():
            if is_mock_run:
                # Generate synthetic bytes in mock mode if file is missing
                audio_bytes = simulate_telephony(b"") if telephony else b"RIFFmock"
            else:
                raise FileNotFoundError(f"Audio file not found: {audio_file}")
        else:
            with open(audio_file, "rb") as f:
                raw_bytes = f.read()
            audio_bytes = simulate_telephony(raw_bytes) if telephony else raw_bytes

        for sys_name in eval_systems:
            error_list: List[str] = []
            hyp_text, latency_ms = await transcribe_with_caching(
                system=sys_name,
                audio_bytes=audio_bytes,
                language=lang,
                cache=cache,
                mock=is_mock_run,
                mock_reference=ref_text,
                tracker=tracker,
                error_sink=error_list,
            )
            if error_list:
                stt_errors_count[sys_name] += 1

            # Normalization per specified scoring mode
            ref_norm = normalize_text(ref_text, mode=mode)
            hyp_norm = normalize_text(hyp_text, mode=mode)

            w_val, c_val = calculate_error_rates(ref_norm, hyp_norm)

            record = {
                "utt_id": utt_id,
                "system": sys_name,
                "language": lang,
                "length_bucket": length_bucket,
                "wer": round(w_val, 4),
                "cer": round(c_val, 4),
                "latency_ms": round(latency_ms, 2),
                "error": error_list[0] if error_list else None,
                "reference_raw": ref_text,
                "hypothesis_raw": hyp_text,
                "reference_norm": ref_norm,
                "hypothesis_norm": hyp_norm,
            }
            all_utterance_results.append(record)
            run.append_jsonl("all_utterances.jsonl", record)

    # Compute aggregate metrics and bootstrap 95% CIs
    aggregated_metrics: Dict[str, Any] = {
        "mode": mode_str,
        "services_used": tracker.get_counts(),
        "total_errors": sum(stt_errors_count.values()),
        "errors_by_system": stt_errors_count,
        "telephony_simulation": telephony,
        "normalisation_mode": mode,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "total_utterances": len(dataset_records),
        "systems": {},
    }

    # Table VII data matrix: rows=systems, columns=[Hindi, Hinglish, English]
    table_vii_rows: List[Dict[str, Any]] = []

    for sys_name in eval_systems:
        sys_records = [r for r in all_utterance_results if r["system"] == sys_name]
        sys_wers = [r["wer"] for r in sys_records]
        sys_cers = [r["cer"] for r in sys_records]
        sys_lats = [r["latency_ms"] for r in sys_records]

        overall_wer_ci = compute_bootstrap_stats(sys_wers, n_samples=bootstrap_samples, seed=seed)
        overall_cer_ci = compute_bootstrap_stats(sys_cers, n_samples=bootstrap_samples, seed=seed)
        overall_lat_ci = compute_bootstrap_stats(sys_lats, n_samples=bootstrap_samples, seed=seed)

        # Per language group
        lang_breakdown: Dict[str, Any] = {}
        for l_code in SUPPORTED_LANGUAGES:
            l_recs = [r for r in sys_records if r["language"] == l_code]
            l_wers = [r["wer"] for r in l_recs]
            l_cers = [r["cer"] for r in l_recs]
            lang_breakdown[l_code] = {
                "count": len(l_recs),
                "wer": compute_bootstrap_stats(l_wers, n_samples=bootstrap_samples, seed=seed),
                "cer": compute_bootstrap_stats(l_cers, n_samples=bootstrap_samples, seed=seed),
            }

        # Per utterance-length bucket
        bucket_breakdown: Dict[str, Any] = {}
        for b_name in ("short", "medium", "long"):
            b_recs = [r for r in sys_records if r["length_bucket"] == b_name]
            b_wers = [r["wer"] for r in b_recs]
            b_cers = [r["cer"] for r in b_recs]
            bucket_breakdown[b_name] = {
                "count": len(b_recs),
                "wer": compute_bootstrap_stats(b_wers, n_samples=bootstrap_samples, seed=seed),
                "cer": compute_bootstrap_stats(b_cers, n_samples=bootstrap_samples, seed=seed),
            }

        aggregated_metrics["systems"][sys_name] = {
            "overall_wer": overall_wer_ci,
            "overall_cer": overall_cer_ci,
            "latency_ms": overall_lat_ci,
            "by_language": lang_breakdown,
            "by_length_bucket": bucket_breakdown,
        }

        # Populate Table VII row
        table_vii_rows.append({
            "system": sys_name,
            "Hindi": lang_breakdown.get(LANG_HI, {}).get("wer", {}).get("mean", 0.0),
            "Hinglish": lang_breakdown.get(LANG_HINGLISH, {}).get("wer", {}).get("mean", 0.0),
            "English": lang_breakdown.get(LANG_EN, {}).get("wer", {}).get("mean", 0.0),
            "Hindi_95CI": f"[{lang_breakdown.get(LANG_HI, {}).get('wer', {}).get('low', 0.0):.4f}, {lang_breakdown.get(LANG_HI, {}).get('wer', {}).get('high', 0.0):.4f}]",
            "Hinglish_95CI": f"[{lang_breakdown.get(LANG_HINGLISH, {}).get('wer', {}).get('low', 0.0):.4f}, {lang_breakdown.get(LANG_HINGLISH, {}).get('wer', {}).get('high', 0.0):.4f}]",
            "English_95CI": f"[{lang_breakdown.get(LANG_EN, {}).get('wer', {}).get('low', 0.0):.4f}, {lang_breakdown.get(LANG_EN, {}).get('wer', {}).get('high', 0.0):.4f}]",
        })

    # Write Table VII CSV (Primary paper table format)
    table_vii_csv = run.path("table_vii.csv")
    with open(table_vii_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "Hindi", "Hinglish", "English"])
        for row in table_vii_rows:
            writer.writerow([row["system"], row["Hindi"], row["Hinglish"], row["English"]])

    # Write Table VII with 95% Confidence Intervals
    table_vii_ci_csv = run.path("table_vii_ci.csv")
    with open(table_vii_ci_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "Hindi", "Hindi_95CI", "Hinglish", "Hinglish_95CI", "English", "English_95CI"])
        for row in table_vii_rows:
            writer.writerow([
                row["system"],
                row["Hindi"],
                row["Hindi_95CI"],
                row["Hinglish"],
                row["Hinglish_95CI"],
                row["English"],
                row["English_95CI"],
            ])

    # Extract 30 worst utterance recognition errors (sorted by WER desc, then CER desc)
    worst_records = sorted(
        all_utterance_results,
        key=lambda r: (r["wer"], r["cer"], -r["latency_ms"]),
        reverse=True,
    )[:30]

    worst_errors_csv = run.path("worst_30_errors.csv")
    with open(worst_errors_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank",
            "utt_id",
            "system",
            "language",
            "length_bucket",
            "wer",
            "cer",
            "latency_ms",
            "reference",
            "hypothesis",
        ])
        for idx, item in enumerate(worst_records, start=1):
            writer.writerow([
                idx,
                item["utt_id"],
                item["system"],
                item["language"],
                item["length_bucket"],
                item["wer"],
                item["cer"],
                item["latency_ms"],
                item["reference_raw"],
                item["hypothesis_raw"],
            ])

    # Write complete predictions CSV
    all_results_csv = run.path("all_predictions.csv")
    with open(all_results_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_utterance_results[0].keys()))
        writer.writeheader()
        writer.writerows(all_utterance_results)

    # Stamp CSVs with MOCK DATA column if in mock mode
    if is_mock_run:
        stamp_csv_mock_data(table_vii_csv, mode="mock")
        stamp_csv_mock_data(table_vii_ci_csv, mode="mock")
        stamp_csv_mock_data(worst_errors_csv, mode="mock")
        stamp_csv_mock_data(all_results_csv, mode="mock")

    # Write comprehensive metrics JSON
    run.write_metrics("metrics.json", aggregated_metrics)

    print(f"Benchmark finished successfully. Artifacts saved in: {run.run_dir}")
    print(f"  - Table VII CSV: {table_vii_csv}")
    print(f"  - Worst 30 Errors CSV: {worst_errors_csv}")
    print(f"  - Full Metrics JSON: {run.path('metrics.json')}")

    return aggregated_metrics


def parse_args() -> argparse.Namespace:
    """Configures CLI flags for run_wer.py."""
    parser = argparse.ArgumentParser(
        description="VoCall Automatic Speech Recognition Benchmark Runner"
    )
    parser.add_argument(
        "--csv",
        default="eval/data/speech/transcripts.csv",
        help="Path to CSV containing utterance IDs, paths, references, and languages",
    )
    parser.add_argument(
        "--audio-dir",
        default=None,
        help="Root folder containing audio files (defaults to CSV directory)",
    )
    parser.add_argument(
        "--telephony",
        action="store_true",
        help="Simulate 8 kHz telephony channel with ITU-T G.711 mu-law companding",
    )
    parser.add_argument(
        "--mode",
        choices=["raw", "roman", "devanagari"],
        default="raw",
        help="Text normalisation scoring mode (raw, roman, or devanagari)",
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        default=ALL_SYSTEMS,
        help="Speech recognizer systems to evaluate",
    )
    parser.add_argument(
        "--out",
        default="results",
        help="Base output directory for results",
    )
    parser.add_argument(
        "--cache-dir",
        default=".eval_cache",
        help="Filesystem directory for persistent disk caching",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=1000,
        help="Number of bootstrap resamples for 95% confidence intervals",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for statistical bootstrap reproducibility",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Execute offline mock benchmark without issuing live network requests",
    )
    parser.add_argument(
        "--generate-sample-dataset",
        action="store_true",
        help="Create initial sample speech dataset at eval/data/speech before running",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    csv_target = Path(args.csv)
    if args.generate_sample_dataset or not csv_target.exists():
        print(f"Creating reference speech dataset at eval/data/speech...")
        created_csv, _ = create_sample_speech_dataset(csv_target.parent)
        args.csv = str(created_csv)

    asyncio.run(
        run_wer_benchmark(
            csv_path=args.csv,
            audio_dir=args.audio_dir,
            telephony=args.telephony,
            mode=args.mode,
            systems=args.systems,
            out_dir=args.out,
            cache_dir=args.cache_dir,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
            mock=args.mock,
        )
    )


if __name__ == "__main__":
    main()
