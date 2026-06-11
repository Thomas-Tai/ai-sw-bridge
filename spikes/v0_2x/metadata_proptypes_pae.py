"""W53 proptypes seat spike — typed custom properties round-trip.

Author-only spike for the live SW seat (W0 holds the seat).

GREEN gate (verify-the-EFFECT):
  For each typed property (TEXT / NUMBER / DATE / YES_NO):
    1. Add3(name, type_id, value, SW_CUSTOM_PROP_REPLACE) → 0
    2. SaveAs3(path, 0, 0) → 0
    3. CloseDoc → reopen → Get4(name, False)
    4. Assert: prop exists in GetNames() AND Get4 value == set value

  Fail-closed: any type that doesn't round-trip → spike FAILS.

Also characterizes:
  - Get4 return tuple shape per type (resolved, value, resolved2)
  - Whether Get5 is callable on the typed proxy (W29 noted Get6 is dead)
  - FUNCDESC dump for Add3/Get4/Get5 from the typelib

swCustomInfoType_e (from typelib — dumped O1, NOT guessed):
  - swCustomInfoText    = 30
  - swCustomInfoNumber  = 31
  - swCustomInfoDate    = 32
  - swCustomInfoYesOrNo = 33
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

repo_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))

# swCustomInfoType_e — W53 seat-corrected (31/32/33 were guesses; real enum is
# sparse: Number=3, Double=5, YesOrNo=11, Text=30, Date=64).
SW_CUSTOM_INFO_TEXT = 30
SW_CUSTOM_INFO_NUMBER = 5   # swCustomInfoDouble — Number(3) is int-only, rejects 42.5
SW_CUSTOM_INFO_DATE = 64
SW_CUSTOM_INFO_YES_OR_NO = 11
SW_CUSTOM_PROP_REPLACE = 1


# Properties to test — one of each type plus a mix.
PROPS_TO_SET: list[dict[str, str]] = [
    {"name": "W53_PartNo", "type": "text", "type_id": "30", "value": "W53-BRK-001"},
    {"name": "W53_Weight", "type": "number", "type_id": "5", "value": "42.5"},
    {"name": "W53_Count", "type": "number", "type_id": "5", "value": "100"},
    {"name": "W53_Created", "type": "date", "type_id": "64", "value": "2024-06-15"},
    {"name": "W53_Reviewed", "type": "date", "type_id": "64", "value": "6/15/2024"},
    {"name": "W53_Approved", "type": "yes_no", "type_id": "11", "value": "Yes"},
    {"name": "W53_Rejected", "type": "yes_no", "type_id": "11", "value": "No"},
]


def _semantic_match(prop_type: str, expected: str, got: str) -> bool:
    """Compare a read-back value to the input, allowing SW normalization.

    SW stores a Double as a 6-decimal string ('42.5' -> '42.500000') and a Date
    in locale format ('2024-06-15' -> '6/15/2024'); both are the SAME value.
    Text / yes_no compare verbatim.
    """
    if got == expected:
        return True
    if prop_type == "number":
        try:
            return float(got) == float(expected)
        except (TypeError, ValueError):
            return False
    if prop_type == "date":
        from datetime import datetime
        fmts = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y")

        def _parse(s):
            for f in fmts:
                try:
                    return datetime.strptime(str(s).strip(), f).date()
                except ValueError:
                    continue
            return None

        de, dg = _parse(expected), _parse(got)
        return de is not None and de == dg
    return False


def _dump_funcdesc(typed_cpm, method_name: str) -> dict:
    """Dump FUNCDESC for a method from the typelib if accessible."""
    info: dict = {"method": method_name, "funcdesc": None, "error": None}
    try:
        disp = typed_cpm._oleobj_
        typeinfo = disp.GetTypeInfo()
        # Find the method by name
        for i in range(typeinfo.GetTypeAttr()[6]):  # cFuncs
            try:
                fd = typeinfo.GetFuncDesc(i)
                names = typeinfo.GetNames(fd[0])
                if names and names[0] == method_name:
                    info["funcdesc"] = {
                        "memid": fd[0],
                        "funckind": fd[1],
                        "invkind": fd[2],
                        "callconv": fd[4],
                        "cParams": fd[5],
                        "paramflags": fd[8] if len(fd) > 8 else None,
                        "names": list(names),
                    }
                    break
            except Exception:
                continue
    except Exception as exc:
        info["error"] = str(exc)
    return info


def run_spike() -> dict:
    """Execute the W53 typed-properties seat spike."""
    result: dict = {
        "ok": False,
        "stage": "init",
        "errors": [],
        "set_props": [],
        "read_back": [],
        "funcdescs": {},
        "get5_probe": None,
        "count_before": None,
        "count_after": None,
    }

    test_parts = list(repo_root.rglob("*.SLDPRT"))
    if not test_parts:
        result["errors"].append("No test parts found under repo root")
        return result

    src_part = test_parts[0]
    result["source_part"] = str(src_part)

    work_dir = Path(__file__).parent / "_artifacts"
    work_dir.mkdir(parents=True, exist_ok=True)

    test_part = work_dir / f"W53_proptypes_{src_part.name}"
    shutil.copy(src_part, test_part)
    result["test_part"] = str(test_part)

    try:
        from ai_sw_bridge.sw_com import get_sw_app
        from ai_sw_bridge.com.earlybind import typed, typed_qi
        from ai_sw_bridge.com.sw_type_info import wrapper_module

        sw = get_sw_app()
        if sw is None:
            result["errors"].append("Failed to connect to SOLIDWORKS")
            return result

        mod = wrapper_module()
        tsw = typed(sw, "ISldWorks", module=mod)

        # Open
        result["stage"] = "open"
        ret = tsw.OpenDoc6(str(test_part), 1, 1, "", 0, 0)
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is None:
            result["errors"].append(f"OpenDoc6 failed for {test_part}")
            return result

        mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)

        # Acquire CPM
        result["stage"] = "cpm_acquire"
        ext_obj = model_doc.Extension
        cpm_raw = ext_obj.CustomPropertyManager("")
        if cpm_raw is None:
            result["errors"].append("CustomPropertyManager('') returned None")
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        typed_cpm = typed_qi(cpm_raw, "ICustomPropertyManager", module=mod)

        # Count before
        count_before = typed_cpm.Count
        result["count_before"] = count_before
        print(f"[W53] Count before: {count_before}", file=sys.stderr)

        # FUNCDESC dump for key methods
        result["stage"] = "funcdesc_dump"
        for mname in ("Add3", "Get4", "Get5", "Get6"):
            result["funcdescs"][mname] = _dump_funcdesc(typed_cpm, mname)
            print(
                f"[W53] FUNCDESC {mname}: {result['funcdescs'][mname]}",
                file=sys.stderr,
            )

        # Get5 probe: does it work on the typed proxy?
        result["stage"] = "get5_probe"
        try:
            get5_result = typed_cpm.Get5("W53_PartNo", False)
            result["get5_probe"] = {
                "callable": True,
                "result": get5_result,
                "type": type(get5_result).__name__,
            }
            print(f"[W53] Get5 probe: {get5_result}", file=sys.stderr)
        except Exception as exc:
            result["get5_probe"] = {"callable": False, "error": repr(exc)}
            print(f"[W53] Get5 probe FAILED: {exc!r}", file=sys.stderr)

        # Set each typed property
        result["stage"] = "set_props"
        for prop in PROPS_TO_SET:
            name = prop["name"]
            type_id = int(prop["type_id"])
            value = prop["value"]

            try:
                add_result = typed_cpm.Add3(
                    name, type_id, value, SW_CUSTOM_PROP_REPLACE
                )
            except Exception as exc:
                result["errors"].append(
                    f"Add3({name}, type={type_id}/{prop['type']}) raised: {exc!r}"
                )
                continue

            if add_result != 0:
                result["errors"].append(
                    f"Add3({name}, type={type_id}/{prop['type']}) "
                    f"returned {add_result} (expected 0)"
                )
                continue

            result["set_props"].append({
                "name": name,
                "type": prop["type"],
                "type_id": type_id,
                "value": value,
                "add3_result": add_result,
            })
            print(
                f"[W53] Set {name} (type={type_id}/{prop['type']}) = {value!r}",
                file=sys.stderr,
            )

        if result["errors"]:
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # Immediate read-back (before save) via Get4
        result["stage"] = "immediate_read_back"
        for prop in result["set_props"]:
            name = prop["name"]
            try:
                get4_result = typed_cpm.Get4(name, False)
                resolved, pvalue, resolved2 = get4_result
                prop["immediate_get4"] = {
                    "raw": get4_result,
                    "resolved": resolved,
                    "value": pvalue,
                    "resolved2": resolved2,
                    "match": pvalue == prop["value"],
                }
                print(
                    f"[W53] Immediate Get4({name}): {pvalue!r} == {prop['value']!r} "
                    f"-> {pvalue == prop['value']}",
                    file=sys.stderr,
                )
            except Exception as exc:
                result["errors"].append(f"Get4({name}) raised: {exc!r}")

        if result["errors"]:
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # Save via SaveAs3
        result["stage"] = "save"
        try:
            save_err = mdoc2.SaveAs3(str(test_part), 0, 0)
            if save_err != 0:
                result["errors"].append(
                    f"SaveAs3 returned {save_err} (expected 0)"
                )
                title = mdoc2.GetTitle
                title = title() if callable(title) else title
                sw.CloseDoc(title)
                return result
            result["saved"] = True
            print("[W53] SaveAs3 OK", file=sys.stderr)
        except Exception as exc:
            result["errors"].append(f"Save failed: {exc!r}")
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # Close
        result["stage"] = "close"
        title = mdoc2.GetTitle
        title = title() if callable(title) else title
        sw.CloseDoc(title)

        # Reopen
        result["stage"] = "reopen"
        time.sleep(0.3)
        ret = tsw.OpenDoc6(str(test_part), 1, 1, "", 0, 0)
        model_doc2 = ret[0] if isinstance(ret, tuple) else ret
        if model_doc2 is None:
            result["errors"].append("Reopen failed")
            return result

        mdoc2b = typed_qi(model_doc2, "IModelDoc2", module=mod)
        ext_obj2 = model_doc2.Extension
        cpm_raw2 = ext_obj2.CustomPropertyManager("")
        typed_cpm2 = typed_qi(cpm_raw2, "ICustomPropertyManager", module=mod)

        count_after = typed_cpm2.Count
        result["count_after"] = count_after
        print(f"[W53] Count after reopen: {count_after}", file=sys.stderr)

        reopen_names = set(typed_cpm2.GetNames() or ())

        # Reopen read-back — THE GREEN GATE
        result["stage"] = "reopen_read_back"
        result["reopen_read_back"] = []
        all_match = True

        for prop in result["set_props"]:
            name = prop["name"]
            expected = prop["value"]
            exists = name in reopen_names

            try:
                get4_result = typed_cpm2.Get4(name, False)
                resolved, pvalue, resolved2 = get4_result
                match = exists and _semantic_match(prop["type"], expected, pvalue)

                entry = {
                    "name": name,
                    "type": prop["type"],
                    "type_id": prop["type_id"],
                    "exists": exists,
                    "get4_raw": get4_result,
                    "resolved": resolved,
                    "value": pvalue,
                    "expected": expected,
                    "match": match,
                }
                result["reopen_read_back"].append(entry)
                result["read_back"].append(entry)

                if not match:
                    all_match = False
                    result["errors"].append(
                        f"FAIL {prop['type']} prop '{name}': "
                        f"expected {expected!r}, got {pvalue!r} "
                        f"(exists={exists}, resolved={resolved})"
                    )

                print(
                    f"[W53] Reopen Get4({name}) [{prop['type']}]: "
                    f"{pvalue!r} == {expected!r} -> {match}",
                    file=sys.stderr,
                )
            except Exception as exc:
                all_match = False
                result["errors"].append(f"reopen Get4({name}) raised: {exc!r}")

        # Also try Get5 on reopen if it worked earlier
        if result.get("get5_probe", {}).get("callable"):
            result["stage"] = "reopen_get5"
            result["reopen_get5"] = []
            for prop in result["set_props"]:
                name = prop["name"]
                try:
                    g5 = typed_cpm2.Get5(name, False)
                    result["reopen_get5"].append({
                        "name": name,
                        "get5_raw": g5,
                    })
                    print(
                        f"[W53] Reopen Get5({name}): {g5}",
                        file=sys.stderr,
                    )
                except Exception as exc:
                    result["reopen_get5"].append({
                        "name": name,
                        "error": repr(exc),
                    })

        # Close
        title2 = mdoc2b.GetTitle
        title2 = title2() if callable(title2) else title2
        sw.CloseDoc(title2)

        # Validation
        count_ok = count_after >= count_before + len(PROPS_TO_SET)
        result["count_delta_ok"] = count_ok
        result["all_match"] = all_match

        if not count_ok:
            result["errors"].append(
                f"count didn't increase: before={count_before}, "
                f"after={count_after}, set={len(PROPS_TO_SET)}"
            )

        if all_match and count_ok:
            result["ok"] = True
            type_summary = {}
            for prop in result["set_props"]:
                t = prop["type"]
                type_summary[t] = type_summary.get(t, 0) + 1
            result["summary"] = (
                f"All {len(PROPS_TO_SET)} typed props round-tripped; "
                f"count {count_before}->{count_after}; "
                f"types: {type_summary}"
            )

        return result

    except Exception as exc:
        result["errors"].append(f"Exception: {exc!r}")
        return result


if __name__ == "__main__":
    print("=== W53 Typed Properties Spike ===", file=sys.stderr)
    result = run_spike()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
