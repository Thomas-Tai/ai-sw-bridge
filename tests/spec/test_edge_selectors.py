"""Pure (COM-free) tests for the semantic edge-selector core (#9).

``spec/_edge_selectors.py`` is the offline-testable heart of semantic edge
addressing: classify an ``edges[]`` item, and resolve a list of selectors to an
ordered, de-duplicated edge-key list over an abstract face->edges incidence map.
No SOLIDWORKS COM here -- the map and the literal resolver are injected, so the
set algebra (the part that decides WHICH edges get filleted) is verified with
hand-built cube dicts and zero live seat.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec._edge_selectors import (
    BetweenFaces,
    EdgeSelectorError,
    LiteralPoint,
    OfFace,
    edge_between_faces,
    faces_can_share_edge,
    faces_referenced,
    is_semantic_item,
    parse_edge_selector,
    parse_edge_selectors,
    resolve_edge_selectors,
)

# --- A topologically-valid cube incidence map (6 faces, 12 edges, each face
# bounded by 4 edges, each edge shared by exactly 2 adjacent faces). Edge keys
# are plain strings here -- the production keys are geometric fingerprints, but
# the set algebra is key-type-agnostic.
_CUBE = {
    "+z": frozenset({"T_xp", "T_xm", "T_yp", "T_ym"}),
    "-z": frozenset({"B_xp", "B_xm", "B_yp", "B_ym"}),
    "+x": frozenset({"T_xp", "B_xp", "V_pp", "V_pm"}),
    "-x": frozenset({"T_xm", "B_xm", "V_mp", "V_mm"}),
    "+y": frozenset({"T_yp", "B_yp", "V_pp", "V_mp"}),
    "-y": frozenset({"T_ym", "B_ym", "V_pm", "V_mm"}),
}
_FACE_EDGES = {("Box", f): edges for f, edges in _CUBE.items()}


# --- parse_edge_selector ---------------------------------------------------


def test_parse_literal_point():
    sel = parse_edge_selector({"x": 1.0, "y": 2.0, "z": 3.0})
    assert sel == LiteralPoint(1.0, 2.0, 3.0)


def test_parse_of_face():
    sel = parse_edge_selector({"of_feature": "Box", "face": "+z"})
    assert sel == OfFace("Box", "+z")


def test_parse_between_faces():
    sel = parse_edge_selector({"of_feature": "Box", "between_faces": ["+z", "+x"]})
    assert sel == BetweenFaces("Box", ("+z", "+x"))


@pytest.mark.parametrize(
    "item",
    [
        {"x": 1.0, "y": 2.0, "of_feature": "Box"},  # mixed literal + semantic
        {"of_feature": "Box"},  # of_face missing `face`
        {"of_feature": "Box", "face": "+q"},  # unknown face name
        {"of_feature": "Box", "face": "+z", "extra": 1},  # extra key
        {"of_feature": "Box", "between_faces": ["+z"]},  # only one face
        {"of_feature": "Box", "between_faces": ["+z", "+x", "+y"]},  # three faces
        {"of_feature": "Box", "between_faces": ["+z", "bogus"]},  # bad face
        {"x": 1.0, "y": 2.0},  # incomplete literal (missing z)
        {},  # empty
    ],
)
def test_parse_malformed_raises(item):
    with pytest.raises(EdgeSelectorError) as ei:
        parse_edge_selector(item, index=2)
    assert ei.value.index == 2


def test_parse_edge_selectors_preserves_order():
    items = [
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"of_feature": "Box", "face": "+z"},
        {"of_feature": "Box", "between_faces": ["+z", "+x"]},
    ]
    parsed = parse_edge_selectors(items)
    assert [type(p).__name__ for p in parsed] == [
        "LiteralPoint",
        "OfFace",
        "BetweenFaces",
    ]


# --- helpers ---------------------------------------------------------------


def test_is_semantic_item():
    assert is_semantic_item({"of_feature": "Box", "face": "+z"}) is True
    assert (
        is_semantic_item({"of_feature": "Box", "between_faces": ["+z", "+x"]}) is True
    )
    assert is_semantic_item({"x": 1.0, "y": 2.0, "z": 3.0}) is False
    assert is_semantic_item("not a dict") is False


def test_faces_referenced():
    assert faces_referenced(LiteralPoint(0, 0, 0)) == ()
    assert faces_referenced(OfFace("Box", "+z")) == ("+z",)
    assert faces_referenced(BetweenFaces("Box", ("+z", "+x"))) == ("+z", "+x")


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("+z", "+x", True),
        ("+x", "+y", True),
        ("+z", "-z", False),  # anti-parallel -- never share an edge
        ("+x", "-x", False),
        ("+z", "+z", False),  # identical face
    ],
)
def test_faces_can_share_edge(a, b, expected):
    assert faces_can_share_edge(a, b) is expected


# --- edge_between_faces (set intersection) ---------------------------------


def test_edge_between_faces_exactly_one():
    # +z meets +x along exactly one edge on a convex cube.
    assert edge_between_faces(_FACE_EDGES, ("Box", "+z"), ("Box", "+x")) == "T_xp"


def test_edge_between_faces_zero_shared_raises():
    # Opposite faces share no edge.
    with pytest.raises(EdgeSelectorError):
        edge_between_faces(_FACE_EDGES, ("Box", "+z"), ("Box", "-z"))


def test_edge_between_faces_ambiguous_raises():
    # Two faces sharing more than one edge (non-convex) is ambiguous.
    fe = {("P", "A"): frozenset({"e1", "e2"}), ("P", "B"): frozenset({"e1", "e2"})}
    with pytest.raises(EdgeSelectorError):
        edge_between_faces(fe, ("P", "A"), ("P", "B"))


# --- resolve_edge_selectors (the orchestrating set algebra) ----------------


def _lit(_p, index):
    # Deterministic fake literal resolver, keyed by item position.
    return f"lit:{index}"


def test_resolve_of_face_returns_all_four_edges():
    out = resolve_edge_selectors(
        [OfFace("Box", "+z")], literal_to_edge=_lit, face_edges=_FACE_EDGES
    )
    assert set(out) == {"T_xp", "T_xm", "T_yp", "T_ym"}
    assert len(out) == 4


def test_resolve_between_faces_returns_single_edge():
    out = resolve_edge_selectors(
        [BetweenFaces("Box", ("+z", "+x"))],
        literal_to_edge=_lit,
        face_edges=_FACE_EDGES,
    )
    assert out == ["T_xp"]


def test_resolve_mixed_dedups_corner_edge_reached_twice():
    # of_face '+z' yields T_xp among its 4; between_faces +z/+x yields T_xp
    # again. The shared edge must appear exactly once, first-seen order.
    out = resolve_edge_selectors(
        [OfFace("Box", "+z"), BetweenFaces("Box", ("+z", "+x"))],
        literal_to_edge=_lit,
        face_edges=_FACE_EDGES,
    )
    assert out.count("T_xp") == 1
    assert len(out) == 4  # 4 from +z, the between-edge already among them


def test_resolve_literal_and_semantic_combine():
    out = resolve_edge_selectors(
        [LiteralPoint(0, 0, 0), OfFace("Box", "+x")],
        literal_to_edge=_lit,
        face_edges=_FACE_EDGES,
    )
    assert "lit:0" in out
    assert set(out) >= {"T_xp", "B_xp", "V_pp", "V_pm"}


def test_resolve_of_face_with_no_edges_raises():
    with pytest.raises(EdgeSelectorError):
        resolve_edge_selectors(
            [OfFace("Box", "+z")],
            literal_to_edge=_lit,
            face_edges={("Box", "+z"): frozenset()},
        )


def test_resolve_unresolved_face_raises():
    # Face not present in the incidence map at all.
    with pytest.raises(EdgeSelectorError):
        resolve_edge_selectors(
            [OfFace("Box", "+z")], literal_to_edge=_lit, face_edges={}
        )
