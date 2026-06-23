"""Inertia-tensor observation helper — E1 (Wave-5).

Reads ``IMassProperty2`` inertia properties from a part document.

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - ``IMassProperty2`` QI returns E_NOINTERFACE — must use ``typed()``
    (by-dispid wrap), NOT ``typed_qi()``.
  - The basic properties ``Volume``, ``SurfaceArea``, ``Mass``,
    ``Density``, ``CenterOfMass`` are readable on the **late-bound**
    proxy (same as ``sw_get_volume``).
  - ``GetMomentOfInertia`` is ``GetMomentOfInertia([in] long WhereTaken)
    -> VT_VARIANT`` (dispid=12, METHOD).  The earlier "VARIANT(array)"
    diagnosis was **wrong** — it takes a single ``long`` frame selector,
    NOT a centre-of-rotation array.  Passing a plain Python ``int``
    works; it returns a 9-tuple = the row-major 3x3 inertia tensor in
    SI units (kg*m^2).  ``WhereTaken=0`` (centre of mass) is the
    physically meaningful frame and was cross-checked against the
    textbook box formula (Ixx = m/12*(h^2+d^2)); ``1`` (output coord)
    and ``2`` (model origin) return zeros unless a coordinate system is
    defined.  Seat-proven 2026-06-01, Epic A (spike ``46e6294``).
  - ``PrincipalAxesOfInertia`` (dispid=7, PROPGET) is **unreachable**
    out-of-process: COM-level DISP_E_BADPARAMCOUNT ("Invalid number of
    parameters") for every probed arg-count / invkind — the gen_py
    wrapper's arity/invkind does not match the live server.  We do NOT
    call it.  Principal moments + axes are **derived** from the inertia
    tensor via ``numpy.linalg.eigh`` — this is exact, not an
    approximation: the principal axes ARE the eigenvectors of the
    (symmetric) inertia tensor and the principal moments ARE its
    eigenvalues.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .com.earlybind import typed
from .sw_com import resolve

# IMassProperty2.GetMomentOfInertia WhereTaken selector: 0 = about the
# centre of mass (the only frame that returns a meaningful tensor without
# a user-defined output coordinate system). Seat-validated.
_WHERE_CENTER_OF_MASS = 0


def read_inertia(mp: Any, mod: Any = None) -> dict[str, Any]:
    """Extract inertia properties from an ``IMassProperty2`` object.

    ``CenterOfMass`` is read on the late-bound proxy.  The full inertia
    tensor is read via the typed wrapper's
    ``GetMomentOfInertia(0)`` (seat-proven 9-tuple, SI kg*m^2); the
    principal moments and axes are derived from it by eigendecomposition
    (``PrincipalAxesOfInertia`` is unreachable out-of-process — see the
    module docstring).  All reads fail-soft and record errors.

    Returns a dict with ``center_of_mass_mm``, ``inertia_tensor_kg_m2``
    (3x3, about the centre of mass), ``principal_moments_kg_m2``
    (eigenvalues, ascending), ``principal_axes`` (3 unit eigenvectors),
    and ``errors``.
    """
    result: dict[str, Any] = {
        "center_of_mass_mm": None,
        "inertia_tensor_kg_m2": None,
        "principal_moments_kg_m2": None,
        "principal_axes": None,
        "errors": [],
    }

    # CenterOfMass — always readable on late-bound proxy (SW returns metres).
    try:
        com = resolve(mp, "CenterOfMass")
        if com is not None and len(com) >= 3:
            result["center_of_mass_mm"] = [float(com[i]) * 1000.0 for i in range(3)]
    except Exception as exc:
        result["errors"].append(f"CenterOfMass: {exc!r}")

    # Typed wrapper for the inertia-tensor read.
    if mod is None:
        from .com.sw_type_info import wrapper_module
        mod = wrapper_module()

    try:
        mp_typed = typed(mp, "IMassProperty2", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IMassProperty2): {exc!r}")
        return result

    # GetMomentOfInertia(long WhereTaken) -> row-major 3x3 inertia tensor
    # (9-tuple, SI kg*m^2). Plain int arg; no VARIANT wrapping. Seat-proven.
    try:
        moi = mp_typed.GetMomentOfInertia(_WHERE_CENTER_OF_MASS)
        if moi is None or len(moi) < 9:
            result["errors"].append(
                f"GetMomentOfInertia(0): expected 9-tuple, got {moi!r}"
            )
        else:
            tensor = [[float(moi[i * 3 + j]) for j in range(3)] for i in range(3)]
            result["inertia_tensor_kg_m2"] = tensor
            # Principal moments + axes by eigendecomposition of the symmetric
            # tensor (exact; replaces the unreachable PrincipalAxesOfInertia).
            # eigh -> eigenvalues ascending, eigenvectors as columns.
            try:
                vals, vecs = np.linalg.eigh(np.asarray(tensor, dtype=float))
                result["principal_moments_kg_m2"] = [float(v) for v in vals]
                result["principal_axes"] = [
                    [float(vecs[r, c]) for r in range(3)] for c in range(3)
                ]
            except Exception as exc:
                result["errors"].append(f"eigh(inertia_tensor): {exc!r}")
    except Exception as exc:
        result["errors"].append(f"GetMomentOfInertia(0): {exc!r}")

    return result


def _sw_get_inertia_impl(doc: Any) -> dict[str, Any]:
    """Core: read inertia from a part document (v0.18 implementation).

    Acquires ``IMassProperty2`` via the typed
    ``IModelDocExtension.CreateMassProperty`` property-get, then
    delegates to :func:`read_inertia`. Internal callers (the
    ``SolidWorksClient.observe`` facade, the URDF orchestrator) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_inertia` free function routes here behind a
    ``PendingDeprecationWarning``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "center_of_mass_mm": None,
        "inertia_tensor_kg_m2": None,
        "principal_moments_kg_m2": None,
        "principal_axes": None,
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


