# Migration Guide: v0.11 to v0.12

This document describes what changed between ai-sw-bridge v0.11.0 and
v0.12.0 for users upgrading existing projects.

## Backward compatibility

Every spec that built successfully in v0.11 builds in v0.12 with all feature
flags OFF and produces byte-identical output. No schema fields were removed or
renamed. No CLI flags changed behavior. The upgrade is additive only.

## Schema changes (additive)

Two new optional fields were added to the spec schema. Neither is required
for existing specs.

### `brep` block (per-feature, optional)

When `flags.brep_interrogation` is enabled, the builder appends a `brep`
block to each feature's output in the build manifest. The block contains
topological fingerprint data extracted from the SOLIDWORKS B-rep kernel:

```json
{
  "feature_id": "Extrude_Plate",
  "brep": {
    "faces": [
      {
        "face_id": "face_0",
        "fingerprint": "a3f2c1...",
        "normal": [0.0, 0.0, 1.0],
        "centroid": [25.0, 25.0, 5.0],
        "box": [0.0, 0.0, 5.0, 50.0, 50.0, 5.0],
        "body_id": 0
      }
    ]
  }
}
```

Specs that do not enable `brep_interrogation` produce no `brep` block.
See `spec.md` section 2 for the full B-rep schema definition.

### `face_role` field (optional)

A new optional `face_role` string field on face-referencing spec primitives
(`sketch_*_on_face`, `simple_hole`). When present, the validator resolves
the symbolic role (e.g., `"top"`, `"bottom"`) to a concrete face ID at
validation time using the B-rep manifest from prior features.

Specs that use literal face coordinates (the v0.11 approach) continue to
work unchanged. `face_role` is an alternative targeting mechanism, not a
replacement.

## CLI changes (additive)

### `--enable-flag` / `--disable-flag`

The feature-flag CLI overrides introduced in v0.11 now gate three new lanes:

| Flag | Lane | Default | What it gates |
|---|---|---|---|
| `brep_interrogation` | L1 | OFF | B-rep interrogation after each feature build |
| `checkpoint` | L4 | OFF | SQLite checkpoint writes per feature |
| `rag_apidoc` | L3 | OFF | RAG-indexed API doc retrieval |

All three flags default to OFF. Enabling a flag activates its lane; disabling
is a no-op when the flag is already OFF. The four-level precedence chain
(CLI > env var > `.ai-sw-bridge.toml` > registry default) is unchanged
from v0.11.

Usage:

```powershell
ai-sw-build spec.json --no-dim --enable-flag brep_interrogation
ai-sw-build spec.json --no-dim --enable-flag checkpoint
```

### `ai-sw-history` (new CLI)

A new `ai-sw-history` command provides checkpoint query subcommands when
`flags.checkpoint` is enabled. Marked `@cli_stability(Tier.EXPERIMENTAL)`.

Subcommands: `part <path>`, `locals <path>`, `since <ts>`.

This CLI does not exist in v0.11. It is a no-op when `checkpoint` is OFF.

## New output files (sidecar)

When new lanes are enabled, the builder writes additional files alongside
the existing `build_metrics.json`:

| File | Gated by | Contents |
|---|---|---|
| `build_brep.json` | `brep_interrogation` | Per-feature B-rep manifest (faces, normals, centroids, fingerprints) |
| `<part>.sqlite` | `checkpoint` | SQLite checkpoint store (per-feature snapshots, locals, tree hashes) |

Neither file is written when its flag is OFF. Existing build pipelines that
do not enable new flags produce the same output as v0.11.

## What did NOT change

- Spec schema version (`schema_version: 1`) is unchanged.
- All 16 feature types from v0.11 work identically.
- `--no-dim` behavior is unchanged.
- `--lint` checks are unchanged (new `face_role` validation is additive).
- `--validate-only` and `--dry-run` behavior is unchanged.
- The two-stream contract (stdout JSON, stderr human text) is unchanged.
- `ai-sw-mutate` and `ai-sw-observe` are unchanged.
- The `locals.txt` equation file format is unchanged.

## Upgrading

No action required for existing specs. To use new capabilities:

1. **B-rep interrogation**: add `--enable-flag brep_interrogation` to your
   build command. Review `build_brep.json` for topological fingerprints.
2. **Checkpoints**: add `--enable-flag checkpoint` to persist per-feature
   build state. Use `ai-sw-history` to query checkpoint history.
3. **RAG API docs**: add `--enable-flag rag_apidoc` to enable API
   documentation retrieval during spec authoring (requires the API index
   built via `tools/build_api_index.py`).

All flags can also be set in `.ai-sw-bridge.toml`:

```toml
[flags]
brep_interrogation = true
checkpoint = true
```
