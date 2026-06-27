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

from ..sw_com import resolve
from .spec_schema import (
    PROPERTIES_SPEC_SCHEMA,
    SW_CUSTOM_DELETE_NOT_PRESENT,
    SW_CUSTOM_DELETE_OK,
    SW_CUSTOM_PROP_ADD,
    SW_CUSTOM_PROP_REPLACE,
    resolve_prop_type_and_value,
    semantic_prop_match,
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
    result["properties_count"] = len(spec.get("properties") or {})
    result["delete_count"] = len(spec.get("delete") or [])
    result["configuration"] = spec.get("configuration") or ""
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
    result["properties_count"] = len(spec.get("properties") or {})
    result["delete_count"] = len(spec.get("delete") or [])
    result["configuration"] = spec.get("configuration") or ""
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
    type (NUMBER/Double=5, DATE=64, YES_NO=11).

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
        "props_deleted": [],
        "read_back": [],
        "errors": [],
    }

    model_path = spec.get("model", "")
    if not os.path.isfile(model_path):
        result["errors"].append(f"model file not found: {model_path}")
        return result

    properties = spec.get("properties") or {}
    delete_names = spec.get("delete") or []
    if not properties and not delete_names:
        result["errors"].append(
            "nothing to do: no properties to set and none to delete"
        )
        return result

    # v3: config-level vs file-level manager. "" = file-level (the default).
    config_name = spec.get("configuration") or ""
    result["configuration"] = config_name

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
        cpm_raw = ext_obj.CustomPropertyManager(config_name)
        if cpm_raw is None:
            result["errors"].append(
                f"CustomPropertyManager({config_name!r}) returned None"
            )
            title = resolve(mdoc2, "GetTitle")
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
                result["props_skipped"].append(
                    {
                        "name": name,
                        "type": type_name,
                        "reason": "exists and overwrite=false",
                        "existing_value": pvalue,
                    }
                )
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

            result["props_set"].append(
                {
                    "name": name,
                    "type": type_name,
                    "type_id": type_id,
                    "value": value,
                }
            )

        if result["errors"]:
            title = resolve(mdoc2, "GetTitle")
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
                    "match": semantic_prop_match(
                        prop_info["type"], prop_info["value"], pvalue
                    ),
                }
                if not prop_info["immediate_read_back"]["match"]:
                    result["errors"].append(
                        f"immediate read-back mismatch for '{name}' "
                        f"(type={prop_info['type']}): "
                        f"set {prop_info['value']!r}, got {pvalue!r}"
                    )
            except Exception as exc:
                result["errors"].append(f"Get4({name}) raised: {exc!r}")

        # v3 — Delete2 teardown (the D in CRUD). 0=OK / 1=NotPresent (already
        # absent → idempotent OK); LinkedProp(2) or any other code is an error.
        # ``was_present`` distinguishes a real deletion (count drops) from a
        # no-op, so the count gate stays honest. Reopen verifies absence.
        for name in delete_names:
            try:
                del_result = typed_cpm.Delete2(name)
            except Exception as exc:
                result["errors"].append(f"Delete2({name}) raised: {exc!r}")
                continue
            if del_result in (SW_CUSTOM_DELETE_OK, SW_CUSTOM_DELETE_NOT_PRESENT):
                result["props_deleted"].append(
                    {
                        "name": name,
                        "result": del_result,
                        "was_present": del_result == SW_CUSTOM_DELETE_OK,
                    }
                )
            else:
                result["errors"].append(
                    f"Delete2({name}) returned {del_result} "
                    f"(linked/unremovable; expected 0 OK or 1 NotPresent)"
                )

        if result["errors"]:
            title = resolve(mdoc2, "GetTitle")
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
                title = resolve(mdoc2, "GetTitle")
                sw.CloseDoc(title)
                return result
            result["saved"] = True
        except Exception as exc:
            result["errors"].append(f"Save failed: {exc!r}")
            title = resolve(mdoc2, "GetTitle")
            sw.CloseDoc(title)
            return result

        title = resolve(mdoc2, "GetTitle")
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
        cpm_raw2 = ext_obj2.CustomPropertyManager(config_name)
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
                    "match": exists
                    and semantic_prop_match(prop_info["type"], expected, pvalue),
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

        # v3 — verify-the-EFFECT for deletions: the name must be ABSENT from the
        # reopened manager's GetNames() (the real witness; the Delete2 return code
        # alone is the property-write equivalent of the W21/W42 ghost trap).
        deletes_verified = True
        for d in result["props_deleted"]:
            name = d["name"]
            still_present = name in reopen_names
            d["verified_absent"] = not still_present
            if still_present:
                deletes_verified = False
                result["errors"].append(
                    f"delete verification failed: '{name}' still present "
                    f"after reopen (config={config_name!r})"
                )

        title2 = resolve(mdoc2b, "GetTitle")
        sw.CloseDoc(title2)

        all_match = all(rb["match"] for rb in result["read_back"])
        # Count gate accounting for adds (only NEW names grow the count) and
        # deletes (only those actually PRESENT shrink it). A pure overwrite or a
        # delete-of-absent leaves the count flat — gating on >= len(props_set)
        # would false-fail those, so compute the true expected net delta.
        new_added = sum(
            1 for p in result["props_set"] if p["name"] not in existing_names
        )
        deleted_present = sum(
            1 for d in result["props_deleted"] if d.get("was_present")
        )
        expected_delta = new_added - deleted_present
        count_delta_ok = (count_after - count_before) == expected_delta

        if result["errors"]:
            return result

        if not all_match:
            result["errors"].append("one or more read-back values don't match")
            return result

        if not deletes_verified:
            result["errors"].append("one or more deletions did not persist")
            return result

        if not count_delta_ok:
            result["errors"].append(
                f"count delta mismatch: before={count_before}, after={count_after}, "
                f"expected net {expected_delta:+d} "
                f"(+{new_added} new, -{deleted_present} deleted)"
            )
            return result

        result["ok"] = True
        result["summary"] = (
            f"config={config_name or '<file-level>'}: "
            f"set {len(result['props_set'])} / deleted {len(result['props_deleted'])} "
            f"properties; count {count_before}->{count_after}; "
            f"all read-back + delete verified"
        )
        return result

    except Exception as exc:
        result["errors"].append(f"Exception: {exc!r}")
        return result
