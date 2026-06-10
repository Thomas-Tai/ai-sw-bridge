"""Tests for the feature_add proposal kind in mutate.py.

Mocks the COM seam so tests run without a SOLIDWORKS seat.
"""

from __future__ import annotations

import json
import math
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


class _FakeBaseFlangeData:
    def __init__(self) -> None:
        self.thickness: float | None = None
        self.bend_radius: float | None = None

    @property
    def Thickness(self) -> float:
        return self.thickness or 0.0

    @Thickness.setter
    def Thickness(self, v: float) -> None:
        self.thickness = v

    @property
    def BendRadius(self) -> float:
        return self.bend_radius or 0.0

    @BendRadius.setter
    def BendRadius(self, v: float) -> None:
        self.bend_radius = v


class _FakeVarFilletData:
    """Multi-radius fillet data: tracks Initialize/IsMultipleRadius and the
    per-item SetRadius calls. ``n_items`` is what FilletItemsCount reports."""

    def __init__(self, n_items: int) -> None:
        self.n_items = n_items
        self.init_calls: list[int] = []
        self.default_radius: float | None = None
        self.is_multiple: bool | None = None
        self.set_radii: list[tuple] = []
        self.access_calls: list[tuple] = []

    def Initialize(self, t: int) -> None:
        self.init_calls.append(t)

    @property
    def DefaultRadius(self) -> float:
        return self.default_radius or 0.0

    @DefaultRadius.setter
    def DefaultRadius(self, v: float) -> None:
        self.default_radius = v

    @property
    def IsMultipleRadius(self) -> bool:
        return bool(self.is_multiple)

    @IsMultipleRadius.setter
    def IsMultipleRadius(self, v: bool) -> None:
        self.is_multiple = v

    def AccessSelections(self, doc: Any, comp: Any) -> bool:
        self.access_calls.append((doc, comp))
        return True

    @property
    def FilletItemsCount(self) -> int:
        return self.n_items

    def GetFilletItemAtIndex(self, i: int) -> tuple:
        return ("item", i)

    def SetRadius(self, item: Any, radius: float) -> None:
        self.set_radii.append((item, radius))


class _FakeVarFilletFeature:
    """Created multi-radius fillet feature: GetDefinition returns the data,
    ModifyDefinition records the call."""

    def __init__(self, defn: Any) -> None:
        self._defn = defn
        self.modify_calls: list[tuple] = []
        self.Name = "Fillet1"

    def GetDefinition(self) -> Any:
        return self._defn

    def ModifyDefinition(self, defn: Any, doc: Any, comp: Any) -> bool:
        self.modify_calls.append((defn, doc, comp))
        return True


class _FakeFeatureManager:
    def __init__(self, data: Any, feature: Any) -> None:
        self._data = data
        self._feature = feature
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list[Any] = []

    def CreateDefinition(self, t: int) -> Any:
        self.create_def_calls.append(t)
        return self._data

    def CreateFeature(self, fd: Any) -> Any:
        self.create_feat_calls.append(fd)
        return self._feature


class _FakeDoc:
    def __init__(self, path: str, fm: _FakeFeatureManager) -> None:
        self._path = path
        self.FeatureManager = fm
        self.save_calls: list[tuple] = []
        self.select_calls: list[tuple] = []
        self.clear_selection_calls: list[bool] = []
        self.select_returns = True
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top_only: bool) -> None:
        self.clear_selection_calls.append(top_only)

    def SelectByID(self, name: str, sel_type: str, x: float, y: float, z: float) -> bool:
        self.select_calls.append((name, sel_type, x, y, z))
        return self.select_returns

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

_VALID_BASEFLANGE_FEATURE = {
    "type": "base_flange",
    "thickness_mm": 2.0,
    "bend_radius_mm": 1.0,
}
_VALID_SKETCH_TARGET = {"sketch": "Sketch1"}

_VALID_VARFIL_FEATURE = {"type": "variable_radius_fillet"}
_VALID_VARFIL_TARGET = {
    "edges": [
        {"ref": dict(_VALID_TARGET), "radius_mm": 2.0},
        {"ref": dict(_VALID_TARGET), "radius_mm": 4.0},
    ]
}


def _patch_all(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    doc_path: str,
    entity: Any,
    feature: Any,
    data: Any = None,
):
    """Wire up all fakes and return a dict of handles for assertions.

    ``data`` is the object ``CreateDefinition`` returns (and on which the
    pipeline sets properties); defaults to a fillet-data fake.
    """
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")

    fd = data if data is not None else _FakeFilletData()
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
            str(doc), {"type": "wrap", "radius_mm": 1.0}, _VALID_TARGET
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
# Base-flange feature type (F2) — CreateDefinition(34) → typed_qi pipeline
# ---------------------------------------------------------------------------


class TestProposeBaseFlange:
    def test_writes_record_no_sw(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(
            monkeypatch, tmp_path, str(doc), None, object(),
            data=_FakeBaseFlangeData(),
        )

        r = sw_propose_feature_add(
            str(doc), _VALID_BASEFLANGE_FEATURE, _VALID_SKETCH_TARGET
        )

        assert r["ok"] is True
        rec = json.loads(
            (tmp_path / "proposals" / f"{r['proposal_id']}.json").read_text()
        )
        assert rec["kind"] == "feature_add"
        assert rec["feature"] == _VALID_BASEFLANGE_FEATURE
        assert rec["target"] == _VALID_SKETCH_TARGET
        # No SW touched at propose time.
        assert fakes["fm"].create_def_calls == []

    def test_rejects_bad_thickness(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), None, object())

        r = sw_propose_feature_add(
            str(doc),
            {"type": "base_flange", "thickness_mm": 0, "bend_radius_mm": 1.0},
            _VALID_SKETCH_TARGET,
        )
        assert r["ok"] is False
        assert "thickness_mm" in r["error"]

    def test_rejects_bad_bend_radius(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), None, object())

        r = sw_propose_feature_add(
            str(doc),
            {"type": "base_flange", "thickness_mm": 2.0, "bend_radius_mm": -1},
            _VALID_SKETCH_TARGET,
        )
        assert r["ok"] is False
        assert "bend_radius_mm" in r["error"]

    def test_rejects_target_without_sketch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), None, object())

        r = sw_propose_feature_add(
            str(doc), _VALID_BASEFLANGE_FEATURE, {"persist_id": "AQID"}
        )
        assert r["ok"] is False
        assert "sketch" in r["error"]


class TestDryRunBaseFlange:
    def test_ok_sets_props_selects_sketch_no_save(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        bf = _FakeBaseFlangeData()
        fakes = _patch_all(
            monkeypatch, tmp_path, str(doc), None, object(), data=bf
        )
        pid = sw_propose_feature_add(
            str(doc), _VALID_BASEFLANGE_FEATURE, _VALID_SKETCH_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        # CreateDefinition(34) — the base-flange id.
        assert fakes["fm"].create_def_calls == [34]
        # Props converted mm → metres.
        assert bf.thickness == pytest.approx(0.002)
        assert bf.bend_radius == pytest.approx(0.001)
        # Profile sketch selected by name as a SKETCH.
        assert fakes["doc"].select_calls == [("Sketch1", "SKETCH", 0, 0, 0)]
        assert len(fakes["fm"].create_feat_calls) == 1
        # Dry-run never saves.
        assert fakes["doc"].save_calls == []
        assert len(fakes["sw"].close_calls) == 1

    def test_sketch_unselectable_broke(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        bf = _FakeBaseFlangeData()
        fakes = _patch_all(
            monkeypatch, tmp_path, str(doc), None, object(), data=bf
        )
        fakes["doc"].select_returns = False  # sketch cannot be selected
        pid = sw_propose_feature_add(
            str(doc), _VALID_BASEFLANGE_FEATURE, _VALID_SKETCH_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is False
        assert r["state"] == ST_DRY_RUN_BROKE
        assert "Sketch1" in r["error"]
        # CreateFeature must not run when the profile can't be selected.
        assert fakes["fm"].create_feat_calls == []
        assert fakes["doc"].save_calls == []


class TestCommitBaseFlange:
    def test_saves_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        bf = _FakeBaseFlangeData()
        fakes = _patch_all(
            monkeypatch, tmp_path, str(doc), None, object(), data=bf
        )
        pid = sw_propose_feature_add(
            str(doc), _VALID_BASEFLANGE_FEATURE, _VALID_SKETCH_TARGET
        )["proposal_id"]
        sw_dry_run_feature_add(pid)

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
# Variable-radius fillet feature type — distinct radius per durable edge
# ---------------------------------------------------------------------------


class TestProposeVariableFillet:
    def test_writes_record_no_sw(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        fakes = _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(
            str(doc), _VALID_VARFIL_FEATURE, _VALID_VARFIL_TARGET
        )
        assert r["ok"] is True
        rec = json.loads(
            (tmp_path / "proposals" / f"{r['proposal_id']}.json").read_text()
        )
        assert rec["target"]["edges"][0]["radius_mm"] == 2.0
        assert fakes["fm"].create_def_calls == []

    def test_rejects_empty_edges(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(str(doc), _VALID_VARFIL_FEATURE, {"edges": []})
        assert r["ok"] is False
        assert "edges" in r["error"]

    def test_rejects_edge_without_ref(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(
            str(doc), _VALID_VARFIL_FEATURE, {"edges": [{"radius_mm": 2.0}]}
        )
        assert r["ok"] is False
        assert "ref" in r["error"]

    def test_rejects_bad_radius(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())

        r = sw_propose_feature_add(
            str(doc),
            _VALID_VARFIL_FEATURE,
            {"edges": [{"ref": dict(_VALID_TARGET), "radius_mm": 0}]},
        )
        assert r["ok"] is False
        assert "radius_mm" in r["error"]


class TestDryRunVariableFillet:
    def _wire(self, monkeypatch, tmp_path, doc_path, n_items):
        data = _FakeVarFilletData(n_items)
        feat = _FakeVarFilletFeature(data)
        fakes = _patch_all(
            monkeypatch, tmp_path, doc_path, _FakeEntity(), feat, data=data
        )
        return data, feat, fakes

    def test_ok_sets_distinct_radii_appends_no_save(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        data, feat, fakes = self._wire(monkeypatch, tmp_path, str(doc), 2)

        # Record the append flags select_entity is called with.
        sel_appends: list[bool] = []
        monkeypatch.setattr(
            mutate, "select_entity",
            lambda e, **kw: (sel_appends.append(kw.get("append", False)), True)[1],
        )

        pid = sw_propose_feature_add(
            str(doc), _VALID_VARFIL_FEATURE, _VALID_VARFIL_TARGET
        )["proposal_id"]
        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        assert fakes["fm"].create_def_calls == [1]  # swFmFillet
        assert data.init_calls == [0]               # const-radius
        assert data.is_multiple is True
        # First edge append=False, second append=True (accumulate).
        assert sel_appends == [False, True]
        # Distinct radii bound per item, mm → metres.
        assert [r for _, r in data.set_radii] == pytest.approx([0.002, 0.004])
        assert len(feat.modify_calls) == 1
        assert fakes["doc"].save_calls == []

    def test_item_count_mismatch_broke(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        # 2 edges requested but the fillet collapses to 1 item.
        data, feat, fakes = self._wire(monkeypatch, tmp_path, str(doc), 1)
        pid = sw_propose_feature_add(
            str(doc), _VALID_VARFIL_FEATURE, _VALID_VARFIL_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is False
        assert r["state"] == ST_DRY_RUN_BROKE
        assert "item count" in r["error"]
        assert feat.modify_calls == []
        assert fakes["doc"].save_calls == []


class TestCommitVariableFillet:
    def test_saves_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "test.sldprt"
        doc.touch()
        data = _FakeVarFilletData(2)
        feat = _FakeVarFilletFeature(data)
        fakes = _patch_all(
            monkeypatch, tmp_path, str(doc), _FakeEntity(), feat, data=data
        )
        pid = sw_propose_feature_add(
            str(doc), _VALID_VARFIL_FEATURE, _VALID_VARFIL_TARGET
        )["proposal_id"]
        sw_dry_run_feature_add(pid)

        fakes["doc"].save_calls.clear()
        r = sw_commit_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_COMMITTED
        assert r["doc_saved"] is True
        assert len(fakes["doc"].save_calls) == 1


# ---------------------------------------------------------------------------
# Wizard hole — dynamic standards-DB arg resolution + creation
# ---------------------------------------------------------------------------


class _FakeHoleTable:
    def __init__(self, sizes: list[str]) -> None:
        self._sizes = sizes

    def GetColumnNames(self) -> tuple:
        return (True, ("SIZE", "DIAMETER"))

    def GetRowCount(self) -> tuple:
        return (True, len(self._sizes))  # retval bool + count

    def GetCellData(self, col: str, row: int) -> tuple:
        return (True, self._sizes[row])


class _FakeHSD:
    """IHoleStandardsData stand-in: returns (retval, *out-arrays) tuples."""

    def __init__(self, sizes: list[str]) -> None:
        self._sizes = sizes

    def GetHoleStandards(self) -> tuple:
        return (True, (1, 8, 4), ("ANSI Metric", "ISO", "DIN"))

    def GetFastenerTypes(self, std_name: str) -> tuple:
        return (True, (39, 41), ("Drill sizes", "Tap Drills"))

    def GetFastenerTableTypes(self, std_name: str, fid: int) -> tuple:
        return (True, (0, 2))

    def GetFastenerTable(self, std_name: str, fid: int, tid: int) -> tuple:
        return (True, _FakeHoleTable(self._sizes))


class _FakeSwAppHoles:
    def __init__(self, sizes: list[str]) -> None:
        self._sizes = sizes

    def GetHoleStandardsData(self, hole_type: int) -> Any:
        return _FakeHSD(self._sizes)


def _patch_holes(monkeypatch: pytest.MonkeyPatch, sizes: list[str]) -> None:
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "get_sw_app", lambda: _FakeSwAppHoles(sizes))


class TestResolveHoleArgs:
    def test_resolves_indexes_and_validates_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6", "M8", "M10"])
        ok, std, fast, err = mutate._resolve_hole_args(
            2, "ANSI Metric", "Tap Drills", "M8"
        )
        assert ok is True
        assert std == 1  # ANSI Metric index (swWzdHoleStandards_e)
        assert fast == 41  # Tap Drills
        assert err is None

    def test_standard_match_is_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6"])
        ok, std, fast, err = mutate._resolve_hole_args(
            2, "ansi metric", "drill sizes", "M6"
        )
        assert ok is True and std == 1 and fast == 39

    def test_unknown_standard_lists_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6"])
        ok, _, _, err = mutate._resolve_hole_args(2, "Klingon", "Tap Drills", "M6")
        assert ok is False
        assert "not found" in err and "ANSI Metric" in err

    def test_unknown_fastener_lists_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6"])
        ok, _, _, err = mutate._resolve_hole_args(2, "ISO", "Nonsense", "M6")
        assert ok is False
        assert "Tap Drills" in err

    def test_invalid_size_rejected_with_valid_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6", "M8", "M10"])
        ok, _, _, err = mutate._resolve_hole_args(2, "ISO", "Tap Drills", "M7.5")
        assert ok is False
        assert "M7.5" in err and "M6" in err and "M10" in err


class TestFormatSizeCatalog:
    """H2: the size list in dry-run error messages must be readable when the
    DB table is long (Tap Drills has ~70 entries in the ANSI Metric DB) and
    still byte-stable for short lists so substring assertions hold."""

    def test_empty_list_returns_placeholder(self) -> None:
        assert mutate._format_size_catalog([]) == "<no sizes enumerated>"

    def test_short_list_is_comma_separated_not_repr(self) -> None:
        # Raw repr would be "['M6', 'M8', 'M10']" with brackets+quotes. The
        # H2 format is a clean comma-separated string.
        assert mutate._format_size_catalog(["M6", "M8", "M10"]) == "M6, M8, M10"

    def test_long_list_is_truncated_with_total_count(self) -> None:
        sizes = [f"M{i}" for i in range(1, 51)]  # 50 entries, well over limit
        out = mutate._format_size_catalog(sizes)
        assert "(50 total)" in out
        assert "..." in out
        # First 20 present; entry #21 (M21) is past the cutoff.
        assert "M1" in out and "M20" in out
        assert "M21" not in out.split("...")[0]

    def test_at_limit_is_not_truncated(self) -> None:
        sizes = [f"M{i}" for i in range(1, mutate._SIZE_ERROR_DISPLAY_LIMIT + 1)]
        out = mutate._format_size_catalog(sizes)
        assert "..." not in out
        assert "total" not in out

    def test_byte_stable_across_calls(self) -> None:
        sizes = ["M6", "M8", "M10", "M12"]
        assert mutate._format_size_catalog(sizes) == mutate._format_size_catalog(sizes)


class TestResolveHoleArgsH2:
    """H2: richer per-fastener size enumeration in validation errors."""

    def test_long_size_list_shows_count_and_truncates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sizes = [f"M{i}" for i in range(1, 40)]  # 39 entries
        _patch_holes(monkeypatch, sizes)
        ok, _, _, err = mutate._resolve_hole_args(2, "ISO", "Tap Drills", "M999")
        assert ok is False
        assert "(39 total)" in err
        # The rejected size is named.
        assert "M999" in err

    def test_empty_db_returns_diagnostic_not_silent_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-H2 behavior: valid_sizes=[] caused the size gate to be skipped,
        letting any size through to the live SW call (which then failed with an
        unhelpful COM error). Post-H2: surface a structured 'no sizes enumerated'
        diagnostic so the user sees what went wrong at the DB read."""
        _patch_holes(monkeypatch, [])
        ok, _, _, err = mutate._resolve_hole_args(2, "ISO", "Tap Drills", "M6")
        assert ok is False
        assert "no sizes enumerated" in err

    def test_short_size_list_is_comma_separated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_holes(monkeypatch, ["M6", "M8", "M10"])
        ok, _, _, err = mutate._resolve_hole_args(2, "ISO", "Tap Drills", "M7.5")
        assert ok is False
        # Post-H2: no raw Python list repr (no brackets/quotes around the catalog).
        assert "[" not in err or err.count("[") == err.count("[")  # sanity
        assert "M6, M8, M10" in err
        # Count prefix is present.
        assert "3 valid sizes" in err


class TestProposeWizardHole:
    _FEATURE = {
        "type": "wizard_hole", "hole_type": "hole", "standard": "ANSI Metric",
        "fastener_type": "Tap Drills", "size": "M8", "end_condition": "blind",
        "depth_mm": 6.0,
    }
    _TARGET = {"face": [0, 0, 0.01], "point": [0.003, 0.002, 0.01]}

    def test_writes_record(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(str(doc), self._FEATURE, self._TARGET)
        assert r["ok"] is True

    def test_rejects_bad_hole_type(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(
            str(doc), {**self._FEATURE, "hole_type": "wormhole"}, self._TARGET
        )
        assert r["ok"] is False and "hole_type" in r["error"]

    def test_rejects_bad_target_point(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(
            str(doc), self._FEATURE, {"face": [0, 0, 0.01], "point": [0, 0]}
        )
        assert r["ok"] is False and "point" in r["error"]

    def test_accepts_durable_face_ref(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # C: a durable manifest-face dict is a valid placement target.
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        face_ref = {
            "normal": [0, 0, 1], "centroid": [0, 0, 0.01], "area_mm2": 1600.0,
            "role_hint": "+z_top", "persist_id": "QUJD",
        }
        r = sw_propose_feature_add(
            str(doc), self._FEATURE, {"face_ref": face_ref, "point": [0.003, 0.002, 0.01]}
        )
        assert r["ok"] is True

    def test_rejects_missing_face_and_ref(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(str(doc), self._FEATURE, {"point": [0, 0, 0.01]})
        assert r["ok"] is False and "face_ref" in r["error"]

    def test_rejects_bad_face_ref(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_all(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(
            str(doc), self._FEATURE, {"face_ref": "nope", "point": [0, 0, 0.01]}
        )
        assert r["ok"] is False and "face_ref" in r["error"]


class _FakeSketchPoint:
    def Select2(self, append: bool, mark: int) -> bool:
        return True


class _FakeSketchManager:
    def InsertSketch(self, rebuild: bool) -> None:
        pass

    def CreatePoint(self, x: float, y: float, z: float) -> Any:
        return _FakeSketchPoint()


class _FakeWizHoleData:
    def __init__(self) -> None:
        self.init_args: tuple | None = None
        self.depth: float | None = None

    def InitializeHole(self, *args) -> None:
        self.init_args = args

    @property
    def Depth(self) -> float:
        return self.depth or 0.0

    @Depth.setter
    def Depth(self, v: float) -> None:
        self.depth = v


class _FakeWizFM:
    def __init__(self, data: Any, feature: Any) -> None:
        self._data = data
        self._feature = feature
        self.create_def_calls: list[int] = []

    def CreateDefinition(self, t: int) -> Any:
        self.create_def_calls.append(t)
        return self._data

    def CreateFeature(self, fd: Any) -> Any:
        return self._feature


class _FakeWizDoc:
    def __init__(self, path: str, fm: Any) -> None:
        self._path = path
        self.FeatureManager = fm
        self.SketchManager = _FakeSketchManager()
        self.save_calls: list[tuple] = []
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top: bool) -> None:
        pass

    def SelectByID(self, name: str, sel_type: str, x: float, y: float, z: float) -> bool:
        return True

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


class TestDryRunWizardHole:
    _FEATURE = {
        "type": "wizard_hole", "hole_type": "hole", "standard": "ANSI Metric",
        "fastener_type": "Tap Drills", "size": "M8", "end_condition": "blind",
        "depth_mm": 6.0,
    }
    _TARGET = {"face": [0, 0, 0.01], "point": [0.003, 0.002, 0.01]}

    def test_resolves_args_and_creates_no_save(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")

        wizdata = _FakeWizHoleData()
        feature_obj = object()  # materialized (not None/int)
        fm = _FakeWizFM(wizdata, feature_obj)
        doc = _FakeWizDoc(str(doc_file), fm)
        sw = _FakeSwAppHoles(["M6", "M8", "M10"])
        # sw also needs OpenDoc6/CloseDoc for the PAE plumbing.
        sw_doc = doc
        monkeypatch.setattr(
            _FakeSwAppHoles, "OpenDoc6",
            lambda self, *a: (sw_doc, 0, 0), raising=False,
        )
        monkeypatch.setattr(
            _FakeSwAppHoles, "CloseDoc", lambda self, title: None, raising=False
        )
        monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
        monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
        monkeypatch.setattr(mutate, "get_active_doc", lambda s: None)

        pid = sw_propose_feature_add(str(doc_file), self._FEATURE, self._TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        assert fm.create_def_calls == [25]            # swFmHoleWzd
        # InitializeHole got the DB-resolved indexes + the exact size string.
        assert wizdata.init_args == (2, 1, 41, "M8", 0)
        assert wizdata.depth == pytest.approx(0.006)
        assert doc.save_calls == []                   # dry-run never saves

    def test_durable_face_ref_resolves_and_creates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # C: the placement face arrives as a durable face_ref; the handler
        # resolves it (resolve_manifest_face) and selects the live entity
        # (select_entity) instead of a raw coordinate SelectByID.
        import types

        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")

        wizdata = _FakeWizHoleData()
        fm = _FakeWizFM(wizdata, object())
        doc = _FakeWizDoc(str(doc_file), fm)
        sw = _FakeSwAppHoles(["M6", "M8", "M10"])
        monkeypatch.setattr(
            _FakeSwAppHoles, "OpenDoc6", lambda self, *a: (doc, 0, 0), raising=False
        )
        monkeypatch.setattr(
            _FakeSwAppHoles, "CloseDoc", lambda self, title: None, raising=False
        )
        monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
        monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
        monkeypatch.setattr(mutate, "get_active_doc", lambda s: None)

        # Durable-resolution seam: resolve to a face entity, select succeeds.
        resolved: list[Any] = []
        face_entity = object()
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, ref, **kw: types.SimpleNamespace(entity=face_entity, method="persist_id"),
        )
        monkeypatch.setattr(
            mutate, "select_entity",
            lambda ent, **kw: resolved.append(ent) or True,
        )

        face_ref = {
            "normal": [0, 0, 1], "centroid": [0, 0, 0.01], "area_mm2": 1600.0,
            "role_hint": "+z_top", "persist_id": "QUJD",
        }
        target = {"face_ref": face_ref, "point": [0.003, 0.002, 0.01]}
        pid = sw_propose_feature_add(str(doc_file), self._FEATURE, target)["proposal_id"]
        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        assert resolved == [face_entity]              # the resolved face was selected
        assert fm.create_def_calls == [25]
        assert wizdata.init_args == (2, 1, 41, "M8", 0)
        assert doc.save_calls == []

    def test_durable_face_ref_unresolved_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import types

        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")

        wizdata = _FakeWizHoleData()
        fm = _FakeWizFM(wizdata, object())
        doc = _FakeWizDoc(str(doc_file), fm)
        sw = _FakeSwAppHoles(["M6", "M8", "M10"])
        monkeypatch.setattr(
            _FakeSwAppHoles, "OpenDoc6", lambda self, *a: (doc, 0, 0), raising=False
        )
        monkeypatch.setattr(
            _FakeSwAppHoles, "CloseDoc", lambda self, title: None, raising=False
        )
        monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
        monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
        monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
        monkeypatch.setattr(mutate, "get_active_doc", lambda s: None)
        # Face does not resolve — the hole must NOT be created.
        monkeypatch.setattr(
            mutate, "resolve_manifest_face",
            lambda d, ref, **kw: types.SimpleNamespace(entity=None, method="unresolved"),
        )
        monkeypatch.setattr(mutate, "select_entity", lambda ent, **kw: True)

        face_ref = {"normal": [0, 0, 1], "centroid": [0, 0, 0.01],
                    "area_mm2": 1600.0, "role_hint": "+z_top"}
        target = {"face_ref": face_ref, "point": [0.003, 0.002, 0.01]}
        pid = sw_propose_feature_add(str(doc_file), self._FEATURE, target)["proposal_id"]
        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is False
        assert "unresolved" in (r.get("error") or "")
        assert fm.create_def_calls == []              # never reached CreateDefinition


# ---------------------------------------------------------------------------
# Shell & Draft (Wall-2: IModelDoc2 / IFeatureManager Insert* methods)
# ---------------------------------------------------------------------------


class _FakeSelMgr:
    def GetSelectedObject6(self, idx: int, mark: int) -> Any:
        return object()  # a face entity stand-in


class _FakeShellFM:
    """FeatureManager exposing GetFeatures(True) -> list (len = feature count).

    The shell handler verifies materialization via len(GetFeatures(True)) rather
    than GetFeatureCount() (a non-callable property on the late-bound doc; the
    W6 dome PAE exposed this).
    """

    def __init__(self, doc: "_FakeShellDoc") -> None:
        self._doc = doc

    def GetFeatures(self, top_level: bool):  # noqa: N802, FBT001
        return ["f"] * self._doc._fcount


class _FakeShellDoc:
    def __init__(self, path: str, features_added: int) -> None:
        self._path = path
        self._fcount = 1
        self._features_added = features_added
        self.SelectionManager = _FakeSelMgr()
        self.shell_calls: list[tuple] = []
        self.save_calls: list[tuple] = []
        self._title = Path(path).name
        self.FeatureManager = _FakeShellFM(self)

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top: bool) -> None:
        pass

    def SelectByID(self, n: str, t: str, x: float, y: float, z: float) -> bool:
        return True

    def GetFeatureCount(self) -> int:
        return self._fcount

    def InsertFeatureShell(self, thickness: float, outward: bool) -> None:
        self.shell_calls.append((thickness, outward))
        self._fcount += self._features_added

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


class _FakeDraftFM:
    def __init__(self, feature: Any, *, adds_feature: bool = True) -> None:
        self._feature = feature
        self._adds_feature = adds_feature
        self._features: list[object] = [object()]  # one pre-existing feature
        self.draft_calls: list[tuple] = []

    def InsertMultiFaceDraft(self, *args) -> Any:
        self.draft_calls.append(args)
        # The real API returns None even on success; the handler verifies via a
        # GetFeatures(True) count delta, so a successful draft grows the tree.
        if self._adds_feature:
            self._features.append(object())
        return self._feature

    def GetFeatures(self, _top: bool) -> list[object]:
        return list(self._features)


class _FakeDraftDoc:
    def __init__(self, path: str, fm: _FakeDraftFM) -> None:
        self._path = path
        self.FeatureManager = fm
        self.SelectionManager = _FakeSelMgr()
        self.save_calls: list[tuple] = []
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top: bool) -> None:
        pass

    def SelectByID(self, n: str, t: str, x: float, y: float, z: float) -> bool:
        return True

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


class _FakeSwOpen:
    def __init__(self, doc: Any) -> None:
        self._doc = doc
        self.close_calls: list[str] = []

    def OpenDoc6(self, *a) -> tuple:
        return (self._doc, 0, 0)

    def CloseDoc(self, title: str) -> None:
        self.close_calls.append(title)


def _patch_wall2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, doc: Any) -> Any:
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    sw = _FakeSwOpen(doc)
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
    monkeypatch.setattr(mutate, "get_active_doc", lambda s: None)
    return sw


_SHELL_FEATURE = {"type": "shell", "thickness_mm": 2.0, "outward": False}
_SHELL_TARGET = {"faces": [[0, 0, 0.02]]}
_DRAFT_FEATURE = {"type": "draft", "angle_deg": 5.0, "propagation": "none"}
_DRAFT_TARGET = {"neutral_face": [0, 0, 0], "faces": [[0.02, 0, 0.01]]}


class TestProposeShellDraft:
    def test_shell_writes_record(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeShellDoc(str(doc), 1))
        r = sw_propose_feature_add(str(doc), _SHELL_FEATURE, _SHELL_TARGET)
        assert r["ok"] is True

    def test_shell_rejects_bad_thickness(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeShellDoc(str(doc), 1))
        r = sw_propose_feature_add(str(doc), {**_SHELL_FEATURE, "thickness_mm": 0}, _SHELL_TARGET)
        assert r["ok"] is False and "thickness_mm" in r["error"]

    def test_shell_rejects_empty_faces(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeShellDoc(str(doc), 1))
        r = sw_propose_feature_add(str(doc), _SHELL_FEATURE, {"faces": []})
        assert r["ok"] is False and "faces" in r["error"]

    def test_draft_rejects_bad_angle(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeDraftDoc(str(doc), _FakeDraftFM(object())))
        r = sw_propose_feature_add(str(doc), {**_DRAFT_FEATURE, "angle_deg": -5}, _DRAFT_TARGET)
        assert r["ok"] is False and "angle_deg" in r["error"]

    def test_draft_rejects_bad_propagation(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeDraftDoc(str(doc), _FakeDraftFM(object())))
        r = sw_propose_feature_add(str(doc), {**_DRAFT_FEATURE, "propagation": "sideways"}, _DRAFT_TARGET)
        assert r["ok"] is False and "propagation" in r["error"]

    def test_draft_rejects_missing_neutral(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeDraftDoc(str(doc), _FakeDraftFM(object())))
        r = sw_propose_feature_add(str(doc), _DRAFT_FEATURE, {"faces": [[0.02, 0, 0.01]]})
        assert r["ok"] is False and "neutral_face" in r["error"]


class TestDryRunShell:
    def test_ok_inserts_shell_no_save(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"; doc_file.touch()
        shell_doc = _FakeShellDoc(str(doc_file), 1)  # +1 feature
        _patch_wall2(monkeypatch, tmp_path, shell_doc)
        monkeypatch.setattr(mutate, "select_entity", lambda e, **kw: True)
        pid = sw_propose_feature_add(str(doc_file), _SHELL_FEATURE, _SHELL_TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)
        assert r["ok"] is True and r["state"] == ST_DRY_RUN_OK
        assert shell_doc.shell_calls == [(pytest.approx(0.002), False)]
        assert shell_doc.save_calls == []

    def test_noop_shell_broke(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"; doc_file.touch()
        shell_doc = _FakeShellDoc(str(doc_file), 0)  # no feature added
        _patch_wall2(monkeypatch, tmp_path, shell_doc)
        monkeypatch.setattr(mutate, "select_entity", lambda e, **kw: True)
        pid = sw_propose_feature_add(str(doc_file), _SHELL_FEATURE, _SHELL_TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)
        assert r["ok"] is False and r["state"] == ST_DRY_RUN_BROKE
        assert "did not add a feature" in r["error"]


class TestDryRunDraft:
    def test_ok_inserts_draft_with_marks_no_save(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"; doc_file.touch()
        fm = _FakeDraftFM(object())  # materialized feature
        draft_doc = _FakeDraftDoc(str(doc_file), fm)
        _patch_wall2(monkeypatch, tmp_path, draft_doc)
        marks: list[tuple] = []
        monkeypatch.setattr(
            mutate, "select_entity",
            lambda e, **kw: (marks.append((kw.get("append", False), kw.get("mark", 0))), True)[1],
        )
        pid = sw_propose_feature_add(str(doc_file), _DRAFT_FEATURE, _DRAFT_TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)
        assert r["ok"] is True and r["state"] == ST_DRY_RUN_OK
        # neutral plane mark=1 (append False), draft face mark=2 (append True).
        assert marks == [(False, 1), (True, 2)]
        # angle passed in radians, propagation 'none' -> 0.
        args = fm.draft_calls[0]
        assert args[0] == pytest.approx(math.radians(5.0))
        assert args[3] == 0
        assert draft_doc.save_calls == []


# ---------------------------------------------------------------------------
# Sweep feature_add (seat-validated by spike_sweep_v2: swFmSweep=17)
# ---------------------------------------------------------------------------


class _FakeSweepExt:
    def __init__(self, ret: bool = True) -> None:
        self.select_calls: list[tuple] = []
        self._ret = ret

    def SelectByID2(self, name, t, x, y, z, append, mark, callout, sd) -> bool:
        self.select_calls.append((name, t, append, mark))
        return self._ret


class _FakeSweepDoc:
    def __init__(self, path: str, fm: _FakeFeatureManager, ext_ret: bool = True) -> None:
        self._path = path
        self.FeatureManager = fm
        self.Extension = _FakeSweepExt(ext_ret)
        self.save_calls: list[tuple] = []
        self.clear_selection_calls: list[bool] = []
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top: bool) -> None:
        self.clear_selection_calls.append(top)

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


# auto_pierce:False isolates the CORE sweep marshaling (CreateDefinition(17) +
# profile/path marks 1/4) in these offline mock tests. The W50 auto-pierce
# pre-step is COM-bound (re-opens sketches, SketchAddConstraints) and is proven
# on the live seat (spikes/v0_2x/sweep_autopierce_pae.py), not against mocks.
_SWEEP_FEATURE = {"type": "sweep", "auto_pierce": False}
_SWEEP_TARGET = {"profile": "Sketch1", "path": "Sketch2"}


class TestProposeSweep:
    def test_sweep_writes_record(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeSweepDoc(str(doc), _FakeFeatureManager(object(), object())))
        r = sw_propose_feature_add(str(doc), _SWEEP_FEATURE, _SWEEP_TARGET)
        assert r["ok"] is True

    def test_sweep_rejects_missing_profile(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeSweepDoc(str(doc), _FakeFeatureManager(object(), object())))
        r = sw_propose_feature_add(str(doc), _SWEEP_FEATURE, {"path": "Sketch2"})
        assert r["ok"] is False and "profile" in r["error"]

    def test_sweep_rejects_missing_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc = tmp_path / "t.sldprt"; doc.touch()
        _patch_wall2(monkeypatch, tmp_path, _FakeSweepDoc(str(doc), _FakeFeatureManager(object(), object())))
        r = sw_propose_feature_add(str(doc), _SWEEP_FEATURE, {"profile": "Sketch1"})
        assert r["ok"] is False and "path" in r["error"]


class TestDryRunSweep:
    def test_ok_inserts_sweep_with_marks_no_save(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"; doc_file.touch()
        fm = _FakeFeatureManager(object(), object())  # materialized feature
        sweep_doc = _FakeSweepDoc(str(doc_file), fm)
        _patch_wall2(monkeypatch, tmp_path, sweep_doc)
        pid = sw_propose_feature_add(str(doc_file), _SWEEP_FEATURE, _SWEEP_TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)
        assert r["ok"] is True and r["state"] == ST_DRY_RUN_OK
        assert fm.create_def_calls == [17]
        # profile select mark 1 (append False), path select mark 4 (append True)
        assert sweep_doc.Extension.select_calls == [
            ("Sketch1", "SKETCH", False, 1),
            ("Sketch2", "SKETCH", True, 4),
        ]
        assert sweep_doc.save_calls == []

    def test_noop_sweep_broke(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"; doc_file.touch()
        fm = _FakeFeatureManager(object(), None)  # CreateFeature returns None
        sweep_doc = _FakeSweepDoc(str(doc_file), fm)
        _patch_wall2(monkeypatch, tmp_path, sweep_doc)
        pid = sw_propose_feature_add(str(doc_file), _SWEEP_FEATURE, _SWEEP_TARGET)["proposal_id"]
        r = sw_dry_run_feature_add(pid)
        assert r["ok"] is False and r["state"] == ST_DRY_RUN_BROKE
        assert "did not materialize" in r["error"]


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


# ---------------------------------------------------------------------------
# Chamfer (W24) — fillet sibling via IChamferFeatureData2
# DE-ADVERTISED: "chamfer" is NOT in _SUPPORTED_FEATURE_TYPES until PAE clears.
# These tests monkeypatch the advertised tuple so validation is reachable.
# ---------------------------------------------------------------------------


class _FakeChamferFM:
    """FeatureManager for chamfer: records InsertFeatureChamfer calls."""

    def __init__(self, feature: Any) -> None:
        self._feature = feature
        self.insert_chamfer_calls: list[tuple] = []

    def InsertFeatureChamfer(self, *args: Any) -> Any:
        self.insert_chamfer_calls.append(args)
        return self._feature


class _FakeChamferDoc:
    def __init__(self, path: str, fm: _FakeChamferFM) -> None:
        self._path = path
        self.FeatureManager = fm
        self.save_calls: list[tuple] = []
        self.clear_selection_calls: list[bool] = []
        self._title = Path(path).name

    def ForceRebuild3(self, _: bool) -> bool:
        return True

    def ClearSelection2(self, top_only: bool) -> None:
        self.clear_selection_calls.append(top_only)

    def Save(self) -> int:
        self.save_calls.append(())
        return 1

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path


class _FakeChamferSw:
    def __init__(self, doc: _FakeChamferDoc) -> None:
        self._doc = doc
        self.close_calls: list[str] = []

    def OpenDoc6(self, *a: Any) -> tuple:
        return (self._doc, 0, 0)

    def CloseDoc(self, title: str) -> None:
        self.close_calls.append(title)


def _patch_chamfer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    doc_path: str,
    entity: Any,
    feature: Any,
) -> dict[str, Any]:
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    fm = _FakeChamferFM(feature)
    doc = _FakeChamferDoc(doc_path, fm)
    sw = _FakeChamferSw(doc)
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
    monkeypatch.setattr(mutate, "get_active_doc", lambda sw_: None)
    monkeypatch.setattr(
        mutate, "resolve_edge_ref",
        lambda doc_, ref, **kw: _FakeRefResolution(entity),
    )
    monkeypatch.setattr(mutate, "select_entity", lambda e, **kw: True)
    return {"sw": sw, "doc": doc, "fm": fm}


_VALID_CHAMFER_FEATURE = {"type": "chamfer", "distance_mm": 2.0}
_VALID_CHAMFER_FEATURE_ANGLE = {"type": "chamfer", "distance_mm": 2.0, "angle_deg": 30.0}


def _patch_chamfer_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Temporarily add 'chamfer' to _SUPPORTED_FEATURE_TYPES for testing."""
    monkeypatch.setattr(
        mutate, "_SUPPORTED_FEATURE_TYPES",
        mutate._SUPPORTED_FEATURE_TYPES + ("chamfer",),
    )


class TestChamferAdvertised:
    def test_in_supported_types(
        self,
    ) -> None:
        assert "chamfer" in mutate._SUPPORTED_FEATURE_TYPES

    def test_accepted_with_valid_params(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        r = sw_propose_feature_add(str(doc), _VALID_CHAMFER_FEATURE, _VALID_TARGET)
        assert r["ok"] is True


class TestProposeChamfer:
    def test_writes_record(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(str(doc), _VALID_CHAMFER_FEATURE, _VALID_TARGET)
        assert r["ok"] is True

    def test_rejects_bad_distance(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(
            str(doc), {"type": "chamfer", "distance_mm": -1}, _VALID_TARGET
        )
        assert r["ok"] is False
        assert "distance_mm" in r["error"]

    def test_rejects_zero_distance(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(
            str(doc), {"type": "chamfer", "distance_mm": 0}, _VALID_TARGET
        )
        assert r["ok"] is False
        assert "distance_mm" in r["error"]

    def test_rejects_bad_angle(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(
            str(doc),
            {"type": "chamfer", "distance_mm": 2.0, "angle_deg": 95},
            _VALID_TARGET,
        )
        assert r["ok"] is False
        assert "angle_deg" in r["error"]

    def test_rejects_zero_angle(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(
            str(doc),
            {"type": "chamfer", "distance_mm": 2.0, "angle_deg": 0},
            _VALID_TARGET,
        )
        assert r["ok"] is False
        assert "angle_deg" in r["error"]

    def test_default_angle_45(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        _patch_chamfer(monkeypatch, tmp_path, str(doc), _FakeEntity(), object())
        _patch_chamfer_advertised(monkeypatch)
        r = sw_propose_feature_add(str(doc), _VALID_CHAMFER_FEATURE, _VALID_TARGET)
        assert r["ok"] is True
        rec = json.loads(
            (tmp_path / "proposals" / f"{r['proposal_id']}.json").read_text()
        )
        assert "angle_deg" not in rec["feature"]


class TestDryRunChamfer:
    def test_ok_calls_insert_chamfer_no_save(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        fakes = _patch_chamfer(
            monkeypatch, tmp_path, str(doc), _FakeEntity(), object()
        )
        _patch_chamfer_advertised(monkeypatch)
        pid = sw_propose_feature_add(
            str(doc), _VALID_CHAMFER_FEATURE_ANGLE, _VALID_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        assert r["state"] == ST_DRY_RUN_OK
        assert len(fakes["fm"].insert_chamfer_calls) == 1
        args = fakes["fm"].insert_chamfer_calls[0]
        assert args[0] == 4  # tangent propagation
        assert args[1] == 1  # swChamferAngleDistance
        assert args[2] == pytest.approx(0.002)  # 2mm → 0.002m
        assert args[3] == pytest.approx(math.radians(30.0))
        assert fakes["doc"].save_calls == []

    def test_default_angle_is_45_deg(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        fakes = _patch_chamfer(
            monkeypatch, tmp_path, str(doc), _FakeEntity(), object()
        )
        _patch_chamfer_advertised(monkeypatch)
        pid = sw_propose_feature_add(
            str(doc), _VALID_CHAMFER_FEATURE, _VALID_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is True
        args = fakes["fm"].insert_chamfer_calls[0]
        assert args[3] == pytest.approx(math.radians(45.0))

    def test_unresolved_edge_broke(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        doc = tmp_path / "t.sldprt"
        doc.touch()
        fakes = _patch_chamfer(
            monkeypatch, tmp_path, str(doc), None, object()
        )
        _patch_chamfer_advertised(monkeypatch)
        pid = sw_propose_feature_add(
            str(doc), _VALID_CHAMFER_FEATURE, _VALID_TARGET
        )["proposal_id"]

        r = sw_dry_run_feature_add(pid)

        assert r["ok"] is False
        assert r["state"] == ST_DRY_RUN_BROKE
        assert "unresolved" in r["error"]
        assert fakes["fm"].insert_chamfer_calls == []
