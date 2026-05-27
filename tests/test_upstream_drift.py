"""Tests for tools/check_upstream_drift.py.

Covers:
  - Pin extraction from harvest_plan.md recipes
  - Pin extraction from CONTRIBUTING.md "Third-party derivations" table
  - Deduplication across both sources
  - GitHub API response parsing (identical / ahead / error)
  - Threshold flagging (exit 1 when >N commits)
  - JSON and table output formats
  - Empty-pins edge case
  - --threshold override

No live GitHub API calls — all network interaction is mocked.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

# tools/ is not on the default import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from check_upstream_drift import (
    UpstreamPin,
    DriftResult,
    check_drift,
    collect_pins,
    format_json,
    format_table,
    main,
    read_pins_from_contributing,
    read_pins_from_harvest_plan,
)


# ---------------------------------------------------------------------------
# Pin extraction — harvest_plan.md
# ---------------------------------------------------------------------------


class TestReadPinsFromHarvestPlan:
    def test_extracts_recipe_with_sha(self, tmp_path):
        hp = tmp_path / "harvest_plan.md"
        hp.write_text(
            textwrap.dedent(
                """\
                ### Recipe 5.2 — Port `circuit_breaker.py` (for L2)

                **Source:** `SolidworksMCP-python/src/solidworks_mcp/adapters/circuit_breaker.py`
                **Target:** `src/ai_sw_bridge/errors/circuit_breaker.py`
                **Attribution:** module-level docstring.
                Commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
            """
            ),
            encoding="utf-8",
        )
        pins = read_pins_from_harvest_plan(hp)
        assert len(pins) == 1
        assert pins[0].pinned_sha == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert "SolidworksMCP-python" in pins[0].repo

    def test_skips_recipe_without_sha(self, tmp_path):
        hp = tmp_path / "harvest_plan.md"
        hp.write_text(
            textwrap.dedent(
                """\
                ### Recipe 5.2 — Port `circuit_breaker.py` (for L2)

                **Source:** `SolidworksMCP-python/src/solidworks_mcp/adapters/circuit_breaker.py`
                **Target:** `src/ai_sw_bridge/errors/circuit_breaker.py`
                **Attribution:** module-level docstring.
            """
            ),
            encoding="utf-8",
        )
        pins = read_pins_from_harvest_plan(hp)
        # A recipe without a Commit: line is informational, not a drift-pin
        # claim. Skip it so the drift report stays actionable.
        assert pins == []

    def test_missing_file_returns_empty(self, tmp_path):
        pins = read_pins_from_harvest_plan(tmp_path / "nonexistent.md")
        assert pins == []


# ---------------------------------------------------------------------------
# Pin extraction — CONTRIBUTING.md
# ---------------------------------------------------------------------------


class TestReadPinsFromContributing:
    def test_extracts_table_row(self, tmp_path):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                ## Third-party derivations

                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/ai_sw_bridge/errors/circuit_breaker.py` | SolidworksMCP-python | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | first port |
            """
            ),
            encoding="utf-8",
        )
        pins = read_pins_from_contributing(contrib)
        assert len(pins) == 1
        assert pins[0].pinned_sha == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert "circuit_breaker" in pins[0].target_file

    def test_skips_row_without_commit(self, tmp_path):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/x.py` | SomeRepo | MIT |  | 2026-06-01 | TBD | no sha |
            """
            ),
            encoding="utf-8",
        )
        pins = read_pins_from_contributing(contrib)
        assert pins == []

    def test_missing_file_returns_empty(self, tmp_path):
        pins = read_pins_from_contributing(tmp_path / "nonexistent.md")
        assert pins == []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestCollectPins:
    def test_deduplicates_across_sources(self, tmp_path):
        hp = tmp_path / "harvest_plan.md"
        hp.write_text(
            textwrap.dedent(
                """\
                ### Recipe 5.2 — Port `circuit_breaker.py` (for L2)

                **Source:** `SolidworksMCP-python/src/solidworks_mcp/adapters/circuit_breaker.py`
                **Target:** `src/ai_sw_bridge/errors/circuit_breaker.py`
                Commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
            """
            ),
            encoding="utf-8",
        )
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/ai_sw_bridge/errors/circuit_breaker.py` | SolidworksMCP-python | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | first port |
            """
            ),
            encoding="utf-8",
        )
        with (
            patch("check_upstream_drift.HARVEST_PLAN", hp),
            patch("check_upstream_drift.CONTRIBUTING", contrib),
        ):
            pins = collect_pins()
        # Same repo + same SHA — deduped to 1
        assert len(pins) == 1


# ---------------------------------------------------------------------------
# GitHub API response parsing
# ---------------------------------------------------------------------------


class TestCheckDrift:
    def test_identical_returns_zero(self):
        pin = UpstreamPin(repo="owner/repo", pinned_sha="a" * 40, source_file="test")
        mock_data = {"status": "identical", "ahead_by": 0, "commits": []}
        with patch("check_upstream_drift._github_get", return_value=(mock_data, "")):
            result = check_drift(pin)
        assert result.commits_since_pin == 0
        assert result.latest_sha == pin.pinned_sha

    def test_ahead_by_returns_count(self):
        pin = UpstreamPin(repo="owner/repo", pinned_sha="a" * 40, source_file="test")
        mock_data = {
            "status": "ahead",
            "ahead_by": 30,
            "commits": [
                {"sha": "b" * 40, "commit": {"committer": {"date": "2026-05-20"}}},
            ],
        }
        with patch("check_upstream_drift._github_get", return_value=(mock_data, "")):
            result = check_drift(pin)
        assert result.commits_since_pin == 30
        assert result.latest_sha == "b" * 40
        assert result.last_commit_date == "2026-05-20"

    def test_api_error_returns_error_string(self):
        pin = UpstreamPin(repo="owner/repo", pinned_sha="a" * 40, source_file="test")
        with patch(
            "check_upstream_drift._github_get",
            side_effect=Exception("network error"),
        ):
            result = check_drift(pin)
        assert result.error == "network error"
        assert result.commits_since_pin is None

    def test_missing_sha_returns_error(self):
        pin = UpstreamPin(repo="owner/repo", pinned_sha="", source_file="test")
        result = check_drift(pin)
        assert "no pinned commit SHA" in result.error


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


class TestOutputFormats:
    def test_table_has_headers(self):
        results = [
            DriftResult(repo="owner/repo", pinned_sha="a" * 40, commits_since_pin=5)
        ]
        table = format_table(results)
        assert "Repo" in table
        assert "owner/repo" in table

    def test_json_is_valid(self):
        results = [
            DriftResult(repo="owner/repo", pinned_sha="a" * 40, commits_since_pin=5)
        ]
        output = format_json(results)
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["repo"] == "owner/repo"
        assert data[0]["commits_since_pin"] == 5


# ---------------------------------------------------------------------------
# Main / threshold
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_1_when_drift_exceeds_threshold(self, tmp_path):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/x.py` | owner/repo | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | test |
            """
            ),
            encoding="utf-8",
        )
        mock_data = {"status": "ahead", "ahead_by": 60, "commits": []}
        with (
            patch("check_upstream_drift.CONTRIBUTING", contrib),
            patch("check_upstream_drift.HARVEST_PLAN", tmp_path / "nope.md"),
            patch("check_upstream_drift._github_get", return_value=(mock_data, "")),
        ):
            exit_code = main(["--threshold", "50"])
        assert exit_code == 1

    def test_exits_0_when_drift_below_threshold(self, tmp_path):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/x.py` | owner/repo | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | test |
            """
            ),
            encoding="utf-8",
        )
        mock_data = {"status": "ahead", "ahead_by": 10, "commits": []}
        with (
            patch("check_upstream_drift.CONTRIBUTING", contrib),
            patch("check_upstream_drift.HARVEST_PLAN", tmp_path / "nope.md"),
            patch("check_upstream_drift._github_get", return_value=(mock_data, "")),
        ):
            exit_code = main(["--threshold", "50"])
        assert exit_code == 0

    def test_threshold_0_flags_any_drift(self, tmp_path):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/x.py` | owner/repo | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | test |
            """
            ),
            encoding="utf-8",
        )
        mock_data = {"status": "ahead", "ahead_by": 1, "commits": []}
        with (
            patch("check_upstream_drift.CONTRIBUTING", contrib),
            patch("check_upstream_drift.HARVEST_PLAN", tmp_path / "nope.md"),
            patch("check_upstream_drift._github_get", return_value=(mock_data, "")),
        ):
            exit_code = main(["--threshold", "0"])
        assert exit_code == 1

    def test_no_pins_exits_0(self, tmp_path):
        with (
            patch("check_upstream_drift.CONTRIBUTING", tmp_path / "nope.md"),
            patch("check_upstream_drift.HARVEST_PLAN", tmp_path / "nope2.md"),
        ):
            exit_code = main([])
        assert exit_code == 0

    def test_json_output(self, tmp_path, capsys):
        contrib = tmp_path / "CONTRIBUTING.md"
        contrib.write_text(
            textwrap.dedent(
                """\
                | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
                | --- | --- | --- | --- | --- | --- | --- |
                | `src/x.py` | owner/repo | MIT | a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 | 2026-06-01 | TBD | test |
            """
            ),
            encoding="utf-8",
        )
        mock_data = {"status": "identical", "ahead_by": 0, "commits": []}
        with (
            patch("check_upstream_drift.CONTRIBUTING", contrib),
            patch("check_upstream_drift.HARVEST_PLAN", tmp_path / "nope.md"),
            patch("check_upstream_drift._github_get", return_value=(mock_data, "")),
        ):
            exit_code = main(["--format", "json"])
        assert exit_code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert isinstance(data, list)
