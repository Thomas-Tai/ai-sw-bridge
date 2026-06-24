"""
Spike v0.16 / S-MATE — assembly mate creation via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the SOLIDWORKS assembly mate API out-of-process:
  - Open/create a blank Assembly
  - Insert two components (parts) into the assembly
  - IAssemblyDoc.AddMate5(entity1, entity2, mate_type, align, ...)
  - Alternative: CreateDefinition(swFmMate) -> IMateFeatureData -> CreateFeature

The goal is to prove the mate-creation pipeline works end-to-end
out-of-process before building assembly support in the spec/builder.

Background
----------
Assemblies are not yet supported in the spec schema. This spike probes
two API paths:

  Path A (legacy): IAssemblyDoc.AddMate5 — direct mate creation with
    entity references. Requires pre-selected faces/edges/planes.

  Path B (modern): FeatureManager.CreateDefinition(swFmMate) ->
    IMateFeatureData -> set entities -> CreateFeature.
    The swFmMate constant is unknown; scan 0..127 to discover.

Risks: entity selection marshaling, mate alignment constants,
AddMate5 arg count (13+ args — known pywin32 marshaling wall).

Verdict
-------
PASS    : mate created between two components, assembly saved.
PARTIAL : assembly opens, components inserted, but mate creation fails —
          narrow the entity selection or mate type constants.
FAIL    : assembly API unreachable out-of-process — defer.

Prereq: SOLIDWORKS running. Creates own parts + assembly (non-destructive).

Usage
-----
    python spikes/v0_16/spike_mate.py --out report.json
    python spikes/v0_16/spike_mate.py --mode vba
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_DEFAULT_TEMPLATE_ASSEMBLY = 10
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2

# Mate type constants (swMateType_e) — from SW API docs
SW_MATE_COINCIDENT = 0
SW_MATE_CONCENTRIC = 1
SW_MATE_DISTANCE = 5

# Mate alignment (swMateAlignment_e)
SW_MATE_ALIGN_ALIGNED = 0
SW_MATE_ALIGN_ANTI_ALIGNED = 1


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _capture(fn: Any, label: str = "") -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "_val": val,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _build_and_save_part(sw: Any, path: Path, name: str) -> dict[str, Any]:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"built": False, "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    if not build.get("built"):
        _try_close(sw, doc)
        return {**build, "reason": "build_single_box failed"}
    try:
        doc.SaveAs3(str(path), 0, 0)
    except Exception as e:  # noqa: BLE001
        _try_close(sw, doc)
        return {"built": False, "reason": f"SaveAs3 raised: {e}"}
    _try_close(sw, doc)
    return {"built": True, "path": str(path), "name": name}


def _scan_create_definition(fm: Any, scan_range: range = range(20)) -> dict[str, Any]:
    """Scan CreateDefinition(i) for i in scan_range to find swFmMate."""
    results: dict[int, str] = {}
    for i in scan_range:
        try:
            data = fm.CreateDefinition(i)
            if data is not None and not isinstance(data, int):
                type_name = _tag(data)
                iface = None
                for attr in ("GetTypeName", "GetTypeName2"):
                    try:
                        m = getattr(data, attr)
                        iface = str(m() if callable(m) else m)
                        break
                    except Exception:  # noqa: BLE001
                        continue
                results[i] = f"{type_name}({iface})" if iface else type_name
            else:
                results[i] = f"None/int({data})"
        except Exception as e:  # noqa: BLE001
            results[i] = f"EXCEPTION: {type(e).__name__}"
    return results


def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_a_path = tmp_dir / "spike_mate_part_a.sldprt"
    part_b_path = tmp_dir / "spike_mate_part_b.sldprt"
    asm_path = tmp_dir / "spike_mate.sldasm"
    for p in (part_a_path, part_b_path, asm_path):
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    # --- 1. Build two parts --------------------------------------------------
    part_a = _build_and_save_part(sw, part_a_path, "PartA")
    part_b = _build_and_save_part(sw, part_b_path, "PartB")
    result["part_a"] = part_a
    result["part_b"] = part_b
    if not part_a.get("built") or not part_b.get("built"):
        return {**result, "overall": "FAIL", "reason": "could not build test parts"}

    # --- 2. Open a blank assembly --------------------------------------------
    asm_template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_ASSEMBLY)
    asm_doc = sw.NewDocument(asm_template, 0, 0.0, 0.0)
    if asm_doc is None:
        return {
            **result,
            "overall": "FAIL",
            "reason": "NewDocument(assembly) returned None",
        }

    result["assembly_opened"] = True
    result["assembly_type"] = _tag(asm_doc)

    # --- 3. Insert components -----------------------------------------------
    probes: dict[str, Any] = {}

    probes["insert_part_a"] = _capture(
        lambda: asm_doc.AddComponent5(
            str(part_a_path), 0, "", False, "", 0.0, 0.0, 0.0
        ),
        "AddComponent5(part_a)",
    )
    probes["insert_part_b"] = _capture(
        lambda: asm_doc.AddComponent5(
            str(part_b_path), 0, "", False, "", 0.1, 0.0, 0.0
        ),
        "AddComponent5(part_b)",
    )

    # --- 4. Scan CreateDefinition for swFmMate --------------------------------
    fm = asm_doc.FeatureManager
    probes["create_definition_scan"] = _scan_create_definition(fm, range(30))
    result["probes"] = probes

    # --- 5. Try AddMate5 (legacy path) ---------------------------------------
    mate_result = _capture(
        lambda: asm_doc.AddMate5(
            SW_MATE_COINCIDENT,
            SW_MATE_ALIGN_ALIGNED,
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            0,
            0,
            False,
            False,
            0,
            None,
        ),
        "AddMate5",
    )
    probes["AddMate5"] = mate_result

    # --- 6. Save assembly ----------------------------------------------------
    try:
        asm_doc.SaveAs3(str(asm_path), 0, 0)
        result["assembly_saved"] = asm_path.exists()
        result["assembly_path"] = str(asm_path)
    except Exception as e:  # noqa: BLE001
        result["assembly_saved"] = False
        result["save_error"] = f"{type(e).__name__}: {e}"

    # --- Cleanup -------------------------------------------------------------
    _try_close(sw, asm_doc)
    if not keep_file:
        for p in (part_a_path, part_b_path, asm_path):
            try:
                p.unlink()
            except OSError:
                pass
        result["cleanup"] = "closed doc + removed temp files"
    else:
        result["cleanup"] = f"kept files: {part_a_path}, {part_b_path}, {asm_path}"

    # --- Verdict -------------------------------------------------------------
    mate_ok = mate_result["status"] == "OK" and mate_result.get("_val") is not None
    asm_saved = result.get("assembly_saved", False)

    if mate_ok and asm_saved:
        overall = "PASS"
        interp = "mate created + assembly saved -> build the assembly handler"
    elif asm_doc is not None:
        overall = "PARTIAL"
        interp = (
            "assembly opened, components inserted, but mate failed "
            "-> run --mode vba to isolate entity selection or arg marshaling"
        )
    else:
        overall = "FAIL"
        interp = "assembly API unreachable out-of-process -> defer"

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-MATE VBA oracle.
' Paste into an Assembly document module with 2 components inserted.
Option Explicit
Sub ProbeMate()
    Dim swApp As SldWorks.SldWorks
    Dim Asm   As SldWorks.AssemblyDoc
    Dim Mate  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Asm   = swApp.ActiveDoc
    ' AddMate5: mateType, alignment, flip, dist, absAng, ...
    Set Mate = Asm.AddMate5(0, 0, False, 0, 0, 0, 0, 0, 0, 0, 0, False, False, 0, Nothing)
    If Mate Is Nothing Then
        MsgBox "AddMate5 returned Nothing"
    Else
        MsgBox "Mate created: " & Mate.Name
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_mate.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
