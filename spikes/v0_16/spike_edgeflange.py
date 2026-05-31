"""Spike v0.16 — S-EDGEFLANGE: crack the edge-flange marshaling wall.

Prior S-SHEETMETAL-v2 was PARTIAL: ``CreateDefinition(37) ->
typed_qi(IEdgeFlangeFeatureData)`` acquires fine, but the only edge-feed it
tried — ``AddEdges([edge])`` (a VARIANT *array*) — left ``GetEdgeCount()`` at 0
out-of-process, so ``CreateFeature`` no-ops. This spike drops the array path and
tries the UNTRIED edge-feed variants; the first that pushes ``GetEdgeCount() >= 1``
(and ideally materializes a feature) wins.

Routes (first PASS wins). Each re-acquires a fresh feature-data so a failed feed
cannot pollute the next attempt:

  FeatureData edge-feeds (CreateDefinition(37) -> typed_qi -> FEED -> props ->
  CreateFeature):
    F1  ISetEdges(1, (edge,))            — explicit-count early-bound setter
    F2  AddEdges(edge)                   — SINGLE dispatch (prior passed a list)
    F3  AddEdges((edge,), None)          — array + explicit SketchArray=None
    F4  pre-select(Select2) then AddEdges(edge)
    F5  pre-select(Select2) then CreateFeature  — bare selection set, no feed

  Legacy fallback:
    L1  InsertSheetMetalEdgeFlange(edge, None, 0, angle, radius, 0, 0, 0, ...)
        — single FlangeEdge dispatch (no array marshaling)

Reuses the seat-proven base-flange build + live-edge acquisition from
``spike_sheetmetal_v2`` (importing them, not re-deriving).

Usage:
    python spikes/v0_16/spike_edgeflange.py --out spikes/v0_16/_results/edgeflange.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402
from spike_sheetmetal_v2 import (  # noqa: E402
    EDGE_FLANGE_ANGLE_RAD,
    EDGE_FLANGE_RADIUS_M,
    IFACE_EDGEFLANGE,
    SW_DEFAULT_TEMPLATE_PART,
    SW_FM_EDGEFLANGE,
    _build_base_flange,
    _build_profile,
    _capture,
    _find_bendable_edges,
    _materialized,
    _title,
    _try_close,
    _type_name,
)


def _set_props(w: Any) -> dict[str, Any]:
    recs: dict[str, Any] = {}
    for name, val in (("BendAngle", EDGE_FLANGE_ANGLE_RAD),
                      ("BendRadius", EDGE_FLANGE_RADIUS_M)):
        rec, _ = _capture(lambda n=name, v=val: setattr(w, n, v))
        recs[name] = rec.get("status")
    return recs


def _edge_count(w: Any) -> Any:
    try:
        return w.GetEdgeCount()
    except Exception as e:  # noqa: BLE001
        return f"ERR:{type(e).__name__}"


# ---- edge-feed strategies (each returns a json-safe record) ----------------


def _feed_isetedges(doc: Any, w: Any, edge: Any) -> dict[str, Any]:
    rec, _ = _capture(lambda: w.ISetEdges(1, (edge,)))
    return {"call": "ISetEdges(1,(edge,))", **rec}


def _feed_addedges_single(doc: Any, w: Any, edge: Any) -> dict[str, Any]:
    rec, _ = _capture(lambda: w.AddEdges(edge))
    return {"call": "AddEdges(edge)", **rec}


def _feed_addedges_array2(doc: Any, w: Any, edge: Any) -> dict[str, Any]:
    rec, _ = _capture(lambda: w.AddEdges((edge,), None))
    return {"call": "AddEdges((edge,),None)", **rec}


def _feed_preselect_then_add(doc: Any, w: Any, edge: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"call": "Select2 then AddEdges(edge)"}
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["select"] = bool(edge.Select2(False, 0))
    except Exception as e:  # noqa: BLE001
        out["select_err"] = f"{type(e).__name__}: {e}"[:120]
    rec, _ = _capture(lambda: w.AddEdges(edge))
    out["add"] = rec.get("status")
    return out


def _feed_preselect_only(doc: Any, w: Any, edge: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"call": "Select2 only (no feed)"}
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["select"] = bool(edge.Select2(False, 0))
    except Exception as e:  # noqa: BLE001
        out["select_err"] = f"{type(e).__name__}: {e}"[:120]
    return out


_FEEDERS = (
    ("F1", _feed_isetedges),
    ("F2", _feed_addedges_single),
    ("F3", _feed_addedges_array2),
    ("F4", _feed_preselect_then_add),
    ("F5", _feed_preselect_only),
)


def _try_featuredata_route(
    doc: Any, fm: Any, mod: Any, edge: Any, tag: str, feeder: Any
) -> dict[str, Any]:
    rec: dict[str, Any] = {"route": tag}
    d_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_EDGEFLANGE))
    if data is None:
        return {**rec, "create_definition": d_rec, "overall": "FAIL"}
    q_rec, w = _capture(lambda: typed_qi(data, IFACE_EDGEFLANGE, module=mod))
    if w is None:
        return {**rec, "typed_qi": q_rec, "overall": "FAIL"}
    rec["feed"] = feeder(doc, w, edge)
    rec["edge_count_after_feed"] = _edge_count(w)
    rec["set_props"] = _set_props(w)
    feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
    feat_rec["materialized"] = _materialized(feat)
    if _materialized(feat):
        feat_rec["type_name"] = _type_name(feat)
        feat_rec["name"] = getattr(feat, "Name", None)
    rec["create_feature"] = feat_rec
    if _materialized(feat):
        rec["overall"] = "PASS"
    elif isinstance(rec["edge_count_after_feed"], int) and rec["edge_count_after_feed"] >= 1:
        rec["overall"] = "PARTIAL-FED"  # edges accepted but CreateFeature no-op
    else:
        rec["overall"] = "NO-EDGE"
    return rec


def _rank_linear_edges(edges: list, mod: Any) -> list[dict[str, Any]]:
    """Rank edges by length (longest linear first) to dodge the thickness trap.

    Live persist-resolved edges -> typed IEdge -> ICurve; IsLine() + GetLength
    over the end params. The 2mm thickness edges rank last; the long boundary
    edges of the base flange rank first.
    """
    ranked: list[dict[str, Any]] = []
    for ei, e in enumerate(edges):
        info: dict[str, Any] = {"index": ei, "edge": e, "is_line": False, "length": 0.0}
        try:
            ie = typed_qi(e, "IEdge", module=mod)
            cv = typed_qi(ie.GetCurve(), "ICurve", module=mod)
            info["is_line"] = bool(cv.IsLine())
            ep = cv.GetEndParams()  # (status, tmin, tmax, isClosed, isPeriodic)
            tmin, tmax = ep[1], ep[2]
            info["length"] = float(cv.GetLength(tmin, tmax))
        except Exception as exc:  # noqa: BLE001
            info["curve_error"] = f"{type(exc).__name__}: {exc}"[:100]
        ranked.append(info)
    linear = sorted((r for r in ranked if r["is_line"]),
                    key=lambda r: r["length"], reverse=True)
    return linear or sorted(ranked, key=lambda r: r["length"], reverse=True)


def _try_legacy(doc: Any, fm: Any, ranked: list[dict[str, Any]]) -> dict[str, Any]:
    """InsertSheetMetalEdgeFlange2 — COM boundary cracked (double VT_DISPATCH
    nulls for SketchFeats + CustomBendAllowance). Now tune topology: longest
    linear (boundary) edge + a valid BooleanOptions bitmask so the kernel uses
    document defaults instead of the (declined) manual bend/relief values.
    """
    out: dict[str, Any] = {"route": "L - InsertSheetMetalEdgeFlange2 (nulls + tuned params)"}
    vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
    angle = math.pi / 2.0
    radius = 0.002
    offset = 0.05
    # swInsertEdgeFlangeOptions_e: UseDefaultRadius=1, UseReliefRatio=64,
    # UseDefaultRelief=128 -> force document defaults, ignore manual values.
    OPT = (
        ("UseDefRadius|UseDefRelief(129)", 1 | 128),
        ("UseDefRadius|UseReliefRatio|UseDefRelief(193)", 1 | 64 | 128),
        ("UseDefRadius(1)", 1),
    )
    top = ranked[:6]
    out["edge_ranking"] = [
        {"index": r["index"], "is_line": r["is_line"],
         "len_mm": round(r["length"] * 1000, 2)} for r in ranked
    ]
    attempts: list[dict[str, Any]] = []
    for opt_label, opts in OPT:
        for r in top:
            e, ei = r["edge"], r["index"]
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            # (FlangeEdges, SketchFeats, BooleanOptions, FlangeAngle, FlangeRadius,
            #  BendPosition, FlangeOffsetDist, ReliefType, FlangeReliefRatio,
            #  FlangeReliefWidth, FlangeReliefDepth, FlangeSharpType, CustomBendAllowance)
            rec, feat = _capture(lambda e=e, o=opts: fm.InsertSheetMetalEdgeFlange2(
                e, vt_disp, o, angle, radius, 1, offset, 2, 0.5, 0.0, 0.0, 0, vt_disp))
            rec["boolean_options"] = opt_label
            rec["edge_index"] = ei
            rec["edge_len_mm"] = round(r["length"] * 1000, 2)
            rec["materialized"] = _materialized(feat)
            if _materialized(feat):
                rec["type_name"] = _type_name(feat)
                rec["name"] = getattr(feat, "Name", None)
                attempts.append(rec)
                out["attempts"], out["overall"] = attempts, "PASS"
                out["winning"] = f"{opt_label} edge[{ei}] len={rec['edge_len_mm']}mm"
                return out
            attempts.append(rec)
    out["attempts"], out["overall"] = attempts, "FAIL"
    hist: dict[str, int] = {}
    for a in attempts:
        key = a.get("type") if a.get("status") == "OK" else a.get("message")
        hist[str(key)[:70]] = hist.get(str(key)[:70], 0) + 1
    out["return_histogram"] = hist
    return out

def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    fm = doc.FeatureManager
    result["profile"] = _build_profile(doc)
    base = _build_base_flange(doc, fm, mod)
    result["base_flange"] = {k: v for k, v in base.items() if not k.startswith("_")}
    if base.get("overall") != "PASS":
        _try_close(sw, doc)
        return {**result, "overall": "FAIL", "reason": "base flange did not materialize"}

    edges = _find_bendable_edges(doc, mod)
    result["edge_count_found"] = len(edges)
    if not edges:
        _try_close(sw, doc)
        return {**result, "overall": "FAIL", "reason": "no live edges acquired"}

    # Legacy single-edge direct-insert is the primary hypothesis (bypasses the
    # array-marshaling wall) — run it FIRST on the pristine base flange.
    routes: list[dict[str, Any]] = []
    overall = "PARTIAL"
    winner = None
    ranked = _rank_linear_edges(edges, mod)
    leg = _try_legacy(doc, fm, ranked)
    routes.append(leg)
    if leg.get("overall") == "PASS":
        overall, winner = "PASS", leg.get("winning", "L")
    else:
        # FeatureData feed strategies (already characterised as the array wall);
        # kept as supplementary diagnostics, first edge only.
        for tag, feeder in _FEEDERS:
            r = _try_featuredata_route(doc, fm, mod, edges[0], tag, feeder)
            routes.append(r)
            if r.get("overall") == "PASS":
                overall, winner = "PASS", tag
                break
    result["routes"] = routes
    result["winner"] = winner

    # If any feed pushed edge_count>=1 but no materialize, that's the key signal.
    fed = [r for r in routes if r.get("overall") == "PARTIAL-FED"]
    if overall != "PASS" and fed:
        overall = "PARTIAL-FED"
    result["overall"] = overall
    result["interpretation"] = {
        "PASS": f"edge flange materialized via {winner} — build the handler.",
        "PARTIAL-FED": "a feed pushed GetEdgeCount>=1 but CreateFeature no-op — "
                       "edges now marshal; narrow the remaining CreateFeature gap.",
        "PARTIAL": "no feed pushed GetEdgeCount>=1 and nothing materialized — the "
                   "out-of-process edge-array marshaling wall persists across all "
                   "variants; escalate (VBA oracle / different edge acquisition).",
    }.get(overall, "")

    _try_close(sw, doc)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep-file", action="store_true")
    args = ap.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>")
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL-FED": 2, "PARTIAL": 2, "FAIL": 1}.get(
        result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
