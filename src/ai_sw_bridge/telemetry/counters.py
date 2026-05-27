"""Counter metric primitive for ai-sw-bridge telemetry.

Counters are monotonically increasing integers. Each increment is recorded
as a row in the telemetry store. Per spec.md §8.8: Counter.inc < 100 µs.

Mandatory counters for v0.11 (audit §1.2, spec §8.8):
  1. builds_total{mode, outcome}
  2. com_errors_total{iface_method, hresult}
  3. hint_emissions_total{hint_key, iface_method}
  4. auto_retry_outcomes_total{attempt, outcome}
  5. checkpoint_writes_total{outcome}
  6. feature_flag_state{flag, state}
  7. com_disconnects_total{hresult}
  8. rag_query_seconds is a histogram, not a counter — see histograms.py
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import TelemetryStore


class Counter:
    """A named counter with string labels.

    Usage::

        c = Counter("builds_total", labels=("mode", "outcome"))
        c.inc(mode="no_dim", outcome="ok")
    """

    __slots__ = ("_name", "_label_keys", "_store")

    def __init__(
        self,
        name: str,
        labels: tuple[str, ...] = (),
        store: TelemetryStore | None = None,
    ) -> None:
        self._name = name
        self._label_keys = labels
        self._store = store

    @property
    def name(self) -> str:
        return self._name

    def bind(self, store: TelemetryStore) -> Counter:
        """Return a copy of this counter bound to a store."""
        return Counter(self._name, self._label_keys, store)

    def inc(self, value: int = 1, **label_values: str) -> None:
        """Increment the counter by ``value`` (default 1).

        Raises TypeError if label_keys don't match label_values.
        """
        if set(label_values.keys()) != set(self._label_keys):
            raise TypeError(
                f"Counter({self._name}): expected labels {self._label_keys}, "
                f"got {tuple(label_values.keys())}"
            )
        if self._store is None:
            return
        t0 = time.perf_counter()
        self._store.record(self._name, float(value), label_values)
        elapsed_us = (time.perf_counter() - t0) * 1e6
        if elapsed_us > 100:
            import sys

            print(
                f"telemetry: Counter.inc took {elapsed_us:.0f} µs "
                f"(budget: 100 µs) for {self._name}",
                file=sys.stderr,
            )


# Registry: all 8 mandatory counters. Missing any counter fails the spec
# contract per audit §1.2.
COUNTERS: dict[str, Counter] = {
    "builds_total": Counter("builds_total", labels=("mode", "outcome")),
    "com_errors_total": Counter("com_errors_total", labels=("iface_method", "hresult")),
    "hint_emissions_total": Counter(
        "hint_emissions_total", labels=("hint_key", "iface_method")
    ),
    "auto_retry_outcomes_total": Counter(
        "auto_retry_outcomes_total", labels=("attempt", "outcome")
    ),
    "checkpoint_writes_total": Counter("checkpoint_writes_total", labels=("outcome",)),
    "feature_flag_state": Counter("feature_flag_state", labels=("flag", "state")),
    "com_disconnects_total": Counter("com_disconnects_total", labels=("hresult",)),
    # rag_query_seconds is a histogram — see histograms.py
}
