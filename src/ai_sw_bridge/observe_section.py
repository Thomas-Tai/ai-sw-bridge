"""Section properties observation helper — W58 (perception axis).

Read-only cross-section properties (area, centroid, moments of inertia,
principal axes) of a pre-selected planar face via
``IModelDocExtension.GetSectionProperties2``.

COM signature — sourced from ``sldworksapi.chm`` (SW 2024 API Help, locally
installed at ``C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\api\\``) and
typelib gen_py ``83A33D31-27C5-11CE-BFD4-00400513BB57x0x32x0.py`` (dispid=66):

  IModelDocExtension.GetSectionProperties2(Sections: VARIANT) -> VARIANT

``Sections`` — array of faces to add to the current selection set (pass
``None`` to use the already-selected entities only; see Remarks below).

Returns a **24-element double array** (SI/metric, from the CHM Remarks):
  [0]   status  — 0=success, 1=invalid input,
                  2=faces not coplanar/parallel, 3=compute failure
  [1]   area (m²)
  [2]   centroid x (m)
  [3]   centroid y (m)
  [4]   centroid z (m)
  [5]   moment of inertia XX (m⁴)
  [6]   moment of inertia YY (m⁴)
  [7]   moment of inertia ZZ (m⁴)
  [8]   product of inertia −XY (m⁴)
  [9]   product of inertia −ZX (m⁴)
  [10]  product of inertia −YZ (m⁴)
  [11]  polar moment of inertia at centroid (m⁴)
  [12]  angle between principal axis and part axis (rad)
  [13]  principal moment lx at centroid (m⁴)
  [14]  principal moment ly at centroid (m⁴)
  [15–17] principal axis X direction vector (x, y, z)
  [18–20] principal axis Y direction vector (x, y, z)
  [21–23] principal axis Z direction vector (x, y, z)

CHM Remarks (load-bearing):
  - "This method clears the selection set."
  - "The objects in the Sections parameter are added to the current
    selection set. If the objects are already in the current selection set,
    an error is generated (status = 1, invalid input)."
  - Passing ``None`` (or an empty VARIANT) is the correct form when the
    caller has already pre-selected the face; the CHM table states:
    "If the user selected a set of either parallel planes or parallel
    faces, You can pass an empty sections array."

Caller contract:
  - Pre-select a planar face via ``SelectByID2`` or ``IEntity.Select4``
    BEFORE calling ``sw_get_section_props``.
  - Pass ``Sections=None`` to ``GetSectionProperties2`` so SW uses only
    the current selection without adding new items (which would raise
    status=1 if the face is already selected).

Seat NOT yet validated (W58 offline author; W0 fires on handback).

v1 scope: section properties of a single pre-selected planar face.
DEFER:
  - CLI wiring (to W0 on handback — see ``cli/observe.py``).
  - check-geometry via ``IBody2.Check3`` (separate axis; R3 gate needed).
  - Multi-face sections, sketch sections.
"""

from __future__ import annotations

import math
from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .sw_com import resolve

# Status codes from GetSectionProperties2 return array index 0.
# Sourced: sldworksapi.chm Remarks table.
_STATUS_OK = 0
_STATUS_INVALID_INPUT = 1
_STATUS_NOT_COPLANAR = 2
_STATUS_COMPUTE_FAIL = 3

_STATUS_MESSAGES = {
    _STATUS_INVALID_INPUT: "invalid input (faces already in selection set, or no selection)",
    _STATUS_NOT_COPLANAR:  "selected faces are not in the same or parallel planes",
    _STATUS_COMPUTE_FAIL:  "unable to compute section properties",
}

# Number of elements in the return array (CHM: "format of returned array of size 24").
_EXPECTED_LEN = 24


def read_section_props(raw: Any) -> dict[str, Any]:
    """Parse a 24-element ``GetSectionProperties2`` return array.

    Converts all values from SI (m, m², m⁴, rad) to the bridge's
    human units (mm, mm², mm⁴, deg).

    ``raw[0]`` is the status code; non-zero means the COM call reported
    an error.  All float fields are ``None`` on parse failure or when
    the status is non-zero.

    Returns dict with keys:
      - ``status`` (int), ``status_ok`` (bool), ``status_message`` (str|None)
      - ``area_mm2`` (float|None)
      - ``centroid_mm`` ([x, y, z]|None) — model-coordinate centroid
      - ``ixx_mm4``, ``iyy_mm4``, ``izz_mm4`` (float|None)
      - ``ixy_mm4``, ``izx_mm4``, ``iyz_mm4`` (float|None) — products (sign per CHM: −XY, −ZX, −YZ)
      - ``jp_mm4`` (float|None) — polar moment at centroid
      - ``principal_angle_deg`` (float|None)
      - ``ix_mm4``, ``iy_mm4`` (float|None) — principal moments lx, ly
      - ``principal_axis_x``, ``principal_axis_y``, ``principal_axis_z``
        ([x, y, z] unit vectors, dimensionless|None)
      - ``errors`` (list[str])
    """
    result: dict[str, Any] = {
        "status": None,
        "status_ok": False,
        "status_message": None,
        "area_mm2": None,
        "centroid_mm": None,
        "ixx_mm4": None,
        "iyy_mm4": None,
        "izz_mm4": None,
        "ixy_mm4": None,
        "izx_mm4": None,
        "iyz_mm4": None,
        "jp_mm4": None,
        "principal_angle_deg": None,
        "ix_mm4": None,
        "iy_mm4": None,
        "principal_axis_x": None,
        "principal_axis_y": None,
        "principal_axis_z": None,
        "errors": [],
    }

    if raw is None:
        result["errors"].append("GetSectionProperties2 returned None")
        return result

    try:
        arr = [float(raw[i]) for i in range(_EXPECTED_LEN)]
    except (TypeError, IndexError, ValueError) as exc:
        result["errors"].append(f"array parse failed (expected {_EXPECTED_LEN} elements): {exc!r}")
        return result

    status = int(arr[0])
    result["status"] = status
    result["status_ok"] = status == _STATUS_OK
    if status != _STATUS_OK:
        result["status_message"] = _STATUS_MESSAGES.get(
            status, f"unknown status {status}"
        )
        result["errors"].append(result["status_message"])
        return result

    # SI → human-unit conversions:
    #   area:    m²  → mm²  × 1e6
    #   length:  m   → mm   × 1e3
    #   moment:  m⁴  → mm⁴  × 1e12
    #   angle:   rad → deg  × (180/π)
    result["area_mm2"] = arr[1] * 1e6
    result["centroid_mm"] = [arr[2] * 1e3, arr[3] * 1e3, arr[4] * 1e3]
    result["ixx_mm4"] = arr[5] * 1e12
    result["iyy_mm4"] = arr[6] * 1e12
    result["izz_mm4"] = arr[7] * 1e12
    result["ixy_mm4"] = arr[8] * 1e12
    result["izx_mm4"] = arr[9] * 1e12
    result["iyz_mm4"] = arr[10] * 1e12
    result["jp_mm4"] = arr[11] * 1e12
    result["principal_angle_deg"] = math.degrees(arr[12])
    result["ix_mm4"] = arr[13] * 1e12
    result["iy_mm4"] = arr[14] * 1e12
    result["principal_axis_x"] = [arr[15], arr[16], arr[17]]
    result["principal_axis_y"] = [arr[18], arr[19], arr[20]]
    result["principal_axis_z"] = [arr[21], arr[22], arr[23]]

    return result


def _sw_get_section_props_impl(doc: Any) -> dict[str, Any]:
    """Core: section properties of the pre-selected planar face (v0.18 implementation).

    Requires a face to be selected in ``doc`` before calling (via
    ``SelectByID2`` or interactive selection in SOLIDWORKS).

    Acquires ``IModelDocExtension``, calls ``GetSectionProperties2(None)``
    to operate on the current selection, then delegates to
    :func:`read_section_props`. Internal callers (the
    ``SolidWorksClient.observe`` facade) call this directly so they bypass
    the deprecation shim; the public :func:`sw_get_section_props` free
    function routes here behind a ``PendingDeprecationWarning``.

    NOTE: ``GetSectionProperties2`` clears the selection set (CHM Remarks).

    Returns::

        {
          "ok": bool,
          "error": str | None,
          "section": {               # present whether ok or not
            "area_mm2": float | None,
            "centroid_mm": [x, y, z] | None,
            "ixx_mm4": float | None,
            "iyy_mm4": float | None,
            "izz_mm4": float | None,
            "ixy_mm4": float | None,
            "izx_mm4": float | None,
            "iyz_mm4": float | None,
            "jp_mm4": float | None,
            "principal_angle_deg": float | None,
            "ix_mm4": float | None,
            "iy_mm4": float | None,
            "principal_axis_x": [x, y, z] | None,
            "principal_axis_y": [x, y, z] | None,
            "principal_axis_z": [x, y, z] | None,
          } | None
        }
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "section": None,
    }

    if doc is None:
        result["error"] = "no_active_doc"
        return result

    # Acquire IModelDocExtension — late-bound first (mock-friendly),
    # then typed fallback (live-seat path where late-bound raises).
    ext = None
    try:
        ext = doc.Extension
    except AttributeError:
        pass

    if ext is None:
        try:
            mod = wrapper_module()
            doc_typed = typed(doc, "IModelDoc2", module=mod)
            ext = doc_typed.Extension
        except Exception as exc:
            result["error"] = f"doc.Extension failed: {exc!r}"
            return result

    if ext is None:
        result["error"] = "doc.Extension returned None"
        return result

    # Call GetSectionProperties2(None):
    #   Passing None uses the current selection without adding new faces.
    #   Source: sldworksapi.chm Remarks — "empty sections array" form.
    #   Seat note: if None is rejected, try [] (empty Python list).
    try:
        raw = ext.GetSectionProperties2(None)
    except Exception as exc:
        result["error"] = f"GetSectionProperties2 failed: {exc!r}"
        return result

    props = read_section_props(raw)
    result["section"] = {
        "area_mm2": props["area_mm2"],
        "centroid_mm": props["centroid_mm"],
        "ixx_mm4": props["ixx_mm4"],
        "iyy_mm4": props["iyy_mm4"],
        "izz_mm4": props["izz_mm4"],
        "ixy_mm4": props["ixy_mm4"],
        "izx_mm4": props["izx_mm4"],
        "iyz_mm4": props["iyz_mm4"],
        "jp_mm4": props["jp_mm4"],
        "principal_angle_deg": props["principal_angle_deg"],
        "ix_mm4": props["ix_mm4"],
        "iy_mm4": props["iy_mm4"],
        "principal_axis_x": props["principal_axis_x"],
        "principal_axis_y": props["principal_axis_y"],
        "principal_axis_z": props["principal_axis_z"],
    }

    if props["errors"]:
        result["error"] = "; ".join(props["errors"])
    else:
        result["ok"] = True

    return result


