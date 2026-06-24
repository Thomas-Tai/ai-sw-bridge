"""
Spike v0.15 / S-MATERIAL — SetMaterialPropertyName2 round-trip + mass-props honesty.

THE load-bearing spike for Phase-1 material assignment (FR-1-01,
docs/central_idea/api_coverage_roadmap.md §9). Decides whether out-of-process
late binding can assign a material to a part via
``IPartDoc.SetMaterialPropertyName2`` AND whether the assigned-material density
flows into mass properties (i.e., the calculation is not left on the SolidWorks
default-density fallback).

Background
----------
The bridge spec maps a top-level ``material`` field to::

    part_doc = doc  # IPartDoc
    part_doc.SetMaterialPropertyName2(config, db, name)

where ``config`` is the configuration name (empty string = all configs),
``db``   is the material-library database string (e.g. ``"SolidWorks Materials"``),
and ``name`` is the material display name (e.g. ``"AISI 1020 Steel"``).

Three distinct risks:
- T2 risk: ``SetMaterialPropertyName2`` may not be reachable via late binding
  (IPartDoc is a sub-interface; ``win32com.client.Dispatch`` may not resolve it).
  ``GetMaterialPropertyName2`` is the read-back proof.
- T3 risk: ``db`` and ``name`` strings are install-dependent (the material library
  must be present in the SOLIDWORKS installation).  PARTIAL if a candidate string
  is rejected.
- T3 risk: after assignment, ``IPartDoc.GetMassProperties2`` (or the legacy
  ``IModelDocExtension.GetMassProperties``) should reflect the assigned material's
  density, not the default 1000 kg/m³ fallback.  This is the "honesty" probe.

Verdict
-------
PASS    : ``SetMaterialPropertyName2`` sets the material for ≥1 candidate (db, name)
          pair, ``GetMaterialPropertyName2`` reads it back with identical strings,
          AND the post-assignment mass density differs from the pre-assignment
          fallback density (proving the material's density flows into mass props).
          Phase-1 ``material`` handler is out-of-process viable; build it.
PARTIAL : The material is set and read back correctly, but mass-props density does
          NOT change (the bridge can assign material metadata, but mass calculations
          will still use the geometry-default density). The fallback route — "carry
          material as a custom property only" — is active; record which sub-probe
          is RED. Orchestrator decides whether to ship the handler with a limitation
          or route differently.
FAIL    : ``SetMaterialPropertyName2`` is unreachable via late binding, or no
          candidate (db, name) pair is accepted by this install's material library.

Prereq: SOLIDWORKS running with a blank Part active.
        SOLIDWORKS default material library present (the standard install includes
        ``"SolidWorks Materials"``).
        Pass ``--skip-build`` to probe the solid body already in the active part.

Usage
-----
    python spikes/v0_15/spike_material.py
    python spikes/v0_15/spike_material.py --skip-build --out report.json
    python spikes/v0_15/spike_material.py --mode vba   # emit .bas early-binding oracle

NOTE: mass-props honesty is the decisive sub-probe for handler viability. A PASS on
assignment alone (read+write round-trip clean) with a FAIL on density-delta is
recorded as PARTIAL — the handler would set the metadata but not produce honest
mass calculations. The fallback (custom-property only) is explicitly called out in
the todolist as the RED route; this spike decides which route ships.
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


# ---------------------------------------------------------------------------
# Box geometry (metres) — same minimal solid as the other v0.15 spikes.
# ---------------------------------------------------------------------------
BOX_W_M = 0.020  # 20 mm x 20 mm footprint
BOX_H_M = 0.020
BOX_D_M = 0.010  # 10 mm tall

# Candidate (db, name) pairs to probe against this install's material library.
# The bridge handler will need to use the exact strings the install accepts.
# Ordered from most-likely-present to less common.
CANDIDATE_MATERIALS = [
    ("SolidWorks Materials", "AISI 1020 Steel (SS)"),
    ("SolidWorks Materials", "AISI 1020 Steel"),
    ("SolidWorks Materials", "Steel"),
    ("SolidWorks Materials", "Aluminum Alloy 1060"),
    ("SolidWorks Materials", "Copper"),
    ("SolidWorks Materials", "Nylon 6/10"),
    ("solidworks materials", "AISI 1020 Steel (SS)"),  # lower-case variant
    ("SolidWorks DIN Materials", "1.0402"),  # DIN library variant
]

# Default geometry-based density SOLIDWORKS uses before material is assigned
# (1000 kg/m³ — water). Density delta above this epsilon is the "honesty" probe.
_FALLBACK_DENSITY_KG_M3 = 1000.0
_DENSITY_DELTA_THRESHOLD = 50.0  # kg/m³ — intentionally loose; steel ~7800, Al ~2700


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


# ---------------------------------------------------------------------------
# Minimal solid fixture
# ---------------------------------------------------------------------------


def _build_box(doc: Any) -> dict[str, Any]:
    """Insert a 20×20×10 mm Boss-Extrude on the Front Plane."""
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


# ---------------------------------------------------------------------------
# Mass-properties helper
# ---------------------------------------------------------------------------


def _probe_mass_props(doc: Any) -> dict[str, Any]:
    """Read mass properties, returning density and raw output for the report.

    Tries ``IModelDocExtension.GetMassProperties2`` first (the current
    late-binding approach); falls back to the legacy form if unavailable.
    ``GetMassProperties2`` returns a SAFEARRAY:
        [0] = volume (m³), [1] = surface area (m²), [2] = mass (kg),
        [3..5] = CoM XYZ, [6..14] = inertia tensor (9 values)
    Density = mass / volume (kg/m³).
    """
    rec: dict[str, Any] = {}
    ext = doc.Extension
    t0 = time.perf_counter()
    try:
        # status=0 → default (not-overridden); accuracy=1 → normal
        props = ext.GetMassProperties2(0, 1, True)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["call"] = "GetMassProperties2"
        rec["return_type"] = _type_tag(props)
        if props is None:
            rec["status"] = "NONE_RETURNED"
            return rec
        # Convert SAFEARRAY-like result to a plain list for JSON serialisation.
        try:
            vals = list(props)
        except TypeError:
            vals = [props]
        rec["status"] = "OK"
        rec["raw"] = vals
        if len(vals) >= 3:
            volume_m3 = float(vals[0]) if vals[0] else None
            mass_kg = float(vals[2]) if vals[2] else None
            if volume_m3 and mass_kg and volume_m3 > 0:
                density = mass_kg / volume_m3
                rec["density_kg_m3"] = density
            else:
                rec["density_kg_m3"] = None
    except pywintypes.com_error as e:
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["status"] = "COM_ERROR"
        rec["hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["description"] = getattr(e, "strerror", str(e))
    except Exception as e:
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["status"] = "PY_EXCEPTION"
        rec["exception_type"] = type(e).__name__
        rec["message"] = str(e)
        # Fallback: legacy GetMassProperties (no status arg)
        t1 = time.perf_counter()
        try:
            props2 = doc.GetMassProperties()
            rec["fallback_call"] = "GetMassProperties"
            rec["fallback_type"] = _type_tag(props2)
            if props2 is not None:
                try:
                    vals2 = list(props2)
                except TypeError:
                    vals2 = [props2]
                rec["fallback_raw"] = vals2
                if len(vals2) >= 3 and vals2[0] and vals2[2] and float(vals2[0]) > 0:
                    rec["density_kg_m3"] = float(vals2[2]) / float(vals2[0])
        except Exception as e2:
            rec["fallback_error"] = f"{type(e2).__name__}: {e2}"
        rec["fallback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    return rec


# ---------------------------------------------------------------------------
# SetMaterialPropertyName2 / GetMaterialPropertyName2 probes
# ---------------------------------------------------------------------------


def _probe_set_material(doc: Any, config: str, db: str, name: str) -> dict[str, Any]:
    """Probe SetMaterialPropertyName2(config, db, name) and read-back."""
    rec: dict[str, Any] = {"config": config, "db": db, "name": name}

    t0 = time.perf_counter()
    try:
        ok = doc.SetMaterialPropertyName2(config, db, name)
        rec["set_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["set_status"] = "OK"
        rec["set_return_type"] = _type_tag(ok)
        rec["set_return_value"] = bool(ok) if isinstance(ok, (bool, int)) else str(ok)
    except pywintypes.com_error as e:
        rec["set_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["set_status"] = "COM_ERROR"
        rec["set_hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["set_description"] = getattr(e, "strerror", str(e))
        return rec
    except Exception as e:
        rec["set_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["set_status"] = "PY_EXCEPTION"
        rec["set_exception_type"] = type(e).__name__
        rec["set_message"] = str(e)
        return rec

    # Read-back: GetMaterialPropertyName2(config) → (db_readback, name_readback)
    # Under late binding this may return a tuple (db, name), or just the name,
    # or raise. Probe all shapes.
    t1 = time.perf_counter()
    try:
        rb = doc.GetMaterialPropertyName2(config)
        rec["get_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        rec["get_status"] = "OK"
        rec["get_return_type"] = _type_tag(rb)
        if isinstance(rb, (tuple, list)) and len(rb) >= 2:
            rec["get_db_readback"] = rb[0]
            rec["get_name_readback"] = rb[1]
            rec["roundtrip_db_match"] = str(rb[0]) == db
            rec["roundtrip_name_match"] = str(rb[1]) == name
        elif isinstance(rb, str):
            # Some late-binding shapes return only the name as a string.
            rec["get_name_readback"] = rb
            rec["roundtrip_name_match"] = rb == name
            rec["get_db_readback"] = None
            rec["roundtrip_db_match"] = None  # indeterminate
        else:
            rec["get_raw_value"] = str(rb)
            rec["roundtrip_db_match"] = None
            rec["roundtrip_name_match"] = None
    except pywintypes.com_error as e:
        rec["get_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        rec["get_status"] = "COM_ERROR"
        rec["get_hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["get_description"] = getattr(e, "strerror", str(e))
    except Exception as e:
        rec["get_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        rec["get_status"] = "PY_EXCEPTION"
        rec["get_exception_type"] = type(e).__name__
        rec["get_message"] = str(e)

    return rec


def probe_candidates(doc: Any) -> dict[str, Any]:
    """Try every candidate (db, name) pair; record which ones set and read back."""
    results: list[dict[str, Any]] = []
    first_working: dict[str, Any] | None = None

    for db, name in CANDIDATE_MATERIALS:
        rec = _probe_set_material(doc, "", db, name)  # config="" = all configs
        results.append(rec)
        if (
            first_working is None
            and rec.get("set_status") == "OK"
            and rec.get("set_return_value") is not False
        ):
            first_working = rec

    # Report the winning pair (if any) and whether the method is reachable at all.
    method_reachable = any(r.get("set_status") == "OK" for r in results)
    roundtrip_clean = (
        first_working is not None
        and first_working.get("get_status") == "OK"
        and first_working.get("roundtrip_name_match") is True
    )
    return {
        "method_reachable": method_reachable,
        "first_working_pair": (
            {"db": first_working["db"], "name": first_working["name"]}
            if first_working
            else None
        ),
        "roundtrip_clean": roundtrip_clean,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Top-level COM run
# ---------------------------------------------------------------------------


def run_com(skip_build: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build_rec: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        build_rec.update(_build_box(doc))
        if not build_rec.get("built"):
            return {
                "overall": "FAIL",
                "reason": "box did not build",
                "build": build_rec,
            }
        try:
            doc.EditRebuild3
        except Exception:
            pass

    # 1. Baseline mass props BEFORE material assignment.
    mass_pre = _probe_mass_props(doc)

    # 2. Probe SetMaterialPropertyName2 / GetMaterialPropertyName2.
    candidates_probe = probe_candidates(doc)

    # 3. Post-assignment mass props (only meaningful if assignment succeeded).
    mass_post: dict[str, Any] = {}
    if candidates_probe["method_reachable"] and candidates_probe["first_working_pair"]:
        # Re-apply the first working material to make sure it is currently active.
        fw = candidates_probe["first_working_pair"]
        try:
            doc.SetMaterialPropertyName2("", fw["db"], fw["name"])
        except Exception:
            pass
        mass_post = _probe_mass_props(doc)

    # 4. Density-delta check (the "honesty" probe).
    density_delta: dict[str, Any] = {}
    if (
        mass_pre.get("density_kg_m3") is not None
        and mass_post.get("density_kg_m3") is not None
    ):
        delta = abs(
            float(mass_post["density_kg_m3"]) - float(mass_pre["density_kg_m3"])
        )
        density_delta = {
            "pre_density_kg_m3": mass_pre["density_kg_m3"],
            "post_density_kg_m3": mass_post["density_kg_m3"],
            "delta_kg_m3": delta,
            "density_changed": delta > _DENSITY_DELTA_THRESHOLD,
        }
    else:
        density_delta = {
            "pre_density_kg_m3": mass_pre.get("density_kg_m3"),
            "post_density_kg_m3": mass_post.get("density_kg_m3"),
            "density_changed": None,  # indeterminate — mass-props call failed
            "reason": "mass-props density unreadable in pre or post measurement",
        }

    # 5. Derive overall verdict.
    method_ok = candidates_probe["method_reachable"]
    roundtrip_ok = candidates_probe["roundtrip_clean"]
    density_ok = density_delta.get("density_changed") is True

    if roundtrip_ok and density_ok:
        overall = "PASS"
    elif roundtrip_ok and not density_ok:
        # Assignment metadata works but mass-props density does not update.
        overall = "PARTIAL"
    elif method_ok and not roundtrip_ok:
        # Method reachable but no candidate pair accepted by this install's library.
        overall = "PARTIAL"
    else:
        overall = "FAIL"

    interpretation_map = {
        "PASS": (
            "SetMaterialPropertyName2 round-trips out-of-process AND assigned-material "
            "density flows into mass props → Phase-1 material handler is out-of-process "
            "viable; build it (P1.2)"
        ),
        "PARTIAL": (
            "Material metadata assigns (or method is reachable) BUT either: "
            "(a) mass-props density does not update after assignment — carry material "
            "as a custom property only (the documented RED fallback), or "
            "(b) no candidate (db, name) pair accepted — retry on a seat with the "
            "correct material-library strings. Run --mode vba to isolate whether "
            "the wall is the marshaler or the install's library."
        ),
        "FAIL": (
            "SetMaterialPropertyName2 unreachable via late binding, or IPartDoc "
            "sub-interface not resolvable out-of-process → custom-property fallback "
            "only; document in DEFERRED.md."
        ),
    }

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "interpretation": interpretation_map[overall],
        "build": build_rec,
        "mass_props_pre": mass_pre,
        "candidates_probe": candidates_probe,
        "mass_props_post": mass_post,
        "density_delta": density_delta,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding cross-check)
# ---------------------------------------------------------------------------


def emit_vba() -> str:
    """Early-binding oracle for the SetMaterialPropertyName2 round-trip.

    If Python is PARTIAL (method unreachable or density does not update) but
    this VBA PASSes, the out-of-process late-binding marshaler (not the SW API)
    is the blocker → Route-C signal. If VBA also fails, the API or the material
    library is the problem.
    """
    return r"""' Spike v0.15 S-MATERIAL VBA oracle.
' Paste into a Part-document module and press F5.
' Prereq: SOLIDWORKS running with a blank Part active (a solid body helps
' for mass-props honesty check, but is not required for assignment probe).
' Checks SetMaterialPropertyName2 + GetMaterialPropertyName2 + GetMassProperties2.
Option Explicit
Sub ProbeMaterialAssignment()
    Dim swApp   As SldWorks.SldWorks
    Dim Part    As SldWorks.PartDoc
    Dim ext     As SldWorks.ModelDocExtension
    Dim dbName  As String
    Dim matName As String
    Dim setOk   As Boolean
    Dim rb      As Variant
    Dim props   As Variant
    Dim density As Double
    Dim msg     As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set ext   = Part.Extension

    dbName  = "SolidWorks Materials"
    matName = "AISI 1020 Steel (SS)"

    ' --- Mass props BEFORE assignment ---
    props = Part.GetMassProperties2(0, 1, True)
    If IsEmpty(props) Or IsNull(props) Then
        msg = "GetMassProperties2 pre: (empty)"
    ElseIf UBound(props) >= 2 And CDbl(props(0)) > 0 Then
        density = CDbl(props(2)) / CDbl(props(0))
        msg = "Pre-assignment density: " & density & " kg/m3"
    Else
        msg = "Pre-assignment density: n/a"
    End If

    ' --- Assign material ---
    setOk = Part.SetMaterialPropertyName2("", dbName, matName)
    msg = msg & Chr(10) & "SetMaterialPropertyName2 returned: " & setOk

    ' --- Read-back ---
    rb = Part.GetMaterialPropertyName2("")
    If IsArray(rb) Then
        msg = msg & Chr(10) & "GetMaterialPropertyName2 db=" & rb(0) & " name=" & rb(1)
    Else
        msg = msg & Chr(10) & "GetMaterialPropertyName2 = " & rb
    End If

    ' --- Mass props AFTER assignment ---
    props = Part.GetMassProperties2(0, 1, True)
    If IsEmpty(props) Or IsNull(props) Then
        msg = msg & Chr(10) & "GetMassProperties2 post: (empty)"
    ElseIf UBound(props) >= 2 And CDbl(props(0)) > 0 Then
        density = CDbl(props(2)) / CDbl(props(0))
        msg = msg & Chr(10) & "Post-assignment density: " & density & " kg/m3"
    Else
        msg = msg & Chr(10) & "Post-assignment density: n/a"
    End If

    MsgBox msg, vbInformation, "S-MATERIAL spike"
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
        help="Skip creating the test box; probe the solid body already in the active part.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_material.bas"
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

    # PARTIAL exits 2 to distinguish the Route-C / fallback signal from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
