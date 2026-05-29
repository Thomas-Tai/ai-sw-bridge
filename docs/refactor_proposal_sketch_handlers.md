# Refactor Proposal: Sketch-Handler Class Hierarchy

**Status:** ✅ APPLIED — shipped in v0.7+. Live code at
[`src/ai_sw_bridge/spec/sketches/`](../src/ai_sw_bridge/spec/sketches/)
with `base.py` (SketchHandler ABC) + per-feature handlers
(rectangle_on_plane.py, rectangle_on_face.py, circle_on_plane.py,
circle_on_face.py, circles_on_face.py).

This document is retained as the design rationale — answers "why a
class hierarchy and not functions?" without re-litigating from
scratch. Read before proposing further sketch-handler refactors.

**Author:** code audit, 2026-05-20.

---

## What this proposes

Convert the five sketch-feature handlers from module-level functions into a small class hierarchy. The non-sketch handlers (extrudes, cuts, fillets, chamfers, patterns, mirror) stay as functions. The handler registry (`FEATURE_REGISTRY`, `_wire_handlers`) keeps the same shape; the only difference is that sketch-feature entries get `Handler.build` (bound method) where they currently get a module-level function.

## What this does NOT propose

- No changes to the 12 non-sketch handlers. They work, they're tested, they don't share enough code for class-extraction to pay.
- No `FeatureHandler` ABC across all 17 handlers. The "mode" dimension (`no_dim`/`deferred_dim`/inline) is only meaningful for sketches; imposing the same ABC across extrudes is structure for the sake of pattern.
- No change to the public surface of `build()`, the CLI, the spec schema, or `BuildResult`. Tests should pass unchanged.
- No `BuildMode` enum replacing the two booleans. The booleans are validated as mutually exclusive at one place; replacing them touches every handler for marginal value.

## Why the sketch handlers specifically

The five sketch handlers (`_build_sketch_rectangle_on_plane`, `_build_sketch_rectangle_on_face`, `_build_sketch_circle_on_plane`, `_build_sketch_circle_on_face`, `_build_sketch_circles_on_face`) share a common life-cycle that no other handler does:

1. Enter a sketch surface (plane OR face)
2. Draw primary geometry (rectangle OR circle OR circle-array)
3. (Rectangles only) Strip the spurious Midpoint relation (Spike ZF, today)
4. Add dimensions, dispatching on `ctx.no_dim` / `ctx.deferred_dim` / inline
5. Close the sketch (`InsertSketch(True)`)
6. Rename the just-created feature to `feat["name"]`
7. Build a `BuiltFeature` recording origin/extent metadata

Steps 1, 2, and 5–7 are entirely duplicated across rectangle-on-plane and rectangle-on-face (just with different setup/teardown). Step 4 is the same three-way branch in every handler. Step 3 was added in two places this morning (Spike ZF).

This is the only place in the codebase where the duplication is real **and** the duplication touches load-bearing logic (the mode dispatch and the Midpoint strip).

## Target shape

### New package layout

```
src/ai_sw_bridge/spec/
├── builder.py              # build() loop, FEATURE_REGISTRY, _wire_handlers (~2150 lines, down from 2883)
└── sketches/               # NEW
    ├── __init__.py         # exports the 5 handler classes
    ├── base.py             # SketchHandler ABC, ~80 lines
    ├── rectangle_on_plane.py   # RectangleOnPlaneHandler, ~80 lines
    ├── rectangle_on_face.py    # RectangleOnFaceHandler, ~100 lines
    ├── circle_on_plane.py      # CircleOnPlaneHandler, ~60 lines
    ├── circle_on_face.py       # CircleOnFaceHandler, ~90 lines
    └── circles_on_face.py      # CirclesOnFaceHandler, ~110 lines
```

Total: 5 new files, ~520 lines added under `sketches/`, ~730 lines removed from `builder.py`. Net change ≈ −200 lines.

### The ABC

```python
# src/ai_sw_bridge/spec/sketches/base.py
"""Sketch-feature handler base class.

Defines the shared life-cycle for all sketch handlers: enter a sketch
surface, draw primary geometry, optionally strip spurious relations, add
dimensions via the mode dispatch, close the sketch, build a BuiltFeature.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from ..builder import BuildContext, BuiltFeature, DeferredDim


@dataclass(frozen=True)
class SketchFrame:
    """Per-sketch state captured during _enter_sketch.

    Attributes:
        center_part: Sketch center in part-frame coordinates (meters).
        face_origin: For face-based sketches only — the face's part-frame
            origin (the point _select_extrude_face succeeded at).
        out_normal: Outward normal of the sketch surface in part frame.
        sketch_extent_uv: For rectangle profiles only — (half_width, half_height)
            in sketch-local frame (meters). None for circle profiles.
    """
    center_part: tuple[float, float, float]
    face_origin: Optional[tuple[float, float, float]] = None
    out_normal: Optional[tuple[float, float, float]] = None
    sketch_extent_uv: Optional[tuple[float, float]] = None


class SketchHandler(abc.ABC):
    """Base for all sketch-feature handlers.

    Subclasses override:
        _enter_sketch: select the surface (plane or face) and open a sketch.
        _draw_geometry: create primitives. Optionally return data (e.g. the
            segment tuple from CreateCenterRectangle) the dim-add step needs.
        _add_dimensions_inline: select entities and call AddDimension2.
        _record_deferred_dimensions: append entries to ctx.deferred_dims for
            later replay.

    The shared life-cycle is handled by build().
    """

    @abc.abstractmethod
    def _enter_sketch(self, ctx: BuildContext, feat: dict[str, Any]) -> SketchFrame:
        """Selects the sketch surface and opens a sketch.

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.

        Returns:
            A SketchFrame capturing the surface's part-frame coordinates.

        Raises:
            RuntimeError: if the surface cannot be selected.
        """

    @abc.abstractmethod
    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> Any:
        """Creates primary geometry (rectangle, circle, or circle-array).

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.
            frame: The sketch frame returned by _enter_sketch.

        Returns:
            Handler-specific geometry data passed to the dim-add methods
            (e.g. captured ISketchSegment tuple for rectangles, None for
            circles).
        """

    @abc.abstractmethod
    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        """Adds driving dimensions immediately (popup blocks each call).

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.
            frame: The sketch frame.
            geometry: Geometry data from _draw_geometry.

        Raises:
            RuntimeError: if any AddDimension2 call returns None.
        """

    @abc.abstractmethod
    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        """Appends DeferredDim entries for later replay (no popups during
        the geometry phase)."""

    def _strip_relations(
        self, ctx: BuildContext, feat: dict[str, Any], geometry: Any
    ) -> None:
        """Optional hook to delete spurious relations after CreateCenterRectangle.

        Default no-op. Overridden by rectangle handlers to strip the Type-14
        Midpoint relation (see Spike ZF, 2026-05-20).
        """
        # Default: nothing to strip.

    def build(self, ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
        """Build this sketch feature end-to-end.

        Args:
            ctx: Per-build state.
            feat: The feature spec entry.

        Returns:
            BuiltFeature recording the sketch's part-frame origin and metadata.
        """
        frame = self._enter_sketch(ctx, feat)
        geometry = self._draw_geometry(ctx, feat, frame)
        self._strip_relations(ctx, feat, geometry)

        if ctx.no_dim:
            # Geometry already at literal target size; no dims, no bindings.
            pass
        elif ctx.deferred_dim:
            self._record_deferred_dimensions(ctx, feat, frame, geometry)
        else:
            self._add_dimensions_inline(ctx, feat, frame, geometry)

        return self._finalize(ctx, feat, frame)

    def _finalize(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> BuiltFeature:
        """Close the sketch, rename, and build a BuiltFeature.

        Calls _draw_centerline_if_present before closing so revolve_boss
        consumers see the centerline as part of the sketch.
        """
        # ... shared close/rename/build BuiltFeature ...
```

### Example concrete handler

```python
# src/ai_sw_bridge/spec/sketches/rectangle_on_plane.py
"""Rectangle sketched on a reference plane (Front/Top/Right)."""

from __future__ import annotations

from typing import Any

import pythoncom
import win32com.client

from ..builder import (
    BuildContext,
    BuiltFeature,
    DeferredDim,
    PLACEHOLDER_MM,
    PLANE_FULL_NAME,
    _dismiss_dim_pane,
    _draw_centerline_if_present,
    _identify_rect_edge,
    _literal_or_default,
    _strip_centerrectangle_midpoint_relation,
)
from .base import SketchFrame, SketchHandler


class RectangleOnPlaneHandler(SketchHandler):
    """Rectangle sketched on a named reference plane.

    Uses CreateCenterRectangle so the rectangle is centered on the sketch
    origin via construction diagonals. The spurious Type-14 Midpoint
    relation (Spike ZF, 2026-05-20) is stripped before adding dimensions.
    """

    def _enter_sketch(
        self, ctx: BuildContext, feat: dict[str, Any]
    ) -> SketchFrame:
        plane = feat["plane"]
        full = PLANE_FULL_NAME[plane]
        if not ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0):
            raise RuntimeError(f"could not select {full}")
        ctx.doc.SketchManager.InsertSketch(True)

        center = feat.get("center", {})
        cx_m = float(center.get("x", 0.0)) / 1000.0
        cy_m = float(center.get("y", 0.0)) / 1000.0
        return SketchFrame(center_part=(cx_m, cy_m, 0.0))

    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> Any:
        width_m = _literal_or_default(
            feat["width"], PLACEHOLDER_MM["rectangle_side"]
        )
        height_m = _literal_or_default(
            feat["height"], PLACEHOLDER_MM["rectangle_side"]
        )
        cx_m, cy_m, _ = frame.center_part
        return {
            "segs": ctx.doc.SketchManager.CreateCenterRectangle(
                cx_m, cy_m, 0.0,
                cx_m + width_m / 2, cy_m + height_m / 2, 0.0,
            ),
            "width_m": width_m,
            "height_m": height_m,
        }

    def _strip_relations(
        self, ctx: BuildContext, feat: dict[str, Any], geometry: Any
    ) -> None:
        _strip_centerrectangle_midpoint_relation(ctx.doc)

    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        # ... (current inline code, unchanged behavior — uses captured
        # segment pointers via Select4, NOT coordinate-based SelectByID,
        # to avoid the post-Midpoint-delete vertex-selection issue)

    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        # ... (current deferred code, unchanged)
```

### Updated registry wire-up

```python
# In builder.py:

from .sketches import (
    RectangleOnPlaneHandler,
    RectangleOnFaceHandler,
    CircleOnPlaneHandler,
    CircleOnFaceHandler,
    CirclesOnFaceHandler,
)

def _wire_handlers() -> None:
    handlers = {
        "sketch_rectangle_on_plane": RectangleOnPlaneHandler().build,
        "sketch_rectangle_on_face": RectangleOnFaceHandler().build,
        "sketch_circle_on_plane": CircleOnPlaneHandler().build,
        "sketch_circle_on_face": CircleOnFaceHandler().build,
        "sketch_circles_on_face": CirclesOnFaceHandler().build,
        # ... non-sketch handlers unchanged:
        "boss_extrude_blind": _build_boss_extrude_blind,
        "cut_extrude_through_all": _build_cut_extrude_through_all,
        # ... etc.
    }
    for name, ft in FEATURE_REGISTRY.items():
        FEATURE_REGISTRY[name] = FeatureType(
            name=ft.name,
            handler=handlers[name],
            dim_fields=ft.dim_fields,
            rhs_walker=ft.rhs_walker,
        )
```

The registry stores `Handler().build` (a bound method) where it currently stores a function. The calling convention from `build()`'s loop is unchanged.

## Google Python Style adherence

This proposal applies all four dimensions you asked for:

1. **Naming.** All classes are PascalCase with full words: `RectangleOnPlaneHandler`, `SketchHandler`, `SketchFrame`. Methods are snake_case with leading underscore for internal: `_enter_sketch`, `_draw_geometry`, `_strip_relations`. No abbreviations in public names (no `Rect`, no `Geom`).
2. **Type hints.** Every method has full annotations including return types. `Optional[T]` from `typing` for nullable fields. `Sequence`/`Mapping` for collection params. `Any` reserved for COM-dispatch objects (matching project precedent — pywin32 late-binding has no real type).
3. **Docstrings.** Google format throughout: one-line summary, blank line, Args:/Returns:/Raises: sections as applicable. Module docstring at top of every new file. Class docstrings include Attributes: section where relevant.
4. **Module organization.** stdlib / third-party / local imports separated by blank lines. No wildcard imports. Module-level docstring at top of every file.

## Risk analysis

### What could go wrong

**(High) Subtle COM-state regressions that 84 tests don't catch.** The 84-test suite uses a stub `MockSwApp` (no live SOLIDWORKS). Tests verify spec validation, schema, RHS resolution, dim-field mapping. They do NOT verify that the SW COM sequence inside each handler is unchanged. A reordering of `ClearSelection2` → `SelectByID` → `AddDimension2` could pass all 84 tests and silently break a live build.

Mitigation: after the refactor compiles cleanly, the smoke-test is an end-to-end MMP build on live SW for **all three modes** (default, `--no-dim`, `--deferred-dim`), with visual EqMgr inspection on each. This is what we did today for Spike ZF; the same protocol applies.

**(Medium) Circular-import risk between `builder.py` and `sketches/`.** The handlers depend on `BuildContext`, `BuiltFeature`, and helpers like `_strip_centerrectangle_midpoint_relation` that currently live in `builder.py`. `builder.py` then imports the handler classes back. If not structured carefully, this circular dependency breaks.

Mitigation: extract `BuildContext`, `BuiltFeature`, `DeferredDim`, `_strip_centerrectangle_midpoint_relation`, `_identify_rect_edge`, `_dismiss_dim_pane`, `_draw_centerline_if_present`, `_literal_or_default`, `PLACEHOLDER_MM`, `PLANE_FULL_NAME`, `_face_frame`, `_sketch_uv_to_part`, `_select_extrude_face`, `_warn_face_sketch_offset` into a separate `_shared.py` module that both `builder.py` and `sketches/*.py` import. This is mechanical but touches a lot of import statements.

**(Medium) Loss of git-blame continuity.** Moving code into new files means `git blame` will show the move as "you added all these lines" rather than tracing back to the original commits. The Spike ZF context (today) and the prior provenance gets buried.

Mitigation: use `git log --follow` for archaeology. Add a note in each new file pointing at the original commit chain.

**(Low) Slightly higher import-time cost.** Five new modules loaded at import time. Negligible (~milliseconds) but real.

**(Low) Code review burden.** This is a +700/−700 line PR. Reviewing it carefully takes 30-60 minutes per file. Most of the changes are mechanical, but the reviewer still has to confirm.

### What will NOT change

- All 84 tests pass unchanged.
- The CLI behavior is identical (same flags, same outputs, same error messages).
- The spec schema is unchanged.
- `BuildResult` wire format is unchanged.
- The handler dispatch from `build()` is unchanged (still a callable lookup in `FEATURE_REGISTRY[feat["type"]].handler`).
- Mode dispatch logic is unchanged (`no_dim` short-circuits at the top, `deferred_dim` records entries, else inline).
- The Spike ZF fix (Midpoint strip, captured-pointer `Select4`) stays intact — just moved into `RectangleOnPlaneHandler._strip_relations` and `_add_dimensions_inline`.

### Rollback plan

```powershell
git checkout master                      # back to v0.6.1
git branch -D refactor/class-hierarchy   # delete the refactor branch
# Or, after merge:
git reset --hard pre-class-refactor-2026-05-20
git push --force-with-lease origin master  # ONLY with explicit approval
```

The `pre-class-refactor-2026-05-20` tag is annotated and points at v0.6.1's SHA. It will never move.

## Estimated effort

- Extracting `_shared.py` (mechanical move + import updates): 30-45 min
- Writing `SketchHandler` ABC + `SketchFrame`: 20 min
- Converting 5 handlers to subclasses: 60-90 min (15 min each, with care)
- Running tests after each conversion: 20 min cumulative
- End-to-end MMP smoke-test on all 3 modes: 15 min (with you ticking popups)
- Doc updates (architecture.md, this proposal closed out): 15 min

**Total: 3-4 hours of focused work.** Not the "4-8 hours" I estimated when proposing the full 17-handler refactor — this is genuinely smaller scope.

## What this proposal does NOT solve

- **Popup ticking.** Still required (12 candidate paths empirically falsified across 6 spike sessions). The refactor doesn't change SW's popup behavior.
- **The 2883-line builder.py problem in general.** Even after the refactor, builder.py is still ~2150 lines. The non-sketch handlers (extrudes, cuts, etc.) make up most of the remaining bulk. They're not duplicative; they're just numerous.
- **`Any`-typed COM dispatch objects.** pywin32 late-binding has no real type for SW interfaces. `Any` stays as the project precedent.

## Recommendation

If you decide to proceed:

1. Read this proposal end-to-end before approving.
2. The work happens on `refactor/class-hierarchy`. Master stays at v0.6.1 until the smoke-test passes.
3. Single commit, ~10 file changes. Reviewable as one diff.
4. Smoke-test: `ai-sw-build motor_mount_plate/spec.json` on all three modes, with visual EqMgr check on each. Same protocol as Spike ZF verification.
5. If green, fast-forward merge to master and push.
6. If anything regresses, `git reset --hard pre-class-refactor-2026-05-20` and we keep v0.6.1.

If you decide NOT to proceed:

1. Delete the `refactor/class-hierarchy` branch (`git branch -D refactor/class-hierarchy`).
2. Keep the `pre-class-refactor-2026-05-20` tag as a v0.6.1 snapshot anyway — costs nothing.
3. This proposal stays in `docs/` as a record of the option that was considered and declined.

## Open questions for the reviewer

1. Is the asymmetry (sketch handlers as classes, non-sketch handlers as functions) acceptable, or do you want a uniform structure across all 17 handlers? My recommendation is keep the asymmetry; the duplication doesn't pay across non-sketch.
2. Should `SketchFrame` carry the `sm` (SketchManager) and `doc` references, or should handlers always reach for `ctx.doc` / `ctx.doc.SketchManager`? My recommendation is keep them on `ctx` only — adding them to `SketchFrame` is duplicate state.
3. Should the Midpoint-strip hook be on `SketchHandler` base (with a default no-op) or only on a hypothetical `RectangleHandler` intermediate base? My recommendation is base with default no-op — there are only two rectangle subclasses, an intermediate base is YAGNI.
