"""Material assignment helpers (P1.2).

Two paths for material on a part:

1. **Custom-property path** (SW-free in the sense that the call shape is
   proven): write the material name as a custom property on the part doc
   via ``ICustomPropertyManager.Add3``. This is a text property — it
   does NOT activate the SW material library. Useful for BOM / drawing
   title block / downstream tooling that reads "Material" from custom
   properties.

2. **Library-material path** (🔴 SEAT-gated, deferred): call
   ``IPartDoc.SetMaterialPropertyName2(config_name, db_name, mat_name)``
   to assign a real SW material from the library. This activates
   density, appearance, and simulation properties. Needs a seat to
   confirm the marshal shape (``db_name`` is the library file path
   without extension, e.g. ``"SOLIDWORKS Materials"``).

Only path 1 is wired into the builder today. Path 2 is a TODO for
when a seat session confirms the API shape.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ai_sw_bridge.material")

# ICustomPropertyManager type constants (swCustomInfoType_e)
SW_CUSTOM_INFO_TEXT = 30

# ICustomPropertyManager options (swCustomPropertyAddOption_e)
SW_CUSTOM_PROP_ADD = 0
SW_CUSTOM_PROP_REPLACE = 1

MATERIAL_PROP_NAME = "Material"


def set_material_custom_prop(doc: Any, material_name: str) -> bool:
    """Write the material name as a custom property on the part doc.

    Uses ``ICustomPropertyManager`` at file level (empty config name).
    Returns True on success, False on any failure.

    This is the SW-free path — the call shape is proven, no material
    library interaction. The property shows up in the part's Custom
    Properties dialog and in BOM / drawing title blocks.
    """
    if not material_name or not isinstance(material_name, str):
        return False

    try:
        ext = doc.Extension
        cpm = ext.CustomPropertyManager("")
    except Exception as exc:
        logger.warning("CustomPropertyManager acquisition failed: %s", exc)
        return False

    try:
        # Add3(name, type, value, options) — options=1 means overwrite
        result = cpm.Add3(
            MATERIAL_PROP_NAME,
            SW_CUSTOM_INFO_TEXT,
            material_name,
            SW_CUSTOM_PROP_REPLACE,
        )
        # Add3 returns 0 on success, non-zero on failure
        ok = result == 0 if isinstance(result, int) else result is not None
        if ok:
            logger.info("material custom prop set: %s", material_name)
        else:
            logger.warning("Add3 returned %r for material %r", result, material_name)
        return ok
    except Exception as exc:
        logger.warning("Add3(Material) raised: %s", exc)
        return False


def apply_material(doc: Any, spec: dict[str, Any]) -> bool | None:
    """Apply the material from the spec to the part doc.

    Returns:
        True if material was set, False if the call failed, None if the
        spec does not declare a material (no-op).
    """
    material = spec.get("material")
    if material is None:
        return None
    if not isinstance(material, str):
        logger.warning("material must be a string, got %r", type(material).__name__)
        return False
    return set_material_custom_prop(doc, material)
