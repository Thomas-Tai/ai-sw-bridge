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

- **Formatter:** `black` (line-length 88, default settings). Run before committing:
  ```powershell
  pip install black
  black .
  ```
- **No type-checking CI yet**, but the codebase uses type annotations. Keep them accurate.

## Tests

```powershell
pytest
```

The test suite is pure-Python (no SOLIDWORKS needed). It covers schema validation, validator logic, locals file I/O, rhs resolution, and parameterization helpers. Integration tests that drive SW are manual for now.

If you add a new feature primitive, add at least:
- A schema-level test in `tests/test_schema.py`
- A reference-check test in `tests/test_validator.py`

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
3. **Add the builder handler** in `src/ai_sw_bridge/spec/builder.py` — implement `_build_<type>`, wire it in `_wire_handlers`, and register it in `FEATURE_REGISTRY` with any `dim_fields`.
4. **Spike first.** For SW API calls you haven't used before, write a spike script in `spikes/` that exercises the API via pywin32 late-binding. Verify arg counts against `sldworksapi.chm` (or `tools/chm_extract.py`).
5. **Add an example** in `examples/` with a `spec.json` and a `README.md` explaining what it builds.
6. **Update docs** — add the primitive to the capability matrix in `README.md` and to `docs/spec_reference.md`.

## Reporting issues

Please include:
- The spec JSON (or a minimal repro)
- Full CLI output with traceback
- SOLIDWORKS version (Help → About → revision string)
- `doc.GetPartBox(True)` output after the (partial) build, if applicable

## Translating docs

See [`docs/i18n/TRANSLATION_PROMPT.md`](docs/i18n/TRANSLATION_PROMPT.md) for the parameterized translation prompt. The DO-NOT-TRANSLATE list in that prompt is the authoritative reference for which technical terms must survive translation verbatim.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
