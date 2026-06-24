"""Tests for the golden geometry (B-rep fingerprint) harness — X6 (TR-OBS-02).

Covers the SW-free harness added to tools/regression_check.py:
  - hash_brep_manifest: stable, order-independent, drift-sensitive
  - check_geometry_drift: skip when no golden, pass on match, fail on drift

No SOLIDWORKS required.  Populating golden_brep_hash.json files requires a
seat run; see tools/regression_check.py --capture for the write path.

CI integration (test_no_geometry_drift_across_examples) is opt-in: it
skips automatically when no examples/*/golden_brep_hash.json files exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from regression_check import check_geometry_drift, hash_brep_manifest

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest(features: list[dict]) -> dict:
    return {"schema_version": 1, "features": features}


def _feature(name: str, fingerprints: list[str]) -> dict:
    faces = [{"fingerprint": fp, "face_idx": i} for i, fp in enumerate(fingerprints)]
    return {"feature": name, "faces": faces}


# ---------------------------------------------------------------------------
# hash_brep_manifest
# ---------------------------------------------------------------------------


class TestHashBrepManifest:
    def test_returns_64_hex_chars(self):
        h = hash_brep_manifest(_manifest([_feature("A", ["abc1234567890abcd"])]))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        m = _manifest(
            [_feature("A", ["aabbccdd11223344"]), _feature("B", ["eeff00112233aabb"])]
        )
        assert hash_brep_manifest(m) == hash_brep_manifest(m)

    def test_order_independent_across_features(self):
        m1 = _manifest([_feature("A", ["aaaa"]), _feature("B", ["bbbb"])])
        m2 = _manifest([_feature("B", ["bbbb"]), _feature("A", ["aaaa"])])
        assert hash_brep_manifest(m1) == hash_brep_manifest(m2)

    def test_order_independent_within_feature(self):
        m1 = _manifest([_feature("A", ["xxxx", "yyyy"])])
        m2 = _manifest([_feature("A", ["yyyy", "xxxx"])])
        assert hash_brep_manifest(m1) == hash_brep_manifest(m2)

    def test_different_fingerprints_change_hash(self):
        m1 = _manifest([_feature("A", ["aaaa"])])
        m2 = _manifest([_feature("A", ["bbbb"])])
        assert hash_brep_manifest(m1) != hash_brep_manifest(m2)

    def test_extra_face_changes_hash(self):
        m1 = _manifest([_feature("A", ["aaaa"])])
        m2 = _manifest([_feature("A", ["aaaa", "bbbb"])])
        assert hash_brep_manifest(m1) != hash_brep_manifest(m2)

    def test_empty_manifest_stable(self):
        h = hash_brep_manifest(_manifest([]))
        assert len(h) == 64
        assert hash_brep_manifest(_manifest([])) == h

    def test_faces_without_fingerprint_skipped(self):
        """Error-feature faces (no 'fingerprint' key) do not crash or contribute."""
        m_with_error = _manifest([{"feature": "A", "faces": [{"face_idx": 0}]}])
        m_empty = _manifest([])
        assert hash_brep_manifest(m_with_error) == hash_brep_manifest(m_empty)

    def test_mixed_error_and_good_faces(self):
        good = _manifest([_feature("A", ["cccc"])])
        mixed = _manifest(
            [
                {
                    "feature": "A",
                    "faces": [
                        {"face_idx": 0},  # error face, no fingerprint
                        {"fingerprint": "cccc", "face_idx": 1},
                    ],
                }
            ]
        )
        assert hash_brep_manifest(mixed) == hash_brep_manifest(good)


# ---------------------------------------------------------------------------
# check_geometry_drift
# ---------------------------------------------------------------------------


class TestCheckGeometryDrift:
    def test_no_golden_passes(self, tmp_path):
        m = _manifest([_feature("A", ["aaaa"])])
        assert check_geometry_drift(tmp_path, m) is True

    def test_matching_golden_passes(self, tmp_path):
        m = _manifest([_feature("A", ["aaaa"])])
        stored = hash_brep_manifest(m)
        (tmp_path / "golden_brep_hash.json").write_text(
            json.dumps({"brep_hash": stored, "face_count": 1}),
            encoding="utf-8",
        )
        assert check_geometry_drift(tmp_path, m) is True

    def test_drifted_hash_fails(self, tmp_path):
        m = _manifest([_feature("A", ["aaaa"])])
        (tmp_path / "golden_brep_hash.json").write_text(
            json.dumps({"brep_hash": "0" * 64, "face_count": 1}),
            encoding="utf-8",
        )
        assert check_geometry_drift(tmp_path, m) is False

    def test_missing_brep_hash_key_fails(self, tmp_path):
        """A golden file without 'brep_hash' stores empty string → mismatch."""
        m = _manifest([_feature("A", ["aaaa"])])
        (tmp_path / "golden_brep_hash.json").write_text(
            json.dumps({"note": "no brep_hash key"}),
            encoding="utf-8",
        )
        assert check_geometry_drift(tmp_path, m) is False

    def test_added_face_detected_as_drift(self, tmp_path):
        m_orig = _manifest([_feature("A", ["aaaa"])])
        stored = hash_brep_manifest(m_orig)
        (tmp_path / "golden_brep_hash.json").write_text(
            json.dumps({"brep_hash": stored}), encoding="utf-8"
        )
        m_new = _manifest([_feature("A", ["aaaa", "bbbb"])])
        assert check_geometry_drift(tmp_path, m_new) is False

    def test_removed_face_detected_as_drift(self, tmp_path):
        m_orig = _manifest([_feature("A", ["aaaa", "bbbb"])])
        stored = hash_brep_manifest(m_orig)
        (tmp_path / "golden_brep_hash.json").write_text(
            json.dumps({"brep_hash": stored}), encoding="utf-8"
        )
        m_fewer = _manifest([_feature("A", ["aaaa"])])
        assert check_geometry_drift(tmp_path, m_fewer) is False


# ---------------------------------------------------------------------------
# CI opt-in: skip when no golden_brep_hash.json files exist
# ---------------------------------------------------------------------------

_GOLDEN_DIRS = sorted(EXAMPLES_ROOT.glob("*/golden_brep_hash.json"))


@pytest.mark.skipif(
    not _GOLDEN_DIRS,
    reason=(
        "no examples/*/golden_brep_hash.json files found — "
        "run 'python tools/regression_check.py --capture' on a live SOLIDWORKS seat first"
    ),
)
def test_no_geometry_drift_across_examples():
    """CI opt-in: fail if any example's B-rep fingerprint hash drifts from its golden.

    Requires both golden_brep_hash.json (written by --capture on a seat) and
    build_brep.json (written by ai-sw-build alongside the .sldprt) to be present.
    Skips individual examples whose build_brep.json is absent.
    """
    failures: list[str] = []
    skipped: list[str] = []
    for golden_path in _GOLDEN_DIRS:
        spec_dir = golden_path.parent
        brep_path = spec_dir / "build_brep.json"
        if not brep_path.exists():
            skipped.append(spec_dir.name)
            continue
        manifest_dict = json.loads(brep_path.read_text(encoding="utf-8"))
        if not check_geometry_drift(spec_dir, manifest_dict):
            failures.append(spec_dir.name)
    if skipped:
        pytest.skip(
            f"build_brep.json absent for: {', '.join(skipped)} — rebuild on a seat first"
        )
    assert not failures, f"B-rep fingerprint drift detected in: {', '.join(failures)}"
