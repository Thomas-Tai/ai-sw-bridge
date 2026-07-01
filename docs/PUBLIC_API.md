# Public API & Stability Contract

> **Status:** the supported surface of ai-sw-bridge as of **v1.7.0**.
> Anything not listed here is **internal** and may change without notice.

This is the contract a customer/integrator may rely on. It has three supported
surfaces — the **CLI**, the **MCP tools**, and the **Python facade** — plus an
explicit SemVer promise (§4). Everything else under `ai_sw_bridge.*` (notably
`ai_sw_bridge.features`, `ai_sw_bridge.mutate`, `ai_sw_bridge.observe`, `com`,
`spec`, `brep`, `selection`, `checkpoint`, `resilience` internals) is **private**.

---

## 1. CLI commands (`[project.scripts]`)

Each command declares a **stability tier**, printed in its `--help` banner and
enforced by `tests/test_cli_stability.py`:

- **stable** — no breaking change without a major version bump.
- **experimental** — may change or be removed in any release.
- **deprecated** — removed next major; prints a stderr warning on every run.

| Tier | Commands |
|---|---|
| **stable** | `ai-sw-build`, `ai-sw-observe`, `ai-sw-mutate`, `ai-sw-assembly`, `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations` |
| **experimental** | `ai-sw-probe`, `ai-sw-batch`, `ai-sw-codegen`, `ai-sw-history`, `ai-sw-apidoc`, `ai-sw-memory`, `ai-sw-checkpoint`, `ai-sw-import`, `ai-sw-export-dxf-flat`, `ai-sw-motion`, `ai-sw-solver`, `ai-sw-urdf`, `ai-sw-sketch-relations`, `ai-sw-sketch-edit` |
| **daemon** | `ai-sw-mcp` — the MCP stdio server (not an argparse CLI; see §2) |

The authoritative tier per command is `cli/stability.py::TIER_REGISTRY` and the
command's own `--help`. Every mutating command follows **propose → approve →
execute**: the AI never changes a model without an explicit human/`--yes` gate.

## 2. MCP tools (`ai-sw-mcp`)

The MCP server exposes a tool set pinned **by name and payload shape** in
`tests/mcp_lane/test_server_contract.py` (`EXPECTED_TOOLS`) + the per-tool
snapshots in `tests/mcp_lane/fixtures/` — those tests are the contract, so a
tool add/remove/rename or a payload-shape change fails CI loudly. Groups:

- **Observation (read-only):** `sw_active_doc`, `sw_feature_errors`, `sw_equations`,
  `sw_bbox`, `sw_volume`, `sw_screenshot`, `sw_measure`, `sw_measure_selection`,
  `sw_mate_errors`, `sw_custom_props`, `sw_enabled_addins`, `sw_interference`,
  `sw_bounding_box`, `sw_inertia`, `sw_clearance`, `sw_draft_analysis`,
  `sw_current_selection`, `sw_undercut_faces`, `sw_min_wall_thickness`,
  `sw_feature_statistics`, `sw_analyze_stackup`, `sw_observe_mbd`.
- **Build / batch:** `sw_build` (validate → **elicit-in-chat approval** → build;
  no build or `save_as` without an explicit `approve=true`); `sw_batch_plan`
  (**hard-wired `dry_run=True`** — can never persist to disk); `sw_batch_execute`
  (PLAN → elicit-in-chat → COMMIT). The two write tools (`sw_build`,
  `sw_batch_execute`) are the only MCP paths that reach disk, and both are
  human-gated by MCP elicitation.
- **API docs:** `sw_apidoc_search`, `sw_apidoc_detail`, `sw_apidoc_members`,
  `sw_apidoc_examples`, `sw_apidoc_enum`.
- **History / resilience:** `sw_history_part`, `sw_history_since`,
  `sw_history_diff`, `sw_checkpoint_info`, `sw_session_health` (read-only),
  `sw_reconnect`.
- **Design-Memory (RAG):** `sw_retrieve_design_memory` (local, on-device).

**Autonomous-write safety:** no MCP tool persists to disk without an explicit
in-chat human approval. Both write tools (`sw_build`, `sw_batch_execute`) gate
their COM write behind an MCP elicitation `approve=true`; `sw_batch_plan` is
plan-only by construction. Pinned by `tests/mcp_lane/test_build_elicit.py` +
`test_batch_execute.py` (the COM write callable is invoked only on approval) and
the `COM_SAFE_VIA_MANUAL_DISPATCH` contract in `test_server_contract.py`.

## 3. Python facade

```python
from ai_sw_bridge.client import SolidWorksClient
sw = SolidWorksClient()                 # lazy, injectable app/module
sw.observe. ...                         # read lanes
sw.mutate.batch(path, proposals)        # supervised-by-default write (v1.6.0)
sw.export. ... / sw.urdf. ...           # export lanes
```

`SolidWorksClient` (and its `.observe` / `.mutate` / `.export` / `.urdf` /
`.features` domain facades) is the **sole supported Python entry point**. The
package also re-exports the pure-Python utilities (`locals_io`, `parameterize`,
`spec`) for non-Windows use. The free `sw_*` functions removed at v1.0 are gone;
the remaining module-private `_*_impl` cores are **not** public.

## 4. SemVer & compatibility promise

Within a major version (`1.x`):

- **Guaranteed backward-compatible:** the **stable** CLI commands' flags +
  two-stream (stdout-JSON / stderr-text) contract; the **MCP tool names + I/O
  payload shapes** (the `EXPECTED_TOOLS` contract); the **`SolidWorksClient`
  facade** method signatures.
- **May change in a minor release:** **experimental** CLI commands; anything
  under `ai_sw_bridge.features.*` and every other `_internal`/`_impl` module;
  the on-disk checkpoint / transaction-ledger formats.
- **Deprecation:** a stable surface marked `deprecated` keeps working for the
  rest of the `1.x` line and emits a warning, per the **Deprecation policy** and
  **Stability tiers** sections below.

Breaking changes to a guaranteed surface require a **major** bump (`2.0.0`).

## 5. Frozen integration contracts

These are the invariants packaging and downstream integrators bind to. Each is
already enforced by an existing test — this section is the human-readable
index, not a new check.

- **Console-script names.** The 21 `ai-sw-*` entry points (`ai-sw-probe`,
  `ai-sw-observe`, `ai-sw-mutate`, `ai-sw-batch`, `ai-sw-assembly`,
  `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`,
  `ai-sw-sketch-relations`, `ai-sw-sketch-edit`, `ai-sw-codegen`,
  `ai-sw-build`, `ai-sw-history`, `ai-sw-apidoc`, `ai-sw-memory`,
  `ai-sw-checkpoint`, `ai-sw-import`, `ai-sw-export-dxf-flat`,
  `ai-sw-motion`, `ai-sw-solver`, `ai-sw-urdf`) plus `ai-sw-mcp`, all defined
  in `[project.scripts]` (`pyproject.toml`) and targeting
  `ai_sw_bridge.cli.*` / `ai_sw_bridge.mcp.server`. A rename, removal, or
  target-module change to any of these is a breaking packaging change.
  Guarded by `tests/test_doc_truth.py` (`_cli_command_count` derives the
  count straight from `pyproject.toml` and pins every doc surface that
  restates it).
- **CLI exit-code contract.** `ai-sw-build` (`src/ai_sw_bridge/cli/build.py`)
  returns exactly `0` (success), `2` (argument/spec-file/flag errors), `3`
  (schema validation failed), `4` (build failed, or `--strict-addins`
  blocked), `5` (`--dry-run` rhs-resolution failure), `6` (`--lint` findings
  present), or `7` (`--auto-retry` refused an identical resubmission) —
  **never `1`** (`1` is the shared generic `ok:false` code used by other
  CLIs, e.g. `ai-sw-batch` / `ai-sw-checkpoint`, not by `ai-sw-build`).
  Guarded by `tests/cli/test_exit_codes_documented.py`, which pins that
  `docs/tools_reference.md`'s "Exit codes" section documents codes `3`–`7`
  and still mentions `stderr` (the seat banner writes there).
- **MCP tool-name set.** The `ai-sw-mcp` server's tool surface (names +
  payload shapes) is pinned by `EXPECTED_TOOLS` in
  `tests/mcp_lane/test_server_contract.py` — currently 37 tools across the
  observation / build-batch / API-docs / history-resilience / design-memory
  groups listed in §2 above. A tool add/remove/rename or a payload-shape
  change fails that test (and, transitively, `tests/test_doc_truth.py`'s
  `_mcp_tool_count`, which imports `EXPECTED_TOOLS` to keep every doc count
  in sync).

---

## Stability tiers (per-command)

_Consolidated from the former `cli_stability.md`._


Every `ai-sw-bridge` CLI entry point declares an explicit stability tier.
The tier appears in `--help` output as a `[tier]` prefix on the
description line and is tracked in a module-level registry
(``TIER_REGISTRY`` in ``cli/stability.py``) that tests can inspect.

## Tier definitions

| Tier           | Back-compat promise                                                    |
|----------------|------------------------------------------------------------------------|
| **stable**     | No breaking changes to CLI flags, positional args, or JSON output     |
|                | shape without a major version bump (v0.x → v1.0). Minor additions    |
|                | (new optional flags, new output keys) are allowed in any release.     |
| **experimental**| May change or disappear in any release. Output shape and flag names  |
|                | are not guaranteed. Use in production at your own risk.               |
| **deprecated** | Will be removed in the next major release. Emits a stderr warning    |
|                | on every invocation.                                                   |

## How to add a tier

1. Import the decorator and helper:

   ```python
   from .stability import add_tier, cli_stability
   ```

2. Decorate your ``main()`` function:

   ```python
   @cli_stability("stable")
   def main() -> int:
       ...
   ```

3. Call ``add_tire()`` on the ``ArgumentParser`` **after** construction:

   ```python
   parser = argparse.ArgumentParser(...)
   add_tier(parser, "stable")
   ```

4. The test suite enforces that every CLI module in
   ``src/ai_sw_bridge/cli/`` with a ``main()`` function has an explicit
   tier — a new subcommand without one will fail
   ``test_all_cli_modules_registered``.

## Current assignments

| CLI entry point   | Tier           |
|-------------------|----------------|
| ai-sw-build       | stable         |
| ai-sw-observe     | stable         |
| ai-sw-mutate      | stable         |
| ai-sw-probe       | experimental   |
| ai-sw-codegen     | experimental   |

---

## Deprecation policy

_Consolidated from the former `deprecation_policy.md`._


How ai-sw-bridge removes things, and how the spec format evolves. This
exists so downstream specs and integrations are never broken without
warning. (Enhancement plan P3.2.)

## Semantic versioning

The package version (`pyproject.toml`) follows [SemVer](https://semver.org/):

- **MAJOR** — backwards-incompatible change to the spec schema or the CLI
  contract (flags, exit codes, JSON output keys).
- **MINOR** — backwards-compatible feature (new feature primitive, new flag).
- **PATCH** — backwards-compatible bug fix.

Pre-1.0, a MINOR release may carry a small breaking change, but only when a
`DeprecationWarning` for it shipped in the preceding MINOR release.

## Deprecation procedure

Nothing user-facing is removed without a deprecation cycle:

1. **Announce.** The thing being removed — a CLI flag, a JSON output key, a
   feature type, a public function — emits a `DeprecationWarning` via
   `warnings.warn(..., DeprecationWarning)` and is listed under a
   `### Deprecated` heading in `CHANGELOG.md`. The warning names the
   replacement.
2. **Grace period.** It keeps working for **at least one MINOR release**.
3. **Remove.** Removal lands in a later release under `### Removed` in
   `CHANGELOG.md`.

A removal that skips the warning cycle is a bug, not a release.

## Spec `schema_version` migration

The spec format carries an integer `schema_version` (currently `1`, exposed
as `schema.SCHEMA_VERSION`):

- The validator accepts **only** specs whose `schema_version` equals the
  current `SCHEMA_VERSION`; a mismatch fails fast with a clear error.
- **Additive** changes (new optional field, new feature type) do **not**
  bump `schema_version` — existing specs stay valid.
- A **breaking** spec change (renamed/removed field, changed semantics)
  bumps `schema_version` to the next integer and ships, in the same release:
  - the new `SCHEMA_VERSION` constant,
  - a `tools/migrate_spec.py` one-shot converter (e.g. `v1 -> v2`),
  - a `### Changed` CHANGELOG entry pointing at the converter.
- The converter is retained for at least one MAJOR release so specs in the
  wild can still be upgraded.

Until a `schema_version: 2` is required, this section is the standing
forward commitment: **no silent spec breakage.**
