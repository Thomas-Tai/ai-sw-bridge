"""Metadata spec JSON schema (Wave-29, extended Wave-53).

Defines the ``kind: "properties"`` spec structure: a model path and a map
of custom file properties to set.

The schema enforces:
  - ``kind`` == "properties" (required)
  - ``model`` (required, path to .sldprt or .sldasm)
  - ``properties`` (required, non-empty map of name -> value)
  - ``overwrite`` (optional, bool, default True)

v1 scope (W29):
  - TEXT values only (swCustomInfoText = 30)
  - File-level properties (empty config, not configuration-specific)
  - Flat string->string map (no nested values)

v2 scope (W53):
  - Typed properties: text / number / date / yes_no
  - Backwards-compatible: plain string values still resolve to TEXT
  - Each typed property is ``{"type": "<type>", "value": "<string>"}``
  - Value format per type:
    - text: any non-empty string
    - number: numeric string (e.g., "42.5", "-3", "100")
    - date: date string (e.g., "2024-06-15" or locale format)
    - yes_no: "Yes" or "No" (case-sensitive per SW API)

v3 scope (W71 — CRUD completion):
  - ``configuration`` (optional): config name for config-specific properties.
    Absent or "" = file-level (document) properties — the historical default,
    so existing specs are unchanged. A string selects
    ``Extension.CustomPropertyManager(<config>)`` (the config-specific store,
    isolated from the file-level one).
  - ``delete`` (optional): a list of property names to remove via
    ``ICustomPropertyManager.Delete2`` (the D in CRUD). Honored against the
    same ``configuration`` as the writes.
  - ``properties`` is now OPTIONAL — a delete-only spec ({configuration, delete})
    is valid; a spec must set OR delete at least one property.

Linked properties (ZERO-CODE — seat-proven W71, spike_linked_property_probe):
  A property *value* that uses SOLIDWORKS' QUOTED link syntax is resolved by the
  kernel natively through the shipped Add3 path — no new COM surface needed.
  Just feed the link string as the value:
    - dimension link:  "D1@Boss-Extrude1"   → evaluates to the dim (e.g. "10.00")
    - mass/system link: "SW-Mass@<file>.SLDPRT" → evaluates to the mass
  The QUOTES are mandatory — the BARE form ("D1@Boss-Extrude1" without the
  surrounding quotes) is stored literally and NOT resolved, and the ``$PRP:"X"``
  field-code form (valid in note/title-block TEXT, W38) is NOT resolved as a
  property value. The STORED value is the raw link text (so read-back/overwrite
  semantics are unchanged); the EVALUATED value is Get4's 3rd return element.

Deferred:
  - (none for custom properties — CRUD + linked values are complete)
"""

from __future__ import annotations

import re
from typing import Any


# swCustomInfoType_e (from swconst.tlb — W53 seat-corrected; the 31/32/33 here
# were +1/+2/+3 guesses off Text=30 and made Add3 return GenericFail=1. The real
# enum is sparse: Number=3, Double=5, YesOrNo=11, Text=30, Date=64, Equation=105.)
SW_CUSTOM_INFO_TEXT = 30
SW_CUSTOM_INFO_NUMBER = 5  # swCustomInfoDouble — Number(3) is int-only, rejects 42.5
SW_CUSTOM_INFO_DATE = 64
SW_CUSTOM_INFO_YES_OR_NO = 11

# swCustomPropertyAddOption_e
SW_CUSTOM_PROP_ADD = 0  # add only, fail if exists
SW_CUSTOM_PROP_REPLACE = 1  # overwrite if exists

# swCustomInfoDeleteResult_e (Delete2 return codes)
SW_CUSTOM_DELETE_OK = 0  # deleted
SW_CUSTOM_DELETE_NOT_PRESENT = 1  # nothing to delete (already absent → idempotent OK)
SW_CUSTOM_DELETE_LINKED = 2  # property is linked → cannot delete (error)

# Property type name -> swCustomInfoType_e int
SW_CUSTOM_INFO_TYPE_MAP: dict[str, int] = {
    "text": SW_CUSTOM_INFO_TEXT,
    "number": SW_CUSTOM_INFO_NUMBER,
    "date": SW_CUSTOM_INFO_DATE,
    "yes_no": SW_CUSTOM_INFO_YES_OR_NO,
}

_VALID_PROP_TYPES = frozenset(SW_CUSTOM_INFO_TYPE_MAP)

_NUMERIC_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")

_VALID_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$" r"|^\d{1,2}/\d{1,2}/\d{4}$" r"|^\d{1,2}\.\d{1,2}\.\d{4}$"
)


def resolve_prop_type_and_value(
    name: str, entry: str | dict[str, Any]
) -> tuple[int, str, str]:
    """Resolve a property entry to (type_id, value_string, type_name).

    Backwards-compatible: a plain string entry resolves to TEXT.

    Returns:
        (sw_type_id, value, type_name) where type_name is one of
        "text", "number", "date", "yes_no".

    Raises:
        ValueError: if the entry is malformed.
    """
    if isinstance(entry, str):
        return SW_CUSTOM_INFO_TEXT, entry, "text"

    if not isinstance(entry, dict):
        raise ValueError(
            f"property '{name}' must be a string or a typed-object; "
            f"got {type(entry).__name__}"
        )

    prop_type = entry.get("type")
    if prop_type not in _VALID_PROP_TYPES:
        raise ValueError(
            f"property '{name}' has invalid type {prop_type!r}; "
            f"expected one of {sorted(_VALID_PROP_TYPES)}"
        )

    value = entry.get("value")
    if not isinstance(value, str) or not value:
        raise ValueError(f"property '{name}' value must be a non-empty string")

    type_id = SW_CUSTOM_INFO_TYPE_MAP[prop_type]
    return type_id, value, prop_type


def semantic_prop_match(prop_type: str, expected: str, got: str) -> bool:
    """Compare a read-back value to the input, allowing SW normalization.

    SW stores a Double as a 6-decimal string ('42.5' -> '42.500000') and a
    Date in locale format ('2024-06-15' -> '6/15/2024'); both are the SAME
    value. Text and yes_no compare verbatim.
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

        def _parse(s: str) -> object | None:
            for f in fmts:
                try:
                    return datetime.strptime(str(s).strip(), f).date()
                except ValueError:
                    continue
            return None

        de, dg = _parse(expected), _parse(got)
        return de is not None and de == dg
    return False


PROPERTIES_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge properties spec v2",
    "type": "object",
    "required": ["kind", "model"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "properties"},
        "model": {
            "type": "string",
            "minLength": 1,
            "description": "Path to the .sldprt or .sldasm file.",
        },
        "configuration": {
            "type": "string",
            "description": (
                "Configuration name for config-specific properties. Absent or "
                "empty string = file-level (document) properties (the default). "
                "A non-empty string selects CustomPropertyManager(<config>)."
            ),
        },
        "delete": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
            "description": (
                "Custom property names to delete via Delete2, honored against "
                "the same 'configuration' as the writes."
            ),
        },
        "properties": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {
                "oneOf": [
                    {
                        "type": "string",
                        "minLength": 1,
                        "description": "Plain string value (resolves to TEXT type).",
                    },
                    {
                        "type": "object",
                        "required": ["type", "value"],
                        "additionalProperties": False,
                        "properties": {
                            "type": {
                                "enum": ["text", "number", "date", "yes_no"],
                                "description": "swCustomInfoType_e mapping.",
                            },
                            "value": {
                                "type": "string",
                                "minLength": 1,
                                "description": (
                                    "Value string in the format expected by the type: "
                                    "text=any, number=numeric string, "
                                    "date=ISO/locale date string, yes_no='Yes'/'No'."
                                ),
                            },
                        },
                    },
                ],
            },
            "description": (
                "Map of custom property names to values. "
                "Values can be plain strings (TEXT type) or typed objects "
                "with {type, value} for NUMBER / DATE / YES_NO."
            ),
        },
        "overwrite": {
            "type": "boolean",
            "default": True,
            "description": (
                "If true (default), overwrite existing properties. "
                "If false, skip properties that already exist."
            ),
        },
    },
}


def validate_properties_spec(spec: dict[str, Any]) -> None:
    """Semantic validation beyond the structural JSON-schema check.

    Raises ``ValueError`` on the first semantic error found.

    Checks:
      - model file extension is .sldprt or .sldasm
      - all property names are non-empty strings
      - all property values are valid for their declared type
      - number values are numeric strings
      - date values match an accepted date format
      - yes_no values are exactly "Yes" or "No"
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")

    if spec.get("kind") != "properties":
        raise ValueError("spec kind must be 'properties'")

    model = spec.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")

    ext = model.lower().split(".")[-1] if "." in model else ""
    if ext not in ("sldprt", "sldasm"):
        raise ValueError(
            f"model must be a .sldprt or .sldasm file; got extension '{ext}'"
        )

    # v3: ``properties`` is optional (a delete-only spec is valid); when present
    # it must be a non-empty object with valid typed values.
    properties = spec.get("properties")
    if properties is not None:
        if not isinstance(properties, dict) or not properties:
            raise ValueError("properties, if present, must be a non-empty object")

        for name, entry in properties.items():
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"property name must be a non-empty string; got {type(name).__name__}"
                )

            _type_id, value, type_name = resolve_prop_type_and_value(name, entry)

            if type_name == "number":
                if not _NUMERIC_RE.match(value):
                    raise ValueError(
                        f"property '{name}' (number) value must be a numeric string; "
                        f"got {value!r}"
                    )

            if type_name == "date":
                if not _VALID_DATE_RE.match(value):
                    raise ValueError(
                        f"property '{name}' (date) value must be a date string "
                        f"(YYYY-MM-DD, M/D/YYYY, or DD.MM.YYYY); got {value!r}"
                    )

            if type_name == "yes_no":
                if value not in ("Yes", "No"):
                    raise ValueError(
                        f"property '{name}' (yes_no) value must be 'Yes' or 'No'; "
                        f"got {value!r}"
                    )
    else:
        properties = {}

    # v3: ``configuration`` (file-level if absent/empty) + ``delete`` list.
    configuration = spec.get("configuration")
    if configuration is not None and not isinstance(configuration, str):
        raise ValueError("configuration must be a string if present")

    delete = spec.get("delete")
    if delete is not None:
        if not isinstance(delete, list):
            raise ValueError("delete must be a list of property names")
        for d in delete:
            if not isinstance(d, str) or not d:
                raise ValueError("delete entries must be non-empty strings")
        if len(set(delete)) != len(delete):
            raise ValueError("delete entries must be unique")
    else:
        delete = []

    if not properties and not delete:
        raise ValueError(
            "spec must set at least one property or delete at least one "
            "(both 'properties' and 'delete' are empty)"
        )

    overwrite = spec.get("overwrite")
    if overwrite is not None and not isinstance(overwrite, bool):
        raise ValueError("overwrite must be a boolean if present")
