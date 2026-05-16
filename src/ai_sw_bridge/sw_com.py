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

from typing import Any

import pythoncom
import win32com.client


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


def get_sw_app() -> Any:
    """Dispatch (or attach to) the running SldWorks.Application.

    Raises pywintypes.com_error if SOLIDWORKS is not running. The caller
    can catch and surface a friendlier message ("please open SOLIDWORKS").
    """
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("SldWorks.Application")


def get_active_doc(sw: Any) -> Any | None:
    """Return the active document object, or None if nothing is open."""
    return sw.ActiveDoc
