"""Sync gate for the published standalone spec JSON Schema.

``schema/ai-sw-bridge.spec.schema.json`` is the editor-facing ``$schema`` file
(autocomplete + inline validation for ``spec.json`` authoring). It is a
*serialization* of the v1 ``schema.SCHEMA`` and must never drift from it. These
tests are the enforced CI gate:

1. it stays byte-identical to ``tools/emit_spec_schema.render()``;
2. it is itself a valid Draft 2020-12 schema;
3. every canonical example spec validates against it.

Regenerate the published file after an intentional schema change with::

    python tools/emit_spec_schema.py

(mirrors the golden-fixture oracle in ``test_descriptor_schema_equivalence.py``.)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PUBLISHED = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
_EXAMPLES = sorted((_REPO_ROOT / "examples").rglob("spec.json"))


def _load_emit_tool():
    """Import ``tools/emit_spec_schema.py`` (it lives off the package path)."""
    spec = importlib.util.spec_from_file_location(
        "emit_spec_schema", _REPO_ROOT / "tools" / "emit_spec_schema.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_published_schema_in_sync() -> None:
    """The committed file equals the tool's render() byte-for-byte."""
    emit = _load_emit_tool()
    assert _PUBLISHED.read_text(encoding="utf-8") == emit.render(), (
        "schema/ai-sw-bridge.spec.schema.json drifted from schema.py -- "
        "regenerate: python tools/emit_spec_schema.py"
    )


def test_published_schema_is_valid_metaschema() -> None:
    """The published schema is itself a valid Draft 2020-12 schema."""
    doc = json.loads(_PUBLISHED.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(doc)


def test_examples_are_present() -> None:
    """Guard against the glob silently matching nothing."""
    assert _EXAMPLES, "no examples/**/spec.json found -- validation coverage lost"


@pytest.mark.parametrize("spec_path", _EXAMPLES, ids=lambda p: p.parent.name)
def test_example_validates_against_published_schema(spec_path: Path) -> None:
    """Every canonical example spec validates against the published schema."""
    doc = json.loads(_PUBLISHED.read_text(encoding="utf-8"))
    validator = Draft202012Validator(doc)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
    assert not errors, (
        f"{spec_path.relative_to(_REPO_ROOT)} does not validate against the "
        "published schema: " + "; ".join(e.message for e in errors[:3])
    )
