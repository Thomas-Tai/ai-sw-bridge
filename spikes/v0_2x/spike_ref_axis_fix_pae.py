"""ref_axis dry_run transaction defect — FIX witness gate.

The defect (queued from Recipe-C cut #3): ref_axis materialized on a DIRECT
late-bound handler call but its full propose -> dry_run -> commit lifecycle
threw TypeError('The Python instance can not be converted to a COM object') at
the Extension.SelectByID2 VARIANT(VT_DISPATCH,None) callout. Root cause (probe
2026-06-23): the disk-transaction path opens docs via mutate._open_doc_typed
(a makepy-TYPED IModelDocExtension), on which the VARIANT callout fails to
marshal; the W64 "VARIANT not bare-None" fix was characterized on a late-bound
OOP probe, the wrong binding. Fix: features.ref_geometry._latebound() re-wraps
the Extension late-bound before the callout (candidate D).

  A lifecycle : on a box seed (Front/Right planes), the FULL
                propose -> dry_run -> commit for ref_axis succeeds — dry_run
                ok=True with NO TypeError, commit ok=True — and a 'RefAxis'
                node appears in the live feature tree on reopen.
  B no_typeerror : the dry_run error field does NOT contain the marshaling
                TypeError (regression guard for the specific defect).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_ref_axis_fix_pae.py
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

_PROPOSALS = _HERE.parent / "_results" / "refaxisfix_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402

_OUT = _HERE.parent / "_results" / "refaxisfix_gate_pae.json"
_WORK = _HERE.parent / "_results" / "refaxisfix_work"
results: dict[str, Any] = {"pae": "ref_axis_dryrun_transaction_fix_gate", "gates": {}}


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


def _build_box_seed(sw: Any, path: str) -> bool:
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return False
    fm, sm = doc.FeatureManager, doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
    sm.InsertSketch(True)
    fm.FeatureExtrusion3(True, False, False, 0, 0, 0.01, 0.0,
                         False, False, False, False, 0.0, 0.0,
                         False, False, False, False, True, True, True, 0.0, 0.0, False)
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return os.path.isfile(path)


def _refaxis_node_present(sw: Any, path: str) -> bool:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(path, 1, 0, "", errs, warns)
    if doc is None:
        return False
    try:
        for f in (doc.FeatureManager.GetFeatures(False) or []):
            for attr in ("GetTypeName2", "GetTypeName"):
                try:
                    v = getattr(f, attr)
                    if "refaxis" in str(v() if callable(v) else v).lower():
                        return True
                    break
                except Exception:
                    continue
        return False
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        seed = str(_WORK / "refaxisfix_seed.SLDPRT")
        if not _build_box_seed(sw, seed):
            gate("lifecycle", False, "box seed build/save failed")
            return _finish()

        client = SolidWorksClient()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        prop = client.mutate.propose_feature_add(
            seed, {"type": "ref_axis"},
            {"planes": ["Front Plane", "Right Plane"]})
        pid = prop.get("proposal_id")
        results["propose"] = prop
        if not pid:
            gate("lifecycle", False, f"propose failed: {prop.get('error')}")
            return _finish()

        dry = client.mutate.dry_run_feature_add(pid)
        com = client.mutate.commit_feature_add(pid)
        results["dry_run"] = dry
        results["commit"] = com
        node_ok = _refaxis_node_present(sw, seed)

        lifecycle_ok = (bool(prop.get("ok")) and bool(dry.get("ok"))
                        and bool(com.get("ok")) and node_ok)
        gate("lifecycle", lifecycle_ok,
             f"propose={prop.get('ok')} dry_run={dry.get('ok')} "
             f"commit={com.get('ok')} 'RefAxis'_node={node_ok} "
             f"err={com.get('error') or dry.get('error')}")

        dry_err = str(dry.get("error") or "")
        no_typeerror = "can not be converted to a COM object" not in dry_err
        gate("no_typeerror", no_typeerror,
             f"dry_run error clean of the marshaling TypeError "
             f"(error={dry_err[:80]!r})")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
