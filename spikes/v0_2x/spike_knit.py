"""W66 knit — surface-aggregation BOSS FIGHT spike (LIVE seat only).

Chained fixture: build_block → two surface bodies sharing an edge → fire
``create_knit`` handler → A7 GetTypeName2 probe → save→reopen survival
check → writes ``_results/knit.json``.

Decisive discriminator (AGGREGATION gate — INVERTED):
    ΔSheetBodies < 0  ∧  total area > 0  (surface-knit mode)
    OR
    ΔSheetBodies < 0  ∧  ΔSolidBodies ≥ +1  ∧  ΔVol > 0  (solid-knit mode)

Verdicts:
    PASS     — knit merged bodies (ΔSheetBodies < 0, area > 0), survives reopen
    WEAK_PASS — knit merged bodies but does NOT survive reopen
    FAIL     — knit did NOT merge bodies (ghost / no-op)

The fixture creates two surface bodies via the CHM VB6 recipe:
  1. FeatureExtruRefSurface2 from Sketch1 → Surface-Extrude1 (BODYFEATURE)
  2. InsertPlanarRefSurface from Sketch1 → Surface-Plane1 (SURFACEBODY)
These share the sketch contour edge, making them adjacent and sewable.

Usage:
    C:/Python314/python.exe spikes/v0_2x/spike_knit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS_PATH = (
    Path(__file__).resolve().parents[1] / "_results" / "knit.json"
)

import pythoncom

from _feature_spike_fixtures import build_block, save_and_reopen
from ai_sw_bridge.features.knit import create_knit


_BLIND = 0
SURFACE_EXTRUDE_DEPTH_M = 0.005  # 5 mm surface extrude


def _type_name(node: Any) -> str | None:
    """A7 probe — GetTypeName2 with GetTypeName fallback."""
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _count_sheet_bodies(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(1, False)  # swSheetBody = 1
    except Exception:
        return 0
    if not bodies:
        return 0
    return len(bodies) if isinstance(bodies, (list, tuple)) else 1


def _count_solid_bodies(doc: Any) -> int:
    try:
        bodies = doc.GetBodies2(0, False)  # swSolidBody = 0
    except Exception:
        return 0
    if not bodies:
        return 0
    return len(bodies) if isinstance(bodies, (list, tuple)) else 1


def _total_sheet_area_mm2(doc: Any) -> float:
    try:
        bodies = doc.GetBodies2(1, False)
    except Exception:
        return 0.0
    if not bodies:
        return 0.0
    body_list = list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]
    total = 0.0
    for b in body_list:
        try:
            faces = b.GetFaces
            if callable(faces):
                faces = faces()
            if not faces:
                continue
            for f in faces:
                try:
                    a = f.GetArea
                    if callable(a):
                        a = a()
                    total += float(a) * 1e6
                except Exception:
                    pass
        except Exception:
            pass
    return total


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


def _create_two_surface_bodies(doc: Any) -> tuple[bool, list[str]]:
    """Create two surface bodies sharing Sketch1's edge contour.

    Follows the CHM VB6 recipe:
      1. FeatureExtruRefSurface2 from Sketch1 → Surface-Extrude1
      2. InsertPlanarRefSurface from Sketch1  → Surface-Plane1

    Returns (success, [feature_names]) for body_refs targeting.
    """
    import pythoncom as pc
    from win32com.client import VARIANT

    null_disp = VARIANT(pc.VT_DISPATCH, None)
    ext = doc.Extension

    # 1) Select Sketch1 and extrude as a surface
    try:
        ext.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, False, 4, null_disp, 0)
    except Exception as exc:
        print(f"  SelectByID2(Sketch1, SKETCH) raised: {exc!r}", file=sys.stderr)
        return False, []

    sheets_before = _count_sheet_bodies(doc)
    try:
        doc.FeatureManager.FeatureExtruRefSurface2(
            True, False, False, _BLIND, 0,
            SURFACE_EXTRUDE_DEPTH_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False, False, False, False,
        )
    except Exception as exc:
        print(f"  FeatureExtruRefSurface2 raised: {exc!r}", file=sys.stderr)
        return False, []
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    doc.ClearSelection2(True)

    sheets_after_extrude = _count_sheet_bodies(doc)
    print(
        f"  surface-extrude: sheets {sheets_before} → {sheets_after_extrude}",
        file=sys.stderr,
    )

    # 2) Select Sketch1 again and create a planar surface
    try:
        ext.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, True, 1, null_disp, 0)
    except Exception as exc:
        print(f"  SelectByID2(Sketch1, SKETCH, append) raised: {exc!r}", file=sys.stderr)
        return False, []

    try:
        ips = doc.InsertPlanarRefSurface
        result = ips() if callable(ips) else ips
        print(f"  InsertPlanarRefSurface -> {result!r}", file=sys.stderr)
    except Exception as exc:
        print(f"  InsertPlanarRefSurface raised: {exc!r}", file=sys.stderr)
        return False, []
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    doc.ClearSelection2(True)

    sheets_final = _count_sheet_bodies(doc)
    print(
        f"  planar-surface: sheets {sheets_after_extrude} → {sheets_final}",
        file=sys.stderr,
    )

    if sheets_final < 2:
        print(
            f"  NEED ≥2 sheet bodies for knit, got {sheets_final}",
            file=sys.stderr,
        )
        return False, []

    # Discover the actual feature names for the surface bodies.
    # The CHM recipe uses "Surface-Extrude1" (BODYFEATURE) and
    # "Surface-Plane1" (SURFACEBODY).
    body_refs = [
        {"name": "Surface-Extrude1", "type": "BODYFEATURE"},
        {"name": "Surface-Plane1", "type": "SURFACEBODY"},
    ]
    return True, body_refs


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike_id": "W66_knit"}

    try:
        from ai_sw_bridge.sw_com import get_sw_app
        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"connect: {exc!r}"}
    if sw is None:
        return {**result, "overall": "ERROR", "reason": "get_sw_app() returned None"}

    doc = build_block(sw)
    try:
        # --- CHAIN STEP 1: create two surface bodies ---
        ok_surfaces, body_refs = _create_two_surface_bodies(doc)
        if not ok_surfaces:
            return {
                **result,
                "overall": "FAIL",
                "reason": "chained surface-body creation failed",
            }

        # --- CHAIN STEP 2: fire the knit handler ---
        sheets_before = _count_sheet_bodies(doc)
        area_before = _total_sheet_area_mm2(doc)
        solids_before = _count_solid_bodies(doc)
        vol_before = _volume_mm3(doc)

        ok, note = create_knit(doc, {}, {"body_refs": body_refs})
        result["handler_ok"] = ok
        result["handler_note"] = note

        sheets_after = _count_sheet_bodies(doc)
        area_after = _total_sheet_area_mm2(doc)
        solids_after = _count_solid_bodies(doc)
        vol_after = _volume_mm3(doc)

        result["sheets_before"] = sheets_before
        result["sheets_after"] = sheets_after
        result["delta_sheets"] = sheets_after - sheets_before
        result["area_before_mm2"] = round(area_before, 6)
        result["area_after_mm2"] = round(area_after, 6)
        result["solids_before"] = solids_before
        result["solids_after"] = solids_after
        result["vol_before_mm3"] = round(vol_before, 6)
        result["vol_after_mm3"] = round(vol_after, 6)

        # --- A7 probe: GetTypeName2 on the latest feature ---
        try:
            feats = doc.FeatureManager.GetFeatures(False)
            if feats:
                last = feats[-1]
                result["last_feature_type"] = _type_name(last)
                try:
                    nm = last.Name
                    result["last_feature_name"] = (
                        nm() if callable(nm) else str(nm)
                    )
                except Exception:
                    pass
        except Exception as exc:
            result["a7_error"] = str(exc)

        # --- Save → reopen survival ---
        try:
            doc2 = save_and_reopen(sw, doc)
            if doc2 is not None:
                sheets_reopen = _count_sheet_bodies(doc2)
                area_reopen = _total_sheet_area_mm2(doc2)
                result["survives_reopen"] = sheets_reopen <= sheets_before
                result["sheets_after_reopen"] = sheets_reopen
                result["area_after_reopen_mm2"] = round(area_reopen, 6)
            else:
                result["survives_reopen"] = False
                result["reopen_note"] = "save_and_reopen returned None"
        except Exception as exc:
            result["survives_reopen"] = False
            result["reopen_error"] = f"{type(exc).__name__}: {exc}"

        # --- Verdict ---
        d_sheets = sheets_after - sheets_before
        merged = d_sheets < 0 and area_after > 1e-6

        if merged and result.get("survives_reopen"):
            result["overall"] = "PASS"
            result["finding"] = (
                f"knit merged sheets: ΔSheets={d_sheets}, "
                f"area={area_after:.3f} mm², survives reopen"
            )
        elif merged:
            result["overall"] = "WEAK_PASS"
            result["finding"] = (
                f"knit merged sheets (ΔSheets={d_sheets}, "
                f"area={area_after:.3f} mm²) but did NOT survive reopen"
            )
        else:
            result["overall"] = "FAIL"
            result["finding"] = (
                f"knit did NOT merge sheets: ΔSheets={d_sheets}, "
                f"area_after={area_after:.3f} mm²"
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
    print(f"results -> {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
