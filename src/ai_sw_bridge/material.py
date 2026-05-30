"""Material assignment helpers (P1.2).

Two paths for material on a part:

1. **Custom-property path**: write the material name as a custom property
   on the part doc via ``ICustomPropertyManager.Add3``. This is a text
   property — it does NOT activate the SW material library, so mass
   properties stay on the geometry-default density. Useful for BOM /
   drawing title block / downstream tooling that reads "Material" from
   custom properties.

2. **Library-material path** (✅ SEAT-VALIDATED 2026-05-30, SW 32.1.0):
   ``IPartDoc.SetMaterialPropertyName2(config, db, name)`` assigns a real
   SW library material, which DOES flow into mass-props density. The
   v0.15 PARTIAL had two compounding causes, both now resolved
   (spike ``spikes/v0_16/spike_material_v3.py``):

   * **Marshaling wall** — late-bound ``GetMaterialPropertyName2`` raised
     "Parameter not optional" (it has ``[out] BSTR`` params) and
     ``GetMassProperties2`` raised "Type mismatch". Both clear under the
     early-bound :func:`com.earlybind.typed` seam, exactly like the
     persist-ref / GetDefinition cases.
   * **Wrong name** — the guessed ``"AISI 1020 Steel (SS)"`` is not in
     this install's library; ``"AISI 1020"`` is. ``SetMaterialPropertyName2``
     returns void and silently no-ops on an unknown name — the same trap
     as the wizard-hole size string.

   Seat-proven recipe: pass ``db=""`` (SW resolves the default library and
   reports it back as ``"SOLIDWORKS Materials"``), then VERIFY the
   assignment took by reading the name back through a typed ``IPartDoc``
   (non-empty ⟺ a real library material is now assigned and density
   follows — proven: density moved 1000 → 7900 kg/m³ for steel).

The handler tries path 2 first and *verifies it took*; on an unknown name
(read-back empty) it degrades to path 1 so the metadata is still carried.
"""

from __future__ import annotations

import logging
from typing import Any

from .com.earlybind import typed

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


def read_library_material_name(doc: Any) -> str | None:
    """Read the part's currently-assigned library material name, or None.

    Uses an early-bound typed ``IPartDoc`` because
    ``GetMaterialPropertyName2`` has ``[out] BSTR`` params that the
    late-bound marshaler cannot surface (it raises "Parameter not
    optional"). Returns the material name string if a library material is
    assigned, or ``None`` if none is assigned or the read-back is
    unavailable for any reason (never raises).

    A non-empty return is the proof that a real SW library material is
    active — and therefore that mass-props density reflects it.
    """
    try:
        part = typed(doc, "IPartDoc")
        rb = part.GetMaterialPropertyName2("")
    except Exception as exc:  # noqa: BLE001 — degrade to "no library material"
        logger.debug("GetMaterialPropertyName2 read-back unavailable: %s", exc)
        return None
    # Early binding surfaces [out] params as a tuple: (name, db).
    if isinstance(rb, (tuple, list)) and rb:
        name = str(rb[0])
        return name or None
    if isinstance(rb, str):
        return rb or None
    return None


def set_library_material(doc: Any, material_name: str, *, database: str = "") -> bool:
    """Assign a real SW *library* material and verify the assignment took.

    Calls ``IPartDoc.SetMaterialPropertyName2(config="", db, name)`` (an
    empty ``db`` lets SW resolve the default library), rebuilds so the
    material settles, then reads the name back through a typed ``IPartDoc``.

    Returns ``True`` only if the read-back confirms a non-empty material
    name — i.e. ``material_name`` is a genuine library material and density
    now reflects it. Returns ``False`` if the name is not in the library
    (``SetMaterialPropertyName2`` no-ops silently on an unknown name) or any
    call fails. A ``False`` here is the signal for the caller to fall back
    to the custom-property path.
    """
    if not material_name or not isinstance(material_name, str):
        return False
    try:
        doc.SetMaterialPropertyName2("", database, material_name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("SetMaterialPropertyName2 raised for %r: %s", material_name, exc)
        return False
    # Rebuild so the assigned material's density flows into the model.
    try:
        doc.ForceRebuild3(False)
    except Exception:  # noqa: BLE001 — rebuild is best-effort
        try:
            _ = doc.EditRebuild3
        except Exception:  # noqa: BLE001
            pass
    assigned = read_library_material_name(doc)
    if assigned:
        logger.info("library material assigned: %s", assigned)
        return True
    logger.info(
        "material %r not found in SW library (no-op); falling back to custom property",
        material_name,
    )
    return False


def apply_material(doc: Any, spec: dict[str, Any]) -> bool | None:
    """Apply the material from the spec to the part doc.

    Tries the honest library-material path first (assign + verify); if the
    name is not a real library material, degrades to the custom-property
    path so the metadata is still carried for BOM / title-block tooling.

    Returns:
        True if material was applied (library or custom-property), False if
        both paths failed, None if the spec does not declare a material.
    """
    material = spec.get("material")
    if material is None:
        return None
    if not isinstance(material, str):
        logger.warning("material must be a string, got %r", type(material).__name__)
        return False
    # Honest path: assign a real library material and confirm it took.
    if set_library_material(doc, material):
        return True
    # Unknown library name — carry the material as a text custom property.
    return set_material_custom_prop(doc, material)
