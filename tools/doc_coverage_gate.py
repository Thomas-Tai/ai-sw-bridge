#!/usr/bin/env python3
"""Doc-coverage gate: every schema.ALL_TYPES feature type must have a
section heading in docs/spec_reference.md, be listed in AGENTS.md's
feature-type table, and have at least one example spec under examples/.

Exit 0 if all checks pass, 1 otherwise. Prints a diff-style report.
Run from the repo root: python tools/doc_coverage_gate.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _documented_types(spec_ref: Path) -> set[str]:
    """Extract feature type names that have ### headings in spec_reference.md."""
    text = spec_ref.read_text(encoding="utf-8")
    return set(re.findall(r"^### `(\w+)`", text, re.MULTILINE))


def _schema_types() -> set[str]:
    """Import ALL_TYPES from the schema module."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from ai_sw_bridge.spec.schema import ALL_TYPES

    return set(ALL_TYPES)


def _agents_md_types(agents_md: Path) -> set[str]:
    """Extract feature type names listed in AGENTS.md's feature-type table.

    Matches table rows containing snake_case feature type names
    (e.g. ``sketch_rectangle_on_plane``).
    """
    text = agents_md.read_text(encoding="utf-8")
    return set(re.findall(r"`(sketch_\w+|boss_\w+|cut_\w+|revolve_\w+|fillet_\w+|chamfer_\w+|simple_\w+|linear_\w+|circular_\w+|mirror_\w+)`", text))


def _example_spec_types() -> set[str]:
    """Collect all feature types referenced in examples/**/*.json specs."""
    types: set[str] = set()
    examples_dir = REPO_ROOT / "examples"
    if not examples_dir.exists():
        return types
    for spec_path in examples_dir.rglob("spec.json"):
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for feat in spec.get("features", []):
            feat_type = feat.get("type", "")
            if feat_type:
                types.add(feat_type)
    return types


def check_spec_reference_drift(schema: set[str]) -> bool:
    """Check spec_reference.md covers all schema types. Returns True if OK."""
    spec_ref = REPO_ROOT / "docs" / "spec_reference.md"
    if not spec_ref.exists():
        print(f"FAIL: {spec_ref} not found", file=sys.stderr)
        return False

    documented = _documented_types(spec_ref)
    missing = schema - documented
    extra = documented - schema

    ok = True
    if missing:
        ok = False
        print("MISSING from spec_reference.md (in schema but not documented):")
        for t in sorted(missing):
            print(f"  - {t}")
    if extra:
        print("EXTRA in spec_reference.md (documented but not in schema):")
        for t in sorted(extra):
            print(f"  - {t}")

    if ok:
        print(f"OK: all {len(schema)} schema types documented in spec_reference.md")
    return ok


def check_agents_md_drift(schema: set[str]) -> bool:
    """Check AGENTS.md, examples/, and spec_reference.md against schema.

    Assertion (a): every schema type appears in AGENTS.md.
    Assertion (b): every schema type has at least one example spec.
    Assertion (c): every schema type has a section heading in spec_reference.md.
    """
    ok = True

    # Assertion (a) — AGENTS.md
    agents_md = REPO_ROOT / "docs" / "agents.md"
    if agents_md.exists():
        agents_types = _agents_md_types(agents_md)
        missing_agents = schema - agents_types
        if missing_agents:
            ok = False
            print("MISSING from AGENTS.md (schema type not in feature-type table):")
            for t in sorted(missing_agents):
                print(f"  - {t}")
        else:
            print(f"OK: all {len(schema)} schema types listed in AGENTS.md")
    else:
        print(f"WARN: {agents_md} not found, skipping AGENTS.md check", file=sys.stderr)

    # Assertion (b) — examples/
    example_types = _example_spec_types()
    missing_examples = schema - example_types
    if missing_examples:
        ok = False
        print("MISSING from examples/ (schema type with zero example specs):")
        for t in sorted(missing_examples):
            print(f"  - {t}")
    else:
        print(f"OK: all {len(schema)} schema types have at least one example spec")

    # Assertion (c) — spec_reference.md
    spec_ref = REPO_ROOT / "docs" / "spec_reference.md"
    if spec_ref.exists():
        documented = _documented_types(spec_ref)
        missing_docs = schema - documented
        if missing_docs:
            ok = False
            print("MISSING from spec_reference.md (schema type has no section heading):")
            for t in sorted(missing_docs):
                print(f"  - {t}")
        else:
            print(f"OK: all {len(schema)} schema types have spec_reference.md headings")
    else:
        print(f"WARN: {spec_ref} not found, skipping spec_reference.md check", file=sys.stderr)

    return ok


def main() -> int:
    schema = _schema_types()
    if not schema:
        print("FAIL: could not load ALL_TYPES from schema", file=sys.stderr)
        return 1

    ok_a = check_spec_reference_drift(schema)
    ok_b = check_agents_md_drift(schema)

    if ok_a and ok_b:
        print(f"\nALL CHECKS PASSED ({len(schema)} schema types)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
