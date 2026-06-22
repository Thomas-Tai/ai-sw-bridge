"""W78 production PAE — export_urdf through the ai-sw-urdf CLI.

Builds an ASYMMETRIC 2-component assembly and exports it to a URDF package via
the SHIPPED CLI entry (cli.urdf._run_export) on the hot seat:

  base : a 40x30x5mm plate at the origin
  arm  : a 20mm cube offset to (30, 0, 20)mm  -> a non-trivial relative pose
         and a different mass (asymmetric distribution)

Gates:
  A fixture   : assembly + parts saved to disk
  B urdf      : ok=True, <robot_name>.urdf written and well-formed XML
  C meshes    : meshes/ holds 2 non-empty .stl files
  D structure : base_link + 2 component links + 2 fixed joints
  E inertial  : both component links carry non-zero, DISTINCT masses (asymmetry)
  F placement : the arm joint (selected by child link name) places the link
                frame at placed-CoM == [0.030, 0, 0.010]m, and the world CoM
                (joint_origin + inertial CoM) lands at the AddComponent4 input
                [0.030, 0, 0.020]m. Kernel ground truth: AddComponent4 places by
                CoM (spike_component_transform_probe), so the joint origin is
                the part-origin pose, not the placement coordinate.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_urdf_pae.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
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
from ai_sw_bridge.cli.urdf import _run_export  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "urdf_pae.json"
results: dict[str, Any] = {"pae": "w78_export_urdf", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _near(v: Any, target: float, tol: float = 0.002) -> bool:
    try:
        return abs(float(v) - target) <= tol
    except (TypeError, ValueError):
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
        base = P._build("urdf_base", P._plate("urdf_base"))      # 40x30x5
        arm = P._build("urdf_arm", P._cube("urdf_arm", 20.0))    # 20mm cube
        for x in (base, arm):
            if "error" in x:
                gate("fixture", False, x["error"])
                raise SystemExit(_finish())
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [30, 0, 20]}},
        ]
        asm, placed, err = P._place(sw, mod, comps)
        if err:
            gate("fixture", False, err)
            raise SystemExit(_finish())
        asm_path = str(Path(t1._results_tmp(), f"w78_urdf_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        gate("fixture", Path(asm_path).exists(), f"asm={asm_path}")
        sw.CloseAllDocuments(True)

        out_dir = str(Path(t1._results_tmp(), f"w78_urdfout_{os.getpid()}"))
        ns = argparse.Namespace(
            assembly=asm_path, output_dir=out_dir,
            robot_name="sorter", ascii_stl=False)
        rep = _run_export(ns)
        results["report"] = rep

        urdf_path = rep.get("urdf_path")
        urdf_ok = bool(rep.get("ok")) and urdf_path and Path(urdf_path).exists()
        root = None
        if urdf_ok:
            try:
                root = ET.parse(urdf_path).getroot()
            except Exception as exc:  # noqa: BLE001
                urdf_ok = False
                rep["xml_error"] = repr(exc)
        gate("urdf", urdf_ok and root is not None and root.get("name") == "sorter",
             f"ok={rep.get('ok')} path={urdf_path} err={rep.get('error')}")
        if root is None:
            raise SystemExit(_finish())

        # ── meshes ───────────────────────────────────────────────────────
        mesh_dir = Path(rep.get("mesh_dir") or (Path(out_dir) / "meshes"))
        stls = sorted(mesh_dir.glob("*.stl"))
        gate("meshes",
             len(stls) == 2 and all(p.stat().st_size > 0 for p in stls),
             f"stls={[p.name for p in stls]} "
             f"sizes={[p.stat().st_size for p in stls]}")

        # ── structure ────────────────────────────────────────────────────
        links = root.findall("link")
        joints = root.findall("joint")
        link_names = {ln.get("name") for ln in links}
        gate("structure",
             len(links) == 3 and len(joints) == 2 and "base_link" in link_names
             and all(j.get("type") == "fixed" for j in joints),
             f"links={sorted(link_names)} joints={len(joints)}")

        # ── inertial asymmetry ───────────────────────────────────────────
        masses = {}
        for ln in links:
            mass_el = ln.find("inertial/mass")
            if mass_el is not None:
                masses[ln.get("name")] = float(mass_el.get("value"))
        vals = sorted(masses.values())
        gate("inertial",
             len(masses) == 2 and all(m > 0 for m in vals)
             and abs(vals[0] - vals[1]) > 1e-6,
             f"masses={masses}")

        # ── placement: select the ARM joint by its child link name ───────
        # Kernel ground truth (spike_component_transform_probe): AddComponent4
        # places by CoM, so the component transform — and thus the joint origin
        # (the part-origin / link-frame pose) — is (placed - CoM). The robust,
        # frame-independent invariant is that the world CoM (joint origin +
        # the inertial CoM offset) equals the AddComponent4 placement.
        arm_joint = next(
            (j for j in joints
             if "arm" in ((j.find("child") is not None
                           and j.find("child").get("link")) or "")), None)
        arm_link = next(
            (ln for ln in links if "arm" in (ln.get("name") or "")), None)
        arm_origin = com_world = None
        if arm_joint is not None and arm_link is not None:
            org = arm_joint.find("origin")
            inert_org = arm_link.find("inertial/origin")
            if org is not None and inert_org is not None:
                arm_origin = [float(v) for v in org.get("xyz").split()]
                com = [float(v) for v in inert_org.get("xyz").split()]
                com_world = [arm_origin[i] + com[i] for i in range(3)]
        gate("placement",
             arm_origin is not None
             # link-frame pose == placed - CoM == [0.030, 0, 0.010]
             and _near(arm_origin[0], 0.030) and _near(arm_origin[1], 0.0)
             and _near(arm_origin[2], 0.010)
             # physical invariant: the CoM lands at the AddComponent4 placement
             and com_world is not None and _near(com_world[0], 0.030)
             and _near(com_world[1], 0.0) and _near(com_world[2], 0.020),
             f"arm_joint_origin_m={arm_origin} (expect [0.030,0,0.010]); "
             f"world_CoM={com_world} (expect [0.030,0,0.020])")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
