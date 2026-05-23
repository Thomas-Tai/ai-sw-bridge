"""Circuit breaker for SOLIDWORKS COM operations.

Implements the circuit breaker pattern to prevent cascading failures when
COM calls fail repeatedly.  The state machine has three states:

  CLOSED  → normal operation; failures increment a counter
  OPEN    → all calls rejected; waits for recovery_timeout before probing
  HALF_OPEN → allows a limited number of probe calls; success closes the
              circuit, failure re-opens it

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: a10fb74933bb681a5d1569621b33bdcb213faae0
SPDX-License-Identifier: MIT

The original is an async adapter wrapper (``CircuitBreakerAdapter``).  This
port extracts the standalone ``CircuitBreaker`` class and makes it
synchronous — ai-sw-bridge drives COM via pywin32 late binding, which is
inherently synchronous from the caller's thread.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Synchronous circuit breaker for COM call protection.

    Args:
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds to wait in OPEN before transitioning to
            HALF_OPEN.
        half_open_max_calls: Probe calls allowed in HALF_OPEN before
            re-opening on failure.
        expected_exception: Exception type that counts as a failure.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0

    def _should_allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        # HALF_OPEN
        return self.half_open_calls < self.half_open_max_calls

    def _record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def _record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker opened after %d failures", self.failure_count
            )

    def call(self, operation: Callable[[], Any]) -> Any:
        """Execute *operation* through the circuit breaker.

        Returns the operation's result on success.  Raises
        :class:`CircuitOpenError` when the circuit is OPEN and the
        recovery timeout has not elapsed, or re-raises the original
        exception on failure.

        In HALF_OPEN state, each call increments the probe counter.
        A successful probe closes the circuit; a failed probe re-opens it.
        """
        if not self._should_allow_request():
            raise CircuitOpenError(
                f"Circuit breaker is {self.state.value} "
                f"(failures={self.failure_count}, "
                f"last_failure={self.last_failure_time:.1f})"
            )

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1

        try:
            result = operation()
            self._record_success()
            return result
        except self.expected_exception:
            self._record_failure()
            raise


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is OPEN and blocks a call."""
