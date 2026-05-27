"""Tests for the BuildError envelope (spec.md §3.2)."""

from __future__ import annotations

import json

import pytest

from ai_sw_bridge.errors.build_error import (
    BuildError,
    build_error_from_exception,
)


def _make_error(**overrides) -> BuildError:
    base = dict(
        feature="Extrude_Plate",
        json_path="features[3].depth",
        hresult="0x80004005",
        iface_method="IFeatureManager.FeatureExtrusion2",
        diagnosis="Extrusion returned None",
        next_action_hint="Check sketch profile",
        traceback=None,
        tier="B",
        hint_key="face_no_longer_exists",
    )
    base.update(overrides)
    return BuildError(**base)


def test_envelope_shape_matches_spec() -> None:
    err = _make_error()
    env = err.to_envelope()
    assert "error" in env
    payload = env["error"]
    # spec.md §3.2 required fields (additive: tier, hint_key, version)
    for key in (
        "feature",
        "json_path",
        "hresult",
        "iface_method",
        "diagnosis",
        "next_action_hint",
    ):
        assert key in payload, f"missing required field: {key}"
    assert payload["version"] == 1
    assert payload["tier"] == "B"
    assert payload["hint_key"] == "face_no_longer_exists"


def test_envelope_excludes_traceback() -> None:
    err = _make_error(traceback="File foo.py, line 42...")
    payload = err.to_envelope()["error"]
    assert "traceback" not in payload
    # traceback still accessible on the dataclass for human stderr
    assert err.traceback.startswith("File foo.py")


def test_envelope_json_serializable() -> None:
    err = _make_error()
    text = err.to_json()
    round_tripped = json.loads(text)
    assert round_tripped == err.to_envelope()
    # single-line (no newlines) for two-stream stdout contract
    assert "\n" not in text


def test_tier_validation_rejects_unknown_literal() -> None:
    with pytest.raises(ValueError, match="tier must be one of"):
        _make_error(tier="Z")


@pytest.mark.parametrize("tier", ["A", "B", "C", "unknown"])
def test_tier_accepts_valid_literals(tier: str) -> None:
    err = _make_error(tier=tier)
    assert err.tier == tier
    assert err.to_envelope()["error"]["tier"] == tier


def test_none_fields_default_explicitly() -> None:
    err = BuildError(
        feature="f",
        json_path="p",
        hresult="0x0",
        iface_method="m",
        diagnosis="d",
        next_action_hint="h",
    )
    assert err.traceback is None
    assert err.tier == "unknown"
    assert err.hint_key is None
    payload = err.to_envelope()["error"]
    assert payload["hint_key"] is None
    assert payload["tier"] == "unknown"


def test_frozen_dataclass_is_immutable() -> None:
    err = _make_error()
    with pytest.raises(AttributeError):
        err.feature = "changed"  # type: ignore[misc]


def test_build_error_is_exception_subclass() -> None:
    err = _make_error()
    assert isinstance(err, Exception)
    with pytest.raises(BuildError) as raised:
        raise err
    assert raised.value is err


def test_build_error_from_exception_captures_traceback() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        err = build_error_from_exception(
            e,
            feature="Cut1",
            json_path="features[0]",
            hresult="0x80010108",
            iface_method="IFeatureManager.FeatureCut4",
            diagnosis="cut failed",
            next_action_hint="inspect sketch",
            tier="B",
            hint_key="sketch_under_constrained",
        )
    assert "RuntimeError: boom" in err.traceback
    assert err.hint_key == "sketch_under_constrained"
    # envelope still serializes cleanly
    json.loads(err.to_json())


def test_format_traceback_uses_fallback_when_none() -> None:
    err = _make_error(traceback=None)
    assert err.format_traceback() == "BuildError: Extrusion returned None"


def test_format_traceback_returns_real_traceback_when_present() -> None:
    err = _make_error(traceback="Traceback (most recent call last):\n...")
    assert err.format_traceback().startswith("Traceback")
