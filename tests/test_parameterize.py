"""Tests for the pure helpers in ai_sw_bridge.parameterize.

Skips _extract_vba (needs a real .swp binary) and parameterize() end-to-end.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.parameterize import (
    _build_link_block,
    _build_param_bindings,
)


# -----------------------------------------------------------------------------
# _build_link_block
# -----------------------------------------------------------------------------


def test_link_block_emits_filepath_assignment_with_escaped_quotes() -> None:
    # A path containing a literal double-quote must have it doubled in the
    # emitted VBA string literal.
    path = r'C:\evil"path\locals.txt'
    out = _build_link_block(path)
    # The doubled quote pattern must be present
    assert r'C:\evil""path\locals.txt' in out
    # And the raw single quote must NOT appear unescaped inside the literal
    assert r'C:\evil"path\locals.txt' not in out


def test_link_block_has_required_vba_lines() -> None:
    out = _build_link_block(r"C:\tmp\locals.txt")
    assert "bridgeEq.FilePath" in out
    assert "bridgeEq.LinkToFile = True" in out
    assert "bridgeEq.AutomaticRebuild = True" in out
    assert "UpdateValuesFromExternalEquationFile" in out
    # Path round-trips
    assert r"C:\tmp\locals.txt" in out


def test_link_block_plain_path_unmodified() -> None:
    path = r"C:\tmp\locals.txt"
    out = _build_link_block(path)
    # Plain path has no inner quotes => should appear verbatim, wrapped in "..."
    assert f'"{path}"' in out


# -----------------------------------------------------------------------------
# _build_param_bindings
# -----------------------------------------------------------------------------


def test_param_bindings_emits_add2_with_doubled_quotes() -> None:
    bindings = [{"dim": "D1@Sketch1", "rhs": '"PART_DIAMETER"'}]
    out = _build_param_bindings(bindings)
    # Inside the VBA string literal, every " becomes ""
    # Expected formula inside the literal: ""D1@Sketch1"" = ""PART_DIAMETER""
    assert '""D1@Sketch1"" = ""PART_DIAMETER""' in out
    assert "bridgeEq.Add2(-1," in out


def test_param_bindings_wraps_legacy_var() -> None:
    """Legacy spec form: {"dim": ..., "var": "FOO"} -> RHS becomes "FOO"."""
    bindings = [{"dim": "D1@Sketch1", "var": "PART_DIAMETER"}]
    out = _build_param_bindings(bindings)
    # Legacy `var` gets wrapped in quotes -> doubled in VBA literal -> ""PART_DIAMETER""
    assert '""D1@Sketch1"" = ""PART_DIAMETER""' in out


def test_param_bindings_raises_when_neither_rhs_nor_var() -> None:
    bindings = [{"dim": "D1@Sketch1"}]
    with pytest.raises(ValueError) as exc:
        _build_param_bindings(bindings)
    assert "rhs" in str(exc.value).lower() or "var" in str(exc.value).lower()


def test_param_bindings_empty_returns_empty_string() -> None:
    assert _build_param_bindings([]) == ""


def test_param_bindings_emits_one_add2_per_binding() -> None:
    bindings = [
        {"dim": "D1@A", "rhs": '"X"'},
        {"dim": "D2@A", "rhs": '"Y" + 1'},
        {"dim": "D1@B", "var": "Z"},
    ]
    out = _build_param_bindings(bindings)
    # Each binding emits one Add2 call
    assert out.count("bridgeEq.Add2(-1,") == 3


def test_param_bindings_includes_rebuild_call() -> None:
    bindings = [{"dim": "D1@Sketch1", "rhs": '"FOO"'}]
    out = _build_param_bindings(bindings)
    # Must end with an EditRebuild3 so dims propagate
    assert "EditRebuild3" in out


def test_param_bindings_expression_rhs_doubled_correctly() -> None:
    """An rhs like `"X" + 0.5` should end up as ""X"" + 0.5 inside the literal."""
    bindings = [{"dim": "D1@A", "rhs": '"X" + 0.5'}]
    out = _build_param_bindings(bindings)
    assert '""D1@A"" = ""X"" + 0.5' in out
