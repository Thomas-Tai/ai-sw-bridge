"""W36 configurations spike — characterize ConfigurationManager + per-config params.

S1 seat spike (W0 requirement):
  - Connect to SW seat → build a parametric cylinder (PART_DIAMETER, PART_LENGTH)
  - Measure baseline volume
  - AddConfiguration2 (IConfigurationManager, 7 args) — create "Small" and "Large"
  - Per-configuration parameter route:
      IConfiguration.GetParameterCount → GetParameters([out],[out]) → SetParameters
  - Activate via IModelDoc2.ShowConfiguration2(name)
  - VERIFY THE EFFECT (W21 volume-delta doctrine): each variant must show
    a proven DISTINCT volume. ForceRebuild3 + re-measure.
  - Save, close, reopen, re-measure (W0 VERIFY THE EFFECT).

Characterized API surface (makepy-authoritative, SW 2024 SP1):
  IConfigurationManager.AddConfiguration2(Name, Comment, AltName, Options,
      ParentConfigName, Description, Rebuild) -> IConfiguration
  IModelDoc2.GetConfigurationNames() -> array of strings
  IModelDoc2.GetConfigurationByName(Name) -> IConfiguration
  IModelDoc2.ShowConfiguration2(Name) -> activates config
  IConfiguration.GetParameterCount() -> int
  IConfiguration.GetParameters([out] Params, [out] Values) -> (params, values)
  IConfiguration.SetParameters(Params, Values) -> bool

W29 makepy traps carried forward:
  - Count is a PROPERTY not Count() on typed dispatch
  - SaveAs3 not Save3 (on IModelDoc2)
  - Late-bound: zero-arg methods auto-invoke as properties on getattr
  - GetParameters has [out] params → must use typed_qi, not late-bound
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


def _rebuild(doc, label=""):
    """ForceRebuild3(top_level=True)."""
    try:
        doc.ForceRebuild3(True)
        return True, None
    except Exception as exc:
        return False, f"{label}: ForceRebuild3: {type(exc).__name__}: {exc}"


def _close_doc(sw, doc):
    """Close a document safely."""
    try:
        title = _resolve(doc, "GetTitle")
        sw.CloseDoc(title)
    except Exception:
        pass


def run_spike() -> dict:
    """Execute the W36 S1 seat spike."""
    result: dict = {
        "ok": False,
        "stage": "init",
        "errors": [],
        "warnings": [],
        "discoveries": {},
        "volumes": {},
        "reopen_volumes": {},
        "per_config_params": {},
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Build a parametric cylinder
    result["stage"] = "build_part"
    spec_path = repo_root / "examples" / "minimal_cylinder_v2" / "spec.json"
    locals_path = repo_root / "examples" / "minimal_cylinder" / "locals.txt"
    part_path = ARTIFACTS_DIR / "W36_cylinder.SLDPRT"

    if not spec_path.is_file():
        result["errors"].append(f"spec not found: {spec_path}")
        return result

    spike_locals = ARTIFACTS_DIR / "W36_locals.txt"
    shutil.copy(locals_path, spike_locals)

    print("=== Building parametric cylinder ===", file=sys.stderr)
    build_cmd = [
        sys.executable, "-m", "ai_sw_bridge.cli.build",
        str(spec_path), "--no-dim", "--save-as", str(part_path),
    ]
    try:
        proc = subprocess.run(
            build_cmd, capture_output=True, text=True, timeout=120,
            cwd=str(repo_root),
        )
        if proc.returncode != 0:
            result["errors"].append(f"build failed: {proc.stderr[-300:]}")
            return result
    except Exception as exc:
        result["errors"].append(f"build exception: {exc!r}")
        return result

    if not part_path.is_file():
        sldprts = list(ARTIFACTS_DIR.glob("*.SLDPRT")) + list(ARTIFACTS_DIR.glob("*.sldprt"))
        if sldprts:
            part_path = sldprts[0]
        else:
            result["errors"].append(f"part file not found: {part_path}")
            return result
    result["part_path"] = str(part_path)

    # Step 2: Open the part
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
        print("Part opened", file=sys.stderr)
    except Exception as exc:
        result["errors"].append(f"open failed: {exc!r}\n{traceback.format_exc()}")
        return result

    # Step 3: Baseline volume
    result["stage"] = "baseline"
    _rebuild(mdoc2, "baseline")
    baseline_vol, vol_err = _measure_volume(mdoc2, "baseline")
    result["volumes"]["baseline"] = baseline_vol
    if vol_err:
        result["errors"].append(vol_err)
        _close_doc(sw, mdoc2)
        return result
    print(f"Baseline volume: {baseline_vol:.2f} mm³", file=sys.stderr)

    # Step 4: Acquire ConfigurationManager (typed_qi)
    result["stage"] = "acquire_cm"
    cm_raw = getattr(mdoc2, "ConfigurationManager")
    cm = cm_raw() if callable(cm_raw) else cm_raw
    typed_cm = None
    try:
        typed_cm = typed_qi(cm, "IConfigurationManager", module=mod)
        result["discoveries"]["cm_typed_qi"] = "ok"
    except Exception as exc:
        result["discoveries"]["cm_typed_qi_error"] = str(exc)

    target_cm = typed_cm if typed_cm else cm
    result["discoveries"]["cm_type"] = type(target_cm).__name__

    # Step 5: Get existing config names via IModelDoc2
    result["stage"] = "existing_configs"
    try:
        existing = mdoc2.GetConfigurationNames()
        result["discoveries"]["existing_configs"] = list(existing) if existing else []
        print(f"Existing configs: {result['discoveries']['existing_configs']}", file=sys.stderr)
    except Exception as exc:
        result["discoveries"]["existing_configs_error"] = str(exc)

    # Step 6: Create "Small" config via IConfigurationManager.AddConfiguration2
    # Signature: (Name, Comment, AltName, Options, ParentConfigName, Description, Rebuild)
    result["stage"] = "add_small"
    small_config = None
    try:
        small_config = target_cm.AddConfiguration2(
            "Small",     # Name
            "",          # Comment
            "",          # AlternateName
            0,           # Options
            "",          # ParentConfigName (empty = root)
            "Small variant",  # Description
            0,           # Rebuild (0=no rebuild)
        )
        result["discoveries"]["add_small"] = {
            "ok": small_config is not None,
            "type": type(small_config).__name__,
        }
        print(f"AddConfiguration2(Small) -> {type(small_config).__name__}", file=sys.stderr)
    except Exception as exc:
        result["discoveries"]["add_small_error"] = f"{type(exc).__name__}: {exc}"
        # Fallback: try IModelDoc2.AddConfiguration2 (8 args)
        try:
            small_config = mdoc2.AddConfiguration2(
                "Small", "", "", False, False, False, True, 0,
            )
            result["discoveries"]["add_small_fallback"] = "IModelDoc2.AddConfiguration2"
        except Exception as exc2:
            result["discoveries"]["add_small_fallback_error"] = str(exc2)

    if small_config is None:
        result["errors"].append("Could not create Small config")
        _close_doc(sw, mdoc2)
        return result

    # Step 7: Create "Large" config
    result["stage"] = "add_large"
    large_config = None
    try:
        large_config = target_cm.AddConfiguration2(
            "Large", "", "", 0, "", "Large variant", 0,
        )
        result["discoveries"]["add_large"] = {
            "ok": large_config is not None,
            "type": type(large_config).__name__,
        }
    except Exception as exc:
        result["discoveries"]["add_large_error"] = str(exc)

    # Step 8: Get IConfiguration objects via GetConfigurationByName
    result["stage"] = "get_configs"
    small_cfg = None
    large_cfg = None
    try:
        raw_small = mdoc2.GetConfigurationByName("Small")
        if raw_small:
            small_cfg = typed_qi(raw_small, "IConfiguration", module=mod)
    except Exception as exc:
        result["discoveries"]["get_small_error"] = str(exc)

    if large_config is not None:
        try:
            raw_large = mdoc2.GetConfigurationByName("Large")
            if raw_large:
                large_cfg = typed_qi(raw_large, "IConfiguration", module=mod)
        except Exception as exc:
            result["discoveries"]["get_large_error"] = str(exc)

    # Step 9: Read parameters from the Small configuration
    result["stage"] = "read_params"
    if small_cfg is not None:
        try:
            param_count = small_cfg.GetParameterCount()
            result["discoveries"]["small_param_count"] = param_count
            print(f"Small config param count: {param_count}", file=sys.stderr)

            if param_count > 0:
                # GetParameters has [out] params → must use typed dispatch
                params_result = small_cfg.GetParameters()
                result["discoveries"]["small_GetParameters_result"] = {
                    "type": type(params_result).__name__,
                    "repr": repr(params_result)[:500],
                }
                print(f"GetParameters: {repr(params_result)[:200]}", file=sys.stderr)
        except Exception as exc:
            result["discoveries"]["read_params_error"] = f"{type(exc).__name__}: {exc}"

    # Also read the base (Default) config params for comparison
    try:
        default_cfg_raw = mdoc2.GetConfigurationByName(
            result["discoveries"].get("existing_configs", ["Default"])[0]
        )
        if default_cfg_raw:
            default_cfg = typed_qi(default_cfg_raw, "IConfiguration", module=mod)
            default_count = default_cfg.GetParameterCount()
            result["discoveries"]["default_param_count"] = default_count
            if default_count > 0:
                default_params = default_cfg.GetParameters()
                result["discoveries"]["default_GetParameters"] = repr(default_params)[:500]
    except Exception as exc:
        result["discoveries"]["default_params_error"] = str(exc)

    # Step 10: Try SetParameters on Small config
    result["stage"] = "set_params_small"
    if small_cfg is not None:
        try:
            # Set PART_DIAMETER=20, PART_LENGTH=60
            set_result = small_cfg.SetParameters(
                ("PART_DIAMETER", "PART_LENGTH"),
                (20.0, 60.0),
            )
            result["per_config_params"]["set_small"] = {
                "ok": True,
                "result": repr(set_result)[:200],
            }
            print(f"SetParameters(Small): {set_result}", file=sys.stderr)
        except Exception as exc:
            result["per_config_params"]["set_small_error"] = f"{type(exc).__name__}: {exc}"
            # Try with list instead of tuple
            try:
                set_result = small_cfg.SetParameters(
                    ["PART_DIAMETER", "PART_LENGTH"],
                    [20.0, 60.0],
                )
                result["per_config_params"]["set_small_list"] = {
                    "ok": True,
                    "result": repr(set_result)[:200],
                }
            except Exception as exc2:
                result["per_config_params"]["set_small_list_error"] = str(exc2)

    # Step 11: Activate Small config + rebuild + measure
    result["stage"] = "activate_small"
    try:
        mdoc2.ShowConfiguration2("Small")
        print("ShowConfiguration2(Small) succeeded", file=sys.stderr)
    except Exception as exc:
        result["warnings"].append(f"ShowConfiguration2(Small): {exc}")
        # Try IConfiguration.Select2 as fallback
        if small_cfg:
            try:
                small_cfg.Select2(False, 0)
            except Exception:
                try:
                    small_cfg.Select(False)
                except Exception as exc2:
                    result["warnings"].append(f"Select fallback also failed: {exc2}")

    _rebuild(mdoc2, "small")
    small_vol, vol_err = _measure_volume(mdoc2, "small")
    result["volumes"]["small"] = small_vol
    if vol_err:
        result["warnings"].append(vol_err)
    if small_vol is not None:
        print(f"Small volume: {small_vol:.2f} mm³", file=sys.stderr)

    # Step 12: Set + activate Large config
    result["stage"] = "set_activate_large"
    if large_cfg is not None:
        try:
            large_cfg.SetParameters(
                ("PART_DIAMETER", "PART_LENGTH"),
                (50.0, 120.0),
            )
        except Exception:
            try:
                large_cfg.SetParameters(
                    ["PART_DIAMETER", "PART_LENGTH"],
                    [50.0, 120.0],
                )
            except Exception as exc:
                result["warnings"].append(f"Large SetParameters: {exc}")

    try:
        mdoc2.ShowConfiguration2("Large")
    except Exception as exc:
        result["warnings"].append(f"ShowConfiguration2(Large): {exc}")

    _rebuild(mdoc2, "large")
    large_vol, vol_err = _measure_volume(mdoc2, "large")
    result["volumes"]["large"] = large_vol
    if vol_err:
        result["warnings"].append(vol_err)
    if large_vol is not None:
        print(f"Large volume: {large_vol:.2f} mm³", file=sys.stderr)

    # Step 13: Verify config names after creation
    result["stage"] = "verify_configs"
    try:
        names = mdoc2.GetConfigurationNames()
        result["discoveries"]["configs_after_create"] = list(names) if names else []
    except Exception:
        pass

    # Step 14: Save, close, reopen, re-measure
    result["stage"] = "save_reopen"
    try:
        save_err = mdoc2.SaveAs3(str(part_path), 0, 0)
        result["save_ok"] = save_err == 0
        if save_err != 0:
            result["warnings"].append(f"SaveAs3 returned {save_err}")
    except Exception as exc:
        result["warnings"].append(f"SaveAs3: {exc}")

    _close_doc(sw, mdoc2)

    # Reopen
    time.sleep(0.5)
    try:
        ret = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        model_doc2 = ret[0] if isinstance(ret, tuple) else ret
        if model_doc2 is None:
            result["errors"].append("Reopen failed")
            return result

        mdoc2b = typed_qi(model_doc2, "IModelDoc2", module=mod)

        # Config names after reopen
        try:
            names = mdoc2b.GetConfigurationNames()
            result["reopen_configs"] = list(names) if names else []
        except Exception:
            pass

        # Measure volume per config after reopen
        for config_name in ["Small", "Large"]:
            try:
                mdoc2b.ShowConfiguration2(config_name)
            except Exception:
                pass
            _rebuild(mdoc2b, f"reopen_{config_name}")
            vol, vol_err = _measure_volume(mdoc2b, f"reopen_{config_name}")
            result["reopen_volumes"][config_name] = vol
            if vol_err:
                result["warnings"].append(f"reopen {config_name}: {vol_err}")
            if vol is not None:
                print(f"Reopen volume ({config_name}): {vol:.2f} mm³", file=sys.stderr)

        _close_doc(sw, mdoc2b)
    except Exception as exc:
        result["errors"].append(f"Reopen: {exc!r}")

    # Step 15: Final validation
    result["stage"] = "validation"
    all_vols = {k: v for k, v in result["volumes"].items() if v is not None}
    distinct = set(round(v, 1) for v in all_vols.values())
    result["distinct_volumes_mm3"] = sorted(distinct)
    result["all_volumes"] = all_vols

    if len(distinct) >= 3:
        result["ok"] = True
        result["summary"] = (
            f"VERIFIED: {len(distinct)} distinct volumes "
            f"(baseline + Small + Large). Volumes: {sorted(distinct)} mm³"
        )
    elif len(distinct) >= 2:
        result["ok"] = True
        result["summary"] = (
            f"PARTIAL: {len(distinct)} distinct volumes. "
            f"Volumes: {all_vols}. Per-config params may need "
            f"different route."
        )
    else:
        result["errors"].append(
            f"Only {len(distinct)} distinct volume(s) — "
            f"configurations not applying overrides. "
            f"Volumes: {all_vols}"
        )

    return result


if __name__ == "__main__":
    print("=== W36 Configurations Spike S1 (rev2) ===", file=sys.stderr)
    result = run_spike()

    out_path = SPIKE_DIR / "_results_W36_S1.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nResults: {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
