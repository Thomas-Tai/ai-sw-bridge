# Examples

Worked examples for ai-sw-bridge. Each subfolder is a self-contained workflow you can run end-to-end.

## v0.2 examples (JSON spec → direct-COM build)

Run with `ai-sw-build <path>/spec.json --no-dim`. Recommended order:

| Example | Features | What it demonstrates |
|---|---|---|
| [`filleted_box/`](filleted_box/) | 3 | Simplest example: box + fillet. Start here. |
| [`minimal_cylinder_v2/`](minimal_cylinder_v2/) | 2 | Parametric cylinder with `{rhs}` bindings |
| [`motor_mount_plate/`](motor_mount_plate/) | 10 | Full MMP: 6 primitives, face sketches on both sides, multi-circle hole patterns |
| [`tension_bracket/`](tension_bracket/) | 8 | Stacked extrudes, face-sketch-origin offset workaround |

## Path C example (recorded-macro parameterization)

| Example | What it demonstrates |
|---|---|
| [`minimal_cylinder/`](minimal_cylinder/) | Record a cylinder in SW UI, parameterize against `locals.txt`, replay in VBE. Validates full Path C workflow. |

## Running an example

**v0.2 examples** — open SOLIDWORKS, then:

```powershell
ai-sw-build examples/filleted_box/spec.json --no-dim
```

**Path C example** — follow the step-by-step instructions in that folder's `README.md`.

## Notes

- Examples with `{rhs}` bindings reference a `locals.txt` file. Some use a machine-specific absolute path — update the `locals` field in `spec.json` to point to your copy, or replace `{rhs}` expressions with literal mm values.
- Path C expects you to record your own `.swp` macro (recordings are machine- and version-specific — see [docs/known_gotchas.md](../docs/known_gotchas.md)).
