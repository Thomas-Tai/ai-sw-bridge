"""Unit tests for tools/emit_spec_reference.py.

The per-feature field tables in docs/spec_reference.md are generated from the
published JSON Schema. These tests pin the renderer, the marker-splice, and
the --check gate without touching the committed doc.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_emit():
    spec = importlib.util.spec_from_file_location(
        "emit_spec_reference", _REPO_ROOT / "tools" / "emit_spec_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def emit():
    return _load_emit()


def test_render_table_includes_schema_fields_missing_from_hand_docs(emit) -> None:
    """boss_extrude_blind grew start_offset / flip_start_offset / merge in
    schema; the hand table never did. The generator must surface them."""
    table = emit.render_feature_table("boss_extrude_blind")
    assert "`start_offset`" in table
    assert "`flip_start_offset`" in table
    assert "`merge`" in table
    assert "`depth`" in table
    assert "`flip`" in table


def test_render_table_columns_and_defaults(emit) -> None:
    table = emit.render_feature_table("boss_extrude_blind")
    header = table.splitlines()[0]
    assert header.startswith("| Field | Type | Required | Default | Description |")
    # flip defaults to false; merge defaults to true (schema).
    assert "| `flip` |" in table
    assert "`false`" in table
    assert "`true`" in table
    # required vs optional
    assert "| `depth` | length | yes |" in table
    assert "| `start_offset` | length | no |" in table


def test_length_type_detected_for_rhs_union(emit) -> None:
    table = emit.render_feature_table("boss_extrude_blind")
    assert "| `depth` | length |" in table
    assert "| `start_offset` | length |" in table


def test_enum_and_const_types(emit) -> None:
    table = emit.render_feature_table("mirror_feature")
    assert 'const `"mirror_feature"`' in table
    assert '`"Front"`' in table
    assert '`"Top"`' in table
    assert '`"Right"`' in table
    assert "| `seed` | string | yes |" in table


def test_schema_description_is_copied(emit) -> None:
    table = emit.render_feature_table("mirror_feature")
    assert "Name of an earlier feature to mirror." in table
    # plane description is the schema's, not the hand-written paraphrase
    assert "Default reference plane to mirror about." in table


def test_center_description_is_schema_sketch_local(emit) -> None:
    """The schema (not the example comment) is what the table must say."""
    table = emit.render_feature_table("sketch_rectangle_on_plane")
    assert "Sketch-local center (mm)" in table
    assert "`center`" in table
    assert "`centerline`" in table
    assert "`relations`" in table


def test_splice_replaces_region_and_preserves_prose(emit) -> None:
    doc = (
        "### `mirror_feature`\n"
        "\n"
        "Hand-written intro.\n"
        "\n"
        "<!-- BEGIN GENERATED: mirror_feature -->\n"
        "OLD TABLE\n"
        "<!-- END GENERATED -->\n"
        "\n"
        "Hand-written outro.\n"
    )
    tables = {"mirror_feature": "| Field | Type |\n|---|---|\n"}
    out = emit.splice(doc, tables)
    assert "Hand-written intro." in out
    assert "Hand-written outro." in out
    assert "OLD TABLE" not in out
    assert "| Field | Type |" in out
    assert "<!-- BEGIN GENERATED: mirror_feature -->" in out
    assert "<!-- END GENERATED -->" in out


def test_splice_fails_when_a_type_has_no_marker(emit) -> None:
    doc = "no markers here\n"
    with pytest.raises(emit.MarkerError, match="MISSING"):
        emit.splice(doc, {"mirror_feature": "x\n"})


def test_splice_fails_on_unknown_marker(emit) -> None:
    doc = "<!-- BEGIN GENERATED: not_a_real_type -->\n" "x\n" "<!-- END GENERATED -->\n"
    with pytest.raises(emit.MarkerError, match="UNKNOWN"):
        emit.splice(doc, {"mirror_feature": "x\n"})


def test_check_fails_on_stale_table(emit, tmp_path: Path, monkeypatch) -> None:
    schema = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
    monkeypatch.setattr(emit, "SCHEMA_PATH", schema)
    doc = tmp_path / "spec_reference.md"
    # Wrap every schema type so splice can succeed, but put a stale body in one.
    tables = emit.render_tables()
    parts = ["# Spec\n"]
    for name, body in tables.items():
        stale = "STALE\n" if name == "boss_extrude_blind" else body
        parts.append(
            f"<!-- BEGIN GENERATED: {name} -->\n{stale}<!-- END GENERATED -->\n"
        )
    doc.write_text("".join(parts), encoding="utf-8")
    monkeypatch.setattr(emit, "DOC_PATH", doc)
    assert emit.main(["--check"]) == 1


def test_check_ok_when_in_sync(emit, tmp_path: Path, monkeypatch) -> None:
    schema = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
    monkeypatch.setattr(emit, "SCHEMA_PATH", schema)
    doc = tmp_path / "spec_reference.md"
    tables = emit.render_tables()
    parts = ["# Spec\n"]
    for name, body in tables.items():
        parts.append(
            f"<!-- BEGIN GENERATED: {name} -->\n{body}<!-- END GENERATED -->\n"
        )
    doc.write_text("".join(parts), encoding="utf-8")
    monkeypatch.setattr(emit, "DOC_PATH", doc)
    assert emit.main(["--check"]) == 0


def test_write_refreshes_stale_table(emit, tmp_path: Path, monkeypatch) -> None:
    schema = _REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
    monkeypatch.setattr(emit, "SCHEMA_PATH", schema)
    doc = tmp_path / "spec_reference.md"
    tables = emit.render_tables()
    parts = ["# Spec\n"]
    for name, body in tables.items():
        stale = "STALE\n" if name == "mirror_feature" else body
        parts.append(
            f"<!-- BEGIN GENERATED: {name} -->\n{stale}<!-- END GENERATED -->\n"
        )
    doc.write_text("".join(parts), encoding="utf-8")
    monkeypatch.setattr(emit, "DOC_PATH", doc)
    assert emit.main([]) == 0
    assert emit.main(["--check"]) == 0
    text = doc.read_text(encoding="utf-8")
    assert "STALE" not in text
    assert "<!-- BEGIN GENERATED: mirror_feature -->" in text
    assert 'const `"mirror_feature"`' in text
    assert "# Spec\n" in text
