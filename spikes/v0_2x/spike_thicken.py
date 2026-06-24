"""W66 thicken — surface→solid bridge spike (LIVE seat only).

Chained fixture: build_block → InsertOffsetSurface → select the new sheet
body → fire create_thicken handler → A7 GetTypeName2 probe → save→reopen
survival check → writes ``_results/thicken.json``.

Decisive discriminator (ADDITIVE gate):
    ΔVol > 0  ∧  ΔSolidBodies ≥ +1

Verdicts:
    PASS     — thicken produced a solid (ΔVol > 0, ΔSolidBodies ≥ +1), survives reopen
    WEAK_PASS — thicken produced a solid but does not survive reopen
    FAIL     — thicken did not produce a solid (ghost / no-op)

Usage:
    C:/Python314/python.exe spikes/v0_2x/spike_thicken.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS_PATH = Path(__file__).resolve().parents[1] / "_results" / "thicken.json"

import pythoncom

from _feature_spike_fixtures import build_block, save_and_reopen, top_face
from ai_sw_bridge.features.thicken import create_thicken


OFFSET_M = 0.005  # 5 mm offset surface
THICKEN_MM = 2.0  # 2 mm thicken depth


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
        src = doc if hasattr(doc, "GetBodies2") else doc
        bodies = src.GetBodies2(1, True)  # swSheetBody = 1
    except Exception:
        return 0
    if not bodies:
        return 0
    return len(bodies) if isinstance(bodies, (list, tuple)) else 1


def _count_solid_bodies(doc: Any) -> int:
    try:
        src = doc if hasattr(doc, "GetBodies2") else doc
        bodies = src.GetBodies2(0, True)  # swSolidBody = 0
    except Exception:
        return 0
    if not bodies:
        return 0
    return len(bodies) if isinstance(bodies, (list, tuple)) else 1


def _volume_mm3(doc: Any) -> float:
    try:
        src = doc if hasattr(doc, "GetBodies2") else doc
        bodies = src.GetBodies2(0, True)
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


_SW_DEFAULT_TEMPLATE_PART = 8


def _create_standalone_surface(sw: Any) -> Any:
    """W66 round-4 STANDALONE probe — a planar surface in EMPTY space (no solid
    block), to isolate the thicken from any boolean-merge context (the W66
    multi-body merge hypothesis). Returns the doc with exactly one sheet body
    and zero solids, or None on failure.

    Recipe: new empty part → rectangle sketch on Top Plane → InsertPlanarRefSurface
    (the proven planar_surface GREEN recipe) → one standalone sheet body.
    """
    template = sw.GetUserPreferenceStringValue(_SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("  NewDocument returned None", file=sys.stderr)
        return None
    try:
        import pythoncom as _pc
        from win32com.client import VARIANT as _V

        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCornerRectangle(0.0, 0.0, 0.0, 0.04, 0.03, 0.0)
        doc.SketchManager.InsertSketch(True)  # close -> Sketch1
        doc.ClearSelection2(True)
        doc.Extension.SelectByID2(
            "Sketch1",
            "SKETCH",
            0,
            0,
            0,
            False,
            0,
            _V(_pc.VT_DISPATCH, None),
            0,
        )
        # InsertPlanarRefSurface is a 0-arg method win32com auto-invokes as a
        # PROPERTY (it fires + returns a bool on attribute access). Calling ()
        # on the bool is the "'bool' not callable" trap — callable-or-property guard.
        _ips = doc.InsertPlanarRefSurface
        if callable(_ips):
            _ips()
        doc.ForceRebuild3(False)
    except Exception as exc:
        print(f"  standalone planar-surface authoring raised: {exc!r}", file=sys.stderr)
        return None
    sheets = _count_sheet_bodies(doc)
    solids = _count_solid_bodies(doc)
    print(f"  standalone surface: sheets={sheets}, solids={solids}", file=sys.stderr)
    if sheets < 1 or solids != 0:
        return None
    return doc


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike_id": "W66_thicken"}

    try:
        from ai_sw_bridge.sw_com import get_sw_app

        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"connect: {exc!r}"}
    if sw is None:
        return {**result, "overall": "ERROR", "reason": "get_sw_app() returned None"}

    # --- CHAIN STEP 1: STANDALONE surface (no solid block — round-4 probe) ---
    doc = _create_standalone_surface(sw)
    if doc is None:
        return {
            **result,
            "overall": "FAIL",
            "reason": "standalone planar surface fixture did not build (sheets<1 or solids!=0)",
        }
    try:
        # --- CHAIN STEP 2: fire the thicken handler ---
        solids_before = _count_solid_bodies(doc)
        vol_before = _volume_mm3(doc)
        sheets_before = _count_sheet_bodies(doc)

        ok, note = create_thicken(
            doc,
            {"thickness_mm": THICKEN_MM, "direction": "side1"},
            {},  # no face_ref → handler picks first sheet body
        )
        result["handler_ok"] = ok
        result["handler_note"] = note

        solids_after = _count_solid_bodies(doc)
        vol_after = _volume_mm3(doc)
        sheets_after = _count_sheet_bodies(doc)
        result["solids_before"] = solids_before
        result["solids_after"] = solids_after
        result["delta_solids"] = solids_after - solids_before
        result["vol_before_mm3"] = round(vol_before, 6)
        result["vol_after_mm3"] = round(vol_after, 6)
        result["delta_vol_mm3"] = round(vol_after - vol_before, 6)
        result["sheets_before"] = sheets_before
        result["sheets_after"] = sheets_after

        # --- A7 probe: GetTypeName2 on the latest feature ---
        try:
            feats = doc.FeatureManager.GetFeatures(False)
            if feats:
                last = feats[-1]
                result["last_feature_type"] = _type_name(last)
                try:
                    nm = last.Name
                    result["last_feature_name"] = nm() if callable(nm) else str(nm)
                except Exception:
                    pass
        except Exception as exc:
            result["a7_error"] = str(exc)

        # --- Save → reopen survival ---
        try:
            doc2 = save_and_reopen(sw, doc)
            if doc2 is not None:
                solids_reopen = _count_solid_bodies(doc2)
                vol_reopen = _volume_mm3(doc2)
                result["survives_reopen"] = solids_reopen >= solids_after
                result["solids_after_reopen"] = solids_reopen
                result["vol_after_reopen_mm3"] = round(vol_reopen, 6)
            else:
                result["survives_reopen"] = False
                result["reopen_note"] = "save_and_reopen returned None"
        except Exception as exc:
            result["survives_reopen"] = False
            result["reopen_error"] = f"{type(exc).__name__}: {exc}"

        # --- Verdict ---
        d_vol = vol_after - vol_before
        d_solids = solids_after - solids_before
        produced_solid = d_vol > 1e-6 and d_solids >= 1

        if produced_solid and result.get("survives_reopen"):
            result["overall"] = "PASS"
            result["finding"] = (
                f"thicken produced solid: ΔSolids={d_solids}, "
                f"ΔVol={d_vol:.3f} mm³, survives reopen"
            )
        elif produced_solid:
            result["overall"] = "WEAK_PASS"
            result["finding"] = (
                f"thicken produced solid (ΔSolids={d_solids}, "
                f"ΔVol={d_vol:.3f} mm³) but did NOT survive reopen"
            )
        else:
            result["overall"] = "FAIL"
            result["finding"] = (
                f"thicken did NOT produce solid: ΔSolids={d_solids}, "
                f"ΔVol={d_vol:.3f} mm³"
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
