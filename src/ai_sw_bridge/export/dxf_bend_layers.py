"""Flat-pattern DXF bend-line classification + layer assignment (W48).

SOLIDWORKS collapses every flat-pattern DXF entity onto layer ``"0"`` (the W46
wall), so a layer-NAME parser cannot tell a bend (fold) line from the part
outline. ``classify_bend_lines_geometric`` reads the TOPOLOGY instead — the
developed outline is the bounding-rectangle PERIMETER, and bend lines are the
INTERIOR LINE entities that do not lie on a bbox side.

``rewrite_dxf_with_bend_layer`` then performs the production transform the CAM
payload needs: it walks the DXF and re-assigns the layer (group code 8) of every
classified interior bend LINE from ``"0"`` to a dedicated bend layer (default
``"BEND"``), leaving the developed-boundary perimeter on ``"0"``. The rewrite is
IN-PLACE — all other geometry (arcs, text, perimeter lines) is preserved byte
for byte; only the bend LINEs' layer token changes. The bend layer is assigned
at the entity level (DXF consumers auto-create a referenced-but-undeclared
layer); declaring a LAYER table record is a possible refinement.

This module is the canonical home; ``cli.export_dxf_flat`` re-exports the
classifier/parser for back-compat with the W46 offline tests.
"""

from __future__ import annotations

from typing import Any


def _parse_dxf_line_segments(
    dxf_text: str,
) -> list[tuple[float, float, float, float]]:
    """Return every LINE entity as an ``(x1, y1, x2, y2)`` segment.

    A DXF LINE is the group-code run ``0/LINE`` then ``10``=x1, ``20``=y1,
    ``11``=x2, ``21``=y2 (the ``30``/``31`` Z codes are ignored — flat-pattern
    exports are planar). Non-LINE entities (MTEXT/ARC/…) are skipped. Group
    codes for a given LINE may arrive in any order, so we collect them per
    entity and only emit a segment once all four planar coordinates are present.
    """
    lines = dxf_text.splitlines()
    segments: list[tuple[float, float, float, float]] = []
    in_line = False
    pending: dict[str, float] = {}

    def _flush() -> None:
        if {"10", "20", "11", "21"} <= pending.keys():
            segments.append(
                (pending["10"], pending["20"], pending["11"], pending["21"])
            )

    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            if in_line:
                _flush()
            in_line = val == "LINE"
            pending = {}
        elif in_line and code in ("10", "20", "11", "21"):
            try:
                pending[code] = float(val)
            except ValueError:
                pass
        i += 2
    if in_line:
        _flush()
    return segments


def classify_bend_lines_geometric(dxf_text: str) -> dict[str, Any]:
    """Classify flat-pattern LINE entities into OUTLINE perimeter vs. BEND lines.

    The developed outline forms the bounding-rectangle PERIMETER; every bend
    (fold) line is an INTERIOR segment that does not lie on a bbox side.

    Algorithm:
      1. Parse all LINE entities into ``(x1, y1, x2, y2)`` segments.
      2. Compute the bbox (xmin/xmax/ymin/ymax) over every line endpoint.
      3. A segment is PERIMETER iff BOTH endpoints lie on the SAME bbox side
         (both x≈xmin, both x≈xmax, both y≈ymin, or both y≈ymax) within EPS.
      4. Every remaining (non-perimeter) LINE is an INTERIOR bend line.

    EPS = ``max(1e-6, 1e-6 * max_coord_magnitude)`` — 1 ppm of the largest
    absolute coordinate, floored so a degenerate file still gets a finite
    tolerance. Robust to empty / no-LINE input (returns ``bend_line_count=0``,
    ``bbox=None``).
    """
    segments = _parse_dxf_line_segments(dxf_text)
    if not segments:
        return {
            "bend_line_count": 0,
            "bend_lines": [],
            "outline_line_count": 0,
            "bbox": None,
        }

    xs = [c for (x1, _y1, x2, _y2) in segments for c in (x1, x2)]
    ys = [c for (_x1, y1, _x2, y2) in segments for c in (y1, y2)]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    max_mag = max(abs(v) for v in (*xs, *ys))
    eps = max(1e-6, 1e-6 * max_mag)

    def _on(a: float, b: float) -> bool:
        return abs(a - b) <= eps

    bend_lines: list[dict[str, Any]] = []
    outline_count = 0
    for x1, y1, x2, y2 in segments:
        on_perimeter = (
            (_on(x1, x_min) and _on(x2, x_min))
            or (_on(x1, x_max) and _on(x2, x_max))
            or (_on(y1, y_min) and _on(y2, y_min))
            or (_on(y1, y_max) and _on(y2, y_max))
        )
        if on_perimeter:
            outline_count += 1
        else:
            bend_lines.append({"start": [x1, y1], "end": [x2, y2]})

    return {
        "bend_line_count": len(bend_lines),
        "bend_lines": bend_lines,
        "outline_line_count": outline_count,
        "bbox": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        },
    }


def rewrite_dxf_with_bend_layer(
    dxf_text: str, bend_layer: str = "BEND"
) -> tuple[str, dict[str, Any]]:
    """Re-assign every classified interior bend LINE to ``bend_layer``.

    Returns ``(rewritten_dxf_text, classification)``. The classification is the
    ``classify_bend_lines_geometric`` result (so callers can verify/report the
    bend count). When there are no interior bend lines the original text is
    returned unchanged.

    The transform is IN-PLACE: it walks the DXF group-code/value pairs, and for
    each LINE entity whose endpoints match a classified bend segment it replaces
    the value following that entity's layer code (8) — ``"0"`` → ``bend_layer``.
    All other bytes (perimeter LINEs, ARCs, MTEXT, headers, tables) are
    preserved. Line endings are detected and preserved.
    """
    classified = classify_bend_lines_geometric(dxf_text)
    bends = classified["bend_lines"]
    if not bends:
        return dxf_text, classified

    nl = "\r\n" if "\r\n" in dxf_text else "\n"
    lines = dxf_text.split(nl)
    n = len(lines)

    def _close(a: float, b: float) -> bool:
        # The bend coords come from float-parsing THIS same text, so the
        # producing LINE matches exactly; a tight tolerance guards round-trips.
        return abs(a - b) <= 1e-6

    def _matches_bend(x1: float, y1: float, x2: float, y2: float) -> bool:
        for b in bends:
            sx, sy = b["start"]
            ex, ey = b["end"]
            fwd = (
                _close(x1, sx) and _close(y1, sy) and _close(x2, ex) and _close(y2, ey)
            )
            rev = (
                _close(x1, ex) and _close(y1, ey) and _close(x2, sx) and _close(y2, sy)
            )
            if fwd or rev:
                return True
        return False

    cur_entity: str | None = None
    seg: dict[str, float] = {}
    layer_val_idx: int | None = None
    rewrite_idxs: list[int] = []

    def _close_entity() -> None:
        if (
            cur_entity == "LINE"
            and {"10", "20", "11", "21"} <= seg.keys()
            and layer_val_idx is not None
            and _matches_bend(seg["10"], seg["20"], seg["11"], seg["21"])
        ):
            rewrite_idxs.append(layer_val_idx)

    i = 0
    while i < n - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            _close_entity()
            cur_entity = val
            seg = {}
            layer_val_idx = None
        elif cur_entity == "LINE":
            if code in ("10", "20", "11", "21"):
                try:
                    seg[code] = float(val)
                except ValueError:
                    pass
            elif code == "8":
                layer_val_idx = i + 1
        i += 2
    _close_entity()

    for idx in rewrite_idxs:
        orig = lines[idx]
        indent = orig[: len(orig) - len(orig.lstrip())]
        lines[idx] = indent + bend_layer

    classified["rewritten_bend_entities"] = len(rewrite_idxs)
    return nl.join(lines), classified
