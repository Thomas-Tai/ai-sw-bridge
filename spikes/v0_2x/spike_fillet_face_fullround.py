"""W68 face fillet / full-round fillet — LIVE-seat spike (W0's fire harness).

Two sub-types, two fixtures, one handler pipeline:

  A. FACE fillet     (swFaceFillet = 2)     → 2 adjacent faces of a 40×30×10 block
  B. FULL-ROUND fillet (swFullRoundFillet=3) → side / center / side faces of a slab

Pipeline is the shipped constant-fillet recipe
(``mutate._create_fillet``) with the delta being the ``FilletType`` arg to
``ISimpleFilletFeatureData2.Initialize``.  The handler uses mark-bound
``select_entity`` for face-set routing (mark 1/2 for face, mark 3/4/5 for
full-round).  W0 closes the "marks-alone vs. SetFaces" residual unknown on
the seat — the spike includes a direct-API ``SetFaces`` diagnostic probe
that fires if the marks-only path no-ops.

Verdicts:
  PASS     — handler ok AND GetTypeName2 matches "Fillet*" AND survives reopen
  WEAK_PASS — handler ok + type-name matches but does NOT survive reopen
  FAIL     — handler returned False OR type-name does not match
  ERROR    — connect / fixture failure before the handler fired

Usage (W0 fires on the live seat):
    C:/Python314/python.exe spikes/v0_2x/spike_fillet_face_fullround.py
"""

from __future__ import annotations

import base64
import json
import sys
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS_PATH = Path(__file__).resolve().parents[1] / "_results" / "fillet_face_fullround.json"

import pythoncom

from _feature_spike_fixtures import build_block, save_and_reopen
from ai_sw_bridge.features.fillet_face_fullround import (
    create_fillet_face_fullround,
)
from ai_sw_bridge.selection.live import capture_persist_id


# --- face capture (persist-id + minimal fingerprint) ----------------------

def _null_disp() -> Any:
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _face_normal(face: Any) -> list[float]:
    """Best-effort unit normal of a planar face.  Falls back to [0,0,1]."""
    try:
        surf = face.GetSurface
        if callable(surf):
            surf = surf()
        if surf is None:
            return [0.0, 0.0, 1.0]
        # IPlane.ParamAt (u, v) returns (status, pt, udir, vdir, normal)
        # per SW2024 CHM.  Use the parametric centre (0,0).
        try:
            params = surf.ParamAt(0.0, 0.0)
        except Exception:
            params = None
        if (
            isinstance(params, (list, tuple))
            and len(params) >= 5
            and isinstance(params[4], (list, tuple))
            and len(params[4]) >= 3
        ):
            n = params[4]
            return [float(n[0]), float(n[1]), float(n[2])]
    except Exception:
        pass
    return [0.0, 0.0, 1.0]


def _face_centroid_m(face: Any) -> list[float]:
    """Face centroid (metres) via GetMassProperties; fallback [0,0,0]."""
    try:
        mp = face.GetMassProperties(1.0)
        if mp and len(mp) >= 3:
            return [float(mp[0]), float(mp[1]), float(mp[2])]
    except Exception:
        pass
    return [0.0, 0.0, 0.0]


def _face_area_mm2(face: Any) -> float:
    try:
        a = face.GetArea
        if callable(a):
            a = a()
        return float(a) * 1e6
    except Exception:
        return 0.0


def _capture_face_ref(doc: Any, face: Any, role: str) -> dict:
    """Build a handler-consumable face_ref dict (manifest-face shape).

    The handler resolves via ``resolve_manifest_face`` → ``DurableRef.from_manifest_face``
    which requires ``normal``, ``centroid``, ``area_mm2`` and (optionally)
    ``persist_id`` (base64url, no padding).
    """
    pid_bytes = capture_persist_id(doc, face)
    pid_b64: str | None = None
    if pid_bytes:
        pid_b64 = base64.urlsafe_b64encode(pid_bytes).decode("ascii").rstrip("=")
    out: dict = {
        "normal": _face_normal(face),
        "centroid": _face_centroid_m(face),
        "area_mm2": _face_area_mm2(face),
        "role_hint": role,
    }
    if pid_b64 is not None:
        out["persist_id"] = pid_b64
    return out


def _select_face_at(doc: Any, x_m: float, y_m: float, z_m: float) -> Any:
    """Extension.SelectByID2("", "FACE", x, y, z) → GetSelectedObject6.
    Returns the live IFace2 or ``None``.  Always clears selection after.
    """
    ext = doc.Extension
    null = _null_disp()
    try:
        ok = ext.SelectByID2("", "FACE", x_m, y_m, z_m, False, 0, null, 0)
    except Exception as exc:
        print(f"  SelectByID2(FACE@{x_m},{y_m},{z_m}) raised: {exc!r}", file=sys.stderr)
        return None
    if not ok:
        return None
    try:
        face = doc.SelectionManager.GetSelectedObject6(1, -1)
    except Exception:
        face = None
    doc.ClearSelection2(True)
    return face


def _type_name(node: Any) -> str | None:
    """A7 probe — GetTypeName2 with GetTypeName fallback."""
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _latest_feature(doc: Any) -> Any | None:
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return None
    if not feats:
        return None
    return feats[-1]


def _volume_mm3(doc: Any) -> float:
    try:
        bodies = doc.GetBodies2(0, False)
    except Exception:
        return 0.0
    if not bodies:
        return 0.0
    body_list = list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]
    vol = 0.0
    for b in body_list:
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol += float(mp[3]) * 1e9
        except Exception:
            pass
    return vol


def _face_count(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(0, False)
    except Exception:
        return 0
    if not bodies:
        return 0
    body_list = list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]
    n = 0
    for b in body_list:
        try:
            f = b.GetFaces
            if callable(f):
                f = f()
            n += len(f) if f else 0
        except Exception:
            pass
    return n


# --- fixture: 40x30x10 block face refs (face fillet needs 2 adjacent) ------

def _block_face_refs(doc: Any) -> tuple[dict, dict] | None:
    """Capture two ADJACENT face refs on the 40x30x10 block.

    Block spans x∈[-20,20]mm, y∈[-15,15]mm, z∈[0,10]mm.  Adjacent pair:
      set1: top face    (z=10mm, normal +z)
      set2: +x side     (x=20mm, normal +x)
    Their shared top-right edge is the fillet target.
    """
    top = _select_face_at(doc, 0.0, 0.0, 0.010)        # z=10mm
    side_x = _select_face_at(doc, 0.020, 0.0, 0.005)   # x=20mm
    if top is None or side_x is None:
        return None
    return (
        _capture_face_ref(doc, top, "+z_top"),
        _capture_face_ref(doc, side_x, "+x_side"),
    )


# --- fixture: slab for full-round (3 parallel faces on a thin slab) -------
# A full-round fillet needs side1 / center / side2 faces that share tangent
# edges — the canonical shape is a rectangular slab where the TOP face is
# flanked by two SIDE faces along parallel long edges.  We build the slab
# by boss-extruding a narrow rectangle on the block's top face (Sketch2).

_SLAB_WIDTH_M = 0.010   # 10 mm
_SLAB_LENGTH_M = 0.030  # 30 mm
_SLAB_HEIGHT_M = 0.005  # 5 mm
_BLIND = 0


def _build_slab_on_block(doc: Any) -> bool:
    """Add a 30x10x5 mm slab on the block's top face.  Returns True on success.

    Sketches on the top face (Sketch2 — Sketch1 was consumed by Boss-Extrude1).
    The resulting Boss-Extrude2 yields 5 new faces: top + 4 sides.  The
    full-round fillet targets the TOP face (center) flanked by the two long
    SIDE faces (+y / -y).
    """
    from win32com.client import VARIANT
    null = VARIANT(pythoncom.VT_DISPATCH, None)
    ext = doc.Extension
    try:
        ext.SelectByID2("", "FACE", 0.0, 0.0, 0.010, False, 0, null, 0)
    except Exception as exc:
        print(f"  slab: SelectByID2(top face) raised: {exc!r}", file=sys.stderr)
        return False
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    doc.ClearSelection2(True)
    if face is None:
        return False
    face.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)
    hw = _SLAB_WIDTH_M / 2
    hl = _SLAB_LENGTH_M / 2
    doc.SketchManager.CreateCornerRectangle(-hl, -hw, 0.0, hl, hw, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    try:
        ext.SelectByID2("Sketch2", "SKETCH", 0, 0, 0, False, 4, null, 0)
    except Exception as exc:
        print(f"  slab: SelectByID2(Sketch2) raised: {exc!r}", file=sys.stderr)
        return False
    try:
        doc.FeatureManager.FeatureExtrusion2(
            True, False, False, _BLIND, 0,
            _SLAB_HEIGHT_M, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False,
            True, True, True, 0, 0.0, False,
        )
    except Exception as exc:
        print(f"  slab: FeatureExtrusion2 raised: {exc!r}", file=sys.stderr)
        return False
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    doc.ClearSelection2(True)
    return True


def _slab_face_refs(doc: Any) -> tuple[dict, dict, dict] | None:
    """Capture side1 / center / side2 face refs for the full-round fillet.

    Slab spans x∈[-15,15]mm, y∈[-5,5]mm, z∈[10,15]mm (atop the block).
      side1:  +y long side    (y=+5mm, normal +y, z~12.5mm midpoint)
      center: slab top        (z=15mm, normal +z)
      side2:  -y long side    (y=-5mm, normal -y, z~12.5mm)
    """
    side1 = _select_face_at(doc, 0.0, 0.005, 0.0125)      # +y slab side
    center = _select_face_at(doc, 0.0, 0.0, 0.015)         # slab top (z=15mm)
    side2 = _select_face_at(doc, 0.0, -0.005, 0.0125)      # -y slab side
    if side1 is None or center is None or side2 is None:
        return None
    return (
        _capture_face_ref(doc, side1, "+y_slab_side"),
        _capture_face_ref(doc, center, "+z_slab_top"),
        _capture_face_ref(doc, side2, "-y_slab_side"),
    )


# --- direct-API diagnostic probe (closes the SetFaces residual unknown) ---

def _setfaces_diagnostic(doc: Any, face_refs: list[dict], type_id: int) -> dict:
    """Diagnostic: try SetFaces(WhichFaceList, FaceList) explicitly.

    Fires ONLY when the marks-only path no-ops.  Returns a dict with
    (ok, error, setfaces_called, notes) so W0 can read whether the explicit
    face-commit is needed.
    """
    from ai_sw_bridge.com.earlybind import typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.selection.live import resolve_manifest_face

    out: dict = {"called": False, "ok": False, "notes": []}
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(1)  # swFmFillet
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        fd.Initialize(type_id)
        faces_by_set: list[tuple[int, list[Any]]] = []
        # face fillet → set1=1, set2=2; full-round → side1=3, center=4, side2=5
        which_list = (1, 2) if type_id == 2 else (3, 4, 5)
        for ref, which in zip(face_refs, which_list):
            res = resolve_manifest_face(doc, ref)
            if res.entity is None:
                out["notes"].append(f"resolve fail at which={which}")
                continue
            faces_by_set.append((which, [res.entity]))
        for which, faces in faces_by_set:
            try:
                fd.SetFaces(which, faces)
                out["called"] = True
            except Exception as exc:
                out["notes"].append(f"SetFaces({which}, ...) raised: {exc!r}")
        feat = fm.CreateFeature(fd)
        out["ok"] = feat is not None and not isinstance(feat, (int, bool))
        out["feature_return"] = repr(feat)[:120]
    except Exception as exc:
        out["notes"].append(f"diagnostic pipeline raised: {exc!r}")
    return out


# --- main run --------------------------------------------------------------

def _run_sub(
    doc: Any,
    sub: str,
    feature: dict,
    target: dict,
    face_refs_for_diag: list[dict],
) -> dict:
    out: dict = {"sub": sub}
    try:
        faces_before = _face_count(doc)
        vol_before = _volume_mm3(doc)
    except Exception:
        faces_before, vol_before = 0, 0.0
    out["faces_before"] = faces_before
    out["vol_before_mm3"] = round(vol_before, 6)

    try:
        ok, note = create_fillet_face_fullround(doc, feature, target)
    except Exception as exc:
        ok, note = False, f"handler raised: {exc!r}"
        traceback.print_exc()
    out["handler_ok"] = ok
    out["handler_note"] = note

    try:
        faces_after = _face_count(doc)
        vol_after = _volume_mm3(doc)
    except Exception:
        faces_after, vol_after = 0, 0.0
    out["faces_after"] = faces_after
    out["vol_after_mm3"] = round(vol_after, 6)
    out["delta_faces"] = faces_after - faces_before
    out["delta_vol_mm3"] = round(vol_after - vol_before, 6)

    # A7 probe — GetTypeName2 on the last feature
    last = _latest_feature(doc)
    if last is not None:
        out["last_feature_type"] = _type_name(last)
        try:
            nm = last.Name
            out["last_feature_name"] = nm() if callable(nm) else str(nm)
        except Exception:
            pass

    # SetFaces diagnostic: fire only if handler failed AND the failure looks
    # like a ghost (no volume delta).  This closes the "marks-alone vs.
    # SetFaces" residual unknown on the seat.
    if not ok:
        type_id = 2 if feature.get("fillet_type") == "face" else 3
        try:
            out["setfaces_diagnostic"] = _setfaces_diagnostic(
                doc, face_refs_for_diag, type_id,
            )
        except Exception as exc:
            out["setfaces_diagnostic_error"] = f"{type(exc).__name__}: {exc}"

    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike_id": "W68_fillet_face_fullround"}
    try:
        from ai_sw_bridge.sw_com import get_sw_app
        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"connect: {exc!r}"}
    if sw is None:
        return {**result, "overall": "ERROR", "reason": "get_sw_app() returned None"}

    try:
        # --- A. FACE fillet on 40x30x10 block ------------------------------
        doc_a = build_block(sw)
        try:
            pair = _block_face_refs(doc_a)
            if pair is None:
                a = {"sub": "face", "handler_ok": False,
                     "handler_note": "fixture: could not select block top/+x faces"}
            else:
                a = _run_sub(
                    doc_a,
                    sub="face",
                    feature={"fillet_type": "face", "radius_mm": 3.0},
                    target={"faces": list(pair)},
                    face_refs_for_diag=list(pair),
                )
                # survival
                try:
                    doc_a2 = save_and_reopen(sw, doc_a)
                    if doc_a2 is not None:
                        a["survives_reopen"] = True
                        a["vol_after_reopen_mm3"] = round(_volume_mm3(doc_a2), 6)
                    else:
                        a["survives_reopen"] = False
                except Exception as exc:
                    a["survives_reopen"] = False
                    a["reopen_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            pass  # CloseAllDocuments in outer finally

        # --- B. FULL-ROUND fillet on a slab-on-block -----------------------
        doc_b = build_block(sw)
        try:
            slab_ok = _build_slab_on_block(doc_b)
            if not slab_ok:
                b = {"sub": "full_round", "handler_ok": False,
                     "handler_note": "fixture: slab extrusion failed"}
            else:
                triple = _slab_face_refs(doc_b)
                if triple is None:
                    b = {"sub": "full_round", "handler_ok": False,
                         "handler_note": "fixture: could not select slab side1/center/side2"}
                else:
                    side1, center, side2 = triple
                    b = _run_sub(
                        doc_b,
                        sub="full_round",
                        feature={"fillet_type": "full_round"},
                        target={"side1": side1, "center": center, "side2": side2},
                        face_refs_for_diag=[side1, center, side2],
                    )
                    try:
                        doc_b2 = save_and_reopen(sw, doc_b)
                        if doc_b2 is not None:
                            b["survives_reopen"] = True
                            b["vol_after_reopen_mm3"] = round(_volume_mm3(doc_b2), 6)
                        else:
                            b["survives_reopen"] = False
                    except Exception as exc:
                        b["survives_reopen"] = False
                        b["reopen_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            pass

        result["face"] = a
        result["full_round"] = b

        # --- overall verdict ----------------------------------------------
        def _sub_verdict(r: dict) -> str:
            if not r.get("handler_ok"):
                return "FAIL"
            tname = (r.get("last_feature_type") or "").lower()
            if "fillet" not in tname and "roundfillet" not in tname and "facefillet" not in tname:
                return "FAIL"
            if r.get("survives_reopen"):
                return "PASS"
            return "WEAK_PASS"

        a_v = _sub_verdict(a)
        b_v = _sub_verdict(b)
        result["face_verdict"] = a_v
        result["full_round_verdict"] = b_v
        if a_v == "PASS" and b_v == "PASS":
            result["overall"] = "PASS"
        elif "FAIL" in (a_v, b_v):
            result["overall"] = "FAIL"
        else:
            result["overall"] = "WEAK_PASS"
        result["finding"] = (
            f"face={a_v}, full_round={b_v}; "
            f"handler_ok(A)={a.get('handler_ok')}, handler_ok(B)={b.get('handler_ok')}"
        )

    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

    return result


def main() -> None:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"),
        encoding="utf-8",
    )
    print(f"overall: {result.get('overall')}", file=sys.stderr)
    print(f"finding: {result.get('finding')}", file=sys.stderr)
    print(f"face: {result.get('face_verdict')}  full_round: {result.get('full_round_verdict')}", file=sys.stderr)
    print(f"results -> {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
