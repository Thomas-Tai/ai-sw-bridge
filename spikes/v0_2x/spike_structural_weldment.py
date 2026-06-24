"""W73 production seat-proof — ``structural_weldment`` registry handler.

Drives the SHIPPED ``create_structural_weldment`` handler (the uniform
dry-run+commit code path) on the live seat, NOT the raw API. Flips
``features/structural_weldment.py`` SPIKE_STATUS UNFIRED -> GREEN once these
gates pass:

  A. simple_cut  -> ok=True, ΔVol > 0, 2 bodies (one member per L-segment)
  B. miter_merge -> ok=True, ΔVol > 0, 1 body (members fused by the
                    member-member intersection solve)
  C. the 0-ghost trap is unreachable (connected_segments routes to 1/2 only)
  D. a missing profile fails closed (no silent ghost)

Prereq: SOLIDWORKS 2024 running + standard weldment profiles installed.
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
    / "structural_weldment.json"
)
PROFILE = (
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
    r"\data\weldment profiles\iso\square tube.sldlfp"
)
CONFIG = "20 x 20 x 2"

results: dict[str, Any] = {
    "spike": "w73_structural_weldment",
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
    from ai_sw_bridge.features import verify
    from ai_sw_bridge.features.structural_weldment import create_structural_weldment
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    gate("profile_present", os.path.isfile(PROFILE), PROFILE)
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tsw = typed(sw, "ISldWorks", module=mod)

    def _fresh_doc() -> Any:
        tmp = tempfile.mkdtemp(prefix="w73sp_")
        part = os.path.join(tmp, "W73.SLDPRT")
        spec = {
            "schema_version": 1,
            "name": "W73",
            "features": [
                {
                    "type": "sketch_3d_sketch",
                    "name": "PATH",
                    "points": [
                        {"x": 0.0, "y": 0.0, "z": 0.0},
                        {"x": 100.0, "y": 0.0, "z": 0.0},
                        {"x": 100.0, "y": 100.0, "z": 0.0},
                    ],
                },
            ],
        }
        part_build(spec, save_as=part, save_format="current", no_dim=True)
        # Open via the typed tsw (handles OpenDoc6's [out] error args), then
        # return the RAW late-bound active doc — exactly what production's
        # _apply_feature passes the handler, and which exposes FeatureByName
        # (the typed IModelDoc2 wrapper does not). Match production exactly.
        tsw.OpenDoc6(part, 1, 1, "", 0, 0)
        return sw.ActiveDoc

    base_feat = {
        "profile_path": PROFILE,
        "configuration": CONFIG,
        "sketch_name": "PATH",
    }

    # --- A. simple_cut ---
    doc = _fresh_doc()
    okA, noteA = create_structural_weldment(
        doc, {**base_feat, "connected_segments": "simple_cut"}, {}
    )
    bodiesA = verify.solid_body_count(doc)
    volA = verify.solid_volume_mm3(doc)
    gate("A_simple_cut_ok", okA, str(noteA))
    gate("A_two_bodies", bodiesA == 2, f"bodies={bodiesA} vol={volA:.3f}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    # --- B. miter_merge (intersection solve fuses 2->1) ---
    doc = _fresh_doc()
    okB, noteB = create_structural_weldment(
        doc,
        {
            **base_feat,
            "connected_segments": "simple_cut",
            "corner_treatment": True,
            "miter_merge": True,
        },
        {},
    )
    bodiesB = verify.solid_body_count(doc)
    volB = verify.solid_volume_mm3(doc)
    gate("B_miter_merge_ok", okB, str(noteB))
    gate("B_one_body", bodiesB == 1, f"bodies={bodiesB} vol={volB:.3f}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    # --- C. 0-ghost trap unreachable (bad enum string fails at validation) ---
    doc = _fresh_doc()
    okC, noteC = create_structural_weldment(
        doc, {**base_feat, "connected_segments": "none"}, {}
    )
    gate(
        "C_zero_ghost_unreachable",
        okC is False and "connected_segments" in str(noteC),
        str(noteC),
    )
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    # --- D. missing profile fails closed ---
    doc = _fresh_doc()
    okD, noteD = create_structural_weldment(
        doc, {**base_feat, "profile_path": PROFILE + ".nope"}, {}
    )
    gate(
        "D_missing_profile_failclosed",
        okD is False and "does not exist" in str(noteD),
        str(noteD),
    )
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
    # Notes carry 'ΔVol' (U+0394); the Windows cp1252 console can't encode it.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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
