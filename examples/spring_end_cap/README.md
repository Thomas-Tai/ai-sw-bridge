# spring_end_cap

A real S1b part — `SM-HW-S1b-006b_SpringEndCap` — combining blind and
through-all cuts with a multi-circle face sketch. A small PETG slab that hosts a
compression-spring pocket and mounting holes.

- **`Extrude_Body`** — the slab body (`boss_extrude_blind` from a Front-plane
  rectangle).
- **`Cut_SpringPocket`** — a Ø6 × 4 mm compression-spring pocket
  (`cut_extrude_blind` from a circle on the `+x` face).
- **`Cut_MountHoles`** — the mounting holes (`cut_extrude_through_all` from a
  `sketch_circles_on_face` multi-circle sketch on the `-z` face).

Dimensions come from `SW_Design_Guide.md` §13.6b (v1.7) via `{rhs}` bindings, so
this part references a `locals.txt` — see the locals note in
[../README.md](../README.md) before running.

Run it:

```bash
ai-sw-build examples/spring_end_cap/spec.json --no-dim
```
