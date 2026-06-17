"""W62 offline tests — ``helix`` handler (Mode-A QUARANTINED, Mode-B operative).

The seat-validated doctrine for helix curves on SW2024:
  * Mode-A is **documented unreachable for CREATION** — the swconst harvest
    exposes NO swFeatureNameID for helix (DLL reflection 2026-06-17). Like
    composite, IHelixFeatureData is edit-only via IFeature.GetDefinition();
    no creation enum exists. The handler does not attempt Mode-A.
  * Mode-B is the operative path: select the sketch via
    Extension.SelectByID2 (with VARIANT(VT_DISPATCH,None) callout — the
    W60/W61 proven idiom), then ``doc.InsertHelix(10 args)`` (void return).

Verify gate: feature-node count delta via
``IFeatureManager.GetFeatures(False)`` filtered by type-name "Helix".
``IModelDoc2.FirstFeature`` is unreachable headless out-of-process — proven
on the W62 composite seat fire 2026-06-17.

COM seams are patched on the lane module itself (``features.helix``) per
the registry lane protocol. No SW process is involved; the live-seat probe
is ``spikes/v0_2x/spike_helix.py`` (UNRUN).
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
    def __init__(self, type_name: str):
        self._type_name = type_name

    def GetTypeName(self):
        return self._type_name


class _FakeFM:
    def __init__(self, *, owning_doc=None):
        self._owning_doc = owning_doc

    def GetFeatures(self, top_only):
        return tuple(self._owning_doc.current_tree()) if self._owning_doc else ()


class _FakeExt:
    def __init__(self, *, owning_doc, select_ok=True):
        self._owning_doc = owning_doc
        self._select_ok = select_ok

    def SelectByID2(self, name, kind, x, y, z, append, mark, callout, opt):
        self._owning_doc.select_calls.append((name, kind, append, mark))
        return self._select_ok


class _FakeDoc:
    def __init__(self, *, select_ok=True, insert_helix_effect=True,
                 insert_helix_raises=False):
        self.fm = _FakeFM()
        self.fm._owning_doc = self
        self.FeatureManager = self.fm
        self.Extension = _FakeExt(owning_doc=self, select_ok=select_ok)
        self._insert_helix_effect = insert_helix_effect
        self._insert_helix_raises = insert_helix_raises
        self.insert_helix_calls: list[tuple] = []
        self.select_calls: list[tuple] = []
        self.cleared = False
        self.rebuilt = False
        self._helix_count = 0
        self._base_nodes = [
            _FakeFeature("Origin"),
            _FakeFeature("Planes"),
            _FakeFeature("Base"),
            _FakeFeature("Sketch"),
        ]

    def current_tree(self) -> list[_FakeFeature]:
        nodes = list(self._base_nodes)
        for _ in range(self._helix_count):
            nodes.append(_FakeFeature("Helix"))
        return nodes

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True

    def InsertHelix(self, *args):
        if self._insert_helix_raises:
            raise RuntimeError("InsertHelix boom")
        self.insert_helix_calls.append(args)
        if self._insert_helix_effect:
            self._helix_count += 1


# ---------------------------------------------------------------------------
# Mode-A quarantine
# ---------------------------------------------------------------------------

class TestModeAQuarantined:
    """Mode-A no longer exists in the handler — the SW2024 swconst harvest
    proves there is no swFeatureNameID for helix. The handler fires Mode-B
    only; this test pins the doctrine."""

    def test_no_mode_a_symbols_in_module(self):
        """No CreateDefinition/typed_qi/IHelixFeatureData paths remain."""
        assert not hasattr(helix, "_try_mode_a")
        assert not hasattr(helix, "_SW_FM_HELIX")


# ---------------------------------------------------------------------------
# Mode-B operative path
# ---------------------------------------------------------------------------

class TestModeB:
    def test_green_mode_b(self):
        doc = _FakeDoc()
        ok, err = create_helix(
            doc,
            {"pitch_mm": 5, "revolutions": 4, "start_angle_deg": 0, "clockwise": True},
            {"sketch": "Sketch2"},
        )
        assert ok is True, err
        assert err is None
        assert len(doc.insert_helix_calls) == 1
        assert len(doc.select_calls) == 1
        # SelectByID2 called with (name, kind, append, mark)
        assert doc.select_calls[0] == ("Sketch2", "SKETCH", False, 0)

    def test_unit_conversion(self):
        doc = _FakeDoc()
        ok, _ = create_helix(
            doc,
            {"pitch_mm": 10, "revolutions": 3, "start_angle_deg": 90, "clockwise": True},
            {"sketch": "Sketch2"},
        )
        assert ok is True
        args = doc.insert_helix_calls[0]
        assert len(args) == 10
        assert args[0] is True       # ConstantPitch
        assert args[3] is True       # Clockwise
        assert args[4] == 0          # DefinedBy
        assert args[5] == pytest.approx(0.010)  # Pitch 10 mm
        assert args[6] == pytest.approx(3.0)    # Revolution
        assert args[7] == pytest.approx(0.030)  # Height = 0.010 * 3
        assert args[8] == pytest.approx(math.radians(90))

    def test_select_failure_short_circuits(self):
        doc = _FakeDoc(select_ok=False)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "select" in err.lower()
        assert doc.insert_helix_calls == []

    def test_insert_helix_raises_returns_false(self):
        doc = _FakeDoc(insert_helix_raises=True)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "InsertHelix" in err

    def test_insert_helix_no_effect_is_ghost(self):
        """InsertHelix called, no exception, but no Helix node materialized."""
        doc = _FakeDoc(insert_helix_effect=False)
        ok, err = create_helix(
            doc, {"pitch_mm": 5, "revolutions": 4}, {"sketch": "Sketch2"},
        )
        assert ok is False
        assert "no Helix node materialized" in err


# ---------------------------------------------------------------------------
# Verify gate (ghost trap)
# ---------------------------------------------------------------------------

class TestVerifyGate:
    def test_count_helices_via_getfeatures(self):
        """The verify gate reads from FeatureManager.GetFeatures(False)."""
        doc = _FakeDoc()
        assert helix._count_helices(doc) == 0
        doc._helix_count = 2
        assert helix._count_helices(doc) == 2

    def test_count_helices_handles_callable_getfeatures(self):
        """If GetFeatures returns nothing, count is zero."""
        class _EmptyFM:
            def GetFeatures(self, top_only):
                return ()
        class _EmptyDoc:
            FeatureManager = _EmptyFM()
        assert helix._count_helices(_EmptyDoc()) == 0


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
    def test_spike_status_is_green(self):
        assert helix.SPIKE_STATUS == "GREEN"

    def test_helix_in_registry_when_green(self):
        assert HANDLER_REGISTRY.get("helix") is create_helix


class TestKindNames:
    def test_helix_disjoint_from_builtin_types(self):
        builtin_kinds = {
            "fillet_constant_radius", "base_flange", "variable_radius_fillet",
            "wizard_hole", "shell", "draft", "sweep", "ref_plane",
            "ref_axis", "coordinate_system", "ref_point", "dome",
            "sweep_cut",
        }
        assert "helix" not in builtin_kinds
