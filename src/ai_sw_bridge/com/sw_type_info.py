"""SolidWorks type-library introspection for robust COM method resolution (W5.3).

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

The original lives at ``src/solidworks_mcp/adapters/sw_type_info.py`` in
the upstream. This port:

- Replaces the upstream's ``loguru`` dependency with the stdlib
  ``logging`` module (the bridge ships zero third-party logging deps).
- Adds SPDX port-attribution headers.
- Keeps the core logic (lazy gen_py loading, per-interface method
  flagging, incrementality cache) identical apart from the cherry-picked
  cache fix noted below.

Cherry-picked from upstream *after* the base port above: the flag-cache
soundness fix from commit ``7695ae8956ee4a9cfe430eb837f5308ce7f36610``
(2026-08-13, "Stop the flag cache trusting a recycled address"). Only that
fix was taken; the rest of the upstream file has moved on and is not ported.
See :func:`_flagged_interfaces`.

Background: pywin32's late-binding (``CDispatch``) sometimes resolves SW
zero-argument methods (``GetType``, ``GetTitle``, ``GetPathName``,
``RevisionNumber`` ...) as *properties* instead of methods. Calling them
raises ``TypeError: 'int'/'str' object is not callable`` because the
property getter returns the value, and Python tries to call the value.

Fix: call ``CDispatch._FlagAsMethod(name)`` for each method name **that
actually belongs to the object's COM interface**. The calls tell pywin32
to resolve ``name`` via method invocation (IDispatch ``Invoke``), not
property access.

This module:

1. Loads the makepy-generated wrapper for ``sldworks.tlb`` (``gen_py``).
2. Builds per-interface sets of method names (``ISldWorks``, ``IModelDoc2``,
   ``IAssemblyDoc``, ``IPartDoc``, ``IDrawingDoc`` ...).
3. Exposes ``flag_methods(obj, *interfaces)`` to flag a dispatch in one shot.

Why per-interface rather than flagging everything: flagging an unknown name
triggers a COM ``GetIDsOfNames`` round-trip that fails with ``Unknown name.``.
Those round-trips are ~5 ms each; the full SW TLB has ~6 000 method names
across 482 interfaces, so a naive flag-everything approach costs ~30 s per
object. Per-interface flagging is ~1-3 s.

Fallback: if the gen_py wrapper is missing (e.g. fresh install on a new box),
we attempt lazy generation via ``gencache.EnsureModule``. If that also fails,
``flag_methods`` silently becomes a no-op; callers will fall back to the
original ``TypeError`` symptom on affected methods, but everything else still
works.
"""

from __future__ import annotations

import inspect
import logging
import weakref
from typing import Any

logger = logging.getLogger(__name__)

try:
    import win32com.client  # noqa: F401 — optional Windows dep
    from win32com.client import DispatchBaseClass, gencache

    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


SW_TLB_IID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

_wrapper_module: Any | None = None
_interface_methods: dict[str, frozenset[str]] = {}
# Per-object record of which interfaces have already been flagged. Keyed by
# id(obj) so ``flag_methods(doc, 'IModelDoc2')`` followed by
# ``flag_methods(doc, 'IAssemblyDoc')`` does incremental work, not a no-op.
# The value carries a weak reference to the object the entry describes; that
# weakref is what makes the id() key safe to trust. See _flagged_interfaces.
_flag_cache: dict[int, tuple[weakref.ref[Any] | None, set[str]]] = {}


def _load_wrapper() -> None:
    """Load the gen_py wrapper and extract per-interface method names.

    Tries ``GetModuleForTypelib`` first (fast path, no COM work), falls back
    to ``EnsureModule`` (may trigger makepy generation), then gives up and
    logs a warning. Probes common SW major versions (35..30) because the
    minor/major numbers change per SW year.
    """
    global _wrapper_module

    if not PYWIN32_AVAILABLE:
        return

    for major in (35, 34, 33, 32, 31, 30):
        try:
            mod = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
        except Exception:
            mod = None
        if mod is not None:
            _wrapper_module = mod
            break

    if _wrapper_module is None:
        for major in (35, 34, 33, 32, 31, 30):
            try:
                gencache.EnsureModule(SW_TLB_IID, 0, major, 0)
                _wrapper_module = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
                if _wrapper_module is not None:
                    break
            except Exception:
                continue

    if _wrapper_module is None:
        logger.warning(
            "SolidWorks gen_py wrapper not available; method flagging "
            "disabled. Zero-arg SW methods may raise TypeError. To fix, "
            "run: python -m win32com.client.makepy "
            '"C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"'
        )
        return

    for name in dir(_wrapper_module):
        cls = getattr(_wrapper_module, name, None)
        if not (inspect.isclass(cls) and issubclass(cls, DispatchBaseClass)):
            continue
        method_names: set[str] = set()
        for attr_name, attr in vars(cls).items():
            if attr_name.startswith("_"):
                continue
            if callable(attr):
                method_names.add(attr_name)
        if method_names:
            _interface_methods[name] = frozenset(method_names)

    logger.info(
        "SolidWorks type info loaded: %d interfaces, wrapper=%s",
        len(_interface_methods),
        _wrapper_module.__name__,
    )


def _ensure_loaded() -> None:
    """Lazy-load the wrapper on first use."""
    if _wrapper_module is None and PYWIN32_AVAILABLE:
        _load_wrapper()


def wrapper_module() -> Any | None:
    """Return the loaded gen_py (makepy) wrapper module, lazy-loading on first
    use, or ``None`` if pywin32/the wrapper is unavailable.

    The early-binding typed-wrap helpers (``com.earlybind``) need the module
    object itself to construct typed interface proxies; this is the single
    accessor for it so module loading stays owned by one place.
    """
    _ensure_loaded()
    return _wrapper_module


def interface_method_names(interface: str) -> frozenset[str]:
    """Return the set of method names declared by the given SW interface.

    Args:
        interface: Interface name as it appears in the type library
            (e.g. ``"ISldWorks"``, ``"IModelDoc2"``).

    Returns:
        Immutable set of method names, or an empty set if the interface is
        unknown or the wrapper isn't loaded.
    """
    _ensure_loaded()
    return _interface_methods.get(interface, frozenset())


DOC_TYPE_TO_INTERFACES: dict[int, tuple[str, ...]] = {
    1: ("IModelDoc2", "IPartDoc"),
    2: ("IModelDoc2", "IAssemblyDoc"),
    3: ("IModelDoc2", "IDrawingDoc"),
}


def _flagged_interfaces(obj: Any) -> set[str]:
    """Return the set of interfaces already flagged on ``obj``.

    The entry is keyed by ``id(obj)`` for speed, but is only trusted while the
    stored weak reference still resolves to *this same object*. Without that
    check the cache is unsound: an id is unique only among **live** objects,
    and CPython hands a freed block straight back to the next allocation of
    the same size. A fresh COM dispatch landing on a dead one's address was
    judged "already flagged", so :func:`flag_methods` returned without flagging
    anything — after which that object's methods resolve as *properties* and
    SolidWorks answers ``Member not found``. The failure is intermittent and
    allocator-dependent, which is what makes it so hard to attribute.

    :func:`invalidate_flag_cache` documents the same hazard but has to be
    called explicitly, and callers have no way to know when a dispatch has been
    released. This makes the cache self-healing instead.

    Objects that do not support weak references (some test doubles) are simply
    not cached; they are flagged every time, which is correct if slower.

    Args:
        obj: A pywin32 ``CDispatch`` (or any object) to look up.

    Returns:
        The live set of interface names already flagged on ``obj``. Mutating
        it updates the cache entry in place.
    """
    key = id(obj)
    entry = _flag_cache.get(key)
    if entry is not None:
        ref, cached = entry
        if ref is None or ref() is obj:
            return cached
        # Stale: the object this entry described is gone and its address has
        # been recycled. Drop it and start fresh for the new occupant.
        del _flag_cache[key]

    names: set[str] = set()
    try:
        _flag_cache[key] = (weakref.ref(obj), names)
    except TypeError:
        # Not weak-referenceable, so a later address reuse would be
        # undetectable. Skip caching rather than risk a stale entry.
        pass
    return names


def flag_methods(obj: Any, *interfaces: str) -> int:
    """Flag SW methods on ``obj`` so pywin32 dispatches them as methods.

    Safe to call repeatedly on the same object — results are cached by
    ``id(obj)``, guarded by a weakref so a recycled address cannot be
    mistaken for an already-flagged object. Unknown method names are
    silently skipped.

    Args:
        obj: A pywin32 ``CDispatch`` wrapping a SolidWorks COM object.
        *interfaces: One or more interface names whose methods to flag.

    Returns:
        Number of methods successfully flagged.
    """
    _ensure_loaded()

    if not _interface_methods or obj is None:
        return 0

    already = _flagged_interfaces(obj)

    new_interfaces = [i for i in interfaces if i not in already]
    if not new_interfaces:
        return 0

    names: set[str] = set()
    for iface in new_interfaces:
        names.update(_interface_methods.get(iface, ()))

    flagged = 0
    for name in names:
        try:
            obj._FlagAsMethod(name)
            flagged += 1
        except Exception:
            pass

    already.update(new_interfaces)
    return flagged


def flagged(obj: Any, *interfaces: str) -> Any:
    """Flag ``obj``'s methods then return ``obj`` — call-chain friendly.

    If ``obj`` is ``None``, passes through unchanged.
    """
    if obj is not None:
        flag_methods(obj, *interfaces)
    return obj


def flag_doc(obj: Any, doc_type: int) -> int:
    """Flag methods for a SolidWorks document dispatch given its type.

    Args:
        obj: ``CDispatch`` wrapping the document.
        doc_type: Value returned by ``swDoc.GetType()`` — 1=Part, 2=Assembly,
            3=Drawing.

    Returns:
        Number of methods flagged.
    """
    interfaces = DOC_TYPE_TO_INTERFACES.get(doc_type, ("IModelDoc2",))
    return flag_methods(obj, *interfaces)


def invalidate_flag_cache(obj: Any | None = None) -> None:
    """Forget that ``obj`` has been flagged, or clear the cache entirely.

    Since the flag cache became weakref-guarded (see
    :func:`_flagged_interfaces`) a recycled address can no longer be mistaken
    for an already-flagged object, so this is no longer *required* for
    correctness when a dispatch is closed and re-acquired. It remains useful to
    force a re-flag explicitly, and to drop entries in tests.
    """
    if obj is None:
        _flag_cache.clear()
    else:
        _flag_cache.pop(id(obj), None)


__all__ = [
    "DOC_TYPE_TO_INTERFACES",
    "SW_TLB_IID",
    "flag_doc",
    "flag_methods",
    "flagged",
    "interface_method_names",
    "invalidate_flag_cache",
    "wrapper_module",
]
