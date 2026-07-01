"""Face-frame geometry helpers shared by face-sketch handlers and simple-hole.

Pure geometry plus the SOLIDWORKS face-selection probe ``_select_extrude_face``.
Consumed by the sketch handlers in ``sketches/`` and by ``_build_simple_hole``
in ``builder.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._build_context import BuildContext, BuiltFeature


# Plane name -> outward-normal vector (in part coordinates, +X right, +Y up,
# +Z out of screen). Matches SW's default English template orientation:
#   Front Plane = XY plane (normal +Z)
#   Top   Plane = XZ plane (normal +Y)
#   Right Plane = YZ plane (normal +X)
PLANE_FULL_NAME = {
    "Front": "Front Plane",
    "Top": "Top Plane",
    "Right": "Right Plane",
}


# Per-face sketch-frame table for a parent extrusion whose axis is +z
# (the only parent orientation supported for side faces in v1). For each
# face, we record:
#   u_axis: the sketch +u direction in part-frame (unit vector)
#   v_axis: the sketch +v direction in part-frame (unit vector)
# Together with the face-center point, they let us convert any sketch
# (u, v) point to part-frame coords for SelectByID.
#
# Discovered empirically by Spike U4 (2026-05-18) -- created a centered
# 30mm cube, sketched circles at sketch (u=+5, v=+3) on each side face,
# extruded outward bosses, and measured the boss-cap centers in part
# coords. The mapping below reproduces those observed centers.
#
#   +z face (top):  sketch +u -> part +x, sketch +v -> part +y
#   -z face (bot):  sketch +u -> part -x, sketch +v -> part +y
#   +x face (right):sketch +u -> part -z, sketch +v -> part +y
#   -x face (left): sketch +u -> part +z, sketch +v -> part +y
#   +y face (back): sketch +u -> part +x, sketch +v -> part -z
#   -y face (front):sketch +u -> part +x, sketch +v -> part +z
_FACE_UV_AXES_PARENT_PLUSZ: dict[
    str, tuple[tuple[int, int, int], tuple[int, int, int]]
] = {
    "+z": ((1, 0, 0), (0, 1, 0)),
    "-z": ((-1, 0, 0), (0, 1, 0)),
    "+x": ((0, 0, -1), (0, 1, 0)),
    "-x": ((0, 0, 1), (0, 1, 0)),
    "+y": ((1, 0, 0), (0, 0, -1)),
    "-y": ((1, 0, 0), (0, 0, 1)),
}

# Side-face sketch-on-face frames for +y-axis (Top Plane) and +x-axis (Right
# Plane) parents (Task #15). These are SOLIDWORKS' OWN sketch coordinate axes
# on each side face, read directly off ISketch.ModelToSketchTransform on a live
# seat (Task #15 diag, 2026-07-01) -- so `sketch_origin + u*u_axis + v*v_axis`
# lands exactly where SW maps sketch (u, v). Only the +y / +x (non-flipped)
# orientations are measured; ±z uses the table above, everything else stays
# uv_calibrated=False (sketch-on-face refused) until measured.
_FACE_UV_AXES_PARENT_PLUSY: dict[
    str, tuple[tuple[int, int, int], tuple[int, int, int]]
] = {
    "+x": ((0, 0, 1), (0, 1, 0)),
    "-x": ((0, 0, -1), (0, 1, 0)),
    "+y": ((1, 0, 0), (0, 1, 0)),
    "-y": ((-1, 0, 0), (0, 1, 0)),
}
_FACE_UV_AXES_PARENT_PLUSX: dict[
    str, tuple[tuple[int, int, int], tuple[int, int, int]]
] = {
    "+x": ((1, 0, 0), (0, 1, 0)),
    "-x": ((-1, 0, 0), (0, 1, 0)),
    "+y": ((1, 0, 0), (0, 0, 1)),
    "-y": ((1, 0, 0), (0, 0, -1)),
}


@dataclass(frozen=True)
class FaceFrame:
    """The part-frame embedding of a face's sketch coordinate system.

    Two reference points to keep separate:
    - face_center: geometric center of the face. Used by _select_extrude_face
      to seed the face-pick (highest probability of hitting material).
    - sketch_origin: where SW puts the (u=0, v=0) point of a sketch
      created on this face. Empirically, SW projects the PART ORIGIN onto
      the face plane to define the sketch's (0,0). For +z/-z faces, that
      lands on the face center (because the face is perpendicular to the
      part-origin's projection axis). For side faces (+/-x, +/-y),
      sketch_origin lands on the BOTTOM EDGE of the face (z=0), not the
      face center -- this is the gotcha that _warn_face_sketch_offset
      surfaces. Used by _sketch_uv_to_part to convert sketch coords to
      part-frame coords for SKETCHSEGMENT picks and AddDimension2 leaders.

    Lets a handler do:
      part_xyz = sketch_origin + u * u_axis + v * v_axis
    to compute the part-frame click point for a sketch entity at (u, v).

    out_normal is the face's outward-pointing unit normal in part coords;
    used for boss/cut direction inheritance.
    """

    face_center: tuple[float, float, float]
    sketch_origin: tuple[float, float, float]
    u_axis: tuple[float, float, float]
    v_axis: tuple[float, float, float]
    out_normal: tuple[float, float, float]
    # True when u_axis/v_axis/sketch_origin are the CALIBRATED sketch-on-face
    # frame (safe for _sketch_uv_to_part -> child-feature placement). False for
    # side faces of ±x/±y-axis (Top/Right-plane) parents, where face_center +
    # out_normal are measured-correct (enough for fillet/chamfer edge selection
    # and the _select_extrude_face probe) but the in-plane u/v are NOT yet
    # calibrated for placing a sketch. _sketch_uv_to_part refuses those.
    uv_calibrated: bool = True


def _face_frame(parent: BuiltFeature, face: str) -> FaceFrame:
    """Build the part-frame transform for a +z-axis parent extrusion's face.

    The parent must:
      - have extrude_axis == +/- z (the only supported parent orientation
        for side faces in v1; ±z faces also work for ±y, ±x parents)
      - for ±x/±y faces specifically: have sketch_extent_uv set (i.e. the
        parent profile is a rectangle, not a circle/arbitrary curve).
        Without extents we don't know where the side face lives.

    Raises RuntimeError with a clear message on any of these violations.
    """
    assert parent.extrude_origin is not None, f"{parent.name}: extrude_origin not set"
    assert parent.extrude_axis is not None, f"{parent.name}: extrude_axis not set"
    assert parent.extrude_depth_m is not None, f"{parent.name}: extrude_depth_m not set"
    ox, oy, oz = parent.extrude_origin
    ax, ay, az = parent.extrude_axis
    depth = parent.extrude_depth_m
    if parent.extrude_flip:
        ax, ay, az = -ax, -ay, -az

    # ±z faces: handled for any parent axis. Logic preserves prior behavior:
    #   "+z" face = outboard face (extrude_origin + axis * depth)
    #   "-z" face = inboard face (extrude_origin)
    if face in ("+z", "-z"):
        if face == "+z":
            fx0 = ox + ax * depth
            fy0 = oy + ay * depth
            fz0 = oz + az * depth
            out_nrm = (ax, ay, az)
        else:
            fx0, fy0, fz0 = ox, oy, oz
            out_nrm = (-ax, -ay, -az)
        # In-face sketch frame depends on parent axis orientation. Today
        # we only have a verified table for parent axis = +z (Front Plane).
        # For Top/Right Plane parents, fall back to the historical
        # mirror_u convention so existing parts don't regress.
        if abs(az) > 0.99:
            u_ax, v_ax = _FACE_UV_AXES_PARENT_PLUSZ[face]
        elif abs(ay) > 0.99:
            # Top Plane parent (axis +y). Sketch X -> part X, sketch Y -> part Z.
            # On the inboard "-z" of this parent (= -y of part), mirror u.
            if face == "+z":
                u_ax, v_ax = (1, 0, 0), (0, 0, 1)
            else:
                u_ax, v_ax = (-1, 0, 0), (0, 0, 1)
        else:
            # Right Plane parent (axis +x). Sketch X -> part Y, sketch Y -> part Z.
            if face == "+z":
                u_ax, v_ax = (0, 1, 0), (0, 0, 1)
            else:
                u_ax, v_ax = (0, -1, 0), (0, 0, 1)
        # ±z face: sketch_origin == face_center (part origin projects onto
        # the face center along the face normal, which is parallel to the
        # part-origin axis).
        return FaceFrame(
            face_center=(fx0, fy0, fz0),
            sketch_origin=(fx0, fy0, fz0),
            u_axis=(float(u_ax[0]), float(u_ax[1]), float(u_ax[2])),
            v_axis=(float(v_ax[0]), float(v_ax[1]), float(v_ax[2])),
            out_normal=out_nrm,
        )

    # ±x, ±y faces: side faces (parallel to the extrude axis). Addressable on
    # Front/Top/Right-plane extrudes with a rectangular profile (known
    # half-extents); a circular/arbitrary profile has a curved side surface.
    if parent.sketch_extent_uv is None:
        raise RuntimeError(
            f"side face '{face}' of '{parent.name}': parent has no "
            f"sketch_extent_uv stashed. Side faces are only addressable on "
            f"extrusions whose profile is a rectangle (the rectangle's "
            f"half-extents define where the side faces sit). For circle/"
            f"arbitrary-curve profiles the side surface is curved and "
            f"can't be sketched on through this builder."
        )
    half_u, half_v = parent.sketch_extent_uv

    # Sketch-plane basis in part frame, keyed by the parent's extrude axis.
    # This is the ORIGINAL-sketch extent mapping (where the rectangle's u/v
    # half-extents point in part frame), measured empirically (Task #14 diag,
    # 2026-07-01) by building Top- and Right-plane boxes and reading the
    # resulting face normals + positions:
    #   Front (axis ∥z): sketch u -> +x, v -> +y
    #   Top   (axis ∥y): sketch u -> +x, v -> +z
    #   Right (axis ∥x): sketch u -> +z, v -> +y
    # NOTE this is DISTINCT from _FACE_UV_AXES_PARENT_PLUSZ, which is the
    # sketch-ON-a-face frame (a different operation, calibrated separately).
    if abs(az) > 0.99:
        ext_u, ext_v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    elif abs(ay) > 0.99:
        ext_u, ext_v = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    elif abs(ax) > 0.99:
        ext_u, ext_v = (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
    else:
        raise RuntimeError(
            f"side face '{face}' of '{parent.name}': parent extrude axis "
            f"({ax:+.2f}, {ay:+.2f}, {az:+.2f}) is not axis-aligned; side "
            f"faces are only addressable on Front/Top/Right-plane extrudes."
        )

    # Face center = the extrude mid-depth point (origin + half the depth along
    # the flip-adjusted axis) shifted by the half-extent along the in-sketch
    # axis this face faces.
    mx = ox + 0.5 * ax * depth
    my = oy + 0.5 * ay * depth
    mz = oz + 0.5 * az * depth
    if face in ("+x", "-x"):
        s = 1.0 if face == "+x" else -1.0
        ext, half = ext_u, half_u
        in_plane_v = ext_v  # the other in-sketch axis lies in the face plane
    elif face in ("+y", "-y"):
        s = 1.0 if face == "+y" else -1.0
        ext, half = ext_v, half_v
        in_plane_v = ext_u
    else:
        raise RuntimeError(f"unknown face label {face!r}")
    out_nrm = (s * ext[0], s * ext[1], s * ext[2])
    face_center = (
        mx + s * half * ext[0],
        my + s * half * ext[1],
        mz + s * half * ext[2],
    )

    # sketch_origin: SW projects the part origin (0,0,0) onto the face plane.
    # For an axis-aligned face plane `face_center . n = d`, that projection is
    # `d * n`.
    nx, ny, nz = out_nrm
    d = face_center[0] * nx + face_center[1] * ny + face_center[2] * nz
    sketch_origin = (d * nx, d * ny, d * nz)

    # Pick the CALIBRATED sketch-on-face u/v table for this parent orientation,
    # if one has been measured. Front (±z) has always been calibrated; Top (+y)
    # and Right (+x) were measured in Task #15 (SW's own sketch frame). Other
    # orientations (flipped -y/-x axis, etc.) are not yet measured.
    calibrated_table = None
    if abs(az) > 0.99:
        calibrated_table = _FACE_UV_AXES_PARENT_PLUSZ  # byte-identical to pre-#14
    elif ay > 0.99:
        calibrated_table = _FACE_UV_AXES_PARENT_PLUSY
    elif ax > 0.99:
        calibrated_table = _FACE_UV_AXES_PARENT_PLUSX

    if calibrated_table is not None:
        u_ax, v_ax = calibrated_table[face]
        return FaceFrame(
            face_center=face_center,
            sketch_origin=sketch_origin,
            u_axis=(float(u_ax[0]), float(u_ax[1]), float(u_ax[2])),
            v_axis=(float(v_ax[0]), float(v_ax[1]), float(v_ax[2])),
            out_normal=out_nrm,
        )

    # No calibrated sketch frame for this orientation. face_center + out_normal
    # are measured-correct (enough for fillet/chamfer edge selection and the
    # _select_extrude_face probe), but the in-plane axes below are only valid
    # tangents, NOT the sketch-on-face u/v -- mark uncalibrated so
    # _sketch_uv_to_part refuses a child sketch on this face.
    axis_hat = (ax, ay, az)
    return FaceFrame(
        face_center=face_center,
        sketch_origin=sketch_origin,
        u_axis=axis_hat,
        v_axis=in_plane_v,
        out_normal=out_nrm,
        uv_calibrated=False,
    )


def _sketch_uv_to_part(
    frame: FaceFrame, u_m: float, v_m: float
) -> tuple[float, float, float]:
    """Convert sketch-frame (u, v) in meters to part-frame (x, y, z).

    Origin is `frame.sketch_origin` (where SW puts the sketch's (0,0)),
    NOT `frame.face_center`. For +/-z faces they coincide; for side faces
    sketch_origin sits on the face's bottom edge (z=0 in part frame for
    a block on Front Plane).

    Refuses an uncalibrated frame (a side face of a Top/Right-plane parent):
    face_center + normal are known there, but the sketch u/v are not yet
    calibrated for placing a child sketch.
    """
    if not frame.uv_calibrated:
        raise RuntimeError(
            "sketch-on-face on a side face (+/-x, +/-y) of a Top/Right-plane "
            "(±x/±y-axis) parent is not yet supported: only the face center "
            "and normal are calibrated (enough for fillet/chamfer edge "
            "selection, not for placing a child sketch). Use a Front-plane "
            "parent for sketch-on-side-face, or address this face via +/-z on "
            "a child extrude. Tracked: _face_frame ±x/±y sketch-frame "
            "calibration."
        )
    cx, cy, cz = frame.sketch_origin
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    return (
        cx + u_m * ux + v_m * vx,
        cy + u_m * uy + v_m * vy,
        cz + u_m * uz + v_m * vz,
    )


def _warn_face_sketch_offset(
    parent: BuiltFeature,
    face: str,
    feat: dict[str, Any],
    in_face_keys: tuple[str, str],
) -> None:
    """Emit a one-line stderr warning when the user's face-sketch will
    land at the part-origin projection rather than the face centroid.

    Triggers when:
      - parent face center (in part frame) has a meaningful in-face
        component (>0.1 mm) -- i.e. the face doesn't sit on the part
        origin's projection along the face normal, AND
      - the spec's `center` field is missing or zero (no explicit shift)

    The warning includes the in-face offset (in sketch u/v) the user
    would need to add to put the child feature at the face centroid.
    This is the #1 source of "wrong-position child feature" bugs
    surfaced in the TensionBracket work; see docs/known_limitations.md.
    """
    import sys

    frame = _face_frame(parent, face)
    # Uncalibrated side faces (Top/Right parents) can't place a child sketch at
    # all -- _sketch_uv_to_part will raise -- so the offset advice is moot.
    if not frame.uv_calibrated:
        return
    fx, fy, fz = frame.face_center
    # Project the face-center vector onto the sketch u/v axes to get the
    # in-face offset of the face center from the part-origin projection.
    # u = (face_center - 0) . u_axis ; v likewise.
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    tu_mm = (fx * ux + fy * uy + fz * uz) * 1000.0
    tv_mm = (fx * vx + fy * vy + fz * vz) * 1000.0

    # If face is centered on origin (within 0.1 mm), no warning needed.
    if abs(tu_mm) < 0.1 and abs(tv_mm) < 0.1:
        return

    # If user explicitly set a center offset, assume they know what they're
    # doing and don't second-guess. We don't try to validate whether the
    # offset they picked matches the face center -- that's a richer check
    # than this warning is meant to do.
    center = feat.get("center", {})
    u_key, v_key = in_face_keys
    cu = float(center.get(u_key, 0.0))
    cv = float(center.get(v_key, 0.0))
    if abs(cu) > 0.001 or abs(cv) > 0.001:
        return

    print(
        f"WARNING: {feat['type']} '{feat['name']}' on parent "
        f"'{parent.name}' face {face}: parent face center is at "
        f"part-frame ({tu_mm:+.2f}, {tv_mm:+.2f}) mm, but the face-sketch "
        f"origin lands at (0, 0) (part-origin projection). The child "
        f"feature will be drawn relative to (0, 0), NOT the face center. "
        f"If you want it centered on the face, add "
        f'`"center": {{"{u_key}": {tu_mm:.2f}, "{v_key}": {tv_mm:.2f}}}` '
        f"to the spec entry. See docs/known_limitations.md section 1.",
        file=sys.stderr,
    )


def _select_extrude_face(
    ctx: BuildContext,
    parent: BuiltFeature,
    face: str,
) -> tuple[bool, float, float, float]:
    """Select one of the 6 faces of an extrusion (+z, -z, +x, -x, +y, -y).

    Uses _face_frame to find the face center and in-face tangent axes.
    Tries the face center first; if that fails (e.g. earlier cut removed
    material at the center), spirals outward in the face's tangent plane
    until one offset hits material. Returns (ok, fx, fy, fz) where the
    coords are the point on the face that successfully selected (used
    downstream as the sketch origin reference for stacked extrudes).

    SelectByID("", "FACE", x, y, z) is unreliable on side faces of a
    multi-boss part: it can return True while picking a DIFFERENT face
    than the one geometrically at (x, y, z) -- empirically observed when
    the part has multiple recently-modified faces sharing screen-space
    proximity. We verify by querying IFace2.Normal after each pick and
    rejecting any face whose normal doesn't match `frame.out_normal`.
    On rejection, fall back to enumerating body faces and selecting via
    IEntity.Select2 (no Callout, late-binding-safe).
    """
    frame = _face_frame(parent, face)
    fx0, fy0, fz0 = frame.face_center
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    nx_e, ny_e, nz_e = frame.out_normal

    def _matches_expected(face_obj: Any) -> bool:
        try:
            n = face_obj.Normal
            return (
                abs(n[0] - nx_e) < 0.1
                and abs(n[1] - ny_e) < 0.1
                and abs(n[2] - nz_e) < 0.1
            )
        except Exception:
            return False

    # Spiral of (du, dv) offsets in the face's local sketch frame. Each
    # (du, dv) is projected to part coords via the frame's u/v axes.
    # Distances chosen to handle small interior holes (1mm) up to large
    # voids (15mm). Worst case: spec asks for a face entirely consumed
    # by prior features -- raise on caller side.
    offsets_uv = [
        (0, 0),
        (0.001, 0),
        (0, 0.001),
        (-0.001, 0),
        (0, -0.001),
        (0.005, 0),
        (0, 0.005),
        (-0.005, 0),
        (0, -0.005),
        (0.015, 0),
        (0, 0.015),
        (-0.015, 0),
        (0, -0.015),
        (0.005, 0.005),
        (-0.005, -0.005),
        (0.015, 0.015),
        (-0.015, -0.015),
    ]
    for du, dv in offsets_uv:
        fx = fx0 + du * ux + dv * vx
        fy = fy0 + du * uy + dv * vy
        fz = fz0 + du * uz + dv * vz
        ctx.doc.ClearSelection2(True)
        if ctx.doc.SelectByID("", "FACE", fx, fy, fz):
            face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
            if _matches_expected(face_obj):
                return True, fx, fy, fz
            # Wrong face picked. Clear and keep trying other offsets;
            # may pick the right one. (e.g. a SelectByID at face-center
            # may hit a screen-occluding face but an off-center probe
            # lands on the intended face.)

    # SelectByID spiral exhausted. Fall back to body-face enumeration:
    # find the face whose normal matches frame.out_normal AND whose
    # closest point to (fx0, fy0, fz0) is within 1um. Then select via
    # IEntity.Select2 (no Callout arg, late-binding-safe).
    try:
        bodies = ctx.doc.GetBodies2(0, True)  # swSolidBody=0
    except Exception:
        return False, fx0, fy0, fz0
    for body in bodies:
        faces = body.GetFaces()
        if faces is None:
            continue
        for face_obj in faces:
            if not _matches_expected(face_obj):
                continue
            try:
                cp = face_obj.GetClosestPointOn(fx0, fy0, fz0)
            except Exception:
                continue
            if cp is None or len(cp) < 3:
                continue
            d2 = (cp[0] - fx0) ** 2 + (cp[1] - fy0) ** 2 + (cp[2] - fz0) ** 2
            if d2 > 1e-12:  # >1 micron away
                continue
            ctx.doc.ClearSelection2(True)
            if face_obj.Select2(False, 0):
                return True, cp[0], cp[1], cp[2]

    return False, fx0, fy0, fz0


def _resolve_face_object(ctx: BuildContext, parent: BuiltFeature, face: str) -> Any:
    """Return the live ``IFace2`` for a semantic face name of an extrusion.

    Reuses :func:`_select_extrude_face` (the normal-verified spiral + body-face
    enumeration probe) to select the face, then reads it back via
    ``GetSelectedObject6(1, -1)`` -- the same idiom ``_build_simple_hole`` uses
    (builder.py). Used by the semantic edge selectors (``of_face`` /
    ``between_faces``) to walk to the face's bounding edges.

    Note: ``_select_extrude_face`` clears the selection internally, so callers
    resolving more than one face must read each face object back IMMEDIATELY and
    build their incidence map in Python BEFORE any edge selection -- never rely
    on the selection set persisting across resolves.

    Raises RuntimeError if the face cannot be resolved.
    """
    ok, _fx, _fy, _fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"could not resolve {face} face of '{parent.name}' "
            f"(no body face matched the expected normal/position)"
        )
    face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
    if face_obj is None:
        raise RuntimeError(
            f"resolved {face} face of '{parent.name}' but GetSelectedObject6 "
            f"returned None"
        )
    return face_obj


def _face_edge_objects(face_obj: Any) -> list:
    """The ``IEdge`` objects bounding a face via ``IFace2.GetEdges``.

    ``GetEdges`` is a return-array (the proven-class analog of the body-level
    ``IBody2.GetEdges`` used in builder.py), so it is wrapped with the same
    callable-or-property guard. The caller MUST keep both the returned edges and
    their parent ``face_obj`` alive until selection completes (the W67 IEdge
    COM-lifetime trap: an IEdge invalidates when its parent proxy is released).
    """
    raw = face_obj.GetEdges
    if callable(raw):
        raw = raw()
    return list(raw or ())
