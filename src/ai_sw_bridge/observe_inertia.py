"""Inertia-tensor observation helper — E1 (Wave-5).

Reads ``IMassProperty2`` inertia properties from a part document.

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - ``IMassProperty2`` QI returns E_NOINTERFACE — must use ``typed()``
    (by-dispid wrap), NOT ``typed_qi()``.
  - On the typed wrapper, ``PrincipalAxesOfInertia`` and
    ``GetMomentOfInertia`` are **methods** (not properties) that take a
    center-of-rotation VARIANT(array of 3 doubles) as the first arg.
  - ``Moments`` and ``RadiusOfGyration`` are NOT exposed on the typed
    wrapper in SW 2024 — they may require a different access pattern.
  - The basic properties ``Volume``, ``SurfaceArea``, ``Mass``,
    ``Density``, ``CenterOfMass`` are readable on the **late-bound**
    proxy (same as ``sw_get_volume``).

The inertia tensor reads (``PrincipalAxesOfInertia``,
``GetMomentOfInertia``) require VARIANT(array) arg marshaling that
currently fails with "Type mismatch" / "Parameter not optional" on the
out-of-process COM boundary.  This is a **known marshaling wall** —
the helpers fail-soft and record the error.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed
from .sw_com import resolve


def read_inertia(mp: Any, mod: Any = None) -> dict[str, Any]:
    """Extract inertia properties from an ``IMassProperty2`` object.

    Uses ``typed(mp, "IMassProperty2")`` for access to methods not
    available on the late-bound proxy.  The inertia tensor reads
    (PrincipalAxesOfInertia, GetMomentOfInertia) currently fail due
    to COM VARIANT marshaling walls — the function fail-softs and
    records the errors.

    Returns a dict with ``center_of_mass_mm`` (always readable),
    ``principal_axes``, ``moments_of_inertia_kg_mm2``, and ``errors``.
    """
    result: dict[str, Any] = {
        "center_of_mass_mm": None,
        "principal_axes": None,
        "moments_of_inertia_kg_mm2": None,
        "errors": [],
    }

    # CenterOfMass — always readable on late-bound proxy.
    try:
        com = resolve(mp, "CenterOfMass")
        if com is not None and len(com) >= 3:
            result["center_of_mass_mm"] = [float(com[i]) * 1000.0 for i in range(3)]
    except Exception as exc:
        result["errors"].append(f"CenterOfMass: {exc!r}")

    # Try typed access for inertia tensor.
    if mod is None:
        from .com.sw_type_info import wrapper_module
        mod = wrapper_module()

    try:
        mp_typed = typed(mp, "IMassProperty2", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IMassProperty2): {exc!r}")
        return result

    # PrincipalAxesOfInertia / GetMomentOfInertia — methods on typed wrapper
    # that take a center-of-rotation VARIANT(array of 3 doubles). Seat-
    # validated (SW 2024 SP1, 2026-06-01): both raise with zero args
    # ("Invalid number of parameters"); with an explicit VARIANT(VT_ARRAY |
    # VT_R8, [0,0,0]) they hit the out-of-process VARIANT marshaling wall
    # ("int() argument must be a string ... not 'VARIANT'"). The helper
    # records the error and moves on; center-of-mass is still readable.
    try:
        import pythoncom
        import win32com.client
        center_v = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, 0.0]
        )
        axes = mp_typed.PrincipalAxesOfInertia(center_v)
        if axes is not None and len(axes) >= 9:
            result["principal_axes"] = [
                [float(axes[i * 3 + j]) for j in range(3)] for i in range(3)
            ]
    except Exception as exc:
        result["errors"].append(f"PrincipalAxesOfInertia: {exc!r}")

    try:
        import pythoncom
        import win32com.client
        center_v = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, 0.0]
        )
        moi = mp_typed.GetMomentOfInertia(center_v)
        if moi is not None and len(moi) >= 6:
            si = [float(moi[k]) for k in range(6)]
            result["moments_of_inertia_kg_mm2"] = [v * 1e6 for v in si]
    except Exception as exc:
        result["errors"].append(f"GetMomentOfInertia: {exc!r}")

    return result


def sw_get_inertia(doc: Any) -> dict[str, Any]:
    """Top-level observer: read inertia from a part document.

    Acquires ``IMassProperty2`` via
    ``doc.Extension.CreateMassProperty()``, then delegates to
    :func:`read_inertia`.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "center_of_mass_mm": None,
        "principal_axes": None,
        "moments_of_inertia_kg_mm2": None,
    }

    try:
        ext = doc.Extension
    except Exception as exc:
        result["error"] = f"doc.Extension failed: {exc!r}"
        return result

    # Seat-validated (SW 2024 SP1, 2026-06-01): ``CreateMassProperty`` is
    # exposed as a property-get on the typed ``IModelDocExtension`` wrapper.
    # Late-bound ``ext.CreateMassProperty()`` (as method-call) raises
    # ``Member not found``. Route via typed() and read without parens.
    try:
        from .com.earlybind import typed
        from .com.sw_type_info import wrapper_module
        mod = wrapper_module()
        text = typed(ext, "IModelDocExtension", module=mod)
        mp = text.CreateMassProperty  # property-get
        if callable(mp):
            mp = mp()
    except Exception as exc:
        result["error"] = f"CreateMassProperty failed: {exc!r}"
        return result

    if mp is None:
        result["error"] = "CreateMassProperty returned None"
        return result

    inertia = read_inertia(mp, mod=mod)
    result.update(inertia)
    result["ok"] = True
    return result
