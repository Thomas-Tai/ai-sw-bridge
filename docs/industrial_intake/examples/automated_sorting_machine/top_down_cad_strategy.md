# Top-down CAD Strategy — Automated Sorting Machine

## Global coordinate system

Origin at frame center, front face, bottom
(`machine_origin_at_frame_center_front_bottom`); X = belt travel, Y = across
belt, Z = up. Matches `engineering_specs.md`.

## Master origin and datum planes

- `PLN_BASE` — bench contact plane (Z = 0).
- `PLN_BELT_TOP` — Z = `INF_FRAME_H` (150 mm): belt working surface.
- `PLN_BELT_CL` — Y = 0 centerline of the belt.

## Skeleton/layout sketch strategy

One machine-layout sketch positioning the six module envelopes is desirable —
**manual-in-GUI** (skeleton parts and in-context references are not executable
by the bridge). For the first slice it is skipped: module positions come from
explicit placement coordinates in the assembly spec instead.

## Global variables and parameter names

| Parameter | Value | Scope | Status |
|---|---|---|---|
| `CONVEYOR_WIDTH` | 120 mm | machine-global | assumed |
| `INF_BELT_L` | 600 mm | module (infeed) | assumed |
| `INF_ROLLER_D` | 40 mm | module (infeed) | assumed |
| `INF_FRAME_H` | 150 mm | module (infeed) | assumed |

Module-owned parameters carry the `INF_` prefix; `CONVEYOR_WIDTH` is
machine-global. Each custom part binds its values through its own
`<part>_locals.txt` equation file; `cad_ready_summary.json` is the source of
truth when files disagree. (`INF_BELT_SPEED` is derived and non-geometric —
it lives in the summary and calculations, not in any `*_locals.txt`.)

## Executable-by-bridge vs manual-in-GUI split

| Work | Path |
|---|---|
| Part builds from specs (`*_locals.txt` parametric) | executable (`ai-sw-build`) |
| Component placement + mates | executable (`ai-sw-assembly`) |
| Drawings, custom properties | executable (`ai-sw-drawing`, `ai-sw-properties`) |
| Skeleton part / in-context references | **manual-in-GUI** |
| Belt as a flexible body | **not modeled in v1** (represented by roller pitch + clearance) |

## Assembly structure

`sorting_machine.SLDASM` → `infeed_conveyor.SLDASM` (side plates ×2, slider
bed, rollers ×2, motor, motor bracket) + later `frame`, `vision_module`,
`diverter_unit`. First slice builds only `infeed_conveyor.SLDASM`.

## Naming conventions

Sketches `SK_<purpose>`, extrudes `EX_<purpose>` (repo convention); parts
`INF_<name>.SLDPRT`; mates `MATE_<partA>_<partB>_<n>`.

## Rebuild and variant strategy

Width variants (e.g. 160 mm belt) materialize as separate part files via
`ai-sw-configurations` variants over `CONVEYOR_WIDTH`; no in-file
configurations (platform constraint).
