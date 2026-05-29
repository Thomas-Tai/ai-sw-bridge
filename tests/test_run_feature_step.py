"""Direct unit tests for builder.run_feature_step (FR-X-06).

Before X1 the per-feature build body lived inline in build()'s loop and was
only exercisable against a live SOLIDWORKS seat. Extracting run_feature_step
makes each per-feature path directly testable with a minimal fake handler +
doc — no seat, no mock-adapter wiring needed. These cover the success path
and the error paths X1 calls out: handler raises, mass-delta _expect miss,
and the L4 checkpoint pending/committed/failed transitions. (Stale-handle
reconnect is covered by tests/com/test_reconnect.py around with_reconnect.)
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import builder
from ai_sw_bridge.spec._build_context import BuildContext, BuiltFeature

# NB: run_feature_step / StepOptions / StepResult are referenced through
# the ``builder`` module namespace (``builder.run_feature_step`` etc.),
# never captured as module-level ``from``-imports. tests/brep/
# test_builder_integration.py calls importlib.reload(builder) mid-suite,
# which rebinds these classes to fresh objects; a captured ``from``-import
# would go stale and break isinstance checks against results built by the
# (reloaded) function. Reading through the module gets the live object.

FAKE_TYPE = "__test_fake__"  # not in FEATURE_REGISTRY -> no parametric bindings


class _FakeMassProp:
    def __init__(self, volume_m3: float) -> None:
        self.Volume = volume_m3  # SW reports m³


class _FakeExt:
    def __init__(self, volume_m3: float) -> None:
        self._v = volume_m3

    @property
    def CreateMassProperty(self):  # zero-arg COM method: attribute access invokes
        return _FakeMassProp(self._v)


class _FakeDoc:
    def __init__(self, volume_m3: float = 1e-6) -> None:
        self.Extension = _FakeExt(volume_m3)
        self.rebuilds = 0

    @property
    def EditRebuild3(self):  # attribute-access idiom, mirrors the real call site
        self.rebuilds += 1
        return True


class _FakeStore:
    """Records the checkpoint transitions run_feature_step drives."""

    def __init__(self) -> None:
        self.failed: list[int] = []

    def mark_failed(self, row_id: int) -> None:
        self.failed.append(row_id)


def _opts(**overrides) -> "builder.StepOptions":
    base = dict(
        spec={"name": "t", "features": []},
        mode="no_dim",
        no_dim=True,
        deferred_dim=False,
        verify_mass=False,
        reconnect=False,
        brep_enabled=False,
        brep_manifest=None,
        cp_store=None,
        cp_locals_dict=None,
    )
    base.update(overrides)
    return builder.StepOptions(**base)


def _ctx(doc=None) -> BuildContext:
    return BuildContext(sw=object(), doc=doc or _FakeDoc())


@pytest.fixture
def fake_handler(monkeypatch):
    """Register a handler that returns a BuiltFeature named after the spec."""

    def handler(ctx, feat):
        return BuiltFeature(name=feat["name"], type=feat["type"])

    monkeypatch.setitem(builder.HANDLERS, FAKE_TYPE, handler)


def test_success_returns_stepresult_and_records_feature(fake_handler):
    ctx = _ctx()
    built: list[str] = []
    cp_built: list[dict] = []
    res = builder.run_feature_step(
        ctx,
        {"name": "F1", "type": FAKE_TYPE},
        opts=_opts(),
        feature_index=0,
        prev_volume_mm3=0.0,
        deferred_watermark=0,
        built=built,
        cp_built=cp_built,
    )
    assert isinstance(res, builder.StepResult)
    assert res.bf.name == "F1"
    assert res.feature_metric["name"] == "F1"
    assert res.feature_metric["type"] == FAKE_TYPE
    assert "build_time_s" in res.feature_metric
    assert res.bindings == []
    assert res.mass_entry is None
    # ctx + built + cp_built mutated in place exactly as the inline loop did.
    assert ctx.features_by_name["F1"].name == "F1"
    assert built == ["F1"]
    assert cp_built == [{"name": "F1", "type": FAKE_TYPE}]


def test_verify_mass_records_volume_delta(fake_handler):
    doc = _FakeDoc(volume_m3=2e-6)  # 2000 mm³
    res = builder.run_feature_step(
        _ctx(doc),
        {"name": "F1", "type": FAKE_TYPE},
        opts=_opts(verify_mass=True),
        feature_index=0,
        prev_volume_mm3=0.0,
        deferred_watermark=0,
        built=[],
        cp_built=[],
    )
    assert res.mass_entry is not None
    assert res.mass_entry["feature"] == "F1"
    assert res.mass_entry["actual_mm3"] == pytest.approx(2000.0)
    # running volume is threaded forward to the next feature
    assert res.prev_volume_mm3 == pytest.approx(2000.0)


def test_mass_expect_miss_fails_fast(fake_handler):
    doc = _FakeDoc(volume_m3=2e-6)  # 2000 mm³ actual vs 500 expected
    feat = {
        "name": "F1",
        "type": FAKE_TYPE,
        "_expect": {"mass_delta_mm3": 500.0, "tolerance_mm3": 1.0},
    }
    built: list[str] = []
    with pytest.raises(RuntimeError, match="mass verification failed"):
        builder.run_feature_step(
            _ctx(doc),
            feat,
            opts=_opts(verify_mass=True),
            feature_index=0,
            prev_volume_mm3=0.0,
            deferred_watermark=0,
            built=built,
            cp_built=[],
        )
    # The name was recorded right after the handler, so a later mass-verify
    # failure still leaves the feature in build()'s features_built list --
    # matching the pre-extraction loop (the failed BuildResult reports it).
    assert built == ["F1"]


def test_handler_failure_marks_checkpoint_row_failed(monkeypatch):
    import ai_sw_bridge.checkpoint.snapshot as snap

    monkeypatch.setattr(snap, "write_pre_feature", lambda *a, **k: 42)

    def boom(ctx, feat):
        raise ValueError("handler boom")

    monkeypatch.setitem(builder.HANDLERS, FAKE_TYPE, boom)
    store = _FakeStore()
    with pytest.raises(Exception):
        builder.run_feature_step(
            _ctx(),
            {"name": "F1", "type": FAKE_TYPE},
            opts=_opts(cp_store=store),
            feature_index=0,
            prev_volume_mm3=0.0,
            deferred_watermark=0,
            built=[],
            cp_built=[],
        )
    # the in-flight pending row is marked failed before the re-raise
    assert store.failed == [42]


def test_success_commits_checkpoint_row(monkeypatch, fake_handler):
    import ai_sw_bridge.checkpoint.snapshot as snap

    committed: list[tuple] = []
    monkeypatch.setattr(snap, "write_pre_feature", lambda *a, **k: 7)
    monkeypatch.setattr(
        snap,
        "commit_post_feature",
        lambda store, row, already_built: committed.append((row, list(already_built))),
    )
    store = _FakeStore()
    res = builder.run_feature_step(
        _ctx(),
        {"name": "F1", "type": FAKE_TYPE},
        opts=_opts(cp_store=store),
        feature_index=0,
        prev_volume_mm3=0.0,
        deferred_watermark=0,
        built=[],
        cp_built=[],
    )
    assert res.bf.name == "F1"
    assert committed == [(7, [{"name": "F1", "type": FAKE_TYPE}])]
    assert store.failed == []
