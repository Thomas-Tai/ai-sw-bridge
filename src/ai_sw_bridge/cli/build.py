"""
ai-sw-build CLI entry point. Validates a v0.2 spec JSON, then builds it in
a fresh blank part on the running SOLIDWORKS session.

Usage:
    ai-sw-build <spec.json>            # validate + build
    ai-sw-build <spec.json> --validate-only   # validate, do not touch SW

Exits with non-zero status and prints a JSON error object on failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..spec import validate, ValidationError
from ..spec.builder import build


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2))
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-build",
        description="Build a SOLIDWORKS part from a declarative JSON spec.",
    )
    parser.add_argument("spec_path", help="Path to a part spec JSON")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run schema/refs/locals validation without touching SOLIDWORKS.",
    )
    args = parser.parse_args()

    p = Path(args.spec_path)
    if not p.exists():
        return _emit({"ok": False, "error": f"spec file not found: {p}"}, 2)

    try:
        spec = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _emit(
            {"ok": False, "error": f"spec is not valid JSON: {e}", "spec_path": str(p)},
            2,
        )

    try:
        validate(spec)
    except ValidationError as e:
        return _emit(
            {"ok": False, "error": "validation_failed", "path": e.path, "message": e.message},
            3,
        )

    if args.validate_only:
        return _emit({"ok": True, "validated": True, "feature_count": len(spec["features"])}, 0)

    result = build(spec)
    payload = {
        "ok": result.ok,
        "features_built": result.features_built,
        "bindings_added": [
            {"dim": d, "rhs": r, "add2_index": i} for d, r, i in result.bindings_added
        ],
    }
    if not result.ok:
        payload["error"] = result.error
        payload["error_feature"] = result.error_feature
        return _emit(payload, 4)
    return _emit(payload, 0)


if __name__ == "__main__":
    sys.exit(main())
