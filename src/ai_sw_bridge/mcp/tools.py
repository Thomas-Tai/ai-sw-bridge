"""``@com_tool`` decorator + tool-registration helpers (W5.4).

The ``@com_tool`` decorator is the **single load-bearing safety
invariant** of the MCP server: every COM-touching tool MUST go
through the ComExecutor's STA-threaded worker, or pywin32 surfaces
the cross-thread bug as ``AttributeError`` at attribute lookup
(see ``docs/com_failure_modes.md`` row M-02).

Forgetting the decorator on a COM-touching tool is a real bug. The
contract test ``test_all_com_tools_have_decorator`` walks the
registered tool set after server creation and asserts every tool
that calls into ``runtime.adapter`` carries ``_is_com_tool = True``.

Design: ``docs/mcp_server_design.md`` §4, §10.
"""

from __future__ import annotations

import functools
import logging
import re
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)


T = TypeVar("T")


# Wave 5 Phase 2.5 finding: pywin32 surfaces SW process death as
# ``AttributeError('SldWorks.Application.<member>')`` from dynamic
# dispatch attribute lookup, NOT as the ``pywintypes.com_error`` with
# HRESULT 0x800401FD / 0x80010108 that ``ComExecutor`` originally
# trapped. observe.* and mutate.* catch the AttributeError and turn
# it into ``result['error'] = f'dispatch failed: {exc!r}'`` so the
# exception never reaches ``ComExecutor._worker``'s catch.
#
# This regex detects that wrapped form so ``@com_tool`` can flip
# ``is_sw_dead`` post-hoc. The ``SldWorks.`` prefix on the failing
# member discriminates from genuine late-binding misses (which carry
# ``<unknown>.<name>`` — see e.g. ``Extension.GetCustomInfoNames3``
# on parts that don't expose it).
_DEAD_DISPATCH_RE = re.compile(r"AttributeError\(['\"]SldWorks\.")


def _looks_like_dead_dispatch(payload: Any) -> bool:
    """True iff *payload* is an observe.*/mutate.* result whose ``error``
    field matches the dead-dispatch pattern from a killed SW process."""
    if not isinstance(payload, dict):
        return False
    err = payload.get("error")
    if not isinstance(err, str):
        return False
    return bool(_DEAD_DISPATCH_RE.search(err))


def run_on_executor(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run *fn* on the ComExecutor STA thread with the full ``@com_tool``
    safety guards, in IMPERATIVE form.

    This is the load-bearing dispatch that ``@com_tool`` wraps. It is
    exposed separately for the one class of tool that CANNOT use the
    decorator: an ``async def`` tool that must ``await`` a client
    round-trip (e.g. ``ctx.elicit``) on the asyncio event loop *between*
    two COM phases. ``@com_tool`` would submit the whole coroutine
    function to the STA worker, which has no event loop — so such a tool
    calls ``run_on_executor(...)`` for each COM phase individually and
    keeps the await on the loop in between.

    The COM-safety invariant is identical either way: every COM call
    goes through ``ComExecutor.run`` on the single STA thread. Only the
    wrapping shape differs (decorator vs. explicit call).

    Args:
        fn: The COM-touching callable (typically an ``observe.sw_*`` /
            ``mutate._sw_*_impl`` function). Bound args follow.

    Returns:
        Whatever *fn* returns, propagated through the executor future.
    """
    # Late import so decorators can run at module import time, before
    # ``create_server`` has wired the runtime reference.
    from . import runtime as _rt_module

    rt = _rt_module._current_runtime
    if rt is None:
        raise RuntimeError(
            "MCP ServerRuntime is not wired yet — "
            "call create_server(runtime) before invoking tools"
        )
    # Fail fast with a reconnect hint when the SW process died (W5.6).
    # The executor's run() would surface the next queued call as
    # ConnectionError, but tools should not have to wait for that; the
    # is_sw_dead flag is the authoritative signal.
    if rt.executor.is_sw_dead:
        raise RuntimeError(
            "SOLIDWORKS process is no longer reachable "
            "(ComExecutor.is_sw_dead=True). Call the sw_reconnect "
            "tool to re-acquire SldWorks.Application on a fresh "
            "STA thread, or restart the MCP server."
        )
    result = rt.executor.run(lambda: fn(*args, **kwargs))
    # Post-hoc death detection: observe.*/mutate.* swallow the
    # dead-dispatch AttributeError into result['error'], so the
    # exception never reaches ComExecutor's HRESULT trap. Inspect the
    # payload and flip the flag here so the next call short-circuits
    # cleanly instead of repeating the dispatch error. Wave 5 Phase 2.5.
    if _looks_like_dead_dispatch(result):
        logger.warning(
            "run_on_executor: dead-dispatch pattern in %s result; "
            "marking executor sw_dead",
            getattr(fn, "__name__", "<tool>"),
        )
        rt.executor.mark_sw_dead()
    return result


def com_tool(fn: Callable[..., T]) -> Callable[..., T]:
    """Wrap an MCP tool so its body runs on the ComExecutor thread.

    The wrapper closes over args/kwargs and submits a thunk to
    ``runtime.executor.run(...)`` via :func:`run_on_executor`. Result and
    exceptions propagate through the future, so the MCP client sees the
    same return value or error it would see from a single-threaded call.

    Args:
        fn: The tool implementation. Typically delegates to an
            ``ai_sw_bridge.observe.sw_*`` function or to
            ``ai_sw_bridge.spec.builder.build``.

    Returns:
        A wrapped callable with ``_is_com_tool = True`` so the
        contract test can verify wrapping.

    Notes:
        Synchronous tools only. An ``async def`` tool that awaits a
        client round-trip between COM phases must instead call
        :func:`run_on_executor` per phase — see
        ``_tool_batch_execute.py`` and the documented exemption in
        ``test_all_com_tools_have_decorator``.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return run_on_executor(fn, *args, **kwargs)

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
