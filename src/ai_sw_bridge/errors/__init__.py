"""Error-handling utilities for ai-sw-bridge."""

from .auto_retry import IdenticalSpecError, RetryGuard, spec_hash
from .build_error import BuildError, Tier, build_error_from_exception
from .circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from .hints import HINT_CATALOG, Hint, default_hint, resolve_hint

__all__ = [
    "BuildError",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "HINT_CATALOG",
    "Hint",
    "IdenticalSpecError",
    "RetryGuard",
    "Tier",
    "build_error_from_exception",
    "default_hint",
    "resolve_hint",
    "spec_hash",
]
