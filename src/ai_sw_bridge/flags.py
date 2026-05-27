"""Feature-flag module for ai-sw-bridge v0.11 lanes.

Every v0.11 lane ships behind a feature flag. The flag's purpose is graceful
degradation — when a lane has a subtle bug, we can disable it per-installation
without re-shipping the package.

Resolution priority (highest first):
  1. CLI flag override (``--enable-flag`` / ``--disable-flag``).
  2. Environment variable (``AI_SW_BRIDGE_FLAG_<NAME>``).
  3. Per-repo ``.ai-sw-bridge.toml`` ``[flags]`` section.
  4. Module defaults (defined in ``FLAG_REGISTRY``).

This is NOT a general configuration framework. The flag set is small and
curated. Adding a new flag is a PR with justification; "flag-of-the-week"
growth is anti-pattern.

Ref: spec.md §8.7, audit §1.6.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeatureFlag:
    """Definition of a single feature flag.

    Attributes:
        name: Canonical flag name (e.g. ``brep_interrogation``).
        default: Default state when no override is present.
        description: Human-readable summary of what the flag gates.
        lane: Owning lane (L1, L2, L3, L4, M, or "core").
        removal_date: Earliest version where the flag may be removed
            once the lane reaches GA and the flag has been on-by-default
            for at least one minor release with no regressions.
    """

    name: str
    default: bool
    description: str
    lane: str
    removal_date: str


# ---------------------------------------------------------------------------
# Flag registry — the single source of truth for all v0.11 flags.
# ---------------------------------------------------------------------------

FLAG_REGISTRY: dict[str, FeatureFlag] = {
    "brep_interrogation": FeatureFlag(
        name="brep_interrogation",
        default=False,
        description="L1 B-rep interrogation lane — topological fingerprint + face metadata in build output.",
        lane="L1",
        removal_date="v0.13",
    ),
    "rag_apidoc": FeatureFlag(
        name="rag_apidoc",
        default=False,
        description="L3 RAG-indexed API documentation retrieval for spec authoring assistance.",
        lane="L3",
        removal_date="v0.13",
    ),
    "checkpoint": FeatureFlag(
        name="checkpoint",
        default=False,
        description="L4 checkpoint writes — persist build state for mid-session resume and post-mortem.",
        lane="L4",
        removal_date="v0.14",
    ),
    "mcp_wrapper": FeatureFlag(
        name="mcp_wrapper",
        default=False,
        description="Lane M MCP server wrapper — expose ai-sw-bridge as an MCP tool server.",
        lane="M",
        removal_date="v0.14",
    ),
}


def _env_var_name(flag_name: str) -> str:
    """Map a flag name to its environment variable key.

    ``brep_interrogation`` → ``AI_SW_BRIDGE_FLAG_BREP_INTERROGATION``
    """
    return f"AI_SW_BRIDGE_FLAG_{flag_name.upper()}"


def _read_env(flag_name: str) -> bool | None:
    """Read the environment variable override for *flag_name*.

    Returns ``True`` when the value is ``"1"``, ``"true"``, or ``"yes"``
    (case-insensitive), ``False`` when ``"0"``, ``"false"``, or ``"no"``,
    and ``None`` when unset or unparseable (the caller falls through to the
    next precedence level).
    """
    val = os.environ.get(_env_var_name(flag_name))
    if val is None:
        return None
    if val.lower() in ("1", "true", "yes"):
        return True
    if val.lower() in ("0", "false", "no"):
        return False
    return None


def _read_toml(flag_name: str, toml_path: Path | None = None) -> bool | None:
    """Read the ``.ai-sw-bridge.toml`` ``[flags]`` override for *flag_name*.

    Returns ``None`` when the file is absent, the ``[flags]`` section is
    missing, or the key is not present — the caller falls through to the
    next precedence level.

    Uses only stdlib ``tomllib`` (Python 3.11+) or the ``tomli`` backport
    if available. No third-party dependency is *required* — if neither is
    importable the TOML layer is silently skipped.
    """
    if toml_path is None:
        candidate = Path(".ai-sw-bridge.toml")
        toml_path = candidate if candidate.exists() else None
    if toml_path is None or not toml_path.exists():
        return None

    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        return None

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    flags_section = data.get("flags", {})
    if not isinstance(flags_section, dict):
        return None
    val = flags_section.get(flag_name)
    if isinstance(val, bool):
        return val
    return None


def resolve(
    *,
    cli_overrides: dict[str, bool] | None = None,
    toml_path: Path | None = None,
) -> dict[str, bool]:
    """Resolve all feature flags using the four-level precedence chain.

    Args:
        cli_overrides: Mapping of flag-name → bool from ``--enable-flag``
            / ``--disable-flag`` CLI arguments (highest priority).
        toml_path: Explicit path to ``.ai-sw-bridge.toml``.  When ``None``
            the file is looked up at ``./.ai-sw-bridge.toml``.

    Returns:
        Mapping of every registered flag name to its resolved boolean state.

    Raises:
        ValueError: If *cli_overrides* contains a flag name that is not in
            ``FLAG_REGISTRY``.
    """
    cli_overrides = cli_overrides or {}
    unknown = set(cli_overrides) - set(FLAG_REGISTRY)
    if unknown:
        raise ValueError(f"unknown feature flag(s): {', '.join(sorted(unknown))}")

    resolved: dict[str, bool] = {}
    for name, flag in FLAG_REGISTRY.items():
        # Level 1: CLI override (highest priority)
        if name in cli_overrides:
            resolved[name] = cli_overrides[name]
            continue
        # Level 2: Environment variable
        env_val = _read_env(name)
        if env_val is not None:
            resolved[name] = env_val
            continue
        # Level 3: .ai-sw-bridge.toml [flags]
        toml_val = _read_toml(name, toml_path)
        if toml_val is not None:
            resolved[name] = toml_val
            continue
        # Level 4: Registry default
        resolved[name] = flag.default
    return resolved


def parse_flag_args(
    enable: list[str] | None, disable: list[str] | None
) -> dict[str, bool]:
    """Convert ``--enable-flag`` / ``--disable-flag`` lists into a single overrides dict.

    Validates every flag name against ``FLAG_REGISTRY``. Raises ``ValueError``
    on unknown names or contradictory enable/disable of the same flag.
    """
    enable = enable or []
    disable = disable or []
    overrides: dict[str, bool] = {}
    for name in enable:
        if name not in FLAG_REGISTRY:
            raise ValueError(f"unknown feature flag: {name!r}")
        overrides[name] = True
    for name in disable:
        if name not in FLAG_REGISTRY:
            raise ValueError(f"unknown feature flag: {name!r}")
        if name in overrides and overrides[name] is True:
            raise ValueError(f"flag {name!r} is both enabled and disabled")
        overrides[name] = False
    return overrides
