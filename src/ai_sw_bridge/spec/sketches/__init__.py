"""Sketch-feature handlers as a small class hierarchy.

The five sketch handlers share a common life-cycle (enter surface, draw
primary geometry, optionally strip spurious relations, add dimensions via
the 3-mode dispatch, close, rename, build a BuiltFeature). The shared
work lives in ``SketchHandler.build`` in :mod:`.base`; each concrete
handler overrides the surface-entry, geometry-draw, and dim-add steps.
"""

from __future__ import annotations

from .base import SketchFrame, SketchHandler
from .circle_on_face import CircleOnFaceHandler
from .circle_on_plane import CircleOnPlaneHandler
from .circles_on_face import CirclesOnFaceHandler
from .rectangle_on_face import RectangleOnFaceHandler
from .rectangle_on_plane import RectangleOnPlaneHandler

__all__ = [
    "CircleOnFaceHandler",
    "CircleOnPlaneHandler",
    "CirclesOnFaceHandler",
    "RectangleOnFaceHandler",
    "RectangleOnPlaneHandler",
    "SketchFrame",
    "SketchHandler",
]
