"""Stale COM handle detection and reconnect logic.

When the SW process dies mid-build, the cached IDispatch proxy becomes
stale. Subsequent COM calls raise pywintypes.com_error with specific
HRESULTs. This module detects those HRESULTs and, when reconnect is
enabled, tears down the old proxy and re-acquires SldWorks.Application.

COM marshaling risk: re-acquiring the IDispatch chain mid-build means
the new SW process has NO knowledge of the partially-built part. The
reconnect only retries the CURRENT operation; it does NOT rewind or
replay completed steps. The resulting model state is undefined — the
user must review the checkpoint to verify.

Per spec.md §6.9 ComExecutor death-recovery and audit §6.5.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, TypeVar

logger = logging.getLogger("ai_sw_bridge.com.connection")

# HRESULTs that indicate a stale handle (SW process died or disconnected).
# Per audit §6.5 and spec.md §6.9. List to be confirmed empirically.
STALE_HANDLE_HRESULTS: frozenset[int] = frozenset(
    {
        0x800706BA,  # RPC_S_SERVER_UNAVAILABLE
        0x80010108,  # RPC_E_DISCONNECTED
    }
)

F = TypeVar("F", bound=Callable[..., Any])


def is_stale_handle_error(exc: Exception) -> bool:
    """Check if an exception is a stale-handle COM error.

    Works with both real pywintypes.com_error and any exception with
    an `hresult` attribute (for testing without pywin32).
    """
    hresult = getattr(exc, "hresult", None)
    if hresult is None:
        # pywintypes.com_error stores hresult as the first element
        args = getattr(exc, "args", None)
        if args and isinstance(args, tuple) and len(args) >= 1:
            try:
                hresult = int(args[0])
            except (TypeError, ValueError):
                return False
    return hresult in STALE_HANDLE_HRESULTS


def reconnect_sw_app() -> Any:
    """Tear down the old SW Application handle and re-acquire it.

    Calls release_sw_app() to drop the cached proxy, then get_sw_app()
    to re-dispatch. Returns the new SldWorks.Application IDispatch.
    """
    from ..sw_com import get_sw_app, release_sw_app

    release_sw_app()
    sw = get_sw_app()
    logger.warning(
        "COM handle re-acquired mid-build; review checkpoint to verify state."
    )
    print(
        "COM handle re-acquired mid-build; review checkpoint to verify state.",
        file=sys.stderr,
    )
    return sw


def with_reconnect(
    fn: Callable[..., Any],
    *args: Any,
    reconnect: bool = False,
    **kwargs: Any,
) -> Any:
    """Call fn(*args, **kwargs), reconnecting on stale-handle errors.

    If reconnect is False, stale-handle errors propagate as-is with a
    hint appended. If reconnect is True, one reconnect attempt is made
    before re-raising.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if not is_stale_handle_error(exc):
            raise
        if not reconnect:
            hint = "Restart SW or use --reconnect to attempt mid-build recovery (experimental)."
            logger.error("stale COM handle: %s", hint)
            raise
        # Reconnect and retry once
        reconnect_sw_app()
        return fn(*args, **kwargs)
