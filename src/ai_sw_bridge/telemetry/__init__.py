"""ai-sw-bridge telemetry — local-only metrics (spec.md §8.8, §8.9).

Public API::

    from ai_sw_bridge.telemetry import counter, histogram, trace_id

No PII, no automatic upload (per privacy_review.md).
"""

from __future__ import annotations

from .counters import Counter
from .histograms import Histogram
from .store import TelemetryStore
from .trace import clear_trace_id, new_trace_id, set_trace_id, trace_id

__all__ = [
    "Counter",
    "Histogram",
    "TelemetryStore",
    "clear_trace_id",
    "counter",
    "histogram",
    "new_trace_id",
    "set_trace_id",
    "trace_id",
]

# Module-level store singleton. Initialized on first use.
_store: TelemetryStore | None = None
# Cache of bound counter/histogram instances keyed by name.
_bound_counters: dict[str, Counter] = {}
_bound_histograms: dict[str, Histogram] = {}


def _get_store() -> TelemetryStore:
    global _store
    if _store is None:
        _store = TelemetryStore()
        _bound_counters.clear()
        _bound_histograms.clear()
    return _store


def counter(name: str, **label_values: str) -> None:
    """Emit a single counter increment using the module-level store.

    Resolves the counter definition from counters.py by name. If the name
    is not a registered counter, the emission is silently dropped (guards
    against typos causing runtime crashes in the build path).
    """
    from .counters import COUNTERS

    bound = _bound_counters.get(name)
    if bound is None:
        c = COUNTERS.get(name)
        if c is None:
            return
        bound = c.bind(_get_store())
        _bound_counters[name] = bound
    bound.inc(1, **label_values)


def histogram(name: str, value: float, **label_values: str) -> None:
    """Emit a single histogram observation using the module-level store."""
    from .histograms import HISTOGRAMS

    bound = _bound_histograms.get(name)
    if bound is None:
        h = HISTOGRAMS.get(name)
        if h is None:
            return
        bound = h.bind(_get_store())
        _bound_histograms[name] = bound
    bound.observe(value, **label_values)
