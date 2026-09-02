#!/usr/bin/env python
"""Emit per-feature field tables in docs/spec_reference.md from the JSON Schema.

The published spec schema (``schema/ai-sw-bridge.spec.schema.json``) is the
source of truth for each feature type's fields. This tool renders those fields
as markdown tables and splices them into ``docs/spec_reference.md`` between
explicit markers::

    <!-- BEGIN GENERATED: boss_extrude_blind -->
    | Field | Type | Required | Default | Description |
    ...
    <!-- END GENERATED -->

Hand-written prose around each table is preserved. Adding a new primitive
requires a matching marker pair in the doc (the gate fails closed if one is
missing) so a type cannot silently go undocumented.

Usage::

    python tools/emit_spec_reference.py            # splice fresh tables
    python tools/emit_spec_reference.py --check    # CI/pre-commit: fail if stale

``--check`` is the sync gate: it re-renders from the published schema and
compares byte-for-byte with the committed doc. The same guard also runs inside
the pytest suite (``tests/test_spec_reference_published.py``), mirroring
``tools/emit_spec_schema.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"
DOC_PATH = REPO_ROOT / "docs" / "spec_reference.md"

BEGIN_PREFIX = "<!-- BEGIN GENERATED: "
END_MARKER = "<!-- END GENERATED -->"
_REGION_RE = re.compile(
    r"<!-- BEGIN GENERATED: ([a-z0-9_]+) -->.*?<!-- END GENERATED -->",
    re.DOTALL,
)


class MarkerError(ValueError):
    """Generated-region markers are missing, extra, or unknown."""


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Load the published spec JSON Schema."""
    target = path if path is not None else SCHEMA_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def feature_fragments(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each feature type name to its JSON-Schema fragment.

    Order follows the schema's ``oneOf`` (the published FEATURE_ORDER).
    """
    items = schema["properties"]["features"]["items"]["oneOf"]
    out: dict[str, dict[str, Any]] = {}
    for frag in items:
        name = frag["properties"]["type"]["const"]
        out[name] = frag
    return out


def _is_length(node: dict[str, Any]) -> bool:
    """True when *node* is LENGTH_SCHEMA (number mm | {rhs} object)."""
    alts = node.get("oneOf")
    if not isinstance(alts, list) or len(alts) != 2:
        return False
    kinds = {alt.get("type") for alt in alts}
    if kinds != {"number", "object"}:
        return False
    return any(
        isinstance(alt.get("properties"), dict) and "rhs" in alt["properties"]
        for alt in alts
    )


def _format_type(node: dict[str, Any]) -> str:
    if _is_length(node):
        return "length"
    if "const" in node:
        return f'const `"{node["const"]}"`'
    if "enum" in node:
        values = " / ".join(f'`"{v}"`' for v in node["enum"])
        return f"enum ({values})"
    t = node.get("type")
    if t == "array":
        extra = []
        if "minItems" in node:
            extra.append(f"min {node['minItems']}")
        if "maxItems" in node:
            extra.append(f"max {node['maxItems']}")
        return f"array ({', '.join(extra)})" if extra else "array"
    if t == "integer":
        if "minimum" in node:
            return f"integer (≥ {node['minimum']})"
        return "integer"
    if t in {"string", "boolean", "number", "object"}:
        return str(t)
    if "oneOf" in node:
        return "oneOf"
    return ""


def _format_default(value: object) -> str:
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, str):
        return f'`"{value}"`'
    return f"`{json.dumps(value)}`"


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def _cell(text: str) -> str:
    return _flatten(text) if text else ""


def render_fragment_table(fragment: dict[str, Any]) -> str:
    """Render one feature-type fragment as a markdown field table."""
    required = set(fragment.get("required") or [])
    properties: dict[str, Any] = fragment.get("properties") or {}
    lines = [
        "| Field | Type | Required | Default | Description |",
        "|---|---|---|---|---|",
    ]
    for name, node in properties.items():
        if not isinstance(node, dict):
            continue
        default = ""
        if "default" in node:
            default = _format_default(node["default"])
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{name}`",
                    _format_type(node),
                    "yes" if name in required else "no",
                    default,
                    _cell(str(node.get("description") or "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_tables(schema: dict[str, Any] | None = None) -> dict[str, str]:
    """Return ``{feature_type: markdown_table}`` for every schema fragment."""
    doc = schema if schema is not None else load_schema()
    return {
        name: render_fragment_table(frag)
        for name, frag in feature_fragments(doc).items()
    }


def render_feature_table(name: str, schema: dict[str, Any] | None = None) -> str:
    """Render the field table for one feature type (raises KeyError if unknown)."""
    tables = render_tables(schema)
    return tables[name]


def splice(doc: str, tables: dict[str, str]) -> str:
    """Replace every generated region in *doc* with the matching table.

    Raises ``MarkerError`` if a schema type has no region, or a region names a
    type that is not in *tables*. Surrounding prose is left untouched.
    """
    found: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        found.append(name)
        body = tables.get(name)
        if body is None:
            return match.group(0)
        return f"{BEGIN_PREFIX}{name} -->\n{body.rstrip()}\n{END_MARKER}"

    out = _REGION_RE.sub(_replace, doc)
    found_set = set(found)
    unknown = [n for n in found if n not in tables]
    # Preserve first-seen order for stable error messages.
    missing = [n for n in tables if n not in found_set]
    extra_dupes = [n for n in found_set if found.count(n) > 1]
    parts: list[str] = []
    if unknown:
        parts.append(
            "UNKNOWN generated region(s): " + ", ".join(dict.fromkeys(unknown))
        )
    if extra_dupes:
        parts.append("DUPLICATE generated region(s): " + ", ".join(sorted(extra_dupes)))
    if missing:
        parts.append("MISSING generated region(s): " + ", ".join(missing))
    if parts:
        raise MarkerError("; ".join(parts))
    return out


def render_document(
    doc: str | None = None, schema: dict[str, Any] | None = None
) -> str:
    """Return *doc* with every generated region refreshed from the schema."""
    text = doc if doc is not None else DOC_PATH.read_text(encoding="utf-8")
    return splice(text, render_tables(schema))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit or verify spec_reference.md field tables from the JSON Schema."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 1) if the committed doc is missing or stale",
    )
    args = parser.parse_args(argv)

    try:
        rel = DOC_PATH.relative_to(REPO_ROOT)
    except ValueError:
        rel = DOC_PATH
    if not SCHEMA_PATH.is_file():
        print(
            f"MISSING: {SCHEMA_PATH.relative_to(REPO_ROOT)} -- "
            "run: python tools/emit_spec_schema.py",
            file=sys.stderr,
        )
        return 1
    if not DOC_PATH.is_file():
        print(
            f"MISSING: {rel} -- run: python tools/emit_spec_reference.py",
            file=sys.stderr,
        )
        return 1

    current = DOC_PATH.read_text(encoding="utf-8")
    try:
        rendered = render_document(current)
    except MarkerError as exc:
        print(f"{rel}: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if current != rendered:
            print(
                f"STALE: {rel} drifted from the published JSON Schema -- "
                "run: python tools/emit_spec_reference.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel} field tables are in sync with the published JSON Schema")
        return 0

    if current != rendered:
        DOC_PATH.write_text(rendered, encoding="utf-8")
        print(f"wrote {rel} ({len(rendered)} bytes)")
    else:
        print(f"OK: {rel} already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
