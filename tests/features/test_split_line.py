"""W62 offline tests — ``split_line`` handler (dual-mode, verify ΔFace>0 ∧ ΔVol==0).

The split_line handler probes two COM routes: Mode-A (CreateDefinition →
ISplitLineFeatureData → CreateFeature) and Mode-B (InsertSplitLineProject on
pre-selected entities).  These tests cover BOTH branches plus the verify gate
(topological split: face count up, volume unchanged).

COM seams are patched on the lane module itself (``features.split_line``) per
the registry lane protocol — never on ``mutate``.  No SW process is involved.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import split_line as sl
from ai_sw_bridge.features.split_line import create_split_line


# ---------------------------------------------------------------------------
# Fake COM objects — dual-mode (CreateDefinition/CreateFeature + Insert*)
# ---------------------------------------------------------------------------


class _FakeSD:
    """Fake ISplitLineFeatureData (Mode-A)."""

    def __init__(self) -> None:
        self._accessed = False
        self._released = False
        self.Sketch = None
        self.SplitType = -1
        self._faces: tuple = ()

    def AccessSelections(self, doc: object, _extra: object) -> None:
        self._accessed = True

    def ISetFaces(self, *args: object) -> None:
        if len(args) == 1:
            self._faces = args[0]  # type: ignore[assignment]
        elif len(args) == 2:
            self._faces = args[1]  # type: ignore[assignment]

    def ReleaseSelectionAccess(self) -> None:
        self._released = True


class _FakeFM:
    """Fake FeatureManager (CreateDefinition + CreateFeature)."""

    def __init__(self, *, data: object | None = _FakeSD()) -> None:
        self._data = data
        self.created_features: list[object] = []

    def CreateDefinition(self, type_id: int) -> object | None:
        return self._data

    def CreateFeature(self, data: object) -> object:
        sentinel = object()
        self.created_features.append(sentinel)
        return sentinel


class _FakeDoc:
    """Fake IModelDoc2 — supports Mode-A + Mode-B + verify helpers."""

    def __init__(self, *, fm: _FakeFM | None = None) -> None:
        self.FeatureManager = fm or _FakeFM()
        self.cleared = False
        self.rebuilt = False
        self.selected: list[tuple[object, int]] = []
        self._split_calls: list[tuple[bool, bool]] = []

    def ClearSelection2(self, flag: bool) -> None:
        self.cleared = True
        self.selected.clear()

    def ForceRebuild3(self, flag: bool) -> None:
        self.rebuilt = True

    def FeatureByName(self, name: str) -> object:
        return object()

    def InsertSplitLineProject(self, reverse: bool, single_dir: bool) -> None:
        self._split_calls.append((reverse, single_dir))


# ---------------------------------------------------------------------------
# Wiring helper
# ---------------------------------------------------------------------------


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    typed_qi_result: object = "ok",
    select_ok: bool = True,
    metrics: tuple[tuple[int, float], ...] = ((6, 12000.0), (8, 12000.0)),
    data: _FakeSD | None = None,
) -> None:
    """Patch typed_qi / select_entity / _metrics on the split_line lane module.

    ``typed_qi_result``:
      "ok"    — return *data* (the shared fake ISplitLineFeatureData)
      "raise" — raise EarlyBindError (Mode-A E_NOINTERFACE → Mode-B fallback)
      "none"  — return None (Mode-A silent drop → Mode-B fallback)

    ``data``:
      Shared fake data object — pass the SAME instance to ``_FakeFM(data=...)``
      so Mode-A tests can inspect AccessSelections/SplitType/ISetFaces afterwards.
    """
    def fake_typed_qi(obj: object, iface: str, **kw: object) -> object:
        if typed_qi_result == "raise":
            from ai_sw_bridge.com.earlybind import EarlyBindError
            raise EarlyBindError(f"E_NOINTERFACE: {iface}")
        if typed_qi_result == "none":
            return None
        return data or _FakeSD()

    monkeypatch.setattr(sl, "typed_qi", fake_typed_qi)
    monkeypatch.setattr(
        sl, "select_entity",
        lambda entity, *, append=False, mark=0: select_ok,
    )

    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc: object) -> tuple[int, float]:
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(sl, "_metrics", fake_metrics)


def _target(**overrides: object) -> dict:
    """Default target dict; override keys as needed."""
    base: dict = {"sketch_name": "Sketch2", "face_entity": object()}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path — Mode-A
# ---------------------------------------------------------------------------


class TestModeA:
    def test_green_split_line_mode_a(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)
        ok, note = create_split_line(_FakeDoc(), {}, _target())
        assert ok is True
        assert note is not None and "mode-A" in note

    def test_mode_a_calls_access_and_release(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sd = _FakeSD()
        fm = _FakeFM(data=sd)
        _patch(monkeypatch, data=sd)
        doc = _FakeDoc(fm=fm)
        ok, _ = create_split_line(doc, {}, _target())
        assert ok
        assert sd._accessed is True
        assert sd._released is True

    def test_mode_a_sets_sketch_and_split_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sd = _FakeSD()
        fm = _FakeFM(data=sd)
        _patch(monkeypatch, data=sd)
        doc = _FakeDoc(fm=fm)
        ok, _ = create_split_line(
            doc, {"split_type": "projection"}, _target(),
        )
        assert ok
        assert sd.SplitType == 0  # projection
        assert sd.Sketch is not None

    def test_mode_a_select_entity_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)
        ok, _ = create_split_line(_FakeDoc(), {}, _target())
        assert ok


# ---------------------------------------------------------------------------
# Mode-B fallback
# ---------------------------------------------------------------------------


class TestModeB:
    def test_mode_b_fallback_on_qi_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """typed_qi raises EarlyBindError → Mode-A fails → Mode-B fires."""
        _patch(monkeypatch, typed_qi_result="raise")
        ok, note = create_split_line(_FakeDoc(), {}, _target())
        assert ok is True
        assert note is not None and "mode-B" in note

    def test_mode_b_fallback_on_create_definition_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CreateDefinition returns None → Mode-A fails → Mode-B fires."""
        fm = _FakeFM(data=None)
        _patch(monkeypatch)
        ok, note = create_split_line(_FakeDoc(fm=fm), {}, _target())
        assert ok is True
        assert note is not None and "mode-B" in note

    def test_mode_b_calls_insert_split_line_project(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch(monkeypatch, typed_qi_result="raise")
        doc = _FakeDoc()
        ok, _ = create_split_line(
            doc, {"reverse": True, "single_direction": True}, _target(),
        )
        assert ok
        assert doc._split_calls == [(True, True)]

    def test_mode_b_selects_sketch_then_face(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mode-B calls ClearSelection2 then InsertSplitLineProject after selecting."""
        _patch(monkeypatch, typed_qi_result="raise")
        doc = _FakeDoc()
        ok, _ = create_split_line(doc, {}, _target())
        assert ok
        assert doc.cleared is True
        assert doc._split_calls == [(False, False)]

    def test_mode_b_default_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, typed_qi_result="raise")
        doc = _FakeDoc()
        ok, _ = create_split_line(doc, {}, _target())
        assert ok
        assert doc._split_calls == [(False, False)]


# ---------------------------------------------------------------------------
# Both modes fail
# ---------------------------------------------------------------------------


class TestBothModesFail:
    def test_both_modes_fail_qi_and_insert(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mode-A QI fails AND Mode-B Insert raises → (False, reason)."""
        _patch(monkeypatch, typed_qi_result="raise")
        doc = _FakeDoc()
        # Make InsertSplitLineProject raise
        def bad_insert(*a: object, **kw: object) -> None:
            raise RuntimeError("COM dead")
        doc.InsertSplitLineProject = bad_insert  # type: ignore[assignment]
        ok, err = create_split_line(doc, {}, _target())
        assert ok is False
        assert "both Mode-A" in err and "Mode-B" in err

    def test_mode_b_select_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mode-A QI fails, Mode-B select_entity returns False → (False, reason)."""
        _patch(monkeypatch, typed_qi_result="raise", select_ok=False)
        ok, err = create_split_line(_FakeDoc(), {}, _target())
        assert ok is False
        assert "both Mode-A" in err


# ---------------------------------------------------------------------------
# Verify gate — ΔFace > 0 AND ΔVol == 0
# ---------------------------------------------------------------------------


class TestVerifyGate:
    def test_ghost_no_face_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ΔFace == 0 → ghost (the split was a silent no-op)."""
        _patch(monkeypatch, metrics=((6, 12000.0), (6, 12000.0)))
        ok, err = create_split_line(_FakeDoc(), {}, _target())
        assert ok is False
        assert "did not split" in err

    def test_ghost_volume_changed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ΔFace > 0 but ΔVol != 0 → something cut or added material."""
        _patch(monkeypatch, metrics=((6, 12000.0), (8, 12500.0)))
        ok, err = create_split_line(_FakeDoc(), {}, _target())
        assert ok is False
        assert "did not split" in err

    def test_no_solid_bodies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, metrics=((0, 0.0), (0, 0.0)))
        ok, err = create_split_line(_FakeDoc(), {}, _target())
        assert ok is False
        assert "no solid bodies" in err

    def test_small_volume_noise_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FP jitter below _VOL_EPS_MM3 is still a valid split."""
        _patch(monkeypatch, metrics=((6, 12000.0), (8, 12000.0 + 1e-9)))
        ok, _ = create_split_line(_FakeDoc(), {}, _target())
        assert ok is True


# ---------------------------------------------------------------------------
# Validation — fail-closed
# ---------------------------------------------------------------------------


class TestValidation:
    def test_feature_not_dict(self) -> None:
        ok, err = create_split_line(_FakeDoc(), "bad", _target())  # type: ignore[arg-type]
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict(self) -> None:
        ok, err = create_split_line(_FakeDoc(), {}, "bad")  # type: ignore[arg-type]
        assert ok is False and "target must be a dict" in err

    def test_missing_sketch_name(self) -> None:
        ok, err = create_split_line(_FakeDoc(), {}, {"face_entity": object()})
        assert ok is False and "sketch_name" in err

    def test_missing_face_entity(self) -> None:
        ok, err = create_split_line(
            _FakeDoc(), {}, {"sketch_name": "Sketch2"},
        )
        assert ok is False and "face_entity" in err

    def test_bad_split_type_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)
        ok, err = create_split_line(
            _FakeDoc(), {"split_type": "bogus"}, _target(),
        )
        assert ok is False and "split_type" in err

    def test_bad_split_type_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)
        ok, err = create_split_line(
            _FakeDoc(), {"split_type": [1, 2]}, _target(),
        )
        assert ok is False and "split_type" in err

    def test_int_split_type_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sd = _FakeSD()
        fm = _FakeFM(data=sd)
        _patch(monkeypatch, data=sd)
        ok, _ = create_split_line(
            _FakeDoc(fm=fm), {"split_type": 0}, _target(),
        )
        assert ok
        assert sd.SplitType == 0


# ---------------------------------------------------------------------------
# Dual-mode interaction
# ---------------------------------------------------------------------------


class TestDualMode:
    def test_mode_a_ignores_select_entity_failure(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mode-A uses ISetFaces (not select_entity), so select_ok=False
        does not block Mode-A.  Mode-B would fail, but Mode-A fires first."""
        _patch(monkeypatch, select_ok=False)
        ok, note = create_split_line(_FakeDoc(), {}, _target())
        assert ok is True
        assert note is not None and "mode-A" in note

    def test_rebuild_called_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_split_line(doc, {}, _target())
        assert ok and doc.rebuilt

    def test_rebuild_called_on_mode_b(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, typed_qi_result="raise")
        doc = _FakeDoc()
        ok, _ = create_split_line(doc, {}, _target())
        assert ok and doc.rebuilt
