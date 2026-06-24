"""bounding_box typed-transaction hardening — seat PAE.

Proves the bounding_box handler materializes through the TYPED ``_open_doc_typed``
path (the production propose→dry_run→commit lifecycle), after re-routing its Front
Plane lookup from ``IModelDoc2.FeatureByName`` (absent on the typed proxy → silent
ghost) to the callout-free ``verify.find_feature_by_name`` (GetFeatures(True) walk).

  A facade_seam : client.mutate exposes the feature-add lifecycle verbs.
  B dry_run     : propose→dry_run_feature_add a bounding_box on a saved block →
                  state dry_run_ok, no COM TypeError (the typed path applies the
                  feature, sees the effect, rolls back).
  C commit      : commit_feature_add → ok=True, doc_saved=True.
  D witness     : reopen the saved part → a BoundingBox-typed node is present
                  (bb._find_bbox_node), proving real materialization (not a ghost).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_bbox_typed_pae.py
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
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import bounding_box as bb  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_OUT = _RESULTS / "bbox_typed_pae.json"
results: dict[str, Any] = {"pae": "bbox_typed", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _RESULTS.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block_to_disk(sw: Any, path: Path) -> None:
    _close_all(sw)
    doc = fx.build_block(sw)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    doc.SaveAs3(str(path), 0, 0)
    _close_all(sw)


def _reopen(sw: Any, path: Path) -> Any:
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    return sw.OpenDoc6(str(path), 1, 1, "", errs, warns)


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    client = SolidWorksClient()
    _RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        gate(
            "facade_seam",
            hasattr(client.mutate, "propose_feature_add")
            and hasattr(client.mutate, "commit_feature_add"),
            "lifecycle verbs present",
        )

        path = _RESULTS / "bbox_typed_pae.sldprt"
        _build_block_to_disk(sw, path)

        # B: propose → dry_run through the TYPED transaction.
        # target is unused by the bounding_box handler, but the single propose
        # path requires a non-empty target dict (batch bypasses this validation).
        prop = client.mutate.propose_feature_add(
            str(path), {"type": "bounding_box"}, {"plane": "Front Plane"}
        )
        pid = prop.get("proposal_id")
        dr = (
            client.mutate.dry_run_feature_add(pid)
            if pid
            else {"error": "no proposal_id"}
        )
        results["propose"] = prop
        results["dry_run"] = dr
        ok_b = (
            pid is not None and dr.get("state") == "dry_run_ok" and not dr.get("error")
        )
        gate(
            "dry_run",
            bool(ok_b),
            f"pid={pid} state={dr.get('state')} err={dr.get('error')}",
        )

        # C: commit through the TYPED transaction.
        cm = (
            client.mutate.commit_feature_add(pid)
            if pid
            else {"error": "no proposal_id"}
        )
        results["commit"] = cm
        ok_c = (
            cm.get("ok") is True and cm.get("doc_saved") is True and not cm.get("error")
        )
        gate(
            "commit",
            bool(ok_c),
            f"ok={cm.get('ok')} saved={cm.get('doc_saved')} err={cm.get('error')}",
        )

        # D: reopen witness — a BoundingBox-typed node really exists.
        doc = _reopen(sw, path)
        node = bb._find_bbox_node(doc)
        tname = None
        if node is not None:
            try:
                tname = node.GetTypeName2
                tname = tname() if callable(tname) else tname
            except Exception:
                tname = "<type?>"
        _close_all(sw)
        gate(
            "reopen_witness",
            node is not None,
            f"bbox_node_present={node is not None} type={tname!r}",
        )
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
