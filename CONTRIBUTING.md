# Contributing to ai-sw-bridge

Thanks for your interest. This project is early-stage (v0.2) and actively evolving.

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

The test suite is pure-Python (no SOLIDWORKS needed). It covers schema validation, validator logic, locals file I/O, rhs resolution, and parameterization helpers. Integration tests that drive SW are manual for now.

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

## Adding a new feature primitive

The recipe (established by `fillet_constant_radius` in v0.2):

1. **Add the schema** in `src/ai_sw_bridge/spec/schema.py` — define a per-feature schema dict, add it to the `oneOf` list in `SCHEMA`, and add the type string to the appropriate set (`SKETCH_TYPES`, `EXTRUDE_TYPES`, or `MODIFY_TYPES`).
2. **Update the validator** in `src/ai_sw_bridge/spec/validator.py` — if the new type references a parent feature, add it to `FACE_SKETCH_TYPES` or handle it in `_check_references`.
3. **Add the builder handler.** Non-sketch features (extrude, cut, fillet, chamfer, pattern, mirror, hole) are functions in `src/ai_sw_bridge/spec/builder.py`: implement `_build_<type>`, wire it in `_wire_handlers`, and register it in `FEATURE_REGISTRY` with any `dim_fields`. Sketch features (rectangle/circle on plane or face, circle arrays) are subclasses of `SketchHandler` in `src/ai_sw_bridge/spec/sketches/`: add a new module under `sketches/`, subclass `SketchHandler`, override `_enter_sketch` / `_draw_geometry` / `_add_dimensions_inline` / `_record_deferred_dimensions` / `_finalize` (and optionally `_strip_relations`), export the class from `sketches/__init__.py`, and wire `Handler().build` into `_wire_handlers` via the corresponding `_build_sketch_<type>` adapter. Every COM-touching handler needs the postcondition verification pattern from [`CODESTYLE.md`](CODESTYLE.md) §2.4 — verify the postcondition, not the return code.
4. **Spike first.** For SW API calls you haven't used before, write a spike script in `spikes/` that exercises the API via pywin32 late-binding. Verify arg counts against `sldworksapi.chm` (or `tools/chm_extract.py`).
5. **Add an example** in `examples/` with a `spec.json` and a `README.md` explaining what it builds.
6. **Update docs** — add the primitive to the capability matrix in `README.md` and to `docs/spec_reference.md`.

## Reporting issues

Before opening an issue, scan [`docs/com_failure_modes.md`](docs/com_failure_modes.md) for the symptom — most repeat failures are already documented there with a diagnostic and mitigation.

Please include:
- The spec JSON (or a minimal repro)
- Full CLI output with traceback
- SOLIDWORKS version (Help → About → revision string)
- `doc.GetPartBox(True)` output after the (partial) build, if applicable

## Translating docs

See [`docs/i18n/TRANSLATION_PROMPT.md`](docs/i18n/TRANSLATION_PROMPT.md) for the parameterized translation prompt. The DO-NOT-TRANSLATE list in that prompt is the authoritative reference for which technical terms must survive translation verbatim.

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
