"""W68 curve_through_xyz derisk spike — Mode-B probe on the live seat (DO NOT RUN offline).

Mode-A does not exist for free-form curves: the SW2024 swconst harvest exposes
no ``swFeatureNameID`` for a curve-through-points creation definition.  The
operative path is Mode-B only: the legacy ``IModelDoc2`` pipeline
``InsertCurveFileBegin`` → N × ``InsertCurveFilePoint(X, Y, Z)`` →
``InsertCurveFileEnd``.

Probes:

  (1) Does the InsertCurveFile* pipeline create a reference-curve node?
  (2) What is the exact ``GetTypeName2`` of the new node (UNKNOWN-1)?
  (3) What is the minimum point count the kernel accepts (UNKNOWN-2)?
  (4) Does the curve carry readable arc length (W67 P3b geometric gate)?
  (5) Does the curve survive save → reopen?

Fixture: ``build_block`` (40×30×10 mm) then fire a 3-point polyline well
outside the block (offset in Z so it doesn't intersect the solid).

** DO NOT RUN OFFLINE — requires a live SOLIDWORKS seat. **
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

import pythoncom

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import _feature_spike_fixtures as fx  # noqa: E402

# --- curve parameters (W0-tunable on the seat) --------------------------------
# 3-point polyline well outside the 40x30x10 block.  The block occupies
# x=[-20,20]mm, y=[-15,15]mm, z=[0,10]mm.  Place the curve at z=50mm,
# running from x=-50 to x=+50 mm, with a midpoint offset in Y.
CURVE_POINTS_MM: list[list[float]] = [
    [-50.0, 0.0, 50.0],
    [0.0, 30.0, 50.0],
    [50.0, 0.0, 50.0],
]


def _resolve(obj: Any, attr: str) -> Any:
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _feature_type_names(doc: Any) -> list[str]:
    """All feature type-names via GetFeatures(False) + callable-or-property guard."""
    names: list[str] = []
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return names
    if feats is None:
        return names
    for feat in feats:
        for attr in ("GetTypeName2", "GetTypeName"):
            try:
                names.append(str(_resolve(feat, attr)))
                break
            except Exception:
                continue
        else:
            names.append("<unknown>")
    return names


def _count_curve_nodes(doc: Any) -> int:
    """Count nodes whose type-name contains 'curve' or 'refcurve' (substring)."""
    count = 0
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return 0
    if not feats:
        return 0
    for feat in feats:
        for attr in ("GetTypeName2", "GetTypeName"):
            try:
                tname = str(_resolve(feat, attr)).lower()
                if "curve" in tname or "refcurve" in tname:
                    count += 1
                break
            except Exception:
                continue
    return count


def _newest_curve_node(doc: Any) -> Any | None:
    """Return the last curve-type node (for GetTypeName2 + arc-length probe)."""
    found = None
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return None
    if not feats:
        return None
    for feat in feats:
        for attr in ("GetTypeName2", "GetTypeName"):
            try:
                tname = str(_resolve(feat, attr)).lower()
                if "curve" in tname or "refcurve" in tname:
                    found = feat
                break
            except Exception:
                continue
    return found


def _probe_type_name2(node: Any) -> str:
    """A7 probe: exact GetTypeName2 of the new node."""
    if node is None:
        return "<no node>"
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            return str(_resolve(node, attr))
        except Exception:
            continue
    return "<unreadable>"


def _metrics(doc: Any) -> dict[str, Any]:
    faces = 0
    vol_mm3 = 0.0
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies:
            for b in (list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]):
                try:
                    f = b.GetFaces()
                    faces += len(f) if f else 0
                except Exception:
                    pass
                try:
                    mp = b.GetMassProperties(1.0)
                    if mp and len(mp) > 3:
                        vol_mm3 += float(mp[3]) * 1e9
                except Exception:
                    pass
    except Exception:
        pass
    return {"faces": faces, "vol_mm3": vol_mm3}


def _fire_curve(points_mm: list[list[float]]) -> dict[str, Any]:
    """Probe: fire InsertCurveFileBegin/Point/End on the active doc."""
    from ai_sw_bridge.features.curve_through_xyz import _try_mode_b

    doc = None
    try:
        from ai_sw_bridge.sw_com import get_sw_app
        sw = get_sw_app()
        doc = sw.ActiveDoc
    except Exception:
        return {"error": "could not get active doc"}

    if doc is None:
        return {"error": "ActiveDoc is None"}

    result = _try_mode_b(doc, points_mm)
    return {"result": repr(result), "ok": result is not None}


def _write_and_report(out: dict[str, Any], code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "curve_through_xyz_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[curve_through_xyz] wrote {out_path}\n")
    sys.stderr.write(f"[curve_through_xyz] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "curve_through_xyz",
        "purpose": (
            "Mode-B curve-through-XYZ probe — InsertCurveFileBegin/Point/End "
            "pipeline on IModelDoc2 (no CreateDefinition route).  Probes "
            "UNKNOWN-1 (GetTypeName2 of new node) and UNKNOWN-2 (min point "
            "count the kernel accepts)."
        ),
        "params": {"points_mm": CURVE_POINTS_MM},
    }
    sw = None
    doc = None
    code = 1
    try:
        sw = fx.connect()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        doc = fx.build_block(sw)

        before = _metrics(doc)
        out["faces_before"] = before["faces"]
        out["vol_mm3_before"] = before["vol_mm3"]
        curves_before = _count_curve_nodes(doc)
        out["curves_before"] = curves_before
        out["feature_tree_before"] = _feature_type_names(doc)
        out["node_count_before"] = fx.count_feature_nodes(doc)

        # --- Mode-B fire ---------------------------------------------------
        mode_b_diag: dict[str, Any] = {}
        mode_b_ok = False
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass

        # InsertCurveFileBegin
        try:
            begin = doc.InsertCurveFileBegin
            begin_result = begin() if callable(begin) else begin
            mode_b_diag["begin"] = repr(begin_result)
        except Exception as e:
            mode_b_diag["begin_error"] = f"{type(e).__name__}: {e}"[:200]

        # InsertCurveFilePoint (loop)
        point_results: list[Any] = []
        points_ok = True
        for i, pt in enumerate(CURVE_POINTS_MM):
            x_m, y_m, z_m = pt[0] / 1000.0, pt[1] / 1000.0, pt[2] / 1000.0
            try:
                ins = doc.InsertCurveFilePoint
                r = ins(x_m, y_m, z_m) if callable(ins) else ins
                point_results.append({"idx": i, "result": repr(r)})
                if r is not None and not r:
                    points_ok = False
            except Exception as e:
                point_results.append({"idx": i, "error": f"{type(e).__name__}: {e}"[:200]})
                points_ok = False
        mode_b_diag["points"] = point_results
        mode_b_diag["points_ok"] = points_ok

        # InsertCurveFileEnd
        end_ok = False
        try:
            end = doc.InsertCurveFileEnd
            end_result = end() if callable(end) else end
            mode_b_diag["end"] = repr(end_result)
            end_ok = bool(end_result)
        except Exception as e:
            mode_b_diag["end_error"] = f"{type(e).__name__}: {e}"[:200]

        mode_b_diag["end_ok"] = end_ok

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        curves_after = _count_curve_nodes(doc)
        node_count_after = fx.count_feature_nodes(doc)
        mode_b_diag["curves_after"] = curves_after
        mode_b_diag["node_count_after"] = node_count_after

        if curves_after > curves_before:
            mode_b_ok = True
        out["mode_b"] = mode_b_diag
        out["mode_b_ok"] = mode_b_ok

        # --- UNKNOWN-1 probe: GetTypeName2 of the new node -----------------
        new_node = _newest_curve_node(doc)
        out["UNKNOWN_1_type_name2"] = _probe_type_name2(new_node)

        # --- UNKNOWN-2 probe: minimum point count --------------------------
        # The 3-point fire above is the primary test.  If it succeeded, the
        # minimum is <= 3.  A 2-point probe could be added by W0 if needed.
        out["UNKNOWN_2_min_points"] = (
            "<=3 (3-point fire succeeded)" if mode_b_ok
            else "UNKNOWN (3-point fire failed)"
        )

        # --- Arc-length probe (W67 P3b geometric gate) -------------------
        try:
            from ai_sw_bridge.features import verify as v
            length_mm = v.curve_length_mm(new_node)
            out["arc_length_mm"] = length_mm
            out["curve_gate_pass"] = v.gate_curve(
                curves_after - curves_before, length_mm,
            )
        except Exception as e:
            out["arc_length_error"] = f"{type(e).__name__}: {e}"[:200]

        after = _metrics(doc)
        out["faces_after"] = after["faces"]
        out["vol_mm3_after"] = after["vol_mm3"]
        out["delta_faces"] = after["faces"] - before["faces"]
        out["delta_vol_mm3"] = round(after["vol_mm3"] - before["vol_mm3"], 3)
        out["curves_after"] = curves_after
        out["feature_tree_after"] = _feature_type_names(doc)

        if mode_b_ok:
            out["verdict"] = "PASS"
            try:
                doc2 = fx.save_and_reopen(sw, doc)
                doc = None
                curves_reopen = _count_curve_nodes(doc2)
                out["persist_survived"] = curves_reopen > curves_before
                out["curves_after_reopen"] = curves_reopen
                out["node_count_reopen"] = fx.count_feature_nodes(doc2)
                out["feature_tree_reopen"] = _feature_type_names(doc2)

                reopen_node = _newest_curve_node(doc2)
                out["type_name2_reopen"] = _probe_type_name2(reopen_node)

                code = 0 if out["persist_survived"] else 2
                if not out["persist_survived"]:
                    out["verdict"] = "PASS_BUT_NOT_PERSISTED"
            except Exception as e:
                out["persist_error"] = f"{type(e).__name__}: {e}"[:200]
                out["verdict"] = "PASS_BUT_NOT_PERSISTED"
                code = 2
        else:
            out["verdict"] = "NO_OP"
            code = 2

    except Exception as exc:
        out["fatal_error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["traceback"] = traceback.format_exc()
        out["verdict"] = "ERROR"
        code = 1
    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        pythoncom.CoUninitialize()

    return _write_and_report(out, code)


if __name__ == "__main__":
    raise SystemExit(main())
