"""Tests for assembly placement + mate handlers (Wave-9 Slices 4-5).

Fake-doc tests: all COM objects are mocked. No SOLIDWORKS required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---- Fake COM objects ------------------------------------------------------


class FakeBody:
    def __init__(self, n_bodies: int = 1) -> None:
        self._n = n_bodies

    def GetFaces(self) -> tuple:
        return ()


class FakeModelDoc:
    def __init__(self, n_bodies: int = 1) -> None:
        self._bodies = tuple(FakeBody() for _ in range(n_bodies))

    def GetBodies2(self, body_type: int, visible: bool) -> tuple:
        return self._bodies


class FakeComponent:
    def __init__(self, name: str = "comp-1", n_bodies: int = 1) -> None:
        self.Name = name
        self._model = FakeModelDoc(n_bodies)

    def GetModelDoc2(self) -> FakeModelDoc:
        return self._model


class FakeAssemblyDoc:
    """Fake IAssemblyDoc that records AddComponent4/CreateMate calls."""

    def __init__(self) -> None:
        self._components: list[FakeComponent] = []
        self._mates: list[Any] = []
        self._next_comp_idx = 0

    def AddComponent4(
        self, path: str, config: str, x: float, y: float, z: float
    ) -> FakeComponent:
        self._next_comp_idx += 1
        comp = FakeComponent(f"comp-{self._next_comp_idx}")
        self._components.append(comp)
        return comp

    def CreateMateData(self, mate_type: int) -> MagicMock:
        return MagicMock()

    def CreateMate(self, mate_data: Any) -> MagicMock:
        feat = MagicMock()
        self._mates.append(feat)
        return feat


class FakeSldWorks:
    """Fake ISldWorks that records OpenDoc6 calls."""

    def __init__(self) -> None:
        self._opened: list[str] = []

    def OpenDoc6(self, path: str, *args: Any) -> tuple:
        self._opened.append(path)
        return (MagicMock(), 0)


# ---- Mock helpers ----------------------------------------------------------


def _make_mock_mod() -> MagicMock:
    """Create a mock gen_py module with the necessary typed classes."""
    mod = MagicMock()

    # typed(sw, "ISldWorks") → FakeSldWorks-like
    # typed(asm, "IAssemblyDoc") → FakeAssemblyDoc-like
    # We use side_effect to return the object itself for typed()
    return mod


# ---- Placement tests -------------------------------------------------------


class TestPlaceComponents:
    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    def test_places_two_components(
        self, mock_typed_qi: MagicMock, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import place_components

        sw = FakeSldWorks()
        asm = FakeAssemblyDoc()

        mock_typed.side_effect = lambda obj, iface, module=None: (
            sw if iface == "ISldWorks" else
            asm if iface == "IAssemblyDoc" else
            obj
        )

        components = [
            {"id": "a", "part": "/parts/a.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "/parts/b.sldprt", "transform": {"xyz_mm": [100, 0, 0]}},
        ]

        placed, err = place_components(sw, asm, components)
        assert err is None
        assert len(placed) == 2
        assert "a" in placed
        assert "b" in placed
        assert len(sw._opened) == 2  # both parts pre-opened
        assert len(asm._components) == 2

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_fails_on_missing_part_path(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import place_components

        sw = FakeSldWorks()
        asm = FakeAssemblyDoc()
        mock_typed.side_effect = lambda obj, iface, module=None: (
            sw if iface == "ISldWorks" else asm
        )

        components = [{"id": "a"}]  # no 'part' key
        placed, err = place_components(sw, asm, components)
        assert err is not None
        assert "no resolved part path" in err

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_fails_when_add_component_returns_none(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import place_components

        sw = FakeSldWorks()
        asm = FakeAssemblyDoc()
        asm.AddComponent4 = lambda *a: None  # type: ignore[assignment]

        mock_typed.side_effect = lambda obj, iface, module=None: (
            sw if iface == "ISldWorks" else asm
        )

        components = [{"id": "a", "part": "/a.sldprt"}]
        placed, err = place_components(sw, asm, components)
        assert err is not None
        assert "AddComponent4 returned None" in err

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_transform_converts_mm_to_meters(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import place_components

        sw = FakeSldWorks()
        asm = FakeAssemblyDoc()
        calls: list[tuple] = []

        def record_add(path: str, config: str, x: float, y: float, z: float) -> FakeComponent:
            calls.append((x, y, z))
            return FakeComponent()

        asm.AddComponent4 = record_add  # type: ignore[assignment]
        mock_typed.side_effect = lambda obj, iface, module=None: (
            sw if iface == "ISldWorks" else asm
        )

        components = [
            {"id": "a", "part": "/a.sldprt", "transform": {"xyz_mm": [100, 200, 300]}}
        ]
        placed, err = place_components(sw, asm, components)
        assert err is None
        assert calls[0] == pytest.approx((0.1, 0.2, 0.3))


# ---- Mate tests ------------------------------------------------------------


class TestCreateCoincidentMate:
    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_creates_mate(
        self,
        mock_resolve: MagicMock,
        mock_typed_qi: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_coincident_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        fake_face_a = MagicMock()
        fake_face_b = MagicMock()

        mock_resolve.side_effect = [
            ComponentFaceResolution(fake_face_a, "persist_id"),
            ComponentFaceResolution(fake_face_b, "persist_id"),
        ]

        mock_coin_data = MagicMock()
        mock_typed_qi.return_value = mock_coin_data

        mock_mate_feat = MagicMock()
        asm.CreateMate = lambda data: mock_mate_feat  # type: ignore[assignment]

        mock_ifeat = MagicMock()
        mock_ifeat.GetTypeName2.return_value = "MateCoincident"

        def typed_side(obj: Any, iface: str, module: Any = None) -> Any:
            if iface == "IAssemblyDoc":
                return asm
            if iface == "IFeature":
                return mock_ifeat
            return obj

        mock_typed.side_effect = typed_side

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "coincident",
            "alignment": "aligned",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
        }

        feat, err = create_coincident_mate(asm, placed, mate_spec)
        assert err is None
        assert feat is mock_mate_feat

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_fails_when_face_unresolved(
        self,
        mock_resolve: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_coincident_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        mock_resolve.return_value = ComponentFaceResolution(
            None, "unresolved", "no match"
        )
        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "coincident",
            "alignment": "aligned",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
        }

        feat, err = create_coincident_mate(asm, placed, mate_spec)
        assert feat is None
        assert err is not None
        assert "face unresolved" in err

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_fails_when_component_not_placed(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_coincident_mate

        asm = FakeAssemblyDoc()
        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else obj
        )

        placed = {"a": FakeComponent("a-1")}  # "b" not placed
        mate_spec = {
            "type": "coincident",
            "alignment": "aligned",
            "a": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
            "b": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
        }

        feat, err = create_coincident_mate(asm, placed, mate_spec)
        assert feat is None
        assert "not placed" in err


# ---- Phase-2 mate type tests -----------------------------------------------


class TestCreateMate:
    """Tests for the generalized create_mate handler supporting all mate types."""

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_creates_distance_mate_with_value(
        self,
        mock_resolve: MagicMock,
        mock_typed_qi: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        fake_face_a = MagicMock()
        fake_face_b = MagicMock()

        mock_resolve.side_effect = [
            ComponentFaceResolution(fake_face_a, "persist_id"),
            ComponentFaceResolution(fake_face_b, "persist_id"),
        ]

        mock_dist_data = MagicMock()
        mock_typed_qi.return_value = mock_dist_data

        mock_mate_feat = MagicMock()
        asm.CreateMate = lambda data: mock_mate_feat

        mock_ifeat = MagicMock()
        mock_ifeat.GetTypeName2.return_value = "MateDistance"

        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else
            mock_ifeat if iface == "IFeature" else
            obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "distance",
            "alignment": "aligned",
            "value_mm": 25.0,
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
        }

        feat, err = create_mate(asm, placed, mate_spec)
        assert err is None
        assert feat is mock_mate_feat
        # Verify Distance was set (25mm = 0.025m)
        assert mock_dist_data.Distance == pytest.approx(0.025)

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_creates_concentric_mate(
        self,
        mock_resolve: MagicMock,
        mock_typed_qi: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        mock_resolve.side_effect = [
            ComponentFaceResolution(MagicMock(), "persist_id"),
            ComponentFaceResolution(MagicMock(), "persist_id"),
        ]

        mock_typed_qi.return_value = MagicMock()

        mock_mate_feat = MagicMock()
        asm.CreateMate = lambda data: mock_mate_feat

        mock_ifeat = MagicMock()
        mock_ifeat.GetTypeName2.return_value = "MateConcentric"

        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else
            mock_ifeat if iface == "IFeature" else
            obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "concentric",
            "a": {"component": "a", "face_ref": {"normal": [1, 0, 0]}},
            "b": {"component": "b", "face_ref": {"normal": [1, 0, 0]}},
        }

        feat, err = create_mate(asm, placed, mate_spec)
        assert err is None
        assert feat is mock_mate_feat

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_creates_parallel_mate(
        self,
        mock_resolve: MagicMock,
        mock_typed_qi: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        mock_resolve.side_effect = [
            ComponentFaceResolution(MagicMock(), "persist_id"),
            ComponentFaceResolution(MagicMock(), "persist_id"),
        ]

        mock_typed_qi.return_value = MagicMock()

        mock_mate_feat = MagicMock()
        asm.CreateMate = lambda data: mock_mate_feat

        mock_ifeat = MagicMock()
        mock_ifeat.GetTypeName2.return_value = "MateParallel"

        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else
            mock_ifeat if iface == "IFeature" else
            obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "parallel",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, 1]}},
        }

        feat, err = create_mate(asm, placed, mate_spec)
        assert err is None
        assert feat is mock_mate_feat

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    @patch("ai_sw_bridge.assembly.handlers.typed_qi")
    @patch("ai_sw_bridge.assembly.handlers.resolve_component_face")
    def test_creates_perpendicular_mate(
        self,
        mock_resolve: MagicMock,
        mock_typed_qi: MagicMock,
        mock_typed: MagicMock,
        mock_wm: MagicMock,
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_mate
        from ai_sw_bridge.assembly.face_resolver import ComponentFaceResolution

        asm = FakeAssemblyDoc()
        mock_resolve.side_effect = [
            ComponentFaceResolution(MagicMock(), "persist_id"),
            ComponentFaceResolution(MagicMock(), "persist_id"),
        ]

        mock_typed_qi.return_value = MagicMock()

        mock_mate_feat = MagicMock()
        asm.CreateMate = lambda data: mock_mate_feat

        mock_ifeat = MagicMock()
        mock_ifeat.GetTypeName2.return_value = "MatePerpendicular"

        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else
            mock_ifeat if iface == "IFeature" else
            obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "perpendicular",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [1, 0, 0]}},
        }

        feat, err = create_mate(asm, placed, mate_spec)
        assert err is None
        assert feat is mock_mate_feat

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_rejects_unsupported_mate_type(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_mate

        asm = FakeAssemblyDoc()
        mock_typed.side_effect = lambda obj, iface, module=None: (
            asm if iface == "IAssemblyDoc" else obj
        )

        placed = {"a": FakeComponent("a-1"), "b": FakeComponent("b-1")}
        mate_spec = {
            "type": "unknown_mate",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
        }

        feat, err = create_mate(asm, placed, mate_spec)
        assert feat is None
        assert "unsupported mate type" in err
