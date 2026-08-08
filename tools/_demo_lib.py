"""Shared runner helpers for the ai-sw-bridge demo tooling.

This module holds the capability-introspection and step-runner primitives
that are common to the single-part no-dim showcase and (in later tasks) the
full-system chaptered demo. It has no CLI of its own.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SPEC_TYPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Sketches",
        (
            "sketch_rectangle_on_plane",
            "sketch_rectangle_on_face",
            "sketch_circle_on_plane",
            "sketch_circle_on_face",
            "sketch_circles_on_face",
            "sketch_line",
            "sketch_arc",
            "sketch_spline",
            "sketch_slot",
            "sketch_polygon",
            "sketch_ellipse",
            "sketch_text",
            "sketch_3d_sketch",
        ),
    ),
    (
        "Boss/extrude/cut/revolve",
        (
            "boss_extrude_blind",
            "boss_extrude_midplane",
            "boss_extrude_through_all",
            "boss_extrude_two_direction",
            "boss_extrude_up_to_surface",
            "cut_extrude_blind",
            "cut_extrude_midplane",
            "cut_extrude_through_all",
            "cut_extrude_two_direction",
            "revolve_boss",
            "revolve_cut",
        ),
    ),
    (
        "Modify",
        ("fillet_constant_radius", "chamfer_edge", "simple_hole"),
    ),
    ("Patterns", ("linear_pattern", "circular_pattern", "mirror_feature")),
)

FEATURE_ADD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Dress-up",
        (
            "fillet_constant_radius",
            "fillet_face",
            "variable_radius_fillet",
            "chamfer",
            "shell",
            "draft",
        ),
    ),
    (
        "Patterns",
        (
            "linear_pattern",
            "circular_pattern",
            "mirror_feature",
            "sketch_driven_pattern",
        ),
    ),
    (
        "Reference geometry",
        (
            "ref_plane",
            "ref_axis",
            "ref_point",
            "coordinate_system",
            "bounding_box",
            "com_point",
            "mate_reference",
        ),
    ),
    (
        "Curves",
        (
            "composite",
            "helix",
            "spiral",
            "project_curve",
            "curve_through_xyz",
        ),
    ),
    ("Surfaces", ("planar_surface", "offset_surface", "knit")),
    ("Sheet metal", ("base_flange", "hem", "sketched_bend")),
    ("Sweeps and shapes", ("sweep", "sweep_cut", "dome", "wizard_hole")),
    ("Bodies and boolean", ("delete_body", "intersect", "scale")),
    ("Weldment", ("structural_weldment",)),
)

CLI_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Build and edit",
        (
            "ai-sw-build",
            "ai-sw-batch",
            "ai-sw-mutate",
            "ai-sw-sketch-edit",
            "ai-sw-sketch-relations",
        ),
    ),
    (
        "Inspect and diagnose",
        (
            "ai-sw-probe",
            "ai-sw-doctor",
            "ai-sw-observe",
            "ai-sw-apidoc",
            "ai-sw-memory",
            "ai-sw-history",
            "ai-sw-checkpoint",
        ),
    ),
    (
        "Assemblies, drawings, and properties",
        ("ai-sw-assembly", "ai-sw-drawing", "ai-sw-properties"),
    ),
    (
        "Import, export, motion, and variants",
        (
            "ai-sw-configurations",
            "ai-sw-import",
            "ai-sw-export-dxf-flat",
            "ai-sw-motion",
            "ai-sw-solver",
            "ai-sw-urdf",
            "ai-sw-codegen",
            "ai-sw-mcp",
        ),
    ),
)


@dataclass(frozen=True)
class CapabilitySection:
    title: str
    items: list[str]


@dataclass(frozen=True)
class DemoStep:
    id: str
    title: str
    argv: list[str]
    display: str
    capture_json: bool = False
    allow_failure: bool = False


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _strip_toml_key(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def parse_project_scripts(pyproject_path: Path) -> list[str]:
    """Return sorted ``ai-sw-*`` entry points from pyproject.toml.

    This small parser avoids a TOML dependency so the tool works on Python 3.10
    without importing project runtime packages.
    """
    commands: list[str] = []
    in_scripts = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_scripts = stripped == "[project.scripts]"
            continue
        if not in_scripts or "=" not in stripped:
            continue
        key = _strip_toml_key(stripped.split("=", 1)[0])
        if key.startswith("ai-sw-"):
            commands.append(key)
    return sorted(commands)


def parse_observe_tools(observe_py_path: Path) -> list[str]:
    """Read the ``ai-sw-observe`` subcommand list from its module docstring."""
    tools: list[str] = []
    in_subcommands = False
    pattern = re.compile(r"\s+([a-zA-Z0-9_]+)\s+->")
    for line in observe_py_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "Subcommands:":
            in_subcommands = True
            continue
        if in_subcommands and line.startswith("Each subcommand"):
            break
        if not in_subcommands:
            continue
        match = pattern.match(line)
        if match:
            tools.append(match.group(1))
    return tools


def _grouped_lines(
    all_items: list[str], groups: tuple[tuple[str, tuple[str, ...]], ...]
) -> list[str]:
    remaining = set(all_items)
    lines: list[str] = []
    for label, names in groups:
        present = [name for name in names if name in remaining]
        if not present:
            continue
        lines.append(f"{label}: {', '.join(present)}")
        remaining.difference_update(present)
    if remaining:
        lines.append(f"Other supported: {', '.join(sorted(remaining))}")
    return lines


def _compact_group_summary(
    total: int,
    noun: str,
    all_items: list[str],
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    present_groups = [
        label for label, names in groups if any(name in all_items for name in names)
    ]
    if len(present_groups) > 5:
        group_text = ", ".join(present_groups[:5]) + ", and more"
    else:
        group_text = ", ".join(present_groups)
    return f"{total} {noun} across {group_text}"


def build_capability_sections(
    list_kinds_payload: dict[str, Any],
    cli_commands: list[str],
    observe_tools: list[str],
    compact: bool = False,
) -> list[CapabilitySection]:
    spec_types = sorted(str(x) for x in list_kinds_payload["spec_feature_types"])
    feature_add = sorted(str(x) for x in list_kinds_payload["feature_add_kinds"])
    if compact:
        return [
            CapabilitySection(
                "Capability counts",
                [
                    _compact_group_summary(
                        len(spec_types),
                        "part-spec functions",
                        spec_types,
                        SPEC_TYPE_GROUPS,
                    ),
                    _compact_group_summary(
                        len(feature_add),
                        "feature-add functions",
                        feature_add,
                        FEATURE_ADD_GROUPS,
                    ),
                    f"{len(observe_tools)} observe functions for read-back and DFM",
                    f"{len(cli_commands)} CLI/MCP commands for build, observe, assembly, drawing, export, and automation",
                ],
            )
        ]
    return [
        CapabilitySection(
            f"Part spec feature functions ({len(spec_types)})",
            _grouped_lines(spec_types, SPEC_TYPE_GROUPS),
        ),
        CapabilitySection(
            f"Feature-add functions ({len(feature_add)})",
            _grouped_lines(feature_add, FEATURE_ADD_GROUPS),
        ),
        CapabilitySection(
            f"Read-only observe functions ({len(observe_tools)})",
            [", ".join(observe_tools)],
        ),
        CapabilitySection(
            f"CLI/MCP command surface ({len(cli_commands)})",
            _grouped_lines(cli_commands, CLI_GROUPS),
        ),
    ]


def _module_argv(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def _spec_arg(spec_path: Path) -> str:
    return str(spec_path)


def _command_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else src_path + os.pathsep + existing
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _print_wrapped(prefix: str, text: str, width: int = 96) -> None:
    wrapper = textwrap.TextWrapper(
        width=width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )
    print(wrapper.fill(text))


def _print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_capability_tour(sections: list[CapabilitySection]) -> None:
    _print_header("Current supported capability surface")
    for section in sections:
        print()
        print(section.title)
        print("-" * len(section.title))
        for item in section.items:
            _print_wrapped("  - ", item)


def _print_dry_run_summary(payload: dict[str, Any]) -> None:
    dry_run = payload.get("dry_run", payload)
    features = dry_run.get("features", [])
    print()
    print("Preflight result")
    print("----------------")
    print(f"  ok: {payload.get('ok')}")
    print(f"  lint findings: {payload.get('finding_count', 0)}")
    print(f"  spec: {dry_run.get('spec_name')}")
    print(f"  planned features: {dry_run.get('feature_count')}")
    print(f"  locals resolved: {dry_run.get('locals_resolved')}")
    if features:
        order = " -> ".join(str(f.get("name")) for f in features)
        _print_wrapped("  order: ", order)


def _print_json_summary(step: DemoStep, payload: dict[str, Any]) -> None:
    if step.id == "dry_run":
        _print_dry_run_summary(payload)
        return
    if step.id == "list_kinds":
        print(
            "  build surface probe ok: "
            f"{payload.get('ok')} "
            f"({payload.get('spec_feature_type_count')} spec functions, "
            f"{payload.get('feature_add_kind_count')} feature-add functions)"
        )
        return
    print(json.dumps(payload, indent=2))


def run_step(
    step: DemoStep,
    *,
    cwd: Path,
    env: dict[str, str],
    sleep_s: float,
) -> tuple[int, dict[str, Any] | None]:
    _print_header(step.title)
    print(f"$ {step.display}")
    time.sleep(sleep_s)

    if step.capture_json:
        completed = subprocess.run(
            step.argv,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.stderr:
            print(completed.stderr.rstrip(), file=sys.stderr)
        payload: dict[str, Any] | None = None
        if completed.stdout.strip():
            try:
                payload = json.loads(completed.stdout)
                _print_json_summary(step, payload)
            except json.JSONDecodeError:
                print(completed.stdout.rstrip())
        if completed.returncode and not step.allow_failure:
            return completed.returncode, payload
        return 0, payload

    completed = subprocess.run(
        step.argv,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode and not step.allow_failure:
        return completed.returncode, None
    return 0, None


def _pause(message: str, no_pause: bool) -> None:
    print()
    print(message)
    if no_pause:
        return
    input("Press Enter to continue...")
