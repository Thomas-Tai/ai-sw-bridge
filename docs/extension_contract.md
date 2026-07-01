# The Extension Contract

For contributors adding a capability.

`ai-sw-bridge` has exactly five places a new capability can be added:
a `feature_add` kind, a spec-type handler, a CLI verb, an MCP tool, or an
observe lane. Each has ONE canonical directory, ONE registration call, ONE
uniform signature, and ONE CI gate that fails the build if you skip a step.
This doc is the single unified model — read the row for the capability
you're adding, copy the recipe, and the CI gate below tells you whether you
did it right before a human has to.

Phase 0 ships this doc plus a **weak-form** conformance test
(`tests/test_extension_conformance.py`) that pins registry membership to
doc/tier membership. Phase 3 strengthens it into an architecture-defined
manifest; today it just refuses to let a new capability land silently.

## The five rows

| Capability | Canonical directory | Registration call | Uniform signature | CI gate |
|---|---|---|---|---|
| `feature_add` kind | `src/ai_sw_bridge/features/<kind>.py` | `_register_lane(kind, handler, SPIKE_STATUS)` (`features/__init__.py:57`) | `create_<kind>(doc, feature, target) -> tuple[bool, str \| None]` (`features/__init__.py:17`) | `tests/test_extension_conformance.py::test_every_feature_kind_named_in_readme_kind_table` — every `HANDLER_REGISTRY` key must appear backtick-quoted in the README kind table. |
| Spec type handler | Non-sketch: function in `src/ai_sw_bridge/spec/builder.py`. Sketch: `SketchHandler` subclass in `src/ai_sw_bridge/spec/sketches/` | Non-sketch: wire `_build_<type>` into the `handlers` dict inside `_wire_handlers()` and add a `FeatureType(...)` entry to `DESCRIPTORS` (`spec/builder.py:2058`, `spec/builder.py:2232`). Sketch: export the class from `spec/sketches/__init__.py` and wire `Handler().build` the same way via a `_build_sketch_<type>` adapter. | `_build_<type>(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature` (non-sketch) or `SketchHandler.build(self, ctx, feat) -> BuiltFeature` (sketch, template method over `_enter_sketch`/`_draw_geometry`/`_add_dimensions_inline`/`_record_deferred_dimensions`/`_finalize`) — both in `spec/_build_context.py` | Schema test in `tests/test_schema.py` + reference-check test in `tests/test_validator.py` (CONTRIBUTING.md "Adding a new feature primitive"); the type string must be in `schema.py`'s `ALL_TYPES` union. |
| CLI verb | `src/ai_sw_bridge/cli/<verb>.py` | Entry in `[project.scripts]` in `pyproject.toml`: `ai-sw-<verb> = "ai_sw_bridge.cli.<verb>:main"` | `def main() -> int` decorated with `@cli_stability(tier)` from `ai_sw_bridge.cli.stability` (tier is one of `"stable"`/`"experimental"`/`"deprecated"`) | `tests/test_extension_conformance.py::test_every_cli_script_has_a_stability_tier` — every module named by a `[project.scripts]` `ai-sw-*` verb must appear in `stability.TIER_REGISTRY` after that module is imported. |
| MCP tool | `src/ai_sw_bridge/mcp/_tool_<lane>.py`, registered from `src/ai_sw_bridge/mcp/server.py::create_server` | `@mcp.tool()` on a function inside that module's `register(mcp)`, called from `create_server` (e.g. `_tool_observe.register(mcp)`) | `@mcp.tool()` + `@com_tool` (from `ai_sw_bridge.mcp.tools`) wrapping a thin call into a `SolidWorksClient` facade method — return type is a JSON-shaped `dict[str, Any]`. Tools whose body must NOT run on the ComExecutor STA thread (e.g. `sw_batch_execute`, `_tool_reconnect`) are `@mcp.tool()`-only by documented exception. | `tests/mcp_lane/test_server_contract.py` — the registered tool-name set must equal the pinned `EXPECTED_TOOLS` frozenset (currently 37); adding a tool without updating `EXPECTED_TOOLS` fails the contract test. |
| Observe lane | Method on `SolidWorksObserver` in `src/ai_sw_bridge/observe.py` (or a dedicated `observe_<lane>.py` module for larger lanes, e.g. `observe_mbd.py`), exposed via `SolidWorksClient().observe.<lane>()` | No separate registry — the method itself IS the registration; wire the matching MCP tool (`@mcp.tool()` in `_tool_observe.py` or a lane-specific `_tool_<lane>.py`) and CLI subcommand (`cli/observe.py`) by hand. | `def <lane>(self) -> dict[str, Any]` returning the same JSON-shaped dict the legacy `sw_get_*`/`_sw_*_impl` free function returns; read-only, verify-the-EFFECT geometrically where applicable (never count+name+"no error"). | `tests/mcp_lane/test_server_contract.py` (if MCP-exposed) + the relevant offline test module (e.g. `tests/test_observe*.py`) pinning the returned dict shape. |

## Notes shared by every row

- **Verify-the-EFFECT, not the return code.** A COM call returning
  non-`None`/`True` is not proof anything happened (the W21/W42 ghost trap).
  Feature handlers gate on a geometric delta (volume/face/area/arc-length);
  observe lanes return the geometry itself.
- **Fail closed, don't raise, for `feature_add` handlers.** `create_<kind>`
  returns `(False, <reason>)` on failure — the same signature serves both
  dry-run and commit.
- **A lane must be seat-proven to advertise itself.** `_register_lane` only
  admits `SPIKE_STATUS == "GREEN"`; a recognized dormant sentinel
  (`UNFIRED`/`UNRUN`/`DEFERRED`/`WALLED`/`DORMANT`) is accepted but not
  registered; anything else raises `RuntimeError` at import time (fail-loud,
  not silent).
- **Absolute imports, `black --check .` clean, flake8-zero on `src/`.** Same
  global constraints as the rest of the codebase — see `CODESTYLE.md`.

## See also

- `CONTRIBUTING.md` — "Adding a new feature primitive" (the spec-type-handler
  row's step-by-step recipe, with the schema/validator/example steps this
  table doesn't repeat).
- `docs/mcp_server_design.md` §6.1 / §11 — the MCP tool inventory and its
  test-to-design cross-reference.
- `docs/spec_reference.md` — the per-primitive field reference for spec
  type handlers.
- `docs/DEFERRED.md` — kinds/lanes that are characterized OOP walls, kept
  for provenance but never advertised.
