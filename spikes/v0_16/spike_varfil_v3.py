"""
Spike v0.16 / S-VARFIL-V3 — distinct PER-EDGE radii on a multi-radius fillet.
[authored seat-free; RUN ON A LIVE SEAT]

v2 proved multi-radius *creation* (IsMultipleRadius=True → Fillet1 materializes)
but `FilletItemsCount` was 0 *before* CreateFeature, so the fillet items (one
per edge, each carrying its own radius) only exist on the created feature. A
genuinely "variable across edges" fillet needs DIFFERENT radii per edge, so this
spike tests the edit path:

    create multi-radius fillet (default radius)
      → feat.GetDefinition() → typed_qi(ISimpleFilletFeatureData2)
      → AccessSelections(doc) → for each fillet item: SetRadius(item, r_i)
      → feat.ModifyDefinition(defn, doc, None)
      → re-read each item's radius to confirm distinct values stuck.

Verdict
-------
PASS-PER-EDGE : items enumerable post-create AND distinct radii read back →
                build a variable_radius_fillet handler (create-then-edit).
PARTIAL-EDIT  : items enumerable but SetRadius/ModifyDefinition didn't stick →
                record what failed (AccessSelections / ModifyDefinition shape).
NO-ITEMS      : FilletItemsCount still 0 on the created feature's definition →
                per-edge radii use a different accessor; record and rethink.
FAIL          : multi-radius creation regressed.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_varfil_v3.py --out report.json
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_FILLET = 1
SW_CONST_RADIUS_FILLET = 0
IFACE = "ISimpleFilletFeatureData2"

BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
DEFAULT_RADIUS_M = 0.003
PER_EDGE_RADII_M = (0.002, 0.004)

TOP_EDGES = (
    (0.0, BOX_H_M / 2, BOX_D_M),
    (BOX_W_M / 2, 0.0, BOX_D_M),
)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


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


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
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
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _select_edges(doc: Any) -> int:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    n = 0
    for (x, y, z) in TOP_EDGES:
        if doc.SelectByID("", "EDGE", x, y, z):
            n += 1
    return n


def _get_definition(feat: Any, mod: Any) -> Any:
    """GetDefinition, falling back to early-bound IFeature when late-bind
    raises 'Member not found'."""
    try:
        d = feat.GetDefinition()
        if d is not None:
            return d
    except Exception:  # noqa: BLE001
        pass
    tf = typed(feat, "IFeature", module=mod)
    return tf.GetDefinition()


def _per_item_radii(defn: Any) -> list[Any]:
    out: list[Any] = []
    try:
        count = int(defn.FilletItemsCount)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"FilletItemsCount: {type(e).__name__}: {e}"}]
    for i in range(count):
        rec, item = _capture(lambda i=i: defn.GetFilletItemAtIndex(i))
        entry: dict[str, Any] = {"index": i, "get_item": rec}
        if item is not None:
            rrec, r = _capture(lambda it=item: defn.GetRadius(it))
            entry["radius"] = r
        out.append(entry)
    return out


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
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    items_count = 0
    readback: list[Any] = []
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        fm = doc.FeatureManager
        _, data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
        if data is None:
            return {**result, "overall": "FAIL", "reason": "CreateDefinition(1) None"}
        _, fd = _capture(lambda: typed_qi(data, IFACE, module=mod))
        fd.Initialize(SW_CONST_RADIUS_FILLET)
        fd.DefaultRadius = DEFAULT_RADIUS_M
        fd.IsMultipleRadius = True
        result["edges_selected"] = _select_edges(doc)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        result["create_feature"] = {**feat_rec, "materialized": _materialized(feat)}
        if not _materialized(feat):
            return {**result, "overall": "FAIL", "reason": "multi-radius create no-op"}
        result["create_feature"]["feature_name"] = getattr(feat, "Name", None)

        # --- edit path: set distinct per-edge radii -------------------------
        def_rec, defn_raw = _capture(lambda: _get_definition(feat, mod))
        result["get_definition"] = def_rec
        if defn_raw is None:
            return {**result, "overall": "PARTIAL-EDIT", "reason": "GetDefinition None"}
        _, defn = _capture(lambda: typed_qi(defn_raw, IFACE, module=mod))
        defn = defn if defn is not None else defn_raw

        acc_rec, _ = _capture(lambda: defn.AccessSelections(doc, None))
        result["access_selections"] = acc_rec

        try:
            items_count = int(defn.FilletItemsCount)
        except Exception:  # noqa: BLE001
            items_count = 0
        result["fillet_items_count_post"] = items_count

        set_recs: list[dict[str, Any]] = []
        for i in range(min(items_count, len(PER_EDGE_RADII_M))):
            irec, item = _capture(lambda i=i: defn.GetFilletItemAtIndex(i))
            if item is None:
                set_recs.append({"index": i, "get_item": irec})
                continue
            r = PER_EDGE_RADII_M[i]
            srec, _ = _capture(lambda it=item, r=r: defn.SetRadius(it, r))
            set_recs.append({"index": i, "radius_m": r, "set_radius": srec})
        result["set_per_item"] = set_recs

        # ModifyDefinition(Definition, Doc, Component). Late-bind raised
        # "Type mismatch" marshaling the None Component; try early-bound IFeature
        # (and the raw data dispatch) which marshal per the typelib.
        mod_attempts: list[dict[str, Any]] = []
        mod_ret = None
        tf = typed(feat, "IFeature", module=mod)
        for label, fn in (
            ("typed_feat_raw_defn", lambda: tf.ModifyDefinition(defn_raw, doc, None)),
            ("typed_feat_qi_defn", lambda: tf.ModifyDefinition(defn, doc, None)),
            ("dyn_feat_raw_defn", lambda: feat.ModifyDefinition(defn_raw, doc, None)),
        ):
            rec, mod_ret = _capture(fn)
            rec["variant"] = label
            mod_attempts.append(rec)
            if rec["status"] == "OK":
                break
        result["modify_definition"] = mod_attempts

        # Re-read the radii to confirm distinct values stuck.
        def_rec2, defn2_raw = _capture(lambda: _get_definition(feat, mod))
        if defn2_raw is not None:
            _, defn2 = _capture(lambda: typed_qi(defn2_raw, IFACE, module=mod))
            defn2 = defn2 if defn2 is not None else defn2_raw
            try:
                defn2.AccessSelections(doc, None)
            except Exception:  # noqa: BLE001
                pass
            readback = _per_item_radii(defn2)
        result["radii_readback"] = readback
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
        result["cleanup"] = "closed own doc (no save)"

    # --- Verdict -------------------------------------------------------------
    radii = [e.get("radius") for e in readback if isinstance(e, dict) and "radius" in e]
    distinct = {round(float(r), 6) for r in radii if isinstance(r, (int, float))}
    expected = {round(r, 6) for r in PER_EDGE_RADII_M}
    if items_count <= 0:
        overall = "NO-ITEMS"
        interp = ("FilletItemsCount is 0 even on the created feature's definition "
                  "→ per-edge radii use a different accessor; inspect get_definition "
                  "/ access_selections.")
    elif expected.issubset(distinct):
        overall = "PASS-PER-EDGE"
        interp = (f"distinct per-edge radii stuck ({sorted(distinct)} m) → build a "
                  "variable_radius_fillet handler: create multi-radius, GetDefinition, "
                  "SetRadius per item, ModifyDefinition.")
    else:
        overall = "PARTIAL-EDIT"
        interp = (f"items enumerable (count={items_count}) but readback radii "
                  f"{sorted(distinct)} != expected {sorted(expected)} → SetRadius / "
                  "ModifyDefinition shape needs tuning (see set_per_item / modify_definition).")

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

    return {"PASS-PER-EDGE": 0, "PARTIAL-EDIT": 2, "NO-ITEMS": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
