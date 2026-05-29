"""
Spike v0.15 / S-DISPATCH — forced dynamic.Dispatch vs current dispatch mode.

Cross-cutting probe (docs/central_idea/api_coverage_roadmap.md §9, FR-X-05).
Decides whether switching the bridge's SldWorks.Application acquisition from
the current ``win32com.client.Dispatch`` path to an explicit
``win32com.client.dynamic.Dispatch`` (or a re-dispatched fresh proxy) revives
the ``Callout`` OUT-IDispatch marshaling on
``IModelDocExtension.SelectByID2`` — and, if it does, whether the simpler
``GetSelectByIDString`` route on ``IFace2`` proxies comes back too.

Background
----------
The bridge today is blocked from using the 9-arg ``SelectByID2`` because its
8th positional arg (``Callout``, an OUT ``IDispatch`` pointer) raises
``com_error('Type mismatch', ..., 8)`` under pywin32 late binding. The
workaround (documented at src/ai_sw_bridge/spec/builder.py around the
``_select_edges_by_points`` helper) is the 5-arg legacy ``SelectByID`` plus
coordinate-based closest-edge selection via ``IEdge.GetClosestPointOn`` — a
brittle path that is the single largest wart in the builder.

``IEntity.Select4(Append, Callout)`` fails the same way on arg 2.

Two related late-binding walls are in scope here:

1. ``GetSelectByIDString`` on the ``IFace2`` proxy returned by
   ``IFeature.GetFaces`` is documented UNREACHABLE (spikes/v0_12
   spike_brep_marshal.py) — which is why the bridge identifies entities by a
   session-scoped ``temp_id`` + fingerprint instead of a native token.

2. The ``Callout`` OUT-IDispatch on ``SelectByID2`` / ``Select4``. If either
   revived under an alternative dispatch mode, the coordinate/closest-edge
   selection path could be replaced with the API-native selection path — a
   cross-cutting simplification that would touch every selection site in
   ``builder.py`` and ``observe.py``.

The probe is empirical: obtain the SW app under BOTH dispatch modes, run the
same ``SelectByID2`` forms with a range of ``Callout`` arg shapes (``None``,
``pythoncom.Missing``, an explicit callout object), and record which forms
succeed under which mode.

Verdict
-------
PASS    : under some dispatch mode, at least one ``SelectByID2`` invocation
          form with a ``Callout`` placeholder returns True AND selects the
          target entity — OR ``GetSelectByIDString`` becomes reachable on an
          ``IFace2`` proxy under the alternate mode. The bridge should adopt
          that mode and drop the coordinate/closest-edge workaround.
PARTIAL : the dispatch modes differ (proxy class, attribute surface) but both
          fail on the ``Callout`` arg with the same ``DISP_E_TYPEMISMATCH`` —
          meaning the wall is the pywin32 OLE-automation marshaler, not the
          dispatch wrapper. Route-C signal: in-process (PythonNET/C#) binding
          is the only path to API-native selection. Record and move on.
FAIL    : both modes fail to reach the SldWorks.Application proxy at all, OR
          ``SelectByID2`` is unreachable on both. Install/version issue;
          retry on a different seat.

Prereq: SOLIDWORKS running with a blank Part active (same as the other
v0.15 spikes). Pass ``--skip-build`` to probe the first solid body already
present.

Usage
-----
    python spikes/v0_15/spike_dispatch.py
    python spikes/v0_15/spike_dispatch.py --skip-build --out report.json
    python spikes/v0_15/spike_dispatch.py --mode vba   # emit .bas early-binding oracle
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
import win32com.client  # noqa: E402
import win32com.client.dynamic  # noqa: E402

from ai_sw_bridge.sw_com import get_active_doc, SW_DOC_PART  # noqa: E402


BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010


def _type_tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _proxy_class(obj: Any) -> str:
    """Identify the pywin32 wrapper class of a COM proxy (CDispatch vs other)."""
    return f"{type(obj).__module__}.{type(obj).__qualname__}"


def _ensure_part_doc(doc: Any) -> None:
    if doc is None:
        raise RuntimeError("no active document; open a blank Part first")
    if doc.GetType != SW_DOC_PART:
        raise RuntimeError(
            f"active doc is not a Part (GetType={doc.GetType!r}); open a blank Part"
        )


def _build_box(doc: Any) -> dict[str, Any]:
    """Insert one 20x20x10 mm Boss-Extrude on the Front Plane (shared fixture)."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
         BOX_W_M / 2,  BOX_H_M / 2,  0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)   # 23-arg
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)           # 22-arg fallback
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


# ---------------------------------------------------------------------------
# Dispatch-mode acquisition
# ---------------------------------------------------------------------------

def _acquire_default() -> dict[str, Any]:
    """The bridge's current path: win32com.client.Dispatch."""
    t0 = time.perf_counter()
    try:
        sw = win32com.client.Dispatch("SldWorks.Application")
        rec = {"status": "OK", "proxy_class": _proxy_class(sw),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0, "_sw": sw}
    except pywintypes.com_error as e:
        rec = {"status": "COM_ERROR",
               "hresult": f"{getattr(e, 'hresult', None):#010x}",
               "description": getattr(e, "strerror", str(e)),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as e:
        rec = {"status": "PY_EXCEPTION",
               "exception_type": type(e).__name__, "message": str(e),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    return rec


def _acquire_dynamic() -> dict[str, Any]:
    """The forced path: win32com.client.dynamic.Dispatch (explicit dynamic)."""
    t0 = time.perf_counter()
    try:
        sw = win32com.client.dynamic.Dispatch("SldWorks.Application")
        rec = {"status": "OK", "proxy_class": _proxy_class(sw),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0, "_sw": sw}
    except pywintypes.com_error as e:
        rec = {"status": "COM_ERROR",
               "hresult": f"{getattr(e, 'hresult', None):#010x}",
               "description": getattr(e, "strerror", str(e)),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as e:
        rec = {"status": "PY_EXCEPTION",
               "exception_type": type(e).__name__, "message": str(e),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    return rec


def _acquire_getactive() -> dict[str, Any]:
    """win32com.client.GetActiveObject (ROT attach, no fresh dispatch)."""
    t0 = time.perf_counter()
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        rec = {"status": "OK", "proxy_class": _proxy_class(sw),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0, "_sw": sw}
    except pywintypes.com_error as e:
        rec = {"status": "COM_ERROR",
               "hresult": f"{getattr(e, 'hresult', None):#010x}",
               "description": getattr(e, "strerror", str(e)),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as e:
        rec = {"status": "PY_EXCEPTION",
               "exception_type": type(e).__name__, "message": str(e),
               "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    return rec


# ---------------------------------------------------------------------------
# SelectByID2 probe matrix
# ---------------------------------------------------------------------------

def _probe_selectbyid2(doc: Any, label: str) -> list[dict[str, Any]]:
    """Try every plausible Callout-arg shape on SelectByID2, against one
    known-good target (Front Plane). Records which forms succeed.

    SelectByID2 signature (9 args):
      Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption
    """
    doc.ClearSelection2(True)
    attempts: list[dict[str, Any]] = []

    forms: list[tuple[str, tuple]] = [
        ("all-9 Callout=None",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0, None, 0)),
        ("all-9 Callout=Missing",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0, pythoncom.Missing, 0)),
        ("all-9 Callout=0",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0, 0, 0)),
        ("all-9 Callout='' (empty str)",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0, "", 0)),
        ("kwarg Callout=None",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0),
         {"Callout": None, "SelectOption": 0}),
        ("kwarg Callout=Missing",
         ("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0),
         {"Callout": pythoncom.Missing, "SelectOption": 0}),
    ]

    ext = doc.Extension
    for entry in forms:
        if len(entry) == 2:
            form_label, args = entry
            kwargs: dict[str, Any] = {}
        else:
            form_label, args, kwargs = entry
        t0 = time.perf_counter()
        rec: dict[str, Any] = {
            "dispatch": label,
            "form": form_label,
        }
        try:
            result = ext.SelectByID2(*args, **kwargs)
            rec["status"] = "OK"
            rec["return_type"] = _type_tag(result)
            rec["return_value"] = (bool(result) if isinstance(result, (bool, int))
                                   else str(result))
        except pywintypes.com_error as e:
            hr = getattr(e, "hresult", None)
            rec["status"] = "COM_ERROR"
            rec["hresult"] = f"{hr:#010x}" if isinstance(hr, int) else str(hr)
            rec["description"] = getattr(e, "strerror", str(e))
            # DISP_E_TYPEMISMATCH = -2147352571 / 0x80020005 — the expected
            # marshaling wall on the Callout OUT-IDispatch.
            rec["is_typemismatch"] = (hr in (-2147352571, 0x80020005, -2146827830))
        except Exception as e:
            rec["status"] = "PY_EXCEPTION"
            rec["exception_type"] = type(e).__name__
            rec["message"] = str(e)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        attempts.append(rec)
    return attempts


# ---------------------------------------------------------------------------
# IEntity.Select4 probe (secondary — same Callout failure class)
# ---------------------------------------------------------------------------

def _probe_entity_select4(entity: Any, label: str) -> list[dict[str, Any]]:
    """IEntity.Select4(Append, Callout) — same OUT-IDispatch marshaling risk."""
    attempts: list[dict[str, Any]] = []
    forms = [
        ("Select4(False, None)",           (False, None)),
        ("Select4(False, Missing)",        (False, pythoncom.Missing)),
        ("Select4(False, 0)",              (False, 0)),
    ]
    for form_label, args in forms:
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"dispatch": label, "form": form_label}
        try:
            result = entity.Select4(*args)
            rec["status"] = "OK"
            rec["return_type"] = _type_tag(result)
            rec["return_value"] = (bool(result) if isinstance(result, (bool, int))
                                   else str(result))
        except pywintypes.com_error as e:
            hr = getattr(e, "hresult", None)
            rec["status"] = "COM_ERROR"
            rec["hresult"] = f"{hr:#010x}" if isinstance(hr, int) else str(hr)
            rec["description"] = getattr(e, "strerror", str(e))
            rec["is_typemismatch"] = (hr in (-2147352571, 0x80020005, -2146827830))
        except Exception as e:
            rec["status"] = "PY_EXCEPTION"
            rec["exception_type"] = type(e).__name__
            rec["message"] = str(e)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        attempts.append(rec)
    return attempts


# ---------------------------------------------------------------------------
# GetSelectByIDString on IFace2 (E2.1 follow-up — does dispatch mode revive it?)
# ---------------------------------------------------------------------------

def _probe_get_select_by_id_string(body: Any, label: str) -> dict[str, Any]:
    """E2.1 found GetSelectByIDString UNREACHABLE on IFace2 proxies. Re-test
    under this dispatch mode: is the result different?"""
    faces = list(body.GetFaces() or [])
    if not faces:
        return {"dispatch": label, "status": "NO_FACES"}
    face = faces[0]
    rec: dict[str, Any] = {
        "dispatch": label,
        "face_proxy_class": _proxy_class(face),
    }
    t0 = time.perf_counter()
    try:
        s = face.GetSelectByIDString
        rec["status"] = "OK"
        rec["python_type"] = _type_tag(s)
        rec["value"] = str(s)[:80]
    except pywintypes.com_error as e:
        rec["status"] = "COM_ERROR"
        rec["hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["description"] = getattr(e, "strerror", str(e))
    except Exception as e:
        rec["status"] = "UNREACHABLE"
        rec["exception_type"] = type(e).__name__
        rec["message"] = str(e)[:120]
    rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    return rec


# ---------------------------------------------------------------------------
# Top-level COM run
# ---------------------------------------------------------------------------

def _classify(attempts: list[dict[str, Any]]) -> str:
    if any(a.get("status") == "OK" and a.get("return_value") is True
           for a in attempts):
        return "OK"
    if any(a.get("is_typemismatch") is True for a in attempts):
        return "TYPEMISMATCH"
    if any(a.get("status") == "COM_ERROR" for a in attempts):
        return "COM_ERROR"
    return "OTHER"


def _probe_one_dispatch(label: str, acquire_fn,
                        skip_build: bool) -> dict[str, Any]:
    """Run the full probe matrix under one dispatch mode."""
    rec: dict[str, Any] = {"label": label}
    acq = acquire_fn()
    rec["acquire"] = {k: v for k, v in acq.items() if k != "_sw"}
    if acq.get("status") != "OK":
        rec["verdict"] = "FAIL"
        rec["reason"] = f"acquire failed: {acq.get('status')}"
        return rec

    sw = acq["_sw"]
    doc = get_active_doc(sw)
    try:
        _ensure_part_doc(doc)
    except RuntimeError as e:
        rec["verdict"] = "FAIL"
        rec["reason"] = str(e)
        return rec
    rec["sw_revision"] = sw.RevisionNumber

    build_rec: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        build_rec.update(_build_box(doc))
        if not build_rec.get("built"):
            rec["build"] = build_rec
            rec["verdict"] = "FAIL"
            rec["reason"] = "box did not build"
            return rec
    rec["build"] = build_rec

    # 1. SelectByID2 under this dispatch mode.
    sel2_attempts = _probe_selectbyid2(doc, label)
    rec["SelectByID2_attempts"] = sel2_attempts
    rec["SelectByID2_class"] = _classify(sel2_attempts)

    # 2. IEntity.Select4 — same Callout failure class.
    body = None
    try:
        bodies = doc.GetBodies2(0, True)
        body = bodies[0] if bodies else None
    except Exception:
        body = None
    sel4_attempts: list[dict[str, Any]] = []
    if body is not None:
        try:
            edges = list(body.GetEdges() or [])
        except Exception:
            edges = []
        if edges:
            sel4_attempts = _probe_entity_select4(edges[0], label)
    rec["Select4_attempts"] = sel4_attempts
    rec["Select4_class"] = _classify(sel4_attempts) if sel4_attempts else "N/A"

    # 3. GetSelectByIDString on IFace2 (E2.1 follow-up).
    getstr: dict[str, Any] = {}
    if body is not None:
        getstr = _probe_get_select_by_id_string(body, label)
    rec["GetSelectByIDString_on_IFace2"] = getstr

    # 4. Per-mode verdict.
    sel2_ok = rec["SelectByID2_class"] == "OK"
    sel4_ok = rec["Select4_class"] == "OK"
    getstr_ok = getstr.get("status") == "OK"
    if sel2_ok or sel4_ok or getstr_ok:
        rec["verdict"] = "PASS"
    elif rec["SelectByID2_class"] == "TYPEMISMATCH":
        rec["verdict"] = "PARTIAL"
        rec["reason"] = ("SelectByID2 failed with DISP_E_TYPEMISMATCH on the "
                         "Callout OUT-IDispatch under this dispatch mode — "
                         "the pywin32 marshaler, not the wrapper, is the wall.")
    else:
        rec["verdict"] = "PARTIAL"
        rec["reason"] = "no form succeeded; not a clean TYPEMISMATCH"
    return rec


def run_com(skip_build: bool) -> dict[str, Any]:
    modes: list[dict[str, Any]] = []

    modes.append(_probe_one_dispatch(
        "win32com.client.Dispatch (current)", _acquire_default, skip_build))
    modes.append(_probe_one_dispatch(
        "win32com.client.dynamic.Dispatch (forced)", _acquire_dynamic, skip_build))
    modes.append(_probe_one_dispatch(
        "win32com.client.GetActiveObject (ROT)", _acquire_getactive, skip_build))

    # 5. Derive overall verdict.
    any_pass = any(m.get("verdict") == "PASS" for m in modes)
    any_partial = any(m.get("verdict") == "PARTIAL" for m in modes)
    all_fail = all(m.get("verdict") == "FAIL" for m in modes)

    if any_pass:
        overall = "PASS"
        winning = [m["label"] for m in modes if m.get("verdict") == "PASS"]
        interpretation = (
            "At least one dispatch mode revives Callout-marshaling on "
            "SelectByID2 / Select4 OR GetSelectByIDString on IFace2. "
            f"Winning mode(s): {winning}. The bridge should adopt the winning "
            "mode and replace coordinate/closest-edge selection with the "
            "API-native path. Update builder.py and observe.py."
        )
    elif all_fail:
        overall = "FAIL"
        interpretation = (
            "All dispatch modes failed to acquire SldWorks.Application or the "
            "Part document. Install/version issue; retry on a different seat."
        )
    elif any_partial:
        overall = "PARTIAL"
        interpretation = (
            "All reachable dispatch modes hit DISP_E_TYPEMISMATCH on the "
            "Callout OUT-IDispatch of SelectByID2 / Select4 — AND "
            "GetSelectByIDString remains UNREACHABLE on IFace2 proxies. "
            "The pywin32 OLE-automation marshaler is the wall, not the "
            "wrapper class. ROUTE-C signal: API-native selection needs "
            "in-process (PythonNET/C#) binding. Keep the current "
            "coordinate/closest-edge workaround; record this verdict."
        )
    else:
        overall = "PARTIAL"
        interpretation = "Mixed results; see per-mode verdicts."

    return {
        "overall": overall,
        "interpretation": interpretation,
        "modes": modes,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding cross-check)
# ---------------------------------------------------------------------------

def emit_vba() -> str:
    """Early-binding oracle. If Python is PARTIAL but this PASSes, the
    pywin32 marshaler (not the SW API) is the blocker — Route-C signalled.
    """
    return r"""' Spike v0.15 S-DISPATCH VBA oracle.
' Paste into a Part-document module, press F5.
' Early binding handles the OUT-IDispatch Callout natively, so this
' isolates whether the Python PARTIAL is a marshaler limitation rather
' than an API one.
Option Explicit
Sub ProbeDispatchModes()
    Dim swApp       As Object
    Dim Part        As Object
    Dim ext         As Object
    Dim co          As Object
    Dim ok          As Boolean
    Dim msg         As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set ext   = Part.Extension

    ' 1. SelectByID2 with Callout:=Nothing (late-bound-style placeholder
    '    under early binding — VBA auto-marshals the OUT-IDispatch).
    On Error Resume Next
    ok = ext.SelectByID2("Front Plane", "PLANE", 0#, 0#, 0#, _
                         False, 0, Nothing, 0)
    If Err.Number <> 0 Then
        msg = "SelectByID2(Callout:=Nothing) FAILED: 0x" & Hex(Err.Number) _
              & " " & Err.Description
        Err.Clear
    Else
        msg = "SelectByID2(Callout:=Nothing) returned " & ok
    End If
    On Error GoTo 0

    ' 2. IEntity.Select4 on the first body edge.
    Dim bodies As Variant, body As Object, edges As Variant, e As Object
    bodies = Part.GetBodies2(0, True)
    If Not IsEmpty(bodies) Then
        Set body = bodies(0)
        edges = body.GetEdges
        If Not IsEmpty(edges) Then
            Set e = edges(0)
            On Error Resume Next
            ok = e.Select4(False, Nothing)
            If Err.Number <> 0 Then
                msg = msg & Chr(10) & "IEntity.Select4(Callout:=Nothing) FAILED: " _
                      & "0x" & Hex(Err.Number) & " " & Err.Description
                Err.Clear
            Else
                msg = msg & Chr(10) & "IEntity.Select4(Callout:=Nothing) returned " & ok
            End If
            On Error GoTo 0
        End If
    End If

    ' 3. GetSelectByIDString on IFace2 (E2.1 follow-up).
    Dim faces As Variant, f As Object, s As Variant
    If Not IsEmpty(bodies) Then
        faces = bodies(0).GetFaces
        If Not IsEmpty(faces) Then
            Set f = faces(0)
            On Error Resume Next
            s = f.GetSelectByIDString
            If Err.Number <> 0 Then
                msg = msg & Chr(10) & "IFace2.GetSelectByIDString UNREACHABLE: " _
                      & "0x" & Hex(Err.Number)
                Err.Clear
            Else
                msg = msg & Chr(10) & "IFace2.GetSelectByIDString = " & CStr(s)
            End If
            On Error GoTo 0
        End If
    End If

    MsgBox msg, vbInformation, "S-DISPATCH spike"
End Sub
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode", choices=["com", "vba"], default="com",
        help="com = drive SW from Python under each dispatch mode; "
             "vba = emit the .bas oracle.",
    )
    p.add_argument(
        "--skip-build", action="store_true",
        help="Probe the solid body already in the active part.",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_dispatch.bas"
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

    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
