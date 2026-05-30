# Handoff: build F1 — the `feature_add` proposal kind in `mutate.py`

> Self-contained task brief for a coding agent (Sonnet recommended). Hand this
> over verbatim. Everything COM-hard is already solved and shipped on
> `par/integration`; F1 is wrapping a **proven** sequence in the existing
> Propose→Approve→Execute (PAE) machinery.

You are working in the `ai-sw-bridge` repo (declarative-JSON → SOLIDWORKS
automation middleware, out-of-process Python + pywin32). Branch:
`par/integration`. A durable-selection "feature add on an edge" loop has just
been **proven end-to-end on a live seat**; your job is to productize it into the
existing PAE machinery in `mutate.py`. **Do not re-derive the COM work.**

## Read these first (in order)
1. `spikes/v0_15/spike_durable_feature_add.py` — **the validated reference.** Its
   `run()` performs the exact COM sequence you must port into the production
   handler. Treat it as the source of truth for the call order.
2. `src/ai_sw_bridge/mutate.py` — the PAE module you are extending. Study
   `sw_propose_local_change` / `sw_dry_run` / `sw_commit` / `ProposalState` /
   `_load_proposal` / `_save_proposal` / `ProposalStore`. Match their style,
   return-dict shape, and on-disk record conventions exactly.
3. `src/ai_sw_bridge/com/earlybind.py` (`typed`, `typed_qi`) and
   `src/ai_sw_bridge/selection/__init__.py` (`DurableEdgeRef`, `resolve_edge_ref`,
   `select_entity`) — the shipped helpers you will call.
4. `docs/central_idea/keystone_status.md` §4.1 and §5 slice 4 (gitignored scratch
   — read it locally) for the full rationale and gotchas.

## What to build
Add a **second proposal kind**, `feature_add`, alongside the existing
variable-edit proposals. It does NOT bolt onto the `*_locals.txt` variable path —
it is a parallel kind sharing the propose→dry_run→commit lifecycle. v1 supports
exactly one feature type: **constant-radius fillet on a durable edge.**

### Proposal record (JSON on disk, same dir as existing proposals)
Add a `"kind"` field to disambiguate (`"local_change"` for the existing records —
default it when absent for back-compat; `"feature_add"` for the new ones). A
`feature_add` record carries:

```json
{
  "kind": "feature_add",
  "proposal_id": "<12-hex>",
  "created_at": 0.0,
  "doc_path": "<absolute .sldprt path>",
  "feature": {"type": "fillet_constant_radius", "radius_mm": 2.0},
  "target": { "...DurableEdgeRef.to_dict()..." },
  "state": "proposed",
  "dry_run_result": null,
  "committed_at": null
}
```

Reconstruct the edge ref with `DurableEdgeRef.from_dict(record["target"])`.

### The three functions (new; mirror the existing trio's signatures/returns)
- `sw_propose_feature_add(doc_path: str, feature: dict, target: dict) -> dict`
  Validates inputs and writes the proposal record. **Touches no SW.** Returns the
  standard result dict (`ok`, `proposal_id`, `state`, `error`, …).
- `sw_dry_run_feature_add(proposal_id) -> dict`
  Open the doc → resolve+select the edge → add the fillet → rebuild → capture
  status → **roll back by closing the doc WITHOUT saving**. This is the
  non-destructive approval step. Records `dry_run_result` and sets state to
  `dry_run_ok` / `dry_run_broke`.
- `sw_commit_feature_add(proposal_id) -> dict`
  Refuse unless state is `dry_run_ok`. Re-run the open→resolve→add→rebuild, then
  **save** the doc. Set state `committed`.

Either add these as new functions + extend `ProposalStore` with
`propose_feature_add` / `dry_run_feature_add` / `commit_feature_add`, OR route a
`kind` switch through the existing entry points — your call, but keep the
existing variable-edit behaviour byte-for-byte unchanged.

### The proven COM sequence (port from the spike — exact calls)
```python
from ai_sw_bridge.com.earlybind import typed, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.selection import DurableEdgeRef, resolve_edge_ref, select_entity

mod = wrapper_module()
# open: typed ISldWorks.OpenDoc6 — Errors/Warnings are [in,out] byref longs,
# pass as ints 0, 0 (omitting them raises "Type mismatch"); returns a tuple
# (doc, errors, warnings).
SW_DOC_PART, SW_OPEN_SILENT = 1, 1
ret = typed(sw, "ISldWorks", module=mod).OpenDoc6(path, SW_DOC_PART, SW_OPEN_SILENT, "", 0, 0)
doc = ret[0] if isinstance(ret, tuple) else ret
doc.ForceRebuild3(False)            # MUST rebuild before resolving, else token -> "Deleted"

res = resolve_edge_ref(doc, DurableEdgeRef.from_dict(target))
if res.entity is None:
    ...                             # unresolved -> dry_run failure, not a crash

fm = doc.FeatureManager
data = fm.CreateDefinition(1)        # 1 == swFmFillet
fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
fd.Initialize(0)                     # 0 == swConstRadiusFillet. USE Initialize(0),
                                     # NOT `fd.Type = 0` (Type= raises AttributeError).
fd.DefaultRadius = radius_mm / 1000.0
select_entity(res.entity)            # select the edge right before CreateFeature
feat = fm.CreateFeature(fd)          # materialized fillet; None == failure
# feat.GetTypeName2() -> "Fillet" on success
```

A feature "materialized" iff `feat is not None and not isinstance(feat, int)`.

## Hard constraints (do not violate)
- **File safety:** dry_run is non-destructive — it MUST NOT save; roll back by
  `sw.CloseDoc(<title>)` without saving. commit saves ONLY the target doc.
  Never touch any doc other than `doc_path`. Assume the target doc is not already
  open; if it is the active doc, surface an error rather than closing the user's
  work.
- `mutate.py` already imports `from .sw_com import get_sw_app, get_active_doc,
  resolve`. Reuse `get_sw_app()`. There is **no** existing open-doc helper —
  use the `OpenDoc6` call above.
- **Tests must be pywin32-free** (CI has no SW). Mock the COM seam exactly like
  `tests/test_selection_live.py` and `tests/com/test_earlybind.py` do
  (monkeypatch `get_sw_app`, the `OpenDoc6` / `FeatureManager` / `CreateDefinition`
  surface, and `selection.resolve_edge_ref` / `select_entity`). There is **no
  existing `tests/test_mutate.py`** — create `tests/test_mutate_feature_add.py`.
  Cover: propose writes a record and touches no SW; dry_run on a resolvable edge
  → `dry_run_ok` and **asserts no save was called**; dry_run on an unresolvable
  edge → `dry_run_broke` with a clear error; commit refuses unless `dry_run_ok`;
  commit saves exactly once.
- Run the full suite (`python -m pytest -q`) — it must stay green (currently
  1277 passed, 2 skipped).
- **Commit only, do not push.** No `Co-Authored-By` trailers (forbidden by
  `CONTRIBUTING.md:62`). Use a `feat(mutate): …` subject.
- Windows + bracket in repo path: prefer the Bash tool with quoted paths or
  `git -C "<path>"`; PowerShell mangles the `[Local]_Station` segment.

## Definition of done
1. The three `feature_add` PAE functions + `ProposalStore` methods, with the
   existing variable-edit path unchanged.
2. `tests/test_mutate_feature_add.py` green; full suite green.
3. A short note appended to `docs/central_idea/keystone_status.md` §5 marking F1
   done (this file is gitignored — edit locally, do not commit it).
4. One commit, `feat(mutate): feature_add proposal kind (fillet on durable edge, F1)`.
5. If a live SOLIDWORKS seat is available, also run a manual seat validation that
   mirrors `spike_durable_feature_add.py` through the new PAE functions on a
   throwaway temp `.sldprt` (build+save it yourself; never use the user's saved
   parts), and paste the resulting proposal dicts. If no seat, say so explicitly.

Do not gold-plate: one feature type (constant-radius fillet), one target kind
(`DurableEdgeRef`). Wizard-hole / base-flange and an edit-time fingerprint
fallback are explicitly out of scope for F1.
