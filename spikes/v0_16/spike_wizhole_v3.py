"""
Spike v0.16 / S-WIZHOLE-V3 — wizard hole WITH a positioned sketch point.
[authored seat-free; RUN ON A LIVE SEAT]

v2 proved the mechanism: ``InitializeHole(...)`` succeeds (the old MEMBER-GAP
was a wrong-name artifact). v2's only remaining wall was PLACEMENT — it
pre-selected the face but ``CreateFeature`` no-op'd because the wizard hole had
no *position*. The SW hole-wizard workflow positions each hole at a pre-selected
**sketch point**, not at a bare face.

This spike creates a sketch point on the top face first, selects it, then runs
the v2 InitializeHole pipeline.

Flow
----
  1. NewDocument part; 20×20×10 box.
  2. Open a sketch on the top face; ``CreatePoint`` at an offset location; close.
  3. ``CreateDefinition(25)`` → ``typed_qi(IWizardHoleFeatureData2)``.
  4. ``InitializeHole(swWzdHole, AnsiMetric, drillSizes, "6.0", blind)``; set Depth.
  5. Select the sketch point; ``CreateFeature``.

Verdict
-------
PASS        : wizard hole materializes → build the F2 wizhole handler on
              point-placement + InitializeHole.
PARTIAL     : InitializeHole + point selection OK but CreateFeature no-op →
              placement still off (point not recognised as the hole position);
              record select_point and try a different selection/order.
INIT-FAIL   : every InitializeHole combo raised.
FAIL        : box/point build or acquisition failed.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_wizhole_v3.py --out report.json
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

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
HOLE_DEPTH_M = 0.006

# Point location on the top face (sketch-local ≈ world XY; face at z=BOX_D_M).
PT_X = 0.003
PT_Y = 0.002

SW_WZD_HOLE = 2
SW_STD_ANSI_METRIC = 1
SW_FAST_ANSI_METRIC_DRILL_SIZES = 39
SW_FAST_ANSI_METRIC_TAP_DRILLS = 41
SW_END_BLIND = 0

INIT_COMBOS = (
    (
        SW_WZD_HOLE,
        SW_STD_ANSI_METRIC,
        SW_FAST_ANSI_METRIC_DRILL_SIZES,
        "6.0",
        SW_END_BLIND,
    ),
    (
        SW_WZD_HOLE,
        SW_STD_ANSI_METRIC,
        SW_FAST_ANSI_METRIC_TAP_DRILLS,
        "M6",
        SW_END_BLIND,
    ),
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
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
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


def _place_point(doc: Any) -> dict[str, Any]:
    """Open a sketch on the top face, drop a point, close. Returns a record
    including the created SketchPoint object under '_pt'."""
    out: dict[str, Any] = {}
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", 0, 0, BOX_D_M):
        return {"ok": False, "error": "could not select top face for sketch"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    rec, pt = _capture(lambda: sk.CreatePoint(PT_X, PT_Y, 0.0))
    out["create_point"] = rec
    sk.InsertSketch(True)  # close
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    out["ok"] = pt is not None
    out["_pt"] = pt
    return out


def _select_point(doc: Any, pt: Any) -> dict[str, Any]:
    """Select the placement point: try the object's own Select, then by coords."""
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    # (a) select via the SketchPoint object directly.
    for meth, args in (
        ("Select4", (False, None)),
        ("Select2", (False, 0)),
        ("Select", (False,)),
    ):
        m = getattr(pt, meth, None)
        if m is None:
            continue
        rec, ok = _capture(lambda m=m, a=args: m(*a))
        if rec["status"] == "OK" and ok:
            return {"via": meth, **rec, "selected": True}
    # (b) fall back to coordinate selection.
    rec, ok = _capture(lambda: doc.SelectByID("", "SKETCHPOINT", PT_X, PT_Y, BOX_D_M))
    return {"via": "SelectByID", **rec, "selected": bool(ok)}


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind.typed_qi)"}

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
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    acquired = False
    init_ok = False
    point_selected = False
    create_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        place = _place_point(doc)
        pt = place.pop("_pt", None)
        result["place_point"] = place
        if not place.get("ok"):
            return {
                **result,
                "overall": "FAIL",
                "reason": "could not create sketch point",
            }

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_HOLE_WZD))
        result["create_definition_25"] = def_rec
        if data is None:
            return {
                **result,
                "overall": "FAIL",
                "reason": "CreateDefinition(25) returned None",
            }

        qi_rec, fd = _capture(lambda: typed_qi(data, IFACE, module=mod))
        result["typed_qi"] = qi_rec
        acquired = fd is not None

        if acquired:
            init_attempts: list[dict[str, Any]] = []
            for combo in INIT_COMBOS:
                rec, _ = _capture(lambda c=combo: fd.InitializeHole(*c))
                rec["combo"] = combo
                init_attempts.append(rec)
                if rec["status"] == "OK":
                    init_ok = True
                    result["init_combo_used"] = combo
                    break
            result["initialize_hole"] = init_attempts

            if init_ok:
                if hasattr(fd, "Depth"):
                    r, _ = _capture(lambda: setattr(fd, "Depth", HOLE_DEPTH_M))
                    result["set_depth"] = r

                sel = _select_point(doc, pt)
                result["select_point"] = sel
                point_selected = sel.get("selected", False)

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
        overall, interp = (
            "FAIL",
            "typed_qi(IWizardHoleFeatureData2) acquisition failed.",
        )
    elif not init_ok:
        overall, interp = (
            "INIT-FAIL",
            "every InitializeHole combo raised (wrong table args).",
        )
    elif create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            "wizard hole materializes via point-placement + InitializeHole → "
            "build the F2 wizhole handler on this pipeline (select a sketch point, "
            "CreateDefinition(25) → typed_qi → InitializeHole → CreateFeature)."
        )
    else:
        overall = "PARTIAL"
        interp = (
            f"InitializeHole OK, point_selected={point_selected}, but CreateFeature "
            "no-op → placement still not recognised; inspect select_point.via and "
            "try selecting the point before InitializeHole, or pre-select face+point."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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

    return {"PASS": 0, "PARTIAL": 2, "INIT-FAIL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
