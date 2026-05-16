# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
  on SW 2024 SP1 in our testing. MMP-scale builds need ~15 manual clicks.
  Full investigation in `spikes/phase0/MMP_DEBUG_SESSION.md`.
- **Face-based sketch origins must lie on material**, not inside a void.
  The MMP design pattern (flange recess concentric with through-hole) hits
  this v1 limitation. Workaround sketched: add a feature type that sketches
  on the underlying plane instead. Deferred.
- **MMP example is partial**: 5/10 features build successfully end-to-end
  including the first cut feature ever produced via this pipeline. Feature 6
  (`Cut_FlangeRecess`) hits the limitation above.

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
