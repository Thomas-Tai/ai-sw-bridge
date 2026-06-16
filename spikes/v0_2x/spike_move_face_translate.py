"""W59 / #9 — face-translation spike (InsertMoveFace3 escape hatch).

PIVOT from InsertMoveCopyBody2 (WALLED W58 — COM boundary silently drops
the body-pointer SAFEARRAY; CreateDefinition(swFmMoveCopyBody) QIs
E_NOINTERFACE).  This spike proves the SURFACE-TOPOLOGY route:
IFeatureManager.InsertMoveFace3 (move the face TOPOLOGY, not the body
memory block).

O1 introspection (NEVER guess — the gear=10-not-12 trap):
    Phase A  dump FUNCDESC for InsertMoveFace3 from sldworks.tlb →
             full param VT + names (signature only, NOT enum values).
    Phase B  dump VARDESC for swMoveFaceType_e from swconst.tlb →
             the REAL translate enum value (not the RAG-guessed "2").

Fixture:  50 × 50 × 50 mm extruded block (centered on origin, Front Plane).
Selection: ALL 6 faces via SelectByID2("","FACE", x, y, z) at bbox-derived
           face centres.  NOT the solid body.
Operation: InsertMoveFace3 pure translation → +30 mm along X.
Verify-the-EFFECT: GetPartBox before/after → per-axis bbox delta + ΔVol.
    PASS   = rigid +30 mm X-shift with ΔVol ≈ 0.
    DEFORM = nonzero ΔVol or off-axis delta.
    Assert survival across save → CloseAllDocuments → reopen.

Fallback: if InsertMoveFace3 deforms, the sketch-offset transform route
is characterized in the same spike (open sketch on a face, offset edges,
blind extrude the offset region by 30 mm, measure).

Constraints:
    CloseAllDocuments(True) in finally, NEVER CloseDoc (R2).
    No makepy regen; no live GetTypeInfo.
    No Co-Authored-By trailers.

Exit codes: 0 = RIGID PASS, 2 = DEFORM (with data), 1 = FAIL.
Output: JSON to stdout, human-readable to stderr.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_move_face_translate.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "move_face_translate.json"

SLDWORKS_TLB = Path(
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
)
SWCONST_TLB = Path(
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb"
)

SW_DEFAULT_TEMPLATE_PART = 8

BOX_SIZE_M = 0.050
TRANSLATE_DX_M = 0.030

VT_MAP = {
    0: "VT_EMPTY", 2: "VT_I2", 3: "VT_I4", 4: "VT_R4", 5: "VT_R8",
    6: "VT_CY", 7: "VT_DATE", 8: "VT_BSTR", 9: "VT_DISPATCH",
    10: "VT_ERROR", 11: "VT_BOOL", 12: "VT_VARIANT", 13: "VT_UNKNOWN",
    16: "VT_I1", 17: "VT_UI1", 18: "VT_UI2", 19: "VT_UI4",
    22: "VT_INT", 23: "VT_UINT", 24: "VT_VOID", 26: "VT_LPSTR",
}
INVKIND_NAMES = {
    1: "FUNCTION", 2: "PROPERTYGET", 4: "PROPERTYPUT", 8: "PROPERTYPUTREF",
}


def _vt_str(vt: int) -> str:
    base = vt & 0xFFF
    array = bool(vt & 0x2000)
    byref = bool(vt & 0x4000)
    name = VT_MAP.get(base, f"VT_{base}")
    s = name
    if array:
        s += "[]"
    if byref:
        s += "*"
    return s


def _decode_tdesc(tdesc: Any) -> str:
    if tdesc is None:
        return "None"
    if isinstance(tdesc, (tuple, list)):
        vt = tdesc[0] if tdesc else 0
        if isinstance(vt, (tuple, list)):
            return f"PTR({_decode_tdesc(vt)})"
        return _vt_str(int(vt))
    return str(tdesc)


def _decode_param_flags(flags: int) -> str:
    parts = []
    if flags & 0x1:
        parts.append("IN")
    if flags & 0x2:
        parts.append("OUT")
    if flags & 0x4:
        parts.append("LCID")
    if flags & 0x8:
        parts.append("RETVAL")
    if flags & 0x10:
        parts.append("OPT")
    if flags & 0x40:
        parts.append("HASDEFAULT")
    return "|".join(parts) if parts else "none"


# ── Phase A: FUNCDESC walk — InsertMoveFace3 signature ────────────────


def _walk_insert_move_face3(tlb: Any) -> dict[str, Any]:
    """Dump InsertMoveFace3 FUNCDESC from sldworks.tlb."""
    focus_ifaces = ("IFeatureManager", "IPartDoc", "IModelDoc2")
    report: dict[str, Any] = {"interfaces": {}}

    n = tlb.GetTypeInfoCount()
    for i in range(n):
        name, *_ = tlb.GetDocumentation(i)
        if name not in focus_ifaces:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        matching: list[dict[str, Any]] = []

        for f_idx in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f_idx)
                memid = fd.memid
                names = info.GetNames(memid)
                if not names:
                    continue
                mname = names[0]
                if "moveface" not in mname.lower():
                    continue

                param_names = list(names[1:]) if len(names) > 1 else []
                params: list[dict[str, Any]] = []
                for p_idx in range(len(fd.args) if fd.args else 0):
                    p_name = (
                        param_names[p_idx]
                        if p_idx < len(param_names)
                        else f"p{p_idx}"
                    )
                    if fd.args and p_idx < len(fd.args):
                        arg = fd.args[p_idx]
                        tdesc = arg[0] if arg else None
                        flags = int(arg[1]) if arg and len(arg) > 1 else 0
                        default = arg[2] if arg and len(arg) > 2 else None
                        params.append({
                            "name": p_name,
                            "type": _decode_tdesc(tdesc),
                            "flags": _decode_param_flags(flags),
                            "default": default,
                        })
                    else:
                        params.append({"name": p_name, "type": "unknown"})

                # PyFUNCDESC has no `elemdescFunc`; the return ELEMDESC is
                # `rettype` (a tuple, [0]=tdesc — same shape as args[i]).
                ret_type = (
                    _decode_tdesc(fd.rettype[0])
                    if isinstance(fd.rettype, tuple) else "unknown"
                )
                invkind = INVKIND_NAMES.get(fd.invkind, str(fd.invkind))

                matching.append({
                    "name": mname,
                    "memid": memid,
                    "invkind": invkind,
                    "cParams": (len(fd.args) if fd.args else 0),
                    "return_type": ret_type,
                    "params": params,
                })
            except Exception as exc:
                matching.append({"error": f"f_idx={f_idx}: {exc!r}"})

        if matching:
            report["interfaces"][name] = matching

    return report


# ── Phase B: VARDESC walk — swMoveFaceType_e enum ─────────────────────


def _walk_swconst_move_face_type() -> dict[str, Any]:
    """Dump ALL swMoveFaceType_e members from swconst.tlb."""
    report: dict[str, Any] = {"path": str(SWCONST_TLB), "loadable": False}
    if not SWCONST_TLB.exists():
        report["error"] = f"not found at {SWCONST_TLB}"
        return report
    try:
        tlb = __import__("pythoncom").LoadTypeLib(str(SWCONST_TLB))
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True
    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if name == "swMoveFaceType_e":
            info = tlb.GetTypeInfo(i)
            ta = info.GetTypeAttr()
            for v in range(ta.cVars):
                vd = info.GetVarDesc(v)
                mname = info.GetNames(vd.memid)[0]
                report[mname] = vd.value
    return report


# ── Geometry helpers ──────────────────────────────────────────────────


def _sketch_rect(doc: Any, w: float, h: float) -> None:
    """Sketch a w×h centred rectangle on Front Plane."""
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-w / 2, -h / 2, 0.0, w / 2, h / 2, 0.0)
    sk.InsertSketch(True)


def _extrude(doc: Any, depth_m: float) -> Any:
    fm = doc.FeatureManager
    return fm.FeatureExtrusion3(
        True, False, False,
        0, 0,
        depth_m, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0, 0,
        False,
    )


def _build_fixture(sw: Any) -> dict[str, Any]:
    """Create a new Part and build the 50 mm cube fixture."""
    out: dict[str, Any] = {}
    try:
        template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument returned None"
            return out
        _sketch_rect(doc, BOX_SIZE_M, BOX_SIZE_M)
        feat = _extrude(doc, BOX_SIZE_M)
        if feat is None or isinstance(feat, int):
            out["error"] = "extrude did not materialize"
            return out
        doc.ForceRebuild3(False)
        out["doc"] = doc
        out["built"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _get_bbox(doc: Any) -> list[float] | None:
    """GetPartBox(True) → [xMin, yMin, zMin, xMax, yMax, zMax] in metres."""
    try:
        bb = doc.GetPartBox(True)
        if bb is None:
            return None
        return [float(v) for v in bb]
    except Exception:
        return None


def _get_volume(doc: Any) -> float | None:
    """Sum solid-body volumes via GetBodies2 + IBody2.GetMassProperties.

    Proven recipe (hem PAE): ``IBody2.GetMassProperties(1.0)`` returns an
    array whose index 3 is the volume in m³ (the W1 draft used a non-existent
    ``GetMassProperties2(0)[2]`` -> null). m³ matches the 1e-12 vol threshold.
    """
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies is None:
            return None
        total = 0.0
        for b in (bodies if isinstance(bodies, (list, tuple)) else [bodies]):
            try:
                mp = b.GetMassProperties(1.0)
                if mp and len(mp) > 3:
                    total += float(mp[3])
            except Exception:
                continue
        return total if total > 0 else None
    except Exception:
        return None


def _bbox_vol(bb: list[float]) -> float:
    dx = bb[3] - bb[0]
    dy = bb[4] - bb[1]
    dz = bb[5] - bb[2]
    return abs(dx * dy * dz)


def _bbox_deltas(
    before: list[float], after: list[float],
) -> dict[str, float]:
    return {
        "dx_min_m": after[0] - before[0],
        "dy_min_m": after[1] - before[1],
        "dz_min_m": after[2] - before[2],
        "dx_max_m": after[3] - before[3],
        "dy_max_m": after[4] - before[4],
        "dz_max_m": after[5] - before[5],
    }


def _face_centres_from_bbox(
    bb: list[float],
) -> dict[str, tuple[float, float, float]]:
    """Compute 6 axis-aligned face centres from a bounding box."""
    x0, y0, z0, x1, y1, z1 = bb
    xm, ym, zm = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    return {
        "front": (xm, ym, z1),
        "back": (xm, ym, z0),
        "right": (x1, ym, zm),
        "left": (x0, ym, zm),
        "top": (xm, y1, zm),
        "bottom": (xm, y0, zm),
    }


def _select_faces(doc: Any) -> dict[str, Any]:
    """Select ALL faces of the body via the PROVEN headless method.

    ``body.GetFaces()`` → ``typed(face, "IEntity").Select2(append, 0)``.
    The draft's coordinate ``SelectByID2("","FACE",x,y,z)`` resolves but
    returns False out-of-process (no graphics-area pick context); the
    GetFaces + early-bound IEntity.Select2 path needs neither coordinates
    nor a view (the hem-spike-proven selection recipe). First face
    append=False (replace), the rest append=True (add to selection).
    """
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    mod = wrapper_module()

    # SINGLE +X FACE: moving ALL faces is degenerate (no reference geometry
    # -> kernel no-op). Moving only the +X face is a valid move-face: if it
    # works the +X face shifts +30mm and volume grows (~+75000 mm3), proving
    # InsertMoveFace3 RESHAPES (not a rigid body-translation bypass); if it
    # still no-ops it is a true API wall.
    part_bb = _get_bbox(doc)
    if part_bb is None:
        return {"error": "part bbox unreadable", "selected_count": 0}
    part_xmax = part_bb[3]

    try:
        bodies = doc.GetBodies2(0, True)
    except Exception as exc:
        return {"error": f"GetBodies2 failed: {exc!r}", "selected_count": 0}
    body_list = (
        list(bodies) if isinstance(bodies, (list, tuple))
        else [bodies] if bodies else []
    )
    if not body_list:
        return {"error": "no solid bodies", "selected_count": 0}

    try:
        faces = body_list[0].GetFaces()
    except Exception as exc:
        return {"error": f"GetFaces failed: {exc!r}", "selected_count": 0}
    face_list = (
        list(faces) if isinstance(faces, (list, tuple))
        else [faces] if faces else []
    )

    target = None
    detail: list[dict[str, Any]] = []
    for i, f in enumerate(face_list):
        try:
            gb = f.GetBox
            box = [float(v) for v in (gb() if callable(gb) else gb)]
            is_plus_x = (abs(box[0] - part_xmax) < 1e-4
                         and abs(box[3] - part_xmax) < 1e-4)
            detail.append({"face_idx": i, "box_x": [box[0], box[3]],
                           "is_plus_x": is_plus_x})
            if is_plus_x and target is None:
                target = f
        except Exception as exc:
            detail.append({"face_idx": i,
                           "exception": f"{type(exc).__name__}: {exc!r}"[:120]})

    if target is None:
        return {"error": "could not identify +X face", "selected_count": 0,
                "face_count": len(face_list), "detail": detail}

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        ok = bool(typed(target, "IEntity", module=mod).Select2(False, 0))
    except Exception as exc:
        return {"error": f"Select2 failed: {exc!r}", "selected_count": 0,
                "detail": detail}
    return {"selected_count": 1 if ok else 0, "face_count": len(face_list),
            "target": "+X face", "detail": detail}


# ── InsertMoveFace3 call builder ──────────────────────────────────────


def _build_imf3_args(
    sig: dict[str, Any], move_type_val: int,
) -> list[Any]:
    """Build positional args for a TRANSLATE ``InsertMoveFace3`` call.

    Keys off the FUNCDESC-verified param NAMES (not VT-position guessing).
    Real signature (sldworks.tlb, seat-confirmed 2026-06-16)::

        MoveType:VT_I4  ReverseDir:VT_BOOL  Angle:VT_R8  Distance:VT_R8
        TranslationParams:VT_VARIANT  RotationParams:VT_VARIANT
        EndConditionType:VT_I4  OffsetDistance:VT_R8

    For a pure translate, the [dx,dy,dz] vector is the payload and goes into
    ``TranslationParams`` as a SAFEARRAY-of-R8 VARIANT (constraint: +30mm X =
    ``[0.03, 0, 0]``); Angle/Distance/OffsetDistance stay 0 and the rotate
    slot is a neutral empty VARIANT. (The old VT-position builder mis-assigned
    the X delta to ``Angle`` and passed ``0`` for the variant block.)
    """
    import pythoncom
    from win32com.client import VARIANT

    # Map by the FUNCDESC-verified param NAMES. _decode_tdesc renders the VT
    # as a raw-int string ("11"/"3"/"5"), NOT "VT_BOOL"/"VT_I4"/"VT_R8", so
    # VT-substring matching silently falls through to the default (the bug
    # that wrapped every scalar as VT_EMPTY → SW no-op). Names are exact.
    by_name: dict[str, Any] = {
        "movetype": move_type_val,                                  # I4 (1=translate)
        "reversedir": False,                                        # BOOL
        "angle": 0.0,                                               # R8 (rotate only)
        "distance": 0.0,                                            # R8
        "translationparams": VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                     [TRANSLATE_DX_M, 0.0, 0.0]),    # +30 mm X vector
        "rotationparams": VARIANT(pythoncom.VT_EMPTY, None),        # unused for translate
        "endconditiontype": 0,                                      # I4
        "offsetdistance": 0.0,                                      # R8
    }
    args: list[Any] = []
    for p in sig.get("params", []):
        args.append(by_name.get(p.get("name", "").lower(), 0))
    return args


# ── Main probes ───────────────────────────────────────────────────────


def _probe_move_face(
    doc: Any, sig: dict[str, Any], move_type_val: int,
) -> dict[str, Any]:
    """Call InsertMoveFace3 with verified args and measure the effect."""
    out: dict[str, Any] = {}
    fm = doc.FeatureManager

    args = _build_imf3_args(sig, move_type_val)
    out["args"] = args
    out["arg_count"] = len(args)
    out["expected_cParams"] = sig.get("cParams")

    t0 = time.perf_counter()
    try:
        ret = fm.InsertMoveFace3(*args)
        elapsed = (time.perf_counter() - t0) * 1000.0
        out["call_ok"] = True
        out["return"] = str(ret)[:200] if ret is not None else None
        out["return_type"] = type(ret).__name__
        out["elapsed_ms"] = round(elapsed, 2)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        out["call_ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc!r}"
        out["hresult"] = (
            f"{exc.hresult:#010x}" if hasattr(exc, "hresult") else None
        )
        out["elapsed_ms"] = round(elapsed, 2)

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    return out


def _save_reopen(sw: Any, doc: Any) -> dict[str, Any]:
    """SaveAs3 → CloseAllDocuments → OpenDoc6 → ForceRebuild3.

    Uses CloseAllDocuments (NEVER CloseDoc mid-session — R2).
    """
    out: dict[str, Any] = {}
    tmp = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp.mkdir(parents=True, exist_ok=True)
    save_path = str(tmp / "spike_move_face_translate.sldprt")

    try:
        ret = doc.SaveAs3(save_path, 0, 2)
        out["save_ok"] = True
        out["path"] = save_path
    except Exception as exc:
        out["save_ok"] = False
        out["save_error"] = f"{type(exc).__name__}: {exc!r}"
        return out

    try:
        sw.CloseAllDocuments(True)
        reopened = sw.OpenDoc6(save_path, 1, 0, "", 0, 0)
        if reopened is None:
            reopened = sw.OpenDoc6(save_path, 1, 0, "")
        if reopened is None:
            out["reopen_ok"] = False
            out["reopen_error"] = "OpenDoc6 returned None"
            return out
        reopened.ForceRebuild3(False)
        out["reopen_ok"] = True
        out["doc"] = reopened
    except Exception as exc:
        out["reopen_ok"] = False
        out["reopen_error"] = f"{type(exc).__name__}: {exc!r}"
    return out


def _fallback_sketch_offset(doc: Any) -> dict[str, Any]:
    """Sketch-offset transform escape hatch.

    1. Read bbox to locate the +X face centre.
    2. Select that face, open sketch, draw an offset rectangle
       (inset 5 mm from the face edges).
    3. Close sketch → blind extrude the offset region by +30 mm.
    4. Re-measure bbox + volume → report deltas.

    This is a SEPARATE characterization route: it proves body-shape
    modification via the sketch-offset → extrude pathway, not via
    InsertMoveFace3.
    """
    out: dict[str, Any] = {}
    bb = _get_bbox(doc)
    if bb is None:
        out["error"] = "bbox unreadable"
        return out

    before_vol = _get_volume(doc)
    out["before"] = {"bbox": bb, "volume_mm3": before_vol}

    x0, y0, z0, x1, y1, z1 = bb
    xm, ym, zm = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    inset = 0.005

    doc.ClearSelection2(True)
    try:
        ok = doc.SelectByID2("", "FACE", x1, ym, zm, False, 0, None, 0)
        out["face_select"] = ok
    except Exception as exc:
        out["face_select_error"] = f"{type(exc).__name__}: {exc!r}"
        return out

    sk = doc.SketchManager
    try:
        sk.InsertSketch(True)
        hw = (y1 - y0) / 2 - inset
        hh = (z1 - z0) / 2 - inset
        sk.CreateCornerRectangle(-hw, -hh, 0.0, hw, hh, 0.0)
        sk.InsertSketch(True)
    except Exception as exc:
        out["sketch_error"] = f"{type(exc).__name__}: {exc!r}"
        return out

    try:
        feat = doc.FeatureManager.FeatureExtrusion3(
            True, False, False,
            0, 0,
            TRANSLATE_DX_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0,
            False,
        )
        out["extrude_return"] = type(feat).__name__
    except Exception as exc:
        out["extrude_error"] = f"{type(exc).__name__}: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    after_bb = _get_bbox(doc)
    after_vol = _get_volume(doc)
    out["after"] = {"bbox": after_bb, "volume_mm3": after_vol}
    if bb and after_bb:
        out["bbox_delta"] = _bbox_deltas(bb, after_bb)
    if before_vol is not None and after_vol is not None:
        out["delta_vol_mm3"] = after_vol - before_vol
    out["offset_inset_mm"] = inset * 1000
    return out


# ── Top-level orchestration ───────────────────────────────────────────


def run() -> dict[str, Any]:
    output: dict[str, Any] = {
        "spike": "W59_move_face_translate",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "route": "InsertMoveFace3 (surface topology)",
        "overall": "UNKNOWN",
    }

    import pythoncom
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        tlb = pythoncom.LoadTypeLib(str(SLDWORKS_TLB))
        output["sldworks_tlb"] = {"loadable": True, "path": str(SLDWORKS_TLB)}
    except Exception as exc:
        output["sldworks_tlb"] = {
            "loadable": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        output["overall"] = "FAIL"
        return output

    sig_report = _walk_insert_move_face3(tlb)
    output["funcdesc"] = sig_report

    sig: dict[str, Any] = {}
    for iface_name, members in sig_report.get("interfaces", {}).items():
        for m in members:
            if m.get("name") == "InsertMoveFace3":
                sig = {**m, "interface": iface_name}
                break
        if sig:
            break
    output["insert_move_face3_sig"] = sig

    enum_report = _walk_swconst_move_face_type()
    output["swconst_move_face_type"] = enum_report

    translate_val: int | None = None
    for k, v in enum_report.items():
        if k != "path" and k != "loadable" and k != "error":
            if "translate" in k.lower():
                translate_val = int(v)
                break
    if translate_val is None:
        all_members = {
            k: v for k, v in enum_report.items()
            if k not in ("path", "loadable", "error")
        }
        output["translate_value_not_found"] = True
        output["all_enum_members"] = all_members
        if all_members:
            for k, v in all_members.items():
                if isinstance(v, int) and v == 0:
                    translate_val = int(v)
                    output["translate_fallback"] = (
                        f"using {k}={v} (zero-valued member)"
                    )
                    break
    output["move_type_translate_value"] = translate_val

    if not sig:
        output["overall"] = "FAIL"
        output["failure_point"] = "InsertMoveFace3 not found in sldworks.tlb"
        return output
    if translate_val is None:
        output["overall"] = "FAIL"
        output["failure_point"] = (
            "swMoveFaceType_e translate value not determinable"
        )
        return output

    from spike_earlybind_persist import connect_running_sw

    sw = connect_running_sw()
    try:
        output["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        output["sw_revision"] = "<unreadable>"

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    print("=== W59 move_face_translate spike ===", file=sys.stderr)
    print(
        f"  InsertMoveFace3: {sig.get('cParams')} params on "
        f"{sig.get('interface')}",
        file=sys.stderr,
    )
    print(
        f"  swMoveFaceType_e translate = {translate_val}",
        file=sys.stderr,
    )

    build = _build_fixture(sw)
    output["fixture"] = {
        k: v for k, v in build.items() if k != "doc"
    }
    if not build.get("built"):
        output["overall"] = "FAIL"
        output["failure_point"] = "fixture build failed"
        return output

    doc = build["doc"]
    before_bb = _get_bbox(doc)
    before_vol = _get_volume(doc)
    output["before"] = {"bbox": before_bb, "volume_mm3": before_vol}

    sel = _select_faces(doc)
    output["face_selection"] = sel

    if sel.get("selected_count", 0) < 1:
        output["overall"] = "FAIL"
        output["failure_point"] = (
            f"+X face not selected ({sel.get('error', 'unknown')})"
        )
        output["face_selection_detail"] = sel
        sw.CloseAllDocuments(True)
        return output

    probe = _probe_move_face(doc, sig, translate_val)
    output["move_face_probe"] = probe

    after_bb = _get_bbox(doc)
    after_vol = _get_volume(doc)
    output["after"] = {"bbox": after_bb, "volume_mm3": after_vol}

    if before_bb and after_bb:
        output["bbox_delta"] = _bbox_deltas(before_bb, after_bb)
        output["bbox_vol_before"] = _bbox_vol(before_bb)
        output["bbox_vol_after"] = _bbox_vol(after_bb)
    if before_vol is not None and after_vol is not None:
        output["delta_vol_mm3"] = after_vol - before_vol

    sr = _save_reopen(sw, doc)
    sr_clean = {k: v for k, v in sr.items() if k != "doc"}
    output["save_reopen"] = sr_clean

    reopen_bb = None
    reopen_vol = None
    if sr.get("reopen_ok") and sr.get("doc"):
        rd = sr["doc"]
        reopen_bb = _get_bbox(rd)
        reopen_vol = _get_volume(rd)
        output["reopen"] = {"bbox": reopen_bb, "volume_mm3": reopen_vol}
        if before_bb and reopen_bb:
            output["reopen_bbox_delta"] = _bbox_deltas(
                before_bb, reopen_bb,
            )

    dx_mm = (TRANSLATE_DX_M * 1000)
    if before_bb and after_bb:
        deltas = _bbox_deltas(before_bb, after_bb)
        dx_actual = deltas["dx_max_m"]
        vol_change = (
            (after_vol - before_vol)
            if (before_vol is not None and after_vol is not None)
            else None
        )

        off_axis_max = max(
            abs(deltas["dy_min_m"]), abs(deltas["dy_max_m"]),
            abs(deltas["dz_min_m"]), abs(deltas["dz_max_m"]),
        )
        x_shift_ok = (
            abs(dx_actual - TRANSLATE_DX_M) < 0.001
            and abs(deltas["dx_min_m"] - TRANSLATE_DX_M) < 0.001
        )
        off_axis_ok = off_axis_max < 0.001
        vol_ok = (
            vol_change is not None and abs(vol_change) < 1e-12
        ) or vol_change is None

        if x_shift_ok and off_axis_ok and vol_ok:
            output["verdict"] = "RIGID"
            output["overall"] = "PASS"
            print(
                f"  RIGID: +{dx_actual * 1000:.1f} mm X, "
                f"off-axis max {off_axis_max * 1000:.4f} mm, "
                f"ΔVol={vol_change}",
                file=sys.stderr,
            )
        else:
            output["verdict"] = "DEFORM"
            output["overall"] = "DEFORM"
            output["deform_detail"] = {
                "x_shift_ok": x_shift_ok,
                "off_axis_ok": off_axis_ok,
                "vol_ok": vol_ok,
                "off_axis_max_mm": off_axis_max * 1000,
            }
            print(
                f"  DEFORM: dx={dx_actual * 1000:.2f} mm, "
                f"off-axis {off_axis_max * 1000:.4f} mm, "
                f"ΔVol={vol_change}",
                file=sys.stderr,
            )
            print(
                "  → running sketch-offset fallback …",
                file=sys.stderr,
            )
            fb = _fallback_sketch_offset(doc)
            output["fallback_sketch_offset"] = {
                k: v for k, v in fb.items() if k != "doc"
            }
    else:
        output["verdict"] = "MEASURE_FAIL"
        output["overall"] = "FAIL"

    if output.get("verdict") == "RIGID" and reopen_bb:
        re_deltas = _bbox_deltas(before_bb, reopen_bb)
        re_dx = re_deltas["dx_max_m"]
        if abs(re_dx - TRANSLATE_DX_M) < 0.001:
            output["persistence"] = "CONFIRMED"
        else:
            output["persistence"] = (
                f"LOST (reopen dx={re_dx * 1000:.2f} mm)"
            )
    elif output.get("verdict") == "DEFORM":
        output["persistence"] = "N/A_DEFORM"

    sw.CloseAllDocuments(True)
    return output


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "doc"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    result = run()
    payload = json.dumps(
        _scrub(result), indent=2,
        default=lambda o: f"<{type(o).__name__}>",
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(payload)
    return {
        "PASS": 0, "DEFORM": 2, "FAIL": 1, "UNKNOWN": 1,
    }.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
