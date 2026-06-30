"""Guardrail: tools_reference.md documents ai-sw-build's real exit codes.

``build.py`` returns 0/2/3/4/5/6/7 and never 1 (1 is the shared ``ok:false``
code used by other CLIs, e.g. ai-sw-batch / ai-sw-checkpoint). The
``tools_reference.md`` "Exit codes" section once listed only ``0/1/2`` and
claimed "stderr is unused" -- both wrong for ai-sw-build, which uses the richer
set and writes its seat banner to stderr. This test pins the fix so the doc
can't regress. The authoritative codes live in the ``_emit(...)`` calls in
``cli/build.py``.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DOC = (_ROOT / "docs" / "tools_reference.md").read_text(encoding="utf-8")

# ai-sw-build's specific exit codes (the shared 0/1/2 convention is separate).
_BUILD_CODES = (3, 4, 5, 6, 7)


def test_tools_reference_documents_build_exit_codes() -> None:
    parts = _DOC.split("## Exit codes", 1)
    assert len(parts) == 2, "tools_reference.md lost its '## Exit codes' section"
    body = parts[1]
    for code in _BUILD_CODES:
        assert f"`{code}`" in body, f"ai-sw-build exit code {code} is undocumented"
    # build writes its seat banner to stderr; the old doc wrongly said the
    # opposite ("stderr is unused").
    assert "stderr" in body.lower(), "Exit-codes section no longer mentions stderr"
