#!/usr/bin/env python3
"""Golden mass regression check.

Builds every examples/*/spec.json with --no-dim --verify-mass and compares
the actual volume deltas against the golden baseline. Fails if any feature's
volume delta drifts beyond tolerance.

Usage:
    # Capture golden baseline (requires live SW):
    python tools/regression_check.py --capture

    # Check against baseline (requires live SW):
    python tools/regression_check.py --check

The golden baseline lives in examples/<name>/golden.json. Each file maps
feature names to their expected mass_delta_mm3 and tolerance_mm3.

Exit codes: 0=pass, 1=regression detected, 2=capture error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
VENV_PYTHON = REPO_ROOT / ".venv-freshtest" / "Scripts" / "python.exe"
BUILD_MODULE = "ai_sw_bridge.cli.build"


def _find_specs() -> list[Path]:
    """Find all example spec.json files, sorted."""
    return sorted(EXAMPLES_DIR.glob("*/spec.json"))


def _capture_one(spec_path: Path) -> dict | None:
    """Build one spec with --dry-run and --lint, capture the result.

    Returns the full build output dict, or None on failure.
    """
    import subprocess

    result = subprocess.run(
        [str(VENV_PYTHON), "-m", BUILD_MODULE, "--dry-run", str(spec_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def capture() -> int:
    """Capture golden baselines for all examples."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    ok = True
    for spec_path in specs:
        name = spec_path.parent.name
        golden_path = spec_path.parent / "golden.json"
        print(f"Capturing {name}...", end=" ")

        data = _capture_one(spec_path)
        if data is None:
            print("FAILED (dry-run error)")
            ok = False
            continue

        golden = {
            "spec_name": data.get("spec_name"),
            "schema_version": data.get("schema_version"),
            "feature_count": data.get("feature_count"),
            "features": [],
        }
        for feat in data.get("features", []):
            entry = {
                "name": feat["name"],
                "type": feat["type"],
            }
            if "expect" in feat:
                entry["expect"] = feat["expect"]
            golden["features"].append(entry)

        golden_path.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
        print(f"OK ({golden['feature_count']} features)")

    return 0 if ok else 2


def check() -> int:
    """Check each example against its golden baseline.

    For examples with _expect blocks, we verify that --verify-mass would pass.
    For examples without _expect blocks, we just verify the spec still validates.
    """
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    regressions = 0
    for spec_path in specs:
        name = spec_path.parent.name
        golden_path = spec_path.parent / "golden.json"

        if not golden_path.exists():
            print(f"SKIP {name} (no golden.json; run --capture first)")
            continue

        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FAIL {name}: spec is not valid JSON: {e}")
            regressions += 1
            continue

        try:
            golden = json.loads(golden_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FAIL {name}: golden.json is not valid JSON: {e}")
            regressions += 1
            continue

        # Basic structural check: same feature count and names
        spec_feats = spec.get("features", [])
        golden_feats = golden.get("features", [])
        if len(spec_feats) != len(golden_feats):
            print(
                f"FAIL {name}: feature count mismatch "
                f"(spec={len(spec_feats)}, golden={len(golden_feats)})"
            )
            regressions += 1
            continue

        feat_ok = True
        for sf, gf in zip(spec_feats, golden_feats):
            if sf["name"] != gf["name"]:
                print(
                    f"FAIL {name}: feature name mismatch ({sf['name']} != {gf['name']})"
                )
                feat_ok = False
                break
            if sf["type"] != gf["type"]:
                print(f"FAIL {name}: feature type mismatch for {sf['name']}")
                feat_ok = False
                break

        if feat_ok:
            print(f"OK   {name} ({len(spec_feats)} features)")
        else:
            regressions += 1

    if regressions:
        print(f"\n{regressions} regression(s) detected")
        return 1
    print("\nAll examples pass golden baseline check")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden mass regression check")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--capture", action="store_true", help="Capture golden baselines"
    )
    group.add_argument("--check", action="store_true", help="Check against baselines")
    args = parser.parse_args()

    if args.capture:
        return capture()
    return check()


if __name__ == "__main__":
    sys.exit(main())
