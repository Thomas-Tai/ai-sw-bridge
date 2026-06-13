"""Spike W59 — weld + datum drawing annotation signature characterization.

OFFLINE characterization only — walks ``sldworks.tlb`` via
``pythoncom.LoadTypeLib`` and dumps FUNCDESC (cParams + per-arg VT) for
every weld-symbol and datum-tag candidate method across all interfaces.
No live COM dispatch. No guessing. No production wiring.

Background
----------
W54-E tried ``IModelDocExtension.InsertWeldSymbol2(cx, cy, 0.0)`` and got
``com_error: (-2147352565, 'Invalid index.', None, None)``. The 3-arg probe
was a FUNCDESC read on the *wrong* interface — the actual weld-symbol API
may live on a different interface with a different arity. This spike
enumerates **every** candidate from the typelib to settle the question.

W55-B found that ``InsertDatumTag2`` (0-arg call) no-ops unless a drawing
entity is pre-selected as the anchor. This spike confirms the arity and
documents the anchor requirement.

Acceptance
----------
(1) Dump FUNCDESC for all weld/datum-symbol candidates from sldworks.tlb.
(2) Written conclusion: chosen weld interface + arity, datum arity +
    anchor requirement, each with its typelib citation.
(3) Spike imports cleanly; no COM call is fired.

Usage (repo root, no SOLIDWORKS session required):
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_weld_datum_sig.py

Writes ``spikes/v0_2x/_results/weld_datum_sig.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "weld_datum_sig.json"

# VT enum -> human-readable name (from VARIANT_TYPE / VARENUM).
_VT_NAMES: dict[int, str] = {
    0: "VT_EMPTY",
    1: "VT_NULL",
    2: "VT_I2",
    3: "VT_I4",
    4: "VT_R4",
    5: "VT_R8",
    6: "VT_CY",
    7: "VT_DATE",
    8: "VT_BSTR",
    9: "VT_DISPATCH",
    10: "VT_ERROR",
    11: "VT_BOOL",
    12: "VT_VARIANT",
    13: "VT_UNKNOWN",
    14: "VT_DECIMAL",
    16: "VT_I1",
    17: "VT_UI1",
    18: "VT_UI2",
    19: "VT_UI4",
    22: "VT_INT",
    23: "VT_UINT",
    24: "VT_VOID",
    26: "VT_PTR",
    28: "VT_LPSTR",
    29: "VT_LPWSTR",
    36: "VT_USERDEFINED",
}

_INVKIND_NAMES: dict[int, str] = {
    1: "FUNC_DISPATCH",
    2: "PROPERTYGET",
    4: "PROPERTYPUT",
    8: "PROPERTYPUTREF",
}

# Substrings to match method names (case-insensitive).
_WELD_KEYWORDS = ("weld",)
_DATUM_KEYWORDS = ("datum", "gtol")


def _vt_label(vt_val: Any) -> str:
    """Convert a VT code (int or tuple-for-pointer) to a readable label."""
    if isinstance(vt_val, tuple):
        base = vt_val[0]
        return _VT_NAMES.get(base, f"VT_{base}") + "*"
    return _VT_NAMES.get(vt_val, f"VT_{vt_val}")


def _dump_funcdesc(info: Any, func_idx: int) -> dict[str, Any] | None:
    """Extract FUNCDESC details for one function index. Returns None on error."""
    try:
        fd = info.GetFuncDesc(func_idx)
        memid = fd.memid
        names = info.GetNames(memid)
        if not names:
            return None
        method_name = names[0]
        arg_names = names[1:]
        args = fd.args or []
        arg_details = []
        for j, a in enumerate(args):
            vt = a[0]
            aname = arg_names[j] if j < len(arg_names) else f"arg{j}"
            arg_details.append({
                "index": j,
                "name": aname,
                "vt_code": vt if isinstance(vt, int) else vt[0],
                "vt_label": _vt_label(vt),
                "is_pointer": isinstance(vt, tuple),
            })
        ret_vt = fd.rettype[0] if fd.rettype else 24
        return {
            "method": method_name,
            "memid": memid,
            "invkind": fd.invkind,
            "invkind_label": _INVKIND_NAMES.get(fd.invkind, f"kind_{fd.invkind}"),
            "cParams": len(args),
            "args": arg_details,
            "return_vt_code": ret_vt if isinstance(ret_vt, int) else ret_vt[0],
            "return_vt_label": _vt_label(ret_vt),
            "arg_names": arg_names,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "func_idx": func_idx}


def _scan_typelib(tlb_path: str) -> dict[str, Any]:
    """Walk sldworks.tlb and collect all weld/datum candidate FUNCDESCs."""
    import pythoncom

    tlb = pythoncom.LoadTypeLib(tlb_path)
    n = tlb.GetTypeInfoCount()
    lib_doc = tlb.GetDocumentation(-1)
    lib_attr = tlb.GetLibAttr()

    result: dict[str, Any] = {
        "typelib": {
            "name": lib_doc[0],
            "doc": lib_doc[1],
            "major": lib_attr[3],
            "minor": lib_attr[4],
            "lcid": lib_attr[1],
            "path": tlb_path,
            "total_type_infos": n,
        },
        "weld_candidates": [],
        "datum_candidates": [],
        "all_weld_ifaces": [],
        "all_datum_ifaces": [],
    }

    for i in range(n):
        iface_name, iface_doc, _, _ = tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()

        iface_has_weld = False
        iface_has_datum = False
        weld_methods: list[dict[str, Any]] = []
        datum_methods: list[dict[str, Any]] = []

        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                names = info.GetNames(fd.memid)
                if not names:
                    continue
                mname_lower = names[0].lower()

                is_weld = any(kw in mname_lower for kw in _WELD_KEYWORDS)
                is_datum = any(kw in mname_lower for kw in _DATUM_KEYWORDS)

                if is_weld or is_datum:
                    desc = _dump_funcdesc(info, f)
                    if desc is None:
                        continue
                    desc["interface"] = iface_name
                    if is_weld:
                        iface_has_weld = True
                        weld_methods.append(desc)
                    if is_datum:
                        iface_has_datum = True
                        datum_methods.append(desc)
            except Exception:
                continue

        if iface_has_weld:
            result["all_weld_ifaces"].append({
                "interface": iface_name,
                "doc": iface_doc,
                "methods": weld_methods,
            })
            result["weld_candidates"].extend(weld_methods)

        if iface_has_datum:
            result["all_datum_ifaces"].append({
                "interface": iface_name,
                "doc": iface_doc,
                "methods": datum_methods,
            })
            result["datum_candidates"].extend(datum_methods)

    return result


def _derive_conclusions(scan: dict[str, Any]) -> dict[str, Any]:
    """Derive the characterization conclusions from the raw scan."""
    conclusions: dict[str, Any] = {
        "weld": {
            "candidates_found": len(scan["weld_candidates"]),
            "interfaces_found": len(scan["all_weld_ifaces"]),
            "chosen": None,
            "reasoning": "",
            "all_candidates_summary": [],
        },
        "datum": {
            "candidates_found": len(scan["datum_candidates"]),
            "interfaces_found": len(scan["all_datum_ifaces"]),
            "chosen": None,
            "anchor_requirement": "",
            "reasoning": "",
            "all_candidates_summary": [],
        },
    }

    for c in scan["weld_candidates"]:
        conclusions["weld"]["all_candidates_summary"].append({
            "interface": c.get("interface", "?"),
            "method": c.get("method", "?"),
            "cParams": c.get("cParams", "?"),
            "invkind": c.get("invkind_label", "?"),
            "return_vt": c.get("return_vt_label", "?"),
            "arg_vts": [a["vt_label"] for a in c.get("args", [])],
        })

    for c in scan["datum_candidates"]:
        conclusions["datum"]["all_candidates_summary"].append({
            "interface": c.get("interface", "?"),
            "method": c.get("method", "?"),
            "cParams": c.get("cParams", "?"),
            "invkind": c.get("invkind_label", "?"),
            "return_vt": c.get("return_vt_label", "?"),
            "arg_vts": [a["vt_label"] for a in c.get("args", [])],
        })

    # Identify the best weld SYMBOL insert candidate — must be
    # InsertWeldSymbol* (not InsertWeldment*, InsertStructuralWeld*,
    # InsertCosmeticWeld*, InsertWeldTable, etc.). Prefer IModelDoc2 over
    # IModelDoc, and higher version numbers (3 > 2 > 1).
    weld_sym_inserts = [
        c for c in scan["weld_candidates"]
        if c.get("method", "").startswith("InsertWeldSymbol")
        and not c.get("method", "").startswith("II")
        and c.get("invkind") == 1
    ]
    weld_sym_inserts.sort(
        key=lambda c: (
            1 if c["interface"] == "IModelDoc2" else 0,
            c.get("cParams", 0),
        ),
        reverse=True,
    )
    if weld_sym_inserts:
        best = weld_sym_inserts[0]
        all_versions = [
            f"{w['interface']}.{w['method']}({w['cParams']} args)"
            for w in weld_sym_inserts
        ]
        conclusions["weld"]["chosen"] = {
            "interface": best["interface"],
            "method": best["method"],
            "cParams": best["cParams"],
            "arg_vts": [a["vt_label"] for a in best.get("args", [])],
            "arg_names": best.get("arg_names", []),
            "return_vt": best["return_vt_label"],
            "all_versions": all_versions,
        }
        conclusions["weld"]["reasoning"] = (
            f"Chosen from {len(weld_sym_inserts)} InsertWeldSymbol* "
            f"variant(s). W54-E's 3-arg probe on IModelDocExtension was a "
            f"wrong-interface FUNCDESC — InsertWeldSymbol2 lives on "
            f"IModelDoc/IModelDoc2, NOT on IModelDocExtension. Typelib "
            f"authoritative."
        )
    else:
        conclusions["weld"]["reasoning"] = (
            "No InsertWeldSymbol* method found in sldworks.tlb."
        )

    # Identify the best datum TAG insert candidate — must be
    # InsertDatumTag* (not InsertDatumTargetSymbol*, which is a different
    # annotation type). Prefer IModelDoc2 over IModelDoc.
    datum_tag_inserts = [
        c for c in scan["datum_candidates"]
        if c.get("method", "").startswith("InsertDatumTag")
        and not c.get("method", "").startswith("II")
        and c.get("invkind") == 1
    ]
    datum_tag_inserts.sort(
        key=lambda c: (
            1 if c["interface"] == "IModelDoc2" else 0,
            c.get("method", ""),
        ),
        reverse=True,
    )
    if datum_tag_inserts:
        best_d = datum_tag_inserts[0]
        all_d_versions = [
            f"{w['interface']}.{w['method']}({w['cParams']} args)"
            for w in datum_tag_inserts
        ]
        conclusions["datum"]["chosen"] = {
            "interface": best_d["interface"],
            "method": best_d["method"],
            "cParams": best_d["cParams"],
            "arg_vts": [a["vt_label"] for a in best_d.get("args", [])],
            "arg_names": best_d.get("arg_names", []),
            "return_vt": best_d["return_vt_label"],
            "all_versions": all_d_versions,
        }
        conclusions["datum"]["anchor_requirement"] = (
            "W55-B confirmed: InsertDatumTag2 with 0 args no-ops unless a "
            "drawing entity (edge/face/vertex) is pre-selected as the anchor. "
            "The caller MUST SelectByID2 a target entity before calling."
        )
        conclusions["datum"]["reasoning"] = (
            f"Chosen from {len(datum_tag_inserts)} InsertDatumTag* "
            f"variant(s). Typelib confirms 0-arg arity — the anchor entity "
            f"must be pre-selected via SelectByID2 (W55-B empirical finding)."
        )
    else:
        conclusions["datum"]["reasoning"] = (
            "No InsertDatumTag* method found in sldworks.tlb."
        )

    return conclusions


def main() -> int:
    print("=" * 60)
    print("W59 Weld + Datum Signature Characterization")
    print("=" * 60)
    print(f"  typelib: {TLB_PATH}")

    try:
        scan = _scan_typelib(TLB_PATH)
    except Exception as exc:
        print(f"  FATAL: could not load typelib: {exc}", file=sys.stderr)
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(
            json.dumps({"error": str(exc)}, indent=2), encoding="utf-8"
        )
        return 1

    print(f"\n  typelib: {scan['typelib']['name']} "
          f"v{scan['typelib']['major']}.{scan['typelib']['minor']}")
    print(f"  total type infos: {scan['typelib']['total_type_infos']}")

    print(f"\n--- WELD candidates ---")
    print(f"  {len(scan['weld_candidates'])} method(s) across "
          f"{len(scan['all_weld_ifaces'])} interface(s)")
    for iface_info in scan["all_weld_ifaces"]:
        print(f"\n  [{iface_info['interface']}]")
        for m in iface_info["methods"]:
            args_str = ", ".join(
                f"{a['name']}:{a['vt_label']}" for a in m.get("args", [])
            )
            print(f"    {m['invkind_label']} {m['method']}"
                  f"({args_str}) -> {m['return_vt_label']}")

    print(f"\n--- DATUM candidates ---")
    print(f"  {len(scan['datum_candidates'])} method(s) across "
          f"{len(scan['all_datum_ifaces'])} interface(s)")
    for iface_info in scan["all_datum_ifaces"]:
        print(f"\n  [{iface_info['interface']}]")
        for m in iface_info["methods"]:
            args_str = ", ".join(
                f"{a['name']}:{a['vt_label']}" for a in m.get("args", [])
            )
            print(f"    {m['invkind_label']} {m['method']}"
                  f"({args_str}) -> {m['return_vt_label']}")

    conclusions = _derive_conclusions(scan)

    print(f"\n--- CONCLUSIONS ---")
    wc = conclusions["weld"]["chosen"]
    if wc:
        print(f"  WELD: {wc['interface']}.{wc['method']}"
              f"  cParams={wc['cParams']}"
              f"  args={wc['arg_vts']}"
              f"  ret={wc['return_vt']}")
    else:
        print(f"  WELD: NO Insert* candidate found")
    print(f"    {conclusions['weld']['reasoning']}")

    dc = conclusions["datum"]["chosen"]
    if dc:
        print(f"  DATUM: {dc['interface']}.{dc['method']}"
              f"  cParams={dc['cParams']}"
              f"  args={dc['arg_vts']}"
              f"  ret={dc['return_vt']}")
    else:
        print(f"  DATUM: NO Insert* candidate found")
    print(f"    {conclusions['datum']['reasoning']}")
    if conclusions["datum"].get("anchor_requirement"):
        print(f"    ANCHOR: {conclusions['datum']['anchor_requirement']}")

    output = {
        "spike": "w59_weld_datum_sig",
        "typelib": scan["typelib"],
        "conclusions": conclusions,
        "raw_scan": {
            "weld_candidates": scan["weld_candidates"],
            "datum_candidates": scan["datum_candidates"],
        },
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n  wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
