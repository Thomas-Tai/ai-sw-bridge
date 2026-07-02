"""Shared COM/transport kernel for the feature handlers (Phase 3 Move 0).

Acyclic leaf: imports only stdlib, COM, and the _build_context leaf — NEVER
builder.py or any sibling handler module (import-linter forbidden contract
pins this). Holds only genuinely cross-family primitives.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext


def _select_sketch(ctx: BuildContext, sketch_name: str) -> None:
    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID(sketch_name, "SKETCH", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select sketch '{sketch_name}'")


def _mm_to_m(value: Any) -> float:
    """Convert a LENGTH_SCHEMA field (mm literal or `{rhs}` dict) to metres.

    For `{rhs}` bindings the live handler substitutes the resolved numeric
    value; here we just return a placeholder so the arg tuple has the right
    shape for the seat pass to verify.
    """
    if isinstance(value, dict):
        return 0.0  # placeholder; live path resolves via EquationMgr
    return float(value) / 1000.0


def _r8_safearray(values: list[float]) -> Any:
    """Wrap a flat list of doubles as a ``VT_ARRAY|VT_R8`` VARIANT SAFEARRAY.

    The point buffer shape ``ISketchManager.CreateSpline2`` requires. The
    pywin32 import is function-local so this module stays importable (and
    unit-testable) without SOLIDWORKS / pywin32 present — tests monkeypatch
    this seam. Seat-proven 2026-05-31 (spline materialised first try).
    """
    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(values))
