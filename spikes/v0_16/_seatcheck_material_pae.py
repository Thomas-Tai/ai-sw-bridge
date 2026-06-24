"""Seat-check D1: drive the WIRED material.apply_material through the live seat.

Validates the shipped code path (not just the spike):
  1. apply_material(doc, {"material": "AISI 1020"})  -> True, density ~7900
     (honest library path: assigned + verified + density flows).
  2. apply_material(doc, {"material": "<not a library material>"}) -> True,
     density stays ~1000, custom property "Material" carries the string
     (graceful fallback).
  3. apply_material(doc, {})  -> None  (no material in spec).

Non-destructive: own blank Part, never saves, closes own doc.
Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_material_pae.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge import material  # noqa: E402
from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

BOX_W_M, BOX_H_M, BOX_D_M = 0.020, 0.020, 0.010
SW_DEFAULT_TEMPLATE_PART = 8
KNOWN_NAME = "AISI 1020"
UNKNOWN_NAME = "Totally Made Up Alloy 9000"


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
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
    return feat is not None


def _density(doc: Any) -> float | None:
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        props = ext.GetMassProperties2(0, 1, True)
        vals = list(props)
        arr = list(vals[0]) if vals and isinstance(vals[0], (tuple, list)) else vals
        if len(arr) >= 6 and arr[3] and float(arr[3]) > 0:
            return float(arr[5]) / float(arr[3])
    except Exception:  # noqa: BLE001
        return None
    return None


def _custom_prop(doc: Any, name: str = "Material") -> Any:
    """Read a custom property through a typed ICustomPropertyManager (Get5
    has [out] params that die under dynamic dispatch — same wall as the
    material read-back). Returns the resolved value string, or a diagnostic."""
    try:
        cpm = typed(doc.Extension.CustomPropertyManager(""), "ICustomPropertyManager")
    except Exception as e:  # noqa: BLE001
        return f"<cpm-wrap-err {type(e).__name__}>"
    try:
        res = cpm.Get5(name, False)
    except Exception as e:  # noqa: BLE001
        return f"<get5-err {type(e).__name__}: {e}>"
    # Early binding surfaces [out] ValOut/ResolvedValOut/WasResolved as a tuple,
    # often with the long retval first: (ret, valOut, resolvedOut, wasResolved).
    if isinstance(res, (tuple, list)):
        # The first string element is the stored value.
        for v in res:
            if isinstance(v, str) and v:
                return v
        return list(res)
    return res


def _fresh_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None or not _build_box(doc):
        return None
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return doc


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {}
    try:
        report["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        report["sw_revision"] = "<unreadable>"

    # --- Case 1: known library material -> honest density ---
    doc = _fresh_part(sw)
    if doc is None:
        return {"overall": "FAIL", "reason": "case1 box build failed", **report}
    title = _title(doc)
    try:
        base = _density(doc)
        ret = material.apply_material(doc, {"material": KNOWN_NAME})
        dens = _density(doc)
        report["case_library"] = {
            "apply_return": ret,
            "baseline_density": base,
            "density": dens,
            "honest": (ret is True and dens is not None and dens > 5000.0),
        }
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # --- Case 2: unknown name -> custom-property fallback ---
    doc = _fresh_part(sw)
    if doc is None:
        return {"overall": "FAIL", "reason": "case2 box build failed", **report}
    title = _title(doc)
    try:
        ret = material.apply_material(doc, {"material": UNKNOWN_NAME})
        dens = _density(doc)
        prop = _custom_prop(doc, material.MATERIAL_PROP_NAME)
        report["case_fallback"] = {
            "apply_return": ret,
            "density": dens,
            "custom_prop_material": prop,
            "fallback_ok": (
                ret is True and prop == UNKNOWN_NAME and (dens is None or dens < 2000.0)
            ),
        }
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # --- Case 3: no material in spec -> None ---
    doc = _fresh_part(sw)
    title = _title(doc) if doc is not None else None
    try:
        report["case_none"] = {"apply_return": material.apply_material(doc, {})}
    finally:
        if title is not None:
            try:
                sw.CloseDoc(title)
            except Exception:  # noqa: BLE001
                pass

    c1 = report.get("case_library", {}).get("honest") is True
    c2 = report.get("case_fallback", {}).get("fallback_ok") is True
    c3 = report.get("case_none", {}).get("apply_return") is None
    report["overall"] = "PASS" if (c1 and c2 and c3) else f"c1={c1} c2={c2} c3={c3}"
    return report


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "material_pae.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
