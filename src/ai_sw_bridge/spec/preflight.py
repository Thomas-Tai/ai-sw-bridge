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


Box = tuple[float, float, float, float, float, float]

# Feature types the axis-aligned box model represents exactly.
_MODELED_ADDITIVE = frozenset({"boss_extrude_blind"})
_MODELED_SUBTRACTIVE = frozenset({"cut_extrude_blind"})


def _boxes_overlap(a: Box, b: Box) -> bool:
    """Whether two axis-aligned part-frame boxes intersect (open-interval;
    touching faces do not count as overlapping)."""
    return (
        a[0] < b[1]
        and b[0] < a[1]  # x
        and a[2] < b[3]
        and b[2] < a[3]  # y
        and a[4] < b[5]
        and b[4] < a[5]  # z
    )


def _plane_rect_box(feat: dict[str, Any]) -> Optional[Box]:
    """Part-frame box of a plane rectangle extruded ``depth`` along its
    normal, or None if not a modelable plane rectangle."""
    plane = feat.get("plane", "")
    if plane not in PLANE_AXES or "width" not in feat or "height" not in feat:
        return None
    cu, cv, offset = _plane_center_uvo(plane, feat.get("center", {}) or {})
    extent = _rect_uv_extent(feat, cu, cv)
    if extent is None:
        return None
    umin, umax, vmin, vmax = extent
    xs, ys, zs = [], [], []
    for u in (umin, umax):
        for v in (vmin, vmax):
            x, y, z = map_plane_point(plane, u, v, offset)
            xs.append(x)
            ys.append(y)
            zs.append(z)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _extruded_box(
    sketch: dict[str, Any], depth: float, flip: bool = False
) -> Optional[Box]:
    """Part-frame box of a plane rectangle extruded ``depth`` along the plane
    normal, or None if ``sketch`` is not a modelable plane rectangle.

    ``flip`` honors the schema's boss/cut ``flip`` field: False sweeps
    +normal (``[lo, lo + depth]``), True sweeps -normal (``[lo - depth, lo]``)
    -- e.g. a blind cut on a top face flipped to cut inward into material.
    A sketch is zero-thickness along its own normal (``lo == hi ==`` the plane
    offset), so the swept box grows from that single offset value.
    """
    base = _plane_rect_box(sketch)
    if base is None:
        return None
    plane = sketch.get("plane", "")
    normal_axis = {"Front": 2, "Top": 1, "Right": 0}[plane]
    lo = min(base[normal_axis * 2], base[normal_axis * 2 + 1])
    box = list(base)
    if flip:
        box[normal_axis * 2] = lo - depth
        box[normal_axis * 2 + 1] = lo
    else:
        box[normal_axis * 2] = lo
        box[normal_axis * 2 + 1] = lo + depth
    return (box[0], box[1], box[2], box[3], box[4], box[5])


# Sketch/echo-only types that should not emit a SKIP note (they add no body).
_SKETCH_ONLY_QUIET = frozenset(
    {
        "sketch_rectangle_on_plane",
        "sketch_circle_on_plane",
        "sketch_circles_on_face",
        "sketch_rectangle_on_face",
        "sketch_circle_on_face",
    }
)
# Types that do not modify the solid body (so a SKIP does not invalidate the
# model).
_NON_BODY_TYPES = frozenset({"linear_pattern", "circular_pattern", "mirror_feature"})


def _skip(i: int, name: str, ftype: str) -> LintFinding:
    """Honest-skip note: this feature is not modeled by the axis-aligned
    envelope, so downstream C1/C2 checks are relaxed rather than risking a
    false positive."""
    return LintFinding(
        severity="info",
        path=f"features/{i}/{name}",
        message=(
            f"pre-flight skip: '{name}' ({ftype}) is not modeled by the "
            f"axis-aligned envelope; downstream geometry checks are relaxed."
        ),
    )


def _hole_offface_finding(
    i: int, feat: dict[str, Any], material: list[Box], modeled_complete: bool
) -> list[LintFinding]:
    """C2: WARN when a ``simple_hole`` on a modeled +z/-z face lands outside
    the union X/Y extent of modeled material at that face."""
    face = feat.get("face", "")
    if face not in {"+z", "-z"} or not material or not modeled_complete:
        return []
    center = feat.get("center", {}) or {}
    cu = float(center.get("u", 0.0))
    cv = float(center.get("v", 0.0))
    r = float(feat.get("diameter", 0.0)) / 2
    # +z/-z face: u->X, v->Y; check the hole footprint against material X/Y union
    xmin = min(m[0] for m in material)
    xmax = max(m[1] for m in material)
    ymin = min(m[2] for m in material)
    ymax = max(m[3] for m in material)
    on = xmin <= cu - r and cu + r <= xmax and ymin <= cv - r and cv + r <= ymax
    if on:
        return []
    return [
        LintFinding(
            severity="warning",
            path=f"features/{i}/center",
            message=(
                f"hole '{feat.get('name', '')}' center ({cu}, {cv}) r{r} lands "
                f"off the modeled {face} face (X[{xmin}, {xmax}], "
                f"Y[{ymin}, {ymax}]) -- it may miss material."
            ),
        )
    ]


def material_envelope_scan(spec: dict[str, Any]) -> list[LintFinding]:
    """Conservative axis-aligned material model. Flags empty-air cuts
    (ERROR) and off-face on-face sketches (WARNING). Any feature the box
    model cannot represent honest-SKIPS (INFO) and marks the model
    incomplete so no false ERROR fires downstream."""
    features = spec.get("features", [])
    sketches = {f.get("name", ""): f for f in features if f.get("plane") in PLANE_AXES}
    material: list[Box] = []
    modeled_complete = True
    findings: list[LintFinding] = []

    for i, feat in enumerate(features):
        ftype = feat.get("type", "")
        name = feat.get("name", "")

        if ftype in _MODELED_ADDITIVE:
            box = _extruded_box(
                sketches.get(feat.get("sketch", ""), {}),
                float(feat.get("depth", 0.0)),
                bool(feat.get("flip", False)),
            )
            if box is None:
                modeled_complete = False
                findings.append(_skip(i, name, ftype))
            else:
                material.append(box)

        elif ftype in _MODELED_SUBTRACTIVE:
            box = _extruded_box(
                sketches.get(feat.get("sketch", ""), {}),
                float(feat.get("depth", 0.0)),
                bool(feat.get("flip", False)),
            )
            if box is None:
                modeled_complete = False
                findings.append(_skip(i, name, ftype))
            elif (
                modeled_complete
                and material
                and not any(_boxes_overlap(box, m) for m in material)
            ):
                findings.append(
                    LintFinding(
                        severity="error",
                        path=f"features/{i}/{name}",
                        message=(
                            f"cut '{name}' sweeps a region disjoint from all "
                            f"modeled material -- this is an empty-air cut and "
                            f"SW will return None. Check the sketch plane, "
                            f"coordinates, and offset (see "
                            f"docs/coordinate_conventions.md)."
                        ),
                    )
                )

        elif ftype == "simple_hole":
            findings.extend(_hole_offface_finding(i, feat, material, modeled_complete))

        elif ftype in {"boss_extrude_midplane", "boss_extrude_two_direction"}:
            # additive but not yet modeled -> conservative: mark incomplete
            modeled_complete = False
            findings.append(_skip(i, name, ftype))

        else:
            # sketches carry no body; every other feature type is unmodeled.
            if ftype not in PLANE_AXES and ftype not in _SKETCH_ONLY_QUIET:
                findings.append(_skip(i, name, ftype))
                if ftype not in _NON_BODY_TYPES:
                    modeled_complete = False

    return findings


def _degenerate_profile_checks(spec: dict[str, Any]) -> list[LintFinding]:
    """WARNING for spec-detectable degenerate profiles: an open polyline
    consumed by a boss/cut, or a construction-only sketch. These map to
    the post-mortem hints (sketch_open_contour_needed_closed,
    sketch_construction_only) in errors/hints.py, promoted to pre-build."""
    features = spec.get("features", [])
    consumed = {
        f.get("sketch", "")
        for f in features
        if f.get("type", "").endswith(
            ("_blind", "_midplane", "_two_direction", "_through_all")
        )
    }
    findings: list[LintFinding] = []
    for i, feat in enumerate(features):
        name = feat.get("name", "")
        if feat.get("type") == "sketch_polyline_on_plane":
            if feat.get("closed", True) is False and name in consumed:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/closed",
                        message=(
                            f"polyline sketch '{name}' is closed:false but is "
                            f"consumed by a boss/cut, which needs a closed "
                            f"profile -- SW raises 'No closed profile'. Close "
                            f"the contour (see errors/hints.py "
                            f"sketch_open_contour_needed_closed)."
                        ),
                    )
                )
            if feat.get("construction", False) is True:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/construction",
                        message=(
                            f"sketch '{name}' is construction-only; a boss/cut "
                            f"has no real entities to sweep (see errors/hints.py "
                            f"sketch_construction_only)."
                        ),
                    )
                )
    return findings


def preflight(spec: dict[str, Any]) -> list[LintFinding]:
    """Run all seat-free geometric pre-flight analyzers over ``spec``.

    Returns INFO coordinate echoes, WARNING advisories, and at most one
    ERROR per provable empty-air cut. Never raises; never touches SW.
    """
    findings: list[LintFinding] = []
    findings.extend(coordinate_mapping_report(spec))
    findings.extend(material_envelope_scan(spec))
    findings.extend(_degenerate_profile_checks(spec))
    return findings
