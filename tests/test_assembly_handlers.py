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


# ---- verify_mates tests ----------------------------------------------------


class TestVerifyMates:
    """Tests for the verify_mates() FeatureManager traversal."""

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_returns_empty_when_no_features(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import verify_mates

        asm = MagicMock()
        asm.FeatureManager.GetFeatures.return_value = []
        asm.ForceRebuild3.return_value = True

        mock_typed.side_effect = lambda obj, iface, module=None: obj

        results = verify_mates(asm)
        assert results == []

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_traverses_two_mates(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import verify_mates

        mate1 = MagicMock()
        mate1.Name = "Coincident1"
        mate1.GetTypeName2.return_value = "MateCoincident"
        mate1.GetSuppression2.return_value = 1
        mate1.GetErrorCode2.return_value = 0

        mate2 = MagicMock()
        mate2.Name = "Distance1"
        mate2.GetTypeName2.return_value = "MateDistance"
        mate2.GetSuppression2.return_value = 1
        mate2.GetErrorCode2.return_value = 0

        non_mate = MagicMock()
        non_mate.GetTypeName2.return_value = "Extrusion"

        asm = MagicMock()
        asm.FeatureManager.GetFeatures.return_value = [non_mate, mate2, mate1]
        asm.ForceRebuild3.return_value = True

        mock_typed.side_effect = lambda obj, iface, module=None: obj

        results = verify_mates(asm)
        assert len(results) == 2
        assert results[0]["name"] == "Distance1"
        assert results[0]["type"] == "MateDistance"
        assert results[0]["solved"] is True
        assert results[1]["name"] == "Coincident1"
        assert results[1]["type"] == "MateCoincident"
        assert results[1]["solved"] is True

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_detects_suppressed_mate(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import verify_mates

        mate = MagicMock()
        mate.Name = "BadMate"
        mate.GetTypeName2.return_value = "MateCoincident"
        mate.GetSuppression2.return_value = 0  # suppressed
        mate.GetErrorCode2.return_value = 2  # error

        asm = MagicMock()
        asm.FeatureManager.GetFeatures.return_value = [mate]
        asm.ForceRebuild3.return_value = True

        mock_typed.side_effect = lambda obj, iface, module=None: obj

        results = verify_mates(asm)
        assert len(results) == 1
        assert results[0]["solved"] is False
        assert results[0]["suppressed"] is True
        assert results[0]["error_code"] == 2


# ---- create_exploded_view -------------------------------------------------


class TestCreateExplodedView:
    """Tests for the exploded view handler (W32v)."""

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_creates_step_on_happy_path(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_exploded_view

        # Fake IConfiguration that records AddExplodeStep calls
        step_obj = MagicMock()
        step_obj.GetNumOfComponents.return_value = 1

        mock_cfg_cls = MagicMock()
        mock_cfg_inst = MagicMock()
        mock_cfg_inst.AddExplodeStep.return_value = step_obj
        mock_cfg_cls.return_value = mock_cfg_inst
        mock_wm.return_value = MagicMock(IConfiguration=mock_cfg_cls)

        sel_mgr = MagicMock()
        sel_mgr.GetSelectedObjectCount2.return_value = 2

        model_ext = MagicMock()
        model_ext.SelectByID2.return_value = True

        typed_model_mock = MagicMock()
        typed_model_mock.GetActiveConfiguration.return_value = MagicMock(_oleobj_=MagicMock())
        typed_model_mock.SelectionManager = sel_mgr
        typed_model_mock.Extension = model_ext
        typed_model_mock.ClearSelection2.return_value = True

        def typed_side(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                m = MagicMock()
                m.CreateExplodedView.return_value = True
                return m
            elif iface == "IModelDoc2":
                return typed_model_mock
            return MagicMock()

        mock_typed.side_effect = typed_side

        asm = MagicMock()
        asm.GetTitle = "Asm1.SLDASM"

        comp = MagicMock()
        comp.Select2.return_value = True
        comp._oleobj_ = MagicMock()
        placed = {"b": comp}

        view_spec = {
            "name": "Default",
            "steps": [
                {
                    "components": ["b"],
                    "distance_mm": 50.0,
                    "direction": "front",
                },
            ],
        }

        count, err = create_exploded_view(asm, placed, view_spec)

        assert err is None
        assert count == 1
        mock_cfg_inst.AddExplodeStep.assert_called_once()

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_fails_on_create_exploded_view_false(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_exploded_view

        def typed_side(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                m = MagicMock()
                m.CreateExplodedView.return_value = False
                return m
            return MagicMock()

        mock_typed.side_effect = typed_side

        asm = MagicMock()
        count, err = create_exploded_view(asm, {}, {"name": "X", "steps": []})

        assert count == 0
        assert "CreateExplodedView" in (err or "")

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_fails_on_missing_component(
        self, mock_typed: MagicMock, mock_wm: MagicMock
    ) -> None:
        from ai_sw_bridge.assembly.handlers import create_exploded_view

        step_obj = MagicMock()

        mock_cfg_cls = MagicMock()
        mock_cfg_inst = MagicMock()
        mock_cfg_inst.AddExplodeStep.return_value = step_obj
        mock_cfg_cls.return_value = mock_cfg_inst
        mock_wm.return_value = MagicMock(IConfiguration=mock_cfg_cls)

        typed_model_mock = MagicMock()
        typed_model_mock.GetActiveConfiguration.return_value = MagicMock(_oleobj_=MagicMock())
        typed_model_mock.SelectionManager = MagicMock()
        typed_model_mock.Extension = MagicMock()

        def typed_side(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                m = MagicMock()
                m.CreateExplodedView.return_value = True
                return m
            elif iface == "IModelDoc2":
                return typed_model_mock
            return MagicMock()

        mock_typed.side_effect = typed_side

        asm = MagicMock()
        asm.GetTitle = "Asm1.SLDASM"

        # Empty placed dict — component "b" not found
        count, err = create_exploded_view(
            asm, {},
            {"name": "X", "steps": [
                {"components": ["b"], "distance_mm": 50.0, "direction": "front"}
            ]},
        )

        assert count == 0
        assert "not found" in (err or "")

    @patch("ai_sw_bridge.assembly.handlers.wrapper_module")
    @patch("ai_sw_bridge.assembly.handlers.typed")
    def test_multiple_steps(self, mock_typed: MagicMock, mock_wm: MagicMock) -> None:
        from ai_sw_bridge.assembly.handlers import create_exploded_view

        step_obj = MagicMock()

        mock_cfg_cls = MagicMock()
        mock_cfg_inst = MagicMock()
        mock_cfg_inst.AddExplodeStep.return_value = step_obj
        mock_cfg_cls.return_value = mock_cfg_inst
        mock_wm.return_value = MagicMock(IConfiguration=mock_cfg_cls)

        sel_mgr = MagicMock()
        sel_mgr.GetSelectedObjectCount2.return_value = 2

        typed_model_mock = MagicMock()
        typed_model_mock.GetActiveConfiguration.return_value = MagicMock(_oleobj_=MagicMock())
        typed_model_mock.SelectionManager = sel_mgr
        typed_model_mock.Extension = MagicMock(SelectByID2=MagicMock(return_value=True))
        typed_model_mock.ClearSelection2.return_value = True

        def typed_side(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                m = MagicMock()
                m.CreateExplodedView.return_value = True
                return m
            elif iface == "IModelDoc2":
                return typed_model_mock
            return MagicMock()

        mock_typed.side_effect = typed_side

        asm = MagicMock()
        asm.GetTitle = "Asm1.SLDASM"

        comp_a = MagicMock(Select2=MagicMock(return_value=True))
        comp_b = MagicMock(Select2=MagicMock(return_value=True))
        placed = {"a": comp_a, "b": comp_b}

        view_spec = {
            "name": "Default",
            "steps": [
                {"components": ["a"], "distance_mm": 30.0, "direction": "top"},
                {"components": ["b"], "distance_mm": 50.0, "direction": "right"},
            ],
        }

        count, err = create_exploded_view(asm, placed, view_spec)

        assert err is None
        assert count == 2
        assert mock_cfg_inst.AddExplodeStep.call_count == 2
