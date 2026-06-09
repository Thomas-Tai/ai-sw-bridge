"""Deep-merge utility for spec dict overrides (Phase 4, multifile).

Merges a variant's override dict into a base spec dict, producing a
new spec for each variant.  Used by ``_materialize_variant`` to create
distinct per-variant specs that yield different geometry when built.

Rules:

- Dicts are merged recursively; non-dict values in the override
  **replace** the base value.
- The base dict is never mutated — a fresh copy is returned.
- Lists in the override **replace** the base list entirely (no
  element-level merging).  This keeps the semantics simple and
  predictable.
"""

from __future__ import annotations

import copy
from typing import Any


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overrides* into a copy of *base*.

    Args:
        base: The base spec dict.  Never mutated.
        overrides: A dict of overrides.  Dict values are merged
            recursively; all other types replace the base value.

    Returns:
        A new dict with overrides applied.
    """
    result = copy.deepcopy(base)
    _merge_in_place(result, overrides)
    return result


def _merge_in_place(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge *source* into *target* (mutates *target*)."""
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _merge_in_place(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
