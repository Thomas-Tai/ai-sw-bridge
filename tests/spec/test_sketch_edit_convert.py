"""W60 offline tests — ``sketch_convert`` lane (Convert Entities, SketchUseEdge3).

Drives ``spec.sketch_editing.convert`` against a fake COM seam (no pywin32, no
SOLIDWORKS). The durable-selection seam (``resolve_edge_ref`` / ``select_entity``)
is patched ON THE LANE MODULE'S NAMESPACE (mirrors tests/features/test_hem.py),
never on ``selection.live``.

Pins:
  * ``_validate`` — happy path + empty/missing ``refs`` rejection.
  * ``_apply`` — every ref is resolved + selected, ``SketchUseEdge3`` called
    with the chain/inner_loops flags; fail-closed when ``res.entity`` is None.
  * ``_verify`` — direction (``after > before``) + boundary (no delta -> False).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import convert
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError


# ---------------------------------------------------------------------------
# Minimal valid serialized DurableEdgeRef dict (resolve_edge_ref is patched)
# ---------------------------------------------------------------------------


def _edge_ref(length: float = 0.04) -> dict:
    return {
        "start": [0.0, 0.0, 0.0],
        "end": [length, 0.0, 0.0],
        "length": length,
        "role_hint": "edge",
    }


# ---------------------------------------------------------------------------
# Fake COM seam
# ---------------------------------------------------------------------------


class _FakeSketchManager:
    def __init__(self, ret: Any = True) -> None:
        self.ret = ret
        self.calls: list[tuple] = []

    def SketchUseEdge3(self, chain: bool, inner_loops: bool) -> Any:
        self.calls.append((chain, inner_loops))
        return self.ret


class _FakeDoc:
    def __init__(self, ret: Any = True) -> None:
        self._sm = _FakeSketchManager(ret)
        self.cleared = False

    @property
    def SketchManager(self) -> _FakeSketchManager:
        return self._sm

    def ClearSelection2(self, _all: bool) -> None:
        self.cleared = True


_sentinel = object()


def _wire(monkeypatch, *, entity=_sentinel, select_ok: bool = True):
    """Patch resolve_edge_ref / select_entity on the convert module namespace."""
    if entity is _sentinel:
        entity = object()
    monkeypatch.setattr(
        convert,
        "resolve_edge_ref",
        lambda doc, ref: type("R", (), {"entity": entity, "note": "test"})(),
    )
    selected: list[tuple] = []

    def fake_select(e, *, append=False, mark=0):
        selected.append((e, append, mark))
        return select_ok

    monkeypatch.setattr(convert, "select_entity", fake_select)
    return selected


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_single_ref(self) -> None:
        convert._validate({"refs": [_edge_ref()]})

    def test_happy_empty_dict_ref(self) -> None:
        # _validate only checks refs is truthy; from_dict validation is _apply's job
        convert._validate({"refs": [{}]})

    def test_empty_refs_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            convert._validate({"refs": []})

    def test_missing_refs_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            convert._validate({})


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_single_ref_resolved_selected_converted(self, monkeypatch) -> None:
        selected = _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [_edge_ref()]})
        assert res["ok"] is True
        assert res["raw_return"] is True
        assert doc.cleared is True
        assert len(selected) == 1
        assert selected[0][1] is False  # append=False for first seed
        assert doc.SketchManager.calls == [(False, False)]

    def test_multi_ref_append_advances(self, monkeypatch) -> None:
        selected = _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        res = convert._apply(
            doc,
            object(),
            {"refs": [_edge_ref(), _edge_ref(0.06), _edge_ref(0.08)]},
        )
        assert res["ok"] is True
        appends = [a for (_e, a, _m) in selected]
        assert appends == [False, True, True]

    def test_chain_and_inner_loops_flags_forwarded(self, monkeypatch) -> None:
        _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        convert._apply(
            doc,
            object(),
            {"refs": [_edge_ref()], "chain": True, "inner_loops": True},
        )
        assert doc.SketchManager.calls == [(True, True)]

    def test_com_return_false_propagates_ok(self, monkeypatch) -> None:
        _wire(monkeypatch)
        doc = _FakeDoc(ret=False)
        res = convert._apply(doc, object(), {"refs": [_edge_ref()]})
        assert res["ok"] is False
        assert res["raw_return"] is False

    def test_unresolved_ref_fails_closed(self, monkeypatch) -> None:
        _wire(monkeypatch, entity=None)
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [_edge_ref()]})
        assert res["ok"] is False
        assert "did not resolve" in res["error"]
        assert doc.SketchManager.calls == []

    def test_invalid_ref_dict_fails_closed(self, monkeypatch) -> None:
        _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [{"start": [0, 0, 0]}]})
        assert res["ok"] is False
        assert "invalid edge_ref[0]" in res["error"]
        assert doc.SketchManager.calls == []

    def test_select_failure_fails_closed(self, monkeypatch) -> None:
        _wire(monkeypatch, select_ok=False)
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [_edge_ref()]})
        assert res["ok"] is False
        assert "could not select ref[0]" in res["error"]
        assert doc.SketchManager.calls == []


# ---------------------------------------------------------------------------
# _verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = convert._verify(0, 1, {})
        assert ok is True
        assert "0->1" in note

    def test_no_delta_fails(self) -> None:
        ok, note = convert._verify(1, 1, {})
        assert ok is False
        assert "1->1" in note

    def test_decrease_fails(self) -> None:
        ok, _note = convert._verify(5, 4, {})
        assert ok is False


# ---------------------------------------------------------------------------
# OP descriptor wiring
# ---------------------------------------------------------------------------


class TestOpDescriptor:
    def test_op_token(self) -> None:
        assert convert.OP.op == "sketch_convert"

    def test_schema_rejects_additional_props(self) -> None:
        assert convert.OP.schema["additionalProperties"] is False
        assert convert.OP.schema["properties"]["refs"]["minItems"] == 1

    def test_op_callables_wired(self) -> None:
        assert convert.OP.validate is convert._validate
        assert convert.OP.apply is convert._apply
        assert convert.OP.verify_effect is convert._verify
