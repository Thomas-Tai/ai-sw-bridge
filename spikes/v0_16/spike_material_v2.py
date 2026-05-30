"""Spike v0.16 / S-MATERIAL v2 — early-bind the read-back + mass-props honesty.

The v0.15 S-MATERIAL run came back PARTIAL, and the JSON makes the cause
unambiguous (spikes/v0_15/_results/material.json):

  * SetMaterialPropertyName2(config, db, name)  -> set_status = "OK" (None)
        the ASSIGNMENT itself round-trips out-of-process fine.
  * GetMaterialPropertyName2(config)            -> COM_ERROR "Parameter not optional."
        hresult -0x7ffdfff1  (DISP_E_PARAMNOTOPTIONAL)
  * GetMassProperties2(0, 1, True)              -> COM_ERROR "Type mismatch."
        hresult -0x7ffdfffb  (DISP_E_TYPEMISMATCH)

That is the SAME dynamic-dispatch `[out]`-param wall the early-bind seam
(`com.earlybind.typed`) was built to clear — exactly like
GetObjectByPersistReference3 / GetDefinition. `GetMaterialPropertyName2` has
two `[out] BSTR` params (db, name); `GetMassProperties2` returns a SAFEARRAY.
Under late binding pywin32 cannot marshal either; under a typed IPartDoc /
IModelDocExtension it can.

This spike retries with the typed wrappers and decides D1:

  PASS    : typed GetMaterialPropertyName2 round-trips (db,name) identical to
            what was set, AND typed GetMassProperties2 density flips from the
            ~1000 kg/m3 default to the assigned material's density
            (steel ~7800). -> wire the library-material path into material.py.
  PARTIAL : assignment + read-back clean but density still does not move
            -> custom-property fallback stays the only honest route.
  FAIL    : typed read-back itself errors -> deeper than marshaling.

Non-destructive: opens its own blank Part via NewDocument, never saves, closes
its own doc by title. Prereq: SOLIDWORKS running.

Usage:  .venv-py310\Scripts\python spikes\v0_16\spike_material_v2.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

# Box geometry (metres) — minimal solid so mass-props has something to weigh.
BOX_W_M, BOX_H_M, BOX_D_M = 0.020, 0.020, 0.010

SW_DEFAULT_TEMPLATE_PART = 8  # swDefaultTemplatePart

# Steel is ~7800, water-default is 1000; loose threshold separates them.
_FALLBACK_DENSITY_KG_M3 = 1000.0
_DENSITY_DELTA_THRESHOLD = 50.0

CANDIDATE_DB = "SolidWorks Materials"
CANDIDATE_NAME = "AISI 1020 Steel (SS)"


def _type_tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-BOX_W_M / 2, -BOX_H_M / 2, 0.0,
                             BOX_W_M / 2, BOX_H_M / 2, 0.0)
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (True, False, False, 0, 0, BOX_D_M, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0)
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return {"built": feat is not None}


def _density_via_typed_ext(doc: Any) -> dict[str, Any]:
    """GetMassProperties2 through a typed IModelDocExtension (clears the
    late-bound 'Type mismatch' wall)."""
    rec: dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        props = ext.GetMassProperties2(0, 1, True)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["return_type"] = _type_tag(props)
        if props is None:
            rec["status"] = "NONE_RETURNED"
            return rec
        try:
            vals = list(props)
        except TypeError:
            vals = [props]
        rec["status"] = "OK"
        rec["raw_len"] = len(vals)
        rec["raw_repr"] = [str(type(v).__name__) for v in vals]
        # Early binding surfaces the [out] Status param: shape is (array, status).
        # Unwrap to the actual mass-props SAFEARRAY (the first sequence element).
        arr = None
        if vals and isinstance(vals[0], (tuple, list)):
            arr = list(vals[0])
        elif len(vals) >= 15:  # already flat
            arr = vals
        if arr is not None:
            rec["arr_len"] = len(arr)
            rec["arr_full"] = [float(x) for x in arr]
            # 12-element layout: [CoM x,y,z, Volume, Area, Mass, ...inertia]
            if len(arr) >= 6 and arr[3] and float(arr[3]) > 0:
                volume_m3 = float(arr[3])
                mass_kg = float(arr[5])
                rec["volume_m3"] = volume_m3
                rec["mass_kg"] = mass_kg
                rec["density_kg_m3"] = mass_kg / volume_m3
            else:
                rec["density_kg_m3"] = None
        else:
            rec["density_kg_m3"] = None
            rec["raw_dump"] = str(vals)
    except pywintypes.com_error as e:
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["status"] = "COM_ERROR"
        rec["hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["description"] = getattr(e, "strerror", str(e))
    except Exception as e:  # noqa: BLE001
        rec["status"] = "PY_EXCEPTION"
        rec["exception"] = f"{type(e).__name__}: {e}"
    return rec


def _set_and_readback(doc: Any, db: str, name: str) -> dict[str, Any]:
    """Set via late-bound IPartDoc (proven OK), read back via typed IPartDoc."""
    rec: dict[str, Any] = {"db": db, "name": name}

    # SET — already proven OK out-of-process in v0.15.
    t0 = time.perf_counter()
    try:
        ret = doc.SetMaterialPropertyName2("", db, name)
        rec["set_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["set_status"] = "OK"
        rec["set_return"] = _type_tag(ret)
    except Exception as e:  # noqa: BLE001
        rec["set_status"] = "ERROR"
        rec["set_error"] = f"{type(e).__name__}: {e}"
        return rec

    # READ-BACK — the v0.15 wall. typed IPartDoc surfaces the [out] BSTRs.
    t1 = time.perf_counter()
    try:
        part = typed(doc, "IPartDoc")
        rb = part.GetMaterialPropertyName2("")
        rec["get_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        rec["get_status"] = "OK"
        rec["get_return_type"] = _type_tag(rb)
        if isinstance(rb, (tuple, list)) and len(rb) >= 2:
            rec["db_readback"] = rb[0]
            rec["name_readback"] = rb[1]
            rec["roundtrip_db_match"] = (str(rb[0]) == db)
            rec["roundtrip_name_match"] = (str(rb[1]) == name)
        else:
            rec["get_raw"] = str(rb)
    except pywintypes.com_error as e:
        rec["get_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        rec["get_status"] = "COM_ERROR"
        rec["get_hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["get_description"] = getattr(e, "strerror", str(e))
    except Exception as e:  # noqa: BLE001
        rec["get_status"] = "PY_EXCEPTION"
        rec["get_error"] = f"{type(e).__name__}: {e}"
    return rec


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    result: dict[str, Any] = {}
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None", **result}

    title = _title(doc)
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {"overall": "FAIL", "reason": "box did not build", **result}
        try:
            doc.EditRebuild3
        except Exception:  # noqa: BLE001
            pass

        result["density_pre"] = _density_via_typed_ext(doc)
        result["assign"] = _set_and_readback(doc, CANDIDATE_DB, CANDIDATE_NAME)
        try:
            doc.EditRebuild3
        except Exception:  # noqa: BLE001
            pass
        result["density_post"] = _density_via_typed_ext(doc)
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    # Verdict.
    pre = result["density_pre"].get("density_kg_m3")
    post = result["density_post"].get("density_kg_m3")
    rt = result["assign"].get("roundtrip_name_match") is True
    density_moved = (
        pre is not None and post is not None
        and abs(float(post) - float(pre)) > _DENSITY_DELTA_THRESHOLD
    )
    result["density_delta"] = {
        "pre_kg_m3": pre, "post_kg_m3": post,
        "moved": density_moved,
        "post_is_material_like": (post is not None and abs(float(post) - _FALLBACK_DENSITY_KG_M3) > _DENSITY_DELTA_THRESHOLD),
    }
    if rt and density_moved:
        result["overall"] = "PASS"
    elif rt:
        result["overall"] = "PARTIAL"
    else:
        result["overall"] = "FAIL"
    result["interpretation"] = {
        "PASS": "typed read-back + typed mass-props both clear the late-bind wall; "
                "density flows from the assigned material -> wire library-material path into material.py.",
        "PARTIAL": "read-back clean but density did not move -> custom-property fallback only.",
        "FAIL": "typed read-back itself errored -> deeper than marshaling.",
    }[result["overall"]]
    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "material_v2.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
