"""Offline tests for the W60 ``sketch_offset`` lane (no pywin32, no SOLIDWORKS).

Drives ``ai_sw_bridge.spec.sketch_editing.offset`` against a fake COM seam
modelled on ``tests/spec/test_sketch_edit_base.py``. Pins:

- ``_validate`` — happy path + each rejection (zero distance, empty entities).
- ``_apply`` — selects the right seed indices (append=False for the first,
  True after), calls ``SketchManager.SketchOffset2`` with the METRE-converted
  offset and the correct flag TYPES (bool flags bool, cap_ends/make_construction
  Int32), and returns ``ok`` from the raw COM verdict; selection failure rides
  back as ``ok=False``.
- ``_verify`` — ``after > before`` True; ``==`` / ``<`` False (verify-the-EFFECT).
- The exported ``OP`` descriptor shape (token + schema additionalProperties).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import offset as offset_mod
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError, SketchEditOp


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors test_sketch_edit_base conventions)
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


class _FakeSketchManager:
    def __init__(self, ret: Any = True) -> None:
        self._ret = ret
        self.offset_calls: list[tuple] = []

    def SketchOffset2(self, *args) -> Any:
        self.offset_calls.append(args)
        return self._ret


class _FakeDoc:
    def __init__(self, sketch: _FakeSketch, *, ret: Any = True) -> None:
        self._sketch = sketch
        self._sm = _FakeSketchManager(ret=ret)
        self.clear_calls = 0

    @property
    def SketchManager(self) -> _FakeSketchManager:
        return self._sm

    def ClearSelection2(self, _all: bool) -> None:
        self.clear_calls += 1


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_path(self) -> None:
        offset_mod._validate({"distance_mm": 5.0, "entities": [0, 1, 2, 3]})

    def test_negative_distance_is_valid(self) -> None:
        # A negative offset (inward) is legal; only zero is rejected.
        offset_mod._validate({"distance_mm": -3.0, "entities": [0]})

    def test_zero_distance_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-zero"):
            offset_mod._validate({"distance_mm": 0.0, "entities": [0]})

    def test_missing_distance_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-zero"):
            offset_mod._validate({"entities": [0]})

    def test_empty_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="at least one seed"):
            offset_mod._validate({"distance_mm": 5.0, "entities": []})

    def test_missing_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="at least one seed"):
            offset_mod._validate({"distance_mm": 5.0})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_selects_right_indices_with_append_progression(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        offset_mod._apply(doc, sk, {"distance_mm": 5.0, "entities": [0, 2, 3]})
        segs = sk._segments
        # first seed: append=False; subsequent: append=True; mark always 0
        assert segs[0].select_calls == [(False, 0)]
        assert segs[2].select_calls == [(True, 0)]
        assert segs[3].select_calls == [(True, 0)]
        # untouched seed never selected
        assert segs[1].select_calls == []
        assert doc.clear_calls == 1  # cleared selection first

    def test_offset_called_with_metre_conversion_and_flag_types(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        res = offset_mod._apply(
            doc,
            sk,
            {
                "distance_mm": 5.0,
                "entities": [0, 1, 2, 3],
                "both_directions": True,
                "chain": True,
                "cap_ends": 2,
                "make_construction": True,
                "add_dimensions": False,
            },
        )
        assert len(doc.SketchManager.offset_calls) == 1
        args = doc.SketchManager.offset_calls[0]
        offset, both, chain, cap, mkconst, adddim = args
        # distance: 5 mm -> 0.005 m
        assert offset == pytest.approx(0.005)
        # bool flags are real bools
        assert both is True and isinstance(both, bool)
        assert chain is True and isinstance(chain, bool)
        assert adddim is False and isinstance(adddim, bool)
        # cap_ends + make_construction are Int32 (int), NOT bool
        assert cap == 2 and type(cap) is int
        assert mkconst == 1 and type(mkconst) is int
        assert res["ok"] is True
        assert res["raw_return"] is True

    def test_defaults_applied_for_omitted_flags(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        offset_mod._apply(doc, sk, {"distance_mm": 3.0, "entities": [0]})
        offset, both, chain, cap, mkconst, adddim = doc.SketchManager.offset_calls[0]
        assert offset == pytest.approx(0.003)
        assert both is False and chain is False and adddim is False
        assert cap == 0 and mkconst == 0

    def test_make_construction_false_is_int_zero(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        offset_mod._apply(
            doc, sk, {"distance_mm": 1.0, "entities": [0], "make_construction": False}
        )
        _, _, _, _, mkconst, _ = doc.SketchManager.offset_calls[0]
        assert mkconst == 0 and type(mkconst) is int

    def test_returns_ok_false_on_com_false(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk, ret=False)
        res = offset_mod._apply(doc, sk, {"distance_mm": 5.0, "entities": [0]})
        assert res["ok"] is False
        assert res["raw_return"] is False

    def test_out_of_range_index_fails_without_calling_offset(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = offset_mod._apply(doc, sk, {"distance_mm": 5.0, "entities": [5]})
        assert res["ok"] is False
        assert "could not select segment 5" in res["error"]
        assert doc.SketchManager.offset_calls == []  # never fired

    def test_unselectable_segment_fails_without_calling_offset(self) -> None:
        sk = _FakeSketch(2)
        sk._segments[0].selectable = False
        doc = _FakeDoc(sk)
        res = offset_mod._apply(doc, sk, {"distance_mm": 5.0, "entities": [0]})
        assert res["ok"] is False
        assert "could not select segment 0" in res["error"]
        assert doc.SketchManager.offset_calls == []


# ---------------------------------------------------------------------------
# _verify (the verify-the-EFFECT gate)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = offset_mod._verify(4, 8, {})
        assert ok is True
        assert "4->8" in note

    def test_equal_fails(self) -> None:
        ok, _ = offset_mod._verify(4, 4, {})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = offset_mod._verify(4, 3, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert offset_mod.OP.op == "sketch_offset"
        assert isinstance(offset_mod.OP, SketchEditOp)

    def test_schema_closed(self) -> None:
        assert offset_mod.OP.schema["additionalProperties"] is False
        assert offset_mod.OP.schema["required"] == ["distance_mm", "entities"]
        assert offset_mod.OP.schema["properties"]["entities"]["minItems"] == 1

    def test_wired_callables(self) -> None:
        assert offset_mod.OP.validate is offset_mod._validate
        assert offset_mod.OP.apply is offset_mod._apply
        assert offset_mod.OP.verify_effect is offset_mod._verify
