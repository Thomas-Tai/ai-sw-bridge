"""Tests for the anti-loop retry guard (Task 2.1).

Covers: identical-spec refusal, whitespace-only diff (canonicalized, still
refused), single-param change accepted, cross-session persistence via
telemetry store.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.errors.auto_retry import IdenticalSpecError, RetryGuard, spec_hash
from ai_sw_bridge.telemetry.store import TelemetryStore


def _spec(**overrides: object) -> dict:
    base = {
        "name": "test_part",
        "schema_version": 1,
        "features": [
            {"type": "cylinder", "name": "cyl", "diameter": 25.0, "length": 80.0}
        ],
    }
    base.update(overrides)
    return base


class TestSpecHash:
    def test_deterministic(self) -> None:
        s = _spec()
        assert spec_hash(s) == spec_hash(s)

    def test_key_order_independent(self) -> None:
        a = {"name": "x", "schema_version": 1}
        b = {"schema_version": 1, "name": "x"}
        assert spec_hash(a) == spec_hash(b)

    def test_whitespace_irrelevant(self) -> None:
        # json.dumps with default separators includes spaces; canonical
        # form strips them. Both must hash the same.
        raw = '{"name": "x"}'
        parsed = json.loads(raw)
        h = spec_hash(parsed)
        assert isinstance(h, str) and len(h) == 64

    def test_different_content_different_hash(self) -> None:
        assert spec_hash(_spec(name="a")) != spec_hash(_spec(name="b"))


class TestRetryGuardInMemory:
    def test_first_attempt_passes(self) -> None:
        guard = RetryGuard()
        s = _spec()
        h = guard.check(s)
        assert h == spec_hash(s)

    def test_identical_spec_refused(self) -> None:
        guard = RetryGuard()
        s = _spec()
        guard.record_attempt(s, error="build failed")
        with pytest.raises(IdenticalSpecError) as exc_info:
            guard.check(s)
        assert "identical spec submitted" in str(exc_info.value)
        assert exc_info.value.attempt_count == 1
        assert exc_info.value.last_error == "build failed"

    def test_whitespace_only_diff_still_refused(self) -> None:
        guard = RetryGuard()
        s = _spec()
        guard.record_attempt(s)
        # Re-parse from JSON with extra whitespace — canonicalization
        # collapses it, so the hash matches.
        s2 = json.loads(json.dumps(s, indent=2))
        with pytest.raises(IdenticalSpecError):
            guard.check(s2)

    def test_single_param_change_accepted(self) -> None:
        guard = RetryGuard()
        s1 = _spec()
        guard.record_attempt(s1, error="wrong diameter")
        # Change one parameter
        s2 = _spec()
        s2["features"][0]["diameter"] = 30.0
        h = guard.check(s2)
        assert h != spec_hash(s1)

    def test_multiple_attempts_tracked(self) -> None:
        guard = RetryGuard()
        s = _spec()
        guard.record_attempt(s, error="fail 1")
        guard.record_attempt(s, error="fail 2")
        with pytest.raises(IdenticalSpecError) as exc_info:
            guard.check(s)
        assert exc_info.value.attempt_count == 2

    def test_different_specs_independent(self) -> None:
        guard = RetryGuard()
        s1 = _spec(name="part_a")
        s2 = _spec(name="part_b")
        guard.record_attempt(s1)
        # s2 is different, should pass
        h2 = guard.check(s2)
        assert h2 == spec_hash(s2)

    def test_record_after_check_allows_rejection(self) -> None:
        guard = RetryGuard()
        s = _spec()
        h = guard.check(s)
        assert h == spec_hash(s)
        # Now record it — future checks should fail
        guard.record_attempt(s, error="failed")
        with pytest.raises(IdenticalSpecError):
            guard.check(s)


class TestRetryGuardWithStore:
    def test_cross_session_persistence(self, tmp_path: Path) -> None:
        db = tmp_path / "telemetry.sqlite"

        # Session 1: record an attempt
        store1 = TelemetryStore(db_path=db)
        guard1 = RetryGuard(store=store1)
        s = _spec()
        guard1.record_attempt(s, error="COM error")
        store1.close()

        # Session 2: same spec should be refused
        store2 = TelemetryStore(db_path=db)
        guard2 = RetryGuard(store=store2)
        with pytest.raises(IdenticalSpecError) as exc_info:
            guard2.check(s)
        assert "COM error" in str(exc_info.value)
        store2.close()

    def test_cross_session_different_spec_passes(self, tmp_path: Path) -> None:
        db = tmp_path / "telemetry.sqlite"

        store1 = TelemetryStore(db_path=db)
        guard1 = RetryGuard(store=store1)
        guard1.record_attempt(_spec(name="a"))
        store1.close()

        store2 = TelemetryStore(db_path=db)
        guard2 = RetryGuard(store=store2)
        h = guard2.check(_spec(name="b"))
        assert isinstance(h, str) and len(h) == 64
        store2.close()

    def test_no_store_memory_only(self) -> None:
        guard = RetryGuard(store=None)
        s = _spec()
        guard.record_attempt(s)
        with pytest.raises(IdenticalSpecError):
            guard.check(s)
