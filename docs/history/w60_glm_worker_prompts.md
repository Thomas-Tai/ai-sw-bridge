# W60 Sketch-Editing — GLM / Sonnet Worker Prompts (literal, paste-ready)

> These are the **lower-capability-model** variants of the W60 lane briefs:
> flat, explicit, "write this file verbatim" rather than "read and infer." Use
> them for Sonnet/GLM authoring sessions. Each block is fully self-contained —
> paste ONE block into ONE fresh session.
>
> **Status note:** the four W60 lanes were already authored GREEN by Opus
> workers (offset `09788e6`, convert `314aeb7`, trim `da81923`, pattern
> `d949168`). This file is therefore (a) the reproducible record, (b) a re-run
> artifact if a lane needs reworking, and (c) the template for the *next*
> sketch-editing lanes (Mirror, Move/Copy/Rotate/Scale/Stretch, Sketch
> Fillet/Chamfer) — copy a block and swap the op recipe.
>
> The op-module code below is **reference-correct** (matches the shipped lanes).
> A GLM/Sonnet worker should write it verbatim and focus its effort on the
> offline tests + running them green + the spike + the commit.

---

## LANE 1 — offset (`sketch_offset`)

```
ROLE
You are authoring ONE file-set for the ai-sw-bridge project (a declarative
JSON → SOLIDWORKS COM bridge). You have NO SOLIDWORKS — you write Python + offline
tests + a spike file you will NOT run. Follow this prompt LITERALLY. Do not
explore the repo beyond the files named here. Do not redesign anything.

WORKTREE (already created — do NOT create it)
  Path:   C:/D/wt_w60offset      Branch: feat/w60-offset
  Work only inside this path, with absolute paths.
  Python: C:/Python314/python.exe   Always prefix env: PYTHONPATH=src

HARD RULES (violating any = failure)
  - Create/modify ONLY these 3 files:
      src/ai_sw_bridge/spec/sketch_editing/offset.py
      tests/spec/test_sketch_edit_offset.py
      spikes/v0_2x/spike_sketch_offset.py
  - NEVER touch: __init__.py, _base.py, cli/sketch_edit.py, pyproject.toml,
    spikes/v0_2x/_sketch_edit_fixtures.py
  - Success is a sketch-SEGMENT-COUNT change, never a True return value.
  - No "Co-Authored-By" lines in the commit.

STEP 1 — read only these (for context, do not edit):
  src/ai_sw_bridge/spec/sketch_editing/_base.py
  tests/spec/test_sketch_edit_base.py

STEP 2 — write src/ai_sw_bridge/spec/sketch_editing/offset.py EXACTLY:
----------------------------------------------------------------------
"""sketch_offset — Offset Entities on the active sketch (W60)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["distance_mm", "entities"],
    "properties": {
        "distance_mm": {"type": "number"},
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "both_directions": {"type": "boolean"},
        "chain": {"type": "boolean"},
        "cap_ends": {"type": "integer", "minimum": 0, "maximum": 2},
        "make_construction": {"type": "boolean"},
        "add_dimensions": {"type": "boolean"},
    },
}

def _validate(params: dict) -> None:
    if params.get("distance_mm", 0) == 0:
        raise SketchEditError("sketch_offset: distance_mm must be non-zero")
    if not params.get("entities"):
        raise SketchEditError("sketch_offset: entities must be a non-empty list")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
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

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (offset adds >=1)"

OP = SketchEditOp(op="sketch_offset", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
----------------------------------------------------------------------

STEP 3 — write tests/spec/test_sketch_edit_offset.py. Build a fake doc with a
fake SketchManager whose .SketchOffset2(*args) records args and appends 1 fake
segment; a fake sketch whose GetSketchSegments PROPERTY returns a tuple of fake
segments; fake segments whose Select2(append, mark) return True. Copy the
fake-COM style from tests/spec/test_sketch_edit_base.py. Tests (minimum):
  - _validate accepts {"distance_mm":5,"entities":[0]}
  - _validate raises on distance_mm==0
  - _validate raises on entities==[]
  - _apply selects [0,1] and calls SketchOffset2 with first arg == 0.005 and
    make_construction passed as int (0 or 1)
  - _apply returns {"ok": False, ...} when an entity index is out of range
  - _verify(4,8,{}) -> (True, ...) ; _verify(4,4,{}) -> (False, ...)

STEP 4 — write spikes/v0_2x/spike_sketch_offset.py from the §5 SPIKE HARNESS
skeleton in docs/w60_sketch_editing_worker_prompts.md, with:
  sketch, n0 = fx.build_rect_sketch(doc)
  params = {"distance_mm": 5, "entities": [0,1,2,3], "chain": True}
  apply_sketch_edit(doc, sketch, "sketch_offset", params)
  PASS iff res["ok"] and segments_after > segments_before and survives reopen.
DO NOT run this file.

STEP 5 — run until green:
  cd "C:/D/wt_w60offset" && PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_offset.py -q
  PYTHONPATH=src C:/Python314/python.exe -c "from ai_sw_bridge.spec.sketch_editing.offset import OP; print(OP.op)"

STEP 6 — commit:
  git add src/ai_sw_bridge/spec/sketch_editing/offset.py tests/spec/test_sketch_edit_offset.py spikes/v0_2x/spike_sketch_offset.py
  git commit -m "feat(W60): sketch_offset lane — SketchOffset2 op + offline tests + derisk spike"

STEP 7 — report: pytest summary line, commit hash, and the spike's {op,sketch,params}.
If anything blocked you, STOP and describe it — do not guess.
```

---

## LANE 2 — convert (`sketch_convert`)  [MED risk — model-edge seeds]

```
ROLE
You are authoring ONE file-set for the ai-sw-bridge project. You have NO
SOLIDWORKS — write Python + offline tests + a spike you will NOT run. Follow
LITERALLY; do not explore beyond named files; do not redesign.

WORKTREE (already created)
  Path: C:/D/wt_w60convert     Branch: feat/w60-convert
  Python: C:/Python314/python.exe   env: PYTHONPATH=src

HARD RULES
  - Create/modify ONLY:
      src/ai_sw_bridge/spec/sketch_editing/convert.py
      tests/spec/test_sketch_edit_convert.py
      spikes/v0_2x/spike_sketch_convert.py
  - NEVER touch: __init__.py, _base.py, cli/sketch_edit.py, pyproject.toml,
    spikes/v0_2x/_sketch_edit_fixtures.py
  - Success = sketch-SEGMENT-COUNT increase, never a True return.
  - No "Co-Authored-By" lines.

STEP 1 — read: src/ai_sw_bridge/spec/sketch_editing/_base.py,
  tests/spec/test_sketch_edit_base.py, and src/ai_sw_bridge/features/hem.py
  lines ~37-38 and ~155-180 (the durable edge-ref pattern).

STEP 2 — write src/ai_sw_bridge/spec/sketch_editing/convert.py EXACTLY:
----------------------------------------------------------------------
"""sketch_convert — Convert Entities (project model edges onto the sketch) (W60)."""
from __future__ import annotations
from typing import Any
from ._base import SketchEditOp, SketchEditError, clear_selection
from ...selection._edge_ref import DurableEdgeRef
from ...selection.live import resolve_edge_ref, select_entity

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["refs"],
    "properties": {
        "refs": {"type": "array", "items": {"type": "object"}, "minItems": 1},
        "chain": {"type": "boolean"},
        "inner_loops": {"type": "boolean"},
    },
}

def _validate(params: dict) -> None:
    if not params.get("refs"):
        raise SketchEditError("sketch_convert: refs must be a non-empty list")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    for j, ref_data in enumerate(params["refs"]):
        try:
            ref = DurableEdgeRef.from_dict(ref_data)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"invalid edge_ref[{j}]: {exc}"}
        res = resolve_edge_ref(doc, ref)
        edge = getattr(res, "entity", None)
        if edge is None:
            return {"ok": False, "error": f"ref[{j}] did not resolve ({getattr(res, 'note', '')})"}
        if not select_entity(edge, append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select ref[{j}]"}
    ret = doc.SketchManager.SketchUseEdge3(
        bool(params.get("chain", False)),
        bool(params.get("inner_loops", False)),
    )
    return {"ok": bool(ret), "raw_return": ret}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (convert adds >=1)"

OP = SketchEditOp(op="sketch_convert", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
----------------------------------------------------------------------

STEP 3 — write tests/spec/test_sketch_edit_convert.py. In each test,
monkeypatch the two seams on YOUR module's namespace:
    import ai_sw_bridge.spec.sketch_editing.convert as convert
    monkeypatch.setattr(convert, "resolve_edge_ref", fake_resolve)
    monkeypatch.setattr(convert, "select_entity", fake_select)
where fake_resolve returns an object with a .entity attribute. Tests (minimum):
  - _validate accepts {"refs":[{}]} ; raises on refs==[]
  - _apply resolves+selects each ref, calls SketchUseEdge3(chain, inner_loops),
    returns ok
  - _apply returns {"ok": False, ...} when res.entity is None (fail closed)
  - _verify(0,1,{}) -> (True, ...) ; _verify(1,1,{}) -> (False, ...)
Note: DurableEdgeRef.from_dict({}) may need minimal valid keys — check
features/hem.py / selection/_edge_ref.py for the dict shape; or monkeypatch
DurableEdgeRef.from_dict too if simpler.

STEP 4 — write spikes/v0_2x/spike_sketch_convert.py from the §5 SPIKE HARNESS
convert variant:
  sketch, edge = fx.build_box_top_sketch(doc)
  params = {"refs": [fx.capture_edge_ref(doc, edge)]}
  apply_sketch_edit(doc, sketch, "sketch_convert", params)
  Expect +1 segment. Classify clean-return-but-segment_delta==0 as NO_OP (exit 2).
DO NOT run this file.

STEP 5 — run until green:
  cd "C:/D/wt_w60convert" && PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_convert.py -q
  PYTHONPATH=src C:/Python314/python.exe -c "from ai_sw_bridge.spec.sketch_editing.convert import OP; print(OP.op)"

STEP 6 — commit:
  git add src/ai_sw_bridge/spec/sketch_editing/convert.py tests/spec/test_sketch_edit_convert.py spikes/v0_2x/spike_sketch_convert.py
  git commit -m "feat(W60): sketch_convert lane — SketchUseEdge3 op + offline tests + derisk spike"

STEP 7 — report: pytest summary, commit hash, spike {op,sketch,params}, and note
the NO_OP-vs-PASS discrimination. Blocker -> STOP and describe, do not guess.
```

---

## LANE 3 — trim (`sketch_trim`)

```
ROLE
You are authoring ONE file-set for the ai-sw-bridge project. NO SOLIDWORKS —
write Python + offline tests + a spike you will NOT run. Follow LITERALLY; do
not explore beyond named files; do not redesign.

WORKTREE (already created)
  Path: C:/D/wt_w60trim     Branch: feat/w60-trim
  Python: C:/Python314/python.exe   env: PYTHONPATH=src

HARD RULES
  - Create/modify ONLY:
      src/ai_sw_bridge/spec/sketch_editing/trim.py
      tests/spec/test_sketch_edit_trim.py
      spikes/v0_2x/spike_sketch_trim.py
  - NEVER touch: __init__.py, _base.py, cli/sketch_edit.py, pyproject.toml,
    spikes/v0_2x/_sketch_edit_fixtures.py
  - Success = sketch-SEGMENT-COUNT change, never a True return.
  - No "Co-Authored-By" lines.

STEP 1 — read: src/ai_sw_bridge/spec/sketch_editing/_base.py,
  tests/spec/test_sketch_edit_base.py.

STEP 2 — write src/ai_sw_bridge/spec/sketch_editing/trim.py EXACTLY:
----------------------------------------------------------------------
"""sketch_trim — Trim Entities on the active sketch (W60)."""
from __future__ import annotations
from typing import Any
from ._base import SketchEditOp, SketchEditError, mm_to_m

# swSketchTrimChoice_e: 0 Closest, 1 Corner, 2 TwoEntities, 3 EntityPoint,
#                       4 Entities, 5 Outside, 6 Inside
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x_mm", "y_mm"],
    "properties": {
        "option": {"type": "integer", "minimum": 0, "maximum": 6},
        "x_mm": {"type": "number"},
        "y_mm": {"type": "number"},
        "z_mm": {"type": "number"},
    },
}

def _validate(params: dict) -> None:
    opt = params.get("option", 0)
    if isinstance(opt, bool) or not isinstance(opt, int) or opt < 0 or opt > 6:
        raise SketchEditError("sketch_trim: option must be an integer 0..6 (swSketchTrimChoice_e)")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    ret = doc.SketchManager.SketchTrim(
        int(params.get("option", 0)),
        mm_to_m(params["x_mm"]),
        mm_to_m(params["y_mm"]),
        mm_to_m(params.get("z_mm", 0.0)),
    )
    return {"ok": bool(ret), "raw_return": ret}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after != before, f"segments {before}->{after} (trim changes count)"

OP = SketchEditOp(op="sketch_trim", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
----------------------------------------------------------------------

STEP 3 — write tests/spec/test_sketch_edit_trim.py. Fake doc with a fake
SketchManager whose .SketchTrim(option, x, y, z) records args and returns True.
Tests (minimum):
  - _validate accepts {"x_mm":0,"y_mm":12.5} (default option 0) and option 0..6
  - _validate raises on option == -1, option == 7, option == True
  - _apply passes int option and METRE-converted pick point (y_mm 12.5 -> 0.0125)
  - _apply returns {"ok": False, ...} when SketchTrim returns False
  - _verify(2,1,{}) -> (True, ...) ; _verify(2,3,{}) -> (True, ...) ;
    _verify(2,2,{}) -> (False, ...)

STEP 4 — write spikes/v0_2x/spike_sketch_trim.py from the §5 SPIKE HARNESS trim
variant:
  sketch, n0, pick = fx.build_overhang_lines_sketch(doc)
  params = {"option": 0, "x_mm": pick[0]*1000, "y_mm": pick[1]*1000}
  apply_sketch_edit(doc, sketch, "sketch_trim", params)
  PASS iff res["ok"] and segments_after != segments_before and survives reopen.
  Classify clean-return-but-segment_delta==0 as NO_OP (exit 2).
DO NOT run this file.

STEP 5 — run until green:
  cd "C:/D/wt_w60trim" && PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_trim.py -q
  PYTHONPATH=src C:/Python314/python.exe -c "from ai_sw_bridge.spec.sketch_editing.trim import OP; print(OP.op)"

STEP 6 — commit:
  git add src/ai_sw_bridge/spec/sketch_editing/trim.py tests/spec/test_sketch_edit_trim.py spikes/v0_2x/spike_sketch_trim.py
  git commit -m "feat(W60): sketch_trim lane — SketchTrim op + offline tests + derisk spike"

STEP 7 — report: pytest summary, commit hash, spike {op,sketch,params}, expected
count-change direction (note op contract is !=). Blocker -> STOP and describe.
```

---

## LANE 4 — pattern (`sketch_pattern`)

```
ROLE
You are authoring ONE file-set for the ai-sw-bridge project. NO SOLIDWORKS —
write Python + offline tests + a spike you will NOT run. Follow LITERALLY; do
not explore beyond named files; do not redesign.

WORKTREE (already created)
  Path: C:/D/wt_w60pattern     Branch: feat/w60-pattern
  Python: C:/Python314/python.exe   env: PYTHONPATH=src

HARD RULES
  - Create/modify ONLY:
      src/ai_sw_bridge/spec/sketch_editing/pattern.py
      tests/spec/test_sketch_edit_pattern.py
      spikes/v0_2x/spike_sketch_pattern.py
  - NEVER touch: __init__.py, _base.py, cli/sketch_edit.py, pyproject.toml,
    spikes/v0_2x/_sketch_edit_fixtures.py
  - Success = sketch-SEGMENT-COUNT increase, never a True return.
  - No "Co-Authored-By" lines.

STEP 1 — read: src/ai_sw_bridge/spec/sketch_editing/_base.py,
  tests/spec/test_sketch_edit_base.py.

STEP 2 — write src/ai_sw_bridge/spec/sketch_editing/pattern.py EXACTLY:
----------------------------------------------------------------------
"""sketch_pattern — Linear Sketch Step-and-Repeat on the active sketch (W60)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m, deg_to_rad,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "num_x", "spacing_x_mm"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "num_x": {"type": "integer", "minimum": 1},
        "num_y": {"type": "integer", "minimum": 1},
        "spacing_x_mm": {"type": "number"},
        "spacing_y_mm": {"type": "number"},
        "angle_x_deg": {"type": "number"},
        "angle_y_deg": {"type": "number"},
        "delete_instances": {"type": "string"},
        "x_spacing_dim": {"type": "boolean"},
        "y_spacing_dim": {"type": "boolean"},
        "angle_dim": {"type": "boolean"},
        "num_x_dim": {"type": "boolean"},
        "num_y_dim": {"type": "boolean"},
    },
}

def _validate(params: dict) -> None:
    if not params.get("entities"):
        raise SketchEditError("sketch_pattern: entities must be a non-empty list")
    if int(params.get("num_x", 1)) * int(params.get("num_y", 1)) < 2:
        raise SketchEditError("sketch_pattern: num_x*num_y must be >= 2 (1x1 is a no-op)")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ret = doc.SketchManager.CreateLinearSketchStepAndRepeat(
        int(params["num_x"]),
        int(params.get("num_y", 1)),
        mm_to_m(params["spacing_x_mm"]),
        mm_to_m(params.get("spacing_y_mm", 0.0)),
        deg_to_rad(params.get("angle_x_deg", 0.0)),
        deg_to_rad(params.get("angle_y_deg", 90.0)),
        str(params.get("delete_instances", "")),
        bool(params.get("x_spacing_dim", False)),
        bool(params.get("y_spacing_dim", False)),
        bool(params.get("angle_dim", False)),
        bool(params.get("num_x_dim", False)),
        bool(params.get("num_y_dim", False)),
    )
    return {"ok": bool(ret), "raw_return": ret}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (pattern multiplies seeds)"

OP = SketchEditOp(op="sketch_pattern", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
----------------------------------------------------------------------

STEP 3 — write tests/spec/test_sketch_edit_pattern.py. Fake doc with a fake
SketchManager whose .CreateLinearSketchStepAndRepeat(*args) records args and
appends fake segments; fake sketch/segments as in test_sketch_edit_base.py.
Tests (minimum):
  - _validate accepts {"entities":[0],"num_x":3,"spacing_x_mm":20}
  - _validate raises on entities==[] and on num_x*num_y < 2 (e.g. num_x 1, num_y 1)
  - _apply selects seed indices and calls CreateLinearSketchStepAndRepeat with:
      arg0 int num_x, arg2 == 0.020 (spacing METRES), arg5 == radians(90) default,
      arg6 str, args 7..11 bool — verify ORDER and TYPES
  - _apply returns {"ok": False, ...} on out-of-range / unselectable seed
  - _verify(1,3,{}) -> (True, ...) ; _verify(1,1,{}) -> (False, ...)

STEP 4 — write spikes/v0_2x/spike_sketch_pattern.py from the §5 SPIKE HARNESS
skeleton:
  sketch, n0 = fx.build_circle_sketch(doc)
  params = {"entities": [0], "num_x": 3, "num_y": 1, "spacing_x_mm": 20}
  apply_sketch_edit(doc, sketch, "sketch_pattern", params)
  PASS iff res["ok"] and segments_after > segments_before (expect 1 -> 3) and
  survives reopen. NO_OP (exit 2) when call_ok and segment_delta == 0.
DO NOT run this file.

STEP 5 — run until green:
  cd "C:/D/wt_w60pattern" && PYTHONPATH=src C:/Python314/python.exe -m pytest tests/spec/test_sketch_edit_pattern.py -q
  PYTHONPATH=src C:/Python314/python.exe -c "from ai_sw_bridge.spec.sketch_editing.pattern import OP; print(OP.op)"

STEP 6 — commit:
  git add src/ai_sw_bridge/spec/sketch_editing/pattern.py tests/spec/test_sketch_edit_pattern.py spikes/v0_2x/spike_sketch_pattern.py
  git commit -m "feat(W60): sketch_pattern lane — CreateLinearSketchStepAndRepeat op + offline tests + derisk spike"

STEP 7 — report: pytest summary, commit hash, spike {op,sketch,params},
expected segments_before/after. Blocker -> STOP and describe, do not guess.
```

---

### Notes for the operator
- These four worktrees already exist (created off `feat/w60-sketchedit`). If you
  re-run a lane via a GLM session, first `git -C C:/D/wt_w60<lane> reset --hard
  feat/w60-sketchedit` to clear the Opus worker's commit, or branch a fresh
  worktree.
- The shared spike-fixture helper (`spikes/v0_2x/_sketch_edit_fixtures.py`) and
  `§5 SPIKE HARNESS` skeleton live in `docs/w60_sketch_editing_worker_prompts.md`
  — a GLM worker copies the spike skeleton from there.
- W0 (the seat holder) fires every `spike_sketch_<lane>.py` on the live seat,
  adjudicates the segment-count delta + save→reopen survival, then wires the
  `register()` line into `__init__.py` and merges.
