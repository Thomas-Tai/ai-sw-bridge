"""Surface UV evaluation helper — E2 (Wave-5).

Evaluates a face's underlying surface at a given (U, V) parameter,
returning the 3-D point and unit normal.  Uses the proven early-bound
``typed_qi`` pattern from the interrogator (see ``brep/interrogator.py``).

Pipeline::

    face → IFace2.GetSurface → typed_qi(surf, "ISurface")
         → surf.Evaluate(u, v) → (point_tuple, normal_tuple)

All values are in model metres (SW internal).  The helper converts
to mm for the spec layer.

Designed to be called from ``brep/interrogator.py`` (W0 wires it in)
or used directly by the MCP observe layer.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("ai_sw_bridge.brep.surface_eval")


def evaluate_surface_at_uv(
    face: Any,
    u: float,
    v: float,
    module: Any = None,
) -> dict[str, Any]:
    """Evaluate a face's surface at the given (U, V) parameter.

    Parameters
    ----------
    face : IFace2 dispatch
        A face object obtained from body traversal.
    u, v : float
        Surface parameters.
    module : optional
        The early-bound wrapper module for typed QI (from
        ``com.sw_type_info.wrapper_module()``).  If None, the
        function attempts to load it internally.

    Returns
    -------
    dict with keys:
        ``ok`` — bool
        ``point_mm`` — [x, y, z] in millimetres (or None on failure)
        ``normal`` — [nx, ny, nz] unit normal (or None)
        ``error`` — str or None
    """
    result: dict[str, Any] = {
        "ok": False,
        "point_mm": None,
        "normal": None,
        "error": None,
    }

    if module is None:
        from ..com.sw_type_info import wrapper_module
        module = wrapper_module()

    from ..com.earlybind import typed as _typed

    # Step 1: Get the surface from the face (needs typed IFace2).
    try:
        tface = _typed(face, "IFace2", module=module)
        raw_surf = tface.GetSurface()
    except Exception as exc:
        result["error"] = f"IFace2.GetSurface failed: {exc!r}"
        return result

    if raw_surf is None:
        result["error"] = "GetSurface returned None"
        return result

    # Step 2: typed wrap to ISurface (NOT typed_qi — QI returns E_NOINTERFACE).
    try:
        surf = _typed(raw_surf, "ISurface", module=module)
    except Exception as exc:
        result["error"] = f"typed(ISurface) failed: {exc!r}"
        return result

    # Step 3: Evaluate at (U, V).
    # Seat-validated (SW 2024 SP1): ISurface.Evaluate takes **4 args**
    # (u, v, u, v) and returns a 6-tuple (x, y, z, nx, ny, nz) in metres.
    try:
        eval_result = surf.Evaluate(float(u), float(v), float(u), float(v))
    except Exception as exc:
        result["error"] = f"ISurface.Evaluate({u}, {v}) failed: {exc!r}"
        return result

    if eval_result is None:
        result["error"] = "Evaluate returned None"
        return result

    # Unpack the result — SW returns (x, y, z, nx, ny, nz).
    try:
        if isinstance(eval_result, tuple) and len(eval_result) >= 6:
            point_m = [float(eval_result[i]) for i in range(3)]
            normal = [float(eval_result[i]) for i in range(3, 6)]
        else:
            result["error"] = f"unexpected Evaluate result shape: {type(eval_result)}"
            return result

        result["point_mm"] = [c * 1000.0 for c in point_m]
        result["normal"] = normal
        result["ok"] = True
    except (IndexError, TypeError, ValueError) as exc:
        result["error"] = f"failed to unpack Evaluate result: {exc!r}"

    return result


def get_surface_parameter_range(face: Any, module: Any = None) -> dict[str, Any]:
    """Read the UV parameter range of a face's surface.

    Seat-validated (SW 2024 SP1): ``ISurface.ParameterRange`` uses byref
    VARIANT output parameters that do **not** marshal out-of-process —
    the method returns ``self`` (the ISurface instance) rather than the
    range values.  This is a known COM marshaling wall.

    Returns ``{u_min, u_max, v_min, v_max}`` or error info.
    When the marshaling wall is hit, returns a default range of (0,1,0,1)
    with a warning in ``error`` so callers can still attempt Evaluate at
    the parametric midpoint.
    """
    result: dict[str, Any] = {
        "ok": False,
        "u_min": None,
        "u_max": None,
        "v_min": None,
        "v_max": None,
        "error": None,
    }

    if module is None:
        from ..com.sw_type_info import wrapper_module
        module = wrapper_module()

    from ..com.earlybind import typed as _typed

    try:
        tface = _typed(face, "IFace2", module=module)
        raw_surf = tface.GetSurface()
    except Exception as exc:
        result["error"] = f"GetSurface failed: {exc!r}"
        return result

    if raw_surf is None:
        result["error"] = "GetSurface returned None"
        return result

    try:
        surf = _typed(raw_surf, "ISurface", module=module)
    except Exception as exc:
        result["error"] = f"typed(ISurface) failed: {exc!r}"
        return result

    # ParameterRange — seat-validated: returns self out-of-process.
    try:
        pr = surf.ParameterRange
        if isinstance(pr, (tuple, list)) and len(pr) >= 4:
            result["u_min"] = float(pr[0])
            result["u_max"] = float(pr[1])
            result["v_min"] = float(pr[2])
            result["v_max"] = float(pr[3])
            result["ok"] = True
        else:
            # Marshaling wall — return default range so Evaluate can still be
            # attempted at the midpoint (0.5, 0.5).
            result["u_min"] = 0.0
            result["u_max"] = 1.0
            result["v_min"] = 0.0
            result["v_max"] = 1.0
            result["ok"] = True
            result["error"] = "ParameterRange not readable out-of-process; using default (0,1,0,1)"
    except Exception as exc:
        result["error"] = f"ParameterRange failed: {exc!r}"

    return result
