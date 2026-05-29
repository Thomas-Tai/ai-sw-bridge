"""Tests for --save-format flag (W2.4).

Verifies that the save_format CLI flag correctly maps to SaveAs3's
version argument, that argparse rejects bad values, and that the
BuildResult and build_metrics sidecar carry the field.

No SW required; SaveAs3 is mocked via a stub doc object.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_sw_bridge.spec.builder import (
    SAVE_FORMAT_VERSIONS,
    BuildResult,
    _save_as_with_verification,
)


class _StubDoc:
    """Minimal IModelDoc2 stub that captures SaveAs3 arguments."""

    def __init__(self) -> None:
        self.save_args: tuple | None = None

    def SaveAs3(self, path: str, options: int, version: int) -> int:
        self.save_args = (path, options, version)
        Path(path).write_bytes(b"stub-content")
        return 0

    @property
    def GetSaveFlag(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# SAVE_FORMAT_VERSIONS mapping
# ---------------------------------------------------------------------------


class TestSaveFormatVersions:
    def test_current_maps_to_zero(self) -> None:
        assert SAVE_FORMAT_VERSIONS["current"] == 0

    def test_all_years_present(self) -> None:
        for year in ("2021", "2022", "2023", "2024"):
            assert year in SAVE_FORMAT_VERSIONS
            assert isinstance(SAVE_FORMAT_VERSIONS[year], int)
            assert SAVE_FORMAT_VERSIONS[year] > 0

    def test_years_are_distinct(self) -> None:
        vals = [SAVE_FORMAT_VERSIONS[y] for y in ("2021", "2022", "2023", "2024")]
        assert len(set(vals)) == 4


# ---------------------------------------------------------------------------
# _save_as_with_verification passes version through
# ---------------------------------------------------------------------------


class TestSaveVersionPassthrough:
    def test_default_version_is_zero(self, tmp_path: Path) -> None:
        doc = _StubDoc()
        out = tmp_path / "part.sldprt"
        _save_as_with_verification(doc, out)
        assert doc.save_args is not None
        assert doc.save_args[2] == 0  # version arg

    def test_explicit_version_flows_through(self, tmp_path: Path) -> None:
        doc = _StubDoc()
        out = tmp_path / "part.sldprt"
        _save_as_with_verification(doc, out, save_version=30)
        assert doc.save_args is not None
        assert doc.save_args[2] == 30

    @pytest.mark.parametrize(
        "fmt,expected_version",
        [
            ("current", 0),
            ("2024", SAVE_FORMAT_VERSIONS["2024"]),
            ("2023", SAVE_FORMAT_VERSIONS["2023"]),
            ("2022", SAVE_FORMAT_VERSIONS["2022"]),
            ("2021", SAVE_FORMAT_VERSIONS["2021"]),
        ],
    )
    def test_each_format_maps_correctly(
        self, tmp_path: Path, fmt: str, expected_version: int
    ) -> None:
        doc = _StubDoc()
        out = tmp_path / "part.sldprt"
        version = SAVE_FORMAT_VERSIONS.get(fmt, 0)
        _save_as_with_verification(doc, out, save_version=version)
        assert doc.save_args is not None
        assert doc.save_args[2] == expected_version


# ---------------------------------------------------------------------------
# BuildResult.to_dict() includes save_format
# ---------------------------------------------------------------------------


class TestBuildResultSaveFormat:
    def test_save_format_absent_by_default(self) -> None:
        r = BuildResult(ok=True, features_built=["X"], bindings_added=[])
        d = r.to_dict()
        assert "save_format" not in d

    def test_save_format_present_when_set(self) -> None:
        r = BuildResult(
            ok=True, features_built=["X"], bindings_added=[], save_format="2021"
        )
        d = r.to_dict()
        assert d["save_format"] == "2021"

    def test_save_format_current(self) -> None:
        r = BuildResult(
            ok=True, features_built=["X"], bindings_added=[], save_format="current"
        )
        assert r.to_dict()["save_format"] == "current"


# ---------------------------------------------------------------------------
# CLI argparse validation
# ---------------------------------------------------------------------------


class TestCliSaveFormatArgparse:
    def test_valid_choices_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each valid choice parses without argparse error (exit 2 = file not found)."""
        from ai_sw_bridge.cli.build import main

        for choice in ("current", "2024", "2023", "2022", "2021"):
            monkeypatch.setattr(
                "sys.argv",
                ["ai-sw-build", "nonexistent.json", "--save-format", choice],
            )
            rc = main()
            # 2 = file not found (not argparse error which would sys.exit(2))
            assert rc == 2, f"choice {choice!r}: expected rc=2, got {rc}"

    def test_invalid_choice_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An invalid --save-format value triggers an argparse error (exit 2)."""
        from ai_sw_bridge.cli.build import main

        monkeypatch.setattr(
            "sys.argv",
            ["ai-sw-build", "nonexistent.json", "--save-format", "2019"],
        )
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_default_is_current(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without --save-format, the default is 'current'."""
        from ai_sw_bridge.cli.build import main

        import io
        from contextlib import redirect_stdout, redirect_stderr

        monkeypatch.setattr("sys.argv", ["ai-sw-build", "--help"])
        buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err_buf):
            with pytest.raises(SystemExit):
                main()
        help_text = buf.getvalue()
        assert "current" in help_text
        assert "save-format" in help_text


# ---------------------------------------------------------------------------
# build_metrics sidecar includes save_format
# ---------------------------------------------------------------------------


class TestBuildMetricsSaveFormat:
    def test_metrics_includes_save_format(self, tmp_path: Path) -> None:
        from ai_sw_bridge.cli.build import _write_build_metrics

        result = SimpleNamespace(
            ok=True,
            mode="no_dim",
            features_built=["A", "B"],
            build_time_s=1.234,
            feature_metrics=[],
            bindings_added=[],
            mass_verification=[],
            save_format="2021",
        )
        spec = {"name": "test_part"}
        sldprt = str(tmp_path / "test_part.sldprt")
        # Create a fake .sldprt file
        Path(sldprt).write_bytes(b"fake")
        metrics_path = _write_build_metrics(result, spec, sldprt)
        metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
        assert metrics["save_format"] == "2021"

    def test_metrics_omits_save_format_when_none(self, tmp_path: Path) -> None:
        from ai_sw_bridge.cli.build import _write_build_metrics

        result = SimpleNamespace(
            ok=True,
            mode="no_dim",
            features_built=["A"],
            build_time_s=0.5,
            feature_metrics=[],
            bindings_added=[],
            mass_verification=[],
            save_format=None,
        )
        spec = {"name": "test_part"}
        sldprt = str(tmp_path / "test_part.sldprt")
        Path(sldprt).write_bytes(b"fake")
        metrics_path = _write_build_metrics(result, spec, sldprt)
        metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
        assert "save_format" not in metrics
