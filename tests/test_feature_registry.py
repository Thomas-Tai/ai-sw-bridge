"""Offline tests for the features/ handler-registry seam (W56 prep).

The registry lets a new feature_add kind ship as its own module under
``ai_sw_bridge/features/`` plus one registry entry, instead of editing
``mutate.py`` — the single-file collision that forced W56 production
wiring to be sequenced one-lane-at-a-time. These tests pin the seam's
contract: dispatch, propose advertisement, fail-closed unknowns, and
key-disjointness from the built-in chain.
"""

from __future__ import annotations

from ai_sw_bridge import features, mutate


def test_registry_contains_wired_lanes():
    # W59 wired hem (generative, seat-proven); registry is non-empty.
    assert "hem" in features.HANDLER_REGISTRY


def test_walled_move_copy_body_not_advertised():
    # move_copy_body imports DORMANT and stays walled (W58/W59 — all OOP
    # routes silent no-op), so it must NOT advertise either kind: a wall
    # is never in the registry (combine/split precedent).
    assert "move_body" not in features.HANDLER_REGISTRY
    assert "copy_body" not in features.HANDLER_REGISTRY


def test_w59_dormant_module_registers_when_spike_green(monkeypatch):
    # Pin the dormant-gate: flipping SPIKE_STATUS to GREEN and re-calling
    # _register() must register both kinds. No exec/eval (Invariant #3/R1).
    from ai_sw_bridge.features import move_copy_body as mcb

    monkeypatch.setattr(mcb, "SPIKE_STATUS", "GREEN")
    mcb._register()
    try:
        assert "move_body" in features.HANDLER_REGISTRY
        assert "copy_body" in features.HANDLER_REGISTRY
        assert callable(features.HANDLER_REGISTRY["move_body"])
        assert callable(features.HANDLER_REGISTRY["copy_body"])
    finally:
        features.HANDLER_REGISTRY.pop("move_body", None)
        features.HANDLER_REGISTRY.pop("copy_body", None)


def test_registry_keys_disjoint_from_builtin_chain():
    # Built-in kinds win in _apply_feature, so a collision would shadow
    # the registry entry silently — keep the key sets disjoint.
    overlap = set(features.HANDLER_REGISTRY) & set(mutate._SUPPORTED_FEATURE_TYPES)
    assert not overlap


def test_apply_feature_dispatches_registry_kind(monkeypatch):
    seen = {}

    def fake_handler(doc, feature, target):
        seen["args"] = (doc, feature, target)
        return True, None

    monkeypatch.setitem(features.HANDLER_REGISTRY, "fake_kind", fake_handler)
    feature = {"type": "fake_kind", "depth_mm": 3.0}
    target = {"face_ref": "F1"}
    ok, err = mutate._apply_feature("DOC", feature, target)
    assert (ok, err) == (True, None)
    assert seen["args"] == ("DOC", feature, target)


def test_apply_feature_dispatches_purely_through_registry(monkeypatch):
    # Recipe-C cut #6: sweep/sweep_cut relocated to features/sweep.py; there are
    # no inline built-in branches left. _apply_feature is now a pure registry
    # dispatch — every kind, including sweep, resolves through HANDLER_REGISTRY.
    seen = {}

    def spy(doc, feature, target):
        seen["called"] = True
        return (True, "registry")

    monkeypatch.setitem(features.HANDLER_REGISTRY, "sweep", spy)
    ok, err = mutate._apply_feature("DOC", {"type": "sweep"}, {})
    assert (ok, err) == (True, "registry")
    assert seen.get("called") is True  # the registry handler ran (no builtin shadow)


def test_apply_feature_unknown_kind_still_fails_closed():
    ok, err = mutate._apply_feature(object(), {"type": "no_such_kind"}, {})
    assert ok is False
    assert "unsupported feature type" in err


def test_propose_accepts_registry_kind(monkeypatch, tmp_path):
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    monkeypatch.setitem(
        features.HANDLER_REGISTRY, "fake_kind", lambda d, f, t: (True, None)
    )
    doc = tmp_path / "part.sldprt"
    doc.write_text("stub")
    res = mutate._sw_propose_feature_add_impl(
        str(doc), {"type": "fake_kind"}, {"face_ref": "F1"}
    )
    assert res["error"] is None
    assert res["ok"] is True
    assert res["proposal_id"]


def test_propose_rejects_unknown_kind_and_lists_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    monkeypatch.setitem(
        features.HANDLER_REGISTRY, "fake_kind", lambda d, f, t: (True, None)
    )
    res = mutate._sw_propose_feature_add_impl("C:/nope.sldprt", {"type": "bogus"}, {})
    assert res["ok"] is False
    assert "unsupported feature type 'bogus'" in res["error"]
    # Registry kinds are advertised alongside the built-ins.
    assert "fake_kind" in res["error"]
