"""Documentation gate for the Industrial Design Intake tree.

Committed guarantees (spec 2026-07-07-industrial-design-intake-design.md,
section 13):

1. The tree contains every file the spec's section 7 promises (frozen to
   literals -- derive nothing from the tree being tested).
2. Every shipped CAD-ready summary validates against
   ``cad_ready_summary.schema.json`` -- and the schema demonstrably rejects
   invalid documents, so this gate cannot rot into always-green.
3. Every relative link in every intake Markdown file resolves on disk (the
   dead-link pattern from ``tests/test_i18n_staleness.py``).

Pure filesystem: no git, no SOLIDWORKS seat, safe on shallow checkouts.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_INTAKE = _ROOT / "docs" / "industrial_intake"
_TEMPLATES = _INTAKE / "templates"
_EXAMPLE = _INTAKE / "examples" / "automated_sorting_machine"

_SCHEMA_PATH = _TEMPLATES / "cad_ready_summary.schema.json"
_SUMMARY_PATHS = [
    _TEMPLATES / "cad_ready_summary.example.json",
    _EXAMPLE / "cad_ready_summary.json",
]

# The repository shape promised by spec section 7, frozen to literals
# (snapshot-mirror rule: derive nothing from the tree being tested).
_EXPECTED_FILES = [
    "README.md",
    "AGENTS.md",
    "workflow.md",
    "templates/idea_brief.md",
    "templates/requirements.md",
    "templates/engineering_specs.md",
    "templates/system_architecture.md",
    "templates/module_breakdown.md",
    "templates/calculations.md",
    "templates/cots_selection.md",
    "templates/top_down_cad_strategy.md",
    "templates/dfm_dfa_checklist.md",
    "templates/verification_plan.md",
    "templates/cad_ready_summary.schema.json",
    "templates/cad_ready_summary.example.json",
    "examples/automated_sorting_machine/idea_brief.md",
    "examples/automated_sorting_machine/requirements.md",
    "examples/automated_sorting_machine/engineering_specs.md",
    "examples/automated_sorting_machine/system_architecture.md",
    "examples/automated_sorting_machine/module_breakdown.md",
    "examples/automated_sorting_machine/calculations.md",
    "examples/automated_sorting_machine/cots_selection.md",
    "examples/automated_sorting_machine/top_down_cad_strategy.md",
    "examples/automated_sorting_machine/dfm_dfa_checklist.md",
    "examples/automated_sorting_machine/verification_plan.md",
    "examples/automated_sorting_machine/cad_ready_summary.json",
    "examples/automated_sorting_machine/solidworks_handoff.md",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_intake_tree_matches_spec_shape() -> None:
    missing = [rel for rel in _EXPECTED_FILES if not (_INTAKE / rel).is_file()]
    msg = f"intake files promised by spec section 7 are missing: {missing}"
    assert not missing, msg


@pytest.mark.parametrize("summary_path", _SUMMARY_PATHS, ids=lambda p: p.parent.name)
def test_summary_validates_against_schema(summary_path: Path) -> None:
    jsonschema.validate(_load(summary_path), _load(_SCHEMA_PATH))


def test_schema_rejects_unknown_readiness_state() -> None:
    doc = copy.deepcopy(_load(_SUMMARY_PATHS[0]))
    doc["readiness"]["state"] = "totally_ready"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _load(_SCHEMA_PATH))


def test_schema_rejects_unknown_top_level_key() -> None:
    doc = copy.deepcopy(_load(_SUMMARY_PATHS[0]))
    doc["solidworks_specifics"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _load(_SCHEMA_PATH))


def _relative_links(text: str) -> list[str]:
    # ](target) where target is not http(s), not an in-page #anchor, not a
    # mailto -- the same extraction as tests/test_i18n_staleness.py.
    links = re.findall(r"\]\(([^)]+)\)", text)
    out = []
    for t in links:
        t = t.split(" ", 1)[0].split("#", 1)[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(t)
    return out


def _dead_links(md_file: Path) -> list[str]:
    return [
        t
        for t in _relative_links(md_file.read_text(encoding="utf-8"))
        if not (md_file.parent / t).resolve().exists()
    ]


def test_no_dead_relative_links_in_intake_tree() -> None:
    dead = {
        str(p.relative_to(_ROOT)).replace("\\", "/"): links
        for p in sorted(_INTAKE.rglob("*.md"))
        if (links := _dead_links(p))
    }
    assert not dead, f"intake docs have dead relative links: {dead}"


def test_dead_link_detector_actually_detects(tmp_path: Path) -> None:
    bad = tmp_path / "doc.md"
    bad.write_text("see [missing](does_not_exist.md)", encoding="utf-8")
    assert _dead_links(bad) == ["does_not_exist.md"]
