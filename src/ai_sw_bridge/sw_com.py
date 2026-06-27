"""
Shared SOLIDWORKS COM helpers.

Every observation/mutation tool imports from here. Keeps the late-binding
property-vs-method handling and SW constants in one place.

Why we prefer late binding:
    SldWorks.Application usually refuses typelib generation via
    win32com.client.gencache.EnsureDispatch (raises "this COM object can
    not automate the makepy process" on most installs), so we Dispatch
    late-bound. But a gen_py typelib cached by some *other* tool means
    GetActiveObject can still hand back an early-bound object, where a
    zero-arg method is a real bound method rather than an auto-invoked
    property. `resolve()` below tolerates both bindings so the entry
    points (probe, version gate, observe reads) stay correct either way.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import pythoncom
import win32com.client

logger = logging.getLogger("ai_sw_bridge.sw_com")

# Minimum verified SOLIDWORKS version. Every COM API surface this package
# drives has been validated on this build; get_sw_app() refuses to run on
# anything older (see _check_sw_version).
SW_VERSION_VERIFIED = (32, 1)  # SW 2024 SP1 -> RevisionNumber "32.1.0"


SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3
DOC_TYPE_NAMES = {
    SW_DOC_PART: "Part",
    SW_DOC_ASSEMBLY: "Assembly",
    SW_DOC_DRAWING: "Drawing",
}

# swOpenDocOptions_e.swOpenDocOptions_Silent — the OpenDoc6 options flag that
# suppresses the open dialog. Canonical home for the OpenDoc6 call shape shared
# by mutate / export_urdf (was duplicated as a private `_SW_OPEN_SILENT = 1`).
SW_OPEN_SILENT = 1


def resolve(obj: Any, name: str) -> Any:
    """
    Read `obj.name`, tolerating both COM binding modes.

    pywin32 *late*-binding (no typelib / makepy) auto-invokes zero-arg
    methods on attribute access, so properties and zero-arg methods are
    both reached the same way: plain `getattr`. But if a makepy / gen_py
    typelib is cached for SOLIDWORKS (the SW installer or any prior
    `EnsureDispatch` anywhere on the box can create one), `GetActiveObject`
    hands back an *early*-bound object where a zero-arg method is a real
    Python bound method, NOT an auto-invoked property. A plain `getattr`
    then returns the *method object* instead of its value -- e.g.
    `RevisionNumber` comes back as ``<bound method ...>`` instead of
    ``"32.1.0"``, which silently broke the version gate and `ai-sw-probe`.

    So: if the attribute is a genuine bound method, invoke it. We key on
    `inspect.ismethod`, NOT `callable()`, on purpose -- late-bound
    `CDispatch` sub-objects report ``callable() == True`` but must never be
    called (calling one throws DISP_E_MEMBERNOTFOUND, -2147352573). A
    `CDispatch` is not a bound method, so `ismethod` correctly leaves it
    untouched. Callers still invoke methods that take *arguments*
    explicitly; this only auto-reads the zero-arg case `resolve` is for.
    """
    attr = getattr(obj, name)
    if inspect.ismethod(attr):
        return attr()
    return attr


_CACHED_SW_APP: Any | None = None
_COINIT_DONE: bool = False


def get_sw_app() -> Any:
    """Attach to the running SldWorks.Application, or launch one.

    Tries ``GetActiveObject`` first to attach to a SOLIDWORKS instance
    already in the COM Running Object Table (ROT). If that fails (no
    running instance registered, or the calling process can't see it),
    falls back to ``Dispatch`` which either re-uses an existing
    instance or auto-launches a fresh one per the SW COM registration.

    The GetActiveObject-first ordering matters for out-of-process
    callers (MCP server subprocess, IDE plugins) that would otherwise
    spawn a *separate* headless SW instance and miss the user's
    foreground document. Caught by v0.13 Wave 5 Phase 3 audit when a
    Claude-Desktop-launched ``ai-sw-mcp.exe`` created its own ghost
    SW process instead of attaching to the foreground one.

    Caches the result + the ``CoInitialize`` call. Repeated calls in
    the same process reuse the same handle -- important for long-
    running services (MCP wrappers, future servers) that otherwise
    leak STA apartments and re-dispatch SW per request.

    Raises ``pywintypes.com_error`` only if both ``GetActiveObject``
    AND ``Dispatch`` fail (typically: SW not installed or registry
    misconfigured). Call ``release_sw_app()`` to drop the cache
    (e.g. when SW has been restarted and the old handle is dead).
    """
    global _CACHED_SW_APP, _COINIT_DONE
    if not _COINIT_DONE:
        pythoncom.CoInitialize()
        _COINIT_DONE = True
    if _CACHED_SW_APP is None:
        # ROT-attach first: prefer an already-running SW instance so
        # out-of-process callers (MCP subprocess, IDE plugins) see
        # the user's foreground session and its open documents.
        try:
            _CACHED_SW_APP = win32com.client.GetActiveObject("SldWorks.Application")
            logger.debug("attached to running SldWorks via GetActiveObject")
        except (
            Exception
        ) as exc:  # noqa: BLE001 -- broad: pywintypes.com_error + OSError
            logger.debug("GetActiveObject failed (%r); falling back to Dispatch", exc)
            _CACHED_SW_APP = win32com.client.Dispatch("SldWorks.Application")
        _check_sw_version(_CACHED_SW_APP)
    return _CACHED_SW_APP


def _check_sw_version(sw: Any) -> None:
    """Fail fast if the running SW version is below the verified minimum.

    The COM API surfaces this package drives are validated on
    SW_VERSION_VERIFIED (SOLIDWORKS 2024 SP1). An older build can marshal
    calls differently; rather than fail deep inside a build with a cryptic
    COM error, refuse up front with a clear message. (Enhancement plan P3.3.)
    """
    try:
        # Route through resolve() so the version gate reads a real value
        # under BOTH bindings. Reading sw.RevisionNumber directly returns a
        # bound method (not "32.1.0") on an early-bound handle, which made
        # this gate silently no-op on any box with a cached gen_py typelib.
        rev = resolve(sw, "RevisionNumber")  # e.g. "32.1.0"
        parts = tuple(int(x) for x in str(rev).split("."))
    except Exception:
        # RevisionNumber unreadable -- log and continue rather than block.
        logger.warning("could not read SW RevisionNumber; skipping version check")
        return
    if parts[:2] < SW_VERSION_VERIFIED:
        floor = ".".join(str(x) for x in SW_VERSION_VERIFIED)
        raise RuntimeError(
            f"SOLIDWORKS {rev} is older than the verified minimum {floor} "
            f"(SW 2024 SP1). ai-sw-bridge's COM calls are not validated on "
            f"this build -- upgrade SOLIDWORKS, or relax SW_VERSION_VERIFIED "
            f"in sw_com.py at your own risk."
        )


def release_sw_app() -> None:
    """Drop the cached SW Application handle. Subsequent get_sw_app() calls
    will re-dispatch. Use after SW has been restarted, or in test teardown."""
    global _CACHED_SW_APP
    _CACHED_SW_APP = None


def get_active_doc(sw: Any) -> Any | None:
    """Return the active document object, or None if nothing is open."""
    return sw.ActiveDoc
