#!/usr/bin/env python3
"""Guided no-dim capability demo for recording a GitHub GIF.

The script is intentionally a wrapper around the public CLIs. It first tours
the supported surface from current repository sources, then pauses so the
operator can bring the SOLIDWORKS window into the recording before running a
live ``ai-sw-build ... --no-dim --yes`` showcase build.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow ``python tools/demo_no_dim_showcase.py`` from any cwd: the direct
# script invocation puts this file's own directory on sys.path[0], not the
# repo root, so the ``tools`` package would otherwise be unimportable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._demo_lib import (  # noqa: E402,F401  (re-exported for back-compat + tests)
    CapabilitySection,
    DemoStep,
    SPEC_TYPE_GROUPS,
    FEATURE_ADD_GROUPS,
    CLI_GROUPS,
    repo_root_from_script,
    parse_project_scripts,
    parse_observe_tools,
    build_capability_sections,
    _command_env,
    _module_argv,
    _spec_arg,
    _print_capability_tour,
    _print_header,
    run_step,
    _pause,
)


DEFAULT_SHOWCASE = "motor_mount"


@dataclass(frozen=True)
class ShowcaseDefinition:
    key: str
    label: str
    spec_path: Path | None
    intent: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedShowcase:
    key: str
    label: str
    spec_path: Path | None
    smoke: bool
    intent: tuple[str, ...]


SHOWCASES: dict[str, ShowcaseDefinition] = {
    "motor_mount": ShowcaseDefinition(
        key="motor_mount",
        label="Motor mount plate",
        spec_path=Path("examples") / "motor_mount_plate" / "spec.json",
        intent=(
            "base plate",
            "center coupler hole",
            "flange recess",
            "motor holes",
            "frame holes",
        ),
    ),
    "drive_roller": ShowcaseDefinition(
        key="drive_roller",
        label="Drive roller",
        spec_path=Path("examples") / "drive_roller" / "spec.json",
        intent=(
            "cylindrical roller body",
            "center bore",
            "bearing pockets",
            "revolved belt groove",
        ),
    ),
    "patterned_plate": ShowcaseDefinition(
        key="patterned_plate",
        label="Patterned plate",
        spec_path=Path("examples") / "patterned_plate" / "spec.json",
        intent=("base plate", "seed hole", "linear hole pattern"),
    ),
    "smoke": ShowcaseDefinition(
        key="smoke",
        label="Bundled smoke demo",
        spec_path=None,
        intent=("box", "blind extrude", "constant-radius fillet"),
    ),
}


def resolve_showcase(
    repo_root: Path,
    showcase_name: str,
    spec_arg: str | None,
    smoke_flag: bool,
) -> ResolvedShowcase:
    if smoke_flag:
        showcase_name = "smoke"
    if spec_arg is not None:
        spec_path = Path(spec_arg)
        if not spec_path.is_absolute():
            spec_path = repo_root / spec_path
        return ResolvedShowcase(
            key="custom",
            label="Custom spec",
            spec_path=spec_path,
            smoke=False,
            intent=("custom JSON spec",),
        )
    definition = SHOWCASES[showcase_name]
    spec_path = (
        None if definition.spec_path is None else repo_root / definition.spec_path
    )
    return ResolvedShowcase(
        key=definition.key,
        label=definition.label,
        spec_path=spec_path,
        smoke=definition.spec_path is None,
        intent=definition.intent,
    )


def build_demo_plan(repo_root: Path, showcase: ResolvedShowcase) -> list[DemoStep]:
    if showcase.smoke:
        build_target = ["--demo"]
        display_target = "--demo"
    else:
        if showcase.spec_path is None:
            raise ValueError("non-smoke showcase requires a spec path")
        build_target = [_spec_arg(showcase.spec_path)]
        display_target = str(showcase.spec_path)

    return [
        DemoStep(
            id="list_kinds",
            title="Probe the current supported build surface",
            argv=_module_argv("ai_sw_bridge.cli.build", "--list-kinds"),
            display="ai-sw-build --list-kinds",
            capture_json=True,
        ),
        DemoStep(
            id="dry_run",
            title="Validate and lint the showcase spec before touching SOLIDWORKS",
            argv=_module_argv(
                "ai_sw_bridge.cli.build",
                *build_target,
                "--dry-run",
                "--lint",
            ),
            display=f"ai-sw-build {display_target} --dry-run --lint",
            capture_json=True,
        ),
        DemoStep(
            id="live_build",
            title="Live SOLIDWORKS build in no-dim mode",
            argv=_module_argv(
                "ai_sw_bridge.cli.build",
                *build_target,
                "--no-dim",
                "--yes",
            ),
            display=f"ai-sw-build {display_target} --no-dim --yes",
        ),
        DemoStep(
            id="observe_active_doc",
            title="Read back the active SOLIDWORKS document",
            argv=_module_argv("ai_sw_bridge.cli.observe", "active_doc"),
            display="ai-sw-observe active_doc",
            capture_json=True,
            allow_failure=True,
        ),
        DemoStep(
            id="observe_feature_statistics",
            title="Read back feature statistics",
            argv=_module_argv("ai_sw_bridge.cli.observe", "feature_statistics"),
            display="ai-sw-observe feature_statistics",
            capture_json=True,
            allow_failure=True,
        ),
        DemoStep(
            id="observe_bounding_box",
            title="Read back the bounding box",
            argv=_module_argv("ai_sw_bridge.cli.observe", "bounding_box"),
            display="ai-sw-observe bounding_box",
            capture_json=True,
            allow_failure=True,
        ),
    ]


def steps_for_run(
    plan: list[DemoStep],
    *,
    preflight_only: bool,
    skip_post_observe: bool,
) -> list[DemoStep]:
    if preflight_only:
        return [step for step in plan if step.id in {"list_kinds", "dry_run"}]
    if skip_post_observe:
        return [step for step in plan if not step.id.startswith("observe_")]
    return list(plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="demo_no_dim_showcase",
        description=(
            "Guided capability tour plus live ai-sw-build --no-dim demo for "
            "recording a SOLIDWORKS GIF."
        ),
    )
    parser.add_argument(
        "--spec",
        default=None,
        help=(
            "Custom showcase spec to build. Overrides --showcase and is "
            "ignored with --smoke."
        ),
    )
    parser.add_argument(
        "--showcase",
        choices=sorted(SHOWCASES),
        default=DEFAULT_SHOWCASE,
        help=(
            "Named showcase to run. Defaults to motor_mount; use drive_roller "
            "for cylindrical/revolve-cut geometry or patterned_plate for a "
            "short pattern demo."
        ),
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Use a GIF-friendly capability summary instead of full function lists.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Shortcut for --showcase smoke: use the bundled filleted box.",
    )
    parser.add_argument(
        "--tour-only",
        action="store_true",
        help="Print the current capability tour and stop before SOLIDWORKS work.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Run the capability tour plus dry-run/lint rehearsal, then stop "
            "before the live SOLIDWORKS build."
        ),
    )
    parser.add_argument(
        "--skip-post-observe",
        action="store_true",
        help="Skip read-back observation commands after the live build.",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Do not wait for Enter prompts; useful for CI and rehearsals.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.8,
        help="Seconds to pause after printing each command caption.",
    )
    args = parser.parse_args(argv)

    repo_root = repo_root_from_script()
    showcase = resolve_showcase(
        repo_root=repo_root,
        showcase_name=args.showcase,
        spec_arg=args.spec,
        smoke_flag=args.smoke,
    )
    if (
        not showcase.smoke
        and showcase.spec_path is not None
        and not showcase.spec_path.exists()
    ):
        print(
            f"showcase spec not found: {showcase.spec_path}; falling back to --demo",
            file=sys.stderr,
        )
        showcase = resolve_showcase(
            repo_root=repo_root,
            showcase_name="smoke",
            spec_arg=None,
            smoke_flag=False,
        )

    env = _command_env(repo_root)
    plan = build_demo_plan(repo_root, showcase)
    run_steps = steps_for_run(
        plan,
        preflight_only=args.preflight_only,
        skip_post_observe=args.skip_post_observe,
    )

    print("ai-sw-bridge no-dim showcase")
    print("JSON spec -> validated plan -> live SOLIDWORKS build")
    print(f"Showcase: {showcase.label} ({showcase.key})")
    print(f"Intent: {' -> '.join(showcase.intent)}")
    print("Mode note: 'nodim' in conversation maps to the real CLI flag --no-dim.")

    list_step = next(step for step in plan if step.id == "list_kinds")
    rc, list_payload = run_step(
        list_step,
        cwd=repo_root,
        env=env,
        sleep_s=args.sleep,
    )
    if rc:
        return rc
    if list_payload is None:
        print("could not read build surface payload", file=sys.stderr)
        return 2

    cli_commands = parse_project_scripts(repo_root / "pyproject.toml")
    observe_tools = parse_observe_tools(
        repo_root / "src" / "ai_sw_bridge" / "cli" / "observe.py"
    )
    sections = build_capability_sections(
        list_payload,
        cli_commands,
        observe_tools,
        compact=args.compact,
    )
    _print_capability_tour(sections)

    if args.tour_only:
        return 0

    dry_run = next(step for step in run_steps if step.id == "dry_run")
    rc, _payload = run_step(dry_run, cwd=repo_root, env=env, sleep_s=args.sleep)
    if rc:
        return rc
    if args.preflight_only:
        return 0

    _pause(
        "Bring the SOLIDWORKS model window into the recording frame now. "
        "The next command creates a fresh part with --no-dim, so there are "
        "no Modify Dimension popups.",
        args.no_pause,
    )

    live_build = next(step for step in plan if step.id == "live_build")
    rc, _payload = run_step(live_build, cwd=repo_root, env=env, sleep_s=args.sleep)
    if rc:
        return rc

    for step in run_steps:
        if not step.id.startswith("observe_"):
            continue
        run_step(step, cwd=repo_root, env=env, sleep_s=args.sleep)

    _pause(
        "Keep the finished SOLIDWORKS part visible for the final seconds "
        "of the GIF. Demo complete.",
        args.no_pause,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
