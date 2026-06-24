"""Offline tests for the ``sketch_circular_pattern`` lane.

Drives ``ai_sw_bridge.spec.sketch_editing.circular_pattern`` against a fake COM
seam (no pywin32, no SOLIDWORKS), mirroring ``test_sketch_edit_pattern.py``.

Pins:
- ``_validate``: happy path + reject ``num < 2`` (no-op) + reject empty entities.
- ``_apply``: selects the right seed indices (append after the first), calls
  ``CreateCircularSketchStepAndRepeat`` with METRE radius + RADIAN angles in the
  exact 9-arg order/types, and returns ``ok``.
- ``_effective_spacing_deg``: equal-spacing defaults (full circle / num,
  partial arc / (num-1)); an explicit spacing wins.
- ``_verify``: ``after > before`` gate.
"""

from __future__ import annotations

import math

import pytest

from ai_sw_bridge.spec.sketch_editing.circular_pattern import (
    OP,
    _apply,
    _effective_spacing_deg,
    _validate,
    _verify,
)
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError


# ---------------------------------------------------------------------------
# Fake COM seam
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
        return tuple(self._segments)


class _FakeSketchManager:
    def __init__(self, ret: bool = True) -> None:
        self._ret = ret
        self.repeat_args: tuple | None = None
        self.call_count = 0

    def CreateCircularSketchStepAndRepeat(self, *args) -> bool:
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
        assert OP.op == "sketch_circular_pattern"

    def test_schema_additional_properties_false(self) -> None:
        assert OP.schema["additionalProperties"] is False
        assert "entities" in OP.schema["required"]
        assert "num" in OP.schema["required"]
        assert "radius_mm" in OP.schema["required"]

    def test_callables_wired(self) -> None:
        assert OP.validate is _validate
        assert OP.apply is _apply
        assert OP.verify_effect is _verify


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy(self) -> None:
        _validate({"entities": [0], "num": 4, "radius_mm": 20})

    def test_reject_num_1_noop(self) -> None:
        with pytest.raises(SketchEditError, match="num >= 2"):
            _validate({"entities": [0], "num": 1, "radius_mm": 20})

    def test_reject_empty_entities(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'entities'"):
            _validate({"entities": [], "num": 4, "radius_mm": 20})

    def test_reject_missing_entities(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'entities'"):
            _validate({"num": 4, "radius_mm": 20})


# ---------------------------------------------------------------------------
# _effective_spacing_deg
# ---------------------------------------------------------------------------


class TestEffectiveSpacing:
    def test_full_circle_divides_by_num(self) -> None:
        # 4 instances over 360 -> 90 deg apart
        assert _effective_spacing_deg(
            {"num": 4, "arc_angle_deg": 360}
        ) == pytest.approx(90.0)

    def test_partial_arc_divides_by_num_minus_1(self) -> None:
        # 3 instances over 90 deg arc -> 45 deg apart
        assert _effective_spacing_deg({"num": 3, "arc_angle_deg": 90}) == pytest.approx(
            45.0
        )

    def test_explicit_spacing_wins(self) -> None:
        assert _effective_spacing_deg(
            {"num": 4, "arc_angle_deg": 360, "spacing_deg": 30}
        ) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_first_seed_no_append_rest_append(self) -> None:
        sk = _FakeSketch(3)
        doc = _FakeDoc(sk)
        _apply(doc, sk, {"entities": [0, 2], "num": 4, "radius_mm": 20})
        segs = sk.GetSketchSegments
        assert segs[0].select_args == (False, 0)
        assert segs[2].select_args == (True, 0)

    def test_call_args_units_order_and_types(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk)
        res = _apply(
            doc,
            sk,
            {
                "entities": [0],
                "num": 4,
                "radius_mm": 20,
                "arc_angle_deg": 360,
                "spacing_deg": 90,
                "pattern_rotate": True,
                "delete_instances": "2",
            },
        )
        args = doc.SketchManager.repeat_args
        assert doc.SketchManager.call_count == 1
        assert len(args) == 9
        assert args[0] == pytest.approx(0.020)  # ArcRadius — METRES
        assert args[1] == pytest.approx(2 * math.pi)  # ArcAngle — RADIANS (360)
        assert args[2] == 4 and isinstance(args[2], int)  # PatternNum
        assert args[3] == pytest.approx(math.pi / 2)  # PatternSpacing — RADIANS (90)
        assert args[4] is True  # PatternRotate
        assert args[5] == "2" and isinstance(args[5], str)  # DeleteInstances
        assert args[6] is False and args[7] is False and args[8] is False  # dim flags
        assert res["ok"] is True
        assert res["seeds_selected"] == 1

    def test_defaults_when_optional_omitted(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk)
        _apply(doc, sk, {"entities": [0], "num": 4, "radius_mm": 20})
        args = doc.SketchManager.repeat_args
        assert args[1] == pytest.approx(2 * math.pi)  # arc_angle default 360
        assert args[3] == pytest.approx(math.pi / 2)  # spacing default = 360/4 = 90
        assert args[4] is True  # pattern_rotate default True
        assert args[5] == ""  # delete_instances default ""

    def test_returns_not_ok_when_com_false(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk, ret=False)
        res = _apply(doc, sk, {"entities": [0], "num": 4, "radius_mm": 20})
        assert res["ok"] is False

    def test_out_of_range_seed_fails_closed(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = _apply(doc, sk, {"entities": [5], "num": 4, "radius_mm": 20})
        assert res["ok"] is False
        assert "could not select segment 5" in res["error"]
        assert doc.SketchManager.call_count == 0


# ---------------------------------------------------------------------------
# _verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = _verify(1, 4, {"entities": [0], "num": 4})
        assert ok is True
        assert "1->4" in note and "expected 4" in note

    def test_no_change_fails(self) -> None:
        ok, _ = _verify(1, 1, {"entities": [0], "num": 4})
        assert ok is False
