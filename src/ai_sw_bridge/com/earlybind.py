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


def typed_qi(obj: Any, iface: str, *, module: Any | None = None) -> Any:
    """QI-validated typed wrap — for objects whose interface must be *proven*.

    Where :func:`typed` wraps by compiled dispid (sound only when the object is
    already known to be ``iface`` — e.g. ``doc.Extension`` genuinely is
    ``IModelDocExtension``), ``typed_qi`` first asks the C++ ``IUnknown`` whether
    it implements ``iface`` via a real ``QueryInterface`` against the interface
    IID. This is the proven, side-effect-free way to acquire *and identify*
    objects whose runtime type is unknown — notably the ``IFeatureData`` objects
    returned by ``IFeatureManager.CreateDefinition`` / ``IFeature.GetDefinition``,
    where a dispid guess would silently invoke a colliding member instead of
    failing (S-QI-FEATUREDATA = DISCRIMINATING, SW 2024 SP1).

    QI never invokes a member, and it does not use ``GetTypeInfo`` (which SW
    refuses), so a wrong ``iface`` fails cleanly with ``E_NOINTERFACE`` rather
    than returning a misidentified object.

    Two non-obvious mechanics this encapsulates:

    * The IID is read from the makepy class's ``.CLSID`` — no hand-copied GUIDs.
    * The QI passes ``IID_IDispatch`` as the wrapping hint. SW feature-data
      interfaces are *dual* but have no compiled pywin32 gateway, so a bare
      ``QueryInterface(iid)`` raises ``TypeError`` **on success** — easily
      mistaken for failure. The hint wraps the (QI-validated) pointer as
      ``IDispatch`` so makepy can then invoke it by dispid safely.

    Args:
        obj: A pywin32 dispatch wrapping the untyped SOLIDWORKS object.
        iface: The typed interface name to acquire and validate against
            (e.g. ``"IShellFeatureData"``).
        module: The gen_py wrapper module. Defaults to the shared module.

    Returns:
        The early-bound typed wrapper, *after* QI has confirmed the object
        implements ``iface``.

    Raises:
        EarlyBindError: if ``obj`` is ``None`` / lacks ``_oleobj_``, the wrapper
            module or interface is unavailable, the interface class carries no
            IID, or — the discriminating case — the object does **not** implement
            ``iface`` (``E_NOINTERFACE``). Callers that probe a type use this
            exception as the "not that interface" signal.
    """
    if obj is None:
        raise EarlyBindError(f"cannot QI-wrap None as {iface!r}")

    mod = module if module is not None else wrapper_module()
    if mod is None:
        raise EarlyBindError(
            f"SOLIDWORKS gen_py wrapper unavailable; cannot QI-wrap {iface!r}."
        )

    cls = getattr(mod, iface, None)
    if cls is None:
        raise EarlyBindError(
            f"interface {iface!r} not found in gen_py wrapper "
            f"{getattr(mod, '__name__', mod)!r}"
        )

    iid = getattr(cls, "CLSID", None)
    if iid is None:
        raise EarlyBindError(
            f"interface {iface!r} carries no CLSID/IID; cannot QueryInterface"
        )

    raw = getattr(obj, "_oleobj_", None)
    if raw is None:
        raise EarlyBindError(
            f"object {type(obj).__name__!r} exposes no _oleobj_; it is not a "
            "pywin32 dispatch and cannot be QI-wrapped"
        )

    import pythoncom  # lazy: keep the module importable without pywin32

    try:
        disp = raw.QueryInterface(iid, pythoncom.IID_IDispatch)
    except pythoncom.com_error as e:
        hr = getattr(e, "hresult", None)
        if hr is None and getattr(e, "args", None):
            hr = e.args[0]
        hr_u = (hr & 0xFFFFFFFF) if isinstance(hr, int) else None
        if hr_u == 0x80004002:  # E_NOINTERFACE — the object is not this type
            raise EarlyBindError(
                f"object does not implement {iface!r} (E_NOINTERFACE)"
            ) from e
        raise EarlyBindError(
            f"QueryInterface for {iface!r} failed (hresult {hr_u:#010x})"
            if hr_u is not None
            else f"QueryInterface for {iface!r} failed"
        ) from e

    return cls(disp)


def typed_extension(doc: Any, *, module: Any | None = None) -> Any:
    """Return a typed ``IModelDocExtension`` for ``doc`` — the persist-ref path.

    Convenience for the keystone use: durable selection round-trips through
    ``GetPersistReference3`` / ``GetObjectByPersistReference3`` on the typed
    extension. Equivalent to ``typed(doc.Extension, "IModelDocExtension")``.
    """
    if doc is None:
        raise EarlyBindError("cannot get typed Extension of None doc")
    return typed(doc.Extension, "IModelDocExtension", module=module)


def read_persist_reference(doc: Any, entity: Any) -> bytes | None:
    """Read the durable persist token for *entity* via a typed Extension.

    The canonical OUT-param read this module exists for:
    ``IModelDocExtension.GetPersistReference3(entity)`` through an early-bound
    typed Extension (late binding cannot marshal the result reliably). Returns
    the raw token bytes, or ``None`` if the token can't be read for any reason
    (no Extension, API unavailable, marshaler failure, or a token shape that
    won't coerce to bytes). Never raises — ``None`` is the first-class
    "persist unavailable" state callers degrade on.

    This is the single low-level read shared by the build-time capture path
    (``brep.interrogator``) and the resolve-time bridge
    (``selection.live.capture_persist_id``), so both produce identical tokens.
    """
    if doc is None or entity is None:
        return None
    try:
        ext = typed_extension(doc)
        pid = ext.GetPersistReference3(entity)
    except EarlyBindError:
        return None
    except Exception:  # noqa: BLE001 — any COM failure degrades to None
        return None
    if pid is None:
        return None
    try:
        return bytes(pid)
    except Exception:  # noqa: BLE001 — token shape not coercible
        return None


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
    "read_persist_reference",
    "typed",
    "typed_extension",
    "typed_qi",
]
