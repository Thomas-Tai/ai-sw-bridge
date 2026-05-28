"""Tests for ai_sw_bridge.com.executor (W5.1).

The executor wraps pythoncom + a worker thread. Tests run cross-platform
(no pywin32 in CI) by patching ``pythoncom`` in the executor module's
namespace with a stub that records ``CoInitialize`` / ``CoUninitialize``
calls. The threading semantics — Future propagation, queue draining,
cross-thread submit — are real; only the COM apartment calls are stubbed.

The load-bearing test is :func:`test_submit_from_different_thread_works` —
that is the specific cross-thread scenario the executor exists to make
safe (see ``docs/com_failure_modes.md`` row M-XX).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import CancelledError, TimeoutError as FutureTimeoutError
from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.com import executor as executor_module
from ai_sw_bridge.com.executor import ComExecutor


@pytest.fixture
def fake_pythoncom(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``pythoncom`` in the executor module with a recording stub.

    Pins ``_PYWIN32_AVAILABLE`` to True so ``start()`` proceeds past the
    install-check. Returns the stub so tests can assert call counts.
    """
    stub = MagicMock()
    monkeypatch.setattr(executor_module, "pythoncom", stub, raising=False)
    monkeypatch.setattr(executor_module, "_PYWIN32_AVAILABLE", True)
    return stub


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_construct_does_not_start_thread(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        assert not ex.is_alive
        assert fake_pythoncom.CoInitialize.call_count == 0

    def test_start_initializes_com_and_marks_alive(
        self, fake_pythoncom: MagicMock
    ) -> None:
        ex = ComExecutor()
        try:
            ex.start()
            assert ex.is_alive
            assert fake_pythoncom.CoInitialize.call_count == 1
        finally:
            ex.stop()

    def test_start_is_idempotent(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        try:
            ex.start()
            ex.start()  # no-op
            assert fake_pythoncom.CoInitialize.call_count == 1
        finally:
            ex.stop()

    def test_stop_calls_couninitialize(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        ex.start()
        ex.stop()
        # join is short; CoUninitialize runs in the worker's finally block.
        # Poll briefly to let the worker run cleanup.
        for _ in range(50):
            if fake_pythoncom.CoUninitialize.call_count >= 1:
                break
            time.sleep(0.01)
        assert fake_pythoncom.CoUninitialize.call_count == 1
        assert not ex.is_alive

    def test_stop_is_idempotent(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        ex.start()
        ex.stop()
        ex.stop()  # no-op
        assert not ex.is_alive

    def test_context_manager_starts_and_stops(self, fake_pythoncom: MagicMock) -> None:
        with ComExecutor() as ex:
            assert ex.is_alive
            assert fake_pythoncom.CoInitialize.call_count == 1
        assert not ex.is_alive

    def test_start_raises_when_pywin32_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(executor_module, "_PYWIN32_AVAILABLE", False)
        ex = ComExecutor()
        with pytest.raises(RuntimeError, match="pywin32 is required"):
            ex.start()


# ---------------------------------------------------------------------------
# submit / run / Future propagation
# ---------------------------------------------------------------------------


class TestSubmitAndRun:
    def test_submit_returns_future_with_result(self, fake_pythoncom: MagicMock) -> None:
        with ComExecutor() as ex:
            fut = ex.submit(lambda: 42)
            assert fut.result(timeout=2) == 42

    def test_run_returns_callable_value(self, fake_pythoncom: MagicMock) -> None:
        with ComExecutor() as ex:
            assert ex.run(lambda: "hello") == "hello"

    def test_run_propagates_exceptions(self, fake_pythoncom: MagicMock) -> None:
        class _MyError(Exception):
            pass

        with ComExecutor() as ex:
            with pytest.raises(_MyError, match="boom"):
                ex.run(lambda: (_ for _ in ()).throw(_MyError("boom")))

    def test_run_timeout_raises(self, fake_pythoncom: MagicMock) -> None:
        with ComExecutor() as ex:
            slow = threading.Event()
            with pytest.raises(FutureTimeoutError):
                ex.run(lambda: slow.wait(timeout=10), timeout=0.05)
            slow.set()  # let the worker finish so stop() doesn't hang

    def test_submit_before_start_raises(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        with pytest.raises(RuntimeError, match="not running"):
            ex.submit(lambda: 1)

    def test_submit_after_stop_raises(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        ex.start()
        ex.stop()
        with pytest.raises(RuntimeError, match="not running"):
            ex.submit(lambda: 1)


# ---------------------------------------------------------------------------
# Cross-thread invocation (the load-bearing property)
# ---------------------------------------------------------------------------


class TestCrossThread:
    def test_submit_from_different_thread_works(
        self, fake_pythoncom: MagicMock
    ) -> None:
        """The exact scenario the executor exists to make safe.

        FastMCP-style: tool handler runs on worker thread T2 distinct
        from the main thread T1 where the executor was constructed.
        Submitting from T2 must still execute on the executor's own
        worker thread (T3, which is the COM apartment thread).
        """
        with ComExecutor() as ex:
            apartment_thread_id = ex.run(lambda: threading.get_ident())

            results = []

            def worker():
                # We're on T2 here. Submit a job.
                tid = ex.run(lambda: threading.get_ident())
                results.append(tid)

            t = threading.Thread(target=worker)
            t.start()
            t.join()

            assert len(results) == 1
            # The COM apartment thread is the same regardless of which
            # caller thread submitted the work.
            assert results[0] == apartment_thread_id

    def test_multiple_threads_share_one_apartment(
        self, fake_pythoncom: MagicMock
    ) -> None:
        with ComExecutor() as ex:
            apartment_ids = set()
            lock = threading.Lock()

            def submit_from_caller():
                tid = ex.run(lambda: threading.get_ident())
                with lock:
                    apartment_ids.add(tid)

            threads = [threading.Thread(target=submit_from_caller) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All 5 caller threads' work ran on the same apartment thread.
            assert len(apartment_ids) == 1


# ---------------------------------------------------------------------------
# CoInitialize failure surfaces as is_dead, not silent hang
# ---------------------------------------------------------------------------


class TestCoInitializeFailure:
    def test_coinitialize_failure_marks_dead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = MagicMock()
        stub.CoInitialize.side_effect = RuntimeError("simulated CoInit failure")
        monkeypatch.setattr(executor_module, "pythoncom", stub, raising=False)
        monkeypatch.setattr(executor_module, "_PYWIN32_AVAILABLE", True)

        ex = ComExecutor()
        ex.start()
        # Worker should have terminated quickly with the error.
        for _ in range(50):
            if not ex.is_alive:
                break
            time.sleep(0.01)
        assert not ex.is_alive
        assert ex.is_dead

    def test_is_dead_false_before_start(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        assert ex.is_dead is False

    def test_is_dead_false_after_clean_stop(self, fake_pythoncom: MagicMock) -> None:
        ex = ComExecutor()
        ex.start()
        ex.stop()
        # Clean stop is not "dead." is_dead is reserved for CoInit failure.
        assert ex.is_dead is False


# ---------------------------------------------------------------------------
# Shutdown semantics
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_pending_items_cancelled_on_stop(self, fake_pythoncom: MagicMock) -> None:
        """Items queued behind a slow job get CancelledError on stop()."""
        with ComExecutor() as ex:
            block = threading.Event()
            release = threading.Event()

            # First item: holds the worker.
            blocker_fut = ex.submit(lambda: (block.set(), release.wait(timeout=10)))
            block.wait(timeout=2)

            # Second item: queued behind the blocker.
            queued_fut = ex.submit(lambda: 42)

            # Stop: pushes _SHUTDOWN which lands AFTER queued_fut. So:
            # - worker reads queued_fut from queue, runs it (returns 42)
            # - worker reads _SHUTDOWN, exits loop
            # - the drain step finds nothing to cancel.
            # To exercise the drain path we'd need to inject items
            # AFTER _SHUTDOWN. That isn't a real scenario; cover the
            # drain via the close-path direct test below.
            release.set()
            blocker_fut.result(timeout=2)
            assert queued_fut.result(timeout=2) == 42

    def test_drain_cancels_post_shutdown_items(self, fake_pythoncom: MagicMock) -> None:
        """Direct test of the drain path: queue items, push _SHUTDOWN,
        then push more items. The drain step in the worker's finally
        block cancels them."""
        ex = ComExecutor()
        ex.start()

        block = threading.Event()
        release = threading.Event()

        ex.submit(lambda: (block.set(), release.wait(timeout=10)))
        block.wait(timeout=2)

        # Push SHUTDOWN sentinel directly into the queue, then push more
        # items behind it. The worker will read SHUTDOWN and drain the rest.
        ex._queue.put(executor_module._SHUTDOWN)  # type: ignore[attr-defined]
        late_futs = [ex.submit(lambda: 1) for _ in range(3)]

        release.set()

        # Wait for the worker to drain.
        for _ in range(100):
            if not ex.is_alive:
                break
            time.sleep(0.01)

        for fut in late_futs:
            with pytest.raises(CancelledError):
                fut.result(timeout=1)


# ---------------------------------------------------------------------------
# Concurrency stress
# ---------------------------------------------------------------------------


class TestStress:
    def test_high_volume_submission_ordering(self, fake_pythoncom: MagicMock) -> None:
        """100 sequential submissions complete in FIFO order."""
        with ComExecutor() as ex:
            order: list[int] = []
            futures = [ex.submit(lambda i=i: order.append(i)) for i in range(100)]
            for fut in futures:
                fut.result(timeout=5)
            assert order == list(range(100))
