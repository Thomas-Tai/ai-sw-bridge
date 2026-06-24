"""Tests for tools/sw_version_tag.py — the N/N-1 matrix tagging helper (D-4).

Covers:
  - tag_revision: revision string -> "SW<year>" normalisation
  - tag_record: annotation of result dicts (shallow copy, never mutate input)
  - should_skip: per-(version, feature) skip logic
  - Parametrised matrix scaffold: (version, feature) cells run or skip correctly
  - Edge cases: unknown revisions, empty strings, non-string input

OFFLINE — no seat, no COM calls.  The revision string is injected directly;
the seat supplies ``sw.RevisionNumber`` later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable (it lives at the repo root, not inside a package).
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from sw_version_tag import (  # noqa: E402
    FEATURE_VERSION_SUPPORT,
    KNOWN_MAJORS,
    SUPPORTED_VERSIONS,
    should_skip,
    tag_record,
    tag_revision,
)


# ---------------------------------------------------------------------------
# tag_revision — normalisation
# ---------------------------------------------------------------------------


class TestTagRevision:
    @pytest.mark.parametrize(
        "revision,expected",
        [
            ("32.1.0", "SW2024"),
            ("32.0.0", "SW2024"),
            ("32", "SW2024"),
            ("33.0.0", "SW2025"),
            ("33", "SW2025"),
            ("34.1.0", "SW2026"),
        ],
    )
    def test_known_revisions(self, revision, expected):
        assert tag_revision(revision) == expected

    def test_integer_major(self):
        assert tag_revision(32) == "SW2024"
        assert tag_revision(33) == "SW2025"

    def test_unknown_major_gets_epoch_tag(self):
        assert tag_revision("99.0.0") == "SW2091"

    def test_empty_string(self):
        assert tag_revision("") == "SW_UNKNOWN"

    def test_none(self):
        assert tag_revision(None) == "SW_UNKNOWN"

    def test_non_numeric(self):
        assert tag_revision("garbage") == "SW_UNKNOWN"

    def test_bool_rejected(self):
        assert tag_revision(True) == "SW_UNKNOWN"
        assert tag_revision(False) == "SW_UNKNOWN"

    def test_dotted_non_numeric_first(self):
        assert tag_revision("abc.def") == "SW_UNKNOWN"


# ---------------------------------------------------------------------------
# tag_record — result-record annotation
# ---------------------------------------------------------------------------


class TestTagRecord:
    def test_annotates_sw_version_and_major(self):
        rec = tag_record({"ok": True}, "32.1.0")
        assert rec["sw_version"] == "SW2024"
        assert rec["sw_major"] == 32
        assert rec["ok"] is True

    def test_does_not_mutate_input(self):
        original = {"ok": True}
        tagged = tag_record(original, "33.0.0")
        assert "sw_version" not in original
        assert tagged is not original

    def test_unknown_revision(self):
        rec = tag_record({}, "bad")
        assert rec["sw_version"] == "SW_UNKNOWN"
        assert rec["sw_major"] is None

    def test_preserves_existing_keys(self):
        rec = tag_record({"feature": "boss_extrude", "ok": False}, "32.1.0")
        assert rec["feature"] == "boss_extrude"
        assert rec["ok"] is False
        assert rec["sw_version"] == "SW2024"

    def test_overwrites_existing_sw_version(self):
        rec = tag_record({"sw_version": "old"}, "32.1.0")
        assert rec["sw_version"] == "SW2024"


# ---------------------------------------------------------------------------
# should_skip — per-(version, feature) skip logic
# ---------------------------------------------------------------------------


class TestShouldSkip:
    def test_known_unsupported_returns_true(self):
        assert should_skip("SW2025", "FeatureCut4") is True

    def test_known_supported_returns_false(self):
        assert should_skip("SW2024", "FeatureCut4") is False

    def test_unknown_feature_returns_false(self):
        assert should_skip("SW2024", "nonexistent_feature") is False

    def test_unknown_version_returns_false(self):
        assert should_skip("SW9999", "FeatureCut4") is False

    def test_both_unknown_returns_false(self):
        assert should_skip("SW9999", "nonexistent_feature") is False


# ---------------------------------------------------------------------------
# Matrix scaffold — parametrised (version, feature) cells
# ---------------------------------------------------------------------------


class TestVersionFeatureMatrix:
    """Demonstrates the parametrize-by-(version, feature) pattern.

    The actual N-1 (SW2025) RUN is seat-gated — this scaffold asserts the
    tagging and skip logic offline, without a live SW process.
    """

    @pytest.mark.parametrize("version_tag", list(SUPPORTED_VERSIONS))
    def test_tag_round_trip(self, version_tag):
        """Each supported version round-trips through tag_revision."""
        reverse = {v: k for k, v in KNOWN_MAJORS.items()}
        major = reverse[version_tag]
        assert tag_revision(f"{major}.0.0") == version_tag

    @pytest.mark.parametrize(
        "version_tag,feature,expected_skip",
        [
            ("SW2024", "FeatureCut4", False),
            ("SW2025", "FeatureCut4", True),
            ("SW2024", "FeatureRevolve2", False),
            ("SW2025", "FeatureRevolve2", True),
            ("SW2024", "boss_extrude_blind", False),
            ("SW2025", "boss_extrude_blind", False),
        ],
        ids=[
            "SW2024-FeatureCut4-run",
            "SW2025-FeatureCut4-skip",
            "SW2024-FeatureRevolve2-run",
            "SW2025-FeatureRevolve2-skip",
            "SW2024-boss_extrude-run",
            "SW2025-boss_extrude-run",
        ],
    )
    def test_matrix_cell_skip_logic(self, version_tag, feature, expected_skip):
        assert should_skip(version_tag, feature) is expected_skip

    def test_matrix_records_tagged_correctly(self):
        """Simulate tagging a batch of result records from a matrix run."""
        fixtures = [
            ("32.1.0", "FeatureCut4", True),
            ("33.0.0", "FeatureCut4", False),
            ("32.1.0", "boss_extrude_blind", True),
        ]
        for rev, feature, expected_ok in fixtures:
            rec = tag_record({"feature": feature, "ok": expected_ok}, rev)
            tag = rec["sw_version"]
            assert tag in SUPPORTED_VERSIONS
            if should_skip(tag, feature):
                assert (
                    not expected_ok
                ), f"expected ok=False for skipped cell ({tag}, {feature})"


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_known_majors_are_contiguous(self):
        majors = sorted(KNOWN_MAJORS)
        assert majors == list(range(majors[0], majors[0] + len(majors)))

    def test_supported_versions_subset_of_known(self):
        known_tags = set(KNOWN_MAJORS.values())
        for v in SUPPORTED_VERSIONS:
            assert v in known_tags
