"""W71 production PAE — Hole Table via the SHIPPED commit_drawing pipeline.

Drives the real propose -> dry_run -> commit_drawing path with hole_table:true
(NOT a parallel COM copy — the production lane) on a 2-hole part, then reopens
and verifies the hole table survived serialization.

Gates:
  * drawing commit ok
  * result.hole_table_inserted == True (the wired flag)
  * reopen: >=1 IHoleTableAnnotation persists on a model view

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
    / "drawing_hole_table_pae.json"
)
results: dict[str, Any] = {
    "pae": "w71_drawing_hole_table",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _build_part(path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W71_HoleTblPAE",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Base",
                "plane": "Front",
                "width": 40.0,
                "height": 40.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Base",
                "sketch": "SK_Base",
                "depth": 10.0,
            },
            {
                "type": "sketch_circle_on_face",
                "name": "SK_H1",
                "of_feature": "EX_Base",
                "face": "+z",
                "diameter": 6.0,
                "center": {"u": -10.0, "v": 0.0},
            },
            {"type": "cut_extrude_through_all", "name": "CUT_H1", "sketch": "SK_H1"},
            {
                "type": "sketch_circle_on_face",
                "name": "SK_H2",
                "of_feature": "EX_Base",
                "face": "+z",
                "diameter": 6.0,
                "center": {"u": 10.0, "v": 0.0},
            },
            {"type": "cut_extrude_through_all", "name": "CUT_H2", "sketch": "SK_H2"},
        ],
    }
    r = part_build(spec, save_as=path, save_format="current", no_dim=True)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(path)


def run() -> str:
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
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

    tmp = tempfile.mkdtemp(prefix="w71_htpae_")
    part_path = os.path.join(tmp, "W71_HoleTblPAE.SLDPRT")
    drw_path = os.path.join(tmp, "W71_HoleTblPAE.SLDDRW")

    if not gate("build_part", _build_part(part_path), part_path):
        return "WALL"

    spec = {
        "kind": "drawing",
        "name": "ht_pae",
        "model": part_path,
        "views": ["front", "top"],
        "hole_table": True,
        "sheet": {"template_size": "A3"},
    }
    dp = sw_propose_drawing(spec)
    if not gate("propose", dp.get("ok", False), str(dp.get("error") or "")):
        return "PARTIAL"
    sw_dry_run_drawing(dp["proposal_id"])
    dc = sw_commit_drawing(dp["proposal_id"], drw_path)
    gate("commit", dc.get("ok", False), str(dc.get("error") or ""))
    gate(
        "hole_table_inserted_flag",
        dc.get("hole_table_inserted") is True,
        f"hole_table_inserted={dc.get('hole_table_inserted')}",
    )
    if not dc.get("ok"):
        results["commit_error"] = dc.get("error")
        return "PARTIAL"
    gate(
        "drw_on_disk",
        os.path.isfile(drw_path),
        f"size={os.path.getsize(drw_path) if os.path.isfile(drw_path) else 0}",
    )

    # Reopen part + drawing; walk views for a persisted IHoleTableAnnotation.
    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    except Exception:
        pass
    ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
    drw_doc = ret[0] if isinstance(ret, tuple) else ret
    reopen_hole_tables = 0
    if drw_doc is not None:
        drw_typed = typed(drw_doc, "IDrawingDoc", module=mod)
        v = drw_typed.GetFirstView()
        while v is not None:
            tv = typed_qi(v, "IView", module=mod)
            try:
                ta = tv.GetFirstTableAnnotation()
                while ta is not None:
                    try:
                        typed_qi(ta, "IHoleTableAnnotation", module=mod)
                        reopen_hole_tables += 1
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
            t = drw_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
    results["reopen_hole_tables"] = reopen_hole_tables
    gate(
        "reopen_hole_table_persists",
        reopen_hole_tables >= 1,
        f"hole_tables={reopen_hole_tables}",
    )

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
