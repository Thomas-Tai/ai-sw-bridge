"""Regression guard: the constant-radius fillet handler MUST force a rebuild
before it resolves its semantic edge selectors.

Root cause (verified live 2026-08-17): a prior topology-changing feature -- a
through-all cut in particular -- can leave the model un-rebuilt, so the fillet's
``_select_edges`` -> ``_resolve_face_object`` face query transiently misses a
side face the body actually has (the ``demo_bearing_block`` "could not resolve
-x face of 'EX_Block'" build failure). The same face resolves 12/12 against the
same body once the model is rebuilt. The chamfer handler already guards against
this with ``ForceRebuild3`` (after itself); the fillet now does the equivalent
BEFORE its face query.

This test is COM-free: ``FeatureManager`` and ``_select_edges`` are stubbed and
the call ORDER is recorded, so the guard cannot silently regress if someone
reshuffles the handler body.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec._build_context import BuildContext
from ai_sw_bridge.spec.handlers import dress_up


class _FakeFilletData:
    def __init__(self) -> None:
        self._radius: float | None = None

    def Initialize(self, fillet_type: int) -> bool:
        self.initialize_type = int(fillet_type)
        return True

    @property
    def DefaultRadius(self) -> float:
        return self._radius if self._radius is not None else 0.0

    @DefaultRadius.setter
    def DefaultRadius(self, value: float) -> None:
        self._radius = float(value)


class _FakeFeature:
    def __init__(self) -> None:
        self.Name: str | None = None


class _FakeFM:
    def __init__(self, data: _FakeFilletData, feat: _FakeFeature) -> None:
        self._data = data
        self._feat = feat
        self.def_calls: list[int] = []
        self.create_calls: list[object] = []

    def CreateDefinition(self, type_id: int) -> _FakeFilletData:
        self.def_calls.append(int(type_id))
        return self._data

    def CreateFeature(self, data: object) -> _FakeFeature:
        self.create_calls.append(data)
        return self._feat


class _FakeDoc:
    """Records ForceRebuild3 into a shared ordered event log."""

    def __init__(self, events: list) -> None:
        self.events = events
        self.data = _FakeFilletData()
        self.feature = _FakeFeature()
        self.FeatureManager = _FakeFM(self.data, self.feature)
        self.rebuilds = 0

    def ForceRebuild3(self, top_only: bool) -> bool:
        self.rebuilds += 1
        self.events.append(("rebuild", top_only))
        return True


def _feat() -> dict:
    return {
        "name": "FIL_Block",
        "type": "fillet_constant_radius",
        "radius": 3.0,  # literal mm
        "edges": [{"of_feature": "EX_Block", "between_faces": ["+x", "+y"]}],
    }


def _ctx_with_recorded_select(monkeypatch) -> tuple[BuildContext, list, _FakeDoc]:
    events: list = []
    doc = _FakeDoc(events)
    ctx = BuildContext(sw=None, doc=doc, features_by_name={})

    def fake_select(ctx_arg, edges):
        events.append(("select", len(edges)))
        return 4  # non-zero so the handler does not treat it as a no-op

    monkeypatch.setattr(dress_up, "_select_edges", fake_select)
    return ctx, events, doc


def test_fillet_rebuilds_before_resolving_edges(monkeypatch):
    ctx, events, doc = _ctx_with_recorded_select(monkeypatch)
    dress_up._build_fillet_constant_radius(ctx, _feat())

    # The whole point: the rebuild lands BEFORE the edge/face resolution.
    kinds = [e[0] for e in events]
    assert kinds == ["rebuild", "select"], (
        "fillet must ForceRebuild3 before _select_edges (stale B-rep after a "
        f"through-all cut misses side faces otherwise); saw {kinds}"
    )
    assert doc.rebuilds == 1  # exactly once, not on a loop


def test_fillet_rebuild_is_full_not_top_only(monkeypatch):
    # Mirror the chamfer handler's ForceRebuild3(False): a full rebuild, so a
    # topology change earlier in the tree is actually settled before the query.
    ctx, events, _doc = _ctx_with_recorded_select(monkeypatch)
    dress_up._build_fillet_constant_radius(ctx, _feat())
    rebuild_args = [arg for kind, arg in events if kind == "rebuild"]
    assert rebuild_args == [False]


def test_fillet_still_builds_the_feature(monkeypatch):
    # Guard-rail must not change the observable result: definition on
    # SW_FM_FILLET, radius in metres, feature named, BuiltFeature returned.
    ctx, _events, doc = _ctx_with_recorded_select(monkeypatch)
    bf = dress_up._build_fillet_constant_radius(ctx, _feat())
    assert doc.FeatureManager.def_calls == [dress_up.SW_FM_FILLET]
    assert doc.data.initialize_type == dress_up.SW_CONST_RADIUS_FILLET
    assert doc.data.DefaultRadius == pytest.approx(0.003)
    assert doc.feature.Name == "FIL_Block"
    assert bf.name == "FIL_Block"
