"""Tests for the W60 sketch-editing base scaffold (W0-owned contract).

Drives ``ai_sw_bridge.spec.sketch_editing._base`` against a fake COM seam (no
pywin32, no SOLIDWORKS). This is the contract the offset/convert/trim/pattern
lane modules are authored against, so it pins:

- The COM helpers lifted from the seat-proven W39 recipe (GetSketchSegments
  PROPERTY auto-invoke, raw Select2, open/close toggle).
- ``count_segments`` as the verify-the-EFFECT metric (segment-count delta).
- The ``SketchEditOp`` descriptor + ``register`` registry seam.
- ``validate_sketch_edit_spec`` offline validation dispatch.
- ``apply_sketch_edit`` orchestration: open -> snapshot -> dispatch ->
  snapshot -> close -> rebuild -> adjudicate, including the failure paths
  (op raises / op reports False / effect not verified) and the invariant that
  the sketch is ALWAYS closed (never left mid-edit).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec.sketch_editing import _base
from ai_sw_bridge.spec.sketch_editing._base import (
    OP_REGISTRY,
    SketchEditError,
    SketchEditOp,
    apply_sketch_edit,
    clear_selection,
    close_sketch,
    count_segments,
    deg_to_rad,
    get_segments,
    mm_to_m,
    open_sketch_for_edit,
    register,
    select_segment,
    sketch_edit_spec_schema,
    validate_sketch_edit_spec,
)


# ---------------------------------------------------------------------------
# Fake COM seam (mirrors tests/spec/test_sketch_relations conventions)
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, idx: int, *, selectable: bool = True) -> None:
        self.idx = idx
        self.selectable = selectable
        self.selected = False

    def Select2(self, append: bool, mark: int) -> bool:
        if not self.selectable:
            return False
        self.selected = True
        return True


class _FakeSketch:
    def __init__(self, n: int) -> None:
        self._segments = [_FakeSegment(i) for i in range(n)]

    @property
    def GetSketchSegments(self):
        """PROPERTY (no parens) — matches late-bound COM auto-invoke."""
        return tuple(self._segments)

    def _add_segments(self, k: int) -> None:
        base = len(self._segments)
        self._segments.extend(_FakeSegment(base + i) for i in range(k))

    def _remove_segments(self, k: int) -> None:
        del self._segments[len(self._segments) - k :]


class _FakeFeature:
    def __init__(self) -> None:
        self.selected = False

    def Select2(self, append: bool, mark: int) -> bool:
        self.selected = True
        return True


class _FakeSketchManager:
    def __init__(self) -> None:
        self.insert_calls = 0

    def InsertSketch(self, rebuild: bool) -> None:
        self.insert_calls += 1


class _FakeDoc:
    """Fake IModelDoc2 sufficient for the sketch-edit orchestrator."""

    def __init__(self, sketch: _FakeSketch | None, *, has_feature: bool = True) -> None:
        self._sketch = sketch
        self._has_feature = has_feature
        self._sm = _FakeSketchManager()
        self.clear_calls = 0
        self.rebuild_reads = 0

    def FeatureByName(self, name: str) -> Any:
        return _FakeFeature() if self._has_feature else None

    @property
    def SketchManager(self) -> _FakeSketchManager:
        return self._sm

    @property
    def GetActiveSketch2(self) -> _FakeSketch | None:
        return self._sketch

    def ClearSelection2(self, _all: bool) -> None:
        self.clear_calls += 1

    @property
    def EditRebuild3(self) -> bool:
        self.rebuild_reads += 1
        return True


# ---------------------------------------------------------------------------
# Registry isolation: snapshot + restore OP_REGISTRY around every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(OP_REGISTRY)
    OP_REGISTRY.clear()
    try:
        yield
    finally:
        OP_REGISTRY.clear()
        OP_REGISTRY.update(saved)


def _make_op(
    token: str = "sketch_fake",
    *,
    add: int = 1,
    remove: int = 0,
    apply_ok: bool = True,
    expect: str = "increase",
    raises: bool = False,
) -> SketchEditOp:
    """Build a fake op that mutates the active sketch's segment count."""

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"n": {"type": "integer", "minimum": 1}},
    }

    def _validate(params: dict) -> None:
        # Semantic check on a SCHEMA-VALID value (schema only bounds n >= 1),
        # so this exercises op.validate independently of jsonschema.
        if params.get("n", 1) > 100:
            raise SketchEditError("n must be 100 or less")

    def _apply(doc: Any, sk: Any, params: dict) -> dict:
        if raises:
            raise RuntimeError("boom inside apply")
        if add:
            sk._add_segments(add)
        if remove:
            sk._remove_segments(remove)
        return {"ok": apply_ok, "fake_diag": "applied"}

    def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
        if expect == "increase":
            return after > before, f"{before}->{after}"
        if expect == "decrease":
            return after < before, f"{before}->{after}"
        return after != before, f"{before}->{after}"

    return SketchEditOp(
        op=token,
        schema=schema,
        validate=_validate,
        apply=_apply,
        verify_effect=_verify,
    )


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------


class TestConversions:
    def test_mm_to_m(self) -> None:
        assert mm_to_m(1000) == 1.0
        assert mm_to_m(25.4) == pytest.approx(0.0254)

    def test_deg_to_rad(self) -> None:
        assert deg_to_rad(180) == pytest.approx(3.141592653589793)
        assert deg_to_rad(0) == 0.0


# ---------------------------------------------------------------------------
# COM helpers
# ---------------------------------------------------------------------------


class TestComHelpers:
    def test_count_segments_reads_property(self) -> None:
        sk = _FakeSketch(3)
        assert count_segments(sk) == 3
        sk._add_segments(2)
        assert count_segments(sk) == 5  # live re-read

    def test_get_segments_returns_list(self) -> None:
        sk = _FakeSketch(2)
        segs = get_segments(sk)
        assert isinstance(segs, list)
        assert len(segs) == 2

    def test_get_segments_empty_on_none(self) -> None:
        class _Empty:
            GetSketchSegments = None

        assert get_segments(_Empty()) == []

    def test_open_sketch_for_edit_returns_active(self) -> None:
        sk = _FakeSketch(1)
        doc = _FakeDoc(sk)
        out = open_sketch_for_edit(doc, "Sketch1")
        assert out is sk
        assert doc.SketchManager.insert_calls == 1  # entered edit mode

    def test_open_sketch_missing_feature_raises(self) -> None:
        doc = _FakeDoc(None, has_feature=False)
        with pytest.raises(SketchEditError, match="not found"):
            open_sketch_for_edit(doc, "Nope")

    def test_open_sketch_no_active_raises(self) -> None:
        doc = _FakeDoc(None, has_feature=True)
        with pytest.raises(SketchEditError, match="could not open"):
            open_sketch_for_edit(doc, "Sketch1")

    def test_close_sketch_toggles(self) -> None:
        doc = _FakeDoc(_FakeSketch(1))
        close_sketch(doc)
        assert doc.SketchManager.insert_calls == 1

    def test_select_segment_raw_first(self) -> None:
        seg = _FakeSegment(0)
        assert select_segment(seg) is True
        assert seg.selected is True

    def test_select_segment_failure_returns_false(self) -> None:
        seg = _FakeSegment(0, selectable=False)
        assert select_segment(seg) is False

    def test_clear_selection_swallows(self) -> None:
        doc = _FakeDoc(_FakeSketch(1))
        clear_selection(doc)
        assert doc.clear_calls == 1


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_adds(self) -> None:
        op = _make_op("sketch_x")
        register(op)
        assert OP_REGISTRY["sketch_x"] is op

    def test_register_duplicate_raises(self) -> None:
        register(_make_op("sketch_dup"))
        with pytest.raises(SketchEditError, match="already registered"):
            register(_make_op("sketch_dup"))

    def test_register_rejects_non_op(self) -> None:
        with pytest.raises(SketchEditError, match="SketchEditOp"):
            register({"op": "nope"})  # type: ignore[arg-type]

    def test_register_rejects_empty_token(self) -> None:
        with pytest.raises(SketchEditError, match="non-empty"):
            register(_make_op(""))

    def test_spec_schema_reflects_registry(self) -> None:
        register(_make_op("sketch_a"))
        register(_make_op("sketch_b"))
        schema = sketch_edit_spec_schema()
        assert schema["properties"]["op"]["enum"] == ["sketch_a", "sketch_b"]
        assert schema["required"] == ["op", "sketch"]


# ---------------------------------------------------------------------------
# Offline spec validation
# ---------------------------------------------------------------------------


class TestValidateSpec:
    def test_happy_path(self) -> None:
        register(_make_op("sketch_v"))
        validate_sketch_edit_spec(
            {"op": "sketch_v", "sketch": "Sketch1", "params": {"n": 2}}
        )

    def test_unknown_op_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="unknown op"):
            validate_sketch_edit_spec({"op": "ghost", "sketch": "Sketch1"})

    def test_missing_sketch_rejected(self) -> None:
        register(_make_op("sketch_v"))
        with pytest.raises(SketchEditError, match="sketch"):
            validate_sketch_edit_spec({"op": "sketch_v", "sketch": ""})

    def test_params_schema_failure(self) -> None:
        register(_make_op("sketch_v"))
        with pytest.raises(SketchEditError, match="schema validation"):
            validate_sketch_edit_spec(
                {"op": "sketch_v", "sketch": "S", "params": {"bogus": 1}}
            )

    def test_op_semantic_validate_runs(self) -> None:
        # n=200 passes the schema (>= 1) but op.validate rejects it.
        register(_make_op("sketch_v"))
        with pytest.raises(SketchEditError, match="100 or less"):
            validate_sketch_edit_spec(
                {"op": "sketch_v", "sketch": "S", "params": {"n": 200}}
            )

    def test_non_dict_spec_rejected(self) -> None:
        with pytest.raises(SketchEditError, match="must be an object"):
            validate_sketch_edit_spec("not a dict")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TestApplySketchEdit:
    def test_happy_increase(self) -> None:
        register(_make_op("sketch_inc", add=3, expect="increase"))
        doc = _FakeDoc(_FakeSketch(2))
        res = apply_sketch_edit(doc, "Sketch1", "sketch_inc", {"n": 1})
        assert res["ok"] is True
        assert res["segments_before"] == 2
        assert res["segments_after"] == 5
        assert res["segment_delta"] == 3
        assert res["effect_verified"] is True
        assert res["call_ok"] is True
        assert res["fake_diag"] == "applied"  # op diagnostics merged
        # sketch entered AND exited edit mode (open + close), rebuilt once
        assert doc.SketchManager.insert_calls == 2
        assert doc.rebuild_reads == 1

    def test_decrease_effect(self) -> None:
        register(_make_op("sketch_trim", add=0, remove=1, expect="decrease"))
        doc = _FakeDoc(_FakeSketch(4))
        res = apply_sketch_edit(doc, "Sketch1", "sketch_trim", {})
        assert res["segment_delta"] == -1
        assert res["effect_verified"] is True
        assert res["ok"] is True

    def test_effect_not_verified_fails_ok(self) -> None:
        # op claims success but adds nothing -> effect gate fails -> ok False
        register(_make_op("sketch_noop", add=0, expect="increase"))
        doc = _FakeDoc(_FakeSketch(2))
        res = apply_sketch_edit(doc, "Sketch1", "sketch_noop", {})
        assert res["call_ok"] is True
        assert res["effect_verified"] is False
        assert res["ok"] is False

    def test_call_failure_fails_ok(self) -> None:
        # op adds segments (effect ok) but reports COM failure -> ok False
        register(_make_op("sketch_callfail", add=2, apply_ok=False))
        doc = _FakeDoc(_FakeSketch(1))
        res = apply_sketch_edit(doc, "Sketch1", "sketch_callfail", {})
        assert res["effect_verified"] is True
        assert res["call_ok"] is False
        assert res["ok"] is False

    def test_unknown_op_raises(self) -> None:
        doc = _FakeDoc(_FakeSketch(1))
        with pytest.raises(SketchEditError, match="unknown op"):
            apply_sketch_edit(doc, "Sketch1", "ghost", {})

    def test_sketch_not_found_raises(self) -> None:
        register(_make_op("sketch_inc"))
        doc = _FakeDoc(None, has_feature=False)
        with pytest.raises(SketchEditError, match="not found"):
            apply_sketch_edit(doc, "Nope", "sketch_inc", {})

    def test_apply_raises_is_wrapped_and_sketch_closed(self) -> None:
        register(_make_op("sketch_boom", raises=True))
        doc = _FakeDoc(_FakeSketch(2))
        with pytest.raises(SketchEditError, match="raised"):
            apply_sketch_edit(doc, "Sketch1", "sketch_boom", {})
        # invariant: sketch was still closed (open + close = 2 toggles)
        assert doc.SketchManager.insert_calls == 2

    def test_defensive_revalidate_runs(self) -> None:
        # orchestrator re-runs op.validate; bad params raise before COM work
        register(_make_op("sketch_inc"))
        doc = _FakeDoc(_FakeSketch(2))
        with pytest.raises(SketchEditError, match="100 or less"):
            apply_sketch_edit(doc, "Sketch1", "sketch_inc", {"n": 200})
        assert doc.SketchManager.insert_calls == 0  # never entered edit mode


def test_module_exports_present() -> None:
    # the public surface op authors rely on
    for name in (
        "open_sketch_for_edit",
        "close_sketch",
        "get_segments",
        "count_segments",
        "select_segment",
        "clear_selection",
        "mm_to_m",
        "deg_to_rad",
        "SketchEditOp",
        "register",
        "apply_sketch_edit",
        "validate_sketch_edit_spec",
    ):
        assert hasattr(_base, name)
