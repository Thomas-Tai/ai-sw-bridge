"""W62 offline tests — ``composite`` handler (dual-mode contract).

Tests pin the Mode-A (CreateDefinition + typed_qi + SetEntitiesToJoin +
CreateFeature) and Mode-B (select edges + InsertCompositeCurve) branches,
plus the verify-gate (feature-node delta → True; no delta → False ghost).

COM seams are patched on the lane module itself (``features.composite``) per
the registry lane protocol. No SW process is involved.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import composite
from ai_sw_bridge.features.composite import create_composite


# --- fake COM objects -------------------------------------------------------


class _FakeFeatureData:
    """Mimics a raw FeatureData returned by CreateDefinition."""

    def __init__(self):
        self._oleobj_ = object()
        self.accessed = False
        self.entities = None
        self.released = False

    def AccessSelections(self, doc, callout):
        self.accessed = True

    def SetEntitiesToJoin(self, edges):
        self.entities = edges

    def ReleaseSelectionAccess(self):
        self.released = True


class _FakeTypedData:
    """Mimics the typed_qi-wrapped ICompositeCurveFeatureData."""

    def __init__(self, inner: _FakeFeatureData):
        self._inner = inner

    def AccessSelections(self, doc, callout):
        self._inner.AccessSelections(doc, callout)

    def SetEntitiesToJoin(self, edges):
        self._inner.SetEntitiesToJoin(edges)

    def ReleaseSelectionAccess(self):
        self._inner.ReleaseSelectionAccess()


class _FakeFM:
    def __init__(self, *, create_def=None, create_feat=None):
        self._create_def = create_def
        self._create_feat = create_feat
        self.create_feature_calls = []

    def CreateDefinition(self, feature_id):
        if self._create_def is not None:
            return self._create_def
        return _FakeFeatureData()

    def CreateFeature(self, data):
        self.create_feature_calls.append(data)
        if self._create_feat is not None:
            return self._create_feat
        return object()


class _FakeFeatureNode:
    """A node in the feature tree walk."""

    def __init__(self, next_node=None):
        self._next = next_node

    def GetNextFeature(self):
        return self._next


class _FakeDoc:
    def __init__(self, *, node_count_before=3, node_count_after=4,
                 insert_result=True, fm=None):
        self.FeatureManager = fm or _FakeFM()
        self._nodes_before = node_count_before
        self._nodes_after = node_count_after
        self._insert_result = insert_result
        self.cleared = False
        self.rebuilt = False
        self._walk_count = 0

    def FirstFeature(self):
        self._walk_count += 1
        if self._walk_count % 2 == 1:
            return self._build_chain(self._nodes_before)
        return self._build_chain(self._nodes_after)

    def _build_chain(self, n):
        if n <= 0:
            return None
        nodes = [_FakeFeatureNode() for _ in range(n)]
        for i in range(n - 1):
            nodes[i]._next = nodes[i + 1]
        nodes[-1]._next = None
        return nodes[0]

    def ClearSelection2(self, flag):
        self.cleared = True

    def InsertCompositeCurve(self):
        return self._insert_result

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# --- helpers ----------------------------------------------------------------


def _wire(monkeypatch, *, mode_a_ok=True, mode_b_ok=True,
          nodes_before=3, nodes_after=4, select_ok=True):
    """Patch typed_qi and select_entity seams on the composite lane module."""
    if mode_a_ok:
        inner_data = _FakeFeatureData()

        def fake_typed_qi(obj, iface, *, module=None):
            return _FakeTypedData(inner_data)

        monkeypatch.setattr(composite, "typed_qi", fake_typed_qi)
    else:
        from ai_sw_bridge.com.earlybind import EarlyBindError

        def failing_typed_qi(obj, iface, *, module=None):
            raise EarlyBindError(f"object does not implement {iface!r} (E_NOINTERFACE)")

        monkeypatch.setattr(composite, "typed_qi", failing_typed_qi)

    monkeypatch.setattr(composite, "select_entity", lambda e, append=False, mark=0: select_ok)

    walk_state = {"call": 0}

    def fake_count(doc):
        walk_state["call"] += 1
        if walk_state["call"] <= 1:
            return nodes_before
        return nodes_after

    monkeypatch.setattr(composite, "_count_feature_nodes", fake_count)


# --- Mode-A happy path ------------------------------------------------------


class TestModeA:
    def test_mode_a_creates_composite(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=True)
        doc = _FakeDoc()
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is True
        assert "Mode-A" in note

    def test_mode_a_uses_set_entities_to_join(self, monkeypatch):
        inner_data = _FakeFeatureData()

        def fake_typed_qi(obj, iface, *, module=None):
            return _FakeTypedData(inner_data)

        monkeypatch.setattr(composite, "typed_qi", fake_typed_qi)
        _wire(monkeypatch, mode_a_ok=True)
        # Re-patch typed_qi after _wire to use our specific inner_data
        monkeypatch.setattr(composite, "typed_qi", fake_typed_qi)

        doc = _FakeDoc()
        e1, e2 = object(), object()
        ok, note = create_composite(doc, {}, {"edges": [e1, e2]})
        assert ok is True
        assert inner_data.accessed is True
        assert inner_data.entities == [e1, e2]
        assert inner_data.released is True


# --- Mode-B fallback -------------------------------------------------------


class TestModeB:
    def test_mode_b_fallback_on_qi_failure(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=False, mode_b_ok=True)
        doc = _FakeDoc()
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is True
        assert "Mode-B" in note
        assert doc.cleared is True

    def test_mode_b_calls_insert_composite_curve(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=False, mode_b_ok=True)
        doc = _FakeDoc()
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is True

    def test_mode_b_select_failure(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=False, mode_b_ok=True, select_ok=False)
        doc = _FakeDoc()
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is False
        assert "both Mode-A" in note


# --- both modes fail -------------------------------------------------------


class TestBothModesFail:
    def test_both_modes_fail_returns_false(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=False, mode_b_ok=False)
        doc = _FakeDoc(insert_result=False)
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is False
        assert "both Mode-A" in note

    def test_insert_returns_false(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=False)
        doc = _FakeDoc(insert_result=False)
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is False


# --- verify gate (ghost trap) -----------------------------------------------


class TestVerifyGate:
    def test_no_new_node_is_ghost(self, monkeypatch):
        """Mode returns success but no feature node materialized → ghost trap."""
        _wire(monkeypatch, mode_a_ok=False, mode_b_ok=True,
              nodes_before=3, nodes_after=3)
        doc = _FakeDoc()
        edges = [object(), object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
        assert ok is False
        assert "no feature node materialized" in note

    def test_new_node_passes_verify(self, monkeypatch):
        _wire(monkeypatch, mode_a_ok=True, nodes_before=3, nodes_after=4)
        doc = _FakeDoc()
        edges = [object()]
        ok, note = create_composite(doc, {}, {"edges": edges})
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
