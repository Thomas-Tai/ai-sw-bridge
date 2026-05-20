"""
ai-sw-build CLI entry point. Validates a v0.2 spec JSON, then builds it in
a fresh blank part on the running SOLIDWORKS session.

Usage:
    ai-sw-build <spec.json>                # parametric mode (default): inline AddDimension2 popups interleaved with build
    ai-sw-build <spec.json> --deferred-dim # geometry first (no popups), then batched popup-ticking at end; keeps live equation link
    ai-sw-build <spec.json> --no-dim       # resolve rhs upfront, zero popups, no equation links
    ai-sw-build <spec.json> --validate-only

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
    parser.add_argument(
        "--no-dim",
        action="store_true",
        help=(
            "Resolve every {rhs} reference against spec['locals'] in Python "
            "upfront, then build geometry at literal target sizes -- no "
            "AddDimension2 calls, no equation links. Eliminates the Modify-"
            "Dimension popup toll on SW 2024 SP1 (~16 manual ticks per MMP "
            "build). Trade-off: the resulting SLDPRT has no link back to "
            "locals.txt; editing locals requires re-running ai-sw-build."
        ),
    )
    parser.add_argument(
        "--deferred-dim",
        dest="deferred_dim",
        action="store_true",
        help=(
            "Build all geometry FIRST with zero AddDimension2 calls (Phase 1), "
            "then re-enter each sketch in turn and replay the AddDimension2 "
            "calls in a contiguous batch at the end (Phase 2). The user ticks "
            "N popups in a row rather than having them interleaved through "
            "a multi-minute build. The resulting SLDPRT retains the live "
            "equation link to locals.txt -- same as default parametric mode. "
            "Mutually exclusive with --no-dim. Verified by Spikes Z1/Z3/Z4."
        ),
    )
    parser.add_argument(
        "--save-as",
        dest="save_as",
        default=None,
        help=(
            "Absolute path to save the built part to via SaveAs3 after the "
            "build completes. Missing parent dirs are created; '.sldprt' is "
            "appended if absent. NOTE: in non-no_dim mode the build still "
            "blocks on AddDimension2 popups -- tick those before SaveAs3 "
            "fires. Combine with --no-dim to save without any popups."
        ),
    )
    args = parser.parse_args()

    # Mode conflict check runs before anything else so --validate-only
    # doesn't mask a misuse of flags.
    if args.no_dim and args.deferred_dim:
        return _emit(
            {
                "ok": False,
                "error": "--no-dim and --deferred-dim are mutually exclusive",
            },
            2,
        )

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
            {
                "ok": False,
                "error": "validation_failed",
                "path": e.path,
                "message": e.message,
            },
            3,
        )

    if args.validate_only:
        return _emit(
            {"ok": True, "validated": True, "feature_count": len(spec["features"])}, 0
        )

    result = build(
        spec,
        no_dim=args.no_dim,
        deferred_dim=args.deferred_dim,
        save_as=args.save_as,
    )
    # BuildResult.to_dict() owns the wire format; CLI only adds CLI-level
    # context (here: which mode the caller picked).
    payload = result.to_dict()
    payload["no_dim"] = args.no_dim
    payload["deferred_dim"] = args.deferred_dim
    return _emit(payload, 0 if result.ok else 4)


if __name__ == "__main__":
    sys.exit(main())
