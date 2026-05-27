"""CLI stability tier markers (UIUX §2.2, requirements.md §4.8.1).

Every CLI entry point must declare an explicit stability tier so that
downstream consumers (agents, CI, humans) know what back-compat promise
to expect.  The tier is injected into ``--help`` output and tracked in
a module-level registry that tests can inspect.

Tiers
-----
stable
    No breaking changes without a major version bump.
experimental
    May change or disappear in any release.
deprecated
    Will be removed next major release; emits a stderr warning on
    every invocation.
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Literal

Tier = Literal["stable", "experimental", "deprecated"]

TIER_REGISTRY: dict[str, Tier] = {}


def cli_stability(tier: Tier) -> Callable[[Callable], Callable]:
    """Mark a CLI ``main()`` with a stability tier.

    Registers the tier in :data:`TIER_REGISTRY` keyed by the decorated
    function's module and attaches ``_cli_tier`` to the function object.
    """

    def decorator(func: Callable) -> Callable:
        mod = func.__module__
        TIER_REGISTRY[mod] = tier
        func._cli_tier = tier  # type: ignore[attr-defined]
        return func

    return decorator


def add_tier(parser: argparse.ArgumentParser, tier: Tier) -> None:
    """Inject *tier* into *parser*'s help output.

    Prepends ``[tier]`` to the parser description and sets
    ``parser._cli_tier`` for programmatic access.  If *tier* is
    ``"deprecated"``, prints a one-time stderr warning.
    """
    tag = f"[{tier}]"
    desc = parser.description or ""
    if not desc.startswith(tag):
        parser.description = f"{tag} {desc}"
    parser._cli_tier = tier  # type: ignore[attr-defined]
    if tier == "deprecated":
        print(
            f"WARNING: {parser.prog} is deprecated and will be removed "
            "in the next major release.",
            file=sys.stderr,
        )


def add_subcommand_tier(sub: argparse.ArgumentParser, tier: Tier) -> None:
    """Inject *tier* into a subcommand parser.

    Same visual treatment as :func:`add_tier`.  Call this after
    creating each subparser so that ``<cli> <subcommand> --help``
    shows the tier banner.
    """
    add_tier(sub, tier)
