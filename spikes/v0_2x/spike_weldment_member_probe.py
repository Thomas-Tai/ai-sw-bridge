"""W73 Weldment Structural Member PROBE — boundary-law two-tier crucible.

Tests whether `IFeatureManager.InsertStructuralWeldment5` materializes real frame
geometry out-of-process, and where (if anywhere) the corner intersection-solve
hits the Parasolid traversal/solve wall.

  Phase 2 (base members): sweep a library profile along an explicit 3D-sketch
    L-path with the MINIMAL connected-segment cut. Prediction: MATERIALIZE
    (explicit-path sweep = closed-form, like the shipped `sweep` lane).
  Phase 3 (corner solve): re-fire with the heavier coped cut + corner treatment
    + miter-merge (fuses members by solving the member-member intersection).
    Prediction (the crucible): does the intersection solve ghost (ret=None) or
    does it materialize OOP?

Recipe (seat-cracked):
  * Path arg = FULL .sldlfp path; ConfigurationName = a size config inside it
    (square tube.sldlfp -> '20 x 20 x 2').
  * swConnectedSegmentsOption_e: SimpleCut=1, CopedCut=2 (there is NO 0 — connected
    segments MUST be cut; passing 0 ghosts the whole feature — the W73 footgun).
  * Group: `fm.CreateStructuralMemberGroup()`; assign segments via the `Segments`
    PROPERTY (= VARIANT(VT_ARRAY|VT_DISPATCH, segs)) — the `ISetSegments` method
    raises 'Python instance can not be converted to a COM object'.
  * Groups arg to InsertStructuralWeldment5 = VARIANT(VT_ARRAY|VT_DISPATCH, [grp]).
  * Path sketch feature re-typed to IFeature before GetSpecificFeature2 (the
    FirstFeature-walk lesson); ISketch.GetSketchSegments -> the path segments.

Witness: ret is a real Feature AND ΔVol > 0 (frame geometry is mass-bearing).
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
    / "spikes" / "v0_2x" / "_results" / "weldment_member_probe.json"
)
PROFILE = (
    r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
    r"\data\weldment profiles\iso\square tube.sldlfp"
)
CONFIG = "20 x 20 x 2"

results: dict[str, Any] = {
    "probe": "w73_weldment_structural_member",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "profile": PROFILE,
    "config": CONFIG,
    "gates": {},
    "variants": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def run() -> str:
    import pythoncom as pc
    import win32com.client as w32
    from win32com.client import VARIANT

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.features import verify
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()

    if not os.path.isfile(PROFILE):
        return gate("profile_present", False, f"missing {PROFILE}") and "WALL" or "WALL"
    gate("profile_present", True, PROFILE)

    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tsw = typed(sw, "ISldWorks", module=mod)

    def fire(label: str, connected_opt: int, apply_corner: bool,
             corner_type: int | None = None, miter: bool | None = None) -> dict:
        tmp = tempfile.mkdtemp(prefix="w73_")
        part = os.path.join(tmp, "W73.SLDPRT")
        spec = {
            "schema_version": 1, "name": "W73",
            "features": [
                {"type": "sketch_3d_sketch", "name": "PATH", "points": [
                    {"x": 0.0, "y": 0.0, "z": 0.0},
                    {"x": 100.0, "y": 0.0, "z": 0.0},
                    {"x": 100.0, "y": 100.0, "z": 0.0}]},
            ],
        }
        r = part_build(spec, save_as=part, save_format="current", no_dim=True)
        ok = getattr(r, "ok", None)
        if ok is None and isinstance(r, dict):
            ok = r.get("ok")
        if not (ok and os.path.isfile(part)):
            return {"label": label, "error": "part build failed"}
        ret = tsw.OpenDoc6(part, 1, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        mdoc2 = typed(doc, "IModelDoc2", module=mod)
        sk_feat = typed_qi(doc.FeatureByPositionReverse(0), "IFeature", module=mod)
        sketch = typed_qi(sk_feat.GetSpecificFeature2(), "ISketch", module=mod)
        segs = list(sketch.GetSketchSegments())
        fm = typed_qi(mdoc2.FeatureManager, "IFeatureManager", module=mod)
        grp = fm.CreateStructuralMemberGroup()
        grp.Segments = VARIANT(pc.VT_ARRAY | pc.VT_DISPATCH, segs)
        grp.ApplyCornerTreatment = apply_corner
        if corner_type is not None:
            try:
                grp.CornerTreatmentType = corner_type
            except Exception:
                pass
        if miter is not None:
            try:
                grp.MiterMergeCondition = miter
            except Exception:
                pass
        vol_before = verify.solid_volume_mm3(doc)
        feat = None
        err = None
        try:
            feat = fm.InsertStructuralWeldment5(
                PROFILE, connected_opt, True,
                VARIANT(pc.VT_ARRAY | pc.VT_DISPATCH, [grp]), CONFIG)
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
        try:
            mdoc2.EditRebuild3()
        except Exception:
            pass
        vol_after = verify.solid_volume_mm3(doc)
        bods = verify.bodies(doc, 0, False)
        rec = {
            "label": label, "connected_opt": connected_opt,
            "apply_corner": apply_corner, "corner_type": corner_type,
            "miter": miter,
            "ret_is_feature": feat is not None and not isinstance(feat, int),
            "delta_vol_mm3": round(vol_after - vol_before, 3),
            "bodies": len(bods) if bods else 0,
            "error": err,
        }
        results["variants"][label] = rec
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        return rec

    def materialized(rec: dict) -> bool:
        return rec.get("ret_is_feature") and rec.get("delta_vol_mm3", 0) > 0

    # ---- Phase 2: base members (minimal simple cut) ----
    p2 = fire("phase2_simple_cut", 1, False)
    gate("P2_base_members_materialize", materialized(p2),
         f"ret_feat={p2.get('ret_is_feature')} dVol={p2.get('delta_vol_mm3')} "
         f"bodies={p2.get('bodies')}")

    # ---- Phase 3: heavier corner intersection solves ----
    coped = fire("phase3_coped_cut", 2, False)
    gate("P3_coped_cut_materialize", materialized(coped),
         f"dVol={coped.get('delta_vol_mm3')} bodies={coped.get('bodies')}")

    ct0 = fire("phase3_corner_treat_0", 1, True, corner_type=0)
    gate("P3_corner_treatment_materialize", materialized(ct0),
         f"dVol={ct0.get('delta_vol_mm3')} bodies={ct0.get('bodies')}")

    miter = fire("phase3_miter_merge", 1, True, corner_type=0, miter=True)
    # miter-merge FUSES the two members -> expect 1 body (the intersection solve)
    gate("P3_miter_merge_materialize",
         materialized(miter),
         f"dVol={miter.get('delta_vol_mm3')} bodies={miter.get('bodies')} "
         f"(fuse 2->1 = {miter.get('bodies') == 1})")

    all_pass = all(g["ok"] for g in results["gates"].values())
    gate("OVERALL", all_pass,
         f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
         f"{len(results['gates'])}")
    return "GREEN" if all_pass else "PARTIAL"


def main() -> int:
    import pythoncom
    pythoncom.CoInitialize()
    try:
        verdict = run()
    except Exception as exc:
        import traceback
        results["gates"]["UNEXPECTED"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
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
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {verdict}  (wrote {RESULTS_PATH})")
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
