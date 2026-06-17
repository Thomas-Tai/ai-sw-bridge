"""W62 offline tests — ``helix`` handler dual-mode + registry gate.

Tests the dual-mode doctrine for the helix feature-add handler:
Mode-A (CreateDefinition → typed_qi(IHelixFeatureData) → CreateFeature)
and Mode-B (doc.InsertHelix with 10 args), plus the verify-gate
(feature-node materialization via FirstFeature walk; no ΔVol expected).

COM seams are patched on the lane module itself (``features.helix``) per
the registry lane protocol — never on ``mutate``.  No SW process is
involved; the live-seat probe is ``spikes/v0_2x/spike_helix.py`` (UNRUN).
"""

from __future__ import annotations

import math

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import helix
from ai_sw_bridge.features.helix import create_helix


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------

class _FakeFeature:
    def __init__(self, type_name: str, next_feat=None):
        self._type_name = type_name
        self._next = next_feat

    def GetTypeName(self):
        return self._type_name

    def GetNextFeature(self):
        return self._next


class _FakeFM:
    def __init__(self, *, cd_fails=False, qi_fails=False, cf_noop=False):
        self.cd_fails = cd_fails
        self.qi_fails = qi_fails
        self.cf_noop = cf_noop
        self.create_def_calls = 0
        self.create_feat_calls = 0
        self.feature_data = object()

    def CreateDefinition(self, feature_id):
        self.create_def_calls += 1
        if self.cd_fails:
            return None
        return self.feature_data

    def CreateFeature(self, data):
        self.create_feat_calls += 1
        if self.cf_noop:
            return None
        return object()


class _FakeDoc:
    def __init__(self, *, fm=None, insert_helix_effect=True):
        self.fm = fm or _FakeFM()
        self.FeatureManager = self.fm
        self._insert_helix_effect = insert_helix_effect
        self.insert_helix_calls: list[tuple] = []
        self.select_calls: list[tuple] = []
        self.cleared = False
        self.rebuilt = False
        self._helix_count = 0
        self._build_tree()

    def _build_tree(self):
        origin = _FakeFeature("Origin")
        planes = _FakeFeature("Planes", origin)
        base = _FakeFeature("Base", planes)
        sketch = _FakeFeature("Sketch", base)
        self._base_tree = sketch
        helix_node = _FakeFeature("Helix", sketch)
        self._tree_with_helix = helix_node

    def FirstFeature(self):
        if self._helix_count > 0:
            return self._tree_with_helix
        return self._base_tree

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True

    def SelectByID(self, name, kind, x, y, z):
        self.select_calls.append((name, kind))
        return True

    def InsertHelix(self, *args):
        self.insert_helix_calls.append(args)
        if self._insert_helix_effect:
            self._helix_count += 1


def _wire(
    monkeypatch,
    *,
    qi_fails=False,
    fake_fm=None,
    fake_doc=None,
):
    """Patch wrapper_module and typed_qi on the helix lane module."""
    monkeypatch.setattr(helix, "wrapper_module", lambda: object())

    if qi_fails:
        from ai_sw_bridge.com.earlybind import EarlyBindError

        def fake_typed_qi(obj, iface, *, module=None):
            raise EarlyBindError(f"E_NOINTERFACE for {iface}")

        monkeypatch.setattr(helix, "typed_qi", fake_typed_qi)
    else:
        class _StubFD:
            DefinedBy = None
            Pitch = None
            Revolution = None
            Height = None
            StartingAngle = None
            Clockwise = None

        monkeypatch.setattr(
            helix, "typed_qi",
            lambda obj, iface, *, module=None: _StubFD(),
        )

    def fake_typed(obj, iface, *, module=None):
        return obj

    from ai_sw_bridge.com import earlybind as _eb

    monkeypatch.setattr(_eb, "typed", fake_typed)


# ---------------------------------------------------------------------------
# Mode-A success
# ---------------------------------------------------------------------------

class TestModeA:
    def test_green_mode_a(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, err = create_helix(
            doc,
            {"pitch_mm": 5, "revolutions": 4, "start_angle_deg": 0, "clockwise": True},
            {"sketch": "Sketch2"},
        )
        assert ok is True
        assert err is None
        assert doc.fm.create_def_calls == 1
        assert doc.fm.create_feat_calls == 1
        assert len(doc.select_calls) == 1
        assert doc.select_calls[0] == ("Sketch2", "SKETCH")

    def test_mode_a_unit_conversion(self, monkeypatch):
        """Pitch mm→m, start_angle deg→rad, height = pitch * revolutions."""
        _wire(monkeypatch)
        doc = _FakeDoc()
        fd_mock = type("FakeFD", (), {})()
        fd_mock.DefinedBy = None
        fd_mock.Pitch = None
        fd_mock.Revolution = None
        fd_mock.Height = None
        fd_mock.StartingAngle = None
        fd_mock.Clockwise = None

        original_typed_qi = helix.typed_qi
        monkeypatch.setattr(
            helix, "typed_qi",
            lambda obj, iface, *, module=None: fd_mock,
        )
        ok, err = create_helix(
            doc,
            {"pitch_mm": 10, "revolutions": 3, "start_angle_deg": 90},
            {"sketch": "Sketch2"},
        )
        assert ok, err
        assert fd_mock.Pitch == pytest.approx(0.010)
        assert fd_mock.Revolution == pytest.approx(3.0)
        assert fd_mock.Height == pytest.approx(0.030)
        assert fd_mock.StartingAngle == pytest.approx(math.radians(90))

    def test_mode_a_not_used_when_qi_fails(self, monkeypatch):
        """When typed_qi raises EarlyBindError, Mode-A is abandoned."""
        _wire(monkeypatch, qi_fails=True)
        doc = _FakeDoc()
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is True  # Mode-B should pick up
        assert doc.fm.create_feat_calls == 0  # CreateFeature never called


# ---------------------------------------------------------------------------
# Mode-B fallback
# ---------------------------------------------------------------------------

class TestModeB:
    def test_mode_b_when_create_definition_none(self, monkeypatch):
        fm = _FakeFM(cd_fails=True)
        _wire(monkeypatch, fake_fm=fm)
        doc = _FakeDoc(fm=fm)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is True
        assert err is None
        assert len(doc.insert_helix_calls) == 1

    def test_mode_b_when_qi_fails(self, monkeypatch):
        _wire(monkeypatch, qi_fails=True)
        doc = _FakeDoc()
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is True
        assert len(doc.insert_helix_calls) == 1

    def test_mode_b_when_create_feature_noop(self, monkeypatch):
        fm = _FakeFM(cf_noop=True)
        _wire(monkeypatch, fake_fm=fm)
        doc = _FakeDoc(fm=fm)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is True
        assert len(doc.insert_helix_calls) == 1

    def test_mode_b_arg_count_and_pitch_conversion(self, monkeypatch):
        fm = _FakeFM(cd_fails=True)
        _wire(monkeypatch, fake_fm=fm)
        doc = _FakeDoc(fm=fm)
        ok, err = create_helix(
            doc,
            {"pitch_mm": 5, "revolutions": 4, "start_angle_deg": 45, "clockwise": True},
            {"sketch": "Sketch2"},
        )
        assert ok, err
        args = doc.insert_helix_calls[0]
        assert len(args) == 10
        assert args[0] is True       # ConstantPitch
        assert args[3] is True       # Clockwise
        assert args[4] == 0          # DefinedBy (pitch+revolution)
        assert args[5] == pytest.approx(0.005)  # Pitch 5mm → 0.005m
        assert args[6] == pytest.approx(4.0)    # Revolution
        assert args[7] == pytest.approx(0.020)  # Height = 0.005*4 = 0.020m
        assert args[8] == pytest.approx(math.radians(45))  # StartAngle rad

    def test_mode_b_insert_helix_failure(self, monkeypatch):
        """Both modes fail → (False, reason)."""
        fm = _FakeFM(cd_fails=True)
        _wire(monkeypatch, fake_fm=fm)
        doc = _FakeDoc(fm=fm, insert_helix_effect=False)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "Mode-A" in err
        assert "Mode-B" in err


# ---------------------------------------------------------------------------
# Verify gate
# ---------------------------------------------------------------------------

class TestVerifyGate:
    def test_mode_a_no_effect_falls_to_mode_b(self, monkeypatch):
        """Mode-A fires but doesn't add a Helix node → Mode-B tried."""
        fm = _FakeFM(cf_noop=True)
        _wire(monkeypatch, fake_fm=fm)
        doc = _FakeDoc(fm=fm)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is True  # Mode-B picks up
        assert len(doc.insert_helix_calls) == 1

    def test_ghost_rejected_both_modes_no_node(self, monkeypatch):
        """Neither mode produces a Helix node → (False, reason)."""
        _wire(monkeypatch, qi_fails=True)
        doc = _FakeDoc(insert_helix_effect=False)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "failed" in err


# ---------------------------------------------------------------------------
# Validation (fail-closed)
# ---------------------------------------------------------------------------

class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_helix(_FakeDoc(), "not_a_dict", {"sketch": "Sketch2"})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict(self):
        ok, err = create_helix(_FakeDoc(), {"pitch_mm": 5}, "not_a_dict")
        assert ok is False and "target must be a dict" in err

    def test_missing_sketch(self):
        ok, err = create_helix(_FakeDoc(), {"pitch_mm": 5}, {})
        assert ok is False and "sketch" in err

    def test_empty_sketch(self):
        ok, err = create_helix(_FakeDoc(), {"pitch_mm": 5}, {"sketch": ""})
        assert ok is False and "sketch" in err

    def test_invalid_pitch(self):
        ok, err = create_helix(
            _FakeDoc(), {"pitch_mm": "abc"}, {"sketch": "Sketch2"},
        )
        assert ok is False and "invalid" in err

    def test_nonpositive_pitch(self):
        ok, err = create_helix(
            _FakeDoc(), {"pitch_mm": 0}, {"sketch": "Sketch2"},
        )
        assert ok is False and "pitch_mm" in err

    def test_nonpositive_revolutions(self):
        ok, err = create_helix(
            _FakeDoc(), {"pitch_mm": 5, "revolutions": -1}, {"sketch": "Sketch2"},
        )
        assert ok is False and "revolutions" in err

    def test_never_raises_on_none_inputs(self):
        for _ in range(5):
            ok, err = create_helix(None, None, None)  # type: ignore[arg-type]
            assert ok is False


# ---------------------------------------------------------------------------
# Dormant gate + kind disjointness
# ---------------------------------------------------------------------------

class TestDormantGate:
    def test_spike_status_is_unrun(self):
        assert helix.SPIKE_STATUS == "UNRUN"

    def test_helix_not_in_registry_when_dormant(self):
        assert "helix" not in HANDLER_REGISTRY


class TestKindNames:
    def test_helix_disjoint_from_builtin_types(self):
        builtin_kinds = {
            "fillet_constant_radius", "base_flange", "variable_radius_fillet",
            "wizard_hole", "shell", "draft", "sweep", "ref_plane",
            "ref_axis", "coordinate_system", "ref_point", "dome",
            "sweep_cut",
        }
        assert "helix" not in builtin_kinds
