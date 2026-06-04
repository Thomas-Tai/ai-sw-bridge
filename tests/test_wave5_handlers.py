"""Tests for Wave-5 feature_add handler stubs (F0, F1, F2–F6).

These tests validate the handler logic that will be wired into
mutate.py by W0.  The handlers are tested against fake COM objects;
the real CreateFeature paths are marked ``# SEAT-PENDING (W0)``
and are NOT exercised here.

Test structure mirrors ``test_mutate_feature_add.py``:
  - TestPropose<Feature>  — propose-validation rejects bad inputs
  - TestDryRun<Feature>   — dry-run calls the right COM methods
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import sw_propose_feature_add

# ---------------------------------------------------------------------------
# F1 — Sweep-cut handler (mirror _create_sweep with swFmSweepCut=18)
# ---------------------------------------------------------------------------


def _patch_com_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch COM imports so _create_sweep_cut works with fake objects."""
    import ai_sw_bridge.mutate as mutate_mod

    def _fake_typed(obj: Any, iface: str, module: Any = None) -> Any:
        return obj

    def _fake_typed_qi(obj: Any, iface: str, module: Any = None) -> Any:
        return obj

    def _fake_wrapper_module() -> Any:
        return object()

    monkeypatch.setattr(mutate_mod, "typed", _fake_typed)
    monkeypatch.setattr(mutate_mod, "typed_qi", _fake_typed_qi)
    monkeypatch.setattr(mutate_mod, "wrapper_module", _fake_wrapper_module)


class _FakeSweepCutExt:
    def __init__(self, ret: bool = True) -> None:
        self.select_calls: list[tuple] = []
        self._ret = ret

    def SelectByID2(self, name: str, t: str, x: float, y: float, z: float,
                     append: bool, mark: int, callout: Any, sd: int) -> bool:
        self.select_calls.append((name, t, append, mark))
        return self._ret


class _FakeSweepCutFm:
    def __init__(self, create_feat_ret: Any = object(), *, materializes: bool = True) -> None:
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list = []
        self._feat_ret = create_feat_ret
        # W6 T4: production handler verifies via GetFeatures(True) delta, since
        # CreateFeature may return None even on success.
        self._count = 21
        self._materializes = materializes

    def CreateDefinition(self, const: int) -> Any:
        self.create_def_calls.append(const)
        return object()

    def CreateFeature(self, data: Any) -> Any:
        self.create_feat_calls.append(data)
        if self._materializes:
            self._count += 1
        return self._feat_ret

    def GetFeatures(self, top_level: bool):  # noqa: N802, FBT001
        return ["f"] * self._count


class _FakeSweepCutDoc:
    def __init__(self, fm: _FakeSweepCutFm, ext_ret: bool = True) -> None:
        self.FeatureManager = fm
        self.Extension = _FakeSweepCutExt(ext_ret)
        self.rebuild_calls: list[bool] = []
        self.clear_calls: list[bool] = []

    def ForceRebuild3(self, verify: bool) -> None:
        self.rebuild_calls.append(verify)

    def ClearSelection2(self, top: bool) -> None:
        self.clear_calls.append(top)


_SW_FM_SWEEP_CUT = 18  # swFmSweepCut (SEAT-PENDING: confirm const from typelib)


class TestProposeSweepCut:
    def test_validates_profile_and_path(self) -> None:
        ok, err = _validate_sweep_cut_target({"profile": "Sketch1", "path": "Sketch2"})
        assert ok is True

    def test_rejects_missing_profile(self) -> None:
        ok, err = _validate_sweep_cut_target({"path": "Sketch2"})
        assert ok is False and "profile" in err

    def test_rejects_missing_path(self) -> None:
        ok, err = _validate_sweep_cut_target({"profile": "Sketch1"})
        assert ok is False and "path" in err


class TestDryRunSweepCut:
    def test_ok_creates_sweep_cut(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeSweepCutFm()
        doc = _FakeSweepCutDoc(fm)
        _patch_com_imports(monkeypatch)
        ok, err = _create_sweep_cut(doc, {"profile": "Sketch1", "path": "Sketch2"})
        assert ok is True
        assert fm.create_def_calls == [_SW_FM_SWEEP_CUT]
        assert doc.Extension.select_calls == [
            ("Sketch1", "SKETCH", False, 1),
            ("Sketch2", "SKETCH", True, 4),
        ]

    def test_noop_when_create_feature_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeSweepCutFm(create_feat_ret=None)
        doc = _FakeSweepCutDoc(fm)
        _patch_com_imports(monkeypatch)
        ok, err = _create_sweep_cut(doc, {"profile": "Sketch1", "path": "Sketch2"})
        assert ok is False
        assert "did not materialize" in err

    def test_select_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeSweepCutFm()
        doc = _FakeSweepCutDoc(fm, ext_ret=False)
        _patch_com_imports(monkeypatch)
        ok, err = _create_sweep_cut(doc, {"profile": "Sketch1", "path": "Sketch2"})
        assert ok is False
        assert "could not select" in err


# ---------------------------------------------------------------------------
# F2–F6 — Stub handlers (seat-pending; these validate the scaffolding)
# ---------------------------------------------------------------------------


class TestLoftStub:
    def test_propose_validates_profiles(self) -> None:
        ok, err = _validate_loft_target({"profiles": ["Sketch1", "Sketch2"]})
        assert ok is True

    def test_rejects_empty_profiles(self) -> None:
        ok, err = _validate_loft_target({"profiles": []})
        assert ok is False and "profiles" in err


class TestRibStub:
    def test_propose_validates(self) -> None:
        ok, err = _validate_rib_target({"sketch": "Sketch1", "face": [0, 0, 0.01]})
        assert ok is True

    def test_rejects_missing_sketch(self) -> None:
        ok, err = _validate_rib_target({"face": [0, 0, 0.01]})
        assert ok is False and "sketch" in err


class TestDomeStub:
    def test_propose_validates(self) -> None:
        ok, err = _validate_dome_target({"face": [0, 0, 0.01]})
        assert ok is True

    def test_rejects_bad_face(self) -> None:
        ok, err = _validate_dome_target({"face": [0, 0]})
        assert ok is False and "face" in err


class TestWrapStub:
    def test_propose_validates(self) -> None:
        ok, err = _validate_wrap_target({"sketch": "Sketch1", "face": [0, 0, 0.01]})
        assert ok is True

    def test_rejects_missing_sketch(self) -> None:
        ok, err = _validate_wrap_target({"face": [0, 0, 0.01]})
        assert ok is False and "sketch" in err


class TestBoundaryBossStub:
    def test_propose_validates(self) -> None:
        ok, err = _validate_boundary_target({
            "dir1_profiles": ["Sketch1"],
            "dir2_profiles": ["Sketch2"],
        })
        assert ok is True

    def test_rejects_empty_dir1(self) -> None:
        ok, err = _validate_boundary_target({
            "dir1_profiles": [],
            "dir2_profiles": ["Sketch2"],
        })
        assert ok is False and "dir1_profiles" in err


def _validate_sweep_cut_target(target: dict) -> tuple[bool, str | None]:
    """Validate sweep-cut target (profile + path sketch names)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    for pname in ("profile", "path"):
        if not isinstance(target.get(pname), str) or not target.get(pname):
            return False, f"sweep_cut target.{pname} must be a non-empty sketch name"
    return True, None


def _create_sweep_cut(
    doc: Any, target: dict
) -> tuple[bool, str | None]:
    """Create a sweep-cut feature.  # SEAT-PENDING (W0)

    Mirror of _create_sweep (swFmSweep=17) with swFmSweepCut=18.
    Same ISweepFeatureData interface; same marked select pipeline.

    NOTE: this offline stub uses doc.Extension directly (no typed_qi);
    the real handler in mutate.py will wrap with typed/typed_qi.
    """
    profile = target.get("profile")
    path = target.get("path")
    if not profile or not path:
        return False, "target must contain non-empty 'profile' and 'path'"
    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_SWEEP_CUT)
        if data is None:
            return False, "CreateDefinition returned None"
        ext = doc.Extension
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        if not ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0):
            return False, f"could not select profile sketch {profile!r}"
        if not ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0):
            return False, f"could not select path sketch {path!r}"
        feat = fm.CreateFeature(data)
        if feat is not None and not isinstance(feat, int):
            return True, None
        return False, (
            "CreateFeature did not materialize "
            "(the path sketch must leave the profile plane)"
        )
    except Exception as exc:
        return False, f"sweep-cut pipeline failed: {exc!r}"


def _validate_loft_target(target: dict) -> tuple[bool, str | None]:
    """Validate loft target (list of profile sketch names)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    profiles = target.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False, "loft target.profiles must be a non-empty list of sketch names"
    return True, None


def _validate_rib_target(target: dict) -> tuple[bool, str | None]:
    """Validate rib target (sketch name + face coord)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
        return False, "rib target.sketch must be a non-empty sketch name"
    face = target.get("face")
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "rib target.face must be a 3-element [x,y,z]"
    return True, None


def _validate_dome_target(target: dict) -> tuple[bool, str | None]:
    """Validate dome target (face coord)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    face = target.get("face")
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "dome target.face must be a 3-element [x,y,z]"
    return True, None


def _validate_wrap_target(target: dict) -> tuple[bool, str | None]:
    """Validate wrap target (sketch name + face coord)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
        return False, "wrap target.sketch must be a non-empty sketch name"
    face = target.get("face")
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "wrap target.face must be a 3-element [x,y,z]"
    return True, None


def _validate_boundary_target(target: dict) -> tuple[bool, str | None]:
    """Validate boundary-boss target (dir1 + dir2 profile lists)."""
    if not isinstance(target, dict):
        return False, "target must be a dict"
    for key in ("dir1_profiles", "dir2_profiles"):
        val = target.get(key)
        if not isinstance(val, list) or not val:
            return False, f"boundary target.{key} must be a non-empty list"
    return True, None


# ===========================================================================
# End-to-end propose-validation tests using real mutate.py (Wave-5 wiring)
# ===========================================================================

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import sw_propose_feature_add


class _FakeWave5Doc:
    """Minimal fake doc for propose-validation (no COM calls needed)."""

    def __init__(self, path: str) -> None:
        self._path = path

    def GetPathName(self) -> str:
        return self._path

    def GetTitle(self) -> str:
        return Path(self._path).name


def _patch_propose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, doc: Any) -> None:
    """Monkeypatch mutate.py for propose-only tests (no dry-run/COM)."""

    class _FakeSw:
        def OpenDoc6(self, path, *a: Any) -> tuple:
            return (doc, 0, 0)

    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    monkeypatch.setattr(mutate, "get_sw_app", lambda: _FakeSw())
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)


# ---------------------------------------------------------------------------
# F0 ref-geom: seat-GREEN PAE on live SW 2024 SP1 (3 of 4 kinds).
#   ref_plane / ref_axis / coordinate_system: propose->dry_run->commit all
#   GREEN; re-advertised in _SUPPORTED_FEATURE_TYPES.
#   ref_point: DEFERRED -- SelectByID(VERTEX) walls from out-of-process
#   Python. Its test still asserts the fail-close rejection.
# ---------------------------------------------------------------------------
class TestProposeRefPlane:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 50.0},
            {"plane": "Front Plane"},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_valid_edge_ref(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Normal-to-edge variant: a durable edge_ref, no plane/distance_mm.
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane"},
            {"edge_ref": {"persist_id": "AAAA", "length": 0.05}},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_rejects_missing_plane(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 50.0},
            {"unrelated": 1},
        )
        assert r["ok"] is False
        assert "plane" in r["error"]

    def test_rejects_non_positive_distance(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 0},
            {"plane": "Front Plane"},
        )
        assert r["ok"] is False
        assert "distance_mm" in r["error"]


class TestProposeRefAxis:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_axis"},
            {"planes": ["Front Plane", "Right Plane"]},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_rejects_wrong_plane_count(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_axis"},
            {"planes": ["Front Plane"]},
        )
        assert r["ok"] is False
        assert "planes" in r["error"]


class TestProposeCoordinateSystem:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "coordinate_system", "flip_x": False, "flip_y": False, "flip_z": False},
            {"origin": "Origin"},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None


class TestProposeRefPoint:
    """W5.3 Epic B: ref_point advertised via durable face_ref (face-centroid).

    Production-handler PAE GREEN (spike 40ea050). The legacy vertex-coordinate
    path still walls but is retained as a non-advertised fallback.
    """

    def test_valid_face_ref(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"face_ref": {"normal": [0, 0, 1], "centroid": [0, 0, 0.02], "area_mm2": 1600.0}},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_rejects_empty_face_ref(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"face_ref": {}},
        )
        assert r["ok"] is False
        assert "face_ref" in r["error"]

    def test_rejects_missing_target(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"unrelated": 1},
        )
        assert r["ok"] is False
        assert "face_ref" in r["error"] or "point" in r["error"]


class _FakeRefResolution:
    def __init__(self, entity: object, method: str = "persist_id") -> None:
        self.entity = entity
        self.method = method


class _FakeRefPointFm:
    """FeatureManager whose InsertReferencePoint(type,...) materializes."""

    def __init__(self, materialize: bool = True) -> None:
        self.materialize = materialize
        self.calls: list[tuple] = []

    def InsertReferencePoint(self, ptype, ref, dist, count):  # noqa: N802
        self.calls.append((ptype, ref, dist, count))
        if not self.materialize:
            return None
        return object()  # a non-None, non-int "Feature"


class _FakeRefPointDoc:
    def __init__(self, fm: _FakeRefPointFm) -> None:
        self.FeatureManager = fm

    def ClearSelection2(self, flag: bool) -> None:  # noqa: N802
        pass


class TestCreateRefPointHandler:
    """Direct handler tests for _create_ref_point (W5.3 Epic B face-centroid).

    ref_point stays DE-ADVERTISED (gated behind a production-handler PAE), so
    these exercise the wiring directly rather than through propose.
    """

    def test_face_ref_centroid_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fm = _FakeRefPointFm(materialize=True)
        doc = _FakeRefPointDoc(fm)
        sentinel_face = object()
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(sentinel_face),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda e: True)
        ok, err = mutate._create_ref_point(doc, {"type": "ref_point"}, {"face_ref": {"role": "top"}})
        assert ok is True
        assert err is None
        # type 4 = swRefPointTypeInCentreOfFace
        assert fm.calls == [(4, 0, 0.0, 1)]

    def test_face_ref_unresolved_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeRefPointDoc(_FakeRefPointFm())
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(None, method="none"),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda e: True)
        ok, err = mutate._create_ref_point(doc, {"type": "ref_point"}, {"face_ref": {"role": "x"}})
        assert ok is False
        assert "unresolved" in err

    def test_face_ref_select_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeRefPointDoc(_FakeRefPointFm())
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(object()),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda e: False)
        ok, err = mutate._create_ref_point(doc, {"type": "ref_point"}, {"face_ref": {"role": "x"}})
        assert ok is False
        assert "could not select" in err

    def test_no_target_fails_soft(self) -> None:
        doc = _FakeRefPointDoc(_FakeRefPointFm())
        ok, err = mutate._create_ref_point(doc, {"type": "ref_point"}, {})
        assert ok is False
        assert "face_ref" in err


class _FakeDomeFeatureManager:
    """FeatureManager exposing GetFeatures(True) -> list (len = feature count)."""

    def __init__(self, doc: "_FakeDomeDoc") -> None:
        self._doc = doc

    def GetFeatures(self, top_level: bool):  # noqa: N802, FBT001
        return ["f"] * self._doc._count


class _FakeDomeDoc:
    """Doc whose InsertDome bumps the feature count iff a face was selected.

    Mirrors the seat finding: InsertDome returns None even on success, so the
    handler must verify via a feature-count delta read from
    FeatureManager.GetFeatures(True) (NOT GetFeatureCount(), which is a
    non-callable property on the late-bound doc — the dome PAE exposed this).
    mark=1 selection is the trigger; modeled via the select flag.
    """

    def __init__(self, *, will_materialize: bool = True) -> None:
        self._count = 19
        self._will_materialize = will_materialize
        self.insert_args: tuple | None = None
        self.selected = False
        self.FeatureManager = _FakeDomeFeatureManager(self)

    def ForceRebuild3(self, flag: bool) -> None:  # noqa: N802
        pass

    def ClearSelection2(self, flag: bool) -> None:  # noqa: N802
        pass

    def InsertDome(self, height, reverse, elliptical):  # noqa: N802
        self.insert_args = (height, reverse, elliptical)
        # Models reality: returns None; bumps count only if selection + valid.
        if self._will_materialize and self.selected:
            self._count += 1
        return None


class TestCreateDomeHandler:
    """Direct handler tests for _create_dome (W6 T2 face-centroid + delta verify).

    Dome stays DE-ADVERTISED (gated behind a production-handler PAE), so these
    exercise the wiring directly rather than through propose.
    """

    def test_face_ref_green_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeDomeDoc(will_materialize=True)
        sentinel = object()

        def _sel(entity, *, append=False, mark=0):
            # mark=1 is the seat-proven trigger; only then mark "selected".
            if mark == 1:
                doc.selected = True
                return True
            return False

        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(sentinel),
        )
        monkeypatch.setattr(mutate, "select_entity", _sel)
        ok, err = mutate._create_dome(
            doc, {"type": "dome", "distance_mm": 10.0}, {"face_ref": {"role": "top"}}
        )
        assert ok is True
        assert err is None
        # 10 mm -> 0.01 m height, forward, round.
        assert doc.insert_args == (pytest.approx(0.01), False, False)

    def test_face_ref_no_delta_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeDomeDoc(will_materialize=False)
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(object()),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda e, *, append=False, mark=0: True)
        ok, err = mutate._create_dome(doc, {"type": "dome"}, {"face_ref": {"role": "x"}})
        assert ok is False
        assert "did not add a feature" in err

    def test_face_ref_unresolved_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeDomeDoc()
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, fr: _FakeRefResolution(None, method="none"),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda e, *, append=False, mark=0: True)
        ok, err = mutate._create_dome(doc, {"type": "dome"}, {"face_ref": {"role": "x"}})
        assert ok is False
        assert "unresolved" in err

    def test_no_target_fails_soft(self) -> None:
        doc = _FakeDomeDoc()
        ok, err = mutate._create_dome(doc, {"type": "dome"}, {})
        assert ok is False
        assert "face_ref" in err or "face" in err


# ---------------------------------------------------------------------------
# ref_plane normal-to-edge variant (W6 T6 v2, seat spike 13b35e3 = GREEN).
# Two-reference construction: vertex (Coincident, mark=0) + edge (Perpendicular,
# append mark=1) -> InsertRefPlane(4,0,2,0,0,0), delta-verified.
# ---------------------------------------------------------------------------
class _FakeEdgePlaneFm:
    def __init__(self, doc: "_FakeEdgePlaneDoc") -> None:
        self._doc = doc

    def GetFeatures(self, top_level: bool):  # noqa: N802, FBT001
        return ["f"] * self._doc._count

    def InsertRefPlane(self, c1, d1, c2, d2, c3, d3):  # noqa: N802
        self._doc.insert_args = (c1, d1, c2, d2, c3, d3)
        # Models reality: returns None/bare COMObject; bumps count only when
        # BOTH references were selected (vertex anchor + edge).
        if self._doc._will_materialize and self._doc.sel_vertex and self._doc.sel_edge:
            self._doc._count += 1
        return None


class _FakeEdge:
    def __init__(self, vertex: object) -> None:
        self._vertex = vertex

    def GetStartVertex(self):  # noqa: N802
        return self._vertex


class _FakeEdgePlaneDoc:
    def __init__(self, *, will_materialize: bool = True) -> None:
        self._count = 19
        self._will_materialize = will_materialize
        self.insert_args: tuple | None = None
        self.sel_vertex = False
        self.sel_edge = False
        self.FeatureManager = _FakeEdgePlaneFm(self)

    def ForceRebuild3(self, flag: bool) -> None:  # noqa: N802
        pass

    def ClearSelection2(self, flag: bool) -> None:  # noqa: N802
        pass


_VALID_EDGE_REF = {
    "persist_id": "AAAA",
    "start": [0.0, 0.0, 0.0],
    "end": [0.0, 0.0, 0.05],
    "length": 0.05,
}


class TestCreateRefPlaneNormalToEdge:
    """Direct handler tests for the normal-to-edge ref_plane variant.

    Stays DE-ADVERTISED until a production-handler PAE; these exercise the
    two-reference selection + delta verification wiring directly.
    """

    def test_edge_ref_green_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        doc = _FakeEdgePlaneDoc(will_materialize=True)
        vertex = object()
        edge = _FakeEdge(vertex)
        monkeypatch.setattr(
            mutate, "resolve_edge_ref",
            lambda d, ref: _FakeRefResolution(edge),
        )

        def _sel(entity, *, append=False, mark=0):
            if entity is vertex and mark == 0 and not append:
                doc.sel_vertex = True
                return True
            if entity is edge and mark == 1 and append:
                doc.sel_edge = True
                return True
            return False

        monkeypatch.setattr(mutate, "select_entity", _sel)
        ok, err = mutate._create_ref_plane(
            doc, {"type": "ref_plane"}, {"edge_ref": _VALID_EDGE_REF}
        )
        assert ok is True
        assert err is None
        # Coincident=4 (vertex slot), Perpendicular=2 (edge slot).
        assert doc.insert_args == (4, 0, 2, 0, 0, 0)

    def test_edge_ref_no_delta_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        doc = _FakeEdgePlaneDoc(will_materialize=False)
        edge = _FakeEdge(object())
        monkeypatch.setattr(
            mutate, "resolve_edge_ref", lambda d, ref: _FakeRefResolution(edge),
        )
        monkeypatch.setattr(
            mutate, "select_entity", lambda e, *, append=False, mark=0: True,
        )
        ok, err = mutate._create_ref_plane(
            doc, {"type": "ref_plane"}, {"edge_ref": _VALID_EDGE_REF}
        )
        assert ok is False
        assert "did not materialize" in err

    def test_edge_ref_unresolved_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        doc = _FakeEdgePlaneDoc()
        monkeypatch.setattr(
            mutate, "resolve_edge_ref",
            lambda d, ref: _FakeRefResolution(None, method="none"),
        )
        ok, err = mutate._create_ref_plane(
            doc, {"type": "ref_plane"}, {"edge_ref": _VALID_EDGE_REF}
        )
        assert ok is False
        assert "unresolved" in err

    def test_edge_ref_no_start_vertex_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        doc = _FakeEdgePlaneDoc()
        edge = _FakeEdge(None)  # GetStartVertex -> None
        monkeypatch.setattr(
            mutate, "resolve_edge_ref", lambda d, ref: _FakeRefResolution(edge),
        )
        ok, err = mutate._create_ref_plane(
            doc, {"type": "ref_plane"}, {"edge_ref": _VALID_EDGE_REF}
        )
        assert ok is False
        assert "start vertex" in err


# ---------------------------------------------------------------------------
# edge_flange — Wave-7 T6 custom-profile (seat spike 1897670 = GREEN).
# Monolithic handler: resolve edge -> normal-edge plane -> profile line ->
# SAFEARRAY InsertSheetMetalEdgeFlange2. DE-ADVERTISED pending production PAE,
# so these exercise the handler directly + assert propose fails closed.
# ---------------------------------------------------------------------------
class _FF:
    """Minimal fake IFeature: Name + GetTypeName2."""

    def __init__(self, name: str, tname: str) -> None:
        self.Name = name
        self._t = tname

    def GetTypeName2(self) -> str:  # noqa: N802
        return self._t


class _FakeEFEdge:
    def __init__(self, vertex: object) -> None:
        self._v = vertex

    def GetStartVertex(self):  # noqa: N802
        return self._v


class _FakeEFExt:
    def __init__(self, edge: object) -> None:
        self._edge = edge

    def GetObjectByPersistReference3(self, pid: bytes):  # noqa: N802
        return self._edge


class _FakeEFSketchMgr:
    def __init__(self, doc: "_FakeEdgeFlangeDoc") -> None:
        self._doc = doc

    def CreateLine(self, *a):  # noqa: N802
        self._doc.line_args = a
        return None


class _FakeEFFm:
    def __init__(self, doc: "_FakeEdgeFlangeDoc") -> None:
        self._doc = doc

    def GetFeatures(self, top: bool):  # noqa: N802, FBT001
        return list(self._doc._feats)

    def InsertRefPlane(self, *a):  # noqa: N802
        self._doc.plane_args = a
        self._doc._plane_built = True
        self._doc._feats.append(_FF("Plane1", "RefPlane"))
        return None

    def InsertSheetMetalEdgeFlange2(self, *a):  # noqa: N802
        self._doc.flange_args = a
        if (self._doc._will_materialize and self._doc._plane_built
                and self._doc._sketch_built):
            self._doc._feats.append(_FF("Edge-Flange1", "EdgeFlange"))
        return None


class _FakeEdgeFlangeDoc:
    """Models the seat: InsertRefPlane/InsertSheetMetalEdgeFlange2 return None and
    bump the feature list; the flange only materializes when plane+sketch exist."""

    def __init__(self, *, will_materialize: bool = True) -> None:
        self._feats = [_FF("Sketch1", "ProfileFeature"), _FF("Base-Flange1", "SMBaseFlange")]
        self._will_materialize = will_materialize
        self._plane_built = False
        self._sketch_built = False
        self.plane_args: tuple | None = None
        self.flange_args: tuple | None = None
        self.line_args: tuple | None = None
        self._vertex = object()
        self._edge = _FakeEFEdge(self._vertex)
        self.Extension = _FakeEFExt(self._edge)
        self.FeatureManager = _FakeEFFm(self)
        self.SketchManager = _FakeEFSketchMgr(self)

    def ForceRebuild3(self, flag: bool) -> None:  # noqa: N802
        pass

    def ClearSelection2(self, flag: bool) -> None:  # noqa: N802
        pass

    def SelectByID(self, *a) -> bool:  # noqa: N802
        return True

    def InsertSketch2(self, flag: bool) -> None:  # noqa: N802, FBT001
        if not flag:  # closing the sketch adds the profile feature
            self._feats.append(_FF("Sketch7", "ProfileFeature"))
            self._sketch_built = True
        return None


_EF_TARGET = {
    "edge_ref": {
        "persist_id": "AAAA", "start": [0.0, 0.0, 0.0],
        "end": [0.0, 0.0, 0.05], "length": 0.05,
    }
}


class TestCreateEdgeFlangeHandler:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, doc: _FakeEdgeFlangeDoc) -> None:
        _patch_com_imports(monkeypatch)
        monkeypatch.setattr(
            mutate, "resolve_edge_ref", lambda d, ref: _FakeRefResolution(doc._edge)
        )
        monkeypatch.setattr(mutate, "read_persist_reference", lambda d, e: b"pid")
        monkeypatch.setattr(
            mutate, "select_entity", lambda e, *, append=False, mark=0: True
        )
        monkeypatch.setattr(mutate, "VARIANT", lambda vt, val: ("V", vt, val))

    def test_green_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeEdgeFlangeDoc(will_materialize=True)
        self._patch(monkeypatch, doc)
        ok, err = mutate._create_edge_flange(
            doc, {"type": "edge_flange", "height_mm": 10}, _EF_TARGET
        )
        assert ok is True
        assert err is None
        # default angle 90deg / radius 2mm; proven fixed args carried.
        assert doc.flange_args[2] == 129  # BooleanOptions
        assert doc.flange_args[3] == pytest.approx(math.radians(90))
        assert doc.flange_args[4] == pytest.approx(0.002)
        assert doc.flange_args[5] == 1  # BendPosition MaterialInside
        # profile line drawn to the 10 mm flange height.
        assert doc.line_args[4] == pytest.approx(0.010)

    def test_flange_noop_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Plane+sketch build, but the flange call no-ops -> must NOT report success
        # off the plane/sketch delta (the bug the count-around-the-flange guards).
        doc = _FakeEdgeFlangeDoc(will_materialize=False)
        self._patch(monkeypatch, doc)
        ok, err = mutate._create_edge_flange(
            doc, {"type": "edge_flange", "height_mm": 10}, _EF_TARGET
        )
        assert ok is False
        assert "did not materialize" in err

    def test_edge_unresolved_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        doc = _FakeEdgeFlangeDoc()
        _patch_com_imports(monkeypatch)
        monkeypatch.setattr(
            mutate, "resolve_edge_ref",
            lambda d, ref: _FakeRefResolution(None, method="none"),
        )
        ok, err = mutate._create_edge_flange(
            doc, {"type": "edge_flange", "height_mm": 10}, _EF_TARGET
        )
        assert ok is False
        assert "unresolved" in err

    def test_rejects_non_positive_height(self) -> None:
        doc = _FakeEdgeFlangeDoc()
        ok, err = mutate._create_edge_flange(
            doc, {"type": "edge_flange", "height_mm": 0}, _EF_TARGET
        )
        assert ok is False
        assert "height_mm" in err

    def test_rejects_missing_edge_ref(self) -> None:
        doc = _FakeEdgeFlangeDoc()
        ok, err = mutate._create_edge_flange(
            doc, {"type": "edge_flange", "height_mm": 10}, {}
        )
        assert ok is False
        assert "edge_ref" in err


class TestProposeEdgeFlangeDeadvertised:
    def test_propose_fails_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # edge_flange is NOT in _SUPPORTED_FEATURE_TYPES until the PAE clears it.
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file), {"type": "edge_flange", "height_mm": 10}, _EF_TARGET
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]


class TestCreateSweepCutHandler:
    """Direct tests for the PRODUCTION mutate._create_sweep_cut (W6 T4).

    Distinct from TestDryRunSweepCut, which exercises a test-local mirror.
    Verifies the delta-based detection: CreateFeature may return None even on
    success, so materialization is read from GetFeatures(True), not the return.
    """

    def test_green_delta_with_none_return(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        # CreateFeature returns None but the feature count bumps -> GREEN.
        fm = _FakeSweepCutFm(create_feat_ret=None, materializes=True)
        doc = _FakeSweepCutDoc(fm)
        ok, err = mutate._create_sweep_cut(
            doc, {"type": "sweep_cut"}, {"profile": "Sketch2", "path": "Sketch3"}
        )
        assert ok is True
        assert err is None
        assert fm.create_def_calls == [mutate._SW_FM_SWEEP_CUT]

    def test_no_delta_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        # CreateFeature returns a non-None object but NO feature appears (the
        # path didn't pierce the solid) -> must still fail on the delta.
        fm = _FakeSweepCutFm(create_feat_ret=object(), materializes=False)
        doc = _FakeSweepCutDoc(fm)
        ok, err = mutate._create_sweep_cut(
            doc, {"type": "sweep_cut"}, {"profile": "Sketch2", "path": "Sketch3"}
        )
        assert ok is False
        assert "did not materialize" in err

    def test_missing_path_fails_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_com_imports(monkeypatch)
        fm = _FakeSweepCutFm()
        doc = _FakeSweepCutDoc(fm)
        ok, err = mutate._create_sweep_cut(doc, {"type": "sweep_cut"}, {"profile": "Sketch2"})
        assert ok is False
        assert "profile" in err and "path" in err


class TestProposeSweepCut_Advertised:
    """W6 T4: sweep_cut advertised (13th kind). Recipe seat-GREEN (spike
    b5d1174); the prior WALL was a geometry constraint (path must pierce the
    solid), not an API wall."""

    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "sweep_cut"},
            {"profile": "Sketch2", "path": "Sketch3"},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_rejects_missing_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "sweep_cut"},
            {"profile": "Sketch2"},
        )
        assert r["ok"] is False
        assert "path" in r["error"]


class TestProposeLoft:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "loft"},
            {"profiles": ["Sketch1", "Sketch2"]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "loft" in r["error"]

    def test_rejects_single_profile(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "loft"},
            {"profiles": ["Sketch1"]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "loft" in r["error"]


class TestProposeRib:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "rib"},
            {"sketch": "Sketch1", "face": [0, 0, 0.01]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "rib" in r["error"]


class TestProposeDome:
    """W6 T2: dome advertised via durable face_ref. Production-handler PAE GREEN
    (spike e44711f). Legacy face-coord path is a non-advertised fallback."""

    def test_valid_face_ref(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "dome", "distance_mm": 10.0},
            {"face_ref": {"normal": [0, 0, 1], "centroid": [0, 0, 0.02], "area_mm2": 1600.0}},
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_rejects_empty_face_ref(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "dome"},
            {"face_ref": {}},
        )
        assert r["ok"] is False
        assert "face_ref" in r["error"]

    def test_rejects_missing_target(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "dome"},
            {"unrelated": 1},
        )
        assert r["ok"] is False
        assert "face_ref" in r["error"] or "face" in r["error"]


class TestProposeWrap:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "wrap"},
            {"sketch": "Sketch1", "face": [0, 0, 0.01]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "wrap" in r["error"]


class TestProposeBoundaryBoss:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "boundary_boss"},
            {"dir1_profiles": ["Sketch1"], "dir2_profiles": ["Sketch2"]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "boundary_boss" in r["error"]

    def test_rejects_empty_dir1(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "boundary_boss"},
            {"dir1_profiles": [], "dir2_profiles": ["Sketch2"]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "boundary_boss" in r["error"]

