"""Tests for tools/regression_check.py SLI instrumentation.

Covers:
  - Percentile math (p50/p95/p99) with various input sizes
  - SLO-01/02 threshold enforcement
  - Baseline regression detection (p95 >15%, p99 >25%)
  - --write-baseline output structure
  - --baseline-compare with missing/empty file
  - Edge cases: empty list, single value

No SOLIDWORKS required — tests only the pure-Python SLI functions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from regression_check import (
    SLO_01_P95_MAX_S,
    SLO_02_P99_MAX_S,
    _check_slo_and_baseline,
    _compute_percentiles,
    _make_perf_payload,
)


class TestComputePercentiles:
    def test_empty_list(self):
        result = _compute_percentiles([])
        assert result["p50"] is None
        assert result["p95"] is None
        assert result["p99"] is None

    def test_single_value(self):
        result = _compute_percentiles([5.0])
        assert result["p50"] == 5.0
        assert result["p95"] == 5.0
        assert result["p99"] == 5.0

    def test_multiple_values(self):
        times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = _compute_percentiles(times)
        assert result["p50"] is not None
        assert result["p95"] is not None
        assert result["p99"] is not None
        # p50 should be near the median
        assert 4.0 <= result["p50"] <= 6.0
        # p95 should be near the top
        assert result["p95"] >= 8.0
        # p99 should be near the top
        assert result["p99"] >= 9.0

    def test_large_dataset(self):
        times = list(range(1, 101))  # 1..100
        result = _compute_percentiles(times)
        assert 49 <= result["p50"] <= 51
        assert 93 <= result["p95"] <= 96
        assert 97 <= result["p99"] <= 100

    def test_values_are_rounded(self):
        result = _compute_percentiles([1.123456, 2.654321])
        for key in ("p50", "p95", "p99"):
            if result[key] is not None:
                # Check rounded to 3 decimal places
                assert str(result[key])[::-1].find(".") <= 3


class TestSLOThresholds:
    def test_within_slo_passes(self):
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, None) is True

    def test_p95_exceeds_slo01(self):
        percentiles = {"p50": 3.0, "p95": 13.0, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, None) is False

    def test_p99_exceeds_slo02(self):
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 26.0}
        assert _check_slo_and_baseline(percentiles, None) is False

    def test_none_percentiles_skip_check(self):
        percentiles = {"p50": None, "p95": None, "p99": None}
        assert _check_slo_and_baseline(percentiles, None) is True

    def test_exactly_at_threshold_passes(self):
        percentiles = {"p50": 3.0, "p95": SLO_01_P95_MAX_S, "p99": SLO_02_P99_MAX_S}
        assert _check_slo_and_baseline(percentiles, None) is True


class TestBaselineRegression:
    def _baseline_file(self, tmp_path, p95: float, p99: float) -> Path:
        bp = tmp_path / "baseline.json"
        bp.write_text(
            json.dumps({"p95": p95, "p99": p99, "version": "v0.10"}), encoding="utf-8"
        )
        return bp

    def test_no_regression_passes(self, tmp_path):
        bp = self._baseline_file(tmp_path, p95=8.0, p99=15.0)
        percentiles = {"p50": 3.0, "p95": 9.0, "p99": 18.0}
        assert _check_slo_and_baseline(percentiles, bp) is True

    def test_p95_regresses_beyond_threshold(self, tmp_path):
        bp = self._baseline_file(tmp_path, p95=8.0, p99=15.0)
        # 10.0 is 25% above 8.0, exceeds 15% threshold
        percentiles = {"p50": 3.0, "p95": 10.0, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, bp) is False

    def test_p99_regresses_beyond_threshold(self, tmp_path):
        bp = self._baseline_file(tmp_path, p95=8.0, p99=15.0)
        # 20.0 is ~33% above 15.0, exceeds 25% threshold
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 20.0}
        assert _check_slo_and_baseline(percentiles, bp) is False

    def test_p95_just_under_threshold_passes(self, tmp_path):
        bp = self._baseline_file(tmp_path, p95=8.0, p99=15.0)
        # 9.1 is ~13.75% above 8.0, under 15% threshold
        percentiles = {"p50": 3.0, "p95": 9.1, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, bp) is True

    def test_missing_baseline_file_passes(self, tmp_path):
        bp = tmp_path / "nonexistent.json"
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, bp) is True

    def test_baseline_none_passes(self):
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 15.0}
        assert _check_slo_and_baseline(percentiles, None) is True


class TestMakePerfPayload:
    def test_structure(self):
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 15.0}
        payload = _make_perf_payload(
            percentiles, n_specs=15, spec_times=[1.0, 2.0, 3.0]
        )
        assert payload["p50"] == 3.0
        assert payload["p95"] == 8.0
        assert payload["p99"] == 15.0
        assert payload["n_specs"] == 15
        assert "timestamp" in payload
        assert "host_meta" in payload
        assert payload["spec_times"] == [1.0, 2.0, 3.0]

    def test_json_serializable(self):
        percentiles = {"p50": 3.0, "p95": 8.0, "p99": 15.0}
        payload = _make_perf_payload(percentiles, n_specs=5, spec_times=[1.0])
        text = json.dumps(payload, indent=2)
        reloaded = json.loads(text)
        assert reloaded == payload
