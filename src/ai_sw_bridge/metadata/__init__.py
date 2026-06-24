"""Metadata package (Wave-29, extended Wave-53).

Public API for custom file property management on SOLIDWORKS models.

- ``propose_properties`` — validate a properties spec offline.
- ``dry_run_properties`` — confirm model file exists.
- ``commit_properties`` — set properties on the model with read-back verification.
- ``PROPERTIES_SPEC_SCHEMA`` — the ``kind: "properties"`` JSON-Schema.
- ``SW_CUSTOM_INFO_TYPE_MAP`` — type-name to swCustomInfoType_e int mapping.
- ``resolve_prop_type_and_value`` — resolve a spec entry to (type_id, value, type_name).
"""

from __future__ import annotations

from .lifecycle import commit_properties, dry_run_properties, propose_properties
from .spec_schema import (
    PROPERTIES_SPEC_SCHEMA,
    SW_CUSTOM_INFO_DATE,
    SW_CUSTOM_INFO_NUMBER,
    SW_CUSTOM_INFO_TEXT,
    SW_CUSTOM_INFO_TYPE_MAP,
    SW_CUSTOM_INFO_YES_OR_NO,
    SW_CUSTOM_PROP_ADD,
    SW_CUSTOM_PROP_REPLACE,
    resolve_prop_type_and_value,
    semantic_prop_match,
    validate_properties_spec,
)

__all__ = [
    "PROPERTIES_SPEC_SCHEMA",
    "SW_CUSTOM_INFO_DATE",
    "SW_CUSTOM_INFO_NUMBER",
    "SW_CUSTOM_INFO_TEXT",
    "SW_CUSTOM_INFO_TYPE_MAP",
    "SW_CUSTOM_INFO_YES_OR_NO",
    "SW_CUSTOM_PROP_ADD",
    "SW_CUSTOM_PROP_REPLACE",
    "commit_properties",
    "dry_run_properties",
    "propose_properties",
    "resolve_prop_type_and_value",
    "semantic_prop_match",
    "validate_properties_spec",
]
