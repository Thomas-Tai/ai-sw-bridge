"""
Spike v0.16 / S-WIZHOLE-V5 — wizard hole with DYNAMICALLY resolved DB args.
[authored seat-free; RUN ON A LIVE SEAT]

The Hole Wizard bridges COM to a local standards database (SWBrowser); the
FastenerTypeIndex is a CONTEXTUAL index (per standard+holetype), not the global
swWzdHoleStandardFastenerTypes_e value (39) that v4 wrongly passed, and SSize
must exactly match a DB entry. So this spike does NOT hardcode those: it queries
``ISldWorks.GetHoleStandardsData(holeType) -> IHoleStandardsData`` →
``GetHoleStandards`` / ``GetFastenerTypes(standardName)`` /
``GetFastenerTable(...) -> IHoleDataTable`` to learn the real indexes + valid
sizes, then tries to create.

It also re-tests the v2/v3 conclusion: maybe CreateFeature(data) no-op'd only
because InitializeHole got an invalid fastener index (uninitialized data), not
because the data-object path is edit-only. With VALID args we try both:
  (a) CreateDefinition(25) → typed_qi → InitializeHole(valid) → CreateFeature
  (b) fm.HoleWizard5(valid 27 args)

Discovery output (standards/fasteners/sizes) is the durable payoff regardless of
which creation path wins.

Usage
-----
    python spikes/v0_16/spike_wizhole_v5.py --out report.json
    python spikes/v0_16/spike_wizhole_v5.py --hole-type 2 --standard-substr "Ansi Metric"
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
PT_X = 0.003
PT_Y = 0.002

SW_END_BLIND = 0
DEPTH_M = 0.006
DIAMETER_M = 0.006


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


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, (tuple, list)):
        return list(v)
    return [v]


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(-BOX_W_M / 2, -BOX_H_M / 2, 0.0,
                                   BOX_W_M / 2, BOX_H_M / 2, 0.0)
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (True, False, False, 0, 0, BOX_D_M, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0)
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return {"built": feat is not None, "feature_name": getattr(feat, "Name", None)}


def _place_select_point(doc: Any) -> bool:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", 0, 0, BOX_D_M):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    pt = sk.CreatePoint(PT_X, PT_Y, 0.0)
    sk.InsertSketch(True)
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if pt is not None:
        m = getattr(pt, "Select2", None)
        if m is not None:
            try:
                return bool(m(False, 0))
            except Exception:  # noqa: BLE001
                pass
    return bool(doc.SelectByID("", "SKETCHPOINT", PT_X, PT_Y, BOX_D_M))


def _discover(sw: Any, hole_type: int, standard_substr: str, mod: Any) -> dict[str, Any]:
    """Query the standards DB: standards → fastener types → a valid size.

    The IHoleStandardsData / IHoleDataTable methods return data through byref
    [out] SAFEARRAY params, which a dynamic dispatch can't auto-supply
    ('Parameter not optional'). Early-bind via typed_qi so makepy returns the
    out arrays as a tuple.
    """
    out: dict[str, Any] = {"hole_type": hole_type}
    rec, hsd_raw = _capture(lambda: sw.GetHoleStandardsData(hole_type))
    out["GetHoleStandardsData"] = rec
    if hsd_raw is None:
        return out
    qrec, hsd = _capture(lambda: typed_qi(hsd_raw, "IHoleStandardsData", module=mod))
    out["typed_qi_hsd"] = qrec
    if hsd is None:
        return out

    srec, sret = _capture(lambda: hsd.GetHoleStandards())
    out["GetHoleStandards_raw"] = {**srec, "repr": repr(sret)[:300]}
    # The two [out] arrays (indexes, names) come back appended to the bool
    # return; find them defensively.
    arrays = [a for a in _as_list(sret) if isinstance(a, (tuple, list))]
    std_indexes = _as_list(arrays[0]) if len(arrays) >= 1 else []
    std_names = _as_list(arrays[1]) if len(arrays) >= 2 else []
    out["standards"] = [{"index": i, "name": n}
                        for i, n in zip(std_indexes, std_names)]

    # Choose a standard by name substring (else first).
    chosen = None
    for s in out["standards"]:
        if standard_substr.lower() in str(s["name"]).lower():
            chosen = s
            break
    if chosen is None and out["standards"]:
        chosen = out["standards"][0]
    out["chosen_standard"] = chosen
    if chosen is None:
        return out

    std_name = chosen["name"]
    frec, fret = _capture(lambda: hsd.GetFastenerTypes(std_name))
    out["GetFastenerTypes_raw"] = {**frec, "repr": repr(fret)[:300]}
    farr = [a for a in _as_list(fret) if isinstance(a, (tuple, list))]
    f_indexes = _as_list(farr[0]) if len(farr) >= 1 else []
    f_names = _as_list(farr[1]) if len(farr) >= 2 else []
    out["fastener_types"] = [{"index": i, "name": n}
                             for i, n in zip(f_indexes, f_names)]
    if not out["fastener_types"]:
        return out
    fastener = out["fastener_types"][0]
    out["chosen_fastener"] = fastener

    # Table types → table → sizes (the 'Size' column).
    trec, tret = _capture(lambda: hsd.GetFastenerTableTypes(std_name, fastener["index"]))
    out["GetFastenerTableTypes_raw"] = {**trec, "repr": repr(tret)[:200]}
    tids = [t for a in _as_list(tret) if isinstance(a, (tuple, list)) for t in a]
    table_id = tids[0] if tids else 0
    out["table_id"] = table_id

    htrec, htret = _capture(
        lambda: hsd.GetFastenerTable(std_name, fastener["index"], table_id)
    )
    out["GetFastenerTable_raw"] = {**htrec, "repr": repr(htret)[:200]}
    table_raw = None
    for a in _as_list(htret):
        if a is not None and not isinstance(a, (bool, int, float, str, tuple, list)):
            table_raw = a
            break
    table = None
    if table_raw is not None:
        _, table = _capture(lambda: typed_qi(table_raw, "IHoleDataTable", module=mod))
    sizes: list[str] = []
    if table is not None:
        crec, cnames = _capture(lambda: table.GetColumnNames())
        out["table_columns_raw"] = {**crec, "repr": repr(cnames)[:200]}
        cols = [c for a in _as_list(cnames) if isinstance(a, (tuple, list)) for c in a]
        out["table_columns"] = cols
        rrec, rcount = _capture(lambda: table.GetRowCount())
        rc_vals = [v for v in _as_list(rcount) if isinstance(v, int)]
        nrows = rc_vals[0] if rc_vals else 0
        out["row_count"] = nrows
        size_col = next((c for c in cols if "size" in str(c).lower()), cols[0] if cols else None)
        out["size_column"] = size_col
        if size_col is not None:
            for r in range(min(nrows, 40)):
                _, cell = _capture(lambda r=r: table.GetCellData(size_col, r))
                vals = [v for v in _as_list(cell) if isinstance(v, str)]
                if vals:
                    sizes.append(vals[0])
    out["sizes"] = sizes
    out["chosen_size"] = sizes[len(sizes) // 2] if sizes else None
    return out


def run(hole_type: int, standard_substr: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mod = wrapper_module() or ensure_sw_module()[0]
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    disc = _discover(sw, hole_type, standard_substr, mod)
    result["discovery"] = disc
    std = disc.get("chosen_standard")
    fastener = disc.get("chosen_fastener")
    size = disc.get("chosen_size")
    if not std or not fastener or not size:
        return {**result, "overall": "DISCOVERY-FAIL",
                "reason": "could not resolve standard/fastener/size from the DB"}

    std_idx = std["index"]
    fast_idx = fastener["index"]
    result["resolved_args"] = {
        "generic_hole_type": hole_type, "std_index": std_idx,
        "fastener_index": fast_idx, "size": size, "end_cond": SW_END_BLIND,
    }

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument None"}

    materialized_via = None
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box build failed"}

        # --- path (a): CreateDefinition + InitializeHole(valid) + CreateFeature
        result["point_selected_a"] = _place_select_point(doc)
        fm = doc.FeatureManager
        _, data = _capture(lambda: fm.CreateDefinition(SW_FM_HOLE_WZD))
        a_rec: dict[str, Any] = {}
        if data is not None:
            _, fd = _capture(lambda: typed_qi(data, IFACE, module=mod))
            init_rec, _ = _capture(
                lambda: fd.InitializeHole(hole_type, std_idx, fast_idx, size, SW_END_BLIND)
            )
            a_rec["InitializeHole"] = init_rec
            if hasattr(fd, "Depth"):
                _capture(lambda: setattr(fd, "Depth", DEPTH_M))
            # re-assert point
            _place_select_point(doc)
            feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
            a_rec["CreateFeature"] = {**feat_rec, "materialized": _materialized(feat)}
            if _materialized(feat):
                a_rec["feature_name"] = getattr(feat, "Name", None)
                a_rec["type_name"] = _type_name(feat)
                materialized_via = "CreateDefinition+InitializeHole+CreateFeature"
        result["path_a"] = a_rec

        # --- path (b): HoleWizard5 (only if (a) didn't materialize) ----------
        if materialized_via is None:
            result["point_selected_b"] = _place_select_point(doc)
            values = (0.0,) * 12
            args = (hole_type, std_idx, fast_idx, size, SW_END_BLIND,
                    DIAMETER_M, DEPTH_M, 0.0, *values, "", False, True, False,
                    False, False, False)
            hw_rec, feat = _capture(lambda: fm.HoleWizard5(*args))
            b = {**hw_rec, "materialized": _materialized(feat)}
            if _materialized(feat):
                b["feature_name"] = getattr(feat, "Name", None)
                b["type_name"] = _type_name(feat)
                materialized_via = "HoleWizard5"
            result["path_b"] = b
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
        result["cleanup"] = "closed own doc (no save)"

    if materialized_via:
        result["overall"] = "PASS"
        result["materialized_via"] = materialized_via
        result["interpretation"] = (
            f"wizard hole materializes via {materialized_via} with DB-resolved "
            f"args (std_idx={std_idx}, fastener_idx={fast_idx}, size={size!r}). "
            "Build the F2 wizhole handler: resolve args from GetHoleStandardsData, "
            "validate the size against the table, then this creation path."
        )
    else:
        result["overall"] = "PARTIAL"
        result["interpretation"] = (
            "DB args resolved but neither CreateFeature nor HoleWizard5 "
            "materialized — inspect path_a/path_b; size/placement may still be off."
        )
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--hole-type", type=int, default=2)  # swWzdHole
    p.add_argument("--standard-substr", default="Ansi Metric")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run(args.hole_type, args.standard_substr)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "DISCOVERY-FAIL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
