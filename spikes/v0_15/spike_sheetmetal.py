"""
Spike v0.15 / S-SHEETMETAL — InsertSheetMetalBaseFlange2 + flat-pattern probe.

THE load-bearing spike for Phase-3 sheet metal (FR-3-01). Decides whether
out-of-process late binding can drive ``InsertSheetMetalBaseFlange2`` with
gauge / bend-radius / k-factor args, AND whether the resulting flat-pattern
config and body are accessible — including the flat-pattern DXF export path
(``ExportToDWG2``).

Background
----------
Sheet metal is a stateful multi-call feature.  The sequence the handler must
drive is::

    # 1. Sketch a profile (rectangle on Front Plane).
    # 2. Call InsertSheetMetalBaseFlange2 — this is the primary risk call:
    #       doc.FeatureManager.InsertSheetMetalBaseFlange2(
    #           thickness,    # float (m) — wall thickness / gauge
    #           reverse,      # bool  — extrude direction
    #           bend_radius,  # float (m)
    #           k_factor,     # float — sheet-metal k-factor (0.0–1.0)
    #           relief_type,  # int   — swSheetMetalReliefType_e
    #           relief_w,     # float (m) — rectangular relief width
    #           relief_d,     # float (m) — rectangular relief depth
    #           relief_ratio, # float — oblong/tear relief ratio
    #           auto_relief,  # bool  — use auto relief
    #           form_feature, # bool  — use form feature on bend
    #           merge_result, # bool  — merge with existing body
    #       )
    # 3. Retrieve the flat-pattern configuration via
    #       doc.GetConfigurationByName("Flat Pattern(1)")  (name may vary)
    #    OR activate it via doc.ShowConfiguration2("Flat Pattern(1)").
    # 4. Get the flat body from GetBodies2(swSheetMetalFlattenedBody).
    # 5. Probe ExportToDWG2 for the flat-pattern DXF path (P1.1 export table).

Arity risk: ``InsertSheetMetalBaseFlange2`` is a 11-arg call.  The project
has encountered arity splits on SW yearly releases (FeatureCut4, FeatureRevolve2)
— so both 11-arg and a 10-arg fallback are tried.  The exact arg shape is
recorded in the report so the handler can version-route via X4.

Flat-pattern risk: the flat-pattern config name is locale-dependent ("Flat
Pattern(1)" in English; may differ on non-English installs).  This spike
scans all configuration names and flags the match (or absence).

ExportToDWG2 risk: the call signature is
    ``ext.ExportToDWG2(path, doc, exportType, exportAllSheets, alignment,
                       useTemplatSize, pdfPages, insertionPoint, scaleFactor)``
and carries its own OUT-param / SAFEARRAY risk.  Probe it here alongside the
flat-pattern activation so one seat session covers both.

Verdict
-------
PASS    : ``InsertSheetMetalBaseFlange2`` materializes a sheet-metal body,
          flat-pattern config is reachable by name, flat body is accessible,
          AND ``ExportToDWG2`` succeeds (or at least does not raise a COM error
          — a None return is still PASS-with-warning if the file is created).
          Phase-3 sheet metal handler is out-of-process viable; build it.
PARTIAL : Base flange creates a body but one downstream step fails:
          flat-pattern config absent/unreachable (locale issue or SW SKU limit),
          OR ExportToDWG2 raises a marshaling error.
          Record which sub-probe is RED; orchestrator decides Route-B/C.
FAIL    : ``InsertSheetMetalBaseFlange2`` returns None or raises (arity
          unknown / method unreachable via late binding).

Prereq: SOLIDWORKS running with a blank Part active.
        Sheet Metal add-in enabled (required for flat-pattern config and DXF).
        Pass ``--skip-build`` to probe a sheet-metal part already open.

Usage
-----
    python spikes/v0_15/spike_sheetmetal.py
    python spikes/v0_15/spike_sheetmetal.py --skip-build --out report.json
    python spikes/v0_15/spike_sheetmetal.py --mode vba   # emit .bas oracle

NOTE: the flat-pattern DXF export writes to a temp path that is cleaned up
after the probe.  Pass ``--keep-files`` to retain it for manual inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc, SW_DOC_PART  # noqa: E402


# ---------------------------------------------------------------------------
# Sheet metal geometry constants (metres)
# ---------------------------------------------------------------------------

# Profile sketch: 60 mm × 40 mm rectangle on Front Plane.
PROFILE_W_M = 0.060
PROFILE_H_M = 0.040

# Base flange call args — all probe-grade "safe" values.
SM_THICKNESS_M = 0.0015    # 1.5 mm wall / gauge-equivalent
SM_REVERSE = False         # extrude in +z direction
SM_BEND_RADIUS_M = 0.0015  # 1.5 mm bend radius (equals thickness — common default)
SM_K_FACTOR = 0.44         # industry default k-factor for mild steel
SM_RELIEF_TYPE = 0         # swReliefRectangular = 0 (probe default; scan if needed)
SM_RELIEF_W_M = 0.00125    # 1.25 mm relief width
SM_RELIEF_D_M = 0.00125    # 1.25 mm relief depth
SM_RELIEF_RATIO = 0.5      # oblong/tear relief ratio (unused for rectangular, still passed)
SM_AUTO_RELIEF = True      # let SW calculate relief geometry
SM_FORM_FEATURE = False    # no form feature on bend
SM_MERGE_RESULT = True     # merge into single body

# swBodyType_e for flat sheet-metal body (value 9).
# swSolidBody=0 is the general form; 9 = swSheetMetalFlattenedBody.
SW_BODY_SOLID = 0
SW_BODY_SHEET_METAL_FLAT = 9

# Expected flat-pattern config name prefix (EN-US locale).
FLAT_PATTERN_NAME_PREFIX = "Flat Pattern"

# swExportToDWG_e — export type for DXF/DWG.
# Value 4 = swExportToDWG_ExportSheetMetal (flat-pattern sheet metal DXF).
SW_DWG_EXPORT_SHEETMETAL = 4


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
# Test fixture: sketch profile for base flange
# ---------------------------------------------------------------------------

def _build_profile_sketch(doc: Any) -> dict[str, Any]:
    """Open a profile sketch on Front Plane; leave it open for InsertSheetMetalBaseFlange2.

    InsertSheetMetalBaseFlange2 consumes the open sketch (like FeatureExtrusion2),
    so the sketch must NOT be closed before the call.
    """
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -PROFILE_W_M / 2, -PROFILE_H_M / 2, 0.0,
        PROFILE_W_M / 2,  PROFILE_H_M / 2,  0.0,
    )
    if seg is None:
        sk.InsertSketch(True)  # close the empty sketch so the doc is consistent
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    # Sketch is left OPEN — InsertSheetMetalBaseFlange2 expects it.
    return {"built": True}


# ---------------------------------------------------------------------------
# Base flange probe
# ---------------------------------------------------------------------------

def _probe_base_flange(fm: Any) -> dict[str, Any]:
    """Try InsertSheetMetalBaseFlange2 with the 11-arg and 10-arg arities.

    Both attempts are made in order; the first non-None return wins.
    Recording the winning arity is the primary data point for the handler's
    version-routing decision (X4).
    """
    base_11 = (
        SM_THICKNESS_M,
        SM_REVERSE,
        SM_BEND_RADIUS_M,
        SM_K_FACTOR,
        SM_RELIEF_TYPE,
        SM_RELIEF_W_M,
        SM_RELIEF_D_M,
        SM_RELIEF_RATIO,
        SM_AUTO_RELIEF,
        SM_FORM_FEATURE,
        SM_MERGE_RESULT,
    )
    # 10-arg form: drop merge_result (some SW versions omit it).
    base_10 = base_11[:10]

    arities = [
        ("11-arg", base_11),
        ("10-arg", base_10),
    ]

    attempts: list[dict[str, Any]] = []
    winning_feat: Any = None
    winning_arity: str | None = None

    for label, args in arities:
        t0 = time.perf_counter()
        try:
            feat = fm.InsertSheetMetalBaseFlange2(*args)
        except pywintypes.com_error as e:
            attempts.append({
                "arity": label,
                "status": "COM_ERROR",
                "hresult": f"{getattr(e, 'hresult', None):#010x}",
                "description": getattr(e, "strerror", str(e)),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            })
            continue
        except Exception as e:
            attempts.append({
                "arity": label,
                "status": "PY_EXCEPTION",
                "exception_type": type(e).__name__,
                "message": str(e),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            })
            continue
        elapsed = (time.perf_counter() - t0) * 1000.0
        if feat is None:
            attempts.append({
                "arity": label,
                "status": "NONE_RETURNED",
                "elapsed_ms": elapsed,
            })
        else:
            rec: dict[str, Any] = {
                "arity": label,
                "status": "OK",
                "elapsed_ms": elapsed,
                "feature_type": _type_tag(feat),
            }
            try:
                rec["feature_name"] = feat.Name
                rec["feature_type_name"] = feat.GetTypeName2
            except Exception as e:
                rec["feature_attr_error"] = f"{type(e).__name__}: {e}"
            attempts.append(rec)
            if winning_feat is None:
                winning_feat = feat
                winning_arity = label
            break  # first working arity wins

    return {
        "winning_arity": winning_arity,
        "_feat": winning_feat,
        "attempts": attempts,
    }


# ---------------------------------------------------------------------------
# Arg / return type-tag probe
# ---------------------------------------------------------------------------

def _probe_flange_args(feat: Any) -> dict[str, Any]:
    """Read back the base flange feature data to confirm arg round-trip.

    Uses IFeature.GetDefinition() → ISheetMetalBaseFlange (if available) to
    read thickness / bend-radius / k-factor back from the feature.  This is
    the write-then-read confirmation.  Also records the types of all returned
    values.
    """
    rec: dict[str, Any] = {}

    # Try GetDefinition — not always available via late binding for sheet metal.
    t0 = time.perf_counter()
    try:
        defn = feat.GetDefinition()
        rec["GetDefinition_status"] = "OK"
        rec["GetDefinition_type"] = _type_tag(defn)
    except pywintypes.com_error as e:
        rec["GetDefinition_status"] = "COM_ERROR"
        rec["GetDefinition_error"] = f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        defn = None
    except Exception as e:
        rec["GetDefinition_status"] = "PY_EXCEPTION"
        rec["GetDefinition_error"] = f"{type(e).__name__}: {e}"
        defn = None
    rec["GetDefinition_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    if defn is not None:
        # Probe the thickness / bend-radius / k-factor fields.
        for attr, label in [
            ("Thickness", "thickness"),
            ("BendRadius", "bend_radius"),
            ("KFactor", "k_factor"),
            ("ReliefType", "relief_type"),
        ]:
            t0 = time.perf_counter()
            try:
                val = getattr(defn, attr)
                rec[f"{label}_read_type"] = _type_tag(val)
                rec[f"{label}_read_value"] = val
                rec[f"{label}_read_status"] = "OK"
            except pywintypes.com_error as e:
                rec[f"{label}_read_status"] = "COM_ERROR"
                rec[f"{label}_read_error"] = f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
            except Exception as e:
                rec[f"{label}_read_status"] = "PY_EXCEPTION"
                rec[f"{label}_read_error"] = f"{type(e).__name__}: {e}"
            rec[f"{label}_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    return rec


# ---------------------------------------------------------------------------
# Flat-pattern config probe
# ---------------------------------------------------------------------------

def _probe_flat_pattern_config(doc: Any) -> dict[str, Any]:
    """Scan all configs for the flat-pattern config and activate it.

    The flat-pattern config is auto-created by SW on a sheet-metal base flange.
    Its exact name is locale-dependent; we scan all configuration names and
    match against FLAT_PATTERN_NAME_PREFIX.
    """
    rec: dict[str, Any] = {}

    # List all configuration names.
    t0 = time.perf_counter()
    try:
        names = doc.GetConfigurationNames()
        rec["config_names"] = list(names) if names else []
        rec["config_count"] = len(rec["config_names"])
    except pywintypes.com_error as e:
        rec["GetConfigurationNames_status"] = "COM_ERROR"
        rec["GetConfigurationNames_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
        rec["config_names"] = []
    except Exception as e:
        rec["GetConfigurationNames_status"] = "PY_EXCEPTION"
        rec["GetConfigurationNames_error"] = f"{type(e).__name__}: {e}"
        rec["config_names"] = []
    rec["GetConfigurationNames_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    # Identify the flat-pattern config.
    flat_name: str | None = None
    for name in rec["config_names"]:
        if str(name).startswith(FLAT_PATTERN_NAME_PREFIX):
            flat_name = str(name)
            break
    rec["flat_pattern_config_name"] = flat_name
    rec["flat_pattern_found"] = flat_name is not None

    if flat_name is None:
        rec["reason"] = (
            "No configuration name starts with "
            f'"{FLAT_PATTERN_NAME_PREFIX}" — sheet-metal add-in may be disabled, '
            "or the base flange did not materialize a sheet-metal body"
        )
        return rec

    # Activate the flat-pattern config.
    t0 = time.perf_counter()
    try:
        ok = doc.ShowConfiguration2(flat_name)
        rec["ShowConfiguration2_status"] = "OK"
        rec["ShowConfiguration2_return"] = ok
        rec["ShowConfiguration2_return_type"] = _type_tag(ok)
    except pywintypes.com_error as e:
        rec["ShowConfiguration2_status"] = "COM_ERROR"
        rec["ShowConfiguration2_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
    except Exception as e:
        rec["ShowConfiguration2_status"] = "PY_EXCEPTION"
        rec["ShowConfiguration2_error"] = f"{type(e).__name__}: {e}"
    rec["ShowConfiguration2_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    return rec


# ---------------------------------------------------------------------------
# Flat body probe
# ---------------------------------------------------------------------------

def _probe_flat_body(doc: Any) -> dict[str, Any]:
    """Retrieve the flattened sheet-metal body from the active config.

    Tries GetBodies2(swSheetMetalFlattenedBody) first; falls back to
    GetBodies2(swSolidBody) so we at least record what is present.
    """
    rec: dict[str, Any] = {}

    for btype, label in [
        (SW_BODY_SHEET_METAL_FLAT, "swSheetMetalFlattenedBody"),
        (SW_BODY_SOLID, "swSolidBody"),
    ]:
        t0 = time.perf_counter()
        try:
            bodies = doc.GetBodies2(btype, True)
            rec[f"GetBodies2_{label}_status"] = "OK"
            rec[f"GetBodies2_{label}_count"] = len(bodies) if bodies else 0
            rec[f"GetBodies2_{label}_types"] = (
                [_type_tag(b) for b in bodies] if bodies else []
            )
        except pywintypes.com_error as e:
            rec[f"GetBodies2_{label}_status"] = "COM_ERROR"
            rec[f"GetBodies2_{label}_error"] = (
                f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
            )
        except Exception as e:
            rec[f"GetBodies2_{label}_status"] = "PY_EXCEPTION"
            rec[f"GetBodies2_{label}_error"] = f"{type(e).__name__}: {e}"
        rec[f"GetBodies2_{label}_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    return rec


# ---------------------------------------------------------------------------
# Flat-pattern DXF export probe
# ---------------------------------------------------------------------------

def _probe_flat_pattern_dxf(doc: Any, keep_files: bool) -> dict[str, Any]:
    """Probe ExportToDWG2 for flat-pattern DXF output.

    The export path is a temp file; it is deleted after the probe unless
    ``--keep-files`` is set.
    """
    rec: dict[str, Any] = {}

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = tmp_dir / "spike_sheetmetal_flat.dxf"

    # ExportToDWG2 signature (late-bound, doc.Extension):
    #   ExportToDWG2(bstrFileName, pDoc, nExportToDWGType, bExportAllSheets,
    #                bAlignView, bUseTemplatSize, pDWGPages, pInsertionPoint,
    #                dScaleFactor) -> bool
    # For sheet-metal flat DXF: nExportToDWGType = SW_DWG_EXPORT_SHEETMETAL (4).
    # pDWGPages / pInsertionPoint = None (not used for sheet-metal export).
    ext = doc.Extension
    t0 = time.perf_counter()
    try:
        result = ext.ExportToDWG2(
            str(dxf_path),          # file path
            doc,                    # IModelDoc2
            SW_DWG_EXPORT_SHEETMETAL,  # export type
            False,                  # bExportAllSheets — N/A for sheet metal
            False,                  # bAlignView
            False,                  # bUseTemplatSize
            None,                   # pDWGPages
            None,                   # pInsertionPoint
            1.0,                    # dScaleFactor
        )
        rec["status"] = "OK"
        rec["return_value"] = result
        rec["return_type"] = _type_tag(result)
        rec["file_created"] = dxf_path.exists()
        if dxf_path.exists():
            rec["file_size_bytes"] = dxf_path.stat().st_size
    except pywintypes.com_error as e:
        rec["status"] = "COM_ERROR"
        rec["hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["description"] = getattr(e, "strerror", str(e))
    except Exception as e:
        rec["status"] = "PY_EXCEPTION"
        rec["exception_type"] = type(e).__name__
        rec["message"] = str(e)
    rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    rec["path"] = str(dxf_path)

    if not keep_files and dxf_path.exists():
        try:
            dxf_path.unlink()
            rec["file_cleaned_up"] = True
        except Exception:
            rec["file_cleaned_up"] = False

    return rec


# ---------------------------------------------------------------------------
# Top-level COM run
# ---------------------------------------------------------------------------

def run_com(skip_build: bool, keep_files: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build_rec: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        sketch_rec = _build_profile_sketch(doc)
        build_rec.update(sketch_rec)
        if not sketch_rec.get("built"):
            return {
                "overall": "FAIL",
                "reason": "profile sketch did not build",
                "build": build_rec,
            }

    fm = doc.FeatureManager

    # 1. Base flange call — the primary arity probe.
    flange_probe = _probe_base_flange(fm)
    feat = flange_probe["_feat"]

    if feat is None:
        return {
            "overall": "FAIL",
            "reason": (
                "InsertSheetMetalBaseFlange2 returned no feature in any arity form; "
                "sheet metal is unreachable via late binding or the sketch was invalid"
            ),
            "build": build_rec,
            "flange_probe": {k: v for k, v in flange_probe.items() if k != "_feat"},
        }

    # Trigger a rebuild so the flat-pattern config materializes.
    try:
        doc.EditRebuild3
    except Exception:
        pass

    # 2. Arg / return type-tag probe.
    args_probe = _probe_flange_args(feat)

    # 3. Flat-pattern config probe.
    flat_config_probe = _probe_flat_pattern_config(doc)
    flat_config_ok = flat_config_probe.get("flat_pattern_found") is True

    # 4. Flat body probe (in flat-pattern config, if activated).
    flat_body_probe = _probe_flat_body(doc)
    flat_body_ok = (
        flat_body_probe.get("GetBodies2_swSheetMetalFlattenedBody_count", 0) > 0
        or flat_body_probe.get("GetBodies2_swSolidBody_count", 0) > 0
    )

    # 5. Flat-pattern DXF export probe.
    dxf_probe = _probe_flat_pattern_dxf(doc, keep_files)
    dxf_ok = dxf_probe.get("status") == "OK" and bool(dxf_probe.get("file_created"))

    # Verdict derivation.
    flange_ok = feat is not None  # True by this point
    if flange_ok and flat_config_ok and flat_body_ok and dxf_ok:
        overall = "PASS"
    elif flange_ok and (flat_config_ok or flat_body_ok):
        overall = "PARTIAL"  # flange works; downstream step(s) missing
    elif flange_ok:
        overall = "PARTIAL"  # flange works but flat-pattern unreachable
    else:
        overall = "FAIL"

    interpretation_map = {
        "PASS": (
            "InsertSheetMetalBaseFlange2 materializes out-of-process, flat-pattern "
            "config is reachable, flat body accessible, DXF export succeeds "
            "→ Phase-3 sheet metal handler is viable; build it"
        ),
        "PARTIAL": (
            "Base flange created, but one downstream step failed: "
            "flat-pattern config absent (sheet metal add-in disabled?), "
            "flat body not found, or ExportToDWG2 raised (marshaling wall). "
            "Run --mode vba to isolate; orchestrator decides Route-B/C"
        ),
        "FAIL": (
            "InsertSheetMetalBaseFlange2 unreachable via late binding "
            "→ defer lane; revisit Route-C per todolist.md S-SHEETMETAL row"
        ),
    }

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "winning_arity": flange_probe["winning_arity"],
        "interpretation": interpretation_map[overall],
        "build": build_rec,
        "flange_probe": {k: v for k, v in flange_probe.items() if k != "_feat"},
        "args_probe": args_probe,
        "flat_config_probe": flat_config_probe,
        "flat_body_probe": flat_body_probe,
        "dxf_probe": dxf_probe,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding)
# ---------------------------------------------------------------------------

def emit_vba() -> str:
    """Early-binding oracle for the sheet-metal base flange + flat-pattern pipeline.

    If Python is PARTIAL (e.g. arity unknown or ExportToDWG2 fails) but this
    VBA PASSes, the out-of-process marshaler (not the SW API) is the blocker
    → Route-C signal.  If VBA also fails, the API itself is the problem.
    """
    return r"""' Spike v0.15 S-SHEETMETAL VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a blank Part is active.
' Creates a 60x40 mm sheet-metal base flange (1.5 mm / R1.5 / k=0.44),
' activates the flat-pattern config, and exports a DXF to %TEMP%\spike_sm.dxf.
' Early binding resolves arity and enum values natively, isolating whether
' a Python PARTIAL is a marshaling limitation rather than an API one.
Option Explicit
Sub ProbeSheetMetal()
    Dim swApp    As SldWorks.SldWorks
    Dim Part     As SldWorks.ModelDoc2
    Dim fm       As SldWorks.FeatureManager
    Dim sm       As SldWorks.SketchManager
    Dim ext      As SldWorks.ModelDocExtension
    Dim feat     As SldWorks.Feature
    Dim cfg      As SldWorks.Configuration
    Dim cfgNames As Variant
    Dim dxfPath  As String
    Dim i        As Integer
    Dim ok       As Boolean

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    Set sm    = Part.SketchManager
    Set ext   = Part.Extension

    ' --- profile sketch on Front Plane ---
    Part.ClearSelection2 True
    Part.SelectByID2 "Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0
    sm.InsertSketch True
    sm.CreateCornerRectangle -0.03, -0.02, 0, 0.03, 0.02, 0
    sm.InsertSketch True   ' close sketch — VBA closes before InsertSheetMetalBaseFlange2

    ' In VBA the sketch must be open; re-enter edit mode.
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Part.EditSketch

    ' --- base flange (11-arg form) ---
    ' InsertSheetMetalBaseFlange2(thickness, reverse, bendRadius, kFactor,
    '   reliefType, reliefW, reliefD, reliefRatio, autoRelief,
    '   formFeature, mergeResult)
    Set feat = fm.InsertSheetMetalBaseFlange2( _
        0.0015, False, 0.0015, 0.44, _
        swReliefRectangular, 0.00125, 0.00125, 0.5, _
        True, False, True)

    If feat Is Nothing Then
        MsgBox "InsertSheetMetalBaseFlange2 returned Nothing"
        Exit Sub
    End If
    MsgBox "Base flange OK: " & feat.Name & " / " & feat.GetTypeName2

    Part.EditRebuild3

    ' --- flat-pattern config ---
    cfgNames = Part.GetConfigurationNames
    Dim flatName As String
    flatName = ""
    For i = 0 To UBound(cfgNames)
        If Left(cfgNames(i), 12) = "Flat Pattern" Then
            flatName = cfgNames(i)
            Exit For
        End If
    Next i

    If flatName = "" Then
        MsgBox "No Flat Pattern config found; sheet metal add-in may be off"
        Exit Sub
    End If

    ok = Part.ShowConfiguration2(flatName)
    MsgBox "ShowConfiguration2(""" & flatName & """) = " & ok

    ' --- DXF export ---
    dxfPath = Environ("TEMP") & Chr(92) & "spike_sm.dxf"
    ok = ext.ExportToDWG2(dxfPath, Part, swExportToDWG_ExportSheetMetal, _
                          False, False, False, Nothing, Nothing, 1.0)
    MsgBox "ExportToDWG2 = " & ok & " -> " & dxfPath
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
        help="com = drive SW from Python; vba = emit the .bas oracle.",
    )
    p.add_argument(
        "--skip-build", action="store_true",
        help="Skip creating the profile sketch; probe a sheet-metal part already open.",
    )
    p.add_argument(
        "--keep-files", action="store_true",
        help="Retain the exported DXF file for manual inspection.",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_sheetmetal.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run_com(args.skip_build, args.keep_files)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    # PARTIAL exits 2 to distinguish the Route-C signal from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
