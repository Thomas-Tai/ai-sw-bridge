#!/usr/bin/env python
"""Emit the canonical published JSON Schema for the ai-sw-bridge part spec.

The stable, shipping spec surface is the v1 ``schema.SCHEMA`` (assembled from
the declarative descriptors). This tool serializes it to
``schema/ai-sw-bridge.spec.schema.json`` -- the standalone ``$schema`` file an
editor points at to get autocomplete and inline validation while authoring a
``spec.json`` (see ``docs/spec_reference.md`` for the editor wiring).

Usage::

    python tools/emit_spec_schema.py            # (re)write the published file
    python tools/emit_spec_schema.py --check    # CI/pre-commit: fail if stale

``--check`` is the sync gate: it re-renders from source and compares
byte-for-byte with the committed file, so the published schema can never drift
from ``schema.py`` unnoticed. The same guard also runs inside the pytest suite
(``tests/test_spec_schema_published.py``), mirroring the golden-fixture oracle
in ``tests/test_descriptor_schema_equivalence.py``.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_sw_bridge.spec.schema import SCHEMA  # noqa: E402  (needs sys.path above)

PUBLISHED_PATH = REPO_ROOT / "schema" / "ai-sw-bridge.spec.schema.json"

# Canonical identifier for the published schema. The repo is public, so this
# raw URL resolves; editors also accept a plain relative path (see the docs).
CANONICAL_ID = (
    "https://raw.githubusercontent.com/Thomas-Tai/ai-sw-bridge/"
    "master/schema/ai-sw-bridge.spec.schema.json"
)


def _allow_comment_keys(node: object) -> None:
    """Let ``_``-prefixed comment keys through every closed object, recursively.

    The validator strips ``_``-prefixed keys (``spec.validator._strip_comments``)
    *before* it checks a spec, so ``_comment`` annotations are legal anywhere,
    but ``additionalProperties: false`` in the raw schema would reject them. We
    model the real acceptance set by adding ``patternProperties: {"^_": {}}`` to
    every object that closes itself: a matched ``_*`` key then satisfies the
    object instead of tripping it, while genuinely-unknown keys are still
    rejected. This is an emit-time transform only; the in-memory ``SCHEMA`` the
    validator uses is untouched.
    """
    if isinstance(node, dict):
        if (
            node.get("additionalProperties") is False
            and "patternProperties" not in node
        ):
            node["patternProperties"] = {"^_": {}}
        for value in node.values():
            _allow_comment_keys(value)
    elif isinstance(node, list):
        for value in node:
            _allow_comment_keys(value)


def render() -> str:
    """Serialize the v1 spec schema exactly as it is published on disk.

    Applies the ``_``-comment transform, then injects a canonical ``$id`` (right
    after ``$schema``), all without mutating the in-memory ``SCHEMA`` the
    validator uses. Deterministic: the same source always yields byte-identical
    output (trailing newline included).
    """
    doc = copy.deepcopy(SCHEMA)
    _allow_comment_keys(doc)
    ordered = {"$schema": doc.pop("$schema"), "$id": CANONICAL_ID, **doc}
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit or verify the published spec JSON Schema."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 1) if the published file is missing or stale",
    )
    args = parser.parse_args(argv)

    rendered = render()
    rel = PUBLISHED_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not PUBLISHED_PATH.exists():
            print(
                f"MISSING: {rel} -- run: python tools/emit_spec_schema.py",
                file=sys.stderr,
            )
            return 1
        if PUBLISHED_PATH.read_text(encoding="utf-8") != rendered:
            print(
                f"STALE: {rel} drifted from schema.py -- "
                "run: python tools/emit_spec_schema.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel} is in sync with schema.py")
        return 0

    PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {rel} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
