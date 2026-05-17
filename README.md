# ai-sw-bridge

A semi-automated bridge that lets an AI assistant (Claude, ChatGPT, Codex, etc.)
drive SOLIDWORKS through the COM API.

## What it does

Today, ai-sw-bridge ships **four capabilities** along a continuum from observation to AI-driven creation:

| Capability | CLI | What it gives you |
|---|---|---|
| **Inspection** | `ai-sw-observe` | Read features, equations, mates, screenshots as JSON. Safe to run any time. |
| **Variable mutation** | `ai-sw-mutate` | Propose–Approve–Execute changes to `*_locals.txt` variables. Dry-run + rollback before commit. |
| **Recorded-macro parameterization** (Path C) | `ai-sw-codegen` | Record once in SW UI, parameterize against `*_locals.txt`, replay to regenerate. |
| **Declarative part synthesis** (v0.2, in progress) | `ai-sw-build` | Take a JSON spec describing features + parametric bindings, drive SW via direct-COM to produce the part. **AI-native authoring path.** |

The long-term target is the fourth capability: an AI agent reads a design guide, emits a JSON part spec, drives SOLIDWORKS to build it, and verifies the result — all through diffable, version-controlled artifacts. Phases 0 and 1 are landed; MMP (motor mount plate) is a partial end-to-end demonstration. See [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md) for the full plan.

Designed around a **Propose–Approve–Execute** discipline: every mutation runs as a dry-run with rollback first, surfaces a delta, and only commits after explicit approval. The AI never gets a `do-anything` button into your CAD model.

## Current status (2026-05-17)

**v0.1 capabilities — production-validated** on SOLIDWORKS 2024 SP1:
- `ai-sw-probe`, `ai-sw-observe`, `ai-sw-mutate` end-to-end working
- Path C parameterization verified on a single-extrude cylinder

**v0.2 capabilities — Phase 1 GREEN:**
- Phase 0 spikes: **GREEN** — direct-COM late-binding is viable for the v0.2 architecture
- Phase 1 (JSON-spec builder): **GREEN**
  - Cylinder example builds end-to-end with parametric bindings
  - **Motor Mount Plate (MMP) builds 10/10 features end-to-end** with 7 parametric bindings (50×50 plate with concentric Ø12 coupler hole + Ø20.5 flange recess + pairs of motor/frame holes at ±15mm). Geometry verified centered.
- **CHM-verified API reference** ([docs/api_reference.md](docs/api_reference.md)) — 23 in-use SW methods + 5 enums extracted from the official `sldworksapi.chm`, with arg-count assertion at runtime

## Why this matters

**Building AI-driven SOLIDWORKS automation is genuinely R&D.** The SW community has spent a decade building add-in frameworks (angelsix, xCAD, codestack) and modify-only wrappers (pyswx, pySldWrap), but nobody has shipped a declarative part-builder. ai-sw-bridge's v0.2 work is that gap — see the field survey in [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md).

What makes it tractable now:

- **AI assistants are good at JSON.** The spec is pure data, not VBA prose. The AI writes spec, the bridge runs it.
- **Direct-COM via pywin32 late-binding works** for most of the SW API on the builds we've tested. The lesson "cuts don't work" was wrong (see commit `c560e97`) — they work fine once you pass all 27 args FeatureCut4 expects, not the 24 the older docs imply.
- **Authoritative API signatures.** When an SW call returns `PARAMNOTOPTIONAL`, the very first check is the arg count per `sldworksapi.chm`. We codified that lookup; see [tools/chm_extract.py](tools/chm_extract.py).

## Limitations (read before adopting)

**Platform and API**

- **Windows only.** SOLIDWORKS is Windows-only, and `pywin32` only supports Windows.
- **pywin32 late-binding only.** `EnsureDispatch`/makepy doesn't work on `SldWorks.Application` on most installs. Consequences: API methods with `OUT` parameters or COM-interface args (e.g. `SelectByID2`'s `Callout`, `AddSpecificDimension`'s `Error`) are unreachable. Every new API surface needs sandbox confirmation. See [docs/known_gotchas.md](docs/known_gotchas.md).
- **SW state is invisible.** The SW state machine (active sketch, current selection, edit mode) lives in SW's UI memory; the API cannot reliably query it. Every operation must set state explicitly.
- **`AddDimension2` opens a Modify Dimension popup** that requires manual ticking in parametric mode. The `swInputDimValOnCreate` (toggle 8) and `swSketchEnableOnScreenNumericInput`-class (toggle 78) preferences empirically don't suppress it on SW 2024 SP1 via pywin32. Documented in [spikes/phase0/MMP_DEBUG_SESSION.md](spikes/phase0/MMP_DEBUG_SESSION.md). **Workaround shipped: `ai-sw-build --no-dim`** resolves `{rhs}` references against `locals.txt` in Python upfront and builds geometry at literal target size, skipping every `AddDimension2` call. Trade-off: the resulting SLDPRT has no equation link to `locals.txt` (editing locals requires re-running `ai-sw-build`). MMP `--no-dim` builds in ~3s with 0 manual ticks vs. ~60s + ~16 ticks in parametric mode.

**Performance and AI iteration**

- **COM is ~5-50ms per call.** A 30-feature part needs ~200 calls = 30-120 seconds end-to-end. AI iteration must be *plan-then-execute*, not call-by-call.

**Scope (v0.2 today)**

- **No fluent part-builder API.** No `part.box().hole()` chaining. v0.2 is JSON-spec → direct-COM. The AI generates spec JSON, not freehand prose.
- **Limited face/edge selection.** SW selects faces via 3D coordinates, not "outboard face of feature X". The builder computes coords from feature geometry and tries small offsets as a fallback when an earlier feature has cut material at the center. Fragile in edge cases like concentric holes.
- **No fillets, sweeps, lofts.** Need human judgment (which edges) or path geometry that doesn't map cleanly to declarative spec. Deferred.
- **No assemblies, no mates, no drawings.** Separate problem each. The current bridge handles part-level workflows only.
- **No "describe the part in English and get geometry."** The spec language is precise. The AI generates spec JSON.
- **Will not replace CAD engineers.** This is a tool to make designers more productive and more reproducible.

## Quickstart

### Prerequisites

- **Windows** (SOLIDWORKS is Windows-only, and `pywin32` only supports Windows)
- **SOLIDWORKS** installed and running (tested on 2024 SP1; should work on 2021 SP5+)
- **Python 3.10+** (tested on 3.14)

### Install

```powershell
git clone https://github.com/Thomas-Tai/ai-sw-bridge.git
cd ai-sw-bridge

python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

After install, **five** CLI commands are on your PATH:

| Command | Purpose |
|---|---|
| `ai-sw-probe` | COM connectivity sanity check |
| `ai-sw-observe` | Read-only inspection (features, equations, mates, screenshots) |
| `ai-sw-mutate` | Propose–Approve–Execute mutations of `*_locals.txt` variables |
| `ai-sw-codegen` | Path C: parameterize a recorded `.swp` macro |
| `ai-sw-build` | **v0.2**: build a part from a JSON spec via direct-COM |

### Smoke test

Open SOLIDWORKS, then:

```powershell
ai-sw-probe
```

You should see:
```json
{
  "ok": true,
  "sw_revision": "32.1.0",
  "active_doc": null,
  "error": null
}
```

## Five-minute tour

### 1. Inspect a model (safe, read-only)

```powershell
ai-sw-observe active_doc
ai-sw-observe feature_errors
ai-sw-observe equations
ai-sw-observe screenshot --width=1280 --height=720
ai-sw-observe mate_errors                              # assemblies only
ai-sw-observe measure                                  # uses current SW UI selection
```

Each command prints one JSON object to stdout. Exit code is non-zero on failure.

### 2. Mutate a parametric variable (Propose–Approve–Execute)

Your active SOLIDWORKS part must have a linked `*_locals.txt` equation file:

```powershell
ai-sw-mutate propose --var=PART_DIAMETER --new_value=30.0
# -> { "proposal_id": "abc123def456", ... }

ai-sw-mutate dry_run --proposal_id=abc123def456     # apply, rebuild, capture, roll back
ai-sw-mutate commit  --proposal_id=abc123def456     # only allowed after dry_run_ok
ai-sw-mutate undo_last_commit
```

Proposals are persisted as JSON in `./proposals/` so an AI agent can resume across sessions.

### 3. Build a part from a JSON spec (v0.2, direct-COM)

Open a fresh blank Part in SOLIDWORKS, then:

```powershell
ai-sw-build examples/minimal_cylinder_v2/spec.json
```

The spec is a small JSON file declaring features and their parametric bindings:

```json
{
  "schema_version": 1,
  "name": "MyCylinder",
  "locals": "C:\\path\\to\\globals_locals.txt",
  "features": [
    {"type": "sketch_circle_on_plane", "name": "SK_Body", "plane": "Front",
     "diameter": {"rhs": "\"PART_DIAMETER\""}},
    {"type": "boss_extrude_blind", "name": "Extrude_Body", "sketch": "SK_Body",
     "depth": {"rhs": "\"PART_LENGTH\""}}
  ]
}
```

The builder:
1. Validates the spec (schema + topological references + locals-file vars)
2. Creates a fresh part via `NewDocument`
3. Links the locals file (4-call sequence for `EquationMgr`)
4. Walks features in order; emits direct-COM calls for each
5. Binds parametric dims via `EquationMgr.Add2`

Output is JSON with `features_built` and `bindings_added`. See [examples/minimal_cylinder_v2/](examples/minimal_cylinder_v2/) and [examples/motor_mount_plate/](examples/motor_mount_plate/) for worked examples.

**Note**: each `AddDimension2` call opens a Modify Dimension popup that requires manual tick. A 10-feature MMP build needs ~15 clicks. Known limitation; see [spikes/phase0/MMP_DEBUG_SESSION.md](spikes/phase0/MMP_DEBUG_SESSION.md).

### 4. Parametric replay of a hand-recorded part (Path C)

For shapes that the v0.2 spec language doesn't yet cover (fillets, sweeps, complex profiles), Path C lets you record once in SW UI and replay parameterized:

```powershell
# Record a part in SW (Tools → Macro → Record). Save as recorded.swp.
# Write a tiny spec mapping the recorded dims to your variables.
ai-sw-codegen parameterize examples/minimal_cylinder/recorded.swp examples/minimal_cylinder/spec.json
# Paste the generated .bas into VBE, F5.
```

See [examples/minimal_cylinder/README.md](examples/minimal_cylinder/README.md).

## API reference (CHM-verified)

The bridge keeps an authoritative reference of every SW API it calls, extracted from `sldworksapi.chm`:

- [docs/api_reference.md](docs/api_reference.md) — human-readable: signatures, arg docs, enum values, availability
- [docs/api_reference.json](docs/api_reference.json) — machine-readable

### Supported SW API surface

24 methods across 7 interfaces and 5 enums. Each call's exact arg count is asserted at runtime by [src/ai_sw_bridge/sw_types.py](src/ai_sw_bridge/sw_types.py) — drift between CHM and our calls fails fast with the expected signature in the error message. Full per-method arg lists are in [docs/api_reference.md](docs/api_reference.md).

**`ISldWorks`** (app-level)

| Method | Args | Purpose |
|---|---|---|
| `NewDocument` | 4 | Create a new part/asm/drw from a template |
| `GetUserPreferenceStringValue` | 1 | Read string preference (e.g. default template path) |
| `GetUserPreferenceToggle` | 1 | Read boolean preference |
| `SetUserPreferenceToggle` | 2 | Write boolean preference |

**`IModelDoc2`** (document-level)

| Method | Args | Purpose |
|---|---|---|
| `SelectByID` | 5 | Select an entity by name + 3D coord (legacy 5-arg form; `SelectByID2` Callout arg is unreachable via late-binding) |
| `ClearSelection2` | 1 | Drop the current selection |
| `AddDimension2` | 3 | Add a display dimension at a leader position |
| `FeatureByPositionReverse` | 1 | Get the Nth-from-last feature (used to grab the just-built feature for rename) |
| `EditRebuild3` | 0 | Rebuild only stale features in the active config (auto-invoked as property) |
| `EditUndo2` | 1 | Undo N actions |
| `Parameter` | 1 | Get a named dim parameter (`"D1@Sketch1"`) for inspection |
| `GetFeatureCount` | 0 | Count features in the doc (auto-invoked as property) |
| `SaveBMP` | 3 | Save current view as BMP |

**`IModelDocExtension`**

| Method | Args | Purpose |
|---|---|---|
| `SelectByID2` | 9 | Documented 9-arg select; the `Callout` interface arg fails to marshal via pywin32 late-binding, so we use the legacy `SelectByID` instead |

**`IFeatureManager`**

| Method | Args | Purpose |
|---|---|---|
| `FeatureExtrusion2` | 23 | Boss extrude (used for all boss/extrude features in v0.2) |
| `FeatureExtrusion3` | 23 | Newer extrude variant (same arg shape; not currently used) |
| `FeatureCut4` | 27 | Cut extrude (used for all cut features in v0.2). **CHM says 27 args** — the missing `AutoSelectComponents`, `PropagateFeatureToParts`, `OptimizeGeometry` caused our earlier PARAMNOTOPTIONAL failures |
| `CreateDefinition` | 1 | Creates a per-feature-type data object (used for the SW 2020+ canonical fillet path; takes a `swFeatureNameID_e` int, e.g. `swFmFillet=1`). Replaces the deprecated single-call form for fillets/chamfers |
| `CreateFeature` | 1 | Consumes a populated feature-data object and creates the feature. Late-binding pass-through of the data CDispatch verified to work (Spike P) |

**`ISketchManager`**

| Method | Args | Purpose |
|---|---|---|
| `InsertSketch` | 1 | Open/close a sketch in the active context |
| `CreateCornerRectangle` | 6 | Rect by two opposite corners (NOT used in v0.2 — unconstrained, causes asymmetric resize on dim binding) |
| `CreateCenterRectangle` | 6 | Rect by center + corner. Anchors via center diagonals so dim resize stays centered |
| `CreateCircle` | 6 | Circle by center point + perimeter point |

**`IEquationMgr`**

| Method | Args | Purpose |
|---|---|---|
| `Add2` | 3 | Add an equation row (e.g. `"D1@SK_Plate" = "S1B_W"`). The 4-call link sequence (`FilePath` + `LinkToFile=True` + `AutomaticRebuild=True` + `UpdateValuesFromExternalEquationFile`) must happen first |

**`IFeature`**

| Method | Args | Purpose |
|---|---|---|
| `GetTypeName` | 0 | Distinguish "Boss" vs "Cut" features (auto-invoked as property) |
| `GetNextFeature` | 0 | Walk the feature tree (auto-invoked as property) |

**Enums** (from `swconst.chm`, exposed as constants in [`sw_types.py`](src/ai_sw_bridge/sw_types.py))

| Enum | Values | Notes |
|---|---|---|
| `swEndConditions_e` | 11 | `swEndCondBlind=0`, `swEndCondThroughAll=1` (not 4 — 4 is the deprecated `swEndCondUpToSurface`), `swEndCondMidPlane=6`, etc. |
| `swStartConditions_e` | 4 | `swStartSketchPlane=0` (default for all v0.2 extrudes) |
| `swDocumentTypes_e` | 8 | Part=1, Assembly=2, Drawing=3 |
| `swDimensionType_e` | 17 | Used for `AddSpecificDimension` (which is currently unreachable due to OUT-param marshalling) |
| `swSelectType_e` | — | String form used as 2nd arg to `SelectByID` ("PLANE", "FACE", "SKETCH", "SKETCHSEGMENT") |

**Not yet wired into the bridge** (but available in the CHM, candidates for v0.3+):
`FeatureRevolve`, `FeatureChamferType`, `InsertCutSwept5`, `InsertProtrusionSwept`, `FeatureCutThin2`, `FeatureBossThin2`, `SimpleHole3`, `InsertMirrorFeature`, `InsertLinearPatternFeature`. Add them to [`tools/_api_extract_input.json`](tools/_api_extract_input.json) and regenerate to expose them via `sw_types.py`.

Constant-radius fillets ARE wired (added via the CreateDefinition + ISimpleFilletFeatureData2 + CreateFeature 3-call pipeline, not the deprecated FeatureFillet3). See [`examples/filleted_box/`](examples/filleted_box/) for usage. Variable-radius / asymmetric / setback fillets remain unwired (no immediate use case).

Generated by:

```powershell
# 1. Decompile the CHM (one-time setup)
hh.exe -decompile spikes/phase0/_chm_decompiled "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\sldworksapi.chm"

# 2. Extract the methods + enums declared in tools/_api_extract_input.json
python tools/chm_extract.py batch tools/_api_extract_input.json docs/api_reference.json

# 3. Regenerate the human-readable + Python-stub forms
python tools/gen_api_markdown.py docs/api_reference.json docs/api_reference.md
python tools/gen_sw_types.py docs/api_reference.json src/ai_sw_bridge/sw_types.py
```

The generated [src/ai_sw_bridge/sw_types.py](src/ai_sw_bridge/sw_types.py) exports enum constants (`SW_END_COND_THROUGH_ALL = 1`, etc.) and a `METHOD_SIGNATURES` dict. The builder calls `assert_args()` before each FeatureManager call, so any future arg-count drift fails fast with a clear diagnostic.

**Lesson**: when an SW call returns `PARAMNOTOPTIONAL` or `Invalid number of parameters`, the very first check is whether the arg count matches the CHM. ([commit c560e97](https://github.com/Thomas-Tai/ai-sw-bridge/commit/c560e97) — `FeatureCut4` was 27 args, not the 24 we'd been sending.)

## Why this design

- **AI agents need verifiable, reversible operations.** Every mutation is `propose → dry-run → review → commit`. Rollback verification reads the file back from disk and compares against the snapshot.
- **The `*_locals.txt` file is the single source of truth.** Editing variables in SW Equation Manager directly is fragile (the link can overwrite them). We always edit the file, then reload + rebuild.
- **Late-binding pywin32 only.** `EnsureDispatch`/makepy doesn't work against `SldWorks.Application` on most installs. We accept the late-binding tax (some APIs unreachable, see gotchas) and work around it.
- **JSON in/out for everything.** Trivially scriptable from any AI agent harness — Claude Code, OpenAI Assistants, custom MCP servers, plain shell scripts.
- **CHM is authoritative.** API signatures change between SW versions. Re-extract on a fresh SW install; the generated `sw_types.py` adapts the runtime arg-count assertion automatically.

## Layout

```
ai-sw-bridge/
├── src/ai_sw_bridge/
│   ├── sw_com.py            # SldWorks dispatch + helpers
│   ├── sw_types.py          # auto-generated enum constants + assert_args
│   ├── observe.py           # Phase 1: read-only tools
│   ├── mutate.py            # Phase 2: Propose-Approve-Execute
│   ├── locals_io.py         # *_locals.txt parser + atomic writer
│   ├── parameterize.py      # Path C: recorded-macro parameterizer
│   ├── spec/                # v0.2: JSON-spec build pipeline
│   │   ├── schema.py        # JSON schema for the spec language
│   │   ├── validator.py     # 3-layer validation (schema, refs, locals)
│   │   └── builder.py       # direct-COM build executor
│   └── cli/                 # CLI entry points
├── tools/
│   ├── chm_extract.py       # decompiled-CHM signature/enum parser
│   ├── gen_api_markdown.py  # JSON → docs/api_reference.md
│   ├── gen_sw_types.py      # JSON → src/ai_sw_bridge/sw_types.py
│   └── _api_extract_input.json  # which methods/enums to extract
├── docs/
│   ├── architecture.md                     # phases, design rationale (v0.1)
│   ├── ai_driven_architecture_review.md    # field survey + v0.2 plan
│   ├── tools_reference.md                  # every CLI command, every flag
│   ├── known_gotchas.md                    # things we learned the hard way
│   └── api_reference.{md,json}             # CHM-verified SW API reference
├── examples/
│   ├── minimal_cylinder/        # Path C example (recorded macro → parametric)
│   ├── minimal_cylinder_v2/     # v0.2 example (JSON spec → direct-COM)
│   └── motor_mount_plate/       # v0.2 spec for the S1b MMP (partial; v1 limitation)
├── spikes/phase0/                # Phase 0 de-risking spikes + MMP debug log
├── USAGE.md
├── CHANGELOG.md
├── pyproject.toml
└── requirements.txt
```

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

SOLIDWORKS API patterns reference: [CodeStack](https://www.codestack.net/solidworks-api/). The Path C dim-binding fix (`EquationMgr.Add2` 3-arg form) came from their `document/dimensions/add-equation/` example.
