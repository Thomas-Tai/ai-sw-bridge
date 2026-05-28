"""COM connection management + STA executor for Lane M.

- ``connection.py`` — stale-handle detection and reconnect.
- ``executor.py`` — single-threaded STA executor (W5.1, Lane M).
"""

from .connection import (
    STALE_HANDLE_HRESULTS,
    is_stale_handle_error,
    reconnect_sw_app,
    with_reconnect,
)
from .executor import ComExecutor

__all__ = [
    "STALE_HANDLE_HRESULTS",
    "ComExecutor",
    "is_stale_handle_error",
    "reconnect_sw_app",
    "with_reconnect",
]
