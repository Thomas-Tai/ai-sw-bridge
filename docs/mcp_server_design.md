# MCP Server — Design (W5.4)

**Status:** Design approved, implementation pending (W5.4-impl).
**Authors:** v0.13 closure track.
**Cross-refs:** *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §6
(Lane M deferred design), [`docs/decisions.md`](decisions.md)
2026-05-23 "Lane M adoption-driven",
[`docs/com_failure_modes.md`](com_failure_modes.md) row M-XX.

This document is the binding design for the MCP server (Lane M). It
commits to the framework choice, the cross-thread COM-safety wiring,
the tool surface, the wire format, the lifecycle, and the test
contract. The impl task (W5.4-impl, Sonnet/GLM) fills in the bodies;
behavior must match this document.

---

## 1. Problem statement

The bridge's CLI surface (`ai-sw-build`, `ai-sw-observe`, `ai-sw-mutate`,
`ai-sw-history`, `ai-sw-apidoc`, `ai-sw-checkpoint`, `ai-sw-probe`,
`ai-sw-codegen`) already provides a complete tool surface for any
shell-capable AI agent (Claude Code, Codex CLI, ChatGPT with code
execution).

But two classes of agents can't shell out:

- **Claude Desktop** — runs MCP servers over stdio, has no shell.
- **Cursor / other IDE-integrated MCP clients** — same constraint.

For these clients, the MCP server exposes the same tool surface over
the MCP protocol. The server is a **thin transport wrapper** over the
existing tool implementations — not a reimplementation.

## 2. Non-goals

- **Not 88+ tools.** The upstream `SolidworksMCP-python` ships 88+ MCP
  tools because it built the SW automation surface inside the MCP
  server. The bridge already has that surface in `spec/`, `observe.py`,
  and the CLIs. Our MCP server exposes ~10 tools that map 1:1 to the
  existing CLI subcommands.
- **Not pydantic-ai.** No LLM agent loop runs inside the server. The
  server is a stateless tool dispatcher; reasoning is the client's job.
- **Not a complexity analyzer / intelligent router / circuit breaker.**
  Those are MCP-server-specific abstractions that exist in the upstream
  because the upstream owns the safety surface. We own it in
  `spec/validator.py` (zero ACE) — the bridge's validator runs before
  any COM call, so the MCP server inherits the safety property.
- **Not HTTP transport.** Stdio only for v0.13. HTTP is a v0.14+
  consideration; the design doesn't preclude it.
- **Not write tools beyond `ai_sw_build`.** Approval-gated mutation
  (the `--apply` flag on `ai-sw-mutate`) is intentionally NOT exposed
  via MCP in v0.13 — MCP tool calls happen without human-in-the-loop
  per tool call. Mutation flows still require explicit `ai-sw-mutate`
  CLI invocation by the human.

## 3. Framework choice — `mcp` (Anthropic SDK with bundled FastMCP)

**Decision:** Use the `mcp` package (Anthropic-maintained Python SDK)
with its bundled high-level `FastMCP` wrapper.

```
mcp >= 1.0.0
```

Added to `pyproject.toml` `[project.optional-dependencies] mcp`.
Optional install: `pip install ai-sw-bridge[mcp]`.

**Why not `fastmcp`** (jlowin/fastmcp, the standalone PyPI package):

| Concern | Anthropic `mcp` (bundles FastMCP) | jlowin `fastmcp` |
|---|---|---|
| Maintenance | Anthropic, canonical | Community fork, more features but more churn |
| API stability | Tracks MCP spec versions | Ahead of spec at times |
| Dependency surface | Single dep | Pulls more transitively |
| Ergonomics | Has `mcp.server.fastmcp.FastMCP` for decorator-style tools | Slightly nicer DX, but the difference is small |
| Future-proof | Spec-aligned | Possible divergence |

For a single-maintainer project shipping its first MCP server: pin
to the reference implementation. We can switch if we hit a real
ergonomic gap.

**Why not raw `mcp.server.Server`** (lowest-level):

We'd reimplement schema registration, capability negotiation, and
JSON-RPC framing for no benefit — the bundled `FastMCP` wrapper is
exactly what we'd write by hand. Use it.

**Why not custom stdio JSON-RPC**:

Zero new deps, but ~600 lines of MCP protocol handling we'd have to
audit ourselves. Not worth it.

## 4. Cross-thread COM safety — `@com_tool` decorator

**Decision:** The MCP server owns STA discipline at the **tool-handler
layer** via a `@com_tool` decorator. The adapter (`PyWin32Adapter`
from W5.2) stays thin; the executor (`ComExecutor` from W5.1) is held
by the server runtime and wraps every COM-touching call.

Pattern:

```python
@mcp.tool()
@com_tool  # wraps body in executor.run(...)
def sw_get_bbox() -> dict[str, Any]:
    """Report the active part's bounding box."""
    return sw_get_bbox_impl()  # the existing observe.py function
```

`@com_tool` expands to:

```python
def wrapper(*args, **kwargs):
    return runtime.executor.run(lambda: fn(*args, **kwargs))
```

**Why this resolves the W5.2 audit finding (Track E):**

The Track E audit (2026-05-28) noted that `PyWin32Adapter` does not
hold a `ComExecutor` internally. Upstream did; Track E simplified it
out. Two options were considered:

1. **Wire executor at the MCP tool layer** (this design choice).
2. Refactor `PyWin32Adapter` to hold an internal `ComExecutor`.

We chose Option 1 because:

- **Additive change only.** No revisit of already-shipped W5.2 code.
- **Adapter stays single-purpose.** Non-MCP callers (the existing
  CLI builds, which are single-threaded) don't pay the executor
  overhead and don't depend on a worker thread.
- **Invariant correct by construction at the boundary.** The
  `@com_tool` decorator is the gate — every MCP-exposed COM tool
  goes through it. Forgetting to decorate is a registration-time
  error (the contract test catches it).

The cost: `PyWin32Adapter` is still unsafe if used directly from a
non-main thread *outside* MCP. We document this constraint in
`CODESTYLE.md` §6 (lane boundaries) — anyone using the adapter
from a multi-threaded context must wrap calls explicitly.

## 5. Module layout

New lane: `ai_sw_bridge.mcp` — between `mutate` and `com` in the
import-linter layer ordering. Sits above `com/` (depends on adapter +
executor), below `cli/` (CLI shouldn't import MCP server; they're
peers, not a chain).

```
src/ai_sw_bridge/mcp/
    __init__.py        # exports FastMCP server factory
    server.py          # main entry: create_server() + main() for stdio
    runtime.py         # ServerRuntime — holds executor + adapter + state
    tools.py           # @com_tool decorator + tool registration
    _tool_observe.py   # one tool function per ai-sw-observe subcommand
    _tool_build.py     # ai_sw_build tool
    _tool_apidoc.py    # ai_sw_apidoc:* tools (search, detail, members, examples, enum)
    _tool_history.py   # ai_sw_history:* tools (query) + sw_checkpoint_info
    _tool_reconnect.py # sw_reconnect (post-SW-death re-acquire)

tests/mcp_lane/
    __init__.py
    test_server_contract.py  # contract tests (§11 rows, one file)
```

The test directory is named ``mcp_lane`` (not ``mcp``) because a
``tests/mcp/__init__.py`` would register ``mcp`` in pytest's
``sys.modules`` before the real ``mcp`` PyPI package, shadowing it
and breaking ``from mcp.server.fastmcp import FastMCP`` at test
collection time. Renaming the directory avoids the collision without
requiring ``conftest.py`` hacks.

`pyproject.toml` adds:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0.0"]

[project.scripts]
ai-sw-mcp = "ai_sw_bridge.mcp.server:main"
```

`pyproject.toml [tool.importlinter]` layer order (insert `mcp` between
`mutate` and `com`):

```
ai_sw_bridge.cli
ai_sw_bridge.spec
ai_sw_bridge.parameterize
ai_sw_bridge.observe
ai_sw_bridge.mutate
ai_sw_bridge.mcp        # NEW
ai_sw_bridge.com
ai_sw_bridge.checkpoint
...
```

This means: `mcp` can import from `com`, `checkpoint`, `observe`,
etc., but `cli` doesn't import `mcp` (the MCP server is a peer
entry point, not a CLI extension).

## 6. Tool surface — v0.13 inventory

Each tool maps 1:1 to an existing CLI subcommand. The MCP tool name
follows the convention `<surface>_<verb>` (snake_case, no `ai_sw_`
prefix — the prefix is on the CLIs, not the MCP tools).

### 6.1 Observation (read-only)

| MCP tool | CLI equivalent | Arguments | Returns |
|---|---|---|---|
| `sw_active_doc` | `ai-sw-observe active_doc` | (none) | doc metadata dict |
| `sw_feature_errors` | `ai-sw-observe feature_errors` | (none) | non-OK features list |
| `sw_equations` | `ai-sw-observe equations` | (none) | equations dump |
| `sw_bbox` | `ai-sw-observe bbox` | (none) | bbox dict |
| `sw_volume` | `ai-sw-observe volume` | (none) | volume / area / mass |
| `sw_screenshot` | `ai-sw-observe screenshot` | width, height, fit_view, filename | screenshot path |
| `sw_measure` | `ai-sw-observe measure` | entity_a, entity_b | measurement dict |
| `sw_mate_errors` | `ai-sw-observe mate_errors` | (none) | per-mate status |
| `sw_custom_props` | `ai-sw-observe custom_props` | (none) | properties dict |
| `sw_enabled_addins` | `ai-sw-observe addins` | (none) | addins + known_problematic |

### 6.2 Build (write, validator-gated)

| MCP tool | CLI equivalent | Arguments | Returns |
|---|---|---|---|
| `sw_build` | `ai-sw-build` | spec_path, mode, save_as, save_format, disable_addins, strict_addins, checkpoint, checkpoint_encrypt | BuildResult dict |

The `sw_build` tool **does not accept inline spec JSON** in v0.13 —
the agent must save the spec to a file and pass the path. This
enforces the bridge's "spec as artifact" principle and lets the
validator run normally.

### 6.3 API documentation (RAG)

| MCP tool | CLI equivalent | Arguments | Returns |
|---|---|---|---|
| `sw_apidoc_search` | `ai-sw-apidoc search` | query, k, corpus | hits list |
| `sw_apidoc_detail` | `ai-sw-apidoc detail` | retrieval_key | chunk dict |
| `sw_apidoc_members` | `ai-sw-apidoc members` | interface | members list |
| `sw_apidoc_examples` | `ai-sw-apidoc examples` | limit, corpus | example chunks |
| `sw_apidoc_enum` | `ai-sw-apidoc enum` | enum_name | enum dict (or rc=0 + corpus_missing) |

### 6.4 History (checkpoint introspection)

| MCP tool | CLI equivalent | Arguments | Returns |
|---|---|---|---|
| `sw_history_part` | `ai-sw-history part <name>` | part_name, limit | checkpoint rows |
| `sw_history_since` | `ai-sw-history since <ISO-date>` | since, limit | checkpoint rows |
| `sw_history_diff` | `ai-sw-history diff <id-a> <id-b>` | id_a, id_b | structured diff |
| `sw_checkpoint_info` | `ai-sw-checkpoint info` | part_name, root | encryption status |

The `ai-sw-checkpoint genkey/rekey/migrate` subcommands are
**deliberately NOT exposed** as MCP tools — those operate on
credentials and at-rest encryption setup. They stay CLI-only.

### 6.5 Tools NOT exposed in v0.13

- `ai-sw-mutate apply` — mutation requires human-in-the-loop approval
  per the bridge's safety model. MCP clients can call
  `ai-sw-mutate diff` if we add a read-only diff tool later, but
  applying mutations is CLI-only.
- `ai-sw-codegen` — code generation is offline; doesn't fit MCP
  request/response.
- `ai-sw-probe` — already a one-shot CLI; redundant for an MCP client
  that can call individual observe tools.
- `ai-sw-checkpoint genkey/rekey/migrate` — credential operations,
  CLI-only (see §6.4).

## 7. Wire format

### 7.1 Tool input schema

Each tool's argument list is the same as its CLI counterpart's
argparse, expressed as MCP's input schema. `FastMCP` derives this
from Python type hints + docstrings.

Example:

```python
@mcp.tool()
@com_tool
def sw_screenshot(
    width: int = 800,
    height: int = 600,
    fit_view: bool = True,
    filename: str | None = None,
) -> dict[str, Any]:
    """Capture the active SW viewport to a PNG file."""
    return observe.sw_screenshot(
        width=width, height=height,
        fit_view=fit_view, filename=filename,
    )
```

### 7.2 Tool output payload

Every tool returns a dict matching the existing CLI's stdout JSON
envelope. No extra wrapping — what `ai-sw-observe bbox` prints to
stdout is exactly what `sw_bbox` returns.

FastMCP serializes to `content: [{ type: "text", text: <json> }]`
per the MCP spec. Clients parse the text as JSON.

**Known divergence — history / checkpoint-info error paths.** The CLI
surfaces "DB not found", "invalid timestamp", and "checkpoint id not
found" as `_emit_json({ok: False, …}, 2)` + `sys.exit(2)`. MCP has no
process-exit channel (JSON-RPC error responses carry a numeric code,
not a process rc), so the three history bodies and `sw_checkpoint_info`
return the same `{ok: False, …}` dict as their normal return value.
The agent sees a structured error payload it can recover from, not a
JSON-RPC `-32603` internal-error envelope. Success paths match the CLI
stdout byte-for-byte — no MCP-layer `ok: True` is added (the shared
library in `checkpoint/__init__.py` doesn't emit one). Audit record:
`docs/audit_s1_cli_mcp_parallelism.md` (W5.5 follow-up).

### 7.3 Tool error path

When a tool's underlying function raises:

- `ValidationError` (from `spec/validator.py`) → MCP error response
  with `code: -32602` (Invalid params), human message from the
  exception.
- `KeySourceError` (encryption mishap) → MCP error response,
  `code: -32603` (Internal error).
- `RuntimeError` from `ComExecutor` (SW dead, executor stopped) →
  MCP error response, `code: -32603`, with a hint to call
  `sw_reconnect` (if `--reconnect` is wired) or restart the server.
- Any other exception → MCP error response, `code: -32603`,
  full traceback in the message.

This is FastMCP's default behavior. We don't override.

## 8. Stdio transport + lifecycle

### 8.1 Entry point

```python
# src/ai_sw_bridge/mcp/server.py

def main() -> int:
    """Stdio entry point. Blocks until the client disconnects."""
    runtime = ServerRuntime.create()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        mcp.run(transport="stdio")
    finally:
        runtime.executor.stop()
        runtime.shutdown()
    return 0
```

### 8.2 Connection negotiation

`mcp` handles MCP `initialize` / capability negotiation. Our server
declares:

- `tools` capability — yes
- `resources` capability — no (v0.13)
- `prompts` capability — no (v0.13)

### 8.3 Add-in detection on first build call

Per W7.1, the first `sw_build` call enumerates add-ins. If
known-problematic add-ins are loaded, the build's payload includes
a `warnings` field naming them. The server does NOT auto-block —
MCP clients should surface the warning and let the user proceed
(matches the CLI's `--disable-addins` behavior, not
`--strict-addins`). If clients want strict behavior, they pass
`strict_addins=True` to the `sw_build` tool.

### 8.4 SW reconnect

When `ComExecutor.is_sw_dead` flips (W5.6 wires this), the next tool
call gets a `RuntimeError`. The MCP error response includes a hint
to call `sw_reconnect` (one tool that calls `runtime.reconnect()`,
which stops the dead executor, starts a fresh one, re-Dispatches
SldWorks.Application).

## 9. ServerRuntime

```python
# src/ai_sw_bridge/mcp/runtime.py

@dataclass
class ServerRuntime:
    executor: ComExecutor
    adapter: SolidWorksAdapter
    config: dict[str, Any]

    @classmethod
    def create(cls, *, adapter_type: str | None = None) -> "ServerRuntime":
        """Create a runtime. Does NOT start the executor — main() does."""
        adapter = AdapterFactory.create_adapter(adapter_type)
        executor = ComExecutor(name="SolidWorks-MCP-COM")
        return cls(executor=executor, adapter=adapter, config={})

    def reconnect(self) -> None:
        """Tear down the dead executor + adapter, start fresh."""

    def shutdown(self) -> None:
        """Final cleanup. Called from main()'s finally block."""
```

The runtime is the **single point of state** for the MCP server.
Tools access it via a module-level reference set in `create_server()`.

## 10. `@com_tool` decorator

```python
# src/ai_sw_bridge/mcp/tools.py

import functools
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def com_tool(fn: Callable[..., T]) -> Callable[..., T]:
    """Wrap an MCP tool so its body runs on the ComExecutor thread.

    The body is closed over with its args/kwargs and submitted to
    runtime.executor. Cross-thread COM safety is the load-bearing
    invariant — see docs/mcp_server_design.md §4 and
    docs/com_failure_modes.md row M-XX.

    Forgetting this decorator on a COM-touching tool is a real bug.
    The contract test (test_all_com_tools_wrapped) walks the registered
    tool set and asserts every tool that touches the adapter has
    @com_tool applied.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # `runtime` is set at server creation; tools that call
        # adapter.get_sw_app() before runtime is ready fail with
        # AttributeError — caught at the FastMCP error layer.
        from . import runtime as _rt
        return _rt.executor.run(lambda: fn(*args, **kwargs))
    # Tag the wrapper so the contract test can find it.
    wrapper._is_com_tool = True  # type: ignore[attr-defined]
    return wrapper
```

## 11. Test contract

Tests live in `tests/mcp_lane/`. Initial state has all tests marked
`@pytest.mark.skip(reason="W5.4-impl pending")` until the impl task
lands.

### 11.1 Runtime smoke (no SW needed)

- `test_create_runtime_returns_executor_and_adapter` — both wired.
- `test_runtime_shutdown_stops_executor` — no thread leak.
- `test_runtime_reconnect_resets_dead_state` — patched executor's
  `is_sw_dead` flips, then `reconnect()` clears it.

### 11.2 Tool registration

- `test_all_com_tools_have_decorator` — walk registered tools, every
  tool that calls `runtime.adapter.*` must have `_is_com_tool = True`
  on its wrapper. Forgetting the decorator is a registration-time
  fail.
- `test_tool_inventory_matches_design` — count tools, names match
  §6 inventory exactly.
- `test_excluded_tools_not_registered` — none of the four mutate
  operations (`sw_propose_local_change`, `sw_dry_run`, `sw_commit`,
  `sw_undo_last_commit`), the key-management ops
  (`sw_checkpoint_genkey`, `sw_checkpoint_rekey`,
  `sw_checkpoint_migrate`), nor `sw_codegen` / `sw_probe` are in
  the MCP tool registry — they remain CLI-only per §6.5.

### 11.3 @com_tool wrapping

- `test_com_tool_runs_on_executor_thread` — patched runtime; the
  wrapped function executes on the executor's worker thread, not the
  caller.
- `test_com_tool_propagates_exceptions` — function raises, MCP
  client sees a tool error.
- `test_com_tool_propagates_return_value` — function returns a dict,
  MCP client sees a dict.
- `test_com_tool_handles_executor_dead` — when executor's `is_sw_dead`
  is True, raises `RuntimeError` with reconnect hint.

### 11.4 Wire format

- `test_tool_returns_json_serializable` — every tool's return value
  passes `json.dumps`. (Catches accidental tuple / set / datetime
  returns.)
- `test_validation_error_maps_to_invalid_params` — `sw_build` on a
  malformed spec → MCP error with code -32602.

### 11.5 End-to-end (with `mcp` test transport)

- `test_initialize_handshake` — MCP `initialize` request → response
  with `tools` capability declared.
- `test_list_tools` — `tools/list` returns the design-doc inventory.
- `test_call_observe_bbox_against_mock` — `tools/call` with
  `name=sw_bbox`, adapter is MockAdapter, returns the expected dict.

## 12. Acceptance criteria (W5.4-impl ships when ALL pass)

- All §11 tests green (markers removed).
- `mcp>=1.0.0` added to `pyproject.toml [project.optional-dependencies] mcp`.
- `ai-sw-mcp` entry point in `pyproject.toml [project.scripts]`.
- `ai_sw_bridge.mcp` added to the import-linter layer list.
- `mypy src` still clean.
- `black --check .` still clean (full repo).
- `flake8` clean.
- `import-linter` 1 kept, 0 broken — including the new layer.
- License-lint clean (no new ported files; the MCP server is
  clean-room based on the design doc, not a code-lift).
- Manual smoke: `ai-sw-mcp` connects to Claude Desktop and serves the
  `sw_bbox` tool against a live SW session. (Captured as a screenshot
  in `docs/mcp_server_design.md` Appendix A by the impl task.)

## 13. Open questions (resolved at impl time)

- **Resources / prompts capabilities — v0.14+?** Resources would let
  the server expose `docs/api_reference.md` and the corpus chunks as
  navigable resources. Prompts would let the server ship pre-baked
  user-facing prompt templates (e.g., "build a drilled plate"). Both
  are clean v0.14+ additions; not in v0.13.
- **HTTP transport — v0.14+?** Stdio is the primary MCP transport
  today. HTTP is in the spec but not yet adopted by Claude Desktop.
  Defer until a real client needs it.
- **Per-tool timeouts.** `executor.run(timeout=...)` exists; should
  each tool declare a timeout? Default `None` (wait forever) matches
  the CLI; a future hardening pass adds per-tool timeouts driven by
  observation of real failure-mode durations.

---

## Appendix A — Why we don't port the upstream MCP server

The upstream `SolidworksMCP-python` (commit 82e505d8) ships
`src/solidworks_mcp/server.py` — ~700 lines wiring FastMCP +
pydantic-ai + Typer + loguru + a 6-table SQLite event log +
complexity-analyzer + intelligent-router + circuit-breaker +
response-cache + agent-history-db.

We port only the structural concepts:

- ComExecutor (✅ W5.1)
- Adapter ABC + factory (✅ W5.2)
- sw_type_info flagging (✅ W5.3 — Sonnet/GLM)
- Death-recovery semantics (✅ W5.6 — Sonnet/GLM)

The MCP server itself is **clean-room** because:

1. The upstream's tool surface (88+ tools) overlaps with the bridge's
   `spec/`, `observe.py`, and the CLIs. Re-porting would duplicate
   capability.
2. The upstream's safety surface (complexity-analyzer, intelligent-
   router, circuit-breaker) is the bridge's `spec/validator.py` +
   `errors/wrapper.py` already. Re-porting would conflict.
3. The upstream's agent-history-db is the bridge's `checkpoint/`
   already. Re-porting would conflict.

So the W5.4 attribution is **none** — no upstream code is lifted.
The architectural debt is captured in the W5.1/W5.2/W5.3/W5.6
attributions; the MCP server is a thin wrapper our team writes.

This is recorded for license-lint clarity: `mcp/server.py` and
`mcp/runtime.py` and `mcp/tools.py` have **no SPDX-Port-* tags**
because there is no port. License-lint sees no ported markers and
expects no CONTRIBUTING.md row — consistent.

## Appendix B — Why `@com_tool` is correct enough

The Track E audit (2026-05-28) noted that `PyWin32Adapter` doesn't
hold a `ComExecutor` internally. Option 2 (refactor the adapter)
would be architecturally cleaner. We chose Option 1 (decorate at
the MCP layer) because:

- v0.13 ships sooner.
- The invariant is enforced at the registration boundary (the
  contract test `test_all_com_tools_have_decorator`).
- Non-MCP callers (the existing CLIs) don't pay executor overhead.
- If a future use case needs a multi-threaded adapter outside MCP,
  Option 2 can land then — the public ABC is stable.

The risk we accept: a future contributor adds a COM-touching tool to
`mcp/_tool_*.py` and forgets `@com_tool`. The contract test
(`test_all_com_tools_have_decorator`) is the defense; CI catches it
before merge.
