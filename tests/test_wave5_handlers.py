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
    def __init__(self, create_feat_ret: Any = object()) -> None:
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list = []
        self._feat_ret = create_feat_ret

    def CreateDefinition(self, const: int) -> Any:
        self.create_def_calls.append(const)
        return object()

    def CreateFeature(self, data: Any) -> Any:
        self.create_feat_calls.append(data)
        return self._feat_ret


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
# F0 ref-geom: PAE-gated, NOT advertised yet (W0 directive).
# The handlers are wired and the recipe is seat-proven at the spike level
# (W3 S-REFGEOM PASS), but the production handlers have not had a fresh
# gold-standard PAE. Until that PAE is GREEN these kinds fail closed at
# propose, so the propose-validation tests assert rejection (mirroring the
# F1–F6 deferred pattern). The original "test_valid" / param-validation tests
# live in merge commit d7d43e6 and should be restored when ref_plane/ref_axis/
# coordinate_system/ref_point are re-added to _SUPPORTED_FEATURE_TYPES.
# ---------------------------------------------------------------------------
class TestProposeRefPlane:
    def test_deferred_unsupported(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 50.0},
            {"plane": "Front Plane"},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "ref_plane" in r["error"]


class TestProposeRefAxis:
    def test_deferred_unsupported(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_axis"},
            {"planes": ["Front Plane", "Right Plane"]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "ref_axis" in r["error"]


class TestProposeCoordinateSystem:
    def test_deferred_unsupported(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "coordinate_system"},
            {"origin": [0, 0, 0]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "coordinate_system" in r["error"]


class TestProposeRefPoint:
    def test_deferred_unsupported(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"point": [0.01, 0.01, 0.01]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "ref_point" in r["error"]


class TestProposeSweepCut:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "sweep_cut"},
            {"profile": "Sketch1", "path": "Sketch2"},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "sweep_cut" in r["error"]

    def test_rejects_missing_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "sweep_cut"},
            {"profile": "Sketch1"},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "sweep_cut" in r["error"]


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
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "dome"},
            {"face": [0, 0, 0.01]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
        assert "dome" in r["error"]


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

