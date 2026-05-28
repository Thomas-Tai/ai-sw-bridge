#!/usr/bin/env python3
"""Redact a spec.json for safe sharing (W3.3, privacy_review §4.4).

Strips proprietary information while preserving schema validity:

- ``{"rhs": "VAR_NAME"}`` → ``{"rhs": "<redacted>"}``
- ``feature.name`` → ``<feature_type>_<index>``
- File paths (``locals``) reduced to basenames
- ``_comment`` fields stripped entirely
- ``spec.name`` → ``redacted_spec``
- With ``--coarsen``: every numeric dimension rounded to nearest 10 mm

Usage::

    python tools/spec_redact.py examples/drive_roller/spec.json
    python tools/spec_redact.py examples/drive_roller/spec.json --coarsen
    python tools/spec_redact.py spec.json --output spec_redacted.json

Exit codes: 0 = success, 2 = input error.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


_COARSEN_STEP = 10  # mm


def _coarsen_number(v: float) -> float:
    """Round *v* to the nearest multiple of 10 mm (half-up).

    Zero stays zero. Uses floor-based rounding to avoid Python's
    banker's rounding (round(0.5) == 0).
    """
    if v == 0.0:
        return 0.0
    sign = 1.0 if v >= 0 else -1.0
    return sign * math.floor(abs(v) / _COARSEN_STEP + 0.5) * _COARSEN_STEP


def _redact_rhs(node: Any) -> Any:
    """Walk the spec tree and replace every ``{"rhs": "..."}`` value."""
    if isinstance(node, dict):
        if "rhs" in node and isinstance(node["rhs"], str):
            return {"rhs": "<redacted>"}
        return {k: _redact_rhs(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_redact_rhs(x) for x in node]
    return node


def _redact_names_v2(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace feature names and rewrite cross-references.

    Names use ``redact_<type>_<index>`` format to satisfy the schema's
    ``^[A-Za-z_][A-Za-z0-9_]*$`` name pattern.
    """
    old_names: list[str] = [f.get("name", "") for f in features]
    new_names: list[str] = []
    for i, feat in enumerate(features):
        ftype = feat.get("type", "unknown").replace("-", "_")
        new_names.append(f"redact_{ftype}_{i}")

    rename_map = dict(zip(old_names, new_names))

    for feat, new_name in zip(features, new_names):
        feat["name"] = new_name
        if "sketch" in feat and isinstance(feat["sketch"], str):
            feat["sketch"] = rename_map.get(feat["sketch"], feat["sketch"])
        if "of_feature" in feat and isinstance(feat["of_feature"], str):
            feat["of_feature"] = rename_map.get(feat["of_feature"], feat["of_feature"])

    return features


def _strip_comments(spec: dict[str, Any]) -> dict[str, Any]:
    """Remove ``_comment`` fields from the spec and all features."""
    spec.pop("_comment", None)
    for feat in spec.get("features", []):
        feat.pop("_comment", None)
    return spec


def _redact_paths(spec: dict[str, Any]) -> dict[str, Any]:
    """Reduce file paths to basenames."""
    if isinstance(spec.get("locals"), str):
        spec["locals"] = Path(spec["locals"]).name
    return spec


def _coarsen_numbers(node: Any) -> Any:
    """Walk the tree and round numeric values to nearest 10 mm.

    Preserves integers that are clearly not dimensions (schema_version,
    indices). Only rounds float values.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            # Don't coarsen schema_version or array indices
            if k in ("schema_version", "add2_index"):
                out[k] = v
            else:
                out[k] = _coarsen_numbers(v)
        return out
    if isinstance(node, list):
        return [_coarsen_numbers(x) for x in node]
    if isinstance(node, float):
        return _coarsen_number(node)
    return node


def redact_spec(spec: dict[str, Any], *, coarsen: bool = False) -> dict[str, Any]:
    """Produce a redacted copy of *spec*.

    The result is a valid spec (passes schema validation) with all
    proprietary information stripped:

    - ``rhs`` bindings → ``<redacted>``
    - Feature names → ``<type_index>``
    - Cross-references (sketch, of_feature) rewritten to match
    - ``_comment`` fields removed
    - File paths reduced to basenames
    - ``spec.name`` → ``redacted_spec``

    When *coarsen* is True, all float dimensions are rounded to the
    nearest 10 mm.
    """
    out = copy.deepcopy(spec)
    out = _strip_comments(out)
    out["name"] = "redacted_spec"
    out = _redact_paths(out)
    out = _redact_rhs(out)
    out["features"] = _redact_names_v2(out.get("features", []))
    if coarsen:
        out = _coarsen_numbers(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spec_redact",
        description=(
            "Redact a spec.json for safe sharing: strip rhs bindings, "
            "anonymize feature names, remove comments, and optionally "
            "coarsen dimensions to 10mm boundaries (W3.3)."
        ),
    )
    parser.add_argument("spec_path", help="Path to the spec JSON to redact.")
    parser.add_argument(
        "--coarsen",
        action="store_true",
        help="Round every numeric dimension to the nearest 10 mm.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=("Output path (default: <input>_redacted.json next to the input)."),
    )
    args = parser.parse_args(argv)

    spec_path = Path(args.spec_path)
    if not spec_path.exists():
        print(f"error: spec not found: {spec_path}", file=sys.stderr)
        return 2

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2

    redacted = redact_spec(spec, coarsen=args.coarsen)

    out_path = (
        Path(args.output)
        if args.output
        else spec_path.with_name(spec_path.stem + "_redacted.json")
    )
    out_path.write_text(json.dumps(redacted, indent=2) + "\n", encoding="utf-8")
    print(f"redacted spec written to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
