"""COM connection management with stale-handle detection and reconnect."""

from .connection import (
    STALE_HANDLE_HRESULTS,
    is_stale_handle_error,
    reconnect_sw_app,
    with_reconnect,
)
