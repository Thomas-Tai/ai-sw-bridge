from __future__ import annotations

from pathlib import Path

from tools import demo_no_dim_showcase as demo


def test_parse_project_scripts_keeps_ai_sw_commands(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "\n".join(
            [
                "[project.scripts]",
                'ai-sw-build = "ai_sw_bridge.cli.build:main"',
                'ai-sw-observe = "ai_sw_bridge.cli.observe:main"',
                'not-bridge = "example:main"',
                "",
                "[tool.black]",
            ]
        ),
        encoding="utf-8",
    )

    assert demo.parse_project_scripts(pyproject) == [
        "ai-sw-build",
        "ai-sw-observe",
    ]


def test_parse_observe_tools_reads_docstring_subcommands(tmp_path: Path) -> None:
    observe_py = tmp_path / "observe.py"
    observe_py.write_text(
        '"""ai-sw-observe: read-only inspection CLI.\n'
        "\n"
        "Subcommands:\n"
        "  active_doc          -> sw_get_active_doc()\n"
        "  feature_statistics  -> sw_get_feature_statistics()\n"
        "  min_wall            -> sw_min_wall_thickness(samples_per_face)\n"
        "\n"
        "Each subcommand prints JSON.\n"
        '"""\n',
        encoding="utf-8",
    )

    assert demo.parse_observe_tools(observe_py) == [
        "active_doc",
        "feature_statistics",
        "min_wall",
    ]


def test_capability_sections_include_every_build_kind() -> None:
    payload = {
        "spec_feature_types": [
            "sketch_rectangle_on_plane",
            "boss_extrude_blind",
            "fillet_constant_radius",
            "linear_pattern",
        ],
        "feature_add_kinds": [
            "shell",
            "helix",
            "base_flange",
            "structural_weldment",
            "future_kind",
        ],
    }

    sections = demo.build_capability_sections(
        payload,
        cli_commands=["ai-sw-build", "ai-sw-observe"],
        observe_tools=["active_doc", "bounding_box"],
    )
    flattened = "\n".join(item for section in sections for item in section.items)

    for name in payload["spec_feature_types"] + payload["feature_add_kinds"]:
        assert name in flattened
    assert "ai-sw-build" in flattened
    assert "bounding_box" in flattened


def test_compact_capability_sections_summarize_without_full_name_list() -> None:
    payload = {
        "spec_feature_types": [
            "sketch_rectangle_on_plane",
            "boss_extrude_blind",
            "fillet_constant_radius",
            "linear_pattern",
        ],
        "feature_add_kinds": [
            "shell",
            "helix",
            "base_flange",
            "structural_weldment",
        ],
    }

    sections = demo.build_capability_sections(
        payload,
        cli_commands=["ai-sw-build", "ai-sw-observe"],
        observe_tools=["active_doc", "bounding_box"],
        compact=True,
    )
    flattened = "\n".join(item for section in sections for item in section.items)

    assert "4 part-spec functions" in flattened
    assert "4 feature-add functions" in flattened
    assert "sketch_rectangle_on_plane" not in flattened
    assert "base_flange" not in flattened


def test_resolve_showcase_selects_drive_roller_spec() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="drive_roller",
        spec_arg=None,
        smoke_flag=False,
    )

    assert selected.key == "drive_roller"
    assert selected.spec_path == Path("C:/repo/examples/drive_roller/spec.json")
    assert selected.smoke is False
    assert "bearing pockets" in " ".join(selected.intent)


def test_resolve_showcase_prefers_smoke_alias() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="drive_roller",
        spec_arg=None,
        smoke_flag=True,
    )

    assert selected.key == "smoke"
    assert selected.spec_path is None
    assert selected.smoke is True


def test_resolve_showcase_allows_custom_spec() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="motor_mount",
        spec_arg="C:/parts/custom/spec.json",
        smoke_flag=False,
    )

    assert selected.key == "custom"
    assert selected.spec_path == Path("C:/parts/custom/spec.json")
    assert selected.smoke is False


def test_demo_plan_runs_lint_then_live_no_dim_build() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="motor_mount",
        spec_arg=None,
        smoke_flag=False,
    )
    plan = demo.build_demo_plan(
        repo_root=Path("C:/repo"),
        showcase=selected,
    )
    dry_run = next(step for step in plan if step.id == "dry_run")
    live_build = next(step for step in plan if step.id == "live_build")

    assert "--dry-run" in dry_run.argv
    assert "--lint" in dry_run.argv
    assert "--no-dim" in live_build.argv
    assert "--yes" in live_build.argv
    assert "--nodim" not in live_build.argv


def test_smoke_plan_uses_bundled_demo_for_live_build() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="smoke",
        spec_arg=None,
        smoke_flag=False,
    )
    plan = demo.build_demo_plan(
        repo_root=Path("C:/repo"),
        showcase=selected,
    )
    live_build = next(step for step in plan if step.id == "live_build")

    assert "--demo" in live_build.argv
    assert "C:/repo/examples/motor_mount_plate/spec.json" not in live_build.argv


def test_preflight_only_steps_stop_before_live_build() -> None:
    selected = demo.resolve_showcase(
        repo_root=Path("C:/repo"),
        showcase_name="motor_mount",
        spec_arg=None,
        smoke_flag=False,
    )
    plan = demo.build_demo_plan(
        repo_root=Path("C:/repo"),
        showcase=selected,
    )

    steps = demo.steps_for_run(
        plan,
        preflight_only=True,
        skip_post_observe=False,
    )

    assert [step.id for step in steps] == ["list_kinds", "dry_run"]
