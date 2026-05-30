"""
Spike v0.16 / S-VARFIL-DIRECT — variable-radius fillet WITHOUT a separate
interface (follow-up to spike_varfil_qi.py = MORPH-FALSE). [seat]

spike_varfil_qi.py proved the morph hypothesis FALSE: Initialize(1|2|3) on the
typed_qi'd ISimpleFilletFeatureData2 does NOT make the object answer a separate
IVariableFilletFeatureData2 (E_NOINTERFACE every time, SW 2024 rev 32.1.0).

This tests the *other* shape: modern SW folds variable-radius parameters
directly onto ISimpleFilletFeatureData2. So after Initialize(<variable type>)
the SAME typed object should expose variable-radius setters
(SetVariableRadiusParameters / VariableRadiusInstances / per-point radii) —
no second interface. The v0.15 spike couldn't test this because it never got
past the late-bind FilletType= wall; with typed_qi + Initialize the members
should be reachable.

Two probes:
  H1 — member surface of the Initialize(var)'d ISimpleFilletFeatureData2, then
       set radii + CreateFeature, and report the resulting fillet's type name
       (does it materialize, and is it actually a variable-radius fillet?).
  H2 — a small CreateDefinition id-scan QI'd against IVariableFilletFeatureData2,
       in case a *distinct* constant (not swFmFillet=1) yields it.

Verdict
-------
PASS-DIRECT : Initialize(var) + variable setters on ISimpleFilletFeatureData2
              materialize a variable-radius fillet → P1.5 handler extends
              _create_fillet by setting variable params on the same object.
PASS-CONST  : materializes a fillet but only constant-radius members worked /
              the variable setters are absent → variable radius not reachable
              this way; constant path unaffected.
NO-MEMBERS  : Initialize(var) runs but no variable-radius setter is present on
              ISimpleFilletFeatureData2 AND H2 finds no distinct id → variable
              fillet is not reachable via CreateDefinition; try legacy
              InsertFeatureFillet (a FeatureManager method).
FAIL        : pipeline regression (typed_qi/build).

Non-destructive (own NewDocument part, closed without save).
Usage: python spikes/v0_16/spike_varfil_direct.py --out report.json
"""

from __future__ import annotations

import argparse
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

from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_FILLET = 1
SIMPLE_IFACE = "ISimpleFilletFeatureData2"
VAR_IFACE = "IVariableFilletFeatureData2"
VAR_TYPE = 1  # swFilletType_e variable-radius candidate (constant = 0)

BOX_W_M = BOX_H_M = 0.020
BOX_D_M = 0.010
EDGE_X_M, EDGE_Y_M, EDGE_Z_M = 0.0, -BOX_H_M / 2, 0.0
VARRAD_START_M, VARRAD_END_M = 0.002, 0.004

# Candidate variable-radius members on ISimpleFilletFeatureData2.
CANDIDATE_MEMBERS = (
    "DefaultRadius",
    "FilletType",
    "Type",
    "SetVariableRadiusParameters",
    "VariableRadiusParameters",
    "SetVariableRadiusInstances",
    "GetVariableRadiusInstances",
    "SetVariableRadiusPoint",
    "AddVariableRadiusPoint",
    "RadiiCount",
    "NumberOfRadii",
    "AsymmetricFillet",
)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {"status": "OK", "type": _tag(val),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, val
    except Exception as e:  # noqa: BLE001
        return {"status": "EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e)[:200],
                "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, None


def _probe_members(obj: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in CANDIDATE_MEMBERS:
        try:
            getattr(obj, name)
            out[name] = "present"
        except AttributeError:
            out[name] = "MISSING"
        except Exception as e:  # noqa: BLE001
            out[name] = f"reachable({type(e).__name__})"
    return out


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(-BOX_W_M / 2, -BOX_H_M / 2, 0.0,
                                   BOX_W_M / 2, BOX_H_M / 2, 0.0)
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (True, False, False, 0, 0, BOX_D_M, 0.0, False, False, False,
                 False, 0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0)
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _scan_for_variable(fm: Any, mod: Any) -> dict[str, Any]:
    """H2: which CreateDefinition ids yield an object that QI-supports the
    variable interface?"""
    hits: dict[int, str] = {}
    for i in range(0, 40):
        _, data = _capture(lambda i=i: fm.CreateDefinition(i))
        if data is None:
            continue
        rec, w = _capture(lambda data=data: typed_qi(data, VAR_IFACE, module=mod))
        if w is not None:
            hits[i] = "VARIABLE-OK"
    return {"variable_iface_ids": hits}


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (typed_qi)"}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback_info"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument None"}

    members: dict[str, str] = {}
    create_rec: dict[str, Any] = {}
    write_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}
        fm = doc.FeatureManager

        # H2 scan first (cheap, independent).
        result["scan"] = _scan_for_variable(fm, mod)

        # H1: Initialize(var) on a typed_qi'd simple object, probe + create.
        _, data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
        init_rec_outer, simple = _capture(lambda: typed_qi(data, SIMPLE_IFACE, module=mod))
        result["typed_qi_simple"] = init_rec_outer
        if simple is None:
            return {**result, "overall": "FAIL", "reason": "typed_qi(simple) failed"}

        result["initialize_var"], _ = _capture(lambda: simple.Initialize(VAR_TYPE))
        members = _probe_members(simple)
        result["members"] = members

        # Best-effort: set a default radius, then variable radii via whichever
        # setter is present.
        if members.get("DefaultRadius") == "present":
            _capture(lambda: setattr(simple, "DefaultRadius", VARRAD_START_M))

        array = (VARRAD_START_M, VARRAD_END_M)
        if members.get("SetVariableRadiusParameters") == "present":
            write_rec, _ = _capture(lambda: simple.SetVariableRadiusParameters(array))
            write_rec["via"] = "SetVariableRadiusParameters"
        elif members.get("VariableRadiusParameters") == "present":
            write_rec, _ = _capture(lambda: setattr(simple, "VariableRadiusParameters", array))
            write_rec["via"] = "VariableRadiusParameters"
        else:
            write_rec = {"status": "SKIPPED", "reason": "no variable setter present"}
        result["set_radii"] = write_rec

        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        result["edge_select"], _ = _capture(
            lambda: doc.SelectByID("", "EDGE", EDGE_X_M, EDGE_Y_M, EDGE_Z_M)
        )

        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        create_rec = feat_rec
        create_rec["materialized"] = _materialized(feat)
        if _materialized(feat):
            create_rec["feature_name"] = getattr(feat, "Name", None)
            create_rec["type_name"] = _type_name(feat)
        result["create_feature"] = create_rec
    finally:
        _try_close(sw, doc)
        result["cleanup"] = "closed own doc (no save)"

    # --- Verdict -------------------------------------------------------------
    has_var_setter = (
        members.get("SetVariableRadiusParameters") == "present"
        or members.get("VariableRadiusParameters") == "present"
    )
    mat = create_rec.get("materialized")
    if mat and has_var_setter and write_rec.get("status") == "OK":
        overall = "PASS-DIRECT"
        interp = (
            f"Initialize({VAR_TYPE}) + variable setters on ISimpleFilletFeatureData2 "
            f"materialized a fillet ({create_rec.get('type_name')}) → P1.5 handler "
            "extends _create_fillet by setting variable params on the same object "
            "(no separate interface)."
        )
    elif mat:
        overall = "PASS-CONST"
        interp = (
            f"a fillet materialized ({create_rec.get('type_name')}) but the variable "
            "setters were absent/failed → variable radius not reachable this way; "
            "constant path unaffected."
        )
    elif result.get("scan", {}).get("variable_iface_ids"):
        overall = "NO-MEMBERS"
        interp = (
            "no variable setter on ISimpleFilletFeatureData2, but the id-scan found "
            f"{result['scan']['variable_iface_ids']} supporting IVariableFilletFeatureData2 "
            "→ pursue that distinct CreateDefinition id."
        )
    else:
        overall = "NO-MEMBERS"
        interp = (
            "Initialize(var) runs but no variable-radius setter is present and no "
            "distinct CreateDefinition id supports the variable interface → try the "
            "legacy InsertFeatureFillet FeatureManager method."
        )
    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS-DIRECT": 0, "PASS-CONST": 2, "NO-MEMBERS": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
