"""W67 — unit coverage for the consolidated verify substrate.

Covers the shared readers, the FeatureClass gates (boundary behavior), and the
W67 Phase-3 ``visible_only`` normalization (every reader now counts ALL bodies
by default — a hidden but created body is a real effect).
"""

from __future__ import annotations

from ai_sw_bridge.features import verify as v


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _Body:
    def __init__(self, faces: int = 1, vol_m3: float = 0.0) -> None:
        self._faces = faces
        self._vol_m3 = vol_m3

    def GetFaces(self):  # noqa: N802
        return [object() for _ in range(self._faces)]

    def GetMassProperties(self, accuracy):  # noqa: N802
        # SW layout: index 3 = volume (m³).
        return [0.0, 0.0, 0.0, self._vol_m3, 0.0, 0.0]


class _VisibilityDoc:
    """GetBodies2 returns a SUPERSET when visible_only is False."""

    def __init__(self, visible, hidden) -> None:
        self._visible = list(visible)
        self._all = list(visible) + list(hidden)

    def GetBodies2(self, body_type, visible_only):  # noqa: N802
        return self._visible if visible_only else self._all


class _Node:
    def __init__(self, name2=None, name=None) -> None:
        if name2 is not None:
            self.GetTypeName2 = lambda: name2  # noqa: N802
        if name is not None:
            self.GetTypeName = lambda: name  # noqa: N802


class _FM:
    def __init__(self, feats) -> None:
        self._feats = feats

    def GetFeatures(self, top_only):  # noqa: N802
        return self._feats


class _Doc:
    def __init__(self, feats) -> None:
        self.FeatureManager = _FM(feats)


# ---------------------------------------------------------------------------
# Phase-3 visible_only normalization — the headline regression
# ---------------------------------------------------------------------------
class TestVisibleOnlyNormalization:
    def test_solid_body_count_counts_hidden_by_default(self) -> None:
        doc = _VisibilityDoc(visible=[_Body()], hidden=[_Body()])
        # Default (Phase-3): count ALL bodies including the hidden one.
        assert v.solid_body_count(doc) == 2
        # The historical visible-only behavior is still reachable explicitly.
        assert v.solid_body_count(doc, visible_only=True) == 1

    def test_sheet_body_count_counts_hidden_by_default(self) -> None:
        doc = _VisibilityDoc(visible=[_Body()], hidden=[_Body(), _Body()])
        assert v.sheet_body_count(doc) == 3
        assert v.sheet_body_count(doc, visible_only=True) == 1

    def test_solid_metrics_aggregates_all_bodies(self) -> None:
        doc = _VisibilityDoc(
            visible=[_Body(faces=4, vol_m3=1e-6)],
            hidden=[_Body(faces=2, vol_m3=2e-6)],
        )
        faces, vol_mm3 = v.solid_metrics(doc)  # default False
        assert faces == 6
        assert abs(vol_mm3 - 3000.0) < 1e-6  # (1e-6 + 2e-6) m³ * 1e9


# ---------------------------------------------------------------------------
# Body readers — robustness
# ---------------------------------------------------------------------------
class TestBodyReaders:
    def test_bodies_none_on_com_failure(self) -> None:
        class _Boom:
            def GetBodies2(self, *a):  # noqa: N802
                raise RuntimeError("COM down")

        assert v.bodies(_Boom(), v.SW_SOLID_BODY, False) is None

    def test_bodies_empty_list_when_none(self) -> None:
        class _Empty:
            def GetBodies2(self, *a):  # noqa: N802
                return None

        assert v.bodies(_Empty(), v.SW_SOLID_BODY, False) == []

    def test_solid_body_count_zero_on_failure(self) -> None:
        class _Boom:
            def GetBodies2(self, *a):  # noqa: N802
                raise RuntimeError("x")

        assert v.solid_body_count(_Boom()) == 0


# ---------------------------------------------------------------------------
# Feature-node readers
# ---------------------------------------------------------------------------
class TestFeatureNodes:
    def test_count_none_and_raise_are_zero(self) -> None:
        assert v.feature_node_count(_Doc(None)) == 0

        class _BoomFM:
            def GetFeatures(self, _):  # noqa: N802
                raise RuntimeError("severed")

        class _BoomDoc:
            FeatureManager = _BoomFM()

        assert v.feature_node_count(_BoomDoc()) == 0

    def test_count_returns_length(self) -> None:
        assert v.feature_node_count(_Doc([1, 2, 3, 4, 5])) == 5

    def test_type_name_prefers_name2_then_falls_back(self) -> None:
        assert v.type_name(_Node(name2="Helix")) == "Helix"
        # GetTypeName2 absent -> fallback to GetTypeName
        assert v.type_name(_Node(name="RefCurve")) == "RefCurve"
        # neither -> None
        assert v.type_name(_Node()) is None

    def test_count_nodes_by_type_exact(self) -> None:
        doc = _Doc([_Node(name2="Helix"), _Node(name2="Cut"), _Node(name2="Helix")])
        assert v.count_nodes_by_type(doc, ("Helix",), match="exact") == 2

    def test_count_nodes_by_type_substring(self) -> None:
        doc = _Doc([_Node(name2="ProjectedCurve"), _Node(name2="Boss")])
        assert v.count_nodes_by_type(doc, ("projectedcurve",), match="substring") == 1

    def test_count_nodes_by_type_limit(self) -> None:
        doc = _Doc([_Node(name2="Helix"), _Node(name2="Helix"), _Node(name2="Helix")])
        assert v.count_nodes_by_type(doc, ("Helix",), match="exact", limit=1) == 1


# ---------------------------------------------------------------------------
# Class gates — boundary behavior (thresholds locked)
# ---------------------------------------------------------------------------
class TestGates:
    def test_additive_solid(self) -> None:
        assert v.gate_additive_solid(8, 1103.84) is True
        assert v.gate_additive_solid(0, 1103.84) is False     # no new faces
        assert v.gate_additive_solid(8, 1e-9) is False        # vol below eps

    def test_fold(self) -> None:
        before = (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
        after = (0.0, 0.0, 0.0, 1.0, 1.0, 1.5)
        assert v.gate_fold(8, before, after) is True
        assert v.gate_fold(0, before, after) is False
        assert v.gate_fold(8, before, before) is False        # bbox unchanged

    def test_fold_volume_preserving(self) -> None:
        assert v.gate_fold_volume_preserving(2, 1e-9) is True
        assert v.gate_fold_volume_preserving(2, 1.0) is False  # volume changed
        assert v.gate_fold_volume_preserving(0, 1e-9) is False

    def test_surface_create(self) -> None:
        assert v.gate_surface_create(1, 600.0) is True
        assert v.gate_surface_create(0, 600.0) is False        # no new sheet
        assert v.gate_surface_create(1, 1e-9) is False         # area below eps

    def test_surface_aggregate_inverted(self) -> None:
        assert v.gate_surface_aggregate(-1, 1900.0) is True    # sheets consumed
        assert v.gate_surface_aggregate(1, 1900.0) is False    # sheets INCREASED
        assert v.gate_surface_aggregate(-1, 1e-9) is False     # area ghost

    def test_surface_to_solid(self) -> None:
        assert v.gate_surface_to_solid(500.0, 1) is True
        assert v.gate_surface_to_solid(0.0, 1) is False
        assert v.gate_surface_to_solid(500.0, 0) is False


# ---------------------------------------------------------------------------
# CURVE geometric witness (W67 P3b) — proven tail + hard gate + head ladder
# ---------------------------------------------------------------------------
class _Curve:
    """Fake ICurve: GetEndParams -> (status, tmin, tmax, ...); GetLength(t1,t2) m."""

    def __init__(self, length_m: float, tmin: float = 0.0, tmax: float = 1.0) -> None:
        self._len_m = length_m
        self._tmin = tmin
        self._tmax = tmax

    def GetEndParams(self):  # noqa: N802
        return (True, self._tmin, self._tmax, False, False)

    def GetLength(self, t1, t2):  # noqa: N802
        return self._len_m


class _Edge:
    """Fake reference-curve segment (an edge) whose GetCurve() -> ICurve."""

    def __init__(self, curve) -> None:
        self._curve = curve

    def GetCurve(self):  # noqa: N802
        return self._curve


class _SpecWithSegments:
    """Fake IReferenceCurve: GetSegments() -> edge[] (the seat-proven head)."""

    def __init__(self, *edges) -> None:
        self._edges = list(edges)

    def GetSegments(self):  # noqa: N802
        return self._edges


class _SpecWithCurves:
    """Fake GetSpecificFeature2() return exposing GetCurves() -> ICurve[]
    (the defensive last-ditch branch)."""

    def __init__(self, *curves) -> None:
        self._curves = list(curves)

    def GetCurves(self):  # noqa: N802
        return self._curves


class _CurveNode:
    """Fake IFeature whose GetSpecificFeature2() yields a curve-bearing spec."""

    def __init__(self, spec) -> None:
        self._spec = spec

    def GetSpecificFeature2(self):  # noqa: N802
        return self._spec


class TestCurveWitness:
    def test_icurve_length_mm_proven_tail(self) -> None:
        # 0.025 m arc -> 25.0 mm.
        assert abs(v.icurve_length_mm(_Curve(0.025)) - 25.0) < 1e-9

    def test_icurve_length_none_when_degenerate(self) -> None:
        # tmax <= tmin -> unreadable.
        assert v.icurve_length_mm(_Curve(0.025, tmin=1.0, tmax=1.0)) is None
        assert v.icurve_length_mm(None) is None

    def test_curve_length_mm_via_reference_curve_segments(self) -> None:
        # PRIMARY seat-proven head: IReferenceCurve.GetSegments() -> edges ->
        # IEdge.GetCurve() -> ICurve -> length.
        node = _CurveNode(
            _SpecWithSegments(_Edge(_Curve(0.010)), _Edge(_Curve(0.005)))
        )
        assert abs(v.curve_length_mm(node) - 15.0) < 1e-9

    def test_curve_length_mm_defensive_get_curves(self) -> None:
        # LAST-DITCH branch: spec exposes GetCurves() directly.
        node = _CurveNode(_SpecWithCurves(_Curve(0.010), _Curve(0.005)))
        assert abs(v.curve_length_mm(node) - 15.0) < 1e-9

    def test_curve_length_mm_none_when_no_geometry(self) -> None:
        # A node whose specific feature exposes no curves -> ghost (None).
        assert v.curve_length_mm(_CurveNode(_SpecWithCurves())) is None
        assert v.curve_length_mm(None) is None

    def test_gate_curve_is_hard(self) -> None:
        assert v.gate_curve(1, 25.0) is True
        assert v.gate_curve(0, 25.0) is False        # no new node
        assert v.gate_curve(1, 1e-9) is False        # length below eps (ghost)
        # HARD gate: unreadable length is FAILURE, never node-count fallback.
        assert v.gate_curve(1, None) is False


# ---------------------------------------------------------------------------
# Centroid
# ---------------------------------------------------------------------------
class TestCentroid:
    def test_centroid_reads_center_of_mass(self) -> None:
        class _MP:
            CenterOfMass = (0.01, 0.02, 0.03)

        class _Ext:
            def CreateMassProperty(self):  # noqa: N802
                return _MP()

        class _D:
            Extension = _Ext()

        assert v.body_centroid_m(_D()) == (0.01, 0.02, 0.03)

    def test_centroid_none_on_failure(self) -> None:
        class _D:
            @property
            def Extension(self):  # noqa: N802
                raise RuntimeError("no ext")

        assert v.body_centroid_m(_D()) is None
