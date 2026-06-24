"""W71 production PAE — Revision / General / Weldment table cluster.

Drives the SHIPPED commit_drawing pipeline with the three new table flags and
verifies persistence by reopening and reading each table's
swTableAnnotationType_e via ITableAnnotation.Type (the universal discriminator):
  General=0  HoleChart=1  BOM=2  RevisionBlock=3  WeldmentCutList=4

Two fixtures:
  A. plain block        -> revision_table + general_table  (expect Type 3 + 0)
  B. bar + InsertWeldmentFeature (a real cut list) -> weldment_table (Type 4)

Prereq: SOLIDWORKS 2024 running.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_SRC))

RESULTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "drawing_table_cluster_pae.json"
)
results: dict[str, Any] = {
    "pae": "w71_drawing_table_cluster",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _build_block(path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W71_TblBlock",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 60.0,
                "height": 40.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }
    r = part_build(spec, save_as=path, save_format="current", no_dim=True)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(path)


def _build_weldment(sw: Any, path: str, mod: Any) -> tuple[bool, str]:
    """Build a bar, then enable weldments (IFeatureManager.InsertWeldmentFeature)
    so the part carries a populated cut-list folder."""
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W71_Weldment",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK",
                "depth": 120.0,
            },
        ],
    }
    r = part_build(spec, save_as=path, save_format="current", no_dim=True)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    if not (ok and os.path.isfile(path)):
        return False, "bar build failed"
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        return False, "reopen bar failed"
    try:
        fm = typed_qi(doc.FeatureManager, "IFeatureManager", module=mod)
        feat = fm.InsertWeldmentFeature()
    except Exception as exc:
        return False, f"InsertWeldmentFeature raised: {exc!r}"
    weld_ok = feat is not None and not isinstance(feat, int)
    mdoc2 = typed(doc, "IModelDoc2", module=mod)
    try:
        mdoc2.EditRebuild3()
    except Exception:
        pass
    mdoc2.SaveAs3(path, 0, 0)
    try:
        t = mdoc2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass
    return weld_ok, (
        "weldment feature ok" if weld_ok else "InsertWeldmentFeature returned None"
    )


def _reopen_table_types(
    sw: Any, part_path: str, drw_path: str, mod: Any
) -> dict[int, int]:
    """Reopen the drawing and tally table annotations by swTableAnnotationType_e."""
    from ai_sw_bridge.com.earlybind import typed, typed_qi

    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    except Exception:
        pass
    ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
    drw = ret[0] if isinstance(ret, tuple) else ret
    counts: dict[int, int] = {}
    if drw is not None:
        dt = typed(drw, "IDrawingDoc", module=mod)
        v = dt.GetFirstView()
        while v is not None:
            tv = typed_qi(v, "IView", module=mod)
            try:
                ta = tv.GetFirstTableAnnotation()
                while ta is not None:
                    try:
                        tta = typed_qi(ta, "ITableAnnotation", module=mod)
                        ttype = tta.Type
                        ttype = ttype() if callable(ttype) else ttype
                        counts[int(ttype)] = counts.get(int(ttype), 0) + 1
                    except Exception:
                        pass
                    try:
                        ta = ta.GetNext()
                    except Exception:
                        break
            except Exception:
                pass
            try:
                v = tv.GetNextView()
            except Exception:
                break
        try:
            t = drw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
    return counts


def run() -> str:
    import win32com.client as w32

    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.mutate import (
        sw_commit_drawing,
        sw_dry_run_drawing,
        sw_propose_drawing,
    )

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tmp = tempfile.mkdtemp(prefix="w71_tblcluster_")

    def _commit(part_path: str, drw_path: str, flags: dict) -> dict:
        spec = {
            "kind": "drawing",
            "name": "tbl",
            "model": part_path,
            "views": ["front", "top"],
            "sheet": {"template_size": "A2"},
            **flags,
        }
        dp = sw_propose_drawing(spec)
        if not dp.get("ok"):
            return {"ok": False, "error": f"propose: {dp.get('error')}"}
        sw_dry_run_drawing(dp["proposal_id"])
        return sw_commit_drawing(dp["proposal_id"], drw_path)

    # ---- Fixture A: revision + general on a plain block ----
    block = os.path.join(tmp, "W71_TblBlock.SLDPRT")
    drwA = os.path.join(tmp, "W71_TblBlock.SLDDRW")
    if not gate("build_block", _build_block(block), block):
        return "WALL"
    dcA = _commit(block, drwA, {"revision_table": True, "general_table": True})
    gate("commit_A", dcA.get("ok", False), str(dcA.get("error") or ""))
    gate(
        "revision_inserted",
        dcA.get("revision_table_inserted") is True,
        f"flag={dcA.get('revision_table_inserted')}",
    )
    gate(
        "general_inserted",
        dcA.get("general_table_inserted") is True,
        f"flag={dcA.get('general_table_inserted')}",
    )
    if dcA.get("ok"):
        typesA = _reopen_table_types(sw, block, drwA, mod)
        results["reopen_types_A"] = {str(k): v for k, v in typesA.items()}
        gate("revision_persists_type3", typesA.get(3, 0) >= 1, f"types={typesA}")
        gate("general_persists_type0", typesA.get(0, 0) >= 1, f"types={typesA}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    # ---- Fixture B: weldment cut list ----
    weld = os.path.join(tmp, "W71_Weldment.SLDPRT")
    drwB = os.path.join(tmp, "W71_Weldment.SLDDRW")
    weld_ok, weld_detail = _build_weldment(sw, weld, mod)
    gate("build_weldment_fixture", weld_ok, weld_detail)
    if weld_ok:
        dcB = _commit(weld, drwB, {"weldment_table": True})
        gate("commit_B", dcB.get("ok", False), str(dcB.get("error") or ""))
        gate(
            "weldment_inserted",
            dcB.get("weldment_table_inserted") is True,
            f"flag={dcB.get('weldment_table_inserted')}",
        )
        if dcB.get("ok"):
            typesB = _reopen_table_types(sw, weld, drwB, mod)
            results["reopen_types_B"] = {str(k): v for k, v in typesB.items()}
            gate("weldment_persists_type4", typesB.get(4, 0) >= 1, f"types={typesB}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    all_pass = all(g["ok"] for g in results["gates"].values())
    gate(
        "OVERALL_GREEN",
        all_pass,
        f"{sum(1 for g in results['gates'].values() if g['ok'])}/{len(results['gates'])}",
    )
    return "GREEN" if all_pass else "PARTIAL"


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "WALL"
    finally:
        try:
            import win32com.client as w32

            w32.Dispatch("SldWorks.Application").CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    results["verdict"] = verdict
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nVerdict: {verdict}  (wrote {RESULTS_PATH})")
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
