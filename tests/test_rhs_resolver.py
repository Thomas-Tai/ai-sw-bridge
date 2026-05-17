"""Tests for the no_dim rhs resolver in ai_sw_bridge.spec.builder.

Targets the pure-Python helpers _eval_rhs / _load_locals_map /
_resolve_rhs_in_spec (no SOLIDWORKS dependency).
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ai_sw_bridge.spec.builder import (
    _eval_rhs,
    _load_locals_map,
    _resolve_rhs_in_spec,
)


# -----------------------------------------------------------------------------
# _eval_rhs
# -----------------------------------------------------------------------------


def test_eval_rhs_single_var() -> None:
    lookup = {"FOO": 5.0}.__getitem__
    assert _eval_rhs('"FOO"', lookup) == 5.0


def test_eval_rhs_var_plus_literal() -> None:
    lookup = {"FOO": 5.0}.__getitem__
    assert _eval_rhs('"FOO" + 0.5', lookup) == 5.5


def test_eval_rhs_var_times_var() -> None:
    lookup = {"A": 2.0, "B": 3.0}.__getitem__
    assert _eval_rhs('"A" * "B"', lookup) == 6.0


def test_eval_rhs_returns_float() -> None:
    lookup = {"A": 4}.__getitem__
    out = _eval_rhs('"A"', lookup)
    assert isinstance(out, float)
    assert out == 4.0


# -----------------------------------------------------------------------------
# _load_locals_map
# -----------------------------------------------------------------------------


def test_load_locals_map_literal_values(tmp_path: Path) -> None:
    path = tmp_path / "locals.txt"
    path.write_text(
        '"A" = 1.0\n"B" = 2.5\n"C" = 7\n',
        encoding="utf-8",
    )
    m = _load_locals_map(path)
    assert m == {"A": 1.0, "B": 2.5, "C": 7.0}


def test_load_locals_map_resolves_dependent_vars(tmp_path: Path) -> None:
    path = tmp_path / "locals.txt"
    path.write_text(
        '"A" = 5\n"B" = "A" + 1\n',
        encoding="utf-8",
    )
    m = _load_locals_map(path)
    assert m["A"] == 5.0
    assert m["B"] == 6.0


def test_load_locals_map_raises_on_cycle(tmp_path: Path) -> None:
    path = tmp_path / "locals.txt"
    path.write_text(
        '"A" = "B"\n"B" = "A"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_locals_map(path)
    assert "cycle" in str(exc.value).lower()


def test_load_locals_map_raises_on_undeclared_ref(tmp_path: Path) -> None:
    path = tmp_path / "locals.txt"
    path.write_text(
        '"A" = "MISSING" + 1\n',
        encoding="utf-8",
    )
    with pytest.raises(KeyError):
        _load_locals_map(path)


# -----------------------------------------------------------------------------
# _resolve_rhs_in_spec
# -----------------------------------------------------------------------------


def _spec_with_rhs(locals_path: Path) -> dict:
    return {
        "schema_version": 1,
        "name": "Test",
        "locals": str(locals_path),
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_A",
                "plane": "Front",
                "diameter": {"rhs": '"PART_DIAMETER"'},
            },
            {
                "type": "sketch_circles_on_face",
                "name": "SK_Holes",
                "of_feature": "EX",
                "face": "+z",
                "circles": [
                    {"u": 0.0, "v": 0.0, "diameter": {"rhs": '"PART_LENGTH"'}},
                    {"u": 1.0, "v": 0.0, "diameter": 3.2},
                ],
            },
        ],
    }


def test_resolve_rhs_does_not_mutate_input(simple_locals: Path) -> None:
    spec = _spec_with_rhs(simple_locals)
    snapshot = copy.deepcopy(spec)
    _ = _resolve_rhs_in_spec(spec)
    assert spec == snapshot


def test_resolve_rhs_substitutes_top_level_and_nested_array(simple_locals: Path) -> None:
    spec = _spec_with_rhs(simple_locals)
    out = _resolve_rhs_in_spec(spec)
    # Top-level circle's diameter -> literal 25.0
    assert out["features"][0]["diameter"] == 25.0
    # circles[0].diameter -> literal 80.0
    assert out["features"][1]["circles"][0]["diameter"] == 80.0
    # circles[1].diameter was already a literal: unchanged
    assert out["features"][1]["circles"][1]["diameter"] == 3.2


def test_resolve_rhs_no_locals_key_returns_deepcopy() -> None:
    spec = {
        "schema_version": 1,
        "name": "NoLocals",
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK",
                "plane": "Front",
                "diameter": 5.0,
            }
        ],
    }
    out = _resolve_rhs_in_spec(spec)
    # Equal content, but distinct object (deep-copied)
    assert out == spec
    assert out is not spec
    assert out["features"] is not spec["features"]


def test_resolve_rhs_empty_locals_string_returns_deepcopy() -> None:
    """If `locals` is the empty string (falsy), behave like no locals at all."""
    spec = {
        "schema_version": 1,
        "name": "EmptyLocals",
        "locals": "",
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK",
                "plane": "Front",
                "diameter": 5.0,
            }
        ],
    }
    out = _resolve_rhs_in_spec(spec)
    assert out == spec
    assert out is not spec
