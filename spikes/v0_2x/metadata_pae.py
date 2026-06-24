"""W29 metadata spike — custom file properties via ICustomPropertyManager.

S1 seat spike (W0 requirement):
  - Open a part → Extension.CustomPropertyManager("") → Add3(name, type, value, overwrite)
  - Save3 → reopen → Get6(name) → assert read-back exact + count increased.
  - DUMP swCustomInfoType_e (Text/Number/Date/YesOrNo — don't guess, T6).
  - v1 = TEXT values only.
  - VERIFY THE EFFECT: set >=2 props → reopen → both read back exact + count.

swCustomInfoType_e (from typelib):
  - swCustomInfoText = 30  (v1: text values only)
  - swCustomInfoNumber = 31
  - swCustomInfoDate = 32
  - swCustomInfoYesOrNo = 33

swCustomPropertyAddOption_e:
  - swCustomPropertyAdd = 0     (add only, fail if exists)
  - swCustomPropertyReplace = 1 (overwrite if exists)

ICustomPropertyManager methods (makepy-authoritative):
  - Add3(Name: BSTR, Type: I4, Value: BSTR, Options: I4) -> I4
      Returns 0 on success, non-zero on failure.
  - Get6(Name: BSTR, [out] Type: I4*, [out] Value: BSTR*, [out] Resolved: BSTR*)
      Returns True if prop exists, False if not.
      Early-bind surfaces [out] params as tuple: (exists, type, value, resolved).
  - Count() -> I4
      Number of custom properties at this level.
  - GetNames() -> VARIANT (array of BSTR)

Note: Get6 under late-bound raises "Parameter not optional" on [out] params —
must use typed_qi to early-bind ICustomPropertyManager.

Expected seat recipe:
  1. sw.OpenDoc6(model_path, doc_type, 1, "", 0, 0) -> model_doc
  2. ext = model_doc.Extension
  3. cpm = ext.CustomPropertyManager("")  # file-level, empty config
  4. typed_cpm = typed_qi(cpm, "ICustomPropertyManager", module=mod)
  5. typed_cpm.Add3("PartNo", 30, "BRK-001", 1) -> 0 on success
  6. model_doc.Save3(True, errors, warnings) or SaveAs3(path, 0, 2)
  7. sw.CloseDoc(title)
  8. REOPEN via OpenDoc6
  9. typed_cpm.Get6("PartNo") -> (True, 30, "BRK-001", "BRK-001")
  10. Assert read-back matches set value + Count increased

Deferred:
  - Configuration-specific properties
  - Number/Date/YesOrNo types (v1 = TEXT only)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

# Add src to PYTHONPATH
repo_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))

SW_CUSTOM_INFO_TEXT = 30
SW_CUSTOM_PROP_REPLACE = 1


def run_spike() -> dict:
    """Execute the W29 S1 seat spike."""
    result: dict = {
        "ok": False,
        "stage": "init",
        "errors": [],
        "set_props": [],
        "read_back": [],
        "count_before": None,
        "count_after": None,
    }

    # Find a test part to use
    test_parts = list(repo_root.rglob("*.SLDPRT"))
    if not test_parts:
        result["errors"].append("No test parts found")
        return result

    # Use the first test part, copy to a temp location to avoid modifying original
    src_part = test_parts[0]
    result["source_part"] = str(src_part)

    work_dir = Path(__file__).parent / "_artifacts"
    work_dir.mkdir(parents=True, exist_ok=True)

    test_part = work_dir / f"W29_test_{src_part.name}"
    shutil.copy(src_part, test_part)
    result["test_part"] = str(test_part)

    try:
        from ai_sw_bridge.com.connection import get_sw_app
        from ai_sw_bridge.com.earlybind import typed, typed_qi
        from ai_sw_bridge.com.sw_type_info import wrapper_module

        sw = get_sw_app()
        if sw is None:
            result["errors"].append("Failed to connect to SOLIDWORKS")
            return result

        mod = wrapper_module()
        tsw = typed(sw, "ISldWorks", module=mod)

        # Open the part
        result["stage"] = "open"
        ret = tsw.OpenDoc6(str(test_part), 1, 1, "", 0, 0)  # doc_type=1=part
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is None:
            result["errors"].append(f"OpenDoc6 failed for {test_part}")
            return result

        mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)

        # Get CustomPropertyManager
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
        count_before = typed_cpm.Count()
        result["count_before"] = count_before
        print(f"Count before: {count_before}", file=sys.stderr)

        # Set 3 properties (PartNo, Description, Revision)
        props_to_set = {
            "PartNo": "BRK-001",
            "Description": "W29 test bracket",
            "Revision": "A",
        }

        result["stage"] = "set_props"
        for name, value in props_to_set.items():
            add_result = typed_cpm.Add3(
                name, SW_CUSTOM_INFO_TEXT, value, SW_CUSTOM_PROP_REPLACE
            )
            if add_result != 0:
                result["errors"].append(f"Add3({name}) returned {add_result}")
                continue
            result["set_props"].append({"name": name, "value": value})
            print(f"Set {name} = {value!r}", file=sys.stderr)

        if result["errors"]:
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # Immediate read-back
        result["stage"] = "immediate_read_back"
        for name, expected in props_to_set.items():
            exists, ptype, pvalue, resolved = typed_cpm.Get6(name)
            result["read_back"].append(
                {
                    "name": name,
                    "exists": exists,
                    "value": pvalue,
                    "match": pvalue == expected,
                }
            )
            print(
                f"Immediate Get6({name}): {pvalue!r} == {expected!r} -> {pvalue == expected}",
                file=sys.stderr,
            )

        # Count after set
        count_after_set = typed_cpm.Count()
        result["count_after_set"] = count_after_set

        # Save
        result["stage"] = "save"
        try:
            mdoc2.Save3(False)
            result["saved"] = True
        except Exception as exc:
            # Try SaveAs3
            mdoc2.SaveAs3(str(test_part), 0, 2)
            result["saved"] = True

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

        # Count after reopen
        count_after = typed_cpm2.Count()
        result["count_after"] = count_after
        print(f"Count after reopen: {count_after}", file=sys.stderr)

        # Get6 read-back
        result["stage"] = "reopen_read_back"
        result["reopen_read_back"] = []
        for name, expected in props_to_set.items():
            exists, ptype, pvalue, resolved = typed_cpm2.Get6(name)
            result["reopen_read_back"].append(
                {
                    "name": name,
                    "value": pvalue,
                    "expected": expected,
                    "match": pvalue == expected,
                }
            )
            print(
                f"Reopen Get6({name}): {pvalue!r} == {expected!r} -> {pvalue == expected}",
                file=sys.stderr,
            )

        # Close
        title2 = mdoc2b.GetTitle
        title2 = title2() if callable(title2) else title2
        sw.CloseDoc(title2)

        # Validation
        all_match = all(rb["match"] for rb in result["reopen_read_back"])
        count_ok = count_after >= count_before + len(props_to_set)

        result["stage"] = "validation"
        result["all_match"] = all_match
        result["count_delta_ok"] = count_ok

        if all_match and count_ok:
            result["ok"] = True
            result["summary"] = (
                f"All {len(props_to_set)} props read back; count {count_before}->{count_after}"
            )
        else:
            result["errors"].append(
                f"Validation: all_match={all_match}, count_ok={count_ok}"
            )

        return result

    except Exception as exc:
        result["errors"].append(f"Exception: {exc!r}")
        return result


if __name__ == "__main__":
    print("=== W29 Metadata Spike ===", file=sys.stderr)
    result = run_spike()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)
