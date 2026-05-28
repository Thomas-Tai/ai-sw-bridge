"""``@com_tool`` decorator + tool-registration helpers (W5.4).

The ``@com_tool`` decorator is the **single load-bearing safety
invariant** of the MCP server: every COM-touching tool MUST go
through the ComExecutor's STA-threaded worker, or pywin32 surfaces
the cross-thread bug as ``AttributeError`` at attribute lookup
(see ``docs/com_failure_modes.md`` row M-XX).

Forgetting the decorator on a COM-touching tool is a real bug. The
contract test ``test_all_com_tools_have_decorator`` walks the
registered tool set after server creation and asserts every tool
that calls into ``runtime.adapter`` carries ``_is_com_tool = True``.

Design: ``docs/mcp_server_design.md`` §4, §10.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)


T = TypeVar("T")


def com_tool(fn: Callable[..., T]) -> Callable[..., T]:
    """Wrap an MCP tool so its body runs on the ComExecutor thread.

    The wrapper closes over args/kwargs and submits a thunk to
    ``runtime.executor.run(...)``. Result and exceptions propagate
    through the future, so the MCP client sees the same return value
    or error it would see from a single-threaded call.

    Args:
        fn: The tool implementation. Typically delegates to an
            ``ai_sw_bridge.observe.sw_*`` function or to
            ``ai_sw_bridge.spec.builder.build``.

    Returns:
        A wrapped callable with ``_is_com_tool = True`` so the
        contract test can verify wrapping.

    Notes:
        The wrapper imports :mod:`ai_sw_bridge.mcp.runtime` lazily
        because the runtime is set at server creation, after
        decorators run at import time.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Late import so decorators can run at module import time,
        # before ``create_server`` has wired the runtime reference.
        from . import runtime as _rt_module

        rt = _rt_module._current_runtime
        if rt is None:
            raise RuntimeError(
                "MCP ServerRuntime is not wired yet — "
                "call create_server(runtime) before invoking tools"
            )
        # Fail fast with a reconnect hint when the SW process died
        # (W5.6). The executor's run() would surface the next queued
        # call as ConnectionError, but tools should not have to wait
        # for that; the is_sw_dead flag is the authoritative signal.
        if rt.executor.is_sw_dead:
            raise RuntimeError(
                "SOLIDWORKS process is no longer reachable "
                "(ComExecutor.is_sw_dead=True). Call the sw_reconnect "
                "tool to re-acquire SldWorks.Application on a fresh "
                "STA thread, or restart the MCP server."
            )
        return rt.executor.run(lambda: fn(*args, **kwargs))

    # Tag the wrapper so the contract test can find it.
    wrapper._is_com_tool = True  # type: ignore[attr-defined]
    return wrapper


def is_com_tool(fn: Callable[..., Any]) -> bool:
    """Return True iff *fn* was wrapped with :func:`com_tool`.

    Used by the contract test to walk the registered tool set and
    assert each COM-touching tool has the wrapping. The check is
    "does the wrapper carry the tag?", not "does the function name
    look com-y" — registration is the source of truth.
    """
    return bool(getattr(fn, "_is_com_tool", False))
