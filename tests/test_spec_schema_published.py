"""Sync gate for the published standalone spec JSON Schema.

The editor-facing ``$schema`` file (autocomplete + inline validation for
``spec.json`` authoring) is a *serialization* of the v1 ``schema.SCHEMA`` and
must never drift from it. It is committed in two byte-identical copies, both
generated from one ``emit_spec_schema.render()``:

* ``schema/ai-sw-bridge.spec.schema.json`` -- repo-root canonical (the ``$id``);
* ``src/ai_sw_bridge/schema/ai-sw-bridge.spec.schema.json`` -- the in-wheel copy
  a pip install resolves via ``ai_sw_bridge.spec.published_schema_path()``.

These tests are the enforced CI gate:

1. both copies stay byte-identical to ``render()`` (hence to each other);
2. the resolver resolves to the packaged copy;
3. the published schema is itself a valid Draft 2020-12 schema;
4. every canonical example spec validates against it.

Regenerate both copies after an intentional schema change with::

    python tools/emit_spec_schema.py

(mirrors the golden-fixture oracle in ``test_descriptor_schema_equivalence.py``.)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_sw_bridge.spec import published_schema_path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PUBLISHED = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
_PACKAGED = (
    _REPO_ROOT / "src" / "ai_sw_bridge" / "schema" / "ai-sw-bridge.spec.schema.json"
)
_COPIES = [_PUBLISHED, _PACKAGED]
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


@pytest.mark.parametrize("copy_path", _COPIES, ids=["repo_root", "packaged"])
def test_published_schema_in_sync(copy_path: Path) -> None:
    """Each committed copy equals the tool's render() byte-for-byte."""
    emit = _load_emit_tool()
    assert copy_path.read_text(encoding="utf-8") == emit.render(), (
        f"{copy_path.relative_to(_REPO_ROOT)} drifted from schema.py -- "
        "regenerate: python tools/emit_spec_schema.py"
    )


def test_resolver_points_at_packaged_copy() -> None:
    """published_schema_path() resolves to the in-wheel copy on disk."""
    resolved = published_schema_path()
    assert resolved.is_file(), f"{resolved} does not exist"
    assert resolved.read_text(encoding="utf-8") == _PACKAGED.read_text(
        encoding="utf-8"
    ), "resolver returned a file that differs from the committed packaged copy"


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
