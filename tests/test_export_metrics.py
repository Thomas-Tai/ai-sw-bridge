"""Tests for tools/export_metrics.py — --help, export function, consent gate."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from tools.export_metrics import export, main

_TOOLS_DIR = Path(__file__).resolve().parent.parent
_TOOL_PATH = _TOOLS_DIR / "tools" / "export_metrics.py"


@pytest.fixture
def telemetry_db(tmp_path):
    """Create a minimal telemetry SQLite database with the expected schema."""
    db_path = tmp_path / "telemetry.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE metrics ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "timestamp TEXT NOT NULL,"
        "metric_name TEXT NOT NULL,"
        "labels_json TEXT NOT NULL DEFAULT '{}',"
        "value REAL NOT NULL)"
    )
    conn.execute(
        "INSERT INTO metrics (timestamp, metric_name, labels_json, value) "
        "VALUES ('2026-05-27T00:00:00+00:00', 'builds_total', "
        '\'{"mode": "no_dim"}\', 1.0)'
    )
    conn.commit()
    conn.close()
    return db_path


class TestExportFunction:
    def test_export_returns_rows(self, telemetry_db):
        result = export(Path("out.json"), db_path=telemetry_db)
        assert result["row_count"] == 1
        assert len(result["rows"]) == 1
        row = result["rows"][0]
        assert row["metric_name"] == "builds_total"
        assert row["labels"] == {"mode": "no_dim"}
        assert row["value"] == 1.0

    def test_export_no_database(self, tmp_path):
        result = export(Path("out.json"), db_path=tmp_path / "nonexistent.sqlite")
        assert "error" in result
        assert result["rows"] == []

    def test_export_empty_database(self, tmp_path):
        db_path = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE metrics ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "timestamp TEXT NOT NULL,"
            "metric_name TEXT NOT NULL,"
            "labels_json TEXT NOT NULL DEFAULT '{}',"
            "value REAL NOT NULL)"
        )
        conn.commit()
        conn.close()
        result = export(Path("out.json"), db_path=db_path)
        assert result["row_count"] == 0


class TestHelpFlag:
    def test_help_prints_usage_and_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(_TOOL_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "usage:" in result.stdout
        assert "export_metrics" in result.stdout
        assert "output" in result.stdout

    def test_help_creates_no_side_effects(self, tmp_path):
        before = set(p.name for p in tmp_path.iterdir())
        subprocess.run(
            [sys.executable, str(_TOOL_PATH), "--help"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        after = set(p.name for p in tmp_path.iterdir())
        created = after - before
        json_files = [f for f in created if f.endswith(".json")]
        assert not json_files, f"--help created JSON files: {json_files}"
        assert "metrics_export.json" not in created
        assert "--help" not in created


class TestConsentGate:
    def test_refuses_without_consent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            main()

    def test_main_with_consent_and_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        consent_dir = tmp_path / ".telemetry"
        consent_dir.mkdir()
        (consent_dir / "consent.txt").write_text("consent", encoding="utf-8")

        db_path = tmp_path / "telemetry.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE metrics ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "timestamp TEXT NOT NULL,"
            "metric_name TEXT NOT NULL,"
            "labels_json TEXT NOT NULL DEFAULT '{}',"
            "value REAL NOT NULL)"
        )
        conn.commit()
        conn.close()

        output_path = tmp_path / "test_output.json"

        import tools.export_metrics as em

        monkeypatch.setattr(em, "_CONSENT_FILE", consent_dir / "consent.txt")
        monkeypatch.setattr(em, "_DB_PATH", db_path)
        main([str(output_path)])

        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert "row_count" in data
        assert "rows" in data
