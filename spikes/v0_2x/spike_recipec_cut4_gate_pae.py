"""Recipe-C cut #4 gate — dress-up + advanced-shapes + flanges families
migrated mutate.py -> features/.

This is the bulk consolidated cut. 12 handlers + the edge_flange island
evacuate mutate.py into three new feature modules; disposition is PER-FEATURE
(Option A — a structural boundary port relocates code, it grants walls NO
behaviour amnesty):

  * 8 GREEN (advertised through HANDLER_REGISTRY, were in HEAD
    _SUPPORTED_FEATURE_TYPES): fillet_constant_radius / chamfer /
    variable_radius_fillet / shell / draft  (dress_up); dome / wizard_hole
    (advanced_shapes); base_flange (flanges).
  * 5 DORMANT (evacuated for provenance, NEVER advertised, propose still
    fail-closes exactly as at HEAD): loft / rib / wrap (WALLED — documented
    permanent kernel walls) + boundary_boss (DORMANT — propose-walled at
    HEAD, never seat-proven) (advanced_shapes); edge_flange (DORMANT — W42
    ghost) (flanges).

  A registry_seam   : HANDLER_REGISTRY advertises the 8 GREEN kinds and does
                      NOT advertise the 5 walls; the 3 new modules expose their
                      _create_* fns; mutate NO LONGER defines any of the 13
                      handlers (the physical move + the dispatch cut); the 8
                      GREEN kinds left _SUPPORTED_FEATURE_TYPES (only sweep /
                      sweep_cut remain).
  B fillet_lifecycle : on a box seed with a captured durable edge_ref, propose
                      -> dry_run -> commit a fillet_constant_radius materializes
                      (commit ok=True) and a 'Fillet' node appears on reopen
                      — the edge-driven GREEN archetype routed through the
                      registry.
  C dome_lifecycle   : on a box seed with a captured durable face_ref (the
                      coordinate-face path walls OOP — see _create_dome
                      docstring), propose -> dry_run -> commit a dome
                      materializes and a 'Dome' node appears on reopen — the
                      advanced-shape GREEN archetype routed through the registry.
  D wrap_fail_closed       : propose wrap -> rejected ("unsupported feature
                      type") — the documented kernel wall stays walled after the
                      cut (WALLED registry status, never advertised).
  E edge_flange_fail_closed: propose edge_flange -> rejected, same (DORMANT).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_recipec_cut4_gate_pae.py
"""

from __future__ import annotations

import base64
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

_PROPOSALS = _HERE.parent / "_results" / "recipec4_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id  # noqa: E402
import ai_sw_bridge.features.advanced_shapes as adv  # noqa: E402,F401
import ai_sw_bridge.features.dress_up as du  # noqa: E402,F401
import ai_sw_bridge.features.flanges as fl  # noqa: E402,F401
import ai_sw_bridge.mutate as mutate_mod  # noqa: E402

_OUT = _HERE.parent / "_results" / "recipec4_gate_pae.json"
_WORK = _HERE.parent / "_results" / "recipec4_work"
results: dict[str, Any] = {
    "pae": "recipec4_dressup_advshapes_flanges_migration_gate",
    "gates": {},
}

_GREEN_KINDS = (
    "fillet_constant_radius",
    "chamfer",
    "variable_radius_fillet",
    "shell",
    "draft",
    "dome",
    "wizard_hole",
    "base_flange",
)
_WALL_KINDS = ("loft", "rib", "wrap", "boundary_boss", "edge_flange")
_MOVED_HANDLERS = (
    "_create_fillet",
    "_create_chamfer",
    "_create_variable_fillet",
    "_create_shell",
    "_create_draft",
    "_create_loft",
    "_create_rib",
    "_create_dome",
    "_create_wrap",
    "_create_boundary_boss",
    "_create_wizard_hole",
    "_create_base_flange",
    "_create_edge_flange",
)

# 20x20x10 mm box centred on origin, extruded +Z from Front Plane.
BOX_HW_M = 0.01  # half-width / half-height
BOX_D_M = 0.01  # depth (Z)


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _b64(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _build_box(sw: Any, path: str) -> Any:
    """A 20x20x10 box on Front Plane; returns the live doc (or None)."""
    template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return None
    fm = doc.FeatureManager
    sm = doc.SketchManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-BOX_HW_M, -BOX_HW_M, 0, BOX_HW_M, BOX_HW_M, 0)
    sm.InsertSketch(True)
    f = fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0.0,
        0.0,
        False,
    )
    if f:
        try:
            f.Name = "Box_Seed"
        except Exception:
            pass
    doc.ForceRebuild3(False)
    return doc


def _capture_edge_ref(sw: Any, path: str) -> dict | None:
    """Box + durable edge_ref for the top +X edge (midpoint), saved to *path*."""
    doc = _build_box(sw, path)
    if doc is None:
        return None
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        if not ext.SelectByID2("", "EDGE", BOX_HW_M, 0.0, BOX_D_M, False, 0, None, 0):
            return None
        edge = doc.SelectionManager.GetSelectedObject6(1, -1)
        pid = capture_persist_id(doc, edge)
        try:
            p = edge.GetCurveParams2()
            start = (p[7], p[8], p[9])
            end = (p[10], p[11], p[12])
            length = float(p[1]) - float(p[0])
        except Exception:
            start = (BOX_HW_M, -BOX_HW_M, BOX_D_M)
            end = (BOX_HW_M, BOX_HW_M, BOX_D_M)
            length = 2 * BOX_HW_M
        doc.ClearSelection2(True)
        doc.SaveAs3(path, 0, 0)
        return {
            "persist_id": _b64(pid),
            "start": list(start),
            "end": list(end),
            "length": length,
        }
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _capture_face_ref(sw: Any, path: str) -> dict | None:
    """Box + durable manifest face_ref for the top (+Z) face, saved to *path*."""
    doc = _build_box(sw, path)
    if doc is None:
        return None
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        if not ext.SelectByID2("", "FACE", 0.0, 0.0, BOX_D_M, False, 0, None, 0):
            return None
        face = doc.SelectionManager.GetSelectedObject6(1, -1)
        pid = capture_persist_id(doc, face)
        doc.ClearSelection2(True)
        doc.SaveAs3(path, 0, 0)
        return {
            "persist_id": _b64(pid),
            "normal": [0.0, 0.0, 1.0],
            "centroid": [0.0, 0.0, BOX_D_M],
            "area_mm2": (2 * BOX_HW_M * 1000.0) ** 2,  # 20mm x 20mm = 400
            "role_hint": "+z_top",
        }
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _node_type_present(sw: Any, path: str, token: str) -> bool:
    """Reopen *path* standalone; True if any feature node's type-name contains
    *token* (case-insensitive)."""
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(path, 1, 0, "", errs, warns)  # swDocPART=1
    if doc is None:
        return False
    try:
        for fnode in doc.FeatureManager.GetFeatures(False) or []:
            for attr in ("GetTypeName2", "GetTypeName"):
                try:
                    v = getattr(fnode, attr)
                    tn = str(v() if callable(v) else v)
                    if token.lower() in tn.lower():
                        return True
                    break
                except Exception:
                    continue
        return False
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


def _lifecycle(
    client: Any,
    sw: Any,
    name: str,
    seed: str,
    feature: dict,
    target: dict,
    node_token: str,
) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    prop = client.mutate.propose_feature_add(seed, feature, target)
    pid = prop.get("proposal_id")
    results[f"{name}_propose"] = prop
    if not pid:
        gate(f"{name}_lifecycle", False, f"propose failed: {prop.get('error')}")
        return
    dry = client.mutate.dry_run_feature_add(pid)
    com = client.mutate.commit_feature_add(pid)
    results[f"{name}_dry_run"] = dry
    results[f"{name}_commit"] = com
    node_ok = _node_type_present(sw, seed, node_token)
    lifecycle_ok = bool(prop.get("ok")) and bool(dry.get("ok")) and bool(com.get("ok"))
    gate(
        f"{name}_lifecycle",
        lifecycle_ok and node_ok,
        f"propose={prop.get('ok')} dry_run={dry.get('ok')} commit={com.get('ok')} "
        f"'{node_token}'_node={node_ok} (routed through HANDLER_REGISTRY) "
        f"err={com.get('error') or dry.get('error')}",
    )


def _fail_closed(
    client: Any, sw: Any, name: str, seed: str, feature: dict, target: dict
) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    r = client.mutate.propose_feature_add(seed, feature, target)
    results[f"{name}_propose"] = r
    gate(
        f"{name}_fail_closed",
        (not r.get("ok")) and ("unsupported" in str(r.get("error", "")).lower()),
        f"ok={r.get('ok')} error={r.get('error')!r}",
    )


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
        # ── A: structural — the cut happened; 8 GREEN advertised, 5 walls not ──
        green_advertised = all(k in HANDLER_REGISTRY for k in _GREEN_KINDS)
        walls_dormant = not any(k in HANDLER_REGISTRY for k in _WALL_KINDS)
        in_modules = (
            all(
                hasattr(du, n)
                for n in (
                    "_create_fillet",
                    "_create_chamfer",
                    "_create_variable_fillet",
                    "_create_shell",
                    "_create_draft",
                )
            )
            and all(
                hasattr(adv, n)
                for n in (
                    "_create_loft",
                    "_create_rib",
                    "_create_dome",
                    "_create_wrap",
                    "_create_boundary_boss",
                    "_create_wizard_hole",
                )
            )
            and all(
                hasattr(fl, n) for n in ("_create_base_flange", "_create_edge_flange")
            )
        )
        gone_from_mutate = not any(hasattr(mutate_mod, n) for n in _MOVED_HANDLERS)
        supported = tuple(mutate_mod._SUPPORTED_FEATURE_TYPES)
        supported_pruned = (
            not any(k in supported for k in _GREEN_KINDS)
            and "sweep" in supported
            and "sweep_cut" in supported
        )
        gate(
            "registry_seam",
            green_advertised
            and walls_dormant
            and in_modules
            and gone_from_mutate
            and supported_pruned,
            f"green8_advertised={green_advertised} walls5_dormant={walls_dormant} "
            f"in_new_modules={in_modules} removed_from_mutate={gone_from_mutate} "
            f"supported_pruned={supported_pruned} (_SUPPORTED={supported})",
        )

        client = SolidWorksClient()

        # ── B: fillet (edge-driven GREEN) full lifecycle ──
        fillet_seed = str(_WORK / "recipec4_fillet_seed.SLDPRT")
        edge_ref = _capture_edge_ref(sw, fillet_seed)
        if not edge_ref or not edge_ref.get("persist_id"):
            gate("fillet_lifecycle", False, f"edge_ref capture failed: {edge_ref!r}")
        else:
            results["fillet_edge_ref"] = edge_ref
            _lifecycle(
                client,
                sw,
                "fillet",
                fillet_seed,
                {"type": "fillet_constant_radius", "radius_mm": 2.0},
                edge_ref,
                "Fillet",
            )

        # ── C: dome (advanced-shape GREEN) full lifecycle ──
        dome_seed = str(_WORK / "recipec4_dome_seed.SLDPRT")
        face_ref = _capture_face_ref(sw, dome_seed)
        if not face_ref or not face_ref.get("persist_id"):
            gate("dome_lifecycle", False, f"face_ref capture failed: {face_ref!r}")
        else:
            results["dome_face_ref"] = face_ref
            _lifecycle(
                client,
                sw,
                "dome",
                dome_seed,
                {"type": "dome", "distance_mm": 5.0},
                {"face_ref": face_ref},
                "Dome",
            )

        # ── D/E: the walls stay walled (propose fail-closes) ──
        wall_seed = (
            fillet_seed if (edge_ref and edge_ref.get("persist_id")) else dome_seed
        )
        _fail_closed(
            client,
            sw,
            "wrap",
            wall_seed,
            {"type": "wrap"},
            {"sketch": "Sketch1", "face": [0, 0, BOX_D_M]},
        )
        _fail_closed(
            client,
            sw,
            "edge_flange",
            wall_seed,
            {"type": "edge_flange", "height_mm": 10.0},
            {"edge_ref": (edge_ref or {"persist_id": "x"})},
        )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
