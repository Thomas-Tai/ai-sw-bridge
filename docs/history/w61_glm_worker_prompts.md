# W61 — Residual sketch-editing lanes — GLM/Sonnet worker prompts

Four paste-ready prompts (one per offline session). Same architecture as W60:
each lane authors **one** op module + offline tests + a derisk spike it does NOT
run, inside an isolated worktree. W0 (the seat holder) fires each spike on the
live SOLIDWORKS seat, adjudicates the segment-count delta + save/reopen
survival, then wires `register()` + merges.

W61 closes the **residual Sketch-tab editing rows** (§5.1/§5.18) that W60 left in
Population C — Mirror, Sketch Fillet, Sketch Chamfer, Move/Copy — extending the
**shipped `spec/sketch_editing` sub-package** (W60). All four methods are
DLL-verified (SW2024 v32) and **selection-based, not ray-cast** — they sidestep
the headless UI wall that walled `sketch_trim`.

| Lane | Method (DLL-verified) | Effect | Risk |
|---|---|---|---|
| fillet | `ISketchManager.CreateFillet(Radius, ConstrainedCorners)→SketchSegment` | +1 arc (4→5) | low |
| chamfer | `ISketchManager.CreateChamfer(Type, Distance, AngleORdist)→SketchSegment` | +1 line (4→5) | low |
| move_copy | `IModelDocExtension.MoveOrCopy(Copy, NumCopies, KeepRel, bx,by,bz, dx,dy,dz)→void` | +N copies (4→8) | low |
| mirror | `IModelDoc2.SketchMirror()→void` (no args; acts on selection) | +N mirror (3→5) | **boss fight** |

---

## §0 SHARED CONTEXT (every lane reads this)

**Project:** `ai-sw-bridge` — a declarative JSON→SOLIDWORKS COM bridge. You author
Python + offline tests + a spike file you will NOT run (you have no seat).
Follow the prompt LITERALLY. Do not explore beyond the named files. Do not
redesign.

**Architecture you are extending (already shipped, do NOT modify):**
`src/ai_sw_bridge/spec/sketch_editing/` — a CLI-only Propose/DryRun/Commit
surface (`ai-sw-sketch-edit`), NOT the feature_add registry, NOT MCP. Each op is
one collision-free module exporting an `OP` descriptor; W0 registers it in
`__init__.py` (one line per lane). The W0-owned `_base.py` gives you everything:

```
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m, deg_to_rad,
)
```
- `SketchEditOp(op, schema, validate, apply, verify_effect)` — the descriptor.
- `get_segments(sk)` → tuple of sketch segments (wraps the `GetSketchSegments`
  PROPERTY — no parens).
- `select_segment(seg, append, mark)` → bool (raw `seg.Select2`; typed fails).
- `clear_selection(doc)`, `mm_to_m(x)`, `deg_to_rad(d)`.
- The orchestrator `apply_sketch_edit(doc, sketch_name, op_token, params)` does:
  open by name → snapshot segment count → `op.apply(doc, sk, params)` →
  snapshot → **always close** → rebuild → adjudicate via `op.verify_effect`.
  Your op operates ONLY on the already-open active sketch; it NEVER opens/closes/
  rebuilds.

**Op-module contract (mirror the W60 lanes `offset.py`/`convert.py`):**
- module-scope imports only `._base` + stdlib (must import with NO live seat).
- `_SCHEMA` = JSON Schema, `additionalProperties: False`.
- `_validate(params)` raises `SketchEditError` on semantic violations.
- `_apply(doc, sk, params) -> dict` — select entities via `select_segment`, call
  the COM method, return `{"ok": <bool>, ...}`. On a bad index / failed select,
  return `{"ok": False, "error": "..."}` (fail closed, do NOT raise).
- `_verify(before, after, params) -> (bool, str)` — the EFFECT gate. Success is a
  **segment-COUNT delta**, never a True return (the W21/W42 ghost trap). All four
  W61 ops ADD segments → `after > before`.
- `OP = SketchEditOp(op="sketch_<x>", schema=_SCHEMA, validate=_validate,
  apply=_apply, verify_effect=_verify)`.

**HARD RULES (violating any = failure):**
- Create/modify ONLY your 3 files (named per lane). NEVER touch `__init__.py`,
  `_base.py`, `cli/sketch_edit.py`, `pyproject.toml`, or
  `spikes/v0_2x/_sketch_edit_fixtures.py` (all W0-owned).
- Success is a sketch-segment COUNT change, never a truthy return.
- No "Co-Authored-By" lines in commits.
- Python: `C:/Python314/python.exe`; always prefix env `PYTHONPATH=src`.

**Tests:** build fake COM objects in the style of
`tests/spec/test_sketch_edit_base.py` / `test_sketch_edit_offset.py` — a fake
`doc` with a fake `SketchManager` (and, where used, `Extension`) whose methods
record args and mutate a fake segment list; a fake sketch whose
`GetSketchSegments` PROPERTY returns a tuple of fake segments; fake segments
whose `Select2(append, mark)` returns True. Read those two files for the exact
idiom before writing yours.

**Spike harness:** copy the skeleton from `spike_sketch_offset.py` — it imports
`_sketch_edit_fixtures as fx`, `register`s your `OP`, builds a fixture, drives
`apply_sketch_edit`, then `fx.save_and_reopen` + `fx.count_named_segments` to
prove survival. Exit 0=PASS, 2=NO_OP (clean return, Δ0), 1=ERROR. DO NOT run it.
The fixtures named below already exist in `_sketch_edit_fixtures.py` (W0-owned).

---

## LANE 1 — fillet  (worktree `C:/D/wt_w61fillet`, branch `feat/w61-fillet`)

Files (ONLY these 3):
```
src/ai_sw_bridge/spec/sketch_editing/fillet.py
tests/spec/test_sketch_edit_fillet.py
spikes/v0_2x/spike_sketch_fillet.py
```

Write `fillet.py` EXACTLY:
```python
"""sketch_fillet — round the corner between two selected sketch entities (W61)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["radius_mm", "entities"],
    "properties": {
        "radius_mm": {"type": "number", "exclusiveMinimum": 0},
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0},
                     "minItems": 2, "maxItems": 2},
        "constrained_corners": {"type": "integer", "minimum": 0},
    },
}

def _validate(params: dict) -> None:
    if params.get("radius_mm", 0) <= 0:
        raise SketchEditError("sketch_fillet: radius_mm must be > 0")
    if len(params.get("entities", [])) != 2:
        raise SketchEditError("sketch_fillet: exactly 2 entities (two sides of a corner) required")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ret = doc.SketchManager.CreateFillet(
        mm_to_m(params["radius_mm"]),
        int(params.get("constrained_corners", 0)),
    )
    return {"ok": ret is not None, "raw_return": str(ret)}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (fillet trims 2 sides + inserts an arc, net +1)"

OP = SketchEditOp(op="sketch_fillet", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
```

Tests (`test_sketch_edit_fillet.py`) — fake `SketchManager.CreateFillet(rad, cc)`
records args and appends 1 fake segment, returns a truthy fake segment object:
- `_validate` accepts `{"radius_mm": 5, "entities": [0, 1]}`.
- `_validate` raises on `radius_mm == 0`; raises on `entities == [0]` (not 2).
- `_apply` selects [0,1] and calls `CreateFillet` with first arg `== 0.005`
  (metres) and second arg an int.
- `_apply` returns `{"ok": False, ...}` when an entity index is out of range.
- `_apply` returns `{"ok": False, ...}` when `CreateFillet` returns None.
- `_verify(4, 5, {})` → `(True, ...)`; `_verify(4, 4, {})` → `(False, ...)`.

Spike (`spike_sketch_fillet.py`) — from the offset skeleton:
```python
sketch, n0 = fx.build_rect_sketch(doc)          # ("Sketch1", 4) corner rect
params = {"radius_mm": 5, "entities": [0, 1]}    # two adjacent sides share a corner
res = apply_sketch_edit(doc, sketch, "sketch_fillet", params)
# PASS iff res["ok"] and segments_after > segments_before (expect 4->5) and survives reopen.
```

Run until green, then commit:
```
cd "C:/D/wt_w61fillet" && PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_fillet.py -q
PYTHONPATH=src C:/Python314/python.exe -c "from ai_sw_bridge.spec.sketch_editing.fillet import OP; print(OP.op)"
git add src/ai_sw_bridge/spec/sketch_editing/fillet.py tests/spec/test_sketch_edit_fillet.py spikes/v0_2x/spike_sketch_fillet.py
git commit -m "feat(W61): sketch_fillet lane — CreateFillet op + offline tests + derisk spike"
```
Report: pytest summary, commit hash, spike `{op, sketch, params}`. Blocker → STOP and describe.

---

## LANE 2 — chamfer  (worktree `C:/D/wt_w61chamfer`, branch `feat/w61-chamfer`)

Files (ONLY these 3):
```
src/ai_sw_bridge/spec/sketch_editing/chamfer.py
tests/spec/test_sketch_edit_chamfer.py
spikes/v0_2x/spike_sketch_chamfer.py
```

Write `chamfer.py` EXACTLY:
```python
"""sketch_chamfer — chamfer the corner between two selected sketch entities (W61)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

# swSketchChamferType_e (DLL-verified): 0 DistanceAngle, 1 DistanceDistance, 2 DistanceEqual.
# This op supports the DISTANCE modes (1, 2) only; angle mode (0) is deferred
# (its second arg is an angle in radians, not a distance).
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dist1_mm", "entities"],
    "properties": {
        "chamfer_type": {"type": "integer", "enum": [1, 2]},
        "dist1_mm": {"type": "number", "exclusiveMinimum": 0},
        "dist2_mm": {"type": "number", "exclusiveMinimum": 0},
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0},
                     "minItems": 2, "maxItems": 2},
    },
}

def _validate(params: dict) -> None:
    if params.get("dist1_mm", 0) <= 0:
        raise SketchEditError("sketch_chamfer: dist1_mm must be > 0")
    if len(params.get("entities", [])) != 2:
        raise SketchEditError("sketch_chamfer: exactly 2 entities required")
    if params.get("chamfer_type", 1) not in (1, 2):
        raise SketchEditError("sketch_chamfer: chamfer_type must be 1 (DistanceDistance) or 2 (DistanceEqual)")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ctype = int(params.get("chamfer_type", 1))
    d1 = mm_to_m(params["dist1_mm"])
    d2 = mm_to_m(params.get("dist2_mm", params["dist1_mm"]))  # CreateChamfer 3rd arg = 2nd distance
    ret = doc.SketchManager.CreateChamfer(ctype, d1, d2)
    return {"ok": ret is not None, "raw_return": str(ret)}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (chamfer inserts a line, net +1)"

OP = SketchEditOp(op="sketch_chamfer", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
```

Tests — fake `CreateChamfer(type, d1, d2)` records args, appends 1 segment, returns truthy:
- `_validate` accepts `{"dist1_mm": 5, "entities": [0, 1]}` (default type 1).
- `_validate` raises on `dist1_mm == 0`; on `entities` length != 2; on `chamfer_type == 0`.
- `_apply` passes int type, `d1 == 0.005`, `d2 == 0.005` (defaults to d1 when dist2 omitted).
- `_apply` returns `{"ok": False, ...}` on out-of-range index and on None return.
- `_verify(4, 5, {})` → `(True, ...)`; `_verify(4, 4, {})` → `(False, ...)`.

Spike — from the offset skeleton:
```python
sketch, n0 = fx.build_rect_sketch(doc)                       # ("Sketch1", 4)
params = {"chamfer_type": 1, "dist1_mm": 5, "dist2_mm": 5, "entities": [0, 1]}
res = apply_sketch_edit(doc, sketch, "sketch_chamfer", params)
# PASS iff res["ok"] and segments_after > segments_before (expect 4->5) and survives reopen.
```
Run/commit exactly like Lane 1 (`sketch_chamfer`). Commit msg:
`feat(W61): sketch_chamfer lane — CreateChamfer op + offline tests + derisk spike`

---

## LANE 3 — move_copy  (worktree `C:/D/wt_w61movecopy`, branch `feat/w61-movecopy`)

Files (ONLY these 3):
```
src/ai_sw_bridge/spec/sketch_editing/move_copy.py
tests/spec/test_sketch_edit_move_copy.py
spikes/v0_2x/spike_sketch_move_copy.py
```

Write `move_copy.py` EXACTLY:
```python
"""sketch_move_copy — copy selected sketch entities to a new location (W61).

Uses IModelDocExtension.MoveOrCopy with Copy=True (the verifiable mode: it adds
NumCopies * selected segments). Pure move (Copy=False) transforms in place with
NO segment-count change (delta 0) and is out of scope for the count-delta verify
doctrine, so this op always copies.
"""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "dest_mm"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "num_copies": {"type": "integer", "minimum": 1},
        "base_mm": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "dest_mm": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "keep_relations": {"type": "boolean"},
    },
}

def _validate(params: dict) -> None:
    if not params.get("entities"):
        raise SketchEditError("sketch_move_copy: entities must be a non-empty list")
    if len(params.get("dest_mm", [])) != 3:
        raise SketchEditError("sketch_move_copy: dest_mm must be [x, y, z] mm")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    base = params.get("base_mm", [0.0, 0.0, 0.0])
    dest = params["dest_mm"]
    # MoveOrCopy returns void -> NEVER trust a return; the orchestrator's count
    # delta is the gate. (Copy, NumCopies, KeepRelations, bx,by,bz, dx,dy,dz)
    doc.Extension.MoveOrCopy(
        True,
        int(params.get("num_copies", 1)),
        bool(params.get("keep_relations", False)),
        mm_to_m(base[0]), mm_to_m(base[1]), mm_to_m(base[2]),
        mm_to_m(dest[0]), mm_to_m(dest[1]), mm_to_m(dest[2]),
    )
    return {"ok": True, "raw_return": "void"}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (copy adds num_copies*selected)"

OP = SketchEditOp(op="sketch_move_copy", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
```

Tests — fake `doc.Extension.MoveOrCopy(*args)` records args and appends
`num_copies * len(selected)` fake segments (returns None — it's void):
- `_validate` accepts `{"entities": [0,1,2,3], "dest_mm": [30,0,0]}`.
- `_validate` raises on `entities == []`; on `dest_mm` length != 3.
- `_apply` selects all entities, calls `MoveOrCopy` with first arg `True`, 2nd an
  int, and the dest coords metre-converted (`30` mm → `0.030`).
- `_apply` returns `{"ok": False, ...}` on an out-of-range index.
- `_verify(4, 8, {})` → `(True, ...)`; `_verify(4, 4, {})` → `(False, ...)`.

Spike — from the offset skeleton:
```python
sketch, n0 = fx.build_rect_sketch(doc)                                  # ("Sketch1", 4)
params = {"entities": [0, 1, 2, 3], "num_copies": 1, "dest_mm": [60, 0, 0]}
res = apply_sketch_edit(doc, sketch, "sketch_move_copy", params)
# PASS iff segments_after > segments_before (expect 4->8) and survives reopen.
# Classify clean-return-but-segment_delta==0 as NO_OP (exit 2).
```
Run/commit like Lane 1 (`sketch_move_copy`). Commit msg:
`feat(W61): sketch_move_copy lane — MoveOrCopy op + offline tests + derisk spike`

---

## LANE 4 — mirror  (worktree `C:/D/wt_w61mirror`, branch `feat/w61-mirror`) — BOSS FIGHT

Files (ONLY these 3):
```
src/ai_sw_bridge/spec/sketch_editing/mirror.py
tests/spec/test_sketch_edit_mirror.py
spikes/v0_2x/spike_sketch_mirror.py
```

Why boss fight: `IModelDoc2.SketchMirror()` takes **NO args** — it acts entirely
on selection state. It mirrors the currently-selected entities about the
selected centerline. The exact selection protocol (which mark the centerline
needs) is the one unknown the W0 seat spike will validate/correct. Author the
best-guess below; W0 fires it and adjudicates.

Write `mirror.py` EXACTLY:
```python
"""sketch_mirror — mirror selected sketch entities about a centerline (W61).

IModelDoc2.SketchMirror() takes NO args; it mirrors the currently-selected
entities about the selected centerline. Protocol (W0 validates on the seat):
select the entities to mirror, then select the centerline LAST.
"""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "centerline"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "centerline": {"type": "integer", "minimum": 0},
    },
}

def _validate(params: dict) -> None:
    if not params.get("entities"):
        raise SketchEditError("sketch_mirror: entities must be a non-empty list")
    if params.get("centerline") is None:
        raise SketchEditError("sketch_mirror: centerline index required")
    if params["centerline"] in params["entities"]:
        raise SketchEditError("sketch_mirror: centerline must not be among the mirrored entities")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for idx in list(params["entities"]) + [params["centerline"]]:
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
    # entities to mirror first, then the centerline LAST (all appended, mark 0)
    for j, idx in enumerate(params["entities"]):
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select mirror entity {idx}"}
    if not select_segment(segs[params["centerline"]], append=True, mark=0):
        return {"ok": False, "error": "could not select centerline"}
    # SketchMirror is on IModelDoc2 (the doc), NOT SketchManager. Returns void.
    doc.SketchMirror()
    return {"ok": True, "raw_return": "void"}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (mirror duplicates entities across the line)"

OP = SketchEditOp(op="sketch_mirror", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
```

Tests — fake `doc.SketchMirror()` (a method on the fake DOC, not SketchManager)
records the call and appends `len(selected_entities)` fake segments; fake
`select_segment` via the fake segments' `Select2`:
- `_validate` accepts `{"entities": [1, 2], "centerline": 0}`.
- `_validate` raises on `entities == []`; on `centerline` in `entities`.
- `_apply` selects entities then the centerline (centerline appended LAST) and
  calls `doc.SketchMirror()`.
- `_apply` returns `{"ok": False, ...}` on an out-of-range index.
- `_verify(3, 5, {})` → `(True, ...)`; `_verify(3, 3, {})` → `(False, ...)`.

Spike — from the offset skeleton, using the W0 mirror fixture:
```python
sketch, n0, ents, cl = fx.build_mirror_seed_sketch(doc)   # ("Sketch1", 3, [1,2], 0)
params = {"entities": ents, "centerline": cl}
res = apply_sketch_edit(doc, sketch, "sketch_mirror", params)
# PASS iff segments_after > segments_before (expect 3->5) and survives reopen.
# Classify clean-return-but-segment_delta==0 as NO_OP (exit 2) -> STOP, report to W0
# (likely the centerline selection-mark protocol; W0 fixes on the seat).
```
Run/commit like Lane 1 (`sketch_mirror`). Commit msg:
`feat(W61): sketch_mirror lane — SketchMirror op + offline tests + derisk spike`

---

## W0 return protocol (for reference — W0 runs this, not the workers)

Per lane: pull branch → fire spike on the live seat → adjudicate (segment delta
in expected direction AND survives save→reopen) → if GREEN wire
`register(_<lane>.OP)` in `__init__.py` + merge; if NO_OP/ERROR halt that lane
(pause-on-errors) and diagnose. Fixture/harness bugs are W0's to fix (the W60
lesson: when a spike ERRORs, suspect the W0 fixture before the lane).
