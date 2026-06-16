"""W59 offline tests — ``hem`` handler + registry dispatch (PROVEN contract).

Supersedes the bc5c849 stale-draft suite, which pinned the WALLED-draft
contract (``edge_name``/``SelectByID2``, integer ``hem_type`` with
negative-rejection, ``d_length_m``, face-count-only effect gate). The live
seat overturned that draft (spike_hem_v5 / the handler PAE): hem is
generative via ``InsertSheetMetalHem`` + ``VARIANT(VT_DISPATCH, None)`` PCBA
null + a durable boundary ``edge_ref``. These tests pin that real contract.

COM seams are patched on the lane module itself (``features.hem``) per the
registry lane protocol — never on ``mutate``. No SW process is involved; the
live fold + save→reopen is proven by the seat PAE.
"""

from __future__ import annotations

import math

import pythoncom
import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import hem
from ai_sw_bridge.features.hem import create_hem


def _edge_ref(length: float = 0.06) -> dict:
    """A minimal valid serialized DurableEdgeRef (no persist token needed —
    ``resolve_edge_ref`` is patched in the wired tests)."""
    return {
        "start": [0.0, 0.0, 0.0],
        "end": [length, 0.0, 0.0],
        "length": length,
        "role_hint": "edge",
    }


class _FakeFM:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def InsertSheetMetalHem(self, *args):
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


def _wire(monkeypatch, *, entity: object = None, select_ok: bool = True,
          metrics=((6, 4800.0), (14, 5903.84))) -> None:
    """Patch resolve/select/metrics seams on the hem lane module."""
    ent = object() if entity is None else entity
    if entity is False:  # explicit "unresolved" sentinel
        ent = None
    monkeypatch.setattr(
        hem, "resolve_edge_ref",
        lambda doc, ref: type("R", (), {"entity": ent, "note": "test"})(),
    )
    monkeypatch.setattr(hem, "select_entity", lambda e, mark=0: select_ok)
    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(hem, "_metrics", fake_metrics)


# --- enum mapper -----------------------------------------------------------

class TestEnumMapping:
    def test_maps_strings_ints_and_rejects_garbage(self):
        assert hem._enum("closed", hem._HEM_TYPES, "hem_type") == (1, None)
        assert hem._enum("TearDrop", hem._HEM_TYPES, "hem_type") == (2, None)
        assert hem._enum(3, hem._HEM_TYPES, "hem_type") == (3, None)
        val, err = hem._enum("bogus", hem._HEM_TYPES, "hem_type")
        assert val is None and "bogus" in err
        val, err = hem._enum(True, hem._HEM_TYPES, "hem_type")  # bool is int subclass
        assert val is None and "bool" in err


# --- happy path + recipe pin ----------------------------------------------

class TestEffectGate:
    def test_green_hem_closed(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_hem(
            doc, {"hem_type": "closed", "position": "inside", "length_mm": 10},
            {"edge_ref": _edge_ref()},
        )
        assert (ok, err) == (True, None)
        assert doc.cleared and doc.rebuilt

    def test_recipe_pins_pcba_null_and_unit_conversion(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_hem(
            doc,
            {"hem_type": "closed", "position": "inside", "length_mm": 10,
             "angle_deg": 90, "radius_mm": 2, "miter_gap_mm": 1},
            {"edge_ref": _edge_ref()},
        )
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert len(args) == 9
        assert args[0] == 1            # hem_type closed
        assert args[1] == 0            # position inside
        assert args[2] is False        # reverse default
        assert args[3] == pytest.approx(0.010)              # 10 mm -> m
        assert args[5] == pytest.approx(math.radians(90))   # 90 deg -> rad
        assert args[6] == pytest.approx(0.002)              # radius 2 mm -> m
        assert args[7] == pytest.approx(0.001)              # miter 1 mm -> m
        pcba = args[8]
        assert pcba.varianttype == pythoncom.VT_DISPATCH    # Tactic-1 null coercion
        assert pcba.value is None

    def test_int_enums_pass_through(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_hem(
            doc, {"hem_type": 2, "position": 1, "length_mm": 5},
            {"edge_ref": _edge_ref()},
        )
        assert ok, err
        args = doc.FeatureManager.calls[0]
        assert args[0] == 2 and args[1] == 1

    def test_ghost_zero_volume_rejected(self, monkeypatch):
        # Faces go up but volume is unchanged -> W42-class ghost -> NOT success.
        _wire(monkeypatch, metrics=((6, 4800.0), (8, 4800.0)))
        ok, err = create_hem(_FakeDoc(), {"length_mm": 10}, {"edge_ref": _edge_ref()})
        assert ok is False
        assert "did not fold" in err

    def test_no_solid_bodies_fails_closed(self, monkeypatch):
        _wire(monkeypatch, metrics=((0, 0.0), (0, 0.0)))
        ok, err = create_hem(_FakeDoc(), {"length_mm": 10}, {"edge_ref": _edge_ref()})
        assert ok is False and "no solid bodies" in err


# --- fail-closed contract --------------------------------------------------

class TestValidation:
    def test_missing_edge_ref_rejected(self):
        ok, err = create_hem(_FakeDoc(), {"length_mm": 10}, {})
        assert ok is False and "edge_ref" in err

    def test_invalid_edge_ref_rejected(self):
        # missing 'end'/'length' -> DurableEdgeRef.from_dict raises -> fail-closed
        ok, err = create_hem(
            _FakeDoc(), {"length_mm": 10}, {"edge_ref": {"start": [0, 0, 0]}}
        )
        assert ok is False and "edge_ref" in err

    def test_edge_unresolved_rejected(self, monkeypatch):
        _wire(monkeypatch, entity=False)  # resolve returns entity=None
        ok, err = create_hem(_FakeDoc(), {"length_mm": 10}, {"edge_ref": _edge_ref()})
        assert ok is False and "did not resolve" in err

    def test_select_failure_rejected(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        ok, err = create_hem(_FakeDoc(), {"length_mm": 10}, {"edge_ref": _edge_ref()})
        assert ok is False and "select" in err

    def test_bad_hem_type_rejected(self):
        ok, err = create_hem(
            _FakeDoc(), {"hem_type": "bogus", "length_mm": 10}, {"edge_ref": _edge_ref()}
        )
        assert ok is False and "hem_type" in err

    def test_bad_position_rejected(self):
        ok, err = create_hem(
            _FakeDoc(), {"position": "sideways", "length_mm": 10},
            {"edge_ref": _edge_ref()},
        )
        assert ok is False and "position" in err

    def test_nonpositive_length_rejected(self):
        ok, err = create_hem(
            _FakeDoc(), {"length_mm": 0}, {"edge_ref": _edge_ref()}
        )
        assert ok is False and "length_mm" in err


# --- registry dispatch — hem auto-advertised -------------------------------

class TestRegistryDispatch:
    def test_kind_in_handler_registry(self):
        assert "hem" in HANDLER_REGISTRY

    def test_registry_handler_is_create_fn(self):
        assert HANDLER_REGISTRY["hem"] is create_hem

    def test_registry_dispatches_correctly(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = HANDLER_REGISTRY["hem"](
            doc, {"type": "hem", "length_mm": 10}, {"edge_ref": _edge_ref()}
        )
        assert (ok, err) == (True, None)
