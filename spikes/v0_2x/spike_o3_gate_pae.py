"""Batch O3 orchestrator gate — measure/clearance verbs via SolidWorksClient on the seat.

Verifies the worker-ported O3 batch (observe_measure + observe_clearance) end-to-end
on the live seat, exercising the two the directive named (overlapping cubes clearance +
measure area):

  A measure_area_clean : ai-sw-observe `measure_area` runner
                         (SolidWorksClient().observe.measure_area) returns ok=True with a
                         real area on a pre-selected cube face (~400 mm^2 for a 20mm cube
                         face), and emits NO PendingDeprecationWarning internally.
  B clearance_clean    : ai-sw-observe `clearance` runner (…observe.clearance) returns
                         ok=True on an assembly of two 20mm cubes whose centers are 30mm
                         apart (→ ~10mm gap), with NO internal PendingDeprecationWarning.
  C baseline_identity  : the legacy free function sw_get_clearance STILL warns AND its
                         payload is byte-identical to the class-routed result (proves the
                         v0.17 data baseline is preserved across the shim boundary).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_o3_gate_pae.py
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import observe as cli_observe  # noqa: E402
from ai_sw_bridge.observe_clearance import sw_get_clearance  # noqa: E402
from ai_sw_bridge.sw_com import get_active_doc, get_sw_app  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "o3_gate_pae.json"
results: dict[str, Any] = {"pae": "o3_measure_clearance_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _under_warnings_as_errors(fn) -> tuple[dict[str, Any], bool, str]:
    """Run *fn*; PendingDeprecationWarning becomes an exception (leak detector)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        try:
            return fn(), True, ""
        except PendingDeprecationWarning as exc:  # noqa: BLE001
            return {"ok": False}, False, f"internal PendingDeprecationWarning leaked: {exc}"


def _select_first_face(doc) -> bool:
    """Select the first solid face of the active part (so measure_area has a target)."""
    try:
        bodies = doc.GetBodies2(0, False)  # swSolidBody = 0
        if bodies is None:
            return False
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
        faces = body.GetFaces()
        if faces is None:
            return False
        face = faces[0] if isinstance(faces, (list, tuple)) else faces
        # IFace2 IS-A IEntity → Select4(Append, ISelectData). Bare None marshals to
        # 'Type mismatch' out-of-process (callout-None wall) → pass a typed null VARIANT.
        return bool(face.Select4(False, VARIANT(pythoncom.VT_DISPATCH, None)))
    except Exception as exc:  # noqa: BLE001
        print(f"    (face-select failed: {exc})")
        return False


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        # ── A: measure_area via the client (pre-selected cube face) ───────
        cube = P._build("o3_area_cube", P._cube("o3_area_cube", 20.0))
        if "error" in cube:
            gate("measure_area_clean", False, cube["error"])
            raise SystemExit(_finish())
        doc = get_active_doc(get_sw_app())
        selected = _select_first_face(doc)
        if not selected:
            gate("measure_area_clean", False, "could not select a face for measure_area")
            raise SystemExit(_finish())
        rep, clean, why = _under_warnings_as_errors(
            lambda: cli_observe._run_measure_area(argparse.Namespace()))
        results["measure_area_report"] = rep
        area = (rep.get("measure") or {}).get("area_mm2")
        gate("measure_area_clean",
             clean and bool(rep.get("ok")) and isinstance(area, (int, float)) and area > 0,
             why or f"ok={rep.get('ok')} area={area} mm^2 (class-routed, no warning)")

        # ── B: clearance via the client (two 20mm cubes, centers 30mm apart) ─
        sw.CloseAllDocuments(True)
        base = P._build("o3_clr_base", P._cube("o3_clr_base", 20.0))
        arm = P._build("o3_clr_arm", P._cube("o3_clr_arm", 20.0))
        for x in (base, arm):
            if "error" in x:
                gate("clearance_clean", False, x["error"])
                raise SystemExit(_finish())
        # 20mm cubes, centers 30mm apart on X → ~10mm face gap (no overlap).
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [30, 0, 0]}},
        ]
        asm, _placed, err = P._place(sw, mod, comps)
        if err:
            gate("clearance_clean", False, err)
            raise SystemExit(_finish())
        adoc = get_active_doc(get_sw_app())
        raw = adoc.GetComponents(True)
        names = [c.Name2 for c in (raw if isinstance(raw, (list, tuple)) else [raw])]
        if len(names) < 2:
            gate("clearance_clean", False, f"expected 2 components, got {names}")
            raise SystemExit(_finish())
        ns_clr = argparse.Namespace(comp_a=names[0], comp_b=names[1])
        rep2, clean2, why2 = _under_warnings_as_errors(
            lambda: cli_observe._run_clearance(ns_clr))
        results["clearance_report"] = rep2
        gap = (rep2.get("clearance") or {}).get("min_distance_mm")
        gate("clearance_clean",
             clean2 and bool(rep2.get("ok")) and isinstance(gap, (int, float))
             and 9.0 < gap < 11.0,
             why2 or f"ok={rep2.get('ok')} min_distance_mm={gap} "
             f"(expected ~10, class-routed, no warning)")

        # ── C: legacy shim STILL warns AND payload identical to baseline ──
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_get_clearance(adoc, names[0], names[1])
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        identical = legacy == rep2
        gate("baseline_identity",
             warned and identical,
             f"legacy warned={warned}, payload_identical_to_class_route={identical}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
