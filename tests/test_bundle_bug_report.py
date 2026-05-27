"""Tests for tools/bundle_bug_report.py — scrub, consent, zip integrity."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ai_sw_bridge.telemetry.scrub import redact_file_contents, redact_string
from tools.bundle_bug_report import bundle


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project structure with spec + locals."""
    spec_dir = tmp_path / "examples" / "test_part"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "TestPart",
                "features": [],
            }
        ),
        encoding="utf-8",
    )
    locals_file = spec_dir / "test_locals.txt"
    locals_file.write_text(
        '"PART_DIAMETER" = 50.0\n"S1B_HEIGHT" = 30.0\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def consent_file(project_dir):
    """Create .telemetry/consent.txt in project dir."""
    consent_dir = project_dir / ".telemetry"
    consent_dir.mkdir()
    (consent_dir / "consent.txt").write_text("consent", encoding="utf-8")
    return consent_dir / "consent.txt"


class TestScrub:
    def test_redact_locals_var(self):
        assert "S1B_" not in redact_string("value S1B_HEIGHT here")
        assert "<redacted_local>" in redact_string("value S1B_HEIGHT here")

    def test_redact_path(self):
        result = redact_string("path C:\\Users\\secret\\project\\file.txt end")
        assert "secret" not in result
        assert "file.txt" in result

    def test_locals_file_fully_redacted(self):
        content = '"PART_DIAMETER" = 50.0\n"S1B_HEIGHT" = 30.0\n'
        result = redact_file_contents(content, is_locals=True)
        assert result == "<redacted_locals>"

    def test_non_locals_file_partially_redacted(self):
        content = "var S1B_HEIGHT and path C:\\secret\\file.txt"
        result = redact_file_contents(content, is_locals=False)
        assert "<redacted_local>" in result
        assert "secret" not in result


class TestConsentGate:
    def test_refuses_without_consent(self, project_dir, monkeypatch):
        monkeypatch.chdir(project_dir)
        with pytest.raises(SystemExit):
            import tools.bundle_bug_report as bbr

            bbr.main()

    def test_bundle_with_no_telemetry_flag(self, project_dir, monkeypatch):
        monkeypatch.chdir(project_dir)
        zip_path = bundle(output_dir=project_dir, no_telemetry=True)
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "README.md" in names
            telemetry_files = [n for n in names if n.startswith("telemetry/")]
            assert len(telemetry_files) == 0

    def test_bundle_with_consent(self, project_dir, consent_file, monkeypatch):
        monkeypatch.chdir(project_dir)
        import tools.bundle_bug_report as bbr

        monkeypatch.setattr(bbr, "_CONSENT_FILE", consent_file)
        zip_path = bundle(output_dir=project_dir)
        assert zip_path.exists()


class TestZipIntegrity:
    def test_zip_contains_readme(self, project_dir, consent_file, monkeypatch):
        monkeypatch.chdir(project_dir)
        import tools.bundle_bug_report as bbr

        monkeypatch.setattr(bbr, "_CONSENT_FILE", consent_file)
        zip_path = bundle(output_dir=project_dir)
        with zipfile.ZipFile(zip_path) as zf:
            readme = zf.read("README.md").decode("utf-8")
            assert "Bug Report Bundle" in readme

    def test_zip_contains_spec(self, project_dir, consent_file, monkeypatch):
        monkeypatch.chdir(project_dir)
        import tools.bundle_bug_report as bbr

        monkeypatch.setattr(bbr, "_CONSENT_FILE", consent_file)
        zip_path = bundle(output_dir=project_dir)
        with zipfile.ZipFile(zip_path) as zf:
            spec_files = [n for n in zf.namelist() if n.startswith("specs/")]
            assert len(spec_files) >= 1
            content = zf.read(spec_files[0]).decode("utf-8")
            data = json.loads(content)
            assert data["name"] == "TestPart"

    def test_zip_locals_redacted(self, project_dir, consent_file, monkeypatch):
        monkeypatch.chdir(project_dir)
        import tools.bundle_bug_report as bbr

        monkeypatch.setattr(bbr, "_CONSENT_FILE", consent_file)
        zip_path = bundle(output_dir=project_dir)
        with zipfile.ZipFile(zip_path) as zf:
            locals_files = [n for n in zf.namelist() if n.startswith("locals/")]
            assert len(locals_files) >= 1
            content = zf.read(locals_files[0]).decode("utf-8")
            assert content == "<redacted_locals>"
