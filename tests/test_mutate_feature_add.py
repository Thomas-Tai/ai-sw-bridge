"""Tests for the feature_add proposal kind in mutate.py.

Mocks the COM seam so tests run without a SOLIDWORKS seat.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import (
    ST_COMMITTED,
    ST_DRY_RUN_BROKE,
    ST_DRY_RUN_OK,
    ST_PROPOSED,
    ProposalStore,
    sw_commit_feature_add,
    sw_dry_run_feature_add,
    sw_propose_feature_add,
)


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeEntity:
    def __init__(self) -> None:
        self.select_calls: list[tuple[bool, int]] = []

    def Select2(self, append: bool, mark: int) -> bool:
        self.select_calls.append((append, mark))
        return True


class _FakeFilletData:
    def __init__(self) -> None:
        self.init_calls: list[int] = []
        self.default_radius: float | None = None

    def Initialize(self, t: int) -> None:
        self.init_calls.append(t)

    @property
    def DefaultRadius(self) -> float:
        return self.default_radius or 0.0

    @DefaultRadius.setter
    def DefaultRadius(self, v: float) -> None:
        self.default_radius = v


class _FakeFeatureManager:
    def __init__(self, fillet_data: _FakeFilletData, feature: Any) -> None:
        self._fillet_data = fillet_data
        self._feature = feature
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list[Any] = []

    def CreateDefinition(self, t: int) -> Any:
        self.create_def_calls.append(t)
        return self._fillet_data

    def CreateFeature(self, fd: Any) -> Any:
        self.create_feat_calls.append(fd)
        return self._feature


class _FakeDoc:
    def __init__(self, path: str, fm: _FakeFeatureManager) -> None:
        self._path = path
        self.FeatureManager = fm
        self.save_calls: list[tuple] = []
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


class _FakeSldWorks:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc
        self.close_calls: list[str] = []

    def OpenDoc6(self, path: str, t: int, opts: int, cfg: str, e: int, w: int) -> tuple:
        return (self._doc, 0, 0)

    def CloseDoc(self, title: str) -> None:
        self.close_calls.append(title)


class _FakeRefResolution:
    def __init__(self, entity: Any) -> None:
        self.entity = entity
        self.method = "persist_id" if entity is not None else "unresolved"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_VALID_TARGET = {
    "start": [0.0, 0.0, 0.0],
    "end": [0.1, 0.0, 0.0],
    "length": 0.1,
    "persist_id": "AQID",
}

_VALID_FEATURE = {"type": "fillet_constant_radius", "radius_mm": 2.0}


def _patch_all(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    doc_path: str,
    entity: Any,
    feature: Any,
):
    """Wire up all fakes and return a dict of handles for assertions."""
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")

    fd = _FakeFilletData()
    fm = _FakeFeatureManager(fd, feature)
    doc = _FakeDoc(doc_path, fm)
    sw = _FakeSldWorks(doc)
    fake_entity = entity

    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
    monkeypatch.setattr(mutate, "get_active_doc", lambda sw_: None)
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(
        mutate,
        "resolve_edge_ref",
        lambda doc_, ref: _FakeRefResolution(fake_entity),
    )
    monkeypatch.setattr(
        mutate, "select_entity", lambda e, **kw: True
    )

    return {
        "sw": sw,
        "doc": doc,
        "fm": fm,
        "fd": fd,
        "entity": fake_entity,
    }


# ---------------------------------------------------------------------------
# Propose tests
# ---------------------------------------------------------------------------


class TestProposeFeatureAdd:
    def test_writes_record_no_sw(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(str(doc), _VALID_FEATURE, _VALID_TARGET)

        assert r["ok"] is True
        assert r["proposal_id"] is not None
        assert r["state"] == ST_PROPOSED

        rec = json.loads(
            (tmp_path / "proposals" / f"{r['proposal_id']}.json").read_text()
        )
        assert rec["kind"] == "feature_add"
        assert rec["feature"] == _VALID_FEATURE
        assert rec["target"] == _VALID_TARGET

        # No COM calls — propose touches no SW.
        assert fakes["sw"].close_calls == []
        assert fakes["fm"].create_def_calls == []

    def test_rejects_unsupported_type(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(
            str(doc), {"type": "chamfer", "radius_mm": 1.0}, _VALID_TARGET
        )
        assert r["ok"] is False
        assert "unsupported" in r["error"]

    def test_rejects_bad_radius(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(
            str(doc),
            {"type": "fillet_constant_radius", "radius_mm": -1},
            _VALID_TARGET,
        )
        assert r["ok"] is False
        assert "radius_mm" in r["error"]

    def test_rejects_missing_doc_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_all(monkeypatch, tmp_path, "/no/such.sldprt", _FakeEntity(), object())

        r = sw_propose_feature_add(
            "/no/such.sldprt", _VALID_FEATURE, _VALID_TARGET
        )
        assert r["ok"] is False
        assert "does not exist" in r["error"]


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


class TestDryRunFeatureAdd:
    def _propose(self, tmp_path: Path, doc_path: str) -> str:
        r = sw_propose_feature_add(doc_path, _VALID_FEATURE, _VALID_TARGET)
        return r["proposal_id"]

    def test_ok_no_save(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        pid = self._propose(tmp_path, str(doc))

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        assert fakes["fm"].create_def_calls == [1]
        assert len(fakes["fm"].create_feat_calls) == 1
        # No save — rollback via CloseDoc only.
        assert fakes["doc"].save_calls == []
        assert len(fakes["sw"].close_calls) == 1

    def test_unresolved_edge_broke(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), None, object())
        pid = self._propose(tmp_path, str(doc))

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is False
        assert r["state"] == ST_DRY_RUN_BROKE
        assert "unresolved" in r["error"]
        assert fakes["fm"].create_feat_calls == []
        assert fakes["doc"].save_calls == []


# ---------------------------------------------------------------------------
# Commit tests
# ---------------------------------------------------------------------------


class TestCommitFeatureAdd:
    def _propose_and_dry_run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        doc_path: str,
        entity: Any,
        feature: Any,
    ) -> str:
        fakes = _patch_all(monkeypatch, tmp_path, doc_path, entity, feature)
        r = sw_propose_feature_add(doc_path, _VALID_FEATURE, _VALID_TARGET)
        pid = r["proposal_id"]
        sw_dry_run_feature_add(pid)
        # Re-patch after dry_run (state persists on disk, fakes still wired).
        return pid, fakes

    def test_refuses_unless_dry_run_ok(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(str(doc), _VALID_FEATURE, _VALID_TARGET)

        cr = sw_commit_feature_add(r["proposal_id"])

        assert cr["ok"] is False
        assert "refusing" in cr["error"]

    def test_saves_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        pid, fakes = self._propose_and_dry_run(
            monkeypatch, tmp_path, str(doc), _FakeEntity(), object()
        )

        # Reset counters after dry_run.
        fakes["doc"].save_calls.clear()
        fakes["sw"].close_calls.clear()
        fakes["fm"].create_feat_calls.clear()

        r = sw_commit_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_COMMITTED
        assert r["doc_saved"] is True
        assert len(fakes["doc"].save_calls) == 1
        assert len(fakes["fm"].create_feat_calls) == 1


# ---------------------------------------------------------------------------
# ProposalStore facade tests
# ---------------------------------------------------------------------------


class TestProposalStoreFeatureAdd:
    def test_facade(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        store = ProposalStore()
        r = store.propose_feature_add(str(doc), _VALID_FEATURE, _VALID_TARGET)
        assert r["ok"] is True

        pid = r["proposal_id"]
        dr = store.dry_run_feature_add(pid)
        assert dr["ok"] is True

        fakes["doc"].save_calls.clear()
        cr = store.commit_feature_add(pid)
        assert cr["ok"] is True
        assert len(fakes["doc"].save_calls) == 1


# ---------------------------------------------------------------------------
# _save_doc — late-bound Save() return-value handling
# ---------------------------------------------------------------------------


class _SaveReturningDoc:
    """Doc whose Save() returns a configurable value (still counts calls)."""

    def __init__(self, ret: Any) -> None:
        self._ret = ret
        self.save_calls: list[tuple] = []

    def Save(self) -> Any:
        self.save_calls.append(())
        return self._ret


class TestSaveDoc:
    def test_none_return_is_success(self) -> None:
        # The actual bug: late-bound pywin32 swallows Save()'s S_OK bool as
        # None, which must NOT be reported as a failed save.
        doc = _SaveReturningDoc(None)
        assert mutate._save_doc(doc) is True
        assert len(doc.save_calls) == 1

    def test_true_return_is_success(self) -> None:
        assert mutate._save_doc(_SaveReturningDoc(True)) is True

    def test_explicit_false_is_failure(self) -> None:
        assert mutate._save_doc(_SaveReturningDoc(False)) is False

    def test_commit_reports_saved_when_save_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # End-to-end through commit: a None-returning Save must still set
        # doc_saved True (the file is written; only the retval was dropped).
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(str(doc), _VALID_FEATURE, _VALID_TARGET)
        pid = r["proposal_id"]
        sw_dry_run_feature_add(pid)

        # Swap in a Save() that returns None, as late binding does on S_OK.
        monkeypatch.setattr(fakes["doc"], "Save", lambda: None)

        cr = sw_commit_feature_add(pid)
        assert cr["ok"] is True
        assert cr["doc_saved"] is True
