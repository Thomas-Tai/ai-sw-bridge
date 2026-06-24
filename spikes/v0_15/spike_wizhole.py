"""
Spike v0.15 / S-WIZHOLE — IWizardHoleFeatureData2 marshaling + standards-DB probe.

THE load-bearing spike for Phase-1 HoleWizard (FR-1-04). Decides whether
out-of-process late binding can drive ``IWizardHoleFeatureData2`` through the
``CreateDefinition → set props → CreateFeature`` pipeline, AND whether the
target install's Toolbox standards DB responds to the standard/fastener-type/
size string triple the handler will emit.

Background
----------
HoleWizard is the #1 production machined feature: tapped holes, clearance
fits, countersinks, and counterbores — with their callouts flowing
automatically to drawings. The bridge spec maps::

    {"type":"hole_wizard", "standard":"ANSI Metric", "fastener":"Socket Head Cap Screw",
     "size":"M6", "fit":"Normal", "end_condition":"through_all"}

to::

    data = fm.CreateDefinition(swFmHoleWzd)  # int value unknown — scan required
    data.HoleType      = swWzdTap / swWzdCounterBore / …
    data.Standard      = "ANSI Metric"        # install-dependent DB string
    data.FastenerType  = "Socket Head Cap Screw"
    data.Size          = "M6"
    data.EndCondition  = swEndCondThroughAll
    # + placement: face + sketch-point pre-selected
    feat = fm.CreateFeature(data)             # the marshaling risk

Risks (T4 — highest marshaling risk class in the project):
- ``swFmHoleWzd`` integer value not in the decompiled CHM; must scan.
- ``IWizardHoleFeatureData2`` property read/write under late binding —
  each property is its own risk (SAFEARRAY, string, enum).
- ``Standard``/``FastenerType``/``Size`` strings are install-dependent
  (Toolbox/standards DB must be present on the seat); PARTIAL if absent.
- Placement requires face + sketch-point pre-selected, without triggering
  the Callout/SelectByID2 marshaling wall (the known-hostile OUT-IDispatch
  failure class — ``SelectByID2``, ``Select4``, ``GetErrorCode2`` all fail).

Verdict
-------
PASS    : All props settable, ``CreateFeature`` materializes a hole feature,
          ≥1 standard string accepted from the install.
          Phase-1 HoleWizard handler is out-of-process viable; build it.
PARTIAL : Data object accessible and props readable/writable, but either
          ``CreateFeature`` fails (marshaling wall at feature-creation level)
          OR no standard strings accepted (Toolbox absent — environment issue;
          retry on a Toolbox-enabled seat).
          Record which sub-probe is RED; orchestrator decides Route-B/C.
FAIL    : ``swFmHoleWzd`` not found in scan range (method unreachable or enum
          range wider than 0..127); or the SW feature manager is inaccessible.

Prereq: SOLIDWORKS running with a blank Part active.
        Toolbox add-in enabled for standards-string probe to pass.
        Pass ``--skip-build`` to skip creating the test box (use an
        already-open part that already has a solid body).

Usage
-----
    python spikes/v0_15/spike_wizhole.py
    python spikes/v0_15/spike_wizhole.py --skip-build --out report.json
    python spikes/v0_15/spike_wizhole.py --mode vba   # emit .bas oracle

NOTE: this spike intentionally leaves all VBA/early-binding cross-checks
in the --mode vba oracle so that a Python-PARTIAL / VBA-PASS split proves
the marshaler (not the SW API) is the wall — the Route-C signal.
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
# Box geometry (metres)
# ---------------------------------------------------------------------------
BOX_W_M = 0.020  # 20 mm x 20 mm footprint
BOX_H_M = 0.020
BOX_D_M = 0.010  # 10 mm tall — +z face at z=0.010

# Sketch-point placement for the test hole (sketch coords on +z face)
HOLE_U_M = 0.005  # 5 mm from centre → part X = 5 mm, Y = 0, Z = 10 mm

# Candidate standard strings to probe against the install's Toolbox DB.
# The bridge handler will need the exact strings the install accepts.
CANDIDATE_STANDARDS = [
    "ANSI Inch",
    "ANSI Metric",
    "ISO",
    "DIN",
    "JIS",
    "BSI",
    "PEM Metric",
    "PEM Inch",
    "Torx Plus",
]

# swWzdHoleTypes_e candidates — try all plausible values.
# SW docs: CounterBore=0, CounterSink=1, Hole=2, Tapered=3, Tap=4,
# Legacy=5, PipeTap=6, SlotStraightBottom=7  (probe, don't trust).
HOLE_TYPE_CANDIDATES = list(range(0, 8))

# swEndConditions_e candidates for the depth probe.
END_COND_THROUGH_ALL_CANDIDATES = [1, 2]  # probe both; 2 is typical swEndCondThroughAll
END_COND_BLIND = 0


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
        END_COND_BLIND,
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
# swFmHoleWzd discovery
# ---------------------------------------------------------------------------


def _is_wizhole_data(data: Any) -> bool:
    """Discriminate an IWizardHoleFeatureData* object from other CreateDefinition
    returns.  We probe `Standard` (a string property unique to wizard-hole data
    objects); on the wrong type it either raises a COM member-not-found error or
    returns a non-string.  We deliberately avoid calling Initialize() — that is
    for ISimpleFilletFeatureData2, not wizard-hole data.
    """
    try:
        val = data.Standard
        # A WizardHoleFeatureData object returns a string (possibly empty).
        return isinstance(val, str)
    except pywintypes.com_error:
        return False
    except Exception:
        return False


def scan_swFmHoleWzd(fm: Any, scan_range: int = 128) -> dict[str, Any]:
    """Probe CreateDefinition(i) for i in 0..scan_range to find swFmHoleWzd.

    The integer value is not in the decompiled CHM enum table — same discovery
    approach that found swFmFillet=1 in Spike P.
    """
    candidates: list[dict[str, Any]] = []
    winning_int: int | None = None
    winning_data: Any = None

    for v in range(scan_range):
        t0 = time.perf_counter()
        try:
            data = fm.CreateDefinition(v)
        except pywintypes.com_error:
            continue
        except Exception:
            continue
        if data is None:
            continue
        elapsed = (time.perf_counter() - t0) * 1000.0
        is_wiz = _is_wizhole_data(data)
        if is_wiz:
            # Read the default Standard string as a bonus data point.
            try:
                default_std = data.Standard
            except Exception:
                default_std = None
            candidates.append(
                {
                    "int_value": v,
                    "Standard_default": default_std,
                    "elapsed_ms": elapsed,
                }
            )
            if winning_int is None:
                winning_int = v
                winning_data = data

    return {
        "swFmHoleWzd_found": winning_int is not None,
        "swFmHoleWzd_int": winning_int,
        "_winning_data": winning_data,
        "all_candidates": candidates,
        "scan_range": scan_range,
    }


# ---------------------------------------------------------------------------
# IWizardHoleFeatureData2 property probes
# ---------------------------------------------------------------------------


def _probe_prop_rw(data: Any, prop: str, write_val: Any) -> dict[str, Any]:
    """Read then write-back a single property on the data object."""
    rec: dict[str, Any] = {"prop": prop}
    # Read
    t0 = time.perf_counter()
    try:
        read_val = getattr(data, prop)
        rec["read_status"] = "OK"
        rec["read_type"] = _type_tag(read_val)
        rec["read_value"] = (
            read_val if not isinstance(read_val, (bytes, bytearray)) else read_val.hex()
        )
    except pywintypes.com_error as e:
        rec["read_status"] = "COM_ERROR"
        rec["read_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
    except Exception as e:
        rec["read_status"] = "PY_EXCEPTION"
        rec["read_error"] = f"{type(e).__name__}: {e}"
    rec["read_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    # Write
    t0 = time.perf_counter()
    try:
        setattr(data, prop, write_val)
        # Read-back to confirm
        read_back = getattr(data, prop)
        rec["write_status"] = "OK"
        rec["write_readback"] = (
            read_back
            if not isinstance(read_back, (bytes, bytearray))
            else read_back.hex()
        )
    except pywintypes.com_error as e:
        rec["write_status"] = "COM_ERROR"
        rec["write_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
    except Exception as e:
        rec["write_status"] = "PY_EXCEPTION"
        rec["write_error"] = f"{type(e).__name__}: {e}"
    rec["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    return rec


def probe_data_object_props(data: Any) -> dict[str, Any]:
    """Probe read+write of every IWizardHoleFeatureData2 property the handler needs."""
    # Probe HoleType through all plausible enum values to find the correct int.
    hole_type_scan: list[dict[str, Any]] = []
    for ht in HOLE_TYPE_CANDIDATES:
        rec: dict[str, Any] = {"hole_type_int": ht}
        try:
            data.HoleType = ht
            try:
                readback = data.HoleType
                rec["status"] = "OK"
                rec["readback"] = readback
            except Exception as e:
                rec["status"] = "WRITE_OK_READ_FAIL"
                rec["read_error"] = f"{type(e).__name__}: {e}"
        except pywintypes.com_error as e:
            rec["status"] = "COM_ERROR"
            rec["error"] = (
                f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
            )
        except Exception as e:
            rec["status"] = "PY_EXCEPTION"
            rec["error"] = f"{type(e).__name__}: {e}"
        hole_type_scan.append(rec)

    props = [
        # (property_name, test_write_value)
        ("HoleType", 2),  # swWzdHole = simple drill (typically 2)
        ("Standard", "ANSI Metric"),
        ("FastenerType", "Socket Head Cap Screw"),
        ("Size", "M6"),
        ("EndCondition", END_COND_BLIND),  # blind — safe default
        ("Depth", 0.010),  # 10 mm
        ("DrillAngle", 0.0),
        ("ThreadDepth", 0.008),  # 8 mm
        ("CsinkAngle", 1.5707963),  # 90° in radians (π/2)
        ("CsinkDiameter", 0.012),  # 12 mm
        ("CounterBoreDiameter", 0.010),
        ("CounterBoreDepth", 0.005),
    ]
    prop_results = [_probe_prop_rw(data, name, val) for name, val in props]

    all_readable = all(r["read_status"] == "OK" for r in prop_results)
    all_writable = all(r["write_status"] == "OK" for r in prop_results)
    return {
        "hole_type_scan": hole_type_scan,
        "props": prop_results,
        "all_readable": all_readable,
        "all_writable": all_writable,
    }


# ---------------------------------------------------------------------------
# Standards DB probe
# ---------------------------------------------------------------------------


def probe_standard_strings(data: Any) -> dict[str, Any]:
    """Try setting data.Standard to each candidate string and record which work.

    The Standard/FastenerType/Size triple is install-dependent (Toolbox must be
    present).  This tells the handler which strings are safe to emit on this
    install.
    """
    results: list[dict[str, Any]] = []
    accepted: list[str] = []

    for std in CANDIDATE_STANDARDS:
        rec: dict[str, Any] = {"standard": std}
        t0 = time.perf_counter()
        try:
            data.Standard = std
            readback = data.Standard
            rec["status"] = "OK"
            rec["readback"] = readback
            accepted.append(std)
        except pywintypes.com_error as e:
            rec["status"] = "COM_ERROR"
            rec["error"] = (
                f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
            )
        except Exception as e:
            rec["status"] = "PY_EXCEPTION"
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        results.append(rec)

    return {
        "accepted_standards": accepted,
        "at_least_one_accepted": len(accepted) > 0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Placement probe: face + sketch-point selection
# ---------------------------------------------------------------------------


def _place_sketch_point_on_top_face(doc: Any) -> dict[str, Any]:
    """Open a 2D sketch on the +z face, drop one point, close it.

    Returns the name of the created sketch feature and whether the subsequent
    multi-select (face + SKETCHPOINT) works without triggering the Callout wall.
    """
    rec: dict[str, Any] = {}

    # Select the +z face (at z = BOX_D_M in part coords).
    doc.ClearSelection2(True)
    ok_face = doc.SelectByID("", "FACE", 0.0, 0.0, BOX_D_M)
    rec["face_select"] = ok_face
    if not ok_face:
        rec["error"] = "+z face selection failed; cannot create placement sketch"
        return rec

    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreatePoint(HOLE_U_M, 0.0, 0.0)  # sketch coords (5 mm, 0) → part (5,0,10) mm
    sm.InsertSketch(True)

    # Name the placement sketch for later re-selection.
    try:
        sk_feat = doc.FeatureByPositionReverse(0)
        if sk_feat is not None:
            sk_feat.Name = "SK_WizHole_Pos"
            rec["sketch_name"] = sk_feat.Name
            rec["sketch_type"] = sk_feat.GetTypeName2
    except Exception as e:
        rec["sketch_name_error"] = f"{type(e).__name__}: {e}"

    # Now probe multi-select: face + sketch point.  This is the Callout-wall test.
    # Strategy A: plain SelectByID for face, then IEntity.Select2 for the point
    # (the no-Callout form that the bridge already uses for edge selection).
    doc.ClearSelection2(True)
    ok_face2 = doc.SelectByID("", "FACE", 0.0, 0.0, BOX_D_M)
    rec["face_reselect"] = ok_face2

    # Get the sketch point entity via the sketch manager and use Select2(append, mark).
    sk_entity_select: dict[str, Any] = {}
    try:
        sk_feat2 = doc.GetEntityByName(
            "SK_WizHole_Pos", 26
        )  # swSelectType_e.swSelSKETCHES=26
    except Exception:
        sk_feat2 = None
    if sk_feat2 is None:
        # Fallback: get by position
        try:
            sk_feat2 = doc.FeatureByPositionReverse(0)
        except Exception:
            sk_feat2 = None

    if sk_feat2 is not None:
        try:
            sketch_obj = sk_feat2.GetSpecificFeature2
            pts = sketch_obj.GetSketchPoints2 if sketch_obj is not None else None
            if pts:
                pt = pts[0]
                try:
                    ok_pt = pt.Select2(True, 0)  # Append=True, Mark=0 (no Callout)
                    sk_entity_select["Select2_append"] = ok_pt
                except Exception as e:
                    sk_entity_select["Select2_error"] = f"{type(e).__name__}: {e}"
                    # Fallback: SelectByID SKETCHPOINT at part coordinates
                    try:
                        ok_pt2 = doc.SelectByID(
                            "", "SKETCHPOINT", HOLE_U_M, 0.0, BOX_D_M
                        )
                        sk_entity_select["SelectByID_fallback"] = ok_pt2
                    except Exception as e2:
                        sk_entity_select["SelectByID_fallback_error"] = (
                            f"{type(e2).__name__}: {e2}"
                        )
            else:
                sk_entity_select["sketch_points"] = "none found"
        except Exception as e:
            sk_entity_select["error"] = f"{type(e).__name__}: {e}"
    else:
        sk_entity_select["error"] = "sketch feature not found"

    rec["sketch_point_select"] = sk_entity_select

    # Report total selection count
    try:
        n_sel = doc.SelectionManager.GetSelectedObjectCount2(-1)
        types_sel = [
            doc.SelectionManager.GetSelectedObjectType3(i, -1)
            for i in range(1, n_sel + 1)
        ]
        rec["total_selected"] = n_sel
        rec["selected_types"] = types_sel
    except Exception as e:
        rec["selection_count_error"] = f"{type(e).__name__}: {e}"

    return rec


# ---------------------------------------------------------------------------
# CreateFeature probe
# ---------------------------------------------------------------------------


def probe_create_feature(fm: Any, data: Any, doc: Any) -> dict[str, Any]:
    """Attempt to materialize the wizard hole via CreateFeature(data).

    Pre-requisite: placement selection is in place (face + sketch point or
    face only as fallback).
    """
    rec: dict[str, Any] = {}

    # Configure data for a simple M6 through-all drill hole on ANSI Metric.
    # These are best-effort defaults — the prop-probe established what works.
    try:
        data.HoleType = 2  # swWzdHole (probe value — simple drill)
        data.Standard = "ANSI Metric"
        data.FastenerType = "Hex Bolt"
        data.Size = "M6"
        data.EndCondition = 1  # probe: might be swEndCondThroughAll
    except Exception as e:
        rec["data_setup_error"] = f"{type(e).__name__}: {e}"

    t0 = time.perf_counter()
    try:
        feat = fm.CreateFeature(data)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        if feat is None:
            rec["status"] = "NONE_RETURNED"
            rec["reason"] = "CreateFeature(data) returned None"
        else:
            rec["status"] = "OK"
            rec["feature_type"] = _type_tag(feat)
            try:
                rec["feature_name"] = feat.Name
                rec["feature_type_name"] = feat.GetTypeName2
            except Exception as e:
                rec["feature_attr_error"] = f"{type(e).__name__}: {e}"
            # Confirm the hole appears in the feature tree
            try:
                n_features = doc.GetFeatureCount
                rec["feature_count_after"] = n_features
            except Exception:
                pass
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

    return rec


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

    # Need at least one solid body to have a +z face.
    try:
        bodies = doc.GetBodies2(0, True)
        build_rec["body_count"] = len(bodies) if bodies else 0
    except Exception as e:
        build_rec["body_count_error"] = f"{type(e).__name__}: {e}"

    fm = doc.FeatureManager

    # 1. Discover swFmHoleWzd.
    scan = scan_swFmHoleWzd(fm)
    if not scan["swFmHoleWzd_found"]:
        return {
            "overall": "FAIL",
            "reason": (
                f"swFmHoleWzd not found by scanning CreateDefinition(0..{scan['scan_range']-1}); "
                "extend scan range or confirm HoleWizard is available on this install"
            ),
            "scan": {k: v for k, v in scan.items() if k != "_winning_data"},
            "build": build_rec,
        }
    data = scan["_winning_data"]

    # 2. Prop read/write probe.
    props_probe = probe_data_object_props(data)

    # 3. Standards DB probe.
    standards_probe = probe_standard_strings(data)

    # 4. Placement sketch + multi-select probe.
    placement_probe = _place_sketch_point_on_top_face(doc)

    # 5. CreateFeature probe (uses the placement selection left in place by step 4).
    create_feat_probe = probe_create_feature(fm, data, doc)

    # Derive overall verdict.
    feat_ok = create_feat_probe.get("status") == "OK"
    props_ok = props_probe["all_readable"] and props_probe["all_writable"]
    stds_ok = standards_probe["at_least_one_accepted"]

    if feat_ok and stds_ok:
        overall = "PASS"
    elif props_ok and not feat_ok:
        overall = "PARTIAL"  # props work, CreateFeature is the wall → T4 Route-C signal
    elif feat_ok and not stds_ok:
        overall = "PARTIAL"  # feature created but Toolbox absent → env issue
    else:
        overall = "PARTIAL" if props_ok else "FAIL"

    interpretation_map = {
        "PASS": (
            "IWizardHoleFeatureData2 props marshal out-of-process AND CreateFeature "
            "lands AND ≥1 standard string accepted → build Phase-1 hole_wizard handler"
        ),
        "PARTIAL": (
            "Data object accessible (props ok), but either CreateFeature failed "
            "(T4 marshaling wall → Route-C signal; run --mode vba to isolate) "
            "OR Toolbox DB absent (retry on a Toolbox-enabled seat)"
        ),
        "FAIL": (
            "swFmHoleWzd unreachable or CreateDefinition itself fails → "
            "Route-C or single-call fallback (SimpleHole2 for straight bores only)"
        ),
    }

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "interpretation": interpretation_map[overall],
        "swFmHoleWzd_int": scan["swFmHoleWzd_int"],
        "build": build_rec,
        "scan": {k: v for k, v in scan.items() if k != "_winning_data"},
        "props_probe": props_probe,
        "standards_probe": standards_probe,
        "placement_probe": placement_probe,
        "create_feature_probe": create_feat_probe,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding)
# ---------------------------------------------------------------------------


def emit_vba() -> str:
    """Early-binding oracle for the HoleWizard pipeline.

    If Python is PARTIAL (CreateFeature fails) but this VBA PASSes, the
    out-of-process late-binding marshaler (not the SW API) is the blocker
    → Route-C signal.  If VBA also fails, the API itself is the problem.
    """
    return r"""' Spike v0.15 S-WIZHOLE VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a 20x20x10 box on Front Plane (z from 0 to 10 mm).
' Creates a M6 ANSI Metric through-all hole at part position (5,0,10 mm).
' Early binding resolves IWizardHoleFeatureData2 and enum values natively,
' isolating whether a Python PARTIAL is a marshaling limitation.
Option Explicit
Sub ProbeWizardHole()
    Dim swApp       As SldWorks.SldWorks
    Dim Part        As SldWorks.ModelDoc2
    Dim fm          As SldWorks.FeatureManager
    Dim sm          As SldWorks.SketchManager
    Dim holeData    As SldWorks.WizardHoleFeatureData2
    Dim feat        As SldWorks.Feature

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sm    = Part.SketchManager

    ' --- placement sketch ---
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreatePoint 0.005, 0, 0
    sm.InsertSketch True

    ' --- hole data object ---
    Set holeData = fm.CreateDefinition(swFmHoleWzd)
    If holeData Is Nothing Then
        MsgBox "CreateDefinition(swFmHoleWzd) returned Nothing"
        Exit Sub
    End If

    holeData.HoleType      = swWzdHole            ' simple drill
    holeData.Standard      = "ANSI Metric"
    holeData.FastenerType  = "Hex Bolt"
    holeData.Size          = "M6"
    holeData.EndCondition  = swEndCondThroughAll

    ' --- re-select face + point ---
    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    Part.SelectByID2 "", "SKETCHPOINT", 0.005, 0, 0.01, True, 0, Nothing, 0

    ' --- create feature ---
    Set feat = fm.CreateFeature(holeData)
    If feat Is Nothing Then
        MsgBox "CreateFeature returned Nothing"
    Else
        MsgBox "VBA OK — feature: " & feat.Name & " type: " & feat.GetTypeName2
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
        help="Skip creating the test box; probe the first solid body already present.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_wizhole.bas"
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

    # PARTIAL exits 2 to distinguish the T4/Route-C signal from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
