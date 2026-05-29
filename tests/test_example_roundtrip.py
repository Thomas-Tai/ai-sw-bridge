"""Tests for tools/example_roundtrip.py (W4.3).

Verifies the doc-as-test tool correctly validates example specs
and detects planted invalid specs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from example_roundtrip import _validate_one, main  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLES = _REPO_ROOT / "examples"


class TestValidateOne:
    def test_valid_spec_returns_none(self) -> None:
        spec_path = _EXAMPLES / "filleted_box" / "spec.json"
        if not spec_path.exists():
            pytest.skip("filleted_box example not found")
        assert _validate_one(spec_path) is None

    def test_invalid_json_returns_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken" / "spec.json"
        bad.parent.mkdir()
        bad.write_text("{not valid json", encoding="utf-8")
        err = _validate_one(bad)
        assert err is not None
        assert "invalid JSON" in err

    def test_schema_violation_returns_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken" / "spec.json"
        bad.parent.mkdir()
        bad.write_text(
            json.dumps({"schema_version": 1, "name": "x", "features": "not_a_list"}),
            encoding="utf-8",
        )
        err = _validate_one(bad)
        assert err is not None
        assert "validation_failed" in err


class TestMain:
    def test_shipped_examples_pass(self) -> None:
        rc = main(["--examples-dir", str(_EXAMPLES)])
        assert rc == 0

    def test_planted_invalid_spec_fails(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "broken_example"
        bad_dir.mkdir()
        (bad_dir / "spec.json").write_text(
            json.dumps({"schema_version": 99, "name": "bad"}),
            encoding="utf-8",
        )
        # Create a second valid example so the tool finds at least one
        good_dir = tmp_path / "good_example"
        good_dir.mkdir()
        (good_dir / "spec.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "good",
                    "features": [],
                }
            ),
            encoding="utf-8",
        )
        rc = main(["--examples-dir", str(tmp_path)])
        assert rc == 1

    def test_missing_dir_returns_2(self, tmp_path: Path) -> None:
        rc = main(["--examples-dir", str(tmp_path / "nonexistent")])
        assert rc == 2

    def test_empty_dir_returns_2(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_examples"
        empty.mkdir()
        rc = main(["--examples-dir", str(empty)])
        assert rc == 2
