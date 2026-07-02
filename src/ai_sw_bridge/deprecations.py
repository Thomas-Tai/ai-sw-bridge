"""Cross-surface deprecation registry + grace-policy validator.

Leaf module: imports only stdlib. Governs the four public surface classes
(stable CLI, MCP tool, facade, spec handler) by *opaque string id* — it never
imports the symbols it governs, so it cannot form an import cycle. An
import-linter forbidden contract (pyproject.toml) pins the leaf property.

Policy (PUBLIC_API.md "Deprecation policy", ratified 2026-07-02):
  stable_cli / mcp_tool / facade  -> deprecate in 1.N; removed ONLY at the next
      major boundary (2.0), floor >= 2 minor releases between announce and cut.
      The gate enforces the stronger, cleanly-checkable superset: removal lands
      only on the next major's .0 (never within the announcing major), which
      guarantees the whole remainder of the 1.x line elapses first.
  experimental_cli / spec_handler -> deprecate in 1.N; removed in 1.N+1.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from typing import Sequence

_STABLE_CLASSES = frozenset({"stable_cli", "mcp_tool", "facade"})
_EXPERIMENTAL_CLASSES = frozenset({"experimental_cli", "spec_handler"})


@dataclass(frozen=True)
class DeprecationEntry:
    id: str  # "<surface_class>:<surface-name>", e.g. "mcp_tool:sw_bbox"
    surface_class: str
    deprecated_in: str  # "1.8"
    remove_in: str  # "2.0"
    replacement: str


@dataclass(frozen=True)
class Violation:
    entry_id: str
    reason: str


# Production registry — EMPTY at v1.7.0. Immutable tuple: an accidental
# mutation raises rather than silently pollutes. Add entries HERE (never in a
# test) when a real surface is deprecated.
DEPRECATIONS: tuple[DeprecationEntry, ...] = ()


def _parse(v: str) -> tuple[int, int]:
    """Parse 'MAJOR.MINOR' (any patch suffix ignored)."""
    parts = v.split(".")
    return int(parts[0]), int(parts[1])


def current_version() -> str:
    return _pkg_version("ai-sw-bridge")


def validate_registry(
    entries: Sequence[DeprecationEntry], current: str
) -> list[Violation]:
    """Pure validator — reads only its arguments, never the module global.

    ``current`` is intentionally unused today: the structural grace-policy
    checks (major-boundary / next-minor / announce-before-remove) are
    version-independent. It is a reserved parameter for the future
    present-vs-absent check (a surface whose ``remove_in`` <= ``current`` must
    no longer exist). Keeping it in the signature now avoids a later breaking
    change to this contract.
    """
    out: list[Violation] = []
    for e in entries:
        try:
            dep = _parse(e.deprecated_in)
            rem = _parse(e.remove_in)
        except (ValueError, IndexError):
            out.append(Violation(e.id, f"unparseable version in {e!r}"))
            continue
        if rem <= dep:
            out.append(
                Violation(e.id, "remove_in must be strictly after deprecated_in")
            )
            continue
        if e.surface_class in _STABLE_CLASSES:
            # Removal only at the next major boundary: (dep_major + 1, 0).
            if rem != (dep[0] + 1, 0):
                out.append(
                    Violation(
                        e.id,
                        "stable surface must be removed at the next major boundary "
                        f"({dep[0] + 1}.0), not {e.remove_in}",
                    )
                )
        elif e.surface_class in _EXPERIMENTAL_CLASSES:
            if rem != (dep[0], dep[1] + 1):
                out.append(
                    Violation(
                        e.id,
                        f"experimental surface must be removed in the next minor "
                        f"({dep[0]}.{dep[1] + 1}), not {e.remove_in}",
                    )
                )
        else:
            out.append(Violation(e.id, f"unknown surface_class {e.surface_class!r}"))
    return out
