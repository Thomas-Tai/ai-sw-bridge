"""W73 offline tests — ``structural_weldment`` handler + ADDITIVE_SOLID gate.

``structural_weldment`` sweeps a library profile along an explicit 3D-sketch
path via ``IFeatureManager.InsertStructuralWeldment5`` — the boundary-law
macro-feature corollary (the encapsulated end-trim/miter intersection solve
materializes out-of-process; W73 probe ΔVol +26739.822 mm³ / 2 bodies).

The crux this lane guards: ``swConnectedSegmentsOption`` is 1/2 — there is NO
``0`` (a 0 ghosts the WHOLE feature). The handler maps {simple_cut, coped_cut}
-> {1, 2} ONLY, so the ghost trap is unreachable. A missing profile fails
closed (else InsertStructuralWeldment5 ghosts silently).

COM seams are patched on the lane module itself (``features.structural_weldment``)
per the registry lane protocol — never on ``mutate``. The real
``verify.gate_additive_solid`` runs against fake before/after metrics.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import structural_weldment as swm
from ai_sw_bridge.features import verify
from ai_sw_bridge.features.structural_weldment import create_structural_weldment


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeGroup:
    def __init__(self) -> None:
        self.Segments = None
        self.ApplyCornerTreatment = None
        self.CornerTreatmentType = None
        self.MiterMergeCondition = None


class _FakeFM:
    def __init__(self, *, returns=object()) -> None:
        self.returns = returns
        self.group = _FakeGroup()
        self.weldment_calls: list[tuple] = []

    def CreateStructuralMemberGroup(self):
        return self.group

    def InsertStructuralWeldment5(self, path, conn, prot, groups, cfg):
        self.weldment_calls.append((path, conn, prot, groups, cfg))
        return self.returns


class _FakeSketch:
    def __init__(self, n_segs: int = 2) -> None:
        self._segs = tuple(object() for _ in range(n_segs))

    def GetSketchSegments(self):
        return self._segs


class _FakeFeature:
    def __init__(self, sketch) -> None:
        self._sketch = sketch

    def GetSpecificFeature2(self):
        return self._sketch


class _FakeDoc:
    def __init__(self, *, fm=None, sketch=None, has_feature=True) -> None:
        self.FeatureManager = fm or _FakeFM()
        self._sketch = sketch if sketch is not None else _FakeSketch()
        self._has_feature = has_feature
        self.cleared = 0
        self.rebuilt = 0

    def FeatureByName(self, name):
        return _FakeFeature(self._sketch) if self._has_feature else None

    def ClearSelection2(self, flag):
        self.cleared += 1

    def ForceRebuild3(self, flag):
        self.rebuilt += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFILE = r"C:\fake\square tube.sldlfp"


def _feat(**kw) -> dict:
    base = {
        "profile_path": _PROFILE,
        "configuration": "20 x 20 x 2",
        "sketch_name": "PATH",
    }
    base.update(kw)
    return base


def _wire(
    monkeypatch,
    *,
    metrics=((0, 0.0), (36, 26739.822)),
    bodies_after=2,
    profile_exists=True,
) -> None:
    """Patch the COM-marshalling, typed-FM, sketch-resolution, and verify seams.

    The REAL ``verify.gate_additive_solid`` is NOT patched — it runs against
    the fake before/after metrics.
    """
    # SAFEARRAY marshalling -> identity (keep COM off the test path)
    monkeypatch.setattr(swm, "_disp_array", lambda items: list(items))
    # typed FM / sketch resolution use the fakes directly
    monkeypatch.setattr(swm, "typed_qi", lambda obj, iface, module=None: obj)
    monkeypatch.setattr(swm, "resolve", lambda doc, name: getattr(doc, name))
    monkeypatch.setattr(swm.os.path, "isfile", lambda p: profile_exists)

    seq = list(metrics)
    state = {"n": 0}

    def fake_metrics(doc, visible_only=False):
        m = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return m

    monkeypatch.setattr(verify, "solid_metrics", fake_metrics)
    monkeypatch.setattr(verify, "solid_body_count", lambda doc, vis=False: bodies_after)


# ---------------------------------------------------------------------------
# Registration gate (survives the UNFIRED→GREEN flip without a second edit)
# ---------------------------------------------------------------------------


class TestRegistrationGate:
    def test_spike_status_is_a_known_sentinel(self):
        assert swm.SPIKE_STATUS in {
            "GREEN",
            "UNFIRED",
            "UNRUN",
            "DEFERRED",
            "WALLED",
            "DORMANT",
        }

    def test_registration_matches_spike_status(self):
        if swm.SPIKE_STATUS == "GREEN":
            assert (
                HANDLER_REGISTRY.get("structural_weldment")
                is create_structural_weldment
            )
        else:
            assert "structural_weldment" not in HANDLER_REGISTRY

    def test_verify_class_is_additive_solid(self):
        assert swm.VERIFY_CLASS == verify.FeatureClass.ADDITIVE_SOLID


# ---------------------------------------------------------------------------
# Validation — fail closed before / around COM access
# ---------------------------------------------------------------------------


class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_structural_weldment(_FakeDoc(), "x", {})
        assert ok is False and "dict" in err

    def test_target_not_dict(self):
        ok, err = create_structural_weldment(_FakeDoc(), _feat(), "x")
        assert ok is False and "dict" in err

    def test_missing_profile_path(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_structural_weldment(_FakeDoc(), _feat(profile_path=""), {})
        assert ok is False and "profile_path" in err

    def test_profile_not_on_disk_fails_closed(self, monkeypatch):
        _wire(monkeypatch, profile_exists=False)
        ok, err = create_structural_weldment(_FakeDoc(), _feat(), {})
        assert ok is False and "does not exist" in err

    def test_missing_configuration(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_structural_weldment(_FakeDoc(), _feat(configuration=""), {})
        assert ok is False and "configuration" in err

    def test_missing_sketch_name(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_structural_weldment(_FakeDoc(), _feat(sketch_name=""), {})
        assert ok is False and "sketch_name" in err

    def test_zero_ghost_trap_unreachable(self, monkeypatch):
        """connected_segments must map to {1,2}; '0'/'none' rejected at validation."""
        _wire(monkeypatch)
        ok, err = create_structural_weldment(
            _FakeDoc(), _feat(connected_segments="none"), {}
        )
        assert ok is False and "connected_segments" in err

    def test_bad_corner_treatment_type(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_structural_weldment(
            _FakeDoc(), _feat(corner_treatment_type="miter"), {}
        )
        assert ok is False and "corner_treatment_type" in err

    def test_unresolvable_sketch(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_structural_weldment(_FakeDoc(has_feature=False), _feat(), {})
        assert ok is False and "could not resolve" in err

    def test_sketch_no_segments(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(sketch=_FakeSketch(n_segs=0))
        ok, err = create_structural_weldment(doc, _feat(), {})
        assert ok is False and "no path segments" in err


# ---------------------------------------------------------------------------
# Green path — ΔFaces > 0 ∧ ΔVol > 0
# ---------------------------------------------------------------------------


class TestGreen:
    def test_simple_cut_green(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, note = create_structural_weldment(doc, _feat(), {})
        assert ok is True
        assert "structural_weldment created" in note
        assert doc.rebuilt >= 1 and doc.cleared >= 1

    def test_connected_segments_maps_to_enum(self, monkeypatch):
        """simple_cut -> 1, coped_cut -> 2 (never 0)."""
        _wire(monkeypatch)
        for kind, expected in (("simple_cut", 1), ("coped_cut", 2)):
            fm = _FakeFM()
            doc = _FakeDoc(fm=fm)
            create_structural_weldment(doc, _feat(connected_segments=kind), {})
            assert fm.weldment_calls, f"{kind}: no weldment call recorded"
            assert fm.weldment_calls[0][1] == expected

    def test_default_connected_segments_is_simple_cut(self, monkeypatch):
        _wire(monkeypatch)
        fm = _FakeFM()
        create_structural_weldment(_FakeDoc(fm=fm), _feat(), {})
        assert fm.weldment_calls[0][1] == 1  # never 0

    def test_segments_assigned_to_group(self, monkeypatch):
        _wire(monkeypatch)
        fm = _FakeFM()
        create_structural_weldment(_FakeDoc(fm=fm), _feat(), {})
        assert fm.group.Segments is not None
        assert len(fm.group.Segments) == 2

    def test_miter_merge_sets_group_flag(self, monkeypatch):
        _wire(monkeypatch, bodies_after=1)
        fm = _FakeFM()
        ok, note = create_structural_weldment(
            _FakeDoc(fm=fm), _feat(corner_treatment=True, miter_merge=True), {}
        )
        assert ok is True
        assert fm.group.MiterMergeCondition is True
        assert fm.group.ApplyCornerTreatment is True


# ---------------------------------------------------------------------------
# Ghost rejection — Feature returned but no geometry
# ---------------------------------------------------------------------------


class TestGhostRejection:
    def test_no_geometry_change_rejected(self, monkeypatch):
        """ret-is-Feature but ΔFaces/ΔVol 0 (the 0-enum / missing-config ghost)."""
        _wire(monkeypatch, metrics=((0, 0.0), (0, 0.0)), bodies_after=0)
        ok, err = create_structural_weldment(_FakeDoc(), _feat(), {})
        assert ok is False
        assert "did not materialize" in err

    def test_insertweldment_raises_fail_closed(self, monkeypatch):
        _wire(monkeypatch)

        class _BoomFM(_FakeFM):
            def InsertStructuralWeldment5(self, *a):
                raise RuntimeError("kernel boom")

        ok, err = create_structural_weldment(_FakeDoc(fm=_BoomFM()), _feat(), {})
        assert ok is False and "raised" in err
