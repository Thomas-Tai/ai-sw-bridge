"""Variants block JSON-Schema fragment (Phase 4, FR-4-01).

Defines the variants: array schema for the schema-v2 spec.  This
fragment is consumed by the v2 validator when assembling the top-level
schema — it is not wired into the v1 SCHEMA constant.

The variants: block is an array of objects, each with a name
field and an optional overrides object mapping variable names to
expression strings.

Example in a v2 spec::

    "variants": [
        {
            "name": "Small",
            "overrides": {"WIDTH": "20.0", "HEIGHT": "30.0"}
        },
        {
            "name": "Large",
            "overrides": {"WIDTH": "50.0", "HEIGHT": "80.0"},
            "description": "Production variant for heavy-duty use"
        }
    ]
"""

from __future__ import annotations

from typing import Any

VARIANT_OVERRIDE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"type": "string"},
    "description": (
        "Map of locals-variable names to replacement RHS expression "
        "strings.  Each key must match a variable in the base locals "
        "file; each value is a raw SW-equation expression."
    ),
}

VARIANT_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Configuration name.  Becomes the SW configuration "
                "name verbatim.  Must be unique within the spec."
            ),
        },
        "overrides": VARIANT_OVERRIDE_SCHEMA,
        "description": {
            "type": "string",
            "description": (
                "Optional human-readable description stored in the "
                "SW configuration's description field."
            ),
        },
    },
}

VARIANTS_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "array",
    "minItems": 1,
    "items": VARIANT_ENTRY_SCHEMA,
    "description": (
        "List of configuration variants.  Each variant defines a named "
        "set of locals-variable overrides that produces one SW "
        "configuration via ConfigurationManager.AddConfiguration2."
    ),
}
