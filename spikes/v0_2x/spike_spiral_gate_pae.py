"""spiral lane — seat PAE (full propose -> dry_run -> commit transaction).

Proves the new `spiral` feature_add kind routes through HANDLER_REGISTRY and
materializes a flat Archimedean spiral on the live seat via the disk-backed
transaction (which opens the doc TYPED through mutate._open_doc_typed — the path
the _latebound re-wrap exists to navigate).

  A registry_seam : HANDLER_REGISTRY advertises 'spiral' (GREEN);
                    features.spiral exposes create_spiral.
  B lifecycle     : on a seed with a base circle sketch, propose -> dry_run ->
                    commit a spiral materializes (commit ok=True) and a
                    'Helix'-type node carrying real arc length survives reopen.
                    (A spiral is a Helix feature in SW.)

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_spiral_gate_pae.py
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

_PROPOSALS = _HERE.parent / "_results" / "spiral_proposals"
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
import ai_sw_bridge.features.spiral as spiral_mod  # noqa: E402,F401

_OUT = _HERE.parent / "_results" / "spiral_gate_pae.json"
_WORK = _HERE.parent / "_results" / "spiral_work"
results: dict[str, Any] = {"pae": "spiral_lane_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _build_circle_seed(sw: Any, path: str) -> str | None:
    """New part with a named circle sketch (the spiral start radius). Returns
    the sketch name, saves to *path*."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return None
    doc = typed(raw, "IModelDoc2", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)  # 5mm start radius
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    name = None
    for f in doc.FeatureManager.GetFeatures(True) or []:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                tf.Name = "SpiralBase"
                name = "SpiralBase"
        except Exception:
            continue
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return name if os.path.isfile(path) else None


def _spiral_arc_len_mm(sw: Any, path: str) -> float | None:
    """Reopen *path*; return the arc length (mm) of the newest Helix node, or
    None if absent/unreadable. Uses the same verify substrate the handler does."""
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(path, 1, 0, "", errs, warns)
    if doc is None:
        return None
    try:
        doc.ForceRebuild3(False)
        from ai_sw_bridge.features import verify as _v

        node = _v.newest_node_by_type(doc, ("Helix",), match="exact")
        if node is None:
            return None
        return _v.curve_length_mm(node)
    except Exception:
        return None
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
        # A: structural
        gate(
            "registry_seam",
            ("spiral" in HANDLER_REGISTRY) and hasattr(spiral_mod, "create_spiral"),
            f"spiral_GREEN={'spiral' in HANDLER_REGISTRY} "
            f"handler={hasattr(spiral_mod, 'create_spiral')}",
        )

        seed = str(_WORK / "spiral_seed.SLDPRT")
        sketch = _build_circle_seed(sw, seed)
        if not sketch:
            gate("lifecycle", False, "circle seed build/save failed")
            return _finish()

        client = SolidWorksClient()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        prop = client.mutate.propose_feature_add(
            seed,
            {"type": "spiral", "pitch_mm": 10.0, "revolutions": 3.0},
            {"sketch": sketch},
        )
        pid = prop.get("proposal_id")
        results["propose"] = prop
        if not pid:
            gate("lifecycle", False, f"propose failed: {prop.get('error')}")
            return _finish()
        dry = client.mutate.dry_run_feature_add(pid)
        com = client.mutate.commit_feature_add(pid)
        results["dry_run"], results["commit"] = dry, com
        arc_mm = _spiral_arc_len_mm(sw, seed)
        results["spiral_arc_len_mm"] = arc_mm

        lifecycle_ok = (
            bool(prop.get("ok"))
            and bool(dry.get("ok"))
            and bool(com.get("ok"))
            and arc_mm is not None
            and arc_mm > 0
        )
        gate(
            "lifecycle",
            lifecycle_ok,
            f"propose={prop.get('ok')} dry_run={dry.get('ok')} commit={com.get('ok')} "
            f"spiral_arc_len_mm={arc_mm} (routed via registry through the TYPED "
            f"transaction doc; _latebound navigated the COM boundary) "
            f"err={com.get('error') or dry.get('error')}",
        )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
