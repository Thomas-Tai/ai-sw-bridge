# Contributing to ai-sw-bridge

Thanks for your interest. This project is commercial and stable (v1.7.1).

## Quick start

```powershell
git clone https://github.com/Thomas-Tai/ai-sw-bridge.git
cd ai-sw-bridge
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Development workflow

1. Create a branch from `master`.
2. Make your changes.
3. Run the checks below.
4. Open a PR against `master`.

## Code style

Load-bearing patterns live in [`CODESTYLE.md`](CODESTYLE.md) — read
it before contributing code. The short version:

- **Formatter:** `black==25.12.0` (pinned). Run `black --check .` (whole tree).
- **Linter:** `flake8`. **Type checker:** `mypy` (config in `mypy.ini`).
- **Lane boundaries:** `import-linter` (config in `pyproject.toml`).
- **pywin32 late binding only** — never `gencache.EnsureDispatch`.
- **Two-stream contract** — stdout JSON, stderr text. Never both.
- **No co-author trailers in commits.**

### Pre-commit hooks

Install the hooks once, after cloning:

```powershell
pip install pre-commit
pre-commit install
```

`pre-commit` then runs `black`, `flake8`, `mypy`, and the spec linter on every
`git commit` — the same gates CI enforces. Run them across the whole tree at
any time with `pre-commit run --all-files`.

## Tests

```powershell
pytest
```

The test suite is pure-Python (no SOLIDWORKS needed). It covers schema validation, validator logic, locals file I/O, rhs resolution, and parameterization helpers. Integration tests that drive SW run behind the `solidworks_only`/`destructive_sw` markers (see `tests/e2e_sw/`); they are gated separately from the hermetic suite.

If you add a new feature primitive, add at least:
- A schema-level test in `tests/test_schema.py`
- A reference-check test in `tests/test_validator.py`

## Designing new code

Topic-keyed pointers to the right CODESTYLE.md section before you start:

- **When you're about to touch COM** — read [`CODESTYLE.md`](CODESTYLE.md) §2 (out-of-process marshaling discipline) and scan [`docs/com_failure_modes.md`](docs/com_failure_modes.md) for the operation you're about to perform. Late binding only (§2.1), every call is fallible (§2.3), verify the postcondition (§2.4).
- **When you're about to add a CLI** — read [`CODESTYLE.md`](CODESTYLE.md) §3 (the two-stream contract). stdout is JSON, stderr is text, there is no third stream. Add two-stream assertions to your tests (§9.2).
- **When you're about to wrap a failure path** — read [`CODESTYLE.md`](CODESTYLE.md) §4 (fail-soft for non-essential paths). Bare `except Exception` is correct for telemetry / sidecars / optional reads; it is wrong for the save verifier and the validator.
- **When you're crossing a lane boundary** — read [`CODESTYLE.md`](CODESTYLE.md) §6 (module boundaries) and check `[tool.importlinter]` in `pyproject.toml`. If your new import isn't in the contract, CI will fail — that's the contract doing its job.

## Commit style

Short, imperative mood. Examples from the project:

```
add fillet_constant_radius via SW 2020+ CreateDefinition pipeline
fix face-sketch-origin offset calculation for Y-shifted parents
docs: add Simplified Chinese translation
```

No co-author trailers.

## Adding a capability — the Extension Contract

There are exactly **five** places a new capability can be added. Each has one
canonical directory, one registration call, one uniform signature, and one CI
gate that fails the build if you skip a step. [`docs/extension_contract.md`](docs/extension_contract.md)
is the detailed per-row reference; the summary:

| Add a… | Directory | Register via | Uniform signature | CI gate |
|---|---|---|---|---|
| **`feature_add` kind** | `features/<kind>.py` | `_register_lane(kind, handler, SPIKE_STATUS)` | `create_<kind>(doc, feature, target) -> tuple[bool, str \| None]` | conformance: kind in README kind table + fail-loud registry |
| **spec type / handler** | `spec/handlers/<family>.py` (sketches: `spec/sketches/`) | re-export into `builder.py`, wire in `_wire_handlers()`, add a `FeatureType(...)` to `DESCRIPTORS` | `_build_<kind>(ctx: BuildContext, feat) -> BuiltFeature` | `doc_coverage_gate` + import-linter handler-leaf contract + `test_every_spec_handler_lives_in_handlers_package` |
| **CLI verb** | `cli/<verb>.py` | `@cli_stability(tier)` + `[project.scripts]` | `def main() -> int` (two-stream) | `two_stream_lint` + `TIER_REGISTRY` test |
| **MCP tool** | `mcp/_tool_<name>.py` | `@mcp.tool()` (+ `@com_tool`) via `register(mcp)` | tool fn → JSON `dict[str, Any]` | `EXPECTED_TOOLS` contract + `com_tool` decorator test |
| **observe lane** | `observe.py` / `observe_<x>.py` + facade method | facade property; optional MCP `_tool_observe` | `<lane>(self) -> dict[str, Any]` (read-only, verify-the-EFFECT) | facade / equivalence + contract tests |

### Two feature registries — two separate surfaces

Two of those rows build features and are easy to confuse. They are **two
distinct registries for two distinct surfaces** — pick by *when* the feature
is applied:

- **Spec-build handler** — a part-modelling feature declared inside a
  `spec.json` and materialized by `ai-sw-build`. Implement
  `_build_<kind>(ctx: BuildContext, feat) -> BuiltFeature` in the appropriate
  `src/ai_sw_bridge/spec/handlers/<family>.py` (dress_up, extrude, hole,
  pattern, revolve, sketch — or a new family module). Handlers **must not**
  live in `builder.py`: the import-linter handler-leaf contract and
  `test_every_spec_handler_lives_in_handlers_package` fail the build if one
  does. `builder.py` is pure orchestration.
- **`feature_add` handler** — an imperative mutation on an *already-open*
  model, the `client.mutate` / `ai-sw-batch` path. Register in
  `features/HANDLER_REGISTRY` via `_register_lane(kind, handler, SPIKE_STATUS)`
  with signature `create_<kind>(doc, feature, target) -> tuple[bool, str | None]`
  (fail-closed: return `(False, reason)`, never raise).

### Spec-build handler recipe

1. **Add the schema** in `src/ai_sw_bridge/spec/schema.py` — define a per-feature schema dict, add it to the `oneOf` list in `SCHEMA`, and add the type string to the appropriate set (`SKETCH_TYPES`, `EXTRUDE_TYPES`, or `MODIFY_TYPES`).
2. **Update the validator** in `src/ai_sw_bridge/spec/validator.py` — if the new type references a parent feature, add it to `FACE_SKETCH_TYPES` or handle it in `_check_references`.
3. **Add the handler in the family leaf.** Implement `_build_<type>(ctx, feat) -> BuiltFeature` in the matching `src/ai_sw_bridge/spec/handlers/<family>.py`, then re-export it into `builder.py` (`from .handlers.<family> import _build_<type>  # noqa: F401`) so `_wire_handlers()` resolves it by name, wire it into the `handlers` dict inside `_wire_handlers`, and add a `FeatureType(...)` entry to `DESCRIPTORS` with any `dim_fields`. Sketch features (rectangle/circle on plane or face, circle arrays) are instead `SketchHandler` subclasses in `src/ai_sw_bridge/spec/sketches/`: subclass `SketchHandler`, override `_enter_sketch` / `_draw_geometry` / `_add_dimensions_inline` / `_record_deferred_dimensions` / `_finalize` (and optionally `_strip_relations`), export the class from `sketches/__init__.py`, and wire `Handler().build` into `_wire_handlers` via the corresponding `_build_sketch_<type>` adapter. Every COM-touching handler needs the postcondition verification pattern from [`CODESTYLE.md`](CODESTYLE.md) §2.4 — verify the postcondition, not the return code.
4. **Spike first.** For SW API calls you haven't used before, write a spike script in `spikes/` that exercises the API via pywin32 late-binding. Verify arg counts against `sldworksapi.chm` (or `tools/chm_extract.py`).
5. **Add an example** in `examples/` with a `spec.json` and a `README.md` explaining what it builds.
6. **Update docs** — add the primitive to the capability matrix in `README.md` and to `docs/spec_reference.md`.

### Architecture reference

For how these layers fit together — the public class API, the facades and the
`_impl` cores they delegate to, the spec handler families, the resilience
envelope, and the CI-enforced import hierarchy — read the canonical
[`docs/CLASS_RELATION_MAP.md`](docs/CLASS_RELATION_MAP.md) (the *structure*),
companion to [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md) (the *contract*).

## Reporting issues

Before opening an issue, scan [`docs/com_failure_modes.md`](docs/com_failure_modes.md) for the symptom — most repeat failures are already documented there with a diagnostic and mitigation.

Please include:
- The spec JSON (or a minimal repro)
- Full CLI output with traceback
- SOLIDWORKS version (Help → About → revision string)
- `doc.GetPartBox(True)` output after the (partial) build, if applicable

## Translating docs

See [`docs/i18n/TRANSLATION_PROMPT.md`](docs/i18n/TRANSLATION_PROMPT.md) for the parameterized translation prompt. The DO-NOT-TRANSLATE list in that prompt is the authoritative reference for which technical terms must survive translation verbatim.

**i18n freshness is a PR gate.** If your change touches `README.md`, `USAGE.md`, or `docs/PUBLIC_API.md`, the Simplified/Traditional Chinese mirrors under `docs/i18n/{zh-CN,zh-TW}/` are now out of date, and you must do **one** of two things before the PR is merge-ready:

- **Re-translate** the affected mirror(s) and bump each `translated-from:` frontmatter SHA to the source's new commit (mirror lands *fresh*); **or**
- **Mark them honestly stale** by adding the `<!-- i18n-staleness-banner -->` sentinel (with localized banner prose) to each affected mirror.

`tests/test_i18n_staleness.py` enforces the biconditional *stale ⇔ sentinel* in CI (it runs with `fetch-depth: 0`), so a stale mirror with no banner — or a fresh one with a stale banner — fails the build. Honest lag is allowed; silent rot is not. English remains the single authoritative surface. See the "staleness gate" section of `TRANSLATION_PROMPT.md` for the full contract.

**Performance freshness is also a gate.** If you change the feature-build hot path (`src/ai_sw_bridge/spec/`, `src/ai_sw_bridge/features/`, `src/ai_sw_bridge/cli/build.py`, or `examples/*/spec.json`), the committed performance receipt (`tools/perf_baselines/receipt.json`) is now stale. Before the change is merge-ready, either **re-measure on a live seat** (`python tools/regression_check.py --check --baseline-compare tools/perf_baselines/v0.10.json --emit-receipt tools/perf_baselines/receipt.json`) and commit the fresh receipt, **or** set `lag_acknowledged: true` (+ a `lag_reason`) on it. `tests/test_perf_receipt.py` enforces `stale ⇔ lag_acknowledged` and re-derives the SLO verdict from the raw numbers (it never trusts a committed pass/fail). See `docs/perf_gate.md`.

## Port attribution

When porting code from upstream repositories, three attribution surfaces are
required:

1. **Docstring** — module-level SPDX tags + upstream commit SHA
2. **This table** — one row per ported file
3. **README.md** — one consolidated-credit line per upstream repo

| Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `src/ai_sw_bridge/errors/circuit_breaker.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-24 | TBD | `src/solidworks_mcp/adapters/circuit_breaker.py` — sync wrapper extraction |
| `src/ai_sw_bridge/com/executor.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/com_executor.py` — replaced loguru with stdlib logging, added is_dead introspection, drain pending on shutdown |
| `src/ai_sw_bridge/com/adapter.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/base.py` — simplified to sync interface, removed pydantic dependency |
| `src/ai_sw_bridge/com/adapters/mock.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/mock_adapter.py` — simplified mock dispatch for testing |
| `src/ai_sw_bridge/com/adapters/pywin32.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/pywin32_adapter.py` — late-binding COM dispatch wrapper |
| `src/ai_sw_bridge/com/factory.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/factory.py` — simplified factory with platform-based auto-selection |
| `src/ai_sw_bridge/com/sw_type_info.py` | [SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT | 82e505d88da07fd81acd66b3cd85f6da65323ee4 | 2026-05-28 | TBD | `src/solidworks_mcp/adapters/sw_type_info.py` — replaced loguru with stdlib logging; per-interface COM method flagging |

## License

The project ships under a commercial/proprietary [LICENSE](LICENSE) as of v1.5.0.
By contributing, you agree to the [Contributor License Agreement](CLA.md), which
grants the right to license your contribution under that commercial license
(and open-source terms). Third-party material in a contribution must be declared
so it can be recorded in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and the
port-attribution table above.
