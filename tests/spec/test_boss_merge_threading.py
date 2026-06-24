"""W54 merge-on-create: guard the `merge` flag's threading to FeatureExtrusion2 arg 18.

The modeling-time boolean UNION is the invariant-clean stand-in for the walled
post-hoc ``combine`` (see docs/decisions.md): a boss with ``merge: true``
(default) fuses into the solid body it overlaps; ``merge: false`` keeps it as a
separate body. SOLIDWORKS expresses that on ``FeatureExtrusion2`` argument 18
(``Merge``). This test pins the wiring offline -- the live body-count proof is
spikes/_probe_merge_effect.py (merge=True -> 1 body, merge=False -> 2 bodies).

Arg 18 is index 17 (0-based) in the 23-arg tuple.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import builder

MERGE_ARG_INDEX = 17  # arg 18 (1-based) == Merge


class _RecordingFeatureManager:
    def __init__(self) -> None:
        self.last_args: tuple | None = None

    def FeatureExtrusion2(self, *args):  # noqa: N802 (COM name)
        self.last_args = args

        class _Feat:  # accepts `.Name = ...`
            pass

        return _Feat()


class _FakeDoc:
    def __init__(self) -> None:
        self.FeatureManager = _RecordingFeatureManager()


def _extrude(merge):
    """Drive _call_feature_extrusion through whatever `merge` resolves to and
    return the Merge argument actually handed to FeatureExtrusion2."""
    ctx = builder.BuildContext(sw=None, doc=_FakeDoc())
    kwargs = dict(end_cond=builder.SW_END_COND_BLIND, depth_m=0.05, flip=False)
    if merge is not None:
        kwargs["merge"] = merge
    builder._call_feature_extrusion(ctx, **kwargs)
    return ctx.doc.FeatureManager.last_args[MERGE_ARG_INDEX]


def test_merge_true_sets_arg18_true():
    assert _extrude(True) is True


def test_merge_false_sets_arg18_false():
    assert _extrude(False) is False


def test_merge_defaults_to_true():
    # Omitting merge must default to UNION -- the LLM declares separation
    # explicitly, never accidentally.
    assert _extrude(None) is True


class _Stop(Exception):
    pass


def test_boss_extrude_blind_reads_feat_merge(monkeypatch):
    """The feature builder must read feat['merge'] and forward it as the
    `merge` kwarg. Capture it at the _call_feature_extrusion boundary and
    short-circuit the downstream face/BuiltFeature machinery (out of scope)."""
    captured = {}

    def _spy(ctx, *, end_cond, depth_m, flip, merge=True):
        captured["merge"] = merge
        raise _Stop  # stop before the irrelevant downstream build steps

    monkeypatch.setattr(builder, "_call_feature_extrusion", _spy)

    ctx = builder.BuildContext(sw=None, doc=_FakeDoc())

    class _Sketch:
        parent_plane_normal = (0.0, 0.0, 1.0)

    ctx.features_by_name["SK"] = _Sketch()
    ctx.doc.ClearSelection2 = lambda *a: None
    ctx.doc.SelectByID = lambda *a: True

    feat = {
        "type": "boss_extrude_blind",
        "name": "Block",
        "sketch": "SK",
        "depth": 50.0,
        "merge": False,
    }
    with pytest.raises(_Stop):
        builder._build_boss_extrude_blind(ctx, feat)
    assert captured["merge"] is False
