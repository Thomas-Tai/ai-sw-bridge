"""Drawing dispatch (P2.x).

Iterates the ``drawing:`` block from a schema-v2 spec, creates a drawing
document, places each requested view, and saves the result.

Two-stream discipline (``UIUX.md`` §8):
  - **Human stream** (stderr): one line per view placed, with position.
  - **Machine stream**: ``DrawingResult`` list returned to the caller.

The SW-free skeleton validates view names, resolves positions, and
structures the dispatch loop. The actual COM calls are:

- **Standard views**: ``CreateDrawViewFromModelView3(part_path, view_name,
  x, y, z)`` — the proven call shape. Per-view name strings need a seat
  to confirm.
- **Projected / section views**: SEAT-gated and stubbed.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .formats import (
    DRAWING_FORMATS,
    DrawingFormat,
    DrawingMethod,
    resolve_format,
)

logger = logging.getLogger("ai_sw_bridge.drawing")


@dataclass(frozen=True)
class DrawingRequest:
    """One view from the spec's ``drawing.views`` array.

    Attributes:
        view: View name from ``DRAWING_FORMATS`` (e.g. ``"front"``).
        x: X position on the sheet (metres). ``None`` uses the format default.
        y: Y position on the sheet (metres). ``None`` uses the format default.
    """

    view: str
    x: float | None = None
    y: float | None = None


@dataclass
class DrawingResult:
    """Outcome of one view placement.

    Attributes:
        view: The view name that was requested.
        ok: ``True`` if the view was placed on the sheet.
        position: ``(x, y)`` position where the view was placed.
        error: Human-readable error string on failure; ``None`` on success.
    """

    view: str
    ok: bool
    position: tuple[float, float] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"view": self.view, "ok": self.ok}
        if self.position is not None:
            out["position"] = {"x": self.position[0], "y": self.position[1]}
        if self.error is not None:
            out["error"] = self.error
        return out


def resolve_output_path(
    output_dir: Path,
    part_name: str,
) -> Path:
    """Compute the absolute output path for the drawing file.

    Uses ``part_name`` as the stem with ``.slddrw`` extension.
    Creates the output directory if missing.
    """
    out_path = (output_dir / f"{part_name}.slddrw").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return out_path


def generate_all(
    drawing_doc: Any,
    requests: list[DrawingRequest],
    part_path: str,
) -> list[DrawingResult]:
    """Place every requested view on the drawing document.

    Args:
        drawing_doc: An ``IDrawingDoc``-like dispatch object (live or mock).
        requests: Parsed entries from the spec's ``drawing.views`` array.
        part_path: Absolute path to the part file to create views of.

    Returns:
        One ``DrawingResult`` per request, in the same order. Failures
        are captured per-entry.

    Side effects:
        Prints each placed view to stderr (human stream).
    """
    results: list[DrawingResult] = []
    for req in requests:
        result = _place_one_view(drawing_doc, req, part_path)
        if result.ok:
            pos = result.position or (0, 0)
            print(
                f"  placed {result.view} at ({pos[0]:.3f}, {pos[1]:.3f})",
                file=sys.stderr,
            )
        else:
            print(
                f"  FAILED {result.view}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _place_one_view(
    drawing_doc: Any,
    req: DrawingRequest,
    part_path: str,
) -> DrawingResult:
    """Place one view on the drawing sheet."""
    try:
        fmt = resolve_format(req.view)
    except ValueError as exc:
        return DrawingResult(view=req.view, ok=False, error=str(exc))

    x = req.x if req.x is not None else fmt.default_x
    y = req.y if req.y is not None else fmt.default_y

    if fmt.draw_method == DrawingMethod.STANDARD_VIEW:
        return _standard_view(drawing_doc, fmt, part_path, x, y)

    if fmt.draw_method == DrawingMethod.PROJECTED_VIEW:
        return DrawingResult(
            view=fmt.name,
            ok=False,
            error=(
                "Projected views are SEAT-gated (P2.x). "
                "Need a parent view reference + projection direction."
            ),
        )

    if fmt.draw_method == DrawingMethod.SECTION_VIEW:
        return DrawingResult(
            view=fmt.name,
            ok=False,
            error=(
                "Section views are SEAT-gated (P2.x). "
                "Need section-line sketch + CreateSectionLineAt."
            ),
        )

    return DrawingResult(
        view=fmt.name,
        ok=False,
        error=f"Unhandled draw method: {fmt.draw_method}",
    )


def _standard_view(
    drawing_doc: Any,
    fmt: DrawingFormat,
    part_path: str,
    x: float,
    y: float,
) -> DrawingResult:
    """Create a standard view via CreateDrawViewFromModelView3.

    Post-condition: the view object is returned (non-None).
    """
    try:
        view = drawing_doc.CreateDrawViewFromModelView3(
            part_path, fmt.view_name, x, y, 0.0
        )
    except Exception as exc:
        return DrawingResult(
            view=fmt.name,
            ok=False,
            position=(x, y),
            error=f"CreateDrawViewFromModelView3 raised {type(exc).__name__}: {exc}",
        )

    if view is None or isinstance(view, int):
        return DrawingResult(
            view=fmt.name,
            ok=False,
            position=(x, y),
            error=f"CreateDrawViewFromModelView3 returned {view!r}",
        )

    return DrawingResult(view=fmt.name, ok=True, position=(x, y))
