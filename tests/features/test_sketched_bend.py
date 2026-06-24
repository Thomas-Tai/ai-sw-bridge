"""W65 offline tests — ``sketched_bend`` handler (UNFIRED contract).

Mirrors ``test_hem.py`` verbatim: fake-COM harness, PCBA-is-a-VARIANT-not-None
spy (the W64 OOP-guard pattern), ΔVol ghost-gate, never-raise, enum mapping,
fail-closed validation.  ``SPIKE_STATUS`` is ``"UNFIRED"`` — the gated block
in ``features/__init__.py`` stays dormant until W0 flips GREEN on the seat.

Two target modes are tested:

* ``edge_ref`` — durable entity resolved via ``resolve_edge_ref`` (the hem
  pattern; the spike may use this if it captures a persist token for the
  sketch line).
* ``sketch`` — feature name resolved via ``FeatureByName`` + ``Select2``
  (the brief's primary target shape for jog / 3dBend).

COM seams are patched on the lane module itself (``features.sketched_bend``)
per the registry lane protocol — never on ``mutate``.  No SW process is
involved; the live fold + save→reopen is proven by the seat spike.
"""

from __future__ import annotations

import math

import pythoncom
import pytest

from ai_sw_bridge.features import sketched_bend as sb
from ai_sw_bridge.features.sketched_bend import create_sketched_bend


def _edge_ref(length: float = 0.06) -> dict:
    """A minimal valid serialized DurableEdgeRef (no persist token needed —
    ``resolve_edge_ref`` is patched in the wired tests)."""
    return {
        "start": [0.0, 0.0, 0.0],
        "end": [length, 0.0, 0.0],
        "length": length,
        "role_hint": "edge",
    }


class _FakeSketchFeat:
    """Minimal fake of an IFeature returned by FeatureByName for a sketch."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.selected = False

    def Select2(self, append: bool, mark: int) -> None:
        self.selected = True


class _FakeFM:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def InsertSheetMetal3dBend(self, *args):
        self.calls.append(args)
        return object()  # non-None handle (the EFFECT, not the return, decides)


class _FakeDoc:
    def __init__(self, sketch_name: str = "Sketch2") -> None:
        self.FeatureManager = _FakeFM()
        self.cleared = False
        self.rebuilt = False
        self._sketch = _FakeSketchFeat(sketch_name)

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True

    def FeatureByName(self, name: str):
        if name == self._sketch._name:
            return self._sketch
        return None


def _wire(
    monkeypatch,
    *,
    entity: object = None,
    select_ok: bool = True,
    metrics=((6, 4800.0), (10, 5500.0)),
    bbox_changes: bool = True,
) -> None:
    """Patch resolve/select/metrics/bbox seams on the sketched_bend lane module.

    Fold-class gate (W65): a bend is volume-preserving, so success = ΔFaces>0 ∧
    a bounding-box change (material rotates out of plane), NOT a volume delta.
    ``metrics`` drives the face count; ``bbox_changes`` toggles the simulated
    bbox move (False = no-op/ghost)."""
    ent = object() if entity is None else entity
    if entity is False:  # explicit "unresolved" sentinel
        ent = None
    monkeypatch.setattr(
        sb,
        "resolve_edge_ref",
        lambda doc, ref: type("R", (), {"entity": ent, "note": "test"})(),
    )
    monkeypatch.setattr(sb, "select_entity", lambda e, mark=0: select_ok)
    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(sb, "_metrics", fake_metrics)

    before_box = (0.0, 0.0, 0.0, 0.06, 0.04, 0.0)
    after_box = (0.0, 0.0, -0.01, 0.06, 0.04, 0.0) if bbox_changes else before_box
    bseq = [before_box, after_box]
    bstate = {"n": 0}

    def fake_bbox(doc):
        v = bseq[min(bstate["n"], len(bseq) - 1)]
        bstate["n"] += 1
        return v

    monkeypatch.setattr(sb, "_body_bbox", fake_bbox)


# --- SPIKE_STATUS pin -------------------------------------------------------


class TestSpikeStatus:
    def test_green_after_seat_proof(self):
        # Seat-proven W0 2026-06-18: InsertSheetMetal3dBend -> SM3dBend,
        # ΔFaces +8, bbox moved (fold-class gate), survives reopen.
        assert sb.SPIKE_STATUS == "GREEN"


# --- enum mapper -----------------------------------------------------------


class TestEnumMapping:
    def test_maps_strings_ints_and_rejects_garbage(self):
        assert sb._enum("material_inside", sb._BEND_POSITIONS, "position") == (1, None)
        assert sb._enum("Bend_Outside", sb._BEND_POSITIONS, "position") == (3, None)
        assert sb._enum(4, sb._BEND_POSITIONS, "position") == (4, None)
        val, err = sb._enum("bogus", sb._BEND_POSITIONS, "position")
        assert val is None and "bogus" in err
        val, err = sb._enum(True, sb._BEND_POSITIONS, "position")
        assert val is None and "bool" in err


# --- happy path + recipe pin ----------------------------------------------


class TestEffectGate:
    def test_green_bend_via_sketch_name(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_sketched_bend(
            doc,
            {"angle_deg": 90, "position": "material_inside"},
            {"sketch": "Sketch2"},
        )
        assert (ok, err) == (True, None)
        assert doc.cleared and doc.rebuilt
        assert doc._sketch.selected

    def test_green_bend_via_edge_ref(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_sketched_bend(
            doc,
            {"angle_deg": 90, "position": "material_inside"},
            {"edge_ref": _edge_ref()},
        )
        assert (ok, err) == (True, None)

    def test_recipe_pins_pcba_null_and_unit_conversion(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_sketched_bend(
            doc,
            {
                "angle_deg": 45,
                "radius_mm": 2,
                "use_default_radius": False,
                "flip": True,
                "position": "bend_outside",
            },
            {"sketch": "Sketch2"},
        )
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert len(args) == 6
        assert args[0] == pytest.approx(math.radians(45))  # 45 deg -> rad
        assert args[1] is False  # use_default_radius=False
        assert args[2] == pytest.approx(0.002)  # 2 mm -> m
        assert args[3] is True  # flip
        assert args[4] == 3  # bend_outside
        pcba = args[5]
        assert pcba.varianttype == pythoncom.VT_DISPATCH  # Tactic-1 null
        assert pcba.value is None

    def test_default_radius_true_ignores_radius(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_sketched_bend(
            doc,
            {"angle_deg": 90, "use_default_radius": True, "radius_mm": 999},
            {"sketch": "Sketch2"},
        )
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert args[1] is True  # BUseDefaultRadius = True

    def test_int_position_passes_through(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_sketched_bend(
            doc,
            {"position": 2},
            {"sketch": "Sketch2"},
        )
        assert ok, err
        assert doc.FeatureManager.calls[0][4] == 2

    def test_ghost_no_bbox_change_rejected(self, monkeypatch):
        # Fold-class gate: faces can rise yet, with NO bounding-box change,
        # nothing folded — NO_OP/ghost, NOT success. (A bend is volume-
        # preserving; ΔVol is no longer the discriminator — W65 seat finding.)
        _wire(monkeypatch, metrics=((6, 4800.0), (8, 4800.0)), bbox_changes=False)
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "did not fold" in err

    def test_no_solid_bodies_fails_closed(self, monkeypatch):
        _wire(monkeypatch, metrics=((0, 0.0), (0, 0.0)))
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"sketch": "Sketch2"},
        )
        assert ok is False and "no solid bodies" in err


# --- fail-closed contract --------------------------------------------------


class TestValidation:
    def test_missing_target_rejected(self):
        ok, err = create_sketched_bend(_FakeDoc(), {"angle_deg": 90}, {})
        assert ok is False and ("edge_ref" in err or "sketch" in err)

    def test_invalid_edge_ref_rejected(self):
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"edge_ref": {"start": [0, 0, 0]}},  # missing end/length
        )
        assert ok is False and "edge_ref" in err

    def test_edge_unresolved_rejected(self, monkeypatch):
        _wire(monkeypatch, entity=False)
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"edge_ref": _edge_ref()},
        )
        assert ok is False and "did not resolve" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"edge_ref": _edge_ref()},
        )
        assert ok is False and "select" in err

    def test_sketch_not_found_rejected(self):
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": 90},
            {"sketch": "NoSuchSketch"},
        )
        assert ok is False and "not found" in err

    def test_bad_position_rejected(self):
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"position": "sideways"},
            {"sketch": "Sketch2"},
        )
        assert ok is False and "position" in err

    def test_bad_angle_rejected(self):
        ok, err = create_sketched_bend(
            _FakeDoc(),
            {"angle_deg": "not_a_number"},
            {"sketch": "Sketch2"},
        )
        assert ok is False and "numeric" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_sketched_bend(_FakeDoc(), "bad", {"sketch": "Sketch2"})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_sketched_bend(_FakeDoc(), {"angle_deg": 90}, "bad")
        assert ok is False and "target must be a dict" in err


# --- never-raise -----------------------------------------------------------


class TestNeverRaise:
    def test_com_exception_caught(self, monkeypatch):
        """InsertSheetMetal3dBend raising does not propagate — returns (False, …)."""
        _wire(monkeypatch)
        doc = _FakeDoc()

        def boom(*a):
            raise RuntimeError("COM wall")

        doc.FeatureManager.InsertSheetMetal3dBend = boom
        ok, err = create_sketched_bend(
            doc,
            {"angle_deg": 90},
            {"sketch": "Sketch2"},
        )
        assert ok is False and "raised" in err


# --- registry gate ---------------------------------------------------------


class TestRegistryGate:
    def test_kind_registered_when_green(self):
        from ai_sw_bridge.features import HANDLER_REGISTRY

        assert sb.SPIKE_STATUS == "GREEN"
        assert "sketched_bend" in HANDLER_REGISTRY
        assert HANDLER_REGISTRY["sketched_bend"] is sb.create_sketched_bend

    def test_handler_callable_matches_contract(self):
        assert callable(create_sketched_bend)
