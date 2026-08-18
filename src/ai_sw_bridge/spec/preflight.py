"""Seat-free geometric pre-flight for ai-sw-build specs.

Two independent analyzers, both pure functions over the spec dict that
return ``LintFinding`` lists and never touch SOLIDWORKS:

1. ``coordinate_mapping_report`` — exact, deterministic INFO echoes of the
   part-frame coordinates each plane-sketch maps to (Component 1).
2. ``material_envelope_scan`` — a conservative axis-aligned material model
   that flags empty-air cuts and off-material on-face sketches, and
   honestly SKIPS any feature it cannot model exactly (Component 2).

Wired into ``ai-sw-build --lint`` via ``preflight``. See
docs/superpowers/specs/2026-08-18-geometric-preflight-design.md and
docs/coordinate_conventions.md.
"""

from __future__ import annotations

from typing import Any, Optional

from .lint import LintFinding

# Plane name -> (X, Y, Z) token exprs over sketch-local u, v and offset o.
PLANE_AXES: dict[str, tuple[str, str, str]] = {
    "Front": ("u", "v", "o"),
    "Top": ("u", "o", "-v"),
    "Right": ("o", "v", "-u"),
}


def _eval_axis(token: str, u: float, v: float, o: float) -> float:
    return {"u": u, "-u": -u, "v": v, "-v": -v, "o": o}[token]


def map_plane_point(
    plane: str, u: float, v: float, offset: float
) -> tuple[float, float, float]:
    """Map a sketch-local point (u, v) on ``plane`` to part-frame (x, y, z).

    ``offset`` is the plane's position along its own normal (0 for the
    standard planes through the origin). Raises KeyError on unknown plane.
    """
    ax, ay, az = PLANE_AXES[plane]
    return (
        _eval_axis(ax, u, v, offset),
        _eval_axis(ay, u, v, offset),
        _eval_axis(az, u, v, offset),
    )


def _plane_center_uvo(plane: str, center: dict[str, Any]) -> tuple[float, float, float]:
    """Project a part-frame sketch ``center`` {x, y, z} (mm) to sketch-local
    (u, v) plus the plane's out-of-plane offset o, consistent with
    ``PLANE_AXES``: Front->(x, y, z); Top->(x, -z, y); Right->(-z, y, x).

    The real schema's plane-sketch ``center`` is part-frame (see
    descriptors.py ``_SKETCH_PLANE_CENTER``); the builder projects it
    per-plane (sketches/rectangle_on_plane.py). Front is identity in x/y;
    Top and Right carry the out-of-plane component that must NOT be dropped.
    """
    x = float(center.get("x", 0.0))
    y = float(center.get("y", 0.0))
    z = float(center.get("z", 0.0))
    if plane == "Top":
        return x, -z, y
    if plane == "Right":
        return -z, y, x
    return x, y, z  # Front (and default)


def _rect_uv_extent(
    feat: dict[str, Any], cu: float, cv: float
) -> Optional[tuple[float, float, float, float]]:
    """Return (umin, umax, vmin, vmax) for a rectangle/circle plane-sketch
    centered at sketch-local (cu, cv), or None if the feature carries no
    modelable planar profile."""
    if "width" in feat and "height" in feat:
        w, h = float(feat["width"]), float(feat["height"])
        return (cu - w / 2, cu + w / 2, cv - h / 2, cv + h / 2)
    if "diameter" in feat:
        r = float(feat["diameter"]) / 2
        return (cu - r, cu + r, cv - r, cv + r)
    return None


def coordinate_mapping_report(spec: dict[str, Any]) -> list[LintFinding]:
    """Emit one INFO finding per plane-sketch naming its part-frame spans.

    Exact (a linear transform of declared coordinates) — zero
    false-positive risk. On-face sketches (no ``plane``) are skipped;
    they are handled by ``material_envelope_scan``.
    """
    findings: list[LintFinding] = []
    for i, feat in enumerate(spec.get("features", [])):
        plane = feat.get("plane", "")
        if plane not in PLANE_AXES:
            continue
        cu, cv, offset = _plane_center_uvo(plane, feat.get("center", {}) or {})
        extent = _rect_uv_extent(feat, cu, cv)
        if extent is None:
            continue
        umin, umax, vmin, vmax = extent
        xs, ys, zs = [], [], []
        for u, v in ((umin, vmin), (umax, vmax)):
            x, y, z = map_plane_point(plane, u, v, offset)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        msg = (
            f"{plane} sketch '{feat.get('name', '')}': part spans "
            f"X[{min(xs)}, {max(xs)}], Y[{min(ys)}, {max(ys)}], "
            f"Z[{min(zs)}, {max(zs)}] (plane offset {offset})"
        )
        findings.append(
            LintFinding(severity="info", path=f"features/{i}/plane", message=msg)
        )
    return findings
