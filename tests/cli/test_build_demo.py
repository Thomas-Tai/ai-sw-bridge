"""ai-sw-build --demo builds the bundled example on any install (B1 fix).

The operator quickstart used to say `ai-sw-build examples/filleted_box/spec.json`,
but examples/ lives at the repo root and is NOT packaged into the wheel -- so on
pipx / .exe installs (no clone) the very first "does it work?" command errored
file-not-found. `--demo` reads the spec from package data instead, so it works
everywhere. These tests are COM-free (validate/dry-run only; no SOLIDWORKS).

See docs/operator_experience_audit_2026-07-04.md (B1).
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge.cli import build as build_cli

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bundled_demo_matches_root_example() -> None:
    """Drift guard: the packaged demo spec must equal the repo-root example.

    Two copies exist (root examples/ for cloners to browse; src/ package data
    for --demo). Pin them semantically identical so they cannot drift apart.
    """
    bundled = json.loads(build_cli._read_demo_spec())
    root = json.loads(
        (_REPO_ROOT / "examples" / "filleted_box" / "spec.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundled == root


def test_read_demo_spec_is_valid_three_feature_spec() -> None:
    spec = json.loads(build_cli._read_demo_spec())
    assert spec["schema_version"] == 1
    assert len(spec["features"]) == 3


def test_demo_validate_only_exits_zero(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["ai-sw-build", "--demo", "--validate-only"])
    rc = build_cli.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["validated"] is True
    assert payload["feature_count"] == 3


def test_demo_dry_run_reports_three_features(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["ai-sw-build", "--demo", "--dry-run"])
    rc = build_cli.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["feature_count"] == 3


def test_demo_with_spec_path_is_rejected(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["ai-sw-build", "--demo", "some_spec.json", "--validate-only"]
    )
    rc = build_cli.main()
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "--demo" in payload["error"]
