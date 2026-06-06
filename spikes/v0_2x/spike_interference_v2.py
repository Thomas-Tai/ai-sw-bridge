"""Spike W27 / INTERFERENCE — go/no-go probe (perception axis).

Tests whether IAssemblyDoc.InterferenceDetectionManager (dispid 126, property-get)
→ IInterferenceDetectionMgr can detect physical clashes between components.

Pipeline under test:
  1. Create two 20mm block parts (reuse one part twice).
  2. OpenDoc6 (mandatory pre-open) → AddComponent4 at overlapping offset (10mm).
  3. InterferenceDetectionManager → configure options → GetInterferenceCount.
  4. Enumerate GetInterferences() → IInterference (Components + Volume).
  5. NEGATIVE CONTROL: re-place 50mm apart → count == 0.

DISCRIMINATION GATE: overlap → count>0 + clean enumeration + positive volume;
clearance → count==0. Anything else = NO-GO.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_interference_v2.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "interference.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

BOX_SIZE_M = 0.020  # 20 mm cube
OVERLAP_OFFSET_M = 0.010  # 10 mm → 10mm overlap
CLEARANCE_OFFSET_M = 0.050  # 50 mm → no overlap
SW_DOC_PART = 1


# ── Helpers ────────────────────────────────────────────────────────────────

def _find_asm_template() -> str | None:
    import glob
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.asmdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _retry(fn, *args, retries=3, delay=5, label=""):
    """Retry a COM call with backoff."""
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as exc:
            if attempt < retries - 1:
                print(f"  [{label}] Attempt {attempt+1} failed: {exc!r}, retrying in {delay}s …")
                time.sleep(delay)
            else:
                raise


def _make_block_part(sw_typed: Any, mod: Any, path: str) -> str | None:
    """Create a 20mm cube part. Returns error string or None on success."""
    try:
        doc = _retry(
            sw_typed.NewDocument,
            r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
            0, 0, 0,
            retries=3, delay=5, label="part_new",
        )
        if doc is None:
            return "NewDocument(part) returned None"
        dt = typed(doc, "IModelDoc2", module=mod)

        dt.SketchManager.InsertSketch(True)
        half = BOX_SIZE_M / 2.0
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half, half, 0)
        dt.SketchManager.InsertSketch(True)

        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True, False, False, 0, 0,
            BOX_SIZE_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0,
            False,
        )
        if feat is None:
            return "FeatureExtrusion2 returned None"

        _retry(dt.SaveAs3, path, 0, 2, retries=2, delay=3, label="part_save")
        # NOTE: Do NOT close the part doc here — closing can corrupt the COM channel.
        # The doc will be reused by OpenDoc6 in _build_assembly.
        # Leave it open until end of spike.
        return None, dt  # return the doc so we can close it later
    except Exception as exc:
        return f"exception: {exc!r}", None


def _close_all(sw_typed: Any) -> None:
    try:
        sw_typed.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(1)


def _build_assembly(
    sw_typed: Any, mod: Any,
    part_path: str, asm_template: str,
    offset_m: float, label: str,
) -> tuple[Any, Any, Any, str | None]:
    """Open new assembly, place two copies of *part_path* at *offset_m*.

    Returns (asm_doc, asm_typed, doc_typed, error).
    """
    # Pre-open the part (MANDATORY — the W8 lesson)
    print(f"  [{label}] OpenDoc6(part) …")
    try:
        open_ret = sw_typed.OpenDoc6(part_path, SW_DOC_PART, 1, "", 0, 0)
        part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
    except Exception as exc:
        return None, None, None, f"OpenDoc6(part) exception: {exc!r}"
    if part_doc is None:
        return None, None, None, "OpenDoc6(part) returned None"
    print(f"  [{label}] Part doc opened")

    print(f"  [{label}] NewDocument(asm) …")
    try:
        asm_doc = sw_typed.NewDocument(asm_template, 0, 0, 0)
    except Exception as exc:
        return None, None, None, f"NewDocument(asm) exception: {exc!r}"
    if asm_doc is None:
        return None, None, None, "NewDocument(asm) returned None"
    print(f"  [{label}] Assembly doc created")

    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
    except Exception as exc:
        return None, None, None, f"typed(IAssemblyDoc) exception: {exc!r}"
    print(f"  [{label}] IAssemblyDoc typed OK")

    try:
        doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
    except Exception as exc:
        return None, None, None, f"typed(IModelDoc2) exception: {exc!r}"

    print(f"  [{label}] AddComponent4(A) …")
    try:
        comp_a = asm_typed.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    except Exception as exc:
        return None, None, None, f"AddComponent4(A) exception: {exc!r}"
    if comp_a is None or isinstance(comp_a, int):
        return None, None, None, "AddComponent4(A) returned None"
    print(f"  [{label}] Component A placed")

    print(f"  [{label}] AddComponent4(B) …")
    try:
        comp_b = asm_typed.AddComponent4(part_path, "", offset_m, 0.0, 0.0)
    except Exception as exc:
        return None, None, None, f"AddComponent4(B) exception: {exc!r}"
    if comp_b is None or isinstance(comp_b, int):
        return None, None, None, "AddComponent4(B) returned None"
    print(f"  [{label}] Placed A @origin, B @{offset_m*1000:.0f}mm")

    print(f"  [{label}] ForceRebuild3 …")
    try:
        doc_typed.ForceRebuild3(True)
    except Exception as exc:
        print(f"  [{label}] ForceRebuild3 exc: {exc!r}")

    time.sleep(2)  # solver settle
    return asm_doc, asm_typed, doc_typed, None


def _detect_interference(
    asm_typed: Any, mod: Any, label: str,
) -> tuple[int | None, list[dict[str, Any]], list[str]]:
    """Run interference detection on an open assembly.

    Returns (count, interferences_list, errors).
    """
    errors: list[str] = []
    interferences: list[dict[str, Any]] = []

    # ── Acquire manager (dispid 126, property-get) ────────────────────
    mgr = None
    try:
        mgr = asm_typed.InterferenceDetectionManager
    except Exception as exc:
        errors.append(f"InterferenceDetectionManager access: {exc!r}")
        return None, interferences, errors

    if mgr is None:
        errors.append("InterferenceDetectionManager returned None")
        return None, interferences, errors

    print(f"  [{label}] Got mgr: {type(mgr).__name__}")

    # ── Typed wrapper + configure options ──────────────────────────────
    mgr_typed = None
    try:
        mgr_typed = typed(mgr, "IInterferenceDetectionMgr", module=mod)
        mgr_typed.TreatCoincidenceAsInterference = False
        mgr_typed.ShowIgnoredInterferences = False
        mgr_typed.TreatSubAssembliesAsComponents = True
        mgr_typed.IncludeMultibodyPartInterferences = True
        mgr_typed.MakeInterferingPartsTransparent = False
        mgr_typed.CreateFastenersFolder = False
        mgr_typed.IgnoreHiddenBodies = True
        print(f"  [{label}] Typed options configured")
    except Exception as exc:
        errors.append(f"typed mgr/options: {exc!r}")
        # Late-bound fallback
        try:
            mgr.TreatCoincidenceAsInterference = False
            mgr.ShowIgnoredInterferences = False
            mgr.IgnoreHiddenBodies = True
        except Exception as exc2:
            errors.append(f"late-bound options: {exc2!r}")

    # ── GetInterferenceCount ───────────────────────────────────────────
    count = None
    caller = mgr_typed if mgr_typed is not None else mgr
    try:
        count = caller.GetInterferenceCount()
        print(f"  [{label}] GetInterferenceCount = {count}")
    except Exception as exc:
        errors.append(f"GetInterferenceCount: {exc!r}")
        return None, interferences, errors

    count_val = count
    if isinstance(count_val, tuple):
        count_val = count_val[0]
    int_count = int(count_val) if count_val is not None else 0

    # ── Enumerate if count > 0 ────────────────────────────────────────
    if int_count > 0:
        try:
            intf_array = caller.GetInterferences()
            if intf_array is None:
                errors.append("GetInterferences() returned None")
            else:
                # Could be tuple or list of COM objects
                items = intf_array
                if not isinstance(items, (list, tuple)):
                    items = (items,)
                for idx, intf_obj in enumerate(items):
                    entry = _read_interference(intf_obj, mod, idx)
                    interferences.append(entry)
                print(f"  [{label}] Enumerated {len(interferences)} interference(s)")
        except Exception as exc:
            errors.append(f"GetInterferences enumeration: {exc!r}")

    # ── Done ───────────────────────────────────────────────────────────
    try:
        caller.Done()
    except Exception:
        pass

    return int_count, interferences, errors


def _read_interference(
    intf_obj: Any, mod: Any, idx: int,
) -> dict[str, Any]:
    """Read one IInterference object: Components + Volume."""
    entry: dict[str, Any] = {
        "index": idx,
        "volume_m3": None,
        "component_count": None,
        "component_names": [],
        "errors": [],
    }

    # Volume (dispid 2, DOUBLE property-get)
    try:
        vol = intf_obj.Volume
        if callable(vol):
            vol = vol()
        entry["volume_m3"] = float(vol) if vol is not None else None
    except Exception as exc:
        entry["errors"].append(f"Volume: {exc!r}")

    # GetComponentCount (dispid 4, method)
    try:
        cc = intf_obj.GetComponentCount
        if callable(cc):
            cc = cc()
        entry["component_count"] = int(cc) if cc is not None else None
    except Exception as exc:
        entry["errors"].append(f"GetComponentCount: {exc!r}")

    # Components (dispid 3, VARIANT property-get → array of IComponent2)
    try:
        comps = intf_obj.Components
        if callable(comps):
            comps = comps()
        if comps is not None:
            if not isinstance(comps, (list, tuple)):
                comps = (comps,)
            for c in comps:
                try:
                    name = c.Name2 if hasattr(c, "Name2") else c.Name
                    if callable(name):
                        name = name()
                    entry["component_names"].append(str(name))
                except Exception:
                    entry["component_names"].append("<error>")
    except Exception as exc:
        entry["errors"].append(f"Components: {exc!r}")

    # Also try typed_qi for richer access
    try:
        intf_typed = typed(intf_obj, "IInterference", module=mod)
        if entry["volume_m3"] is None:
            try:
                entry["volume_m3"] = float(intf_typed.Volume)
            except Exception:
                pass
        if entry["component_count"] is None:
            try:
                entry["component_count"] = int(intf_typed.GetComponentCount())
            except Exception:
                pass
    except Exception as exc:
        entry["errors"].append(f"typed_qi(IInterference): {exc!r}")

    return entry


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "overlap_count": None,
        "negative_control_count": None,
        "interference_enumeration": None,
        "recipe": None,
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W27_")
    part_path = str(Path(tmpdir) / "block_20mm.sldprt")
    asm_overlap_path = str(Path(tmpdir) / "overlap_test.sldasm")
    asm_clearance_path = str(Path(tmpdir) / "clearance_test.sldasm")

    try:
        # ── Step 1: Create block part ──────────────────────────────────
        print("[S1] Creating 20mm block part …")
        err, part_doc = _make_block_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print(f"[S1] Part saved: {part_path}")
        # part_doc stays OPEN — don't close until end of spike

        asm_templ = _find_asm_template()
        if not asm_templ:
            result["errors"].append("no ASMDOT template found")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # ── Step 2: OVERLAP assembly — count + enumerate ───────────────
        print("[S1] Building OVERLAP assembly (2 cubes, 10mm offset) …")

        asm_doc, asm_typed, doc_typed, build_err = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            OVERLAP_OFFSET_M, "overlap",
        )
        if build_err:
            result["errors"].append(f"overlap build: {build_err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        overlap_count, overlap_interferences, overlap_errors = _detect_interference(
            asm_typed, mod, "overlap",
        )
        result["overlap_count"] = overlap_count
        result["interference_enumeration"] = {
            "interferences": overlap_interferences,
            "errors": overlap_errors,
        }
        result["errors"].extend(overlap_errors)

        print(f"[S1] Overlap count={overlap_count}, "
              f"enumerated {len(overlap_interferences)} interference(s)")

        # Leave overlap assembly OPEN — closing corrupts COM channel
        # Just save it for persistence
        try:
            doc_typed.SaveAs3(asm_overlap_path, 0, 2)
            print(f"[S1] Overlap assembly saved")
        except Exception as exc:
            print(f"[S1] SaveAs3 overlap: {exc!r}")

        # ── Step 3: NEGATIVE CONTROL — clearance assembly ──────────────
        print("[S1] Building CLEARANCE assembly (2 cubes, 50mm offset) …")

        asm_doc2, asm_typed2, doc_typed2, build_err2 = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            CLEARANCE_OFFSET_M, "clearance",
        )
        if build_err2:
            result["errors"].append(f"clearance build: {build_err2}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        clearance_count, _, clearance_errors = _detect_interference(
            asm_typed2, mod, "clearance",
        )
        result["negative_control_count"] = clearance_count
        result["errors"].extend(clearance_errors)

        print(f"[S1] Clearance count={clearance_count}")

        # Save clearance assembly (leave open until finally)
        try:
            doc_typed2.SaveAs3(asm_clearance_path, 0, 2)
            print(f"[S1] Clearance assembly saved")
        except Exception as exc:
            print(f"[S1] SaveAs3 clearance: {exc!r}")

        # ── Step 4: Confirmed recipe ───────────────────────────────────
        result["recipe"] = {
            "manager_access": (
                "typed(asm_doc, 'IAssemblyDoc').InterferenceDetectionManager "
                "(dispid 126, property-get)"
            ),
            "manager_interface": "IInterferenceDetectionMgr",
            "option_props": [
                "TreatCoincidenceAsInterference",
                "ShowIgnoredInterferences",
                "TreatSubAssembliesAsComponents",
                "IncludeMultibodyPartInterferences",
                "MakeInterferingPartsTransparent",
                "CreateFastenersFolder",
                "NonInterferingComponentDisplay",
                "IgnoreHiddenBodies",
            ],
            "count_method": "GetInterferenceCount()",
            "enum_method": "GetInterferences() → IInterference[]",
            "interference_props": [
                "Volume (dispid 2, DOUBLE property-get)",
                "Components (dispid 3, VARIANT property-get)",
                "GetComponentCount (dispid 4, method)",
            ],
            "cleanup": "Done()",
        }

        # ── DISCRIMINATION GATE ────────────────────────────────────────
        oc = result["overlap_count"]
        cc = result["negative_control_count"]
        enum = result["interference_enumeration"]

        if oc is not None and oc > 0 and cc is not None and cc == 0:
            has_volume = False
            has_components = False
            if enum and "interferences" in enum:
                for intf in enum["interferences"]:
                    if intf.get("volume_m3") is not None and intf["volume_m3"] > 0:
                        has_volume = True
                    if intf.get("component_names") and len(intf["component_names"]) >= 2:
                        has_components = True
            if has_volume and has_components:
                result["verdict"] = "GREEN"
            else:
                result["verdict"] = "PARTIAL"
                result["errors"].append(
                    f"count>0 but enumeration incomplete: "
                    f"has_volume={has_volume}, has_components={has_components}"
                )
        elif oc is not None and oc == 0:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                "overlap assembly returned 0 interferences — "
                "detector cannot distinguish clash from clearance"
            )
        elif cc is not None and cc > 0:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                f"clearance assembly returned {cc} interferences — false positive"
            )
        else:
            result["verdict"] = "NO-GO"
            result["errors"].append(
                f"unexpected counts: overlap={oc}, clearance={cc}"
            )

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["verdict"] = "NO-GO"
    finally:
        # Cleanup: close all docs
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[S1] VERDICT: {result['verdict']}")
        print(f"[S1] overlap_count={result['overlap_count']}, "
              f"negative_control_count={result['negative_control_count']}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[S1] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
