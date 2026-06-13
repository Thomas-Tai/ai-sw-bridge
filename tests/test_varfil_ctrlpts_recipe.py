"""Offline tests for the variable-fillet control-point recipe shape.

Tests the recipe documented in ``spikes/v0_2x/spike_varfil_ctrlpts.py``:
intermediate radii at parametric positions along a fillet edge, via
``IVariableFilletFeatureData2.SetControlPointRadiusAtIndex``.

All COM objects are mocked — no SOLIDWORKS seat required.
"""

from __future__ import annotations

from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fake COM: IVariableFilletFeatureData2 (control-point surface)
# ---------------------------------------------------------------------------


class _FakeEdge:
    """Stand-in for an IEdge returned by GetFilletEdgeAtIndex."""

    def __init__(self, edge_id: int) -> None:
        self.edge_id = edge_id


class _FakeVarFilletData:
    """Mock of IVariableFilletFeatureData2.

    Tracks all control-point setter calls and provides readback, mirroring
    the typelib-declared API surface:
      - DefaultRadius (property)
      - FilletEdgeCount (property, get-only)
      - GetFilletEdgeAtIndex(Index) -> IEdge
      - GetControlPointsCount() -> int
      - SetControlPointRadiusAtIndex(Index, Location, Radius)
      - GetControlPointRadiusAtIndex(Index) -> (Radius, Location, Edge)
      - TransitionType (property)
    """

    def __init__(self, n_edges: int = 1) -> None:
        self._n_edges = n_edges
        self._edges = [_FakeEdge(i) for i in range(n_edges)]
        self._control_points: list[tuple[int, float, float]] = []
        self.default_radius: float = 0.0
        self.transition_type: int = 0
        self.init_calls: list[int] = []
        self.access_calls: list[tuple] = []

    def Initialize(self, fillet_type: int) -> bool:
        self.init_calls.append(fillet_type)
        return True

    @property
    def DefaultRadius(self) -> float:
        return self.default_radius

    @DefaultRadius.setter
    def DefaultRadius(self, v: float) -> None:
        self.default_radius = v

    @property
    def FilletEdgeCount(self) -> int:
        return self._n_edges

    def GetFilletEdgeAtIndex(self, index: int) -> _FakeEdge:
        if index < 0 or index >= self._n_edges:
            raise IndexError(f"edge index {index} out of range")
        return self._edges[index]

    @property
    def TransitionType(self) -> int:
        return self.transition_type

    @TransitionType.setter
    def TransitionType(self, v: int) -> None:
        self.transition_type = v

    def AccessSelections(self, doc: Any, comp: Any) -> bool:
        self.access_calls.append((doc, comp))
        return True

    def GetControlPointsCount(self) -> int:
        return len(self._control_points)

    def SetControlPointRadiusAtIndex(
        self, index: int, location: float, radius: float
    ) -> None:
        if index == len(self._control_points):
            self._control_points.append((index, location, radius))
        elif 0 <= index < len(self._control_points):
            self._control_points[index] = (index, location, radius)
        else:
            raise IndexError(f"control point index {index} out of range")

    def GetControlPointRadiusAtIndex(
        self, index: int
    ) -> tuple[float, float, _FakeEdge]:
        if index < 0 or index >= len(self._control_points):
            raise IndexError(f"control point index {index} out of range")
        _, loc, rad = self._control_points[index]
        edge = self._edges[0] if self._edges else _FakeEdge(-1)
        return (rad, loc, edge)


class _FakeFeature:
    """Mock created fillet feature."""

    def __init__(self, defn: _FakeVarFilletData) -> None:
        self._defn = defn
        self.Name = "Fillet1"
        self.modify_calls: list[tuple] = []

    def GetDefinition(self) -> _FakeVarFilletData:
        return self._defn

    def ModifyDefinition(self, defn: Any, doc: Any, comp: Any) -> bool:
        self.modify_calls.append((defn, doc, comp))
        return True

    def GetTypeName2(self) -> str:
        return "VariableFillet"


class _FakeFeatureManager:
    def __init__(self, data: _FakeVarFilletData, feature: _FakeFeature) -> None:
        self._data = data
        self._feature = feature
        self.create_def_calls: list[int] = []
        self.create_feat_calls: list[Any] = []

    def CreateDefinition(self, t: int) -> _FakeVarFilletData:
        self.create_def_calls.append(t)
        return self._data

    def CreateFeature(self, fd: Any) -> _FakeFeature:
        self.create_feat_calls.append(fd)
        return self._feature


# ---------------------------------------------------------------------------
# The proposed recipe (mirrors spike_varfil_ctrlpts.py Part 3)
# ---------------------------------------------------------------------------

SW_FM_FILLET = 1
SW_VARIABLE_RADIUS_FILLET = 1


def apply_ctrlpt_varfil_recipe(
    fm: _FakeFeatureManager,
    data: _FakeVarFilletData,
    base_radius_m: float,
    control_points: list[tuple[float, float]],
    transition_type: int = 0,
) -> dict[str, Any]:
    """Apply the proposed control-point variable-fillet recipe.

    Args:
        fm: The feature manager (mocked).
        data: The variable fillet data object (mocked).
        base_radius_m: Default radius in metres.
        control_points: List of (location_0_to_1, radius_m) pairs.
        transition_type: Transition profile between radii.

    Returns:
        Recipe execution record.
    """
    defn = fm.CreateDefinition(SW_FM_FILLET)
    data.Initialize(SW_VARIABLE_RADIUS_FILLET)
    data.DefaultRadius = base_radius_m
    data.TransitionType = transition_type

    set_calls: list[tuple[int, float, float]] = []
    for idx, (location, radius) in enumerate(control_points):
        data.SetControlPointRadiusAtIndex(idx, location, radius)
        set_calls.append((idx, location, radius))

    feat = fm.CreateFeature(data)
    return {
        "materialized": feat is not None,
        "feature_name": getattr(feat, "Name", None),
        "type_name": feat.GetTypeName2() if feat else None,
        "control_points_set": set_calls,
        "n_control_points": data.GetControlPointsCount(),
    }


# ---------------------------------------------------------------------------
# Tests: recipe shape
# ---------------------------------------------------------------------------


class TestCtrlPtRecipeShape:
    """Tests that the recipe correctly wires control-point count, position,
    and radius — the shape of the proposed handler."""

    def _wire(self, n_edges: int = 1):
        data = _FakeVarFilletData(n_edges=n_edges)
        feat = _FakeFeature(data)
        fm = _FakeFeatureManager(data, feat)
        return data, feat, fm

    def test_initialize_uses_variable_type(self) -> None:
        data, feat, fm = self._wire()
        apply_ctrlpt_varfil_recipe(fm, data, 0.002, [(0.5, 0.004)])
        assert data.init_calls == [SW_VARIABLE_RADIUS_FILLET]

    def test_default_radius_set(self) -> None:
        data, feat, fm = self._wire()
        apply_ctrlpt_varfil_recipe(fm, data, 0.003, [(0.5, 0.005)])
        assert data.default_radius == pytest.approx(0.003)

    def test_single_mid_edge_control_point(self) -> None:
        data, feat, fm = self._wire()
        result = apply_ctrlpt_varfil_recipe(fm, data, 0.002, [(0.5, 0.005)])
        assert result["materialized"] is True
        assert result["n_control_points"] == 1
        assert result["control_points_set"] == [(0, 0.5, 0.005)]

    def test_multiple_control_points_along_edge(self) -> None:
        data, feat, fm = self._wire()
        ctrl_pts = [(0.25, 0.003), (0.5, 0.005), (0.75, 0.004)]
        result = apply_ctrlpt_varfil_recipe(fm, data, 0.002, ctrl_pts)
        assert result["n_control_points"] == 3
        assert result["control_points_set"] == [
            (0, 0.25, 0.003),
            (1, 0.5, 0.005),
            (2, 0.75, 0.004),
        ]

    def test_control_point_readback_radius(self) -> None:
        data, feat, fm = self._wire()
        apply_ctrlpt_varfil_recipe(fm, data, 0.002, [(0.5, 0.005)])
        radius, location, edge = data.GetControlPointRadiusAtIndex(0)
        assert radius == pytest.approx(0.005)
        assert location == pytest.approx(0.5)

    def test_transition_type_set(self) -> None:
        data, feat, fm = self._wire()
        apply_ctrlpt_varfil_recipe(
            fm, data, 0.002, [(0.5, 0.005)], transition_type=2
        )
        assert data.transition_type == 2

    def test_create_feature_called(self) -> None:
        data, feat, fm = self._wire()
        apply_ctrlpt_varfil_recipe(fm, data, 0.002, [(0.5, 0.005)])
        assert len(fm.create_feat_calls) == 1
        assert fm.create_def_calls == [SW_FM_FILLET]

    def test_feature_type_name_is_variable(self) -> None:
        data, feat, fm = self._wire()
        result = apply_ctrlpt_varfil_recipe(fm, data, 0.002, [(0.5, 0.005)])
        assert result["type_name"] == "VariableFillet"


class TestCtrlPtRecipeVsBaseline:
    """Tests that the control-point recipe produces a DISCRIMINATING result
    vs the per-edge baseline — ΔVol is the success signal, not ok=True."""

    def _wire(self, n_edges: int = 1):
        data = _FakeVarFilletData(n_edges=n_edges)
        feat = _FakeFeature(data)
        fm = _FakeFeatureManager(data, feat)
        return data, feat, fm

    def test_ctrlpt_radius_differs_from_baseline(self) -> None:
        """A mid-edge control point at a different radius than the base
        radius must read back as the control-point value, not the base."""
        data, feat, fm = self._wire()
        base_r = 0.002
        ctrl_r = 0.005
        apply_ctrlpt_varfil_recipe(fm, data, base_r, [(0.5, ctrl_r)])

        read_r, read_loc, _ = data.GetControlPointRadiusAtIndex(0)
        assert read_r != pytest.approx(base_r), (
            "Control-point radius must differ from base radius "
            "(ΔVol discriminating signal)"
        )
        assert read_r == pytest.approx(ctrl_r)

    def test_ctrlpt_at_endpoints_matches_per_edge(self) -> None:
        """Control points at location 0.0 and 1.0 with the same radius as
        per-edge endpoints produce an equivalent fillet (no ΔVol)."""
        data, feat, fm = self._wire()
        base_r = 0.003
        apply_ctrlpt_varfil_recipe(
            fm, data, base_r, [(0.0, base_r), (1.0, base_r)]
        )
        r0, loc0, _ = data.GetControlPointRadiusAtIndex(0)
        r1, loc1, _ = data.GetControlPointRadiusAtIndex(1)
        assert r0 == pytest.approx(base_r)
        assert r1 == pytest.approx(base_r)
        assert loc0 == pytest.approx(0.0)
        assert loc1 == pytest.approx(1.0)


class TestFakeVarFilletDataSurface:
    """Tests that the fake IVariableFilletFeatureData2 surface matches the
    typelib-declared API — catches recipe drift vs the real interface."""

    def test_has_control_points_count(self) -> None:
        data = _FakeVarFilletData()
        assert hasattr(data, "GetControlPointsCount")
        assert data.GetControlPointsCount() == 0

    def test_has_set_control_point_radius(self) -> None:
        data = _FakeVarFilletData()
        assert hasattr(data, "SetControlPointRadiusAtIndex")

    def test_has_get_control_point_radius(self) -> None:
        data = _FakeVarFilletData()
        assert hasattr(data, "GetControlPointRadiusAtIndex")

    def test_has_fillet_edge_count(self) -> None:
        data = _FakeVarFilletData(n_edges=3)
        assert data.FilletEdgeCount == 3

    def test_has_get_fillet_edge_at_index(self) -> None:
        data = _FakeVarFilletData(n_edges=2)
        edge = data.GetFilletEdgeAtIndex(0)
        assert isinstance(edge, _FakeEdge)

    def test_has_transition_type(self) -> None:
        data = _FakeVarFilletData()
        assert hasattr(data, "TransitionType")
        data.TransitionType = 1
        assert data.TransitionType == 1

    def test_has_initialize(self) -> None:
        data = _FakeVarFilletData()
        result = data.Initialize(1)
        assert result is True

    def test_has_default_radius(self) -> None:
        data = _FakeVarFilletData()
        data.DefaultRadius = 0.003
        assert data.DefaultRadius == pytest.approx(0.003)

    def test_edge_index_out_of_range(self) -> None:
        data = _FakeVarFilletData(n_edges=1)
        with pytest.raises(IndexError):
            data.GetFilletEdgeAtIndex(5)

    def test_control_point_index_out_of_range(self) -> None:
        data = _FakeVarFilletData()
        with pytest.raises(IndexError):
            data.GetControlPointRadiusAtIndex(0)
