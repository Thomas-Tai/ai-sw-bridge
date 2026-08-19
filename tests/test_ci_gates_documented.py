"""Guard: every gate script is named in the CONTRIBUTING CI-gates reference.

``CONTRIBUTING.md`` carries a "CI gates -- what can red your PR" table so a
contributor can see, and reproduce, every gate that guards the repo. That table
drifts the moment a new ``tools/*_gate.py`` lands undocumented. This test fails
in that case, the same way ``test_examples_index_complete.py`` guards the
examples index and ``doc_coverage_gate.py`` guards the feature-type docs. It runs
in the existing pytest CI step, so no ``ci.yml`` change is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRIBUTING = _REPO_ROOT / "CONTRIBUTING.md"

# The gate scripts that run in CI and must appear in the reference table. Every
# tools/*_gate.py is a gate by construction; two_stream_lint.py is the one gate
# whose name does not end in _gate.
_GATE_SCRIPTS = sorted(
    {p.name for p in (_REPO_ROOT / "tools").glob("*_gate.py")} | {"two_stream_lint.py"}
)


def test_contributing_present() -> None:
    """Guard against the check silently passing on a missing file/glob."""
    assert _CONTRIBUTING.is_file(), "CONTRIBUTING.md missing"
    assert _GATE_SCRIPTS, "no gate scripts found -- glob broke"


@pytest.mark.parametrize("gate_script", _GATE_SCRIPTS)
def test_gate_documented(gate_script: str) -> None:
    """Every gate script must be named in the CONTRIBUTING CI-gates reference."""
    text = _CONTRIBUTING.read_text(encoding="utf-8")
    assert gate_script in text, (
        f"tools/{gate_script} is not named in CONTRIBUTING.md -- add it to the "
        "'CI gates -- what can red your PR' reference"
    )
