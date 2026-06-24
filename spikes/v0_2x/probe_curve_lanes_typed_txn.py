"""MEASURE-FIRST probe — do the 4 sibling curve lanes break through the TYPED
disk transaction (the ref_axis / spiral binding trap)?

The premise under test (curve-lane hardening directive): helix, composite,
project_curve, curve_through_xyz all carry an unmitigated VARIANT-callout
marshaling vulnerability beneath features/, only ever verified via direct-call
spikes, never through the typed propose->dry_run->commit transaction.

Static reading (to be CONFIRMED or FALSIFIED here):
  * helix             — doc.Extension.SelectByID2(..., VARIANT(VT_DISPATCH,None))
                        on the TYPED doc → the exact ref_axis trap. JSON-reachable
                        via {"sketch": name}. PREDICT: reproduces TypeError.
  * curve_through_xyz — NO selection at all (absolute XYZ points). JSON-reachable
                        via {"points": [...]}. PREDICT: GREEN, immune.
  * composite         — select_entity()/IEntity.Select2 (callout-FREE, returns
                        False not raise) + live-edge target (NOT JSON-reachable —
                        no durable-ref resolution at commit). PREDICT: immune.
  * project_curve     — select_entity()/IEntity.Select2 + face.Select2 + live-face
                        target (NOT JSON-reachable). PREDICT: immune.

Probe design:
  A helix             — drive the REAL transaction (propose {sketch} -> dry_run)
                        on a circle seed; capture the dry_run error verbatim and
                        flag whether it contains the TypeError signature.
  B curve_through_xyz — drive the REAL transaction (propose {points} -> dry_run
                        -> commit) on a bare seed; expect GREEN + arc length.
  C composite/        — open a doc TYPED via mutate._open_doc_typed (the exact
    project_curve       transaction binding), acquire a LIVE entity on it, and
                        call selection.live.select_entity — assert it does NOT
                        raise the VARIANT TypeError (callout-free immunity), and
                        record that neither is JSON-transaction-reachable.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_curve_lanes_typed_txn.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_PROPOSALS = _HERE.parent / "_results" / "curvelane_probe_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402
from ai_sw_bridge.selection.live import select_entity  # noqa: E402
from ai_sw_bridge.features import verify as _v  # noqa: E402

_OUT = _HERE.parent / "_results" / "probe_curve_lanes_typed_txn.json"
_WORK = _HERE.parent / "_results" / "curvelane_probe_work"
out: dict[str, Any] = {"probe": "curve_lanes_typed_txn", "lanes": {}}

_TYPEERROR_SIG = "can not be converted to a COM object"


def _build_circle_seed(sw: Any, path: str) -> str | None:
    """New part with a named circle sketch (helix start radius). Returns sketch name."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return None
    doc = typed(raw, "IModelDoc2", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    name = None
    for f in doc.FeatureManager.GetFeatures(True) or []:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                tf.Name = "HelixBase"
                name = "HelixBase"
        except Exception:
            continue
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return name if os.path.isfile(path) else None


def _build_bare_seed(sw: Any, path: str) -> bool:
    """New empty part (curve_through_xyz needs no pre-geometry). Save to *path*."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return False
    doc = typed(raw, "IModelDoc2", module=mod)
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return os.path.isfile(path)


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _drive_txn(client: Any, sw: Any, seed: str, feature: dict, target: dict) -> dict:
    """propose -> dry_run -> (commit if dry_run ok). Returns the staged results."""
    _close_all(sw)
    prop = client.mutate.propose_feature_add(seed, feature, target)
    pid = prop.get("proposal_id")
    r: dict[str, Any] = {
        "propose_ok": bool(prop.get("ok")),
        "propose_err": prop.get("error"),
        "pid": pid,
    }
    if not pid:
        return r
    dry = client.mutate.dry_run_feature_add(pid)
    r["dry_run_ok"] = bool(dry.get("ok"))
    r["dry_run_err"] = dry.get("error")
    if dry.get("ok"):
        com = client.mutate.commit_feature_add(pid)
        r["commit_ok"] = bool(com.get("ok"))
        r["commit_err"] = com.get("error")
    return r


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all(sw)
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    client = SolidWorksClient()
    try:
        # ---- A: helix — real transaction, expect the TypeError reproduction ----
        try:
            seed = str(_WORK / "helix_seed.SLDPRT")
            sk = _build_circle_seed(sw, seed)
            if not sk:
                out["lanes"]["helix"] = {"error": "circle seed build failed"}
            else:
                res = _drive_txn(
                    client,
                    sw,
                    seed,
                    {"type": "helix", "pitch_mm": 10.0, "revolutions": 4.0},
                    {"sketch": sk},
                )
                err_blob = f"{res.get('dry_run_err')} {res.get('commit_err')}"
                res["reproduces_typeerror"] = _TYPEERROR_SIG in err_blob
                res["verdict"] = (
                    "BROKEN_TYPED_TXN"
                    if res["reproduces_typeerror"]
                    else ("GREEN" if res.get("commit_ok") else "OTHER_FAIL")
                )
                out["lanes"]["helix"] = res
        except Exception as e:  # noqa: BLE001
            out["lanes"]["helix"] = {
                "probe_exc": repr(e),
                "tb": traceback.format_exc()[-400:],
            }

        # ---- B: curve_through_xyz — real transaction, expect GREEN (immune) ----
        try:
            seed = str(_WORK / "cxyz_seed.SLDPRT")
            if not _build_bare_seed(sw, seed):
                out["lanes"]["curve_through_xyz"] = {"error": "bare seed build failed"}
            else:
                pts = [[0, 0, 0], [20, 10, 5], [40, 0, 10], [60, 15, 5]]
                res = _drive_txn(
                    client, sw, seed, {"type": "curve_through_xyz"}, {"points": pts}
                )
                err_blob = f"{res.get('dry_run_err')} {res.get('commit_err')}"
                res["reproduces_typeerror"] = _TYPEERROR_SIG in err_blob
                res["verdict"] = (
                    "GREEN"
                    if res.get("commit_ok")
                    else (
                        "BROKEN_TYPED_TXN"
                        if res["reproduces_typeerror"]
                        else "OTHER_FAIL"
                    )
                )
                out["lanes"]["curve_through_xyz"] = res
        except Exception as e:  # noqa: BLE001
            out["lanes"]["curve_through_xyz"] = {
                "probe_exc": repr(e),
                "tb": traceback.format_exc()[-400:],
            }

        # ---- C: composite / project_curve — typed-doc select_entity immunity ----
        # These take LIVE entity targets (edges / face) that do NOT serialize to
        # a JSON proposal and have NO durable-ref resolution at commit, so they
        # are not reachable through propose/commit. Their selection is
        # select_entity()/IEntity.Select2 — callout-free. Prove select_entity
        # does NOT raise the VARIANT TypeError on a doc opened the way the
        # transaction opens it (mutate._open_doc_typed), using a live edge.
        try:
            seed = str(_WORK / "block_seed.SLDPRT")
            # Build a block with a real solid so we have edges to select.
            mod = wrapper_module()
            template = sw.GetUserPreferenceStringValue(8)
            raw = sw.NewDocument(template, 0, 0.0, 0.0)
            bdoc = typed(raw, "IModelDoc2", module=mod)
            sm = typed(bdoc.SketchManager, "ISketchManager", module=mod)
            bdoc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
            sm.InsertSketch(True)
            sm.CreateCornerRectangle(0.0, 0.0, 0.0, 0.04, 0.03, 0.0)
            sm.InsertSketch(True)
            bdoc.ClearSelection2(True)
            # extrude 10mm
            bdoc.FeatureManager.FeatureExtrusion2(
                True,
                False,
                False,
                0,
                0,
                0.010,
                0.0,
                False,
                False,
                False,
                False,
                0,
                0,
                False,
                False,
                False,
                False,
                True,
                True,
                True,
                0,
                0,
                False,
            )
            bdoc.ForceRebuild3(False)
            bdoc.SaveAs3(seed, 0, 0)
            _close_all(sw)

            tdoc = mutate._open_doc_typed(seed)  # the EXACT transaction binding
            comp = {"typed_doc_open": tdoc is not None}
            # acquire a live edge off the typed doc. GetBodies2 lives on IPartDoc,
            # which the typed IModelDoc2 proxy does not expose — reach it via a
            # late-bound dynamic re-wrap (resolves through IDispatch).
            import win32com.client.dynamic as _w32dyn

            ldoc = _w32dyn.Dispatch(tdoc)
            body = None
            for b in ldoc.GetBodies2(0, False) or []:
                body = b
                break
            edge = None
            if body is not None:
                tb = typed(body, "IBody2", module=mod)
                edges = tb.GetEdges()
                if edges:
                    edge = edges[0]
            comp["got_live_edge"] = edge is not None
            # the immunity test: does select_entity raise on the typed doc?
            raised = None
            sel_ok = None
            if edge is not None:
                try:
                    sel_ok = select_entity(edge, append=False, mark=0)
                    raised = False
                except Exception as e:  # noqa: BLE001
                    raised = True
                    comp["select_entity_exc"] = repr(e)
            comp["select_entity_raised"] = raised
            comp["select_entity_ok"] = sel_ok
            comp["callout_free_immune"] = raised is False
            comp["json_transaction_reachable"] = (
                False  # live-entity targets, no ref-resolution
            )
            comp["verdict"] = "IMMUNE" if raised is False else "NEEDS_REVIEW"
            out["lanes"]["composite_project_curve"] = comp
            _close_all(sw)
        except Exception as e:  # noqa: BLE001
            out["lanes"]["composite_project_curve"] = {
                "probe_exc": repr(e),
                "tb": traceback.format_exc()[-400:],
            }
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
