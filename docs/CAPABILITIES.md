# Capability Matrix

What the bridge can build, observe, and export today. This is the affirmative
counterpart to [`DEFERRED.md`](DEFERRED.md) (what it cannot do, and why) — together
they bound the supported surface.

Reflects **v1.7.0**, derived from the live repository (the feature-handler registry,
the `ai-sw-*` entry points, the MCP tool contract, and `export/formats.py`). The
authoring model is the same everywhere: **declarative JSON in, propose → approve →
execute, no arbitrary code execution, driven out-of-process.** Mutations are
approval-gated and CLI-only; read-only observation is available over both the CLI and
the MCP server.

---

## Surfaces

- **21 command-line tools** (`ai-sw-build`, `ai-sw-mutate`, `ai-sw-assembly`,
  `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`, `ai-sw-sketch-edit`,
  `ai-sw-sketch-relations`, `ai-sw-observe`, `ai-sw-import`, `ai-sw-export-dxf-flat`,
  `ai-sw-motion`, `ai-sw-solver`, `ai-sw-urdf`, `ai-sw-checkpoint`, `ai-sw-history`,
  `ai-sw-memory`, `ai-sw-apidoc`, `ai-sw-codegen`, `ai-sw-probe`) — see
  [`PUBLIC_API.md`](PUBLIC_API.md) for stability tiers.
- **One MCP server** (`ai-sw-mcp`) exposing 37 tools to MCP-capable AI clients.

---

## Build — part features

The core builder produces a part from a declarative spec: **extrude, cut, and
revolve** over seven sketch primitives (with construction geometry and text). On top
of that, **36 additional feature kinds** can be added to a model. Each is verified by
its geometric *effect* (a volume / face / area / length change), never by a bare
"no error".

| Group | Features |
|---|---|
| Dress-up | constant-radius fillet, face fillet, variable-radius fillet, chamfer, shell, draft |
| Patterns | linear, circular, mirror, sketch-driven |
| Reference geometry | plane, axis, point, coordinate system, bounding box, center-of-mass point, mate reference |
| Curves | composite, helix, spiral, projected, through-XYZ-points |
| Surfaces | planar, offset, knit |
| Sheet metal | base flange, hem, sketched bend |
| Sweeps & shapes | sweep, sweep cut, dome, hole wizard |
| Bodies & boolean | delete body, intersect, scale |
| Weldment | structural weldment |

The runtime source of truth is `client.features.list_kinds()`.

---

## Observe — read-only perception (CLI + MCP)

| Capability | What it returns |
|---|---|
| Mass properties / inertia | Inertia tensor, center of mass, principal moments |
| Bounding box | Axis-aligned part box; combined assembly box |
| Measure | Distance/angle/area over the current selection or a durable entity pair |
| Interference | Assembly component clashes; body-to-body clashes within a multibody part |
| Clearance | Minimum distance between components or named faces |
| Draft / undercut (DFM) | Faces classified against a pull direction |
| Minimum wall thickness (DFM) | Thinnest-wall probe over a solid |
| Section properties | Properties of a selected planar face |
| Import diagnostics | Body breakdown and geometry-health faults of imported parts |
| MBD / PMI | Read existing datums, dimensions, and geometric tolerances |
| Feature & mate health | Per-feature and per-mate status; equations; custom properties |
| Selection | The current selection as durable references |
| Add-ins | Currently-loaded SOLIDWORKS add-ins |
| Screenshot | Capture the active viewport to PNG |

---

## Assembly — `ai-sw-assembly`

| Capability | Detail |
|---|---|
| Component placement | Place prebuilt parts or parts built from an inline spec; positioned and rotated (roll/pitch/yaw) |
| Mates (13 types) | coincident, distance, concentric, parallel, perpendicular, tangent, angle, width, gear, rack-and-pinion, cam-follower, slot, hinge |
| Limit mates | Distance and angle limit modifiers |
| Component arrays | Linear and circular, via placement expansion |
| Mirror components | Mirror a component across a plane |
| Exploded views | Build an exploded view with per-component explode steps |
| Motion audit | Drive a mate through its travel and check for collisions / clearance in motion |
| Interactive edit | Add/remove components and mates, then re-commit |
| Persistence | Durable assembly manifest (lossless round-trip of the spec) |

---

## Drawing — `ai-sw-drawing`

| Capability | Detail |
|---|---|
| Views | Orthographic, isometric, section, and detail views |
| Multi-sheet | Multiple sheets, with per-sheet view placement |
| Dimensions | Insert model dimensions; apply symmetric / bilateral / limit tolerances |
| BOM | Insert a bill-of-materials table (assemblies) |
| Title block | Populate title-block fields from a closed vocabulary |

---

## Export

All formats below are seat-confirmed.

| Format | Notes |
|---|---|
| STEP (AP203 / AP214) | Solid model exchange |
| IGES | Use the `.igs` extension |
| Parasolid | Native kernel format |
| STL | ASCII or binary |
| 3MF | Additive-manufacturing format |
| PDF | Drawing → PDF, single or multi-sheet |
| DXF / DWG | 2D vector from a drawing |
| Flat-pattern DXF | Sheet-metal developed outline, with optional bend lines (`ai-sw-export-dxf-flat`) |
| URDF | Assembly → ROS robot model with per-link meshes (`ai-sw-urdf`) |

---

## Sketch authoring

| Capability | Detail |
|---|---|
| Geometric relations (`ai-sw-sketch-relations`) | horizontal, vertical, parallel, perpendicular, equal, concentric |
| Sketch editing (`ai-sw-sketch-edit`) | Convert-entities, offset, sketch pattern |

---

## Configurations — `ai-sw-configurations`

A family of parts as **multiple part files**: a `variants` spec builds one distinct
`.SLDPRT` per variant, each volume-verified. (In-file native configurations are a
platform constraint — see [`DEFERRED.md`](DEFERRED.md).)

---

## Reliability & infrastructure

| Capability | Detail |
|---|---|
| Approval workflow | Every mutation is propose → dry-run → commit, human-gated |
| Self-healing batch | Multi-feature batches survive a SOLIDWORKS crash (detect → respawn → replay) |
| Checkpoints & history | Per-feature snapshots with optional at-rest encryption; query and roll back |
| Durable selection | Edge/face references that survive rebuilds |
| Foreign import | STEP / IGES → `.sldprt` with import diagnostics |
| API documentation (`ai-sw-apidoc`) | Searchable SOLIDWORKS API reference |
| Design memory (`ai-sw-memory`) | On-device semantic search over your own past designs |

---

*For the boundaries of each domain — what is unsupported and why — see
[`DEFERRED.md`](DEFERRED.md).*
