"""Test for tools/doc_coverage_gate.py."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "tools" / "doc_coverage_gate.py"

# Make `import doc_coverage_gate` work when this file runs as a subset, not
# only when an alphabetically-earlier test module has already put tools/ on
# sys.path as a collection side effect.
_TOOLS = REPO_ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def test_doc_coverage_passes() -> None:
    """The doc coverage gate should pass on the current repo."""
    # Run the gate with the interpreter running the tests, so this works on
    # CI (no .venv-freshtest there) as well as locally.
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (
        result.returncode == 0
    ), f"Doc coverage gate failed:\n{result.stdout}\n{result.stderr}"


def _run_gate() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=15,
    )


class TestAgentsMdDrift:
    """Drift scenarios for check_agents_md_drift() assertions."""

    def test_missing_from_agents_md(self, tmp_path, monkeypatch):
        """A schema type not in AGENTS.md triggers a MISSING message."""
        import doc_coverage_gate as gate

        monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
        agents_md = tmp_path / "docs" / "agents.md"
        agents_md.parent.mkdir(parents=True, exist_ok=True)
        agents_md.write_text("No feature types here.\n", encoding="utf-8")
        # Create stub examples/ and spec_reference.md so assertions (b)/(c) pass
        examples = tmp_path / "examples" / "stub"
        examples.mkdir(parents=True)
        (examples / "spec.json").write_text(
            json.dumps({"features": [{"type": "fake_type"}]}), encoding="utf-8"
        )
        spec_ref = tmp_path / "docs" / "spec_reference.md"
        spec_ref.write_text("### `fake_type`\n", encoding="utf-8")

        ok = gate.check_agents_md_drift({"fake_type"})
        assert ok is False

    def test_missing_from_examples(self, tmp_path, monkeypatch):
        """A schema type with zero example specs triggers a MISSING message."""
        import doc_coverage_gate as gate

        monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
        agents_md = tmp_path / "docs" / "agents.md"
        agents_md.parent.mkdir(parents=True, exist_ok=True)
        agents_md.write_text("`fake_type` is here\n", encoding="utf-8")
        # Empty examples/
        (tmp_path / "examples").mkdir(exist_ok=True)
        spec_ref = tmp_path / "docs" / "spec_reference.md"
        spec_ref.write_text("### `fake_type`\n", encoding="utf-8")

        ok = gate.check_agents_md_drift({"fake_type"})
        assert ok is False

    def test_missing_from_spec_reference(self, tmp_path, monkeypatch):
        """A schema type with no spec_reference.md heading triggers a MISSING message."""
        import doc_coverage_gate as gate

        monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
        agents_md = tmp_path / "docs" / "agents.md"
        agents_md.parent.mkdir(parents=True, exist_ok=True)
        agents_md.write_text("`fake_type` is here\n", encoding="utf-8")
        examples = tmp_path / "examples" / "stub"
        examples.mkdir(parents=True)
        (examples / "spec.json").write_text(
            json.dumps({"features": [{"type": "fake_type"}]}), encoding="utf-8"
        )
        spec_ref = tmp_path / "docs" / "spec_reference.md"
        spec_ref.write_text("No headings here\n", encoding="utf-8")

        ok = gate.check_agents_md_drift({"fake_type"})
        assert ok is False
