"""import_diagnostics observe lane — seat PAE.

Drives the production facade ``client.observe.import_diagnostics()`` against two
live fixtures:

  A facade_seam   : SolidWorksClient().observe exposes import_diagnostics.
  B healthy_solid : a native 40x30x10 block -> clean=True, solid=1, surface=0,
                    total_fault_count=0 (the healthy baseline).
  C surface_body  : a part carrying a planar surface (sheet) body via
                    InsertPlanarRefSurface -> surface_body_count>=1, clean=False
                    (the unstitched/incomplete-geometry flag — the reliable
                    "imperfect import" signal; genuine corrupt-B-rep Check3
                    faults are covered by the offline mocks, since the kernel
                    resists manufacturing them on a seat — see
                    probe_import_diagnostics).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_import_diagnostics_pae.py
"""
from __future__ import annotations

import json
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

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_OUT = _HERE.parent / "_results" / "import_diagnostics_pae.json"
results: dict[str, Any] = {"pae": "import_diagnostics", "gates": {}}


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


def _build_surface_part(sw: Any) -> Any:
    """New part with a single planar SURFACE (sheet) body via
    InsertPlanarRefSurface on a closed rectangle sketch. Built on the RAW
    late-bound doc (mirrors fx.build_block — FeatureByName is unreachable on the
    typed proxy), leaving it active."""
    doc = sw.NewDocument(fx.PART_TEMPLATE, 0, 0, 0)
    fx._select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.020, -0.015, 0.0, 0.020, 0.015, 0.0)
    doc.SketchManager.InsertSketch(True)  # close Sketch1
    doc.ClearSelection2(True)
    fx._select_feature(doc, "Sketch1")
    ips = doc.InsertPlanarRefSurface
    if callable(ips):
        ips()
    doc.ClearSelection2(True)
    doc.ForceRebuild3(False)
    return doc


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all(sw)
    client = SolidWorksClient()
    try:
        # A: facade seam
        gate("facade_seam", hasattr(client.observe, "import_diagnostics"),
             f"client.observe.import_diagnostics present="
             f"{hasattr(client.observe, 'import_diagnostics')}")

        # B: healthy native solid
        _close_all(sw)
        fx.build_block(sw)  # 40x30x10, becomes the active doc
        rb = client.observe.import_diagnostics()
        results["healthy"] = rb
        ok_b = (rb.get("ok") and rb.get("clean") is True
                and rb.get("solid_body_count") == 1
                and rb.get("surface_body_count") == 0
                and rb.get("total_fault_count") == 0)
        gate("healthy_solid", bool(ok_b),
             f"ok={rb.get('ok')} clean={rb.get('clean')} "
             f"solid={rb.get('solid_body_count')} surface={rb.get('surface_body_count')} "
             f"faults={rb.get('total_fault_count')} "
             f"import_status={rb.get('import_diagnosis_status')} err={rb.get('error')}")

        # C: part with a surface (sheet) body
        _close_all(sw)
        _build_surface_part(sw)  # becomes the active doc
        rc = client.observe.import_diagnostics()
        results["surface"] = rc
        ok_c = (rc.get("ok") and rc.get("surface_body_count", 0) >= 1
                and rc.get("clean") is False)
        gate("surface_body", bool(ok_c),
             f"ok={rc.get('ok')} clean={rc.get('clean')} "
             f"solid={rc.get('solid_body_count')} surface={rc.get('surface_body_count')} "
             f"faults={rc.get('total_fault_count')} err={rc.get('error')}")
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
