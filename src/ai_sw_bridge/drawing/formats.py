"""Drawing format registry (P2.x).

Maps each declarative view-type name to the SOLIDWORKS API call pattern
needed to produce it on a drawing sheet.

The view-type *names* are SW-free (pure data). The actual
``CreateDrawViewFromModelView3`` call is SEAT-gated — the dispatch table
records which call path each format uses.

View categories:

- **Standard views** — ``*Front``, ``*Top``, ``*Right``, etc. These use
  ``IDrawingDoc.CreateDrawViewFromModelView3`` with a standard view name.
- **Projected views** — derived from a parent view by projection direction.
- **Section / detail** — need additional sketch geometry on the sheet.
  SEAT-gated and stubbed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DrawingMethod(Enum):
    """Which COM call path produces this view type.

    STANDARD_VIEW: ``CreateDrawViewFromModelView3(part_path, view_name, x, y, z)``
    with a standard view name (``*Front``, ``*Top``, etc.).

    PROJECTED_VIEW: ``CreateDrawViewFromModelView3`` with a parent view
    reference and projection direction. Needs a parent view already on sheet.

    SECTION_VIEW: ``CreateSectionLineAt`` + ``CreateDrawViewFromModelView3``
    with the section-line sketch. SEAT-gated.
    """

    STANDARD_VIEW = "standard_view"
    PROJECTED_VIEW = "projected_view"
    SECTION_VIEW = "section_view"


@dataclass(frozen=True)
class DrawingFormat:
    """One drawable view type.

    Attributes:
        name: The spec-facing view identifier (e.g. ``"front"``).
        view_name: SOLIDWORKS standard view string passed to
            ``CreateDrawViewFromModelView3`` (e.g. ``"*Front"``).
        draw_method: Which COM call path produces this view.
        default_x: Default X position on the sheet (metres, drawing frame).
        default_y: Default Y position on the sheet (metres, drawing frame).
        description: One-line human description for docs / error msgs.
        seat_confirmed: ``False`` until confirmed on a live SW seat.
    """

    name: str
    view_name: str
    draw_method: DrawingMethod
    default_x: float = 0.1
    default_y: float = 0.15
    description: str = ""
    seat_confirmed: bool = False


DRAWING_FORMATS: dict[str, DrawingFormat] = {
    "front": DrawingFormat(
        name="front",
        view_name="*Front",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.1,
        default_y=0.15,
        description="Front orthographic view",
    ),
    "top": DrawingFormat(
        name="top",
        view_name="*Top",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.1,
        default_y=0.4,
        description="Top orthographic view",
    ),
    "right": DrawingFormat(
        name="right",
        view_name="*Right",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.35,
        default_y=0.15,
        description="Right orthographic view",
    ),
    "isometric": DrawingFormat(
        name="isometric",
        view_name="*Isometric",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.35,
        default_y=0.4,
        description="Isometric pictorial view",
    ),
    "dimetric": DrawingFormat(
        name="dimetric",
        view_name="*Dimetric",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.55,
        default_y=0.15,
        description="Dimetric pictorial view",
    ),
    "trimetric": DrawingFormat(
        name="trimetric",
        view_name="*Trimetric",
        draw_method=DrawingMethod.STANDARD_VIEW,
        default_x=0.55,
        default_y=0.4,
        description="Trimetric pictorial view",
    ),
}

DRAWING_FORMAT_NAMES: frozenset[str] = frozenset(DRAWING_FORMATS)


def resolve_format(name: str) -> DrawingFormat:
    """Look up a view format by name. Raises ``ValueError`` on unknown names."""
    try:
        return DRAWING_FORMATS[name]
    except KeyError:
        known = ", ".join(sorted(DRAWING_FORMAT_NAMES))
        raise ValueError(
            f"Unknown drawing view {name!r}. Known views: {known}"
        ) from None
