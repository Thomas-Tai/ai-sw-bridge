"""Offline tests for the W61 ``sketch_fillet`` lane (no pywin32, no SOLIDWORKS).

Drives ``ai_sw_bridge.spec.sketch_editing.fillet`` against a fake COM seam
modelled on ``tests/spec/test_sketch_edit_base.py`` / ``test_sketch_edit_offset.py``.
Pins:

- ``_validate`` — happy path + each rejection (zero radius, wrong entity count).
- ``_apply`` — selects [0,1] with the right append progression, calls
  ``SketchManager.CreateFillet`` with the METRE-converted radius and an int
  ``constrained_corners``; returns ``ok`` from the raw COM verdict (None -> False);
  selection failure rides back as ``ok=False``.
- ``_verify`` — ``after > before`` True; ``==`` False (verify-the-EFFECT).
- The exported ``OP`` descriptor shape (token + schema additionalProperties).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import fillet as fillet_mod
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

    def _add_segments(self, k: int) -> None:
        base = len(self._segments)
        self._segments.extend(_FakeSegment(base + i) for i in range(k))


class _FakeArcSegment:
    """Truthy stand-in for the arc handle CreateFillet returns on success."""


class _FakeSketchManager:
    def __init__(self, sketch: _FakeSketch, *, ret: Any = "USE_DEFAULT") -> None:
        self._sketch = sketch
        self._ret = ret
        self.fillet_calls: list[tuple] = []

    def CreateFillet(self, *args) -> Any:
        self.fillet_calls.append(args)
        if self._ret == "USE_DEFAULT":
            self._sketch._add_segments(1)
            return _FakeArcSegment()
        if self._ret is None:
            return None
        self._sketch._add_segments(1)
        return self._ret


class _FakeDoc:
    def __init__(self, sketch: _FakeSketch, *, fillet_ret: Any = "USE_DEFAULT") -> None:
        self._sketch = sketch
        self._sm = _FakeSketchManager(sketch, ret=fillet_ret)
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
        fillet_mod._validate({"radius_mm": 5, "entities": [0, 1]})

    def test_zero_radius_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="radius_mm must be > 0"):
            fillet_mod._validate({"radius_mm": 0, "entities": [0, 1]})

    def test_negative_radius_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="radius_mm must be > 0"):
            fillet_mod._validate({"radius_mm": -1, "entities": [0, 1]})

    def test_missing_radius_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="radius_mm must be > 0"):
            fillet_mod._validate({"entities": [0, 1]})

    def test_too_few_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="exactly 2 entities"):
            fillet_mod._validate({"radius_mm": 5, "entities": [0]})

    def test_too_many_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="exactly 2 entities"):
            fillet_mod._validate({"radius_mm": 5, "entities": [0, 1, 2]})

    def test_missing_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="exactly 2 entities"):
            fillet_mod._validate({"radius_mm": 5})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_selects_entities_with_append_progression(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        fillet_mod._apply(doc, sk, {"radius_mm": 5, "entities": [0, 1]})
        segs = sk._segments
        # first entity: append=False; second: append=True; mark always 0
        assert segs[0].select_calls == [(False, 0)]
        assert segs[1].select_calls == [(True, 0)]
        # untouched segments never selected
        assert segs[2].select_calls == []
        assert segs[3].select_calls == []
        assert doc.clear_calls == 1

    def test_fillet_called_with_metre_conversion_and_int_corners(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        res = fillet_mod._apply(
            doc,
            sk,
            {"radius_mm": 5, "entities": [0, 1], "constrained_corners": 1},
        )
        assert len(doc.SketchManager.fillet_calls) == 1
        args = doc.SketchManager.fillet_calls[0]
        assert len(args) == 2
        radius, cc = args
        assert radius == pytest.approx(0.005)
        assert cc == 1 and type(cc) is int
        assert res["ok"] is True

    def test_defaults_constrained_corners_to_zero(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        fillet_mod._apply(doc, sk, {"radius_mm": 3, "entities": [0, 1]})
        _, cc = doc.SketchManager.fillet_calls[0]
        assert cc == 0 and type(cc) is int

    def test_returns_ok_false_on_none_return(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk, fillet_ret=None)
        res = fillet_mod._apply(doc, sk, {"radius_mm": 5, "entities": [0, 1]})
        assert res["ok"] is False

    def test_out_of_range_index_fails_without_calling_fillet(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = fillet_mod._apply(doc, sk, {"radius_mm": 5, "entities": [0, 5]})
        assert res["ok"] is False
        assert "out of range" in res["error"] or "could not select" in res["error"]
        assert doc.SketchManager.fillet_calls == []

    def test_unselectable_segment_fails_without_calling_fillet(self) -> None:
        sk = _FakeSketch(2)
        sk._segments[1].selectable = False
        doc = _FakeDoc(sk)
        res = fillet_mod._apply(doc, sk, {"radius_mm": 5, "entities": [0, 1]})
        assert res["ok"] is False
        assert "could not select segment 1" in res["error"]
        assert doc.SketchManager.fillet_calls == []


# ---------------------------------------------------------------------------
# _verify (the verify-the-EFFECT gate)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = fillet_mod._verify(4, 5, {})
        assert ok is True
        assert "4->5" in note

    def test_equal_fails(self) -> None:
        ok, _ = fillet_mod._verify(4, 4, {})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = fillet_mod._verify(4, 3, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert fillet_mod.OP.op == "sketch_fillet"
        assert isinstance(fillet_mod.OP, SketchEditOp)

    def test_schema_closed(self) -> None:
        assert fillet_mod.OP.schema["additionalProperties"] is False
        assert fillet_mod.OP.schema["required"] == ["radius_mm", "entities"]
        assert fillet_mod.OP.schema["properties"]["entities"]["minItems"] == 2
        assert fillet_mod.OP.schema["properties"]["entities"]["maxItems"] == 2

    def test_wired_callables(self) -> None:
        assert fillet_mod.OP.validate is fillet_mod._validate
        assert fillet_mod.OP.apply is fillet_mod._apply
        assert fillet_mod.OP.verify_effect is fillet_mod._verify
