"""W78 diagnostic — lightweight resolution unlocks per-component STL.

Confirms the root cause of the URDF mesh ghost: on a reopened-from-disk
assembly the components load LIGHTWEIGHT (B-rep absent from the kernel), so
SaveAs3-STL writes 0 bytes while returning NoError. Proves the fix:

  1. reopen the assembly from disk
  2. log each component's GetSuppression() state (lightweight)
  3. SaveAs3-STL BEFORE resolve            -> expect 0-byte ghost
  4. IAssemblyDoc.ResolveAllLightWeightComponents(True)
  5. re-log GetSuppression() state         -> expect changed (resolved)
  6. SaveAs3-STL AFTER resolve (in-context) -> expect >0 bytes
  7. SaveAs3-STL AFTER resolve (standalone open) -> expect >0 bytes

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_lightweight_resolution.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import resolve  # noqa: E402
from ai_sw_bridge.export.dispatch import ExportRequest, export_all  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "lightweight_resolution.json"
results: dict[str, Any] = {"probe": "w78_lightweight_resolution", "gates": {}, "log": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _suppression(comp: Any, mod: Any) -> Any:
    try:
        v = typed(comp, "IComponent2", module=mod).GetSuppression()
        return int(v() if callable(v) else v)
    except Exception as exc:  # noqa: BLE001
        return f"ERR:{exc!r}"


def _name2(comp: Any) -> str:
    nm = resolve(comp, "Name2")
    return str(nm() if callable(nm) else nm)


def _export_stl(doc: Any, name: str, out_dir: Path, binary: bool = True) -> int:
    """Export doc to out_dir/name.stl; return the byte count (0 = ghost/missing)."""
    reqs = [ExportRequest(format="stl", output_dir=out_dir, filename=name, binary=binary)]
    try:
        export_all(doc, reqs, name)
    except Exception:
        pass
    p = out_dir / f"{name}.stl"
    return p.stat().st_size if p.exists() else 0


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
        # ── Build + save a 2-component assembly, then CLOSE (force disk) ──
        base = P._build("lw_base", P._plate("lw_base"))
        arm = P._build("lw_arm", P._cube("lw_arm", 20.0))
        for x in (base, arm):
            if "error" in x:
                gate("fixture", False, x["error"])
                raise SystemExit(_finish())
        comps_spec = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [30, 0, 20]}},
        ]
        asm, _placed, err = P._place(sw, mod, comps_spec)
        if err:
            gate("fixture", False, err)
            raise SystemExit(_finish())
        asm_path = str(Path(t1._results_tmp(), f"w78_lw_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        sw.CloseAllDocuments(True)
        gate("fixture", Path(asm_path).exists(), asm_path)

        # ── Reopen from disk (components load lightweight) ────────────────
        tsw = typed(sw, "ISldWorks", module=mod)
        ro = tsw.OpenDoc6(asm_path, 2, 0, "", 0, 0)
        rdoc = ro[0] if isinstance(ro, tuple) else ro
        asm_typed = typed(rdoc, "IAssemblyDoc", module=mod)
        comps = asm_typed.GetComponents(True)
        comps = list(comps) if isinstance(comps, (list, tuple)) else [comps]
        target = comps[0]
        tname = _name2(target)

        out_dir = Path(t1._results_tmp(), f"w78_lwout_{os.getpid()}")
        out_dir.mkdir(parents=True, exist_ok=True)

        # 2. state before resolve
        before = _suppression(target, mod)
        results["log"]["suppression_before"] = before
        print(f"  suppression(before) = {before}")

        # 3. STL before resolve (in-context part-doc)
        pdoc_before = typed(target, "IComponent2", module=mod).GetModelDoc2()
        bytes_before = _export_stl(pdoc_before, f"{tname}_before", out_dir) \
            if pdoc_before is not None else -1
        results["log"]["stl_bytes_before"] = bytes_before
        gate("ghost_before_resolve", bytes_before == 0,
             f"in-context STL before resolve = {bytes_before} bytes (expect 0 ghost)")

        # 4. resolve all lightweight
        try:
            asm_typed.ResolveAllLightWeightComponents(True)
            resolve_ok = True
        except Exception as exc:  # noqa: BLE001
            resolve_ok = False
            results["log"]["resolve_error"] = repr(exc)
        gate("resolve_call", resolve_ok, "ResolveAllLightWeightComponents(True)")

        # 5. state after resolve
        after = _suppression(target, mod)
        results["log"]["suppression_after"] = after
        print(f"  suppression(after)  = {after}")
        gate("state_changed", before != after,
             f"suppression {before} -> {after}")

        # 6. STL after resolve (in-context)
        pdoc_after = typed(target, "IComponent2", module=mod).GetModelDoc2()
        bytes_incontext = _export_stl(pdoc_after, f"{tname}_incontext", out_dir) \
            if pdoc_after is not None else -1
        results["log"]["stl_bytes_incontext"] = bytes_incontext
        gate("incontext_after_resolve", bytes_incontext > 0,
             f"in-context STL after resolve = {bytes_incontext} bytes (expect >0)")

        # 7. STL after resolve (standalone open of the part file)
        part_path = resolve(pdoc_after, "GetPathName")
        so = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        sdoc = so[0] if isinstance(so, tuple) else so
        bytes_standalone = _export_stl(sdoc, f"{tname}_standalone", out_dir) \
            if sdoc is not None else -1
        results["log"]["stl_bytes_standalone"] = bytes_standalone
        gate("standalone_after_resolve", bytes_standalone > 0,
             f"standalone STL after resolve = {bytes_standalone} bytes (expect >0)")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
