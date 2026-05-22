"""
ai-sw-build CLI entry point. Validates a v0.2 spec JSON, then builds it in
a fresh blank part on the running SOLIDWORKS session.

Usage:
    ai-sw-build <spec.json>                # parametric mode (default): inline AddDimension2 popups interleaved with build
    ai-sw-build <spec.json> --deferred-dim # geometry first (no popups), then batched popup-ticking at end; keeps live equation link
    ai-sw-build <spec.json> --no-dim       # resolve rhs upfront, zero popups, no equation links
    ai-sw-build <spec.json> --validate-only
    ai-sw-build <spec.json> --dry-run      # validate + resolve locals + dump planned feature list; never touches SW

Exits with non-zero status and prints a JSON error object on failure.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ..spec import validate, ValidationError
from ..spec.builder import _resolve_rhs_in_spec, build
from ..spec.lint import lint as spec_lint


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2))
    return code


# Fields that aren't user-interesting in a planned-feature summary --
# `type` and `name` are promoted to their own keys; underscore-prefixed
# fields (like `_comment`) are spec-author scaffolding.
_PLAN_HIDDEN_FIELDS = frozenset({"type", "name"})


def _plan_value(v: Any) -> Any:
    """Compact a spec field for plan output.

    Preserves `{"rhs": "..."}` objects as-is so the author can see which
    bindings were left parametric. Recurses into dicts/lists. Strips
    underscore-prefixed keys (comments, future `_expect` etc. — see P0.5)
    from nested dicts; top-level `_expect` is surfaced separately.
    """
    if isinstance(v, dict):
        if "rhs" in v and isinstance(v["rhs"], str):
            return {"rhs": v["rhs"]}
        return {k: _plan_value(x) for k, x in v.items() if not k.startswith("_")}
    if isinstance(v, list):
        return [_plan_value(x) for x in v]
    return v


def _plan_entry(feat: dict[str, Any]) -> dict[str, Any]:
    """One feature's row in the dry-run plan.

    `name` and `type` are promoted to top-level keys. Every other field
    is preserved under `params`. `_expect` (when present, see P0.5) is
    surfaced separately so authors can confirm the volume oracle they
    declared survives validation.
    """
    out: dict[str, Any] = {
        "name": feat["name"],
        "type": feat["type"],
        "params": {
            k: _plan_value(v)
            for k, v in feat.items()
            if k not in _PLAN_HIDDEN_FIELDS and not k.startswith("_")
        },
    }
    if "_expect" in feat:
        out["expect"] = feat["_expect"]
    return out


def _dry_run(spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve locals (catches rhs lookup errors) and emit a planned-feature list.

    Caller has already run `validate(spec)` and confirmed it passed.
    Locals resolution is best-effort: if it fails we report the failure
    but still return the un-resolved plan, because authors want to see
    BOTH "validation passed" AND "this rhs broke when I tried to resolve
    it." The two failure modes have different fixes.
    """
    feature_count = len(spec["features"])
    locals_status: dict[str, Any] = {
        "declared": bool(spec.get("locals")),
        "resolved": False,
        "error": None,
    }
    if spec.get("locals"):
        try:
            _ = _resolve_rhs_in_spec(spec)
            locals_status["resolved"] = True
        except Exception as exc:
            locals_status["error"] = f"{type(exc).__name__}: {exc}"
    return {
        "ok": locals_status["error"] is None,
        "dry_run": True,
        "spec_name": spec.get("name"),
        "schema_version": spec.get("schema_version"),
        "feature_count": feature_count,
        "locals": locals_status,
        "features": [_plan_entry(f) for f in spec["features"]],
    }


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
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help=(
            "Validate, resolve every {rhs} against the linked locals file, "
            "and dump a planned-feature list as JSON. Never boots SW. "
            "Catches the same lookup errors that today fire mid-build "
            "(missing var, cycle, syntax) without paying the ~30s SW "
            "boot cost per iteration. Strict superset of --validate-only."
        ),
    )
    parser.add_argument(
        "--lint",
        dest="lint",
        action="store_true",
        help=(
            "Run semantic lint checks after validation. Catches likely "
            "authoring mistakes (unconsumed sketches, missing center.z on "
            "Top Plane centerlines, center.z thread-through gaps) that "
            "pass schema validation but indicate a probable bug. Implies "
            "--dry-run unless a build mode is also selected. No SW needed."
        ),
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
    parser.add_argument(
        "--verify-mass",
        dest="verify_mass",
        action="store_true",
        help=(
            "After each feature, read the part volume via SW's "
            "CreateMassProperty and compare the delta against the "
            "feature's _expect.mass_delta_mm3 (if declared). Fails fast "
            "on mismatch. NOTE: adds one COM call per feature (~50ms each) "
            "which is noticeable on large specs."
        ),
    )
    parser.add_argument(
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Enable debug logging from the builder.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s"
        )
    else:
        logging.basicConfig(level=logging.WARNING)

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
        validate(spec, spec_path=p)
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

    # --lint runs semantic checks after validation. It implies --dry-run
    # unless a build mode (--no-dim, --deferred-dim) was also selected.
    lint_findings = spec_lint(spec)
    lint_payload = [f.to_dict() for f in lint_findings]

    if args.lint and not (args.no_dim or args.deferred_dim):
        # Lint-only mode: also run dry-run and include both outputs
        dry_run_payload = _dry_run(spec) if args.dry_run or args.lint else None
        payload: dict[str, Any] = {
            "ok": len(lint_findings) == 0,
            "lint": True,
            "findings": lint_payload,
            "finding_count": len(lint_findings),
        }
        if dry_run_payload is not None:
            payload["dry_run"] = dry_run_payload
        return _emit(payload, 0 if not lint_findings else 6)

    if args.dry_run:
        payload = _dry_run(spec)
        # Include lint findings if --lint was also passed
        if args.lint and lint_findings:
            payload["lint_findings"] = lint_payload
        # Exit 5 (distinct from validation=3 and build=4) on rhs-resolution
        # failure so CI can tell apart "spec is malformed" from "spec refs
        # missing vars in locals".
        return _emit(payload, 0 if payload["ok"] else 5)

    result = build(
        spec,
        no_dim=args.no_dim,
        deferred_dim=args.deferred_dim,
        save_as=args.save_as,
        verify_mass=args.verify_mass,
    )
    # BuildResult.to_dict() owns the wire format; CLI only adds CLI-level
    # context (here: which mode the caller picked).
    payload = result.to_dict()
    payload["no_dim"] = args.no_dim
    payload["deferred_dim"] = args.deferred_dim
    return _emit(payload, 0 if result.ok else 4)


if __name__ == "__main__":
    sys.exit(main())
