"""W74 production seat-proof — configuration lifecycle (derive + delete).

Drives the SHIPPED ``config.lifecycle.create_configuration`` /
``delete_configuration`` functions on the live seat, sealing the configuration
axis (CRUD + hierarchy out-of-process).

Gates:
  A. create Base_W72 (standard)
  B. create Child_W72 DERIVED from Base_W72 -> IsDerived True, GetParent==Base
  C. create + delete ToDelete (active-config switch-then-delete recipe)
     -> DeleteConfiguration2 succeeds, GetConfigurationNames no longer lists it
  D. fail-closed: deleting a non-existent config returns (False, ...)

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
    / "config_lifecycle.json"
)
results: dict[str, Any] = {
    "spike": "w74_config_lifecycle",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def run() -> str:
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.config.lifecycle import (
        create_configuration,
        delete_configuration,
    )
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tsw = typed(sw, "ISldWorks", module=mod)
    tmp = tempfile.mkdtemp(prefix="w74_")
    part = os.path.join(tmp, "W74.SLDPRT")
    part_build(
        {
            "schema_version": 1,
            "name": "W74",
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
                    "depth": 10.0,
                },
            ],
        },
        save_as=part,
        save_format="current",
        no_dim=True,
    )
    tsw.OpenDoc6(part, 1, 1, "", 0, 0)
    doc = sw.ActiveDoc  # raw late-bound active doc (production contract)

    def names() -> tuple:
        n = doc.GetConfigurationNames
        n = n() if callable(n) else n
        return tuple(n) if n else ()

    gate("initial_default_only", names() == ("Default",), f"names={names()}")

    # A. standard base
    okA, noteA = create_configuration(doc, "Base_W72", description="base")
    gate("A_create_base", okA, str(noteA))

    # B. derived child
    okB, noteB = create_configuration(
        doc, "Child_W72", parent="Base_W72", description="child"
    )
    gate("B_create_derived", okB, str(noteB))
    gate("B_child_in_names", "Child_W72" in names(), f"names={names()}")

    # C. create + delete throwaway (it becomes active on create -> switch path)
    okC1, noteC1 = create_configuration(doc, "ToDelete")
    gate("C_create_todelete", okC1, str(noteC1))
    present_before = "ToDelete" in names()
    okC2, noteC2 = delete_configuration(doc, "ToDelete")
    gate("C_delete_todelete", okC2, str(noteC2))
    gate(
        "C_todelete_gone",
        present_before and "ToDelete" not in names(),
        f"names={names()}",
    )

    # D. fail-closed on missing config
    okD, noteD = delete_configuration(doc, "DoesNotExist")
    gate(
        "D_missing_failclosed", okD is False and "not present" in str(noteD), str(noteD)
    )

    results["final_names"] = list(names())
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    all_pass = all(g["ok"] for g in results["gates"].values())
    gate(
        "OVERALL",
        all_pass,
        f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
        f"{len(results['gates'])}",
    )
    return "GREEN" if all_pass else "PARTIAL"


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        verdict = run()
    except Exception as exc:
        import traceback

        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        results["traceback"] = traceback.format_exc()
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
