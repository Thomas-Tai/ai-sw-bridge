"""W62 offline tests — ``composite`` handler (Mode-A QUARANTINED).

The seat-validated doctrine for composite curves on SW2024:
  * Mode-A is **documented unreachable for CREATION** — the
    ``ICompositeCurveFeatureData`` interface exists in the typelib but has
    no valid ``swFeatureNameID_e`` for ``CreateDefinition`` (the swconst
    harvest exposes only ids 14 and 61 in the curve family; on the live
    seat, 61 returns None and 14 instantiates a generic ref-curve container
    whose QI rejects ICompositeCurveFeatureData with E_NOINTERFACE). The
    interface is edit-only (post-hoc via IFeature.GetDefinition). The
    handler's ``_try_mode_a`` is a no-op stub.
  * Mode-B is the operative path: select edges with ``mark=1`` (the macro-
    recorder's selection mark for the "Edges to join" PropertyManager list
    box), then call ``InsertCompositeCurve`` via the callable-or-property
    indirection (it resolves as a late-bound bool on the raw IDispatch
    proxy — same trap class as FirstFeature).

These tests pin the Mode-B path, the verify gate (feature-node count delta
via _count_feature_nodes), the validation surface, and confirm Mode-A is a
no-op stub.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import composite
from ai_sw_bridge.features.composite import create_composite


@pytest.fixture(autouse=True)
def _mock_curve_length(monkeypatch):
    """Offline, the COM-heavy arc-length read is mocked to a positive default;
    the geometric CURVE gate (W67 P3b) is exercised explicitly in TestCurveGate.
    A composite fake carries no curve geometry, so without this the hard gate
    would null every success path."""
    monkeypatch.setattr(composite, "_curve_length_mm", lambda node: 25.0)


# --- fake COM objects -------------------------------------------------------


class _FakeDoc:
    def __init__(self, *, insert_result=True, raise_clear=False):
        self.cleared = False
        self.rebuilt = False
        self._insert_result = insert_result
        self._raise_clear = raise_clear

    def ClearSelection2(self, flag):
        if self._raise_clear:
            raise RuntimeError("ClearSelection2 boom")
        self.cleared = True

    # InsertCompositeCurve resolves as a *property* on the raw late-bound
    # proxy (the bool the SW dispatch returns). The handler must handle both
    # "callable returning Boolean" and "non-callable Boolean attribute". We
    # model the property shape here so the callable-or-property guard is
    # exercised.
    @property
    def InsertCompositeCurve(self):
        return self._insert_result

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# --- helpers ----------------------------------------------------------------


def _wire(
    monkeypatch, *, select_ok=True, nodes_before=3, nodes_after=4, select_calls=None
):
    """Patch select_entity + _count_feature_nodes on the lane module.

    ``select_calls`` (optional): a list the helper appends ``(edge, append, mark)``
    tuples to so tests can assert the selection-mark contract (mark=1 for
    the "Edges to join" list box).
    """

    def fake_select(e, append=False, mark=0):
        if select_calls is not None:
            select_calls.append((e, append, mark))
        return select_ok

    monkeypatch.setattr(composite, "select_entity", fake_select)

    walk_state = {"call": 0}

    def fake_count(doc):
        walk_state["call"] += 1
        if walk_state["call"] <= 1:
            return nodes_before
        return nodes_after

    monkeypatch.setattr(composite, "_count_feature_nodes", fake_count)


# --- Mode-A quarantine ------------------------------------------------------


class TestModeAQuarantined:
    """Mode-A is a documented unreachable path; _try_mode_a returns None.

    This is intentional and is recorded in the module docstring. If a future
    SW version exposes a valid swFeatureNameID for ICompositeCurveFeatureData
    creation, restore from git history.
    """

    def test_mode_a_returns_none_always(self):
        """_try_mode_a is a no-op stub on every input."""
        assert composite._try_mode_a(_FakeDoc(), [object(), object()]) is None
        assert composite._try_mode_a(None, []) is None


# --- Mode-B happy path ------------------------------------------------------


class TestModeBOperative:
    def test_mode_b_succeeds_and_passes_verify(self, monkeypatch):
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        doc = _FakeDoc(insert_result=True)
        ok, note = create_composite(doc, {}, {"edges": [object(), object()]})
        assert ok is True
        assert "Mode-B" in note
        assert doc.cleared is True
        assert doc.rebuilt is True

    def test_mode_b_uses_mark_1_for_edges_to_join(self, monkeypatch):
        """Macro-recorder corpus: composite curve's 'Edges to join' list box uses mark=1."""
        calls: list[tuple] = []
        _wire(monkeypatch, select_calls=calls)
        e1, e2, e3 = object(), object(), object()
        ok, _ = create_composite(_FakeDoc(), {}, {"edges": [e1, e2, e3]})
        assert ok is True
        assert calls == [(e1, True, 1), (e2, True, 1), (e3, True, 1)]

    def test_mode_b_select_failure_short_circuits(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, note = create_composite(_FakeDoc(), {}, {"edges": [object(), object()]})
        assert ok is False
        assert "Mode-B" in note

    def test_mode_b_insert_returns_false_is_ghost(self, monkeypatch):
        """InsertCompositeCurve property returns False → Mode-B yields None → handler fails."""
        _wire(monkeypatch)
        doc = _FakeDoc(insert_result=False)
        ok, note = create_composite(doc, {}, {"edges": [object(), object()]})
        assert ok is False
        assert "Mode-B" in note

    def test_clear_selection_raise_handled(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(raise_clear=True)
        ok, note = create_composite(doc, {}, {"edges": [object()]})
        assert ok is False


# --- verify gate (ghost trap) -----------------------------------------------


class TestVerifyGate:
    def test_no_new_node_is_ghost(self, monkeypatch):
        """Mode-B returns truthy but no feature node materialized → ghost trap."""
        _wire(monkeypatch, nodes_before=3, nodes_after=3)
        doc = _FakeDoc(insert_result=True)
        ok, note = create_composite(doc, {}, {"edges": [object(), object()]})
        assert ok is False
        assert "no feature node materialized" in note

    def test_new_node_passes_verify(self, monkeypatch):
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        doc = _FakeDoc(insert_result=True)
        ok, _ = create_composite(doc, {}, {"edges": [object()]})
        assert ok is True


# --- validation (fail-closed) -----------------------------------------------


class TestValidation:
    def test_missing_edges_rejected(self):
        ok, err = create_composite(_FakeDoc(), {}, {})
        assert ok is False and "edges" in err

    def test_empty_edges_rejected(self):
        ok, err = create_composite(_FakeDoc(), {}, {"edges": []})
        assert ok is False and "edges" in err

    def test_non_list_edges_rejected(self):
        ok, err = create_composite(_FakeDoc(), {}, {"edges": "not_a_list"})
        assert ok is False and "edges" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_composite(_FakeDoc(), "not_a_dict", {"edges": [1]})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_composite(_FakeDoc(), {}, "not_a_dict")
        assert ok is False and "target must be a dict" in err


# --- CURVE geometric gate (W67 P3b) -----------------------------------------


class TestCurveGate:
    def test_node_without_arc_length_is_rejected(self, monkeypatch):
        """A composite node materialized but with no readable arc length is the
        W42 geometric ghost — the hard gate_curve must reject it."""
        monkeypatch.setattr(composite, "_curve_length_mm", lambda node: None)
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        ok, err = create_composite(_FakeDoc(), {}, {"edges": [object()]})
        assert ok is False
        assert "arc length" in err

    def test_node_with_arc_length_passes(self, monkeypatch):
        monkeypatch.setattr(composite, "_curve_length_mm", lambda node: 70.0)
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        ok, err = create_composite(_FakeDoc(), {}, {"edges": [object()]})
        assert ok is True, err
