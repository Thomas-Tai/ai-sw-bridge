# Operator Guide

**For the SOLIDWORKS user who wants to drive the bridge from an AI assistant —
no coding required beyond copy-pasting a few commands.**

This is the canonical, end-to-end guide for operators. If you run SOLIDWORKS
every day but don't write Python, start here. It folds together the three-command
"hello world", the first-run troubleshooting you'll actually hit, and the sharp
edges to know before you author your own part.

> **Pairing with an AI assistant?** Hand it [`docs/AGENTS.md`](AGENTS.md) — that
> file is written *for the AI*: it spells out the rules, the spec format, which
> example to copy, and exactly what needs your confirmation before anything runs.
> You stay in the loop; the AI drafts, you approve.

---

## Before you start — what you need

- **Windows** with SOLIDWORKS installed and running (2024 SP1 tested; 2021 SP5+ works).
- **Python 3.10+, 64-bit**, on your PATH. SOLIDWORKS is 64-bit, so a 32-bit Python
  will not attach over COM. Check with `python --version`.
- **Git** on your `PATH` — `pipx` fetches the bridge over Git. Check with `git --version`.
- **pipx** — the isolated-app installer. Install once: `python -m pip install --user pipx`.

> **Heads-up:** this is a Python developer tool. You'll work at a terminal and
> copy-paste a few commands. `pipx` manages the isolated environment for you, so you
> don't set up a virtualenv by hand — but you should be comfortable running commands
> in PowerShell. If `python` from a command line is brand new to you, skim the
> [Python beginner's guide](https://docs.python.org/3/using/index.html) first.

### Install the bridge

```powershell
# once, if you don't have pipx:
python -m pip install --user pipx
python -m pipx ensurepath            # then reopen your terminal

# install the bridge (with the MCP extra) straight from Git, isolated:
pipx install "ai-sw-bridge[mcp] @ git+https://github.com/Thomas-Tai/ai-sw-bridge.git"
```

**One-time `pywin32` step (do not skip — COM won't attach without it).** Register
pywin32's DLLs *inside the pipx environment*:

```powershell
& "$(pipx environment --value PIPX_LOCAL_VENVS)\ai-sw-bridge\Scripts\python.exe" -m pywin32_postinstall -install
```

The `[mcp]` extra (bundled above) is what lets `ai-sw-mcp` run for Claude Desktop /
Cursor. `ai-sw-doctor` (next) checks both the PATH and this pywin32 step for you.

### Preflight your machine

Before anything else, let the bridge check your setup:

```powershell
ai-sw-doctor
```

`ai-sw-doctor` is the operator preflight — it checks Python, `pywin32`, your
PATH, whether a live SOLIDWORKS seat is reachable, and (if installed) your MCP
registration. Fix anything it flags red before running the commands below.

---

## The three commands — hello world

Get from a fresh install to your first observed part in exactly three commands.
Each is copy-pasteable and needs only the prerequisites above.

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
ai-sw-build examples/filleted_box/spec.json --no-dim
```

Builds a 20x20x10 mm box with a 2 mm fillet on one edge. The `--no-dim` flag
resolves every dimension in Python so the build completes in ~3 seconds with
zero blocking popups.

Before the first COM write, `ai-sw-build` prints a **seat banner** to stderr
naming the exact SOLIDWORKS it's about to drive (its PID and your active
document) and pauses for a `[y/N]` confirmation. That's the safety gate — a build
never lands in your session by surprise. Press **`y`**. (For unattended
automation, add `--yes`/`-y` to skip the prompt.)

On success, the part appears in SOLIDWORKS and the CLI prints a JSON object and
exits 0:

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

---

## First run didn't work?

| Symptom | Most likely cause | Fix |
|---|---|---|
| `ai-sw-probe` / `ai-sw-build`: *"command not found"* / *"not recognized"* | pipx's shim directory isn't on your `PATH` yet | run `pipx ensurepath`, then close and reopen your terminal — or run `ai-sw-doctor`, which detects this and tells you |
| `ai-sw-probe` returns `ok: false` or a COM error | SOLIDWORKS isn't running, or it's a different bitness than your Python | start SOLIDWORKS; use 64-bit Python (SW is 64-bit) |
| `ai-sw-build` seems to hang with a "Modify Dimension" popup in SW | parametric mode opens a blocking dialog per dimension | use `--no-dim` (the smoke test already does) — [why](why_no_addim2.md) |
| A `[y/N]` prompt appears before anything builds | that's the seat-confirmation gate, **not** an error | press `y` to proceed, or pass `--yes` for automation |

When in doubt, re-run `ai-sw-doctor` — it re-checks the four things that break
most first-run installs.

---

## Hand the keys to your AI assistant

This is the real workflow. Open Claude / ChatGPT / Codex and paste:

> I'm using **ai-sw-bridge** — a bridge that lets AI assistants drive SOLIDWORKS
> via the COM API. Before doing anything, read **[`docs/AGENTS.md`](AGENTS.md)** —
> it tells you the rules, the spec format, which example to copy, and what needs
> my confirmation before running.
>
> My goal: *describe your part here — e.g. "build a 40 × 30 × 10 mm plate with
> four Ø5 mm through-holes at the corners, 5 mm in from each edge."*
>
> Propose a JSON spec for me to review before running `ai-sw-build`.

The agent reads [`docs/AGENTS.md`](AGENTS.md), picks the closest
[`examples/`](../examples/) match, drafts a spec, and **stops** for your review.
You approve, run the command yourself, and watch the part build. That's the whole
loop — propose → approve → execute, every time.

---

## What to try next

- **Different part:** swap the spec path for another example —
  `examples/motor_mount_plate/spec.json` builds a plate with bolt holes.
  Run `ls examples/` to see all 20 working specs.
- **Dry-run without SOLIDWORKS:** `ai-sw-build examples/filleted_box/spec.json --dry-run`
  validates, resolves every `{rhs}` binding, and prints a planned-feature list
  without booting SW.
- **Lint check:** `ai-sw-build examples/filleted_box/spec.json --lint` runs
  semantic checks (unconsumed sketches, missing `center.z`) on top of
  validation.
- **Read the part's volume:** `ai-sw-observe volume` reports volume (mm^3 and
  m^3), surface area, mass, and centre of mass.
- **Take a screenshot:** `ai-sw-observe screenshot --fit-view` saves a PNG of
  the current viewport.
- **MCP server:** `ai-sw-mcp` exposes 37 read-only + build tools to Claude
  Desktop, Cursor, and other MCP clients. Bundled via the `[mcp]` extra in the pipx install above.

---

## Sharp edges to know before you author your own part

The [full known-limitations doc](known_limitations.md) is **required reading**
before you write your own spec. The ones that bite operators first:

- **Windows only.** Non-negotiable — `pywin32` only runs on Windows.
- **`AddDimension2` opens a blocking popup in parametric mode.** Default AI-driven
  flows should use `--no-dim` (geometry at literal target size, no equation link);
  `--deferred-dim` batches the popups at the end.
- **Face-sketch origin is the part-origin projection, not the face centroid.** A
  `center` offset on a face sketch resolves relative to where SW projects (0,0,0)
  onto the face, not the visual face center. This bites everyone once — see
  [known_limitations.md §1](known_limitations.md) for the worked example.
- **Some advanced features are walled out-of-process.** A handful of feature kinds
  (e.g. `loft`, `combine`, `split`, `wrap`, the profile-sketch sheet-metal flanges)
  can't be materialized through the COM boundary and fail loud rather than
  silently no-op. See [`DEFERRED.md`](DEFERRED.md) for the classification.
- **No "describe the part in English and get geometry" for free.** The spec
  language is precise; the AI generates spec JSON, not freehand prose. The
  natural-language step happens in your chat with the agent, before the spec is
  drafted.

---

## Where to read more

| Concern | File |
|---|---|
| AI assistant briefing (hand this to your AI) | [`docs/AGENTS.md`](AGENTS.md) |
| Capability matrix | [`docs/CAPABILITIES.md`](CAPABILITIES.md) |
| Spec JSON reference | [`docs/spec_reference.md`](spec_reference.md) |
| CLI + MCP tool reference | [`docs/tools_reference.md`](tools_reference.md) |
| Known limitations (required reading) | [`docs/known_limitations.md`](known_limitations.md) |
| Known gotchas | [`docs/known_gotchas.md`](known_gotchas.md) |
| Working example specs | [`examples/`](../examples/) |

The full command inventory (all 22 CLI commands) lives in the
[README's "What ships in the box" table](../README.md#what-ships-in-the-box).
