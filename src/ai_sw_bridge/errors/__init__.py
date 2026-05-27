"""Error-handling utilities for ai-sw-bridge."""

from .auto_retry import IdenticalSpecError, RetryGuard, spec_hash
from .circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .hints import HINT_CATALOG, Hint, default_hint, resolve_hint

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "HINT_CATALOG",
    "Hint",
    "IdenticalSpecError",
    "RetryGuard",
    "default_hint",
    "resolve_hint",
    "spec_hash",
]
