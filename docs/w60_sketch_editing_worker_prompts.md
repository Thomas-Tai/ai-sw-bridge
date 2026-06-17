# W60 Sketch-Editing — Parallel Worker Prompts

> **Orchestration model (W0 = me, the integrator holding the live SOLIDWORKS seat):**
> W0 has shipped the W0-owned scaffold (`feat/w60-sketchedit @ 8bf6a09`): the
> `spec/sketch_editing/_base.py` contract, the empty `__init__.py` registration
> seam, and the `ai-sw-sketch-edit` CLI. Each worker below authors **exactly one
> op lane** in an **isolated git worktree** off `feat/w60-sketchedit`. The four
> lanes touch **disjoint files**, so they run fully in parallel with zero
> hot-file collisions. W0 fires each lane's derisk spike on the singleton seat,
> adjudicates verify-the-EFFECT, then wires the proven `OP` into `__init__.py`
> (one line) and merges.
>
> **How to launch:** open one fresh session per lane. Paste **§0 SHARED CONTEXT**
> followed by **one** lane block (§1–§4). That is the entire self-contained brief.

---

## 0. SHARED CONTEXT — paste into EVERY worker session

You are an **offline worker** on the `ai-sw-bridge` project — a declarative
JSON → SOLIDWORKS COM bridge (out-of-process via pywin32, marshaled into a live
SW seat). You do **not** have a SOLIDWORKS seat; you author code + offline tests
+ a derisk spike. **W0 (the orchestrator) holds the only live seat and will fire
your spike.** You work in an isolated worktree and never touch shared files.

**Repo:** `C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge`
**Python:** `C:\Python314\python.exe`, always with `PYTHONPATH=src`.
**Branch point:** `feat/w60-sketchedit` (commit `8bf6a09` — the scaffold).

**Set up your worktree (substitute `<lane>` per the lane block):**
```bash
git worktree add -b feat/w60-<lane> "C:/D/wt_w60<lane>" feat/w60-sketchedit
cd "C:/D/wt_w60<lane>"
```

### What you are building

A **sketch-editing op** in the §6.5 **CLI-only Propose-DryRun-Commit** surface
(`ai-sw-sketch-edit`), mirroring `ai-sw-sketch-relations`. **NEVER MCP** — these
are mutations gated behind the CLI propose/approve flow. The op edits an
**existing sketch's segment set**. The CLI + orchestrator already exist; you
supply one op module + its tests + a derisk spike.

### The contract (read `src/ai_sw_bridge/spec/sketch_editing/_base.py` first)

W0's orchestrator `apply_sketch_edit(doc, sketch_name, op_token, params)` already
does all of this **for you**: opens the named sketch for edit, snapshots the
segment count, dispatches your op against the **OPEN active sketch**, snapshots
again, **closes** the sketch, rebuilds, then calls your `verify_effect`. So your
op module **operates only on the already-open active sketch** — it **must NOT**
open / close / rebuild / save.

Your module exports exactly one module-level descriptor:

```python
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment,
    mm_to_m, deg_to_rad,
)

_SCHEMA = { ... }                       # JSON-schema for params, additionalProperties: false

def _validate(params: dict) -> None:    # semantic checks beyond schema; raise SketchEditError
    ...

def _apply(doc, sk, params: dict) -> dict:
    # operate on the OPEN active sketch `sk` via doc.SketchManager.<call>
    # return at least {"ok": <did the COM call report success>} + diagnostics
    ...

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    # adjudicate the segment-count delta (the verify-the-EFFECT gate)
    ...

OP = SketchEditOp(op="sketch_<lane>", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
```

**`_base` helpers available to your `_apply` (do not re-implement):**
- `clear_selection(doc)` — `doc.ClearSelection2(True)`, swallowed.
- `get_segments(sk) -> list` — reads `sk.GetSketchSegments` (a **PROPERTY**, no
  parens — calling it `()` raises "'tuple' object is not callable").
- `select_segment(seg, append=, mark=) -> bool` — **raw** `seg.Select2(append, mark)`.
  Use raw; the typed `IEntity.Select2` fails ("Invalid number of parameters").
- `mm_to_m(v)` (÷1000), `deg_to_rad(v)`.
- `SketchEditError` (raise for bad params), `SketchEditOp`.

### Verify-the-EFFECT doctrine (load-bearing — the W21/W42 ghost trap)

Success is a **sketch-segment COUNT delta**, never a `True` return / non-None
handle. `_verify` is the gate; the orchestrator's `ok` = `call_ok AND
effect_verified`. Pick the predicate your op genuinely produces (see your lane
block). Your **spike** must additionally prove the delta **survives
save→reopen**.

### Doctrine (non-negotiable)

- **pause-on-errors:** if your spike walls (clean COM return but **zero** segment
  delta — a silent no-op) or errors, **STOP and report** the diagnosis +
  options. Do not thrash. A silent no-op is the signature of an out-of-process
  COM wall (cf. rib / move-copy-body) — surface it, don't paper over it.
- **Never `Close()` / `CloseDoc` mid-session** — corrupts COM. Your spike cleans
  up with `CloseAllDocuments(True)` in a `finally`.
- **Raw-first selection.** Raw `seg.Select2` over typed `IEntity.Select2`.
- **Offline-importable:** no `get_sw_app` at module import. Any live-COM helper
  (e.g. durable-ref resolution) is **lazily imported inside `_apply`**, so
  `propose` validates fully offline.

### HOT-FILE BOUNDARIES (the parallel-safety contract — DO NOT CROSS)

You create/edit **only these three files**:
1. `src/ai_sw_bridge/spec/sketch_editing/<lane>.py` — your op module.
2. `tests/spec/test_sketch_edit_<lane>.py` — your offline mock-COM tests.
3. `spikes/v0_2x/spike_sketch_<lane>.py` — your derisk spike (W0 fires it).

You **must NOT touch** (W0 owns these — editing them causes merge collisions and
breaks the other three lanes):
- `spec/sketch_editing/__init__.py` (W0 wires your `OP` with one line)
- `spec/sketch_editing/_base.py`, `cli/sketch_edit.py`, `pyproject.toml`

### Deliverables / definition of done

1. Op module exporting `OP`, importing cleanly **offline**.
2. Offline tests (fake COM seam — model on
   `tests/spec/test_sketch_edit_base.py` and `tests/spec/test_sketch_relations.py`):
   cover `_validate` (happy + each rejection), `_apply` (selects the right seeds,
   calls the right `SketchManager` method with **unit-converted** args, returns
   `ok`), and `_verify` (correct direction + boundary). Run:
   `PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_<lane>.py -q`
3. Derisk spike (model on `spikes/v0_2x/spike_hem_v5.py` for the
   connect / fixture-build / capture / save-reopen / exit-code skeleton):
   - connect to the running SW; build its **own** sketch fixture (don't assume
     state);
   - `from ai_sw_bridge.spec.sketch_editing import register, apply_sketch_edit`,
     `from ai_sw_bridge.spec.sketch_editing.<lane> import OP`, then `register(OP)`
     (W0 hasn't wired `__init__.py` yet — register in the spike);
   - call `apply_sketch_edit(doc, "<sketch>", "sketch_<lane>", params)`;
   - assert the segment delta in the expected direction, **save→reopen→recount**;
   - exit `0` = PASS (delta + survived), `2` = NO_OP (silent wall), `1` = ERROR;
     `CloseAllDocuments(True)` in `finally`.
4. Commit on `feat/w60-<lane>`. **No `Co-Authored-By` trailers** (CONTRIBUTING.md:62).
   Report PASS/NO-OP/ERROR to W0 and stop.

The exact COM signatures below are confirmed in `docs/sw_api_full.md` (the
DLL-validated full reference; gitignored — ask W0 if you need the raw entry).

---

## 1. LANE: offset — `sketch_offset` (`SketchOffset2`)  ·  worktree `wt_w60offset`

**Risk: LOW** (ISketchManager primitive; offsets selected sketch segments).

**COM signature (`ISketchManager`):**
```
SketchOffset2(double Offset, bool BothDirections, bool Chain,
              int CapEnds, int MakeConstruction, bool AddDimensions) -> bool
```
- `Offset` is in **METRES** (use `mm_to_m`). `MakeConstruction` and `CapEnds`
  are **Int32** (0 = off), not bool.

**`_apply` recipe:**
```python
clear_selection(doc)
segs = get_segments(sk)
for j, idx in enumerate(params["entities"]):
    if idx >= len(segs) or not select_segment(segs[idx], append=(j > 0), mark=0):
        return {"ok": False, "error": f"could not select segment {idx}"}
ret = doc.SketchManager.SketchOffset2(
    mm_to_m(params["distance_mm"]),
    bool(params.get("both_directions", False)),
    bool(params.get("chain", False)),
    int(params.get("cap_ends", 0)),
    1 if params.get("make_construction", False) else 0,
    bool(params.get("add_dimensions", False)),
)
return {"ok": bool(ret), "raw_return": ret}
```

**`params` schema:** `distance_mm` (number, `!= 0`), `entities` (array of int ≥ 0,
minItems 1), `both_directions`/`chain`/`make_construction`/`add_dimensions`
(bool, default false), `cap_ends` (int 0–2, default 0). `additionalProperties:
false`. `_validate`: reject `distance_mm == 0` and empty `entities`.

**`_verify`:** `after > before` (an offset adds ≥1 new segment; `both_directions`
adds 2×). Note in the `effect_note`.

**Spike fixture:** a sketch with one closed rectangle (4 segments) on the Front
plane; offset it 5 mm outward (`entities=[0,1,2,3]`, `chain=true`). Expect
`segments_after > segments_before` and survival on reopen.

---

## 2. LANE: convert — `sketch_convert` (`SketchUseEdge3`)  ·  worktree `wt_w60convert`

**Risk: MEDIUM** (seeds are **model edges/faces**, not sketch segments — needs
durable topology selection; verify out-of-process behaviour early).

**COM signature (`ISketchManager`):**
```
SketchUseEdge3(bool Chain, bool InnerLoops) -> bool
```
Converts the **currently-selected model edges/faces** onto the active sketch
plane (Convert Entities). So `_apply` must select the seed topology **before**
the call.

**Selection — use the project's durable reference infra (proven by hem/thread).**
Import at **module level** (exactly as `hem.py:38` does — `selection.live` is
offline-importable, so this keeps your module offline-safe AND lets your tests
monkeypatch the seam on your module's namespace):
```python
# top of convert.py, alongside the _base imports (mirrors hem.py:37-38):
from ...selection._edge_ref import DurableEdgeRef
from ...selection.live import resolve_edge_ref, select_entity

def _apply(doc, sk, params):
    clear_selection(doc)
    for j, ref_data in enumerate(params["refs"]):
        try:
            ref = DurableEdgeRef.from_dict(ref_data)          # ref_data is a dict
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"invalid edge_ref[{j}]: {exc}"}
        res = resolve_edge_ref(doc, ref)                       # -> RefResolution
        edge = getattr(res, "entity", None)                   # the live IEdge
        if edge is None:
            return {"ok": False,
                    "error": f"ref[{j}] did not resolve ({getattr(res, 'note', '')})"}
        if not select_entity(edge, append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select ref[{j}]"}
    ret = doc.SketchManager.SketchUseEdge3(
        bool(params.get("chain", False)),
        bool(params.get("inner_loops", False)),
    )
    return {"ok": bool(ret), "raw_return": ret}
```
> `resolve_edge_ref(doc, ref)` returns a `RefResolution`; the live edge is
> `res.entity` (can be `None` if the ref doesn't resolve — fail closed). This is
> hem.py's exact pattern (lines 159-177). Note the one **deliberate exception**
> to "no top-level live-COM import": the durable-selection seam is offline-safe
> (the whole offline suite imports it via `features/`), so importing it at module
> level is correct here. Everything else stays lazy.
> First task: read `src/ai_sw_bridge/features/hem.py` (lines ~37–38, 160–180) for
> the durable-ref shape (`selection._edge_ref.DurableEdgeRef`, base64 persist ID)
> and how it captures/resolves an edge. Your offline tests mock
> `resolve_edge_ref` + `select_entity` on **your** module's namespace
> (`monkeypatch.setattr(convert, "resolve_edge_ref", ...)`), as hem's tests do.

**`params` schema:** `refs` (array of **object**, minItems 1 — each a
`DurableEdgeRef` dict, the same shape hem's `edge_ref` accepts; type `object`,
leave its inner shape open or copy hem's), `chain`/`inner_loops` (bool, default
false). `additionalProperties: false`. `_validate`: reject empty `refs`.

**`_verify`:** `after > before` (each converted edge becomes a new sketch
segment).

**Spike fixture:** extrude a box; open a **new** sketch on a planar face;
capture a durable ref for one of that face's perimeter edges (model on hem's
edge_ref capture); convert it. Expect `+1` segment and survival on reopen. **If
`SketchUseEdge3` returns cleanly but adds 0 segments → STOP (silent o-o-p wall),
report to W0.**

---

## 3. LANE: trim — `sketch_trim` (`SketchTrim`)  ·  worktree `wt_w60trim`

**Risk: LOW–MEDIUM** (no seed selection; identifies the target by pick-point).

**COM signature (`ISketchManager`):**
```
SketchTrim(int Option, double X, double Y, double Z) -> bool
```
`Option` ∈ `swSketchTrimChoice_e`: `Closest=0`, `Corner=1`, `TwoEntities=2`,
`EntityPoint=3`, `Entities=4`, `Outside=5`, `Inside=6`. For `Closest=0`,
`(X,Y,Z)` is the pick point (**METRES**) on the segment piece to remove.

**`_apply` recipe:**
```python
ret = doc.SketchManager.SketchTrim(
    int(params.get("option", 0)),
    mm_to_m(params["x_mm"]),
    mm_to_m(params["y_mm"]),
    mm_to_m(params.get("z_mm", 0.0)),
)
return {"ok": bool(ret), "raw_return": ret}
```

**`params` schema:** `option` (int 0–6, default 0), `x_mm` / `y_mm` (number,
required), `z_mm` (number, default 0). `additionalProperties: false`.
`_validate`: reject `option` outside 0–6.

**`_verify`:** `after != before` — trim **always** changes the segment count
(removes a dangling piece → `−1`, or splits a crossing segment → `+1`). Return
`(after != before, f"{before}->{after}")`.
> Your **spike** must pin the *specific* direction for its fixture (assert the
> exact expected count), even though the production predicate is `!=`.

**Spike fixture:** two crossing lines (or a line with a dangling end past an
intersection); trim-closest (`option=0`) with the pick point on the dangling
piece → expect `segments_after < segments_before` (a piece removed) **or** a
clean split `+1`, whichever your fixture deterministically produces. Prove it
survives reopen.

---

## 4. LANE: pattern — `sketch_pattern` (`CreateLinearSketchStepAndRepeat`)  ·  worktree `wt_w60pattern`

**Risk: LOW** (multiplies selected seed segments along X/Y).

**COM signature (`ISketchManager`, 12-arg form):**
```
CreateLinearSketchStepAndRepeat(int NumX, int NumY, double SpacingX, double SpacingY,
    double AngleX, double AngleY, string DeleteInstances,
    bool XSpacingDim, bool YSpacingDim, bool AngleDim,
    bool CreateNumOfInstancesDimInXDir, bool CreateNumOfInstancesDimInYDir) -> bool
```
- Spacing in **METRES** (`mm_to_m`); angles in **RADIANS** (`deg_to_rad`).
- `DeleteInstances` = a string of skipped instance indices (default `""`).

**`_apply` recipe:**
```python
clear_selection(doc)
segs = get_segments(sk)
for j, idx in enumerate(params["entities"]):
    if idx >= len(segs) or not select_segment(segs[idx], append=(j > 0), mark=0):
        return {"ok": False, "error": f"could not select segment {idx}"}
ret = doc.SketchManager.CreateLinearSketchStepAndRepeat(
    int(params["num_x"]), int(params.get("num_y", 1)),
    mm_to_m(params["spacing_x_mm"]), mm_to_m(params.get("spacing_y_mm", 0.0)),
    deg_to_rad(params.get("angle_x_deg", 0.0)), deg_to_rad(params.get("angle_y_deg", 90.0)),
    str(params.get("delete_instances", "")),
    bool(params.get("x_spacing_dim", False)), bool(params.get("y_spacing_dim", False)),
    bool(params.get("angle_dim", False)),
    bool(params.get("num_x_dim", False)), bool(params.get("num_y_dim", False)),
)
return {"ok": bool(ret), "raw_return": ret}
```

**`params` schema:** `entities` (array int ≥ 0, minItems 1), `num_x` (int ≥ 1,
required), `num_y` (int ≥ 1, default 1), `spacing_x_mm` (number, required),
`spacing_y_mm` (number, default 0), `angle_x_deg`/`angle_y_deg` (number, default
0 / 90), `delete_instances` (string, default ""), the five `*_dim` flags (bool,
default false). `additionalProperties: false`. `_validate`: require
`num_x*num_y >= 2` (a 1×1 pattern is a no-op) and non-empty `entities`.

**`_verify`:** `after > before` (a 3×1 pattern of one seed adds 2 copies →
`after = before + seeds*(num_x*num_y - 1)`). Optionally tighten the note with the
expected count.

**Spike fixture:** a sketch with one circle (1 segment); 3×1 linear pattern,
`spacing_x_mm=20`. Expect `segments_after = 3` (`+2`) and survival on reopen.

---

## 5. SPIKE HARNESS — use the W0-owned fixture helper (do NOT hand-roll)

A shared helper already sits in your worktree at
`spikes/v0_2x/_sketch_edit_fixtures.py` (W0-owned — do not edit it). It removes
the three spike footguns: the connect/template boot, the proven sketch-build
sequence (a hand-rolled one silently yields a 0-segment sketch and a bogus
result), and durable-ref capture. **Import from it; keep your spike ~15 lines.**

Surface:
- `connect()` → live raw SW app · `new_part(sw)` → raw blank-part doc.
- `build_rect_sketch(doc)` → `("Sketch1", 4)` (offset) · `build_circle_sketch(doc)`
  → `("Sketch1", 1)` (pattern) · `build_overhang_lines_sketch(doc)` →
  `("Sketch1", 2, pick_xyz)` (trim) · `build_box_top_sketch(doc)` →
  `("Sketch2", edge)` (convert).
- `capture_edge_ref(doc, edge)` → a `DurableEdgeRef` dict for `refs` (convert).
- `count_named_segments(doc, name)` → int · `save_and_reopen(sw, doc)` → reopened doc.

Each lane's spike (replace `<lane>`/`<op>`/params/direction per your block):
```python
import sys, json, traceback
import _sketch_edit_fixtures as fx
from ai_sw_bridge.spec.sketch_editing import register, apply_sketch_edit
from ai_sw_bridge.spec.sketch_editing.<lane> import OP

def main():
    sw = fx.connect()
    try:
        register(OP)
        doc = fx.new_part(sw)
        sketch, n0 = fx.build_rect_sketch(doc)          # << your lane's fixture
        params = { ... }                                # << your lane's params
        res = apply_sketch_edit(doc, sketch, "sketch_<lane>", params)
        delta_ok = res["segments_after"] > res["segments_before"]   # << your direction
        doc2 = fx.save_and_reopen(sw, doc)
        n_reopen = fx.count_named_segments(doc2, sketch)
        survived = n_reopen == res["segments_after"]
        verdict = "PASS" if (res["ok"] and delta_ok and survived) else (
                  "NO_OP" if res["call_ok"] and res["segment_delta"] == 0 else "FAIL")
        print(json.dumps({"verdict": verdict, "result": res,
                          "n_reopen": n_reopen, "survived": survived}, default=str, indent=2))
        return 0 if verdict == "PASS" else (2 if verdict == "NO_OP" else 1)
    except Exception as exc:
        print(json.dumps({"verdict": "ERROR", "error": f"{type(exc).__name__}: {exc}",
                          "tb": traceback.format_exc()}, default=str)); return 1
    finally:
        try: sw.CloseAllDocuments(True)
        except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
```
- **convert** differs: `sketch, edge = fx.build_box_top_sketch(doc)` then
  `params = {"refs": [fx.capture_edge_ref(doc, edge)]}`; expect `+1`. Your spike
  MUST classify clean-return-but-`segment_delta == 0` as **NO_OP** (exit 2) —
  the out-of-process wall signature.
- **trim** differs: `sketch, n0, pick = fx.build_overhang_lines_sketch(doc)`;
  `params = {"option": 0, "x_mm": pick[0]*1000, "y_mm": pick[1]*1000}`; verify
  `res["segments_after"] != res["segments_before"]`.
- Still **DO NOT RUN** the spike — W0 fires it on the seat.

---

### W0 integration order (for reference — workers don't do this)

Per lane returning PASS, W0: fires the spike on the seat → confirms ΔSegments +
reopen-survival → adds one line to `spec/sketch_editing/__init__.py`
(`from . import <lane> as _<lane>; register(_<lane>.OP)`) → reruns the full
offline suite → merges `feat/w60-<lane>`. A NO_OP/ERROR lane is paused for joint
diagnosis (per pause-on-errors), exactly as rib/move-copy were.
