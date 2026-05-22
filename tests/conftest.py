"""Shared fixtures for the ai-sw-bridge test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Resolve relative to this file so the tests run anywhere the repo is checked
# out -- previously this was hardcoded to one developer's laptop, which
# silently "worked" locally for that developer and broke on every CI runner.
EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"


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
