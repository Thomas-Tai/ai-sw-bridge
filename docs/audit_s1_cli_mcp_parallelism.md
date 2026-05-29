# S1 — CLI / MCP Parallelism Audit (W5.5 follow-up)

One row per tool. The 21-tool surface minus 4 that were spot-checked in
Wave 5 = 17 tools in scope.

## Audit method

For each MCP tool body, I read the matching CLI subcommand body side-by-
side and traced the shared-library function both delegate to. Key sets
were compared on the happy-path return payload. Value semantics were
compared on the same.

## Table

| MCP tool              | Shared library fn          | Key-set match | Value-semantics match | Notes                                                       |
|-----------------------|----------------------------|---------------|-----------------------|-------------------------------------------------------------|
| sw_active_doc         | observe.sw_get_active_doc  | IDENTICAL     | IDENTICAL             | Both get `ok` from the shared fn.                           |
| sw_feature_errors     | observe.sw_get_feature_errors | IDENTICAL  | IDENTICAL             |                                                             |
| sw_equations          | observe.sw_get_equations   | IDENTICAL     | IDENTICAL             |                                                             |
| sw_bbox               | observe.sw_get_bbox        | IDENTICAL     | IDENTICAL             |                                                             |
| sw_volume             | observe.sw_get_volume      | IDENTICAL     | IDENTICAL             |                                                             |
| sw_screenshot         | observe.sw_screenshot      | IDENTICAL     | IDENTICAL             |                                                             |
| sw_measure            | observe.sw_measure         | IDENTICAL     | IDENTICAL             |                                                             |
| sw_mate_errors        | observe.sw_get_mate_errors | IDENTICAL     | IDENTICAL             |                                                             |
| sw_custom_props       | observe.sw_get_custom_props| IDENTICAL     | IDENTICAL             |                                                             |
| sw_enabled_addins     | observe.sw_get_enabled_addins | IDENTICAL  | IDENTICAL             |                                                             |
| sw_build              | spec.builder.build + BuildResult.to_dict | IDENTICAL (core) | IDENTICAL (core) | Mode encoding differs — see D1 below.                       |
| sw_apidoc_detail      | rag.VectorIndex.get_chunk  | IDENTICAL     | IDENTICAL             | Both paths share the same chunk-to-dict helper.             |
| sw_apidoc_members     | rag.VectorIndex.list_interfaces / _conn.execute | IDENTICAL | IDENTICAL     |                                                             |
| sw_apidoc_examples    | rag.VectorIndex.find_with_code | IDENTICAL  | IDENTICAL             |                                                             |
| sw_history_part       | checkpoint.by_part         | MCP EXTRA     | —                     | **FIX applied (D2):** removed MCP-layer `ok: True`.         |
| sw_history_since      | checkpoint.since           | MCP EXTRA     | –                     | **FIX applied (D2):** removed MCP-layer `ok: True`.         |
| sw_history_diff       | checkpoint.feature_diff    | MCP EXTRA     | –                     | **FIX applied (D2):** removed MCP-layer `ok: True`.         |

## Documented divergences (not bugs)

**D1 — sw_build mode encoding.** CLI emits two booleans (`no_dim`,
`deferred_dim`); MCP emits one string (`mode`). Design doc §6.2 rows
`mode` as an MCP argument, so the divergence is by design. No fix.

**D2 — History success-path `ok: True` (REMOVED).** The CLI's
`ai-sw-history` success payloads (`part`, `since`, `diff`) carry no
`ok` field — the shared library in `checkpoint/__init__.py` returns
bare `{subcommand, part_name, count, checkpoints}` shapes. The MCP
wrappers had been adding `ok: True` at the MCP layer, violating design
doc §7.2 ("No extra wrapping — what `ai-sw-observe bbox` prints to
stdout is exactly what `sw_bbox` returns."). Fix: remove the MCP-layer
`ok: True` from the three success paths. Snapshot fixtures regenerated
to match.

**D3 — History / checkpoint-info error paths return structured dicts.**
The CLI emits `_emit_json({ok: False, …}, 2)` and exits with rc=2; the
MCP wrapper returns the same dict as the tool's return value. MCP has
no exit-code channel (JSON-RPC error responses use numeric codes, not
process rc), so the MCP-layer error dicts are a structural necessity.
Design doc §7.3 enumerates the error mappings (ValidationError →
-32602, RuntimeError → -32603) but the history tools currently return
structured `ok: False` dicts instead of raising. Keeping this as-is
because a structured payload is more useful to an MCP client than a
JSON-RPC error code for "DB not found" and "invalid timestamp" — both
of which the agent can recover from. No fix; design doc note added.

## Out of scope for S1

- Tools excluded from MCP surface per §6.5 (the four mutate
  operations: sw_propose_local_change, sw_dry_run, sw_commit,
  sw_undo_last_commit; plus sw_codegen, sw_probe,
  sw_checkpoint_genkey/rekey/migrate): no MCP body exists to compare.
- Argument-level schema differences (MCP has no `--dry-run`, `--lint`,
  `--verify-mass`, `--reconnect`, `--auto-retry` on sw_build): these
  are deliberate omissions from the v0.13 MCP surface, documented in
  §6.2.
- `sw_apidoc_search` `backend="auto"` resolution and the committed-
  index default: identical on both surfaces.
