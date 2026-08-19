# sketch_3d_primitives

A gallery of the `sketch_3d_sketch` primitive (W53): a single non-planar 3D
polyline whose points span all three axes.

- **`SK3D_NonPlanarPath`** — a `sketch_3d_sketch` with a 4-point path not
  confined to any one plane.

This is a substrate primitive; the example exists for schema/doc coverage of the
3D-sketch entity itself (see [../../docs/spec_reference.md](../../docs/spec_reference.md)
and [../../docs/known_limitations.md](../../docs/known_limitations.md) for what a
3D sketch can and cannot drive downstream).

Run it:

```bash
ai-sw-build examples/sketch_3d_primitives/spec.json --no-dim
```
