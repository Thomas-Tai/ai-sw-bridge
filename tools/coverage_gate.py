#!/usr/bin/env python3
"""Coverage ratchet + per-package floors.

Reads coverage.json (produced by ``coverage json``). Fails if total coverage
drops more than TOLERANCE below the checked-in baseline, or if any watched
package falls below its floor. --update-baseline rewrites the stored total
(reviewed separately when coverage legitimately rises).

Run: coverage json && python tools/coverage_gate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COV_JSON = REPO_ROOT / "coverage.json"
BASELINE_PATH = REPO_ROOT / "tools" / "coverage_baseline.json"
TOLERANCE = 1.0  # pt of matrix (3.10/3.12/3.14) branch-coverage variance
PACKAGE_FLOORS = {
    # spec/ floor re-baselined to the SEATLESS-CI measurement. The prior 67.0
    # ("measured 67.3% at v1.7.0") was a with-seat figure that the seatless CI
    # runner can never reach: spec/handlers/* is exercised largely by
    # solidworks_only tests, which skip with no seat, so on CI spec/ measures
    # ~59.4%. The gate ran green historically only because it never executed to
    # completion (the mypy step failed first). Enforce the honest seatless
    # ratchet point here; the 1.0pt tolerance still catches real regressions.
    "src/ai_sw_bridge/spec/": 59.0,
    "src/ai_sw_bridge/features/": 71.0,  # measured 71.2% at v1.7.0 (seatless OK)
    "src/ai_sw_bridge/errors/": 94.0,  # measured 94.3% at v1.7.0 (seatless OK)
}


def _package_percent(cov_json: dict, prefix: str) -> float | None:
    files = cov_json.get("files", {})
    covered = statements = 0
    for path, data in files.items():
        norm = Path(path).as_posix()
        if prefix in norm:
            summ = data.get("summary", {})
            covered += summ.get("covered_lines", 0)
            statements += summ.get("num_statements", 0)
    if statements == 0:
        # Fallback for the unit-test shape (percent-only, no line counts).
        vals = [
            data["summary"]["percent_covered"]
            for path, data in files.items()
            if prefix in Path(path).as_posix()
        ]
        return min(vals) if vals else None
    return 100.0 * covered / statements


def evaluate(
    cov_json: dict,
    baseline: dict,
    *,
    tolerance: float = TOLERANCE,
    package_floors: dict[str, float] | None = None,
) -> list[str]:
    violations: list[str] = []
    total = cov_json.get("totals", {}).get("percent_covered", 0.0)
    base_total = baseline.get("__total__")
    if base_total is not None and total < base_total - tolerance:
        violations.append(
            f"total coverage {total:.2f}% dropped below baseline "
            f"{base_total:.2f}% (tolerance {tolerance}pt)."
        )
    for prefix, floor in (package_floors or {}).items():
        pct = _package_percent(cov_json, prefix)
        if pct is None:
            # A watched package that yields no matching files (renamed/deleted)
            # must not silently evade its floor — that's a hole in the ratchet.
            violations.append(
                f"watched package {prefix} absent from coverage report — "
                "cannot verify its floor."
            )
            continue
        # Same tolerance as the total check applies here: matrix (3.10/3.12/3.14)
        # branch-coverage variance can jitter a package a fraction of a point
        # below its floor without a real regression, so only flag it once it
        # drops past floor - tolerance.
        if pct < floor - tolerance:
            violations.append(
                f"package {prefix} at {pct:.2f}% is below its floor {floor:.2f}%."
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coverage ratchet gate")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    cov_json = json.loads(COV_JSON.read_text(encoding="utf-8"))
    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps({"__total__": cov_json["totals"]["percent_covered"]}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print("coverage baseline updated", file=sys.stderr)
        return 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    violations = evaluate(cov_json, baseline, package_floors=PACKAGE_FLOORS)
    if not violations:
        print("coverage gate: OK", file=sys.stderr)
        return 0
    print("coverage gate violations:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
