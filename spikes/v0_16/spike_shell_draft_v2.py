"""
Spike v0.16 / S-SHELL-DRAFT-V2 — find the working creation calls for Shell and
Draft (Wall-2 features: IFeatureManager/IModelDoc2 Insert* methods, not
CreateDefinition).
[authored seat-free; RUN ON A LIVE SEAT]

Typelib facts (this build):
  * Shell  = IModelDoc2.InsertFeatureShell(Thickness:r8, Outward:bool) -> void
             (pre-select the face(s) to remove). The v0.15 "no attribute" was a
             makepy-wrapper gap; the method exists.
  * Draft  = IFeatureManager.InsertMultiFaceDraft(Angle, FlipDir, EdgeDraft,
             PropType, IsStepDraft, IsBodyDraft) -> Feature
             (pre-select neutral plane + faces to draft, with marks).

Selection is ENTITY-based (select_entity append+mark) — the dynamic doc's 9-arg
SelectByID2 hits the <unknown> wall, and coordinate SelectByID can't carry marks.

Verdicts per feature: PASS / PARTIAL / FAIL, plus an overall.

Usage:  python spikes/v0_16/spike_shell_draft_v2.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.selection import select_entity  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
BOX_W_M = 0.040
BOX_H_M = 0.030
BOX_D_M = 0.020

SHELL_THICK_M = 0.002
DRAFT_ANGLE_RAD = math.radians(5.0)
SW_FACE_PROP_NONE = 0  # swDraftFacePropagationType_e


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(f: Any) -> bool:
    return f is not None and not isinstance(f, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (tuple, list)) else [v]


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return {"built": False, "error": "select Front Plane failed"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return {"built": feat is not None, "feature_name": getattr(feat, "Name", None)}


def _normal(face: Any) -> tuple | None:
    try:
        n = face.Normal
        n = n() if callable(n) else n
    except Exception:  # noqa: BLE001
        return None
    n = _as_list(n)
    return tuple(n[:3]) if len(n) >= 3 else None


def _faces(doc: Any) -> list[tuple[Any, tuple | None]]:
    body = None
    rec, bodies = _capture(lambda: doc.GetBodies2(0, True))
    bl = _as_list(bodies)
    if bl:
        body = bl[0]
    if body is None:
        return []
    edges = _as_list(body.GetFaces())
    return [(f, _normal(f)) for f in edges]


def _pick(faces: list, want: tuple[float, float, float], tol: float = 0.3) -> Any:
    for f, n in faces:
        if n is None:
            continue
        if all(abs(n[i] - want[i]) < tol for i in range(3)):
            return f
    return None


def _last_feature_type(doc: Any) -> str | None:
    try:
        f = doc.FirstFeature()
        last = None
        guard = 0
        while f is not None and guard < 300:
            guard += 1
            last = f
            f = f.GetNextFeature()
        return _type_name(last) if last is not None else None
    except Exception:  # noqa: BLE001
        return None


def _run_shell(sw: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument None"}
    try:
        out["build"] = _build_box(doc)
        if not out["build"].get("built"):
            return {**out, "overall": "FAIL", "reason": "box build"}
        faces = _faces(doc)
        out["n_faces"] = len(faces)
        top = _pick(faces, (0, 0, 1))
        if top is None:
            return {**out, "overall": "FAIL", "reason": "no top face"}
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        out["selected_top"] = select_entity(top, append=False, mark=0)
        # InsertFeatureShell is on IModelDoc2; try dynamic then typed.
        rec, _ = _capture(lambda: doc.InsertFeatureShell(SHELL_THICK_M, False))
        if rec["status"] != "OK":
            tdoc = typed(doc, "IModelDoc2", module=mod)
            select_entity(top, append=False, mark=0)
            rec, _ = _capture(lambda: tdoc.InsertFeatureShell(SHELL_THICK_M, False))
            rec["via"] = "typed IModelDoc2"
        else:
            rec["via"] = "dynamic doc"
        out["InsertFeatureShell"] = rec
        try:
            doc.ForceRebuild3(False)
        except Exception:  # noqa: BLE001
            pass
        # A shell (top removed, walled) adds interior faces: 6 -> ~11.
        out["faces_before"] = len(faces)
        out["faces_after"] = len(_faces(doc))
        out["last_feature_type"] = _last_feature_type(doc)
        shelled = out["faces_after"] > out["faces_before"]
        out["overall"] = (
            "PASS"
            if (rec["status"] == "OK" and shelled)
            else ("PARTIAL" if rec["status"] == "OK" else "FAIL")
        )
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
    return out


def _run_draft(sw: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument None"}
    try:
        out["build"] = _build_box(doc)
        if not out["build"].get("built"):
            return {**out, "overall": "FAIL", "reason": "box build"}
        faces = _faces(doc)
        out["n_faces"] = len(faces)
        neutral = _pick(faces, (0, 0, -1))  # bottom face = neutral plane
        side = _pick(faces, (1, 0, 0)) or _pick(faces, (0, 1, 0))
        if neutral is None or side is None:
            return {
                **out,
                "overall": "FAIL",
                "reason": "could not find neutral/side face",
            }
        fm = doc.FeatureManager
        # Try a couple of mark conventions for (neutral, draft-face).
        attempts: list[dict[str, Any]] = []
        feat = None
        for nm_mark, face_mark in ((1, 0), (1, 1), (1, 2)):
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            sn = select_entity(neutral, append=False, mark=nm_mark)
            sf = select_entity(side, append=True, mark=face_mark)
            rec, feat = _capture(
                lambda: fm.InsertMultiFaceDraft(
                    DRAFT_ANGLE_RAD, False, False, SW_FACE_PROP_NONE, False, False
                )
            )
            rec.update(
                {
                    "neutral_mark": nm_mark,
                    "face_mark": face_mark,
                    "sel_neutral": sn,
                    "sel_face": sf,
                    "materialized": _materialized(feat),
                }
            )
            attempts.append(rec)
            if _materialized(feat):
                rec["feature_name"] = getattr(feat, "Name", None)
                rec["type_name"] = _type_name(feat)
                break
        out["attempts"] = attempts
        out["overall"] = (
            "PASS"
            if _materialized(feat)
            else ("PARTIAL" if any(a["status"] == "OK" for a in attempts) else "FAIL")
        )
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {}
    mod = wrapper_module() or ensure_sw_module()[0]
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"
    result["shell"] = _run_shell(sw, mod)
    result["draft"] = _run_draft(sw, mod)
    sv = result["shell"].get("overall")
    dv = result["draft"].get("overall")
    result["overall"] = (
        "PASS" if (sv == "PASS" and dv == "PASS") else f"shell={sv} draft={dv}"
    )
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0 if result.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
