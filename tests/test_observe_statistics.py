"""Tests for observe.sw_get_feature_statistics — W71 build-tree statistics.

Mock-tests sw_get_feature_statistics without a SW seat. The handler reads
IFeatureManager.FeatureStatistics (Refresh()ed first) via late-bound
``resolve``; these fakes stand in for that proxy chain.
"""

from __future__ import annotations

from typing import Any

import pytest

import ai_sw_bridge.observe as observe
from ai_sw_bridge.observe import sw_get_feature_statistics


class _FakeStats:
    def __init__(self) -> None:
        self.FeatureCount = 4
        self.SolidBodiesCount = 1
        self.SurfaceBodiesCount = 1
        self.TotalRebuildTime = 0.123
        self.PartName = "W71_Fixture"
        self.FeatureNames = ("Sketch1", "Boss1", "Cut1", "Surface1")
        self.FeatureTypes = ("ProfileFeature", "Extrusion", "Cut", "RefSurface")
        self.FeatureUpdateTimes = (0.01, 0.02, 0.03, 0.04)
        self.refreshed = False

    def Refresh(self) -> bool:
        self.refreshed = True
        return True


class _FakeStatsFailingArray:
    """Counts read fine; one per-feature array raises (fail-soft path)."""

    def __init__(self) -> None:
        self.FeatureCount = 4
        self.SolidBodiesCount = 1
        self.SurfaceBodiesCount = 1
        self.TotalRebuildTime = 0.123
        self.PartName = "W71_Fixture"
        self.FeatureNames = ("Sketch1", "Boss1", "Cut1", "Surface1")
        self.FeatureTypes = ("ProfileFeature", "Extrusion", "Cut", "RefSurface")

    def Refresh(self) -> bool:
        return True

    @property
    def FeatureUpdateTimes(self) -> Any:
        raise RuntimeError("array read failed")


class _FakeStatsRefreshProperty:
    """Refresh exposed as a BOOLEAN PROPERTY (the late-bound footgun), not a
    method — accessing it triggers the refresh and returns the success flag."""

    def __init__(self) -> None:
        self.FeatureCount = 2
        self.SolidBodiesCount = 1
        self.SurfaceBodiesCount = 0
        self.TotalRebuildTime = 0.01
        self.PartName = "W71_Prop"
        self.FeatureNames = ("Sketch1", "Boss1")
        self.FeatureTypes = (9, 22)
        self.FeatureUpdateTimes = (0.0, 0.0)

    @property
    def Refresh(self) -> bool:
        return True


class _FakeFM:
    def __init__(self, stats: Any) -> None:
        self.FeatureStatistics = stats


class _FakeDoc:
    def __init__(self, fm: Any) -> None:
        self.FeatureManager = fm

    def GetPathName(self) -> str:
        return "C:/tmp/W71.sldprt"


def _fake_resolve(obj: Any, name: str) -> Any:
    """Mimic sw_com.resolve: late-bound getattr, calling methods."""
    v = getattr(obj, name)
    return v() if callable(v) else v


@pytest.fixture
def patched(monkeypatch):
    def _apply(doc):
        monkeypatch.setattr(observe, "get_sw_app", lambda: object())
        monkeypatch.setattr(observe, "get_active_doc", lambda sw: doc)
        monkeypatch.setattr(observe, "resolve", _fake_resolve)
    return _apply


class TestFeatureStatistics:
    def test_ok_counts(self, patched) -> None:
        stats = _FakeStats()
        patched(_FakeDoc(_FakeFM(stats)))
        r = sw_get_feature_statistics()
        assert r["ok"] is True and not r["errors"]
        assert r["feature_count"] == 4
        assert r["solid_bodies_count"] == 1
        assert r["surface_bodies_count"] == 1
        assert r["total_rebuild_time"] == pytest.approx(0.123)
        assert r["part_name"] == "W71_Fixture"
        assert r["doc_path"] == "C:/tmp/W71.sldprt"

    def test_refresh_called_before_read(self, patched) -> None:
        stats = _FakeStats()
        patched(_FakeDoc(_FakeFM(stats)))
        r = sw_get_feature_statistics()
        assert stats.refreshed is True  # Refresh() ran
        assert r["refreshed"] is True

    def test_refresh_as_property_footgun(self, patched) -> None:
        # Refresh exposed as a bool property (the live-seat form) must not
        # crash on a () call; the callable-or-property guard handles it.
        patched(_FakeDoc(_FakeFM(_FakeStatsRefreshProperty())))
        r = sw_get_feature_statistics()
        assert r["ok"] is True
        assert r["refreshed"] is True
        assert not any("Refresh" in e for e in r["errors"])
        assert r["feature_count"] == 2

    def test_per_feature_arrays(self, patched) -> None:
        patched(_FakeDoc(_FakeFM(_FakeStats())))
        r = sw_get_feature_statistics()
        assert r["feature_names"] == ["Sketch1", "Boss1", "Cut1", "Surface1"]
        assert r["feature_types"] == ["ProfileFeature", "Extrusion", "Cut", "RefSurface"]
        assert r["feature_update_times"] == [0.01, 0.02, 0.03, 0.04]

    def test_no_active_doc(self, patched) -> None:
        patched(None)
        r = sw_get_feature_statistics()
        assert r["ok"] is False and r["error"] == "no_active_doc"

    def test_feature_manager_none(self, patched) -> None:
        patched(_FakeDoc(None))
        r = sw_get_feature_statistics()
        assert r["ok"] is False and "FeatureManager returned None" in r["error"]

    def test_statistics_none_is_drawing_like(self, patched) -> None:
        patched(_FakeDoc(_FakeFM(None)))
        r = sw_get_feature_statistics()
        assert r["ok"] is False and "FeatureStatistics returned None" in r["error"]

    def test_fail_soft_on_array_read(self, patched) -> None:
        # A failing per-feature array is recorded but counts still succeed.
        patched(_FakeDoc(_FakeFM(_FakeStatsFailingArray())))
        r = sw_get_feature_statistics()
        assert r["ok"] is True  # counts are the load-bearing witness
        assert r["feature_count"] == 4
        assert r["feature_update_times"] is None
        assert any("FeatureUpdateTimes" in e for e in r["errors"])


class TestObserverWiring:
    def test_observer_method_delegates(self, patched) -> None:
        patched(_FakeDoc(_FakeFM(_FakeStats())))
        r = observe.SolidWorksObserver().feature_statistics()
        assert r["ok"] is True and r["feature_count"] == 4
