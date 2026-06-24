"""Interference detection observation helper — E4 (Wave-27).

Read-only interference detection via ``IAssemblyDoc.InterferenceDetectionManager``.

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - ``InterferenceDetectionManager`` is a property-get on ``IAssemblyDoc``
    (dispid 126, NOT ``GetInterferenceDetectionManager()``).
  - Returns ``IInterferenceDetectionMgr`` (interface is ``…Mgr``, not ``…Manager``).
  - ``GetInterferenceCount()`` returns the number of physical clashes.
  - ``GetInterferences()`` returns an array of ``IInterference`` objects.
  - Each ``IInterference`` exposes ``Volume`` (m³), ``Components`` (array),
    and ``GetComponentCount()``.
  - ``Done()`` must be called to clean up the detection session.

Discrimination proven (W27 spike):
  - Overlapping 20mm cubes at 10mm offset → count=1, volume=4e-6 m³.
  - Non-overlapping at 50mm offset → count=0.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .sw_com import SW_DOC_ASSEMBLY, resolve


def read_interference(asm_doc: Any, mod: Any = None) -> dict[str, Any]:
    """Detect physical interferences in an assembly document.

    Uses the seat-proven ``InterferenceDetectionManager`` recipe:
      - ``typed(asm_doc, "IAssemblyDoc").InterferenceDetectionManager`` → mgr
      - Configure options (ignore coincidence, hidden bodies, etc.)
      - ``GetInterferenceCount()`` → count
      - ``GetInterferences()`` → enumerate ``IInterference`` objects
      - ``Done()`` cleanup

    Returns a dict with ``interference_count`` and ``interferences`` list.
    Volume converted from m³ to mm³ (×1e9).
    """
    result: dict[str, Any] = {
        "interference_count": 0,
        "interferences": [],
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    # Typed IAssemblyDoc wrapper
    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IAssemblyDoc): {exc!r}")
        return result

    # InterferenceDetectionManager (dispid 126, property-get)
    mgr = None
    try:
        mgr = asm_typed.InterferenceDetectionManager
    except Exception as exc:
        result["errors"].append(f"InterferenceDetectionManager access: {exc!r}")
        return result

    if mgr is None:
        result["errors"].append("InterferenceDetectionManager returned None")
        return result

    # Typed manager wrapper + configure options
    try:
        mgr_typed = typed(mgr, "IInterferenceDetectionMgr", module=mod)
        # Configure options for clean physical interference detection
        mgr_typed.TreatCoincidenceAsInterference = (
            False  # Coincident faces ≠ interference
        )
        mgr_typed.ShowIgnoredInterferences = False
        mgr_typed.TreatSubAssembliesAsComponents = True
        mgr_typed.IncludeMultibodyPartInterferences = True
        mgr_typed.MakeInterferingPartsTransparent = False
        mgr_typed.CreateFastenersFolder = False
        mgr_typed.IgnoreHiddenBodies = True
    except Exception as exc:
        result["errors"].append(f"typed(IInterferenceDetectionMgr)/options: {exc!r}")
        # Try late-bound fallback
        try:
            mgr.TreatCoincidenceAsInterference = False
            mgr.IgnoreHiddenBodies = True
        except Exception:
            pass
        mgr_typed = mgr  # use late-bound as fallback

    # GetInterferenceCount
    caller = mgr_typed if mgr_typed is not None else mgr
    try:
        count = caller.GetInterferenceCount()
    except Exception as exc:
        result["errors"].append(f"GetInterferenceCount: {exc!r}")
        # Done cleanup
        try:
            caller.Done()
        except Exception:
            pass
        return result

    count_val = count
    if isinstance(count_val, tuple):
        count_val = count_val[0]
    int_count = int(count_val) if count_val is not None else 0
    result["interference_count"] = int_count

    # Enumerate if count > 0
    if int_count > 0:
        try:
            intf_array = caller.GetInterferences()
            if intf_array is not None:
                items = intf_array
                if not isinstance(items, (list, tuple)):
                    items = (items,)
                for idx, intf_obj in enumerate(items):
                    entry = _read_single_interference(intf_obj, mod, idx)
                    result["interferences"].append(entry)
        except Exception as exc:
            result["errors"].append(f"GetInterferences enumeration: {exc!r}")

    # Done cleanup
    try:
        caller.Done()
    except Exception:
        pass

    return result


def _read_single_interference(
    intf_obj: Any,
    mod: Any,
    idx: int,
) -> dict[str, Any]:
    """Read one ``IInterference`` object: Volume + Components."""
    entry: dict[str, Any] = {
        "components": [],
        "interference_volume_mm3": None,
        "errors": [],
    }

    # Volume (m³ → mm³)
    vol_m3 = None
    try:
        vol = intf_obj.Volume
        if callable(vol):
            vol = vol()
        vol_m3 = float(vol) if vol is not None else None
    except Exception as exc:
        entry["errors"].append(f"Volume: {exc!r}")

    # Typed wrapper fallback for Volume
    if vol_m3 is None:
        try:
            intf_typed = typed(intf_obj, "IInterference", module=mod)
            vol_m3 = float(intf_typed.Volume)
        except Exception:
            pass

    # Convert m³ → mm³ (×1e9)
    if vol_m3 is not None:
        entry["interference_volume_mm3"] = vol_m3 * 1e9

    # Components (array of IComponent2)
    try:
        comps = intf_obj.Components
        if callable(comps):
            comps = comps()
        if comps is not None:
            if not isinstance(comps, (list, tuple)):
                comps = (comps,)
            for c in comps:
                try:
                    # Name2 is the component instance name (e.g., "block_20mm-1")
                    name = c.Name2 if hasattr(c, "Name2") else c.Name
                    if callable(name):
                        name = name()
                    entry["components"].append(str(name))
                except Exception:
                    entry["components"].append("<error>")
    except Exception as exc:
        entry["errors"].append(f"Components: {exc!r}")

    return entry


def _sw_get_interference_impl(doc: Any) -> dict[str, Any]:
    """Core: detect interference in an assembly document (v0.18 implementation).

    Acquires the document type, validates it is an assembly, then delegates
    to :func:`read_interference`. Returns the structured report:
    ``{"ok": bool, "interference_count": int, "interferences": list, ...}``.
    Internal callers (the ``SolidWorksClient.observe`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_interference` free function routes here behind a
    ``PendingDeprecationWarning``.

    Fail-closed: non-assembly input → ``ok=False`` with clear error.
    Manager-acquisition failure → ``ok=False`` (not a false "0 clashes").
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "interference_count": 0,
        "interferences": [],
    }

    # Check document type
    try:
        doc_type = resolve(doc, "GetType")
        if callable(doc_type):
            doc_type = doc_type()
    except Exception as exc:
        result["error"] = f"doc.GetType failed: {exc!r}"
        return result

    if doc_type != SW_DOC_ASSEMBLY:
        result["error"] = (
            f"interference detection requires assembly document (got type {doc_type})"
        )
        return result

    mod = wrapper_module()
    intf_result = read_interference(doc, mod=mod)
    result["interference_count"] = intf_result["interference_count"]
    result["interferences"] = intf_result["interferences"]

    if intf_result["errors"]:
        result["error"] = "; ".join(intf_result["errors"])
        result["ok"] = False
    else:
        result["ok"] = True

    return result
