"""Weak-form extension-conformance: every registered capability is discoverable
through the artifacts the Extension Contract requires. Strengthened in Phase 3
(architecture-defined manifest). Today it pins registry <-> doc/example membership
so a new capability can't be added without its contract obligations.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ai_sw_bridge.features import HANDLER_REGISTRY

_ROOT = Path(__file__).resolve().parents[1]


def test_every_feature_kind_named_in_readme_kind_table() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    missing = [k for k in HANDLER_REGISTRY if f"`{k}`" not in readme]
    assert not missing, f"feature_add kinds absent from README kind table: {missing}"


def test_every_cli_script_has_a_stability_tier() -> None:
    from ai_sw_bridge.cli import stability

    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    verbs = re.findall(
        r'^ai-sw-[\w-]+\s*=\s*"ai_sw_bridge\.cli\.(\w+):main"',
        pyproject,
        re.MULTILINE,
    )
    assert verbs, "no ai_sw_bridge.cli.*:main entries found in [project.scripts]"

    # TIER_REGISTRY is populated as a side effect of importing each cli module
    # (the @cli_stability(...) decorator on its main() registers the tier at
    # decoration time). A fresh interpreter that has only imported
    # ai_sw_bridge.cli.stability sees an EMPTY registry -- so import every
    # declared cli module first. This is import-only (no COM dispatch, no
    # live SOLIDWORKS seat touched) and mirrors what `ai-sw-mcp`/pytest
    # collection does anyway when the full package is exercised.
    #
    # "import" is itself a declared cli module name (ai_sw_bridge.cli.import),
    # which is a Python keyword -- importlib.import_module (not an `import`
    # statement) sidesteps that.
    for verb in verbs:
        importlib.import_module(f"ai_sw_bridge.cli.{verb}")

    missing = [
        verb
        for verb in verbs
        if f"ai_sw_bridge.cli.{verb}" not in stability.TIER_REGISTRY
    ]
    assert not missing, f"cli modules missing a @cli_stability tier: {missing}"


def test_every_spec_handler_lives_in_handlers_package() -> None:
    """Post-Phase-3: every DESCRIPTORS handler resolves to a callable defined
    in a spec.handlers.* module (or the spec.sketches.* handler classes),
    proving the self-registration shape holds and no handler slid back into
    builder.py."""
    from ai_sw_bridge.spec import builder

    strays = []
    for name, ft in builder.DESCRIPTORS.items():
        # spec.sketches.* handler-class .build methods are allowed; everything
        # else must live under spec.handlers.* (NOT spec.builder).
        if getattr(ft.handler, "__module__", "") == "ai_sw_bridge.spec.builder":
            strays.append(name)
    assert (
        not strays
    ), f"handlers still defined in builder.py (should be in handlers/*): {strays}"


def test_handlers_never_import_builder() -> None:
    """The handler leaf layer must not import builder (acyclic guarantee)."""
    import ast

    hdir = _ROOT / "src" / "ai_sw_bridge" / "spec" / "handlers"
    offenders = []
    for py in hdir.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "builder" in node.module
            ):
                offenders.append(py.name)
            if isinstance(node, ast.Import):
                for a in node.names:
                    if "builder" in a.name:
                        offenders.append(py.name)
    assert (
        not offenders
    ), f"handler modules import builder (breaks the leaf): {offenders}"
