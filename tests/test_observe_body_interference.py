"""Offline tests — ``body_interference`` observe lane (multibody-part).

Mocks the IBody2 proxy chain: ``GetIntersectionEdges`` (clash signal),
``Copy`` + ``Operations2(SWBODYINTERSECT)`` + ``GetMassProperties`` (read-only
interference volume on detached temp bodies), and ``GetBodies2`` (the mutation
guard's body-count read). No SW seat — the live discrimination is proven by
spike_body_interference_pae; here we exercise the O(N^2) loop, schema, threshold
logging, and the mutation guard with full control.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

import ai_sw_bridge.observe_body_interference as bi
from ai_sw_bridge.observe_body_interference import _sw_get_body_interference_impl as run
from ai_sw_bridge.observe_body_interference import SW_DOC_PART, _SWBODYINTERSECT


class _FakeResultBody:
    """Temp body from a boolean COMMON — carries a mass-props array w/ volume."""

    def __init__(self, volume_m3: float) -> None:
        self._v = volume_m3

    def GetMassProperties(self, density: float) -> list[float]:
        # [cx, cy, cz, VOLUME, area, mass, + moments...]  (len 12)
        return [0.0, 0.0, 0.0, self._v, 0.0, 0.0, 0, 0, 0, 0, 0, 0]


class _FakeBody:
    """IBody2 stand-in. ``clashes`` maps id(other) -> (edge_count, volume_m3)."""

    _registry: dict = {}

    def __init__(self, name: str) -> None:
        self.Name = name
        self._clash: dict[str, tuple[int, float]] = {}

    def set_clash(self, other: "_FakeBody", edges: int, volume_m3: float) -> None:
        self._clash[other.Name] = (edges, volume_m3)
        other._clash[self.Name] = (edges, volume_m3)

    def GetIntersectionEdges(self, other: "_FakeBody") -> Any:
        edges, _ = self._clash.get(other.Name, (0, 0.0))
        if edges == 0:
            return None
        return tuple(range(edges))  # a fake edge array of the right length

    def Copy(self) -> "_FakeBody":
        return self  # temp copy stands in for itself (carries the clash map)

    def Operations2(self, op: int, tool: "_FakeBody", err: int) -> Any:
        assert op == _SWBODYINTERSECT
        edges, vol = self._clash.get(tool.Name, (0, 0.0))
        if edges == 0:
            return (None, 0)
        return ([_FakeResultBody(vol)], 0)


class _FakeDoc:
    def __init__(
        self,
        bodies: list[_FakeBody],
        *,
        doc_type: int = SW_DOC_PART,
        bodies_after: list[_FakeBody] | None = None,
    ) -> None:
        self._bodies = bodies
        self._doc_type = doc_type
        # bodies_after lets a test simulate a mutation-guard trip.
        self._bodies_after = bodies_after
        self._get_calls = 0

    def GetType(self) -> int:
        return self._doc_type

    def GetPathName(self) -> str:
        return "C:/tmp/multibody.sldprt"

    def GetBodies2(self, btype: int, vis: bool) -> Any:
        self._get_calls += 1
        # First call = the working set; a later call returns bodies_after (guard).
        if self._get_calls > 1 and self._bodies_after is not None:
            return tuple(self._bodies_after)
        return tuple(self._bodies)


def _fake_resolve(obj: Any, name: str) -> Any:
    v = getattr(obj, name)
    return v() if callable(v) else v


@pytest.fixture
def patched(monkeypatch):
    def _apply(doc):
        monkeypatch.setattr(bi, "get_sw_app", lambda: object())
        monkeypatch.setattr(bi, "get_active_doc", lambda sw: doc)
        monkeypatch.setattr(bi, "resolve", _fake_resolve)
        # typed() -> identity so the fakes are used directly.
        monkeypatch.setattr(bi, "typed", lambda obj, iface, module=None: obj)
        monkeypatch.setattr(bi, "wrapper_module", lambda: object())
    return _apply


class TestOverlap:
    def test_two_overlapping_bodies(self, patched):
        a, b = _FakeBody("Boss-Extrude1"), _FakeBody("Boss-Extrude2")
        a.set_clash(b, edges=20, volume_m3=8000.0 / 1e9)  # 8000 mm^3
        patched(_FakeDoc([a, b]))
        r = run()
        assert r["ok"] is True
        assert r["body_count"] == 2
        assert r["pairwise_checks"] == 1
        assert r["interfering_pair_count"] == 1
        assert r["clean"] is False
        assert r["total_interference_volume_mm3"] == pytest.approx(8000.0)
        assert r["mutation_guard_ok"] is True
        p = r["pairs"][0]
        assert {p["body_a"], p["body_b"]} == {"Boss-Extrude1", "Boss-Extrude2"}
        assert p["intersection_edge_count"] == 20
        assert p["interference_volume_mm3"] == pytest.approx(8000.0)


class TestDisjoint:
    def test_two_disjoint_bodies_clean(self, patched):
        a, b = _FakeBody("Boss-Extrude1"), _FakeBody("Boss-Extrude2")
        patched(_FakeDoc([a, b]))  # no clash set
        r = run()
        assert r["ok"] is True
        assert r["clean"] is True
        assert r["interfering_pair_count"] == 0
        assert r["total_interference_volume_mm3"] == pytest.approx(0.0)
        assert r["pairs"] == []
        assert r["mutation_guard_ok"] is True

    def test_single_body_is_vacuously_clean(self, patched):
        patched(_FakeDoc([_FakeBody("Boss-Extrude1")]))
        r = run()
        assert r["ok"] is True
        assert r["body_count"] == 1
        assert r["pairwise_checks"] == 0
        assert r["clean"] is True
        assert r["interfering_pair_count"] == 0

    def test_zero_bodies_clean(self, patched):
        patched(_FakeDoc([]))
        r = run()
        assert r["ok"] is True
        assert r["body_count"] == 0
        assert r["clean"] is True


class TestMultiPair:
    def test_three_bodies_two_clashes(self, patched):
        a, b, c = _FakeBody("B1"), _FakeBody("B2"), _FakeBody("B3")
        a.set_clash(b, edges=8, volume_m3=1000.0 / 1e9)   # 1000 mm^3
        b.set_clash(c, edges=12, volume_m3=2500.0 / 1e9)  # 2500 mm^3
        # a vs c disjoint
        patched(_FakeDoc([a, b, c]))
        r = run()
        assert r["body_count"] == 3
        assert r["pairwise_checks"] == 3   # C(3,2)
        assert r["interfering_pair_count"] == 2
        assert r["clean"] is False
        assert r["total_interference_volume_mm3"] == pytest.approx(3500.0)
        edge_counts = sorted(p["intersection_edge_count"] for p in r["pairs"])
        assert edge_counts == [8, 12]


class TestThresholdLogging:
    def test_large_part_logs_pairwise_count(self, patched, caplog):
        bodies = [_FakeBody(f"B{i}") for i in range(51)]  # > 50 -> 1275 checks
        patched(_FakeDoc(bodies))
        with caplog.at_level(logging.WARNING, logger="ai_sw_bridge.observe_body_interference"):
            r = run()
        assert r["body_count"] == 51
        assert r["pairwise_checks"] == 51 * 50 // 2  # 1275
        assert any("1275" in rec.message and "pairwise" in rec.message
                   for rec in caplog.records)

    def test_under_threshold_no_warning(self, patched, caplog):
        bodies = [_FakeBody(f"B{i}") for i in range(3)]
        patched(_FakeDoc(bodies))
        with caplog.at_level(logging.WARNING, logger="ai_sw_bridge.observe_body_interference"):
            run()
        assert not caplog.records


class TestMutationGuard:
    def test_guard_trips_on_body_count_change(self, patched):
        a, b = _FakeBody("B1"), _FakeBody("B2")
        a.set_clash(b, edges=4, volume_m3=500.0 / 1e9)
        # Simulate the document gaining a body (a leaked boolean) after the loop.
        doc = _FakeDoc([a, b], bodies_after=[a, b, _FakeBody("Leaked")])
        patched(doc)
        r = run()
        assert r["mutation_guard_ok"] is False
        assert r["ok"] is False  # read-only contract violated -> not ok
        assert any("mutation guard" in e.lower() for e in r["errors"])


class TestVolumeFailSoft:
    def test_volume_read_failure_keeps_pair(self, patched, monkeypatch):
        a, b = _FakeBody("B1"), _FakeBody("B2")
        a.set_clash(b, edges=6, volume_m3=0.0)

        def _boom(x, y):
            return None, "Operations2: boom"
        monkeypatch.setattr(bi, "_intersection_volume_mm3", _boom)
        patched(_FakeDoc([a, b]))
        r = run()
        # clash still counted (edges>0); volume incomplete -> total is None
        assert r["interfering_pair_count"] == 1
        assert r["pairs"][0]["intersection_edge_count"] == 6
        assert r["pairs"][0]["interference_volume_mm3"] is None
        assert r["total_interference_volume_mm3"] is None
        assert any("volume" in e for e in r["errors"])


class TestValidation:
    def test_no_active_doc(self, patched):
        patched(None)
        r = run()
        assert r["ok"] is False
        assert r["error"] == "no_active_doc"

    def test_assembly_rejected_points_to_interference(self, patched):
        a, b = _FakeBody("c1"), _FakeBody("c2")
        patched(_FakeDoc([a, b], doc_type=2))  # assembly
        r = run()
        assert r["ok"] is False
        assert "part" in r["error"]
        assert "interference()" in r["error"]
