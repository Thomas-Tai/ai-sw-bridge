"""curve-lane hardening — consolidated seat PAE (typed transaction).

Proves the curve sibling lanes that ARE reachable through the JSON
propose->dry_run->commit transaction materialize a real curve (arc length on
reopen) through the TYPED disk-transaction doc (mutate._open_doc_typed — the
path the _latebound re-wrap navigates).

Scope (see probe_curve_lanes_typed_txn for the ground-truth classification):
  * helix             — was BROKEN through the typed transaction (Extension.
                        SelectByID2 VARIANT callout raised TypeError). Hardened
                        with the _latebound seam (this PAE proves the fix).
  * curve_through_xyz — already immune (no selection); proven GREEN end-to-end.
  * composite / project_curve — NOT covered here: their targets are LIVE entity
                        handles (edges / face) that do not serialize to a JSON
                        proposal and have no durable-ref resolution at commit,
                        so they are not reachable through propose/commit at all.
                        Their selection is callout-free select_entity()/IEntity.
                        Select2 (blanket-guarded, returns False, cannot raise the
                        VARIANT TypeError) — structurally immune. Their node
                        generation is covered by the direct-call fixture spikes
                        (spike_composite / spike_project_curve_v2).

  A registry_seam     : helix + curve_through_xyz advertised in HANDLER_REGISTRY.
  B helix_txn         : circle seed -> propose -> dry_run -> commit; a Helix node
                        with real arc length survives reopen (the hardening proof).
  C curve_xyz_txn     : bare seed -> propose -> dry_run -> commit; a CurveInFile
                        node with real arc length survives reopen.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_curve_lanes_hardening_pae.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
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

_PROPOSALS = _HERE.parent / "_results" / "curvelane_hardening_proposals"
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
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
from ai_sw_bridge.features import verify as _v  # noqa: E402

_OUT = _HERE.parent / "_results" / "curve_lanes_hardening_pae.json"
_WORK = _HERE.parent / "_results" / "curvelane_hardening_work"
results: dict[str, Any] = {"pae": "curve_lanes_hardening", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_circle_seed(sw: Any, path: str) -> str | None:
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
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return False
    doc = typed(raw, "IModelDoc2", module=mod)
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return os.path.isfile(path)


def _arc_len_on_reopen(sw: Any, path: str, tokens: tuple, match: str) -> float | None:
    _close_all(sw)
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(path, 1, 0, "", errs, warns)
    if doc is None:
        return None
    try:
        doc.ForceRebuild3(False)
        node = _v.newest_node_by_type(doc, tokens, match=match)
        if node is None:
            return None
        return _v.curve_length_mm(node)
    except Exception:
        return None
    finally:
        _close_all(sw)


def _drive(client: Any, sw: Any, seed: str, feature: dict, target: dict) -> dict:
    _close_all(sw)
    prop = client.mutate.propose_feature_add(seed, feature, target)
    pid = prop.get("proposal_id")
    r = {"propose": prop.get("ok"), "pid": pid, "propose_err": prop.get("error")}
    if not pid:
        return r
    dry = client.mutate.dry_run_feature_add(pid)
    r["dry_run"], r["dry_run_err"] = dry.get("ok"), dry.get("error")
    if dry.get("ok"):
        com = client.mutate.commit_feature_add(pid)
        r["commit"], r["commit_err"] = com.get("ok"), com.get("error")
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
        gate("registry_seam",
             ("helix" in HANDLER_REGISTRY) and ("curve_through_xyz" in HANDLER_REGISTRY),
             f"helix={'helix' in HANDLER_REGISTRY} "
             f"curve_through_xyz={'curve_through_xyz' in HANDLER_REGISTRY}")

        # B: helix through the typed transaction (the hardening proof)
        seed = str(_WORK / "helix_seed.SLDPRT")
        sk = _build_circle_seed(sw, seed)
        if not sk:
            gate("helix_txn", False, "circle seed build failed")
        else:
            r = _drive(client, sw, seed,
                       {"type": "helix", "pitch_mm": 10.0, "revolutions": 4.0},
                       {"sketch": sk})
            arc = _arc_len_on_reopen(sw, seed, ("Helix",), "exact") if r.get("commit") else None
            ok = bool(r.get("commit")) and arc is not None and arc > 0
            gate("helix_txn", ok,
                 f"propose={r.get('propose')} dry_run={r.get('dry_run')} "
                 f"commit={r.get('commit')} helix_arc_mm={arc} "
                 f"(_latebound navigated the typed-transaction COM boundary) "
                 f"err={r.get('commit_err') or r.get('dry_run_err')}")

        # C: curve_through_xyz through the typed transaction (immunity baseline)
        seed = str(_WORK / "cxyz_seed.SLDPRT")
        if not _build_bare_seed(sw, seed):
            gate("curve_xyz_txn", False, "bare seed build failed")
        else:
            pts = [[0, 0, 0], [20, 10, 5], [40, 0, 10], [60, 15, 5]]
            r = _drive(client, sw, seed, {"type": "curve_through_xyz"}, {"points": pts})
            arc = (_arc_len_on_reopen(sw, seed, ("refcurve", "curve"), "substring")
                   if r.get("commit") else None)
            ok = bool(r.get("commit")) and arc is not None and arc > 0
            gate("curve_xyz_txn", ok,
                 f"propose={r.get('propose')} dry_run={r.get('dry_run')} "
                 f"commit={r.get('commit')} curve_arc_mm={arc} "
                 f"err={r.get('commit_err') or r.get('dry_run_err')}")
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
