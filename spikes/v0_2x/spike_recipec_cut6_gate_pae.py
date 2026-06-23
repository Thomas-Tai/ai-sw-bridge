"""Recipe-C cut #6 gate — sweep family migrated mutate.py -> features/sweep.py
(the FINAL extraction; the monolith's last feature handlers).

Proves sweep / sweep_cut + the sketch-coordinate core now live in
features/sweep.py and route through the HANDLER_REGISTRY, and that the disk-
transaction path (which opens docs TYPED via _open_doc_typed) drives the
bare-None-on-typed SelectByID2 selections + the auto-pierce anchor flawlessly.

  A registry_seam   : HANDLER_REGISTRY advertises sweep + sweep_cut (GREEN);
                      features.sweep exposes the 9 relocated symbols; mutate NO
                      LONGER defines them; _SUPPORTED_FEATURE_TYPES == () (every
                      kind now lives in the registry); _apply_feature is a pure
                      registry lookup (no inline branches).
  B sweep_lifecycle : on a seed with an OFFSET circle profile + a path on a
                      different plane, propose(auto_pierce=True) -> dry_run ->
                      commit a sweep materializes (commit ok=True) — auto-pierce
                      anchors the offset profile to the path — and a solid body
                      (bodies>=1, vol>0) survives reopen. Routed through the
                      registry, driven through the TYPED transaction doc.
  C sweep_cut_lifecycle : on a seed box (solid) + a centered circle profile + a
                      path piercing the box, propose -> dry_run -> commit a
                      sweep_cut materializes and the body volume DROPS on reopen
                      (a through-tunnel removed material). sweep_cut does NOT
                      auto-pierce (only _create_sweep does), so the profile sits
                      on the path.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_recipec_cut6_gate_pae.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_PROPOSALS = _HERE.parent / "_results" / "recipec6_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
import ai_sw_bridge.features.sweep as sweep_mod  # noqa: E402,F401
import ai_sw_bridge.mutate as mutate_mod  # noqa: E402

_OUT = _HERE.parent / "_results" / "recipec6_gate_pae.json"
_WORK = _HERE.parent / "_results" / "recipec6_work"
results: dict[str, Any] = {"pae": "recipec6_sweep_family_migration_gate", "gates": {}}

_MOVED = ("_SW_FM_SWEEP", "_SW_FM_SWEEP_CUT", "_PIERCE_TOKEN",
          "_first_arc_center_coords", "_sketch_centroid_coords",
          "_sketch_to_model_coords", "_apply_auto_pierce",
          "_create_sweep", "_create_sweep_cut")


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _name_last_sketch(doc: Any, mod: Any, newname: str) -> str | None:
    last = None
    for f in doc.FeatureManager.GetFeatures(True) or []:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                last = tf
        except Exception:
            continue
    if last is None:
        return None
    try:
        last.Name = newname
        return newname
    except Exception:
        try:
            return last.Name
        except Exception:
            return None


def _body_stats(path: str) -> tuple[int, float]:
    """Reopen *path* standalone; return (solid_body_count, total_volume_mm3)."""
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    raw = sw.OpenDoc6(path, 1, 0, "", errs, warns)
    if raw is None:
        return -1, -1.0
    mod = wrapper_module()
    try:
        pdoc = typed_qi(raw, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(0, True)
        nb = len(bodies) if bodies else 0
        vol = 0.0
        for b in bodies or ():
            try:
                mp = b.GetMassProperties(1.0)
                if mp and len(mp) > 3:
                    vol += float(mp[3]) * 1e9
            except Exception:
                pass
        return nb, round(vol, 1)
    except Exception:
        return -1, -1.0
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _build_sweep_seed(sw: Any, path: str) -> tuple[str, str] | None:
    """Offset circle profile (Front) + path line (Top) — NO base solid.
    Returns (profile_name, path_name)."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return None
    doc = typed(raw, "IModelDoc2", module=mod)
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    # Path: Top Plane line along part-Z (pierces Front at z=0).
    if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    path_name = _name_last_sketch(doc, mod, "PathSk")
    # Profile: circle on Front Plane OFFSET to (20,0) — auto-pierce must anchor it.
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateCircle(0.020, 0.0, 0.0, 0.025, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    prof_name = _name_last_sketch(doc, mod, "ProfSk")
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    if not (path_name and prof_name):
        return None
    return prof_name, path_name


def _build_sweep_cut_seed(sw: Any, path: str) -> tuple[str, str] | None:
    """Box solid (40x40x40) + centered circle profile (Front) + path (Top)
    piercing the box. Returns (profile_name, path_name)."""
    mod = wrapper_module()
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    if raw is None:
        return None
    doc = typed(raw, "IModelDoc2", module=mod)
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    fm = doc.FeatureManager
    # Box: Front Plane 40x40 rect, extrude 40mm in +Z (z 0..40).
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
    sm.InsertSketch(True)
    fm.FeatureExtrusion3(True, False, False, 0, 0, 0.04, 0.0,
                         False, False, False, False, 0.0, 0.0,
                         False, False, False, False, True, True, True, 0.0, 0.0, False)
    doc.ClearSelection2(True)
    # Path: Top Plane line along part-Z from z=-5..60 (through the box).
    if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    path_name = _name_last_sketch(doc, mod, "CutPathSk")
    # Profile: circle on Front Plane CENTERED at origin (ON the path; r=5mm).
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    prof_name = _name_last_sketch(doc, mod, "CutProfSk")
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    if not (path_name and prof_name):
        return None
    return prof_name, path_name


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        # ── A: structural — the final cut happened ──
        registered = ("sweep" in HANDLER_REGISTRY) and ("sweep_cut" in HANDLER_REGISTRY)
        in_sweep_mod = all(hasattr(sweep_mod, n) for n in _MOVED)
        gone_from_mutate = not any(hasattr(mutate_mod, n) for n in _MOVED)
        supported_empty = tuple(mutate_mod._SUPPORTED_FEATURE_TYPES) == ()
        # pure registry dispatch: a fake registry kind routes; no inline branch
        pure_registry = True
        try:
            import ai_sw_bridge.features as _feat
            sentinel = {"called": False}
            _feat.HANDLER_REGISTRY["__probe6__"] = lambda d, f, t: (sentinel.update(called=True) or (True, "reg"))
            r = mutate_mod._apply_feature("DOC", {"type": "__probe6__"}, {})
            pure_registry = (r == (True, "reg")) and sentinel["called"]
            del _feat.HANDLER_REGISTRY["__probe6__"]
        except Exception as exc:  # noqa: BLE001
            pure_registry = False
            results["pure_registry_probe_exc"] = repr(exc)
        gate("registry_seam",
             registered and in_sweep_mod and gone_from_mutate and supported_empty
             and pure_registry,
             f"sweep+sweep_cut_GREEN={registered} in_features_sweep={in_sweep_mod} "
             f"removed_from_mutate={gone_from_mutate} _SUPPORTED_empty={supported_empty} "
             f"pure_registry_dispatch={pure_registry}")

        client = SolidWorksClient()

        # ── B: sweep (additive) full lifecycle + auto-pierce ──
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        sweep_seed = str(_WORK / "recipec6_sweep_seed.SLDPRT")
        names = _build_sweep_seed(sw, sweep_seed)
        if not names:
            gate("sweep_lifecycle", False, "sweep seed build/naming failed")
        else:
            prof, pth = names
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
            prop = client.mutate.propose_feature_add(
                sweep_seed, {"type": "sweep", "auto_pierce": True},
                {"profile": prof, "path": pth})
            pid = prop.get("proposal_id")
            results["sweep_propose"] = prop
            if not pid:
                gate("sweep_lifecycle", False, f"propose failed: {prop.get('error')}")
            else:
                dry = client.mutate.dry_run_feature_add(pid)
                com = client.mutate.commit_feature_add(pid)
                results["sweep_dry_run"], results["sweep_commit"] = dry, com
                nb, vol = _body_stats(sweep_seed)
                results["sweep_bodies"], results["sweep_vol_mm3"] = nb, vol
                gate("sweep_lifecycle",
                     bool(prop.get("ok")) and bool(dry.get("ok")) and bool(com.get("ok"))
                     and nb >= 1 and vol > 0,
                     f"propose={prop.get('ok')} dry_run={dry.get('ok')} "
                     f"commit={com.get('ok')} bodies={nb} vol_mm3={vol} "
                     f"(auto-pierce anchored the offset profile; routed via registry) "
                     f"err={com.get('error') or dry.get('error')}")

        # ── C: sweep_cut full lifecycle (volume drops) ──
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        cut_seed = str(_WORK / "recipec6_sweepcut_seed.SLDPRT")
        cnames = _build_sweep_cut_seed(sw, cut_seed)
        if not cnames:
            gate("sweep_cut_lifecycle", False, "sweep_cut seed build/naming failed")
        else:
            cprof, cpth = cnames
            nb0, vol0 = _body_stats(cut_seed)  # box-only baseline
            results["sweepcut_box_bodies"], results["sweepcut_box_vol_mm3"] = nb0, vol0
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
            prop = client.mutate.propose_feature_add(
                cut_seed, {"type": "sweep_cut"}, {"profile": cprof, "path": cpth})
            pid = prop.get("proposal_id")
            results["sweepcut_propose"] = prop
            if not pid:
                gate("sweep_cut_lifecycle", False, f"propose failed: {prop.get('error')}")
            else:
                dry = client.mutate.dry_run_feature_add(pid)
                com = client.mutate.commit_feature_add(pid)
                results["sweepcut_dry_run"], results["sweepcut_commit"] = dry, com
                nb1, vol1 = _body_stats(cut_seed)
                results["sweepcut_after_bodies"], results["sweepcut_after_vol_mm3"] = nb1, vol1
                gate("sweep_cut_lifecycle",
                     bool(prop.get("ok")) and bool(dry.get("ok")) and bool(com.get("ok"))
                     and nb1 >= 1 and vol0 > 0 and vol1 < vol0,
                     f"propose={prop.get('ok')} dry_run={dry.get('ok')} "
                     f"commit={com.get('ok')} vol {vol0} -> {vol1} mm3 "
                     f"(through-tunnel removed material; routed via registry) "
                     f"err={com.get('error') or dry.get('error')}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
