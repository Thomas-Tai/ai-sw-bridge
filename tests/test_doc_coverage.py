"""Test for tools/doc_coverage_gate.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "tools" / "doc_coverage_gate.py"
VENV_PYTHON = REPO_ROOT / ".venv-freshtest" / "Scripts" / "python.exe"


def test_doc_coverage_passes() -> None:
    """The doc coverage gate should pass on the current repo."""
    result = subprocess.run(
        [str(VENV_PYTHON), str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (
        result.returncode == 0
    ), f"Doc coverage gate failed:\n{result.stdout}\n{result.stderr}"
