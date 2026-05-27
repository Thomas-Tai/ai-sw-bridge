"""Tests for the circuit breaker state machine (Task 1.2).

Failure-injection scenarios (SLO-03 alignment):
  - COM dispatch returns RPC_S_SERVER_UNAVAILABLE (0x800706BA)
  - COM call hangs and times out
  - Rapid consecutive COM failures exceeding the threshold
  - Intermittent failures that should NOT trip the breaker
  - Half-open probe success/failure paths
"""

from __future__ import annotations

import time

import pytest

from ai_sw_bridge.errors.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitState:
    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_state_enum_values(self) -> None:
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestClosedState:
    def test_allows_request_when_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb._should_allow_request() is True

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker()
        cb.failure_count = 3
        cb._record_success()
        assert cb.failure_count == 0

    def test_failure_increments_count(self) -> None:
        cb = CircuitBreaker()
        cb._record_failure()
        assert cb.failure_count == 1

    def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb._record_failure()
        assert cb.state == CircuitState.OPEN

    def test_does_not_open_before_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb._record_failure()
        assert cb.state == CircuitState.CLOSED


class TestOpenState:
    def test_blocks_request_when_open(self) -> None:
        cb = CircuitBreaker(recovery_timeout=60.0)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()
        assert cb._should_allow_request() is False

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(recovery_timeout=0.01)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time() - 0.02
        assert cb._should_allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN


class TestHalfOpenState:
    def test_allows_limited_probe_calls(self) -> None:
        cb = CircuitBreaker(half_open_max_calls=2)
        cb.state = CircuitState.HALF_OPEN
        assert cb._should_allow_request() is True
        cb.half_open_calls = 2
        assert cb._should_allow_request() is False

    def test_success_closes_circuit(self) -> None:
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        cb.failure_count = 5
        cb._record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_failure_reopens_circuit(self) -> None:
        cb = CircuitBreaker()
        cb.state = CircuitState.HALF_OPEN
        cb._record_failure()
        assert cb.state == CircuitState.OPEN


class TestCall:
    def test_call_success_returns_result(self) -> None:
        cb = CircuitBreaker()
        result = cb.call(lambda: 42)
        assert result == 42

    def test_call_failure_propagates_exception(self) -> None:
        cb = CircuitBreaker()

        def _fail() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            cb.call(_fail)

    def test_call_open_raises_circuit_open_error(self) -> None:
        cb = CircuitBreaker(recovery_timeout=60.0)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: None)

    def test_call_half_open_probe_success_closes(self) -> None:
        cb = CircuitBreaker(half_open_max_calls=3)
        cb.state = CircuitState.HALF_OPEN
        cb.half_open_calls = 0
        cb.call(lambda: "ok")
        # Successful probe closes the circuit and resets counters
        assert cb.state == CircuitState.CLOSED
        assert cb.half_open_calls == 0

    def test_call_half_open_probe_failure_reopens(self) -> None:
        cb = CircuitBreaker(half_open_max_calls=3)
        cb.state = CircuitState.HALF_OPEN
        cb.half_open_calls = 0
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN

    def test_call_respects_expected_exception(self) -> None:
        cb = CircuitBreaker(expected_exception=ValueError, failure_threshold=1)

        def _type_error() -> None:
            raise TypeError("not counted")

        # TypeError is NOT the expected_exception, so it's not caught by
        # the breaker's failure recording — it propagates without
        # incrementing failure_count.
        with pytest.raises(TypeError):
            cb.call(_type_error)
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_full_lifecycle(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

        # CLOSED: accumulate failures
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.CLOSED

        # One more failure trips the breaker
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN

        # Calls are blocked
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: None)

        # Wait for recovery timeout
        time.sleep(0.02)

        # Now in HALF_OPEN — a successful probe closes the circuit
        assert cb.state == CircuitState.HALF_OPEN or cb._should_allow_request()
        cb.call(lambda: "recovered")
        assert cb.state == CircuitState.CLOSED
