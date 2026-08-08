from __future__ import annotations

from tools import _demo_lib
from tools import demo_no_dim_showcase as demo


def test_shared_symbols_are_the_same_object() -> None:
    # Re-export must be identity, not a copy, so both tools share one runner.
    for name in (
        "parse_project_scripts",
        "build_capability_sections",
        "run_step",
        "DemoStep",
        "CapabilitySection",
    ):
        assert getattr(demo, name) is getattr(_demo_lib, name)


def test_parse_project_scripts_filters_ai_sw(tmp_path) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project.scripts]\nai-sw-build = "x:main"\nother = "y:main"\n',
        encoding="utf-8",
    )
    assert _demo_lib.parse_project_scripts(p) == ["ai-sw-build"]
