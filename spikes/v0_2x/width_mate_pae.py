"""Wave-12 Width mate production PAE.

Exercises the production width-mate handler end-to-end on a live SW seat:
  1. Build a slot part (40 mm wide box — groove faces on ±x sides).
  2. Build a tab part (20 mm wide box — tab faces on ±x sides).
  3. Place both in an assembly.
  4. Author a width mate through the production ``create_mate`` handler.
  5. ``verify_mates`` → expect ONE MateWidth, solved:true, error_code 0.

Proves that the W11 spike err-51 was over-constraint-only: a SOLO width
mate on two simple boxes must solve clean.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "width_mate_pae.json"

results: dict[str, Any] = {
    "pae": "wave12_width_mate",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verify_mates": [],
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


def run() -> str:
    print("=" * 70)
    print("Wave-12: Width mate production PAE")
    print("=" * 70)

    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build
    from ai_sw_bridge.assembly.handlers import (
        create_mate,
        place_components,
        verify_mates,
    )
    from ai_sw_bridge.assembly.face_resolver import resolve_component_face

    mod = wrapper_module()

    import win32com.client as w32_compat

    sw = w32_compat.Dispatch("SldWorks.Application")

    # Close all docs for a clean slate
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    d.CloseDoc
                except Exception:
                    pass
    except Exception:
        pass

    # Build parts
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    SLOT_PATH = str(_tmp / f"w12_width_{_ts}_slot.SLDPRT")
    TAB_PATH = str(_tmp / f"w12_width_{_ts}_tab.SLDPRT")

    SLOT_SPEC = {
        "schema_version": 1,
        "name": "WidthSlot",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40.0,
                "height": 10.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    TAB_SPEC = {
        "schema_version": 1,
        "name": "WidthTab",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 20.0,
                "height": 10.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    print("\n--- Building parts ---")
    for label, path, spec in [
        ("slot", SLOT_PATH, SLOT_SPEC),
        ("tab", TAB_PATH, TAB_SPEC),
    ]:
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_{label}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not os.path.isfile(SLOT_PATH) or not os.path.isfile(TAB_PATH):
        gate("parts_built", False, "Part build failed")
        save_results()
        return "WALL"

    # Create assembly
    print("\n--- Creating assembly ---")
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    if not asm_templates:
        gate("template_found", False, "No .ASMDOT template found")
        save_results()
        return "WALL"

    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    gate(
        "asm_create",
        asm_doc is not None,
        f"type={type(asm_doc).__name__ if asm_doc else None}",
    )

    if asm_doc is None:
        save_results()
        return "WALL"

    try:
        # Place components
        print("\n--- Placing components ---")
        components = [
            {"id": "slot", "part": SLOT_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "tab", "part": TAB_PATH, "transform": {"xyz_mm": [0, 0, 0.015]}},
        ]
        placed, place_err = place_components(sw, asm_doc, components, mod=mod)
        gate("place", place_err is None, f"placed={len(placed)}, err={place_err}")

        if place_err:
            save_results()
            return "PARTIAL"

        # Probe faces for face_ref centroids
        print("\n--- Probing face centroids ---")
        slot_comp = placed["slot"]
        tab_comp = placed["tab"]

        def probe_face(comp: Any, normal: list[float]) -> dict:
            ref = {"normal": normal}
            res = resolve_component_face(asm_doc, comp, ref, mod=mod)
            return {
                "ok": res.ok,
                "method": res.method,
                "error": res.error,
            }

        slot_l = probe_face(slot_comp, [-1, 0, 0])
        slot_r = probe_face(slot_comp, [1, 0, 0])
        tab_l = probe_face(tab_comp, [-1, 0, 0])
        tab_r = probe_face(tab_comp, [1, 0, 0])

        all_ok = all(f["ok"] for f in [slot_l, slot_r, tab_l, tab_r])
        gate(
            "faces_resolve",
            all_ok,
            f"slot_L={slot_l['ok']}, slot_R={slot_r['ok']}, "
            f"tab_L={tab_l['ok']}, tab_R={tab_r['ok']}",
        )

        if not all_ok:
            save_results()
            return "PARTIAL"

        # Create width mate through the PRODUCTION handler
        print("\n--- Creating width mate (production handler) ---")
        width_spec = {
            "type": "width",
            "width_faces": [
                {"component": "slot", "face_ref": {"normal": [-1, 0, 0]}},
                {"component": "slot", "face_ref": {"normal": [1, 0, 0]}},
            ],
            "tab_faces": [
                {"component": "tab", "face_ref": {"normal": [-1, 0, 0]}},
                {"component": "tab", "face_ref": {"normal": [1, 0, 0]}},
            ],
        }

        mate_feat, mate_err = create_mate(asm_doc, placed, width_spec, mod=mod)
        mate_ok = mate_feat is not None and mate_err is None
        gate(
            "create_width_mate",
            mate_ok,
            f"feat={type(mate_feat).__name__ if mate_feat else None}, "
            f"err={mate_err}",
        )

        if not mate_ok:
            save_results()
            return "PARTIAL"

        # Verify
        print("\n--- Verifying mates ---")
        try:
            asm_doc.ForceRebuild3(True)
        except Exception:
            pass

        vm = verify_mates(asm_doc, mod=mod)
        results["verify_mates"] = vm

        print(f"  verify_mates: {len(vm)} mates:")
        for m in vm:
            print(
                f"    {m['name']}: type={m['type']}, "
                f"solved={m['solved']}, error_code={m['error_code']}"
            )

        width_mates = [m for m in vm if m["type"] == "MateWidth"]
        gate("has_width_mate", len(width_mates) == 1, f"count={len(width_mates)}")

        if width_mates:
            wm = width_mates[0]
            gate(
                "width_solved",
                wm.get("solved", False),
                f"solved={wm.get('solved')}, " f"error_code={wm.get('error_code')}",
            )
            gate(
                "width_error_clean",
                wm.get("error_code", -1) == 0,
                f"error_code={wm.get('error_code')}",
            )
            gate(
                "width_not_suppressed",
                not wm.get("suppressed", True),
                f"suppressed={wm.get('suppressed')}",
            )

        all_solved = (
            len(width_mates) == 1
            and width_mates[0].get("solved", False)
            and width_mates[0].get("error_code", -1) == 0
            and not width_mates[0].get("suppressed", True)
        )
        gate(
            "OVERALL_GREEN",
            all_solved,
            "solo MateWidth solved clean (err-51 was over-constraint only)",
        )

        return "GREEN" if all_solved else "PARTIAL"

    finally:
        try:
            t = asm_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        for pp in [SLOT_PATH, TAB_PATH]:
            try:
                part_name = Path(pp).stem
                for suffix in (".SLDPRT", ".sldprt"):
                    sw.CloseDoc(part_name + suffix)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "WALL"
    finally:
        results["verdict"] = verdict
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GREEN" else 1)
