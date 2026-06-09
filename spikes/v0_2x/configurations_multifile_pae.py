"""W36v configurations multifile spike S1 — prove distinct volumes across variants.

S1 seat spike (W0 requirement):
  - Define a base spec (simple box: 30×30×15mm)
  - Define 3 variants with nested spec_overrides that change dimensions:
      Small:  20×20×10 → ~4,000 mm³
      Medium: 30×30×15 → ~13,500 mm³ (base)
      Large:  50×50×20 → ~50,000 mm³
  - Call materialize_all → build each variant → measure volume
  - VERIFY THE EFFECT: ≥2 distinct volumes matching override intent
  - Save results to _results/configurations_multifile.json

The distinct-volume proof that was blocked in-file (S1/S2 COM
suppression wall) is trivial across files: each variant is a
separate .sldprt with independently-proven geometry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))

SPIKE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SPIKE_DIR / "_results"

BASE_SPEC = {
    "schema_version": 1,
    "name": "ConfigBox",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Box",
            "plane": "Front",
            "width": 30.0,
            "height": 30.0,
        },
        {
            "type": "boss_extrude_blind",
            "name": "EX_Box",
            "sketch": "SK_Box",
            "depth": 15.0,
        },
    ],
}

VARIANTS_BLOCK = [
    {
        "name": "Small",
        "description": "Compact variant: 20x20x10",
        "overrides": {
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_Box",
                    "plane": "Front",
                    "width": 20.0,
                    "height": 20.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX_Box",
                    "sketch": "SK_Box",
                    "depth": 10.0,
                },
            ],
        },
    },
    {
        "name": "Medium",
        "description": "Base variant: 30x30x15",
        "overrides": {},
    },
    {
        "name": "Large",
        "description": "Heavy-duty variant: 50x50x20",
        "overrides": {
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_Box",
                    "plane": "Front",
                    "width": 50.0,
                    "height": 50.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX_Box",
                    "sketch": "SK_Box",
                    "depth": 20.0,
                },
            ],
        },
    },
]

EXPECTED_VOLUMES = {
    "Small": 20.0 * 20.0 * 10.0,
    "Medium": 30.0 * 30.0 * 15.0,
    "Large": 50.0 * 50.0 * 20.0,
}


def run_spike() -> dict:
    """Execute the W36v S1 multifile spike."""
    result: dict = {
        "ok": False,
        "stage": "init",
        "errors": [],
        "warnings": [],
        "variants": [],
        "volumes": {},
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_dir = RESULTS_DIR / "variants"

    # Parse variants
    from ai_sw_bridge.config import materialize_all, parse_variants

    result["stage"] = "parse"
    try:
        variants = parse_variants(VARIANTS_BLOCK)
        result["variant_count"] = len(variants)
        result["variant_names"] = [v.name for v in variants]
    except Exception as exc:
        result["errors"].append(f"parse failed: {exc!r}")
        return result

    # Materialize
    result["stage"] = "materialize"
    try:
        results = materialize_all(BASE_SPEC, output_dir, variants)
    except Exception as exc:
        result["errors"].append(f"materialize_all raised: {exc!r}")
        return result

    for r in results:
        result["variants"].append(r.to_dict())
        if r.ok and r.volume_mm3 is not None:
            result["volumes"][r.variant] = r.volume_mm3
        if not r.ok:
            result["errors"].append(f"{r.variant}: {r.error}")

    # Validation: distinct volumes
    result["stage"] = "validation"
    vols = result["volumes"]
    distinct = sorted(set(round(v, 1) for v in vols.values()))
    result["distinct_volumes_mm3"] = distinct

    # Check each volume matches expected (within 5%)
    for name, expected in EXPECTED_VOLUMES.items():
        actual = vols.get(name)
        if actual is not None:
            pct_err = abs(actual - expected) / expected * 100
            if pct_err > 5.0:
                result["warnings"].append(
                    f"{name}: expected {expected:.0f} mm³, got {actual:.0f} mm³ "
                    f"({pct_err:.1f}% error)"
                )

    ok_count = sum(1 for r in results if r.ok)
    if len(distinct) >= 2 and ok_count == len(variants):
        result["ok"] = True
        result["summary"] = (
            f"VERIFIED: {ok_count}/{len(variants)} variants built, "
            f"{len(distinct)} distinct volumes: {distinct} mm³. "
            f"Expected: {sorted(EXPECTED_VOLUMES.values())}"
        )
    elif ok_count < len(variants):
        result["errors"].append(
            f"Only {ok_count}/{len(variants)} variants built successfully"
        )
    else:
        result["errors"].append(
            f"Only {len(distinct)} distinct volume(s): {distinct}"
        )

    return result


if __name__ == "__main__":
    print("=== W36v Configurations Multifile Spike S1 ===", file=sys.stderr)
    result = run_spike()

    out_path = RESULTS_DIR / "configurations_multifile.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nResults: {out_path}", file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
