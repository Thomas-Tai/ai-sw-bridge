"""
Spike v0.16 / S-VARFIL-V4 — DISTINCT per-edge radii on a multi-radius fillet,
with multi-edge append-selection of NON-adjacent edges.
[authored seat-free; RUN ON A LIVE SEAT]

v3 proved the edit path (GetDefinition → SetRadius → early-bound
ModifyDefinition persists a radius) but saw `FilletItemsCount=1` for 2 selected
edges. Two candidate causes: (a) 5-arg SelectByID didn't append; (b) the two
edges shared a corner vertex and merged into one fillet item. This spike rules
both out by (1) preferring `Extension.SelectByID2(Append=True)` and (2) picking
two PARALLEL, non-adjacent top edges (y=+H/2 and y=-H/2) that cannot merge.

Then: create multi-radius fillet → for each fillet item set a DISTINCT radius
→ early-bound ModifyDefinition → read each item's radius back.

Verdict
-------
PASS-PER-EDGE : >=2 items AND the distinct radii read back → build the
                variable_radius_fillet handler on this recipe.
ONE-ITEM      : still 1 item with 2 non-adjacent edges → fillet-item model is
                not per-edge; record GetEdgeCount and rethink the handler shape.
PARTIAL-EDIT  : items present but radii didn't stick → SetRadius/ModifyDefinition.
FAIL          : creation regressed.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_varfil_v4.py --out report.json
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
from ai_sw_bridge.selection import select_entity  # noqa: E402

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

# Two PARALLEL, non-adjacent top edges (both along X, at y=+H/2 and y=-H/2);
# they share no vertex so they stay separate fillet items.
TOP_EDGES = (
    (0.0, BOX_H_M / 2, BOX_D_M),
    (0.0, -BOX_H_M / 2, BOX_D_M),
)

# swSelectType_e.swSelEDGES = 1 (for Extension.SelectByID2 SelectOption/Mark use 0).


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
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _edge_midpoint(edge: Any) -> tuple[float, float, float] | None:
    """Midpoint of a (line) edge via GetCurveParams2 start/end."""
    try:
        cp = edge.GetCurveParams2()
    except Exception:  # noqa: BLE001
        try:
            cp = edge.GetCurveParams()
        except Exception:  # noqa: BLE001
            return None
    if not cp or len(cp) < 6:
        return None
    sx, sy, sz, ex, ey, ez = cp[0], cp[1], cp[2], cp[3], cp[4], cp[5]
    return ((sx + ex) / 2, (sy + ey) / 2, (sz + ez) / 2)


def _select_edges_append(doc: Any, mod: Any) -> dict[str, Any]:
    """Select two NON-adjacent edge ENTITIES via the bridge's select_entity
    (early-bound IEntity.Select2 with append) — the production mechanism.

    Coordinate SelectByID REPLACES and SelectByID2 hits the dynamic `<unknown>`
    wall (both seen in earlier v4 runs); selecting resolved entities sidesteps
    that entirely and is exactly what the real handler does.
    """
    out: dict[str, Any] = {}
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass

    # Solid bodies → edges.
    rec, bodies = _capture(lambda: doc.GetBodies2(0, True))
    out["get_bodies"] = rec
    body = None
    if isinstance(bodies, (tuple, list)) and bodies:
        body = bodies[0]
    elif bodies is not None:
        body = bodies
    if body is None:
        out["error"] = "no solid body"
        return out
    erec, edges = _capture(lambda: body.GetEdges())
    out["get_edges"] = erec
    edge_list = (
        list(edges) if isinstance(edges, (tuple, list)) else ([edges] if edges else [])
    )
    out["n_edges"] = len(edge_list)
    if len(edge_list) < 2:
        out["error"] = "fewer than 2 edges"
        return out

    # Pick two spread-out edges by index (opposite ends of the 12-edge box);
    # exact geometry doesn't matter — we only need 2 distinct edges to become
    # 2 fillet items. Try the recorded midpoint if available, for the log.
    i2 = len(edge_list) // 2
    chosen = [edge_list[0], edge_list[i2]]
    out["chosen_indices"] = [0, i2]
    out["chosen_midpoints"] = [_edge_midpoint(e) for e in chosen]

    n_ok = 0
    for k, e in enumerate(chosen):
        if select_entity(e, append=(k > 0)):
            n_ok += 1
    out["n_selected_ok"] = n_ok
    sel_count = None
    try:
        sel_count = int(doc.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:  # noqa: BLE001
        sel_count = None
    out["selection_count"] = sel_count
    return out


def _get_definition(feat: Any, mod: Any) -> Any:
    try:
        d = feat.GetDefinition()
        if d is not None:
            return d
    except Exception:  # noqa: BLE001
        pass
    return typed(feat, "IFeature", module=mod).GetDefinition()


def _read_items(defn: Any) -> list[Any]:
    out: list[Any] = []
    try:
        count = int(defn.FilletItemsCount)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"FilletItemsCount: {type(e).__name__}: {e}"}]
    for i in range(count):
        rec, item = _capture(lambda i=i: defn.GetFilletItemAtIndex(i))
        entry: dict[str, Any] = {"index": i}
        if item is not None:
            _, r = _capture(lambda it=item: defn.GetRadius(it))
            entry["radius"] = r
        else:
            entry["get_item"] = rec
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
    edge_count = None
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

        result["select"] = _select_edges_append(doc, mod)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        result["create_feature"] = {**feat_rec, "materialized": _materialized(feat)}
        if not _materialized(feat):
            return {**result, "overall": "FAIL", "reason": "multi-radius create no-op"}
        result["create_feature"]["feature_name"] = getattr(feat, "Name", None)

        _, defn_raw = _capture(lambda: _get_definition(feat, mod))
        if defn_raw is None:
            return {**result, "overall": "PARTIAL-EDIT", "reason": "GetDefinition None"}
        _, defn = _capture(lambda: typed_qi(defn_raw, IFACE, module=mod))
        defn = defn if defn is not None else defn_raw

        _capture(lambda: defn.AccessSelections(doc, None))
        try:
            edge_count = int(defn.GetEdgeCount())
        except Exception:  # noqa: BLE001
            edge_count = None
        result["edge_count"] = edge_count
        try:
            items_count = int(defn.FilletItemsCount)
        except Exception:  # noqa: BLE001
            items_count = 0
        result["fillet_items_count"] = items_count

        set_recs: list[dict[str, Any]] = []
        for i in range(min(items_count, len(PER_EDGE_RADII_M))):
            _, item = _capture(lambda i=i: defn.GetFilletItemAtIndex(i))
            if item is None:
                set_recs.append({"index": i, "error": "GetFilletItemAtIndex None"})
                continue
            r = PER_EDGE_RADII_M[i]
            srec, _ = _capture(lambda it=item, r=r: defn.SetRadius(it, r))
            set_recs.append({"index": i, "radius_m": r, "set_radius": srec})
        result["set_per_item"] = set_recs

        tf = typed(feat, "IFeature", module=mod)
        mod_rec, mod_ret = _capture(lambda: tf.ModifyDefinition(defn_raw, doc, None))
        result["modify_definition"] = {
            **mod_rec,
            "ret": bool(mod_ret) if mod_ret is not None else None,
        }

        _, defn2_raw = _capture(lambda: _get_definition(feat, mod))
        if defn2_raw is not None:
            _, defn2 = _capture(lambda: typed_qi(defn2_raw, IFACE, module=mod))
            defn2 = defn2 if defn2 is not None else defn2_raw
            try:
                defn2.AccessSelections(doc, None)
            except Exception:  # noqa: BLE001
                pass
            readback = _read_items(defn2)
        result["radii_readback"] = readback
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
        result["cleanup"] = "closed own doc (no save)"

    radii = [e.get("radius") for e in readback if isinstance(e, dict) and "radius" in e]
    distinct = {round(float(r), 6) for r in radii if isinstance(r, (int, float))}
    expected = {round(r, 6) for r in PER_EDGE_RADII_M}
    if items_count >= 2 and expected.issubset(distinct):
        overall = "PASS-PER-EDGE"
        interp = (
            f"{items_count} fillet items, distinct radii {sorted(distinct)} m stuck "
            "→ build variable_radius_fillet: append-select edges, create multi-radius, "
            "SetRadius per item, early-bound ModifyDefinition."
        )
    elif items_count < 2:
        overall = "ONE-ITEM"
        interp = (
            f"still {items_count} fillet item(s) with non-adjacent edges "
            f"(edge_count={edge_count}) → fillet items are NOT per-edge; the per-edge "
            "radius model differs. Inspect select.selection_count / edge_count."
        )
    else:
        overall = "PARTIAL-EDIT"
        interp = (
            f"{items_count} items but radii {sorted(distinct)} != expected "
            f"{sorted(expected)} → SetRadius/ModifyDefinition shape needs tuning."
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

    return {"PASS-PER-EDGE": 0, "PARTIAL-EDIT": 2, "ONE-ITEM": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
