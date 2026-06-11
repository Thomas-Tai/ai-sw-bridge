"""Metadata lifecycle — propose/dry_run/commit (Wave-29, extended Wave-53).

End-to-end ``propose -> dry_run -> commit`` for ``kind: "properties"`` specs.

  - **propose**: validate offline (jsonschema + semantic).
  - **dry_run**: confirm model file exists and is openable.
  - **commit**: open -> Get CustomPropertyManager -> Add3 each prop
    (with resolved type: TEXT/NUMBER/DATE/YES_NO) -> SaveAs3
    -> reopen -> Get4 read-back verification -> close.

Fail-closed: if any Add3 fails or read-back doesn't match, the operation
is considered failed and no partial state is persisted.

VERIFY THE EFFECT (W0 requirement): read-back on reopen proves the props
actually persisted to the model file.
"""

from __future__ import annotations

import jsonschema
import logging
import os
import time
from typing import Any

from .spec_schema import (
    PROPERTIES_SPEC_SCHEMA,
    SW_CUSTOM_PROP_ADD,
    SW_CUSTOM_PROP_REPLACE,
    resolve_prop_type_and_value,
    validate_properties_spec,
)

logger = logging.getLogger("ai_sw_bridge.metadata")


def propose_properties(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a properties spec offline (no SW touch).

    Returns a result dict with ``ok``, and ``error`` on failure.
    """
    result: dict[str, Any] = {"ok": False}

    try:
        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
    except jsonschema.ValidationError as exc:
        result["error"] = f"schema validation failed: {exc.message}"
        return result

    try:
        validate_properties_spec(spec)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    result["ok"] = True
    result["properties_count"] = len(spec.get("properties", {}))
    result["model"] = spec.get("model")
    return result


def dry_run_properties(spec: dict[str, Any]) -> dict[str, Any]:
    """Dry-run a properties spec — confirm model file exists.

    Returns a result dict with ``ok``, ``model_path``, and ``error``.
    """
    result: dict[str, Any] = {"ok": False}

    model_path = spec.get("model", "")
    if not os.path.isfile(model_path):
        result["error"] = f"model file not found: {model_path}"
        return result

    result["model_path"] = model_path
    result["properties_count"] = len(spec.get("properties", {}))
    result["ok"] = True
    return result


def commit_properties(
    sw: Any,
    spec: dict[str, Any],
    *,
    mod: Any | None = None,
) -> dict[str, Any]:
    """Commit a properties spec — set custom properties on the model.

    Fail-closed on any Add3 failure or read-back mismatch.

    W53: each property's type is resolved from the spec entry. Plain
    string values use TEXT (30); typed-object entries use their declared
    type (NUMBER=31, DATE=32, YES_NO=33).

    Args:
        sw: the ``SldWorks.Application`` COM object.
        spec: the validated properties spec dict.
        mod: the gen_py wrapper module.

    Returns:
        A result dict with ``ok``, ``props_set``, ``read_back``, ``errors``.
    """
    from ..com.earlybind import typed, typed_qi
    from ..com.sw_type_info import wrapper_module

    if mod is None:
        mod = wrapper_module()

    result: dict[str, Any] = {
        "ok": False,
        "props_set": [],
        "props_skipped": [],
        "read_back": [],
        "errors": [],
    }

    model_path = spec.get("model", "")
    if not os.path.isfile(model_path):
        result["errors"].append(f"model file not found: {model_path}")
        return result

    properties = spec.get("properties", {})
    if not properties:
        result["errors"].append("properties map is empty")
        return result

    overwrite = spec.get("overwrite", True)

    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        ext = os.path.splitext(model_path)[1].lower()
        doc_type = 2 if ext == ".sldasm" else 1

        ret = tsw.OpenDoc6(model_path, doc_type, 1, "", 0, 0)
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is None:
            result["errors"].append(f"OpenDoc6 failed for {model_path}")
            return result

        mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)

        ext_obj = model_doc.Extension
        cpm_raw = ext_obj.CustomPropertyManager("")
        if cpm_raw is None:
            result["errors"].append("CustomPropertyManager('') returned None")
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        typed_cpm = typed_qi(cpm_raw, "ICustomPropertyManager", module=mod)

        # Count is a PROPERTY on the typed proxy, not a method.
        count_before = typed_cpm.Count
        result["count_before"] = count_before

        # GetNames() membership determines existence; Get4's first return
        # is a RESOLVED flag, not an existence flag.
        existing_names = set(typed_cpm.GetNames() or ())

        for name, entry in properties.items():
            type_id, value, type_name = resolve_prop_type_and_value(name, entry)

            if name in existing_names and not overwrite:
                try:
                    _resolved, pvalue, _resolved2 = typed_cpm.Get4(name, False)
                except Exception:
                    pvalue = None
                result["props_skipped"].append({
                    "name": name,
                    "type": type_name,
                    "reason": "exists and overwrite=false",
                    "existing_value": pvalue,
                })
                continue

            options = SW_CUSTOM_PROP_REPLACE if overwrite else SW_CUSTOM_PROP_ADD
            try:
                add_result = typed_cpm.Add3(name, type_id, value, options)
            except Exception as exc:
                result["errors"].append(f"Add3({name}) raised: {exc!r}")
                continue

            if add_result != 0:
                result["errors"].append(
                    f"Add3({name}, type={type_id}/{type_name}) "
                    f"returned {add_result} (expected 0)"
                )
                continue

            result["props_set"].append({
                "name": name,
                "type": type_name,
                "type_id": type_id,
                "value": value,
            })

        if result["errors"]:
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # Immediate read-back — Get4(name, useCached=False) returns
        # (resolved_flag, value, resolved2).
        for prop_info in result["props_set"]:
            name = prop_info["name"]
            try:
                _resolved, pvalue, _resolved2 = typed_cpm.Get4(name, False)
                prop_info["immediate_read_back"] = {
                    "value": pvalue,
                    "match": pvalue == prop_info["value"],
                }
                if not prop_info["immediate_read_back"]["match"]:
                    result["errors"].append(
                        f"immediate read-back mismatch for '{name}' "
                        f"(type={prop_info['type']}): "
                        f"set {prop_info['value']!r}, got {pvalue!r}"
                    )
            except Exception as exc:
                result["errors"].append(f"Get4({name}) raised: {exc!r}")

        if result["errors"]:
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        # SaveAs3 in-place (W33/W34 proven route).
        # Save3 is DEAD: trailing [out] params break early-bind.
        try:
            save_err = mdoc2.SaveAs3(model_path, 0, 0)
            if save_err != 0:
                result["errors"].append(
                    f"SaveAs3 returned swFileSaveError={save_err} (expected 0)"
                )
                title = mdoc2.GetTitle
                title = title() if callable(title) else title
                sw.CloseDoc(title)
                return result
            result["saved"] = True
        except Exception as exc:
            result["errors"].append(f"Save failed: {exc!r}")
            title = mdoc2.GetTitle
            title = title() if callable(title) else title
            sw.CloseDoc(title)
            return result

        title = mdoc2.GetTitle
        title = title() if callable(title) else title
        sw.CloseDoc(title)

        # Reopen for verification (VERIFY THE EFFECT).
        time.sleep(0.3)
        ret = tsw.OpenDoc6(model_path, doc_type, 1, "", 0, 0)
        model_doc2 = ret[0] if isinstance(ret, tuple) else ret
        if model_doc2 is None:
            result["errors"].append(f"Reopen failed for {model_path}")
            return result

        mdoc2b = typed_qi(model_doc2, "IModelDoc2", module=mod)
        ext_obj2 = model_doc2.Extension
        cpm_raw2 = ext_obj2.CustomPropertyManager("")
        typed_cpm2 = typed_qi(cpm_raw2, "ICustomPropertyManager", module=mod)

        count_after = typed_cpm2.Count
        result["count_after"] = count_after

        reopen_names = set(typed_cpm2.GetNames() or ())
        for prop_info in result["props_set"]:
            name = prop_info["name"]
            expected = prop_info["value"]
            try:
                exists = name in reopen_names
                _resolved, pvalue, _resolved2 = typed_cpm2.Get4(name, False)
                read_back_entry = {
                    "name": name,
                    "type": prop_info["type"],
                    "exists": exists,
                    "value": pvalue,
                    "expected": expected,
                    "match": exists and pvalue == expected,
                }
                result["read_back"].append(read_back_entry)
                prop_info["reopen_read_back"] = read_back_entry
                if not read_back_entry["match"]:
                    result["errors"].append(
                        f"reopen read-back mismatch for '{name}' "
                        f"(type={prop_info['type']}): "
                        f"expected {expected!r}, got {pvalue!r} (exists={exists})"
                    )
            except Exception as exc:
                result["errors"].append(f"reopen Get4({name}) raised: {exc!r}")

        title2 = mdoc2b.GetTitle
        title2 = title2() if callable(title2) else title2
        sw.CloseDoc(title2)

        all_match = all(rb["match"] for rb in result["read_back"])
        count_delta_ok = count_after >= count_before + len(result["props_set"])

        if result["errors"]:
            return result

        if not all_match:
            result["errors"].append("one or more read-back values don't match")
            return result

        if not count_delta_ok:
            result["errors"].append(
                f"count didn't increase as expected: "
                f"before={count_before}, after={count_after}, "
                f"set={len(result['props_set'])}"
            )
            return result

        result["ok"] = True
        result["summary"] = (
            f"set {len(result['props_set'])} properties; "
            f"count {count_before}->{count_after}; "
            f"all read-back verified"
        )
        return result

    except Exception as exc:
        result["errors"].append(f"Exception: {exc!r}")
        return result
