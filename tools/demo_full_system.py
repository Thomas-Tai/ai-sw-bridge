#!/usr/bin/env python3
"""Chaptered full-system demo: tour -> part -> assembly -> observe -> drawing -> export.

The script is a thin orchestrator around the public CLIs, in the same spirit
as ``tools/demo_no_dim_showcase.py``. It is organized into six named
chapters -- ``tour``, ``part``, ``assembly``, ``observe``, ``drawing``, and
``export`` -- so an operator (or a recording session) can run the whole tour
(``--chapter all``) or a single chapter (``--chapter <name>``). All six
chapters are wired to real steps.

``tour`` (pure introspection) and ``--preflight-only`` (construct and print
every remaining chapter's planned steps without running them) are the only
no-SW paths -- they never touch a live SOLIDWORKS session. Every other
chapter's live build/observe/assembly/drawing/export steps need a live
SOLIDWORKS seat; see ``docs/demo_full_system.md`` for the seat-gate note and
the exact per-chapter commands. Two chapters carry a flag-gated identity:
``assembly``'s and ``export``'s title/caption reflect whether the underlying
capability (mates, the schema-v2 export block) has been spike-confirmed on a
live seat (``BuildEnv.mates_proven`` / ``BuildEnv.export_block_wired``);
until then each runs an honest, narrower fallback beat instead of failing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

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
    # Seat-confirmed feasibility flags (Task 9 spikes, 2026-08-11): each gates
    # which real beat a chapter airs. Defaults reflect what the live seat proved
    # against THIS repo state.
    # - mates_proven: Spike 0 authored a concentric mate out-of-process
    #   (mate_count=1, interference=0) via ai-sw-assembly.
    # - export_block_wired: Spike E + the export-stage CLI-wiring fix -- a
    #   schema-v2 export: block now emits STEP/STL/3MF from ai-sw-build.
    # - mutate_drives_nodim: FALSE by design -- --no-dim strips the locals link
    #   ai-sw-mutate needs, so the mutate chapter airs the reparam fallback.
    mates_proven: bool = True
    export_block_wired: bool = True
    mutate_drives_nodim: bool = False


@dataclass(frozen=True)
class Chapter:
    key: str
    title: str
    caption: str
    build_steps: Callable[[BuildEnv], list[DemoStep]]
    # Set only for chapters whose on-screen identity depends on a BuildEnv
    # flag (currently just ``assembly``, gated on ``mates_proven``). Static
    # chapters leave these None and fall back to the fixed title/caption.
    title_fn: Callable[[BuildEnv], str] | None = None
    caption_fn: Callable[[BuildEnv], str] | None = None

    def title_for(self, env: BuildEnv) -> str:
        return self.title_fn(env) if self.title_fn is not None else self.title

    def caption_for(self, env: BuildEnv) -> str:
        return self.caption_fn(env) if self.caption_fn is not None else self.caption


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
# runs (both target its BLOCK_W).
_PART_SPECS: tuple[tuple[str, str, str], ...] = (
    ("baseplate", "demo_baseplate", "DemoBaseplate"),
    ("shaft", "demo_shaft", "DemoShaft"),
    ("bearing_block", "demo_bearing_block", "DemoBearingBlock"),
)

# The variable the mutate/reparam beat resizes, and its new value. Both
# branches of mutate_beat_steps() target this so the on-screen narrative
# ("widen the housing") is identical regardless of which beat is live-valid.
#
# BLOCK_W, not BORE_DIA: the bearing block's CHA_BoreLeadIn chamfer selects the
# bore's top rim by a LITERAL point (8.0, 0, 15) pinned to the original bore
# radius. Changing BORE_DIA moves that edge out from under the selector, so the
# rebuild fails ("edge matches no edge within 1um"). BLOCK_W widens the housing
# without touching the bore rim or the top face, so every feature -- including
# the literal-selected chamfer -- survives. Verified on a live seat 2026-08-11
# (BLOCK_W 40->56: bbox dx 40->56, feature_errors issues:[]).
_MUTATE_VAR = "BLOCK_W"
_MUTATE_NEW_VALUE = "56.0"

# Body of the fallback beat's runtime reparam step: copies the bearing
# block's spec + locals into a demo_out/ scratch copy and bumps BLOCK_W in
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
    """The headline "widen the housing and rebuild" beat.

    Two mutually exclusive branches, selected by ``env.mutate_drives_nodim``:

    * Primary (``True``): drive the change through ``ai-sw-mutate``'s
      propose -> dry_run -> commit workflow against the live-built bearing
      block. Spike M (2026-08-11) determined ``ai-sw-mutate`` CANNOT drive a
      ``--no-dim``-built part: ``--no-dim`` strips the equation link to
      locals.txt, and mutate routes every change through that linked file, so
      the propose fails ("no linked locals file"). This branch is therefore
      pinned inert (mutate_drives_nodim stays False) and kept only to document
      the mechanism.
    * Fallback (``False``, the default and the live path): copy the bearing
      block's spec+locals into ``demo_out/reparam/``, bump ``BLOCK_W`` in the
      copy, and rebuild with ``--no-dim --yes --save-as``. This never touches
      the committed ``examples/`` locals.
    """
    if env.mutate_drives_nodim:
        return [
            DemoStep(
                id="mutate_propose",
                title="Propose: widen the housing",
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
            # <proposal-id> is a placeholder that main()'s seat-phase
            # proposal_id threading substitutes from mutate_propose's JSON
            # stdout (see _substitute_proposal_id). This whole branch is inert
            # anyway (Spike M: mutate cannot drive a --no-dim part), so it
            # never actually runs -- the reparam fallback below is the live
            # path. Kept as a documented reference to the propose/dry_run/
            # commit shape.
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
            title=f"Reparam: bump {_MUTATE_VAR} in a demo_out/ copy",
            argv=[sys.executable, "-c", reparam_script],
            display=(
                f'python -c "<copy demo_bearing_block, {_MUTATE_VAR} -> '
                f'{_MUTATE_NEW_VALUE} in demo_out/reparam/>"'
            ),
        ),
        DemoStep(
            id="reparam_build",
            title="Rebuild the bearing block at the wider width",
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
    # Build-tree statistics belong on a PART: ai-sw-observe feature_statistics
    # returns None on an assembly ("FeatureStatistics returned None / unsupported
    # doc"), so this read lives here (reading the just-rebuilt bearing block that
    # the reparam step left active) rather than in the assembly-scoped observe
    # chapter.
    steps.append(
        DemoStep(
            id="observe_part_feature_statistics",
            title="Build-tree statistics for the rebuilt part",
            argv=_module_argv("ai_sw_bridge.cli.observe", "feature_statistics"),
            display="ai-sw-observe feature_statistics",
            capture_json=True,
            allow_failure=True,
        )
    )
    return steps


# The mate block injected into assembly.resolved.json when env.mates_proven
# is True: the shaft is concentric-mated into BOTH bearing bores
# (shaft<->block_pos and shaft<->block_neg), seating it through both coaxial
# bores -- the functional "real mates, not fixed coordinates" beat. The two
# bearing blocks and the base plate are placed by their assembly.json
# transforms (fixed housings); only the shaft is mated.
# Schema-valid against assembly/schema.py (MATE_SCHEMA / MATE_REF_SCHEMA).
# ``is_cylinder`` matches the FIRST cylindrical face on the component body
# (assembly/face_resolver.py); verified live 2026-08-13 that this resolves to
# each block's Ø16 bore (radius 8mm, local +Z axis), so both concentrics bind
# the shaft to the bore axis. mate_count:2.
#
# ROOT-CAUSE HISTORY (fixed 2026-08-13): the earlier scheme paired the shaft
# concentric with a ``coincident`` block_pos<->base on the block's local -Z
# face. That -Z face is a bore END-CAP, so mating it flat onto the plate stood
# block_pos upright and pointed its bore straight UP (world +Z) -- silently
# overriding the rpy[0,90,0] transform that makes the bore horizontal.
# block_neg (unmated) kept its horizontal bore, so the two bores ended up
# PERPENDICULAR and the shaft seated vertically into the flipped bore, floating
# clear of the plate. Both mates still reported status "ok" (each is
# individually satisfiable) and interference was 0, so nothing flagged it --
# but the "shaft seated through both bores" narrative was false. Fix: drop the
# block coincident; concentric the shaft into both bores. Verified live
# 2026-08-13 (scratch fix_v6): shaft spans x=[-45,45] through both Ø16 bores,
# interference 0. The shaft's axial position comes from its assembly.json
# transform (shaft xyz [0,0,20]); the commit's solve lands it centered.
_ASSEMBLY_MATES: list[dict[str, Any]] = [
    {
        "type": "concentric",
        "a": {"component": "shaft", "face_ref": {"is_cylinder": True}},
        "b": {"component": "block_pos", "face_ref": {"is_cylinder": True}},
    },
    {
        "type": "concentric",
        "a": {"component": "shaft", "face_ref": {"is_cylinder": True}},
        "b": {"component": "block_neg", "face_ref": {"is_cylinder": True}},
    },
]


def _assembly_prep_script(env: BuildEnv, mates_proven: bool) -> str:
    """Body of the assembly_prep runtime step.

    Reads the *committed* examples/demo_widget/assembly.json (Task 3;
    never mutated), rewrites each component's ``part`` from the committed
    ``demo_out/<Part>.SLDPRT`` relative path to the ABSOLUTE path under
    ``env.demo_out`` (where the ``part`` chapter actually built it), and
    swaps in ``_ASSEMBLY_MATES`` when ``mates_proven`` -- else leaves
    ``mates: []`` as committed. Writes demo_out/assembly.resolved.json.

    Built via plain string concatenation, not ``str.format``: the mates
    JSON payload contains literal ``{``/``}`` characters that would collide
    with format-string placeholder syntax. The mates list is embedded as a
    JSON string literal and re-parsed with ``json.loads`` at runtime (not
    spliced in as Python source), since JSON ``true``/``false`` are not
    valid Python literals. Pure string building -- no filesystem I/O
    happens until this text is executed as a subprocess by run_step.
    """
    mates = _ASSEMBLY_MATES if mates_proven else []
    mates_json = json.dumps(mates)
    src = (env.widget_dir / "assembly.json").as_posix()
    dst = (env.demo_out / "assembly.resolved.json").as_posix()
    demo_out = env.demo_out.as_posix()
    return (
        "import json, pathlib\n"
        f'src = pathlib.Path("{src}")\n'
        f'dst = pathlib.Path("{dst}")\n'
        f'demo_out = pathlib.Path("{demo_out}")\n'
        "data = json.loads(src.read_text(encoding='utf-8'))\n"
        "for comp in data.get('components', []):\n"
        "    part = comp.get('part')\n"
        "    if part:\n"
        # NATIVE str(), NOT as_posix(): the assembly handler pre-opens each
        # part with OpenDoc6 and then AddComponent4 matches it by its EXACT
        # registered path, which SOLIDWORKS normalizes to backslashes on
        # Windows. A forward-slash (as_posix) path never matches, so
        # AddComponent4 returns None ("component 'base': AddComponent4
        # returned None"). str(WindowsPath) yields backslashes. (Spike 0 /
        # rehearsal 2026-08-11.)
        "        comp['part'] = str(demo_out / pathlib.Path(part).name)\n"
        f"data['mates'] = json.loads('''{mates_json}''')\n"
        "dst.write_text(json.dumps(data, indent=2), encoding='utf-8')\n"
        "print('assembly resolved ->', dst)\n"
    )


def _assembly_title(env: BuildEnv) -> str:
    if env.mates_proven:
        return "assembly (with mates)"
    return "component placement / layout"


def _assembly_caption(env: BuildEnv) -> str:
    if env.mates_proven:
        return (
            "Concentric mates seat the shaft through both bearing bores; "
            "interference is a build gate."
        )
    return "Transform-only placement (mates seat-unproven -- see Spike 0)."


def _assembly_steps(env: BuildEnv) -> list[DemoStep]:
    # Assumes the 3 parts already exist in demo_out/ (built by the `part`
    # chapter). Do NOT rebuild them here -- rebuilding would clobber the
    # mutate beat's reparam output. `--chapter assembly` run standalone
    # expects a prior part build; the recording always runs `--chapter all`.
    #
    # There is no `mirror`/`exploded` verb on ai-sw-assembly (see
    # cli/assembly.py: propose/dry_run/commit/edit only). component_patterns
    # (mirror) and exploded_views are spec-level constructs (assembly/
    # schema.py), not CLI steps -- and assembly.json (Task 3) already places
    # both block_pos and block_neg explicitly, so there's nothing to mirror.
    # Both are deferred spec-level features, not omitted by oversight.
    resolved = env.demo_out / "assembly.resolved.json"
    return [
        DemoStep(
            id="assembly_prep",
            title="Resolve assembly.json part paths (+ mates if proven)",
            argv=[
                sys.executable,
                "-c",
                _assembly_prep_script(env, env.mates_proven),
            ],
            display=(
                'python -c "<resolve examples/demo_widget/assembly.json '
                "part paths -> demo_out/, mates="
                f'{env.mates_proven} -> demo_out/assembly.resolved.json>"'
            ),
        ),
        # propose -> dry_run -> commit must run back-to-back with no idle
        # gap at seat time -- proposals expire across pauses (the
        # reference_sw_bridge_assembly lesson: propose returns a
        # proposal_id that dry_run/commit must consume before it lapses).
        DemoStep(
            id="assembly_propose",
            title="Propose: validate the assembly spec offline",
            argv=_module_argv(
                "ai_sw_bridge.cli.assembly",
                "propose",
                "--spec",
                str(resolved),
            ),
            display=f"ai-sw-assembly propose --spec {resolved}",
            capture_json=True,
        ),
        # <proposal-id> is a placeholder: assembly_propose emits the real
        # proposal_id in its JSON stdout, and main()'s seat-phase loop
        # captures it and substitutes it here before dry_run/commit run (see
        # _substitute_proposal_id). The three steps run back-to-back within
        # the chapter (no _pause between them) so the proposal is consumed
        # before it lapses.
        DemoStep(
            id="assembly_dry_run",
            title="Dry-run: resolve parts, bind mate faces",
            argv=_module_argv(
                "ai_sw_bridge.cli.assembly",
                "dry_run",
                "--proposal-id",
                "<proposal-id>",
            ),
            display="ai-sw-assembly dry_run --proposal-id <proposal-id>",
        ),
        DemoStep(
            id="assembly_commit",
            title="Commit: place components, create mates, save",
            argv=_module_argv(
                "ai_sw_bridge.cli.assembly",
                "commit",
                "--proposal-id",
                "<proposal-id>",
                "--out",
                str(env.demo_out / "DemoWidget.SLDASM"),
            ),
            display=(
                "ai-sw-assembly commit --proposal-id <proposal-id> --out "
                "demo_out/DemoWidget.SLDASM"
            ),
        ),
    ]


def _observe_open_assembly_script(env: BuildEnv) -> str:
    """Body of the observe chapter's opener step: (re-)open + activate the
    committed DemoWidget.SLDASM so the read-only observe tools inspect the
    ASSEMBLY, not whichever component part happened to stay active.

    An assembly commit does NOT leave the assembly as the active document for
    a separate observe *process* -- each observe step is its own subprocess
    that attaches to the running SW and reads ActiveDoc. Without this opener,
    interference / mate_errors / screenshot would all read the wrong doc
    (observed live 2026-08-11: mate_count:0). OpenDoc6 on an already-open doc
    returns it and makes it active.

    The opener then SETTLES before exiting: OpenDoc6 activates the doc, but
    after a fresh commit with several component docs still open, SW can take a
    beat to finalize ActiveDoc. Because the next observe step is a separate
    process that immediately reads sw.ActiveDoc, a zero-gap handoff can race
    and read `no_active_doc` (seen live in a full `--sleep 0` e2e run,
    2026-08-11, even though the same opener passes in isolation). Confirming
    ActiveDoc here (while this process still holds the seat) plus a short final
    pause closes that window regardless of the demo's global `--sleep`.

    The path is embedded as a forward-slash literal and converted to a native
    (backslash) path with str() at runtime, matching SW's registered path
    form. Pure string building; no COM happens until run_step executes this as
    a subprocess.
    """
    asm = (env.demo_out / "DemoWidget.SLDASM").as_posix()
    return (
        "import pathlib, time\n"
        "from ai_sw_bridge.com.earlybind import typed\n"
        "from ai_sw_bridge.com.sw_type_info import wrapper_module\n"
        "from ai_sw_bridge.sw_com import get_sw_app\n"
        f'asm = str(pathlib.Path("{asm}"))\n'
        "sw = get_sw_app()\n"
        "tsw = typed(sw, 'ISldWorks', module=wrapper_module())\n"
        "opened = tsw.OpenDoc6(asm, 2, 0, '', 0, 0)\n"  # 2 = swDocASSEMBLY
        "doc = opened[0] if isinstance(opened, tuple) else opened\n"
        # Settle so the next (separate) observe process never races in on a
        # not-yet-finalized ActiveDoc -- see the docstring.
        "for _ in range(20):\n"
        "    if sw.ActiveDoc is not None:\n"
        "        break\n"
        "    time.sleep(0.25)\n"
        "time.sleep(0.75)\n"
        "print('observe target open+active:' if doc is not None "
        "else 'OpenDoc6 returned None for:', asm)\n"
    )


def _observe_steps(env: BuildEnv) -> list[DemoStep]:
    # The weighted chapter -- real DFM read-back (interference + mate health)
    # against the committed assembly is the most credible content in the whole
    # tour, so the recording gives it extra header/pause room versus the other
    # chapters (a delivery choice, not a code mechanism: every step here
    # already gets its own _print_header + sleep via run_step). Build-tree
    # statistics live in the part chapter (feature_statistics is part-only).
    #
    # The opener step MUST run first: an assembly commit leaves the assembly
    # non-active for a separate observe process, so without it every observe
    # below would inspect the wrong doc (see _observe_open_assembly_script).
    return [
        DemoStep(
            id="observe_open_assembly",
            title="Open the assembled widget for inspection",
            argv=[sys.executable, "-c", _observe_open_assembly_script(env)],
            display='python -c "<open+activate demo_out/DemoWidget.SLDASM>"',
            allow_failure=True,
        ),
        DemoStep(
            id="observe_interference",
            title="DFM headline: interference detection (expect 0)",
            argv=_module_argv("ai_sw_bridge.cli.observe", "interference"),
            display="ai-sw-observe interference",
            capture_json=True,
            allow_failure=True,
        ),
        DemoStep(
            id="observe_mate_errors",
            title="Mate health (most meaningful once mates are proven)",
            argv=_module_argv("ai_sw_bridge.cli.observe", "mate_errors"),
            display="ai-sw-observe mate_errors",
            capture_json=True,
            allow_failure=True,
        ),
        DemoStep(
            id="observe_screenshot",
            title="Capture the assembled widget",
            argv=_module_argv(
                "ai_sw_bridge.cli.observe",
                "screenshot",
                "--filename",
                "demo_widget.png",
            ),
            display="ai-sw-observe screenshot --filename demo_widget.png",
            capture_json=True,
            allow_failure=True,
        ),
    ]


def _drawing_prep_script(env: BuildEnv) -> str:
    """Body of the drawing_prep runtime step.

    Authors a minimal standalone drawing spec (schema: drawing/
    spec_schema.py) at demo_out/drawing.json -- Task 3 only produced an
    assembly spec, and committed spec files may not be created for this
    task, so it's authored at runtime instead. Legacy single-sheet mode:
    top-level ``views[]``, ``dimensions: true`` (model dims, no tolerance),
    ``bom: true``. Pure string building -- the write happens only when this
    text is executed as a subprocess by run_step.
    """
    model = (env.demo_out / "DemoWidget.SLDASM").as_posix()
    dst = (env.demo_out / "drawing.json").as_posix()
    spec = {
        "kind": "drawing",
        "name": "DemoWidgetDrawing",
        "model": model,
        "views": ["front", "top", "right", "isometric"],
        "dimensions": True,
        "bom": True,
    }
    spec_json = json.dumps(spec, indent=2)
    return (
        "import pathlib\n"
        f'dst = pathlib.Path("{dst}")\n'
        f"dst.write_text('''{spec_json}''', encoding='utf-8')\n"
        "print('drawing spec written ->', dst)\n"
    )


def _drawing_steps(env: BuildEnv) -> list[DemoStep]:
    resolved = env.demo_out / "drawing.json"
    return [
        DemoStep(
            id="drawing_prep",
            title="Author a standalone drawing spec for the assembly",
            argv=[sys.executable, "-c", _drawing_prep_script(env)],
            display='python -c "<write demo_out/drawing.json>"',
        ),
        DemoStep(
            id="drawing_propose",
            title="Propose: validate the drawing spec offline",
            argv=_module_argv(
                "ai_sw_bridge.cli.drawing",
                "propose",
                "--spec",
                str(resolved),
            ),
            display=f"ai-sw-drawing propose --spec {resolved}",
            capture_json=True,
        ),
        # <proposal-id> placeholder -- main()'s seat-phase loop substitutes
        # the real id captured from drawing_propose's JSON stdout before
        # these run (see _substitute_proposal_id), same as assembly above.
        DemoStep(
            id="drawing_dry_run",
            title="Dry-run: confirm the model file is openable",
            argv=_module_argv(
                "ai_sw_bridge.cli.drawing",
                "dry_run",
                "--proposal-id",
                "<proposal-id>",
            ),
            display="ai-sw-drawing dry_run --proposal-id <proposal-id>",
        ),
        DemoStep(
            id="drawing_commit",
            title="Commit: create views, save the .SLDDRW",
            argv=_module_argv(
                "ai_sw_bridge.cli.drawing",
                "commit",
                "--proposal-id",
                "<proposal-id>",
                "--out",
                str(env.demo_out / "DemoWidget.SLDDRW"),
            ),
            display=(
                "ai-sw-drawing commit --proposal-id <proposal-id> --out "
                "demo_out/DemoWidget.SLDDRW"
            ),
        ),
    ]


# Body of the wired branch's list_exports runtime step: globs demo_out/ for
# the artifacts export.json declares (STEP/STL/3MF) and prints whatever is
# found. Pure string building at construction time -- the glob only runs
# once this text is executed as a subprocess by run_step, after the export
# build step has actually written the files.
_LIST_EXPORTS_SCRIPT_TEMPLATE = """import pathlib
demo_out = pathlib.Path(r"{demo_out}")
patterns = ["*.step*", "*.stl", "*.3mf"]
found = []
for pattern in patterns:
    found.extend(sorted(demo_out.glob(pattern)))
if found:
    for path in found:
        print(path)
else:
    print("no export artifacts found in", demo_out)
"""


def _list_exports_script(env: BuildEnv) -> str:
    return _LIST_EXPORTS_SCRIPT_TEMPLATE.format(demo_out=env.demo_out.as_posix())


def _export_fallback_script(env: BuildEnv) -> str:
    """Body of the fallback branch's single reminder step.

    Prints a note pointing at the drawing chapter's output as this build's
    actual downstream artifact, and explains that STEP/STL/3MF ship via the
    spec export block but are seat-gated (Spike E has not confirmed live
    emission yet). Built via an f-string ``!r`` repr, not string
    concatenation, so the message is embedded as a single safely-escaped
    Python string literal in the generated ``python -c`` source -- no
    filesystem I/O happens until that source is executed as a subprocess.
    """
    drawing_out = (env.demo_out / "DemoWidget.SLDDRW").as_posix()
    message = (
        "The drawing (.SLDDRW) is the downstream artifact in this build (drawing "
        f"chapter output: {drawing_out}); STEP/STL/3MF ship via the spec "
        "export block (examples/demo_widget/export.json), seat-gated -- see "
        "docs/demo_full_system.md."
    )
    return f"print({message!r})\n"


def _export_caption(env: BuildEnv) -> str:
    if env.export_block_wired:
        return "One model, every downstream format."
    return (
        "The drawing (.SLDDRW) is the downstream artifact in this build; STEP/STL/3MF "
        "ship via the spec export block, seat-gated."
    )


def _export_steps(env: BuildEnv) -> list[DemoStep]:
    if env.export_block_wired:
        spec_path = env.widget_dir / "export.json"
        return [
            DemoStep(
                id="export_build",
                title="Build the schema-v2 export block (STEP + STL + 3MF)",
                argv=_module_argv(
                    "ai_sw_bridge.cli.build",
                    str(spec_path),
                    "--no-dim",
                    "--yes",
                ),
                display=(
                    "AI_SW_BRIDGE_FLAG_SCHEMA_V2=1 ai-sw-build "
                    "examples/demo_widget/export.json --no-dim --yes"
                ),
            ),
            DemoStep(
                id="list_exports",
                title="List the produced export artifacts",
                argv=[sys.executable, "-c", _list_exports_script(env)],
                display='python -c "<list demo_out/*.step*, *.stl, *.3mf>"',
                allow_failure=True,
            ),
        ]
    return [
        DemoStep(
            id="export_reminder",
            title="Downstream artifact: the drawing (.SLDDRW) (export block is seat-gated)",
            argv=[sys.executable, "-c", _export_fallback_script(env)],
            display=(
                'python -c "<note: the drawing (.SLDDRW) is the downstream artifact; '
                'STEP/STL/3MF ship via the spec export block, seat-gated>"'
            ),
        ),
    ]


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
        caption="Place parts (and mates, once proven) to assemble the demo widget.",
        build_steps=_assembly_steps,
        title_fn=_assembly_title,
        caption_fn=_assembly_caption,
    ),
    "observe": Chapter(
        key="observe",
        title="Observe",
        caption="DFM is a build gate, not a manual afterthought.",
        build_steps=_observe_steps,
    ),
    "drawing": Chapter(
        key="drawing",
        title="Drawing",
        caption="Drawing + BOM fall out of the same model.",
        build_steps=_drawing_steps,
    ),
    "export": Chapter(
        key="export",
        title="Export",
        caption=(
            "Export the finished model to neutral downstream formats "
            "(schema-v2 export block)."
        ),
        build_steps=_export_steps,
        caption_fn=_export_caption,
    ),
}


@dataclass(frozen=True)
class QuickstartStep:
    tier: str  # "A" (no SW) | "B" (needs a seat) | "next" (prose pointer)
    caption: str
    argv: (
        list[str] | None
    )  # doc-form tokens, e.g. ["python", "-m", "..."]; None = prose-only
    prose: str | None = None


# The single source of truth for both the ``--quickstart`` runnable mode and
# QUICKSTART.md. A test (test_quickstart_doc_commands_match_canonical_list)
# asserts every command this list renders is present verbatim in the doc, so
# the two can never drift apart.
QUICKSTART_STEPS: list[QuickstartStep] = [
    # Tier A -- no SOLIDWORKS needed.
    QuickstartStep(
        tier="A",
        caption="Install the package (one-time).",
        argv=["pip", "install", "-e", ".[dev]"],
    ),
    QuickstartStep(
        tier="A",
        caption="Environment health check -- no SOLIDWORKS seat needed.",
        argv=["python", "-m", "ai_sw_bridge.cli.doctor", "--no-seat"],
    ),
    QuickstartStep(
        tier="A",
        caption="See every supported feature/CLI kind.",
        argv=["python", "-m", "ai_sw_bridge.cli.build", "--list-kinds"],
    ),
    QuickstartStep(
        tier="A",
        caption="Validate + lint a real spec -- no SW needed.",
        argv=[
            "python",
            "-m",
            "ai_sw_bridge.cli.build",
            "examples/demo_widget/demo_baseplate/spec.json",
            "--dry-run",
            "--lint",
        ],
    ),
    # Tier B -- needs a live SOLIDWORKS seat.
    QuickstartStep(
        tier="B",
        caption="Build your first real part.",
        argv=[
            "python",
            "-m",
            "ai_sw_bridge.cli.build",
            "--demo",
            "--no-dim",
            "--yes",
        ],
    ),
    QuickstartStep(
        tier="B",
        caption="Read geometry back from the live model.",
        argv=["python", "-m", "ai_sw_bridge.cli.observe", "bounding_box"],
    ),
    # Next -- prose pointers (a couple double as real, non-executed commands).
    QuickstartStep(
        tier="next",
        caption="Edit and re-validate.",
        argv=None,
        prose=(
            "Edit any `examples/demo_widget/*/spec.json` and re-run the "
            "Tier-A dry-run to see your change validated."
        ),
    ),
    QuickstartStep(
        tier="next",
        caption="Run the full chaptered demo.",
        argv=["python", "tools/demo_full_system.py", "--chapter", "all"],
    ),
    QuickstartStep(
        tier="next",
        caption="Learn how each chapter is recorded.",
        argv=None,
        prose="Read `docs/demo_full_system.md` for how to record each chapter.",
    ),
]


def quickstart_command_lines(with_sw: bool = True) -> list[str]:
    """Render the canonical shell command lines, in order.

    This is the exact set QUICKSTART.md's fenced ``bash`` blocks are
    compared against (string-for-string) by the doc-sync test.
    """
    lines: list[str] = []
    for step in QUICKSTART_STEPS:
        if step.argv is None:
            continue
        if step.tier == "B" and not with_sw:
            continue
        lines.append(" ".join(step.argv))
    return lines


def quickstart_steps(env: BuildEnv, with_sw: bool) -> list[DemoStep]:
    """Build the EXECUTABLE steps for ``--quickstart``.

    Only ``python -m <module> ...`` steps are ever executed here. Tier A
    always runs; Tier B only when ``with_sw`` (seat-gated, exercised in a
    later task). The ``pip install`` prerequisite and every ``next`` pointer
    (including the ``--chapter all`` full-tour command) are never executed
    inside quickstart -- they are printed as instructions by ``main``.
    """
    steps: list[DemoStep] = []
    for index, step in enumerate(QUICKSTART_STEPS):
        if step.tier == "next":
            continue
        if step.tier == "B" and not with_sw:
            continue
        argv = step.argv
        if argv is None or len(argv) < 3 or argv[0] != "python" or argv[1] != "-m":
            # Not a "python -m <module>" invocation (e.g. ``pip install``):
            # printed as a prerequisite instruction instead, never executed.
            continue
        module, *rest = argv[2:]
        capture_json = "--list-kinds" in rest or "--dry-run" in rest
        steps.append(
            DemoStep(
                id=f"quickstart_{index}_{module.rsplit('.', 1)[-1]}",
                title=step.caption,
                argv=_module_argv(module, *rest),
                display=" ".join(step.argv),
                allow_failure=True,
                capture_json=capture_json,
            )
        )
    return steps


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


def _run_quickstart(
    env: BuildEnv, *, with_sw: bool, no_pause: bool, sleep_s: float
) -> int:
    """Walk QUICKSTART_STEPS: execute Tier A (and Tier B iff with_sw), print
    everything else (the pip-install prerequisite, an unrun Tier B, and the
    ``next`` pointers) as plain instructions. Never wipes demo_out -- the
    Tier-A steps write nothing, and a live Tier-B build manages its own
    output.
    """
    _print_header("Get running in 5 minutes")
    executable = quickstart_steps(env, with_sw=with_sw)
    by_index = {int(s.id.split("_")[1]): s for s in executable}
    env_dict = _command_env(env.repo_root)

    for index, step in enumerate(QUICKSTART_STEPS):
        demo_step = by_index.get(index)
        if step.tier in ("A", "B") and demo_step is not None:
            rc, _payload = run_step(
                demo_step, cwd=env.repo_root, env=env_dict, sleep_s=sleep_s
            )
            if rc:
                return rc
            continue
        if step.tier == "B" and not with_sw:
            print()
            print(f"[Tier B - needs a SOLIDWORKS seat] {step.caption}")
            print(f"  $ {' '.join(step.argv or [])}")
            print("  Run again with --quickstart --with-sw to execute this live.")
            continue
        if step.tier == "A":
            # The pip-install prerequisite: printed, never executed.
            print()
            print(f"[Prerequisite] {step.caption}")
            print(f"  $ {' '.join(step.argv or [])}")
            continue
        # step.tier == "next": prose pointer, optionally with a real command.
        print()
        print(f"[Next] {step.caption}")
        if step.prose:
            print(f"  {step.prose}")
        if step.argv is not None:
            print(f"  $ {' '.join(step.argv)}")

    _pause("Quickstart complete.", no_pause)
    return 0


# The literal token a propose->dry_run->commit chapter leaves in its dry_run
# and commit argv. main()'s seat-phase loop captures the real proposal_id from
# the propose step's JSON stdout and swaps it in before the dependent steps run
# (a proposal is consumed by dry_run/commit before it lapses -- steps within a
# chapter run back-to-back, with only the small inter-step sleep between them
# and no _pause, so the id is always fresh when substituted). Kept identical to
# the on-screen <proposal-id> the step display shows.
_PROPOSAL_ID_PLACEHOLDER = "<proposal-id>"


def _substitute_proposal_id(argv: list[str], proposal_id: str | None) -> list[str]:
    """Return ``argv`` with every ``<proposal-id>`` token replaced by
    ``proposal_id``.

    Returns the original list object unchanged when there is nothing to do (no
    captured id yet, or no placeholder present) so callers can cheaply detect a
    no-op with ``is``. Never mutates the input (DemoStep is frozen).
    """
    if not proposal_id or _PROPOSAL_ID_PLACEHOLDER not in argv:
        return argv
    return [proposal_id if arg == _PROPOSAL_ID_PLACEHOLDER else arg for arg in argv]


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
    parser.add_argument(
        "--quickstart",
        action="store_true",
        help=(
            "5-minute onboarding mode: run the no-SW Tier-A health/validate "
            "steps and print the Tier-B/next steps as instructions. 100%% "
            "SOLIDWORKS-free unless combined with --with-sw."
        ),
    )
    parser.add_argument(
        "--with-sw",
        action="store_true",
        help="With --quickstart, also execute the Tier-B steps against a live SOLIDWORKS seat.",
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

    if args.quickstart:
        return _run_quickstart(
            env, with_sw=args.with_sw, no_pause=args.no_pause, sleep_s=args.sleep
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
            _print_header(f"Preflight plan: {chapter.title_for(env)}")
            print(chapter.caption_for(env))
            for step in steps:
                print(f"  $ {step.display}")
        return 0

    for key in remaining:
        chapter = CHAPTERS[key]
        steps = chapter.build_steps(env)
        if not steps:
            continue
        _pause(f"Starting chapter: {chapter.title_for(env)}", args.no_pause)
        print(chapter.caption_for(env))
        # Seat-phase proposal_id threading. Reset per chapter: the propose step
        # of each PAE chapter (assembly/drawing) emits a fresh proposal_id that
        # its own dry_run/commit consume; a stale id must never leak across
        # chapters.
        proposal_id: str | None = None
        for step in steps:
            env_dict = _command_env(env.repo_root)
            # Spike E (2026-08-08, no-SW half): the export chapter's v2
            # export block needs the schema_v2 feature flag ON, and the
            # CLI's --enable-flag does NOT reach it -- spec/validator.py's
            # _v2_enabled() re-resolves flags from the environment only
            # (flags.resolve() with no CLI overrides), so a CLI override
            # passed to ai-sw-build never propagates to validation. The
            # environment variable is the only reliable enable. Harmless
            # for every other step: v1 part specs always route to the v1
            # schema regardless of this flag, and assembly/drawing are
            # separate spec kinds entirely.
            env_dict["AI_SW_BRIDGE_FLAG_SCHEMA_V2"] = "1"
            run_argv = _substitute_proposal_id(step.argv, proposal_id)
            run_step_step = (
                step if run_argv is step.argv else replace(step, argv=run_argv)
            )
            rc, payload = run_step(
                run_step_step,
                cwd=env.repo_root,
                env=env_dict,
                sleep_s=args.sleep,
            )
            if rc:
                return rc
            if isinstance(payload, dict) and payload.get("proposal_id"):
                proposal_id = str(payload["proposal_id"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
