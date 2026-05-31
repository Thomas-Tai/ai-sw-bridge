# end_condition_cuts

Demonstrates the two cut end-condition primitives added in D3:

- **`cut_extrude_midplane`** (`MidCut`, Ø8) — removes `depth` of material
  centred on the sketch plane (`depth/2` each side).
- **`cut_extrude_two_direction`** (`TwoDirCut`, Ø6) — removes material in both
  directions from the sketch plane: `depth` into +normal, `depth2` into -normal.

Base body is a 40×30×20 mm block (`boss_extrude_blind`); both cuts are sketched
on its +Z face.

Seat-validated on SW 2024 SP1 (rev 32.1.0) by
`spikes/v0_16/spike_cut_endcond.py` — both cuts materialise and increment the
feature count. The mid-plane (`T1 = swEndCondMidPlane = 6`) and two-direction
(`Sd = False`, independent `T2`/`D2`) arg-shapes are produced by the same
`FeatureCut4` version-dispatched arg-builder the runtime uses.

> Note: the SW 2025 `FeatureCut4` arity variant remains a documented stub
> (`_cut4_args_2025`) pending a SW 2025 seat — these cuts are proven on 2024.
