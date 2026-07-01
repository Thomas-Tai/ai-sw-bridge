"""Pure (COM-free) edge-selector parsing and set algebra for fillet/chamfer.

Fillet (``fillet_constant_radius``) and chamfer (``chamfer_edge``) address their
target edges through an ``edges[]`` array. Each item is one of three forms:

- literal point  ``{x, y, z}``                      -- the legacy coordinate form
- of_face        ``{of_feature, face}``             -- ALL edges bounding a face
- between_faces  ``{of_feature, between_faces:[A,B]}`` -- the ONE shared edge

The semantic forms (``of_face``, ``between_faces``) survive upstream dimension
edits because they name *topology* (a parent feature's semantic face), not
coordinates: the face -- and therefore its bounding edges -- is re-resolved
against the current geometry on every build, where a stored ``{x, y, z}`` point
would land off the relocated edge and raise "matches no edge within 1um".

This module holds ONLY the COM-free half: classify an item into a frozen
dataclass, and resolve a list of selectors to an ordered, de-duplicated list of
opaque *edge keys* given (a) an abstract ``(of_feature, face) -> frozenset of
edge keys`` incidence map and (b) an injected literal-point resolver. All
SOLIDWORKS COM -- face probing, ``IFace2.GetEdges``, edge fingerprinting,
``IEntity.Select2`` -- lives in ``builder.py`` and is injected here as the
``literal_to_edge`` callable plus the pre-built ``face_edges`` map. That seam is
what makes the set algebra unit-testable with hand-built dicts and no live seat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable, Mapping, Sequence, Tuple, Union

# The six orthogonal face names (mirrors descriptors._FACE_ENUM). Kept as a
# local frozenset rather than imported so this module stays dependency-free and
# importable in isolation by the offline tests.
FACE_NAMES = frozenset({"+x", "-x", "+y", "-y", "+z", "-z"})

# Anti-parallel face pairs: two opposite faces provably share no edge on any
# solid, so a between_faces request naming them is a spec error, not a build one.
_OPPOSITE = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y", "+z": "-z", "-z": "+z"}


class EdgeSelectorError(ValueError):
    """A malformed or unresolvable edge selector.

    ``index`` is the position of the offending item in the feature's ``edges[]``
    array (``None`` when not item-specific), so callers can build a located
    error message.
    """

    def __init__(self, message: str, index: "int | None" = None) -> None:
        super().__init__(message)
        self.index = index


@dataclass(frozen=True)
class LiteralPoint:
    """A point on the target edge, in part-frame millimetres (legacy form)."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class OfFace:
    """Select ALL edges bounding ``face`` of the parent feature ``of_feature``."""

    of_feature: str
    face: str


@dataclass(frozen=True)
class BetweenFaces:
    """Select the SINGLE edge shared by two faces of ``of_feature``."""

    of_feature: str
    faces: "tuple[str, str]"


EdgeSelector = Union[LiteralPoint, OfFace, BetweenFaces]

EdgeKey = Hashable
FaceKey = Tuple[str, str]  # (of_feature, face)


def is_semantic_item(item: object) -> bool:
    """True if an ``edges[]`` item is a semantic selector (of_face/between_faces).

    Cheap structural test used by the validator's feature-flag gate: a semantic
    item is a mapping carrying ``of_feature``; the legacy literal form has
    ``x``/``y``/``z`` instead.
    """
    return isinstance(item, Mapping) and "of_feature" in item


def parse_edge_selector(item: Mapping, index: int = 0) -> EdgeSelector:
    """Classify ONE ``edges[]`` item into a frozen selector dataclass.

    The JSON schema already enforces the item's shape (a ``oneOf`` of the three
    forms); this is defense-in-depth plus the typed in-Python representation.
    Raises :class:`EdgeSelectorError` (carrying ``index``) on a malformed item.
    """
    if not isinstance(item, Mapping):
        raise EdgeSelectorError(
            f"edge selector must be an object, got {type(item).__name__}", index
        )
    keys = set(item)
    if "between_faces" in keys:
        if "of_feature" not in keys or keys - {"of_feature", "between_faces"}:
            raise EdgeSelectorError(
                "between_faces selector takes exactly {of_feature, between_faces}",
                index,
            )
        faces = item["between_faces"]
        if not isinstance(faces, Sequence) or isinstance(faces, str) or len(faces) != 2:
            raise EdgeSelectorError(
                "between_faces must be a list of exactly two face names", index
            )
        a, b = faces[0], faces[1]
        for f in (a, b):
            if f not in FACE_NAMES:
                raise EdgeSelectorError(
                    f"unknown face name {f!r} in between_faces", index
                )
        return BetweenFaces(of_feature=str(item["of_feature"]), faces=(a, b))
    if "of_feature" in keys:
        if "face" not in keys or keys - {"of_feature", "face"}:
            raise EdgeSelectorError(
                "of_face selector takes exactly {of_feature, face}", index
            )
        f = item["face"]
        if f not in FACE_NAMES:
            raise EdgeSelectorError(f"unknown face name {f!r}", index)
        return OfFace(of_feature=str(item["of_feature"]), face=f)
    if {"x", "y", "z"} <= keys and not (keys - {"x", "y", "z"}):
        return LiteralPoint(x=float(item["x"]), y=float(item["y"]), z=float(item["z"]))
    raise EdgeSelectorError(
        f"unrecognized edge selector with keys {sorted(keys)}", index
    )


def parse_edge_selectors(items: Sequence[Mapping]) -> "list[EdgeSelector]":
    """Map :func:`parse_edge_selector` over an ``edges[]`` array, preserving order."""
    return [parse_edge_selector(item, i) for i, item in enumerate(items)]


def faces_referenced(sel: EdgeSelector) -> "tuple[str, ...]":
    """The face names a selector needs resolved (empty tuple for a literal point)."""
    if isinstance(sel, OfFace):
        return (sel.face,)
    if isinstance(sel, BetweenFaces):
        return sel.faces
    return ()


def faces_can_share_edge(a: str, b: str) -> bool:
    """False when two faces provably share no edge (identical or anti-parallel)."""
    return a != b and _OPPOSITE.get(a) != b


def edge_between_faces(
    face_edges: "Mapping[FaceKey, frozenset]",
    a: "FaceKey",
    b: "FaceKey",
    index: int = 0,
) -> EdgeKey:
    """The single edge key shared by faces ``a`` and ``b`` (set intersection).

    Raises :class:`EdgeSelectorError` unless EXACTLY one edge is shared: zero
    means the faces don't meet (or one is unresolved), and more than one means
    the request is ambiguous on this (non-convex) geometry.
    """
    shared = face_edges.get(a, frozenset()) & face_edges.get(b, frozenset())
    if len(shared) == 1:
        return next(iter(shared))
    raise EdgeSelectorError(
        f"between_faces {a[1]}/{b[1]} of '{a[0]}' resolved to {len(shared)} "
        f"shared edges (expected exactly 1)",
        index,
    )


def resolve_edge_selectors(
    parsed: "Sequence[EdgeSelector]",
    *,
    literal_to_edge: "Callable[[LiteralPoint, int], EdgeKey]",
    face_edges: "Mapping[FaceKey, frozenset]",
) -> "list[EdgeKey]":
    """Resolve selectors to an ordered, de-duplicated list of edge keys.

    ``literal_to_edge(point, index)`` resolves a literal point to its edge key
    (the COM closest-match, injected by the builder); ``face_edges`` maps
    ``(of_feature, face)`` to the frozenset of edge keys bounding that face
    (pre-built by the COM adapter). Pure given those inputs -- this is the
    offline-testable core. De-duplication preserves first-seen order so a corner
    edge reached two ways (two of_face selectors, or a literal + a face) is
    selected exactly once.
    """
    out: list = []
    seen: set = set()
    for index, sel in enumerate(parsed):
        if isinstance(sel, LiteralPoint):
            keys = [literal_to_edge(sel, index)]
        elif isinstance(sel, OfFace):
            edges = face_edges.get((sel.of_feature, sel.face))
            if not edges:
                raise EdgeSelectorError(
                    f"of_face {sel.face} of '{sel.of_feature}' has no bounding edges",
                    index,
                )
            keys = sorted(edges)
        elif isinstance(sel, BetweenFaces):
            a = (sel.of_feature, sel.faces[0])
            b = (sel.of_feature, sel.faces[1])
            keys = [edge_between_faces(face_edges, a, b, index)]
        else:  # pragma: no cover - exhaustive over EdgeSelector union
            raise EdgeSelectorError(
                f"unknown selector type {type(sel).__name__}", index
            )
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
    if not out:
        raise EdgeSelectorError("edge selectors resolved to zero edges")
    return out
