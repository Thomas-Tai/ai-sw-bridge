"""Sync gate for the generated per-feature tables in spec_reference.md.

The field tables in ``docs/spec_reference.md`` are a *serialization* of the
published spec JSON Schema and must never drift from it. They live inside
explicit ``<!-- BEGIN GENERATED: <type> -->`` / ``<!-- END GENERATED -->``
markers so the surrounding hand-written prose survives regeneration.

These tests are the enforced CI gate (same shape as
``tests/test_spec_schema_published.py``):

1. the committed doc equals ``emit_spec_reference.render_document()``;
2. every schema feature type has a generated region.

Regenerate after an intentional schema change with::

    python tools/emit_spec_reference.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC = _REPO_ROOT / "docs" / "spec_reference.md"
_SCHEMA = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"


def _load_emit_tool():
    spec = importlib.util.spec_from_file_location(
        "emit_spec_reference", _REPO_ROOT / "tools" / "emit_spec_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_types() -> list[str]:
    doc = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    return [
        frag["properties"]["type"]["const"]
        for frag in doc["properties"]["features"]["items"]["oneOf"]
    ]


def test_spec_reference_tables_in_sync() -> None:
    """Committed spec_reference.md equals a fresh splice of schema tables."""
    emit = _load_emit_tool()
    committed = _DOC.read_text(encoding="utf-8")
    assert committed == emit.render_document(committed), (
        "docs/spec_reference.md generated tables drifted from the published "
        "JSON Schema -- regenerate: python tools/emit_spec_reference.py"
    )


def test_every_schema_type_has_a_generated_region() -> None:
    """A new schema primitive without markers must fail the gate."""
    text = _DOC.read_text(encoding="utf-8")
    types = _schema_types()
    assert types, "published schema has no feature types -- glob/path broke"
    missing = [
        name
        for name in types
        if f"<!-- BEGIN GENERATED: {name} -->" not in text
        or "<!-- END GENERATED -->" not in text
    ]
    assert not missing, (
        "schema types with no generated region in docs/spec_reference.md: "
        + ", ".join(missing)
        + " -- add markers and run: python tools/emit_spec_reference.py"
    )
