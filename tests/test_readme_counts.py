"""Guardrail: the README's headline counts must match the live code.

The README advertises several "magic numbers" that historically drifted from
the code (the zh translations still said "12"; a fresh-eyes audit even
mis-claimed the 36 was inflated). This test pins each number that is *purely
derivable from source* to its single source of truth, so the English README
cannot silently drift past green:

  - 30 spec feature types -> len(schema.ALL_TYPES)
  - 36 feature_add kinds   -> len(features.HANDLER_REGISTRY)
  - 21 CLI commands        -> [project.scripts] entries under ai_sw_bridge.cli

The 37-tool MCP count is locked separately by
``tests/mcp_lane/test_server_contract.py`` (its ``EXPECTED_TOOLS`` frozenset),
which is the authoritative contract for that surface.
"""

from __future__ import annotations

from pathlib import Path

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.spec.schema import ALL_TYPES

_ROOT = Path(__file__).resolve().parents[1]
_README = (_ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_spec_type_count_matches_schema() -> None:
    n = len(ALL_TYPES)
    assert (
        f"**{n} part-modelling feature types**" in _README
    ), f"README spec-type count is stale: schema.ALL_TYPES has {n}."


def test_readme_feature_kind_count_matches_registry() -> None:
    n = len(HANDLER_REGISTRY)
    assert (
        f"Feature kinds you can add ({n})" in _README
    ), f"README feature-kind heading is stale: HANDLER_REGISTRY has {n}."
    assert (
        f"**{n} seat-proven**" in _README
    ), f"README feature_add count is stale: HANDLER_REGISTRY has {n}."


def test_readme_cli_command_count_matches_pyproject() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Count [project.scripts] entry points that target the cli package. This
    # excludes ai-sw-mcp (it targets ai_sw_bridge.mcp.server), matching the
    # README's "21 CLI commands + one MCP server" split.
    n_cli = pyproject.count('= "ai_sw_bridge.cli.')
    assert n_cli > 0, "no cli entry points found in pyproject.toml"
    assert (
        f"**{n_cli} CLI commands" in _README
    ), f"README CLI-command count is stale: pyproject has {n_cli} cli scripts."
