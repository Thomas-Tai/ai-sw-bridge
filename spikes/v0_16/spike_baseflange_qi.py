"""
Spike v0.16 / S-BASEFLANGE-QI — sheet-metal base flange via the
CreateDefinition → typed_qi pipeline (O1 / F2, P1.x).
[authored seat-free; RUN ON A LIVE SEAT]

The v0.15 attempt (spikes/v0_15/_results/earlybind_features.json) created the
base flange the WRONG way — through the legacy
``IFeatureManager.InsertSheetMetalBaseFlange2`` *method*, which rejected its
argument shape ("The Python instance can not be converted to a COM object").
But the typed_qi id-scan (recorded in the feature-data-QI memory) showed
``CreateDefinition(34)`` yields a real base-flange data object — i.e. base
flange IS a ``CreateDefinition``-shaped feature, and the proven
``CreateDefinition → typed_qi(IFeatureData) → set props → CreateFeature``
pipeline (the one that materialized Fillet) was never tried for it.

This spike tries exactly that path.

WHAT THIS SPIKE DISTINGUISHES
-----------------------------
``typed_qi`` and ``typed`` wrap with the **same** makepy class, so typed_qi's
only edge over a plain wrap is *sound acquisition* (no dispid-collision
misID) — it cannot add members the makepy class lacks. So a base-flange
attempt can fail in two very different ways, and this spike tells them apart:

  * **MEMBER-GAP** — typed_qi acquires the object but the makepy
    ``IBaseFlangeFeatureData`` class is missing the setters we need
    (``Thickness`` / ``BendRadius`` / …). That is a makepy-coverage problem
    (regen the wrapper), not an acquisition problem.
  * **PARTIAL** — members are present and set cleanly, but ``CreateFeature``
    does not materialize → selection/setup or marshaler wall; run ``--mode vba``.

Flow
----
  1. NewDocument part (own doc; never touches the user's files).
  2. Draw a closed rectangle profile sketch on the Front Plane.
  3. ``CreateDefinition(34)`` (falls back to a 30..40 scan if 34 is wrong on
     this build) → ``typed_qi(IBaseFlangeFeatureData)``.
  4. Probe the member surface (which setters exist), set Thickness/BendRadius.
  5. Select the profile sketch, ``CreateFeature``.

Verdict
-------
PASS       : base flange materializes → build the F2 base-flange handler on
             the CreateDefinition+typed_qi pipeline (NOT the Insert* method).
PARTIAL    : data object acquired + props set, but CreateFeature no-op →
             selection/marshaler wall; run --mode vba.
MEMBER-GAP : typed_qi acquires the object but required setters are missing
             from the makepy class → regenerate makepy for the SW typelib,
             then retry (this is a wrapper-coverage finding, not an API gap).
FAIL       : no CreateDefinition id yields a base-flange data object on this
             build → base flange is not CreateDefinition-shaped here; fall
             back to the Insert* method thread (Wall 2).

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_baseflange_qi.py --out report.json
    python spikes/v0_16/spike_baseflange_qi.py --mode vba
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

# CreateDefinition id for base flange (from the typed_qi id-scan in the
# feature-data-QI memory). Scanned as a fallback if wrong on this build.
SW_FM_BASEFLANGE = 34
_BASEFLANGE_SCAN_RANGE = range(28, 44)

IFACE = "IBaseFlangeFeatureData"

# Profile rectangle (metres) — 40×30 mm on the Front Plane.
PROF_W_M = 0.040
PROF_H_M = 0.030

# Sheet-metal parameters (metres).
THICKNESS_M = 0.002   # 2 mm
BEND_RADIUS_M = 0.001  # 1 mm

# Candidate scalar setters on IBaseFlangeFeatureData (probed for presence).
CANDIDATE_MEMBERS = (
    "Thickness",
    "BendRadius",
    "ReverseDirection",
    "UseGaugeTable",
    "GaugeTableName",
    "CustomBendAllowance",
    "OverrideRadius",
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
    """Run *fn*; return (json-safe record, raw value). COM objects stay out
    of the record."""
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _probe_members(obj: Any, names: tuple[str, ...]) -> dict[str, str]:
    """Record which candidate members are reachable on the typed wrapper.

    The makepy class surface — not the binding path — decides this, so a
    missing member is a makepy-coverage gap, not a typed_qi limitation.
    """
    out: dict[str, str] = {}
    for name in names:
        try:
            getattr(obj, name)
            out[name] = "present"
        except AttributeError:
            out[name] = "MISSING"
        except Exception as e:  # noqa: BLE001
            out[name] = f"reachable({type(e).__name__})"
    return out


# ---------------------------------------------------------------------------
# Profile sketch
# ---------------------------------------------------------------------------

def _build_profile(doc: Any) -> dict[str, Any]:
    """Closed rectangle on the Front Plane (the base-flange profile)."""
    out: dict[str, Any] = {}
    try:
        doc.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        seg = sk.CreateCornerRectangle(
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0,
            PROF_W_M / 2, PROF_H_M / 2, 0.0,
        )
        sk.InsertSketch(True)
        out["built"] = seg is not None
        out["sketch"] = "Sketch1"
    except Exception as e:  # noqa: BLE001
        out["built"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return out


def _acquire_baseflange_data(fm: Any, mod: Any) -> dict[str, Any]:
    """CreateDefinition(34) → typed_qi(IBaseFlangeFeatureData); fall back to a
    small scan if 34 is wrong on this build."""
    out: dict[str, Any] = {}

    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
    out["create_definition_34"] = def_rec
    if data is not None:
        qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE, module=mod))
        out["typed_qi"] = qi_rec
        if wrapped is not None:
            out["id"] = SW_FM_BASEFLANGE
            out["_data"], out["_typed"] = data, wrapped
            return out

    # Fallback scan.
    scan: dict[int, str] = {}
    for i in _BASEFLANGE_SCAN_RANGE:
        d_rec, d = _capture(lambda i=i: fm.CreateDefinition(i))
        if d is None:
            scan[i] = "None"
            continue
        q_rec, w = _capture(lambda d=d: typed_qi(d, IFACE, module=mod))
        scan[i] = "OK" if w is not None else f"def-ok/qi-{q_rec.get('status')}"
        if w is not None:
            out["scan"] = scan
            out["id"] = i
            out["_data"], out["_typed"] = d, w
            return out
    out["scan"] = scan
    return out


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind.typed_qi)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    acquired = False
    members: dict[str, str] = {}
    set_recs: dict[str, Any] = {}
    create_rec: dict[str, Any] = {}
    try:
        prof = _build_profile(doc)
        result["profile"] = prof
        if not prof.get("built"):
            return {**result, "overall": "FAIL", "reason": "profile sketch failed"}

        fm = doc.FeatureManager
        acq = _acquire_baseflange_data(fm, mod)
        data = acq.pop("_data", None)
        typed_obj = acq.pop("_typed", None)
        result["acquire"] = acq
        result["acquired_id"] = acq.get("id")
        acquired = typed_obj is not None

        if acquired:
            members = _probe_members(typed_obj, CANDIDATE_MEMBERS)
            result["members"] = members

            for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
                if members.get(name) == "present":
                    rec, _ = _capture(lambda n=name, v=val: setattr(typed_obj, n, v))
                    set_recs[name] = rec
            result["set_props"] = set_recs

            # Select the profile sketch, then materialize.
            sel_rec, _ = _capture(
                lambda: doc.SelectByID2(prof["sketch"], "SKETCH", 0, 0, 0, False, 0, None, 0)
            )
            result["select_profile"] = sel_rec

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
    required_present = all(
        members.get(n) == "present" for n in ("Thickness", "BendRadius")
    )
    if not acquired:
        overall = "FAIL"
        interp = (
            "no CreateDefinition id yielded an IBaseFlangeFeatureData object on "
            "this build → base flange is not CreateDefinition-shaped here; fall "
            "back to the InsertSheetMetalBaseFlange2 method thread (Wall 2)."
        )
    elif not required_present:
        overall = "MEMBER-GAP"
        interp = (
            "typed_qi ACQUIRED the base-flange data object, but the makepy "
            "IBaseFlangeFeatureData class is missing required setters "
            f"({members}) → regenerate makepy for the SW typelib and retry. "
            "This is a wrapper-coverage gap, not an acquisition or API gap."
        )
    elif create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            "base flange materializes via CreateDefinition+typed_qi → build the "
            "F2 base-flange handler on this pipeline (NOT the Insert* method that "
            "failed in v0.15)."
        )
    else:
        overall = "PARTIAL"
        interp = (
            "data object acquired and props set, but CreateFeature did not "
            "materialize → selection/setup or marshaler wall; run --mode vba to "
            "isolate (sheet-metal base flange may need extra setup the spike omits)."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


# ---------------------------------------------------------------------------
# VBA oracle
# ---------------------------------------------------------------------------

def emit_vba() -> str:
    return r"""' Spike v0.16 S-BASEFLANGE-QI VBA oracle.
' Paste into a Part with a closed rectangle sketch (Sketch1) on the Front Plane.
Option Explicit
Sub ProbeBaseFlange()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.BaseFlangeFeatureData
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Set fd = fm.CreateDefinition(34)        ' base-flange id from Python scan
    If fd Is Nothing Then MsgBox "CreateDefinition(34) Nothing": Exit Sub
    fd.Thickness = 0.002
    fd.BendRadius = 0.001

    Part.ClearSelection2 True
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 0, Nothing, 0
    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING"
    Else
        MsgBox "Base flange: " & feat.Name & " / " & feat.GetTypeName2
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_baseflange_qi.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

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

    return {"PASS": 0, "PARTIAL": 2, "MEMBER-GAP": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
