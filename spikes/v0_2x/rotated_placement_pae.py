"""Wave-13 Slice 4: Rotated placement production PAE.

Exercises the production place_components rotation path end-to-end:
  1. Build a box part.
  2. Author an assembly spec with rpy_deg=[0,0,90].
  3. Run through production lifecycle (place_components with rotation).
  4. Verify the component's Transform2 carries the 90°-Z rotation.
  5. Save + reopen to confirm persistence.

Proves that the production handler correctly applies rotation via the
proven CreateTransform + Transform2 + SetTransformAndSolve recipe.

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
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "rotated_placement_pae.json"
)

results: dict[str, Any] = {
    "pae": "w13_rotated_placement",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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
    print("Wave-13 Slice 4: Rotated placement production PAE")
    print("=" * 70)

    import pythoncom
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build
    from ai_sw_bridge.assembly.handlers import place_components

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all docs
    try:
        for d in (sw.GetDocuments() or []):
            try:
                d.CloseDoc
            except Exception:
                pass
    except Exception:
        pass

    # Build test part
    print("\n--- Building test part ---")
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_PATH = str(_tmp / f"w13_pae_{_ts}_box.SLDPRT")
    ASM_PATH = str(_tmp / f"w13_pae_{_ts}.SLDASM")

    PART_SPEC = {
        "schema_version": 1,
        "name": "RotBox",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 40.0, "height": 20.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 10.0},
        ],
    }

    r = part_build(PART_SPEC, save_as=PART_PATH, save_format="current",
                   no_dim=True)
    gate("build_part", r.ok and os.path.isfile(PART_PATH), f"ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        save_results()
        return "WALL"

    # Create assembly
    print("\n--- Creating assembly ---")
    import glob
    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    gate("asm_create", asm_doc is not None)

    if asm_doc is None:
        save_results()
        return "WALL"

    try:
        # Place components with rpy_deg=[0,0,90] through production handler
        print("\n--- Placing with rotation (production handler) ---")
        components = [
            {
                "id": "rotated_box",
                "part": PART_PATH,
                "transform": {
                    "xyz_mm": [0, 0, 0],
                    "rpy_deg": [0, 0, 90],
                },
            },
        ]

        placed, place_err = place_components(
            sw, asm_doc, components, mod=mod
        )
        gate("place_with_rotation", place_err is None,
             f"placed={len(placed)}, err={place_err}")

        if place_err:
            save_results()
            return "PARTIAL"

        # Verify transform
        print("\n--- Verifying rotation ---")
        comp = placed["rotated_box"]
        comp_typed = typed_qi(comp, "IComponent2", module=mod)
        rb_ad = list(comp_typed.Transform2.ArrayData)

        # Expected: Rz(90°) = [[0,-1,0],[1,0,0],[0,0,1]]
        expected_rot = [0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        rot_match = all(
            abs(rb_ad[i] - expected_rot[i]) < 0.001 for i in range(9)
        )
        gate("rotation_matrix", rot_match,
             f"expected={expected_rot}, "
             f"got={[round(v, 4) for v in rb_ad[:9]]}")

        results["transform_readback"] = [round(v, 6) for v in rb_ad]

        # Save + reopen
        print("\n--- Save + reopen persistence ---")
        try:
            asm_doc.SaveAs3(ASM_PATH, 0, 2)
            gate("save_assembly", os.path.isfile(ASM_PATH))
        except Exception as e:
            gate("save_assembly", False, str(e)[:60])

        # Close
        try:
            t = asm_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

        # Reopen
        if os.path.isfile(ASM_PATH):
            tsw = typed(sw, "ISldWorks", module=mod)
            ret = tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)
            asm2 = ret[0] if isinstance(ret, tuple) else ret
            if asm2:
                tasm2 = typed(asm2, "IAssemblyDoc", module=mod)
                comps = tasm2.GetComponents(True)
                if comps:
                    cc = typed_qi(comps[0], "IComponent2", module=mod)
                    reopen_ad = list(cc.Transform2.ArrayData)
                    persist_match = all(
                        abs(reopen_ad[i] - expected_rot[i]) < 0.001
                        for i in range(9)
                    )
                    gate("persist_after_reopen", persist_match,
                         f"rotation preserved: "
                         f"{[round(v, 4) for v in reopen_ad[:9]]}")
                try:
                    t = asm2.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass

        # Also verify zero-rpy still works (regression check)
        print("\n--- Regression: zero rpy stays on fast path ---")
        asm_doc2 = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
        if asm_doc2:
            try:
                components_no_rot = [
                    {
                        "id": "no_rot",
                        "part": PART_PATH,
                        "transform": {"xyz_mm": [0, 0, 0]},
                    },
                ]
                placed2, err2 = place_components(
                    sw, asm_doc2, components_no_rot, mod=mod
                )
                gate("zero_rpy_still_works",
                     err2 is None and len(placed2) == 1,
                     f"placed={len(placed2)}, err={err2}")
            finally:
                try:
                    t = asm_doc2.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass

        # Overall
        all_pass = all(g["ok"] for g in results["gates"].values())
        gate("OVERALL_GREEN", all_pass,
             "rotation applied + persisted + zero-rpy regression clean")

        return "GREEN" if all_pass else "PARTIAL"

    finally:
        for pp in [PART_PATH]:
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
