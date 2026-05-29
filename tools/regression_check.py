#!/usr/bin/env python3
"""Golden volume regression check with SLI instrumentation.

Builds every examples/*/spec.json on the running SOLIDWORKS session in
``--no-dim --verify-mass`` mode and records the resulting total part volume
(mm^3 -- the field is named ``total_mass_mm3`` for consistency with the
spec's ``_expect.mass_delta_mm3``) plus the per-feature volume deltas to
examples/<name>/golden.json. ``--check`` rebuilds and fails if any total
drifts beyond tolerance.

Both modes require a running SOLIDWORKS (enhancement plan P1.2). Wire
``--check`` as a manual nightly job -- there is no Windows+SW CI runner.

SLI instrumentation (v0.11, spec.md §8.3):
  - Captures wall-clock time per spec build.
  - Computes p50/p95/p99 latency percentiles.
  - ``--baseline-compare <path>`` fails when p95 regresses by >15% or
    p99 by >25% vs the baseline.
  - SLO-01: p95 < 12 s hard-fail.  SLO-02: p99 < 25 s hard-fail.
  - ``--write-baseline <path>`` writes the percentile JSON for future
    comparison (CI gated by ``perf-baseline-bump`` PR label).

    python tools/regression_check.py --capture   # record golden baselines
    python tools/regression_check.py --check      # verify against baselines
    python tools/regression_check.py --check --baseline-compare tools/perf_baselines/v0.10.json

Exit codes: 0=pass, 1=regression detected, 2=capture/build error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
BUILD_MODULE = "ai_sw_bridge.cli.build"

# Default acceptable drift for a part's total volume between builds (mm^3).
DEFAULT_TOLERANCE_MM3 = 50.0

# SLO thresholds (spec.md §8.3, requirements.md §3.5).
SLO_01_P95_MAX_S = 12.0
SLO_02_P99_MAX_S = 25.0

# Baseline regression thresholds (spec.md §8.3).
BASELINE_P95_REGRESSION_PCT = 0.15
BASELINE_P99_REGRESSION_PCT = 0.25


def hash_brep_manifest(manifest_dict: dict) -> str:
    """Stable SHA-256 hash over all face fingerprints in a brep manifest.

    Reads the pre-computed 'fingerprint' field from every face of every
    feature, sorts the collected fingerprints (order-independent across
    features and faces within a feature), then SHA-256-hashes the sorted
    list serialised as canonical JSON.

    Returns a 64-char lowercase hex digest. An empty or fingerprint-free
    manifest hashes to the SHA-256 of '[]'.

    The input shape matches ``Manifest.to_dict()`` and ``build_brep.json``:
    ``{"schema_version": 1, "features": [{"feature": "...", "faces": [...]}]}``.
    Faces without a 'fingerprint' key are silently skipped (error features).
    """
    fps: list[str] = []
    for feature in manifest_dict.get("features", []):
        for face in feature.get("faces", []):
            fp = face.get("fingerprint")
            if fp is not None:
                fps.append(fp)
    fps.sort()
    blob = json.dumps(fps, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def check_geometry_drift(spec_dir: Path, manifest_dict: dict) -> bool:
    """Compare computed brep hash against the stored golden_brep_hash.json.

    Returns True when no golden exists (opt-in skip) or the hash matches.
    Returns False and prints a diagnostic to stderr when the hash drifts.

    The golden file lives at ``spec_dir/golden_brep_hash.json`` and is
    written by the ``--capture`` mode on a live SOLIDWORKS seat.
    """
    golden_path = spec_dir / "golden_brep_hash.json"
    if not golden_path.exists():
        return True
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    stored = golden.get("brep_hash", "")
    computed = hash_brep_manifest(manifest_dict)
    if computed == stored:
        return True
    print(
        f"FAIL geometry drift in {spec_dir.name}: "
        f"computed={computed!r} expected={stored!r}",
        file=sys.stderr,
    )
    return False


def _find_specs() -> list[Path]:
    """All example spec.json files, sorted by directory name."""
    return sorted(EXAMPLES_DIR.glob("*/spec.json"))


def _build_with_mass(spec_path: Path) -> tuple[dict | None, float]:
    """Build one spec via `ai-sw-build --no-dim --verify-mass` on live SW.

    Returns (parsed JSON result, wall-clock seconds). On failure the
    result is None and the elapsed time is still returned for SLI tracking.
    """
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                BUILD_MODULE,
                str(spec_path),
                "--no-dim",
                "--verify-mass",
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        return None, elapsed
    elapsed = time.monotonic() - t0
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, elapsed
    return (data if data.get("ok") else None), elapsed


def _total_mass_and_features(data: dict) -> tuple[float, list[dict]]:
    """Total volume (mm^3) and per-feature deltas from a --verify-mass result.

    The per-feature actual_mm3 deltas telescope to the part's total volume
    (sketches contribute 0, bosses add, cuts subtract).
    """
    mv = data.get("mass_verification") or []
    features = [
        {"name": e.get("feature"), "actual_mm3": e.get("actual_mm3")} for e in mv
    ]
    total = round(sum(e.get("actual_mm3") or 0.0 for e in mv), 2)
    return total, features


def _compute_percentiles(times: list[float]) -> dict[str, float | None]:
    """Compute p50/p95/p99 from a list of wall-clock times (seconds).

    Returns dict with p50/p95/p99 keys. Returns None values when fewer
    than 1 data point is available.
    """
    if not times:
        return {"p50": None, "p95": None, "p99": None}
    sorted_times = sorted(times)
    if len(sorted_times) == 1:
        v = sorted_times[0]
        return {"p50": round(v, 3), "p95": round(v, 3), "p99": round(v, 3)}
    quantiles = statistics.quantiles(sorted_times, n=100, method="inclusive")
    # quantiles returns 99 cut points; index i-1 gives the i-th percentile
    return {
        "p50": round(quantiles[49], 3),
        "p95": round(quantiles[94], 3),
        "p99": round(quantiles[98], 3),
    }


def _make_perf_payload(
    percentiles: dict[str, float | None],
    n_specs: int,
    spec_times: list[float],
) -> dict:
    """Build the perf baseline JSON payload."""
    return {
        "version": "v0.10",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "p50": percentiles["p50"],
        "p95": percentiles["p95"],
        "p99": percentiles["p99"],
        "n_specs": n_specs,
        "host_meta": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "spec_times": [round(t, 3) for t in spec_times],
    }


def _check_slo_and_baseline(
    percentiles: dict[str, float | None],
    baseline_path: Path | None,
) -> bool:
    """Check SLO-01/02 thresholds and optional baseline regression.

    Returns True if all checks pass.
    """
    ok = True
    p95 = percentiles.get("p95")
    p99 = percentiles.get("p99")

    # SLO-01: p95 < 12 s
    if p95 is not None and p95 > SLO_01_P95_MAX_S:
        ok = False
        print(
            f"FAIL SLO-01: p95 = {p95:.3f}s exceeds {SLO_01_P95_MAX_S}s",
            file=sys.stderr,
        )
    # SLO-02: p99 < 25 s
    if p99 is not None and p99 > SLO_02_P99_MAX_S:
        ok = False
        print(
            f"FAIL SLO-02: p99 = {p99:.3f}s exceeds {SLO_02_P99_MAX_S}s",
            file=sys.stderr,
        )

    # Baseline comparison
    if baseline_path is not None and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        bp95 = baseline.get("p95")
        bp99 = baseline.get("p99")
        if p95 is not None and bp95 is not None:
            if p95 > bp95 * (1 + BASELINE_P95_REGRESSION_PCT):
                ok = False
                print(
                    f"FAIL baseline p95 regression: {p95:.3f}s vs baseline {bp95:.3f}s "
                    f"(>{BASELINE_P95_REGRESSION_PCT:.0%} drift)",
                    file=sys.stderr,
                )
        if p99 is not None and bp99 is not None:
            if p99 > bp99 * (1 + BASELINE_P99_REGRESSION_PCT):
                ok = False
                print(
                    f"FAIL baseline p99 regression: {p99:.3f}s vs baseline {bp99:.3f}s "
                    f"(>{BASELINE_P99_REGRESSION_PCT:.0%} drift)",
                    file=sys.stderr,
                )
    return ok


def capture(
    write_baseline: Path | None = None,
    baseline_compare: Path | None = None,
) -> int:
    """Build every example and record its golden baseline."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    ok = True
    spec_times: list[float] = []
    for spec_path in specs:
        name = spec_path.parent.name
        print(f"Capturing {name}...", end=" ", flush=True)
        data, elapsed = _build_with_mass(spec_path)
        spec_times.append(elapsed)
        if data is None:
            print(f"FAILED (build error, {elapsed:.1f}s)")
            ok = False
            continue
        total, features = _total_mass_and_features(data)
        golden = {
            "spec_name": data.get("spec_name") or data.get("name"),
            "feature_count": len(data.get("features_built", [])),
            "equation_count": len(data.get("bindings_added", [])),
            "total_mass_mm3": total,
            "tolerance_mm3": DEFAULT_TOLERANCE_MM3,
            "features": features,
        }
        (spec_path.parent / "golden.json").write_text(
            json.dumps(golden, indent=2) + "\n", encoding="utf-8"
        )
        print(f"OK ({golden['feature_count']} features, {total} mm^3, {elapsed:.1f}s)")

    percentiles = _compute_percentiles(spec_times)
    print(
        f"\nSLI: p50={percentiles['p50']}s p95={percentiles['p95']}s p99={percentiles['p99']}s ({len(spec_times)} specs)"
    )

    if not _check_slo_and_baseline(percentiles, baseline_compare):
        ok = False

    if write_baseline is not None:
        payload = _make_perf_payload(percentiles, len(specs), spec_times)
        write_baseline.parent.mkdir(parents=True, exist_ok=True)
        write_baseline.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Baseline written to {write_baseline}", file=sys.stderr)

    return 0 if ok else 2


def check(
    baseline_compare: Path | None = None,
) -> int:
    """Rebuild every example and compare its total volume to the baseline."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    regressions = 0
    checked = 0
    spec_times: list[float] = []
    for spec_path in specs:
        name = spec_path.parent.name
        golden_path = spec_path.parent / "golden.json"
        if not golden_path.exists():
            print(f"SKIP {name} (no golden.json; run --capture first)")
            continue
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        data, elapsed = _build_with_mass(spec_path)
        spec_times.append(elapsed)
        if data is None:
            print(f"FAIL {name}: build error ({elapsed:.1f}s)")
            regressions += 1
            continue
        checked += 1
        total, _ = _total_mass_and_features(data)
        expected = golden.get("total_mass_mm3", 0.0)
        tol = golden.get("tolerance_mm3", DEFAULT_TOLERANCE_MM3)
        if abs(total - expected) > tol:
            print(
                f"FAIL {name}: total {total} mm^3 vs golden {expected} mm^3 "
                f"(tolerance +/-{tol}, {elapsed:.1f}s)"
            )
            regressions += 1
        else:
            print(f"OK   {name} ({total} mm^3, {elapsed:.1f}s)")

    percentiles = _compute_percentiles(spec_times)
    print(
        f"\nSLI: p50={percentiles['p50']}s p95={percentiles['p95']}s p99={percentiles['p99']}s ({len(spec_times)} specs)"
    )

    slo_ok = _check_slo_and_baseline(percentiles, baseline_compare)

    if regressions:
        print(f"\n{regressions} regression(s) detected")
        return 1
    if not slo_ok:
        return 1
    print(f"\nAll {checked} checked example(s) within tolerance")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Golden volume regression check with SLI instrumentation"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--capture", action="store_true", help="Record golden baselines (live SW)"
    )
    group.add_argument(
        "--check", action="store_true", help="Verify against baselines (live SW)"
    )
    parser.add_argument(
        "--baseline-compare",
        dest="baseline_compare",
        type=Path,
        default=None,
        help="Path to a perf baseline JSON to compare against (p95/p99 regression check).",
    )
    parser.add_argument(
        "--write-baseline",
        dest="write_baseline",
        type=Path,
        default=None,
        help="Path to write the current perf baseline JSON after the run.",
    )
    args = parser.parse_args()
    if args.capture:
        return capture(
            write_baseline=args.write_baseline, baseline_compare=args.baseline_compare
        )
    return check(baseline_compare=args.baseline_compare)


if __name__ == "__main__":
    sys.exit(main())
