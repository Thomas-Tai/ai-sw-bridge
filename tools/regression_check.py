#!/usr/bin/env python3
"""Golden volume regression check.

Builds every examples/*/spec.json on the running SOLIDWORKS session in
``--no-dim --verify-mass`` mode and records the resulting total part volume
(mm^3 -- the field is named ``total_mass_mm3`` for consistency with the
spec's ``_expect.mass_delta_mm3``) plus the per-feature volume deltas to
examples/<name>/golden.json. ``--check`` rebuilds and fails if any total
drifts beyond tolerance.

Both modes require a running SOLIDWORKS (enhancement plan P1.2). Wire
``--check`` as a manual nightly job -- there is no Windows+SW CI runner.

    python tools/regression_check.py --capture   # record golden baselines
    python tools/regression_check.py --check      # verify against baselines

golden.json shape:
    {
      "spec_name": ..., "feature_count": N, "equation_count": 0,
      "total_mass_mm3": ..., "tolerance_mm3": 50.0,
      "features": [{"name": ..., "actual_mm3": ...}, ...]
    }

Exit codes: 0=pass, 1=regression detected, 2=capture/build error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
VENV_PYTHON = REPO_ROOT / ".venv-freshtest" / "Scripts" / "python.exe"
BUILD_MODULE = "ai_sw_bridge.cli.build"

# Default acceptable drift for a part's total volume between builds (mm^3).
DEFAULT_TOLERANCE_MM3 = 50.0


def _find_specs() -> list[Path]:
    """All example spec.json files, sorted by directory name."""
    return sorted(EXAMPLES_DIR.glob("*/spec.json"))


def _build_with_mass(spec_path: Path) -> dict | None:
    """Build one spec via `ai-sw-build --no-dim --verify-mass` on live SW.

    Returns the parsed JSON result on success, or None if the build failed
    (non-ok result, non-JSON output, or timeout).
    """
    try:
        result = subprocess.run(
            [
                str(VENV_PYTHON),
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
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if data.get("ok") else None


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


def capture() -> int:
    """Build every example and record its golden baseline."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    ok = True
    for spec_path in specs:
        name = spec_path.parent.name
        print(f"Capturing {name}...", end=" ", flush=True)
        data = _build_with_mass(spec_path)
        if data is None:
            print("FAILED (build error)")
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
        print(f"OK ({golden['feature_count']} features, {total} mm^3)")
    return 0 if ok else 2


def check() -> int:
    """Rebuild every example and compare its total volume to the baseline."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    regressions = 0
    checked = 0
    for spec_path in specs:
        name = spec_path.parent.name
        golden_path = spec_path.parent / "golden.json"
        if not golden_path.exists():
            print(f"SKIP {name} (no golden.json; run --capture first)")
            continue
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        data = _build_with_mass(spec_path)
        if data is None:
            print(f"FAIL {name}: build error")
            regressions += 1
            continue
        checked += 1
        total, _ = _total_mass_and_features(data)
        expected = golden.get("total_mass_mm3", 0.0)
        tol = golden.get("tolerance_mm3", DEFAULT_TOLERANCE_MM3)
        if abs(total - expected) > tol:
            print(
                f"FAIL {name}: total {total} mm^3 vs golden {expected} mm^3 "
                f"(tolerance +/-{tol})"
            )
            regressions += 1
        else:
            print(f"OK   {name} ({total} mm^3)")

    if regressions:
        print(f"\n{regressions} regression(s) detected")
        return 1
    print(f"\nAll {checked} checked example(s) within tolerance")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden volume regression check")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--capture", action="store_true", help="Record golden baselines (live SW)"
    )
    group.add_argument(
        "--check", action="store_true", help="Verify against baselines (live SW)"
    )
    args = parser.parse_args()
    return capture() if args.capture else check()


if __name__ == "__main__":
    sys.exit(main())
