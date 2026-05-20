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

    # ±x, ±y faces: side faces. Only supported when parent axis is +/-z
    # (Front Plane parent) AND the parent profile has known half-extents
    # (rectangle, not circle).
    if abs(az) < 0.99:
        raise RuntimeError(
            f"side face '{face}' of '{parent.name}': v1 only supports +/-x "
            f"and +/-y side faces when the parent extrude axis is +/-z "
            f"(Front Plane). Parent's axis is ({ax:+.2f}, {ay:+.2f}, "
            f"{az:+.2f}). Use a Front-Plane sketch parent for side-face "
            f"work, or address the side face via +/-z on a child extrude."
        )
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

    # extrude_origin records the sketch's center in part-frame (X, Y) for
    # +z-axis parents. So:
    #   +x side face plane: x = ox + half_u
    #   -x side face plane: x = ox - half_u
    #   +y side face plane: y = oy + half_v
    #   -y side face plane: y = oy - half_v
    # Face-center along the extrude axis: midway through the extrude depth.
    z_mid = oz + 0.5 * az * depth
    if face == "+x":
        face_center = (ox + half_u, oy, z_mid)
        out_nrm = (1.0, 0.0, 0.0)
    elif face == "-x":
        face_center = (ox - half_u, oy, z_mid)
        out_nrm = (-1.0, 0.0, 0.0)
    elif face == "+y":
        face_center = (ox, oy + half_v, z_mid)
        out_nrm = (0.0, 1.0, 0.0)
    elif face == "-y":
        face_center = (ox, oy - half_v, z_mid)
        out_nrm = (0.0, -1.0, 0.0)
    else:
        raise RuntimeError(f"unknown face label {face!r}")

    u_ax, v_ax = _FACE_UV_AXES_PARENT_PLUSZ[face]
    # Side face sketch_origin: SW projects part origin (0,0,0) onto the
    # face plane. The face plane equation is `face_center . out_normal = d`
    # where d = face_center . out_normal (the signed distance from origin
    # to the face plane along the normal). Projection of (0,0,0) onto the
    # plane is then `d * out_normal`. For axis-aligned faces this reduces
    # to setting the normal-component to face_center's normal-component
    # and zeroing the in-face components.
    nx, ny, nz = out_nrm
    d = face_center[0] * nx + face_center[1] * ny + face_center[2] * nz
    sketch_origin = (d * nx, d * ny, d * nz)
    return FaceFrame(
        face_center=face_center,
        sketch_origin=sketch_origin,
        u_axis=(float(u_ax[0]), float(u_ax[1]), float(u_ax[2])),
        v_axis=(float(v_ax[0]), float(v_ax[1]), float(v_ax[2])),
        out_normal=out_nrm,
    )


def _sketch_uv_to_part(
    frame: FaceFrame, u_m: float, v_m: float
) -> tuple[float, float, float]:
    """Convert sketch-frame (u, v) in meters to part-frame (x, y, z).

    Origin is `frame.sketch_origin` (where SW puts the sketch's (0,0)),
    NOT `frame.face_center`. For +/-z faces they coincide; for side faces
    sketch_origin sits on the face's bottom edge (z=0 in part frame for
    a block on Front Plane).
    """
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
