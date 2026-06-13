# Face Roles, Manifests, and Feature Flags — Reference

This document lists every face role, manifest type, and feature flag shipped
with `ai-sw-bridge`. Every entry is traced to the source code — no invented
names or flags.

## Face Roles (role_hint)

When the `brep_interrogation` feature flag is enabled, every face created by
a build feature is automatically assigned a **role hint** based on its
axis-aligned normal and position. These roles are used for symbolic face
selection in downstream features.

### Available role_hint values

The role hint is computed by
[`brep/interrogator.py::_role_hint`](../src/ai_sw_bridge/brep/interrogator.py)
from the face's unit normal, centroid, and bounding box:

| role_hint | When assigned |
|---|---|
| `+x_outboard` | Normal is +X; centroid is on the +X side of the bbox midpoint |
| `-x_inboard` | Normal is -X; centroid is on the -X side of the bbox midpoint |
| `+y_outboard` | Normal is +Y; centroid is on the +Y side of the bbox midpoint |
| `-y_inboard` | Normal is -Y; centroid is on the -Y side of the bbox midpoint |
| `+z_outboard` | Normal is +Z; centroid is on the +Z side of the bbox midpoint |
| `-z_inboard` | Normal is -Z; centroid is on the -Z side of the bbox midpoint |
| `oblique` | Normal is not axis-aligned (falls through all axis checks) |

The "outboard" vs "inboard" distinction is decided by comparing the face
centroid's signed projection along the normal against the bbox midpoint along
the dominant axis. For a centered 20x20x10 mm box built on Front Plane, the
six faces map to the six axis-aligned roles above.

> **Note:** side is judged independently of the normal's sign, so the mixed
> pairings (`+x_inboard`, `-x_outboard`, `+y_inboard`, …) are also valid outputs
> whenever a face's centroid sits on the far side of the bbox midpoint (e.g. an
> inward-facing pocket wall). The six rows above are the common case for a
> roughly centered part — not the exhaustive value space.

### Using face_role in a spec

A face-bound feature can reference a parent feature's face by its role hint
instead of by coordinate. Add `face_role` and `of_feature` to the feature:

```json
{
  "type": "sketch_circle_on_face",
  "name": "SK_TopHole",
  "of_feature": "Extrude_Box",
  "face_role": "+z_outboard",
  "radius": 3.0
}
```

The validator
([`spec/validator.py::_check_face_role_shapes`](../src/ai_sw_bridge/spec/validator.py))
confirms that `face_role` is a non-empty string and that the feature type is
face-bound. At build time, the resolver
([`brep/resolver.py::resolve_face_role`](../src/ai_sw_bridge/brep/resolver.py))
looks up the face in the parent's B-rep manifest block by case-insensitive
role match.

### Feature types that support face_role

Only these feature types accept `face_role` (defined in
[`spec/validator.py::FACE_BOUND_TYPES`](../src/ai_sw_bridge/spec/validator.py)):

| Feature type | Purpose |
|---|---|
| `sketch_rectangle_on_face` | Rectangle sketch on a parent feature's face |
| `sketch_circle_on_face` | Circle sketch on a parent feature's face |
| `sketch_circles_on_face` | Multi-circle sketch on a parent feature's face |
| `simple_hole` | Blind or through-all hole on a parent feature's face |

### Disambiguation

When multiple faces share the same `role_hint`, the resolver raises
`FaceAmbiguityError` and lists the candidate fingerprints. Add a
`face_centroid_hint` field to the spec to disambiguate — the resolver picks
the face whose centroid is closest to the hint.

### Case-insensitive matching

Role matching is case-insensitive: `"top"` matches a face whose `role_hint`
is `"TOP"`, `"+Z_OUTBOARD"`, or any casing variant. The resolver lowercases
both the query and the stored hint before comparison.

## Manifests

The bridge produces two manifest types. Both are JSON-serializable and
versioned.

### B-rep Manifest

The **B-rep manifest** is a per-build record of every face created during a
build. It is populated only when the `brep_interrogation` feature flag is
enabled.

**Structure** (schema version 1, defined in
[`brep/manifest.py::Manifest`](../src/ai_sw_bridge/brep/manifest.py)):

```json
{
  "schema_version": 1,
  "features": [
    {
      "feature": "Extrude_Box",
      "type": "boss_extrude_blind",
      "faces": [
        {
          "fingerprint": "a3f9...",
          "role_hint": "+z_outboard",
          "normal": [0.0, 0.0, 1.0],
          "centroid": [0.0, 0.0, 10.0],
          "bbox": [-10.0, -10.0, 10.0, 10.0, 10.0, 10.0],
          "area_mm2": 400.0,
          "body_id": 0,
          "face_idx": 0,
          "is_surface": false
        }
      ]
    }
  ],
  "active_configuration": "Default"
}
```

Each face carries:

| Field | Description |
|---|---|
| `fingerprint` | SHA-256 hash of (normal + centroid + area) — stable across rebuilds |
| `role_hint` | Axis-aligned role (see table above) |
| `normal` | Unit normal vector [nx, ny, nz] |
| `centroid` | Face centroid in mm [x, y, z] |
| `bbox` | Axis-aligned bounding box [x_min, y_min, z_min, x_max, y_max, z_max] |
| `area_mm2` | Face area in mm^2 |
| `body_id` | Body index within the feature |
| `face_idx` | Face index within the body |
| `is_surface` | True for surface bodies, false for solid bodies |
| `persist_id` | (optional) Durable persist-reference token; present only when `persist_capture` flag is on |

When the manifest is populated, it appears in the build result under the
`brep_manifest` key and is also written as a `build_brep.json` sidecar next
to the saved `.sldprt`.

### Assembly Manifest

The **assembly manifest** is a JSON sidecar written alongside the `.sldasm`
file at assembly commit time. It stores the verbatim assembly spec plus a
runtime overlay of resolved part paths and SOLIDWORKS instance names.

**Structure** (schema version 2, defined in
[`assembly/storage.py`](../src/ai_sw_bridge/assembly/storage.py)):

```json
{
  "schema_version": 2,
  "spec": {
    "kind": "assembly",
    "name": "my_assembly",
    "components": [
      {"id": "block_a", "part": "block_20mm.sldprt", "transform": {"xyz_mm": [0, 0, 0]}}
    ],
    "mates": [
      {"type": "coincident", "a": {"component": "block_a", "face_ref": {}}, "b": {"component": "block_b", "face_ref": {}}}
    ]
  },
  "runtime": {
    "components": [
      {
        "id": "block_a",
        "sw_name": "block_20mm-1",
        "part_path": "block_20mm.sldprt"
      }
    ]
  }
}
```

The manifest is consumed by `ai-sw-assembly edit --manifest <path> --op <json>`
to apply declarative edits (add/remove components or mates) to an existing
assembly. The edit validates the op against the manifest, produces a new
proposal, and routes through the standard propose -> dry_run -> commit
lifecycle.

**How to select/list:** the assembly manifest is written to disk at commit time
alongside the `.sldasm` file (same base name, `.manifest.json` extension).
There is no listing command — the manifest is a file on disk, not a runtime
registry. Open it with any JSON viewer, or pass its path to
`ai-sw-assembly edit`.

## Feature Flags

Feature flags control optional capabilities. Resolution priority (highest
first):

1. CLI flag override (`--enable-flag` / `--disable-flag`)
2. Environment variable (`AI_SW_BRIDGE_FLAG_<NAME>`)
3. Per-repo `.ai-sw-bridge.toml` `[flags]` section
4. Module defaults (defined in the registry)

### Available flags

Defined in
[`flags.py::FLAG_REGISTRY`](../src/ai_sw_bridge/flags.py):

| Flag name | Default | Lane | Description |
|---|---|---|---|
| `brep_interrogation` | `false` | L1 | B-rep interrogation — topological fingerprint + face metadata in build output. Enables the B-rep manifest and `face_role` resolution. |
| `rag_apidoc` | `false` | L3 | RAG-indexed API documentation retrieval for spec authoring assistance via `ai-sw-apidoc`. |
| `checkpoint` | `false` | L4 | Per-feature build checkpoints — persist build state to SQLite for mid-session resume and post-mortem. |
| `mcp_wrapper` | `false` | M | MCP server wrapper — expose the bridge as an MCP tool server via `ai-sw-mcp`. |
| `schema_v2` | `false` | core | Schema v2 surface — accept material/units top-level fields and optional drawing/export blocks. |
| `persist_capture` | `false` | core | Durable selection — capture per-face `GetPersistReference3` tokens into the B-rep manifest. Requires `brep_interrogation`. |

### Enabling flags

**CLI (one build):**

```powershell
ai-sw-build spec.json --no-dim --enable-flag brep_interrogation
```

**Environment variable (session):**

```powershell
$env:AI_SW_BRIDGE_FLAG_BREP_INTERROGATION = "1"
ai-sw-build spec.json --no-dim
```

**Config file (repo-wide):**

Create `.ai-sw-bridge.toml` in the repo root:

```toml
[flags]
brep_interrogation = true
persist_capture = true
```

## How to discover what's available

| Question | How to answer |
|---|---|
| What CLI commands exist? | See the table in [`docs/ONBOARDING.md`](ONBOARDING.md) or run any `ai-sw-* --help` |
| What observe subcommands exist? | Run `ai-sw-observe --help` — lists all 28 subcommands |
| What feature types can I build? | See [`docs/CAPABILITIES.md`](CAPABILITIES.md) §1 or [`docs/AGENTS.md`](AGENTS.md) "Which feature type to pick" |
| What face roles are available? | See the role_hint table above |
| What feature flags exist? | See the flag table above, or inspect `FLAG_REGISTRY` in `flags.py` |
| What MCP tools are available? | See [`docs/CAPABILITIES.md`](CAPABILITIES.md) §0 and §5, or [`docs/mcp_server_design.md`](mcp_server_design.md) §6 |
| What mate types are supported? | See [`assembly/schema.py::MATE_TYPES`](../src/ai_sw_bridge/assembly/schema.py) — 13 types |

## Source tracing

Every name in this document is traced to the following source locations:

| Claim | Source |
|---|---|
| 15 CLI entry points | [`pyproject.toml`](../pyproject.toml) `[project.scripts]` |
| 6 role_hint values + oblique | [`brep/interrogator.py::_role_hint`](../src/ai_sw_bridge/brep/interrogator.py) |
| 4 face-bound feature types | [`spec/validator.py::FACE_BOUND_TYPES`](../src/ai_sw_bridge/spec/validator.py) |
| B-rep manifest schema v1 | [`brep/manifest.py::Manifest`](../src/ai_sw_bridge/brep/manifest.py) |
| Assembly manifest schema v2 | [`assembly/storage.py`](../src/ai_sw_bridge/assembly/storage.py) |
| 6 feature flags | [`flags.py::FLAG_REGISTRY`](../src/ai_sw_bridge/flags.py) |
| 13 mate types | [`assembly/schema.py::MATE_TYPES`](../src/ai_sw_bridge/assembly/schema.py) |
| face_role validation | [`spec/validator.py::_check_face_role_shapes`](../src/ai_sw_bridge/spec/validator.py) |
| face_role resolution | [`brep/resolver.py::resolve_face_role`](../src/ai_sw_bridge/brep/resolver.py) |
| Feature-add supported types | [`mutate.py::_SUPPORTED_FEATURE_TYPES`](../src/ai_sw_bridge/mutate.py) |
