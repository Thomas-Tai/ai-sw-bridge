# Deprecation & Schema-Migration Policy

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
