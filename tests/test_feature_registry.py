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


def test_registry_ships_empty_until_w56():
    # W59 move_copy_body imports dormant (SPIKE_STATUS != "GREEN") so
    # nothing registers until the seat spike proves the arg shape.
    # When W0 flips SPIKE_STATUS to GREEN, this assertion flips to
    # assert "move_body"/"copy_body" present + callable.
    assert features.HANDLER_REGISTRY == {}


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


def test_apply_feature_builtin_kind_wins_over_registry(monkeypatch):
    # The built-in chain runs first; a (disallowed) collision must not
    # reroute a shipped kind through the registry.
    def hijack(doc, feature, target):  # pragma: no cover - must not run
        raise AssertionError("registry shadowed a built-in kind")

    monkeypatch.setitem(features.HANDLER_REGISTRY, "shell", hijack)
    monkeypatch.setattr(
        mutate, "_create_shell", lambda doc, feature, target: (True, "builtin")
    )
    ok, err = mutate._apply_feature("DOC", {"type": "shell"}, {})
    assert (ok, err) == (True, "builtin")


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
    res = mutate.sw_propose_feature_add(
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
    res = mutate.sw_propose_feature_add("C:/nope.sldprt", {"type": "bogus"}, {})
    assert res["ok"] is False
    assert "unsupported feature type 'bogus'" in res["error"]
    # Registry kinds are advertised alongside the built-ins.
    assert "fake_kind" in res["error"]
