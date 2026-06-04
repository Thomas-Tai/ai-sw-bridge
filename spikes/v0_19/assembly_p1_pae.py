"""PAE: Wave-9 Phase-1 assembly — production lifecycle, live SW 2024 SP1 seat.

Proves the SHIPPING assembly lifecycle (sw_propose_assembly -> sw_dry_run_assembly
-> sw_commit_assembly) materializes a real 2-component, 1-coincident-mate
assembly end-to-end through the declarative path.

Recipe:
  1. Build + SaveAs3 a box part (component "base", referenced by `part` path).
  2. Build + SaveAs3 a second box part (component "lid", referenced via
     `part_spec_path` — the build-then-place resolved path).
  3. For each part: re-open, interrogate one planar face via the production
     interrogator's `_probe_face(capture=True, doc=part_doc)`, and read the
     resulting BrepFace → manifest face_ref dict.
  4. Author an assembly spec: 2 components + 1 coincident mate.
  5. sw_propose_assembly(spec) -> ok + proposal_id.
  6. sw_dry_run_assembly(pid) -> ok.
  7. sw_commit_assembly(pid, output_path, part_paths=...) -> ok.
  8. Verify: component count == 2 with real B-rep, a Coincident mate feature
     materialized, assembly saved to disk, manifest round-trips.
  9. Gate: sw_propose_feature_add(doc, {"type":"assembly",...}, {}) rejected.
  10. Write _results/assembly_p1_pae.json.

Usage:
    python spikes/v0_19/assembly_p1_pae.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom

from ai_sw_bridge.brep.interrogator import _probe_face
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.mutate import (
    sw_commit_assembly,
    sw_dry_run_assembly,
    sw_propose_assembly,
    sw_propose_feature_add,
)

from spike_earlybind_persist import connect_running_sw

RESULTS_DIR = Path(__file__).resolve().parent / "_results"

SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box_and_save(sw: Any, part_path: str, mod: Any) -> dict[str, Any]:
    """Build a 50mm x 50mm x 50mm box and SaveAs3 to part_path."""
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        out["error"] = "NewDocument None"
        return out

    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True, False, False, 0, 0, 0.05, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    doc.ClearSelection2(True)
    doc.SaveAs3(part_path, 0, 2)
    out["saved"] = os.path.isfile(part_path)
    out["path"] = part_path
    t = _title(doc)
    sw.CloseDoc(t)
    return out


def _capture_planar_face(sw: Any, part_path: str, target_normal: tuple, mod: Any) -> dict:
    """Open a saved part, find the planar face whose normal best matches
    target_normal, return a manifest face_ref dict for it.

    Captures via the production interrogator (_probe_face with capture=True)
    to get the same shape the single-part wizard_hole/durability path produces.
    """
    typed_sw = typed(sw, "ISldWorks", module=mod)
    open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
    if part_doc is None:
        return {"error": "OpenDoc6 None"}

    try:
        try:
            part_doc.ForceRebuild3(False)
        except Exception:
            pass

        bodies = part_doc.GetBodies2(0, True)
        if not bodies:
            return {"error": "no bodies"}
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
        faces = body.GetFaces()
        if not faces:
            return {"error": "no faces"}

        best = None
        best_score = float("inf")
        for face in faces:
            bf = _probe_face(face, body_id=0, face_idx=0, doc=part_doc, capture=True)
            if bf is None or bf.normal_vec is None:
                continue
            dot = sum(a * b for a, b in zip(target_normal, bf.normal_vec))
            score = 1.0 - abs(dot)
            if score < best_score:
                best_score = score
                best = bf

        if best is None:
            return {"error": "no planar face captured"}

        face_ref: dict[str, Any] = {
            "normal": list(best.normal_vec),
            "centroid": list(best.centroid) if best.centroid else None,
            "area_mm2": best.area_mm2,
        }
        if best.persist_id:
            face_ref["persist_id"] = best.persist_id
        return {"ok": True, "face_ref": face_ref, "score": best_score}
    finally:
        sw.CloseDoc(_title(part_doc))


def _feature_types(doc: Any, mod: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {"ok": False, "ts": time.time()}
    base_path = lid_path = asm_path = None

    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        tmp_dir = Path(os.environ.get("TEMP", r"C:\Temp"))
        ts = int(time.time())
        base_path = str(tmp_dir / f"pae_base_{ts}.SLDPRT")
        lid_path = str(tmp_dir / f"pae_lid_{ts}.SLDPRT")
        asm_path = str(tmp_dir / f"pae_asm_{ts}.SLDASM")

        # ----- STEP 1+2: build two box parts -----
        print("[pae] building base part...")
        base_build = _build_box_and_save(sw, base_path, mod)
        out["build_base"] = base_build
        if not base_build.get("saved"):
            out["error"] = "base build/save failed"
            print("[pae] FAIL: %s" % out["error"])
            return 1

        print("[pae] building lid part...")
        lid_build = _build_box_and_save(sw, lid_path, mod)
        out["build_lid"] = lid_build
        if not lid_build.get("saved"):
            out["error"] = "lid build/save failed"
            print("[pae] FAIL: %s" % out["error"])
            return 1

        # ----- STEP 3: interrogate one planar face per part -----
        # Base: capture the top face (normal ~ +Z). Lid: capture the bottom face
        # (normal ~ -Z). These become coincident when lid is translated +50mm.
        print("[pae] capturing face_ref on base (top, +Z)...")
        base_face = _capture_planar_face(sw, base_path, (0.0, 0.0, 1.0), mod)
        out["capture_base"] = base_face
        if not base_face.get("ok"):
            out["error"] = "base face capture failed: %s" % base_face.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        print("[pae] capturing face_ref on lid (bottom, -Z)...")
        lid_face = _capture_planar_face(sw, lid_path, (0.0, 0.0, -1.0), mod)
        out["capture_lid"] = lid_face
        if not lid_face.get("ok"):
            out["error"] = "lid face capture failed: %s" % lid_face.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        # ----- STEP 4: author the assembly spec -----
        spec = {
            "kind": "assembly",
            "name": "pae_asm",
            "components": [
                {
                    "id": "base",
                    "part": base_path,
                    "transform": {"xyz_mm": [0, 0, 0]},
                },
                {
                    "id": "lid",
                    "part_spec": "lid.aisw.json",
                    "part_spec_path": lid_path,
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

        # ----- STEP 5: propose -----
        print("[pae] sw_propose_assembly...")
        propose = sw_propose_assembly(spec)
        out["propose"] = propose
        if not propose.get("ok"):
            out["error"] = "propose rejected: %s" % propose.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1
        pid = propose["proposal_id"]

        # ----- STEP 6: dry_run -----
        print("[pae] sw_dry_run_assembly(%s)..." % pid)
        dry = sw_dry_run_assembly(pid)
        out["dry_run"] = dry
        if not dry.get("ok"):
            out["error"] = "dry_run failed: %s" % dry.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        # ----- STEP 7: commit -----
        print("[pae] sw_commit_assembly(%s)..." % pid)
        commit = sw_commit_assembly(
            pid, asm_path, part_paths={"lid": lid_path},
        )
        out["commit"] = commit
        out["assembly_saved"] = os.path.isfile(asm_path)
        if not commit.get("ok"):
            out["error"] = "commit failed: %s" % commit.get("error")
            print("[pae] FAIL: %s" % out["error"])
            return 1

        # ----- STEP 8: verify live state -----
        # Re-open the saved assembly to inspect it.
        print("[pae] re-opening saved assembly for verification...")
        typed_sw = typed(sw, "ISldWorks", module=mod)
        open_ret = typed_sw.OpenDoc6(asm_path, 2, 1, "", 0, 0)  # 2 = assembly
        asm_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
        if asm_doc is None:
            out["error"] = "could not re-open saved assembly"
            print("[pae] FAIL: %s" % out["error"])
            return 1

        try:
            typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
            comps = typed_asm.GetComponents(True)
            comp_count = len(comps) if comps else 0
            out["component_count"] = comp_count

            # B-rep on each component
            brep_ok = True
            comp_brep = []
            if comps:
                for c in comps:
                    try:
                        md = c.GetModelDoc2()
                        bs = md.GetBodies2(0, True) if md else None
                        n = len(bs) if bs else 0
                        comp_brep.append({"has_model": md is not None, "bodies": n})
                        if n < 1:
                            brep_ok = False
                    except Exception as exc:
                        comp_brep.append({"error": f"{type(exc).__name__}: {exc}"[:200]})
                        brep_ok = False
            out["component_brep"] = comp_brep

            # Mate feature
            feats = _feature_types(asm_doc, mod)
            mate_feats = [
                f for f in feats
                if "Mate" in f.get("type", "") and f.get("type") != "MateGroup"
            ]
            out["mate_features"] = mate_feats
            out["mate_count"] = len(mate_feats)

            # Manifest round-trip
            manifest_path = asm_path + ".manifest.json"
            manifest_ok = False
            manifest_payload = None
            # The lifecycle stores the manifest in the commit result; round-trip
            # it through serialize/parse to verify shape.
            try:
                manifest_payload = commit.get("manifest")
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

            # SaveAs3 + manifest verified
            out["assembly_saved"] = os.path.isfile(asm_path)
        finally:
            try:
                sw.CloseDoc(_title(asm_doc))
            except Exception:
                pass

        # ----- STEP 9: gate check -----
        print("[pae] gate check: feature_add rejects assembly kind...")
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
            and out.get("component_count") == 2
            and brep_ok
            and out.get("mate_count", 0) >= 1
            and out.get("assembly_saved") is True
            and out.get("manifest_roundtrip") is True
            and out.get("feature_add_gate_rejected") is True
        )

        status = "GREEN" if out["ok"] else "FAIL"
        print(
            "[pae] %s: comps=%d brep=%s mates=%d saved=%s manifest=%s gate=%s"
            % (
                status,
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
        print("[pae] EXCEPTION: %s" % exc)

    finally:
        # Cleanup temp files (best-effort)
        for p in (base_path, lid_path, asm_path):
            if p is None:
                continue
            try:
                os.unlink(p)
            except Exception:
                pass
        pythoncom.CoUninitialize()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "assembly_p1_pae.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("[pae] wrote %s" % out_path)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
