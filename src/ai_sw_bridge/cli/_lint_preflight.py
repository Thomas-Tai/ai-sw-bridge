"""Seat-free lint + geometric pre-flight response assembly for ``ai-sw-build``.

Behavior-preserving extraction from ``cli/build.py`` (which is grandfathered
shrink-only in ``tools/module_size_baseline.json``). Owns the seat-free
``--lint`` / ``--dry-run`` response path: assembling semantic-lint plus
geometric pre-flight findings and building the JSON payload + exit code. No
SOLIDWORKS / COM is required by anything here.

See ``docs/superpowers/plans/2026-08-18-geometric-preflight.md``.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..spec.lint import LintFinding, lint as spec_lint


def assemble_lint_findings(
    spec: dict[str, Any], *, no_preflight: bool
) -> tuple[list[LintFinding], list[dict[str, Any]], bool, dict[str, Any]]:
    """Run semantic lint and (unless suppressed) the geometric pre-flight.

    Returns ``(findings, findings_as_dicts, has_error, coverage)`` where
    ``has_error`` is True iff any finding is ERROR severity (the ERROR-only
    exit-gating contract) and ``coverage`` summarizes how much of the spec the
    geometric pre-flight modeled.

    When ``no_preflight`` suppresses the pre-flight entirely, coverage reports
    zero modeled features and ``complete: False`` -- nothing was checked, and
    saying so is the honest answer. It must not read as a clean bill of health.
    """
    findings = spec_lint(spec)
    if not no_preflight:
        from ..spec.preflight import coverage as preflight_coverage
        from ..spec.preflight import preflight

        pre = preflight(spec)
        findings = findings + pre
        cov = preflight_coverage(spec, pre)
    else:
        solid_ops = sum(
            1
            for f in spec.get("features", [])
            if not str(f.get("type", "")).startswith("sketch_")
        )
        cov = {
            "total": solid_ops,
            "modeled": 0,
            "skipped": solid_ops,
            "skipped_types": [],
            "complete": False,
        }
    findings_dicts = [f.to_dict() for f in findings]
    has_error = any(f.severity == "error" for f in findings)
    return findings, findings_dicts, has_error, cov


def lint_dryrun_response(
    spec: dict[str, Any],
    args: Any,
    dry_run: Callable[[dict[str, Any]], dict[str, Any]],
) -> Optional[tuple[dict[str, Any], int]]:
    """Build ``(payload, exit_code)`` for a seat-free ``--lint`` / ``--dry-run`` request.

    Returns ``None`` when the request is neither lint-only nor dry-run (the
    caller should then proceed to an actual build). Behavior-preserving
    extraction of ``build.py``'s former inline lint/dry-run response block.
    """
    # An actual build (a mode selected without lint-only, and no --dry-run) has
    # no seat-free response here -- return early BEFORE the pure lint+pre-flight
    # pass rather than compute and discard it.
    lint_only = args.lint and not (args.no_dim or args.deferred_dim)
    if not (lint_only or args.dry_run):
        return None

    findings, findings_dicts, has_error, cov = assemble_lint_findings(
        spec, no_preflight=getattr(args, "no_preflight", False)
    )

    # Lint-only mode: implies --dry-run unless a build mode was also selected.
    if lint_only:
        dry_run_payload = dry_run(spec) if args.dry_run or args.lint else None
        payload: dict[str, Any] = {
            "ok": not has_error,
            "lint": True,
            "findings": findings_dicts,
            "finding_count": len(findings),
            "error_count": sum(1 for f in findings if f.severity == "error"),
            "warning_count": sum(1 for f in findings if f.severity == "warning"),
            "coverage": cov,
        }
        if dry_run_payload is not None:
            payload["dry_run"] = dry_run_payload
        return payload, 0 if not has_error else 6

    # Reached only when args.dry_run is True (guaranteed by the early return).
    payload = dry_run(spec)
    # Include lint findings if --lint was also passed
    if args.lint and findings:
        payload["lint_findings"] = findings_dicts
    # Exit 5 (distinct from validation=3 and build=4) on rhs-resolution
    # failure so CI can tell apart "spec is malformed" from "spec refs
    # missing vars in locals".
    return payload, 0 if payload["ok"] else 5
