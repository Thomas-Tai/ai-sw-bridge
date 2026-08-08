# Full-System `--no-dim` Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the single-part `tools/demo_no_dim_showcase.py` into a chaptered full-system demo (`tools/demo_full_system.py`) that drives the ai-sw-bridge through parts → parametric edit → assembly → observe/DFM → drawing → export in `--no-dim` mode, producing recordable GIF(s) for the README.

**Architecture:** Extract the proven helpers from the existing showcase into `tools/_demo_lib.py` (the existing tool re-imports them, staying behavior-identical). The new script composes **chapters** — each an ordered list of `DemoStep`s reusing the shared runner — selected by `--chapter part|assembly|observe|drawing|export|all`. A purpose-built 3-part pillow-block widget (`examples/demo_widget/`) is the subject. Three live-SW feasibility unknowns (mates, the v2 `export:` block, `ai-sw-mutate` on a `--no-dim` part) are each authored to support both branches and resolved by a single seat-gated confirmation task that flips a config flag + on-screen caption — no rework either way.

**Tech Stack:** Python ≥3.10 (stdlib only in the demo tools — argparse, subprocess, dataclasses, pathlib; no new deps), pytest, the ai-sw-bridge CLIs invoked as `python -m ai_sw_bridge.cli.<x>` with `PYTHONPATH=<repo>/src`.

## Global Constraints

- **Python floor 3.10.** Every demo/tool file starts with `from __future__ import annotations`; use only 3.10-safe typing. (`pyproject.toml` `requires-python = ">=3.10"`.)
- **Formatting/lint gates must pass:** `black==25.12.0` (`target-version=["py310"]`), `flake8>=7`, `mypy==2.1.0`. Run `black tools/ tests/tools/` and `flake8 tools/ tests/tools/` before every commit.
- **Never `--yes` against SOLIDWORKS without the operator's approval.** All live-SW steps in this plan are **SEAT-GATED**: they run only after the operator approves, on a **clean single SOLIDWORKS seat** (one instance, no dirty docs). The demo script itself uses `--no-dim --yes` for popup-free recording — that convenience is authored, but the operator triggers each recording run.
- **No SW is touched during authoring.** Tasks 1–8 (extraction, widget specs, chapters, docs, and the `--quickstart` mode) are pure-Python / dry-run / docs and require no SolidWorks. Only Tasks 9 (seat confirmation) and 10 (rehearsal + record) touch SW.
- **CLI invocation form:** `[sys.executable, "-m", "ai_sw_bridge.cli.<module>", ...]` with env from `_demo_lib._command_env(repo_root)` (sets `PYTHONPATH=<repo>/src`, `PYTHONIOENCODING=utf-8`). Never call the `ai-sw-*.exe` console scripts from the demo (they may not be on PATH in CI).
- **Outputs go to `demo_out/`** at repo root — gitignored, wiped at the start of each run. Committed widget specs live in `examples/demo_widget/`. Build products (`.SLDPRT`/`.SLDASM`/`.SLDDRW`/exports) never get committed.
- **`--no-dim` strips the in-file equation link** (`known_limitations.md` §3): recorded parts carry literal dims. The parametric story is told via the mutate/locals beat (Task 5), stated as a one-line caveat, never hidden.
- **Trap avoidance in every widget spec:** origin-centered parents (`known_limitations.md` §1), axis-aligned non-flipped extrudes (§2), semantic edge selectors `of_feature`/`between_faces` for fillet/chamfer (§4), `--save-as <abs path>` on every part (§5).

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/_demo_lib.py` (create) | Shared helpers moved verbatim from the showcase: introspection parsers, `CapabilitySection`/`DemoStep`, `run_step`, `_command_env`, header/pause/sleep, `_module_argv`. Single home for the runner. |
| `tools/demo_no_dim_showcase.py` (modify) | Re-import the moved helpers from `_demo_lib` and re-export them (keeps the existing tool + its test behavior-identical). Its own `SHOWCASES`/`resolve_showcase`/`build_demo_plan`/`main` stay. |
| `tools/demo_full_system.py` (create) | The chaptered full-system demo: chapter registry, `--chapter`/`--list-chapters`, `demo_out/` wiping, feasibility flags + captions, **`--quickstart` mode (§4B)**, `main`. |
| `examples/demo_widget/demo_baseplate/spec.json` (+`locals.txt`) (create) | Pillow-block base plate part spec. |
| `examples/demo_widget/demo_shaft/spec.json` (+`locals.txt`) (create) | Turned shaft part spec (revolve boss + groove). |
| `examples/demo_widget/demo_bearing_block/spec.json` (+`locals.txt`) (create) | Bearing block part spec (bore + counterbore + shell). |
| `examples/demo_widget/assembly.json` (create) | Assembly spec: 4 component placements (base, shaft, 2× block), mates-ready. |
| `examples/demo_widget/export.json` (create) | schema-v2 spec (a built part + `export:` block) for the export chapter — used only if Spike E passes. |
| `examples/demo_widget/README.md` (create) | Walks the feature list + trap-avoidance notes for cloners. |
| `tests/tools/test_demo_lib.py` (create) | Unit tests for the moved helpers (mirror the existing showcase test) + re-export smoke test. |
| `tests/tools/test_demo_full_system.py` (create) | Unit tests: chapter registry, `--chapter` selection, `--list-chapters`, `demo_out/` wiping, feasibility-flag captions, **quickstart tiering + doc-sync** — all no-SW. |
| `.gitignore` (modify) | Add `demo_out/`. |
| `docs/demo_full_system.md` (create) | How to run/record each chapter. |
| `QUICKSTART.md` (create) | Repo-root 5-minute onboarding guide; its fenced commands mirror the `--quickstart` step list (test-enforced sync). |
| `README.md` (modify) | GIF section embedding the chaptered clips **+ a Quickstart link** to `QUICKSTART.md`. |
| `docs/known_limitations.md` **or** `docs/CAPABILITIES.md` (modify) | Reconcile the mates claim per Spike 0 (Task 9). |

---

## Task 1: Extract `tools/_demo_lib.py` and re-export from the showcase (parity)

**Files:**
- Create: `tools/_demo_lib.py`
- Modify: `tools/demo_no_dim_showcase.py`
- Create: `tests/tools/test_demo_lib.py`
- Existing (must stay green): `tests/tools/test_demo_no_dim_showcase.py`

**Interfaces:**
- Produces (importable from `tools._demo_lib`): `CapabilitySection`, `DemoStep`, `repo_root_from_script()`, `parse_project_scripts(pyproject_path: Path) -> list[str]`, `parse_observe_tools(observe_py_path: Path) -> list[str]`, `build_capability_sections(list_kinds_payload: dict, cli_commands: list[str], observe_tools: list[str], compact: bool=False) -> list[CapabilitySection]`, `SPEC_TYPE_GROUPS`, `FEATURE_ADD_GROUPS`, `CLI_GROUPS`, `_module_argv(module: str, *args) -> list[str]`, `_command_env(repo_root: Path) -> dict[str,str]`, `_print_header(title)`, `_print_wrapped(prefix, text, width=96)`, `_print_capability_tour(sections)`, `_print_dry_run_summary(payload)`, `run_step(step, *, cwd, env, sleep_s) -> tuple[int, dict|None]`, `_pause(message, no_pause)`.
- Consumes: nothing from other tasks.
- The moved symbols MUST remain importable as `tools.demo_no_dim_showcase.<name>` (the existing test at `tests/tools/test_demo_no_dim_showcase.py` does `from tools import demo_no_dim_showcase as demo` and calls `demo.parse_project_scripts`, `demo.parse_observe_tools`, `demo.build_capability_sections`, `demo.resolve_showcase`, `demo.build_demo_plan`, `demo.steps_for_run`, and reads `.items` off `CapabilitySection`).

- [ ] **Step 1: Capture the pre-refactor behavior baseline (no SW).**

Run and save output — this is the parity oracle:
```bash
cd "<repo>"  # C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge
python tools/demo_no_dim_showcase.py --tour-only --no-pause --sleep 0 > /tmp/demo_tour_before.txt
python tools/demo_no_dim_showcase.py --preflight-only --no-pause --sleep 0 > /tmp/demo_preflight_before.txt
```
Expected: both exit 0. `--tour-only` prints the capability surface; `--preflight-only` additionally prints the dry-run summary. Neither opens SOLIDWORKS (`--list-kinds` and `--dry-run --lint` are SW-free).

- [ ] **Step 2: Create `tools/_demo_lib.py` by moving the shared helpers.**

Cut these from `demo_no_dim_showcase.py` into `_demo_lib.py` **verbatim** (keep signatures/bodies byte-identical): the module imports it needs (`argparse` not needed here — drop it; keep `json, os, re, subprocess, sys, textwrap, time`, `dataclass`, `Path`, `Any`); `SPEC_TYPE_GROUPS`, `FEATURE_ADD_GROUPS`, `CLI_GROUPS`; `CapabilitySection`, `DemoStep`; `repo_root_from_script`, `_strip_toml_key`, `parse_project_scripts`, `parse_observe_tools`, `_grouped_lines`, `_compact_group_summary`, `build_capability_sections`, `_module_argv`, `_spec_arg`, `_command_env`, `_print_wrapped`, `_print_header`, `_print_capability_tour`, `_print_dry_run_summary`, `_print_json_summary`, `run_step`, `_pause`. Start the file with `from __future__ import annotations`.

Note: `_print_json_summary` branches on `step.id in {"dry_run","list_kinds"}` — keep it in `_demo_lib` unchanged; the full-system script will reuse those ids for its tour/preflight steps.

- [ ] **Step 3: Rewrite `demo_no_dim_showcase.py` to import + re-export from `_demo_lib`.**

Replace the moved definitions with a re-export block near the top (after `from __future__ import annotations` and its remaining stdlib imports `argparse, sys`):
```python
from tools._demo_lib import (  # noqa: F401  (re-exported for back-compat + tests)
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
    _print_capability_tour,
    _print_header,
    run_step,
    _pause,
)
```
Keep in `demo_no_dim_showcase.py` only what is showcase-specific: `DEFAULT_SHOWCASE`, `ShowcaseDefinition`, `ResolvedShowcase`, `SHOWCASES`, `_spec_arg` (or import it), `resolve_showcase`, `build_demo_plan`, `steps_for_run`, `main`, and the `if __name__ == "__main__"` guard. If `main` uses `_print_dry_run_summary`/`_print_json_summary` indirectly (via `run_step`), no extra import is needed; if referenced directly, add them to the import list.

- [ ] **Step 4: Run the existing showcase test — it must still pass unchanged.**

Run: `python -m pytest tests/tools/test_demo_no_dim_showcase.py -v`
Expected: all 10 tests PASS (they import the re-exported symbols).

- [ ] **Step 5: Write the parity + re-export test.**

Create `tests/tools/test_demo_lib.py`:
```python
from __future__ import annotations

from tools import _demo_lib
from tools import demo_no_dim_showcase as demo


def test_shared_symbols_are_the_same_object() -> None:
    # Re-export must be identity, not a copy, so both tools share one runner.
    for name in ("parse_project_scripts", "build_capability_sections",
                 "run_step", "DemoStep", "CapabilitySection"):
        assert getattr(demo, name) is getattr(_demo_lib, name)


def test_parse_project_scripts_filters_ai_sw(tmp_path) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text('[project.scripts]\nai-sw-build = "x:main"\nother = "y:main"\n',
                 encoding="utf-8")
    assert _demo_lib.parse_project_scripts(p) == ["ai-sw-build"]
```

- [ ] **Step 6: Run the new test.**

Run: `python -m pytest tests/tools/test_demo_lib.py -v`
Expected: PASS.

- [ ] **Step 7: Recapture behavior and diff against the baseline (parity gate).**

```bash
python tools/demo_no_dim_showcase.py --tour-only --no-pause --sleep 0 > /tmp/demo_tour_after.txt
python tools/demo_no_dim_showcase.py --preflight-only --no-pause --sleep 0 > /tmp/demo_preflight_after.txt
diff /tmp/demo_tour_before.txt /tmp/demo_tour_after.txt
diff /tmp/demo_preflight_before.txt /tmp/demo_preflight_after.txt
```
Expected: **no diff** on either. If diff is non-empty, the refactor changed behavior — fix before proceeding.

- [ ] **Step 8: Format, lint, commit.**

```bash
black tools/_demo_lib.py tools/demo_no_dim_showcase.py tests/tools/test_demo_lib.py
flake8 tools/_demo_lib.py tools/demo_no_dim_showcase.py tests/tools/test_demo_lib.py
git add tools/_demo_lib.py tools/demo_no_dim_showcase.py tests/tools/test_demo_lib.py
git commit -m "refactor(demo): extract shared runner into tools/_demo_lib, re-export for parity"
```

---

## Task 2: Author the three widget part specs (dry-run validated, no SW)

**Files:**
- Create: `examples/demo_widget/demo_baseplate/spec.json` + `examples/demo_widget/demo_baseplate/locals.txt`
- Create: `examples/demo_widget/demo_shaft/spec.json` + `locals.txt`
- Create: `examples/demo_widget/demo_bearing_block/spec.json` + `locals.txt`

**Interfaces:**
- Produces: three buildable part specs whose paths later tasks reference. Part names (the `"name"` field, used as default output stems): `DemoBaseplate`, `DemoShaft`, `DemoBearingBlock`.
- Consumes: nothing.

**Reference examples for feature param shapes** (copy the exact field names from these — do not invent schema): rectangle+extrude+hole+linear_pattern → `examples/patterned_plate/spec.json`; revolve_boss+revolve_cut → `examples/grooved_shaft/spec.json`; chamfer → `examples/chamfered_box/spec.json`; fillet → `examples/filleted_box/spec.json`; mirror → `examples/mirrored_holes/spec.json`; circular_pattern → `examples/patterned_disc/spec.json`; simple_hole → `examples/drilled_plate/spec.json`; locals convention → `examples/s1b_conveyor_locals.txt` and the `feedback_locals_sot` rule (edit `*_locals.txt`, never the equation manager).

- [ ] **Step 1: Confirm the build CLI surface for save + locals (no SW).**

Run: `python -m ai_sw_bridge.cli.build --help` (env: `PYTHONPATH=<repo>/src`).
Confirm the flags used downstream exist and note their exact spelling: `--save-as` (dest `save_as`), `--save-format`, `--no-dim`, `--dry-run`, `--lint`, `--demo`, and how a sibling `locals.txt` is supplied (look for `--locals`; if none, confirm auto-discovery by reading `src/ai_sw_bridge/cli/build.py` around the spec-load path and `src/ai_sw_bridge/locals_io/`). Record the locals mechanism in the widget `README.md` (Task 7).

- [ ] **Step 2: Write `demo_baseplate/spec.json` with the VERIFIED-feature core first.**

Start from this complete, origin-centered spec (all features have a reference example, so it will dry-run clean):
```json
{
  "schema_version": 1,
  "name": "DemoBaseplate",
  "_comment": "Pillow-block base plate. Origin-centered so face-sketch children resolve (known_limitations §1). Axis-aligned Front extrude (§2). Fillet/chamfer use semantic edge selectors (§4).",
  "features": [
    {"type": "sketch_rectangle_on_plane", "name": "SK_Plate", "plane": "Front",
     "width": 100.0, "height": 60.0, "center": {"x": 0.0, "y": 0.0}},
    {"type": "boss_extrude_blind", "name": "EX_Plate", "sketch": "SK_Plate", "depth": 10.0},
    {"type": "sketch_circle_on_face", "name": "SK_MountSeed", "of_feature": "EX_Plate",
     "face": "+z", "diameter": 5.0, "center": {"u": -40.0, "v": -20.0}},
    {"type": "cut_extrude_through_all", "name": "Hole_MountSeed", "sketch": "SK_MountSeed"},
    {"type": "linear_pattern", "name": "LP_Mounts", "seed": "Hole_MountSeed",
     "direction": {"x": 1.0, "y": 0.0, "z": 0.0}, "count": 3, "spacing": 40.0},
    {"type": "mirror_feature", "name": "MIR_Mounts", "seed": "LP_Mounts", "plane": "Top"},
    {"type": "fillet_constant_radius", "name": "FIL_Corners", "of_feature": "EX_Plate",
     "radius": 4.0},
    {"type": "chamfer_edge", "name": "CHA_TopEdge", "of_feature": "EX_Plate", "distance": 1.5}
  ]
}
```
Adjust `linear_pattern.direction`/`flip` and the mirror `plane` to whatever the reference examples show for a `+z`-face pattern (the direction edge convention is documented inline in `patterned_plate/spec.json`). Fix field names to match the actual handlers if dry-run (Step 5) rejects any (`fillet_constant_radius` vs `fillet`; `chamfer_edge` vs `chamfer` — the `--list-kinds` payload from Task 1 baseline lists the real spec-feature-type names; use those).

- [ ] **Step 3: Write `demo_shaft/spec.json` (revolve boss + groove).**

Model on `examples/grooved_shaft/spec.json` (note its opposite-side cut rule — boss profile on +y, cut profile on −y):
```json
{
  "schema_version": 1,
  "name": "DemoShaft",
  "_comment": "Turned shaft: Ø16 x 90 revolve boss along x, O-ring groove at mid-length via revolve_cut on the opposite side (§ grooved_shaft opposite-side rule). End chamfers.",
  "features": [
    {"type": "sketch_rectangle_on_plane", "name": "SK_Body", "plane": "Front",
     "width": 90.0, "height": 8.0, "center": {"x": 45.0, "y": 4.0},
     "centerline": {"start": {"x": -60.0, "y": 0.0}, "end": {"x": 150.0, "y": 0.0}}},
    {"type": "revolve_boss", "name": "REV_Body", "sketch": "SK_Body", "angle": 360.0},
    {"type": "sketch_rectangle_on_plane", "name": "SK_Groove", "plane": "Front",
     "width": 4.0, "height": 1.0, "center": {"x": 45.0, "y": -8.0},
     "centerline": {"start": {"x": -60.0, "y": 0.0}, "end": {"x": 150.0, "y": 0.0}}},
    {"type": "revolve_cut", "name": "CUT_Groove", "sketch": "SK_Groove", "angle": 360.0}
  ]
}
```
Add end chamfers with `chamfer_edge` (`of_feature: "REV_Body"`) once the body validates.

- [ ] **Step 4: Write `demo_bearing_block/spec.json` (bore + counterbore + shell).**

```json
{
  "schema_version": 1,
  "name": "DemoBearingBlock",
  "_comment": "Bearing housing: 40x30x28 block, centered through-bore Ø16, counterbore, two mounting holes, shell to lighten. Origin-centered.",
  "features": [
    {"type": "sketch_rectangle_on_plane", "name": "SK_Block", "plane": "Front",
     "width": 40.0, "height": 28.0, "center": {"x": 0.0, "y": 0.0}},
    {"type": "boss_extrude_midplane", "name": "EX_Block", "sketch": "SK_Block", "depth": 30.0},
    {"type": "sketch_circle_on_face", "name": "SK_Bore", "of_feature": "EX_Block",
     "face": "+z", "diameter": 16.0, "center": {"u": 0.0, "v": 0.0}},
    {"type": "cut_extrude_through_all", "name": "Cut_Bore", "sketch": "SK_Bore"},
    {"type": "fillet_constant_radius", "name": "FIL_Block", "of_feature": "EX_Block",
     "radius": 3.0}
  ]
}
```
The bore is the mate target for the shaft (concentric, if Spike 0 passes). Counterbore/countersink/shell are added in Step 6 as enrichment.

- [ ] **Step 5: Dry-run + lint every spec (this is the test — no SW).**

For each part:
```bash
python -m ai_sw_bridge.cli.build examples/demo_widget/demo_baseplate/spec.json --dry-run --lint
python -m ai_sw_bridge.cli.build examples/demo_widget/demo_shaft/spec.json --dry-run --lint
python -m ai_sw_bridge.cli.build examples/demo_widget/demo_bearing_block/spec.json --dry-run --lint
```
Expected: each prints `"ok": true` with `finding_count: 0` and a resolved feature order. Any schema/field error here is a spec bug — fix the JSON and re-run until green. **No SW is opened by `--dry-run`.**

- [ ] **Step 6: Enrich toward ~16–18 feature families — iterative, graceful-degrade.**

Add these features **one at a time**, re-running `--dry-run --lint` after each; **keep it only if the dry-run stays green**, else drop it (this is the spec's "any kind not present degrades gracefully" rule):
  - baseplate: `draft` (on the plate side face) and `circular_pattern` (a small bolt circle) — param shapes from `patterned_disc` and the `draft` handler.
  - bearing_block: counterbore + `countersink` on the mounting holes, `shell` (wall ~3 mm), and a `ref_plane` (offset plane) hosting one off-origin sketch.
  - shaft: optional `cosmetic thread` on one end — only if it appears in the `--list-kinds` payload.

For any feature lacking a reference example (`draft`, `shell`, `countersink`, `ref_plane`, cosmetic thread), read its schema in `src/ai_sw_bridge/spec/handlers/` or `src/ai_sw_bridge/features/` (grep the kind name) to get exact field names before writing the JSON, then dry-run. Target 16–18 families total; stop early rather than force a fragile feature. Record the final per-part family list for the README (Task 7).

- [ ] **Step 7: Write per-part `locals.txt` (parametric source of truth).**

Using the mechanism confirmed in Step 1, extract the driving numbers into `<part>/locals.txt` and reference them as `{name}` in the spec (mirror the `s1b_conveyor_locals.txt` idiom). At minimum expose: baseplate `PLATE_L`, `PLATE_W`, `PLATE_T`; shaft `SHAFT_DIA`, `SHAFT_LEN`; block `BORE_DIA`, `BLOCK_W`. These are what the Task 5 headline beat edits. Re-run `--dry-run --lint`; expect `locals_resolved: true`.

- [ ] **Step 8: Commit.**

```bash
git add examples/demo_widget/
git commit -m "feat(demo): add pillow-block widget part specs (dry-run validated)"
```

---

## Task 3: Author the assembly spec (transform-only baseline, mates-ready)

**Files:**
- Create: `examples/demo_widget/assembly.json`

**Interfaces:**
- Produces: an assembly spec consumed by the `assembly` chapter (Task 6). Component ids: `base`, `shaft`, `block_pos`, `block_neg`.
- Consumes: the three part `.SLDPRT` files built to `demo_out/` at run time (Task 6 builds them first).

- [ ] **Step 1: Read the assembly spec + mate schema (no SW).**

Read `src/ai_sw_bridge/cli/assembly.py` (the `propose`/`dry_run`/`commit` verbs and their args) and `tests/test_assembly_schema.py` + `tests/test_assembly_handlers.py` to learn: (a) the component/transform block shape, and (b) the **mate block** shape (mate types, referenced faces/entities). Note the `rpy` anchor convention from `reference_sw_bridge_assembly`: `rpy=[0,0,0]` → xyz is bbox-center; `rpy≠0` → xyz is part-origin.

- [ ] **Step 2: Write the transform-only assembly (the proven, always-works baseline).**

Use the S1b idiom (`kind: "assembly"`, `components[].part` absolute path + `transform.xyz_mm`/`rpy_deg`). Place: `base` at origin; `shaft` concentric-nominal above the plate along its axis; `block_pos` and `block_neg` straddling the shaft at ±X so the shaft bore-line passes through both blocks' bores. Use **relative paths under `demo_out/`** resolved to absolute at runtime by the chapter code (do not hardcode a machine path — Task 6 fills the built-part paths). Keep a `"mates"` array present but empty for now.

- [ ] **Step 3: Validate via the assembly `dry_run` verb against pre-built parts (SEAT-GATED — deferred).**

Full assembly `dry_run` resolves part files and may open SW; mark this validation as part of the Task 10 rehearsal. For now, JSON-lint the file (`python -c "import json,sys; json.load(open('examples/demo_widget/assembly.json'))"`) and confirm the schema shape matches what `test_assembly_schema.py` asserts.

- [ ] **Step 4: Commit.**

```bash
git add examples/demo_widget/assembly.json
git commit -m "feat(demo): add widget assembly spec (transform-only baseline, mates-ready)"
```

---

## Task 4: `demo_full_system.py` skeleton — chapters as data, arg parsing, `demo_out/` wiping

**Files:**
- Create: `tools/demo_full_system.py`
- Create: `tests/tools/test_demo_full_system.py`

**Interfaces:**
- Produces: `CHAPTERS: dict[str, Chapter]` where `Chapter` is a frozen dataclass `{key: str, title: str, caption: str, build_steps: Callable[[BuildEnv], list[DemoStep]]}`; `chapter_order() -> list[str]` (`["tour","part","assembly","observe","drawing","export"]`); `select_chapters(name: str) -> list[str]` (`"all"` → full order; a single key → `[key]`); `wipe_demo_out(demo_out: Path) -> None`; `main(argv=None) -> int`. `BuildEnv` is a small dataclass carrying `repo_root: Path`, `demo_out: Path`, `widget_dir: Path`, feasibility flags (`mates_proven: bool`, `export_block_wired: bool`, `mutate_drives_nodim: bool`).
- Consumes (from `tools._demo_lib`, Task 1): `DemoStep`, `run_step`, `_command_env`, `_module_argv`, `_print_header`, `_pause`, `parse_project_scripts`, `parse_observe_tools`, `build_capability_sections`, `_print_capability_tour`, `repo_root_from_script`.

- [ ] **Step 1: Write the failing test for chapter selection + demo_out wiping.**

Create `tests/tools/test_demo_full_system.py`:
```python
from __future__ import annotations

from pathlib import Path

from tools import demo_full_system as dfs


def test_all_expands_to_full_ordered_chapter_list() -> None:
    assert dfs.select_chapters("all") == [
        "tour", "part", "assembly", "observe", "drawing", "export"
    ]


def test_single_chapter_selection() -> None:
    assert dfs.select_chapters("observe") == ["observe"]


def test_unknown_chapter_raises() -> None:
    import pytest
    with pytest.raises(SystemExit):
        dfs.select_chapters("nope")


def test_wipe_demo_out_clears_and_recreates(tmp_path: Path) -> None:
    out = tmp_path / "demo_out"
    out.mkdir()
    (out / "stale.SLDPRT").write_text("x", encoding="utf-8")
    dfs.wipe_demo_out(out)
    assert out.is_dir()
    assert list(out.iterdir()) == []
```

- [ ] **Step 2: Run it to confirm failure.**

Run: `python -m pytest tests/tools/test_demo_full_system.py -v`
Expected: FAIL with `ModuleNotFoundError`/`AttributeError` (module not written yet).

- [ ] **Step 3: Implement the skeleton.**

Write `tools/demo_full_system.py`: `from __future__ import annotations`; import the shared helpers from `tools._demo_lib`; define `Chapter`, `BuildEnv`, `CHAPTERS` (chapter bodies can be stubs returning `[]` for now except `tour`), `chapter_order`, `select_chapters` (raise `SystemExit(2)` with a helpful message on unknown key), `wipe_demo_out` (`shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True, exist_ok=True)`), and a `main` with argparse: `--chapter` (default `all`, choices = order + `all`), `--list-chapters`, `--no-pause`, `--sleep` (default 0.8), `--compact`, `--tour-only`, `--preflight-only`, plus reuse of `_command_env`. `main` wipes `demo_out/`, prints a title, runs the `tour` chapter first, then the selected chapters.

- [ ] **Step 4: Run the test to confirm pass.**

Run: `python -m pytest tests/tools/test_demo_full_system.py -v`
Expected: PASS.

- [ ] **Step 5: Wire the `tour` chapter for real and smoke it (no SW).**

The `tour` chapter reuses `_demo_lib`: run `ai-sw-build --list-kinds` (capture JSON), `parse_project_scripts(pyproject)`, `parse_observe_tools(observe.py)`, `build_capability_sections(...)`, `_print_capability_tour(...)`. After each list, print the DEFERRED.md signpost line: `"Honest edges: see docs/DEFERRED.md for walled features."`.
```bash
python tools/demo_full_system.py --tour-only --no-pause --sleep 0
python tools/demo_full_system.py --list-chapters
```
Expected: tour prints the full introspected surface + DEFERRED signposts; `--list-chapters` lists the 6 chapters with captions. Exit 0, no SW.

- [ ] **Step 6: Format, lint, commit.**

```bash
black tools/demo_full_system.py tests/tools/test_demo_full_system.py
flake8 tools/demo_full_system.py tests/tools/test_demo_full_system.py
git add tools/demo_full_system.py tests/tools/test_demo_full_system.py
git commit -m "feat(demo): full-system chaptered skeleton + tour chapter"
```

---

## Task 5: `part` chapter + the `ai-sw-mutate` headline beat

**Files:**
- Modify: `tools/demo_full_system.py` (implement the `part` chapter body)
- Modify: `tests/tools/test_demo_full_system.py` (assert the step argv shape)

**Interfaces:**
- Consumes: `BuildEnv` (Task 4), the three widget specs (Task 2), `DemoStep`/`_module_argv` (Task 1).
- Produces: `part` chapter step list; `mutate_beat_steps(env) -> list[DemoStep]` used inside it.

- [ ] **Step 1: Confirm the mutate CLI surface (no SW).**

Run `python -m ai_sw_bridge.cli.mutate --help` and read `src/ai_sw_bridge/cli/mutate.py`. Determine the exact propose→dry-run→commit verbs and how a driving **dimension** (or locals value) is targeted. Record two candidate beats: **(primary)** `ai-sw-mutate` changes a driving dimension on the live-built part and SW rebuilds; **(fallback)** edit `demo_baseplate/locals.txt` and re-run `ai-sw-build --no-dim --save-as` to show the changed geometry. Which one is live-valid is Spike M (Task 9).

- [ ] **Step 2: Write the failing test for the part chapter's build steps.**

Add to `tests/tools/test_demo_full_system.py`:
```python
def test_part_chapter_builds_three_parts_with_no_dim_save_as(tmp_path: Path) -> None:
    env = dfs.BuildEnv(
        repo_root=Path("C:/repo"), demo_out=tmp_path / "demo_out",
        widget_dir=Path("C:/repo/examples/demo_widget"),
        mates_proven=False, export_block_wired=False, mutate_drives_nodim=False,
    )
    steps = dfs.CHAPTERS["part"].build_steps(env)
    build_steps = [s for s in steps if s.id.startswith("build_")]
    assert len(build_steps) == 3
    for s in build_steps:
        assert "--no-dim" in s.argv and "--yes" in s.argv and "--save-as" in s.argv
    # headline mutate beat present
    assert any(s.id.startswith("mutate") or s.id.startswith("reparam") for s in steps)
```

- [ ] **Step 3: Run it to confirm failure.**

Run: `python -m pytest tests/tools/test_demo_full_system.py::test_part_chapter_builds_three_parts_with_no_dim_save_as -v`
Expected: FAIL (part chapter still a stub).

- [ ] **Step 4: Implement the `part` chapter body.**

Three `build_<part>` steps: `_module_argv("ai_sw_bridge.cli.build", str(spec), "--no-dim", "--yes", "--save-as", str(env.demo_out / f"{PartName}.SLDPRT"))`. After each, an `observe_bbox_<part>` step (`allow_failure=True`) reading `bounding_box`. Then the mutate beat from `mutate_beat_steps(env)`: if `env.mutate_drives_nodim` → the primary `ai-sw-mutate` sequence; else → the locals-edit-rebuild fallback (a step that rewrites one locals value in `demo_out/` copies and rebuilds — never mutate the committed `examples/` locals; copy to `demo_out/` first). Add the on-screen caption `"Change one number; the model rebuilds. That's the whole point."` and the one-line `--no-dim` equation-link footnote.

- [ ] **Step 5: Run the test to confirm pass.**

Run: `python -m pytest tests/tools/test_demo_full_system.py -v`
Expected: PASS.

- [ ] **Step 6: Preflight the part chapter without SW.**

Run: `python tools/demo_full_system.py --chapter part --preflight-only --no-pause --sleep 0`
Expected: prints the three build commands + the mutate beat as a **dry-run/plan** (no `--yes` execution in preflight) and exits 0 without opening SW. (Ensure `--preflight-only` degrades live steps to their `--dry-run` form or prints-without-running.)

- [ ] **Step 7: Format, lint, commit.**

```bash
black tools/demo_full_system.py tests/tools/test_demo_full_system.py
flake8 tools/demo_full_system.py tests/tools/test_demo_full_system.py
git add tools/demo_full_system.py tests/tools/test_demo_full_system.py
git commit -m "feat(demo): part chapter with ai-sw-mutate headline beat"
```

---

## Task 6: `assembly`, `observe`, `drawing` chapters

**Files:**
- Modify: `tools/demo_full_system.py`
- Modify: `tests/tools/test_demo_full_system.py`

**Interfaces:**
- Consumes: `assembly.json` (Task 3), built parts in `demo_out/` (Task 5), the assembly/observe/drawing CLI surfaces.
- Produces: three chapter bodies. `assembly` reads `env.mates_proven` to choose title/caption + whether the mate block is sent.

- [ ] **Step 1: Confirm the observe + drawing CLI surfaces (no SW).**

`python -m ai_sw_bridge.cli.observe --help` (confirm subcommands: `interference`, `min_wall`, `mass_properties`, `bounding_box`, `screenshot` — cross-check the list `parse_observe_tools` returns). `python -m ai_sw_bridge.cli.drawing --help` (confirm views/dims/BOM args + `--out` for the `.SLDDRW`, per `drawing.py` lines ~65–97). Note the screenshot flag is `--filename` and output lands in `AI_SW_BRIDGE_CAPTURES` (`%LOCALAPPDATA%\Temp\ai-sw-bridge\captures\`), NOT `--out`.

- [ ] **Step 2: Implement the `assembly` chapter (both branches).**

Steps: build the 3 parts to `demo_out/` (or reuse if `part` chapter already ran in an `all` run — guard with existence check); resolve `assembly.json` component paths to the `demo_out/` absolutes; `ai-sw-assembly propose --spec <resolved> ` → `dry_run --proposal-id <id>` → `commit --proposal-id <id> --out demo_out/DemoWidget.SLDASM`. **Chain propose→dry_run→commit in one run with no idle gap** (proposals expire across pauses — the `reference_sw_bridge_assembly` lesson). Then `mirror` the 2nd bearing block and an `exploded` view step. Branch on `env.mates_proven`: True → include the mate block (concentric bore↔shaft, coincident block↔plate) and caption/title `"assembly with mates"`; False → transform-only, title `"component placement / layout"`, caption noting mates are seat-unproven. Interference step belongs to `observe`.

- [ ] **Step 3: Implement the `observe` chapter (the weighted one).**

Steps against the committed assembly (`allow_failure=True` each, capture JSON): `interference` (expect 0), `min_wall` (DFM), `mass_properties`, `bounding_box`, `screenshot --filename demo_widget.png`. Give this chapter extra header/pause room per the spec (`observe` is the most credible content). Caption: `"DFM is a build gate, not a manual afterthought."`

- [ ] **Step 4: Implement the `drawing` chapter.**

`ai-sw-drawing` with 3 orthographic + isometric views, model dims, BOM, saving `demo_out/DemoWidget.SLDDRW` and (if the drawing verb emits PDF directly) a PDF; else PDF comes via the export chapter. Caption: `"Drawing + BOM fall out of the same model."`

- [ ] **Step 5: Write tests for the branch behavior (no SW).**

Add:
```python
def test_assembly_caption_flips_on_mates_flag(tmp_path: Path) -> None:
    def env(mates: bool) -> "dfs.BuildEnv":
        return dfs.BuildEnv(Path("C:/repo"), tmp_path / "o",
                            Path("C:/repo/examples/demo_widget"),
                            mates_proven=mates, export_block_wired=False,
                            mutate_drives_nodim=False)
    assert dfs.CHAPTERS["assembly"].title_for(env(True)) != \
           dfs.CHAPTERS["assembly"].title_for(env(False))
```
(Expose a `title_for(env)`/`caption_for(env)` on `Chapter` for chapters whose identity depends on a flag; static chapters can return the fixed `title`.)

- [ ] **Step 6: Run tests; preflight the three chapters (no SW).**

Run: `python -m pytest tests/tools/test_demo_full_system.py -v` (PASS), then
`python tools/demo_full_system.py --chapter assembly --preflight-only --no-pause --sleep 0` (and `observe`, `drawing`) — each prints its planned command sequence and exits 0 without SW.

- [ ] **Step 7: Format, lint, commit.**

```bash
black tools/demo_full_system.py tests/tools/test_demo_full_system.py
flake8 tools/demo_full_system.py tests/tools/test_demo_full_system.py
git add tools/demo_full_system.py tests/tools/test_demo_full_system.py
git commit -m "feat(demo): assembly (mates-gated), observe, drawing chapters"
```

---

## Task 7: `export` chapter (Spike-E-gated) + docs, README, gitignore

**Files:**
- Modify: `tools/demo_full_system.py` (export chapter body)
- Create: `examples/demo_widget/export.json` (schema-v2 spec + `export:` block)
- Modify: `tests/tools/test_demo_full_system.py`
- Modify: `.gitignore`
- Create: `docs/demo_full_system.md`
- Create: `examples/demo_widget/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `env.export_block_wired` (set by Spike E, Task 9). Produces: `export` chapter body + docs.

Background (already investigated): there is **no general `ai-sw-export` CLI**. STEP/IGES/Parasolid/STL/3MF export is a **schema-v2 `export:` block** run by `spec/orchestrator.py::_run_export` (`SolidWorksClient().export.run(...)`), gated behind the `schema_v2` flag (`src/ai_sw_bridge/spec/schema.py` `SCHEMA_VERSION_V2`, `build_schema_v2()`). The block shape (`src/ai_sw_bridge/export/schema.py`): array of `{"format": <one of EXPORT_FORMAT_NAMES>, "filename"?, "output_dir"?, "binary"? (STL), "sheets"? (PDF)}`.

- [ ] **Step 1: Write `export.json` (schema-v2 spec producing STEP+STL+3MF).**

A minimal `schema_version: 2` spec that builds a small solid and declares:
```json
{
  "schema_version": 2,
  "name": "DemoExportBlock",
  "features": [
    {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
     "width": 30.0, "height": 20.0, "center": {"x": 0.0, "y": 0.0}},
    {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 8.0}
  ],
  "export": [
    {"format": "step214", "output_dir": "demo_out"},
    {"format": "stl", "output_dir": "demo_out", "binary": true},
    {"format": "3mf", "output_dir": "demo_out"}
  ]
}
```
Confirm the exact `format` identifiers against `EXPORT_FORMAT_NAMES` in `src/ai_sw_bridge/export/formats.py` (e.g. `step214`, `stl`, `3mf`) — use the real names.

- [ ] **Step 2: Spike E (no-SW half): does the build path ACCEPT a v2 export block?**

Run: `python -m ai_sw_bridge.cli.build examples/demo_widget/export.json --dry-run --lint`
- If it validates (v2 routing + `schema_v2` gate are live) → `export_block_wired` **candidate True** (live emission still confirmed on the seat in Task 9). If the validator rejects `schema_version: 2` or the `export:` key, check whether a `schema_v2` flag/env must be set (grep `schema_v2` in `src/ai_sw_bridge/flags/` and `spec/schema.py`); if it cannot be enabled from the CLI → `export_block_wired = False`.
- Record the outcome. **Fallback when False:** the export chapter narrows to the **drawing PDF** (from Task 6) as the "downstream artifact," and the tour still lists STEP/STL/3MF as spec-declared/seat-gated (honest — not live-built in v1). Do NOT add a new `ai-sw-export` CLI in this demo (out of scope).

- [ ] **Step 3: Implement the export chapter (both branches).**

If `env.export_block_wired` → step: `ai-sw-build examples/demo_widget/export.json --no-dim --yes` and then list the produced `demo_out/*.step/*.stl/*.3mf`. Else → a single caption step pointing at the drawing PDF + a tour reminder. Caption: `"One model, every downstream format."` (wired) / `"Drawing PDF is the downstream artifact in this build; STEP/STL/3MF ship via the spec export block, seat-gated."` (fallback).

- [ ] **Step 4: Add `demo_out/` to `.gitignore` and write the docs.**

`.gitignore`: add a line `demo_out/` under the smoke-scratch section (near the existing `captures/`). Write `docs/demo_full_system.md` (how to run/record each chapter: exact commands, the `--no-pause`/`--sleep` recording flags, where outputs land). Write `examples/demo_widget/README.md` (the final per-part feature-family list from Task 2 Step 6, the trap-avoidance notes, the locals mechanism from Task 2 Step 1). Add a **GIF section** to `README.md` with placeholders for the clip embeds (the actual GIFs are produced in Task 10; commit the section now, add the images later).

- [ ] **Step 5: Test + preflight (no SW).**

Add a test asserting the export chapter caption flips on `export_block_wired`. Run the full `tests/tools/` suite (PASS). Run `python tools/demo_full_system.py --chapter export --preflight-only --no-pause --sleep 0` (exit 0, no SW).

- [ ] **Step 6: Format, lint, commit.**

```bash
black tools/ tests/tools/
flake8 tools/ tests/tools/
git add tools/demo_full_system.py tests/tools/test_demo_full_system.py examples/demo_widget/ .gitignore docs/demo_full_system.md README.md
git commit -m "feat(demo): export chapter (spike-E gated) + docs, README GIF section, gitignore"
```

---

## Task 8: Quickstart mode + `QUICKSTART.md` (5-minute onboarding, no SW)

**Files:**
- Modify: `tools/demo_full_system.py` (add the `--quickstart` mode + the canonical step list)
- Create: `QUICKSTART.md` (repo root)
- Modify: `README.md` (Quickstart link near the top)
- Modify: `tests/tools/test_demo_full_system.py` (tiering + doc-sync tests)

**Interfaces:**
- Produces: `QUICKSTART_STEPS: list[QuickstartStep]` — the single source of truth for both the runnable mode and the doc; `quickstart_steps(env, with_sw: bool) -> list[DemoStep]`; `quickstart_command_lines(with_sw: bool=True) -> list[str]` (renders the canonical shell commands, used by the doc-sync test). `QuickstartStep = {tier: "A"|"B"|"next", caption: str, argv: list[str] | None, prose: str | None}`.
- Consumes: `BuildEnv`, the `_demo_lib` runner, the committed `examples/demo_widget/demo_baseplate/spec.json` (from Task 2).

**Design:** one canonical `QUICKSTART_STEPS` list drives **both** the `--quickstart` mode and the doc. `QUICKSTART.md` is prose, but its fenced `bash` commands are asserted equal (content + presence) to `quickstart_command_lines()` by a test, so the guide can never drift from what actually runs. (Spec §4B.)

- [ ] **Step 1: Confirm `ai-sw-doctor` is a read-only, no-launch probe.**

Read `src/ai_sw_bridge/cli/doctor.py`: confirm it checks COM/seat health WITHOUT launching or mutating SOLIDWORKS (a read-only attach to an already-running seat is fine). Record the finding. Tier A must stay no-approval-required — if `doctor` can launch SW, demote it from an executed step to a printed instruction.

- [ ] **Step 2: Write the failing tests (tiering + doc-sync).**

Add to `tests/tools/test_demo_full_system.py`:
```python
def test_quickstart_seatless_runs_tier_a_only(tmp_path: Path) -> None:
    env = dfs.BuildEnv(Path("C:/repo"), tmp_path / "o",
                       Path("C:/repo/examples/demo_widget"),
                       mates_proven=False, export_block_wired=False,
                       mutate_drives_nodim=False)
    steps = dfs.quickstart_steps(env, with_sw=False)
    # Seat-less quickstart never issues a live build/observe.
    assert all("--no-dim" not in (s.argv or []) for s in steps)
    assert all("--yes" not in (s.argv or []) for s in steps)


def test_quickstart_doc_commands_match_canonical_list() -> None:
    import re
    doc = Path(__file__).resolve().parents[2] / "QUICKSTART.md"
    fenced = re.findall(r"```bash\n(.*?)```", doc.read_text(encoding="utf-8"), re.S)
    doc_cmds = [ln.strip() for block in fenced for ln in block.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    for cmd in dfs.quickstart_command_lines(with_sw=True):
        assert cmd in doc_cmds, f"QUICKSTART.md missing/renamed command: {cmd}"
```

- [ ] **Step 3: Run to confirm failure.**

Run: `python -m pytest tests/tools/test_demo_full_system.py -k quickstart -v`
Expected: FAIL (`quickstart_steps`/`quickstart_command_lines` and `QUICKSTART.md` don't exist yet).

- [ ] **Step 4: Implement `QUICKSTART_STEPS` + the mode.**

In `demo_full_system.py`, define the canonical list:
- **Tier A (no SW):** (prose) `pip install -e .[dev]`; then `python -m ai_sw_bridge.cli.doctor`; `python -m ai_sw_bridge.cli.build --list-kinds`; `python -m ai_sw_bridge.cli.build examples/demo_widget/demo_baseplate/spec.json --dry-run --lint`.
- **Tier B (needs seat):** `python -m ai_sw_bridge.cli.build --demo --no-dim --yes`; `python -m ai_sw_bridge.cli.observe bounding_box`.
- **Next (prose pointers):** edit any `examples/demo_widget/*/spec.json` and re-run the dry-run; `python tools/demo_full_system.py --chapter all` for the full tour; read `docs/demo_full_system.md`.

`quickstart_steps(env, with_sw)` returns Tier A always, Tier B only when `with_sw`, and always prints the "next" pointers. Add `--quickstart` and `--with-sw` to `main`'s argparse. Plain `--quickstart` = Tier A executed + Tier B/next printed as instructions (100% no-SW; `doctor` is read-only per Step 1, `allow_failure=True` so a seat-less user still completes). `--quickstart --with-sw` runs Tier B live (SEAT-GATED — exercised in Task 10). `quickstart_command_lines(with_sw)` renders the argv/prose commands in order for the doc-sync test.

- [ ] **Step 5: Run the tests to confirm pass.**

Run: `python -m pytest tests/tools/test_demo_full_system.py -k quickstart -v`
Expected: FAIL still (QUICKSTART.md not written) → proceed to Step 6, then this passes.

- [ ] **Step 6: Write `QUICKSTART.md` (prose + the exact fenced commands).**

Repo-root `QUICKSTART.md` — "Get running in 5 minutes": **Tier A** ("Ready to develop — no license needed"), **Tier B** ("Your first real part — needs a SOLIDWORKS seat"), **Where next**. Each command sits in a ```bash fenced block exactly as `quickstart_command_lines()` renders it (the Step 2 test enforces equality). State the honest split: Tier A alone means you can author + validate specs; Tier B is the live payoff. Re-run `python -m pytest tests/tools/test_demo_full_system.py -k quickstart -v` → PASS.

- [ ] **Step 7: Run the mode end-to-end (no SW) + add the README link.**

Run: `python tools/demo_full_system.py --quickstart --no-pause --sleep 0`
Expected: Tier A executes — `doctor` reports health (or "no seat" gracefully), `--list-kinds` + `--dry-run --lint` pass; Tier B + next steps print as instructions; exit 0; **no SW built or launched.**
Then add a `## Quickstart` block near the top of `README.md`: "Get running in 5 minutes → [QUICKSTART.md](QUICKSTART.md)" plus the one command `python tools/demo_full_system.py --quickstart`.

- [ ] **Step 8: Format, lint, commit.**

```bash
black tools/demo_full_system.py tests/tools/test_demo_full_system.py
flake8 tools/demo_full_system.py tests/tools/test_demo_full_system.py
git add tools/demo_full_system.py tests/tools/test_demo_full_system.py QUICKSTART.md README.md
git commit -m "feat(demo): --quickstart mode + synced QUICKSTART.md (5-min onboarding)"
```

---

## Task 9: SEAT-GATED — feasibility confirmation (Spikes 0, E, M) + capability-doc reconciliation

> **STOP: operator approval required. This is the FIRST task that touches SOLIDWORKS.** Run only on a clean single seat (one SW instance, no dirty docs), after the operator says go. Each spike flips one `BuildEnv` flag + its caption; no code rewrite either way.

**Files:**
- Modify: `tools/demo_full_system.py` (set the three feasibility flags to their confirmed values)
- Modify: `docs/known_limitations.md` **or** `docs/CAPABILITIES.md` (reconcile the mates claim)

- [ ] **Step 1: Confirm the seat is clean.**

`python -m ai_sw_bridge.cli.observe active_doc` and check no unexpected instance/dirty rig is open (the S1b single-seat discipline). If dirty, ask the operator to close it — do not force.

- [ ] **Step 2: Spike 0 — mates.** Build a throwaway 2-part assembly and add ONE `concentric` mate via `ai-sw-assembly` (propose→dry_run→commit, chained). Does it commit out-of-process and hold (`mate_count: 1`, interference sane)?
  - PASS → set `mates_proven=True`.
  - FAIL → keep `mates_proven=False`.

- [ ] **Step 3: Spike E — export.** With `export.json` and the wiring confirmed no-SW in Task 7 Step 2, run the live `ai-sw-build examples/demo_widget/export.json --no-dim --yes`. Do `demo_out/DemoExportBlock.step/.stl/.3mf` actually appear and open?
  - PASS → `export_block_wired=True`. FAIL → `False` (fallback to drawing PDF).

- [ ] **Step 4: Spike M — mutate on a `--no-dim` part.** Build `demo_baseplate` with `--no-dim --save-as demo_out/DemoBaseplate.SLDPRT`, then run the primary mutate beat (change a driving dimension). Does SW rebuild with the changed geometry (bbox changes)?
  - PASS → `mutate_drives_nodim=True` (primary beat). FAIL → `False` (locals-edit-rebuild fallback).

- [ ] **Step 5: Set the flags + reconcile the doc.**

Edit the `BuildEnv` defaults (or the flag-resolution function) in `demo_full_system.py` to the confirmed values. Then reconcile the capability doc per Spike 0: if mates work, correct the stale `known_limitations.md` §8 (“assembly mates out of scope”); if they don't, correct `CAPABILITIES.md`'s 13-mate advertisement to state mates are seat-gated/unproven out-of-process. The demo must not ship against a self-contradictory doc.

- [ ] **Step 6: Commit.**

```bash
black tools/demo_full_system.py
flake8 tools/demo_full_system.py
git add tools/demo_full_system.py docs/known_limitations.md docs/CAPABILITIES.md
git commit -m "chore(demo): pin feasibility flags from seat spikes; reconcile mates capability doc"
```

---

## Task 10: SEAT-GATED — full live rehearsal + record the GIF(s)

> **STOP: operator approval required. Clean single seat.** This is the recording run.

**Files:**
- Modify: `README.md` (embed the produced GIF paths)
- Create: GIF/asset files under `docs/assets/` (or the repo's asset convention)

- [ ] **Step 1: Preflight, no SW (final cheap gate).**

Run: `python tools/demo_full_system.py --chapter all --preflight-only --no-pause --sleep 0`
Expected: all widget specs dry-run clean, tour renders, every chapter's plan prints, exit 0.

- [ ] **Step 2: Full live rehearsal on the clean seat.**

Run: `python tools/demo_full_system.py --chapter all --no-pause --sleep 0`
Expected: every chapter completes; the 3 parts build; the mutate beat rebuilds (and, if `mates_proven`, the mate follows); assembly commits with interference = 0; `min_wall`/`mass`/`bbox`/`screenshot` read back; drawing + (if wired) exports land in `demo_out/`. Fix any live failure before recording. If a chapter genuinely can't pass on the seat, honestly narrow it (drop the feature/caption) rather than fake it. Also run `python tools/demo_full_system.py --quickstart --with-sw --no-pause --sleep 0` and confirm the quickstart **Tier B** live path (`--demo --no-dim --yes` build + `bounding_box`) completes on the seat — that is the only part of Task 8 that needs SW.

- [ ] **Step 3: Per-chapter rehearsal.**

Run each chapter alone (`--chapter part`, `assembly`, …) to confirm it stands as an independent clip.

- [ ] **Step 4: Record.**

Re-run with framing pauses/sleep (`--sleep 1.5`, pauses on) on the clean seat, capturing the GIF(s) with the operator's screen recorder. Produce: one hero `all` clip + short per-chapter clips. Caption each with the current version/tag (`v1.7.1`).

- [ ] **Step 5: Embed + commit.**

Place the GIF assets per the repo convention, fill the README GIF section, and commit.
```bash
git add README.md docs/assets/
git commit -m "docs(demo): add full-system demo GIFs to README"
```

---

## Self-Review (completed during planning)

**Spec coverage** — every spec section maps to a task: §1/§2 goal+decisions → whole plan; §3 principles → Global Constraints + trap-avoidance in Task 2; §4 chapters → Tasks 4–7; §5 widget → Task 2 (incl. the ~16–18 families enrichment loop); §4B quickstart (5-min onboarding, tiered, doc-synced) → Task 8; §6 mutate hero → Task 5 + Spike M (Task 9); §7 Spike 0 mates → Task 6 branch + Task 9; §8 architecture (`_demo_lib` extraction + parity) → Task 1; §9 verification (Spike → preflight → rehearsal → record) → Tasks 9–10; §10 deliverables → Tasks 1–10; §11 risks → the branch/fallback design + graceful-degrade; §12 deferred (export invocation) → **resolved**: schema-v2 `export:` block, Spike-E-gated (Task 7/9).

**Placeholder scan** — widget feature params are grounded in named reference examples or a cited handler-schema-read + dry-run loop (not "add appropriate features"); every code step shows real argv/JSON; the only intentional deferrals are the three seat-gated spikes and the GIF assets, all with explicit runnable procedures.

**Type/name consistency** — `DemoStep`/`CapabilitySection`/`run_step`/`_command_env`/`_module_argv` names match the extraction source; `BuildEnv` flags (`mates_proven`, `export_block_wired`, `mutate_drives_nodim`) are used consistently across Tasks 4/5/6/7/8 and pinned in Task 9; chapter keys (`tour/part/assembly/observe/drawing/export`) are identical everywhere.

**Open risk carried forward:** the exact field names for the enrichment features (draft/shell/countersink/ref_plane/cosmetic thread) and the mate/mutate CLI verbs are confirmed at implementation via `--help` + handler-schema reads + dry-run — the plan cites the exact files to read rather than guessing schema.
