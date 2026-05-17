# chamfered_box

A 20×20×10 mm box with 1 mm equal-distance chamfers applied to its four top edges.

## Run

```powershell
ai-sw-build examples\chamfered_box\spec.json
```

## What it builds

| # | Feature | Primitive | Notes |
|---|---|---|---|
| 1 | `SK_Box` | `sketch_rectangle_on_plane` | 20×20 mm on Front Plane |
| 2 | `EX_Box` | `boss_extrude_blind` | 10 mm tall |
| 3 | `Ch_TopEdges` | `chamfer_edge` | mode `equal_distance`, 1 mm, 4 edges |

## Chamfer modes

`chamfer_edge` supports two modes selected via the `mode` field:

- **`equal_distance`** — symmetric. One `distance` value applied to both adjacent faces of each edge. Used here.
- **`distance_angle`** — asymmetric. One `distance` plus an `angle` in degrees (not radians; SW's `InsertFeatureChamfer` Angle arg is degrees).

Example `distance_angle` variant:

```json
{
  "type": "chamfer_edge",
  "name": "Ch_LeadIn",
  "mode": "distance_angle",
  "distance": 2.0,
  "angle": 30.0,
  "edges": [{"x": 0, "y": 10, "z": 10}]
}
```

## Things to try

- Swap `mode` to `distance_angle` and add an `angle` field. The chamfer becomes asymmetric.
- Add `"flip": true` to flip which face of the edge the asymmetry favours (only meaningful for `distance_angle`).
- Reduce `distance` toward zero to verify SW catches the degenerate case (you should see a runtime error from `InsertFeatureChamfer`, not a silent no-op).
- Try chamfering bottom-face edges by changing `z` from 10.0 to 0.0.
