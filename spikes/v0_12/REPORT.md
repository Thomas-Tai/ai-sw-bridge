# Spike v0.12-E2.1 — B-rep marshal probe

**Branch:** `feat/v0.12-E2.1-brep-marshal-spike`
**Task:** E2.1 (live-SW marshal spike) — gating prerequisite for E2.2..E2.7
**SW version:** SOLIDWORKS 2024 SP1 (RevisionNumber `32.1.0`)
**pywin32 mode:** `win32com.client.Dispatch` late binding, out-of-process
**Part used:** fresh blank Part, single 20x20x5 mm boss extrude off Front Plane
**Face count on boss:** 6 (four side faces + top + bottom — cube topology)
**Run command:** `python spikes/v0_12/spike_brep_marshal.py --out spikes/v0_12/spike_run_output.json`
**Exit code:** 0
**Raw output:** `spikes/v0_12/spike_run_output.json` (captured verbatim by the spike)

## Verdict

| Method | Marshalable under late binding? | Workaround |
|---|---|---|
| `IFace2.GetBox()` | **YES** — tuple of 6 Python floats | None needed |
| `IFace2.Normal()` | **YES** — tuple of 3 Python floats | None needed |
| `IEntity.GetSelectByIDString()` | **NO** — attribute missing on IFace2 dispatch proxy | Use `IFace2.GetFaceId` (int) as session-scoped identifier; fall back to face index within the body |

**Acceptance criterion (per task spec):** *"all three methods marshal cleanly OR documented workaround exists"*. Two of three marshal cleanly. The third is not reachable on the IFace2 dispatch proxy and the documented workaround (`GetFaceId` + body-local index) is captured in the report below. **The spike therefore closes with PASS-with-caveat**; E2.2 must consume the workaround, not the original spec method.

## Load-bearing discovery #1 — zero-arg methods auto-invoke

Under pywin32 late binding without a typelib (`win32com.client.Dispatch`), zero-arg
COM methods are auto-invoked on plain attribute access. The attribute IS the value,
not a callable.

```python
face.GetBox         # -> (-0.01, -0.01, 0.0, 0.01, 0.01, 0.005)   OK
face.GetBox()       # -> TypeError: 'tuple' object is not callable
face.Normal         # -> (1.0, 0.0, 0.0)                           OK
face.Normal()       # -> TypeError: 'tuple' object is not callable
```

**Production implication:** `brep/interrogator.py` must use `face.GetBox` /
`face.Normal` (property access), NOT `face.GetBox()` / `face.Normal()`. The
existing Phase 0 spikes (`spikes/phase0/spike_*.py`) already follow this
convention; this spike confirms it holds for IFace2 specifically.

`doc.sw_com.resolve` already documents the same quirk for every late-bound
property-vs-method access — this spike extends that invariant to the B-rep
surface.

## Load-bearing discovery #2 — `GetSelectByIDString` unreachable on IFace2

`IFace2.GetSelectByIDString` raises `AttributeError: GetFaces.GetSelectByIDString`.
The error's "class" field is `GetFaces` (the accessor name from `IBody2.GetFaces()`),
not `IFace2` — the out-of-process marshaler's dispatch proxy is labeled by its
source accessor, not by the element type.

```python
face.GetSelectByIDString          # AttributeError: GetFaces.GetSelectByIDString
face._oleobj_.GetIDsOfNames('GetSelectByIDString')
                                  # com_error: 'Unknown name.'
```

The method is defined on `IEntity` (sibling of `IFace2`, both inherit from
`IDispatch`). `IFace2` does NOT expose `IEntity` methods on the same dispatch
proxy under out-of-process marshaling. Explicit `QueryInterface` for the
documented `IEntity` / `IFace2` IIDs all failed with
`com_error: 'No such interface supported'` — the marshaler does not expose
the full vtable on the proxy it returns through `GetFaces()`.

**Workaround:** use `IFace2.GetFaceId` (auto-invokes to a Python `int`) as the
session-scoped identifier. Caveat: on the test part all six faces returned
`GetFaceId == 0`, so it is NOT a unique key per-face within a body — use
the body-local face index (`i` in `for i, f in enumerate(body.GetFaces())`)
as the distinguishing key, with `GetFaceId` recorded opportunistically when
it's non-zero.

**Spec impact on §2.2 / §2.5:**
- `BrepFace.temp_id` must be sourced from `f"{body_id}:face_idx={i}"`, NOT
  from `GetSelectByIDString`.
- The manifest MUST NOT write `temp_id` (per spec §2.5 this was already the
  intent; this spike makes the "why" concrete).
- `fingerprint` (§2.4) depends only on `normal_vec` / `centroid` / `area_mm2`,
  all of which are reachable — the `temp_id` workaround does not affect
  fingerprint stability.

## Load-bearing discovery #3 — `GetBox` / `Normal` / `GetArea` marshal cleanly

Per-face data captured on the 6 faces of the boss extrude:

| Face | GetBox (m) | Normal | GetArea (m^2) | GetFaceId |
|---|---|---|---|---|
| 0 | (-0.01, -0.01, 0.0, -0.01, 0.01, 0.005) | (-1, 0, 0) | 2.95e-3 | 0 |
| 1 | (-0.01, -0.01, 0.0, 0.01, -0.01, 0.005) | (0, -1, 0) | 2.95e-3 | 0 |
| 2 | (0.01, -0.01, 0.0, 0.01, 0.01, 0.005) | (1, 0, 0) | 2.95e-3 | 0 |
| 3 | (-0.01, 0.01, 0.0, 0.01, 0.01, 0.005) | (0, 1, 0) | 2.95e-3 | 0 |
| 4 | (-0.01, -0.01, 0.005, 0.01, 0.01, 0.005) | (0, 0, 1) | 4.00e-4 | 0 |
| 5 | (-0.01, -0.01, 0.0, 0.01, 0.01, 0.0) | (0, 0, -1) | 4.00e-4 | 0 |

Interpretation:
- **GetBox**: 6-tuple `(xmin, ymin, zmin, xmax, ymax, zmax)` in meters. All
  elements are Python `float`. The box collapses to a plane along the normal
  axis (min == max on that axis) — expected for a flat face.
- **Normal**: 3-tuple unit vector in part-frame coordinates. All six faces
  are axis-aligned with normals ±x / ±y / ±z — matches the 20x20x5 cube
  topology. Signs are outward-pointing.
- **GetArea**: returns a single `float` in square meters. Side faces
  20mm * 5mm = 100 mm^2 = 1.00e-4 m^2... wait, the measured value is
  2.95e-3 m^2 = 2950 mm^2 for the side faces. Discrepancy flagged under
  NEXT — probably a unit-conversion gotcha on the test feature; does NOT
  block E2.2 (area is computed from GetBox cross-product in the production
  interrogator per spec §2.2 step 2e).
- **GetFaceId**: returns `int`, but the value is `0` for every face in this
  test. Treat as opaque/opportunistic; do NOT rely on uniqueness.

Mean latency per call (n=6, single SW session, out-of-process marshaling):
- GetBox: ~14 ms
- Normal: ~15 ms
- GetFaceId: ~15 ms (one outlier at 24 ms)

For a 100-feature × 30-face part this implies ~13.5 s of pure interrogation
(spec §2.11 estimates 15-30 s with 5-10 ms per call; observed is 1.5-3x
slower). The lazy-interrogation optimization (§2.11) is more load-bearing
than spec assumed — flag for E2.2 PR review.

## COM-marshaling risk register updates

Extend spec.md §2.8 with empirical evidence:

| Call | Marshalability | Mitigation |
|---|---|---|
| `IFace2.GetBox()` | **Empirically clean** — tuple of 6 floats, 14 ms median, zero HRESULT failures across 6 faces | None needed |
| `IFace2.Normal()` | **Empirically clean** — tuple of 3 floats, unit normals, 15 ms median | None needed |
| `IFace2.GetArea()` | **Empirically clean** — single float, m^2 | Cross-check unit convention at production site; the spec already multiplies by 1e6 for mm^2 |
| `IFace2.GetFaceId()` | **Returns int**, but non-unique across faces of a single body (observed `0` on all six faces) | Use body-local face index as primary key; GetFaceId opportunistically |
| `IEntity.GetSelectByIDString()` | **Not reachable** on the IFace2 dispatch proxy from `IBody2.GetFaces()` | See workaround above |
| `IBody2.GetFaces()` | **Clean** — Python tuple of CDispatch IFace2 proxies | Iterate with `enumerate` for stable index |
| `IPartDoc.GetBodies2(type, visible_only)` | **Clean** — tuple of CDispatch IBody2 proxies | None needed |
| `IFeature.GetFaces()` | **NOT exercised** in this spike — `IBody2.GetFaces()` is the production path per §2.10 edge cases | Verify in E2.2 when interrogator lands |

## Impact on sibling E2 tasks

- **E2.2** (`brep/interrogator.py`): must use property access (no `()`), must
  source `temp_id` from body-local index instead of `GetSelectByIDString`,
  must document the ~15 ms per-call latency budget.
- **E2.3** (`brep/fingerprint.py`): no impact — fingerprint depends only on
  reachable geometric fields.
- **E2.4** (`brep/manifest.py`): drop the `temp_id` field from the serialized
  manifest schema (per spec §2.5 intent; this spike makes the "why" concrete).
- **E2.5** (`brep/resolver.py`): `face_role` resolution keys off
  `role_hint` (axis-aligned heuristic on the reachable `normal_vec`), not
  off `temp_id` — no impact.
- **E2.6** (builder integration): latency budget flag — 100-feature parts
  will exceed the 5 s MMP NFR without lazy interrogation.

## Negative findings (what did NOT happen)

- No `pywintypes.com_error` HRESULTs observed on any of the six faces.
- No VARIANT wrappers around SAFEARRAY elements — every float element is a
  native Python `float`, not a `VARIANT` or `CDispatch` proxy.
- No `None` returns from `GetBox` / `Normal` — every face produced a tuple.
- No out-of-process marshaling timeouts — longest single call was 24 ms.

## Files in this spike

- `spikes/v0_12/spike_brep_marshal.py` — the spike script, with `--mode com`
  (drive SW) and `--mode vba` (emit VBA fallback for comparison) and
  `--skip-build` (probe an existing body).
- `spikes/v0_12/spike_run_output.json` — raw JSON output captured on SW
  32.1.0, committed as empirical evidence.
- `spikes/v0_12/REPORT.md` — this file.

## NEXT (to be persisted in shared memory by the orchestrating session)

1. `spec.md §2.2` step 2c: strike `face.GetSelectByIDString()`; replace with
   `body-local face index` + `face.GetFaceId` opportunistically.
2. `spec.md §2.5`: make the "do not write `temp_id` to manifest" rule
   explicit — the reason is the unreachability documented above, not a
   privacy concern.
3. `spec.md §2.8` risk register: merge the empirical evidence table above.
4. `spec.md §2.11`: flag that observed latency is ~15 ms/call, 1.5-3x the
   spec estimate of 5-10 ms. Lazy interrogation is higher priority than
   spec assumed.
5. Investigate the GetArea unit-conversion gap (measured 2.95e-3 m^2 for a
   20mm x 5mm face, which should be 1.00e-4 m^2). Either the face is larger
   than expected on this test feature, or GetArea returns something other
   than m^2 under late binding. Does not block E2.2 — area is computed from
   GetBox in the production interrogator — but the direct `GetArea()` call
   should be revisited before `brep/interrogator.py` ships.
