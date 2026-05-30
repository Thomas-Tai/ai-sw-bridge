"""Early-binding typed-interface wrappers for OUT-param / Callout marshaling.

Late-bound pywin32 (dynamic ``Dispatch``) cannot marshal SOLIDWORKS methods
that return values through ``[out]`` parameters or take ``[out] IDispatch``
Callout args. The seat-run spikes pinned this down precisely:

  * ``IModelDocExtension.GetObjectByPersistReference3`` (persist write-back —
    the durable-selection keystone) → ``[out] long`` error param unreachable.
  * ``IModelDoc2.SelectByID2`` / ``Select4`` Callout ``[out] IDispatch`` →
    ``DISP_E_TYPEMISMATCH``.

The decisive ``spikes/v0_15/spike_earlybind_persist.py`` (S-EARLYBIND = PASS,
SW 2024 SP1) proved Python **early** binding clears that wall *without* leaving
the out-of-process, JSON-only-agent design: under a typed
``IModelDocExtension``, ``GetObjectByPersistReference3(pid)`` returns
``(<entity>, 0)`` — the ``[out]`` error code arrives as the 2nd tuple element,
the object resolves, survives a rebuild, and is selectable. No in-process .NET
add-in ("Route-C") is required.

The non-obvious part is *acquiring* the typed wrapper. Every win32com
convenience path (``EnsureDispatch`` / ``Dispatch`` / ``CastTo``) fails because
SW objects refuse ``IDispatch::GetTypeInfo``. The working pattern, proven by
the spike, is to construct the typed wrapper class **directly from the raw
PyIDispatch**::

    mod = sw_type_info.wrapper_module()        # the gen_py makepy module
    ext = mod.IModelDocExtension(doc.Extension._oleobj_)
    entity, err = ext.GetObjectByPersistReference3(pid)

That uses makepy's compiled-in dispids; no ``GetTypeInfo`` round-trip happens.
``com.sw_type_info`` already owns loading that module (and probing the right SW
major); this module adds the thin, proven typed-wrap on top.

Hybrid binding, not a rewrite
-----------------------------
Early-bound typed objects expose the typelib's real property/method split, so
some calls the bridge currently reaches as auto-invoked attributes (e.g.
``RevisionNumber``) become methods that must be *called*. The migration is
therefore **surgical**: keep late binding by default and typed-wrap *only* the
specific objects whose ``[out]``/Callout methods need it. The agent-safety
model is untouched — there is still no agent COM access; the JSON authoring
surface (invariant #2) and the zero-arbitrary-code rule (invariant #3) do not
change. This helper is the durable home for that selective wrapping.
"""

from __future__ import annotations

import logging
from typing import Any

from .sw_type_info import wrapper_module

logger = logging.getLogger(__name__)


class EarlyBindError(RuntimeError):
    """Raised when a typed early-bound wrapper cannot be constructed.

    Carries a specific, actionable message (wrapper module unavailable,
    unknown interface, or a raw object that exposes no ``_oleobj_``) so call
    sites can decide whether to fall back to the late-bound path.
    """


def typed(obj: Any, iface: str, *, module: Any | None = None) -> Any:
    """Wrap a late-bound SW dispatch in its early-bound typed interface.

    This is the proven OUT-param/Callout escape hatch: it constructs the
    makepy interface class directly from ``obj``'s raw ``_oleobj_``, bypassing
    the ``GetTypeInfo`` round-trip that ``Dispatch``/``CastTo`` trip on.

    Args:
        obj: A pywin32 dispatch wrapping a SOLIDWORKS COM object (e.g.
            ``doc.Extension``, or a face/edge entity).
        iface: The typed interface name as declared in the type library
            (e.g. ``"IModelDocExtension"``, ``"IEntity"``).
        module: The gen_py wrapper module to source the interface class from.
            Defaults to the shared module loaded by ``com.sw_type_info``.

    Returns:
        The early-bound typed wrapper. Methods with ``[out]`` params return
        those values as trailing tuple elements.

    Raises:
        EarlyBindError: if ``obj`` is ``None`` or lacks ``_oleobj_``, the
            wrapper module is unavailable, or ``iface`` is not in the module.
    """
    if obj is None:
        raise EarlyBindError(f"cannot typed-wrap None as {iface!r}")

    mod = module if module is not None else wrapper_module()
    if mod is None:
        raise EarlyBindError(
            "SOLIDWORKS gen_py wrapper unavailable; cannot construct typed "
            f"{iface!r}. Run: python -m win32com.client.makepy "
            '"...\\SOLIDWORKS\\sldworks.tlb"'
        )

    cls = getattr(mod, iface, None)
    if cls is None:
        raise EarlyBindError(
            f"interface {iface!r} not found in gen_py wrapper "
            f"{getattr(mod, '__name__', mod)!r}"
        )

    raw = getattr(obj, "_oleobj_", None)
    if raw is None:
        raise EarlyBindError(
            f"object {type(obj).__name__!r} exposes no _oleobj_; it is not a "
            "pywin32 dispatch and cannot be typed-wrapped"
        )

    return cls(raw)


def typed_extension(doc: Any, *, module: Any | None = None) -> Any:
    """Return a typed ``IModelDocExtension`` for ``doc`` — the persist-ref path.

    Convenience for the keystone use: durable selection round-trips through
    ``GetPersistReference3`` / ``GetObjectByPersistReference3`` on the typed
    extension. Equivalent to ``typed(doc.Extension, "IModelDocExtension")``.
    """
    if doc is None:
        raise EarlyBindError("cannot get typed Extension of None doc")
    return typed(doc.Extension, "IModelDocExtension", module=module)


def is_early_bound(obj: Any) -> bool:
    """True if ``obj`` is a gen_py (early-bound) typed wrapper.

    Lets hybrid call sites assert they are holding the typed object before
    invoking an ``[out]``-param method, rather than silently falling back to
    the late-bound failure mode.
    """
    return "gen_py" in type(obj).__module__


__all__ = [
    "EarlyBindError",
    "is_early_bound",
    "typed",
    "typed_extension",
]
