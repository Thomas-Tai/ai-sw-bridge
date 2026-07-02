"""Hole-family handler, relocated from builder.py (Phase 3 Move 3).

`_build_simple_hole` is self-contained: it uses the `_face_geometry` leaf
(`_select_extrude_face`, `_face_frame`, `_sketch_uv_to_part`,
`_warn_face_sketch_offset`) plus raw `ctx.doc` COM calls -- no builder-local
shared helper. Leaf module: imports only `.._build_context`,
`.._face_geometry`, `.._sketch_primitives`, and `...sw_types` -- never
builder.py or a sibling handler module.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from .._face_geometry import (
    _face_frame,
    _select_extrude_face,
    _sketch_uv_to_part,
    _warn_face_sketch_offset,
)
from .._sketch_primitives import PLACEHOLDER_MM, _literal_or_default
from ...sw_types import SW_END_COND_BLIND, SW_END_COND_THROUGH_ALL, assert_args


def _build_simple_hole(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Drill a straight-bore hole through an existing face.

    No sketch needed -- the (u, v) center positions the hole on the face,
    and the hole is automatically normal to that face. Uses
    IFeatureManager.SimpleHole2 (23 args, SW 2017+). Selection state on
    entry: just the FACE, selected at the desired hole-center point
    (SimpleHole2 uses the SelectByID hit point as the hole center).

    Pre-fix attempt (Spike W) tried also pre-selecting a SKETCHPOINT but
    SimpleHole2 returned None. The simpler "face only, picked at the
    hole center" approach works and matches what the SW UI does
    internally.
    """
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"simple_hole: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    face = feat["face"]
    _warn_face_sketch_offset(parent, face, feat, ("u", "v"))
    _frame = _face_frame(parent, face)

    # Compute the hole's intended (u, v) in sketch coords, then transform
    # to part-frame for SelectByID. We want the face-select to hit at the
    # hole center (not just somewhere on the face) because SimpleHole2
    # uses the pick point as the hole position.
    c = feat.get("center", {})
    u_m = float(c.get("u", 0.0)) / 1000.0
    v_m = float(c.get("v", 0.0)) / 1000.0
    px, py, pz = _sketch_uv_to_part(_frame, u_m, v_m)

    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID("", "FACE", px, py, pz)
    if not ok:
        # Fall back to the same normal-verified spiral _select_extrude_face
        # uses, then re-pick exactly at the hole center via the body face.
        # Most parts only need the direct pick.
        ok2, _, _, _ = _select_extrude_face(ctx, parent, face)
        if not ok2:
            raise RuntimeError(
                f"simple_hole '{feat['name']}': could not select {face} face "
                f"of '{parent_name}' at hole center "
                f"({px*1000:.2f}, {py*1000:.2f}, {pz*1000:.2f}) mm"
            )
        # _select_extrude_face leaves a face selected, but possibly at the
        # face center (not the hole center). Re-pick at the hole center
        # since SimpleHole2 needs the position.
        ctx.doc.ClearSelection2(True)
        if not ctx.doc.SelectByID("", "FACE", px, py, pz):
            raise RuntimeError(
                f"simple_hole '{feat['name']}': SelectByID('','FACE',...) "
                f"at hole center failed even after _select_extrude_face "
                f"confirmed face existence"
            )

    # Verify the selected face has the expected normal -- guards against
    # the same multi-boss face-pick gotcha _select_extrude_face guards.
    face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
    try:
        n = face_obj.Normal
        nx_e, ny_e, nz_e = _frame.out_normal
        if not (
            abs(n[0] - nx_e) < 0.1 and abs(n[1] - ny_e) < 0.1 and abs(n[2] - nz_e) < 0.1
        ):
            raise RuntimeError(
                f"simple_hole '{feat['name']}': SelectByID picked a face with "
                f"normal ({n[0]:+.2f},{n[1]:+.2f},{n[2]:+.2f}) but expected "
                f"({nx_e:+.2f},{ny_e:+.2f},{nz_e:+.2f}) for {face} face"
            )
    except AttributeError:
        # If the selected object doesn't have .Normal we can't verify;
        # let SimpleHole2 fail naturally if the wrong thing is selected.
        pass

    diameter_m = _literal_or_default(feat["diameter"], PLACEHOLDER_MM["hole_diameter"])
    end_condition = feat.get("end_condition", "blind")
    if end_condition == "blind":
        depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["hole_depth"])
        end_cond = SW_END_COND_BLIND
    else:  # through_all
        depth_m = 0.0
        end_cond = SW_END_COND_THROUGH_ALL

    fm = ctx.doc.FeatureManager
    args = (
        diameter_m,  # 1  Dia
        True,  # 2  Sd
        False,  # 3  Flip
        False,  # 4  Dir
        end_cond,  # 5  T1
        0,  # 6  T2
        depth_m,  # 7  D1
        0.0,  # 8  D2
        False,  # 9  Dchk1
        False,  # 10 Dchk2
        False,  # 11 Ddir1
        False,  # 12 Ddir2
        0.0,  # 13 Dang1
        0.0,  # 14 Dang2
        False,  # 15 OffsetReverse1
        False,  # 16 OffsetReverse2
        False,  # 17 TranslateSurface1
        False,  # 18 TranslateSurface2
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        False,  # 21 AssemblyFeatureScope
        False,  # 22 AutoSelectComponents
        False,  # 23 PropagateFeatureToParts
    )
    assert_args("IFeatureManager.SimpleHole2", args)
    f = fm.SimpleHole2(*args)
    if f is None:
        raise RuntimeError(
            f"simple_hole '{feat['name']}': SimpleHole2 returned None "
            f"(face={face}, hole-center=({px*1000:.2f},{py*1000:.2f},"
            f"{pz*1000:.2f})mm, dia={diameter_m*1000:.2f}mm)"
        )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)
