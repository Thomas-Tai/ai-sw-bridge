#!/usr/bin/env python3
"""Doc-coverage gate: every type in schema.ALL_TYPES must have a section in spec_reference.md.

Exit 0 if all types are documented, 1 otherwise. Prints a diff-style report.
Run from the repo root: python tools/doc_coverage_gate.py
"""

from __future__ import annotations

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


def main() -> int:
    spec_ref = REPO_ROOT / "docs" / "spec_reference.md"
    if not spec_ref.exists():
        print(f"FAIL: {spec_ref} not found", file=sys.stderr)
        return 1

    documented = _documented_types(spec_ref)
    schema = _schema_types()

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
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
