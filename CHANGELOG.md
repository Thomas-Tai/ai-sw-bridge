# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
