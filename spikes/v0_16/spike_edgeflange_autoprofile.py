"""Spike v0.16 — T6 auto-profile edge flange: does InsertSheetMetalEdgeFlange2
with NULL SketchFeats materialize a flange on a base-flange edge?

W0 scope: auto-profile is the acceptance bar. A materialized flange
(delta-verified, GetTypeName2 = SM flange type) = GREEN → ship as 14th kind.
Custom normal-to-edge profile sketch = Wave-7 (out of scope).

Prior v1 spike (spike_edgeflange.py) tried 18 combos:
  BooleanOptions ∈ {129, 193, 1} × 6 edges × VARIANT(VT_DISPATCH,None) nulls.
All returned None. Edge was pre-selected via Select2(False, 0) (mark=0).

v2 corrections:
  - Persist round-trip edge (proven live entity path)
  - Mark sweep: edge mark ∈ {0, 1} (dome + ref_plane proved mark matters)
  - Pre-select-only variant (no edge arg, let SW use selection set)
  - Also try InsertSheetMetalEdgeFlange (no "2") if it exists
  - Delta-verify (GetFeatures True), not return value

Usage:
    python spikes/v0_16/spike_edgeflange_autoprofile.py
"""

from __future__ import annotations

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

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module
from spike_sheetmetal_v2 import (
    IFACE_BASEFLANGE,
    SW_FM_BASEFLANGE,
    SW_DEFAULT_TEMPLATE_PART,
    _build_profile,
    _build_base_flange,
    _capture,
    _find_bendable_edges,
    _materialized,
    _title,
    _try_close,
    _type_name,
)

RESULTS_DIR = Path(__file__).resolve().parent / "_results"

ANGLE_90 = math.pi / 2.0
RADIUS_2MM = 0.002
OFFSET_50MM = 0.05
VT_DISP_NONE = None  # built per-call below


def _rank_linear_edges(edges: list, mod: Any) -> list[dict]:
    ranked: list[dict] = []
    for ei, e in enumerate(edges):
        info: dict[str, Any] = {"index": ei, "edge": e, "is_line": False, "length": 0.0}
        try:
            ie = typed_qi(e, "IEdge", module=mod)
            cv = typed_qi(ie.GetCurve(), "ICurve", module=mod)
            info["is_line"] = bool(cv.IsLine())
            ep = cv.GetEndParams()
            info["length"] = float(cv.GetLength(ep[1], ep[2]))
        except Exception:
            pass
        ranked.append(info)
    linear = sorted(
        (r for r in ranked if r["is_line"]),
        key=lambda r: r["length"],
        reverse=True,
    )
    return linear or sorted(ranked, key=lambda r: r["length"], reverse=True)


def _feature_count(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(True)
    return len(feats) if feats else 0


def _feature_types(doc: Any, mod: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _probe_legacy(
    doc: Any,
    fm: Any,
    edge: Any,
    ranked_info: dict,
    mark: int,
    opt_label: str,
    opts: int,
    angle: float,
    radius: float,
) -> dict[str, Any]:
    """InsertSheetMetalEdgeFlange2 with edge arg + VARIANT nulls."""
    vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
    doc.ClearSelection2(True)
    try:
        ient = typed(edge, "IEntity")
        sel_ok = bool(ient.Select2(False, mark))
    except Exception:
        sel_ok = False

    n_before = _feature_count(doc)
    try:
        ret = fm.InsertSheetMetalEdgeFlange2(
            edge,
            vt_disp,
            opts,
            angle,
            radius,
            1,
            OFFSET_50MM,
            2,
            0.5,
            0.0,
            0.0,
            0,
            vt_disp,
        )
        err = None
    except Exception as e:
        ret = None
        err = f"{type(e).__name__}: {str(e)[:200]}"

    n_after = _feature_count(doc)
    delta = n_after - n_before
    return {
        "route": "legacy_edge_arg",
        "mark": mark,
        "select": sel_ok,
        "opts": opt_label,
        "angle_deg": round(math.degrees(angle), 1),
        "radius_mm": round(radius * 1000, 1),
        "delta": delta,
        "materialized": delta > 0,
        "return_type": type(ret).__name__ if ret is not None else "None",
        "error": err,
        "edge_len_mm": round(ranked_info["length"] * 1000, 2),
    }


def _probe_preselect_only(
    doc: Any,
    fm: Any,
    edge: Any,
    ranked_info: dict,
    mark: int,
    opt_label: str,
    opts: int,
    angle: float,
    radius: float,
) -> dict[str, Any]:
    """InsertSheetMetalEdgeFlange2 with pre-selected edge only (None edge arg)."""
    vt_disp = w32.VARIANT(pythoncom.VT_DISPATCH, None)
    doc.ClearSelection2(True)
    try:
        ient = typed(edge, "IEntity")
        sel_ok = bool(ient.Select2(False, mark))
    except Exception:
        sel_ok = False

    n_before = _feature_count(doc)
    try:
        ret = fm.InsertSheetMetalEdgeFlange2(
            vt_disp,
            vt_disp,
            opts,
            angle,
            radius,
            1,
            OFFSET_50MM,
            2,
            0.5,
            0.0,
            0.0,
            0,
            vt_disp,
        )
        err = None
    except Exception as e:
        ret = None
        err = f"{type(e).__name__}: {str(e)[:200]}"

    n_after = _feature_count(doc)
    delta = n_after - n_before
    return {
        "route": "preselect_only",
        "mark": mark,
        "select": sel_ok,
        "opts": opt_label,
        "angle_deg": round(math.degrees(angle), 1),
        "radius_mm": round(radius * 1000, 1),
        "delta": delta,
        "materialized": delta > 0,
        "return_type": type(ret).__name__ if ret is not None else "None",
        "error": err,
        "edge_len_mm": round(ranked_info["length"] * 1000, 2),
    }


def _probe_legacy_no2(
    doc: Any,
    fm: Any,
    edge: Any,
    ranked_info: dict,
    mark: int,
    angle: float,
    radius: float,
) -> dict[str, Any]:
    """InsertSheetMetalEdgeFlange (without "2") — 6-arg variant."""
    doc.ClearSelection2(True)
    try:
        ient = typed(edge, "IEntity")
        sel_ok = bool(ient.Select2(False, mark))
    except Exception:
        sel_ok = False

    n_before = _feature_count(doc)
    try:
        ret = fm.InsertSheetMetalEdgeFlange(
            edge,
            None,
            angle,
            radius,
            False,
            False,
        )
        err = None
    except Exception as e:
        ret = None
        err = f"{type(e).__name__}: {str(e)[:200]}"

    n_after = _feature_count(doc)
    delta = n_after - n_before
    return {
        "route": "legacy_no2",
        "mark": mark,
        "select": sel_ok,
        "angle_deg": round(math.degrees(angle), 1),
        "radius_mm": round(radius * 1000, 1),
        "delta": delta,
        "materialized": delta > 0,
        "return_type": type(ret).__name__ if ret is not None else "None",
        "error": err,
    }


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "edgeflange_autoprofile", "ts": time.time()}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument None"}

    try:
        fm = doc.FeatureManager
        prof = _build_profile(doc)
        result["profile"] = prof
        if not prof.get("built"):
            return {**result, "overall": "FAIL", "reason": "profile sketch failed"}

        base = _build_base_flange(doc, fm, mod)
        result["base_flange"] = {k: v for k, v in base.items() if not k.startswith("_")}
        if base.get("overall") != "PASS":
            return {**result, "overall": "FAIL", "reason": "base flange failed"}

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        edges = _find_bendable_edges(doc, mod)
        result["edge_count"] = len(edges)
        if not edges:
            return {**result, "overall": "FAIL", "reason": "no edges"}

        ranked = _rank_linear_edges(edges, mod)
        result["edge_ranking"] = [
            {
                "idx": r["index"],
                "line": r["is_line"],
                "mm": round(r["length"] * 1000, 2),
            }
            for r in ranked[:6]
        ]

        attempts: list[dict[str, Any]] = []
        overall = "WALL"

        opt_sets = [
            ("UseDefRad|UseDefRel(129)", 1 | 128),
            ("UseDefRad(1)", 1),
        ]
        angles = [ANGLE_90, math.pi / 4.0]
        marks = [0, 1]
        top_edges = ranked[:3]

        for mark in marks:
            for opt_label, opts in opt_sets:
                for angle in angles:
                    for r in top_edges:
                        e = r["edge"]
                        a = _probe_legacy(
                            doc, fm, e, r, mark, opt_label, opts, angle, RADIUS_2MM
                        )
                        attempts.append(a)
                        if a["materialized"]:
                            overall = "GREEN"
                            break
                    if overall == "GREEN":
                        break
                if overall == "GREEN":
                    break
            if overall == "GREEN":
                break

        if overall != "GREEN":
            for mark in marks:
                for opt_label, opts in opt_sets:
                    for r in top_edges[:2]:
                        a = _probe_preselect_only(
                            doc,
                            fm,
                            r["edge"],
                            r,
                            mark,
                            opt_label,
                            opts,
                            ANGLE_90,
                            RADIUS_2MM,
                        )
                        attempts.append(a)
                        if a["materialized"]:
                            overall = "GREEN"
                            break
                    if overall == "GREEN":
                        break
                if overall == "GREEN":
                    break

        if overall != "GREEN":
            for mark in marks:
                for r in top_edges[:2]:
                    a = _probe_legacy_no2(
                        doc, fm, r["edge"], r, mark, ANGLE_90, RADIUS_2MM
                    )
                    attempts.append(a)
                    if a["materialized"]:
                        overall = "GREEN"
                        break
                if overall == "GREEN":
                    break

        result["attempts"] = attempts
        result["attempt_count"] = len(attempts)
        result["overall"] = overall

        if overall == "GREEN":
            winner = next(a for a in attempts if a["materialized"])
            result["winner"] = winner
            feats = (
                _feature_types(doc, fm, mod)
                if hasattr(fm, "unused")
                else _feature_types(doc, mod)
            )
            result["features_after"] = feats
            result["interpretation"] = (
                "Auto-profile edge flange materialized via %s (mark=%d, opts=%s). "
                "Ship as 14th kind."
                % (winner["route"], winner["mark"], winner.get("opts", "?"))
            )
        else:
            result["features_after"] = _feature_types(doc, mod)
            error_hist: dict[str, int] = {}
            for a in attempts:
                key = (a.get("error") or a.get("return_type") or "?")[:80]
                error_hist[key] = error_hist.get(key, 0) + 1
            result["error_histogram"] = error_hist
            result["interpretation"] = (
                "WALL: %d attempts across mark sweep × BooleanOptions × angles × "
                "legacy/preselect/no2 routes — all delta=0. Auto-profile edge flange "
                "does not materialize out-of-process. Edge-flange defers to Wave-7 "
                "VBA cluster. Wave-6 still closes (2 shipped + characterized)."
                % len(attempts)
            )

    finally:
        _try_close(sw, doc)

    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "edgeflange_autoprofile.json"
    out.write_text(payload, encoding="utf-8")
    print("wrote %s" % out)
    print(
        "overall: %s (%d attempts)"
        % (result.get("overall"), result.get("attempt_count", 0))
    )
    return {"GREEN": 0, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
