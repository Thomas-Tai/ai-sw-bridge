"""Histogram metric primitive for ai-sw-bridge telemetry.

Records floating-point observations into configurable buckets. Each
observation is a row in the telemetry store. Per spec.md §8.8:
Histogram.observe < 200 µs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import TelemetryStore

_DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    25.0,
    50.0,
)


class Histogram:
    """A named histogram with string labels.

    Usage::

        h = Histogram("build_duration_seconds", labels=("mode",))
        h.observe(1.23, mode="no_dim")
    """

    __slots__ = ("_name", "_label_keys", "_buckets", "_store")

    def __init__(
        self,
        name: str,
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
        store: TelemetryStore | None = None,
    ) -> None:
        self._name = name
        self._label_keys = labels
        self._buckets = buckets
        self._store = store

    @property
    def name(self) -> str:
        return self._name

    def bind(self, store: TelemetryStore) -> Histogram:
        """Return a copy of this histogram bound to a store."""
        return Histogram(self._name, self._label_keys, self._buckets, store)

    def observe(self, value: float, **label_values: str) -> None:
        """Record an observation.

        Raises TypeError if label_keys don't match label_values.
        """
        if set(label_values.keys()) != set(self._label_keys):
            raise TypeError(
                f"Histogram({self._name}): expected labels {self._label_keys}, "
                f"got {tuple(label_values.keys())}"
            )
        if self._store is None:
            return
        t0 = time.perf_counter()
        self._store.record(self._name, value, label_values)
        elapsed_us = (time.perf_counter() - t0) * 1e6
        if elapsed_us > 200:
            import sys

            print(
                f"telemetry: Histogram.observe took {elapsed_us:.0f} µs "
                f"(budget: 200 µs) for {self._name}",
                file=sys.stderr,
            )


HISTOGRAMS: dict[str, Histogram] = {
    "build_duration_seconds": Histogram("build_duration_seconds", labels=("mode",)),
    "brep_interrogation_seconds": Histogram(
        "brep_interrogation_seconds",
        labels=("feature_type", "mode"),
    ),
    "rag_query_seconds": Histogram("rag_query_seconds", labels=("subcommand",)),
}
