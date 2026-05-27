"""
Spike v0.12-E2.1 — Live-SW B-rep marshal probe.

Drives the three IFace2 methods that brep/interrogator.py will depend on
(spec.md section 2.2) and captures the pywin32 late-binding marshal shape
for each:

    face.GetBox                   -> tuple of 6 floats (meters)
    face.Normal                   -> tuple of 3 floats (unit normal, part frame)
    face.GetSelectByIDString      -> NOT reachable via IFace2 dispatch

Pywin32 late-binding (without a typelib / makepy) AUTO-INVOKES zero-arg
methods on plain attribute access. This is the load-bearing discovery:
`face.GetBox` already returns the value tuple, and `face.GetBox()` raises
TypeError because the attribute is the tuple, not a callable. See
REPORT.md for empirical evidence.

Workflow
--------
1. Build a single boss-extrude feature (20x20x5 mm off Front Plane) via
   ``FeatureManager.FeatureExtrusion2`` (23-arg form, with 22-arg fallback
   copied from ``spikes/phase0/spike_a_extrude.py``) -- OR pass
   ``--skip-build`` to probe the first solid body already in the active
   Part.
2. Walk every IFace2 on the first solid body (via ``IPartDoc.GetBodies2``
   then ``IBody2.GetFaces``) and invoke each of the three methods.
3. For each call, report Python type, element count, element types, and
   raw values (for float-tuples) or raw value (for string).

PASS: GetBox and Normal marshal as float-tuples of the expected length
      on every face. GetSelectByIDString is documented as a known gap
      with the chosen workaround.
FAIL: GetBox or Normal raises, returns None, or wraps elements in a
      non-float VARIANT. A GetBox/Normal FAIL aborts E2.2..E2.7 per
      execution_plan_90d.md section 1.5.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc, SW_DOC_PART  # noqa: E402


BOSS_WIDTH_M = 0.020
BOSS_HEIGHT_M = 0.020
BOSS_DEPTH_M = 0.005


def _python_type_tag(v: Any) -> str:
    """Short type label safe for JSON serialization."""
    if v is None:
        return "NoneType"
    t = type(v).__name__
    if t == "CDispatch":
        return f"CDispatch({getattr(v, '_username_', '?')})"
    return t


def _element_types(seq: Any) -> list[str]:
    """Per-element type labels for an iterable return value."""
    try:
        return [_python_type_tag(x) for x in seq]
    except TypeError:
        return ["<not iterable>"]


def _ensure_part_doc(sw: Any) -> Any:
    """Return the active Part doc; refuse if no doc or wrong type.

    Prereq: SOLIDWORKS running with a blank Part active (same as the
    Phase 0 spikes). New-part creation is out of scope -- that path is
    exercised by the production build flow, not by this marshal probe.
    """
    doc = get_active_doc(sw)
    if doc is None:
        raise RuntimeError("no active document; open a blank Part first")
    if doc.GetType != SW_DOC_PART:
        raise RuntimeError(
            f"active doc is not a Part (GetType={doc.GetType!r}); open a blank Part"
        )
    return doc


def build_single_boss(doc: Any) -> dict[str, Any]:
    """Insert one Boss-Extrude feature on the Front Plane.

    Uses the same late-binding conventions as spikes/phase0/spike_a_extrude.py:
    legacy 5-arg ``SelectByID`` (``SelectByID2``'s Callout arg does not
    marshal under late binding -- see docs/known_gotchas.md) and a 23/22-arg
    fallback on ``FeatureExtrusion2`` (the 23rd arg ``FlipStartOffset`` is
    inconsistently present across SOLIDWORKS service packs).
    """
    ok = doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        return {"built": False, "error": "could not select Front Plane"}

    sketch_mgr = doc.SketchManager
    sketch_mgr.InsertSketch(True)
    seg = sketch_mgr.CreateCornerRectangle(
        -BOSS_WIDTH_M / 2,
        -BOSS_HEIGHT_M / 2,
        0.0,
        BOSS_WIDTH_M / 2,
        BOSS_HEIGHT_M / 2,
        0.0,
    )
    if seg is None:
        sketch_mgr.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sketch_mgr.InsertSketch(True)

    fm = doc.FeatureManager
    try:
        feat = fm.FeatureExtrusion2(
            True, False, False,
            0, 0,
            BOSS_DEPTH_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0.0,
            False,
        )
    except Exception:
        feat = fm.FeatureExtrusion2(
            True, False, False,
            0, 0,
            BOSS_DEPTH_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0.0,
        )
    if feat is None:
        return {
            "built": False,
            "error": "FeatureExtrusion2 returned None -- arg shape rejected by SW",
        }

    return {
        "built": True,
        "feature_name": getattr(feat, "Name", None),
        "feat_type": _python_type_tag(feat),
    }


def _iter_faces(doc: Any) -> list[Any]:
    """Walk the active part's first solid body and return its IFace2 list.

    Under pywin32 late binding ``body.GetFaces()`` returns a Python tuple of
    ``CDispatch`` proxies, each backed by an IFace2 on the out-of-process
    marshaler. The proxy's ``_username_`` reports ``"GetFaces"`` (the
    accessor, not the element type) because the marshaler does not expose
    per-element typeinfo.
    """
    SW_SOLID_BODY = 0
    bodies = doc.GetBodies2(SW_SOLID_BODY, True)
    if not bodies:
        return []
    body = bodies[0]
    faces = body.GetFaces()
    return list(faces) if faces else []


def probe_face(face: Any, idx: int) -> dict[str, Any]:
    """Probe the three IFace2 methods and capture their marshal shape.

    IMPORTANT: under pywin32 late-binding, zero-arg COM methods are
    auto-invoked on attribute access. ``face.GetBox`` is the value, NOT a
    callable. Adding ``()`` raises ``TypeError: 'tuple' object is not
    callable``. The production interrogator MUST use property access, not
    method call syntax, for zero-arg IFace2 methods.
    """
    record: dict[str, Any] = {"face_idx": idx}

    for method in ("GetBox", "Normal", "GetSelectByIDString"):
        t0 = time.perf_counter()
        try:
            result = getattr(face, method)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
        except pywintypes.com_error as e:
            record[method] = {
                "status": "COM_ERROR",
                "hresult": getattr(e, "hresult", None),
                "description": getattr(e, "strerror", str(e)),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }
            continue
        except AttributeError as e:
            record[method] = {
                "status": "ATTRIBUTE_MISSING",
                "message": str(e),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }
            continue
        except Exception as e:
            record[method] = {
                "status": "PYTHON_EXCEPTION",
                "exception_type": type(e).__name__,
                "message": str(e),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            }
            continue

        entry: dict[str, Any] = {
            "status": "OK" if result is not None else "NONE_RETURNED",
            "python_type": _python_type_tag(result),
            "elapsed_ms": elapsed_ms,
        }
        if method in ("GetBox", "Normal"):
            if result is not None:
                entry["length"] = len(result) if hasattr(result, "__len__") else None
                entry["element_types"] = _element_types(result)
                try:
                    entry["raw_values"] = [float(x) for x in result]
                except (TypeError, ValueError):
                    entry["raw_values"] = [repr(x) for x in result]
        else:
            entry["raw_value"] = result
        record[method] = entry

    # Also capture GetFaceId -- the documented fallback identifier when
    # GetSelectByIDString is unreachable via late binding.
    t0 = time.perf_counter()
    try:
        fid = face.GetFaceId
        record["GetFaceId"] = {
            "status": "OK" if fid is not None else "NONE_RETURNED",
            "python_type": _python_type_tag(fid),
            "raw_value": fid,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as e:
        record["GetFaceId"] = {
            "status": "PYTHON_EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }

    return record


def run_com(skip_build: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build_result: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        build_result.update(build_single_boss(doc))
        if not build_result.get("built"):
            return {
                "overall": "FAIL",
                "reason": "boss extrude did not build",
                "build": build_result,
            }
        try:
            doc.EditRebuild3()
        except Exception:
            try:
                doc.EditRebuild()
            except Exception:
                pass

    faces = _iter_faces(doc)
    if not faces:
        return {
            "overall": "FAIL",
            "reason": "no IFace2 discovered on the first solid body",
            "build": build_result,
        }

    probes = [probe_face(f, i) for i, f in enumerate(faces)]

    verdict = "PASS"
    fail_reasons: list[str] = []
    getbox_ok = False
    normal_ok = False
    selbyid_status = "UNKNOWN"

    for p in probes:
        box = p["GetBox"]
        if box.get("status") != "OK":
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.GetBox: {box.get('status')}")
        elif box.get("length") != 6:
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.GetBox length {box.get('length')} != 6")
        elif not all(t == "float" for t in box.get("element_types", [])):
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.GetBox non-float elements")
        else:
            getbox_ok = True

        nrm = p["Normal"]
        if nrm.get("status") != "OK":
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.Normal: {nrm.get('status')}")
        elif nrm.get("length") != 3:
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.Normal length {nrm.get('length')} != 3")
        elif not all(t == "float" for t in nrm.get("element_types", [])):
            verdict = "FAIL"
            fail_reasons.append(f"face {p['face_idx']}.Normal non-float elements")
        else:
            normal_ok = True

        sel = p["GetSelectByIDString"]
        if sel.get("status") == "OK":
            selbyid_status = "OK"
        elif selbyid_status == "UNKNOWN":
            selbyid_status = sel.get("status", "UNKNOWN")

    if not getbox_ok or not normal_ok:
        verdict = "FAIL"

    return {
        "overall": verdict,
        "sw_revision": sw.RevisionNumber,
        "face_count": len(faces),
        "summary": {
            "GetBox": "marshal-clean" if getbox_ok else "FAIL",
            "Normal": "marshal-clean" if normal_ok else "FAIL",
            "GetSelectByIDString": selbyid_status,
        },
        "build": build_result,
        "probes": probes,
        "failures": fail_reasons,
    }


def emit_vba() -> str:
    return """' Spike v0.12-E2.1 VBA fallback
' Paste into a Part-document module, press F5. Confirms the same three
' IFace2 methods return well-typed Variant results in early binding.
Option Explicit
Sub ProbeBrepMarshal()
    Dim swApp As Object, Part As Object
    Dim bodies As Variant, body As Object
    Dim faces As Variant, f As Object
    Dim box As Variant, nrm As Variant, selId As String
    Dim i As Long
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    bodies = Part.GetBodies2(0, True)
    If IsEmpty(bodies) Then MsgBox "No solid body": Exit Sub
    Set body = bodies(0)
    faces = body.GetFaces
    For i = LBound(faces) To UBound(faces)
        Set f = faces(i)
        box = f.GetBox
        nrm = f.Normal
        selId = f.GetSelectByIDString
        Debug.Print "face " & i & ": box(" & box(0) & ".." & box(5) & _
                    ") normal(" & nrm(0) & "," & nrm(1) & "," & nrm(2) & _
                    ") selId=" & selId
    Next i
    MsgBox "Spike E2.1 VBA PASS"
End Sub
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["com", "vba"],
        default="com",
        help="com = drive SW from Python; vba = emit a .bas fallback.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip the boss-extrude build; probe the first solid body already in the active part.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = parser.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_brep_marshal.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run_com(args.skip_build)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
