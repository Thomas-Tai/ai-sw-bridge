"""Shared fixtures for the ai-sw-bridge test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Resolve relative to this file so the tests run anywhere the repo is checked
# out -- previously this was hardcoded to one developer's laptop, which
# silently "worked" locally for that developer and broke on every CI runner.
EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"

# Module-level cache for the live-SW probe. The probe does one COM
# GetObject/Dispatch round trip; cheap but not free.
_SW_PROBE: bool | None = None


def solidworks_available() -> bool:
    """Return True iff a live SOLIDWORKS session can be acquired *and* responds.

    Used by the ``solidworks_only`` auto-skip hook below. Cached after the
    first call so the probe cost is paid once per pytest session.

    Probes both ``Dispatch`` and a property read (``RevisionNumber``) because
    ``Dispatch`` can succeed (COM class registered) even when the SW service
    is unhealthy — subsequent calls then hit ``0x800706BA``
    (RPC_E_SERVER_UNAVAILABLE) as a process-fatal Windows structured
    exception rather than a catchable Python error.
    """
    global _SW_PROBE
    if _SW_PROBE is not None:
        return _SW_PROBE
    try:
        import win32com.client

        sw = win32com.client.Dispatch("SldWorks.Application")
        if sw is None:
            _SW_PROBE = False
            return False
        _ = sw.RevisionNumber
        _SW_PROBE = True
    except Exception:
        _SW_PROBE = False
    return _SW_PROBE


def pytest_collection_modifyitems(config, items):
    """Auto-skip @pytest.mark.solidworks_only tests when no live SW session.

    Also auto-skip @pytest.mark.destructive_sw unless the user explicitly
    selected them (``-m destructive_sw`` or ``-k death_recovery``).  The
    destructive test kills the SW process mid-run; the resulting SEH
    exception in the COM worker thread crashes the entire pytest process —
    it cannot be caught by ``_DEAD_HRESULTS`` or Python ``try/except``.
    """
    if not any(item.get_closest_marker("solidworks_only") for item in items):
        pass
    elif solidworks_available():
        pass
    else:
        skip_sw = pytest.mark.skip(reason="live SOLIDWORKS session not available")
        for item in items:
            if item.get_closest_marker("solidworks_only"):
                item.add_marker(skip_sw)

    explicit = (
        "destructive_sw" in (config.getoption("-m", "") or "")
        or "death_recovery" in (config.getoption("-k", "") or "")
    )
    if not explicit:
        skip_destructive = pytest.mark.skip(
            reason="destructive SW test — run in isolation: "
            "pytest -m destructive_sw tests/e2e_sw/test_e2e_death_recovery.py -v"
        )
        for item in items:
            if item.get_closest_marker("destructive_sw"):
                item.add_marker(skip_destructive)


def _load_spec(rel_path: str) -> dict:
    with (EXAMPLES_ROOT / rel_path).open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def cylinder_spec() -> dict:
    """v1 declarative spec for the minimal cylinder."""
    return _load_spec("minimal_cylinder_v2/spec.json")


@pytest.fixture
def cylinder_spec_path() -> Path:
    """Filesystem path to the cylinder spec, for callers that need to
    resolve its `locals` field relative to the spec's own directory."""
    return EXAMPLES_ROOT / "minimal_cylinder_v2" / "spec.json"


@pytest.fixture
def mmp_spec() -> dict:
    """v1 declarative spec for the S1b motor-mount plate."""
    return _load_spec("motor_mount_plate/spec.json")


@pytest.fixture
def mmp_spec_path() -> Path:
    """Filesystem path to the MMP spec, so callers can resolve its `locals`
    field relative to the spec's own directory."""
    return EXAMPLES_ROOT / "motor_mount_plate" / "spec.json"


@pytest.fixture
def simple_locals(tmp_path: Path) -> Path:
    """A tiny locals.txt file with two literal entries."""
    path = tmp_path / "locals.txt"
    path.write_text(
        '"PART_DIAMETER"          = 25.0\n' '"PART_LENGTH"            = 80.0\n',
        encoding="utf-8",
    )
    return path
