"""W66 offline tests — ``thicken`` handler (UNFIRED contract).

Mirrors ``test_hem.py`` verbatim: fake-COM harness, additive (volume) ghost-
gate, never-raise, enum mapping, fail-closed validation.  ``SPIKE_STATUS``
is ``"UNFIRED"`` — the gated block in ``features/__init__.py`` stays dormant
until W0 flips GREEN on the seat.

**Gate (surface→solid BRIDGE — additive):**
    ΔVol > 0  ∧  ΔSolidBodies ≥ +1

thicken consumes a sheet body into a solid, so the surface-create gate
(ΔSheetBodies ≥ +1) is WRONG here — sheet body count may DECREASE.  The
correct witness is volume + solid-body count (same as boss_extrude additive
verify).

COM seams are patched on the lane module itself (``features.thicken``)
per the registry lane protocol — never on ``mutate``.  No SW process is
involved; the live thicken + save→reopen is proven by the seat spike.
"""

from __future__ import annotations

import pythoncom
import pytest

from ai_sw_bridge.features import thicken as tk
from ai_sw_bridge.features.thicken import create_thicken


# --- fake COM objects -------------------------------------------------------


class _FakeFM:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def FeatureBossThicken(self, *args):
        self.calls.append(args)
        return object()  # non-None handle (the EFFECT, not the return, decides)


class _FakeDoc:
    def __init__(self) -> None:
        self.FeatureManager = _FakeFM()
        self.cleared = False
        self.rebuilt = False

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# A minimal valid serialized DurableRef for face_ref tests.  The hash is the
# canonical brep.fingerprint.fingerprint digest for this geometry (normal +z,
# centroid at 10 mm, 1200 mm²) — computed once; do not change the geometry
# without recomputing.
_FACE_REF = {
    "fingerprint": {
        "hash": "7c1164078f96fdc7",
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.01],
        "area_mm2": 1200.0,
    },
    "role_hint": "+z_face",
}


def _face_ref() -> dict:
    """Return a fresh copy of the valid face_ref dict (tests may mutate it)."""
    import copy

    return copy.deepcopy(_FACE_REF)


def _wire(
    monkeypatch,
    *,
    sheet_bodies=(object(),),
    select_ok: bool = True,
    metrics=((0.0, 0), (1200.0, 8)),
    solid_counts=(1, 2),
) -> None:
    """Patch sheet_bodies/metrics/count/select seams on the thicken lane module.

    Additive gate (W66): thicken consumes a sheet into a solid, so success =
    ΔVol > 0 ∧ ΔSolidBodies ≥ +1.  ``metrics`` drives (vol_mm3, face_count)
    per call; ``solid_counts`` drives the solid-body head-count per call.
    """
    monkeypatch.setattr(tk, "_sheet_bodies", lambda doc: list(sheet_bodies))
    monkeypatch.setattr(tk, "select_entity", lambda e, mark=0: select_ok)

    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(tk, "_metrics_solid", fake_metrics)

    cseq = list(solid_counts)
    cstate = {"n": 0}

    def fake_count(doc):
        v = cseq[min(cstate["n"], len(cseq) - 1)]
        cstate["n"] += 1
        return v

    monkeypatch.setattr(tk, "_solid_body_count", fake_count)


# --- SPIKE_STATUS pin -------------------------------------------------------


class TestSpikeStatus:
    def test_unfired_before_seat_proof(self):
        assert tk.SPIKE_STATUS == "UNFIRED"


# --- enum mapper ------------------------------------------------------------


class TestEnumMapping:
    def test_maps_strings_ints_and_rejects_garbage(self):
        assert tk._enum("side1", tk._THICKEN_DIRECTIONS, "direction") == (0, None)
        assert tk._enum("Side2", tk._THICKEN_DIRECTIONS, "direction") == (1, None)
        assert tk._enum("BOTH", tk._THICKEN_DIRECTIONS, "direction") == (2, None)
        assert tk._enum(2, tk._THICKEN_DIRECTIONS, "direction") == (2, None)
        val, err = tk._enum("bogus", tk._THICKEN_DIRECTIONS, "direction")
        assert val is None and "bogus" in err
        val, err = tk._enum(True, tk._THICKEN_DIRECTIONS, "direction")
        assert val is None and "bool" in err


# --- happy path + recipe pin -----------------------------------------------


class TestEffectGate:
    def test_green_thicken_first_sheet_body(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_thicken(
            doc,
            {"thickness_mm": 2.0, "direction": "side1"},
            {},
        )
        assert (ok, err) == (True, None)
        assert doc.cleared and doc.rebuilt

    def test_recipe_pins_unit_conversion_and_arg_count(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_thicken(
            doc,
            {"thickness_mm": 5.0, "direction": "both"},
            {},
        )
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert len(args) == 7
        assert args[0] == pytest.approx(0.005)  # 5 mm -> 0.005 m
        assert args[1] == 2  # both = 2
        assert args[2] == 0  # FaceIndex = 0
        assert args[3] is False  # FillVolume
        assert args[4] is False  # Merge
        assert args[5] is False  # UseFeatScope
        assert args[6] is True  # UseAutoSelect

    def test_default_params(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_thicken(doc, {}, {})
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert args[0] == pytest.approx(0.002)  # default 2 mm -> m
        assert args[1] == 0  # default side1 = 0

    def test_int_direction_passes_through(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_thicken(
            doc,
            {"direction": 1},
            {},
        )
        assert ok, err
        assert doc.FeatureManager.calls[0][1] == 1

    def test_face_ref_target_resolved(self, monkeypatch):
        _wire(monkeypatch)
        monkeypatch.setattr(
            tk,
            "resolve_manifest_face",
            lambda doc, ref: type("R", (), {"entity": object(), "note": "test"})(),
        )
        doc = _FakeDoc()
        ok, err = create_thicken(
            doc,
            {"thickness_mm": 2.0},
            {"face_ref": _face_ref()},
        )
        assert (ok, err) == (True, None)

    def test_ghost_no_volume_delta_rejected(self, monkeypatch):
        """Thicken that adds no volume is a ghost — NOT success."""
        _wire(monkeypatch, metrics=((600.0, 6), (600.0, 6)), solid_counts=(1, 1))
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False
        assert "did not produce" in err

    def test_ghost_no_solid_body_delta_rejected(self, monkeypatch):
        """Volume rose but no new solid body materialized — ghost."""
        _wire(monkeypatch, metrics=((0.0, 0), (500.0, 4)), solid_counts=(1, 1))
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False
        assert "did not produce" in err

    def test_negative_volume_delta_rejected(self, monkeypatch):
        """Volume went DOWN (e.g. a cut) — not an additive thicken."""
        _wire(monkeypatch, metrics=((1000.0, 8), (500.0, 6)), solid_counts=(1, 2))
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False
        assert "did not produce" in err

    def test_no_sheet_bodies_fails_closed(self, monkeypatch):
        _wire(monkeypatch, sheet_bodies=())
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False and "no sheet bodies" in err


# --- fail-closed contract ---------------------------------------------------


class TestValidation:
    def test_bad_direction_rejected(self):
        ok, err = create_thicken(
            _FakeDoc(),
            {"direction": "sideways"},
            {},
        )
        assert ok is False and "direction" in err

    def test_bad_thickness_rejected(self):
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": "not_a_number"},
            {},
        )
        assert ok is False and "numeric" in err

    def test_nonpositive_thickness_rejected(self):
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 0},
            {},
        )
        assert ok is False and "positive" in err

    def test_negative_thickness_rejected(self):
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": -1},
            {},
        )
        assert ok is False and "positive" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_thicken(_FakeDoc(), "bad", {})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_thicken(_FakeDoc(), {"thickness_mm": 2}, "bad")
        assert ok is False and "target must be a dict" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False and "select" in err

    def test_face_ref_unresolved_rejected(self, monkeypatch):
        _wire(monkeypatch)
        monkeypatch.setattr(
            tk,
            "resolve_manifest_face",
            lambda doc, ref: type("R", (), {"entity": None, "note": "no match"})(),
        )
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {"face_ref": _face_ref()},
        )
        assert ok is False and "did not resolve" in err

    def test_invalid_face_ref_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_thicken(
            _FakeDoc(),
            {"thickness_mm": 2.0},
            {"face_ref": {"incomplete": True}},
        )
        assert ok is False and "face_ref" in err


# --- never-raise ------------------------------------------------------------


class TestNeverRaise:
    def test_com_exception_caught(self, monkeypatch):
        """FeatureBossThicken raising does not propagate — returns (False, …)."""
        _wire(monkeypatch)
        doc = _FakeDoc()

        def boom(*a):
            raise RuntimeError("COM wall")

        doc.FeatureManager.FeatureBossThicken = boom
        ok, err = create_thicken(
            doc,
            {"thickness_mm": 2.0},
            {},
        )
        assert ok is False and "raised" in err


# --- registry gate ----------------------------------------------------------


class TestRegistryGate:
    def test_kind_not_registered_when_unfired(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY

        assert tk.SPIKE_STATUS == "UNFIRED"
        assert "thicken" not in HANDLER_REGISTRY

    def test_handler_callable_matches_contract(self):
        assert callable(create_thicken)
