"""
Shared SOLIDWORKS COM helpers.

Every observation/mutation tool imports from here. Keeps the late-binding
property-vs-method handling and SW constants in one place.

Why late binding only:
    SldWorks.Application does not support typelib generation via
    win32com.client.gencache.EnsureDispatch (raises "this COM object can
    not automate the makepy process" on most installs). We stick with
    win32com.client.Dispatch.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import pythoncom
import win32com.client

logger = logging.getLogger("ai_sw_bridge.sw_com")

# Minimum supported SOLIDWORKS version. All API surfaces in this package
# have been verified on this build. Older versions may work but are untested.
SW_VERSION_FLOOR = (32, 1)  # SW 2024 SP1 -> RevisionNumber "32.1.0"


SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3
DOC_TYPE_NAMES = {
    SW_DOC_PART: "Part",
    SW_DOC_ASSEMBLY: "Assembly",
    SW_DOC_DRAWING: "Drawing",
}


def resolve(obj: Any, name: str) -> Any:
    """
    Read `obj.name` via late-bound COM Dispatch.

    pywin32 late-binding (without a typelib / makepy) auto-invokes zero-arg
    methods on attribute access. So both properties and zero-arg methods
    are reached the same way: plain `getattr`. Sub-Dispatch objects come
    back as `CDispatch` instances and are *always* reported `callable=True`
    even though they are not actually callable - calling them throws
    DISP_E_MEMBERNOTFOUND (-2147352573). Never call the result here; let
    callers invoke explicitly for methods that take arguments.
    """
    return getattr(obj, name)


_CACHED_SW_APP: Any | None = None
_COINIT_DONE: bool = False


def get_sw_app() -> Any:
    """Dispatch (or attach to) the running SldWorks.Application.

    Caches the Dispatch result and the CoInitialize call. Repeated calls
    in the same process reuse the same Application handle -- important
    for long-running services (MCP wrappers, future servers) that
    otherwise leak STA apartments and re-dispatch SW per request.

    Raises pywintypes.com_error if SOLIDWORKS is not running. The caller
    can catch and surface a friendlier message ("please open SOLIDWORKS").
    Call release_sw_app() to drop the cache (e.g. when SW has been
    restarted and the old Dispatch handle is dead).
    """
    global _CACHED_SW_APP, _COINIT_DONE
    if not _COINIT_DONE:
        pythoncom.CoInitialize()
        _COINIT_DONE = True
    if _CACHED_SW_APP is None:
        _CACHED_SW_APP = win32com.client.Dispatch("SldWorks.Application")
        _check_sw_version(_CACHED_SW_APP)
    return _CACHED_SW_APP


def _check_sw_version(sw: Any) -> None:
    """Warn if the running SW version is below the tested floor."""
    try:
        rev = sw.RevisionNumber  # e.g. "32.1.0"
        parts = tuple(int(x) for x in str(rev).split("."))
        if parts[:2] < SW_VERSION_FLOOR:
            msg = (
                f"SW version {rev} is below the tested floor "
                f"{'.'.join(str(x) for x in SW_VERSION_FLOOR)}. "
                f"Some API surfaces may not work correctly."
            )
            warnings.warn(msg, stacklevel=3)
            logger.warning(msg)
    except Exception:
        pass  # non-fatal; don't block the build if version check fails


def release_sw_app() -> None:
    """Drop the cached SW Application handle. Subsequent get_sw_app() calls
    will re-dispatch. Use after SW has been restarted, or in test teardown."""
    global _CACHED_SW_APP
    _CACHED_SW_APP = None


def get_active_doc(sw: Any) -> Any | None:
    """Return the active document object, or None if nothing is open."""
    return sw.ActiveDoc
