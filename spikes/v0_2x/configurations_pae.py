"""W36 configurations spike S2 — topological suppression for distinct volumes.

S2 seat spike (W0 adjudication: Option C):
  - Build a two-feature part (Block_A: 50×50×50, Block_B: 100×100×100)
  - Create Config_A and Config_B
  - Suppress Block_B on Config_A, suppress Block_A on Config_B
  - VERIFY THE EFFECT: Config_A volume ≠ Config_B volume
  - Save, close, reopen, re-measure per config

Key API (characterized in S1):
  IConfigurationManager.AddConfiguration2(Name, Comment, AltName, Options,
      ParentConfigName, Description, Rebuild) -> IConfiguration
  IModelDoc2.ShowConfiguration2(Name) -> activates config
  IFeature.SetSuppression2(SuppressionState, Config_opt, Config_names) -> bool
    Config_opt: 0=active config only

W29 makepy traps (carried from S1):
  - AddConfiguration2 on IConfigurationManager: 7 args NOT 3
  - GetConfigurationNames on IModelDoc2 NOT IConfigurationManager
  - SetSuppression2: 3 args (SuppressionState, Config_opt, Config_names)
  - Count is a PROPERTY not Count() on typed dispatch
  - Late-bound: zero-arg methods auto-invoke as properties on getattr
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))

SPIKE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = SPIKE_DIR / "_artifacts_w36"

TWO_BLOCK_SPEC = {
    "schema_version": 1,
    "name": "TwoBlockConfigTest",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_BlockA",
            "plane": "Front",
            "width": 50.0,
            "height": 50.0,
        },
        {
            "type": "boss_extrude_blind",
            "name": "Block_A",
            "sketch": "SK_BlockA",
            "depth": 50.0,
        },
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_BlockB",
            "plane": "Right",
            "width": 100.0,
            "height": 100.0,
        },
        {
            "type": "boss_extrude_blind",
            "name": "Block_B",
            "sketch": "SK_BlockB",
            "depth": 100.0,
        },
    ],
}

EXPECTED_VOL_A = 50 * 50 * 50
EXPECTED_VOL_B = 100 * 100 * 100


def _resolve(obj, name):
    """Get obj.name, calling it if it's a zero-arg method on typed dispatch."""
    val = getattr(obj, name)
    if callable(val):
        val = val()
    return val


def _measure_volume(doc, label=""):
    """Measure volume via CreateMassProperty. Returns mm^3 or (None, error)."""
    try:
        ext = _resolve(doc, "Extension")
        mp = _resolve(ext, "CreateMassProperty")
        if mp is None:
            return None, f"{label}: CreateMassProperty returned None"
        vol_m3 = float(_resolve(mp, "Volume"))
        return vol_m3 * 1e9, None
    except Exception as exc:
        return None, f"{label}: {type(exc).__name__}: {exc}"


def _close_doc(sw, doc):
    """Close a document safely."""
    try:
        title = _resolve(doc, "GetTitle")
        sw.CloseDoc(title)
    except Exception:
        pass


def run_spike() -> dict:
    """Execute the W36 S2 topological suppression spike."""
    result: dict = {
        "ok": False,
        "stage": "init",
        "errors": [],
        "warnings": [],
        "volumes": {},
        "reopen_volumes": {},
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Write spec + build two-block part
    result["stage"] = "build"
    spec_path = ARTIFACTS_DIR / "W36_two_block_spec.json"
    spec_path.write_text(json.dumps(TWO_BLOCK_SPEC, indent=2), encoding="utf-8")
    part_path = ARTIFACTS_DIR / "W36_two_block.SLDPRT"

    print("=== Building two-block part ===", file=sys.stderr)
    proc = subprocess.run(
        [
            sys.executable, "-m", "ai_sw_bridge.cli.build",
            str(spec_path), "--no-dim", "--save-as", str(part_path),
        ],
        capture_output=True, text=True, timeout=120, cwd=str(repo_root),
    )
    result["build_rc"] = proc.returncode
    if proc.returncode != 0:
        result["errors"].append(f"build failed: {proc.stderr[-500:]}")
        return result

    if not part_path.is_file():
        sldprts = list(ARTIFACTS_DIR.glob("W36_two_block*SLDPRT"))
        if sldprts:
            part_path = sldprts[0]
        else:
            result["errors"].append(f"part not found: {part_path}")
            return result
    result["part_path"] = str(part_path)

    # Step 2: Open part + measure baseline
    result["stage"] = "open"
    try:
        from ai_sw_bridge.com.earlybind import typed, typed_qi
        from ai_sw_bridge.com.sw_type_info import wrapper_module
        from ai_sw_bridge.sw_com import get_sw_app

        sw = get_sw_app()
        mod = wrapper_module()
        tsw = typed(sw, "ISldWorks", module=mod)

        ret = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is None:
            result["errors"].append("OpenDoc6 returned None")
            return result
        mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)
    except Exception as exc:
        result["errors"].append(f"open: {exc!r}")
        return result

    result["stage"] = "baseline"
    mdoc2.ForceRebuild3(True)
    baseline_vol, vol_err = _measure_volume(mdoc2, "baseline")
    result["volumes"]["baseline"] = baseline_vol
    if vol_err:
        result["errors"].append(vol_err)
        _close_doc(sw, mdoc2)
        return result
    print(f"Baseline: {baseline_vol:.2f} mm³ (expected ~{EXPECTED_VOL_A + EXPECTED_VOL_B})",
          file=sys.stderr)

    # Step 3: Discover features (Block_A and Block_B)
    result["stage"] = "find_features"
    features = {}
    for i in range(10):
        try:
            f = mdoc2.FeatureByPositionReverse(i)
            if f is None:
                break
            typed_f = typed_qi(f, "IFeature", module=mod)
            name = _resolve(typed_f, "Name")
            features[name] = typed_f
            print(f"  Feature[{i}]: {name}", file=sys.stderr)
        except Exception:
            break

    block_a = features.get("Block_A")
    block_b = features.get("Block_B")
    if block_a is None or block_b is None:
        result["errors"].append(
            f"Missing features: Block_A={'found' if block_a else 'MISSING'}, "
            f"Block_B={'found' if block_b else 'MISSING'}. "
            f"Available: {list(features.keys())}"
        )
        _close_doc(sw, mdoc2)
        return result

    # Step 4: Create configurations
    result["stage"] = "create_configs"
    cm_raw = getattr(mdoc2, "ConfigurationManager")
    cm = cm_raw() if callable(cm_raw) else cm_raw
    typed_cm = typed_qi(cm, "IConfigurationManager", module=mod)

    cfg_a = typed_cm.AddConfiguration2(
        "Config_A", "", "", 0, "", "Block_A only", 0)
    cfg_b = typed_cm.AddConfiguration2(
        "Config_B", "", "", 0, "", "Block_B only", 0)

    result["configs_created"] = {
        "Config_A": cfg_a is not None,
        "Config_B": cfg_b is not None,
    }
    if cfg_a is None or cfg_b is None:
        result["errors"].append(
            f"Config creation failed: A={cfg_a is not None}, B={cfg_b is not None}")
        _close_doc(sw, mdoc2)
        return result
    print("Configs created: Config_A, Config_B", file=sys.stderr)

    # Step 5: Suppress features per config
    # Strategy: activate config, then SetSuppression2 with Config_opt=0 (active only)
    result["stage"] = "suppress_features"

    # Config_A: suppress Block_B (keep Block_A)
    mdoc2.ShowConfiguration2("Config_A")
    mdoc2.ForceRebuild3(True)
    try:
        r_a = block_b.SetSuppression2(0, 0, "")
        result["suppress_Block_B_on_A"] = {"result": r_a, "state": "suppressed"}
        print(f"Config_A: suppress Block_B -> {r_a}", file=sys.stderr)
    except Exception as exc:
        result["suppress_Block_B_on_A"] = {"error": f"{type(exc).__name__}: {exc}"}
        # Try with tuple
        try:
            r_a = block_b.SetSuppression2(0, 2, ("Config_A",))
            result["suppress_Block_B_on_A_v2"] = {"result": r_a}
            print(f"Config_A: suppress Block_B (v2) -> {r_a}", file=sys.stderr)
        except Exception as exc2:
            result["suppress_Block_B_on_A_v2"] = {"error": str(exc2)}

    mdoc2.ForceRebuild3(True)

    # Config_B: suppress Block_A (keep Block_B)
    mdoc2.ShowConfiguration2("Config_B")
    mdoc2.ForceRebuild3(True)
    try:
        r_b = block_a.SetSuppression2(0, 0, "")
        result["suppress_Block_A_on_B"] = {"result": r_b, "state": "suppressed"}
        print(f"Config_B: suppress Block_A -> {r_b}", file=sys.stderr)
    except Exception as exc:
        result["suppress_Block_A_on_B"] = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            r_b = block_a.SetSuppression2(0, 2, ("Config_B",))
            result["suppress_Block_A_on_B_v2"] = {"result": r_b}
            print(f"Config_B: suppress Block_A (v2) -> {r_b}", file=sys.stderr)
        except Exception as exc2:
            result["suppress_Block_A_on_B_v2"] = {"error": str(exc2)}

    mdoc2.ForceRebuild3(True)

    # Step 6: Measure volume per config
    result["stage"] = "measure"
    for cn in ["Default", "Config_A", "Config_B"]:
        try:
            mdoc2.ShowConfiguration2(cn)
        except Exception as exc:
            result["warnings"].append(f"ShowConfiguration2({cn}): {exc}")
        mdoc2.ForceRebuild3(True)
        vol, vol_err = _measure_volume(mdoc2, cn)
        result["volumes"][cn] = vol
        if vol_err:
            result["warnings"].append(vol_err)
        print(f"{cn}: {vol:.2f} mm³" if vol else f"{cn}: {vol_err}",
              file=sys.stderr)

    # Step 7: Save, close, reopen, re-measure
    result["stage"] = "save_reopen"
    try:
        save_err = mdoc2.SaveAs3(str(part_path), 0, 0)
        result["save_ok"] = save_err == 0
    except Exception as exc:
        result["warnings"].append(f"SaveAs3: {exc}")

    _close_doc(sw, mdoc2)
    time.sleep(0.5)

    try:
        ret = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        model_doc2 = ret[0] if isinstance(ret, tuple) else ret
        if model_doc2 is None:
            result["errors"].append("Reopen failed")
            return result
        mdoc2b = typed_qi(model_doc2, "IModelDoc2", module=mod)

        for cn in ["Default", "Config_A", "Config_B"]:
            try:
                mdoc2b.ShowConfiguration2(cn)
            except Exception:
                pass
            mdoc2b.ForceRebuild3(True)
            vol, vol_err = _measure_volume(mdoc2b, f"reopen_{cn}")
            result["reopen_volumes"][cn] = vol
            if vol_err:
                result["warnings"].append(f"reopen {cn}: {vol_err}")
            print(f"Reopen {cn}: {vol:.2f} mm³" if vol else f"Reopen {cn}: {vol_err}",
                  file=sys.stderr)

        _close_doc(sw, mdoc2b)
    except Exception as exc:
        result["errors"].append(f"Reopen: {exc!r}")

    # Step 8: Validation
    result["stage"] = "validation"
    live_vols = {k: v for k, v in result["volumes"].items() if v is not None}
    distinct_live = set(round(v, 1) for v in live_vols.values())

    reopen_vols = {k: v for k, v in result["reopen_volumes"].items() if v is not None}
    distinct_reopen = set(round(v, 1) for v in reopen_vols.values())

    result["distinct_live"] = sorted(distinct_live)
    result["distinct_reopen"] = sorted(distinct_reopen)
    result["all_volumes"] = live_vols
    result["all_reopen_volumes"] = reopen_vols

    # Config_A should show only Block_A volume (~125000)
    # Config_B should show only Block_B volume (~1000000)
    # Default should show both (~1125000)
    config_a_vol = live_vols.get("Config_A")
    config_b_vol = live_vols.get("Config_B")

    if config_a_vol is not None and config_b_vol is not None:
        if abs(config_a_vol - config_b_vol) > 1000:
            result["ok"] = True
            result["summary"] = (
                f"VERIFIED: Config_A={config_a_vol:.0f} mm³ ≠ "
                f"Config_B={config_b_vol:.0f} mm³. "
                f"Distinct volumes: {len(distinct_live)}. "
                f"Reopen persistence: {len(distinct_reopen)} distinct."
            )
        else:
            result["errors"].append(
                f"Config_A ({config_a_vol:.0f}) ≈ Config_B ({config_b_vol:.0f}) "
                f"— suppression may have leaked to all configs"
            )
    else:
        result["errors"].append(
            f"Missing volume data: Config_A={config_a_vol}, Config_B={config_b_vol}")

    return result


if __name__ == "__main__":
    print("=== W36 Configurations Spike S2 (topological suppression) ===",
          file=sys.stderr)
    result = run_spike()

    out_path = SPIKE_DIR / "_results_W36_S2.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nResults: {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
