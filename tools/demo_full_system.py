#!/usr/bin/env python3
"""Chaptered full-system demo: part -> assembly -> observe -> drawing -> export.

The script is a thin orchestrator around the public CLIs, in the same spirit
as ``tools/demo_no_dim_showcase.py``. It is organized into named chapters so
an operator (or a recording session) can run the whole tour or a single
chapter. Only the ``tour`` chapter is wired to real steps in this skeleton;
the remaining chapters are stubs that later tasks fill in.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Allow ``python tools/demo_full_system.py`` from any cwd: the direct script
# invocation puts this file's own directory on sys.path[0], not the repo
# root, so the ``tools`` package would otherwise be unimportable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._demo_lib import (  # noqa: E402
    DemoStep,
    CapabilitySection,
    repo_root_from_script,
    parse_project_scripts,
    parse_observe_tools,
    build_capability_sections,
    _print_capability_tour,
    _print_header,
    _command_env,
    _module_argv,
    run_step,
    _pause,
)


DEFERRED_SIGNPOST = "Honest edges: see docs/DEFERRED.md for walled features."


@dataclass(frozen=True)
class BuildEnv:
    repo_root: Path
    demo_out: Path
    widget_dir: Path
    mates_proven: bool = False
    export_block_wired: bool = False
    mutate_drives_nodim: bool = False


@dataclass(frozen=True)
class Chapter:
    key: str
    title: str
    caption: str
    build_steps: Callable[[BuildEnv], list[DemoStep]]


def _tour_steps(env: BuildEnv) -> list[DemoStep]:
    return [
        DemoStep(
            id="list_kinds",
            title="Probe the current supported build surface",
            argv=_module_argv("ai_sw_bridge.cli.build", "--list-kinds"),
            display="ai-sw-build --list-kinds",
            capture_json=True,
        )
    ]


# The three demo-widget parts, in build order. The bearing block is built
# LAST so it is the active SOLIDWORKS document when the mutate/reparam beat
# runs (both target its BORE_DIA).
_PART_SPECS: tuple[tuple[str, str, str], ...] = (
    ("baseplate", "demo_baseplate", "DemoBaseplate"),
    ("shaft", "demo_shaft", "DemoShaft"),
    ("bearing_block", "demo_bearing_block", "DemoBearingBlock"),
)

# The variable the mutate/reparam beat resizes, and its new value. Both
# branches of mutate_beat_steps() target this so the on-screen narrative
# ("resize the bore") is identical regardless of which beat is live-valid.
_MUTATE_VAR = "BORE_DIA"
_MUTATE_NEW_VALUE = "20.0"

# Body of the fallback beat's runtime reparam step: copies the bearing
# block's spec + locals into a demo_out/ scratch copy and bumps BORE_DIA in
# the copy, never touching the committed examples/ locals.txt. Two format
# passes: the ``%(var)s``/``%(val)s`` substitution below bakes in the
# variable name/new value at import time (raw string, so the regex's own
# backslashes need no doubling); the ``{src}``/``{dst}`` placeholders are
# left untouched by that pass (``%`` formatting ignores braces) and are
# filled in later, per-call, by mutate_beat_steps() with the concrete
# demo_out paths.
_REPARAM_SCRIPT_TEMPLATE = r"""import pathlib, re, shutil
src = pathlib.Path("{src}")
dst = pathlib.Path("{dst}")
dst.mkdir(parents=True, exist_ok=True)
shutil.copy(src / "spec.json", dst / "spec.json")
loc = (src / "locals.txt").read_text(encoding="utf-8")
loc = re.sub(r'("%(var)s"\s*=\s*)[0-9.]+', r'\g<1>%(val)s', loc)
(dst / "locals.txt").write_text(loc, encoding="utf-8")
print("reparam: %(var)s -> %(val)s in", dst)
""" % {
    "var": _MUTATE_VAR,
    "val": _MUTATE_NEW_VALUE,
}


def mutate_beat_steps(env: BuildEnv) -> list[DemoStep]:
    """The headline "resize the bore and rebuild" beat.

    Two mutually exclusive branches, selected by ``env.mutate_drives_nodim``:

    * Primary (``True``): drive the change through ``ai-sw-mutate``'s
      propose -> dry_run -> commit workflow against the live-built bearing
      block. Whether ``ai-sw-mutate`` can drive a ``--no-dim``-built part at
      all is UNKNOWN and is exactly what Spike M (a later, seat-gated task)
      determines; this branch is inert (its steps are never executed) until
      that spike flips the flag to True.
    * Fallback (``False``, the default and the only no-SW-testable path):
      copy the bearing block's spec+locals into ``demo_out/reparam/``, bump
      ``BORE_DIA`` in the copy, and rebuild with ``--no-dim --yes
      --save-as``. This never touches the committed ``examples/`` locals.
    """
    if env.mutate_drives_nodim:
        return [
            DemoStep(
                id="mutate_propose",
                title="Propose: resize the bore",
                argv=_module_argv(
                    "ai_sw_bridge.cli.mutate",
                    "propose",
                    "--var",
                    _MUTATE_VAR,
                    "--new-value",
                    _MUTATE_NEW_VALUE,
                ),
                display=(
                    f"ai-sw-mutate propose --var {_MUTATE_VAR} "
                    f"--new-value {_MUTATE_NEW_VALUE}"
                ),
                capture_json=True,
            ),
            # <proposal-id> is a placeholder: the real proposal_id is emitted
            # by mutate_propose's JSON stdout at runtime. A dedicated
            # seat-phase runner (a later task, analogous to _run_tour above)
            # captures it from that JSON and substitutes it here before
            # running dry_run/commit. Not wired yet -- this whole branch is
            # inert until env.mutate_drives_nodim is set True at seat time.
            DemoStep(
                id="mutate_dry_run",
                title="Dry-run: apply, verify, roll back",
                argv=_module_argv(
                    "ai_sw_bridge.cli.mutate",
                    "dry_run",
                    "--proposal-id",
                    "<proposal-id>",
                ),
                display="ai-sw-mutate dry_run --proposal-id <proposal-id>",
            ),
            DemoStep(
                id="mutate_commit",
                title="Commit: re-apply and save",
                argv=_module_argv(
                    "ai_sw_bridge.cli.mutate",
                    "commit",
                    "--proposal-id",
                    "<proposal-id>",
                ),
                display="ai-sw-mutate commit --proposal-id <proposal-id>",
            ),
        ]

    reparam_src = env.widget_dir / "demo_bearing_block"
    reparam_dir = env.demo_out / "reparam"
    reparam_script = _REPARAM_SCRIPT_TEMPLATE.format(
        src=reparam_src.as_posix(), dst=reparam_dir.as_posix()
    )
    return [
        DemoStep(
            id="reparam_prep",
            title="Reparam: bump BORE_DIA in a demo_out/ copy",
            argv=[sys.executable, "-c", reparam_script],
            display=(
                f'python -c "<copy demo_bearing_block, {_MUTATE_VAR} -> '
                f'{_MUTATE_NEW_VALUE} in demo_out/reparam/>"'
            ),
        ),
        DemoStep(
            id="reparam_build",
            title="Rebuild the bearing block with the resized bore",
            argv=_module_argv(
                "ai_sw_bridge.cli.build",
                str(reparam_dir / "spec.json"),
                "--no-dim",
                "--yes",
                "--save-as",
                str(env.demo_out / "DemoBearingBlock_reparam.SLDPRT"),
            ),
            display=(
                "ai-sw-build demo_out/reparam/spec.json --no-dim --yes "
                "--save-as demo_out/DemoBearingBlock_reparam.SLDPRT"
            ),
        ),
    ]


def _part_steps(env: BuildEnv) -> list[DemoStep]:
    steps: list[DemoStep] = []
    for slug, dirname, part_name in _PART_SPECS:
        spec_path = env.widget_dir / dirname / "spec.json"
        save_as = env.demo_out / f"{part_name}.SLDPRT"
        steps.append(
            DemoStep(
                id=f"build_{slug}",
                title=f"Build {part_name}",
                argv=_module_argv(
                    "ai_sw_bridge.cli.build",
                    str(spec_path),
                    "--no-dim",
                    "--yes",
                    "--save-as",
                    str(save_as),
                ),
                display=(
                    f"ai-sw-build {dirname}/spec.json --no-dim --yes "
                    f"--save-as demo_out/{part_name}.SLDPRT"
                ),
            )
        )
        steps.append(
            DemoStep(
                id=f"observe_bbox_{slug}",
                title=f"Observe bounding box: {part_name}",
                argv=_module_argv("ai_sw_bridge.cli.observe", "bounding_box"),
                display="ai-sw-observe bounding_box",
                capture_json=True,
                allow_failure=True,
            )
        )
    steps.extend(mutate_beat_steps(env))
    return steps


def _assembly_steps(env: BuildEnv) -> list[DemoStep]:
    return []


def _observe_steps(env: BuildEnv) -> list[DemoStep]:
    return []


def _drawing_steps(env: BuildEnv) -> list[DemoStep]:
    return []


def _export_steps(env: BuildEnv) -> list[DemoStep]:
    return []


CHAPTERS: dict[str, Chapter] = {
    "tour": Chapter(
        key="tour",
        title="Capability tour",
        caption="Introspect the current build surface: --list-kinds, CLI commands, observe tools.",
        build_steps=_tour_steps,
    ),
    "part": Chapter(
        key="part",
        title="Part build",
        caption=(
            "Build the demo widget's three parts, then change one number and "
            "the model rebuilds -- that's the whole point (--no-dim strips the "
            "in-file equation link, but the *_locals.txt file still drives the "
            "rebuild)."
        ),
        build_steps=_part_steps,
    ),
    "assembly": Chapter(
        key="assembly",
        title="Assembly",
        caption="Place parts and add mates to assemble the demo widget (stub; filled in a later task).",
        build_steps=_assembly_steps,
    ),
    "observe": Chapter(
        key="observe",
        title="Observe",
        caption="Read back geometry, mass properties, and feature stats (stub; filled in a later task).",
        build_steps=_observe_steps,
    ),
    "drawing": Chapter(
        key="drawing",
        title="Drawing",
        caption="Generate a drawing view of the assembled widget (stub; filled in a later task).",
        build_steps=_drawing_steps,
    ),
    "export": Chapter(
        key="export",
        title="Export",
        caption="Export the finished assembly to a neutral format (stub; filled in a later task).",
        build_steps=_export_steps,
    ),
}


def chapter_order() -> list[str]:
    return ["tour", "part", "assembly", "observe", "drawing", "export"]


def select_chapters(name: str) -> list[str]:
    if name == "all":
        return chapter_order()
    if name in CHAPTERS:
        return [name]
    valid = ", ".join(chapter_order() + ["all"])
    raise SystemExit(f"unknown chapter {name!r}; valid choices: {valid}")


def wipe_demo_out(demo_out: Path) -> None:
    shutil.rmtree(demo_out, ignore_errors=True)
    demo_out.mkdir(parents=True, exist_ok=True)


def _run_tour(env: BuildEnv, *, sleep_s: float, compact: bool) -> int:
    steps = CHAPTERS["tour"].build_steps(env)
    list_step = next(step for step in steps if step.id == "list_kinds")
    rc, list_payload = run_step(
        list_step,
        cwd=env.repo_root,
        env=_command_env(env.repo_root),
        sleep_s=sleep_s,
    )
    if rc:
        print("capability tour failed: --list-kinds returned nonzero", file=sys.stderr)
        return rc
    if list_payload is None:
        print("could not read build surface payload", file=sys.stderr)
        return 2

    cli_commands = parse_project_scripts(env.repo_root / "pyproject.toml")
    observe_tools = parse_observe_tools(
        env.repo_root / "src" / "ai_sw_bridge" / "cli" / "observe.py"
    )
    sections: list[CapabilitySection] = build_capability_sections(
        list_payload,
        cli_commands,
        observe_tools,
        compact=compact,
    )
    _print_capability_tour(sections)
    print(DEFERRED_SIGNPOST)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="demo_full_system",
        description=(
            "Chaptered full-system demo: part -> assembly -> observe -> "
            "drawing -> export."
        ),
    )
    parser.add_argument(
        "--chapter",
        default="all",
        choices=chapter_order() + ["all"],
        help="Chapter to run. Defaults to all (runs tour first, then the rest in order).",
    )
    parser.add_argument(
        "--list-chapters",
        action="store_true",
        help="Print the available chapters and their captions, then exit.",
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
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Use a GIF-friendly capability summary instead of full function lists.",
    )
    parser.add_argument(
        "--tour-only",
        action="store_true",
        help="Run only the capability tour, then stop.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run only no-SW-safe steps, then stop before any live SOLIDWORKS work.",
    )
    args = parser.parse_args(argv)

    if args.list_chapters:
        _print_header("Available chapters")
        for key in chapter_order():
            chapter = CHAPTERS[key]
            print(f"  {chapter.key:10s} {chapter.caption}")
        return 0

    repo_root = repo_root_from_script()
    env = BuildEnv(
        repo_root=repo_root,
        demo_out=repo_root / "demo_out",
        widget_dir=repo_root / "examples" / "demo_widget",
    )
    wipe_demo_out(env.demo_out)
    _print_header("ai-sw-bridge full-system demo")

    selected = select_chapters(args.chapter)

    rc = _run_tour(env, sleep_s=args.sleep, compact=args.compact)
    if rc:
        return rc
    if args.tour_only:
        return 0

    remaining = [key for key in selected if key != "tour"]
    if args.preflight_only:
        # No-SW "plan" view: construct each remaining chapter's steps (pure,
        # no filesystem/SW touch) and print what would run, without running
        # any of it. Chapters that are still empty stubs contribute nothing.
        for key in remaining:
            chapter = CHAPTERS[key]
            steps = chapter.build_steps(env)
            if not steps:
                continue
            _print_header(f"Preflight plan: {chapter.title}")
            print(chapter.caption)
            for step in steps:
                print(f"  $ {step.display}")
        return 0

    for key in remaining:
        chapter = CHAPTERS[key]
        steps = chapter.build_steps(env)
        if not steps:
            continue
        _pause(f"Starting chapter: {chapter.title}", args.no_pause)
        print(chapter.caption)
        for step in steps:
            rc, _payload = run_step(
                step,
                cwd=env.repo_root,
                env=_command_env(env.repo_root),
                sleep_s=args.sleep,
            )
            if rc:
                return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
