"""Offline tests for the W61 ``sketch_move_copy`` lane (no pywin32, no SOLIDWORKS).

Drives ``ai_sw_bridge.spec.sketch_editing.move_copy`` against a fake COM seam
modelled on ``tests/spec/test_sketch_edit_base.py`` / ``test_sketch_edit_offset.py``.
Pins:

- ``_validate`` — happy path + each rejection (empty entities, wrong dest_mm shape).
- ``_apply`` — selects the right indices (append=False for the first, True after),
  calls ``doc.Extension.MoveOrCopy`` with Copy=True, an int NumCopies, a bool
  KeepRelations, and METRE-converted base/dest coords; returns ``ok=True`` on a
  clean invocation (MoveOrCopy is void, so there is no COM verdict to mirror).
- ``_apply`` — returns ``ok=False`` on an out-of-range entity index WITHOUT
  calling MoveOrCopy.
- ``_verify`` — ``after > before`` is the gate (True when the count grows,
  False on a zero/negative delta).
- The exported ``OP`` descriptor shape (token + schema additionalProperties).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import move_copy as mc_mod
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError, SketchEditOp


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors test_sketch_edit_base / test_sketch_edit_offset)
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, idx: int, *, selectable: bool = True) -> None:
        self.idx = idx
        self.selectable = selectable
        self.select_calls: list[tuple[bool, int]] = []

    def Select2(self, append: bool, mark: int) -> bool:
        if not self.selectable:
            return False
        self.select_calls.append((append, mark))
        return True


class _FakeSketch:
    def __init__(self, n: int) -> None:
        self._segments = [_FakeSegment(i) for i in range(n)]

    @property
    def GetSketchSegments(self):
        return tuple(self._segments)


class _FakeExtension:
    """Records MoveOrCopy args and appends copies of each selected segment."""

    def __init__(self, sketch: _FakeSketch) -> None:
        self._sketch = sketch
        self.move_or_copy_calls: list[tuple] = []

    def MoveOrCopy(self, *args) -> None:
        # Record first, then mutate — so the orchestrator's post-apply snapshot
        # sees the grown segment list. args: (Copy, NumCopies, KeepRelations,
        # bx,by,bz, dx,dy,dz).
        self.move_or_copy_calls.append(args)
        copy_flag, num_copies = args[0], args[1]
        if copy_flag and num_copies:
            # count how many segments are currently "selected"
            selected = sum(1 for s in self._sketch._segments if s.select_calls)
            # each copy adds `selected` new fake segments (num_copies times)
            existing = len(self._sketch._segments)
            for k in range(num_copies * selected):
                self._sketch._segments.append(_FakeSegment(existing + k))


class _FakeDoc:
    def __init__(self, sketch: _FakeSketch) -> None:
        self._sketch = sketch
        self._ext = _FakeExtension(sketch)
        self.clear_calls = 0

    @property
    def Extension(self) -> _FakeExtension:
        return self._ext

    def ClearSelection2(self, _all: bool) -> None:
        self.clear_calls += 1


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_path(self) -> None:
        mc_mod._validate({"entities": [0, 1, 2, 3], "dest_mm": [30, 0, 0]})

    def test_single_entity_happy(self) -> None:
        mc_mod._validate({"entities": [2], "dest_mm": [0, 0, 0]})

    def test_empty_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            mc_mod._validate({"entities": [], "dest_mm": [10, 0, 0]})

    def test_missing_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            mc_mod._validate({"dest_mm": [10, 0, 0]})

    def test_dest_mm_wrong_length_rejected(self) -> None:
        with pytest.raises(SketchEditError, match=r"dest_mm"):
            mc_mod._validate({"entities": [0], "dest_mm": [10, 0]})

    def test_dest_mm_too_long_rejected(self) -> None:
        with pytest.raises(SketchEditError, match=r"dest_mm"):
            mc_mod._validate({"entities": [0], "dest_mm": [10, 0, 0, 0]})

    def test_missing_dest_mm_rejected(self) -> None:
        with pytest.raises(SketchEditError, match=r"dest_mm"):
            mc_mod._validate({"entities": [0]})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_selects_right_indices_with_append_progression(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        mc_mod._apply(doc, sk, {"entities": [0, 1, 2, 3], "dest_mm": [30, 0, 0]})
        segs = sk._segments
        # first seed: append=False; subsequent: append=True; mark always 0
        assert segs[0].select_calls == [(False, 0)]
        assert segs[1].select_calls == [(True, 0)]
        assert segs[2].select_calls == [(True, 0)]
        assert segs[3].select_calls == [(True, 0)]
        assert doc.clear_calls == 1

    def test_move_or_copy_called_with_metres_and_correct_types(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        res = mc_mod._apply(
            doc,
            sk,
            {
                "entities": [0, 1, 2, 3],
                "num_copies": 1,
                "dest_mm": [30, 0, 0],
                "keep_relations": True,
            },
        )
        assert len(doc.Extension.move_or_copy_calls) == 1
        args = doc.Extension.move_or_copy_calls[0]
        # (Copy, NumCopies, KeepRelations, bx, by, bz, dx, dy, dz)
        assert len(args) == 9
        copy_flag, num_copies, keep_rel = args[0], args[1], args[2]
        assert copy_flag is True and isinstance(copy_flag, bool)
        assert num_copies == 1 and type(num_copies) is int
        assert keep_rel is True and isinstance(keep_rel, bool)
        # base_mm defaults to [0,0,0] -> 0.0 metres
        assert args[3] == 0.0 and args[4] == 0.0 and args[5] == 0.0
        # dest_mm[0] = 30 mm -> 0.030 m
        assert args[6] == pytest.approx(0.030)
        assert args[7] == pytest.approx(0.0)
        assert args[8] == pytest.approx(0.0)
        assert res["ok"] is True
        assert res["raw_return"] == "void"

    def test_defaults_num_copies_1_keep_relations_false(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        mc_mod._apply(doc, sk, {"entities": [0], "dest_mm": [10, 20, 30]})
        args = doc.Extension.move_or_copy_calls[0]
        _copy, num_copies, keep_rel = args[0], args[1], args[2]
        assert num_copies == 1 and keep_rel is False

    def test_base_mm_override_is_metre_converted(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        mc_mod._apply(
            doc,
            sk,
            {"entities": [0], "dest_mm": [100, 0, 0], "base_mm": [1000, 0, 0]},
        )
        args = doc.Extension.move_or_copy_calls[0]
        # base 1000 mm -> 1.0 m
        assert args[3] == pytest.approx(1.0)
        # dest 100 mm -> 0.1 m
        assert args[6] == pytest.approx(0.1)

    def test_out_of_range_index_fails_without_calling_move_or_copy(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = mc_mod._apply(doc, sk, {"entities": [5], "dest_mm": [10, 0, 0]})
        assert res["ok"] is False
        assert "entity index 5 out of range" in res["error"]
        assert doc.Extension.move_or_copy_calls == []

    def test_unselectable_segment_fails_closed(self) -> None:
        sk = _FakeSketch(2)
        sk._segments[0].selectable = False
        doc = _FakeDoc(sk)
        res = mc_mod._apply(doc, sk, {"entities": [0], "dest_mm": [10, 0, 0]})
        assert res["ok"] is False
        assert "could not select segment 0" in res["error"]
        assert doc.Extension.move_or_copy_calls == []

    def test_move_or_copy_returns_none_ok_still_true(self) -> None:
        # MoveOrCopy is void — even if a fake returned None implicitly, ok=True.
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = mc_mod._apply(doc, sk, {"entities": [0], "dest_mm": [1, 2, 3]})
        assert res["ok"] is True


# ---------------------------------------------------------------------------
# _verify (verify-the-EFFECT gate)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = mc_mod._verify(4, 8, {})
        assert ok is True
        assert "4->8" in note

    def test_equal_fails(self) -> None:
        ok, _ = mc_mod._verify(4, 4, {})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = mc_mod._verify(4, 2, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert mc_mod.OP.op == "sketch_move_copy"
        assert isinstance(mc_mod.OP, SketchEditOp)

    def test_schema_closed(self) -> None:
        assert mc_mod.OP.schema["additionalProperties"] is False
        assert mc_mod.OP.schema["required"] == ["entities", "dest_mm"]
        assert mc_mod.OP.schema["properties"]["entities"]["minItems"] == 1

    def test_wired_callables(self) -> None:
        assert mc_mod.OP.validate is mc_mod._validate
        assert mc_mod.OP.apply is mc_mod._apply
        assert mc_mod.OP.verify_effect is mc_mod._verify
