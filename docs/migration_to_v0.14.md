# Migration Guide: v0.13 to v0.14

This document describes what changed between ai-sw-bridge v0.13.0 and
v0.14.0 for users upgrading existing projects. v0.14 is the
commercial-hardening release: it fixes a shipped double-binding bug
in parametric builds, removes one broken-by-design legacy function,
and introduces class-based facades over the observe and mutate
modules.

## Backward compatibility summary

| Category | Impact |
|---|---|
| JSON spec language | **Unchanged.** Every v0.13 spec builds identically in v0.14. |
| `ai-sw-build` / `ai-sw-observe` / `ai-sw-mcp` CLIs | **Unchanged.** All flags, subcommands, and output shapes preserved. |
| `ai-sw-mutate` CLI | **Breaking:** `run_macro` subcommand removed. The 4 surviving subcommands (`propose` / `dry_run` / `commit` / `undo_last_commit`) are unchanged. |
| `ai_sw_bridge.observe.sw_get_*` Python API | Preserved as backward-compatible shims. New `SolidWorksObserver` class is the recommended entry point; the legacy shims will be removed in v0.15 (`docs/DEFERRED.md` D-v0.14-06). |
| `ai_sw_bridge.mutate.sw_*` Python API | Same — preserved as shims; new `ProposalStore` class is recommended. |
| `ai_sw_bridge.mutate.sw_run_macro` Python API | **Removed.** No replacement. |
| MCP tool surface | **Unchanged.** The 21 tools still register with identical names and parameters. |

## Fixed bugs (every parametric / deferred-dim build benefited)

### Double-application of equation bindings (`spec/builder.py`)

In v0.13.0, every `--deferred-dim` build (and every parametric
default-mode build) called `_apply_bindings` **twice** per feature
— once inside an `else:` block, again unconditionally outside it.
The result: every `IEquationMgr.Add2` call fired twice and
`BuildResult.bindings_added` carried duplicates. The Motor Mount
Plate build emitted 14 equation entries; the correct count is 7.

v0.14 deletes the first (non-`com_error_boundary`-wrapped) block
and keeps the canonical one. **No spec change required** — re-run
your build and observe the equation manager has half as many
entries.

### `ai_sw_bridge.__version__` reads installed metadata

v0.13 hardcoded `__version__ = "0.1.0"` at the top of the package.
v0.14 reads from `importlib.metadata.version("ai-sw-bridge")` with
a `"0.0.0+unknown"` fallback for source checkouts without
`pip install -e .`. After upgrading, re-run `pip install -e .` so
the dist-info metadata matches `pyproject.toml`.

## Removed (BREAKING)

### `ai-sw-mutate run_macro` subcommand + `mutate.sw_run_macro` function

The `run_macro` subcommand and its underlying `sw_run_macro` Python
function are removed in v0.14. The function was a 0.1.0-era stub
that only worked on binary `.swp` files produced by SOLIDWORKS's
own VBE editor; externally-generated `.swp` / `.bas` files were
silently rejected (`RunMacro` returns `False`). The supported Path
C workflow has always been:

1. Generate a `.bas` via `ai-sw-codegen parameterize`.
2. Paste it into VBE manually.
3. Press F5.

That workflow is unchanged in v0.14. If you imported
`ai_sw_bridge.mutate.sw_run_macro` from a downstream script,
delete the import and the call — there is no in-process
replacement. If/when binary-`.swp` write-back is figured out,
`SldWorks.RunMacro` / `RunMacro2` can be called directly.

## New class-based API

v0.14 introduces two facade classes that wrap the existing
observe and mutate free functions. The classes are the
**recommended entry point** for new code; the free functions
remain as backward-compatible shims and will be removed in v0.15.

### `ai_sw_bridge.observe.SolidWorksObserver`

```python
# Before (v0.13)
from ai_sw_bridge.observe import sw_get_bbox, sw_get_volume
bbox = sw_get_bbox()
volume = sw_get_volume()

# After (v0.14, recommended)
from ai_sw_bridge.observe import SolidWorksObserver
observer = SolidWorksObserver()
bbox = observer.bbox()
volume = observer.volume()
```

The 10 methods on `SolidWorksObserver` map 1:1 to the legacy
`sw_get_*` functions:

| Legacy free function | New method |
|---|---|
| `sw_get_active_doc()` | `SolidWorksObserver().active_doc()` |
| `sw_get_feature_errors()` | `SolidWorksObserver().feature_errors()` |
| `sw_get_equations()` | `SolidWorksObserver().equations()` |
| `sw_get_bbox()` | `SolidWorksObserver().bbox()` |
| `sw_get_volume()` | `SolidWorksObserver().volume()` |
| `sw_screenshot(...)` | `SolidWorksObserver().screenshot(...)` |
| `sw_measure(...)` | `SolidWorksObserver().measure(...)` |
| `sw_get_mate_errors()` | `SolidWorksObserver().mate_errors()` |
| `sw_get_custom_props()` | `SolidWorksObserver().custom_props()` |
| `sw_get_enabled_addins()` | `SolidWorksObserver().enabled_addins()` |

Return shapes are identical. Existing tests that import the
legacy functions continue to work unchanged.

### `ai_sw_bridge.mutate.ProposalStore`

```python
# Before (v0.13)
from ai_sw_bridge.mutate import (
    sw_propose_local_change, sw_dry_run, sw_commit, sw_undo_last_commit,
)
p = sw_propose_local_change("S1B_W", "200")
sw_dry_run(p["proposal_id"])
sw_commit(p["proposal_id"])

# After (v0.14, recommended)
from ai_sw_bridge.mutate import ProposalStore
store = ProposalStore()
p = store.propose("S1B_W", "200")
store.dry_run(p["proposal_id"])
store.commit(p["proposal_id"])
```

A new `ProposalState` enum (`PROPOSED`, `DRY_RUN_OK`,
`DRY_RUN_BROKE`, `COMMITTED`, `UNDONE`) is also exposed; the
existing `ST_*` module constants alias the same values for
backward compatibility.

### Why facades, not full migration?

The plan ([`v0.14_commercial_hardening_plan.md`](v0.14_commercial_hardening_plan.md)
§C1/C2) originally called for a deeper migration that moves every
function's logic into class methods and extracts a template method
for the shared `get_sw_app/get_active_doc/try-except` ceremony.
That migration was deferred mid-execution because every function
has unique error messages, edge cases, and behavioral nuances that
tests assert on directly. Doing the full migration safely is its
own focused PR. v0.14 ships the **stable class API surface** so
callers can migrate now; the deeper refactor (logged as
D-v0.14-06 in [`DEFERRED.md`](DEFERRED.md)) targets v0.15 and
**will not change the public method signatures or return shapes**.

## Documentation parity fixes

- `README.md`: corrects "12 part-modelling primitives" / "12 working specs"
  drift (real counts are 16 and 15 respectively).
- `README.md`: adds the full `ai-sw-build` flag inventory and an
  Environment Variables reference table (`AI_SW_BRIDGE_CAPTURES`,
  `AI_SW_BRIDGE_PROPOSALS`, `AI_SW_BRIDGE_FLAG_<NAME>`, `NO_COLOR`).
- 5 doc/source files replace the fictional `sw_mutate_apply` reference
  with the four real `sw_*` mutate function names that are
  CLI-only-by-design.
- `tests/mcp_lane/test_server_contract.py` now asserts the four
  real mutate names are excluded from the MCP tool registry
  (the v0.13 test was vacuously passing on a name that never
  existed).

## Upgrade procedure

```powershell
git pull
pip install -e ".[mcp,dev]"  # refreshes dist-info metadata
python -c "import ai_sw_bridge; print(ai_sw_bridge.__version__)"  # should report 0.14.0
pytest -q -m "not solidworks_only and not fault_injection"
```

If you have downstream scripts importing `sw_run_macro`, delete
those imports. Otherwise, no code changes are required — the
class APIs are additive.
