"""HRESULT-to-tier classification helper for telemetry wiring.

Maps known COM error HRESULTs to the Tier A/B/C error model per spec.md §3.2:
  Tier A: validation errors (bad spec, caught before COM calls)
  Tier B: COM/marshaling errors (SW-side failures)
  Tier C: bridge bugs (unhandled, should never reach the user)

This module provides the classification logic; actual wiring into the error
envelope waits for Task 1.2 (errors/ package creation).
"""

from __future__ import annotations

# Known HRESULTs from spec.md §6.9 and audit §4.2.
_TIER_B_HRESULTS: frozenset[str] = frozenset({
    "0x800706BA",  # RPC_S_SERVER_UNAVAILABLE
    "0x80010108",  # RPC_E_DISCONNECTED
    "0x80020003",  # DISP_E_MEMBERNOTFOUND
    "0x8002000B",  # DISP_E_BADINDEX
})

_TIER_C_HRESULTS: frozenset[str] = frozenset({
    "0x800401F0",  # CO_E_NOTINITIALIZED (STA discipline violation)
})


def classify_hresult(hresult: int | str) -> str:
    """Classify a COM HRESULT into the Tier A/B/C model.

    Returns one of: "A", "B", "C", or "unknown".
    """
    key = hex(hresult) if isinstance(hresult, int) else hresult.lower()
    if key in _TIER_B_HRESULTS:
        return "B"
    if key in _TIER_C_HRESULTS:
        return "C"
    # Tier A errors are validation-level (no HRESULT); any HRESULT we
    # don't recognize is classified as unknown rather than guessed.
    return "unknown"
