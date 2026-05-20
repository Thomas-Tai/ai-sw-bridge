"""Sketch-feature handler base class.

Defines the shared life-cycle for all sketch handlers:

1. Enter a sketch surface (plane or face)
2. Draw primary geometry (rectangle, circle, circle array)
3. Optionally strip spurious relations (Spike ZF Midpoint strip)
4. Add dimensions, dispatching on ``ctx.no_dim`` / ``ctx.deferred_dim``
5. Optional embedded centerline (for revolve_boss consumers)
6. Close the sketch via ``InsertSketch(True)``
7. Rename the freshly-created sketch feature to ``feat["name"]``
8. Build and return a ``BuiltFeature``

Subclasses override:
    ``_enter_sketch``       — surface-pick + InsertSketch + return SketchFrame
    ``_draw_geometry``      — CreateCenterRectangle / CreateCircle / ...
    ``_add_dimensions_inline`` — selection + AddDimension2 (popup blocks)
    ``_record_deferred_dimensions`` — append DeferredDim entries
    ``_finalize``           — close the sketch, rename, build BuiltFeature

The base ``build`` method enforces three invariants that were previously
held only by convention in the function-style handlers:

* ``ClearSelection2(True)`` runs before the subclass touches selection
  inside ``_add_dimensions_inline``.
* If anything raises after the sketch is opened, the base attempts a
  best-effort ``InsertSketch(True)`` close so the next handler does not
  open a sketch-within-a-sketch.
* The ``centerline`` field — currently only meaningful on plane sketches
  (revolve_boss consumers) — is drawn inside ``_finalize`` by the plane
  handlers, matching the function-style behavior the face handlers never
  performed it.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Optional

from .._build_context import BuildContext, BuiltFeature


@dataclass(frozen=True)
class SketchFrame:
    """Per-sketch state captured during ``_enter_sketch``.

    Subclasses populate the fields they need; unused fields stay ``None``.

    Attributes:
        center_part: Sketch center in part-frame coordinates (meters).
            For face-based sketches this is the resolved face-pick point,
            not the sketch-local origin.
        face_origin: For face-based sketches only — the face's part-frame
            origin (the point ``_select_extrude_face`` succeeded at).
        out_normal: Outward normal of the sketch surface in part frame.
            Used by face-based handlers to populate ``parent_plane_normal``
            on the returned ``BuiltFeature``.
        sketch_extent_uv: For rectangle profiles only — ``(half_width,
            half_height)`` in sketch-local frame (meters). ``None`` for
            circle profiles.
    """

    center_part: tuple[float, float, float]
    face_origin: Optional[tuple[float, float, float]] = None
    out_normal: Optional[tuple[float, float, float]] = None
    sketch_extent_uv: Optional[tuple[float, float]] = None


class SketchHandler(abc.ABC):
    """Template-method base for the five sketch-feature handlers.

    Concrete subclasses live in sibling modules
    (``rectangle_on_plane.py`` etc.) and are wired into ``FEATURE_REGISTRY``
    by ``builder._wire_handlers``.
    """

    @abc.abstractmethod
    def _enter_sketch(self, ctx: BuildContext, feat: dict[str, Any]) -> SketchFrame:
        """Select the sketch surface and open a sketch via ``InsertSketch``.

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.

        Returns:
            A ``SketchFrame`` capturing the surface's part-frame
            coordinates and (for face sketches) the resolved face-pick
            point and outward normal.

        Raises:
            RuntimeError: if the surface cannot be selected.
        """

    @abc.abstractmethod
    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> Any:
        """Create primary sketch geometry.

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.
            frame: The sketch frame returned by ``_enter_sketch``.

        Returns:
            Handler-specific geometry data threaded to the dim-add
            methods. For rectangles this is a dict carrying the captured
            ``ISketchSegment`` tuple plus geometry metadata; for single
            circles, the relevant radii/centers.
        """

    @abc.abstractmethod
    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        """Add driving dimensions immediately (popup blocks per call).

        Called by the template ``build`` only when neither ``ctx.no_dim``
        nor ``ctx.deferred_dim`` is set. The template calls
        ``ctx.doc.ClearSelection2(True)`` before this method runs.

        Raises:
            RuntimeError: if any ``AddDimension2`` call returns ``None``
                or a selection step fails.
        """

    @abc.abstractmethod
    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        """Append ``DeferredDim`` entries for later replay.

        Called by the template ``build`` only when ``ctx.deferred_dim``
        is set. No popups should fire from this method.
        """

    @abc.abstractmethod
    def _finalize(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> BuiltFeature:
        """Close the sketch, rename it, and return the ``BuiltFeature``.

        Called by the template ``build`` after the dim-add step (or after
        ``_draw_geometry`` in ``no_dim`` mode). Plane and face handlers
        return different ``BuiltFeature`` shapes; that divergence is the
        reason this is a subclass hook rather than base-owned.
        """

    def _strip_relations(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        geometry: Any,
    ) -> None:
        """Optional hook to delete spurious relations after geometry draw.

        Default no-op. Overridden by the two rectangle handlers to strip
        the Type-14 Midpoint relation that API-side
        ``CreateCenterRectangle`` adds but UI-side does not (Spike ZF,
        2026-05-20).
        """

    def build(self, ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
        """Run the full sketch life-cycle for one feature.

        Template method. Subclasses customize the hooks listed in the
        class docstring; the structure of this method is fixed.
        """
        frame = self._enter_sketch(ctx, feat)
        try:
            geometry = self._draw_geometry(ctx, feat, frame)
            self._strip_relations(ctx, feat, geometry)

            if ctx.no_dim:
                # Geometry is at literal target size; no dim, no binding.
                pass
            elif ctx.deferred_dim:
                self._record_deferred_dimensions(ctx, feat, frame, geometry)
            else:
                ctx.doc.ClearSelection2(True)
                self._add_dimensions_inline(ctx, feat, frame, geometry)

            return self._finalize(ctx, feat, frame, geometry)
        except Exception:
            # Best-effort close so a partially-built sketch does not leak
            # an open sketch session into the next handler. InsertSketch
            # is idempotent in the toggle sense: a second call when no
            # sketch is open is a no-op.
            try:
                ctx.doc.SketchManager.InsertSketch(True)
            except Exception:
                pass
            raise
