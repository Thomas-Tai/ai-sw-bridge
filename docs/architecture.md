# Architecture

## Phases (how the codebase grew)

### Phase 1 — Observation (read-only, runs freely)

Module: [`observe.py`](../src/ai_sw_bridge/observe.py)

Six functions, each returns a JSON-serializable dict:

| Function | Purpose |
|---|---|
| `sw_get_active_doc()` | Path, type, title, dirty flag |
| `sw_get_feature_errors()` | Walks the feature tree, returns any non-OK feature with code + description |
| `sw_get_equations()` | Every equation, value, linked-file path, manager solver status |
| `sw_screenshot()` | SaveBMP → Pillow → PNG to `./captures/` |
| `sw_measure()` | Reads SW UI selection, calls IMeasure, returns Distance/Delta/Area/etc. |
| `sw_get_mate_errors()` | Walks MateGroup sub-features, reports per-mate status |

No mutation. Safe to invoke without approval. The CLI just serializes one function call per invocation.

### Phase 2 — Mutation (Propose-Approve-Execute, dry-run + rollback)

Module: [`mutate.py`](../src/ai_sw_bridge/mutate.py)

Four functions, all routed through `*_locals.txt`:

| Function | State transition |
|---|---|
| `sw_propose_local_change(var, new_value)` | `(nothing)` → `proposed` |
| `sw_dry_run(proposal_id)` | `proposed` → `dry_run_ok` \| `dry_run_broke` |
| `sw_commit(proposal_id)` | `dry_run_ok` → `committed` |
| `sw_undo_last_commit()` | `committed` → `undone` |

Proposals are JSON files in `./proposals/` (or `$AI_SW_BRIDGE_PROPOSALS`). Each record includes:

- `snapshot_text` — full `*_locals.txt` content at proposal time, used for rollback verification
- `dry_run_result` — before/after manager status, before/after var value, warnings, rebuild_ok flag
- `committed_at` / `undone_at` timestamps

The dry-run sequence:

1. Read manager status + current var value (BEFORE)
2. Lock `*_locals.txt` exclusively, read text, release lock
3. Compute new text via `replace_rhs` (preserves indent, line terminator, alignment)
4. Atomic write (`tmp file → os.replace`)
5. Call `EquationMgr.UpdateValuesFromExternalEquationFile` (reload linked file)
6. Call `IModelDoc2.EditRebuild3` (rebuild geometry)
7. Read manager status + new var value (AFTER)
8. **ROLLBACK**: atomic-write the snapshot back, rebuild again, verify on-disk state matches snapshot
9. Persist updated proposal state

The `finally:` block ensures rollback runs even if rebuild raises. Rollback writes are also under lock.

### Path C — Macro record + parameterize

Module: [`parameterize.py`](../src/ai_sw_bridge/parameterize.py)

The third major workflow added in v0.1.0. Not a "Phase" because it doesn't sit on the same propose/dry-run/commit ladder — it's an orthogonal capability for parametric part *authoring* rather than tuning.

Inputs:
- A user-recorded `.swp` from *Tools → Macro → Record* (binary OLE compound document)
- A JSON spec with `locals_path` + `bindings` list

Outputs:
- A plain-text `.bas` (VBA module source) the user pastes into VBE and runs

The parameterizer is **surgical**: it never modifies recorded code, only injects:

1. **After `Set Part = swApp.ActiveDoc`** — equation-link block (set `EquationMgr.FilePath`, `LinkToFile = True`, call `UpdateValuesFromExternalEquationFile`)
2. **Before `End Sub`** — dimension bindings via `EquationMgr.Add2(-1, formula, True)` for each `{dim, var}` pair

Why surgical? Recorded code uses exact SW API signatures for the user's specific SW version. Rewriting risks breaking signatures we cannot reliably re-author from outside (we tried that route first — see [known_gotchas.md](known_gotchas.md)).

## Why this design

### Why Propose-Approve-Execute

AI agents make mistakes. Even careful ones. A bridge that lets an AI "edit the model" needs three properties:

1. **Verifiable**: the agent sees the delta before committing
2. **Reversible**: a single command undoes the last change
3. **Auditable**: every change leaves a permanent record on disk

Propose-Approve-Execute hits all three. The dry-run shows the delta; the rollback restores the snapshot; the JSON proposal records persist.

### Why `*_locals.txt` as source of truth

SOLIDWORKS Equation Manager lets you either type values directly in the dialog OR link to an external `*_locals.txt` file. The latter:

- Survives a SW version migration (the linked file is plain text)
- Can be version-controlled
- Can be edited from outside SW (with the lock + atomic write discipline this package provides)
- Reload is explicit (`UpdateValuesFromExternalEquationFile`), so we control when the change propagates

Editing inside SW directly is fragile: changes can be silently overwritten next time the linked file reloads.

### Why JSON-out CLI rather than MCP / REST / RPC

- **MCP** ties us to one agent platform. Many AI products will exist; the CLI is universal.
- **REST** requires running a server, which is a lot of infrastructure for what is fundamentally a one-shot dispatch into a desktop app.
- **CLI + JSON** is trivially driven from any agent harness (Claude Code subprocess calls, OpenAI function-calling shells, plain shell scripts, even a manual operator).

If you want MCP, wrap these CLIs — that's a 50-line stdio server.

### Why late-binding pywin32 only

`win32com.client.gencache.EnsureDispatch("SldWorks.Application")` reliably fails with *"This COM object can not automate the makepy process"* on most SW installs. Without a typelib, every COM method call goes through `IDispatch::Invoke` and pywin32 cannot marshal certain argument types (Callout objects in SelectByID2; OUT parameters in GetErrorCode2 and Save3; the third arg of RunMacro2). We accept these limitations and use legacy single-call methods (`SelectByID`, `GetErrorCode`, `Save`) which marshal cleanly.

## Module dependency graph

```
   cli/probe.py
        |
        v
   cli/observe.py   cli/mutate.py   cli/codegen.py
        |               |               |
        v               v               v
     observe.py     mutate.py    parameterize.py
        \             /  \                |
         \           /    `--> locals_io.py
          \         /
           v       v
           sw_com.py
              |
              v
       pywin32 (Dispatch)
              |
              v
        SldWorks.Application
```

`sw_com.py` is the single chokepoint to the COM object. Anything that touches SW imports `get_sw_app`, `get_active_doc`, `resolve` from there.
