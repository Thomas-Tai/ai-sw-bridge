"""Offline tests for the W60 ``sketch_pattern`` lane.

Drives ``ai_sw_bridge.spec.sketch_editing.pattern`` against a fake COM seam
(no pywin32, no SOLIDWORKS), mirroring the conventions in
``tests/spec/test_sketch_edit_base.py`` and ``test_sketch_relations.py``.

Pins:
- ``_validate``: happy path + reject a 1x1 (no-op) pattern + reject empty
  ``entities``.
- ``_apply``: selects the right seed indices (raw Select2, append after the
  first), calls ``CreateLinearSketchStepAndRepeat`` with METRE spacing +
  RADIAN angles in the exact 12-arg order/types, and returns ``ok``.
- ``_verify``: ``after > before`` is the gate (True when the count grows,
  False on a zero/negative delta).
"""

from __future__ import annotations

import math

import pytest

from ai_sw_bridge.spec.sketch_editing.pattern import OP, _apply, _validate, _verify
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors test_sketch_edit_base conventions)
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, idx: int, *, selectable: bool = True) -> None:
        self.idx = idx
        self.selectable = selectable
        self.selected = False
        self.select_args: tuple[bool, int] | None = None

    def Select2(self, append: bool, mark: int) -> bool:
        if not self.selectable:
            return False
        self.selected = True
        self.select_args = (append, mark)
        return True


class _FakeSketch:
    def __init__(self, n: int) -> None:
        self._segments = [_FakeSegment(i) for i in range(n)]

    @property
    def GetSketchSegments(self):
        """PROPERTY (no parens) — matches late-bound COM auto-invoke."""
        return tuple(self._segments)


class _FakeSketchManager:
    def __init__(self, ret: bool = True) -> None:
        self._ret = ret
        self.repeat_args: tuple | None = None
        self.call_count = 0

    def CreateLinearSketchStepAndRepeat(self, *args) -> bool:
        self.call_count += 1
        self.repeat_args = args
        return self._ret


class _FakeDoc:
    def __init__(self, sketch: _FakeSketch, *, ret: bool = True) -> None:
        self._sketch = sketch
        self._sm = _FakeSketchManager(ret=ret)
        self.clear_calls = 0

    @property
    def SketchManager(self) -> _FakeSketchManager:
        return self._sm

    def ClearSelection2(self, _all: bool) -> None:
        self.clear_calls += 1


# ---------------------------------------------------------------------------
# Descriptor
# ---------------------------------------------------------------------------


class TestDescriptor:
    def test_op_token(self) -> None:
        assert OP.op == "sketch_pattern"

    def test_schema_additional_properties_false(self) -> None:
        assert OP.schema["additionalProperties"] is False
        assert "entities" in OP.schema["required"]
        assert "num_x" in OP.schema["required"]
        assert "spacing_x_mm" in OP.schema["required"]

    def test_callables_wired(self) -> None:
        assert OP.validate is _validate
        assert OP.apply is _apply
        assert OP.verify_effect is _verify


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_3x1(self) -> None:
        _validate({"entities": [0], "num_x": 3, "spacing_x_mm": 20})

    def test_happy_2x2(self) -> None:
        _validate({"entities": [0, 1], "num_x": 2, "num_y": 2, "spacing_x_mm": 10})

    def test_reject_1x1_noop(self) -> None:
        with pytest.raises(SketchEditError, match=r"num_x \* num_y >= 2"):
            _validate({"entities": [0], "num_x": 1, "num_y": 1, "spacing_x_mm": 20})

    def test_reject_empty_entities(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'entities'"):
            _validate({"entities": [], "num_x": 3, "spacing_x_mm": 20})

    def test_reject_missing_entities(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'entities'"):
            _validate({"num_x": 3, "spacing_x_mm": 20})

    def test_num_y_default_keeps_1x1_a_noop(self) -> None:
        # num_x=1 with num_y defaulting to 1 -> 1*1 < 2 -> rejected.
        with pytest.raises(SketchEditError, match=r"num_x \* num_y >= 2"):
            _validate({"entities": [0], "num_x": 1, "spacing_x_mm": 20})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_clears_then_selects_correct_seeds(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        _apply(doc, sk, {"entities": [1, 3], "num_x": 3, "spacing_x_mm": 20})
        assert doc.clear_calls == 1
        segs = sk.GetSketchSegments
        # seeds 1 and 3 selected; 0 and 2 untouched
        assert segs[1].selected is True
        assert segs[3].selected is True
        assert segs[0].selected is False
        assert segs[2].selected is False

    def test_first_seed_no_append_rest_append(self) -> None:
        sk = _FakeSketch(3)
        doc = _FakeDoc(sk)
        _apply(doc, sk, {"entities": [0, 2], "num_x": 2, "spacing_x_mm": 10})
        segs = sk.GetSketchSegments
        assert segs[0].select_args == (False, 0)  # first: append=False
        assert segs[2].select_args == (True, 0)  # subsequent: append=True

    def test_call_args_units_order_and_types(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk)
        res = _apply(
            doc,
            sk,
            {
                "entities": [0],
                "num_x": 3,
                "num_y": 2,
                "spacing_x_mm": 20,
                "spacing_y_mm": 15,
                "angle_x_deg": 0,
                "angle_y_deg": 90,
                "delete_instances": "1",
                "x_spacing_dim": True,
                "y_spacing_dim": False,
                "angle_dim": True,
                "num_x_dim": False,
                "num_y_dim": True,
            },
        )
        args = doc.SketchManager.repeat_args
        assert doc.SketchManager.call_count == 1
        assert len(args) == 12
        # NumX, NumY — ints
        assert args[0] == 3 and isinstance(args[0], int)
        assert args[1] == 2 and isinstance(args[1], int)
        # SpacingX, SpacingY — METRES
        assert args[2] == pytest.approx(0.020)
        assert args[3] == pytest.approx(0.015)
        # AngleX, AngleY — RADIANS
        assert args[4] == pytest.approx(0.0)
        assert args[5] == pytest.approx(math.pi / 2)
        # DeleteInstances — str
        assert args[6] == "1" and isinstance(args[6], str)
        # five *_dim flags — bools, in order
        assert args[7] is True  # x_spacing_dim
        assert args[8] is False  # y_spacing_dim
        assert args[9] is True  # angle_dim
        assert args[10] is False  # num_x_dim
        assert args[11] is True  # num_y_dim
        assert res["ok"] is True
        assert res["raw_return"] is True
        assert res["seeds_selected"] == 1

    def test_defaults_when_optional_omitted(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk)
        _apply(doc, sk, {"entities": [0], "num_x": 3, "spacing_x_mm": 20})
        args = doc.SketchManager.repeat_args
        assert args[1] == 1  # num_y default 1
        assert args[3] == pytest.approx(0.0)  # spacing_y default 0 mm
        assert args[4] == pytest.approx(0.0)  # angle_x default 0 deg
        assert args[5] == pytest.approx(math.pi / 2)  # angle_y default 90 deg
        assert args[6] == ""  # delete_instances default ""
        assert args[7:] == (False, False, False, False, False)  # five dims default

    def test_returns_not_ok_when_com_false(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk, ret=False)
        res = _apply(doc, sk, {"entities": [0], "num_x": 3, "spacing_x_mm": 20})
        assert res["ok"] is False
        assert res["raw_return"] is False

    def test_out_of_range_seed_fails_closed(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = _apply(doc, sk, {"entities": [5], "num_x": 3, "spacing_x_mm": 20})
        assert res["ok"] is False
        assert "could not select segment 5" in res["error"]
        # never fired the pattern call
        assert doc.SketchManager.call_count == 0

    def test_unselectable_seed_fails_closed(self) -> None:
        sk = _FakeSketch(2)
        sk._segments[0].selectable = False
        doc = _FakeDoc(sk)
        res = _apply(doc, sk, {"entities": [0], "num_x": 3, "spacing_x_mm": 20})
        assert res["ok"] is False
        assert doc.SketchManager.call_count == 0


# ---------------------------------------------------------------------------
# _verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = _verify(1, 3, {"entities": [0], "num_x": 3, "num_y": 1})
        assert ok is True
        assert "1->3" in note

    def test_no_change_fails(self) -> None:
        ok, _ = _verify(1, 1, {"entities": [0], "num_x": 3, "num_y": 1})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = _verify(3, 1, {"entities": [0], "num_x": 3, "num_y": 1})
        assert ok is False

    def test_note_reports_expected_count(self) -> None:
        _, note = _verify(1, 3, {"entities": [0], "num_x": 3, "num_y": 1})
        # 1 + 1*(3*1-1) = 3
        assert "expected 3" in note
