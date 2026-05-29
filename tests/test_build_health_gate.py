"""Unit tests for the X2 build success-gate (FR-X-02).

"Built" != "manufacturable": before X2, BuildResult.ok was True whenever the
feature loop didn't raise, so a part with post-rebuild errors / over-defined
sketches reported success. X2 adds a post-rebuild GetErrorCode sweep
(observe.collect_feature_health) plus a pure policy gate (builder._health_gate)
folded into BuildResult.ok + feature_health.

These cover the two factored pieces directly (no seat) and the BuildResult
wire-format contract. The full build() path is seat-gated
(tests/checkpoint/test_rollback_live.py); the sweep there is fail-soft.
"""

from __future__ import annotations

from ai_sw_bridge.observe import collect_feature_health
from ai_sw_bridge.spec import builder
from ai_sw_bridge.spec.builder import BuildResult


# --------------------------------------------------------------------------
# Fakes: resolve() is just getattr (sw_com.resolve), so a feature only needs
# attributes. Zero-arg COM "methods" (GetErrorCode, GetNextFeature, ...) are
# auto-invoked on attribute access, i.e. plain attributes here.
# --------------------------------------------------------------------------


class _FakeFeat:
    def __init__(
        self,
        name: str,
        code: int = 0,
        *,
        type_name: str = "Extrusion",
        message: str = "",
        suppressed: bool = False,
    ) -> None:
        self.Name = name
        self.GetErrorCode = code
        self.GetTypeName2 = type_name
        self.ErrorMessage = message
        self.IsSuppressed = suppressed
        self.GetFirstSubFeature = None
        self.GetNextSubFeature = None
        self.GetNextFeature = None


def _chain(feats: list[_FakeFeat]) -> _FakeFeat | None:
    """Link a flat list via GetNextFeature; return the first (or None)."""
    for a, b in zip(feats, feats[1:]):
        a.GetNextFeature = b
    return feats[0] if feats else None


class _FakeFeatMgr:
    def __init__(self, first: _FakeFeat | None) -> None:
        self.FirstFeature = first


class _FakeDoc:
    def __init__(self, feats: list[_FakeFeat]) -> None:
        self.FeatureManager = _FakeFeatMgr(_chain(feats))


class _BadDoc:
    @property
    def FeatureManager(self):  # noqa: D401 - simulates a COM failure
        raise RuntimeError("FeatureManager unavailable")


# --------------------------------------------------------------------------
# collect_feature_health (the doc-walker)
# --------------------------------------------------------------------------


def test_clean_tree_has_no_issues():
    doc = _FakeDoc([_FakeFeat("Boss-Extrude1"), _FakeFeat("Cut-Extrude1")])
    health = collect_feature_health(doc)
    assert health["error"] is None
    assert health["total_features"] == 2
    assert health["issues"] == []


def test_error_feature_is_listed():
    doc = _FakeDoc(
        [
            _FakeFeat("Boss-Extrude1"),
            _FakeFeat("Cut-Extrude1", code=2, message="rebuild failed"),
        ]
    )
    health = collect_feature_health(doc)
    assert health["error"] is None
    assert len(health["issues"]) == 1
    issue = health["issues"][0]
    assert issue["name"] == "Cut-Extrude1"
    assert issue["state_code"] == 2
    assert issue["state"] == "error"
    assert issue["description"] == "rebuild failed"


def test_warning_feature_is_listed_as_warning():
    doc = _FakeDoc([_FakeFeat("Sketch1", code=1, message="over defined")])
    health = collect_feature_health(doc)
    assert len(health["issues"]) == 1
    assert health["issues"][0]["state_code"] == 1
    assert health["issues"][0]["state"] == "warning"


def test_empty_tree_is_clean_not_error():
    doc = _FakeDoc([])
    health = collect_feature_health(doc)
    assert health["error"] is None
    assert health["total_features"] == 0
    assert health["issues"] == []


def test_walker_is_fail_soft_on_bad_doc():
    health = collect_feature_health(_BadDoc())
    assert health["error"] is not None
    assert "FeatureManager" in health["error"]
    assert health["issues"] == []
    assert health["total_features"] == 0


# --------------------------------------------------------------------------
# _health_gate (the pure policy)
# --------------------------------------------------------------------------


def test_gate_passes_on_empty_health():
    ok, err = builder._health_gate([], strict=False)
    assert ok is True
    assert err is None


def test_gate_fails_on_code2_and_names_offender():
    health = [{"name": "Cut-Extrude1", "code": 2, "message": "boom"}]
    ok, err = builder._health_gate(health, strict=False)
    assert ok is False
    assert "Cut-Extrude1" in err
    assert "code 2" in err


def test_gate_passes_on_warning_by_default():
    health = [{"name": "Sketch1", "code": 1, "message": "over defined"}]
    ok, err = builder._health_gate(health, strict=False)
    assert ok is True
    assert err is None


def test_gate_fails_on_warning_under_strict():
    health = [{"name": "Sketch1", "code": 1, "message": "over defined"}]
    ok, err = builder._health_gate(health, strict=True)
    assert ok is False
    assert "Sketch1" in err


def test_gate_reports_only_offenders_in_mixed_set():
    health = [
        {"name": "OK_feat_excluded_by_collect", "code": 0, "message": ""},
        {"name": "Warn1", "code": 1, "message": "w"},
        {"name": "Err1", "code": 2, "message": "e"},
    ]
    ok, err = builder._health_gate(health, strict=False)
    assert ok is False
    assert "Err1" in err
    assert "Warn1" not in err  # warning doesn't trip the default gate


# --------------------------------------------------------------------------
# BuildResult wire-format contract
# --------------------------------------------------------------------------


def test_to_dict_omits_feature_health_when_none():
    r = BuildResult(ok=True, features_built=["A"], bindings_added=[])
    assert "feature_health" not in r.to_dict()
    assert "error_tier" not in r.to_dict()


def test_to_dict_omits_feature_health_when_empty_list():
    # A clean build sets feature_health to None (via `feature_health or None`),
    # but an explicit empty list must also be omitted for wire-compat.
    r = BuildResult(ok=True, features_built=["A"], bindings_added=[], feature_health=[])
    assert "feature_health" not in r.to_dict()


def test_to_dict_includes_feature_health_and_error_tier_when_set():
    health = [{"name": "Cut-Extrude1", "code": 2, "message": "boom"}]
    r = BuildResult(
        ok=False,
        features_built=["Boss-Extrude1", "Cut-Extrude1"],
        bindings_added=[],
        error="post-rebuild feature errors: Cut-Extrude1 (code 2)",
        error_tier="post_rebuild",
        feature_health=health,
    )
    out = r.to_dict()
    assert out["ok"] is False
    assert out["error_tier"] == "post_rebuild"
    assert out["feature_health"] == health
