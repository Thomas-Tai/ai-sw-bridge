"""Offline tests — ``spiral`` handler (curve sibling of helix, seat-proven 2026-06-23).

A flat (planar) Archimedean spiral via the SAME legacy ``IModelDoc2.InsertHelix``
call as the helix lane, with two seat-proven differences (probe_spiral):

  * **DefinedBy = 3** (``swHelixDefinedBy_e.swHelixDefinedBySpiral``) — db 0/1/2/4/5
    all materialize a *helix*; only db=3 is the flat spiral.
  * **ConstantPitch = False** (arg 0) — with ConstantPitch=True db=3 SILENTLY
    no-ops (a spiral has a variable radius, so constant-pitch is degenerate).

Binding (the ref_axis trap): the disk-transaction path opens docs TYPED, so the
``Extension.SelectByID2`` VARIANT(VT_DISPATCH,None) callout AND ``InsertHelix``
both go through :func:`spiral._latebound`. Offline the seam is patched to
identity so the fakes drive directly.

Verify gate: a new 'Helix'-type node (a spiral is a Helix feature in SW) carrying
real arc length (the W42 ghost trap → CURVE gate requires a readable GetLength).

COM seams are patched on the lane module itself (``features.spiral``). No SW
process is involved; the live-seat proof is ``spikes/v0_2x/spike_spiral_gate_pae.py``.
"""

from __future__ import annotations

import math

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import spiral
from ai_sw_bridge.features.spiral import create_spiral


@pytest.fixture(autouse=True)
def _identity_latebound(monkeypatch):
    """Offline, the late-bound re-wrap (``win32com.client.dynamic.Dispatch``) has
    no live COM proxy to re-wrap — patch the seam to identity so the fakes drive
    the SelectByID2 / InsertHelix calls directly. The binding behaviour itself is
    proven on the live seat (spike_spiral_gate_pae)."""
    monkeypatch.setattr(spiral, "_latebound", lambda obj: obj)


@pytest.fixture(autouse=True)
def _mock_curve_length(monkeypatch):
    """The COM-heavy arc-length read is mocked to a positive default; the CURVE
    gate is exercised explicitly in TestCurveGate, which overrides this."""
    monkeypatch.setattr(spiral, "_curve_length_mm", lambda node: 25.0)


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeFeature:
    def __init__(self, type_name: str):
        self._type_name = type_name

    def GetTypeName(self):
        return self._type_name


class _FakeFM:
    def __init__(self, *, owning_doc=None):
        self._owning_doc = owning_doc

    def GetFeatures(self, top_only):
        return tuple(self._owning_doc.current_tree()) if self._owning_doc else ()


class _FakeExt:
    def __init__(self, *, owning_doc, select_ok=True):
        self._owning_doc = owning_doc
        self._select_ok = select_ok

    def SelectByID2(self, name, kind, x, y, z, append, mark, callout, opt):
        self._owning_doc.select_calls.append((name, kind, append, mark))
        return self._select_ok


class _FakeDoc:
    def __init__(self, *, select_ok=True, insert_effect=True, insert_raises=False):
        self.fm = _FakeFM()
        self.fm._owning_doc = self
        self.FeatureManager = self.fm
        self.Extension = _FakeExt(owning_doc=self, select_ok=select_ok)
        self._insert_effect = insert_effect
        self._insert_raises = insert_raises
        self.insert_calls: list[tuple] = []
        self.select_calls: list[tuple] = []
        self.cleared = False
        self.rebuilt = False
        self._spiral_count = 0
        self._base_nodes = [
            _FakeFeature("Origin"),
            _FakeFeature("Planes"),
            _FakeFeature("Base"),
            _FakeFeature("Sketch"),
        ]

    def current_tree(self) -> list[_FakeFeature]:
        nodes = list(self._base_nodes)
        for _ in range(self._spiral_count):
            nodes.append(_FakeFeature("Helix"))  # a spiral IS a Helix node in SW
        return nodes

    def ClearSelection2(self, flag):
        self.cleared = True

    def ForceRebuild3(self, flag):
        self.rebuilt = True

    def InsertHelix(self, *args):
        if self._insert_raises:
            raise RuntimeError("InsertHelix boom")
        self.insert_calls.append(args)
        if self._insert_effect:
            self._spiral_count += 1


# ---------------------------------------------------------------------------
# Operative path — the spiral recipe
# ---------------------------------------------------------------------------


class TestGreenPath:
    def test_green(self):
        doc = _FakeDoc()
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 10, "revolutions": 3, "start_angle_deg": 0, "clockwise": True},
            {"sketch": "SpiralBase"},
        )
        assert ok is True, err
        assert err is None
        assert len(doc.insert_calls) == 1
        assert len(doc.select_calls) == 1
        assert doc.select_calls[0] == ("SpiralBase", "SKETCH", False, 0)

    def test_spiral_args(self):
        """ConstantPitch=False (arg 0) and DefinedBy=3 (arg 4) are the whole
        difference from the helix recipe — pin them."""
        doc = _FakeDoc()
        ok, _ = create_spiral(
            doc,
            {
                "pitch_mm": 10,
                "revolutions": 3,
                "start_angle_deg": 90,
                "clockwise": True,
            },
            {"sketch": "SpiralBase"},
        )
        assert ok is True
        args = doc.insert_calls[0]
        assert len(args) == 10
        assert args[0] is False  # ConstantPitch — MUST be False for spiral
        assert args[3] is True  # Clockwise
        assert args[4] == 3  # DefinedBy = swHelixDefinedBySpiral
        assert args[5] == pytest.approx(0.010)  # Pitch 10 mm
        assert args[6] == pytest.approx(3.0)  # Revolution
        assert args[8] == pytest.approx(math.radians(90))  # StartAngle

    def test_defaults_applied(self):
        """pitch_mm defaults 5, revolutions defaults 3 when omitted."""
        doc = _FakeDoc()
        ok, _ = create_spiral(doc, {}, {"sketch": "SpiralBase"})
        assert ok is True
        args = doc.insert_calls[0]
        assert args[5] == pytest.approx(0.005)  # default pitch 5 mm
        assert args[6] == pytest.approx(3.0)  # default revolutions 3

    def test_uses_latebound_seam(self, monkeypatch):
        """Both SelectByID2 and InsertHelix must route through _latebound (the
        ref_axis binding trap). Count the re-wrap calls."""
        calls = []

        def real_identity(obj):
            calls.append(obj)
            return obj

        monkeypatch.setattr(spiral, "_latebound", real_identity)
        doc = _FakeDoc()
        ok, _ = create_spiral(doc, {"pitch_mm": 5}, {"sketch": "SpiralBase"})
        assert ok is True
        # _latebound(doc.Extension) for the select + _latebound(doc) for the insert
        assert doc.Extension in calls
        assert doc in calls


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestFailureModes:
    def test_select_failure_short_circuits(self):
        doc = _FakeDoc(select_ok=False)
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 5, "revolutions": 4},
            {"sketch": "SpiralBase"},
        )
        assert ok is False
        assert "select" in err.lower()
        assert doc.insert_calls == []

    def test_insert_raises_returns_false(self):
        doc = _FakeDoc(insert_raises=True)
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 5, "revolutions": 4},
            {"sketch": "SpiralBase"},
        )
        assert ok is False
        assert "InsertHelix" in err

    def test_insert_no_effect_is_ghost(self):
        """InsertHelix called, no exception, but no spiral node materialized —
        the db=3 + ConstantPitch=True silent no-op class."""
        doc = _FakeDoc(insert_effect=False)
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 5, "revolutions": 4},
            {"sketch": "SpiralBase"},
        )
        assert ok is False
        assert "no spiral node materialized" in err


# ---------------------------------------------------------------------------
# Validation (fail-closed)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_spiral(_FakeDoc(), "nope", {"sketch": "SpiralBase"})
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict(self):
        ok, err = create_spiral(_FakeDoc(), {"pitch_mm": 5}, "nope")
        assert ok is False and "target must be a dict" in err

    def test_missing_sketch(self):
        ok, err = create_spiral(_FakeDoc(), {"pitch_mm": 5}, {})
        assert ok is False and "sketch" in err

    def test_empty_sketch(self):
        ok, err = create_spiral(_FakeDoc(), {"pitch_mm": 5}, {"sketch": ""})
        assert ok is False and "sketch" in err

    def test_invalid_pitch(self):
        ok, err = create_spiral(
            _FakeDoc(),
            {"pitch_mm": "abc"},
            {"sketch": "SpiralBase"},
        )
        assert ok is False and "invalid" in err

    def test_nonpositive_pitch(self):
        ok, err = create_spiral(
            _FakeDoc(),
            {"pitch_mm": 0},
            {"sketch": "SpiralBase"},
        )
        assert ok is False and "pitch_mm" in err

    def test_nonpositive_revolutions(self):
        ok, err = create_spiral(
            _FakeDoc(),
            {"pitch_mm": 5, "revolutions": -1},
            {"sketch": "SpiralBase"},
        )
        assert ok is False and "revolutions" in err

    def test_never_raises_on_none_inputs(self):
        for _ in range(5):
            ok, err = create_spiral(None, None, None)  # type: ignore[arg-type]
            assert ok is False


# ---------------------------------------------------------------------------
# Registration gate + kind disjointness
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_spike_status_is_green(self):
        assert spiral.SPIKE_STATUS == "GREEN"

    def test_spiral_in_registry_when_green(self):
        assert HANDLER_REGISTRY.get("spiral") is create_spiral

    def test_spiral_distinct_from_helix(self):
        """Spiral and helix are separate kinds sharing the InsertHelix call."""
        assert HANDLER_REGISTRY.get("spiral") is not HANDLER_REGISTRY.get("helix")


# ---------------------------------------------------------------------------
# CURVE geometric gate (W42 ghost trap) — node presence alone is NOT success
# ---------------------------------------------------------------------------


class TestCurveGate:
    def test_node_without_arc_length_is_rejected(self, monkeypatch):
        monkeypatch.setattr(spiral, "_curve_length_mm", lambda node: None)
        doc = _FakeDoc()
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 5, "revolutions": 4},
            {"sketch": "SpiralBase"},
        )
        assert ok is False
        assert "arc length" in err

    def test_node_with_arc_length_passes(self, monkeypatch):
        monkeypatch.setattr(spiral, "_curve_length_mm", lambda node: 90.0)
        doc = _FakeDoc()
        ok, err = create_spiral(
            doc,
            {"pitch_mm": 5, "revolutions": 4},
            {"sketch": "SpiralBase"},
        )
        assert ok is True, err
