"""Unit tests for ``_nominal_or_placeholder`` (SW-free).

Deferred-dim geometry must be created at its NOMINAL resolved size when the
build context carries a ``locals_map`` -- so the later driving dim matches the
geometry and does not resize (and thus drift) it. Without a map (inline/no_dim),
an ``{rhs}`` length falls back to the placeholder exactly as ``_literal_or_default``
did. A literal always passes straight through.

NOTE the rhs wire format: the variable name is QUOTED *inside* the rhs string
(``{"rhs": "\\"BLOCK_W\\""}``) -- that is how the spec stores it and what
``_eval_rhs`` substitutes against.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec._sketch_primitives import _nominal_or_placeholder


class _Ctx:
    def __init__(self, locals_map=None):
        self.locals_map = locals_map


def test_literal_passes_through_mm_to_m():
    assert _nominal_or_placeholder(_Ctx(), 40.0, 10.0) == pytest.approx(0.040)


def test_rhs_with_locals_map_resolves_to_nominal():
    ctx = _Ctx({"BLOCK_W": 40.0, "BLOCK_H": 28.0})
    assert _nominal_or_placeholder(ctx, {"rhs": '"BLOCK_W"'}, 10.0) == pytest.approx(
        0.040
    )
    assert _nominal_or_placeholder(ctx, {"rhs": '"BLOCK_H"'}, 10.0) == pytest.approx(
        0.028
    )


def test_rhs_arithmetic_expression_resolves():
    ctx = _Ctx({"BLOCK_W": 40.0})
    assert _nominal_or_placeholder(
        ctx, {"rhs": '"BLOCK_W" / 2'}, 10.0
    ) == pytest.approx(0.020)


def test_rhs_without_locals_map_falls_back_to_placeholder():
    # inline / no_dim path: no map -> legacy placeholder behavior.
    assert _nominal_or_placeholder(
        _Ctx(None), {"rhs": '"BLOCK_W"'}, 10.0
    ) == pytest.approx(0.010)


def test_rhs_unknown_name_falls_back_to_placeholder():
    ctx = _Ctx({"OTHER": 5.0})
    # Unresolvable rhs must NOT raise -- it fails safe to the placeholder.
    assert _nominal_or_placeholder(ctx, {"rhs": '"MISSING"'}, 10.0) == pytest.approx(
        0.010
    )


def test_empty_locals_map_falls_back_to_placeholder():
    assert _nominal_or_placeholder(
        _Ctx({}), {"rhs": '"BLOCK_W"'}, 10.0
    ) == pytest.approx(0.010)
