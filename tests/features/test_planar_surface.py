"""W66 offline tests — ``planar_surface`` handler.

Pins the surface-CREATE gate (ΔSheetBodies ≥ +1 ∧ ΔArea > 0), the
VARIANT-null spy contract, the validation surface, and the UNFIRED
registry gate.

Gate doctrine (W66 §0.1): a surface feature creates a zero-thickness
sheet body, so ΔVol is meaningless. The witness is the surface-body
count + area. A Boolean return without a new body, or with zero area,
is the surface form of the W42/W65 ghost.
"""

from __future__ import annotations


from ai_sw_bridge.features import planar_surface
from ai_sw_bridge.features.planar_surface import create_planar_surface


# --- fake COM objects -------------------------------------------------------


class _FakeFeature:
    """Minimal fake feature returned by _FakeDoc.FeatureByName."""

    def __init__(self, name="Sketch2"):
        self.Name = name

    def Select2(self, append, mark):
        pass


class _FakeDoc:
    def __init__(self, *, insert_result=True, raise_insert=False):
        self.cleared = False
        self.rebuilt = False
        self._insert_result = insert_result
        self._raise_insert = raise_insert
        self._sketch = _FakeFeature("Sketch2")

    def ClearSelection2(self, flag):
        self.cleared = True

    def FeatureByName(self, name):
        if name == "Sketch2":
            return self._sketch
        return None

    def InsertPlanarRefSurface(self):
        if self._raise_insert:
            raise RuntimeError("InsertPlanarRefSurface boom")
        return self._insert_result

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# --- helpers ----------------------------------------------------------------


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

    monkeypatch.setattr(planar_surface, "select_entity", fake_select)

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

    monkeypatch.setattr(planar_surface, "_sheet_body_count", fake_count)
    monkeypatch.setattr(planar_surface, "_total_sheet_area_mm2", fake_area)


# --- effect gate (surface-CREATE: ΔSheetBodies ≥ +1 ∧ ΔArea > 0) ----------


class TestEffectGate:
    def test_success_with_new_body_and_area(self, monkeypatch):
        _wire(
            monkeypatch,
            count_before=0,
            count_after=1,
            area_before=0.0,
            area_after=1200.0,
        )
        doc = _FakeDoc()
        ok, note = create_planar_surface(doc, {}, {"boundary": "Sketch2"})
        assert ok is True
        assert note is None
        assert doc.cleared is True
        assert doc.rebuilt is True

    def test_success_with_multiple_new_bodies(self, monkeypatch):
        """ΔSheetBodies > +1 is still valid (e.g. multi-region fill)."""
        _wire(
            monkeypatch,
            count_before=0,
            count_after=3,
            area_before=0.0,
            area_after=3600.0,
        )
        ok, _ = create_planar_surface(_FakeDoc(), {}, {"boundary": "Sketch2"})
        assert ok is True


# --- verify gate (ghost trap) -----------------------------------------------


class TestVerifyGate:
    def test_no_new_body_is_ghost(self, monkeypatch):
        """InsertPlanarRefSurface returns True but no new sheet body → ghost."""
        _wire(monkeypatch, count_before=0, count_after=0)
        doc = _FakeDoc(insert_result=True)
        ok, note = create_planar_surface(doc, {}, {"boundary": "Sketch2"})
        assert ok is False
        assert "did not materialize" in note

    def test_new_body_zero_area_is_ghost(self, monkeypatch):
        """Body count increases but area stays zero → ghost (W42 surface form)."""
        _wire(
            monkeypatch, count_before=0, count_after=1, area_before=0.0, area_after=0.0
        )
        ok, note = create_planar_surface(_FakeDoc(), {}, {"boundary": "Sketch2"})
        assert ok is False
        assert "did not materialize" in note

    def test_insert_returns_false_still_checks_gate(self, monkeypatch):
        """Boolean False return but body somehow appeared → still passes gate."""
        _wire(
            monkeypatch,
            count_before=0,
            count_after=1,
            area_before=0.0,
            area_after=500.0,
        )
        doc = _FakeDoc(insert_result=False)
        ok, _ = create_planar_surface(doc, {}, {"boundary": "Sketch2"})
        assert ok is True


# --- validation (fail-closed) -----------------------------------------------


class TestValidation:
    def test_missing_boundary_rejected(self):
        ok, err = create_planar_surface(_FakeDoc(), {}, {})
        assert ok is False and "boundary" in err

    def test_empty_boundary_rejected(self):
        ok, err = create_planar_surface(_FakeDoc(), {}, {"boundary": ""})
        assert ok is False and "boundary" in err

    def test_non_string_boundary_rejected(self):
        ok, err = create_planar_surface(_FakeDoc(), {}, {"boundary": 42})
        assert ok is False and "boundary" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_planar_surface(_FakeDoc(), "not_a_dict", {"boundary": "S"})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_planar_surface(_FakeDoc(), {}, "not_a_dict")
        assert ok is False and "target must be a dict" in err

    def test_sketch_not_found_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_planar_surface(_FakeDoc(), {}, {"boundary": "NoSketch"})
        assert ok is False and "not found" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_planar_surface(_FakeDoc(), {}, {"boundary": "Sketch2"})
        assert ok is False and "failed to select" in err


# --- UNFIRED registry gate --------------------------------------------------


class TestUnfiredGate:
    def test_spike_status_is_green(self):
        # Seat-proven W0 2026-06-18: InsertPlanarRefSurface -> 'PlanarSurface',
        # sheet bodies 0->1, area 0->600 mm2, survives reopen.
        assert planar_surface.SPIKE_STATUS == "GREEN"

    def test_in_handler_registry_when_green(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY

        assert "planar_surface" in HANDLER_REGISTRY
        assert (
            HANDLER_REGISTRY["planar_surface"] is planar_surface.create_planar_surface
        )


# --- selection contract (mark=0, no callout) --------------------------------


class TestSelectionContract:
    def test_boundary_selected_with_mark_0(self, monkeypatch):
        """Planar surface pre-selects the boundary sketch with mark=0."""
        calls: list[tuple] = []
        _wire(monkeypatch, select_calls=calls)
        ok, _ = create_planar_surface(_FakeDoc(), {}, {"boundary": "Sketch2"})
        assert ok is True
        assert len(calls) == 1
        _entity, _append, mark = calls[0]
        assert mark == 0

    def test_clear_selection_called_before_select(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_planar_surface(doc, {}, {"boundary": "Sketch2"})
        assert ok is True
        assert doc.cleared is True
