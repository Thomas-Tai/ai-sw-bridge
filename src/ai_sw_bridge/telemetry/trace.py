"""Per-build trace ID for cross-module correlation.

Every top-level CLI invocation generates a trace ID emitted on stderr and
embedded into every telemetry emission, error envelope, and checkpoint row.
Per spec.md §8.9: ``trace-<UTC-ISO-no-separators>-<8-hex-random>``.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone


_local = threading.local()


def new_trace_id() -> str:
    """Generate a new trace ID and bind it to the current thread.

    Format: ``trace-YYYYMMDDTHHMMSS-<8-hex>`` per spec.md §8.9.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = secrets.token_hex(4)
    tid = f"trace-{ts}-{suffix}"
    _local.trace_id = tid
    return tid


def trace_id() -> str | None:
    """Return the current thread's trace ID, or None if unset."""
    return getattr(_local, "trace_id", None)


def set_trace_id(tid: str) -> None:
    """Explicitly set the current thread's trace ID (e.g. from env var)."""
    _local.trace_id = tid


def clear_trace_id() -> None:
    """Clear the current thread's trace ID (called at process exit)."""
    _local.trace_id = None
