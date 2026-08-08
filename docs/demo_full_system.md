# Full-system demo (`tools/demo_full_system.py`)

A chaptered, recordable walkthrough of the bridge building a small product
end-to-end -- **tour -> part -> assembly -> observe -> drawing -> export** --
against a purpose-built "pillow-block" widget bundled in
`examples/demo_widget/`. It is the GIF-showcase companion to
`tools/demo_no_dim_showcase.py` (the single-part tour). Design background:
`docs/superpowers/specs/2026-08-08-ai-sw-bridge-full-system-demo-design.md`.

## The six chapters

| Chapter | What it does | No-SW? |
|---|---|---|
| `tour` | Introspects the live build surface (`ai-sw-build --list-kinds`, `pyproject.toml` `[project.scripts]`, the `ai-sw-observe` subcommand list) and prints a capability summary. Always runs first in `--chapter all`. | Yes |
| `part` | Builds the widget's 3 parts (`demo_baseplate`, `demo_shaft`, `demo_bearing_block`) via `ai-sw-build --no-dim --yes --save-as`, bbox-checks each, then the headline beat: resize `BORE_DIA` and rebuild (via `ai-sw-mutate` once Spike M confirms it drives a `--no-dim` part, else a `demo_out/reparam/` copy-and-rebuild fallback). | No |
| `assembly` | Resolves `examples/demo_widget/assembly.json` against the parts just built and runs `ai-sw-assembly propose/dry_run/commit`. Title/caption flip on `BuildEnv.mates_proven` (Spike 0): `"assembly (with mates)"` once mates are seat-confirmed, else the honest `"component placement / layout"`. | No |
| `observe` | DFM read-backs against the assembly: `ai-sw-observe interference` (expect 0), `feature_statistics`, `mate_errors`, and a `screenshot`. | No |
| `drawing` | Authors a standalone drawing spec at runtime and runs `ai-sw-drawing propose/dry_run/commit`, producing `demo_out/DemoWidget.SLDDRW`. | No |
| `export` | Caption flips on `BuildEnv.export_block_wired` (Spike E). **Wired:** builds `examples/demo_widget/export.json` -- a schema-v2 spec with a `export:` block (STEP AP-214 / binary STL / 3MF) -- via `ai-sw-build --no-dim --yes`, then lists the produced files in `demo_out/`. **Fallback:** a single reminder step naming the drawing chapter's `.SLDDRW` as this build's actual downstream artifact, noting that STEP/STL/3MF ship via the spec `export:` block but are seat-gated. | No (wired branch is seat-gated at run time; fallback branch is not) |

Run `python tools/demo_full_system.py --list-chapters` to print this table
from the live code (titles/captions there reflect whatever `BuildEnv` flags
are wired at the time).

## Exact commands

```bash
# Whole tour, one chapter after another (the hero recording):
python tools/demo_full_system.py --chapter all

# Or run any chapter in isolation for a short, focused clip:
python tools/demo_full_system.py --chapter tour
python tools/demo_full_system.py --chapter part
python tools/demo_full_system.py --chapter assembly
python tools/demo_full_system.py --chapter observe
python tools/demo_full_system.py --chapter drawing
python tools/demo_full_system.py --chapter export
```

`--chapter` defaults to `all`. `tour` always runs first regardless of which
chapter you asked for (it is the capability-surface intro), unless you pass
`--tour-only`.

**Chapter order matters for a standalone run.** `assembly`/`observe`/
`drawing`/`export` all assume the parts already exist in `demo_out/` (built
by the `part` chapter) -- running one of them alone right after a fresh
`wipe_demo_out()` will fail to find its inputs. `--chapter all` runs them in
the right order in one process; a single-chapter clip should be recorded
right after (or as part of) an `all` run, not from a bare `demo_out/`.

## Recording / rehearsal flags

| Flag | Effect |
|---|---|
| `--no-pause` | Skip the `Press Enter to continue...` prompts between chapters -- required for CI and unattended recording. |
| `--sleep <seconds>` | Pause this long after printing each command's caption before running it (default `0.8`); `--sleep 0` for CI. |
| `--compact` | Use the GIF-friendly capability-count summary in the `tour` chapter instead of the full per-function listing. |
| `--tour-only` | Run only the `tour` chapter, then stop -- no SW needed. |
| `--preflight-only` | No-SW "plan" view: construct every remaining chapter's steps (pure, no filesystem/SW touch) and print what *would* run, without running any of it. |
| `--list-chapters` | Print the chapter table (key + caption) and exit. |

## Where outputs land

- **`demo_out/`** (repo root, gitignored, wiped at the start of every run):
  built parts (`*.SLDPRT`), the assembly (`DemoWidget.SLDASM`), the runtime
  assembly/drawing specs, the drawing (`DemoWidget.SLDDRW`), the reparam
  fallback's resized copy, and -- once the export chapter is wired -- the
  exported `*.step`, `*.stl`, `*.3mf` files.
- **Screenshots** (`observe screenshot` step): `AI_SW_BRIDGE_CAPTURES` env
  var if set, else `./captures/` relative to the working directory the
  script was launched from (also gitignored).
- Committed inputs -- `examples/demo_widget/**/spec.json`, `locals.txt`,
  `assembly.json`, `export.json` -- are never written to by the demo script;
  only `demo_out/` is scratch.

## Seat-gate note

`tour`, `--preflight-only`, and `--list-chapters` are the only paths that
never touch a live SOLIDWORKS session -- they read source/introspect the CLI
surface or construct-but-not-run each chapter's steps. Every live build,
observe, assembly, drawing, and export step needs an attached SOLIDWORKS
seat (single-instance discipline, same as the rest of this workspace); run
`ai-sw-doctor` first to confirm the seat/COM path is healthy.

## The `export` chapter's schema_v2 flag

The wired `export` chapter builds a **schema-v2** spec
(`examples/demo_widget/export.json`, `"schema_version": 2` with an
`"export": [...]` block). Schema v2 is gated behind the `schema_v2` feature
flag, and (Spike E, 2026-08-08) the build CLI's `--enable-flag schema_v2`
does **not** reach the spec validator -- `spec/validator.py::_v2_enabled()`
re-resolves flags from the environment only, ignoring CLI overrides. The
reliable enable is the `AI_SW_BRIDGE_FLAG_SCHEMA_V2=1` environment variable.
`demo_full_system.py`'s `main()` sets this automatically for every chapter
step's subprocess environment (harmless elsewhere: v1 part specs always
route to the v1 schema regardless of the flag, and assembly/drawing are
separate spec kinds entirely). If you invoke the export build directly,
outside the demo script, set the env var yourself:

```bash
# bash / Git Bash
AI_SW_BRIDGE_FLAG_SCHEMA_V2=1 python -m ai_sw_bridge.cli.build examples/demo_widget/export.json --no-dim --yes
```

```powershell
# PowerShell
$env:AI_SW_BRIDGE_FLAG_SCHEMA_V2 = "1"
python -m ai_sw_bridge.cli.build examples/demo_widget/export.json --no-dim --yes
```

The no-SW half of this is verifiable without a seat:

```bash
AI_SW_BRIDGE_FLAG_SCHEMA_V2=1 python -m ai_sw_bridge.cli.build examples/demo_widget/export.json --dry-run --lint
```
