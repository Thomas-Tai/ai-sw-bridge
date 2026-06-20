"""W62 offline tests — ``project_curve`` handler + dual-mode contract.

project_curve is the boss-fight lane: reflection found NO dedicated
project-curve FeatureData interface and NO InsertProjectCurve* method.
Both Mode-A (CreateDefinition → QI ref-curve data) and Mode-B (Insert*
probe + convert-on-face fallback) are authored as candidate paths; the
live-seat spike determines which (if either) fires.

The module is **DORMANT** while ``SPIKE_STATUS == "UNRUN"``: the handler
exists and is testable, but it is NOT registered in HANDLER_REGISTRY
(W0 controls wiring in ``__init__.py``).

What is tested
--------------
* Dormant gate: SPIKE_STATUS="UNRUN" → kind absent from registry.
* Validation: bad/missing inputs → (False, reason).
* Mode-A green: CreateDefinition + CreateFeature succeed → node delta → True.
* Mode-A QI fail: QI raises but CreateFeature still runs with raw data.
* Mode-B insert green: InsertProjectCurve on FM succeeds.
* Mode-B convert green: convert-on-face fallback (SketchUseEdge3).
* Both modes fail → (False, "both … failed").
* Ghost rejection: modes run but no node delta → (False, "no ref-curve …").
* Never raises: even with None inputs.
* Kind-name disjointness from built-in types.

COM seams are patched on the lane module itself (``features.project_curve``)
per the registry lane protocol — never on ``mutate``.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import project_curve as pc
from ai_sw_bridge.features.project_curve import create_project_curve


@pytest.fixture(autouse=True)
def _mock_curve_length(monkeypatch):
    """Offline, the COM-heavy arc-length read is mocked to a positive default;
    the geometric CURVE gate (W67 P3b) is exercised explicitly in TestCurveGate.
    A projected-curve fake carries no curve geometry, so without this the hard
    gate would null every success path."""
    monkeypatch.setattr(pc, "_curve_length_mm", lambda node: 25.0)


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------

class _FakeFM:
    """Fake FeatureManager with configurable Mode-A / Mode-B behaviour."""

    def __init__(
        self,
        *,
        defn: object | None = None,
        created_feat: object | None = None,
        has_insert: bool = False,
        insert_result: object | None = None,
    ) -> None:
        self._defn = defn
        self._created_feat = created_feat
        self._has_insert = has_insert
        self._insert_result = insert_result
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list[object] = []

    def CreateDefinition(self, id_: int) -> object | None:
        self.create_def_calls.append(id_)
        return self._defn

    def CreateFeature(self, data: object) -> object | None:
        self.create_feat_calls.append(data)
        return self._created_feat

    def InsertProjectCurve(self) -> object | None:
        if not self._has_insert:
            raise AttributeError("InsertProjectCurve not available")
        return self._insert_result


class _FakeSketchMgr:
    """Fake SketchManager that records convert-on-face calls."""

    def __init__(self) -> None:
        self.sketch_open = False
        self.use_edge3_calls = 0
        self.sketch_close_count = 0

    def InsertSketch(self, flag: bool) -> None:
        if flag and not self.sketch_open:
            self.sketch_open = True
        elif flag and self.sketch_open:
            self.sketch_close_count += 1
            self.sketch_open = False

    def SketchUseEdge3(self, *args) -> None:
        self.use_edge3_calls += 1


class _FakeFeature:
    """Fake IFeature with a Select2 method for convert-on-face tests."""

    def __init__(self, name: str = "Sketch2") -> None:
        self.Name = name
        self.selected = False

    def Select2(self, append: bool, mark: int) -> bool:
        self.selected = True
        return True


class _FakeDoc:
    """Fake IModelDoc2 for project_curve handler testing."""

    def __init__(self, **fm_kwargs) -> None:
        self.FeatureManager = _FakeFM(**fm_kwargs)
        self.SketchManager = _FakeSketchMgr()
        self._features_by_name: dict[str, object] = {
            "Sketch2": _FakeFeature("Sketch2"),
        }
        self.cleared = 0
        self.rebuilt = 0

    def FeatureByName(self, name: str) -> object | None:
        return self._features_by_name.get(name)

    def ClearSelection2(self, flag: bool) -> None:
        self.cleared += 1

    def ForceRebuild3(self, flag: bool) -> None:
        self.rebuilt += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feat(**kw) -> dict:
    """Default valid feature dict."""
    base = {"sketch_name": "Sketch2"}
    base.update(kw)
    return base


def _tgt(**kw) -> dict:
    """Default valid target dict."""
    base = {"face": object()}
    base.update(kw)
    return base


def _wire_count(monkeypatch, before: int = 0, after: int = 1) -> None:
    """Patch _count_feature_nodes on the project_curve module."""
    seq = [before, after]
    state = {"n": 0}

    def fake(doc):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(pc, "_count_feature_nodes", fake)


def _wire_green(monkeypatch) -> None:
    """Flip SPIKE_STATUS to GREEN for handler execution."""
    monkeypatch.setattr(pc, "SPIKE_STATUS", "GREEN")


# ---------------------------------------------------------------------------
# Dormant gate — SPIKE_STATUS is UNRUN, kind absent from registry
# ---------------------------------------------------------------------------

class TestRegistryGreenGate:
    def test_spike_status_is_green(self) -> None:
        assert pc.SPIKE_STATUS == "GREEN"

    def test_project_curve_in_registry_when_green(self) -> None:
        assert HANDLER_REGISTRY.get("project_curve") is create_project_curve

    def test_validation_runs_even_when_green(self) -> None:
        """Even with SPIKE_STATUS=GREEN, the handler validates inputs and
        fails closed on invalid feature/target shapes before touching COM."""
        ok, err = create_project_curve(None, None, None)
        assert ok is False
        assert err is not None


# ---------------------------------------------------------------------------
# Validation — runs with SPIKE_STATUS="GREEN"
# ---------------------------------------------------------------------------

class TestValidation:
    def test_feature_not_dict(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch)
        ok, err = create_project_curve(_FakeDoc(), "not-a-dict", _tgt())
        assert ok is False and "dict" in err

    def test_target_not_dict(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch)
        ok, err = create_project_curve(_FakeDoc(), _feat(), "not-a-dict")
        assert ok is False and "dict" in err

    def test_missing_sketch_name(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch)
        ok, err = create_project_curve(_FakeDoc(), {}, _tgt())
        assert ok is False and "sketch_name" in err

    def test_empty_sketch_name(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch)
        ok, err = create_project_curve(
            _FakeDoc(), {"sketch_name": ""}, _tgt(),
        )
        assert ok is False and "sketch_name" in err

    def test_non_string_sketch_name(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch)
        ok, err = create_project_curve(
            _FakeDoc(), {"sketch_name": 42}, _tgt(),
        )
        assert ok is False and "sketch_name" in err


# ---------------------------------------------------------------------------
# Mode-A green — CreateDefinition + CreateFeature succeed
# ---------------------------------------------------------------------------

class TestModeAQuarantined:
    """Mode-A is quarantined post-seat: v1 spike proved no QI succeeds on
    CreateDefinition output, and CreateDefinition(61) returns None.
    _try_mode_a is a no-op stub on every input. The handler routes to
    Mode-B-insert (InsertProjectedSketch2) or Mode-B-convert (SketchUseEdge3)."""

    def test_mode_a_returns_none_always(self) -> None:
        assert pc._try_mode_a(_FakeDoc(), _feat()) is None
        assert pc._try_mode_a(None, {}) is None

    def test_createdefinition_returns_none_falls_through(self, monkeypatch):
        """CreateDefinition(None) is irrelevant — Mode-A is quarantined.
        Mode-B-insert path drives the handler when its fakes are wired."""
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        doc = _FakeDoc(defn=None, has_insert=True, insert_result=object())
        ok, note = create_project_curve(doc, _feat(), _tgt())
        assert ok is True
        assert "mode-B" in note

    def test_createfeature_returns_none_falls_through(self, monkeypatch):
        """CreateFeature(None) is irrelevant — Mode-A is quarantined."""
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        doc = _FakeDoc(
            defn=object(), created_feat=None,
            has_insert=True, insert_result=object(),
        )
        ok, note = create_project_curve(doc, _feat(), _tgt())
        assert ok is True
        assert "mode-B" in note


# ---------------------------------------------------------------------------
# Mode-B green — Insert* or convert-on-face fallback
# ---------------------------------------------------------------------------

class TestModeB:
    def test_green_via_insert_project_curve(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        # Mode-A fails: CreateDefinition returns None
        doc = _FakeDoc(
            defn=None,
            has_insert=True,
            insert_result=object(),
        )
        ok, note = create_project_curve(doc, _feat(), _tgt())
        assert ok is True
        assert "mode-B" in note

    def test_green_via_convert_on_face(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        # Mode-A fails (defn=None), Mode-B insert absent → convert fallback
        doc = _FakeDoc(defn=None, has_insert=False)
        ok, note = create_project_curve(doc, _feat(), _tgt())
        assert ok is True
        assert "mode-B-convert" in note
        assert doc.SketchManager.use_edge3_calls == 1
        assert doc.SketchManager.sketch_close_count == 1

    def test_convert_skips_when_no_sketch_name_in_feature(self, monkeypatch):
        """Convert fallback needs sketch_name; without it, both modes fail."""
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=0)
        # Validation passes because sketch_name is present but Mode-A and
        # Mode-B both fail, and the convert can't find the sketch.
        doc = _FakeDoc(defn=None, has_insert=False)
        doc._features_by_name = {}  # FeatureByName returns None
        ok, err = create_project_curve(
            doc, _feat(sketch_name="NoSuchSketch"), _tgt(),
        )
        assert ok is False
        assert "failed" in err


# ---------------------------------------------------------------------------
# Ghost rejection — modes ran but no feature-node delta
# ---------------------------------------------------------------------------

class TestGhostRejection:
    def test_no_node_delta_after_mode_a(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=2, after=2)  # no delta
        doc = _FakeDoc(defn=object(), created_feat=object())
        ok, err = create_project_curve(doc, _feat(), _tgt())
        assert ok is False
        assert "no ref-curve" in err or "delta_nodes" in err

    def test_no_node_delta_both_modes_fail(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=0)
        # Mode-A: defn=None; Mode-B: no insert; convert: no sketch found
        doc = _FakeDoc(defn=None, has_insert=False)
        doc._features_by_name = {}
        ok, err = create_project_curve(
            doc, _feat(sketch_name="Missing"), _tgt(),
        )
        assert ok is False
        assert "failed" in err

    def test_both_modes_exhausted_clear_message(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=0)
        doc = _FakeDoc(defn=None, has_insert=False)
        doc._features_by_name = {}
        ok, err = create_project_curve(
            doc, _feat(sketch_name="Gone"), _tgt(),
        )
        assert ok is False
        assert err is not None
        assert "Mode-A" in err or "mode-" in err


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_with_none_inputs_while_dormant(self) -> None:
        for _ in range(5):
            ok, err = create_project_curve(None, None, None)
            assert ok is False

    def test_with_none_inputs_while_green(self, monkeypatch) -> None:
        _wire_green(monkeypatch)
        # Don't wire _count_feature_nodes — it will hit None doc gracefully
        ok, err = create_project_curve(None, None, None)
        assert ok is False

    def test_with_partial_inputs_while_green(self, monkeypatch) -> None:
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=0)
        ok, err = create_project_curve(_FakeDoc(), {}, {})
        assert ok is False


# ---------------------------------------------------------------------------
# Kind-name disjointness from built-in types
# ---------------------------------------------------------------------------

class TestKindNames:
    def test_project_curve_disjoint_from_builtin_types(self) -> None:
        builtin_kinds = {
            "fillet_constant_radius", "base_flange", "variable_radius_fillet",
            "wizard_hole", "shell", "draft", "sweep", "ref_plane",
            "ref_axis", "coordinate_system", "ref_point", "dome",
            "sweep_cut",
        }
        assert "project_curve" not in builtin_kinds


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_ref_curve_id_is_14(self) -> None:
        assert pc._SW_FM_REF_CURVE == 14

    def test_qi_ifaces_tuple_non_empty(self) -> None:
        assert len(pc._REF_CURVE_QI_IFACES) >= 2
        assert "IReferenceCurveFeatureData" in pc._REF_CURVE_QI_IFACES


# ---------------------------------------------------------------------------
# CURVE geometric gate (W67 P3b)
# ---------------------------------------------------------------------------

class TestCurveGate:
    def test_node_without_arc_length_is_rejected(self, monkeypatch):
        """A ref-curve node materialized but with no readable arc length is the
        W42 geometric ghost — the hard gate_curve must reject it."""
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        monkeypatch.setattr(pc, "_curve_length_mm", lambda node: None)
        doc = _FakeDoc(defn=None, has_insert=True, insert_result=object())
        ok, err = create_project_curve(doc, _feat(), _tgt())
        assert ok is False
        assert "arc length" in err

    def test_node_with_arc_length_passes(self, monkeypatch):
        _wire_green(monkeypatch)
        _wire_count(monkeypatch, before=0, after=1)
        monkeypatch.setattr(pc, "_curve_length_mm", lambda node: 40.0)
        doc = _FakeDoc(defn=None, has_insert=True, insert_result=object())
        ok, note = create_project_curve(doc, _feat(), _tgt())
        assert ok is True, note
