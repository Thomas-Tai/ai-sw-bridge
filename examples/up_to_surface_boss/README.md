# up_to_surface_boss

Demonstrates `boss_extrude_up_to_surface` (W67 P5 Tier 2) — a boss whose
terminus is a **durable reference surface**, not a fixed depth.

- **`EX_Base`** — 100×100×10 mm plate (`boss_extrude_blind`).
- **`EX_Wall`** — a tall 100×20×60 mm wall offset to +Y; its top (`+z`) face
  sits at z = 60 mm and serves as the up-to target.
- **`PostBoss`** — a Ø20 boss sketched on the plate's `+z` face (z = 10 mm) that
  extrudes **up to** `EX_Wall`'s `+z` face via
  `target_ref: {of_feature: "EX_Wall", face: "+z"}`. The boss runs z = 10…60 mm
  with no `depth` field — the surface defines the extent.

## The OOP end-condition trap (seat-proven)

The handler hardcodes `T1 = swEndCondUpToSurface = 4`. This is **not** an
oversight: the matrix sweep in `spikes/v0_2x/spike_extrude_up_to_surface.py`
(SW 2024 SP1, rev 32.1.0) proved that the "modern" `swEndCondUpToSelection = 10`
— the constant SOLIDWORKS' own API docs steer you toward — **silently no-ops
out-of-process** (the feature never materialises), while the formally-deprecated
`UpToSurface = 4` is the only functional OOP path. The sweep also proved the
reference selection *mark* is irrelevant (0/1/2 all passed); what gates is the
end-condition constant plus the reference being on the selection stack.

Do not "modernise" the constant to `10` — it will break the handler. See
`docs/DEFERRED.md` and the `reference_extrude_up_to_surface_seat` memory.
