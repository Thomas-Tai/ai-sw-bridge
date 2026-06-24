"""W68 offline tests -- ``sketch_driven_pattern`` handler + dormant contract.

sketch_driven_pattern is the 4th pattern family (sibling to linear /
circular / mirror shipped in W21). Mode-B only: pre-select seed (mark 4)
+ reference sketch (mark UNKNOWN), then
``fm.FeatureSketchDrivenPattern(UseCentroid, BGeomPatt)``.

The module is **DORMANT** while ``SPIKE_STATUS == "UNFIRED"``: the handler
exists and is testable, but it is NOT registered in HANDLER_REGISTRY
(W0 controls wiring in ``__init__.py``).

What is tested
--------------
* Dormant gate: SPIKE_STATUS="UNFIRED" -> kind absent from registry.
* Validation: bad/missing inputs -> (False, reason).
* Mode-B green: selection + FeatureSketchDrivenPattern -> additive gate -> True.
* Selection failure: seed or sketch not found -> (False, reason).
* Ghost rejection: method ran but no geometry delta -> (False, "did not replicate").
* Never raises: even with None inputs.
* Kind-name disjointness from built-in types.

COM seams are patched on the lane module itself
(``features.sketch_driven_pattern``) per the registry lane protocol --
never on ``mutate``.
"""

from __future__ import annotations


from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import sketch_driven_pattern as sdp
from ai_sw_bridge.features.sketch_driven_pattern import create_sketch_driven_pattern


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeFM:
    """Fake FeatureManager that records FeatureSketchDrivenPattern calls."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def FeatureSketchDrivenPattern(self, use_centroid: bool, geom_patt: bool):
        self.calls.append((use_centroid, geom_patt))
        return object()


class _FakeFeature:
    """Fake IFeature with a Select2 method."""

    def __init__(self, name: str) -> None:
        self.Name = name
        self.selected = False

    def Select2(self, append: bool, mark: int) -> bool:
        self.selected = True
        return True


class _FakeDoc:
    """Fake IModelDoc2 for sketch_driven_pattern handler testing."""

    def __init__(self) -> None:
        self.FeatureManager = _FakeFM()
        self._features_by_name: dict[str, _FakeFeature] = {
            "Boss-Extrude2": _FakeFeature("Boss-Extrude2"),
            "Sketch3": _FakeFeature("Sketch3"),
        }
        self.cleared = 0
        self.rebuilt = 0

    def FeatureByName(self, name: str) -> _FakeFeature | None:
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
    base = {"seed_name": "Boss-Extrude2", "sketch_name": "Sketch3"}
    base.update(kw)
    return base


def _tgt(**kw) -> dict:
    """Default valid target dict."""
    return kw


def _wire(
    monkeypatch,
    *,
    select_ok: bool = True,
    metrics=((6, 4800.0), (14, 5903.84)),
) -> None:
    """Patch select_entity + _metrics seams on the sdp lane module."""
    monkeypatch.setattr(
        sdp,
        "select_entity",
        lambda e, append=False, mark=0: select_ok,
    )
    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(sdp, "_metrics", fake_metrics)


# ---------------------------------------------------------------------------
# Dormant gate -- SPIKE_STATUS is UNFIRED, kind absent from registry
# ---------------------------------------------------------------------------


class TestDormantGate:
    def test_spike_status_is_green(self) -> None:
        # seat-proven 2026-06-21 (SketchPattern node, +5 faces/+423mm³, survives reopen)
        assert sdp.SPIKE_STATUS == "GREEN"

    def test_sketch_driven_pattern_registered(self) -> None:
        assert "sketch_driven_pattern" in HANDLER_REGISTRY
        assert HANDLER_REGISTRY["sketch_driven_pattern"] is create_sketch_driven_pattern


# ---------------------------------------------------------------------------
# Validation -- runs even when UNFIRED (the handler validates before COM)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_sketch_driven_pattern(_FakeDoc(), "not-a-dict", _tgt())
        assert ok is False and "dict" in err

    def test_target_not_dict(self):
        ok, err = create_sketch_driven_pattern(_FakeDoc(), _feat(), "not-a-dict")
        assert ok is False and "dict" in err

    def test_missing_seed_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_sketch_driven_pattern(
            _FakeDoc(),
            {"sketch_name": "Sketch3"},
            _tgt(),
        )
        assert ok is False and "seed_name" in err

    def test_empty_seed_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_sketch_driven_pattern(
            _FakeDoc(),
            {"seed_name": "", "sketch_name": "Sketch3"},
            _tgt(),
        )
        assert ok is False and "seed_name" in err

    def test_missing_sketch_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_sketch_driven_pattern(
            _FakeDoc(),
            {"seed_name": "Boss-Extrude2"},
            _tgt(),
        )
        assert ok is False and "sketch_name" in err

    def test_empty_sketch_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_sketch_driven_pattern(
            _FakeDoc(),
            {"seed_name": "Boss-Extrude2", "sketch_name": ""},
            _tgt(),
        )
        assert ok is False and "sketch_name" in err

    def test_non_string_seed_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_sketch_driven_pattern(
            _FakeDoc(),
            {"seed_name": 42, "sketch_name": "Sketch3"},
            _tgt(),
        )
        assert ok is False and "seed_name" in err


# ---------------------------------------------------------------------------
# Mode-B green -- selection + FeatureSketchDrivenPattern -> additive gate
# ---------------------------------------------------------------------------


class TestModeB:
    def test_green_pattern(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, note = create_sketch_driven_pattern(doc, _feat(), _tgt())
        assert ok is True
        assert "sketch_driven_pattern created" in note
        assert doc.cleared >= 1
        assert doc.rebuilt >= 1

    def test_recipe_pins_args(self, monkeypatch):
        """FeatureSketchDrivenPattern receives (use_centroid, geom_pattern)."""
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, note = create_sketch_driven_pattern(
            doc,
            _feat(use_centroid=False, geom_pattern=True),
            _tgt(),
        )
        assert ok is True
        args = doc.FeatureManager.calls[0]
        assert args == (False, True)

    def test_default_use_centroid_true(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_sketch_driven_pattern(doc, _feat(), _tgt())
        assert ok is True
        args = doc.FeatureManager.calls[0]
        assert args[0] is True  # use_centroid default
        assert args[1] is False  # geom_pattern default


# ---------------------------------------------------------------------------
# Selection failure
# ---------------------------------------------------------------------------


class TestSelectionFailure:
    def test_seed_not_found(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        doc._features_by_name.pop("Boss-Extrude2", None)
        ok, err = create_sketch_driven_pattern(
            doc,
            _feat(seed_name="NoSuchSeed"),
            _tgt(),
        )
        assert ok is False and "seed" in err.lower()

    def test_sketch_not_found(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        doc._features_by_name.pop("Sketch3", None)
        ok, err = create_sketch_driven_pattern(
            doc,
            _feat(sketch_name="NoSuchSketch"),
            _tgt(),
        )
        assert ok is False and "sketch" in err.lower()

    def test_select_entity_fails(self, monkeypatch):
        _wire(monkeypatch, select_ok=False)
        doc = _FakeDoc()
        ok, err = create_sketch_driven_pattern(doc, _feat(), _tgt())
        assert ok is False and "select" in err.lower()

    def test_no_solid_bodies(self, monkeypatch):
        _wire(monkeypatch, metrics=((0, 0.0), (0, 0.0)))
        ok, err = create_sketch_driven_pattern(doc := _FakeDoc(), _feat(), _tgt())
        assert ok is False and "no solid bodies" in err


# ---------------------------------------------------------------------------
# Ghost rejection -- method ran but no geometry delta
# ---------------------------------------------------------------------------


class TestGhostRejection:
    def test_zero_volume_delta_rejected(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 4800.0), (8, 4800.0)))
        doc = _FakeDoc()
        ok, err = create_sketch_driven_pattern(doc, _feat(), _tgt())
        assert ok is False
        assert "did not replicate" in err

    def test_zero_face_delta_rejected(self, monkeypatch):
        _wire(monkeypatch, metrics=((6, 4800.0), (6, 5000.0)))
        doc = _FakeDoc()
        ok, err = create_sketch_driven_pattern(doc, _feat(), _tgt())
        assert ok is False
        assert "did not replicate" in err


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------


class TestNeverRaises:
    def test_with_none_inputs(self) -> None:
        for _ in range(5):
            ok, err = create_sketch_driven_pattern(None, None, None)
            assert ok is False

    def test_with_partial_inputs(self, monkeypatch) -> None:
        _wire(monkeypatch, metrics=((0, 0.0), (0, 0.0)))
        ok, err = create_sketch_driven_pattern(_FakeDoc(), {}, {})
        assert ok is False

    def test_clearselection_raises(self, monkeypatch):
        _wire(monkeypatch)

        class _RaisingDoc(_FakeDoc):
            def ClearSelection2(self, flag):
                raise RuntimeError("COM error")

        ok, err = create_sketch_driven_pattern(_RaisingDoc(), _feat(), _tgt())
        assert ok is False and "ClearSelection2" in err


# ---------------------------------------------------------------------------
# Kind-name disjointness from built-in types
# ---------------------------------------------------------------------------


class TestKindNames:
    def test_sketch_driven_pattern_disjoint_from_builtin_types(self) -> None:
        builtin_kinds = {
            "fillet_constant_radius",
            "base_flange",
            "variable_radius_fillet",
            "wizard_hole",
            "shell",
            "draft",
            "sweep",
            "ref_plane",
            "ref_axis",
            "coordinate_system",
            "ref_point",
            "dome",
            "sweep_cut",
            "boss_extrude",
            "boss_revolve",
            "cut_extrude",
        }
        assert "sketch_driven_pattern" not in builtin_kinds

    def test_sketch_driven_pattern_registered_to_its_handler(self) -> None:
        # post-ship: the kind maps to ITS handler (no collision with another lane)
        assert (
            HANDLER_REGISTRY.get("sketch_driven_pattern")
            is create_sketch_driven_pattern
        )


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_verify_class_is_additive_solid(self) -> None:
        from ai_sw_bridge.features.verify import FeatureClass

        assert sdp.VERIFY_CLASS == FeatureClass.ADDITIVE_SOLID
