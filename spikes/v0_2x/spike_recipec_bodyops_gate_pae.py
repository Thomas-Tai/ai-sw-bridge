"""Recipe-C cut #2 gate — body-ops family migrated from mutate.py into features/.

Proves the body-ops cluster (delete_body / combine / split) now lives in
features/body_ops.py and is wired through the HANDLER_REGISTRY seam:

  A registry_seam   : HANDLER_REGISTRY advertises `delete_body` (GREEN) and does
                      NOT advertise `combine`/`split` (registered DORMANT/WALLED);
                      features.body_ops exposes all three _create_* fns + the
                      _get_body_count_and_volumes helper; mutate NO LONGER defines
                      _create_delete_body / _create_combine / _create_split /
                      _get_body_count_and_volumes (the physical move + the cut).
  B delete_body_lifecycle : on a TWO-body seed part, propose -> dry_run -> commit a
                      delete_body{body_index:1} materializes (commit ok=True) and
                      the solid-body count drops 2 -> 1 (the W41 volume/count gate)
                      — i.e. the displaced logic executed through the registry.
  C combine_fail_closed   : propose combine -> rejected ("unsupported feature type")
                      — the characterized wall stays walled after the cut (DORMANT
                      registry status, never advertised).
  D split_fail_closed     : propose split -> rejected, same.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_recipec_bodyops_gate_pae.py
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

_PROPOSALS = _HERE.parent / "_results" / "recipec_bodyops_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
import ai_sw_bridge.mutate as mutate_mod  # noqa: E402

_OUT = _HERE.parent / "_results" / "recipec_bodyops_gate_pae.json"
_WORK = _HERE.parent / "_results" / "recipec_bodyops_work"
results: dict[str, Any] = {"pae": "recipec_bodyops_registry_migration_gate", "gates": {}}


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


def _extrude(fm: Any, sm: Any, doc: Any, x0: float, x1: float, merge: bool, name: str) -> Any:
    """Sketch a rectangle on Front Plane and blind-extrude 10mm; merge flag (arg 18)
    set False on the 2nd box keeps it a DISJOINT solid body."""
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(x0, -0.01, 0, x1, 0.01, 0)
    sm.InsertSketch(True)
    f = fm.FeatureExtrusion3(
        True, False, False, 0, 0, 0.01, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        merge, True, True, 0.0, 0.0, False,
    )
    if f:
        try:
            f.Name = name
        except Exception:
            pass
    doc.ClearSelection2(True)
    return f


def _build_two_body_part(sw: Any, path: str) -> bool:
    """Two DISJOINT boxes in one part (A: x∈[-10,10], B: x∈[30,50] mm)."""
    template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return False
    fm = doc.FeatureManager
    sm = doc.SketchManager
    _extrude(fm, sm, doc, -0.01, 0.01, True, "Box_A")   # first solid
    _extrude(fm, sm, doc, 0.03, 0.05, False, "Box_B")    # Merge=False -> 2nd body
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return os.path.isfile(path)


def _solid_body_count(sw: Any, path: str) -> int:
    """Reopen *path* standalone and count solid bodies via GetBodies2."""
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(path, 1, 0, "", errs, warns)  # swDocPART=1
    if doc is None:
        return -1
    try:
        bodies = doc.GetBodies2(0, True)  # swSolidBody
        return len(bodies) if bodies else 0
    except Exception:
        return -1
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
        # ── A: structural — the cut happened, handlers relocated + wired ──
        try:
            import ai_sw_bridge.features.body_ops as bo
        except Exception as exc:  # noqa: BLE001
            gate("registry_seam", False, f"features.body_ops import failed: {exc}")
            raise SystemExit(_finish())
        delete_green = "delete_body" in HANDLER_REGISTRY
        walls_dormant = ("combine" not in HANDLER_REGISTRY) and ("split" not in HANDLER_REGISTRY)
        in_features = all(hasattr(bo, n) for n in (
            "_create_delete_body", "_create_combine", "_create_split",
            "_get_body_count_and_volumes"))
        gone_from_mutate = not any(hasattr(mutate_mod, n) for n in (
            "_create_delete_body", "_create_combine", "_create_split",
            "_get_body_count_and_volumes"))
        gate("registry_seam",
             delete_green and walls_dormant and in_features and gone_from_mutate,
             f"delete_body_GREEN={delete_green} combine/split_DORMANT={walls_dormant} "
             f"in_body_ops={in_features} removed_from_mutate={gone_from_mutate}")

        client = SolidWorksClient()

        # ── B: delete_body GREEN lifecycle on a 2-body seed ──
        seed = str(_WORK / "recipec_bodyops_seed.SLDPRT")
        if not _build_two_body_part(sw, seed):
            gate("delete_body_lifecycle", False, "two-body seed build/save failed")
        else:
            before = _solid_body_count(sw, seed)
            prop = client.mutate.propose_feature_add(
                seed, {"type": "delete_body"}, {"body_index": 1})
            pid = prop.get("proposal_id")
            results["delete_body_propose"] = prop
            if not pid:
                gate("delete_body_lifecycle", False, f"propose failed: {prop.get('error')}")
            else:
                dry = client.mutate.dry_run_feature_add(pid)
                com = client.mutate.commit_feature_add(pid)
                results["delete_body_dry_run"] = dry
                results["delete_body_commit"] = com
                after = _solid_body_count(sw, seed)
                lifecycle_ok = (bool(prop.get("ok")) and bool(dry.get("ok"))
                                and bool(com.get("ok")))
                count_ok = (before == 2 and after == 1)
                gate("delete_body_lifecycle",
                     lifecycle_ok and count_ok,
                     f"propose={prop.get('ok')} dry_run={dry.get('ok')} "
                     f"commit={com.get('ok')} bodies {before}->{after} "
                     f"(executed through HANDLER_REGISTRY) err={com.get('error') or dry.get('error')}")

        # ── C/D: the walls stay walled (propose fail-closes) ──
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        c = client.mutate.propose_feature_add(
            seed, {"type": "combine", "operation": "subtract"}, {})
        results["combine_propose"] = c
        gate("combine_fail_closed",
             (not c.get("ok")) and ("unsupported" in str(c.get("error", "")).lower()),
             f"ok={c.get('ok')} error={c.get('error')!r}")
        s = client.mutate.propose_feature_add(seed, {"type": "split"}, {})
        results["split_propose"] = s
        gate("split_fail_closed",
             (not s.get("ok")) and ("unsupported" in str(s.get("error", "")).lower()),
             f"ok={s.get('ok')} error={s.get('error')!r}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
