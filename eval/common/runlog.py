"""VoCall Run Logger.

Creates reproducibility run directories under results/<experiment>/<timestamp>/,
capturing git commit SHA, python and package versions, model names, seed, and
active configuration in config.json.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional, Union
import yaml


def _get_git_commit_sha() -> str:
    """Retrieves current git commit hash, falling back to 'unknown'."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def _get_package_versions() -> Dict[str, str]:
    """Captures installed versions for key dependencies."""
    packages = [
        "fastapi",
        "pydantic",
        "pydantic_settings",
        "numpy",
        "scipy",
        "scikit-learn",
        "httpx",
        "pyyaml",
        "pytest",
    ]
    versions: Dict[str, str] = {}
    for pkg in packages:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except Exception:
            versions[pkg] = "not-installed"
    return versions


def _load_config(config_input: Optional[Union[Dict[str, Any], str, Path]] = None) -> Dict[str, Any]:
    """Loads YAML or dictionary configuration."""
    if isinstance(config_input, dict):
        return config_input

    target_path = Path(config_input) if config_input else Path("eval/config.yaml")
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            return loaded if isinstance(loaded, dict) else {}
    return {}


from eval.common.mode import ServiceTracker, get_eval_mode, stamp_csv_mock_data


class RunContext:
    """Manages files and metrics for a single experiment run."""

    def __init__(
        self,
        experiment: str,
        run_dir: Path,
        timestamp: str,
        config: Dict[str, Any],
        seed: int,
        git_sha: str,
        mode: str = "live",
        services_tracker: Optional[ServiceTracker] = None,
    ):
        self.experiment = experiment
        self.run_dir = run_dir
        self.timestamp = timestamp
        self.config = config
        self.seed = seed
        self.git_sha = git_sha
        self.mode = mode
        self.services_tracker = services_tracker or ServiceTracker()

    def record_service(self, service: str, count: int = 1) -> None:
        """Records external service usage count."""
        self.services_tracker.record(service, count)

    def record_service_call(self, service: str, count: int = 1) -> None:
        """Alias for record_service."""
        self.services_tracker.record(service, count)

    def get_services_used(self) -> Dict[str, int]:
        """Returns dict of external services and call counts."""
        return self.services_tracker.get_counts()

    def stamp_csv(self, file_name_or_path: Union[str, Path]) -> Path:
        """Stamps MOCK DATA column if this is a mock run."""
        resolved = (
            file_name_or_path
            if Path(file_name_or_path).is_absolute()
            else self.run_dir / file_name_or_path
        )
        if self.mode == "mock":
            stamp_csv_mock_data(resolved, mode="mock")
        return resolved

    def path(self, relative_path: Union[str, Path]) -> Path:
        """Resolves a path relative to the run output directory."""
        return self.run_dir / relative_path

    def append_jsonl(self, file_name_or_path: Union[str, Path], record: Dict[str, Any]) -> Path:
        """Appends a single JSON record to a file within this run."""
        resolved = (
            file_name_or_path
            if Path(file_name_or_path).is_absolute()
            else self.run_dir / file_name_or_path
        )
        append_jsonl(resolved, record)
        return resolved

    def write_metrics(
        self,
        file_name_or_path: Union[str, Path],
        metrics: Dict[str, Any],
    ) -> Path:
        """Writes metrics dictionary as formatted JSON with mode and services_used."""
        resolved = (
            file_name_or_path
            if Path(file_name_or_path).is_absolute()
            else self.run_dir / file_name_or_path
        )
        metrics["mode"] = self.mode
        metrics["services_used"] = self.get_services_used()

        # Also update config.json with current services_used snapshot
        config_path = self.run_dir / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as cf:
                    cfg_data = json.load(cf)
                cfg_data["mode"] = self.mode
                cfg_data["services_used"] = self.get_services_used()
                with open(config_path, "w", encoding="utf-8") as cf:
                    json.dump(cfg_data, cf, indent=2, default=str)
            except Exception:
                pass

        write_metrics(resolved, metrics)
        return resolved


def append_jsonl(path: Union[str, Path], record: Dict[str, Any]) -> None:
    """Appends a dictionary as a JSON line to the target path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def write_metrics(path: Union[str, Path], metrics: Dict[str, Any]) -> None:
    """Writes a dictionary as indented JSON to the target path, preserving mode & services_used."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if "mode" not in metrics:
        metrics["mode"] = get_eval_mode()
    if "services_used" not in metrics:
        metrics["services_used"] = {}
    with open(target, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)


def start_run(
    experiment: str,
    config: Optional[Union[Dict[str, Any], str, Path]] = None,
    seed: Optional[int] = None,
    base_dir: Optional[Union[str, Path]] = None,
    mode: Optional[str] = None,
) -> RunContext:
    """
    Initializes a new experiment run directory.

    Creates results/<experiment>/<timestamp>/ (or MOCK_<timestamp>/ in mock mode)
    and writes config.json containing full configuration, mode, services_used,
    git commit SHA, python and package versions, model identifiers, and seed.
    """
    loaded_config = _load_config(config)

    # Determine seed
    if seed is None:
        configured_seeds = loaded_config.get("seeds")
        if isinstance(configured_seeds, list) and len(configured_seeds) > 0:
            seed = int(configured_seeds[0])
        elif isinstance(loaded_config.get("seed"), (int, float)):
            seed = int(loaded_config["seed"])
        else:
            seed = 0

    resolved_mode = mode or get_eval_mode()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    folder_name = f"MOCK_{timestamp}" if resolved_mode == "mock" else timestamp

    root_results = Path(base_dir) if base_dir else Path(loaded_config.get("paths", {}).get("results_dir", "results"))
    run_dir = root_results / experiment / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)

    git_sha = _get_git_commit_sha()
    package_versions = _get_package_versions()
    model_names = loaded_config.get("models", {})
    services_tracker = ServiceTracker()

    try:
        from app.services.voice_pipeline import get_active_pipeline_path
        pipeline_path = get_active_pipeline_path()
    except Exception:
        pipeline_path = "custom"

    try:
        from app.core.config import settings_snapshot
        snapshot = settings_snapshot()
    except Exception:
        snapshot = {}

    manifest: Dict[str, Any] = {
        "experiment": experiment,
        "timestamp": timestamp,
        "mode": resolved_mode,
        "pipeline_path": pipeline_path,
        "services_used": services_tracker.get_counts(),
        "seed": seed,
        "git_commit": git_sha,
        "python_version": sys.version,
        "package_versions": package_versions,
        "model_names": model_names,
        "settings_snapshot": snapshot,
        "config": loaded_config,
    }

    config_json_path = run_dir / "config.json"
    with open(config_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    return RunContext(
        experiment=experiment,
        run_dir=run_dir,
        timestamp=timestamp,
        config=loaded_config,
        seed=seed,
        git_sha=git_sha,
        mode=resolved_mode,
        services_tracker=services_tracker,
    )
