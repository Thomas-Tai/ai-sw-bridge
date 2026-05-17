"""Shared fixtures for the ai-sw-bridge test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EXAMPLES_ROOT = Path(
    r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge\examples"
)


def _load_spec(rel_path: str) -> dict:
    with (EXAMPLES_ROOT / rel_path).open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def cylinder_spec() -> dict:
    """v1 declarative spec for the minimal cylinder."""
    return _load_spec("minimal_cylinder_v2/spec.json")


@pytest.fixture
def mmp_spec() -> dict:
    """v1 declarative spec for the S1b motor-mount plate."""
    return _load_spec("motor_mount_plate/spec.json")


@pytest.fixture
def simple_locals(tmp_path: Path) -> Path:
    """A tiny locals.txt file with two literal entries."""
    path = tmp_path / "locals.txt"
    path.write_text(
        '"PART_DIAMETER"          = 25.0\n'
        '"PART_LENGTH"            = 80.0\n',
        encoding="utf-8",
    )
    return path
