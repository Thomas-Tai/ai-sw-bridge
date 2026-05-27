"""Fault-injection pytest fixtures for COM failure modes.

Provides FaultInjector that wraps a mock COM dispatch layer and injects
synthetic pywintypes.com_error at configurable points. Per audit §4.2:
"§8.3 testing strategy is good but no chaos engineering / fault injection."
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any


# Synthetic pywintypes.com_error — avoids requiring pywin32 in CI.
# The real com_error has signature: (hresult, string, (source, desc, help))
@dataclass
class ComError:
    """Stand-in for pywintypes.com_error for fault injection without pywin32."""

    hresult: int
    strerror: str
    details: tuple[str, str, str] = ("", "", "")

    def __str__(self) -> str:
        return f"com_error({self.hresult:#010x}, {self.strerror!r})"


# HRESULT catalog per task spec and spec.md §8.3.
class HRESULT:
    """Known COM error HRESULTs for fault injection."""

    RPC_S_SERVER_UNAVAILABLE = 0x800706BA
    RPC_E_DISCONNECTED = 0x80010108
    DISP_E_MEMBERNOTFOUND = 0x80020003
    CO_E_NOTINITIALIZED = 0x800401F0
    DISP_E_BADINDEX = 0x8002000B


# Tier classification per spec.md §3.2 / telemetry/classify.py.
EXPECTED_TIERS: dict[int, str] = {
    HRESULT.RPC_S_SERVER_UNAVAILABLE: "B",
    HRESULT.RPC_E_DISCONNECTED: "B",
    HRESULT.DISP_E_MEMBERNOTFOUND: "B",
    HRESULT.DISP_E_BADINDEX: "B",
    HRESULT.CO_E_NOTINITIALIZED: "C",
}

# Human-readable descriptions for each HRESULT.
HRESULT_DESCRIPTIONS: dict[int, str] = {
    HRESULT.RPC_S_SERVER_UNAVAILABLE: "RPC_S_SERVER_UNAVAILABLE — SW process died",
    HRESULT.RPC_E_DISCONNECTED: "RPC_E_DISCONNECTED — COM proxy disconnected",
    HRESULT.DISP_E_MEMBERNOTFOUND: "DISP_E_MEMBERNOTFOUND — late-binding name typo",
    HRESULT.CO_E_NOTINITIALIZED: "CO_E_NOTINITIALIZED — STA discipline violation",
    HRESULT.DISP_E_BADINDEX: "DISP_E_BADINDEX — bad index in dispatch call",
}


@dataclass
class FaultInjector:
    """Configurable COM failure injector.

    Maps (iface_method, attempt_number) to a synthetic ComError. When the
    fault injector is active, calling a method that matches an injection
    point raises the configured error instead of executing normally.

    Usage::

        injector = FaultInjector()
        injector.add_fault("FeatureExtrusion2", attempt=1,
                           error=ComError(0x800706BA, "unavailable"))
        with injector.active():
            # first call to FeatureExtrusion2 raises ComError
            ...
    """

    faults: dict[tuple[str, int], ComError] = field(default_factory=dict)
    _active: bool = field(default=False, repr=False)
    _call_counts: dict[str, int] = field(default_factory=dict, repr=False)

    def add_fault(
        self,
        iface_method: str,
        attempt: int,
        error: ComError | None = None,
        hresult: int | None = None,
    ) -> None:
        """Register a fault at (method, attempt_number).

        Provide either `error` (a ComError) or `hresult` (int).
        """
        if error is None and hresult is not None:
            desc = HRESULT_DESCRIPTIONS.get(hresult, "injected fault")
            error = ComError(hresult, desc)
        if error is None:
            raise ValueError("must provide error or hresult")
        self.faults[(iface_method, attempt)] = error

    def check(self, method: str) -> ComError | None:
        """Check if a fault should fire for the given method.

        Returns the ComError to raise, or None to proceed normally.
        Increments the call counter for the method.
        """
        if not self._active:
            return None
        count = self._call_counts.get(method, 0) + 1
        self._call_counts[method] = count
        return self.faults.get((method, count))

    def reset(self) -> None:
        """Clear call counters (preserves registered faults)."""
        self._call_counts.clear()

    @property
    def active(self) -> bool:
        return self._active

    class _ActiveContext:
        def __init__(self, injector: FaultInjector) -> None:
            self._injector = injector

        def __enter__(self) -> FaultInjector:
            self._injector._active = True
            return self._injector

        def __exit__(self, *args: Any) -> None:
            self._injector._active = False

    def active(self) -> _ActiveContext:
        """Context manager that enables fault injection."""
        return self._ActiveContext(self)


@pytest.fixture
def fault_injector() -> FaultInjector:
    """Provide a fresh FaultInjector for each test."""
    return FaultInjector()
