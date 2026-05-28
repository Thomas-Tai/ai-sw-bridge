"""Single-threaded STA executor for SOLIDWORKS COM calls.

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

The original lives at ``src/solidworks_mcp/adapters/com_executor.py`` in
the upstream. This port:

- Replaces the upstream's ``loguru`` dependency with the stdlib
  ``logging`` module (the bridge ships zero third-party logging deps).
- Tightens the worker shutdown semantics to drain pending work items
  with ``CancelledError`` rather than dropping them silently.
- Adds ``is_dead`` introspection so callers can detect a worker that
  CoInitialize-failed and degrade to a clear error.
- Keeps the upstream's public API (``start``, ``stop``, ``submit``,
  ``run``, context-manager protocol) byte-for-byte compatible.

Background: SOLIDWORKS COM is STA (single-threaded apartment). An
``IDispatch`` proxy obtained on thread A cannot be invoked from thread
B — pywin32 late binding surfaces this as ``AttributeError:
SldWorks.Application.<method>`` at attribute lookup, NOT as
``pywintypes.com_error``. Boundaries that catch only the latter miss
the cross-thread case (see ``docs/com_failure_modes.md`` row M-XX).

Lane M (MCP) tool handlers run on async worker threads distinct from
the thread where the SW process was Dispatch'd. Every COM-touching
call must be routed through this executor so exactly one thread ever
holds the apartment. Because exactly one thread ever touches COM:

1. ``pythoncom.CoInitialize()`` is called once at thread startup.
2. ``self.swApp`` / ``self.currentModel`` can be shared instance
   attributes without marshaling — no thread-local trickery.
3. STA constraints are satisfied (SW is happy).
4. Per-interface method flagging via ``sw_type_info`` accumulates on
   the same object lifetime.

Usage::

    executor = ComExecutor()
    executor.start()
    try:
        title = executor.run(lambda: sw.ActiveDoc.GetTitle())
    finally:
        executor.stop()

or with the context manager::

    with ComExecutor() as ex:
        title = ex.run(lambda: sw.ActiveDoc.GetTitle())
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import CancelledError, Future
from typing import Any, Callable, TypeVar

try:
    import pythoncom

    _PYWIN32_AVAILABLE = True
except ImportError:
    _PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)


T = TypeVar("T")


_SHUTDOWN = object()

# HRESULTs indicating the SW process died (stale IDispatch handle).
# 0x800401FD = CO_E_OBJNOTCONNECTED, 0x80010108 = RPC_E_DISCONNECTED.
# See docs/com_failure_modes.md row M-01.
_DEAD_HRESULTS: frozenset[int] = frozenset({0x800401FD, 0x80010108})


class ComExecutor:
    """Single-threaded STA executor for SOLIDWORKS COM calls.

    Thread-safe: :meth:`submit` and :meth:`run` may be called from any
    thread. Exactly one underlying worker thread services the work
    queue; that thread owns the COM apartment.

    Lifecycle:

    - Construct: creates the executor, no thread yet.
    - :meth:`start` — launches the worker and waits for
      ``pythoncom.CoInitialize`` to succeed.
    - :meth:`submit` — schedules a callable on the worker; returns a
      ``Future``.
    - :meth:`run` — convenience wrapper for submit + wait.
    - :meth:`stop` — signals the worker to exit, drains any pending
      items with ``CancelledError``, joins the thread, then
      ``CoUninitialize``\\ s.
    """

    def __init__(self, name: str = "SolidWorks-COM") -> None:
        """Create the executor (thread not yet running).

        Args:
            name: Thread name for debugging / logs.
        """
        self._name = name
        self._queue: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._co_init_ok = False
        self._sw_app_is_dead = False

    # ---- Public API ------------------------------------------------------

    def start(self, timeout: float = 10.0) -> None:
        """Launch the worker thread and wait until CoInitialize succeeds.

        Idempotent: calling ``start()`` on a running executor is a
        no-op (returns immediately).

        Args:
            timeout: Seconds to wait for the worker to become ready.

        Raises:
            RuntimeError: pywin32 not installed, or the worker did not
                signal ready within ``timeout``.
        """
        if self._thread is not None and self._thread.is_alive():
            return

        if not _PYWIN32_AVAILABLE:
            raise RuntimeError("pywin32 is required for ComExecutor; not available")

        self._ready.clear()
        self._stopped.clear()
        self._co_init_ok = False
        self._thread = threading.Thread(
            target=self._worker, name=self._name, daemon=True
        )
        self._thread.start()

        if not self._ready.wait(timeout):
            raise RuntimeError(
                f"ComExecutor worker {self._name!r} did not initialize "
                f"within {timeout}s"
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to exit and wait for it to join.

        After ``stop()`` returns, :meth:`submit` raises ``RuntimeError``
        on subsequent calls. Pending items in the queue at shutdown
        time are completed with ``CancelledError`` so callers blocked
        on their futures unblock with a clear signal.

        Idempotent.

        Args:
            timeout: Seconds to wait for the worker to exit cleanly.
        """
        if self._thread is None or not self._thread.is_alive():
            return

        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout)
        if self._thread.is_alive():
            logger.warning(
                "ComExecutor worker %r did not exit within %ss; abandoning",
                self._name,
                timeout,
            )
        self._thread = None
        self._stopped.set()

    def submit(self, fn: Callable[[], T]) -> Future[T]:
        """Schedule ``fn`` on the worker; return a future for its result.

        The callable receives no arguments — close over any state
        needed via the enclosing scope. Both return values and
        exceptions propagate through the future.

        Args:
            fn: Zero-argument callable to run on the COM thread.

        Returns:
            ``Future`` resolving to the callable's return value, or
            raising whatever exception the callable raised.

        Raises:
            RuntimeError: Executor isn't running. Call :meth:`start`
                first (or use the context-manager form).
        """
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError(
                f"ComExecutor {self._name!r} is not running; " "call start() first"
            )

        fut: Future[T] = Future()
        self._queue.put((fn, fut))
        return fut

    def run(self, fn: Callable[[], T], timeout: float | None = None) -> T:
        """Run ``fn`` on the worker and block until the result is ready.

        Convenience wrapper around :meth:`submit` + ``Future.result``.

        Args:
            fn: Zero-argument callable to run on the COM thread.
            timeout: Seconds to wait before raising ``TimeoutError``.
                ``None`` waits indefinitely.

        Returns:
            Whatever ``fn`` returned.

        Raises:
            Any exception raised by ``fn``, re-raised in the caller's
            thread.
            TimeoutError: ``timeout`` elapsed before ``fn`` finished.
        """
        return self.submit(fn).result(timeout=timeout)

    # ---- Introspection ---------------------------------------------------

    @property
    def is_alive(self) -> bool:
        """``True`` when the worker thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_dead(self) -> bool:
        """``True`` when the worker exited because CoInitialize failed.

        Distinct from "not started" and from "stopped cleanly." A dead
        executor cannot be reused — construct a fresh one. Callers
        check this when ``start()`` returns to surface a clear error
        message rather than failing on the next ``submit``.
        """
        if self._thread is not None and self._thread.is_alive():
            return False
        if not self._ready.is_set():
            return False
        return not self._co_init_ok

    @property
    def is_sw_dead(self) -> bool:
        """``True`` when the SW process died during operation (W5.6).

        Distinct from :attr:`is_dead` (CoInitialize failure at startup).
        This flag flips when a worker call raises ``pywintypes.com_error``
        with an HRESULT in ``_DEAD_HRESULTS`` (``0x800401FD`` or
        ``0x80010108``), indicating the SW process is no longer reachable.

        When dead, the worker has exited and all pending futures were
        completed with ``ConnectionError``. Call :meth:`reconnect` to
        restart the worker on a fresh STA thread.

        See ``docs/com_failure_modes.md`` row M-01.
        """
        return self._sw_app_is_dead

    # ---- Context manager -------------------------------------------------

    def __enter__(self) -> "ComExecutor":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

    # ---- Death recovery (W5.6) -------------------------------------------

    def reconnect(self, timeout: float = 10.0) -> None:
        """Reset state and start a fresh worker after SW process death.

        Waits for the old worker (if still draining) to exit, clears
        the ``_sw_app_is_dead`` flag, replaces the queue, and calls
        :meth:`start` to launch a new STA worker thread.

        After ``reconnect()`` returns, the executor is usable again —
        ``submit()`` and ``run()`` work as normal.

        .. warning::

           Re-acquiring the IDispatch chain mid-build means the new SW
           process has no knowledge of partially-built state. The caller
           must verify the model after reconnect.

        Args:
            timeout: Seconds to wait for the new worker to become ready.

        Raises:
            RuntimeError: If the new worker fails to initialize.
        """
        if self._thread is not None and self._thread.is_alive():
            self.stop()

        self._sw_app_is_dead = False
        self._queue = queue.Queue()
        self.start(timeout)

    # ---- Worker ----------------------------------------------------------

    def _worker(self) -> None:
        """Run on the dedicated thread: CoInitialize, drain queue, cleanup.

        Loop exits when ``_SHUTDOWN`` appears in the queue. Each work
        item is a ``(callable, Future)`` tuple; the callable runs and
        the Future is set with the result or exception. On shutdown,
        any items still queued are cancelled so blocked callers unblock.
        """
        try:
            pythoncom.CoInitialize()
        except Exception as exc:
            logger.error(
                "CoInitialize failed in ComExecutor worker %r: %r",
                self._name,
                exc,
            )
            # Signal ready so start() doesn't hang. The is_dead property
            # surfaces this; submit() would also fail because COM isn't
            # really initialized.
            self._ready.set()
            return

        self._co_init_ok = True
        self._ready.set()
        logger.info("ComExecutor %r ready", self._name)

        try:
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    break

                fn, fut = item
                if not fut.set_running_or_notify_cancel():
                    continue

                try:
                    result = fn()
                except BaseException as exc:  # noqa: BLE001 — propagate everything
                    # W5.6: detect SW process death via stale-handle HRESULTs.
                    # The worker exits after draining pending callers with
                    # ConnectionError so no future deadlocks.
                    hresult = getattr(exc, "hresult", None)
                    if hresult in _DEAD_HRESULTS:
                        self._sw_app_is_dead = True
                        fut.set_exception(exc)
                        logger.error(
                            "ComExecutor %r: SW process died (HRESULT=0x%08X); "
                            "draining pending callers",
                            self._name,
                            hresult,
                        )
                        self._drain_pending(
                            reason="SW process died (HRESULT=0x{:08X})".format(hresult)
                        )
                        return
                    fut.set_exception(exc)
                else:
                    fut.set_result(result)
        finally:
            # Drain any remaining items so blocked callers unblock with a
            # clear signal rather than hanging forever.
            if not self._sw_app_is_dead:
                self._drain_pending(reason="executor shutting down")
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            logger.info("ComExecutor %r stopped", self._name)

    def _drain_pending(self, *, reason: str) -> None:
        """Cancel every queued work item with ``CancelledError``."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is _SHUTDOWN:
                continue
            _, fut = item
            if fut.set_running_or_notify_cancel():
                fut.set_exception(CancelledError(reason))
