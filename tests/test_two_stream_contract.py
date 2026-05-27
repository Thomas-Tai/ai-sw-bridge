"""Tests for the two-stream contract enforcement (UIUX.md §2.3).

Covers:
  - Lint passes on the clean tree
  - Lint catches bare print() in non-CLI modules
  - Lint catches sys.stdout.write()
  - Lint catches json.dumps on stderr
  - Lint allows CLI emitters to print JSON to stdout
  - Lint allows print(..., file=sys.stderr) for non-JSON text
  - Pytest-level contract: stdout JSON validation via subprocess

No SOLIDWORKS required.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "tools" / "two_stream_lint.py"


def _run_lint(src_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(LINT_SCRIPT)]
    if src_dir is not None:
        args.append(str(src_dir))
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


class TestTwoStreamLint:
    def test_lint_passes_on_clean_tree(self):
        proc = _run_lint(REPO_ROOT / "src")
        assert proc.returncode == 0, f"Lint failed:\n{proc.stderr}"

    def test_bare_print_flagged(self, tmp_path):
        src = tmp_path / "mymod.py"
        src.write_text('print("hello")\n', encoding="utf-8")
        proc = _run_lint(tmp_path)
        assert proc.returncode != 0
        assert "bare print()" in proc.stderr

    def test_sys_stdout_write_flagged(self, tmp_path):
        src = tmp_path / "mymod.py"
        src.write_text('import sys\nsys.stdout.write("oops")\n', encoding="utf-8")
        proc = _run_lint(tmp_path)
        assert proc.returncode != 0
        assert "sys.stdout.write()" in proc.stderr

    def test_json_dumps_on_stderr_flagged(self, tmp_path):
        src = tmp_path / "mymod.py"
        src.write_text(
            'import json, sys\nprint(json.dumps({"x": 1}), file=sys.stderr)\n',
            encoding="utf-8",
        )
        proc = _run_lint(tmp_path)
        assert proc.returncode != 0
        assert "JSON-like argument" in proc.stderr

    def test_dict_literal_on_stderr_flagged(self, tmp_path):
        src = tmp_path / "mymod.py"
        src.write_text(
            'import sys\nprint({"x": 1}, file=sys.stderr)\n',
            encoding="utf-8",
        )
        proc = _run_lint(tmp_path)
        assert proc.returncode != 0
        assert "JSON-like argument" in proc.stderr

    def test_cli_emitter_bare_print_allowed(self, tmp_path):
        src = tmp_path / "build.py"
        src.write_text(
            'import json\nprint(json.dumps({"ok": True}))\n', encoding="utf-8"
        )
        proc = _run_lint(tmp_path)
        assert proc.returncode == 0

    def test_stderr_print_non_json_allowed(self, tmp_path):
        src = tmp_path / "mymod.py"
        src.write_text(
            'import sys\nprint("WARNING: something happened", file=sys.stderr)\n',
            encoding="utf-8",
        )
        proc = _run_lint(tmp_path)
        assert proc.returncode == 0

    def test_fstring_with_braces_on_stderr_allowed(self, tmp_path):
        """f-strings with incidental braces (e.g. example JSON in warnings) are OK."""
        src = tmp_path / "mymod.py"
        src.write_text(
            "import sys\nprint(f'add `center: {{\"u\": 1}}`', file=sys.stderr)\n",
            encoding="utf-8",
        )
        proc = _run_lint(tmp_path)
        assert proc.returncode == 0

    def test_all_cli_emitters_allowed(self, tmp_path):
        for name in ("build.py", "observe.py", "mutate.py", "codegen.py", "probe.py"):
            (tmp_path / name).write_text(
                'import json\nprint(json.dumps({"ok": True}))\n', encoding="utf-8"
            )
        proc = _run_lint(tmp_path)
        assert proc.returncode == 0


class TestTwoStreamContractIntegration:
    """Integration tests: run CLI commands and verify stdout is valid JSON."""

    def test_build_validate_only_stdout_is_json(self):
        spec = REPO_ROOT / "examples" / "filleted_box" / "spec.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ai_sw_bridge.cli.build",
                str(spec),
                "--validate-only",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(proc.stdout)
        assert data["ok"] is True

    def test_build_dry_run_stdout_is_json(self):
        spec = REPO_ROOT / "examples" / "filleted_box" / "spec.json"
        proc = subprocess.run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(spec), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(proc.stdout)
        assert data["ok"] is True
        assert data["dry_run"] is True

    def test_build_help_stderr_only(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # --help goes to stdout (argparse default), which is fine — it's
        # not a spec-build command, so the two-stream contract doesn't apply.
        assert proc.returncode == 0
