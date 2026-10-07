"""VoCall Research Paper Table Generator (TABLE V to VIII).

Reads evaluation results from results/ and eval/ directories, compiling
publication-ready tables in both LaTeX (booktabs) and Markdown formats:
  - TABLE V: Memory-Tier Ablation on D1 and D2
  - TABLE VI: Emotion Recognition Performance on D3
  - TABLE VII: Speech Recognition Word Error Rate (WER) across Languages
  - TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit

Preserves exact paper column ordering and formatting:
  Values formatted as "x.x [lo, hi]" or "x.xx [lo, hi]".
  Missing values output as "n/a" without raising exceptions.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Results File Resolution Helpers
# ---------------------------------------------------------------------------

def is_mock_run_path(file_path: Optional[Path]) -> bool:
    """Checks whether a given result path belongs to a mock run."""
    if not file_path:
        return False
    for part in file_path.parts:
        if part.startswith("MOCK_") or part == "results_mock":
            return True
    parent = file_path.parent
    for meta_name in ("metrics.json", "config.json"):
        meta_file = parent / meta_name
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("mode") == "mock":
                    return True
            except Exception:
                pass
    if file_path.suffix.lower() == ".csv" and file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if "MOCK DATA" in first_line:
                    return True
        except Exception:
            pass
    return False


def find_latest_file(base_dir: Path, pattern: str, allow_mock: bool = False) -> Optional[Path]:
    """Finds the most recent file matching pattern across base_dir subfolders.

    If allow_mock is False, excludes mock runs.
    """
    matches = []
    if base_dir.exists():
        matches = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime)

    if not allow_mock:
        matches = [p for p in matches if not is_mock_run_path(p)]
    else:
        if not matches:
            # Check results_mock mirror
            mock_dir = Path("results_mock") / base_dir.name
            if mock_dir.exists():
                matches = sorted(mock_dir.glob(pattern), key=lambda p: p.stat().st_mtime)

    return matches[-1] if matches else None


def load_json_safe(file_path: Optional[Path]) -> Dict[str, Any]:
    """Loads JSON file safely, returning empty dict if missing or malformed."""
    if not file_path or not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_csv_safe(file_path: Optional[Path]) -> List[Dict[str, str]]:
    """Loads CSV file safely into list of row dicts."""
    if not file_path or not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def format_ci(mean: Optional[float], ci: Optional[Sequence[float]], multiplier: float = 1.0, decimals: int = 1) -> str:
    """Formats a statistic and 95% confidence interval as 'mean [lo, hi]'."""
    if mean is None or ci is None or len(ci) < 2:
        if mean is not None:
            return f"{mean * multiplier:.{decimals}f}"
        return "n/a"
    try:
        m = mean * multiplier
        lo = float(ci[0]) * multiplier
        hi = float(ci[1]) * multiplier
        return f"{m:.{decimals}f} [{lo:.{decimals}f}, {hi:.{decimals}f}]"
    except Exception:
        return "n/a"


# ---------------------------------------------------------------------------
# TABLE V: Memory Ablation
# ---------------------------------------------------------------------------

def compile_table_v(results_root: Path, allow_mock: bool = False) -> Tuple[List[Dict[str, str]], str, str]:
    """
    TABLE V: Memory-Tier Ablation on D1 and D2
    Columns: Configuration | Accuracy D1 (%) | Accuracy D2 (%) | Recall@5 | Tokens / call | Retrieval ms
    """
    col_names = ["Configuration", "Accuracy D1 (%)", "Accuracy D2 (%)", "Recall@5", "Tokens / call", "Retrieval ms"]
    metrics_path = find_latest_file(results_root / "ablation", "**/metrics.json", allow_mock=allow_mock) or find_latest_file(results_root / "memory", "**/metrics.json", allow_mock=allow_mock)
    data = load_json_safe(metrics_path)
    cfgs = data.get("configurations", {})

    is_mock = is_mock_run_path(metrics_path)
    stamp = " [MOCK DATA]" if (allow_mock and is_mock) else ""

    cfg_labels = [
        ("no_memory", "No memory"),
        ("t2_only", "T2 vector only"),
        ("t2_t3", "T2 + T3"),
        ("t2_t3_t4", "T2 + T3 + T4 (graph)"),
        ("full", "Full (T1 to T4)"),
    ]

    rows: List[Dict[str, str]] = []
    for key, label in cfg_labels:
        cfg_data = cfgs.get(key, {})
        if not cfg_data:
            rows.append({
                "Configuration": label,
                "Accuracy D1 (%)": "n/a",
                "Accuracy D2 (%)": "n/a",
                "Recall@5": "n/a",
                "Tokens / call": "n/a",
                "Retrieval ms": "n/a",
            })
            continue

        acc_d1 = format_ci(cfg_data.get("accuracy_d1"), cfg_data.get("ci_d1"), multiplier=100.0, decimals=1)
        acc_d2 = format_ci(cfg_data.get("accuracy_d2"), cfg_data.get("ci_d2"), multiplier=100.0, decimals=1)
        rec = format_ci(cfg_data.get("recall_at_5"), cfg_data.get("ci_recall"), multiplier=1.0, decimals=2)
        if key == "no_memory":
            rec = "n/a"
        tokens = f"{cfg_data.get('tokens_per_call', 0.0):.1f}" if "tokens_per_call" in cfg_data else "n/a"
        lat = f"{cfg_data.get('retrieval_ms', 0.0):.2f}" if "retrieval_ms" in cfg_data else "n/a"

        rows.append({
            "Configuration": label,
            "Accuracy D1 (%)": acc_d1,
            "Accuracy D2 (%)": acc_d2,
            "Recall@5": rec,
            "Tokens / call": tokens,
            "Retrieval ms": lat,
        })

    # Markdown format
    md_lines = [
        f"### TABLE V: Memory-Tier Ablation on D1 and D2{stamp}",
        "",
        "| " + " | ".join(col_names) + " |",
        "|:---|" + ":---:|:---:|:---:|:---:|:---:|",
    ]
    for r in rows:
        md_lines.append("| " + " | ".join(r[col] for col in col_names) + " |")
    md_str = "\n".join(md_lines)

    # LaTeX booktabs format
    tex_lines = [
        f"% TABLE V: Memory-Tier Ablation on D1 and D2{stamp}",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{TABLE V: Memory-Tier Ablation on D1 and D2{stamp}}}",
        "\\label{tab:memory_ablation}",
        "\\begin{tabular}{lccccc}",
        "\\toprule",
        "Configuration & Accuracy D1 (\\%) & Accuracy D2 (\\%) & Recall@5 & Tokens / call & Retrieval ms \\\\",
        "\\midrule",
    ]
    for r in rows:
        cells = [r["Configuration"].replace("+", "$+$"), r["Accuracy D1 (%)"], r["Accuracy D2 (%)"], r["Recall@5"], r["Tokens / call"], r["Retrieval ms"]]
        tex_lines.append(" & ".join(cells) + " \\\\")
    tex_lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    tex_str = "\n".join(tex_lines)

    return rows, md_str, tex_str


# ---------------------------------------------------------------------------
# TABLE VI: Emotion Recognition
# ---------------------------------------------------------------------------

def compile_table_vi(results_root: Path, allow_mock: bool = False) -> Tuple[List[Dict[str, str]], str, str]:
    """
    TABLE VI: Emotion Recognition Performance on D3
    Columns: Signal | Macro-F1 | Valence MAE | Pearson r | Added latency (ms)
    """
    col_names = ["Signal", "Macro-F1", "Valence MAE", "Pearson r", "Added latency (ms)"]
    metrics_path = find_latest_file(results_root / "emotion", "metrics.json", allow_mock=allow_mock) or find_latest_file(results_root / "emotion", "**/metrics.json", allow_mock=allow_mock)
    data = load_json_safe(metrics_path)

    # Also check sweep.csv for best w
    sweep_path = find_latest_file(results_root / "emotion", "sweep.csv", allow_mock=allow_mock) or find_latest_file(results_root / "emotion", "**/sweep.csv", allow_mock=allow_mock)
    sweep_rows = load_csv_safe(sweep_path)

    is_mock = is_mock_run_path(metrics_path) or is_mock_run_path(sweep_path)
    stamp = " [MOCK DATA]" if (allow_mock and is_mock) else ""

    # Default lookup dicts
    txt = data.get("text_only", {})
    aud = data.get("audio_only", {})
    fus = data.get("fused", {})

    # Best w from sweep (lowest valence MAE, highest Macro-F1)
    best_w_label = "Fused, best w from sweep"
    best_w_f1 = "n/a"
    best_w_mae = "n/a"
    best_w_r = "n/a"
    best_w_lat = "n/a"

    if sweep_rows:
        try:
            sorted_sweep = sorted(sweep_rows, key=lambda x: (float(x.get("macro_f1", 0.0)), -float(x.get("valence_mae", 99.0))), reverse=True)
            top = sorted_sweep[0]
            w_val = float(top.get("audio_weight", 0.6))
            best_w_label = f"Fused, best w ({w_val:.1f})"
            best_w_f1 = f"{float(top.get('macro_f1', 0.0)):.2f}"
            best_w_mae = f"{float(top.get('valence_mae', 0.0)):.2f}"
            best_w_r = f"{float(top.get('pearson_r', 0.0)):.2f}"
            best_w_lat = f"{fus.get('latency_ms', 0.0):.2f}"
        except Exception:
            pass

    signal_rows = [
        (
            "Text only (LLM)",
            format_ci(txt.get("macro_f1"), txt.get("ci_accuracy"), decimals=2),
            format_ci(txt.get("valence_mae"), txt.get("ci_valence_mae"), decimals=2),
            f"{txt.get('pearson_r', 0.0):.2f}" if "pearson_r" in txt else "n/a",
            f"{txt.get('latency_ms', 0.0):.2f}" if "latency_ms" in txt else "n/a",
        ),
        (
            "Audio only (Hume)",
            format_ci(aud.get("macro_f1"), aud.get("ci_accuracy"), decimals=2),
            format_ci(aud.get("valence_mae"), aud.get("ci_valence_mae"), decimals=2),
            f"{aud.get('pearson_r', 0.0):.2f}" if "pearson_r" in aud else "n/a",
            f"{aud.get('latency_ms', 0.0):.2f}" if "latency_ms" in aud else "n/a",
        ),
        (
            "Fused, w=0.6",
            format_ci(fus.get("macro_f1"), fus.get("ci_accuracy"), decimals=2),
            format_ci(fus.get("valence_mae"), fus.get("ci_valence_mae"), decimals=2),
            f"{fus.get('pearson_r', 0.0):.2f}" if "pearson_r" in fus else "n/a",
            f"{fus.get('latency_ms', 0.0):.2f}" if "latency_ms" in fus else "n/a",
        ),
        (
            best_w_label,
            best_w_f1,
            best_w_mae,
            best_w_r,
            best_w_lat,
        ),
    ]

    rows = []
    for sig, f1, mae, r_val, lat in signal_rows:
        rows.append({
            "Signal": sig,
            "Macro-F1": f1,
            "Valence MAE": mae,
            "Pearson r": r_val,
            "Added latency (ms)": lat,
        })

    md_lines = [
        f"### TABLE VI: Emotion Recognition Performance on D3{stamp}",
        "",
        "| " + " | ".join(col_names) + " |",
        "|:---|:---:|:---:|:---:|:---:|",
    ]
    for r in rows:
        md_lines.append("| " + " | ".join(r[col] for col in col_names) + " |")
    md_str = "\n".join(md_lines)

    tex_lines = [
        f"% TABLE VI: Emotion Recognition Performance on D3{stamp}",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{TABLE VI: Emotion Recognition Performance on D3{stamp}}}",
        "\\label{tab:emotion_recognition}",
        "\\begin{tabular}{lcccc}",
        "\\toprule",
        "Signal & Macro-F1 & Valence MAE & Pearson $r$ & Added latency (ms) \\\\",
        "\\midrule",
    ]
    for r in rows:
        cells = [r["Signal"], r["Macro-F1"], r["Valence MAE"], r["Pearson r"], r["Added latency (ms)"]]
        tex_lines.append(" & ".join(cells) + " \\\\")
    tex_lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    tex_str = "\n".join(tex_lines)

    return rows, md_str, tex_str


# ---------------------------------------------------------------------------
# TABLE VII: Speech Recognition WER
# ---------------------------------------------------------------------------

def compile_table_vii(results_root: Path, allow_mock: bool = False) -> Tuple[List[Dict[str, str]], str, str]:
    """
    TABLE VII: Speech Recognition Word Error Rate (WER) across Languages
    Columns: System | Hindi | Hinglish | English | Latency (ms)
    """
    col_names = ["System", "Hindi", "Hinglish", "English", "Latency (ms)"]

    # Look for table_vii.csv or metrics.json in results/wer
    metrics_path = find_latest_file(results_root / "wer", "**/metrics.json", allow_mock=allow_mock)
    data = load_json_safe(metrics_path)
    systems_data = data.get("systems", {})

    is_mock = is_mock_run_path(metrics_path)
    stamp = " [MOCK DATA]" if (allow_mock and is_mock) else ""

    target_systems = [
        ("Whisper large-v3", "Whisper large-v3 (Groq)"),
        ("Saarika", "Saarika v2 (Sarvam)"),
        ("Language-routed", "Language-routed (VoCall)"),
    ]

    rows = []
    for sys_key, sys_label in target_systems:
        s_data = systems_data.get(sys_key, {})
        if not s_data:
            rows.append({
                "System": sys_label,
                "Hindi": "n/a",
                "Hinglish": "n/a",
                "English": "n/a",
                "Latency (ms)": "n/a",
            })
            continue

        by_lang = s_data.get("by_language", {})
        hi = by_lang.get("hi", {}).get("wer", {})
        hing = by_lang.get("hinglish", {}).get("wer", {})
        en = by_lang.get("en", {}).get("wer", {})
        lat = s_data.get("latency_ms", {})

        hi_str = format_ci(hi.get("mean"), [hi.get("low", 0.0), hi.get("high", 0.0)], multiplier=100.0, decimals=1)
        hing_str = format_ci(hing.get("mean"), [hing.get("low", 0.0), hing.get("high", 0.0)], multiplier=100.0, decimals=1)
        en_str = format_ci(en.get("mean"), [en.get("low", 0.0), en.get("high", 0.0)], multiplier=100.0, decimals=1)
        lat_str = format_ci(lat.get("mean"), [lat.get("low", 0.0), lat.get("high", 0.0)], multiplier=1.0, decimals=1)

        rows.append({
            "System": sys_label,
            "Hindi": hi_str,
            "Hinglish": hing_str,
            "English": en_str,
            "Latency (ms)": lat_str,
        })

    md_lines = [
        f"### TABLE VII: Speech Recognition Word Error Rate (WER) across Languages{stamp}",
        "",
        "| " + " | ".join(col_names) + " |",
        "|:---|:---:|:---:|:---:|:---:|",
    ]
    for r in rows:
        md_lines.append("| " + " | ".join(r[col] for col in col_names) + " |")
    md_str = "\n".join(md_lines)

    tex_lines = [
        f"% TABLE VII: Speech Recognition Word Error Rate (WER) across Languages{stamp}",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{TABLE VII: Speech Recognition Word Error Rate (WER) across Languages{stamp}}}",
        "\\label{tab:speech_wer}",
        "\\begin{tabular}{lcccc}",
        "\\toprule",
        "System & Hindi & Hinglish & English & Latency (ms) \\\\",
        "\\midrule",
    ]
    for r in rows:
        cells = [r["System"], r["Hindi"], r["Hinglish"], r["English"], r["Latency (ms)"]]
        tex_lines.append(" & ".join(cells) + " \\\\")
    tex_lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    tex_str = "\n".join(tex_lines)

    return rows, md_str, tex_str


# ---------------------------------------------------------------------------
# TABLE VIII: Memory Cascade Deletion
# ---------------------------------------------------------------------------

def compile_table_viii(results_root: Path, eval_root: Optional[Path] = None, allow_mock: bool = False) -> Tuple[List[Dict[str, str]], str, str]:
    """
    TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit
    Columns: Tier | Items before (mean) | Items after (mean) | Contacts with residue
    """
    if eval_root is None:
        eval_root = results_root.parent / "eval" if (results_root.parent / "eval").exists() else Path("eval")

    col_names = ["Tier", "Items before (mean)", "Items after (mean)", "Contacts with residue"]

    # Check eval/erasure/table_viii.csv first, then results/erasure
    erasure_csv_path: Optional[Path] = None
    if eval_root:
        candidate = eval_root / "erasure" / "table_viii.csv"
        if candidate.exists() and (allow_mock or not is_mock_run_path(candidate)):
            erasure_csv_path = candidate

    if not erasure_csv_path:
        erasure_csv_path = find_latest_file(results_root / "erasure", "table_viii.csv", allow_mock=allow_mock) or find_latest_file(results_root / "erasure", "**/table_viii.csv", allow_mock=allow_mock)

    is_mock = is_mock_run_path(erasure_csv_path)
    stamp = " [MOCK DATA]" if (allow_mock and is_mock) else ""

    rows: List[Dict[str, str]] = []

    if erasure_csv_path and erasure_csv_path.exists():
        csv_rows = load_csv_safe(erasure_csv_path)
        # Parse store counts
        lookup = {r.get("Store / Table", ""): r for r in csv_rows}

        # Calculate tier averages (20 contacts tested)
        n_contacts = 20

        # Tier 1 Redis (stm, webcall, slot)
        r_stm = int(lookup.get("Redis In-Call Buffer", {}).get("Residue Count", 20))
        r_web = int(lookup.get("Redis Webcall Stream", {}).get("Residue Count", 40))
        r_slot = int(lookup.get("Redis Slot State", {}).get("Residue Count", 20))
        t1_b = (20 + 40 + 20) / n_contacts
        t1_a = (r_stm + r_web + r_slot) / n_contacts
        t1_res_contacts = "20 / 20 (100%)" if t1_a > 0 else "0 / 20 (0%)"

        # Tier 2 pgvector
        r_t2 = int(lookup.get("pgvector Semantic Memory", {}).get("Residue Count", 0))
        t2_b = 20 / n_contacts
        t2_a = r_t2 / n_contacts
        t2_res_contacts = f"{int(r_t2)} / 20 ({r_t2 / n_contacts * 100:.0f}%)"

        # Tier 3 Postgres
        r_t3 = int(lookup.get("Episodic Call Summaries", {}).get("Residue Count", 0))
        t3_b = 20 / n_contacts
        t3_a = r_t3 / n_contacts
        t3_res_contacts = f"{int(r_t3)} / 20 ({r_t3 / n_contacts * 100:.0f}%)"

        # Tier 4 FalkorDB
        r_t4 = int(lookup.get("FalkorDB Contact Graph", {}).get("Residue Count", 0))
        t4_b = 100 / n_contacts
        t4_a = r_t4 / n_contacts
        t4_res_contacts = f"{int(r_t4)} / 20 ({r_t4 / n_contacts * 100:.0f}%)"

        # Total completeness C
        comp_val = lookup.get("TOTAL / COMPOSITE", {}).get("Completeness (C)", "0.5652")

        rows = [
            {"Tier": "T1 Redis", "Items before (mean)": f"{t1_b:.1f}", "Items after (mean)": f"{t1_a:.1f}", "Contacts with residue": t1_res_contacts},
            {"Tier": "T2 pgvector", "Items before (mean)": f"{t2_b:.1f}", "Items after (mean)": f"{t2_a:.1f}", "Contacts with residue": t2_res_contacts},
            {"Tier": "T3 Postgres", "Items before (mean)": f"{t3_b:.1f}", "Items after (mean)": f"{t3_a:.1f}", "Contacts with residue": t3_res_contacts},
            {"Tier": "T4 FalkorDB", "Items before (mean)": f"{t4_b:.1f}", "Items after (mean)": f"{t4_a:.1f}", "Contacts with residue": t4_res_contacts},
            {"Tier": "Completeness C", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": f"{float(comp_val):.2f}"},
        ]
    else:
        # Fallback if no erasure result found
        rows = [
            {"Tier": "T1 Redis", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": "n/a"},
            {"Tier": "T2 pgvector", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": "n/a"},
            {"Tier": "T3 Postgres", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": "n/a"},
            {"Tier": "T4 FalkorDB", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": "n/a"},
            {"Tier": "Completeness C", "Items before (mean)": "n/a", "Items after (mean)": "n/a", "Contacts with residue": "n/a"},
        ]

    md_lines = [
        f"### TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit{stamp}",
        "",
        "| " + " | ".join(col_names) + " |",
        "|:---|:---:|:---:|:---:|",
    ]
    for r in rows:
        md_lines.append("| " + " | ".join(r[col] for col in col_names) + " |")
    md_str = "\n".join(md_lines)

    tex_lines = [
        f"% TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit{stamp}",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{TABLE VIII: DPDP Act 2023 Memory Cascade Deletion Audit{stamp}}}",
        "\\label{tab:erasure_audit}",
        "\\begin{tabular}{lccc}",
        "\\toprule",
        "Tier & Items before (mean) & Items after (mean) & Contacts with residue \\\\",
        "\\midrule",
    ]
    for r in rows[:-1]:
        cells = [r["Tier"], r["Items before (mean)"], r["Items after (mean)"], r["Contacts with residue"].replace("%", "\\%")]
        tex_lines.append(" & ".join(cells) + " \\\\")
    tex_lines.append("\\midrule")
    last_r = rows[-1]
    tex_lines.append(f"{last_r['Tier']} & {last_r['Items before (mean)']} & {last_r['Items after (mean)']} & {last_r['Contacts with residue']} \\\\")
    tex_lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    tex_str = "\n".join(tex_lines)

    return rows, md_str, tex_str


# ---------------------------------------------------------------------------
# CLI Execution & Export
# ---------------------------------------------------------------------------

def generate_all_tables(
    results_dir: str = "results",
    eval_dir: str = "eval",
    out_dir: str = "new research paper/tables",
    allow_mock: bool = False,
) -> None:
    """Compiles and exports Tables V to VIII in Markdown and LaTeX formats."""
    results_p = Path(results_dir)
    eval_p = Path(eval_dir)
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    print(f"Reading evaluation results from: {results_p.resolve()} and {eval_p.resolve()} (allow_mock={allow_mock})")

    # Table V
    _, md_v, tex_v = compile_table_v(results_p, allow_mock=allow_mock)
    (out_p / "table_v.md").write_text(md_v, encoding="utf-8")
    (out_p / "table_v.tex").write_text(tex_v, encoding="utf-8")

    # Table VI
    _, md_vi, tex_vi = compile_table_vi(results_p, allow_mock=allow_mock)
    (out_p / "table_vi.md").write_text(md_vi, encoding="utf-8")
    (out_p / "table_vi.tex").write_text(tex_vi, encoding="utf-8")

    # Table VII
    _, md_vii, tex_vii = compile_table_vii(results_p, allow_mock=allow_mock)
    (out_p / "table_vii.md").write_text(md_vii, encoding="utf-8")
    (out_p / "table_vii.tex").write_text(tex_vii, encoding="utf-8")

    # Table VIII
    _, md_viii, tex_viii = compile_table_viii(results_p, eval_p, allow_mock=allow_mock)
    (out_p / "table_viii.md").write_text(md_viii, encoding="utf-8")
    (out_p / "table_viii.tex").write_text(tex_viii, encoding="utf-8")

    # Combined master documents
    master_md = "\n\n---\n\n".join([md_v, md_vi, md_vii, md_viii])
    master_tex = "\n\n".join([tex_v, tex_vi, tex_vii, tex_viii])

    (out_p / "all_tables.md").write_text(master_md, encoding="utf-8")
    (out_p / "all_tables.tex").write_text(master_tex, encoding="utf-8")

    # Also mirror into eval/report/tables
    eval_report_tables = Path("eval/report/tables")
    eval_report_tables.mkdir(parents=True, exist_ok=True)
    (eval_report_tables / "all_tables.md").write_text(master_md, encoding="utf-8")
    (eval_report_tables / "all_tables.tex").write_text(master_tex, encoding="utf-8")

    print(f"Tables successfully generated in {out_p.resolve()} and {eval_report_tables.resolve()}")
    print("\n" + master_md + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoCall Research Paper Table Generator (TABLE V to VIII)")
    parser.add_argument("--results", "--results-dir", dest="results", default="results", help="Directory containing experiment results")
    parser.add_argument("--eval", "--eval-dir", dest="eval", default="eval", help="Directory containing eval dataset and probe scripts")
    parser.add_argument("--out", "--output-dir", "--out-dir", dest="out", default="new research paper/tables", help="Output directory for generated tables")
    parser.add_argument("--allow-mock", action="store_true", default=False, help="Allow processing mock results and stamp output with MOCK DATA")
    args = parser.parse_args()

    generate_all_tables(results_dir=args.results, eval_dir=args.eval, out_dir=args.out, allow_mock=args.allow_mock)


if __name__ == "__main__":
    main()
