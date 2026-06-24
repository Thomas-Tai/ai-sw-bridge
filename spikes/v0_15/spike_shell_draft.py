"""
Spike v0.15 / S-SHELL / S-DRAFT — InsertFeatureShell and InsertDraft2 marshaling.

Two Phase-1 dress-up feature spikes bundled in one harness (spec.md §5.5,
FR-1-05).  Each is probed independently; a PARTIAL on one does not block the
other (the todolist says "defer the failing one").

Background
----------
**Shell** (``InsertFeatureShell``) — hollows out a solid body by removing
pre-selected faces and offsetting the remaining walls inward by a uniform
thickness.  The API surface is simple::

    feat = fm.InsertFeatureShell(
        Thickness,      # double — wall thickness in metres
        AutoRelease,    # VARIANT_BOOL — TRUE releases faces after shell
    )

Pre-selection is by coordinate (``SelectByID``, FACE type at a known point
on the target face).  Tier T2 — single-call, two args, no OUT params or
Callout.  Risk: arity confirmation (2-arg vs. a 3-arg variant on newer SW).

**Draft** (``InsertDraft2``) — tapers selected faces at a given angle
relative to a neutral plane.  The API surface::

    feat = fm.InsertDraft2(
        Angle,              # double — draft angle in radians
        OtherSide,          # VARIANT_BOOL — draft direction
        ReverseDir,         # VARIANT_BOOL — reverse pull direction
        StepFace,           # VARIANT_BOOL — use step face
        StepFaceThickness,  # double — step-face thickness (m)
        Propagate,          # VARIANT_BOOL — propagate to tangent faces
        DraftAngle2,        # double — second-side angle (rad)
    )

Pre-selection is the neutral plane (``SelectByID``, PLANE) plus the face(s)
to draft (``IEntity.Select2`` append, or ``SelectByID`` at a face coord).
Tier T2–T3 — single call but 7 mixed bool/double args, and the multi-select
(neutral plane + face) is the selection-marshaling risk.

Verdict
-------
PASS    : both shell and draft return non-None features; arity confirmed.
          Phase-1 shell and draft handlers are out-of-process viable.
PARTIAL : ≥1 succeeds, ≥1 fails.  Defer the failing one per todolist;
          proceed with the passing one.  Record which failed.
FAIL    : both fail.  API signatures unreachable via late binding.

Prereq: SOLIDWORKS running with a blank Part active.
        Pass --skip-build to probe a solid body already present in the
        active part (shell probe only; draft probe always builds fresh).

Usage
-----
    python spikes/v0_15/spike_shell_draft.py
    python spikes/v0_15/spike_shell_draft.py --out report.json
    python spikes/v0_15/spike_shell_draft.py --mode vba   # emit .bas oracle
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
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc, SW_DOC_PART  # noqa: E402


# ---------------------------------------------------------------------------
# Box geometry (metres)
# ---------------------------------------------------------------------------
BOX_W_M = 0.020  # 20 mm wide  (X)
BOX_H_M = 0.020  # 20 mm tall  (Y)
BOX_D_M = 0.010  # 10 mm deep  (Z) — +z face at z=0.010

# Shell wall thickness for the probe call.
SHELL_THICKNESS_M = 0.002  # 2 mm

# Draft angle for the probe call (radians).
DRAFT_ANGLE_RAD = math.radians(5.0)  # 5°


def _type_tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _ensure_part_doc(sw: Any) -> Any:
    doc = get_active_doc(sw)
    if doc is None:
        raise RuntimeError("no active document; open a blank Part first")
    if doc.GetType != SW_DOC_PART:
        raise RuntimeError(
            f"active doc is not a Part (GetType={doc.GetType!r}); open a blank Part"
        )
    return doc


def _build_box(doc: Any) -> dict[str, Any]:
    """Insert a 20×20×10 mm Boss-Extrude on the Front Plane.

    Mirrors spike_persist_reference.py / spike_wizhole.py conventions:
    legacy 5-arg SelectByID, 23/22-arg FeatureExtrusion2 fallback.
    """
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2,
        -BOX_H_M / 2,
        0.0,
        BOX_W_M / 2,
        BOX_H_M / 2,
        0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)

    fm = doc.FeatureManager
    base_args = (
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
        feat = fm.FeatureExtrusion2(*base_args, False)  # 23-arg
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)  # 22-arg fallback
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _first_body(doc: Any) -> Any:
    bodies = doc.GetBodies2(0, True)  # swSolidBody=0
    if not bodies:
        return None
    return bodies[0]


# ---------------------------------------------------------------------------
# InsertFeatureShell probe
# ---------------------------------------------------------------------------


def _probe_shell(fm: Any, doc: Any) -> dict[str, Any]:
    """Probe InsertFeatureShell arity and marshaling.

    1. Build a fresh 20×20×10 mm box.
    2. Pre-select the +z face by coordinate (SelectByID FACE at the face
       centre, z = BOX_D_M).
    3. Call InsertFeatureShell with 2-arg (thickness, autoRelease).
    4. Record whether a non-None feature was returned and the arity form
       that worked.
    """
    rec: dict[str, Any] = {}

    build = _build_box(doc)
    rec["build"] = build
    if not build.get("built"):
        rec["verdict"] = "FAIL"
        rec["reason"] = f"box did not build: {build.get('error')}"
        return rec

    try:
        doc.EditRebuild3
    except Exception:
        pass

    # Pre-select the +z face (at z = BOX_D_M in part coords).
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.0, 0.0, BOX_D_M)
    rec["face_select"] = bool(ok)
    if not ok:
        rec["verdict"] = "FAIL"
        rec["reason"] = "+z face SelectByID returned False"
        return rec

    # --- Try 2-arg form (expected canonical signature) ---
    t0 = time.perf_counter()
    feat = None
    try:
        feat = fm.InsertFeatureShell(SHELL_THICKNESS_M, True)
        rec["call_form"] = "2-arg(thickness, autoRelease)"
    except pywintypes.com_error as e:
        rec["call_form"] = "2-arg(thickness, autoRelease)"
        rec["com_error"] = {
            "hresult": f"{getattr(e, 'hresult', None):#010x}",
            "description": getattr(e, "strerror", str(e)),
        }
    except Exception as e:
        rec["call_form"] = "2-arg(thickness, autoRelease)"
        rec["py_exception"] = f"{type(e).__name__}: {e}"
    rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    if feat is not None:
        rec["verdict"] = "GREEN"
        rec["feature_type"] = _type_tag(feat)
        try:
            rec["feature_name"] = feat.Name
        except Exception:
            pass
        try:
            rec["feature_type_name"] = feat.GetTypeName2
        except Exception:
            pass
    else:
        rec["verdict"] = "FAIL"
        if "com_error" not in rec and "py_exception" not in rec:
            rec["reason"] = "InsertFeatureShell returned None"
        else:
            rec["reason"] = rec.get("com_error", {}).get("description") or rec.get(
                "py_exception", "unknown error"
            )

    return rec


# ---------------------------------------------------------------------------
# InsertDraft2 probe
# ---------------------------------------------------------------------------


def _probe_draft(fm: Any, doc: Any) -> dict[str, Any]:
    """Probe InsertDraft2 arity and marshaling.

    1. Build a fresh 20×20×10 mm box (the shell probe may have shelled
       the previous one, so we always rebuild here).
    2. Select the Front Plane as the neutral plane (SelectByID PLANE).
    3. Append the +z face for drafting (SelectByID FACE, or
       IEntity.Select2 append if available from GetFaces).
    4. Call InsertDraft2 with the standard 7-arg form.  Fallback: try
       a 6-arg form (omitting DraftAngle2) if the 7-arg raises arity.
    5. Record whether a non-None feature was returned.
    """
    rec: dict[str, Any] = {}

    build = _build_box(doc)
    rec["build"] = build
    if not build.get("built"):
        rec["verdict"] = "FAIL"
        rec["reason"] = f"box did not build: {build.get('error')}"
        return rec

    try:
        doc.EditRebuild3
    except Exception:
        pass

    # --- Neutral-plane selection ---
    doc.ClearSelection2(True)
    ok_plane = doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    rec["neutral_plane_select"] = bool(ok_plane)
    if not ok_plane:
        rec["verdict"] = "FAIL"
        rec["reason"] = "Front Plane SelectByID returned False"
        return rec

    # --- Append the +z face for drafting ---
    # Strategy A: SelectByID at the face centre with the legacy 5-arg form.
    # This does NOT have an explicit "append" flag — on SW 2024 it appends
    # to the current selection by default when entities are already selected.
    ok_face = doc.SelectByID("", "FACE", 0.0, 0.0, BOX_D_M)
    rec["face_select_by_id"] = bool(ok_face)

    if not ok_face:
        # Strategy B: get the face entity from the body and use Select2.
        body = _first_body(doc)
        faces = list(body.GetFaces() or []) if body else []
        rec["total_faces"] = len(faces)
        appended = False
        for f in faces:
            try:
                n = f.Normal
                if n and abs(float(n[2])) > 0.99:
                    ok_sel = f.Select2(True, 0)  # Append=True, Mark=0
                    if ok_sel:
                        appended = True
                        rec["face_select_strategy"] = "Select2"
                        break
            except Exception:
                continue
        if not appended:
            rec["verdict"] = "FAIL"
            rec["reason"] = "could not append +z face to selection for draft"
            return rec
    else:
        rec["face_select_strategy"] = "SelectByID"

    # Record selection count before the call.
    try:
        n_sel = doc.SelectionManager.GetSelectedObjectCount2(-1)
        rec["selection_count_before_call"] = n_sel
        rec["selected_types_before_call"] = [
            doc.SelectionManager.GetSelectedObjectType3(i, -1)
            for i in range(1, n_sel + 1)
        ]
    except Exception as e:
        rec["selection_count_error"] = f"{type(e).__name__}: {e}"

    # --- Try 7-arg form (expected canonical signature) ---
    args_7 = (
        DRAFT_ANGLE_RAD,  # Angle (rad)
        False,  # OtherSide
        False,  # ReverseDir
        False,  # StepFace
        0.0,  # StepFaceThickness
        True,  # Propagate to tangent faces
        DRAFT_ANGLE_RAD,  # DraftAngle2 (same angle both sides)
    )

    t0 = time.perf_counter()
    feat = None
    call_form = "7-arg"
    try:
        feat = fm.InsertDraft2(*args_7)
    except pywintypes.com_error as e:
        rec["com_error_7arg"] = {
            "hresult": f"{getattr(e, 'hresult', None):#010x}",
            "description": getattr(e, "strerror", str(e)),
        }
        # Fallback: try 6-arg (drop DraftAngle2).
        t1 = time.perf_counter()
        try:
            feat = fm.InsertDraft2(*args_7[:6])
            call_form = "6-arg (fallback, no DraftAngle2)"
        except Exception:
            pass
        rec["fallback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    except Exception as e:
        rec["py_exception_7arg"] = f"{type(e).__name__}: {e}"
        # Fallback: try 6-arg.
        t1 = time.perf_counter()
        try:
            feat = fm.InsertDraft2(*args_7[:6])
            call_form = "6-arg (fallback, no DraftAngle2)"
        except Exception:
            pass
        rec["fallback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    rec["call_form"] = call_form
    rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    if feat is not None:
        rec["verdict"] = "GREEN"
        rec["feature_type"] = _type_tag(feat)
        try:
            rec["feature_name"] = feat.Name
        except Exception:
            pass
        try:
            rec["feature_type_name"] = feat.GetTypeName2
        except Exception:
            pass
    else:
        rec["verdict"] = "FAIL"
        err = rec.get("com_error_7arg", {}).get("description") or rec.get(
            "py_exception_7arg", "unknown error"
        )
        rec["reason"] = f"InsertDraft2 returned None in all forms ({err})"

    return rec


# ---------------------------------------------------------------------------
# Top-level COM run
# ---------------------------------------------------------------------------


def run_com(skip_build: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build_rec: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        # Build a box so there is a solid body for the shell probe.
        build_rec.update(_build_box(doc))
        if not build_rec.get("built"):
            return {
                "overall": "FAIL",
                "reason": "initial box did not build",
                "build": build_rec,
            }
        try:
            doc.EditRebuild3
        except Exception:
            pass

    body = _first_body(doc)
    if body is None and not skip_build:
        return {
            "overall": "FAIL",
            "reason": "no solid body after build",
            "build": build_rec,
        }

    fm = doc.FeatureManager

    # Probe 1: Shell — builds its own box internally.
    shell_result = _probe_shell(fm, doc)

    # Probe 2: Draft — builds its own box internally.
    draft_result = _probe_draft(fm, doc)

    # Aggregate verdicts.
    sv = shell_result.get("verdict")
    dv = draft_result.get("verdict")
    if sv == "GREEN" and dv == "GREEN":
        overall = "PASS"
    elif sv == "GREEN" or dv == "GREEN":
        overall = "PARTIAL"
    else:
        overall = "FAIL"

    interpretation_map = {
        "PASS": (
            "Both InsertFeatureShell and InsertDraft2 succeed out-of-process → "
            "build Phase-1 shell and draft handlers"
        ),
        "PARTIAL": (
            f"One succeeded ({sv=}, {dv=}); defer the failing one per todolist "
            "and proceed with the passing one"
        ),
        "FAIL": (
            "Both InsertFeatureShell and InsertDraft2 failed → "
            "API signatures unreachable via late binding; escalate"
        ),
    }

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "interpretation": interpretation_map[overall],
        "shell": shell_result,
        "draft": draft_result,
        "build": build_rec,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding)
# ---------------------------------------------------------------------------


def emit_vba() -> str:
    """Early-binding oracle for the Shell + Draft round-trips.

    If Python is PARTIAL/FAIL but this VBA PASSes, the out-of-process
    late-binding marshaler (not the SW API) is the blocker → Route-C signal.
    If VBA also fails, the API arity/signature is the problem.
    """
    return r"""' Spike v0.15 S-SHELL/DRAFT VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: blank Part active.  Creates two boxes (one for each probe).
' Early binding resolves arg types natively, isolating whether a Python
' PARTIAL is a marshaling limitation rather than an API one.
Option Explicit

Private Const BOX_W As Double = 0.02   ' 20 mm
Private Const BOX_H As Double = 0.02   ' 20 mm
Private Const BOX_D As Double = 0.01   ' 10 mm

Sub ProbeShellAndDraft()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim sk    As SldWorks.SketchManager
    Dim feat  As SldWorks.Feature

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sk    = Part.SketchManager

    ' ===== SHELL PROBE =====
    ' Build a 20x20x10 box on the Front Plane.
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sk.InsertSketch True
    sk.CreateCornerRectangle -BOX_W / 2, -BOX_H / 2, 0, BOX_W / 2, BOX_H / 2, 0
    sk.InsertSketch True
    Set feat = fm.FeatureExtrusion2( _
        True, False, False, 0, 0, BOX_D, 0#, _
        False, False, False, False, 0#, 0#, _
        False, False, False, False, True, True, True, 0, 0#, False)
    If feat Is Nothing Then
        MsgBox "Shell: box build FAILED": GoTo DraftProbe
    End If

    ' Select the +z face and shell it.
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, BOX_D, False, 0, Nothing, 0
    Set feat = fm.InsertFeatureShell(0.002, True)   ' 2 mm wall
    If feat Is Nothing Then
        MsgBox "Shell FAIL: InsertFeatureShell returned Nothing"
    Else
        MsgBox "Shell PASS: " & feat.Name & " (" & feat.GetTypeName2 & ")"
    End If

DraftProbe:
    ' ===== DRAFT PROBE =====
    ' Build a fresh box (the shell probe hollowed the previous one).
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sk.InsertSketch True
    sk.CreateCornerRectangle -BOX_W / 2, -BOX_H / 2, 0, BOX_W / 2, BOX_H / 2, 0
    sk.InsertSketch True
    Set feat = fm.FeatureExtrusion2( _
        True, False, False, 0, 0, BOX_D, 0#, _
        False, False, False, False, 0#, 0#, _
        False, False, False, False, True, True, True, 0, 0#, False)
    If feat Is Nothing Then
        MsgBox "Draft: box build FAILED": Exit Sub
    End If

    ' Select Front Plane (neutral) + +z face (to draft).
    Part.ClearSelection2 True
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    Part.SelectByID2 "", "FACE", 0, 0, BOX_D, True, 0, Nothing, 0

    ' 5° draft angle.
    Dim ang As Double: ang = 5# * 3.14159265358979 / 180#
    Set feat = fm.InsertDraft2(ang, False, False, False, 0#, True, ang)
    If feat Is Nothing Then
        MsgBox "Draft FAIL: InsertDraft2 returned Nothing"
    Else
        MsgBox "Draft PASS: " & feat.Name & " (" & feat.GetTypeName2 & ")"
    End If
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
        "--mode",
        choices=["com", "vba"],
        default="com",
        help="com = drive SW from Python; vba = emit the .bas oracle.",
    )
    p.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip creating the initial test box; probe the first solid "
        "body already present in the active part.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_shell_draft.bas"
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

    # PARTIAL exits 2 to distinguish from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
