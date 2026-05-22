# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.10.0] - 2026-05-22

### Added — v0.10 reliability + DX bundle

- **`--lint` flag** for `ai-sw-build`. Semantic checks beyond validation:
  unconsumed sketches, missing `center.z` on Top Plane centerlines,
  `center.z` thread-through, and face references on parents without clean
  orthogonal faces. Exit code 6 on findings.
- **`--verify-mass` flag** for `ai-sw-build`. Per-feature CreateMassProperty
  volume check against `_expect` blocks. Fail-fast on mismatch.
- **`_expect` schema** for per-feature postcondition expectations
  (`mass_delta_mm3`, `tolerance_mm3`). Validated before `_strip_comments`.
- **`--log-level` flag** for `ai-sw-build` (debug/info/warning/error);
  `--verbose` is the shorthand for `--log-level debug`.
- **`build_metrics.json` sidecar** written next to a `--save-as` part:
  per-feature build timings, total time, mode, binding/mass-check counts.
- **`build_time_s`, `mode`, `feature_metrics`** fields in BuildResult.
- **Structured logging** via Python stdlib `logging` in builder.py.
- **`--dry-run`** now reports a `locals_resolved` count.
- **Type stubs** for 21 COM interfaces in `src/ai_sw_bridge/_sw_stubs/`,
  with a README on why late binding is load-bearing.
- **Pre-commit framework**: `.pre-commit-config.yaml` (black, flake8, mypy,
  spec-lint) plus `mypy.ini` and `.flake8`. Enable with `pre-commit install`.
- **Doc-coverage gate**: `tools/doc_coverage_gate.py`, wired as a CI step;
  checks all 16 schema types are documented in spec_reference.md.
- **Golden volume regression**: `tools/regression_check.py --capture/--check`
  builds each example with `--verify-mass` and records total part volume.
- **SW version floor**: `get_sw_app()` fails fast below SW 2024 SP1
  (`SW_VERSION_VERIFIED` in `sw_com.py`).
- **PM-pane dismiss spike**: `spikes/v0_10/spike_p16_pm_dismiss.py`.
- **New docs**: `docs/sketch_axes.md`, `docs/com_failure_modes.md`,
  `docs/deprecation_policy.md`, `docs/handoff_template.md`,
  `examples/drive_roller/README.md`.
- **spec_reference.md**: added `revolve_boss`, `revolve_cut`,
  `circular_pattern`, `simple_hole` sections; `center.z` and `centerline`
  docs; `_expect` postcondition docs; lint checks section.
- **AGENTS.md**: quickstart, 16-type feature table, late-binding explanation,
  session handoff + memory enforcement rules.

### Fixed — v0.10 live-SW validation

- **`--verify-mass` was dead on arrival**: `CreateMassProperty()` was called
  with parens, but pywin32 late binding auto-invokes the zero-arg COM method
  on attribute access, so `()` called the returned object and raised
  DISP_E_MEMBERNOTFOUND. Drop the parens.
- **Relative `locals` paths**: the builder resolved them against the process
  CWD while the validator used the spec directory, so `minimal_cylinder_v2`
  passed validation then failed the build. Normalized to absolute at the CLI
  entry point.
- **`examples/drive_roller/spec.json`**: 4 of 5 `_expect.mass_delta_mm3`
  values were mis-authored (uncheckable until `--verify-mass` worked).
  Corrected to SW-measured, analytically cross-checked actuals.

### Changed

- The pre-commit hook is now the standard `pre-commit` framework
  (`.pre-commit-config.yaml`); the earlier bespoke `tools/pre_commit_hook.py`
  was removed in favor of it.

### Added — `ai-sw-build --no-dim` (zero-popup build mode)

- **`--no-dim` flag** for `ai-sw-build`. When set, every `{"rhs": "..."}`
  reference in the spec is resolved against `spec['locals']` in Python
  upfront (literal mm value substituted), and the builder skips every
  `AddDimension2` call and the entire `EquationMgr.Add2` binding pass.
  Eliminates the ~16 manual ticks per MMP build that the Modify-Dimension
  popup imposes on SW 2024 SP1.
- New helpers in `src/ai_sw_bridge/spec/builder.py`:
  `_load_locals_map`, `_eval_rhs`, `_resolve_rhs_in_spec`. Handle quoted
  variable refs (`"VAR"`), arithmetic, and recursive locals (one var
  referencing another). Cycles raise; unknown refs raise KeyError.
- `BuildContext` gained a `no_dim: bool` field; every per-feature
  handler in `builder.py` gates its `AddDimension2` block on
  `if not ctx.no_dim`. Geometry creation paths are unchanged.

**Trade-off**: the resulting SLDPRT has NO equation link to `locals.txt`.
Editing `locals.txt` will NOT propagate to existing parts; user must
re-run `ai-sw-build`. The locals file is still the single source of
truth — it's just resolved at build time instead of runtime.

**Validation** (SW 2024 SP1):
- Cylinder `--no-dim`: 1.72s, 0 ticks, Ø25 × 80mm verified
- MMP `--no-dim`: ~3s, 0 ticks, 10/10 features, screenshot-verified
  (50×50 plate, Ø12 coupler, Ø20.5 flange recess, 2× Ø3.2 motor holes,
  2× Ø3.4 frame holes, all positioned correctly)

**Why this exists**: three separate community-canonical workarounds for
the AddDimension2 popup were investigated in this session — all toggle-
based, all failed empirically on this build via pywin32:
- Spike I (prior): toggle 8 (`swInputDimValOnCreate`) — confirmed dead
- Spike M: toggle 78 (`swSketchEnableOnScreenNumericInput`-class) — confirmed dead
- Spike O: probed whether SW auto-creates queryable D1/D2 internal
  params without AddDimension2 — none found, confirming linkability is
  unobtainable without the popup. `EquationMgr.Add2` needs a real named
  dim to target.

The toggle works inside SW's VBA editor (the context all the community
advice assumes); it does not work from external pywin32 COM clients on
SW 2024 SP1. `--no-dim` is the only zero-popup path that doesn't require
a VBA-macro round-trip.

### Added — v0.2 declarative build pipeline (in progress)

- **`ai-sw-build`** — new CLI that takes a JSON spec and drives SOLIDWORKS via
  direct-COM to produce the part. Cylinder example builds end-to-end with
  parametric bindings (Ø25 × 80mm, 2 dims bound to `*_locals.txt`).
- **Spec schema** (`src/ai_sw_bridge/spec/schema.py`) — 7 feature types:
  `sketch_rectangle_on_plane`, `sketch_circle_on_plane`, `sketch_circle_on_face`,
  `sketch_circles_on_face`, `boss_extrude_blind`, `cut_extrude_through_all`,
  `cut_extrude_blind`. Length fields accept literal numbers or
  `{"rhs": "<expression>"}` for parametric binding.
- **Spec validator** (3 layers): jsonschema → strict-topological feature refs
  → locals-file variable references.
- **Direct-COM builder** (`src/ai_sw_bridge/spec/builder.py`) — feature dispatch,
  4-call `EquationMgr` link, plane-and-face sketch creation, `FeatureExtrusion2`
  for bosses, `FeatureCut4` (27-arg form) for cuts.
- **CHM-verified API reference** — `docs/api_reference.md`, `docs/api_reference.json`,
  `src/ai_sw_bridge/sw_types.py` (auto-generated enum constants + runtime
  arg-count assertion). Sourced from decompiled `sldworksapi.chm`. Three
  tools support the workflow: `tools/chm_extract.py`, `tools/gen_api_markdown.py`,
  `tools/gen_sw_types.py`.

### Fixed

- **`FeatureCut4` arg count** — was 24 in builder; CHM says 27. The missing
  args were `AutoSelectComponents` (22), `PropagateFeatureToParts` (23),
  `OptimizeGeometry` (27). Spike E7 verified the 27-arg form produces a
  real "Cut-Extrude1" feature. Earlier "cuts unreachable via pywin32"
  conclusion (commit `cad76c2`) was wrong.
- **`swEndCondThroughAll` enum value** — was 4 in builder; CHM says 1. The
  value 4 is `swEndCondUpToSurface` (deprecated, requires a target). This
  is why through-all cuts returned None even when the call succeeded.
- **Face selection robustness** — face-based sketches in MMP would fail when
  the parent face had material cut away at the center by an earlier feature.
  Now tries center first, then 1/5/15mm offsets in the tangent plane.

### Known limitations (v0.2)

- **`AddDimension2` opens a Modify Dimension popup** that requires manual
  ticking. The `swInputDimValOnCreate` toggle (ID 8) does not suppress it
  on SW 2024 SP1 in our testing. MMP-scale builds need ~16 manual clicks.
  Full investigation in `spikes/phase0/MMP_DEBUG_SESSION.md`.
- **Only +/-z faces supported** for face-based sketches in v1. +/-x and +/-y
  faces of extrusions are not yet wired. Adding them is mechanical (extend
  `_select_extrude_face` and the X-mirror logic).
- **SW emits a "warning beep" each time the builder closes a sketch.**
  Caused by sketches being under-constrained (geometry-relation-wise) at
  close time. We bind values numerically via `EquationMgr.Add2`, which
  fully determines the resulting part, but SW prefers full geometric
  constraint (e.g. coincident-to-origin relations). The beep is transient
  and leaves no error in the tree (`ai-sw-observe feature_errors` returns
  empty after a successful MMP build). Adding `sgFIXED` or coincident
  relations per sketch is a future polish item.

### Fixed (continued)

- **Placeholder dim values vs target geometry**: previously all parametric
  bindings were applied AFTER all features were built. This caused MMP's
  flange recess (parametric Ø20.5mm with placeholder Ø6mm) to fail its cut
  because the placeholder circle sat entirely inside the existing Ø12mm
  through-hole at the time `FeatureCut4` ran. **Fix**: interleave bindings
  -- apply each feature's Add2 and rebuild immediately after the feature is
  built, so downstream geometry sees target sizes.
- **-z face X-axis mirror**: SW mirrors the sketch X axis when viewing a
  -z face from outside. `CreateCircle` uses sketch-local coords but
  `SelectByID("SKETCHSEGMENT",...)` uses part-frame. On -z faces with
  off-origin circles, the SKETCHSEGMENT click missed the circle entirely.
  **Fix**: mirror u in the click coords for -z (-x, -y) faces.
- **Rectangle dim-resize was asymmetric**: `CreateCornerRectangle` makes an
  unconstrained rect; dim binding could anchor it at an arbitrary corner
  rather than the origin, putting all downstream features off-center.
  **Fix**: use `CreateCenterRectangle` which anchors via center diagonals.

### MMP demonstration (the v0.2 milestone)

The Motor Mount Plate from S1b conveyor §13.4 now builds 10/10 features
end-to-end from JSON spec via `ai-sw-build`:
  SK_PlateSlab (center rect, 50×50) → Extrude_Plate (boss blind 5mm) →
  SK_CouplerHole (circle on -z face) → Cut_CouplerHole (through-all) →
  SK_FlangeRecess (circle on +z) → Cut_FlangeRecess (blind 1mm) →
  SK_MotorHoles (2 circles on +z at ±12.5mm) → Cut_MotorHoles (through-all) →
  SK_FrameHoles (2 circles on -z at ±15mm) → Cut_FrameHoles (through-all)

7 parametric bindings to `s1b_conveyor_locals.txt` applied via
`EquationMgr.Add2`. Geometry verified centered via the `ai-sw-observe
screenshot` capture.

## [0.1.0] - 2026-05-13

Initial release. Extracted from a private prototype after validating end-to-end
parametric part creation against a real SOLIDWORKS 2024 install.

### Added

- **Phase 1 — Observation tools** (read-only, run freely):
  - `ai-sw-probe` — COM connectivity sanity check
  - `ai-sw-observe active_doc | feature_errors | equations | screenshot | measure | mate_errors`
- **Phase 2 — Mutation tools** (Propose-Approve-Execute, dry-run + rollback):
  - `ai-sw-mutate propose | dry_run | commit | undo_last_commit`
  - Locals-file I/O with exclusive locking and atomic writes
- **Path C — Macro record + parameterize** (parametric part creation):
  - `ai-sw-codegen parameterize <recorded.swp> <spec.json>` produces a `.bas`
    that, when pasted into SolidWorks VBE and run, creates the recorded part
    with dimensions bound to a `*_locals.txt` source of truth.

### Known limitations

- `RunMacro` / `RunMacro2` cannot consume plain-text `.swp` files — the user
  must paste the generated `.bas` into the SOLIDWORKS VBA editor and press F5.
- Recorded macros embed runtime-generated feature names (e.g. `Sketch2` if
  the doc already had `Sketch1`). Always record from a fresh-doc state.
- The "Modify dimension" popup interrupts replay; user dismisses with Enter.
  A future release will inject `SetUserPreferenceToggle swInputDimValOnCreate`
  to suppress it automatically.
