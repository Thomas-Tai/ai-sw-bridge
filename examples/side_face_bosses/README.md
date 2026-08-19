# side_face_bosses

Demonstrates boss extrudes on all four **side faces** of a block (`+x`, `-x`,
`+y`, `-y`) — the check that sketch-origin handling works on the non-`±z` faces.

- **`EX_Block`** — a 30×30×20 mm block (`boss_extrude_blind`) sketched on the
  Front plane.
- **`Boss_PlusY` / `Boss_MinusY` / `Boss_PlusX` / `Boss_MinusX`** — one Ø6 × 5 mm
  boss centred on each side face, each from a `sketch_circle_on_face` targeting
  `+y` / `-y` / `+x` / `-x`.

The point is the face-sketch coordinate mapping: a circle placed at a side
face's centre must land centred no matter which face it is on. See
[../../docs/coordinate_conventions.md](../../docs/coordinate_conventions.md).

Run it:

```bash
ai-sw-build examples/side_face_bosses/spec.json --no-dim
```
