"""VoCall Evaluation Mode and Service Verification Helper.

Centralizes EVAL_MODE switch (live vs mock), missing credential/service validation,
service call tracking, and MOCK DATA stamping across CSVs, tables, and figures.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


def get_eval_mode(cli_mock: Optional[bool] = None) -> str:
    """Resolves evaluation mode: 'mock' if --mock flag or EVAL_MODE=mock, else 'live'."""
    if cli_mock is True:
        return "mock"
    env_val = os.environ.get("EVAL_MODE", "").lower().strip()
    if env_val == "mock":
        return "mock"
    return "live"


def is_mock(cli_mock: Optional[bool] = None) -> bool:
    """Returns True if the active mode is mock."""
    return get_eval_mode(cli_mock) == "mock"


def require_live_services(
    service_checks: Dict[str, bool],
    experiment_name: str,
    cli_mock: Optional[bool] = None,
) -> None:
    """Verifies that all required keys/services are present when running in live mode.

    If in live mode and any required check fails, prints a clear error message
    listing every missing item to stderr and exits non-zero.
    """
    mode = get_eval_mode(cli_mock)
    if mode != "live":
        return

    missing = [name for name, present in service_checks.items() if not present]
    if missing:
        msg_lines = [
            f"ERROR: [{experiment_name}] Live mode requires the following keys/services, which are missing:",
        ]
        for item in missing:
            msg_lines.append(f"  - {item}")
        msg_lines.append(
            "Configure the missing credentials/services or run in mock mode via --mock or EVAL_MODE=mock."
        )
        full_msg = "\n".join(msg_lines)
        sys.stderr.write(full_msg + "\n")
        sys.exit(1)


class ServiceTracker:
    """Thread-safe-compatible call counter for external services used in evaluation runs."""

    def __init__(self, initial: Optional[Dict[str, int]] = None):
        self._counts: Dict[str, int] = dict(initial or {})

    def record(self, service: str, count: int = 1) -> None:
        """Increments call count for named service."""
        svc = service.lower().strip()
        self._counts[svc] = self._counts.get(svc, 0) + count

    def get_counts(self) -> Dict[str, int]:
        """Returns snapshot of current call counts."""
        return dict(self._counts)


def stamp_csv_mock_data(csv_path: Union[str, Path], mode: str = "mock") -> None:
    """Injects a 'MOCK DATA' column into the specified CSV if mode is mock."""
    if mode != "mock":
        return

    target = Path(csv_path)
    if not target.exists():
        return

    with open(target, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    if not reader:
        return

    headers = reader[0]
    if "MOCK DATA" in headers:
        return

    new_headers = headers + ["MOCK DATA"]
    new_rows = [row + ["MOCK DATA"] for row in reader[1:]]

    with open(target, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(new_headers)
        writer.writerows(new_rows)


def stamp_table_caption(caption: str, mode: str = "mock") -> str:
    """Stamps [MOCK DATA] onto table caption if mode is mock."""
    if mode != "mock":
        return caption
    if "MOCK DATA" in caption:
        return caption
    return f"{caption} [MOCK DATA]"
