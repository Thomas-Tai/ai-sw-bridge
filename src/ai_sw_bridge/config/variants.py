"""Configuration variant registry (Phase 4, FR-4-01).

Maps each declarative variant name to the set of locals-variable
overrides that define it.

A **variant** is a named override set applied on top of the base
*_locals.txt file (the shipped equation infrastructure in
locals_io).  Each variant produces one SOLIDWORKS configuration
via ConfigurationManager.AddConfiguration2 — that call is
SEAT-gated (🔴); the override computation and data model are SW-free.

The override format mirrors the locals-file format: each override
maps a variable name to a replacement RHS expression string, exactly
as locals_io.LocalEntry.expression.  This means variant values
are the same raw SW-equation expressions the Equation Manager
already understands ("VAR" + 3, 25.0, "X" * "Y").

Design rules:

- All variable names must exist in the base locals file **or** be
  explicitly flagged as new additions.  The dispatch layer validates
  this before touching COM.
- Variant names are unique within a spec and become the SW
  configuration name verbatim.
- The base locals file is never mutated; apply_overrides returns
  a new string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VariantOverride:
    """One variable override within a variant.

    Attributes:
        variable: Name of the locals-file variable to override (e.g.
            "WIDTH").  Must match the quoted name in the base
            *_locals.txt file.
        expression: The replacement RHS expression string.  Same format
            as locals_io.LocalEntry.expression — a raw SW-equation
            expression (e.g. "25.0", "\"X\" + 3").
    """

    variable: str
    expression: str


@dataclass(frozen=True)
class ConfigVariant:
    """One configuration variant.

    Attributes:
        name: Configuration name — becomes the SW configuration name
            verbatim.  Must be unique within the spec.
        overrides: The set of variable overrides to apply on top of the
            base locals file.  An empty list means the variant uses the
            base values unchanged (useful for a "default" or
            "as-designed" configuration).
        description: Optional human-readable description stored in the
            SW configuration's description field.
    """

    name: str
    overrides: list[VariantOverride] = field(default_factory=list)
    description: str = ""


@dataclass
class ConfigResult:
    """Outcome of creating one configuration.

    Attributes:
        variant: The variant name that was attempted.
        ok: True if the configuration was created and the overrides
            were applied.
        error: Human-readable error string on failure; None on
            success.
    """

    variant: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"variant": self.variant, "ok": self.ok}
        if self.error is not None:
            out["error"] = self.error
        return out


def parse_variants(block: list[dict[str, Any]]) -> list[ConfigVariant]:
    """Parse the variants: array from a schema-v2 spec.

    Each entry must have a name string and an optional overrides
    object mapping variable names to expression strings.

    Raises ValueError on structural problems (missing name, duplicate
    names, non-string expressions).
    """
    if not isinstance(block, list):
        raise ValueError("variants block must be an array")

    seen: set[str] = set()
    variants: list[ConfigVariant] = []

    for i, entry in enumerate(block):
        if not isinstance(entry, dict):
            raise ValueError(f"variants[{i}] must be an object")

        name = entry.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"variants[{i}] missing or non-string 'name'")
        if name in seen:
            raise ValueError(f"duplicate variant name: {name!r}")
        seen.add(name)

        raw_overrides = entry.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            raise ValueError(
                f"variant {name!r}: 'overrides' must be an object"
            )

        overrides: list[VariantOverride] = []
        for var, expr in raw_overrides.items():
            if not isinstance(expr, str):
                raise ValueError(
                    f"variant {name!r}: override for {var!r} must be a string expression"
                )
            overrides.append(VariantOverride(variable=var, expression=expr))

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise ValueError(
                f"variant {name!r}: 'description' must be a string"
            )

        variants.append(
            ConfigVariant(
                name=name,
                overrides=overrides,
                description=description,
            )
        )

    return variants


VARIANT_NAMES: frozenset[str] = frozenset()
"""Reserved for a future static registry (mirrors EXPORT_FORMAT_NAMES).
Currently variants are spec-defined, not pre-registered."""
