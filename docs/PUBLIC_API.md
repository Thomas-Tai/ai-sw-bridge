# Public API & Stability Contract

> **Status:** the supported surface of ai-sw-bridge as of **v1.6.0**.
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
  rest of the `1.x` line and emits a warning, per
  [`deprecation_policy.md`](deprecation_policy.md) and
  [`cli_stability.md`](cli_stability.md).

Breaking changes to a guaranteed surface require a **major** bump (`2.0.0`).
