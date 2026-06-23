"""W41 body-ops offline coverage.

``delete_body`` is the single SHIPPED W41 ``feature_add`` kind (S1 GREEN on the
live seat: 2 disjoint bodies 1800+4000 mm³ -> delete body[1] -> 1 body
1800 mm³, the W21 volume-delta gate).  These tests mirror the live recipe with
fakes — they do NOT touch COM:

  * ``GetBodies2`` enumeration + per-body ``GetMassProperties(1.0)[3]`` volume
    (the seat fix: a body has GetMassProperties, NOT CreateMassProperty).
  * body selection via ``Extension.SelectByID2(name, "SOLIDBODY", …)``.
  * ``InsertDeleteBody2(False)`` (ONE arg) + body-count-delta verification
    (a no-op that leaves the count unchanged must FAIL, never report success).

``combine`` and ``split`` are characterized-but-NOT-advertised (see
docs/DEFERRED.md Wave-41).  The fail-closed tests pin that propose rejects them
with "unsupported feature type" so a regression can't silently re-advertise a
non-materializing kind (the edge-flange / loft precedent).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge import features, mutate
from ai_sw_bridge.features import body_ops
from ai_sw_bridge.mutate import _sw_propose_feature_add_impl


# ---------------------------------------------------------------------------
# Fakes — a multi-body part doc with the seat-proven member surface.
# ---------------------------------------------------------------------------
class _FakeBody:
    def __init__(self, name: str, volume_m3: float) -> None:
        self.Name = name
        self._vol = volume_m3

    def GetMassProperties(self, density: float) -> list[float]:
        # [cx, cy, cz, volume, area, mass, ...] — element [3] is volume (m³).
        return [0.0, 0.0, 0.0, self._vol, 0.0, self._vol * density]


class _FakeExtension:
    def __init__(self, doc: "_FakeBodyDoc") -> None:
        self._doc = doc

    def SelectByID2(self, name, kind, *a: Any) -> bool:
        # Seat-proven: only "SOLIDBODY" addresses a body for InsertDeleteBody2.
        if kind != "SOLIDBODY":
            return False
        if name not in {b.Name for b in self._doc._bodies}:
            return False
        self._doc._selected = name
        return True


class _FakeFeatureManager:
    def __init__(self, doc: "_FakeBodyDoc", will_delete: bool) -> None:
        self._doc = doc
        self._will_delete = will_delete

    def InsertDeleteBody2(self, keep_bodies: bool) -> Any:
        # The live call is 1-arg; a 2-arg form raises on the seat. Mirror the
        # real effect: drop the currently-selected body (when the op "takes").
        if self._will_delete and self._doc._selected is not None:
            self._doc._bodies = [
                b for b in self._doc._bodies if b.Name != self._doc._selected
            ]
        return object()  # IFeature may be returned even when it no-ops


class _FakeBodyDoc:
    def __init__(self, bodies: list[_FakeBody], will_delete: bool = True) -> None:
        self._bodies = list(bodies)
        self._selected: str | None = None
        self.Extension = _FakeExtension(self)
        self.FeatureManager = _FakeFeatureManager(self, will_delete)

    # GetBodies2 present -> the handler skips the IPartDoc QI (hasattr True).
    def GetBodies2(self, body_type: int, visible_only: bool) -> list[_FakeBody]:
        return list(self._bodies)

    def ForceRebuild3(self, top_only: bool) -> bool:
        return True

    def ClearSelection2(self, all_sel: bool) -> bool:
        self._selected = None
        return True


@pytest.fixture
def _patch_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    # typed() is identity (fake Extension already exposes SelectByID2);
    # wrapper_module() is never dereferenced past being passed to typed().
    monkeypatch.setattr(body_ops, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(body_ops, "wrapper_module", lambda: object())


def _two_bodies(will_delete: bool = True) -> _FakeBodyDoc:
    # 1800 mm³ (1.8e-6 m³) + 4000 mm³ (4.0e-6 m³) — the S1 fixture volumes.
    return _FakeBodyDoc(
        [_FakeBody("Body1", 1.8e-6), _FakeBody("Body2", 4.0e-6)],
        will_delete=will_delete,
    )


# ---------------------------------------------------------------------------
# _get_body_count_and_volumes — GetMassProperties[3] volume (the seat fix).
# ---------------------------------------------------------------------------
class TestBodyCountAndVolumes:
    def test_count_and_per_body_volume_mm3(self, _patch_helpers: None) -> None:
        doc = _two_bodies()
        count, vols = body_ops._get_body_count_and_volumes(doc)
        assert count == 2
        assert vols == pytest.approx([1800.0, 4000.0])  # m³ -> mm³ (×1e9)

    def test_empty_doc_returns_zero_none(self, _patch_helpers: None) -> None:
        count, vols = body_ops._get_body_count_and_volumes(_FakeBodyDoc([]))
        assert count == 0
        assert vols == []


# ---------------------------------------------------------------------------
# _create_delete_body — the SHIPPED handler.
# ---------------------------------------------------------------------------
class TestDeleteBodyHandler:
    def test_green_delta_by_index(self, _patch_helpers: None) -> None:
        doc = _two_bodies()
        ok, err = body_ops._create_delete_body(
            doc, {"type": "delete_body"}, {"body_index": 1}
        )
        assert ok is True
        assert err is None
        assert {b.Name for b in doc._bodies} == {"Body1"}  # Body2 dropped

    def test_green_delta_by_name(self, _patch_helpers: None) -> None:
        doc = _two_bodies()
        ok, err = body_ops._create_delete_body(
            doc, {"type": "delete_body"}, {"body_name": "Body1"}
        )
        assert ok is True
        assert {b.Name for b in doc._bodies} == {"Body2"}

    def test_noop_fails_soft(self, _patch_helpers: None) -> None:
        # InsertDeleteBody2 returns a feature but the count never drops -> the
        # handler must NOT report success off the non-None return (W21 gate).
        doc = _two_bodies(will_delete=False)
        ok, err = body_ops._create_delete_body(
            doc, {"type": "delete_body"}, {"body_index": 1}
        )
        assert ok is False
        assert "did not reduce body count" in err

    def test_requires_two_bodies(self, _patch_helpers: None) -> None:
        doc = _FakeBodyDoc([_FakeBody("Body1", 1.8e-6)])
        ok, err = body_ops._create_delete_body(
            doc, {"type": "delete_body"}, {"body_index": 0}
        )
        assert ok is False
        assert ">= 2 bodies" in err

    def test_missing_target_rejected(self, _patch_helpers: None) -> None:
        ok, err = body_ops._create_delete_body(_two_bodies(), {"type": "delete_body"}, {})
        assert ok is False
        assert "body_index" in err and "body_name" in err

    def test_unselectable_body_fails_soft(self, _patch_helpers: None) -> None:
        doc = _two_bodies()
        ok, err = body_ops._create_delete_body(
            doc, {"type": "delete_body"}, {"body_name": "NoSuchBody"}
        )
        assert ok is False
        assert "could not select target body" in err

    def test_negative_index_rejected(self, _patch_helpers: None) -> None:
        ok, err = body_ops._create_delete_body(
            _two_bodies(), {"type": "delete_body"}, {"body_index": -1}
        )
        assert ok is False
        assert "non-negative" in err


# ---------------------------------------------------------------------------
# propose — delete_body advertised; combine/split fail-closed.
# ---------------------------------------------------------------------------
class _FakeProposeDoc:
    def __init__(self, path: str) -> None:
        self._path = path

    def GetPathName(self) -> str:
        return self._path

    def GetTitle(self) -> str:
        return Path(self._path).name


def _patch_propose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, doc: Any) -> None:
    class _FakeSw:
        def OpenDoc6(self, path, *a: Any) -> tuple:
            return (doc, 0, 0)

    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    monkeypatch.setattr(mutate, "get_sw_app", lambda: _FakeSw())
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)


class TestProposeDeleteBody:
    def test_delete_body_is_supported(self) -> None:
        assert "delete_body" in features.HANDLER_REGISTRY
        assert "delete_body" not in mutate._SUPPORTED_FEATURE_TYPES

    def test_propose_accepts_body_index(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        r = _sw_propose_feature_add_impl(
            str(doc_file), {"type": "delete_body"}, {"body_index": 1}
        )
        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["error"] is None

    def test_propose_accepts_body_name(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        r = _sw_propose_feature_add_impl(
            str(doc_file), {"type": "delete_body"}, {"body_name": "Body2"}
        )
        assert r["ok"] is True

    def test_propose_rejects_missing_target(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        # Non-empty target missing both keys -> the delete_body-specific branch
        # (an empty {} is caught earlier by the generic non-empty-dict guard).
        r = _sw_propose_feature_add_impl(
            str(doc_file), {"type": "delete_body"}, {"unrelated": 1}
        )
        assert r["ok"] is False
        assert "body_index" in r["error"] and "body_name" in r["error"]

    def test_propose_rejects_negative_index(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        r = _sw_propose_feature_add_impl(
            str(doc_file), {"type": "delete_body"}, {"body_index": -2}
        )
        assert r["ok"] is False
        assert "non-negative" in r["error"]


class TestCombineSplitFailClosed:
    """combine/split are characterized dead code — propose must reject them as
    unsupported (docs/DEFERRED.md Wave-41). Pins the fail-closed contract."""

    def test_combine_not_advertised(self) -> None:
        assert "combine" not in mutate._SUPPORTED_FEATURE_TYPES
        assert "combine" not in features.HANDLER_REGISTRY

    def test_split_not_advertised(self) -> None:
        assert "split" not in mutate._SUPPORTED_FEATURE_TYPES
        assert "split" not in features.HANDLER_REGISTRY

    def test_propose_combine_fails_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        r = _sw_propose_feature_add_impl(
            str(doc_file),
            {"type": "combine", "operation": "subtract"},
            {"main_body_index": 0, "tool_body_indices": [1]},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]

    def test_propose_split_fails_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeProposeDoc(str(doc_file)))
        r = _sw_propose_feature_add_impl(
            str(doc_file),
            {"type": "split"},
            {"body_index": 0, "cutting_plane": "RefPlane1"},
        )
        assert r["ok"] is False
        assert "unsupported feature type" in r["error"]
