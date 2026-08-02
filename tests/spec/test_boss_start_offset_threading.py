"""Guard the start_offset / flip_start_offset threading to FeatureExtrusion2
args 21-23, plus the extrude_origin shift the downstream face-selects depend on.

``start_offset`` lets a blind boss begin at a distance from its sketch plane
instead of on it (SOLIDWORKS start condition ``swStartOffset``). This unblocks
parts whose geometry sits offset from all three standard planes -- e.g.
SM-HW-S1b-001 ConveyorFrame: the side plate at part-Y=+40, feet at part-Z=-75,
cross-braces at part-Z=-56 (see the ConveyorFrame bridge-capability-gap report).

Opt-in semantics: OMITTING ``start_offset`` keeps the historical single-direction
tuple byte-for-byte (T0=swStartSketchPlane, StartOffset=0, FlipStartOffset=False),
so every existing spec is unaffected. Providing it (even 0.0) selects swStartOffset.

23-arg FeatureExtrusion2 tuple (1-based -> 0-based):
  arg 21 T0              -> index 20
  arg 22 StartOffset     -> index 21
  arg 23 FlipStartOffset -> index 22
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import builder
from ai_sw_bridge.spec.handlers import extrude as extrude_handlers
from ai_sw_bridge.sw_types import SW_START_OFFSET, SW_START_SKETCH_PLANE

T0_INDEX = 20
START_OFFSET_INDEX = 21
FLIP_START_OFFSET_INDEX = 22


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


def _extrude(**extra):
    """Drive _call_feature_extrusion and return the full FeatureExtrusion2 tuple."""
    ctx = builder.BuildContext(sw=None, doc=_FakeDoc())
    kwargs = dict(end_cond=builder.SW_END_COND_BLIND, depth_m=0.05, flip=False)
    kwargs.update(extra)
    builder._call_feature_extrusion(ctx, **kwargs)
    return ctx.doc.FeatureManager.last_args


def test_omitting_start_offset_keeps_sketch_plane_start():
    # The zero-drift guard: existing specs never set start_offset, so they must
    # produce the exact pre-feature tuple.
    args = _extrude()
    assert args[T0_INDEX] == SW_START_SKETCH_PLANE
    assert args[START_OFFSET_INDEX] == 0.0
    assert args[FLIP_START_OFFSET_INDEX] is False


def test_start_offset_selects_swStartOffset_and_distance():
    args = _extrude(start_offset_m=0.040)
    assert args[T0_INDEX] == SW_START_OFFSET
    assert args[START_OFFSET_INDEX] == pytest.approx(0.040)
    assert args[FLIP_START_OFFSET_INDEX] is False


def test_flip_start_offset_threads():
    args = _extrude(start_offset_m=0.075, flip_start_offset=True)
    assert args[T0_INDEX] == SW_START_OFFSET
    assert args[START_OFFSET_INDEX] == pytest.approx(0.075)
    assert args[FLIP_START_OFFSET_INDEX] is True


def test_explicit_zero_start_offset_is_still_an_offset_start():
    # Providing 0.0 is an explicit (if degenerate) offset start; only OMITTING
    # the field keeps swStartSketchPlane. Documents the opt-in boundary.
    args = _extrude(start_offset_m=0.0)
    assert args[T0_INDEX] == SW_START_OFFSET
    assert args[START_OFFSET_INDEX] == 0.0


class _Stop(Exception):
    pass


def test_build_boss_extrude_blind_reads_start_offset(monkeypatch):
    """The feature builder must convert feat['start_offset'] (mm) to meters and
    forward it plus feat['flip_start_offset'] to _call_feature_extrusion."""
    captured = {}

    def _spy(
        ctx,
        *,
        end_cond,
        depth_m,
        flip,
        merge=True,
        start_offset_m=None,
        flip_start_offset=False,
    ):
        captured["start_offset_m"] = start_offset_m
        captured["flip_start_offset"] = flip_start_offset
        raise _Stop  # stop before the downstream face/BuiltFeature machinery

    monkeypatch.setattr(extrude_handlers, "_call_feature_extrusion", _spy)

    ctx = builder.BuildContext(sw=None, doc=_FakeDoc())

    class _Sketch:
        parent_plane_normal = (0.0, 1.0, 0.0)

    ctx.features_by_name["SK"] = _Sketch()
    ctx.doc.ClearSelection2 = lambda *a: None
    ctx.doc.SelectByID = lambda *a: True

    feat = {
        "type": "boss_extrude_blind",
        "name": "Plate",
        "sketch": "SK",
        "depth": 5.0,
        "start_offset": 40.0,
        "flip_start_offset": True,
    }
    with pytest.raises(_Stop):
        builder._build_boss_extrude_blind(ctx, feat)
    assert captured["start_offset_m"] == pytest.approx(0.040)
    assert captured["flip_start_offset"] is True


def test_omitting_start_offset_forwards_none(monkeypatch):
    """A spec without start_offset must forward None (not 0.0) so the arg tuple
    stays on swStartSketchPlane -- the zero-drift contract at the builder layer."""
    captured = {}

    def _spy(
        ctx,
        *,
        end_cond,
        depth_m,
        flip,
        merge=True,
        start_offset_m=None,
        flip_start_offset=False,
    ):
        captured["start_offset_m"] = start_offset_m
        raise _Stop

    monkeypatch.setattr(extrude_handlers, "_call_feature_extrusion", _spy)
    ctx = builder.BuildContext(sw=None, doc=_FakeDoc())

    class _Sketch:
        parent_plane_normal = (0.0, 0.0, 1.0)

    ctx.features_by_name["SK"] = _Sketch()
    ctx.doc.ClearSelection2 = lambda *a: None
    ctx.doc.SelectByID = lambda *a: True

    feat = {"type": "boss_extrude_blind", "name": "B", "sketch": "SK", "depth": 5.0}
    with pytest.raises(_Stop):
        builder._build_boss_extrude_blind(ctx, feat)
    assert captured["start_offset_m"] is None


def test_boss_built_feature_shifts_origin_along_axis():
    """extrude_origin must move by start_offset along the sketch-plane normal so
    _face_frame locates the offset part's faces. Top-plane sketch (+Y normal),
    +40 mm offset, no flip -> origin's part-Y becomes +0.040."""

    class _Sketch:
        parent_plane_normal = (0.0, 1.0, 0.0)
        parent_face_origin = None
        sketch_center_part = (-0.1575, -0.0405, 0.0)
        sketch_extent_uv = (0.175, 0.0345)

    bf = extrude_handlers._boss_built_feature(
        {"name": "Plate", "type": "boss_extrude_blind"},
        _Sketch(),
        "SK",
        object(),  # sw_object stand-in
        0.005,
        False,
        start_offset_m=0.040,
        flip_start_offset=False,
    )
    ox, oy, oz = bf.extrude_origin
    assert oy == pytest.approx(0.040)  # shifted +Y by the offset
    assert ox == pytest.approx(-0.1575)  # in-plane components untouched
    assert oz == pytest.approx(-0.0405)


def test_boss_built_feature_no_offset_is_unchanged():
    class _Sketch:
        parent_plane_normal = (0.0, 0.0, 1.0)
        parent_face_origin = None
        sketch_center_part = (0.01, 0.02, 0.0)
        sketch_extent_uv = (0.05, 0.05)

    bf = extrude_handlers._boss_built_feature(
        {"name": "B", "type": "boss_extrude_blind"},
        _Sketch(),
        "SK",
        object(),
        0.05,
        False,
    )
    assert bf.extrude_origin == pytest.approx((0.01, 0.02, 0.0))
