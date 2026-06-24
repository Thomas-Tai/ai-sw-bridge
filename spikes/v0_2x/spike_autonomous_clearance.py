"""W76 CLOSED-LOOP VANGUARD — autonomous 1D clearance solver.

Proves the framework can ACT on its interference sense, not just read it: an
assembly is spawned in a known COLLIDING state and a lightweight harness drives
it to a geometrically-resolved, clash-free state with zero human intervention.

The capability under test is the ORCHESTRATION loop, built entirely from shipped,
seat-proven production pieces (no new handler, no API discovery):

  - sense   : observe_interference.sw_get_interference  (W27)
  - act     : motion_audit.drive_mate_value_si          (W49 — Parameter
              "D1@<mate>".SystemValue = value_si + EditRebuild3)
  - fixture : a swMateDISTANCE between the two cubes' +X faces; the mate value
              equals the center-to-center offset (each cube is 20mm, ±10 from
              center), so D<20 => overlap, D==20 => faces touch (coincidence,
              NOT interference), D>20 => clear.

Loop logic (deliberately NOT volume-derived): interference VOLUME is a 3D overlap
integral, not a 1D penetration depth, so volume->distance is non-linear and
geometry-specific. The honest, robust solver is monotonic fixed step-out with an
iteration cap; a volume->depth model is a separate future lane needing a true
penetration-depth witness.

  init D = 10mm (10mm overlap) --[+2mm/step]--> halt at first D with
  count==0 AND volume==0 (expected ~20mm). Witness = autonomous overlap->clear.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_autonomous_clearance.py
"""

from __future__ import annotations

import json
import os
import sys
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402
from ai_sw_bridge.motion_audit import drive_mate_value_si  # noqa: E402
from ai_sw_bridge.observe_interference import sw_get_interference  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "autonomous_clearance.json"

CUBE_MM = 20.0
INIT_DIST_MM = 10.0  # colliding: 10mm overlap of the 20mm cubes
STEP_MM = 2.0  # monotonic step-out increment
MAX_ITERS = 20  # runaway guard (caps the live seat)
SW_MATE_DISTANCE = 5  # swMateDISTANCE

results: dict[str, Any] = {
    "spike": "w76_autonomous_clearance",
    "params": {
        "cube_mm": CUBE_MM,
        "init_mm": INIT_DIST_MM,
        "step_mm": STEP_MM,
        "max_iters": MAX_ITERS,
    },
    "trajectory": [],
    "gates": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _plus_x_face(comp: Any, mod: Any) -> Any | None:
    """The component's +X planar face (normal ~+X, most-positive position)."""
    best = None
    best_px = None
    for f, pp in P._planar_faces(comp, mod):
        nx, px = pp[0], pp[3]
        if nx > 0.9 and (best_px is None or px > best_px):
            best, best_px = f, px
    return best


def _vol_sum(intf: dict[str, Any]) -> float:
    return sum(
        float(i.get("interference_volume_mm3") or 0.0)
        for i in (intf.get("interferences") or [])
    )


def _make_distance_mate(
    typed_asm: Any,
    fa: Any,
    fb: Any,
    dist_m: float,
    align: int,
    mod: Any,
) -> tuple[Any | None, str | None, str | None]:
    """CreateMateData(5) -> IDistanceMateFeatureData -> CreateMate. The fixture
    builder; the loop drives this mate via the production driver."""
    try:
        md = typed_asm.CreateMateData(SW_MATE_DISTANCE)
        if md is None:
            return None, None, "CreateMateData None"
        ti = typed_qi(md, "IDistanceMateFeatureData", module=mod)
        ti.EntitiesToMate = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (fa, fb)
        )
        ti.Distance = dist_m
        try:
            ti.MateAlignment = align
        except Exception:
            pass
        mate = typed_asm.CreateMate(md)
        if mate is None or isinstance(mate, int):
            try:
                es = typed_qi(md, "IMateFeatureData", module=mod).ErrorStatus
            except Exception:
                es = "?"
            return None, None, f"CreateMate None (ErrorStatus={es})"
        name = typed(mate, "IFeature", module=mod).Name
        name = name() if callable(name) else name
        return mate, str(name), None
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _try_fixture(
    sw: Any, mod: Any, path_a: str, path_b: str, align: int
) -> dict[str, Any] | None:
    """Spawn a fresh assembly, pre-place B at the colliding offset, add the
    distance mate, and read the initial interference. Returns the fixture dict
    only if the initial state genuinely collides; else closes and returns None."""
    tmpl = _find_assembly_template()
    if tmpl is None:
        return None
    asm = sw.NewDocument(tmpl, 0, 0.1, 0.1)
    if asm is None:
        return None
    comps = [
        {"id": "a", "part": path_a, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "b", "part": path_b, "transform": {"xyz_mm": [INIT_DIST_MM, 0, 0]}},
    ]
    placed, err = place_components(sw, asm, comps, mod=mod)
    if err:
        return None
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    fa = _plus_x_face(placed["a"], mod)
    fb = _plus_x_face(placed["b"], mod)
    if not (fa and fb):
        return None
    typed_asm = typed(asm, "IAssemblyDoc", module=mod)
    mate, name, merr = _make_distance_mate(
        typed_asm, fa, fb, INIT_DIST_MM / 1000.0, align, mod
    )
    if merr or name is None:
        return None
    typed(asm, "IModelDoc2", module=mod).EditRebuild3()
    intf = sw_get_interference(asm)
    if intf.get("interference_count", 0) > 0 and _vol_sum(intf) > 0.0:
        return {"asm": asm, "mate_name": name, "align": align, "init_intf": intf}
    return None


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        a = P._build("clr_a", P._cube("clr_a", CUBE_MM))
        b = P._build("clr_b", P._cube("clr_b", CUBE_MM))
        if "error" in a or "error" in b:
            gate("fixture_parts", False, a.get("error") or b.get("error"))
            raise SystemExit(_finish())
        gate("fixture_parts", True, "two 20mm cubes built")

        # ── Establish a colliding fixture (alignment sweep = single-fire insurance) ──
        fx = None
        for align in (0, 1, 2):
            cand = _try_fixture(sw, mod, a["path"], b["path"], align)
            if cand is not None:
                fx = cand
                break
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        if fx is None:
            gate("fixture_collides", False, "no alignment yielded a colliding init")
            raise SystemExit(_finish())

        asm = fx["asm"]
        mate_name = fx["mate_name"]
        init_intf = fx["init_intf"]
        results["mate"] = {"name": mate_name, "alignment": fx["align"]}
        gate(
            "fixture_collides",
            True,
            f"mate={mate_name} align={fx['align']} "
            f"count={init_intf['interference_count']} "
            f"vol={_vol_sum(init_intf):.1f}mm3",
        )

        # ── The autonomous closed loop ──────────────────────────────────────
        cur_mm = INIT_DIST_MM
        solved = False
        solved_mm = None
        drive_err = None
        for it in range(MAX_ITERS):
            intf = sw_get_interference(asm)
            count = int(intf.get("interference_count", 0))
            vol = _vol_sum(intf)
            step = {
                "iter": it,
                "dist_mm": round(cur_mm, 3),
                "count": count,
                "volume_mm3": round(vol, 3),
            }
            results["trajectory"].append(step)
            print(
                f"  iter {it:2d}: D={cur_mm:5.1f}mm -> count={count} "
                f"vol={vol:8.1f}mm3"
            )
            if count == 0 and vol == 0.0:
                solved = True
                solved_mm = cur_mm
                break
            # ACT: step out via the production W49 driver, then it rebuilds.
            cur_mm += STEP_MM
            rc = drive_mate_value_si(asm, mate_name, cur_mm / 1000.0, mod)
            if rc.startswith("FAIL"):
                drive_err = rc
                break

        results["solved"] = solved
        results["solved_mm"] = solved_mm

        gate(
            "loop_resolved",
            solved,
            (
                f"clash-free at D={solved_mm}mm"
                if solved
                else f"unresolved after {len(results['trajectory'])} iters"
                + (f" (drive {drive_err})" if drive_err else "")
            ),
        )
        if solved:
            gate(
                "monotonic_stepout",
                solved_mm > INIT_DIST_MM,
                f"{INIT_DIST_MM}mm -> {solved_mm}mm",
            )
            # Geometry sanity: 20mm cubes clear at center-offset >= 20mm.
            gate(
                "clearance_geometry_sane",
                19.0
                <= solved_mm
                <= INIT_DIST_MM + STEP_MM * ((CUBE_MM - INIT_DIST_MM) / STEP_MM + 1),
                f"solved at {solved_mm}mm (expected ~{CUBE_MM}mm)",
            )
            gate("no_drive_error", drive_err is None, str(drive_err))
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
