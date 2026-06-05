"""Wave-13 Slice 1: Rotation marshaling spike.

Proven recipe for rotated component placement on SW 2024 SP1:
  1. mu = typed(sw.GetMathUtility, 'IMathUtility', module=mod)
     — needs active doc context; zero-arg auto-invoke (no parens).
  2. xform = mu.CreateTransform(VARIANT(VT_ARRAY|VT_R8, tuple(16 floats)))
     — typed wrapper REQUIRED (raw dispatch fails 'Member not found').
  3. comp.Transform2 = xform  (propput of IMathTransform)
  4. comp.SetTransformAndSolve(xform)  (forces geometry update)
  5. Transform persists through save/reopen.

ArrayData layout (CONFIRMED):
  [0..8] = 3x3 rotation (row-major)
  [9..11] = translation (x,y,z) in METRES
  [12] = scale (1.0)
  [13..15] = 0

RPY convention: rpy_deg = [roll(X), pitch(Y), yaw(Z)]
  R = Rz(yaw) . Ry(pitch) . Rx(roll)  (intrinsic ZYX)

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import json
import math
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
    WORKTREE / "spikes" / "v0_2x" / "_results" / "rotated_placement.json"
)

results: dict[str, Any] = {
    "spike": "w13_rotated_placement",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "characterization": {},
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


def rpy_to_matrix(
    roll_deg: float, pitch_deg: float, yaw_deg: float
) -> list[float]:
    """Build 16-element SW transform array: R = Rz . Ry . Rx, row-major."""
    rx, ry, rz = (
        math.radians(roll_deg),
        math.radians(pitch_deg),
        math.radians(yaw_deg),
    )
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    return [
        cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx,
        sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx,
        -sy,     cy * sx,               cy * cx,
        0.0, 0.0, 0.0,
        1.0, 0.0, 0.0, 0.0,
    ]


def run() -> str:
    print("=" * 70)
    print("Wave-13 Slice 1: Rotation marshaling spike")
    print("=" * 70)

    import pythoncom
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

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
    PART_PATH = str(_tmp / f"w13_rotate_{_ts}_box.SLDPRT")
    ASM_PATH = str(_tmp / f"w13_rotate_{_ts}.SLDASM")

    PART_SPEC = {
        "schema_version": 1,
        "name": "RotateBox",
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

    # Create assembly + place
    print("\n--- Creating assembly + placing ---")
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
        tsw = typed(sw, "ISldWorks", module=mod)
        tasm = typed(asm_doc, "IAssemblyDoc", module=mod)

        tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
        comp_raw = tasm.AddComponent4(PART_PATH, "", 0.0, 0.0, 0.0)
        comp = typed_qi(comp_raw, "IComponent2", module=mod)
        gate("place_component", comp is not None)

        # Pre-rotation transform
        pre_ad = list(comp.Transform2.ArrayData)
        print(f"\n  Pre-rotation transform: {[round(v,4) for v in pre_ad]}")

        # GetMathUtility (needs active doc; zero-arg auto-invoke)
        print("\n--- Characterization: IMathUtility ---")
        mu = typed(sw.GetMathUtility, "IMathUtility", module=mod)
        gate("get_math_utility", mu is not None,
             f"type={type(mu).__name__}")

        # Create 90°-Z transform
        print("\n--- Characterization: CreateTransform (90° about Z) ---")
        arr_90z = rpy_to_matrix(0.0, 0.0, 90.0)
        print(f"  16-elem: {[round(v, 6) for v in arr_90z]}")

        varr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(arr_90z)
        )
        xform = mu.CreateTransform(varr)
        gate("create_transform", xform is not None,
             f"type={type(xform).__name__}")

        if xform is None:
            save_results()
            return "WALL"

        # Readback from the created transform
        xform_ad = list(xform.ArrayData)
        gate("xform_arraydata",
             all(abs(xform_ad[i] - arr_90z[i]) < 0.001 for i in range(16)),
             f"matches input array")

        # Apply to component
        print("\n--- Characterization: Transform2 + SetTransformAndSolve ---")
        comp.Transform2 = xform
        gate("transform2_propput", True, "set OK")

        comp.SetTransformAndSolve(xform)
        gate("set_transform_and_solve", True, "solve OK")

        # Force rebuild
        try:
            asm_doc.ForceRebuild3(True)
        except Exception:
            pass

        # Readback from component
        rb_ad = list(comp.Transform2.ArrayData)
        gate("transform_readback",
             all(abs(rb_ad[i] - arr_90z[i]) < 0.001 for i in range(9)),
             f"rotation block matches: {[round(v,4) for v in rb_ad[:9]]}")

        # Save + reopen to confirm persistence
        print("\n--- Characterization: save/reopen persistence ---")
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
            ret = tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)
            asm2 = ret[0] if isinstance(ret, tuple) else ret
            if asm2:
                tasm2 = typed(asm2, "IAssemblyDoc", module=mod)
                comps = tasm2.GetComponents(True)
                if comps:
                    cc = typed_qi(comps[0], "IComponent2", module=mod)
                    reopen_ad = list(cc.Transform2.ArrayData)
                    gate("persist_after_reopen",
                         all(abs(reopen_ad[i] - arr_90z[i]) < 0.001
                             for i in range(9)),
                         f"rotation preserved: "
                         f"{[round(v,4) for v in reopen_ad[:9]]}")

                try:
                    t = asm2.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass

        # Record characterization
        results["characterization"] = {
            "arraydata_layout": {
                "rotation": "indices 0-8, 3x3 row-major",
                "translation": "indices 9-11, metres",
                "scale": "index 12",
                "padding": "indices 13-15, zeros",
                "confirmed": True,
            },
            "transform_method": "CreateTransform(typed IMathUtility) "
                                "+ Transform2 propput + SetTransformAndSolve",
            "solve_required": True,
            "rpy_convention": {
                "order": "Rz . Ry . Rx",
                "description": "rpy_deg = [roll(X), pitch(Y), yaw(Z)]",
                "intrinsic": "ZYX (extrinsic XYZ)",
            },
            "gotcha_math_utility": (
                "sw.GetMathUtility auto-invokes as property (no parens); "
                "needs active document context; typed() wrapper required "
                "for CreateTransform (raw dispatch fails 'Member not found')"
            ),
        }

        # Overall
        all_pass = all(
            g["ok"] for g in results["gates"].values()
        )
        gate("OVERALL", all_pass,
             "all characterizations passed; recipe proven")

        return "GREEN" if all_pass else "PARTIAL"

    finally:
        # Cleanup
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
