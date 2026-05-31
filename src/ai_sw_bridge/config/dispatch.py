"""Configuration dispatch (Phase 4, FR-4-01, todolist P4.1).

Iterates the ``variants:`` block from a schema-v2 spec, applies each
variant's locals overrides, and creates one SOLIDWORKS configuration per
variant.

Two-stream discipline (``UIUX.md`` §8):
  - **Human stream** (stderr): one line per configuration created.
  - **Machine stream**: ``ConfigResult`` list returned to the caller.

The SW-free layer validates that every override variable exists in the
base locals file, computes the effective locals text for each variant,
and structures the dispatch loop.  The actual COM call
(``ConfigurationManager.AddConfiguration2``) is SEAT-gated — only W0
runs it on a live seat.

Design:

- ``apply_overrides`` is a pure function: base text + overrides -> new
  text.  No file I/O, no COM.  Reuses ``locals_io.parse`` /
  ``locals_io.replace_rhs``.
- ``validate_overrides`` checks variable existence before any dispatch.
  Returns a list of unknown-variable errors (empty = clean).
- ``create_all`` iterates variants, calls ``_create_one`` per variant.
- ``_create_one`` is the seat-gated boundary: the SW-free structure
  computes the override text, then delegates to the SEAT stub.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from ..locals_io import find_entry, parse, replace_rhs
from .variants import (
    ConfigResult,
    ConfigVariant,
    VariantOverride,
    parse_variants,
)

logger = logging.getLogger("ai_sw_bridge.config")


def apply_overrides(
    base_text: str,
    overrides: list[VariantOverride],
) -> str:
    """Compute the effective locals text after applying variant overrides.

    Pure function — no file I/O, no COM.  Reuses the shipped
    ``locals_io`` parser and replacer.

    For each override:
      - If the variable exists in the base, its RHS is replaced.
      - If it does not exist, the override is appended as a new line.

    Args:
        base_text: The full text of the base ``*_locals.txt`` file.
        overrides: The variant's override set.

    Returns:
        The modified locals text with all overrides applied.
    """
    text = base_text
    entries = parse(text)
    known = {e.name: e for e in entries}

    for ov in overrides:
        entry = known.get(ov.variable)
        if entry is not None:
            text = replace_rhs(text, entry.line_index, ov.expression)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f'"{ov.variable}" = {ov.expression}\n'

    return text


def validate_overrides(
    base_text: str,
    variants: list[ConfigVariant],
) -> list[str]:
    """Check that all override variables exist in the base locals.

    Returns a list of error strings (empty = all clean).  Does not
    raise — the caller decides whether to fail-stop or warn.
    """
    entries = parse(base_text)
    known = {e.name for e in entries}
    errors: list[str] = []
    for v in variants:
        for ov in v.overrides:
            if ov.variable not in known:
                errors.append(
                    f"variant {v.name!r}: unknown variable {ov.variable!r} "
                    f"(not in base locals)"
                )
    return errors


def create_all(
    doc: Any,
    variants: list[ConfigVariant],
    base_locals_text: str,
) -> list[ConfigResult]:
    """Create one SW configuration per variant.

    Args:
        doc: An ``IModelDoc2``-like dispatch object (live or mock).
        variants: Parsed from the spec's ``variants:`` block.
        base_locals_text: The full text of the base ``*_locals.txt``.

    Returns:
        One ``ConfigResult`` per variant, in the same order.
    """
    results: list[ConfigResult] = []
    for v in variants:
        result = _create_one(doc, v, base_locals_text)
        if result.ok:
            print(
                f"  config {v.name!r} created ({len(v.overrides)} overrides)",
                file=sys.stderr,
            )
        else:
            print(
                f"  FAILED config {v.name!r}: {result.error}",
                file=sys.stderr,
            )
        results.append(result)
    return results


def _create_one(
    doc: Any,
    variant: ConfigVariant,
    base_locals_text: str,
) -> ConfigResult:
    """Create one configuration.  The COM call is SEAT-gated.

    SW-free pre-condition: computes the effective locals text.
    SEAT-gated: ``ConfigurationManager.AddConfiguration2`` — the
    call shape is ``ConfigurationManager.AddConfiguration2(
    name, alternateName, description)``.  The exact arg semantics
    (is ``alternateName`` the duplicate-name suffix? the display
    name?) and the per-configuration equation-link mechanism need
    a live seat to confirm.
    """
    effective_text = apply_overrides(base_locals_text, variant.overrides)

    try:
        cm = doc.ConfigurationManager
        config = cm.AddConfiguration2(
            variant.name,
            "",
            variant.description,
        )
    except Exception as exc:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error=(
                f"AddConfiguration2 is SEAT-gated (P4.1). "
                f"Call raised {type(exc).__name__}: {exc}"
            ),
        )

    if config is None:
        return ConfigResult(
            variant=variant.name,
            ok=False,
            error="AddConfiguration2 returned None",
        )

    return ConfigResult(variant=variant.name, ok=True)
