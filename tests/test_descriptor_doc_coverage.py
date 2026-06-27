"""X3 doc-coverage gate (FR-X-03, closes audit D-v0.14-05).

Every shipped primitive must stay documented and exemplified. Generated from
the descriptors so docs can't silently drift: for each of the 30 primitives,
this asserts it has descriptor metadata (doc + example_ref), the referenced
examples/<dir>/spec.json exists and actually uses that feature type, and the
type name appears in both docs/AGENTS.md and docs/spec_reference.md.

A new primitive that's added to the descriptors but not documented/exampled
fails here -- which is the point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.spec import builder, descriptors

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = (REPO_ROOT / "docs" / "AGENTS.md").read_text(encoding="utf-8")
SPEC_REF_MD = (REPO_ROOT / "docs" / "spec_reference.md").read_text(encoding="utf-8")

PRIMITIVES = descriptors.FEATURE_ORDER


def test_every_primitive_has_meta():
    assert set(descriptors.FEATURE_META) == set(PRIMITIVES)


@pytest.mark.parametrize("name", PRIMITIVES)
def test_primitive_has_doc_and_example_ref(name):
    meta = descriptors.FEATURE_META[name]
    assert meta.get("doc"), f"{name} has no doc one-liner"
    assert meta.get("example_ref"), f"{name} has no example_ref"


@pytest.mark.parametrize("name", PRIMITIVES)
def test_example_ref_exists_and_uses_the_type(name):
    example = descriptors.FEATURE_META[name]["example_ref"]
    spec_path = REPO_ROOT / "examples" / example / "spec.json"
    assert spec_path.is_file(), f"{name}: examples/{example}/spec.json missing"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    types = {f.get("type") for f in spec.get("features", [])}
    assert (
        name in types
    ), f"{name}: examples/{example} does not actually use feature type {name!r}"


@pytest.mark.parametrize("name", PRIMITIVES)
def test_primitive_documented_in_agents_and_spec_reference(name):
    assert name in AGENTS_MD, f"{name} not documented in docs/AGENTS.md"
    assert name in SPEC_REF_MD, f"{name} not documented in docs/spec_reference.md"


@pytest.mark.parametrize("name", PRIMITIVES)
def test_runtime_descriptor_carries_meta_and_fields(name):
    # _wire_handlers folds fields + metadata onto the live descriptor.
    desc = builder.DESCRIPTORS[name]
    assert desc.doc == descriptors.FEATURE_META[name]["doc"]
    assert desc.example_ref == descriptors.FEATURE_META[name]["example_ref"]
    assert desc.fields == descriptors.FEATURE_FIELDS[name]
    assert desc.handler is not None
