"""W60 offline tests — ``sketch_convert`` lane (Convert Entities).

Drives ``spec.sketch_editing.convert`` against a fake COM seam (no pywin32, no
SOLIDWORKS). The durable-selection seam (``resolve_edge_ref`` / ``select_entity``)
is patched ON THE LANE MODULE'S NAMESPACE per the registry lane protocol
(mirrors ``tests/features/test_hem.py``), never on ``selection.live``.

Pins:
  * ``_validate`` — happy path + empty/missing ``refs`` rejection.
  * ``_apply`` — every ref is resolved + selected (append flag advances after the
    first seed), ``SketchUseEdge3`` is called with the unit-free chain/inner_loops
    flags, returns ``ok`` from the COM return; AND fail-closed when a ref's
    ``res.entity`` is None, when the ref dict won't parse, or when selection fails.
  * ``_verify`` — direction (``after > before``) + boundary (no delta -> False).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import convert
from ai_sw_bridge.spec.sketch_editing._base import SketchEditError


# ---------------------------------------------------------------------------
# A minimal valid serialized DurableEdgeRef (no persist token needed —
# resolve_edge_ref is patched in these tests).
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


def _wire(monkeypatch, *, entity: object = None, select_ok: bool = True):
    """Patch resolve/select seams on the convert lane module.

    ``entity=False`` is the explicit "unresolved" sentinel (res.entity is None).
    Returns the list that records each (edge, append) select call.
    """
    ent = object() if entity is None else entity
    if entity is False:
        ent = None
    monkeypatch.setattr(
        convert, "resolve_edge_ref",
        lambda doc, ref: type("R", (), {"entity": ent, "note": "test"})(),
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

    def test_happy_multi_ref(self) -> None:
        convert._validate({"refs": [_edge_ref(), _edge_ref(0.06)]})

    def test_empty_refs_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'refs'"):
            convert._validate({"refs": []})

    def test_missing_refs_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'refs'"):
            convert._validate({})

    def test_non_list_refs_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty 'refs'"):
            convert._validate({"refs": "nope"})


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
        # cleared selection, selected exactly one edge with append=False
        assert doc.cleared is True
        assert len(selected) == 1
        assert selected[0][1] is False  # append for the first seed
        # SketchUseEdge3 called once with default flags
        assert doc.SketchManager.calls == [(False, False)]

    def test_multi_ref_append_advances(self, monkeypatch) -> None:
        selected = _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        res = convert._apply(
            doc, object(), {"refs": [_edge_ref(), _edge_ref(0.06), _edge_ref(0.08)]}
        )
        assert res["ok"] is True
        # first seed append=False, subsequent seeds append=True
        appends = [a for (_e, a, _m) in selected]
        assert appends == [False, True, True]

    def test_chain_and_inner_loops_flags_forwarded(self, monkeypatch) -> None:
        _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        convert._apply(
            doc, object(),
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
        _wire(monkeypatch, entity=False)  # res.entity is None
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [_edge_ref()]})
        assert res["ok"] is False
        assert "did not resolve" in res["error"]
        # never reached the Convert call
        assert doc.SketchManager.calls == []

    def test_invalid_ref_dict_fails_closed(self, monkeypatch) -> None:
        _wire(monkeypatch)
        doc = _FakeDoc(ret=True)
        # missing 'end'/'length' -> DurableEdgeRef.from_dict raises -> fail-closed
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

    def test_second_ref_unresolved_aborts(self, monkeypatch) -> None:
        # First resolves, second is None -> abort before the Convert call.
        ent = object()
        seq = [ent, None]
        state = {"n": 0}

        def fake_resolve(doc, ref):
            e = seq[min(state["n"], len(seq) - 1)]
            state["n"] += 1
            return type("R", (), {"entity": e, "note": "test"})()

        monkeypatch.setattr(convert, "resolve_edge_ref", fake_resolve)
        monkeypatch.setattr(
            convert, "select_entity", lambda e, *, append=False, mark=0: True
        )
        doc = _FakeDoc(ret=True)
        res = convert._apply(doc, object(), {"refs": [_edge_ref(), _edge_ref(0.06)]})
        assert res["ok"] is False
        assert "ref[1] did not resolve" in res["error"]
        assert doc.SketchManager.calls == []


# ---------------------------------------------------------------------------
# _verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_increase_passes(self) -> None:
        ok, note = convert._verify(4, 5, {"refs": [_edge_ref()]})
        assert ok is True
        assert "4->5" in note

    def test_no_delta_fails(self) -> None:
        ok, note = convert._verify(4, 4, {"refs": [_edge_ref()]})
        assert ok is False

    def test_decrease_fails(self) -> None:
        ok, _note = convert._verify(5, 4, {"refs": [_edge_ref()]})
        assert ok is False

    def test_note_reports_ref_count(self) -> None:
        _ok, note = convert._verify(4, 6, {"refs": [_edge_ref(), _edge_ref(0.06)]})
        assert "convert 2 edge(s)" in note


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
