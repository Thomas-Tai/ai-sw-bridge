# Example: minimal cylinder (v0.2)

The smallest v0.2 (JSON-spec → direct-COM) example. Two features, two parametric bindings.

Builds a cylinder whose diameter and length are driven by variables in a `locals.txt` file.

## Run it

Open SOLIDWORKS, then:

```powershell
ai-sw-build examples/minimal_cylinder_v2/spec.json --no-dim
```

This reads `PART_DIAMETER` and `PART_LENGTH` from `examples/minimal_cylinder/locals.txt`, resolves them to 25 mm and 80 mm, and builds a Ø25 × 80 mm cylinder.

## What it builds (2 features)

| # | Feature | Type | What it does |
|---|---|---|---|
| 1 | `SK_Body` | `sketch_circle_on_plane` | Circle on Front Plane, diameter bound to `PART_DIAMETER` |
| 2 | `Extrude_Body` | `boss_extrude_blind` | Extrude the circle, depth bound to `PART_LENGTH` |

## How parametric bindings work

Both features use `{rhs}` expressions:

```json
"diameter": {"rhs": "\"PART_DIAMETER\""}
```

In `--no-dim` mode, the builder reads `PART_DIAMETER = 25.0` from `locals.txt` and substitutes the literal value. In parametric mode (no flag), it adds an equation link `D1@SK_Body = "PART_DIAMETER"` so future edits to `locals.txt` propagate via Ctrl+B.

## Files

| File | Purpose |
|---|---|
| `spec.json` | v0.2 spec referencing `examples/minimal_cylinder/locals.txt` |

The `locals.txt` lives in [`examples/minimal_cylinder/locals.txt`](../minimal_cylinder/locals.txt) and declares `PART_DIAMETER = 25.0` and `PART_LENGTH = 80.0`.

## Things to try

- Edit `locals.txt`: change `PART_DIAMETER` to `40.0`, re-run — cylinder grows to Ø40
- Remove the `locals` field from `spec.json` and replace `{rhs}` with literal numbers — no `locals.txt` needed
