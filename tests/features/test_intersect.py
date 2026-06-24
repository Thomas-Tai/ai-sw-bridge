"""Offline tests — ``intersect`` handler + the BOOLEAN_INTERSECT gate.

``intersect`` is the boundary-law refinement: the Intersect feature is TWO-PHASE
(``IFeatureManager.PreIntersect2`` RETURNS the mutual region list to the caller,
then ``PostIntersect`` commits a 'Sculpt' feature).  The explicit region hand-back
is the materialize-class signature — it ships OOP where single-call combine/split
wall ``ret=None`` (probe 2026-06-24: 2 overlapping boxes → 3 regions, solid bodies
2→3).

The BOOLEAN_INTERSECT gate is the crux: success requires a real Sculpt node AND a
topology change (body-count delta OR volume delta) — a non-None Feature alone is
the W21/W42 ghost trap.  The real ``verify.gate_boolean_intersect`` runs against
fake counts/volumes; only the body/volume/node-count readers and the typed-FM /
IBody2 seams are patched, on the lane module itself (never on ``mutate``).
"""

from __future__ import annotations

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import intersect as ix
from ai_sw_bridge.features import verify
from ai_sw_bridge.features.intersect import create_intersect


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


class _FakeRegion:
    def __init__(self, idx: int) -> None:
        self.idx = idx


class _FakeFM:
    """Fake FeatureManager recording the two-phase Pre/PostIntersect calls."""

    def __init__(self, n_regions: int = 3) -> None:
        self.regions = tuple(_FakeRegion(i) for i in range(n_regions))
        self.pre_calls: list[tuple] = []
        self.post_calls: list[tuple] = []

    def PreIntersect2(self, cap_planar, region_type):
        self.pre_calls.append((cap_planar, region_type))
        return self.regions

    def PostIntersect(self, exclude, merge, consume):
        self.post_calls.append((exclude, merge, consume))
        return object()


class _FakeDoc:
    def __init__(self, fm: _FakeFM | None = None) -> None:
        self.FeatureManager = fm or _FakeFM()
        self.cleared = 0
        self.rebuilt = 0

    def ClearSelection2(self, flag: bool) -> None:
        self.cleared += 1

    def ForceRebuild3(self, flag: bool) -> None:
        self.rebuilt += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wire(
    monkeypatch,
    *,
    counts=(2, 3),
    vols=(48000.0, 40000.0),
    sculpts=(0, 1),
    bodies=None,
) -> None:
    """Patch the typed-FM / IBody2 seams and the body/volume/node readers.

    The REAL ``verify.gate_boolean_intersect`` is intentionally NOT patched —
    the tests exercise it against the fake before/after counts and volumes.
    """
    monkeypatch.setattr(ix, "typed_qi", lambda obj, iface, module=None: obj)
    monkeypatch.setattr(ix, "typed", lambda obj, iface, module=None: obj)
    monkeypatch.setattr(ix, "resolve", lambda doc, name: getattr(doc, name))

    if bodies is None:
        bodies = [_FakeBody("Body1"), _FakeBody("Body2")]
    monkeypatch.setattr(verify, "bodies", lambda doc, bt, vis: list(bodies))

    monkeypatch.setattr(verify, "solid_body_count", _seq(list(counts)))
    monkeypatch.setattr(verify, "solid_volume_mm3", _seq(list(vols)))
    monkeypatch.setattr(verify, "count_nodes_by_type", _seq(list(sculpts)))


def _seq(values):
    """A reader that yields *values* in order, clamping to the last."""
    state = {"n": 0}

    def reader(*args, **kwargs):
        v = values[min(state["n"], len(values) - 1)]
        state["n"] += 1
        return v

    return reader


# ---------------------------------------------------------------------------
# Registration gate — consistent with SPIKE_STATUS (survives UNFIRED→GREEN flip)
# ---------------------------------------------------------------------------

class TestRegistrationGate:
    def test_spike_status_is_a_known_sentinel(self) -> None:
        assert ix.SPIKE_STATUS in {
            "GREEN", "UNFIRED", "UNRUN", "DEFERRED", "WALLED", "DORMANT",
        }

    def test_registration_matches_spike_status(self) -> None:
        if ix.SPIKE_STATUS == "GREEN":
            assert HANDLER_REGISTRY.get("intersect") is create_intersect
        else:
            assert "intersect" not in HANDLER_REGISTRY

    def test_verify_class_is_boolean_intersect(self) -> None:
        assert ix.VERIFY_CLASS == verify.FeatureClass.BOOLEAN_INTERSECT


# ---------------------------------------------------------------------------
# Validation — runs before any COM mutation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_feature_not_dict(self):
        ok, err = create_intersect(_FakeDoc(), "nope", {})
        assert ok is False and "dict" in err

    def test_target_not_dict(self):
        ok, err = create_intersect(_FakeDoc(), {}, "nope")
        assert ok is False and "dict" in err

    def test_exclude_regions_not_list(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_intersect(_FakeDoc(), {"exclude_regions": 3}, {})
        assert ok is False and "exclude_regions" in err

    def test_exclude_regions_non_int(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_intersect(_FakeDoc(), {"exclude_regions": ["a"]}, {})
        assert ok is False and "exclude_regions" in err

    def test_exclude_regions_bool_rejected(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_intersect(_FakeDoc(), {"exclude_regions": [True]}, {})
        assert ok is False and "exclude_regions" in err

    def test_too_few_bodies(self, monkeypatch):
        _wire(monkeypatch, counts=(1, 1))
        ok, err = create_intersect(_FakeDoc(), {}, {})
        assert ok is False and ">=2 solid bodies" in err

    def test_body_names_wrong_type(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_intersect(_FakeDoc(), {}, {"body_names": [1, 2]})
        assert ok is False and "body_names" in err

    def test_body_names_too_few(self, monkeypatch):
        _wire(monkeypatch)
        ok, err = create_intersect(_FakeDoc(), {}, {"body_names": ["Body1"]})
        assert ok is False and ">=2" in err


# ---------------------------------------------------------------------------
# Green path — 2 bodies → 3 regions → Sculpt feature, topology changed
# ---------------------------------------------------------------------------

class TestGreen:
    def test_basic_green(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, note = create_intersect(doc, {}, {})
        assert ok is True
        assert "intersect created" in note
        assert doc.rebuilt >= 1

    def test_preintersect2_args_pinned(self, monkeypatch):
        """PreIntersect2(cap_planar=False, RegionType=Margins=0) by default."""
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_intersect(doc, {}, {})
        assert ok is True
        assert doc.FeatureManager.pre_calls[0] == (False, 0)

    def test_cap_planar_passed(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_intersect(doc, {"cap_planar": True}, {})
        assert ok is True
        assert doc.FeatureManager.pre_calls[0] == (True, 0)

    def test_merge_flag_passed(self, monkeypatch):
        _wire(monkeypatch, counts=(2, 1))  # merge collapses to 1 body
        doc = _FakeDoc()
        ok, _ = create_intersect(doc, {"merge": True}, {})
        assert ok is True
        excl, merge, consume = doc.FeatureManager.post_calls[0]
        assert merge is True
        assert consume is False  # held at the probe-proven value
        assert excl is None  # no exclusions → None (keep-all-regions form)

    def test_both_bodies_selected(self, monkeypatch):
        bodies = [_FakeBody("Body1"), _FakeBody("Body2")]
        _wire(monkeypatch, bodies=bodies)
        ok, _ = create_intersect(_FakeDoc(), {}, {})
        assert ok is True
        assert all(b.selected for b in bodies)

    def test_exclude_region_wiring(self, monkeypatch):
        """A valid exclusion index reaches PostIntersect via _exclusion_arg."""
        _wire(monkeypatch)
        sentinel = object()
        monkeypatch.setattr(ix, "_exclusion_arg", lambda regions, idx: sentinel)
        doc = _FakeDoc()
        ok, _ = create_intersect(doc, {"exclude_regions": [2]}, {})
        assert ok is True
        assert doc.FeatureManager.post_calls[0][0] is sentinel

    def test_body_names_selected(self, monkeypatch):
        bodies = [_FakeBody("Alpha"), _FakeBody("Beta"), _FakeBody("Gamma")]
        _wire(monkeypatch, counts=(3, 4), bodies=bodies)
        ok, _ = create_intersect(_FakeDoc(), {}, {"body_names": ["Alpha", "Gamma"]})
        assert ok is True
        assert bodies[0].selected and bodies[2].selected
        assert bodies[1].selected is False  # Beta not named


# ---------------------------------------------------------------------------
# Region handling — the two-phase contract's failure modes
# ---------------------------------------------------------------------------

class TestRegions:
    def test_no_regions_fails(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(_FakeFM(n_regions=0))
        ok, err = create_intersect(doc, {}, {})
        assert ok is False and "no regions" in err

    def test_exclude_index_out_of_range(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(_FakeFM(n_regions=3))
        ok, err = create_intersect(doc, {"exclude_regions": [5]}, {})
        assert ok is False and "out of range" in err

    def test_exclude_all_regions_fails(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(_FakeFM(n_regions=3))
        ok, err = create_intersect(doc, {"exclude_regions": [0, 1, 2]}, {})
        assert ok is False and "nothing would" in err


# ---------------------------------------------------------------------------
# Ghost rejection — the anti-ghost crux
# ---------------------------------------------------------------------------

class TestGhostRejection:
    def test_no_topology_change_rejected(self, monkeypatch):
        """Sculpt node appeared but bodies/volume unchanged → ghost."""
        _wire(monkeypatch, counts=(2, 2), vols=(48000.0, 48000.0), sculpts=(0, 1))
        ok, err = create_intersect(_FakeDoc(), {}, {})
        assert ok is False and "ghost" in err

    def test_no_sculpt_node_rejected(self, monkeypatch):
        """Topology changed but no Sculpt node materialized → not our feature."""
        _wire(monkeypatch, counts=(2, 3), vols=(48000.0, 40000.0), sculpts=(0, 0))
        ok, err = create_intersect(_FakeDoc(), {}, {})
        assert ok is False and "ghost" in err

    def test_volume_only_change_passes(self, monkeypatch):
        """Body count steady but volume moved (merge case) → still a real op."""
        _wire(monkeypatch, counts=(2, 2), vols=(48000.0, 40000.0), sculpts=(0, 1))
        ok, _ = create_intersect(_FakeDoc(), {}, {})
        assert ok is True

    def test_preintersect2_raises(self, monkeypatch):
        _wire(monkeypatch)

        class _RaisingFM(_FakeFM):
            def PreIntersect2(self, *a):
                raise RuntimeError("COM boom")

        ok, err = create_intersect(_FakeDoc(_RaisingFM()), {}, {})
        assert ok is False and "PreIntersect2 raised" in err

    def test_postintersect_raises(self, monkeypatch):
        _wire(monkeypatch)

        class _RaisingFM(_FakeFM):
            def PostIntersect(self, *a):
                raise RuntimeError("COM boom")

        ok, err = create_intersect(_FakeDoc(_RaisingFM()), {}, {})
        assert ok is False and "PostIntersect raised" in err

    def test_no_solid_bodies_select_fails(self, monkeypatch):
        _wire(monkeypatch, counts=(2, 3))
        # bodies() returns empty → _select_bodies reports no bodies
        monkeypatch.setattr(verify, "bodies", lambda doc, bt, vis: [])
        ok, err = create_intersect(_FakeDoc(), {}, {})
        assert ok is False and "no solid bodies" in err


# ---------------------------------------------------------------------------
# Never raises / disjoint from built-ins
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_none_inputs(self):
        for _ in range(5):
            ok, err = create_intersect(None, None, None)
            assert ok is False

    def test_kind_disjoint_from_builtins(self):
        from ai_sw_bridge.mutate import _SUPPORTED_FEATURE_TYPES
        assert "intersect" not in _SUPPORTED_FEATURE_TYPES
