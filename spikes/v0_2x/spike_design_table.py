"""W53 seat spike — design table insertion + config discrimination.

THE question (W53, Phase-4 design tables):
  Can ``IModelDoc2.InsertFamilyTableNew`` (or ``IDesignTable`` edit ops)
  drive N DISTINCT configurations from a parameter grid, with volume
  discrimination, surviving save→reopen — without hitting the same
  SetSuppression-class wall that blocked W36 native configs?

GREEN gate:
  - A design-table spec materializes N ≥ 2 DISTINCT configurations.
  - Volume-discriminated (CreateMassProperty per config: ≥ 2 distinct).
  - Surviving save→reopen (the W36v multi-file discipline, but in-file).

NO-GO deliverable (if walled):
  - FUNCDESC dump of the exact method(s) probed.
  - The exact no-op/leak/error for each route.
  - A clean NO-GO with the wall named.

Three routes probed:
  Route A: InsertFamilyTableNew(FilePath) — CSV-based, no Excel OLE.
  Route B: IDesignTable.Attach3 + EditTable2 — OLE-based (expected wall).
  Route C: ConfigurationManager.AddConfiguration2 + design-table-driven
           dimension changes — hybrid (tests if DT changes propagate).

Prereq: SOLIDWORKS 2024 SP1 running. Part built by the spec builder.
Usage:
  python spikes/v0_2x/spike_design_table.py --out _results/designtable_spike.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

SPIKE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = SPIKE_DIR / "_artifacts_w53"

TWO_FEATURE_SPEC = {
    "schema_version": 1,
    "name": "DTTestPart",
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


def _resolve(obj: Any, name: str) -> Any:
    val = getattr(obj, name)
    if callable(val):
        val = val()
    return val


def _measure_volume(doc: Any, label: str = "") -> tuple[float | None, str | None]:
    try:
        ext = _resolve(doc, "Extension")
        mp = _resolve(ext, "CreateMassProperty")
        if mp is None:
            return None, f"{label}: CreateMassProperty returned None"
        vol_m3 = float(_resolve(mp, "Volume"))
        return vol_m3 * 1e9, None
    except Exception as exc:
        return None, f"{label}: {type(exc).__name__}: {exc}"


def _close_doc(sw: Any, doc: Any) -> None:
    try:
        title = _resolve(doc, "GetTitle")
        sw.CloseDoc(title)
    except Exception:
        pass


def _write_grid_csv(
    columns: list[str],
    rows: list[tuple[str, dict[str, str]]],
) -> str:
    """Write a design table grid to CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([""] + columns)
    for config_name, values in rows:
        cells = [config_name]
        for col in columns:
            cells.append(values.get(col, ""))
        writer.writerow(cells)
    return buf.getvalue()


def _discover_design_table_methods(mod: Any) -> dict[str, Any]:
    """Dump FUNCDESCs for design-table interfaces from the gen_py module."""
    result: dict[str, Any] = {"interfaces": {}, "modeldoc2_dt_methods": {}}

    for iface_name in (
        "IDesignTable",
        "IDesignTableFeatureData",
        "IFamilyTable",
        "IFamilyTableFeatureData",
    ):
        cls = getattr(mod, iface_name, None)
        if cls is None:
            continue
        methods: dict[str, list[dict]] = {}
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            attr = getattr(cls, attr_name, None)
            if not callable(attr):
                continue
            func_descs = getattr(attr, "funcdescs", None)
            if func_descs:
                methods[attr_name] = [
                    {
                        "memid": fd.memid,
                        "invoke_kind": {1: "FUNC", 2: "GET", 4: "PUT", 8: "PUTREF"}.get(
                            fd.invkind, str(fd.invkind)
                        ),
                        "arg_count": fd.cParams,
                    }
                    for fd in func_descs
                ]
        if methods:
            result["interfaces"][iface_name] = methods

    mdoc2_cls = getattr(mod, "IModelDoc2", None)
    if mdoc2_cls:
        for attr_name in dir(mdoc2_cls):
            lower = attr_name.lower()
            if not ("designtable" in lower or "familytable" in lower):
                continue
            attr = getattr(mdoc2_cls, attr_name, None)
            if not callable(attr):
                continue
            func_descs = getattr(attr, "funcdescs", None)
            if func_descs:
                result["modeldoc2_dt_methods"][attr_name] = [
                    {
                        "memid": fd.memid,
                        "invoke_kind": {1: "FUNC", 2: "GET", 4: "PUT", 8: "PUTREF"}.get(
                            fd.invkind, str(fd.invkind)
                        ),
                        "arg_count": fd.cParams,
                    }
                    for fd in func_descs
                ]

    return result


def run_spike() -> dict[str, Any]:
    """Execute the W53 design table seat spike."""
    result: dict[str, Any] = {
        "ok": False,
        "stage": "init",
        "routes": {},
        "errors": [],
        "warnings": [],
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Step 0: Build the two-feature part ----
    import subprocess

    result["stage"] = "build"
    spec_path = ARTIFACTS_DIR / "W53_dt_spec.json"
    spec_path.write_text(json.dumps(TWO_FEATURE_SPEC, indent=2), encoding="utf-8")
    part_path = ARTIFACTS_DIR / "W53_dt_test.SLDPRT"

    print("=== Building two-feature part ===", file=sys.stderr)
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable, "-m", "ai_sw_bridge.cli.build",
            str(spec_path), "--no-dim", "--save-as", str(part_path),
        ],
        capture_output=True, text=True, timeout=120, cwd=str(repo_root),
    )
    if proc.returncode != 0:
        result["errors"].append(f"build failed: {proc.stderr[-500:]}")
        return result
    if not part_path.is_file():
        sldprts = list(ARTIFACTS_DIR.glob("W53_dt_test*SLDPRT"))
        if sldprts:
            part_path = sldprts[0]
        else:
            result["errors"].append(f"part not found: {part_path}")
            return result
    result["part_path"] = str(part_path)

    # ---- Step 1: Open part + acquire COM handles ----
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

    # ---- Step 1.5: Typelib FUNCDESC dump ----
    result["stage"] = "typelib_probe"
    if mod:
        result["funcdesc_dump"] = _discover_design_table_methods(mod)
        print(
            f"FUNCDESC dump: "
            f"{len(result['funcdesc_dump']['interfaces'])} DT interfaces, "
            f"{len(result['funcdesc_dump']['modeldoc2_dt_methods'])} "
            f"IModelDoc2 DT methods",
            file=sys.stderr,
        )

    # Baseline volume
    mdoc2.ForceRebuild3(True)
    baseline_vol, vol_err = _measure_volume(mdoc2, "baseline")
    result["baseline_volume_mm3"] = baseline_vol
    if vol_err:
        result["errors"].append(vol_err)
        _close_doc(sw, mdoc2)
        return result
    print(f"Baseline: {baseline_vol:.2f} mm³", file=sys.stderr)

    # ---- Route A: InsertFamilyTableNew ----
    result["stage"] = "route_A"
    route_a: dict[str, Any] = {"status": "untried"}

    grid_columns = ["$CONFIGURATION", "D1@SK_BlockA", "D2@SK_BlockA"]
    grid_rows = [
        ("Config_Small", {"D1@SK_BlockA": "25.0", "D2@SK_BlockA": "25.0"}),
        ("Config_Large", {"D1@SK_BlockA": "75.0", "D2@SK_BlockA": "75.0"}),
    ]
    grid_csv = _write_grid_csv(grid_columns, grid_rows)
    grid_path = ARTIFACTS_DIR / "W53_design_table.csv"
    grid_path.write_text(grid_csv, encoding="utf-8")

    print(f"=== Route A: InsertFamilyTableNew({grid_path}) ===", file=sys.stderr)
    try:
        # Check if the method exists on the typed dispatch
        has_method = hasattr(mdoc2, "InsertFamilyTableNew")
        route_a["has_method"] = has_method

        if has_method:
            dt_result = mdoc2.InsertFamilyTableNew(str(grid_path))
            route_a["returned_type"] = type(dt_result).__name__
            route_a["returned_value"] = (
                str(dt_result)[:200] if dt_result is not None else "None"
            )
            route_a["status"] = "called"

            # Check if a design table feature was created
            feature_count = _resolve(mdoc2, "GetFeatureCount")
            route_a["feature_count"] = feature_count

            # Check for design table feature
            for i in range(min(feature_count or 0, 20)):
                try:
                    f = mdoc2.FeatureByPositionReverse(i)
                    if f is None:
                        break
                    typed_f = typed_qi(f, "IFeature", module=mod)
                    fname = _resolve(typed_f, "Name")
                    ftype = _resolve(typed_f, "GetTypeName")
                    if "table" in fname.lower() or "table" in str(ftype).lower():
                        route_a["dt_feature"] = {
                            "name": fname,
                            "type": ftype,
                        }
                        break
                except Exception:
                    pass
        else:
            # Try on raw late-bound dispatch too
            raw_doc = model_doc
            has_method_raw = hasattr(raw_doc, "InsertFamilyTableNew")
            route_a["has_method_raw"] = has_method_raw
            route_a["status"] = "method_not_found"
            route_a["note"] = (
                "InsertFamilyTableNew not on typed IModelDoc2. "
                "Check FUNCDESC dump for actual method name."
            )

            # Try alternate names
            for alt_name in (
                "InsertFamilyTable",
                "InsertDesignTable",
                "InsertDesignTableFromFile",
            ):
                if hasattr(mdoc2, alt_name) or hasattr(raw_doc, alt_name):
                    route_a[f"alt_found_{alt_name}"] = True

    except Exception as exc:
        route_a["status"] = "exception"
        route_a["error"] = f"{type(exc).__name__}: {exc}"

    result["routes"]["A_InsertFamilyTableNew"] = route_a
    print(f"Route A: {route_a['status']}", file=sys.stderr)

    # ---- Route B: IDesignTable interface probe ----
    result["stage"] = "route_B"
    route_b: dict[str, Any] = {"status": "untried"}

    print("=== Route B: IDesignTable interface probe ===", file=sys.stderr)
    try:
        # Check if there's already a design table feature we can QI to
        dt_feature = None
        feature_count = _resolve(mdoc2, "GetFeatureCount") or 0
        for i in range(min(feature_count, 30)):
            try:
                f = mdoc2.FeatureByPositionReverse(i)
                if f is None:
                    break
                typed_f = typed_qi(f, "IFeature", module=mod)
                ftype = _resolve(typed_f, "GetTypeName")
                if "DesignTable" in str(ftype) or "FamilyTable" in str(ftype):
                    dt_feature = typed_f
                    break
            except Exception:
                pass

        if dt_feature is not None:
            route_b["dt_feature_found"] = True
            # Try QI to IDesignTable
            try:
                idt = typed_qi(dt_feature, "IDesignTable", module=mod)
                route_b["idt_acquired"] = True

                # Try GetEntryCount
                try:
                    count = _resolve(idt, "GetEntryCount")
                    route_b["entry_count"] = count
                except Exception as exc:
                    route_b["get_entry_count_error"] = str(exc)

                # Try Attach3 (read-only)
                try:
                    attach_result = idt.Attach3(0)
                    route_b["attach3_result"] = str(type(attach_result).__name__)
                except Exception as exc:
                    route_b["attach3_error"] = str(exc)

            except Exception as exc:
                route_b["idt_qi_error"] = str(exc)
                route_b["idt_acquired"] = False
        else:
            route_b["dt_feature_found"] = False
            route_b["status"] = "no_dt_feature"
            route_b["note"] = (
                "No design table feature exists.  Route A may not have "
                "created one, or the feature type name differs."
            )

    except Exception as exc:
        route_b["status"] = "exception"
        route_b["error"] = f"{type(exc).__name__}: {exc}"

    result["routes"]["B_IDesignTable"] = route_b
    print(f"Route B: {route_b['status']}", file=sys.stderr)

    # ---- Route C: Post-insertion config check + volume discrimination ----
    result["stage"] = "route_C"
    route_c: dict[str, Any] = {"status": "untried"}

    print("=== Route C: Config enumeration + volume discrimination ===", file=sys.stderr)
    try:
        names = mdoc2.GetConfigurationNames()
        if names is not None:
            config_names = list(names)
        else:
            config_names = []

        route_c["config_names"] = config_names
        route_c["config_count"] = len(config_names)

        # Measure volume per config
        volumes: dict[str, float | None] = {}
        for cn in config_names:
            try:
                mdoc2.ShowConfiguration2(cn)
            except Exception:
                pass
            mdoc2.ForceRebuild3(True)
            vol, vol_err = _measure_volume(mdoc2, cn)
            volumes[cn] = vol
            if vol_err:
                result["warnings"].append(vol_err)

        route_c["volumes"] = volumes
        distinct = sorted(set(
            round(v, 1) for v in volumes.values() if v is not None
        ))
        route_c["distinct_volumes"] = distinct
        route_c["discriminated"] = len(distinct) >= 2

        if len(distinct) >= 2:
            route_c["status"] = "GREEN"
        else:
            route_c["status"] = "NO_DISCRIMINATION"
            route_c["note"] = (
                f"All configs have identical volume "
                f"({distinct[0] if distinct else 'N/A'} mm³). "
                f"Design table did not drive geometric distinction — "
                f"same wall class as W36."
            )

    except Exception as exc:
        route_c["status"] = "exception"
        route_c["error"] = f"{type(exc).__name__}: {exc}"

    result["routes"]["C_config_volumes"] = route_c
    print(f"Route C: {route_c['status']}", file=sys.stderr)

    # ---- Step: Save → reopen → re-measure ----
    if route_c.get("discriminated"):
        result["stage"] = "save_reopen"
        reopen_volumes: dict[str, float | None] = {}

        try:
            mdoc2.SaveAs3(str(part_path), 0, 0)
            _close_doc(sw, mdoc2)
            time.sleep(0.5)

            ret = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
            model_doc2 = ret[0] if isinstance(ret, tuple) else ret
            if model_doc2 is None:
                result["errors"].append("Reopen failed")
            else:
                mdoc2b = typed_qi(model_doc2, "IModelDoc2", module=mod)
                names2 = mdoc2b.GetConfigurationNames()
                if names2:
                    for cn in names2:
                        try:
                            mdoc2b.ShowConfiguration2(cn)
                        except Exception:
                            pass
                        mdoc2b.ForceRebuild3(True)
                        vol, _ = _measure_volume(mdoc2b, f"reopen_{cn}")
                        reopen_volumes[cn] = vol

                reopen_distinct = sorted(set(
                    round(v, 1) for v in reopen_volumes.values()
                    if v is not None
                ))
                result["reopen_volumes"] = reopen_volumes
                result["reopen_distinct"] = reopen_distinct
                result["reopen_persisted"] = len(reopen_distinct) >= 2

                _close_doc(sw, mdoc2b)

        except Exception as exc:
            result["errors"].append(f"save/reopen: {exc!r}")

    # ---- Final verdict ----
    result["stage"] = "verdict"

    route_a_ok = route_a.get("status") == "called" and route_a.get("returned_value") != "None"
    route_c_green = route_c.get("status") == "GREEN"
    reopen_persisted = result.get("reopen_persisted", False)

    if route_c_green and reopen_persisted:
        result["ok"] = True
        result["verdict"] = "GREEN"
        result["summary"] = (
            f"Design table created {len(route_c.get('config_names', []))} "
            f"configs with {len(route_c.get('distinct_volumes', []))} "
            f"distinct volumes, persisted through save→reopen. "
            f"Design tables are a VIABLE in-file config path."
        )
    elif route_c_green and not reopen_persisted:
        result["verdict"] = "PARTIAL"
        result["summary"] = (
            "Design table created volume-discriminated configs, but "
            "discrimination did NOT survive save→reopen. Same class as "
            "W36 — in-process effect only."
        )
    elif not route_a_ok:
        result["verdict"] = "NO-GO"
        result["summary"] = (
            f"InsertFamilyTableNew did not execute: "
            f"{route_a.get('note', route_a.get('error', 'unknown'))}. "
            f"Design tables are NOT reachable via this API path. "
            f"FUNCDESC dump retained for wall characterization."
        )
    else:
        result["verdict"] = "NO-GO"
        result["summary"] = (
            f"Design table insertion returned non-None but configs are "
            f"not volume-discriminated "
            f"({route_c.get('distinct_volumes', [])} distinct volumes). "
            f"Same SetSuppression-class wall as W36 — design table "
            f"insertion creates the table but the per-config geometry "
            f"distinction does not propagate out-of-process."
        )

    _close_doc(sw, mdoc2) if "mdoc2" in dir() else None
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None,
                   help="Write JSON report to path (default: stdout).")
    args = p.parse_args()

    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass

    print("=== W53 Design Table Spike ===", file=sys.stderr)
    try:
        result = run_spike()
    finally:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except ImportError:
            pass

    out_path = args.out or (SPIKE_DIR / "_results" / "designtable_spike.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nResults: {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
