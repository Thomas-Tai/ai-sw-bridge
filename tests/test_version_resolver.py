"""Unit tests for the version-dispatch resolver (FR-X-04).

The resolver picks a revision-keyed arg-builder for a COM op whose arity
changes across SW releases, via a newest->older cascade. Covers parsing,
the late-bound RevisionNumber read (fail-soft), the cascade policy, the
@versioned registry, and the one real wrapped call (FeatureCut4) staying
identical on SW 2024 (the only proven build). No seat needed -- the running
revision is injectable.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import _version_resolver as vr
from ai_sw_bridge.spec._version_resolver import (
    DEFAULT_KEY,
    VersionedOp,
    parse_major_revision,
    read_running_major,
    resolve_op,
)


# ---------------------------------------------------------------------------
# parse_major_revision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("32.1.0", 32),
        ("33", 33),
        (32, 32),
        ("34.0.0", 34),
        (None, None),
        ("", None),
        ("not.a.number", None),
        (True, None),  # bool is an int subclass -- must be rejected
        (False, None),
    ],
)
def test_parse_major_revision(value, expected):
    assert parse_major_revision(value) == expected


# ---------------------------------------------------------------------------
# read_running_major (late-bound, fail-soft)
# ---------------------------------------------------------------------------


class _FakeSW:
    def __init__(self, revision):
        self._rev = revision

    @property
    def RevisionNumber(self):  # zero-arg COM property idiom
        if isinstance(self._rev, Exception):
            raise self._rev
        return self._rev


def test_read_running_major_from_dotted_string():
    assert read_running_major(_FakeSW("32.1.0")) == 32


def test_read_running_major_none_sw():
    assert read_running_major(None) is None


def test_read_running_major_failsoft_on_com_error():
    # An unreadable property must degrade to None (-> default), not raise.
    assert read_running_major(_FakeSW(RuntimeError("no seat"))) is None


# ---------------------------------------------------------------------------
# VersionedOp cascade
# ---------------------------------------------------------------------------


def _op_with(*keys):
    op = VersionedOp("TestOp")
    for k in keys:
        op.register(k, lambda *, _k=k, **kw: ("built", _k))
    return op


def test_exact_major_match_wins():
    op = _op_with(32, 33, DEFAULT_KEY)
    assert op.resolve(33)(_=None)[1] == 33
    assert op.resolve(32)(_=None)[1] == 32


def test_cascade_picks_highest_at_or_below():
    op = _op_with(33, DEFAULT_KEY)
    # running newer than the newest registered -> newest registered (33).
    assert op.resolve(34)()[1] == 33
    assert op.resolve(99)()[1] == 33


def test_cascade_falls_back_to_default_when_below_all():
    op = _op_with(33, DEFAULT_KEY)
    # running older than every registered major -> default.
    assert op.resolve(31)()[1] == DEFAULT_KEY
    assert op.resolve(None)()[1] == DEFAULT_KEY


def test_missing_default_and_no_match_raises():
    op = _op_with(33)  # no default
    with pytest.raises(KeyError):
        op.resolve(31)
    with pytest.raises(KeyError):
        op.resolve(None)


def test_register_rejects_bad_key():
    op = VersionedOp("TestOp")
    with pytest.raises(ValueError):
        op.register("garbage", lambda **kw: ())


def test_build_resolves_and_invokes():
    op = _op_with(32, DEFAULT_KEY)
    assert op.build(32)[0] == "built"


# ---------------------------------------------------------------------------
# Registry + the real FeatureCut4 wiring (2024 behaviour-preserving)
# ---------------------------------------------------------------------------


def test_featurecut4_registered_with_default_and_2025():
    # Importing builder registers the variants via @versioned at module load.
    from ai_sw_bridge.spec import builder  # noqa: F401

    keys = sorted(vr.REGISTRY["FeatureCut4"]._variants, key=str)
    assert keys == [33, "default"]


def test_featurecut4_dispatch_by_running_major():
    from ai_sw_bridge.spec import builder

    # SW 2024 (major 32) and anything below the 2025 break -> the proven 2024
    # arg-builder; 2025+ -> the 2025 stub.
    assert resolve_op("FeatureCut4", running_major=32) is builder._cut4_args_2024
    assert resolve_op("FeatureCut4", running_major=None) is builder._cut4_args_2024
    assert resolve_op("FeatureCut4", running_major=33) is builder._cut4_args_2025
    assert resolve_op("FeatureCut4", running_major=34) is builder._cut4_args_2025


def test_featurecut4_2024_args_unchanged():
    from ai_sw_bridge.spec import builder

    args = builder._cut4_args_2024(end_cond=0, depth_m=0.01, flip=False)
    # The proven SW 2017+ FeatureCut4 signature is exactly 27 positional args.
    assert len(args) == 27
    assert args[0] is True  # Sd (single-ended)
    assert args[1] is False  # Flip


def test_featurecut4_resolved_via_fake_sw_revision():
    from ai_sw_bridge.spec import builder

    # End-to-end injection: a fake app reporting "32.1.0" resolves to 2024.
    builder_2024 = resolve_op("FeatureCut4", sw=_FakeSW("32.1.0"))
    assert builder_2024 is builder._cut4_args_2024
    builder_2025 = resolve_op("FeatureCut4", sw=_FakeSW("33.0.0"))
    assert builder_2025 is builder._cut4_args_2025
