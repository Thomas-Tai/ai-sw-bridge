"""Guard: every example directory is linked from ``examples/README.md``.

The examples index is the discoverability surface for the worked examples, and
it has silently drifted before -- new example folders landed without an index
row (11 of 22 were unlisted before this test). This gate fails the moment a
tracked example directory is missing from the index, the same way
``tools/doc_coverage_gate.py`` keeps the feature-type docs honest. It runs in
the existing pytest CI step, so no ``ci.yml`` change is needed.

Scope: examples only. ``docs/README.md`` deliberately omits some tracked files
(gitignored build outputs and internal audits -- see its preamble), so a
filesystem-equals-index check does not apply there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_INDEX = _EXAMPLES_DIR / "README.md"


def _example_dirs() -> list[Path]:
    """Immediate example subfolders, skipping hidden/dunder dirs (e.g. __pycache__)."""
    if not _EXAMPLES_DIR.is_dir():
        return []
    return sorted(
        p
        for p in _EXAMPLES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    )


def test_examples_index_present() -> None:
    """Guard against the whole check silently passing on a broken layout."""
    assert _EXAMPLES_DIR.is_dir(), "examples/ directory missing"
    assert _INDEX.is_file(), "examples/README.md missing"
    assert _example_dirs(), "no example directories found -- glob broke"


@pytest.mark.parametrize("example_dir", _example_dirs(), ids=lambda p: p.name)
def test_example_linked_in_index(example_dir: Path) -> None:
    """Every example folder must appear as a link in the index."""
    index_text = _INDEX.read_text(encoding="utf-8")
    needle = f"{example_dir.name}/"
    assert needle in index_text, (
        f"examples/{example_dir.name}/ is not linked in examples/README.md -- "
        "add an index row so the example is discoverable"
    )
