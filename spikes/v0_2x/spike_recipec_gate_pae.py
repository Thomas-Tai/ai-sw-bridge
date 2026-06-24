"""Recipe-C gate — pattern family migrated from mutate.py into the features/ registry.

The first 1.0.0 strangler-fig cut. Proves the three pattern handlers (linear /
circular / mirror) now live in features/patterns.py, are registered in
HANDLER_REGISTRY, and that mutate._apply_feature falls THROUGH to the registry to
execute them (the inline if/elif branches were deleted).

  A registry_seam   : HANDLER_REGISTRY advertises linear_pattern / circular_pattern /
                      mirror_feature; features.patterns exposes the three create_*
                      functions; mutate NO LONGER defines _create_*pattern / _create_
                      mirror_feature (proving the physical move + the cut, not a copy).
  B linear_lifecycle : client.mutate.propose_feature_add -> dry_run_feature_add ->
                      commit_feature_add for a linear_pattern materializes (commit
                      ok=True) — i.e. the displaced logic executed through the registry
                      via the public feature-add transaction path.
  C circular_lifecycle : same, circular_pattern (axis-driven).
  D mirror_lifecycle  : same, mirror_feature (plane-driven).

Fixture: one saved part with a `Box_Seed` boss extrude + `Axis1` (Front x Right),
mirroring the W21 patterns PAE. Each pattern runs its own propose/dry_run/commit on
the saved path (the feature-add lifecycle reopens by path).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_recipec_gate_pae.py
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

_PROPOSALS = _HERE.parent / "_results" / "recipec_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
import ai_sw_bridge.mutate as mutate_mod  # noqa: E402

_OUT = _HERE.parent / "_results" / "recipec_gate_pae.json"
_WORK = _HERE.parent / "_results" / "recipec_work"
results: dict[str, Any] = {
    "pae": "recipec_pattern_registry_migration_gate",
    "gates": {},
}

_PATTERN_KINDS = ("linear_pattern", "circular_pattern", "mirror_feature")


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


def _build_seed_part(sw: Any, path: str) -> bool:
    """Build a `Box_Seed` boss + `Axis1` (Front x Right) and save to *path*."""
    template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return False
    fm = doc.FeatureManager
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
    doc.SketchManager.InsertSketch(True)
    f = fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.01,
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
        f.Name = "Box_Seed"
    doc.ForceRebuild3(False)
    # Axis1 = Front Plane x Right Plane
    doc.ClearSelection2(True)
    fp = rp = None
    for feat in fm.GetFeatures(True) or []:
        n = feat.Name
        n = n() if callable(n) else n
        if n == "Front Plane":
            fp = feat
        elif n == "Right Plane":
            rp = feat
    if fp is not None and rp is not None:
        fp.Select2(False, 0)
        rp.Select2(True, 0)
        doc.InsertAxis2(True)
    doc.ForceRebuild3(False)
    doc.SaveAs3(path, 0, 0)
    return os.path.isfile(path)


def _lifecycle(
    client: Any, name: str, seed_path: str, feature: dict, target: dict, sw: Any
) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    prop = client.mutate.propose_feature_add(seed_path, feature, target)
    pid = prop.get("proposal_id")
    results[f"{name}_propose"] = prop
    if not pid:
        gate(f"{name}_lifecycle", False, f"propose failed: {prop.get('error')}")
        return
    dry = client.mutate.dry_run_feature_add(pid)
    com = client.mutate.commit_feature_add(pid)
    results[f"{name}_dry_run"] = dry
    results[f"{name}_commit"] = com
    gate(
        f"{name}_lifecycle",
        bool(prop.get("ok")) and bool(dry.get("ok")) and bool(com.get("ok")),
        f"propose={prop.get('ok')} dry_run={dry.get('ok')} commit={com.get('ok')} "
        f"(executed through HANDLER_REGISTRY) err={com.get('error') or dry.get('error')}",
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
        # ── A: structural — the cut happened, handlers relocated + registered ──
        try:
            import ai_sw_bridge.features.patterns as patterns_mod
        except Exception as exc:  # noqa: BLE001
            gate("registry_seam", False, f"features.patterns import failed: {exc}")
            raise SystemExit(_finish())
        registered = all(k in HANDLER_REGISTRY for k in _PATTERN_KINDS)
        in_features = all(
            hasattr(patterns_mod, f"create_{k}")
            for k in ("linear_pattern", "circular_pattern", "mirror_feature")
        )
        gone_from_mutate = not any(
            hasattr(mutate_mod, n)
            for n in (
                "_create_linear_pattern",
                "_create_circular_pattern",
                "_create_mirror_feature",
            )
        )
        gate(
            "registry_seam",
            registered and in_features and gone_from_mutate,
            f"registered={registered} in_features={in_features} "
            f"removed_from_mutate={gone_from_mutate}",
        )

        # ── Fixture: saved seed part (Box_Seed + Axis1) ──
        seed_path = str(_WORK / "recipec_seed.SLDPRT")
        if not _build_seed_part(sw, seed_path):
            gate("linear_lifecycle", False, "seed part build/save failed")
            raise SystemExit(_finish())

        client = SolidWorksClient()

        # ── B/C/D: each pattern through propose -> dry_run -> commit (registry) ──
        _lifecycle(
            client,
            "linear",
            seed_path,
            {"type": "linear_pattern", "spacing_mm": 5.0, "count": 3},
            {"seed": "Box_Seed", "direction": {"x": 0, "y": 10, "z": 10}},
            sw,
        )
        _lifecycle(
            client,
            "circular",
            seed_path,
            {
                "type": "circular_pattern",
                "count": 4,
                "angle_deg": 360,
                "equal_spacing": True,
            },
            {"seed": "Box_Seed", "axis": "Axis1"},
            sw,
        )
        _lifecycle(
            client,
            "mirror",
            seed_path,
            {"type": "mirror_feature"},
            {"seed": "Box_Seed", "plane": "Right Plane"},
            sw,
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
