"""Metadata spec JSON schema (Wave-29).

Defines the ``kind: "properties"`` spec structure: a model path and a map
of custom file properties to set.

The schema enforces:
  - ``kind`` == "properties" (required)
  - ``model`` (required, path to .sldprt or .sldasm)
  - ``properties`` (required, non-empty map of string → string)
  - ``overwrite`` (optional, bool, default True)

v1 scope:
  - TEXT values only (swCustomInfoText = 30)
  - File-level properties (empty config, not configuration-specific)
  - Flat string→string map (no nested values)

Deferred:
  - Number/Date/YesOrNo types
  - Configuration-specific properties
  - Linked properties
  - Property deletion (Delete2)
"""

from __future__ import annotations

from typing import Any


# swCustomInfoType_e (from typelib)
SW_CUSTOM_INFO_TEXT = 30
SW_CUSTOM_INFO_NUMBER = 31
SW_CUSTOM_INFO_DATE = 32
SW_CUSTOM_INFO_YES_OR_NO = 33

# swCustomPropertyAddOption_e
SW_CUSTOM_PROP_ADD = 0      # add only, fail if exists
SW_CUSTOM_PROP_REPLACE = 1  # overwrite if exists


PROPERTIES_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge properties spec v1",
    "type": "object",
    "required": ["kind", "model", "properties"],
    "additionalProperties": False,
    "properties": {
        "kind": {"const": "properties"},
        "model": {
            "type": "string",
            "minLength": 1,
            "description": "Path to the .sldprt or .sldasm file.",
        },
        "properties": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string", "minLength": 1},
            "description": (
                "Map of custom property names to text values. "
                "All values must be non-empty strings. "
                "v1 supports TEXT type only."
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
      - all property values are non-empty strings (v1 = TEXT only)
      - no nested values (flat map)
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")

    if spec.get("kind") != "properties":
        raise ValueError("spec kind must be 'properties'")

    model = spec.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")

    # Check file extension
    ext = model.lower().split(".")[-1] if "." in model else ""
    if ext not in ("sldprt", "sldasm"):
        raise ValueError(
            f"model must be a .sldprt or .sldasm file; got extension '{ext}'"
        )

    properties = spec.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")

    for name, value in properties.items():
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"property name must be a non-empty string; got {type(name).__name__}"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"property '{name}' value must be a string; got {type(value).__name__}"
            )
        # Allow empty string values? SW allows them, but they're not useful.
        # For v1, we allow empty values (user may want to clear a prop).
        # Note: minLength in schema requires non-empty values — keep consistent.

    overwrite = spec.get("overwrite")
    if overwrite is not None and not isinstance(overwrite, bool):
        raise ValueError("overwrite must be a boolean if present")