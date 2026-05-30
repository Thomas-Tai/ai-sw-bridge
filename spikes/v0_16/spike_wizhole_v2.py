"""
Spike v0.16 / S-WIZHOLE-V2 — wizard hole via the REAL setup call.
[authored seat-free; RUN ON A LIVE SEAT]

Supersedes ``spike_wizhole_qi.py`` (verdict MEMBER-GAP), whose root cause was
FALSIFIED by the 2026-05-30 typelib audit. That spike chased ``HoleType`` /
``Initialize`` / ``Initialize2`` / ``GetHoleElementCount`` — **none of which
exist anywhere in sldworks.tlb.** It was not a makepy coverage gap; the spike
called methods this API never had, so ``CreateFeature`` no-op'd.

The authoritative walk of ``IWizardHoleFeatureData2`` (79 funcs, fully present
in the demand-generated makepy) shows the real setup method is::

    InitializeHole(GenericHoleType:i4, StdIndex:i4, FastnerType:i4,
                   SSize:bstr, EndType:i4)

Enums (swconst.tlb):
  * GenericHoleType — swWzdGeneralHoleTypes_e: swWzdHole = 2
  * StdIndex        — swWzdHoleStandards_e:    swStandardAnsiMetric = 1
  * FastnerType     — swWzdHoleStandardFastenerTypes_e: swStandardAnsiMetricTapDrills = 41
  * EndType         — swEndConditions_e:        swEndCondBlind = 0

This spike calls ``InitializeHole`` (the step the old spike skipped), sets a
depth, places the hole on the box's top face, and tries to materialize.

Flow
----
  1. NewDocument part; 20×20×10 box; select the top face.
  2. ``CreateDefinition(25)`` → ``typed_qi(IWizardHoleFeatureData2)``.
  3. ``InitializeHole(swWzdHole, swStandardAnsiMetric, swStandardAnsiMetricTapDrills,
     "M6", swEndCondBlind)`` — try a couple of (fastener, size) combos.
  4. Set ``Depth``; re-select the top face; ``CreateFeature``.

Verdict
-------
PASS       : wizard hole materializes → build the F2 hole handler on
             CreateDefinition → typed_qi → InitializeHole.
PARTIAL    : InitializeHole succeeds + props set, but CreateFeature no-op →
             placement wall (wizard holes want a positioned sketch point on the
             face); add point placement / pre-selection, then retry.
INIT-FAIL  : every InitializeHole combo raised → wrong enum/size arguments for
             this build's tables; record the exceptions and adjust.
FAIL       : CreateDefinition(25) / typed_qi did not yield a usable object.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_wizhole_v2.py --out report.json
    python spikes/v0_16/spike_wizhole_v2.py --mode vba
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
SW_FM_HOLE_WZD = 25
IFACE = "IWizardHoleFeatureData2"

# Box (metres). Top face center is (0, 0, +BOX_D_M).
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

HOLE_DEPTH_M = 0.006

# swconst enums (verified by spikes/v0_16/_investigate_enums.py).
SW_WZD_HOLE = 2                       # swWzdGeneralHoleTypes_e.swWzdHole
SW_STD_ANSI_METRIC = 1               # swWzdHoleStandards_e.swStandardAnsiMetric
SW_FAST_ANSI_METRIC_TAP_DRILLS = 41  # swWzdHoleStandardFastenerTypes_e
SW_FAST_ANSI_METRIC_DRILL_SIZES = 39
SW_END_BLIND = 0                     # swEndConditions_e.swEndCondBlind

# (GenericHoleType, StdIndex, FastnerType, SSize, EndType) combos to try in
# order; the first that doesn't raise wins. Sizes are guesses against the
# metric drill/tap tables — the spike records which the build accepts.
INIT_COMBOS = (
    (SW_WZD_HOLE, SW_STD_ANSI_METRIC, SW_FAST_ANSI_METRIC_DRILL_SIZES, "6.0", SW_END_BLIND),
    (SW_WZD_HOLE, SW_STD_ANSI_METRIC, SW_FAST_ANSI_METRIC_TAP_DRILLS, "M6", SW_END_BLIND),
    (SW_WZD_HOLE, SW_STD_ANSI_METRIC, SW_FAST_ANSI_METRIC_TAP_DRILLS, "M6x1.0", SW_END_BLIND),
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


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
        BOX_W_M / 2, BOX_H_M / 2, 0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0,
    )
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


def _select_top_face(doc: Any) -> dict[str, Any]:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    rec, ok = _capture(lambda: doc.SelectByID("", "FACE", 0, 0, BOX_D_M))
    rec["selected"] = bool(ok)
    return rec


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
    init_ok = False
    create_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        # Pre-select the placement face before defining the hole.
        result["select_face_pre"] = _select_top_face(doc)

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_HOLE_WZD))
        result["create_definition_25"] = def_rec
        if data is None:
            return {**result, "overall": "FAIL", "reason": "CreateDefinition(25) returned None"}

        qi_rec, fd = _capture(lambda: typed_qi(data, IFACE, module=mod))
        result["typed_qi"] = qi_rec
        acquired = fd is not None

        if acquired:
            # Confirm InitializeHole is reachable (it is, per the audit).
            result["has_InitializeHole"] = hasattr(fd, "InitializeHole")

            init_attempts: list[dict[str, Any]] = []
            for combo in INIT_COMBOS:
                rec, ret = _capture(lambda c=combo: fd.InitializeHole(*c))
                rec["combo"] = combo
                init_attempts.append(rec)
                if rec["status"] == "OK":
                    init_ok = True
                    result["init_combo_used"] = combo
                    break
            result["initialize_hole"] = init_attempts

            if init_ok:
                # Best-effort scalar props.
                set_recs: dict[str, Any] = {}
                for name, val in (("Depth", HOLE_DEPTH_M),):
                    if hasattr(fd, name):
                        r, _ = _capture(lambda n=name, v=val: setattr(fd, n, v))
                        set_recs[name] = r
                result["set_props"] = set_recs

                # Re-assert the placement face (InitializeHole may clear it).
                result["select_face_post"] = _select_top_face(doc)

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
    if not acquired:
        overall = "FAIL"
        interp = "typed_qi(IWizardHoleFeatureData2) failed to acquire the object."
    elif not init_ok:
        overall = "INIT-FAIL"
        interp = (
            "every InitializeHole(GenericHoleType, StdIndex, FastnerType, SSize, "
            "EndType) combo raised → the enum/size arguments are wrong for this "
            "build's hole tables. Inspect the recorded exceptions and the "
            "swWzdHoleStandardFastenerTypes_e / size strings, then adjust."
        )
    elif create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            "wizard hole materializes via CreateDefinition(25) → typed_qi → "
            "InitializeHole → CreateFeature. Build the F2 hole handler on this "
            "pipeline. (Confirms the old MEMBER-GAP verdict was a wrong-call "
            "artifact, not a makepy gap.)"
        )
    else:
        overall = "PARTIAL"
        interp = (
            "InitializeHole succeeded and props set, but CreateFeature did not "
            "materialize → placement wall: wizard holes need a positioned sketch "
            "point on the face (face pre-selection alone is insufficient). Add a "
            "sketch point at the hole location, then retry."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-WIZHOLE-V2 VBA oracle.
' Paste into a Part with a 20x20x10 box. Tests the REAL InitializeHole path.
Option Explicit
Sub ProbeWizHoleV2()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.WizardHoleFeatureData2
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0

    Set fd = fm.CreateDefinition(swFmHoleWzd)    ' 25
    If fd Is Nothing Then MsgBox "CreateDefinition(25) Nothing": Exit Sub
    ' swWzdHole=2, swStandardAnsiMetric=1, fastener=39 (metric drill sizes)
    fd.InitializeHole 2, 1, 39, "6.0", 0          ' swEndCondBlind=0
    fd.Depth = 0.006

    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING (placement likely needs a sketch point)"
    Else
        MsgBox "Wizard hole: " & feat.Name & " / " & feat.GetTypeName2
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
        out = Path(__file__).parent / "spike_wizhole_v2.bas"
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

    return {"PASS": 0, "PARTIAL": 2, "INIT-FAIL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
