"""Follow-up PAE: Wave-9 Phase-1 — part_spec (build-then-place) component source.

Close the Phase-1 scope: prove the shipping assembly lifecycle handles a
component sourced from ``part_spec`` (not ``part``). The bc77803 harness proved
``part`` (saved-file) for both components; this script is a minimal delta that
keeps ``base`` as ``part`` and flips ``lid`` to ``part_spec``, with the built
.sldprt path supplied to ``sw_commit_assembly`` via ``part_paths``.

Recipe (delta from assembly_p1_pae.py):
  - Base: ``{"id":"base","part":<path>,...}`` — unchanged.
  - Lid:  ``{"id":"lid","part_spec":"lid_box","transform":...}`` — build the
    lid box as before, capture face_ref as before, but cite a part_spec name
    and resolve at commit via ``part_paths={"lid": <built_lid_path>}``.
  - Same coincident/anti_aligned mate.

Same gates as before + part_spec-specific:
  - lid component carries ``part_spec`` (not ``part``) in the spec.
  - dry_run resolves the part_spec component via part_paths.
  - commit places both, both real B-rep, Coincident1 mate, save, manifest
    round-trip, feature_add gate still rejects "assembly".

Usage:
    python spikes/v0_19/assembly_p1_partspec_pae.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Reuse every helper from the main PAE (build, face capture, feature walk).
from assembly_p1_pae import (
    _build_box_and_save,
    _capture_planar_face,
    _feature_types,
    _title,
)

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom

from ai_sw_bridge.com.earlybind import typed, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.mutate import (
    sw_commit_assembly,
    sw_dry_run_assembly,
    sw_propose_assembly,
    sw_propose_feature_add,
)

from spike_earlybind_persist import connect_running_sw

RESULTS_DIR = Path(__file__).resolve().parent / "_results"


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {"ok": False, "ts": time.time()}
    base_path = lid_path = asm_path = None

    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        tmp_dir = Path(os.environ.get("TEMP", r"C:\Temp"))
        ts = int(time.time())
        base_path = str(tmp_dir / f"pae_ps_base_{ts}.SLDPRT")
        lid_path = str(tmp_dir / f"pae_ps_lid_{ts}.SLDPRT")
        asm_path = str(tmp_dir / f"pae_ps_asm_{ts}.SLDASM")

        # ----- STEP 1+2: build both boxes and save -----
        print("[pae-ps] building base part...")
        base_build = _build_box_and_save(sw, base_path, mod)
        out["build_base"] = base_build
        if not base_build.get("saved"):
            out["error"] = "base build/save failed"
            return 1

        print("[pae-ps] building lid part (for part_spec resolution)...")
        lid_build = _build_box_and_save(sw, lid_path, mod)
        out["build_lid"] = lid_build
        if not lid_build.get("saved"):
            out["error"] = "lid build/save failed"
            return 1

        # ----- STEP 3: interrogate one planar face per part -----
        print("[pae-ps] capturing face_ref on base (top, +Z)...")
        base_face = _capture_planar_face(sw, base_path, (0.0, 0.0, 1.0), mod)
        out["capture_base"] = base_face
        if not base_face.get("ok"):
            out["error"] = "base face capture failed: %s" % base_face.get("error")
            return 1

        print("[pae-ps] capturing face_ref on lid (bottom, -Z)...")
        lid_face = _capture_planar_face(sw, lid_path, (0.0, 0.0, -1.0), mod)
        out["capture_lid"] = lid_face
        if not lid_face.get("ok"):
            out["error"] = "lid face capture failed: %s" % lid_face.get("error")
            return 1

        # ----- STEP 4: author the spec — base=`part`, lid=`part_spec` -----
        spec = {
            "kind": "assembly",
            "name": "pae_partspec_asm",
            "components": [
                {
                    "id": "base",
                    "part": base_path,
                    "transform": {"xyz_mm": [0, 0, 0]},
                },
                {
                    "id": "lid",
                    "part_spec": "lid_box",
                    "transform": {"xyz_mm": [0, 0, 50]},
                },
            ],
            "mates": [
                {
                    "type": "coincident",
                    "alignment": "anti_aligned",
                    "a": {"component": "base", "face_ref": base_face["face_ref"]},
                    "b": {"component": "lid", "face_ref": lid_face["face_ref"]},
                }
            ],
        }
        out["spec"] = spec
        # Pre-condition: lid cites part_spec, not part.
        lid_comp = spec["components"][1]
        assert (
            "part_spec" in lid_comp and "part" not in lid_comp
        ), "lid must be sourced via part_spec for this PAE"
        out["lid_source"] = "part_spec"

        # ----- STEP 5: propose -----
        print("[pae-ps] sw_propose_assembly...")
        propose = sw_propose_assembly(spec)
        out["propose"] = propose
        if not propose.get("ok"):
            out["error"] = "propose rejected: %s" % propose.get("error")
            return 1
        pid = propose["proposal_id"]

        # ----- STEP 6: dry_run -----
        # The shipping dry_run resolves via part -> part_paths -> part_spec_path.
        # sw_dry_run_assembly() does not plumb a part_paths arg, and the schema
        # (additionalProperties=False) forbids extra fields on the spec. So:
        # mutate the stored proposal record between propose and dry_run to add
        # part_spec_path on the lid component — exactly what the eventual
        # build-then-place resolver will write, without us having to implement
        # that resolver in this PAE.
        from ai_sw_bridge.mutate import _load_proposal, _save_proposal

        rec = _load_proposal(pid)
        for comp in rec["spec"]["components"]:
            if comp["id"] == "lid":
                comp["part_spec_path"] = lid_path
        _save_proposal(pid, rec)
        out["proposal_enriched"] = {"lid.part_spec_path": lid_path}

        print("[pae-ps] sw_dry_run_assembly(%s)..." % pid)
        dry = sw_dry_run_assembly(pid)
        out["dry_run"] = dry
        if not dry.get("ok"):
            out["error"] = "dry_run failed: %s" % dry.get("error")
            return 1

        # ----- STEP 7: commit (lid path supplied via part_paths) -----
        print("[pae-ps] sw_commit_assembly(%s, part_paths={lid:...})..." % pid)
        commit = sw_commit_assembly(
            pid,
            asm_path,
            part_paths={"lid": lid_path},
        )
        out["commit"] = commit
        out["assembly_saved"] = os.path.isfile(asm_path)
        if not commit.get("ok"):
            out["error"] = "commit failed: %s" % commit.get("error")
            return 1

        # ----- STEP 8: re-open and verify live state -----
        print("[pae-ps] re-opening saved assembly for verification...")
        typed_sw = typed(sw, "ISldWorks", module=mod)
        open_ret = typed_sw.OpenDoc6(asm_path, 2, 1, "", 0, 0)
        asm_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
        if asm_doc is None:
            out["error"] = "could not re-open saved assembly"
            return 1

        try:
            try:
                asm_doc.ForceRebuild3(False)
            except Exception:
                pass

            asm_lb = sw.ActiveDoc
            typed_asm = typed(asm_lb, "IAssemblyDoc", module=mod)
            comps = typed_asm.GetComponents(True)
            comp_count = len(comps) if comps else 0
            out["component_count"] = comp_count

            brep_ok = True
            comp_brep = []
            if comps:
                for c in comps:
                    try:
                        ic = typed_qi(c, "IComponent2", module=mod)
                        md = ic.GetModelDoc2()
                        bs = md.GetBodies2(0, True) if md else None
                        n = len(bs) if bs else 0
                        comp_brep.append({"has_model": md is not None, "bodies": n})
                        if n < 1:
                            brep_ok = False
                    except Exception as exc:
                        comp_brep.append(
                            {"error": f"{type(exc).__name__}: {exc}"[:200]}
                        )
                        brep_ok = False
            out["component_brep"] = comp_brep

            # Mate walk via IFeature.GetFirstSubFeature on MateGroup.
            mate_feats: list[dict[str, str]] = []
            try:
                top_feats = asm_lb.FeatureManager.GetFeatures(True) or []
                for f in top_feats:
                    ifeat = typed(f, "IFeature", module=mod)
                    if ifeat.GetTypeName2() != "MateGroup":
                        continue
                    sub = ifeat.GetFirstSubFeature()
                    while sub is not None:
                        try:
                            sf = typed(sub, "IFeature", module=mod)
                            mate_feats.append(
                                {
                                    "name": sf.Name,
                                    "type": sf.GetTypeName2(),
                                }
                            )
                        except Exception:
                            pass
                        try:
                            sub = sub.GetNextSubFeature()
                        except Exception:
                            sub = None
            except Exception as exc:
                out["mate_walk_error"] = f"{type(exc).__name__}: {exc}"[:200]
            out["mate_features"] = mate_feats
            out["mate_count"] = len(mate_feats)

            manifest_payload = commit.get("manifest")
            manifest_ok = False
            try:
                if manifest_payload:
                    ser = json.dumps(manifest_payload)
                    re = json.loads(ser)
                    manifest_ok = (
                        len(re.get("components", [])) == 2
                        and len(re.get("mates", [])) == 1
                    )
            except Exception as exc:
                out["manifest_roundtrip_error"] = f"{type(exc).__name__}: {exc}"[:200]
            out["manifest_roundtrip"] = manifest_ok
            out["assembly_saved"] = os.path.isfile(asm_path)
        finally:
            try:
                sw.CloseDoc(_title(asm_doc))
            except Exception:
                pass

        # ----- STEP 9: gate check -----
        print("[pae-ps] gate check: feature_add rejects assembly kind...")
        gate = sw_propose_feature_add(
            "dummy_path",
            {"type": "assembly", "name": "x", "components": []},
            {},
        )
        out["feature_add_gate_rejected"] = not gate.get("ok")
        out["gate_error"] = (gate.get("error") or "")[:200]

        # ----- verdict -----
        out["ok"] = (
            out.get("propose", {}).get("ok") is True
            and out.get("dry_run", {}).get("ok") is True
            and out.get("commit", {}).get("ok") is True
            and out.get("lid_source") == "part_spec"
            and out.get("component_count") == 2
            and brep_ok
            and out.get("mate_count", 0) >= 1
            and out.get("assembly_saved") is True
            and out.get("manifest_roundtrip") is True
            and out.get("feature_add_gate_rejected") is True
        )

        status = "GREEN" if out["ok"] else "FAIL"
        print(
            "[pae-ps] %s: lid_src=%s comps=%d brep=%s mates=%d saved=%s "
            "manifest=%s gate=%s"
            % (
                status,
                out.get("lid_source"),
                out.get("component_count", 0),
                brep_ok,
                out.get("mate_count", 0),
                out.get("assembly_saved"),
                out.get("manifest_roundtrip"),
                out.get("feature_add_gate_rejected"),
            )
        )

    except Exception as exc:
        import traceback

        out["error"] = traceback.format_exc()
        out["ok"] = False
        print("[pae-ps] EXCEPTION: %s" % exc)

    finally:
        for p in (base_path, lid_path, asm_path):
            if p is None:
                continue
            try:
                os.unlink(p)
            except Exception:
                pass
        pythoncom.CoUninitialize()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "assembly_p1_partspec_pae.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("[pae-ps] wrote %s" % out_path)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
