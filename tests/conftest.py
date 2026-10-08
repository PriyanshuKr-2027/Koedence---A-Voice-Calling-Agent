import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Allow dev authentication fallback during tests unless explicitly disabled
os.environ.setdefault("ALLOW_DEV_AUTH", "true")

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── 1. Create dummy modules ONLY for uninstalled optional packages ─────────

import importlib.abc
import importlib.machinery

class _MockLoader(importlib.abc.Loader):
    def __init__(self, name):
        self.name = name

    def create_module(self, spec):
        mod = MagicMock()
        mod.__name__ = self.name
        mod.__file__ = f"<mock_{self.name}>"
        mod.__path__ = []
        mod.__loader__ = self
        mod.__spec__ = spec
        return mod

    def exec_module(self, module):
        pass

class _MockFinder(importlib.abc.MetaPathFinder):
    def __init__(self, prefixes):
        self.prefixes = prefixes

    def find_spec(self, fullname, path, target=None):
        for prefix in self.prefixes:
            if fullname == prefix or fullname.startswith(prefix + "."):
                return importlib.machinery.ModuleSpec(fullname, _MockLoader(fullname), is_package=True)
        return None

def mock_missing_modules():
    """Mocks only packages that are actually missing/not installed."""
    missing_roots = [
        "livekit",
        "twilio",
        "supabase",
        "postgrest",
        "falkordb",
        "redis",
        "asyncpg",
        "upstash_redis",
        "matplotlib",
        "indic_transliteration",
        "soundfile",
        "jiwer",
        "sentence_transformers",
    ]
    actually_missing = []
    for root_pkg in missing_roots:
        try:
            spec = importlib.util.find_spec(root_pkg)
        except Exception:
            spec = None
        if spec is None:
            actually_missing.append(root_pkg)
            mod = MagicMock()
            mod.__name__ = root_pkg
            mod.__file__ = f"<mock_{root_pkg}>"
            mod.__path__ = []
            mod.__spec__ = importlib.machinery.ModuleSpec(root_pkg, _MockLoader(root_pkg), is_package=True)
            sys.modules[root_pkg] = mod

    if actually_missing:
        sys.meta_path.insert(0, _MockFinder(actually_missing))

mock_missing_modules()


def pytest_addoption(parser):
    """Adds --run-live CLI flag (default off)."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live integration tests marked with @pytest.mark.live against real services",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: mark test as requiring live services/models")


def pytest_collection_modifyitems(config, items):
    """Skips @pytest.mark.live tests unless --run-live flag is passed."""
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="Pass --run-live to run live tests against real services")
        for item in items:
            if "live" in item.keywords or item.get_closest_marker("live") is not None:
                item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def patch_external_services(request: pytest.FixtureRequest):
    """
    Patch external service imports before unit tests run.
    Skips patching for tests marked @pytest.mark.live so they can use real services.
    """
    if request.node.get_closest_marker("live"):
        yield
        return

    with patch("app.services.supabase_client.supabase", None), \
         patch("app.services.supabase_client.get_supabase_client", return_value=None):
        yield


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Prints separate summary counts for live tests."""
    passed_live = 0
    failed_live = 0
    skipped_live = 0

    for rep in terminalreporter.stats.get("passed", []):
        if getattr(rep, "keywords", None) and "live" in rep.keywords:
            passed_live += 1
    for rep in terminalreporter.stats.get("failed", []):
        if getattr(rep, "keywords", None) and "live" in rep.keywords:
            failed_live += 1
    for rep in terminalreporter.stats.get("skipped", []):
        if getattr(rep, "keywords", None) and "live" in rep.keywords:
            skipped_live += 1

    total_live = passed_live + failed_live + skipped_live
    if total_live > 0 or config.getoption("--run-live"):
        terminalreporter.write_sep(
            "-",
            f"Live tests: {passed_live} passed, {failed_live} failed, {skipped_live} skipped (total {total_live})"
        )
