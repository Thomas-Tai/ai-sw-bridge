# sketch_primitives

A gallery with one feature entry per sketch primitive — the seven individual
sketch entities, each building literal-size geometry on the Front plane:

- **`sketch_line`** (`SK_Line_Diagonal`)
- **`sketch_arc`** (`SK_Arc_Quarter`)
- **`sketch_spline`** (`SK_Spline_Curve`)
- **`sketch_slot`** (`SK_Slot_Horizontal`)
- **`sketch_polygon`** (`SK_Polygon_Hex`)
- **`sketch_ellipse`** (`SK_Ellipse_Oval`)
- **`sketch_text`** (`SK_Text_Label`)

Each is a standalone sketch (no extrude) — the example is the reference for the
sketch-entity vocabulary. See [../../docs/spec_reference.md](../../docs/spec_reference.md).

Run it:

```bash
ai-sw-build examples/sketch_primitives/spec.json --no-dim
```
