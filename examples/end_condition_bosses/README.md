# end_condition_bosses

Demonstrates the three boss end-condition primitives added in W67 P5 (Tier 1):

- **`boss_extrude_midplane`** (`MidBoss`, Ø10) — adds `depth` of material
  centred on the sketch plane (`depth/2` each side; `T1 = swEndCondMidPlane = 6`).
- **`boss_extrude_two_direction`** (`TwoDirBoss`, Ø10) — adds material in both
  directions from the sketch plane: `depth` into +normal, `depth2` into -normal
  (`Sd = False`, independent `T2`/`D2`).
- **`boss_extrude_through_all`** (`ThruBoss`, Ø8) — adds material until it
  terminates against existing geometry (`T1 = swEndCondThroughAll = 1`, no
  `depth`). Requires a prior solid body; here the base plate satisfies that and
  `flip` runs the boss -normal through it.

Base body is a 60×40×15 mm plate (`boss_extrude_blind`); all three bosses are
sketched on its +Z face.

The arg-shapes are produced by the same `FeatureExtrusion2` arg-builder the
runtime uses (`_call_feature_extrusion`, extended with `end_cond2`/`depth2_m`).
These are parametric end-condition variants of the proven blind boss; the
`boss_extrude_through_all` `prior-body` requirement is also enforced by the
`_check_through_all_boss_needs_body` lint. Structural example for schema/doc
coverage — seat-validation of these specific end conditions is a separate
authorized fire.
