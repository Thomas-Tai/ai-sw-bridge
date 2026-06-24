"""W66 offline tests — ``knit`` handler (UNFIRED contract, BOSS FIGHT).

Pins the AGGREGATION gate (INVERTED: ΔSheetBodies < 0 ∧ area > 0), the
VARIANT-null callout spy, the mark=1 selection contract, the fail-closed
validation surface, and the UNFIRED registry gate.

Gate doctrine (W66 §0.1, §5): knit MERGES sheet bodies, so the surface-
CREATE gate (ΔSheetBodies ≥ +1) is WRONG here — sheet-body count goes
DOWN.  Gating on "≥1 new body" would false-fail knit (the inverse of the
W65 sketched_bend false-fail).

Two sub-modes:
  * Surface-knit (default): ΔSheetBodies < 0 ∧ area > 0
  * Solid-knit (try_to_form_solid): ΔSheetBodies < 0 ∧ ΔSolidBodies ≥ +1 ∧ ΔVol > 0

COM seams are patched on the lane module itself (``features.knit``) per
the registry lane protocol — never on ``mutate``.
"""

from __future__ import annotations

import pythoncom
import pytest

from ai_sw_bridge.features import knit as kn
from ai_sw_bridge.features.knit import create_knit


# --- fake COM objects -------------------------------------------------------


class _FakeExtension:
    def __init__(self, *, select_ok: bool = True):
        self.calls: list[tuple] = []
        self._select_ok = select_ok

    def SelectByID2(self, *args):
        self.calls.append(args)
        return self._select_ok


class _FakeFM:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def InsertSewRefSurface(self, *args):
        self.calls.append(args)
        return object()


class _FakeBody:
    def __init__(self, name: str = "Surface-Plane1"):
        self.Name = name


class _FakeDoc:
    def __init__(self, *, select_ok: bool = True) -> None:
        self.Extension = _FakeExtension(select_ok=select_ok)
        self.FeatureManager = _FakeFM()
        self.cleared = False
        self.rebuilt = False

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# --- helpers ----------------------------------------------------------------


def _body_refs(*names: str, type: str = "SURFACEBODY") -> list[dict]:
    return [{"name": n, "type": type} for n in names]


def _wire(
    monkeypatch,
    *,
    sheet_counts=(2, 1),
    areas=(2400.0, 2400.0),
    solid_counts=(0, 0),
    volumes=(0.0, 0.0),
) -> None:
    """Patch metric seams on the knit lane module.

    ``sheet_counts`` and ``areas`` drive (before, after) for the AGGREGATION
    gate; ``solid_counts`` and ``volumes`` drive the solid-knit sub-mode.
    """
    seq_sheet = list(sheet_counts)
    seq_area = list(areas)
    seq_solid = list(solid_counts)
    seq_vol = list(volumes)
    state = {"sheet": 0, "area": 0, "solid": 0, "vol": 0}

    def fake_sheet_count(doc):
        v = seq_sheet[min(state["sheet"], len(seq_sheet) - 1)]
        state["sheet"] += 1
        return v

    def fake_area(doc):
        v = seq_area[min(state["area"], len(seq_area) - 1)]
        state["area"] += 1
        return v

    def fake_solid_count(doc):
        v = seq_solid[min(state["solid"], len(seq_solid) - 1)]
        state["solid"] += 1
        return v

    def fake_vol(doc):
        v = seq_vol[min(state["vol"], len(seq_vol) - 1)]
        state["vol"] += 1
        return v

    monkeypatch.setattr(kn, "_sheet_body_count", fake_sheet_count)
    monkeypatch.setattr(kn, "_total_sheet_area_mm2", fake_area)
    monkeypatch.setattr(kn, "_solid_body_count", fake_solid_count)
    monkeypatch.setattr(kn, "_solid_volume_mm3", fake_vol)


# --- SPIKE_STATUS pin -------------------------------------------------------


class TestSpikeStatus:
    def test_green_after_seat_proof(self):
        # Seat-proven W0 2026-06-18: InsertSewRefSurface merged sheets 2->1,
        # area 1900 mm2 conserved, survives reopen (inverted aggregation gate).
        assert kn.SPIKE_STATUS == "GREEN"


# --- effect gate (AGGREGATION: ΔSheetBodies < 0 ∧ area > 0) ----------------


class TestEffectGate:
    def test_surface_knit_success(self, monkeypatch):
        """2 sheets → 1 sheet, area preserved → PASS."""
        _wire(monkeypatch, sheet_counts=(2, 1), areas=(2400.0, 2400.0))
        doc = _FakeDoc()
        ok, err = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert (ok, err) == (True, None)
        assert doc.cleared and doc.rebuilt

    def test_three_to_one_knit(self, monkeypatch):
        """3 sheets → 1 sheet → PASS."""
        _wire(monkeypatch, sheet_counts=(3, 1), areas=(3600.0, 3600.0))
        ok, _ = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": _body_refs("S1", "S2", "S3")},
        )
        assert ok is True

    def test_solid_knit_success(self, monkeypatch):
        """try_to_form_solid: sheets consumed, solid appeared, volume > 0."""
        _wire(
            monkeypatch,
            sheet_counts=(2, 0),
            areas=(2400.0, 0.0),
            solid_counts=(0, 1),
            volumes=(0.0, 8000.0),
        )
        ok, err = create_knit(
            _FakeDoc(),
            {"try_to_form_solid": True},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert (ok, err) == (True, None)


# --- ghost trap (AGGREGATION false-fail / false-pass) -----------------------


class TestGhostTrap:
    def test_no_merge_is_ghost(self, monkeypatch):
        """Sheet count unchanged → knit did nothing → FAIL."""
        _wire(monkeypatch, sheet_counts=(2, 2), areas=(2400.0, 2400.0))
        ok, err = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False
        assert "did not merge" in err

    def test_sheets_increased_is_not_knit(self, monkeypatch):
        """Sheet count went UP → something else happened → FAIL."""
        _wire(monkeypatch, sheet_counts=(2, 3), areas=(2400.0, 3600.0))
        ok, err = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False
        assert "did not merge" in err

    def test_merged_but_zero_area_is_ghost(self, monkeypatch):
        """Sheets merged but result has zero area → W42 surface ghost."""
        _wire(monkeypatch, sheet_counts=(2, 1), areas=(2400.0, 0.0))
        ok, err = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False
        assert "did not merge" in err

    def test_solid_knit_no_volume_is_ghost(self, monkeypatch):
        """try_to_form_solid but no volume → ghost solid."""
        _wire(
            monkeypatch,
            sheet_counts=(2, 0),
            areas=(2400.0, 0.0),
            solid_counts=(0, 1),
            volumes=(0.0, 0.0),
        )
        ok, err = create_knit(
            _FakeDoc(),
            {"try_to_form_solid": True},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False
        assert "did not materialize" in err

    def test_solid_knit_no_solid_body_is_ghost(self, monkeypatch):
        """try_to_form_solid but no new solid body → ghost."""
        _wire(
            monkeypatch,
            sheet_counts=(2, 0),
            areas=(2400.0, 0.0),
            solid_counts=(0, 0),
            volumes=(0.0, 5000.0),
        )
        ok, err = create_knit(
            _FakeDoc(),
            {"try_to_form_solid": True},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False
        assert "did not materialize" in err


# --- recipe pin (5-arg InsertSewRefSurface, VARIANT-null callout) ----------


class TestRecipePin:
    def test_default_args(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok
        args = doc.FeatureManager.calls[0]
        assert len(args) == 5
        assert args[0] is True  # use_gap_filters default
        assert args[1] is False  # try_to_form_solid default
        assert args[2] is False  # merge_entities default
        assert args[3] == pytest.approx(1e-7)  # 0.0001 mm -> m
        assert args[4] == pytest.approx(1e-7)  # 0.0001 mm -> m

    def test_custom_params(self, monkeypatch):
        _wire(
            monkeypatch,
            sheet_counts=(2, 0),
            areas=(2400.0, 0.0),
            solid_counts=(0, 1),
            volumes=(0.0, 8000.0),
        )
        doc = _FakeDoc()
        ok, _ = create_knit(
            doc,
            {
                "try_to_form_solid": True,
                "use_gap_filters": False,
                "merge_entities": True,
                "knit_tolerance_mm": 0.01,
                "max_gap_mm": 0.05,
            },
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok
        args = doc.FeatureManager.calls[0]
        assert args[0] is False  # use_gap_filters off
        assert args[1] is True  # try_to_form_solid on
        assert args[2] is True  # merge_entities on
        assert args[3] == pytest.approx(1e-5)  # 0.01 mm -> m
        assert args[4] == pytest.approx(5e-5)  # 0.05 mm -> m


# --- selection contract (mark=1, VARIANT-null callout, append pattern) -----


class TestSelectionContract:
    def test_mark_1_and_append_pattern(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok
        calls = doc.Extension.calls
        assert len(calls) == 2
        # First: Append=False, Mark=1
        assert calls[0][5] is False  # append
        assert calls[0][6] == 1  # mark
        # Second: Append=True, Mark=1
        assert calls[1][5] is True  # append
        assert calls[1][6] == 1  # mark

    def test_callout_null_is_variant_dispatch(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok
        callout = doc.Extension.calls[0][7]
        assert callout.varianttype == pythoncom.VT_DISPATCH
        assert callout.value is None

    def test_three_bodies_append_chain(self, monkeypatch):
        _wire(monkeypatch, sheet_counts=(3, 1), areas=(3600.0, 3600.0))
        doc = _FakeDoc()
        ok, _ = create_knit(
            doc,
            {},
            {"body_refs": _body_refs("S1", "S2", "S3")},
        )
        assert ok
        calls = doc.Extension.calls
        assert len(calls) == 3
        assert calls[0][5] is False  # first: no append
        assert calls[1][5] is True  # second: append
        assert calls[2][5] is True  # third: append

    def test_clear_selection_called_before_select(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok and doc.cleared


# --- validation (fail-closed) -----------------------------------------------


class TestValidation:
    def test_feature_not_dict_rejected(self):
        ok, err = create_knit(_FakeDoc(), "bad", {"body_refs": _body_refs("S1", "S2")})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_knit(_FakeDoc(), {}, "bad")
        assert ok is False and "target must be a dict" in err

    def test_empty_body_refs_name_rejected(self):
        ok, err = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": [{"name": ""}, {"name": "S2"}]},
        )
        assert ok is False and "name" in err

    def test_single_body_ref_falls_through_to_auto(self, monkeypatch):
        """A single body_ref is not enough → falls through to auto-discover."""
        _wire(monkeypatch, sheet_counts=(1, 1))  # only 1 sheet
        ok, err = create_knit(
            _FakeDoc(),
            {},
            {"body_refs": [{"name": "S1"}]},
        )
        # Auto-discover fails with <2 sheet bodies
        assert ok is False and "sheet bod" in err

    def test_bad_tolerance_rejected(self):
        ok, err = create_knit(
            _FakeDoc(),
            {"knit_tolerance_mm": "bad"},
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False and "tolerance" in err

    def test_tolerance_below_lower_bound_rejected(self):
        ok, err = create_knit(
            _FakeDoc(),
            {"knit_tolerance_mm": 0.00001},  # below 0.0001 mm
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False and "bounds" in err

    def test_tolerance_above_upper_bound_rejected(self):
        ok, err = create_knit(
            _FakeDoc(),
            {"knit_tolerance_mm": 1.0},  # above 0.1 mm
            {"body_refs": _body_refs("S1", "S2")},
        )
        assert ok is False and "bounds" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(select_ok=False)
        ok, err = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok is False and "returned False" in err


# --- never-raise ------------------------------------------------------------


class TestNeverRaise:
    def test_com_exception_caught(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()

        def boom(*a):
            raise RuntimeError("COM wall")

        doc.FeatureManager.InsertSewRefSurface = boom
        ok, err = create_knit(doc, {}, {"body_refs": _body_refs("S1", "S2")})
        assert ok is False and "raised" in err


# --- registry gate ----------------------------------------------------------


class TestRegistryGate:
    def test_kind_registered_when_green(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY

        assert kn.SPIKE_STATUS == "GREEN"
        assert "knit" in HANDLER_REGISTRY
        assert HANDLER_REGISTRY["knit"] is kn.create_knit

    def test_handler_callable_matches_contract(self):
        assert callable(create_knit)
