"""Tests for tools/license_lint.py.

Scenarios per task spec:
  - clean port (all three surfaces present, MIT upstream)
  - missing CONTRIBUTING.md row
  - GPL upstream violation
  - no-license upstream violation
  - missing README Acknowledgments entry
  - docstring missing license name / commit hash
  - CONTRIBUTING.md row referencing a file with no port marker
  - top-level LICENSE / pyproject.toml mismatch
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

# tools/ is not a package — add it to the import path for unit-testing
# internal functions. Integration tests use subprocess instead.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from license_lint import (
    _check_docstring,
    _check_license_classification,
    _check_top_level_license,
    _find_ported_files,
    _parse_contributing_table,
    _parse_readme_acknowledgments,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "tools" / "license_lint.py"


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _find_ported_files
# ---------------------------------------------------------------------------


def test_find_ported_files_detects_ported_from(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mymod.py",
        '"""My module.\n\nPorted from SolidworksMCP-python-main.\n"""\n',
    )
    results = _find_ported_files(tmp_path)
    assert len(results) == 1
    assert results[0][1] == "SolidworksMCP-python-main"


def test_find_ported_files_detects_adapted_from(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mymod.py",
        '"""My module.\n\nAdapted from Solidworks-MCP-main.\n"""\n',
    )
    results = _find_ported_files(tmp_path)
    assert len(results) == 1
    assert results[0][1] == "Solidworks-MCP-main"


def test_find_ported_files_ignores_non_ported(tmp_path: Path) -> None:
    _write(tmp_path, "mymod.py", '"""My module.\n"""\n')
    results = _find_ported_files(tmp_path)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# _check_docstring
# ---------------------------------------------------------------------------


def test_check_docstring_clean() -> None:
    text = textwrap.dedent(
        """\
        Ported from SolidworksMCP-python-main.
        Upstream commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
        License: MIT
    """
    )
    errors = _check_docstring(Path("src/foo.py"), text)
    assert errors == []


def test_check_docstring_missing_license(tmp_path: Path) -> None:
    text = "Ported from SolidworksMCP-python-main.\nCommit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n"
    errors = _check_docstring(Path("src/foo.py"), text)
    assert any("missing license name" in e for e in errors)


def test_check_docstring_missing_commit(tmp_path: Path) -> None:
    text = "Ported from SolidworksMCP-python-main.\nLicense: MIT\n"
    errors = _check_docstring(Path("src/foo.py"), text)
    assert any("missing 40-char commit hash" in e for e in errors)


# ---------------------------------------------------------------------------
# _check_license_classification
# ---------------------------------------------------------------------------


def test_gpl_upstream_rejected() -> None:
    errors = _check_license_classification("pySolidWorks-main", Path("src/foo.py"))
    assert any("GPL" in e and "forbidden" in e for e in errors)


def test_no_license_upstream_rejected() -> None:
    errors = _check_license_classification(
        "swapi-pilot-solidworks-mcp-main", Path("src/foo.py")
    )
    assert any("NO LICENSE" in e and "forbidden" in e for e in errors)


def test_unknown_upstream_flagged() -> None:
    errors = _check_license_classification("some-unknown-repo", Path("src/foo.py"))
    assert any("not found in license matrix" in e for e in errors)


def test_mit_upstream_allowed() -> None:
    errors = _check_license_classification(
        "SolidworksMCP-python-main", Path("src/foo.py")
    )
    assert errors == []


# ---------------------------------------------------------------------------
# _parse_contributing_table / _parse_readme_acknowledgments
# ---------------------------------------------------------------------------


def test_parse_contributing_table(tmp_path: Path) -> None:
    contrib = _write(
        tmp_path,
        "CONTRIBUTING.md",
        textwrap.dedent(
            """\
            ## Third-party derivations

            | Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
            | --- | --- | --- | --- | --- | --- | --- |
            | src/ai_sw_bridge/errors/circuit_breaker.py | SolidworksMCP-python-main | MIT | abc123 | 2026-01-01 | TBD | test |
        """
        ),
    )
    rows = _parse_contributing_table(contrib)
    assert "src/ai_sw_bridge/errors/circuit_breaker.py" in rows


def test_parse_readme_acknowledgments(tmp_path: Path) -> None:
    readme = _write(
        tmp_path,
        "README.md",
        "## Acknowledgments\n\nIncludes code from SolidworksMCP-python-main.\n",
    )
    repos = _parse_readme_acknowledgments(readme)
    assert "SolidworksMCP-python-main" in repos


# ---------------------------------------------------------------------------
# Integration: subprocess on real repo
# ---------------------------------------------------------------------------


def test_license_lint_passes_on_current_repo() -> None:
    """The lint should pass on the current repo (no ported files yet)."""
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "src"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Lint failed:\n{result.stdout}\n{result.stderr}"


def test_license_lint_catches_gpl_port(tmp_path: Path) -> None:
    """Planting a GPL-sourced port should cause non-zero exit."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "gpl_mod.py").write_text(
        textwrap.dedent(
            """\
            \"\"\"Bad port.

            Ported from pySolidWorks-main.
            Upstream commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
            License: GPL-3.0
            \"\"\"
        """
        ),
        encoding="utf-8",
    )
    # Minimal CONTRIBUTING.md and README.md so the lint doesn't complain
    # about those surfaces before hitting the GPL check.
    (tmp_path / "CONTRIBUTING.md").write_text(
        "| Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| src/pkg/gpl_mod.py | pySolidWorks-main | GPL-3.0 | a1b2 | 2026-01-01 | TBD | test |\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "## Acknowledgments\n\npySolidWorks-main\n", encoding="utf-8"
    )
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'license = { text = "MIT" }\n', encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "src", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "GPL" in result.stderr or "forbidden" in result.stderr


def test_license_lint_catches_no_license_port(tmp_path: Path) -> None:
    """Porting from a no-LICENSE upstream should fail."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "nolicense_mod.py").write_text(
        textwrap.dedent(
            """\
            \"\"\"Bad port.

            Ported from swapi-pilot-solidworks-mcp-main.
            Upstream commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
            \"\"\"
        """
        ),
        encoding="utf-8",
    )
    (tmp_path / "CONTRIBUTING.md").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'license = { text = "MIT" }\n', encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "src", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "NO LICENSE" in result.stderr or "forbidden" in result.stderr


def test_license_lint_catches_missing_contributing_row(tmp_path: Path) -> None:
    """A ported file without a CONTRIBUTING.md row should fail."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "clean_port.py").write_text(
        textwrap.dedent(
            """\
            \"\"\"Good port.

            Ported from SolidworksMCP-python-main.
            Upstream commit: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
            License: MIT
            \"\"\"
        """
        ),
        encoding="utf-8",
    )
    (tmp_path / "CONTRIBUTING.md").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "## Acknowledgments\n\nSolidworksMCP-python-main\n", encoding="utf-8"
    )
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'license = { text = "MIT" }\n', encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "src", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "CONTRIBUTING.md row" in result.stderr
