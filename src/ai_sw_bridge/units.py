"""Unit-system constants and the inch-to-mm conversion chokepoint.

The spec layer's internal length unit is **millimetres** (every handler and
placeholder in ``spec/builder.py`` assumes mm and converts to meters only at
the COM boundary). A spec that declaress ``"units": "inch"`` has its length
values normalized to mm *once*, at parse time, through the single entry
point in this module. Downstream code never branches on units.

The document-display preference set
(``SetUserPreferenceInteger(swUnitSystem...)``) is a separate concern — it
lives in the v2 orchestrator, is gated by a 🔴 SEAT, and is intentionally
**not** performed here.

This module is pure (no SW, no filesystem, no randomness) and fully
unit-testable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Supported unit systems
# ---------------------------------------------------------------------------


class SpecUnit(str, Enum):
    """Units a spec may declare. Extensible; add members as lanes open."""

    MM = "mm"
    INCH = "inch"


DEFAULT_UNIT = SpecUnit.MM


def parse_unit(value: Any) -> SpecUnit:
    """Coerce a raw spec value to :class:`SpecUnit`.

    Accepts a :class:`SpecUnit`, a bare string (case-insensitive), or
    ``None`` (returns :data:`DEFAULT_UNIT`). Anything else raises
    :class:`ValueError` so a validator can surface the defect.
    """
    if value is None:
        return DEFAULT_UNIT
    if isinstance(value, SpecUnit):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        for member in SpecUnit:
            if member.value == key:
                return member
    raise ValueError(f"unsupported unit: {value!r}")


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


# Exact by international-inch definition (1 in = 25.4 mm).
INCHES_PER_MM: float = 1.0 / 25.4
MM_PER_INCH: float = 25.4


def inch_to_mm(value: float) -> float:
    """Convert a length from inches to millimetres.

    Pure arithmetic, exact for ``0.0``, monotonic, odd-preserving. Accepts
    ``int`` and ``float`` via duck typing on ``*``. Raises ``TypeError`` on
    non-numeric input rather than coercing silently.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(
            f"inch_to_mm expected a numeric length, got {type(value).__name__}"
        )
    return float(value) * MM_PER_INCH


# ---------------------------------------------------------------------------
# Spec-tree walker (the single chokepoint)
# ---------------------------------------------------------------------------


# Names of JSON fields whose values are lengths in the spec's authored
# unit. The walker descends into every node (dicts, lists) and converts
# only these keys. Keep this set in sync with LENGTH_SCHEMA uses in
# spec/schema.py; if a new length field lands without being listed here,
# an inch-authored spec will silently mis-scale that field.
#
# v1 field coverage (per schema.py LENGTH_SCHEMA uses):
#   width, height, depth, radius, diameter
# Plus literal-mm position fields that the spec author also sets in the
# authored unit (center u/v, edge/target xyz, centerline start/end xy).
LENGTH_FIELDS: frozenset[str] = frozenset(
    {
        # Declared lengths (LENGTH_SCHEMA-tagged in the schema).
        "width",
        "height",
        "depth",
        "radius",
        "diameter",
        # Positional coordinates authored in the length unit.
        "x",
        "y",
        "z",
        "u",
        "v",
    }
)


def convert_spec_units(spec: dict[str, Any], unit: SpecUnit | str) -> dict[str, Any]:
    """Return a deep copy of *spec* with length values normalized to mm.

    If *unit* is :attr:`SpecUnit.MM` (the default / no-op path), the input
    is returned **unmodified** — no copy, no traversal — so the common
    case stays free.

    For :attr:`SpecUnit.INCH`, every numeric value under a key in
    :data:`LENGTH_FIELDS` is multiplied by :data:`MM_PER_INCH`. ``{"rhs":
    "..."}`` bindings and non-numeric values (e.g. the ``locals`` path)
    pass through untouched — the resolved value is converted on a later
    pass (see ``spec.builder._resolve_rhs_in_spec``).

    Raises :class:`ValueError` for an unknown *unit*, :class:`TypeError`
    if a length field carries a non-numeric, non-rhs value.
    """
    parsed = parse_unit(unit)
    if parsed is DEFAULT_UNIT:
        return spec

    def _convert_value(v: Any) -> Any:
        if isinstance(v, dict) and "rhs" in v:
            return v
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"length field holds non-numeric value: {v!r}")
        return inch_to_mm(v)

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: (_convert_value(v) if k in LENGTH_FIELDS else _walk(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(spec)
