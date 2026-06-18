"""W66 offline tests — ``offset_surface`` handler.

Pins the surface-CREATE gate (ΔSheetBodies ≥ +1 ∧ ΔArea > 0), the recipe
pin (mm→m conversion, reverse flag), the validation surface, and the
UNFIRED registry gate.

Gate doctrine (W66 §0.1): a surface feature creates a zero-thickness
sheet body, so ΔVol is meaningless. The witness is the surface-body
count + area. A Void return without a new body, or with zero area,
is the surface form of the W42/W65 ghost.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import offset_surface
from ai_sw_bridge.features.offset_surface import create_offset_surface


# --- fake COM objects -------------------------------------------------------


class _FakeDoc:
    def __init__(self, *, raise_insert=False):
        self.cleared = False
        self.rebuilt = False
        self._raise_insert = raise_insert
        self.insert_calls: list[tuple] = []

    def ClearSelection2(self, flag):
        self.cleared = True

    def InsertOffsetSurface(self, thickness, reverse):
        if self._raise_insert:
            raise RuntimeError("InsertOffsetSurface boom")
        self.insert_calls.append((thickness, reverse))

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# --- helpers ----------------------------------------------------------------


_FACE_SENTINEL = object()


def _wire(
    monkeypatch,
    *,
    select_ok=True,
    count_before=0,
    count_after=1,
    area_before=0.0,
    area_after=1200.0,
    select_calls=None,
):
    """Patch select_entity + surface metrics on the lane module."""

    def fake_select(entity, append=False, mark=0):
        if select_calls is not None:
            select_calls.append((entity, append, mark))
        return select_ok

    monkeypatch.setattr(offset_surface, "select_entity", fake_select)

    call_state = {"count": 0, "area": 0}

    def fake_count(doc):
        call_state["count"] += 1
        if call_state["count"] <= 1:
            return count_before
        return count_after

    def fake_area(doc):
        call_state["area"] += 1
        if call_state["area"] <= 1:
            return area_before
        return area_after

    monkeypatch.setattr(offset_surface, "_sheet_body_count", fake_count)
    monkeypatch.setattr(offset_surface, "_total_sheet_area_mm2", fake_area)


# --- effect gate (surface-CREATE: ΔSheetBodies ≥ +1 ∧ ΔArea > 0) ----------


class TestEffectGate:
    def test_success_with_new_body_and_area(self, monkeypatch):
        _wire(monkeypatch, count_before=0, count_after=1,
              area_before=0.0, area_after=1200.0)
        doc = _FakeDoc()
        ok, note = create_offset_surface(
            doc, {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is True
        assert note is None
        assert doc.cleared is True
        assert doc.rebuilt is True

    def test_success_with_multiple_new_bodies(self, monkeypatch):
        _wire(monkeypatch, count_before=0, count_after=3,
              area_before=0.0, area_after=3600.0)
        ok, _ = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is True


# --- verify gate (ghost trap) -----------------------------------------------


class TestVerifyGate:
    def test_no_new_body_is_ghost(self, monkeypatch):
        """InsertOffsetSurface returns void but no new sheet body → ghost."""
        _wire(monkeypatch, count_before=0, count_after=0)
        ok, note = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is False
        assert "did not materialize" in note

    def test_new_body_zero_area_is_ghost(self, monkeypatch):
        """Body count increases but area stays zero → ghost (W42 surface form)."""
        _wire(monkeypatch, count_before=0, count_after=1,
              area_before=0.0, area_after=0.0)
        ok, note = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is False
        assert "did not materialize" in note

    def test_insert_raises_fails_closed(self, monkeypatch):
        """InsertOffsetSurface raises → handler catches and returns False."""
        _wire(monkeypatch)
        doc = _FakeDoc(raise_insert=True)
        ok, note = create_offset_surface(
            doc, {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is False
        assert "raised" in note


# --- recipe pin (mm→m conversion, reverse flag) -----------------------------


class TestRecipePin:
    def test_offset_converted_mm_to_m(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_offset_surface(
            doc, {"offset_mm": 5.0, "reverse": False},
            {"face_entity": _FACE_SENTINEL},
        )
        assert ok
        assert len(doc.insert_calls) == 1
        thickness, reverse = doc.insert_calls[0]
        assert thickness == pytest.approx(0.005)
        assert reverse is False

    def test_reverse_flag_passed(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_offset_surface(
            doc, {"offset_mm": 10.0, "reverse": True},
            {"face_entity": _FACE_SENTINEL},
        )
        assert ok
        thickness, reverse = doc.insert_calls[0]
        assert thickness == pytest.approx(0.010)
        assert reverse is True

    def test_default_offset_is_5mm(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_offset_surface(
            doc, {}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok
        thickness, reverse = doc.insert_calls[0]
        assert thickness == pytest.approx(0.005)
        assert reverse is False


# --- validation (fail-closed) -----------------------------------------------


class TestValidation:
    def test_missing_face_entity_rejected(self):
        ok, err = create_offset_surface(_FakeDoc(), {"offset_mm": 5.0}, {})
        assert ok is False and "face_entity" in err

    def test_none_face_entity_rejected(self):
        ok, err = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": None}
        )
        assert ok is False and "face_entity" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_offset_surface(
            _FakeDoc(), "not_a_dict", {"face_entity": _FACE_SENTINEL}
        )
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_offset_surface(_FakeDoc(), {}, "not_a_dict")
        assert ok is False and "target must be a dict" in err

    def test_non_numeric_offset_rejected(self):
        ok, err = create_offset_surface(
            _FakeDoc(), {"offset_mm": "not_a_number"},
            {"face_entity": _FACE_SENTINEL},
        )
        assert ok is False and "offset_mm" in err

    def test_negative_offset_rejected(self):
        ok, err = create_offset_surface(
            _FakeDoc(), {"offset_mm": -1.0},
            {"face_entity": _FACE_SENTINEL},
        )
        assert ok is False and "offset_mm" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is False and "failed to select" in err


# --- UNFIRED registry gate --------------------------------------------------


class TestUnfiredGate:
    def test_spike_status_is_green(self):
        # Seat-proven W0 2026-06-18: InsertOffsetSurface -> 'OffsetRefSurface',
        # sheet bodies 0->1, area 0->1200 mm2, survives reopen.
        assert offset_surface.SPIKE_STATUS == "GREEN"

    def test_in_handler_registry_when_green(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY
        assert "offset_surface" in HANDLER_REGISTRY
        assert HANDLER_REGISTRY["offset_surface"] is offset_surface.create_offset_surface


# --- selection contract (mark=0, no callout) --------------------------------


class TestSelectionContract:
    def test_face_selected_with_mark_0(self, monkeypatch):
        calls: list[tuple] = []
        _wire(monkeypatch, select_calls=calls)
        ok, _ = create_offset_surface(
            _FakeDoc(), {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is True
        assert len(calls) == 1
        entity, append, mark = calls[0]
        assert entity is _FACE_SENTINEL
        assert append is False
        assert mark == 0

    def test_clear_selection_called_before_select(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_offset_surface(
            doc, {"offset_mm": 5.0}, {"face_entity": _FACE_SENTINEL}
        )
        assert ok is True
        assert doc.cleared is True
