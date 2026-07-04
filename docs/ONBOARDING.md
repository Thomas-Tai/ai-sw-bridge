# Getting Started — Three-Command Hello World

> **This guide has moved to [docs/operator_guide.md](operator_guide.md).** The
> canonical Operator Guide folds this quickstart together with first-run
> troubleshooting and the sharp edges to know before authoring a part. This page
> is kept as a redirect (and as the authoritative full CLI-command reference
> below).

Get from a fresh install to your first observed part in exactly three commands.
Each command is copy-pasteable and requires only the prerequisites below.

## Prerequisites

- **Windows** with SOLIDWORKS installed and running (2024 SP1 tested; 2021 SP5+ works).
- **Python 3.10+** on your PATH.
- **pipx** and the bridge installed — see the [Operator Guide](operator_guide.md) for the full install steps (pipx from Git URL, with the one-time pywin32 step).

## The three commands

### 1. Verify the connection

```powershell
ai-sw-probe
```

Confirms that `pywin32` can dispatch `SldWorks.Application` against your running
SOLIDWORKS session. On success, prints a JSON object and exits 0:

```json
{
  "ok": true,
  "sw_revision": "33.1.0 SP1.0",
  "active_doc": null,
  "error": null
}
```

If SOLIDWORKS isn't running or `pywin32` can't connect, `ok` is `false`, `error`
describes the problem, and the exit code is 1. Fix the issue before proceeding —
every subsequent command needs a live COM connection.

**What it does:** calls `get_sw_app()` to acquire `SldWorks.Application`, reads
`RevisionNumber`, and queries the active document (if any). Source:
[`cli/probe.py`](../src/ai_sw_bridge/cli/probe.py).

### 2. Build a part

```powershell
ai-sw-build --demo --no-dim
```

Builds a 20x20x10 mm box with a 2 mm fillet on one edge. The `--no-dim` flag
resolves every dimension in Python so the build completes in ~3 seconds with
zero blocking popups. On success, the part appears in SOLIDWORKS and the CLI
prints a JSON object and exits 0:

```json
{
  "ok": true,
  "features_built": ["SK_Box", "Extrude_Box", "Fillet_TopRightEdge"],
  "bindings_added": [],
  "save_as": null,
  "save_as_verified": null,
  "no_dim": true,
  "deferred_dim": false
}
```

If schema/refs/locals validation fails, the exit code is 3 and no COM calls
are made (a malformed-JSON or missing spec file is exit 2). If a feature fails
at build time, the exit code is 4 and `error` describes which feature and why.

**What it does:** validates the spec JSON against the schema, then drives
SOLIDWORKS via COM to create a fresh part and build each feature in order.
Source: [`cli/build.py`](../src/ai_sw_bridge/cli/build.py), spec file:
[`examples/filleted_box/spec.json`](../examples/filleted_box/spec.json).

### 3. Observe the result

```powershell
ai-sw-observe bounding_box
```

Reads the axis-aligned bounding box of the part you just built. Prints a JSON
object and exits 0:

```json
{
  "ok": true,
  "bounding_box": {
    "x_min_mm": -10.0,
    "x_max_mm": 10.0,
    "y_min_mm": -10.0,
    "y_max_mm": 10.0,
    "z_min_mm": 0.0,
    "z_max_mm": 10.0,
    "dx_mm": 20.0,
    "dy_mm": 20.0,
    "dz_mm": 10.0
  },
  "error": null
}
```

The 20x20x10 mm dimensions confirm the build produced the expected geometry.

**What it does:** calls `IPartDoc.GetPartBox(True)` on the active document.
Source: [`cli/observe.py`](../src/ai_sw_bridge/cli/observe.py) (subcommand
`bounding_box`), implementation: [`observe_bbox.py`](../src/ai_sw_bridge/observe_bbox.py).

## What to try next

- **Different part:** swap the spec path for another example —
  `examples/motor_mount_plate/spec.json` builds a plate with bolt holes.
  Run `ls examples/` to see all 20 working specs.
- **Dry-run without SOLIDWORKS:** `ai-sw-build --demo --dry-run`
  validates, resolves every `{rhs}` binding, and prints a planned-feature list
  without booting SW.
- **Lint check:** `ai-sw-build --demo --lint` runs
  semantic checks (unconsumed sketches, missing `center.z`) on top of
  validation.
- **Read the part's volume:** `ai-sw-observe volume` reports volume (mm^3 and
  m^3), surface area, mass, and centre of mass.
- **Take a screenshot:** `ai-sw-observe screenshot --fit-view` saves a PNG of
  the current viewport.
- **MCP server:** `ai-sw-mcp` exposes 37 read-only + build tools to Claude
  Desktop, Cursor, and other MCP clients. Bundled via the `[mcp]` extra in the pipx install.

## Where to read more

| Concern | File |
|---|---|
| AI assistant briefing | [`docs/AGENTS.md`](AGENTS.md) |
| Capability matrix | [`docs/CAPABILITIES.md`](CAPABILITIES.md) |
| Spec JSON reference | [`docs/spec_reference.md`](spec_reference.md) |
| CLI + MCP tool reference | [`docs/tools_reference.md`](tools_reference.md) |
| Known gotchas | [`docs/known_gotchas.md`](known_gotchas.md) |
| Working example specs | [`examples/`](../examples/) |

## All 22 CLI commands at a glance

| Command | Purpose | SW needed? |
|---|---|---|
| `ai-sw-probe` | Verify COM connectivity | Yes |
| `ai-sw-build` | Build a part from a JSON spec | Yes |
| `ai-sw-observe` | Read-only inspection (28 subcommands) | Yes |
| `ai-sw-mutate` | Propose-approve-execute variable changes | Yes |
| `ai-sw-assembly` | Propose-approve-execute assembly lifecycle | Yes |
| `ai-sw-drawing` | Create drawing views + annotations | Yes |
| `ai-sw-properties` | Set custom file properties | Yes |
| `ai-sw-configurations` | Family-of-parts as N distinct files | Yes |
| `ai-sw-sketch-relations` | Add geometric constraints to sketches | Yes |
| `ai-sw-codegen` | Generate Python boilerplate from SW API | No |
| `ai-sw-apidoc` | Search the RAG-indexed SW API docs | No |
| `ai-sw-checkpoint` | Manage per-feature build checkpoints | Varies |
| `ai-sw-history` | Query and rollback build history | Varies |
| `ai-sw-import` | Import geometry into the active part | Yes |
| `ai-sw-export-dxf-flat` | Export flat-pattern DXF | Yes |
| `ai-sw-motion` | Motion audit (parametric DOF sweep) | Yes |
| `ai-sw-batch` | Human-gated batch feature-commit. Executes a multi-feature plan (from MCP `sw_batch_plan`) behind a `[y/N]` gate; greens persist, fail-fast on the first fault. | Yes |
| `ai-sw-sketch-edit` | Propose-Approve-Execute sketch editing ops (Convert / Offset / Trim / Pattern). Subcommands: `propose` / `dry_run` / `commit`. CLI-only. | Yes |
| `ai-sw-memory` | **Design-Memory RAG** — semantic search over *your own* design history (past proposals/checkpoints). `build` (backfill the local index) / `search` / `stats`. Embeddings are computed **on-device**; the index is a private, gitignored artifact. | No |
| `ai-sw-solver` | Autonomous clearance solver (`resolve-clearance`) — drives a distance mate until clash-free, reverts on failure. | Yes |
| `ai-sw-urdf` | URDF export (assembly → ROS robot model). `export` writes `.urdf` + per-component STL meshes. No SW mutation. | Yes |
| `ai-sw-doctor` | Operator preflight: Python/pywin32/PATH/seat + MCP registration | Optional |
| `ai-sw-mcp` | Run the MCP server (stdio transport) | Yes |

Source: [`pyproject.toml`](../pyproject.toml) `[project.scripts]` section.
