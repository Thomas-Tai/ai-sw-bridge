# ai-sw-bridge

A semi-automated bridge that lets an AI assistant (Claude, ChatGPT, Codex, etc.)
drive SOLIDWORKS through the COM API.

## Goal

**Enable AI-driven build-parts-from-scratch via the SOLIDWORKS API.** The long-term target is an AI agent that reads a design guide, emits a declarative part spec, drives SOLIDWORKS to build the part, and verifies the result against the spec — all through diffable, version-controlled artifacts. See [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md) for the full architectural plan, field survey of existing SW automation tools, and v0.2 roadmap.

Today, ai-sw-bridge ships three concrete capabilities that build toward that goal:

- **Design-guide tuning** — verify that a SOLIDWORKS model actually matches what a written design guide claims, and propose corrections.
- **Parametric part creation (Path C)** — record a part once in SOLIDWORKS, parameterize the recorded macro against a `*_locals.txt` source of truth, and replay to regenerate the part with new dimensions.
- **Repeatable inspection** — feature errors, mate errors, equations, measurements, and screenshots are all available as plain JSON over a CLI.

Designed around a **Propose–Approve–Execute** discipline: every mutation runs as a dry-run with rollback first, surfaces a delta, and only commits after explicit approval. The AI never gets a `do-anything` button into your CAD model.

## Limitations (read before adopting)

Building AI-driven SOLIDWORKS automation is genuinely R&D, not a port of an existing solution. The hard constraints below shape what this project can and cannot do. See [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md) for the full survey.

**Platform and API**

- **Windows only.** SOLIDWORKS is Windows-only, and `pywin32` only supports Windows.
- **pywin32 late-binding only.** `EnsureDispatch`/makepy doesn't work on `SldWorks.Application` on most installs. Consequences: API methods with `OUT` parameters (e.g., `SelectByID2`, `GetErrorCode2`, `Save3`) are unreachable; zero-arg methods auto-invoke as properties. Every new API surface needs a sandbox test to confirm late-binding works. See [docs/known_gotchas.md](docs/known_gotchas.md).
- **SW state is invisible.** The SW state machine (active sketch, current selection, edit mode) lives in SW's UI memory; the API cannot reliably query it. Every operation must be designed to set state explicitly, not depend on whatever happened to be selected.
- **`RunMacro` requires binary `.swp`.** Plain-text `.bas` files are silently rejected. Path C accepts a one-time manual paste in lieu of full automation. Future binary-`.swp`-write support is unsolved.

**Performance and AI iteration**

- **COM is ~5-50ms per call.** A 30-feature part needs ~200 calls = 30-120 seconds end-to-end. AI iteration must be *plan-then-execute*, not call-by-call.

**What this project cannot do (today or soon)**

- **No fluent part-builder API yet.** No `part.box().hole()` chaining. Field survey (angelsix, xCAD, pyswx, codestack — see review doc) found that nobody in the SW community has built one in a decade, by choice. ai-sw-bridge v0.2 will offer JSON-spec→VBA-emitter as the AI-native alternative; this is unbuilt.
- **No automated face/edge selection.** SW selects faces via 3D coordinates, not "outboard face of feature X". The emitter has to compute coords from feature geometry; this is fragile and per-feature.
- **No fillets, sweeps, or lofts in v1 scope.** These need human judgment (which edges to fillet) or path geometry that doesn't map cleanly to declarative spec. Deferred.
- **No assemblies, no mates, no drawings.** Separate problem each. The current bridge handles part-level workflows only.
- **No "describe the part in English and get geometry."** The spec language is precise. The AI generates spec JSON, not freehand prose.
- **Will not replace CAD engineers.** This is a tool to make designers more productive and more reproducible. Hand-off to manufacturing still needs human review.

**Where this project meets the field consensus**

- The codestack-canonical pattern is **template + equation file**: build a part once in SOLIDWORKS UI, then drive parametric variations through `*_locals.txt`. ai-sw-bridge fully supports this via `ai-sw-observe` + `ai-sw-mutate`. If your need is variation rather than from-scratch generation, this is the recommended workflow today.

## Status

`v0.1.0` — first public release. Phases 1 (observe) and 2 (mutate) are end-to-end validated. Path C (recorded-macro parameterization) is validated for a single-extrude part on SOLIDWORKS 2024 (rev 32.1.0). v0.2 (JSON-spec→VBA-emitter for AI-driven part synthesis) is on the roadmap, gated on a Phase 0 de-risking spike — see [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md). See [CHANGELOG.md](CHANGELOG.md) and [docs/known_gotchas.md](docs/known_gotchas.md) for honest limitations.

## Quickstart

### Prerequisites

- **Windows** (SOLIDWORKS is Windows-only, and `pywin32` only supports Windows)
- **SOLIDWORKS** installed and running (tested on 2024; should work on 2021 SP5+)
- **Python 3.10+**

### Install

```powershell
# 1. Clone the repo
git clone https://github.com/Thomas-Tai/ai-sw-bridge.git
cd ai-sw-bridge

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install the package + dependencies
pip install -e .
```

After install, four CLI commands are on your PATH:

| Command | Purpose |
|---|---|
| `ai-sw-probe` | COM connectivity sanity check |
| `ai-sw-observe` | Read-only inspection (features, equations, mates, screenshots) |
| `ai-sw-mutate` | Propose-Approve-Execute mutations of `*_locals.txt` variables |
| `ai-sw-codegen` | Path C: parameterize a recorded `.swp` macro |

### Smoke test

Open SOLIDWORKS, then:

```powershell
ai-sw-probe
```

You should see something like:
```json
{
  "ok": true,
  "sw_revision": "32.1.0",
  "active_doc": null,
  "error": null
}
```

If you see `could not dispatch SldWorks.Application`, SOLIDWORKS isn't running or pywin32 wasn't registered properly. See [docs/known_gotchas.md](docs/known_gotchas.md).

## What it actually does

### Observe (read-only — safe to run at any time)

```powershell
ai-sw-observe active_doc
ai-sw-observe feature_errors
ai-sw-observe equations
ai-sw-observe mate_errors                              # assemblies only
ai-sw-observe screenshot                               # 640x360 PNG to ./captures/
ai-sw-observe screenshot --width=1280 --height=720     # detail
ai-sw-observe measure                                  # uses current SW UI selection
```

Each command prints one JSON object to stdout. Exit code is non-zero on failure.

### Mutate (Propose–Approve–Execute)

Your active SOLIDWORKS part must have a linked `*_locals.txt` equation file (Tools > Equations > Link to file). Then:

```powershell
# 1. Propose a change (no SW touch yet)
ai-sw-mutate propose --var=PART_DIAMETER --new_value=30.0
# -> { "proposal_id": "abc123def456", ... }

# 2. Dry-run: apply, rebuild, capture before/after, roll back
ai-sw-mutate dry_run --proposal_id=abc123def456

# 3. Commit (only allowed after dry_run_ok)
ai-sw-mutate commit --proposal_id=abc123def456

# 4. Undo most recent commit if needed
ai-sw-mutate undo_last_commit
```

Proposals are persisted as JSON files in `./proposals/` so an AI agent can resume across multiple sessions.

### Codegen — parametric part creation (Path C)

1. **Record a part in SOLIDWORKS** once via *Tools → Macro → Record*. Save as `recorded.swp`.
2. **Write a tiny spec JSON** mapping the recorded SW dimensions to your variable names.
3. **Run the parameterizer**:
   ```powershell
   ai-sw-codegen parameterize examples/minimal_cylinder/recorded.swp examples/minimal_cylinder/spec.json
   ```
4. **Paste the generated `.bas` into VBE and press F5** — the new part will be created with all dimensions bound to your `*_locals.txt` source of truth.

See [examples/minimal_cylinder/README.md](examples/minimal_cylinder/README.md) for a worked example.

## Why this design

- **AI agents need verifiable, reversible operations.** Every mutation is `propose → dry-run → review → commit`. Rollback verification reads the file back from disk and compares against the snapshot.
- **The `*_locals.txt` file is the single source of truth.** Editing variables in SW Equation Manager directly is fragile (the link can overwrite them). We always edit the file, then reload + rebuild.
- **Late-binding pywin32 only.** `EnsureDispatch`/makepy doesn't work against SldWorks.Application on most installs. We accept the late-binding tax (some APIs unreachable, see gotchas) and work around it.
- **JSON in/out for everything.** Trivially scriptable from any AI agent harness — Claude Code, OpenAI Assistants, custom MCP servers, plain shell scripts.

## Layout

```
ai-sw-bridge/
├── src/ai_sw_bridge/        # the Python package
│   ├── sw_com.py            # SldWorks dispatch + helpers
│   ├── observe.py           # Phase 1: read-only tools
│   ├── mutate.py            # Phase 2: Propose-Approve-Execute
│   ├── locals_io.py         # *_locals.txt parser + atomic writer
│   ├── parameterize.py      # Path C: recorded-macro parameterizer
│   └── cli/                 # CLI entry points (one per command)
├── docs/
│   ├── architecture.md                     # phases, design rationale (v0.1)
│   ├── ai_driven_architecture_review.md    # field survey + v0.2 plan
│   ├── tools_reference.md                  # every CLI command, every flag
│   └── known_gotchas.md                    # the things we learned the hard way
├── examples/
│   └── minimal_cylinder/    # worked example (record → parameterize → run)
├── USAGE.md                 # detailed workflows
├── CHANGELOG.md
├── pyproject.toml
└── requirements.txt
```

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

SOLIDWORKS API patterns reference: [CodeStack](https://www.codestack.net/solidworks-api/). The Path C dim-binding fix (`EquationMgr.Add2` 3-arg form) came from their `document/dimensions/add-equation/` example.
