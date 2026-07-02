"""Builder-level dispatch test for ``_select_edges`` (#9), COM stubbed.

The live COM face resolution (``_resolve_face_object`` / ``IFace2.GetEdges``) is
PAE-gated, not unit-testable offline -- so here it is stubbed, and the test
verifies the part that IS deterministic: that ``_select_edges`` parses the
``edges[]`` array, builds the face->edges incidence map, runs the pure set
algebra, de-duplicates, and calls ``IEntity.Select2(True, 0)`` on exactly the
right edges (the two-phase resolve-then-select discipline). The pure algebra
itself is covered separately in ``test_edge_selectors.py``.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import builder
from ai_sw_bridge.spec._build_context import BuildContext, BuiltFeature
from ai_sw_bridge.spec.handlers import dress_up


class _FakeEdge:
    def __init__(self, name, loc):
        self.name = name
        self.loc = loc  # a point on the edge, in meters
        self.selects = []

    def GetClosestPointOn(self, rx, ry, rz):
        # Ignores the reference point: returns the edge's canonical location, so
        # the geometric fingerprint is stable + unique per edge, and a literal
        # query at this point matches with zero distance.
        return (self.loc[0], self.loc[1], self.loc[2])

    def Select2(self, append, mark):
        self.selects.append((append, mark))
        return True


class _FakeBody:
    def __init__(self, edges):
        self._edges = edges

    def GetEdges(self):
        return self._edges


class _FakeDoc:
    def __init__(self, all_edges):
        self._all = all_edges
        self.clears = 0

    def ClearSelection2(self, flag):
        self.clears += 1

    def GetBodies2(self, btype, visible_only):
        return [_FakeBody(self._all)]


# A topologically-valid cube: 12 distinct edges, each face bounded by 4, each
# edge shared by exactly 2 adjacent faces (so +z meets +x along exactly one).
def _cube_edges():
    locs = {
        "T_xp": (0.01, 0.0, 0.02),
        "T_xm": (-0.01, 0.0, 0.02),
        "T_yp": (0.0, 0.01, 0.02),
        "T_ym": (0.0, -0.01, 0.02),
        "B_xp": (0.01, 0.0, 0.0),
        "B_xm": (-0.01, 0.0, 0.0),
        "B_yp": (0.0, 0.01, 0.0),
        "B_ym": (0.0, -0.01, 0.0),
        "V_pp": (0.01, 0.01, 0.01),
        "V_pm": (0.01, -0.01, 0.01),
        "V_mp": (-0.01, 0.01, 0.01),
        "V_mm": (-0.01, -0.01, 0.01),
    }
    return {name: _FakeEdge(name, loc) for name, loc in locs.items()}


_CUBE_FACES = {
    "+z": ["T_xp", "T_xm", "T_yp", "T_ym"],
    "-z": ["B_xp", "B_xm", "B_yp", "B_ym"],
    "+x": ["T_xp", "B_xp", "V_pp", "V_pm"],
    "-x": ["T_xm", "B_xm", "V_mp", "V_mm"],
    "+y": ["T_yp", "B_yp", "V_pp", "V_mp"],
    "-y": ["T_ym", "B_ym", "V_pm", "V_mm"],
}


@pytest.fixture
def env(monkeypatch):
    edges = _cube_edges()
    face_edges = {
        ("Box", face): [edges[n] for n in names] for face, names in _CUBE_FACES.items()
    }
    # Stub the two COM helpers: resolve returns the (name, face) key, and the
    # edge enumerator maps that key to the cube's fake edges (same object across
    # faces, so a shared corner edge intersects/de-dups correctly).
    # Patched on handlers.dress_up (not builder): _select_edges (Phase 3 Move 4)
    # resolves these names from its own module globals, not builder's re-export.
    monkeypatch.setattr(
        dress_up, "_resolve_face_object", lambda ctx, parent, face: (parent.name, face)
    )
    monkeypatch.setattr(
        dress_up, "_face_edge_objects", lambda key: face_edges.get(key, [])
    )
    parent = BuiltFeature(
        name="Box",
        type="boss_extrude_blind",
        extrude_axis=(0.0, 0.0, 1.0),
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.01,
        sketch_extent_uv=(0.01, 0.01),
    )
    ctx = BuildContext(
        sw=None,
        doc=_FakeDoc(list(edges.values())),
        features_by_name={"Box": parent},
    )
    return ctx, edges


def _selected(edges):
    return {name for name, e in edges.items() if e.selects}


def test_of_face_selects_all_four_bounding_edges(env):
    ctx, edges = env
    n = builder._select_edges(ctx, [{"of_feature": "Box", "face": "+z"}])
    assert n == 4
    assert _selected(edges) == {"T_xp", "T_xm", "T_yp", "T_ym"}
    # Each selected exactly once, appended (append=True, mark=0).
    assert edges["T_xp"].selects == [(True, 0)]


def test_between_faces_selects_single_shared_edge(env):
    ctx, edges = env
    n = builder._select_edges(
        ctx, [{"of_feature": "Box", "between_faces": ["+z", "+x"]}]
    )
    assert n == 1
    assert _selected(edges) == {"T_xp"}


def test_literal_point_selects_nearest_edge(env):
    ctx, edges = env
    # T_xp's location is (0.01, 0, 0.02) m == (10, 0, 20) mm.
    n = builder._select_edges(ctx, [{"x": 10.0, "y": 0.0, "z": 20.0}])
    assert n == 1
    assert _selected(edges) == {"T_xp"}


def test_mixed_selectors_dedup_shared_edge(env):
    ctx, edges = env
    # of_face +z includes T_xp; between_faces +z/+x is T_xp again -> 4 unique.
    n = builder._select_edges(
        ctx,
        [
            {"of_feature": "Box", "face": "+z"},
            {"of_feature": "Box", "between_faces": ["+z", "+x"]},
        ],
    )
    assert n == 4
    assert edges["T_xp"].selects == [(True, 0)]  # selected once, not twice


def test_between_faces_no_shared_edge_raises(env):
    ctx, _edges = env
    with pytest.raises(RuntimeError) as ei:
        builder._select_edges(
            ctx, [{"of_feature": "Box", "between_faces": ["+z", "-z"]}]
        )
    assert "edge selector error" in str(ei.value)


def test_literal_point_no_match_raises_legacy_message(env):
    ctx, _edges = env
    # A point nowhere near any edge keeps the exact legacy error string.
    with pytest.raises(RuntimeError) as ei:
        builder._select_edges(ctx, [{"x": 999.0, "y": 999.0, "z": 999.0}])
    assert "matches no edge within 1um" in str(ei.value)


def test_of_face_with_no_bounding_edges_raises(env, monkeypatch):
    ctx, _edges = env
    monkeypatch.setattr(dress_up, "_face_edge_objects", lambda key: [])
    with pytest.raises(RuntimeError) as ei:
        builder._select_edges(ctx, [{"of_feature": "Box", "face": "+z"}])
    assert "no bounding edges" in str(ei.value)
