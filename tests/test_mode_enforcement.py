"""Mode enforcement and mock stamp verification test suite.

Verifies:
  1. Live mode with missing keys or services exits non-zero with diagnostic message.
  2. Mock runs write to MOCK_ prefixed folders and stamp "MOCK DATA" across CSVs,
     tables, and figures.
  3. claims_check prints "NO LIVE DATA" when evaluating mock-only records without --allow-mock.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest

from eval.common.mode import (
    get_eval_mode,
    is_mock,
    require_live_services,
    stamp_csv_mock_data,
    stamp_table_caption,
    ServiceTracker,
)
from eval.common.runlog import start_run
from eval.report.claims_check import check_claims
from eval.report.make_tables import compile_table_v, compile_table_vi, is_mock_run_path
from eval.report.make_figures import is_mock_run_path as is_mock_fig_path, apply_mock_watermark
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "results"
EVAL_ROOT = REPO_ROOT / "eval"


# ---------------------------------------------------------------------------
# Requirement 10.1: Live mode with missing keys exits non-zero
# ---------------------------------------------------------------------------

def test_get_eval_mode_defaults_to_live():
    """Verify default evaluation mode is live unless explicitly overridden."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_eval_mode() == "live"
        assert not is_mock()

    with patch.dict(os.environ, {"EVAL_MODE": "mock"}):
        assert get_eval_mode() == "mock"
        assert is_mock()

    with patch.dict(os.environ, {"EVAL_MODE": "live"}):
        assert get_eval_mode(cli_mock=True) == "mock"
        assert get_eval_mode(cli_mock=False) == "live"


def test_require_live_services_exits_nonzero_when_services_missing(capsys):
    """Verify require_live_services aborts execution with code 1 and lists missing items."""
    missing_checks = {
        "GROQ_API_KEY": False,
        "CARTESIA_API_KEY": False,
        "EXISTING_SERVICE": True,
    }

    with pytest.raises(SystemExit) as excinfo:
        require_live_services(missing_checks, experiment_name="test_experiment", cli_mock=False)

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: [test_experiment]" in captured.err
    assert "GROQ_API_KEY" in captured.err
    assert "CARTESIA_API_KEY" in captured.err
    assert "EXISTING_SERVICE" not in captured.err


def test_require_live_services_passes_in_mock_mode():
    """Verify missing keys are allowed when running in mock mode."""
    missing_checks = {"GROQ_API_KEY": False}
    # Should not raise
    require_live_services(missing_checks, experiment_name="test_experiment", cli_mock=True)


def test_cli_live_mode_exits_nonzero_without_keys():
    """Verify CLI evaluation scripts exit non-zero in live mode without required API keys."""
    script = REPO_ROOT / "eval" / "speech" / "run_wer.py"
    clean_env = dict(os.environ)
    clean_env["EVAL_MODE"] = "live"
    clean_env["GROQ_API_KEY"] = ""
    clean_env["SARVAM_API_KEY"] = ""

    res = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert res.returncode != 0
    assert "Live mode requires the following keys/services" in res.stderr


# ---------------------------------------------------------------------------
# Requirement 10.2: Mock outputs carry MOCK stamp and write to MOCK_ dirs
# ---------------------------------------------------------------------------

def test_mock_run_folder_prefix_and_metadata(tmp_path: Path):
    """Verify mock run directory starts with MOCK_ and records mode + services_used."""
    run = start_run("test_exp", base_dir=tmp_path, mode="mock")
    assert run.run_dir.name.startswith("MOCK_")

    run.record_service_call("mock_service", count=3)
    run.write_metrics("metrics.json", {"accuracy": 0.95})

    metrics_path = run.path("metrics.json")
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["mode"] == "mock"
    assert metrics["services_used"] == {"mock_service": 3}

    config_path = run.path("config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["mode"] == "mock"


def test_stamp_csv_mock_data(tmp_path: Path):
    """Verify CSV files generated during mock runs carry 'MOCK DATA' column."""
    test_csv = tmp_path / "results.csv"
    with open(test_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["clip_id", "wer", "latency"])
        writer.writerow(["clip_1", "0.05", "120.0"])

    stamp_csv_mock_data(test_csv, mode="mock")

    with open(test_csv, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert reader[0] == ["clip_id", "wer", "latency", "MOCK DATA"]
    assert reader[1] == ["clip_1", "0.05", "120.0", "MOCK DATA"]


def test_stamp_table_caption():
    """Verify table captions are stamped with [MOCK DATA]."""
    caption = "TABLE V: Memory-Tier Ablation"
    assert stamp_table_caption(caption, mode="mock") == "TABLE V: Memory-Tier Ablation [MOCK DATA]"
    assert stamp_table_caption(caption, mode="live") == "TABLE V: Memory-Tier Ablation"


def test_figure_mock_watermark():
    """Verify watermark application adds text element to figure."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    apply_mock_watermark(fig)

    texts = [child.get_text() for child in fig.get_children() if isinstance(child, plt.Text)]
    assert "MOCK DATA" in texts
    plt.close(fig)


def test_is_mock_run_path_detection(tmp_path: Path):
    """Verify accurate detection of mock run paths across files and folders."""
    mock_folder = tmp_path / "MOCK_20261007_120000"
    mock_folder.mkdir()
    sample_file = mock_folder / "metrics.json"
    sample_file.write_text('{"mode": "mock"}', encoding="utf-8")

    assert is_mock_run_path(sample_file)
    assert is_mock_fig_path(sample_file)

    live_folder = tmp_path / "20261007_120000"
    live_folder.mkdir()
    live_file = live_folder / "metrics.json"
    live_file.write_text('{"mode": "live"}', encoding="utf-8")

    assert not is_mock_run_path(live_file)
    assert not is_mock_fig_path(live_file)


# ---------------------------------------------------------------------------
# Requirement 10.3: claims_check on mock-only data prints NO LIVE DATA
# ---------------------------------------------------------------------------

def test_claims_check_on_mock_only_data_verdict():
    """Verify claims check outputs NO LIVE DATA when only mock data exists and --allow-mock is false."""
    audit = check_claims(RESULTS_ROOT, EVAL_ROOT, allow_mock=False)
    for claim_id, record in audit.items():
        assert record["verdict"] == "NO LIVE DATA"
        assert "No live" in record["evidence"].get("status", "")


def test_claims_check_cli_mock_only_stdout():
    """Verify claims_check CLI prints 'NO LIVE DATA' to standard output."""
    script = REPO_ROOT / "eval" / "report" / "claims_check.py"
    res = subprocess.run(
        [sys.executable, str(script), "--results-dir", str(RESULTS_ROOT), "--eval-dir", str(EVAL_ROOT)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Verdict:        [NO LIVE DATA]" in res.stdout
    assert "NO LIVE DATA" in res.stdout
