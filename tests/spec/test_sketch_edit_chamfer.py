"""Offline tests for the W61 ``sketch_chamfer`` lane (no pywin32, no SOLIDWORKS).

Drives ``ai_sw_bridge.spec.sketch_editing.chamfer`` against a fake COM seam
modelled on ``tests/spec/test_sketch_edit_offset.py``. Pins:

- ``_validate`` — happy path + each rejection (zero dist1, wrong entity count,
  angle-mode chamfer_type == 0).
- ``_apply`` — selects the two seed indices (append=False first, True second),
  calls ``SketchManager.CreateChamfer`` with an int chamfer_type and the
  METRE-converted distances (``d2`` defaults to ``d1`` when omitted), and
  returns ``ok`` from the raw COM verdict; selection failure rides back as
  ``ok=False``.
- ``_verify`` — ``after > before`` True; ``==`` / ``<`` False (verify-the-EFFECT).
- The exported ``OP`` descriptor shape (token + schema additionalProperties).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import chamfer as chamfer_mod
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError, SketchEditOp


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors test_sketch_edit_base / test_sketch_edit_offset idiom)
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
        self.chamfer_calls: list[tuple] = []
        self._sketch: _FakeSketch | None = None

    def bind_sketch(self, sk: _FakeSketch) -> None:
        # Lets the fake record the segment-count delta the orchestrator sees.
        self._sketch = sk

    def CreateChamfer(self, *args) -> Any:
        self.chamfer_calls.append(args)
        # Model the side effect: a chamfer inserts a new segment.
        if self._ret is not None and self._sketch is not None:
            next_idx = len(self._sketch._segments)
            self._sketch._segments.append(_FakeSegment(next_idx))
        return self._ret


class _FakeDoc:
    def __init__(self, sketch: _FakeSketch, *, ret: Any = True) -> None:
        self._sketch = sketch
        self._sm = _FakeSketchManager(ret=ret)
        self._sm.bind_sketch(sketch)
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
    def test_happy_path_default_type(self) -> None:
        chamfer_mod._validate({"dist1_mm": 5, "entities": [0, 1]})

    def test_happy_path_explicit_type2(self) -> None:
        chamfer_mod._validate(
            {"dist1_mm": 3.0, "dist2_mm": 2.0, "entities": [0, 1], "chamfer_type": 2}
        )

    def test_zero_dist1_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="dist1_mm"):
            chamfer_mod._validate({"dist1_mm": 0, "entities": [0, 1]})

    def test_missing_dist1_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="dist1_mm"):
            chamfer_mod._validate({"entities": [0, 1]})

    def test_entities_wrong_length_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="exactly 2 entities"):
            chamfer_mod._validate({"dist1_mm": 5, "entities": [0]})

    def test_entities_empty_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="exactly 2 entities"):
            chamfer_mod._validate({"dist1_mm": 5, "entities": []})

    def test_angle_mode_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="chamfer_type"):
            chamfer_mod._validate(
                {"dist1_mm": 5, "entities": [0, 1], "chamfer_type": 0}
            )


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_selects_right_indices_with_append_progression(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        chamfer_mod._apply(doc, sk, {"dist1_mm": 5, "entities": [0, 1]})
        segs = sk._segments
        # first entity: append=False; second: append=True; mark always 0
        assert segs[0].select_calls == [(False, 0)]
        assert segs[1].select_calls == [(True, 0)]
        # untouched seeds never selected
        assert segs[2].select_calls == []
        assert segs[3].select_calls == []
        assert doc.clear_calls == 1  # cleared selection first

    def test_create_chamfer_called_with_metre_conversion_and_int_type(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        res = chamfer_mod._apply(
            doc,
            sk,
            {"dist1_mm": 5, "dist2_mm": 5, "entities": [0, 1], "chamfer_type": 1},
        )
        assert len(doc.SketchManager.chamfer_calls) == 1
        ctype, d1, d2 = doc.SketchManager.chamfer_calls[0]
        assert ctype == 1 and type(ctype) is int
        assert d1 == pytest.approx(0.005)
        assert d2 == pytest.approx(0.005)
        assert res["ok"] is True

    def test_dist2_defaults_to_dist1_when_omitted(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        chamfer_mod._apply(doc, sk, {"dist1_mm": 7, "entities": [0, 1]})
        ctype, d1, d2 = doc.SketchManager.chamfer_calls[0]
        assert d1 == pytest.approx(0.007)
        assert d2 == pytest.approx(0.007)  # defaults to dist1

    def test_default_chamfer_type_is_1(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk)
        chamfer_mod._apply(doc, sk, {"dist1_mm": 5, "entities": [0, 1]})
        ctype, _, _ = doc.SketchManager.chamfer_calls[0]
        assert ctype == 1

    def test_returns_ok_false_on_com_none(self) -> None:
        sk = _FakeSketch(4)
        doc = _FakeDoc(sk, ret=None)
        res = chamfer_mod._apply(doc, sk, {"dist1_mm": 5, "entities": [0, 1]})
        assert res["ok"] is False
        # raw_return is a string of the None return
        assert res["raw_return"] == "None"

    def test_out_of_range_index_fails_without_calling_chamfer(self) -> None:
        sk = _FakeSketch(2)
        doc = _FakeDoc(sk)
        res = chamfer_mod._apply(doc, sk, {"dist1_mm": 5, "entities": [0, 5]})
        assert res["ok"] is False
        assert (
            "out of range" in res["error"]
            or "could not select segment 5" in res["error"]
        )
        assert doc.SketchManager.chamfer_calls == []  # never fired

    def test_unselectable_segment_fails_without_calling_chamfer(self) -> None:
        sk = _FakeSketch(2)
        sk._segments[0].selectable = False
        doc = _FakeDoc(sk)
        res = chamfer_mod._apply(doc, sk, {"dist1_mm": 5, "entities": [0, 1]})
        assert res["ok"] is False
        assert "could not select segment 0" in res["error"]
        assert doc.SketchManager.chamfer_calls == []


# ---------------------------------------------------------------------------
# _verify (the verify-the-EFFECT gate)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = chamfer_mod._verify(4, 5, {})
        assert ok is True
        assert "4->5" in note

    def test_equal_fails(self) -> None:
        ok, _ = chamfer_mod._verify(4, 4, {})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = chamfer_mod._verify(4, 3, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert chamfer_mod.OP.op == "sketch_chamfer"
        assert isinstance(chamfer_mod.OP, SketchEditOp)

    def test_schema_closed(self) -> None:
        assert chamfer_mod.OP.schema["additionalProperties"] is False
        assert chamfer_mod.OP.schema["required"] == ["dist1_mm", "entities"]
        assert chamfer_mod.OP.schema["properties"]["entities"]["minItems"] == 2
        assert chamfer_mod.OP.schema["properties"]["entities"]["maxItems"] == 2

    def test_wired_callables(self) -> None:
        assert chamfer_mod.OP.validate is chamfer_mod._validate
        assert chamfer_mod.OP.apply is chamfer_mod._apply
        assert chamfer_mod.OP.verify_effect is chamfer_mod._verify
