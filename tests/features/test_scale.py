"""W71 offline tests — ``scale`` handler + closed-form volume-ratio gate.

``scale`` uniformly scales the part's solid body about its centroid via
``IFeatureManager.InsertScale(Type, Uniform, X, Y, Z) -> Feature`` — the
boundary-law MATERIALIZE column (a pure matrix transform; W71 probe:
1.5× → Δvol ×3.375 = 1.5³ exact).

The VOLUME_TRANSFORM gate is the crux: success requires the volume to move
by the COMMANDED ratio ``f**3``, not merely ``|ΔVol| > eps`` — so a no-op
(ratio 1.0) AND a wrong-magnitude scale (ratio 2.0 for a 1.5× command) are
both rejected.  The real ``verify.gate_volume_transform`` runs against fake
volumes; only the volume reader + body accessor + typed-FM seams are patched.

COM seams are patched on the lane module itself (``features.scale``) per the
registry lane protocol — never on ``mutate``.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import scale as sc
from ai_sw_bridge.features import verify
from ai_sw_bridge.features.scale import create_scale


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------

class _FakeBody:
    """Fake IBody2 — whole-body select is the body's OWN native Select."""

    def __init__(self, name: str = "Body1", select_ok: bool = True) -> None:
        self.Name = name
        self.select_ok = select_ok
        self.selected = False

    def Select(self, append: bool, mark: int) -> bool:
        self.selected = True
        return self.select_ok


class _FakeFM:
    """Fake FeatureManager recording InsertScale calls."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def InsertScale(self, t, uniform, x, y, z):
        self.calls.append((t, uniform, x, y, z))
        return object()


class _FakeDoc:
    def __init__(self) -> None:
        self.FeatureManager = _FakeFM()
        self.cleared = 0
        self.rebuilt = 0

    def ClearSelection2(self, flag: bool) -> None:
        self.cleared += 1

    def ForceRebuild3(self, flag: bool) -> None:
        self.rebuilt += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feat(**kw) -> dict:
    base = {"scale_factor": 1.5}
    base.update(kw)
    return base


def _wire(monkeypatch, *, vols=(1000.0, 3375.0), bodies=None) -> None:
    """Patch the typed-FM, body-accessor, and volume-reader seams.

    The REAL ``verify.gate_volume_transform`` is intentionally NOT patched —
    the tests exercise it against the fake before/after volumes.
    """
    monkeypatch.setattr(sc, "typed_qi", lambda obj, iface, module=None: obj)
    monkeypatch.setattr(sc, "resolve", lambda doc, name: getattr(doc, name))

    if bodies is None:
        bodies = [_FakeBody()]
    monkeypatch.setattr(verify, "bodies", lambda doc, bt, vis: list(bodies))

    seq = list(vols)
    state = {"n": 0}

    def fake_vol(doc, visible_only=False):
        v = seq[min(state["n"], len(seq) - 1)]
        state["n"] += 1
        return v

    monkeypatch.setattr(verify, "solid_volume_mm3", fake_vol)


# ---------------------------------------------------------------------------
# Registration gate — consistent with SPIKE_STATUS (survives the UNFIRED→GREEN
# flip without a second edit; W0 flips the sentinel after the seat proof).
# ---------------------------------------------------------------------------

class TestRegistrationGate:
    def test_spike_status_is_a_known_sentinel(self) -> None:
        assert sc.SPIKE_STATUS in {
            "GREEN", "UNFIRED", "UNRUN", "DEFERRED", "WALLED", "DORMANT",
        }

    def test_registration_matches_spike_status(self) -> None:
        if sc.SPIKE_STATUS == "GREEN":
            assert HANDLER_REGISTRY.get("scale") is create_scale
        else:
            assert "scale" not in HANDLER_REGISTRY

    def test_verify_class_is_volume_transform(self) -> None:
        assert sc.VERIFY_CLASS == verify.FeatureClass.VOLUME_TRANSFORM


# ---------------------------------------------------------------------------
# Validation — runs before any COM access
# ---------------------------------------------------------------------------

class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_scale(_FakeDoc(), "not-a-dict", {})
        assert ok is False and "dict" in err

    def test_target_not_dict(self):
        ok, err = create_scale(_FakeDoc(), _feat(), "not-a-dict")
        assert ok is False and "dict" in err

    def test_missing_scale_factor(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), {}, {})
        assert ok is False and "scale_factor" in err

    def test_non_numeric_scale_factor(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), _feat(scale_factor="big"), {})
        assert ok is False and "scale_factor" in err

    def test_bool_scale_factor_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), _feat(scale_factor=True), {})
        assert ok is False and "scale_factor" in err

    def test_nonpositive_scale_factor(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), _feat(scale_factor=0.0), {})
        assert ok is False and "positive" in err

    def test_non_uniform_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), _feat(uniform=False), {})
        assert ok is False and "non-uniform" in err.lower()

    def test_bad_origin_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_scale(_FakeDoc(), _feat(origin="middle"), {})
        assert ok is False and "origin" in err

    def test_no_solid_body(self, monkeypatch):
        _wire(monkeypatch, vols=(0.0, 0.0))
        ok, err = create_scale(_FakeDoc(), _feat(), {})
        assert ok is False and "no solid body" in err


# ---------------------------------------------------------------------------
# Green path — ratio matches the commanded f**3
# ---------------------------------------------------------------------------

class TestGreen:
    def test_uniform_1p5_green(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 3375.0))
        doc = _FakeDoc()
        ok, note = create_scale(doc, _feat(scale_factor=1.5), {})
        assert ok is True
        assert "scale created" in note
        assert doc.rebuilt >= 1
        assert doc.cleared >= 1

    def test_insertscale_args_pinned(self, monkeypatch):
        """InsertScale receives (type, Uniform=True, f, f, f) — centroid=0."""
        _wire(monkeypatch, vols=(1000.0, 3375.0))
        doc = _FakeDoc()
        ok, _ = create_scale(doc, _feat(scale_factor=1.5), {})
        assert ok is True
        assert doc.FeatureManager.calls[0] == (0, True, 1.5, 1.5, 1.5)

    def test_origin_origin_maps_to_1(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 3375.0))
        doc = _FakeDoc()
        ok, _ = create_scale(doc, _feat(scale_factor=1.5, origin="origin"), {})
        assert ok is True
        assert doc.FeatureManager.calls[0][0] == 1

    def test_origin_coordsys_maps_to_2(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 3375.0))
        doc = _FakeDoc()
        ok, _ = create_scale(
            doc, _feat(scale_factor=1.5, origin="coordinate_system"), {},
        )
        assert ok is True
        assert doc.FeatureManager.calls[0][0] == 2

    def test_factor_two_green(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 8000.0))
        doc = _FakeDoc()
        ok, _ = create_scale(doc, _feat(scale_factor=2.0), {})
        assert ok is True  # ratio 8.0 == 2**3

    def test_target_body_selected(self, monkeypatch):
        body = _FakeBody("Body1")
        _wire(monkeypatch, vols=(1000.0, 3375.0), bodies=[body])
        ok, _ = create_scale(_FakeDoc(), _feat(), {})
        assert ok is True
        assert body.selected is True

    def test_select_failure_not_fatal(self, monkeypatch):
        """A failed body select must NOT false-reject a working scale (the W71
        probe materialized with no pre-selection)."""
        body = _FakeBody("Body1", select_ok=False)
        _wire(monkeypatch, vols=(1000.0, 3375.0), bodies=[body])
        ok, _ = create_scale(_FakeDoc(), _feat(), {})
        assert ok is True


# ---------------------------------------------------------------------------
# Ghost / wrong-magnitude rejection — the anti-ghost crux
# ---------------------------------------------------------------------------

class TestGhostRejection:
    def test_noop_ratio_one_rejected(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 1000.0))
        ok, err = create_scale(_FakeDoc(), _feat(scale_factor=1.5), {})
        assert ok is False
        assert "did not transform" in err

    def test_wrong_magnitude_rejected(self, monkeypatch):
        """Volume MOVED but not by f**3 — rejected (ratio 2.0 ≠ 1.5³)."""
        _wire(monkeypatch, vols=(1000.0, 2000.0))
        ok, err = create_scale(_FakeDoc(), _feat(scale_factor=1.5), {})
        assert ok is False
        assert "ratio" in err

    def test_insertscale_raises(self, monkeypatch):
        _wire(monkeypatch, vols=(1000.0, 3375.0))

        class _RaisingFM(_FakeFM):
            def InsertScale(self, *a):
                raise RuntimeError("COM boom")

        doc = _FakeDoc()
        doc.FeatureManager = _RaisingFM()
        ok, err = create_scale(doc, _feat(), {})
        assert ok is False and "InsertScale raised" in err


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_none_inputs(self):
        for _ in range(5):
            ok, err = create_scale(None, None, None)
            assert ok is False

    def test_kind_disjoint_from_builtins(self):
        from ai_sw_bridge.mutate import _SUPPORTED_FEATURE_TYPES
        assert "scale" not in _SUPPORTED_FEATURE_TYPES
