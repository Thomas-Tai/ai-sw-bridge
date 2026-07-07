# Top-down CAD Strategy

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

How the CAD model is structured — decided before any backend-specific spec is
written.

## Global coordinate system

*(Where the machine origin sits; which way X/Y/Z point. Must match
`engineering_specs.md`.)*

## Master origin and datum planes

*(The named planes everything references — base plane, belt-top plane,
centerline plane.)*

## Skeleton/layout sketch strategy

*(Which layout sketches drive which modules. NOTE: skeleton parts and
in-context references are **manual-in-GUI** — the bridge cannot create them;
mark them as such.)*

## Global variables and parameter names

*(Bound through per-part `*_locals.txt` equation files. Module-owned parameters
carry the module prefix (e.g. `S1B_BELT_T`); machine-global parameters (e.g.
`CONVEYOR_WIDTH`) may omit it. List every parameter, its owner, and its status.)*

## Executable-by-bridge vs manual-in-GUI split

*(Executable today: per-part `*_locals.txt` parameters, part builds, component
placement, and mates. Manual-in-GUI: skeleton parts, in-context references.
Every manual step must be listed here so nobody waits on the bridge for it.)*

## Assembly structure

*(The assembly tree: which parts under which sub-assemblies, and why.)*

## Naming conventions

*(Features, sketches, parts, mates — e.g. `SK_<purpose>`, `EX_<purpose>`,
`<MODULE>_<part>.SLDPRT`, `MATE_<a>_<b>`.)*

## Rebuild and variant strategy

*(What changes when a parameter changes; which variants are expected and how
they materialize — e.g. multi-file variants via `ai-sw-configurations`.)*
