"""Doc-truth guardrail: numbers that are derivable from source cannot drift.

Generalizes tests/test_readme_counts.py to every doc surface that restates a
code-derived count or the project version. Each (doc, fact) pair is one
parametrized assertion. Fixing a number in code without fixing the docs (or
vice versa) fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.spec.schema import ALL_TYPES

_ROOT = Path(__file__).resolve().parents[1]


def _mcp_tool_count() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_contract", _ROOT / "tests" / "mcp_lane" / "test_server_contract.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return len(mod.TestToolRegistration.EXPECTED_TOOLS)


def _cli_command_count() -> int:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return pyproject.count('= "ai_sw_bridge.cli.')


def _project_version() -> str:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert m, "version not found in pyproject.toml"
    return m.group(1)


# fact-name -> (derive fn, list of (doc-path, substring-template) it must appear in)
DERIVED = {
    "spec_types": (lambda: len(ALL_TYPES), "{n}"),
    "feature_kinds": (lambda: len(HANDLER_REGISTRY), "{n}"),
    "cli_commands": (_cli_command_count, "{n}"),
    "mcp_tools": (_mcp_tool_count, "{n}"),
    "version": (_project_version, "{n}"),
}

# (doc, fact, exact substring template using {n}) — every row must hold.
DOC_SURFACES = [
    ("README.md", "spec_types", "**{n} part-modelling feature types**"),
    ("README.md", "feature_kinds", "Feature kinds you can add ({n})"),
    ("README.md", "feature_kinds", "**{n} seat-proven**"),
    ("README.md", "cli_commands", "**{n} CLI commands"),
    ("README.md", "version", "Current release: `v{n}`"),
    ("README.md", "mcp_tools", "{n}-tool MCP server"),
    ("README.md", "feature_kinds", "{n}-kind `feature_add` registry"),
    ("docs/ONBOARDING.md", "cli_commands", "All {n} CLI commands"),
    ("docs/ONBOARDING.md", "mcp_tools", "exposes {n} read-only + build tools"),
    ("docs/CAPABILITIES.md", "version", "v{n}"),
    ("docs/PUBLIC_API.md", "version", "v{n}"),
    ("docs/CLASS_RELATION_MAP.md", "version", "v{n}"),
    ("CONTRIBUTING.md", "version", "v{n}"),
]


@pytest.mark.parametrize("doc,fact,template", DOC_SURFACES)
def test_doc_states_derived_value(doc: str, fact: str, template: str) -> None:
    derive, _ = DERIVED[fact]
    n = derive()
    needle = template.format(n=n)
    text = (_ROOT / doc).read_text(encoding="utf-8")
    assert needle in text, (
        f"{doc}: expected substring {needle!r} (derived {fact}={n}) not found. "
        f"The doc has drifted from source — update the doc."
    )


def test_onboarding_lists_every_cli_command() -> None:
    """ONBOARDING's command table must mention every ai-sw-* entry point."""
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    commands = re.findall(r"^(ai-sw-[\w-]+)\s*=", pyproject, re.MULTILINE)
    onboarding = (_ROOT / "docs" / "ONBOARDING.md").read_text(encoding="utf-8")
    missing = [c for c in commands if c not in onboarding]
    assert not missing, f"ONBOARDING.md command table is missing: {missing}"
