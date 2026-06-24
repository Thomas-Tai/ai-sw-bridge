"""Offline tests for the W61 ``sketch_mirror`` lane (no pywin32, no SOLIDWORKS).

Drives ``ai_sw_bridge.spec.sketch_editing.mirror`` against a fake COM seam
modelled on ``tests/spec/test_sketch_edit_base.py`` / ``test_sketch_edit_offset.py``.
Pins:

- ``_validate`` — happy path + each rejection (empty entities, centerline in
  entities, missing centerline).
- ``_apply`` — selects entities then centerline (centerline appended LAST, all
  with mark 0), calls ``doc.SketchMirror()`` (NOT SketchManager), and returns
  ``ok``; selection failure or out-of-range index rides back as ``ok=False``.
- ``_verify`` — ``after > before`` True; ``==`` / ``<`` False (verify-the-EFFECT).
- The exported ``OP`` descriptor shape (token + schema additionalProperties).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import mirror as mirror_mod
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError, SketchEditOp


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors test_sketch_edit_offset conventions)
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


class _FakeDoc:
    """Fake IModelDoc2 — SketchMirror is a method on doc, NOT SketchManager."""

    def __init__(self, sketch: _FakeSketch) -> None:
        self._sketch = sketch
        self.clear_calls = 0
        self.mirror_calls = 0

    def SketchMirror(self) -> None:
        self.mirror_calls += 1
        self._sketch._add_segments(
            len(
                [
                    s
                    for s in self._sketch._segments
                    if s.select_calls and s.idx != self._centerline_idx
                ]
            )
        )

    _centerline_idx: int = -1

    def ClearSelection2(self, _all: bool) -> None:
        self.clear_calls += 1


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_path(self) -> None:
        mirror_mod._validate({"entities": [1, 2], "centerline": 0})

    def test_empty_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            mirror_mod._validate({"entities": [], "centerline": 0})

    def test_missing_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            mirror_mod._validate({"centerline": 0})

    def test_centerline_in_entities_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="must not be among"):
            mirror_mod._validate({"entities": [0, 1], "centerline": 0})

    def test_missing_centerline_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="centerline"):
            mirror_mod._validate({"entities": [0, 1]})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def _doc_with_tracking(self, sk: _FakeSketch, cl_idx: int) -> _FakeDoc:
        """Build a _FakeDoc whose SketchMirror adds len(entities) segments
        (mirrors what the real API does: duplicates selected entities)."""
        doc = _FakeDoc(sk)
        doc._centerline_idx = cl_idx
        return doc

    def test_selects_entities_then_centerline_with_correct_append(self) -> None:
        sk = _FakeSketch(3)  # [centerline(0), line(1), line(2)]
        doc = self._doc_with_tracking(sk, cl_idx=0)
        mirror_mod._apply(doc, sk, {"entities": [1, 2], "centerline": 0})
        segs = sk._segments
        # entities selected first; first entity: append=False, rest: append=True
        assert segs[1].select_calls == [(False, 0)]
        assert segs[2].select_calls == [(True, 0)]
        # centerline appended LAST
        assert segs[0].select_calls == [(True, 0)]
        assert doc.clear_calls == 1

    def test_sketchmirror_called_on_doc(self) -> None:
        sk = _FakeSketch(3)
        doc = self._doc_with_tracking(sk, cl_idx=0)
        res = mirror_mod._apply(doc, sk, {"entities": [1, 2], "centerline": 0})
        assert doc.mirror_calls == 1
        assert res["ok"] is True
        assert res["raw_return"] == "void"

    def test_out_of_range_entity_index_fails(self) -> None:
        sk = _FakeSketch(3)
        doc = self._doc_with_tracking(sk, cl_idx=0)
        res = mirror_mod._apply(doc, sk, {"entities": [9], "centerline": 0})
        assert res["ok"] is False
        assert "9" in res["error"]
        assert doc.mirror_calls == 0

    def test_out_of_range_centerline_index_fails(self) -> None:
        sk = _FakeSketch(3)
        doc = self._doc_with_tracking(sk, cl_idx=99)
        res = mirror_mod._apply(doc, sk, {"entities": [1], "centerline": 99})
        assert res["ok"] is False
        assert "99" in res["error"]
        assert doc.mirror_calls == 0

    def test_unselectable_entity_fails(self) -> None:
        sk = _FakeSketch(3)
        sk._segments[1].selectable = False
        doc = self._doc_with_tracking(sk, cl_idx=0)
        res = mirror_mod._apply(doc, sk, {"entities": [1, 2], "centerline": 0})
        assert res["ok"] is False
        assert "mirror entity 1" in res["error"]
        assert doc.mirror_calls == 0

    def test_unselectable_centerline_fails(self) -> None:
        sk = _FakeSketch(3)
        sk._segments[0].selectable = False
        doc = self._doc_with_tracking(sk, cl_idx=0)
        res = mirror_mod._apply(doc, sk, {"entities": [1, 2], "centerline": 0})
        assert res["ok"] is False
        assert "centerline" in res["error"]
        assert doc.mirror_calls == 0


# ---------------------------------------------------------------------------
# _verify (the verify-the-EFFECT gate)
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = mirror_mod._verify(3, 5, {})
        assert ok is True
        assert "3->5" in note

    def test_equal_fails(self) -> None:
        ok, _ = mirror_mod._verify(3, 3, {})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _ = mirror_mod._verify(3, 2, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert mirror_mod.OP.op == "sketch_mirror"
        assert isinstance(mirror_mod.OP, SketchEditOp)

    def test_schema_closed(self) -> None:
        assert mirror_mod.OP.schema["additionalProperties"] is False
        assert mirror_mod.OP.schema["required"] == ["entities", "centerline"]
        assert mirror_mod.OP.schema["properties"]["entities"]["minItems"] == 1

    def test_wired_callables(self) -> None:
        assert mirror_mod.OP.validate is mirror_mod._validate
        assert mirror_mod.OP.apply is mirror_mod._apply
        assert mirror_mod.OP.verify_effect is mirror_mod._verify
