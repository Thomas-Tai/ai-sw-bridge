"""W59 offline tests — ``hem`` handler + registry dispatch.

Every COM seam is faked.  No SW process is involved.

What is tested
--------------
* Parameter validation (missing / bad edge_name, bad hem_type, bad d_length).
* Effect gate: face count must increase after InsertSheetMetalHem; a no-op
  that leaves face count unchanged must FAIL (W21 doctrine).
* Registry dispatch: ``hem`` is auto-advertised by ``sw_propose_feature_add``
  (via HANDLER_REGISTRY).
* Fail-soft: exceptions in InsertSheetMetalHem produce (False, reason),
  never propagate.

COM seams patched on ``features.hem`` (lane protocol W56+):
  ``typed``, ``wrapper_module``
"""

from __future__ import annotations

from typing import Any

import pytest

import ai_sw_bridge.features.hem as _mod
from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features.hem import create_hem


# ---------------------------------------------------------------------------
# Fake COM layer
# ---------------------------------------------------------------------------

class _FakeFace:
    pass


class _FakeEdge:
    def __init__(self, name: str) -> None:
        self.Name = name


class _FakeBody:
    def __init__(self, faces: list[_FakeFace], add_faces_on_hem: int = 3) -> None:
        self._faces = list(faces)
        self._add_faces = add_faces_on_hem

    def GetFaces(self) -> list[_FakeFace]:
        return list(self._faces)

    def simulate_hem(self) -> None:
        for _ in range(self._add_faces):
            self._faces.append(_FakeFace())


class _FakeExtension:
    def __init__(self, doc: "_FakeDoc") -> None:
        self._doc = doc

    def SelectByID2(self, name: str, kind: str, *_: Any) -> bool:
        if kind != "EDGE":
            return False
        if name not in {e.Name for e in self._doc._edges}:
            return False
        self._doc._selected_edge = name
        return True


class _FakeOleObj:
    def __init__(self, fm: "_FakeFeatureManager") -> None:
        self._fm = fm

    def InvokeTypes(
        self, memid: int, lcid: int, invkind: int,
        rettype: tuple, argtypes: tuple, *args: Any,
    ) -> Any:
        if memid == 91:
            return self._fm.InsertSheetMetalHem(*args)
        raise NotImplementedError(f"fake memid {memid}")


class _FakeFeatureManager:
    def __init__(self, doc: "_FakeDoc", will_hem: bool = True) -> None:
        self._doc = doc
        self._will_hem = will_hem
        self._oleobj_ = _FakeOleObj(self)

    def InsertSheetMetalHem(
        self,
        hem_type: int,
        position: int,
        reverse: bool,
        d_length: float,
        d_gap: float,
        d_angle: float,
        d_rad: float,
        d_miter_gap: float,
        pcba: Any,
    ) -> object | None:
        if not self._will_hem:
            return None
        for b in self._doc._bodies:
            b.simulate_hem()
        return object()


class _FakeDoc:
    def __init__(
        self,
        bodies: list[_FakeBody],
        edges: list[_FakeEdge],
        will_hem: bool = True,
    ) -> None:
        self._bodies = list(bodies)
        self._edges = list(edges)
        self._selected_edge: str | None = None
        self.FeatureManager = _FakeFeatureManager(self, will_hem)
        self.Extension = _FakeExtension(self)

    def GetBodies2(self, body_type: int, visible_only: bool) -> list[_FakeBody]:
        return list(self._bodies)

    def ForceRebuild3(self, top_only: bool) -> bool:
        return True

    def ClearSelection2(self, all_sel: bool) -> bool:
        self._selected_edge = None
        return True


# ---------------------------------------------------------------------------
# Fixtures / patch helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_com(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_mod, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(_mod, "wrapper_module", lambda: object())


def _one_body_doc(
    face_count: int = 6,
    edges: list[str] | None = None,
    will_hem: bool = True,
    add_faces: int = 3,
) -> _FakeDoc:
    if edges is None:
        edges = ["Edge1"]
    body = _FakeBody([_FakeFace() for _ in range(face_count)], add_faces_on_hem=add_faces)
    return _FakeDoc(
        bodies=[body],
        edges=[_FakeEdge(n) for n in edges],
        will_hem=will_hem,
    )


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_edge_name_rejected(self) -> None:
        ok, err = create_hem(_one_body_doc(), {"type": "hem"}, {})
        assert ok is False
        assert "edge_name" in err

    def test_empty_edge_name_rejected(self) -> None:
        ok, err = create_hem(_one_body_doc(), {"type": "hem"}, {"edge_name": ""})
        assert ok is False
        assert "edge_name" in err

    def test_negative_hem_type_rejected(self) -> None:
        ok, err = create_hem(
            _one_body_doc(),
            {"type": "hem", "hem_type": -1},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "hem_type" in err

    def test_negative_hem_position_rejected(self) -> None:
        ok, err = create_hem(
            _one_body_doc(),
            {"type": "hem", "hem_position": -1},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "hem_position" in err

    def test_zero_d_length_rejected(self) -> None:
        ok, err = create_hem(
            _one_body_doc(),
            {"type": "hem", "d_length_m": 0},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "d_length_m" in err

    def test_negative_d_length_rejected(self) -> None:
        ok, err = create_hem(
            _one_body_doc(),
            {"type": "hem", "d_length_m": -0.01},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "d_length_m" in err

    def test_unknown_edge_name_rejected(self) -> None:
        ok, err = create_hem(
            _one_body_doc(edges=["Edge1"]),
            {"type": "hem"},
            {"edge_name": "NoSuchEdge"},
        )
        assert ok is False
        assert "NoSuchEdge" in err


# ---------------------------------------------------------------------------
# Effect gate — face-count delta is the success criterion (W21 doctrine)
# ---------------------------------------------------------------------------

class TestEffectGate:
    def test_green_hem_closed(self) -> None:
        doc = _one_body_doc(face_count=6, add_faces=3)
        ok, err = create_hem(
            doc,
            {"type": "hem"},
            {"edge_name": "Edge1"},
        )
        assert ok is True
        assert err is None

    def test_green_hem_open(self) -> None:
        doc = _one_body_doc(face_count=6, add_faces=4)
        ok, err = create_hem(
            doc,
            {"type": "hem", "hem_type": 0, "d_length_m": 0.015, "d_gap_m": 0.002},
            {"edge_name": "Edge1"},
        )
        assert ok is True

    def test_noop_fails_soft(self) -> None:
        """InsertSheetMetalHem that adds no faces → (False, reason)."""
        doc = _one_body_doc(face_count=6, will_hem=False)
        ok, err = create_hem(
            doc,
            {"type": "hem"},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "returned None" in err

    def test_zero_face_delta_fails_soft(self) -> None:
        """Hem created but no face delta → ghost feature detected."""
        doc = _one_body_doc(face_count=6, add_faces=0)
        ok, err = create_hem(
            doc,
            {"type": "hem"},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "face count" in err

    def test_exception_in_insert_fails_soft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _RaisingOleObj:
            def InvokeTypes(self, *_: Any, **__: Any) -> None:
                raise RuntimeError("seat error")

        class _RaisingFM:
            _oleobj_ = _RaisingOleObj()

        doc = _one_body_doc()
        doc.FeatureManager = _RaisingFM()  # type: ignore[assignment]
        ok, err = create_hem(
            doc,
            {"type": "hem"},
            {"edge_name": "Edge1"},
        )
        assert ok is False
        assert "InsertSheetMetalHem failed" in err

    def test_multi_edge_target(self) -> None:
        doc = _one_body_doc(face_count=12, edges=["Edge1", "Edge2", "Edge3"], add_faces=5)
        ok, err = create_hem(
            doc,
            {"type": "hem"},
            {"edge_name": "Edge2"},
        )
        assert ok is True


# ---------------------------------------------------------------------------
# Registry dispatch — hem auto-advertised
# ---------------------------------------------------------------------------

class TestRegistryDispatch:
    def test_kind_in_handler_registry(self) -> None:
        assert "hem" in HANDLER_REGISTRY

    def test_registry_handler_is_create_fn(self) -> None:
        assert HANDLER_REGISTRY["hem"] is create_hem

    def test_registry_dispatches_correctly(self) -> None:
        doc = _one_body_doc(face_count=6, add_faces=3)
        feature = {"type": "hem"}
        tgt = {"edge_name": "Edge1"}
        ok, err = HANDLER_REGISTRY["hem"](doc, feature, tgt)
        assert ok is True
        assert err is None
