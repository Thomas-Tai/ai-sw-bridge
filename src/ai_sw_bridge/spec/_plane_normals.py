"""Reference-plane outward normals and the sketch-to-normal stash rule.

A child extrude inherits its axis from the parent sketch's
``parent_plane_normal``. Plane-hosted sketches get it from the plane they
were drawn on; face-based sketch handlers stash the face's own outward
normal instead. Both live here so the mapping is defined in one place.
"""

from __future__ import annotations

from typing import Any

from .schema import PLANE_HOSTED_SKETCH_TYPES

# Plane name -> outward-normal vector in part coordinates
# (+X right, +Y up, +Z out of screen).
# Matches SW's default English template orientation:
#   Front Plane = XY plane (normal +Z)
#   Top   Plane = XZ plane (normal +Y)
#   Right Plane = YZ plane (normal +X)
PLANE_NORMALS: dict[str, tuple[float, float, float]] = {
    "Front": (0.0, 0.0, 1.0),
    "Top": (0.0, 1.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
}


def _stash_plane_normal(bf: Any, feat: dict[str, Any]) -> None:
    """Give a plane-hosted sketch the outward normal of its plane.

    A child extrude reads ``parent_plane_normal`` and raises when it is
    None, so every plane-hosted sketch type must be covered. This keys off
    the schema-derived PLANE_HOSTED_SKETCH_TYPES rather than a hand-kept
    list: the previous four-type tuple silently omitted sketch_slot,
    sketch_polygon, sketch_text, sketch_line, sketch_arc and sketch_spline,
    so the first extrude consuming any of them failed the build.

    Face-based handlers stash their own face normal, so they are left alone.
    """
    if bf.type in PLANE_HOSTED_SKETCH_TYPES:
        bf.parent_plane_normal = PLANE_NORMALS[feat["plane"]]
