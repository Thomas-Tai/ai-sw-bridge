"""COM connection management + STA executor + type info for Lane M.

- ``connection.py`` — stale-handle detection and reconnect.
- ``executor.py`` — single-threaded STA executor (W5.1, Lane M).
- ``sw_type_info.py`` — per-interface method flagging (W5.3).
"""

from .connection import (
    STALE_HANDLE_HRESULTS,
    is_stale_handle_error,
    reconnect_sw_app,
    with_reconnect,
)
from .executor import ComExecutor
from .sw_type_info import (
    DOC_TYPE_TO_INTERFACES,
    flag_doc,
    flag_methods,
    flagged,
    interface_method_names,
    invalidate_flag_cache,
)

__all__ = [
    "DOC_TYPE_TO_INTERFACES",
    "STALE_HANDLE_HRESULTS",
    "ComExecutor",
    "flag_doc",
    "flag_methods",
    "flagged",
    "interface_method_names",
    "invalidate_flag_cache",
    "is_stale_handle_error",
    "reconnect_sw_app",
    "with_reconnect",
]
