"""Edge-match predicate — "are these two edges geometrically the same?" (O2 spec).

This module is the *pure, SW-free contract* that the edge-fingerprint fallback
(tier-2 of :func:`selection.live.resolve_edge_ref`, worker S1) is built around.
It answers one question with no COM in sight: given two edge geometries (the
manifest-edge / ``BrepEdge.to_dict`` shape — ``start`` / ``end`` / ``length`` /
``midpoint``), do they denote the *same physical edge* within tolerance?

Why a separate predicate (and why Opus authored it before S1 wired it)
----------------------------------------------------------------------
The discriminating power of an edge fingerprint is entirely a function of *what
geometry the interrogator captured*, and today that is impoverished:

* ``length`` is ``math.dist(start, end)`` — the **chord** length, not arc length
  (``interrogator.py:480``).
* ``midpoint`` is ``(start + end) / 2`` — the **chord** midpoint, not the true
  curve midpoint (``interrogator.py:475``).

Both are therefore *derived from the endpoints*. With current capture the only
independent geometric datum an edge carries is its **unordered endpoint pair**,
so this predicate necessarily collapses to "do the endpoint pairs coincide?".
The load-bearing consequence — written here so S1 and reviewers cannot miss it —
is a known **false-positive class**: a straight edge and a curved edge sharing
the same two vertices (e.g. a chord vs a semicircular arc between the same
points) are *indistinguishable* under current capture. See
``test_selection_live.py::TestEdgeMatchPredicate`` for the adversarial cases
that pin this, including the pair that documents the collision.

The predicate is nonetheless written to gate on **endpoints (unordered)**,
**length**, *and* **midpoint** together. Today length and midpoint are
redundant with the endpoints, so the extra gates are free and never reject a
true match. The moment the interrogator captures a *true* arc length and a
*true* curve midpoint (the recommended follow-up — a ~1-line interrogator change
plus a re-spike), those two gates become independent and the predicate
auto-discriminates straight-from-curved with **zero S1 rework**. The
forward-correct shape is the whole point of authoring the predicate up front.

"Direction" (from the menu sketch) is deliberately *not* a separate gate:
unordered-endpoint equality already pins the chord direction, so a direction
check would be pure redundancy under every capture regime. It is folded into the
endpoint comparison, documented here rather than coded twice.

Tolerances
----------
Mirror the face fallback tolerances (``selection.live`` lines 48-54):

* ``_EDGE_POINT_TOL_M`` (endpoint + midpoint position) mirrors the face
  ``_FP_CENTROID_TOL_M`` = 1 mm.
* ``_EDGE_LENGTH_TOL_M`` mirrors it at 1 mm — a chord/arc length delta below a
  millimetre is treated as the same edge.
* ``_EDGE_DIR_TOL`` (``1 - |dot|`` of the two chord directions) mirrors the face
  ``_FP_NORMAL_TOL`` = 0.02 (~11°). It is exposed for callers/tests that want to
  reason about direction explicitly, but is *not* part of the default gate (see
  above — it is subsumed by the endpoint gate).

Failure mode
------------
Every function is fail-soft: malformed or missing geometry yields ``None`` (no
match) and never raises, matching the never-throw-into-the-build-loop contract
of :mod:`selection.live`.
"""

from __future__ import annotations

import math
from typing import Any

# --- tolerances (mirror selection.live face-fallback tolerances) ---
_EDGE_POINT_TOL_M = 1e-3  # 1 mm — endpoint & midpoint position drift
_EDGE_LENGTH_TOL_M = 1e-3  # 1 mm — length delta (chord today; arc once captured)
_EDGE_DIR_TOL = 0.02  # 1 - |dot| of chord directions (~11 deg); not gated by default


def _vec3(seq: Any) -> tuple[float, float, float] | None:
    """Coerce *seq* to a float 3-tuple, or ``None`` if it is malformed."""
    if not isinstance(seq, (list, tuple)) or len(seq) != 3:
        return None
    try:
        return (float(seq[0]), float(seq[1]), float(seq[2]))
    except (TypeError, ValueError):
        return None


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _chord_dir(
    start: tuple[float, float, float], end: tuple[float, float, float]
) -> tuple[float, float, float] | None:
    """Unit chord direction ``end - start``, or ``None`` for a zero-length chord."""
    dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    if mag == 0.0:
        return None
    return (dx / mag, dy / mag, dz / mag)


def chord_direction_error(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    """``1 - |dot|`` of the two edges' chord directions (sign-agnostic).

    Exposed for explicit direction reasoning (and tests). ``None`` if either
    chord is degenerate (zero length) or malformed. This is *not* part of the
    default :func:`edge_match_score` gate — unordered-endpoint equality already
    pins direction — but it is the canonical "direction" measure should a future
    caller want it.
    """
    a_start, a_end = _vec3(a.get("start")), _vec3(a.get("end"))
    b_start, b_end = _vec3(b.get("start")), _vec3(b.get("end"))
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return None
    da, db = _chord_dir(a_start, a_end), _chord_dir(b_start, b_end)
    if da is None or db is None:
        return None
    dot = abs(da[0] * db[0] + da[1] * db[1] + da[2] * db[2])
    return 1.0 - dot


def edge_match_score(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    point_tol_m: float = _EDGE_POINT_TOL_M,
    length_tol_m: float = _EDGE_LENGTH_TOL_M,
) -> tuple[float, float, float] | None:
    """Return a sortable match key for two edges, or ``None`` if they differ.

    Both arguments are edge dicts in the manifest / ``BrepEdge.to_dict`` shape:
    ``start`` / ``end`` (required 3-tuples), ``length`` (optional float),
    ``midpoint`` (optional 3-tuple). Endpoints are matched **unordered** — an
    edge matches itself with start/end swapped.

    A pair qualifies iff *all* of these hold under the tolerances:

    * the better of the two endpoint pairings has both endpoint distances
      ``<= point_tol_m``;
    * if both carry a ``length``, ``abs(la - lb) <= length_tol_m``;
    * if both carry a ``midpoint``, ``dist(ma, mb) <= point_tol_m``.

    (length / midpoint gates are skipped when either side omits them, so the
    predicate stays correct for partially-populated dicts; they only ever
    *tighten* a match, never loosen it.)

    The returned key is ``(endpoint_err, length_err, midpoint_err)`` — all
    "smaller is better", so a caller walking live edges can keep the
    lexicographically-smallest key as the best candidate, mirroring the face
    fallback's ``(1 - dot, centroid_dist)`` ordering in
    :func:`selection.live.resolve_by_fingerprint`. Returns ``None`` (never
    raises) when the pair fails any gate or either dict is malformed.
    """
    a_start, a_end = _vec3(a.get("start")), _vec3(a.get("end"))
    b_start, b_end = _vec3(b.get("start")), _vec3(b.get("end"))
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return None

    # Unordered endpoint match: take the better of the two pairings.
    pairing_aligned = max(_dist(a_start, b_start), _dist(a_end, b_end))
    pairing_swapped = max(_dist(a_start, b_end), _dist(a_end, b_start))
    endpoint_err = min(pairing_aligned, pairing_swapped)
    if endpoint_err > point_tol_m:
        return None

    # Length gate (independent of endpoints only once true arc-length is
    # captured; redundant-but-free today). Skipped if either side omits length.
    length_err = 0.0
    la, lb = a.get("length"), b.get("length")
    if la is not None and lb is not None:
        try:
            length_err = abs(float(la) - float(lb))
        except (TypeError, ValueError):
            return None
        if length_err > length_tol_m:
            return None

    # Midpoint gate (the discriminator once a true curve midpoint is captured;
    # redundant-but-free today). Skipped if either side omits midpoint.
    midpoint_err = 0.0
    ma, mb = _vec3(a.get("midpoint")), _vec3(b.get("midpoint"))
    if a.get("midpoint") is not None and b.get("midpoint") is not None:
        if ma is None or mb is None:
            return None
        midpoint_err = _dist(ma, mb)
        if midpoint_err > point_tol_m:
            return None

    return (endpoint_err, length_err, midpoint_err)


def edges_match(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    point_tol_m: float = _EDGE_POINT_TOL_M,
    length_tol_m: float = _EDGE_LENGTH_TOL_M,
) -> bool:
    """Boolean convenience over :func:`edge_match_score` (``score is not None``)."""
    return (
        edge_match_score(a, b, point_tol_m=point_tol_m, length_tol_m=length_tol_m)
        is not None
    )


__all__ = [
    "chord_direction_error",
    "edge_match_score",
    "edges_match",
    "_EDGE_DIR_TOL",
    "_EDGE_LENGTH_TOL_M",
    "_EDGE_POINT_TOL_M",
]
