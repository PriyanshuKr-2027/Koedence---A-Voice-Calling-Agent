"""Unit and integration tests for eval/report generation modules:
  - make_tables.py: TABLE V through TABLE VIII LaTeX and Markdown generation
  - make_figures.py: Fig 4 and Fig 5 chart generation
  - claims_check.py: Claims empirical verification audit
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Dict, Any

import pytest

from eval.report.make_tables import (
    compile_table_v,
    compile_table_vi,
    compile_table_vii,
    compile_table_viii,
    format_ci,
)
from eval.report.make_figures import (
    generate_figure_4,
    generate_figure_5,
)
from eval.report.claims_check import check_claims


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "results"
EVAL_ROOT = REPO_ROOT / "eval"


# ---------------------------------------------------------------------------
# Unit Tests: make_tables.py
# ---------------------------------------------------------------------------

def test_format_ci_valid():
    """Verify confidence interval formatting function."""
    assert format_ci(25.0, [6.25, 43.75], multiplier=1.0, decimals=1) == "25.0 [6.2, 43.8]"
    assert format_ci(0.8474, [0.68, 0.96], multiplier=1.0, decimals=2) == "0.85 [0.68, 0.96]"
    assert format_ci(None, None) == "n/a"
    assert format_ci(25.0, None) == "25.0"


def test_compile_table_v_with_real_results():
    """Verify Table V compilation from actual ablation records."""
    rows, md_text, tex_text = compile_table_v(RESULTS_ROOT)
    assert len(rows) == 5
    assert "Configuration" in rows[0]
    assert "Accuracy D1 (%)" in rows[0]
    assert "Accuracy D2 (%)" in rows[0]
    assert "\\begin{table}" in tex_text
    assert "\\toprule" in tex_text
    assert "\\bottomrule" in tex_text
    assert "| Configuration |" in md_text
    assert "Full (T1 to T4)" in md_text


def test_compile_table_vi_with_real_results():
    """Verify Table VI compilation from actual emotion metrics."""
    rows, md_text, tex_text = compile_table_vi(RESULTS_ROOT)
    assert len(rows) == 4
    signals = [r["Signal"] for r in rows]
    assert "Text only (LLM)" in signals
    assert "Audio only (Hume)" in signals
    assert "Fused, w=0.6" in signals
    assert "Macro-F1" in rows[0]
    assert "Valence MAE" in rows[0]
    assert "\\caption{TABLE VI:" in tex_text


def test_compile_table_vii_with_real_results():
    """Verify Table VII compilation from actual speech WER metrics."""
    rows, md_text, tex_text = compile_table_vii(RESULTS_ROOT)
    assert len(rows) == 3
    systems = [r["System"] for r in rows]
    assert "Whisper large-v3 (Groq)" in systems
    assert "Saarika v2 (Sarvam)" in systems
    assert "Language-routed (VoCall)" in systems
    assert "Hindi" in rows[0]
    assert "Hinglish" in rows[0]
    assert "\\caption{TABLE VII:" in tex_text


def test_compile_table_viii_with_real_results():
    """Verify Table VIII compilation from actual erasure metrics."""
    rows, md_text, tex_text = compile_table_viii(EVAL_ROOT)
    assert len(rows) == 5  # 4 tiers + Completeness row
    tier_names = [r["Tier"] for r in rows]
    assert "T1 Redis" in tier_names
    assert "T2 pgvector" in tier_names
    assert "T3 Postgres" in tier_names
    assert "T4 FalkorDB" in tier_names
    assert "Completeness C" in tier_names
    assert "\\caption{TABLE VIII:" in tex_text


def test_make_tables_missing_data_resilience(tmp_path: Path):
    """Ensure make_tables handles missing directories gracefully with 'n/a'."""
    empty_results = tmp_path / "empty_results"
    empty_results.mkdir()
    empty_eval = tmp_path / "empty_eval"
    empty_eval.mkdir()

    v_rows, v_md, v_tex = compile_table_v(empty_results)
    assert len(v_rows) == 5
    assert v_rows[0]["Accuracy D1 (%)"] == "n/a"

    vi_rows, vi_md, vi_tex = compile_table_vi(empty_results)
    assert len(vi_rows) == 4
    assert vi_rows[0]["Macro-F1"] == "n/a"

    vii_rows, vii_md, vii_tex = compile_table_vii(empty_results)
    assert len(vii_rows) == 3
    assert vii_rows[0]["Hinglish"] == "n/a"

    viii_rows, viii_md, viii_tex = compile_table_viii(empty_results, empty_eval)
    assert len(viii_rows) == 5
    assert viii_rows[0]["Contacts with residue"] == "n/a"


def test_make_tables_cli_execution(tmp_path: Path):
    """Test executing make_tables.py from command line."""
    out_dir = tmp_path / "cli_tables"
    script = REPO_ROOT / "eval" / "report" / "make_tables.py"

    cmd = [
        sys.executable,
        str(script),
        "--results-dir", str(RESULTS_ROOT),
        "--eval-dir", str(EVAL_ROOT),
        "--output-dir", str(out_dir),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, input="", timeout=30)
    assert res.returncode == 0, f"make_tables.py failed: {res.stderr}"

    assert (out_dir / "all_tables.md").exists()
    assert (out_dir / "all_tables.tex").exists()
    assert (out_dir / "table_v.tex").exists()
    assert (out_dir / "table_vi.tex").exists()
    assert (out_dir / "table_vii.tex").exists()
    assert (out_dir / "table_viii.tex").exists()


# ---------------------------------------------------------------------------
# Unit Tests: make_figures.py
# ---------------------------------------------------------------------------

def test_make_figures_execution(tmp_path: Path):
    """Test generating Fig 4 and Fig 5 figures directly."""
    out_dir = tmp_path / "test_figs"
    out_dir.mkdir()

    generate_figure_4(RESULTS_ROOT, [out_dir])
    generate_figure_5(RESULTS_ROOT, [out_dir])

    # Fig 4 artifacts
    assert (out_dir / "fig4_memory_emotion.png").exists()
    assert (out_dir / "fig4_memory_emotion.pdf").exists()
    assert (out_dir / "fig4a_memory_ablation.png").exists()
    assert (out_dir / "fig4b_emotion_modality.png").exists()

    # Fig 5 artifacts
    assert (out_dir / "fig5_latency_fusion.png").exists()
    assert (out_dir / "fig5_latency_fusion.pdf").exists()
    assert (out_dir / "fig5a_latency_breakdown.png").exists()
    assert (out_dir / "fig5b_fusion_weight_sweep.png").exists()

    # Verify non-trivial file size
    assert (out_dir / "fig4_memory_emotion.png").stat().st_size > 10000
    assert (out_dir / "fig5_latency_fusion.png").stat().st_size > 10000


def test_make_figures_cli_execution(tmp_path: Path):
    """Test executing make_figures.py from command line."""
    out_dir = tmp_path / "cli_figs"
    script = REPO_ROOT / "eval" / "report" / "make_figures.py"

    cmd = [
        sys.executable,
        str(script),
        "--results-dir", str(RESULTS_ROOT),
        "--out-dir", str(out_dir),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, input="", timeout=30)
    assert res.returncode == 0, f"make_figures.py failed: {res.stderr}"

    assert (out_dir / "fig4_memory_emotion.png").exists()
    assert (out_dir / "fig5_latency_fusion.png").exists()


# ---------------------------------------------------------------------------
# Unit Tests: claims_check.py
# ---------------------------------------------------------------------------

def test_check_claims_verdicts():
    """Verify claims check logic returns exact verdicts based on empirical data."""
    # When no live data exists, all verdicts report NO LIVE DATA
    audit_live = check_claims(RESULTS_ROOT, EVAL_ROOT, allow_mock=False)
    for claim_key in ("claim_1_fusion", "claim_2_graph", "claim_3_wer", "claim_4_latency", "claim_5_erasure"):
        assert audit_live[claim_key]["verdict"] == "NO LIVE DATA"

    # With allow_mock=True, audits against mock results and stamps (MOCK DATA)
    audit = check_claims(RESULTS_ROOT, EVAL_ROOT, allow_mock=True)

    assert "claim_1_fusion" in audit
    assert "claim_2_graph" in audit
    assert "claim_3_wer" in audit
    assert "claim_4_latency" in audit
    assert "claim_5_erasure" in audit

    # Claim 1: Fused vs unimodal -> not supported (MOCK DATA)
    assert audit["claim_1_fusion"]["verdict"] == "not supported (MOCK DATA)"
    assert audit["claim_1_fusion"]["evidence"]["diff_f1_vs_text"] == 0.0

    # Claim 2: Graph tier recurring complaint -> supported (MOCK DATA)
    assert audit["claim_2_graph"]["verdict"] == "supported (MOCK DATA)"
    assert audit["claim_2_graph"]["evidence"]["complaint_acc_gain_pct"] == 50.0

    # Claim 3: Hinglish routing WER -> supported (MOCK DATA)
    assert audit["claim_3_wer"]["verdict"] == "supported (MOCK DATA)"
    assert audit["claim_3_wer"]["evidence"]["absolute_reduction_pct"] == "3.96%"

    # Claim 4: P95 turn latency under 800 ms -> supported (MOCK DATA)
    assert audit["claim_4_latency"]["verdict"] == "supported (MOCK DATA)"
    assert audit["claim_4_latency"]["evidence"]["turns_under_800ms_compliance"] == "100.0%"
    assert audit["claim_4_latency"]["evidence"]["p95_latency_ms"] < 800.0

    # Claim 5: Erasure completeness C=1.0 -> supported (MOCK DATA)
    assert audit["claim_5_erasure"]["verdict"] == "supported (MOCK DATA)"
    assert audit["claim_5_erasure"]["evidence"]["measured_completeness_c"] == 1.0


def test_claims_check_cli_execution(tmp_path: Path):
    """Test executing claims_check.py from command line."""
    json_out = tmp_path / "claims_out.json"
    script = REPO_ROOT / "eval" / "report" / "claims_check.py"

    # Default invocation without --allow-mock produces NO LIVE DATA
    cmd = [
        sys.executable,
        str(script),
        "--results-dir", str(RESULTS_ROOT),
        "--eval-dir", str(EVAL_ROOT),
        "--json-out", str(json_out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, input="", timeout=30)
    assert res.returncode == 0, f"claims_check.py failed: {res.stderr}"

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 5
    assert data["claim_1_fusion"]["verdict"] == "NO LIVE DATA"
    assert data["claim_4_latency"]["verdict"] == "NO LIVE DATA"

    # Invocations with --allow-mock stamp MOCK DATA
    cmd_mock = cmd + ["--allow-mock"]
    res_mock = subprocess.run(cmd_mock, capture_output=True, text=True, input="", timeout=30)
    assert res_mock.returncode == 0
    with open(json_out, "r", encoding="utf-8") as f:
        mock_data = json.load(f)
    assert mock_data["claim_1_fusion"]["verdict"] == "not supported (MOCK DATA)"
    assert mock_data["claim_4_latency"]["verdict"] == "supported (MOCK DATA)"
